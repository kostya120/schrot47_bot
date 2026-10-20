"""Тесты механизма эскалации на человека (Handoff) и интеграции со складом:
- Вызов человека по ключевым словам («позови человека», «оператор»)
- Замолкание бота при активном human_mode
- Формирование уведомления для группы склада WhatsApp («Не мало, 2», 120363427990129017@g.us)
- Вежливая обработка непрофильных брендов (ВАЗ, японские авто)
"""

from unittest.mock import MagicMock

from core.evolution_client import WAREHOUSE_GROUP_JID
from core.service import BotService


def _payload(phone, text, msg_id="MSG_H_1"):
    return {
        "event": "messages.upsert",
        "instance": "shrot47",
        "data": {
            "key": {
                "remoteJid": f"{phone}@s.whatsapp.net",
                "fromMe": False,
                "id": msg_id,
            },
            "pushName": "Алексей",
            "message": {"conversation": text},
            "messageType": "conversation",
        },
    }


def test_handoff_by_keyword(session_mgr, evo_client, safety_mgr):
    dialog = MagicMock()
    service = BotService(session_mgr, dialog, evo_client, safety_mgr)

    phone = "77771234567"
    res = service.process_webhook(_payload(phone, "Пожалуйста, позови человека, сложный вопрос"))

    assert res["status"] == "handoff_initiated"
    assert session_mgr.is_human_mode(phone) is True
    # LLM не вызывался зря
    dialog.run_turn.assert_not_called()

    # Проверяем, что в outbox_history есть отправка в группу склада
    warehouse_notifications = [
        msg for msg in evo_client.outbox_history if msg.remote_jid == WAREHOUSE_GROUP_JID
    ]
    assert len(warehouse_notifications) == 1
    assert "ШРОТ 47 — ЗАЯВКА НА СКЛАД" in warehouse_notifications[0].text
    assert phone in warehouse_notifications[0].text


def test_bot_silence_when_human_mode_active(session_mgr, evo_client, safety_mgr):
    dialog = MagicMock()
    service = BotService(session_mgr, dialog, evo_client, safety_mgr)

    phone = "77771234567"
    session_mgr.set_human_mode(phone, True)

    res = service.process_webhook(_payload(phone, "Алло, вы тут?", msg_id="MSG_H_2"))
    assert res["status"] == "human_mode_active"
    assert res["reply_sent"] is False
    dialog.run_turn.assert_not_called()

    # Сообщение клиента сохранено в истории для контекста менеджера
    hist = session_mgr.get_history(phone)
    assert len(hist) == 1
    assert hist[0]["content"] == "Алло, вы тут?"


def test_non_profile_brand_rejection(session_mgr, evo_client, safety_mgr):
    dialog = MagicMock()
    service = BotService(session_mgr, dialog, evo_client, safety_mgr)

    phone = "77017778899"
    res = service.process_webhook(_payload(phone, "Есть фара на Лада Приора?"))

    assert res["status"] == "non_profile_brand_handled"
    # LLM не тратит токены на непрофильные авто
    dialog.run_turn.assert_not_called()

    hist = session_mgr.get_history(phone)
    assert len(hist) == 2
    assert "немецких автомобилях" in hist[1]["content"]
