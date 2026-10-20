"""Хранилище сессий и изоляция клиентов с персистентностью в SQLite (schrot47_bot).
Гарантирует:
1. Полную изоляцию клиентов по нормализованному номеру телефона (remoteJid).
2. Персистентность сессий и сообщений при перезапуске процесса бота.
3. Отслеживание режима перехвата человеком (`human_mode=True`) — при ответе менеджера бот замолкает.
4. Идемпотентность и дедупликацию входящих webhook-сообщений.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

DEFAULT_TTL_SECONDS = 24 * 3600  # 24 часа неактивности
MAX_HISTORY_MESSAGES = 20


@dataclass
class ClientSession:
    session_id: str
    phone: str
    push_name: str
    human_mode: bool
    started_at: float
    last_activity: float
    context: dict[str, Any]


class SessionManager:
    def __init__(self, db_path: str = "schrot47_bot.db", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.db_path = db_path
        self.ttl = ttl_seconds
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    phone TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    push_name TEXT,
                    human_mode INTEGER NOT NULL DEFAULT 0,
                    started_at REAL NOT NULL,
                    last_activity REAL NOT NULL,
                    context_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (phone) REFERENCES sessions(phone)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency (
                    provider_message_id TEXT PRIMARY KEY,
                    received_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS handoffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
                """
            )
            conn.commit()

    def is_duplicate_and_record(self, provider_message_id: str) -> bool:
        """Проверка дедупликации: возвращает True если сообщение уже обрабатывалось."""
        now = time.time()
        with self._lock, self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO idempotency (provider_message_id, received_at) VALUES (?, ?)",
                    (provider_message_id, now),
                )
                conn.commit()
                return False
            except sqlite3.IntegrityError:
                return True

    def get_or_create_session(self, phone: str, push_name: str = "") -> ClientSession:
        """Получение активной сессии клиента или создание новой с изоляцией по номеру телефона."""
        now = time.time()
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE phone = ?", (phone,)).fetchone()
            if row:
                last = row["last_activity"]
                # Проверка TTL: если прошло больше 24ч, сбрасываем контекст сессии
                if now - last > self.ttl:
                    session_id = uuid.uuid4().hex
                    conn.execute(
                        """
                        UPDATE sessions
                        SET session_id = ?, push_name = ?, human_mode = 0,
                            started_at = ?, last_activity = ?, context_json = '{}'
                        WHERE phone = ?
                        """,
                        (session_id, push_name or row["push_name"], now, now, phone),
                    )
                    conn.commit()
                    return ClientSession(session_id, phone, push_name or row["push_name"], False, now, now, {})

                # Обновляем last_activity
                conn.execute(
                    """
                    UPDATE sessions
                    SET last_activity = ?, push_name = COALESCE(NULLIF(?, ''), push_name)
                    WHERE phone = ?
                    """,
                    (now, push_name, phone),
                )
                conn.commit()
                ctx = json.loads(row["context_json"])
                return ClientSession(
                    row["session_id"],
                    phone,
                    push_name or row["push_name"],
                    bool(row["human_mode"]),
                    row["started_at"],
                    now,
                    ctx,
                )

            # Создаём новую сессию
            session_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO sessions (phone, session_id, push_name, human_mode, started_at, last_activity, context_json)
                VALUES (?, ?, ?, 0, ?, ?, '{}')
                """,
                (phone, session_id, push_name, now, now),
            )
            conn.commit()
            return ClientSession(session_id, phone, push_name, False, now, now, {})

    def add_message(self, phone: str, session_id: str, role: str, content: str) -> None:
        """Добавление реплики в историю диалога с клиентом."""
        now = time.time()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (phone, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                (phone, session_id, role, content, now),
            )
            conn.execute("UPDATE sessions SET last_activity = ? WHERE phone = ?", (now, phone))
            conn.commit()

    def get_history(self, phone: str, limit: int = MAX_HISTORY_MESSAGES) -> list[dict[str, str]]:
        """Получение последних N сообщений конкретного клиента (полная изоляция от других)."""
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content FROM messages
                WHERE phone = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (phone, limit),
            ).fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def set_human_mode(self, phone: str, enabled: bool) -> None:
        """Переключение режима ручного управления (human handoff)."""
        now = time.time()
        val = 1 if enabled else 0
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (phone, session_id, push_name, human_mode, started_at, last_activity, context_json)
                VALUES (?, ?, '', ?, ?, ?, '{}')
                ON CONFLICT(phone) DO UPDATE
                SET human_mode = excluded.human_mode, last_activity = excluded.last_activity
                """,
                (phone, uuid.uuid4().hex, val, now, now),
            )
            conn.commit()

    def is_human_mode(self, phone: str) -> bool:
        """Проверка: перехвачен ли диалог живым менеджером."""
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT human_mode FROM sessions WHERE phone = ?", (phone,)).fetchone()
            return bool(row["human_mode"]) if row else False

    def record_handoff(self, phone: str, session_id: str, reason: str) -> None:
        """Фиксация эскалации на менеджера и активация human_mode."""
        now = time.time()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "INSERT INTO handoffs (phone, session_id, reason, created_at, status) VALUES (?, ?, ?, ?, 'pending')",
                (phone, session_id, reason, now),
            )
            conn.commit()
        self.set_human_mode(phone, True)

    def update_context(self, phone: str, updates: dict[str, Any]) -> None:
        """Обновление контекстных переменных сессии клиента."""
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT context_json FROM sessions WHERE phone = ?", (phone,)).fetchone()
            if row:
                ctx = json.loads(row["context_json"])
                ctx.update(updates)
                conn.execute("UPDATE sessions SET context_json = ? WHERE phone = ?", (json.dumps(ctx), phone))
                conn.commit()
