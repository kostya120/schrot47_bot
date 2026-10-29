"""Основной оркестратор сервиса schrot47_bot (WhatsApp автоконсультант по автозапчастям).
Связывает:
- Evolution API Webhook
- Проверку подписи/доступа и дедупликацию
- Фильтрацию собственных сообщений (fromMe=True) и статусных рассылок
- Проверку режима human_mode (тишина бота при ответе человека)
- Специализацию по маркам (немецкие авто, вежливый отказ по ВАЗ/Азии)
- Диалоговый движок (LLM / OpenAI + строгие контракты AgentResult)
- Сторону деталей по ходу движения (parts_orientation)
- Безопасную отправку ответов и эскалацию на группу склада в WhatsApp
"""

from __future__ import annotations

import logging
from hmac import compare_digest
from typing import Any

from .brands import check_brand_policy
from .contracts import (
    NormalizedMessage,
    normalize_phone_number,
)
from .dialog import DialogEngine
from .evolution_client import EvolutionClient
from .safety import SafetyManager, bound_text
from .sessions import SessionManager

logger = logging.getLogger(__name__)

HUMAN_REQUEST_KEYWORDS = ("человек", "менеджер", "оператор", "позови человека", "живой человек", "консультант")


class BotService:
    def __init__(
        self,
        session_manager: SessionManager,
        dialog_engine: DialogEngine,
        evolution_client: EvolutionClient,
        safety_manager: SafetyManager,
        webhook_secret: str = "",
    ) -> None:
        self.session_manager = session_manager
        self.dialog_engine = dialog_engine
        self.evolution_client = evolution_client
        self.safety_manager = safety_manager
        self.webhook_secret = webhook_secret

    def verify_webhook_auth(self, apikey_header: str | None = None) -> bool:
        """Проверка ключа авторизации вебхука Evolution API."""
        # A missing secret must never turn a public webhook into an open endpoint.
        return bool(
            self.webhook_secret
            and apikey_header
            and compare_digest(self.webhook_secret, apikey_header)
        )

    def extract_normalized_message(self, payload_dict: dict[str, Any]) -> NormalizedMessage | None:
        """Парсинг и извлечение нормализованного сообщения из Evolution API payload."""
        data = payload_dict.get("data", {})
        key = data.get("key", {})

        remote_jid = key.get("remoteJid", "")
        from_me = bool(key.get("fromMe", False))
        message_id = key.get("id", "")

        if not remote_jid or not message_id:
            return None

        # Игнорируем статусные широковещательные рассылки
        if "status@broadcast" in remote_jid:
            return None

        is_group = remote_jid.endswith("@g.us")
        push_name = data.get("pushName", "") or ""
        msg_obj = data.get("message", {}) or {}

        # Извлечение текста сообщения (разные форматы WhatsApp в Evolution API)
        text = ""
        if "conversation" in msg_obj:
            text = msg_obj["conversation"]
        elif "extendedTextMessage" in msg_obj and "text" in msg_obj["extendedTextMessage"]:
            text = msg_obj["extendedTextMessage"]["text"]
        elif "imageMessage" in msg_obj and "caption" in msg_obj["imageMessage"]:
            text = msg_obj["imageMessage"]["caption"]

        text = bound_text((text or "").strip())
        phone = normalize_phone_number(remote_jid.split("@")[0])

        return NormalizedMessage(
            provider_message_id=message_id,
            remote_jid=remote_jid,
            phone=phone,
            push_name=push_name,
            text=text,
            from_me=from_me,
            is_group=is_group,
            raw_event=payload_dict,
        )

    def process_webhook(self, payload_dict: dict[str, Any], apikey_header: str | None = None) -> dict[str, Any]:
        """Полный цикл обработки входящего вебхука."""
        if not self.verify_webhook_auth(apikey_header):
            return {"status": "unauthorized", "code": 401}

        event = payload_dict.get("event", "")
        if event != "messages.upsert":
            return {"status": "ignored_event_type", "event": event}

        norm_msg = self.extract_normalized_message(payload_dict)
        if not norm_msg:
            return {"status": "no_valid_message_found"}

        # 1. Фильтрация собственных сообщений бота/менеджера (fromMe=True)
        if norm_msg.from_me:
            # Если менеджер ответил с телефона — переводим диалог в human_mode!
            self.session_manager.set_human_mode(norm_msg.phone, True)
            logger.info(f"Human manager replied from phone to {norm_msg.phone}, human_mode activated.")
            return {"status": "ignored_from_me", "human_mode_activated": True}

        # 2. Фильтрация сообщений из групп (обрабатываем только личные чаты клиентов)
        if norm_msg.is_group:
            return {"status": "ignored_group_message"}

        # 3. Дедупликация (идемпотентность)
        if self.session_manager.is_duplicate_and_record(norm_msg.provider_message_id):
            return {"status": "duplicate_ignored", "message_id": norm_msg.provider_message_id}

        phone = norm_msg.phone
        text = norm_msg.text
        remote_jid = norm_msg.remote_jid

        if not text:
            return {"status": "empty_text_ignored"}

        session = self.session_manager.get_or_create_session(phone, norm_msg.push_name)

        # 4. Проверка режима перехвата человеком (human_mode)
        if self.session_manager.is_human_mode(phone):
            self.session_manager.add_message(phone, session.session_id, "user", text)
            logger.info(f"Client {phone} message received while human_mode active. Bot remains silent.")
            return {"status": "human_mode_active", "reply_sent": False}

        # 5. Проверка явного запроса оператора/человека
        lower_text = text.lower()
        if any(kw in lower_text for kw in HUMAN_REQUEST_KEYWORDS):
            self.session_manager.add_message(phone, session.session_id, "user", text)
            self.session_manager.record_handoff(phone, session.session_id, "customer_requested_human")
            handoff_reply = (
                "Передал ваш запрос менеджеру склада в Караганде. "
                "Специалист уже видит переписку и ответит вам здесь в ближайшее время."
            )
            self.session_manager.add_message(phone, session.session_id, "assistant", handoff_reply)
            self.evolution_client.notify_warehouse(phone, norm_msg.push_name, text, "Запрос оператора клиентом")
            self.evolution_client.send_text(remote_jid, handoff_reply)
            return {"status": "handoff_initiated", "reply_sent": True}

        # 6. Проверка политики марок (немецкие авто vs непрофильные)
        brand_check = check_brand_policy(text)
        if not brand_check.supported:
            self.session_manager.add_message(phone, session.session_id, "user", text)
            self.session_manager.add_message(phone, session.session_id, "assistant", brand_check.suggested_reply)
            self.evolution_client.send_text(remote_jid, brand_check.suggested_reply)
            return {"status": "non_profile_brand_handled", "reply_sent": True}

        # 7. Индикатор набора текста ("печатает...")
        self.evolution_client.send_presence(remote_jid, "composing")

        # 8. Запрос к диалоговому движку (LLM)
        history = self.session_manager.get_history(phone)
        agent_result = self.dialog_engine.run_turn(text, history)

        # 9. Фиксация в истории
        self.session_manager.add_message(phone, session.session_id, "user", text)
        reply_to_send = agent_result.reply_text or "Сейчас уточню наличие у кладовщика на складе в Караганде."
        self.session_manager.add_message(phone, session.session_id, "assistant", reply_to_send)

        # 10. Эскалация на склад при необходимости (needs_handoff)
        if agent_result.needs_handoff:
            reason = agent_result.reason or "agent_escalation"
            self.session_manager.record_handoff(phone, session.session_id, reason)
            self.evolution_client.notify_warehouse(phone, norm_msg.push_name, text, reason)

        # 11. Отправка ответа клиенту через Evolution API (с защитой SafetyManager)
        outbound_res = self.evolution_client.send_text(remote_jid, reply_to_send)

        return {
            "status": "success",
            "phone": phone,
            "session_id": session.session_id,
            "intent": agent_result.intent,
            "needs_handoff": agent_result.needs_handoff,
            "outbound_status": outbound_res.status,
            "reply_text": reply_to_send,
        }
