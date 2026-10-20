"""Тесты границ безопасности (Safety Invariants):
- Принцип Fail-Closed по умолчанию (production_enabled=False, outbound_enabled=False, kill_switch=True)
- Блокировка реальных исходящих сетевых вызовов в WhatsApp при выключенном контуре
- Защита рубильников безопасности (требуются права владельца и явный confirm)
- Санитизация логов и защита от раскрытия секретов
- Защита от resource exhaustion / DoS по длине текста
"""

import pytest

from core.evolution_client import EvolutionClient
from core.safety import SafetyManager, bound_text, sanitize_log_message


def test_safety_fail_closed_defaults():
    sm = SafetyManager()
    snap = sm.snapshot()
    assert snap["production_enabled"] is False
    assert snap["outbound_enabled"] is False
    assert snap["kill_switch"] is True
    assert sm.outbound_allowed() is False


def test_outbound_blocked_in_evolution_client(safety_mgr):
    client = EvolutionClient(
        base_url="http://localhost:8080",
        api_key="secret",
        instance="shrot47",
        safety=safety_mgr,
    )

    # Попытка отправки сообщения при fail-closed защите
    res = client.send_text("77011234567@s.whatsapp.net", "Привет из теста")

    assert res.status == "blocked_safety"
    assert "kill_switch" in (res.details or "")

    # Проверка присутствия («печатает...»)
    assert client.send_presence("77011234567@s.whatsapp.net") is False


def test_safety_toggle_permissions_and_confirm():
    sm = SafetyManager()

    # Попытка переключения не-владельцем
    with pytest.raises(PermissionError):
        sm.toggle("production_enabled", True, actor="hacker", is_owner=False)

    # Попытка ослабления защиты владельцем БЕЗ явного confirm=True
    with pytest.raises(ValueError, match="confirm=True required"):
        sm.toggle("production_enabled", True, actor="owner", is_owner=True, confirm=False)

    # Успешное ослабление с confirm=True
    updated = sm.toggle("production_enabled", True, actor="owner", is_owner=True, confirm=True)
    assert updated["production_enabled"] is True

    # Ужесточение защиты (включение kill_switch) НЕ требует confirm
    updated2 = sm.toggle("kill_switch", True, actor="owner", is_owner=True, confirm=False)
    assert updated2["kill_switch"] is True


def test_sanitize_log_message():
    raw_log = "Error connecting with apikey=sk-proj-abc1234567890abcdef123456 and token: gho_xyz9876543210zyxwvuts"
    clean = sanitize_log_message(raw_log)
    assert "sk-proj-abc" not in clean
    assert "gho_xyz98" not in clean
    assert "***REDACTED***" in clean


def test_bound_text_protection():
    huge_text = "A" * 5000
    bounded = bound_text(huge_text, max_length=1500)
    assert len(bounded) == 1500


def test_bounded_outbox_history(safety_mgr):
    client = EvolutionClient(
        base_url="http://localhost:8080",
        api_key="secret",
        instance="shrot47",
        safety=safety_mgr,
        max_history=5,
    )
    for i in range(10):
        client.send_text("77011234567@s.whatsapp.net", f"Message {i}")

    assert len(client.outbox_history) == 5
    assert client.outbox_history[-1].text == "Message 9"
