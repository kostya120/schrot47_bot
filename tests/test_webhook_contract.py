"""Тесты контракта входящих вебхуков Evolution API v2:
- парсинг messages.upsert
- авторизация apikey / X-Webhook-Secret
- фильтрация fromMe=True
- фильтрация групп и широковещательных рассылок
- дедупликация повторных событий
"""

from unittest.mock import MagicMock

from core.contracts import AgentResult
from core.service import BotService


def _sample_payload(
    msg_id="MSG_001",
    remote_jid="77011234567@s.whatsapp.net",
    from_me=False,
    text="Здравствуйте, нужен генератор на Passat B3 1.8",
    event="messages.upsert",
):
    return {
        "event": event,
        "instance": "shrot47",
        "data": {
            "key": {
                "remoteJid": remote_jid,
                "fromMe": from_me,
                "id": msg_id,
            },
            "pushName": "Константин",
            "message": {
                "conversation": text,
            },
            "messageType": "conversation",
            "messageTimestamp": 1729440000,
        },
    }


def test_webhook_unauthorized(session_mgr, evo_client, safety_mgr):
    dialog = MagicMock()
    service = BotService(session_mgr, dialog, evo_client, safety_mgr, webhook_secret="secret123")

    payload = _sample_payload()
    res = service.process_webhook(payload, apikey_header="wrong-secret")
    assert res["status"] == "unauthorized"
    assert res["code"] == 401


def test_webhook_authorized_and_processed(session_mgr, evo_client, safety_mgr):
    dialog = MagicMock()
    dialog.run_turn.return_value = AgentResult(
        context_version=1,
        reply_text="Генератор 1.8 на Passat B3 есть разных модификаций. Уточните буквенный код двигателя (RP, ABS, 2E)?",
        intent="parts_query",
        needs_handoff=False,
    )
    service = BotService(session_mgr, dialog, evo_client, safety_mgr, webhook_secret="secret123")

    payload = _sample_payload()
    res = service.process_webhook(payload, apikey_header="secret123")

    assert res["status"] == "success"
    assert res["phone"] == "77011234567"
    assert res["needs_handoff"] is False
    assert "Passat B3" in res["reply_text"]


def test_webhook_from_me_activates_human_mode(session_mgr, evo_client, safety_mgr):
    dialog = MagicMock()
    service = BotService(session_mgr, dialog, evo_client, safety_mgr, webhook_secret="secret123")

    payload = _sample_payload(from_me=True, remote_jid="77015555555@s.whatsapp.net")
    res = service.process_webhook(payload, apikey_header="secret123")

    assert res["status"] == "ignored_from_me"
    assert res["human_mode_activated"] is True
    assert session_mgr.is_human_mode("77015555555") is True


def test_webhook_group_ignored(session_mgr, evo_client, safety_mgr):
    dialog = MagicMock()
    service = BotService(session_mgr, dialog, evo_client, safety_mgr, webhook_secret="secret123")

    payload = _sample_payload(remote_jid="120363427990129017@g.us")
    res = service.process_webhook(payload, apikey_header="secret123")

    assert res["status"] == "ignored_group_message"
    dialog.run_turn.assert_not_called()


def test_webhook_deduplication(session_mgr, evo_client, safety_mgr):
    dialog = MagicMock()
    dialog.run_turn.return_value = AgentResult(
        context_version=1,
        reply_text="Ответ на первое сообщение",
        needs_handoff=False,
    )
    service = BotService(session_mgr, dialog, evo_client, safety_mgr, webhook_secret="secret123")

    payload = _sample_payload(msg_id="UNIQUE_ID_999")

    # Первая доставка сообщения
    res1 = service.process_webhook(payload, apikey_header="secret123")
    assert res1["status"] == "success"

    # Повторная доставка того же сообщения (retry Evolution API)
    res2 = service.process_webhook(payload, apikey_header="secret123")
    assert res2["status"] == "duplicate_ignored"
    assert res2["message_id"] == "UNIQUE_ID_999"

    # Диалоговый движок вызывался ровно 1 раз
    assert dialog.run_turn.call_count == 1


def test_webhook_missing_secret_is_denied(session_mgr, evo_client, safety_mgr):
    """No secret configured must be a hard failure, never a dev-mode bypass."""
    service = BotService(session_mgr, MagicMock(), evo_client, safety_mgr, webhook_secret="")
    res = service.process_webhook(_sample_payload(msg_id="MISSING_SECRET"))
    assert res["status"] == "unauthorized"
    assert res["code"] == 401
