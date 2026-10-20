"""Тесты устойчивости к перезапуску (SQLite persistence):
- Сохранность истории диалога после перезапуска приложения
- Сохранность состояния human_mode после перезапуска
- Сохранность таблицы дедупликации (защита от повторной обработки после рестарта)
"""

from core.sessions import SessionManager


def test_persistence_across_restart(temp_db):
    phone = "77089998877"

    # 1. Первый инстанс сервиса (до перезапуска)
    mgr1 = SessionManager(db_path=temp_db)
    s1 = mgr1.get_or_create_session(phone, push_name="Ержан")
    mgr1.add_message(phone, s1.session_id, "user", "Куплю коробку DHN на Ауди А4 Б5")
    mgr1.add_message(phone, s1.session_id, "assistant", "МКПП 5-ступка DHN, передний привод?")
    mgr1.set_human_mode(phone, True)
    mgr1.is_duplicate_and_record("MSG_BEFORE_REBOOT")

    # 2. Имитация перезапуска: создаем новый объект SessionManager к тому же файлу БД
    mgr2 = SessionManager(db_path=temp_db)

    # Проверяем восстановление сессии и истории
    s2 = mgr2.get_or_create_session(phone)
    assert s2.session_id == s1.session_id
    assert s2.push_name == "Ержан"
    assert s2.human_mode is True

    hist = mgr2.get_history(phone)
    assert len(hist) == 2
    assert "DHN" in hist[0]["content"]
    assert "МКПП" in hist[1]["content"]

    # Проверяем, что дедупликация помнит старое сообщение
    assert mgr2.is_duplicate_and_record("MSG_BEFORE_REBOOT") is True
    # И принимает новое
    assert mgr2.is_duplicate_and_record("MSG_AFTER_REBOOT") is False
