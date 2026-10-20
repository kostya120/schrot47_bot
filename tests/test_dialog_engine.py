"""Тесты диалогового движка:
- вызов LLM и сериализация в AgentResult
- валидация контракта (needs_handoff требует reason)
- retry с экспоненциальным backoff при сбоях LLM
- автоматический handoff при исчерпании 3 попыток
"""

import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from core.contracts import AgentResult
from core.dialog import DialogEngine, build_system_prompt


def test_agent_result_contract_validation():
    # Успешная валидация без handoff
    r = AgentResult(context_version=1, reply_text="Привет!", needs_handoff=False)
    assert r.context_version == 1
    assert r.needs_handoff is False

    # Ошибка: needs_handoff=True без указания reason
    with pytest.raises(ValidationError):
        AgentResult(context_version=1, reply_text="Ошибка", needs_handoff=True, reason=None)

    # Успешно с reason
    r2 = AgentResult(context_version=1, reply_text="Ошибка", needs_handoff=True, reason="manager_required")
    assert r2.needs_handoff is True
    assert r2.reason == "manager_required"


def test_system_prompt_builder():
    prompt_ru = build_system_prompt("ru")
    assert "Шрот на 47" in prompt_ru
    assert "Лизы Чайкиной, 157/1" in prompt_ru
    assert "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать цены" in prompt_ru

    prompt_kk = build_system_prompt("kk")
    assert "Қарағанды" in prompt_kk


def test_dialog_engine_success():
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "context_version": 1,
        "reply_text": "Есть капот на Audi 100 C4, цвет темно-синий. Уточните, нужен в сборе с решеткой?",
        "intent": "parts_query",
        "vehicle_updates": [{"make": "Audi", "model": "100 C4"}],
        "parts": [{"part": "hood", "color": "dark_blue"}],
        "needs_handoff": False,
    })
    mock_client.chat.completions.create.return_value.choices = [mock_choice]

    engine = DialogEngine(openai_client=mock_client)
    res = engine.run_turn("Нужен капот на ауди 100 с4", history=[])

    assert isinstance(res, AgentResult)
    assert res.needs_handoff is False
    assert "Audi 100 C4" in res.reply_text


def test_dialog_engine_retry_to_handoff():
    mock_client = MagicMock()
    # Имитируем 3 падения подряд (например, невалидный JSON или 500 от OpenAI)
    mock_choice = MagicMock()
    mock_choice.message.content = "INVALID NON-JSON RESPONSE"
    mock_client.chat.completions.create.return_value.choices = [mock_choice]

    engine = DialogEngine(openai_client=mock_client)
    no_sleep = MagicMock()

    res = engine.run_turn("Сколько стоит мотор?", history=[], sleep_fn=no_sleep)

    assert isinstance(res, AgentResult)
    assert res.needs_handoff is True
    assert "llm_exhausted_retries" in (res.reason or "")
    assert no_sleep.call_count == 2  # спал между попытками 1->2 и 2->3
    assert mock_client.chat.completions.create.call_count == 3
