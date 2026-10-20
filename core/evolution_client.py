"""Клиент для интеграции с Evolution API v2 (schrot47_bot).
Поддерживает:
1. Отправку индикатора набора текста ("composing") в WhatsApp.
2. Отправку текстовых ответов клиенту (/message/sendText/{instance}).
3. Уведомление группы склада в WhatsApp («Не мало, 2», 120363427990129017@g.us).
4. Строгий контроль безопасности: если outbound_allowed() == False (kill_switch включен или production_enabled=False),
   реальные сетевые вызовы блокируются, а сообщения логируются и складываются в очередь dry-run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from .safety import SafetyManager

logger = logging.getLogger(__name__)

WAREHOUSE_GROUP_JID = "120363427990129017@g.us"


@dataclass
class OutboundMessage:
    remote_jid: str
    text: str
    status: str  # "sent", "blocked_safety", "failed"
    details: str | None = None


class EvolutionClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: str = "",
        instance: str = "shrot47",
        safety: SafetyManager | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.instance = instance
        self.safety = safety or SafetyManager()
        self.timeout = timeout
        self.outbox_history: list[OutboundMessage] = []

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

    def send_presence(self, remote_jid: str, presence: str = "composing") -> bool:
        """Отправка индикатора набора текста («печатает...»)."""
        if not self.safety.outbound_allowed():
            logger.info(f"[SAFETY: DRY-RUN] Presence '{presence}' for {remote_jid} suppressed.")
            return False

        url = f"{self.base_url}/chat/sendPresence/{self.instance}"
        payload = {
            "number": remote_jid,
            "presence": presence,
            "delay": 1200,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(url, json=payload, headers=self._headers())
                return res.status_code in (200, 201)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to send presence to {remote_jid}: {e}")
            return False

    def send_text(self, remote_jid: str, text: str) -> OutboundMessage:
        """Отправка текстового сообщения в WhatsApp."""
        if not self.safety.outbound_allowed():
            logger.info(
                f"[SAFETY: OUTBOUND BLOCKED] Outbound to {remote_jid} blocked by safety policy. Text: {text[:80]}..."
            )
            msg = OutboundMessage(
                remote_jid=remote_jid,
                text=text,
                status="blocked_safety",
                details="Safety flags: kill_switch or outbound_enabled=False",
            )
            self.outbox_history.append(msg)
            return msg

        url = f"{self.base_url}/message/sendText/{self.instance}"
        payload = {
            "number": remote_jid,
            "text": text,
            "delay": 1000,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(url, json=payload, headers=self._headers())
                if res.status_code in (200, 201):
                    msg = OutboundMessage(remote_jid=remote_jid, text=text, status="sent")
                else:
                    msg = OutboundMessage(
                        remote_jid=remote_jid,
                        text=text,
                        status="failed",
                        details=f"HTTP {res.status_code}: {res.text}",
                    )
        except Exception as e:  # noqa: BLE001
            msg = OutboundMessage(remote_jid=remote_jid, text=text, status="failed", details=str(e))

        self.outbox_history.append(msg)
        return msg

    def notify_warehouse(self, phone: str, client_name: str, inquiry: str, reason: str = "") -> OutboundMessage:
        """Отправка уведомления об эскалации/заявке в рабочую группу склада."""
        notification_text = (
            f"🔔 *ШРОТ 47 — ЗАЯВКА НА СКЛАД*\n"
            f"👤 Клиент: {client_name or 'Без имени'} (+{phone})\n"
            f"❓ Запрос: {inquiry}\n"
            f"⚠️ Причина эскалации: {reason or 'Квалифицированный лид'}\n"
            f"📍 Проверить наличие на Лизы Чайкиной 157/1"
        )
        return self.send_text(WAREHOUSE_GROUP_JID, notification_text)
