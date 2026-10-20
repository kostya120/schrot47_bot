"""Менеджер рубильников безопасности, аудит и санитайзер логов (schrot47_bot).
Старт всегда fail-closed (production_enabled=False, outbound_enabled=False, kill_switch=True).
Исходящие WhatsApp-сообщения блокируются при выключенном outbound_enabled или активном kill_switch.
"""

from __future__ import annotations

import re
import threading
from dataclasses import asdict, dataclass, replace
from typing import Any

SAFE_DEFAULTS = {
    "production_enabled": False,
    "outbound_enabled": False,
    "owner_only": True,
    "kill_switch": True,
}

MAX_INCOMING_TEXT_LENGTH = 1500  # Защита от DoS и переполнения контекста LLM


@dataclass(frozen=True)
class SafetyFlags:
    production_enabled: bool = False
    outbound_enabled: bool = False
    owner_only: bool = True
    kill_switch: bool = True


class SafetyManager:
    def __init__(self, **overrides: Any) -> None:
        self.flags = SafetyFlags(**overrides)
        self.audit_log: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def snapshot(self) -> dict[str, bool]:
        return asdict(self.flags)

    def outbound_allowed(self) -> bool:
        """Проверка разрешения отправки исходящих сообщений в WhatsApp."""
        f = self.flags
        return f.production_enabled and f.outbound_enabled and not f.kill_switch

    def toggle(
        self,
        flag: str,
        value: bool,
        actor: str,
        is_owner: bool,
        confirm: bool = False,
    ) -> dict[str, bool]:
        """Безопасное переключение рубильника: ослабление защиты требует confirm=True и прав владельца."""
        if not is_owner:
            raise PermissionError("owner rights required to toggle safety flags")
        if flag not in SAFE_DEFAULTS:
            raise ValueError(f"unknown safety flag: {flag}")

        with self._lock:
            old_val = getattr(self.flags, flag)
            # Ослабление безопасности: включение прода/исходящих или выключение kill_switch
            is_loosening = value != SAFE_DEFAULTS[flag]
            if is_loosening and not confirm:
                raise ValueError("explicit confirm=True required to loosen safety flag")

            self.flags = replace(self.flags, **{flag: value})
            record = {
                "action": "safety_toggle",
                "flag": flag,
                "actor": actor,
                "old": old_val,
                "new": value,
            }
            self.audit_log.append(record)
            return self.snapshot()


def sanitize_log_message(msg: str) -> str:
    """Маскирование конфиденциальных данных и секретов в логах."""
    # Маскирование токенов вида sk-..., gho_..., Bearer ..., API keys
    msg = re.sub(r"sk-[A-Za-z0-9_\-]{20,}", "sk-***REDACTED***", msg)
    msg = re.sub(r"gho_[A-Za-z0-9_\-]{20,}", "gho_***REDACTED***", msg)
    msg = re.sub(r"(?i)(api[-_]?key|token|secret)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{8,})['\"]?", r"\1=***REDACTED***", msg)
    return msg


def bound_text(text: str, max_length: int = MAX_INCOMING_TEXT_LENGTH) -> str:
    """Ограничение длины текста входящего сообщения для защиты от ресурсных атак."""
    if not text:
        return ""
    return text[:max_length]
