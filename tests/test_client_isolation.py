"""Тесты строгой изоляции контекста клиентов:
- Клиент А и Клиент Б имеют разные session_id и независимую историю
- Переписка одного клиента не утекает в историю другого клиента
- Включение human_mode у одного клиента не затрагивает другого
"""


def test_client_history_isolation(session_mgr):
    phone_a = "77011111111"
    phone_b = "77022222222"

    sess_a = session_mgr.get_or_create_session(phone_a, push_name="Алиса")
    sess_b = session_mgr.get_or_create_session(phone_b, push_name="Боб")

    assert sess_a.session_id != sess_b.session_id

    # Алиса спрашивает про фару на W124
    session_mgr.add_message(phone_a, sess_a.session_id, "user", "Ищу левую фару на Mercedes W124")
    session_mgr.add_message(phone_a, sess_a.session_id, "assistant", "Фара W124 дорест или рестайл E-класс?")

    # Боб спрашивает про мотор на Passat B4
    session_mgr.add_message(phone_b, sess_b.session_id, "user", "Есть двигатель 2.0 2E на Пассат Б4?")
    session_mgr.add_message(phone_b, sess_b.session_id, "assistant", "Двигатель 2E 2.0 бензин в сборе или столбик?")

    hist_a = session_mgr.get_history(phone_a)
    hist_b = session_mgr.get_history(phone_b)

    assert len(hist_a) == 2
    assert len(hist_b) == 2

    # Проверяем отсутствие перекрестного загрязнения истории
    for msg in hist_a:
        assert "Passat" not in msg["content"]
        assert "2E" not in msg["content"]

    for msg in hist_b:
        assert "W124" not in msg["content"]
        assert "Mercedes" not in msg["content"]


def test_client_human_mode_isolation(session_mgr):
    phone_a = "77011111111"
    phone_b = "77022222222"

    session_mgr.get_or_create_session(phone_a)
    session_mgr.get_or_create_session(phone_b)

    # Переводим Алису в режим оператора
    session_mgr.set_human_mode(phone_a, True)

    assert session_mgr.is_human_mode(phone_a) is True
    assert session_mgr.is_human_mode(phone_b) is False  # Боб продолжает обслуживаться ботом
