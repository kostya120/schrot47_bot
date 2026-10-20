"""Диалоговый движок на базе OpenAI API (GPT-4o / GPT-4o-mini) для schrot47_bot.
Строго соблюдает правила авторазбора из SHROT47:
- Поддерживает русский (ru) и казахский (kk) языки.
- Не выдумывает наличие и складские цены в Караганде.
- Требует сторону детали строго по ходу движения (лево = водитель, право = пассажир).
- Ограничение темпа: не более 1-2 вопросов за сообщение.
- Валидация ответа через Pydantic v2 AgentResult.
- Защита от отказов LLM: 3 попытки с экспоненциальным backoff, при неудаче автоматический handoff.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from openai import OpenAI
from pydantic import ValidationError

from .brands import DEFAULT_SUPPORTED_BRANDS
from .contracts import AgentResult

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.5

_RULES = {
    "ru": (
        "Ты профессиональный консультант авторазбора «Шрот на 47» (Караганда, ул. Лизы Чайкиной, 157/1). "
        "Специализация: только легковые автомобили из Германии ({brands}). "
        "Отвечай на русском языке, кратко и дружелюбно (1–3 предложения). "
        "Задавай не более 1–2 необходимых вопросов за сообщение по чек-листу: "
        "марка, модель, год, тип кузова, буквенный индекс мотора/КПП, сторона детали. "
        "Сторону детали определяй строго по ходу движения автомобиля (лево = сторона водителя, право = сторона пассажира). "
        "При сомнениях проси фото шильдика, старой детали или OEM-код. "
        "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать цены и наличие на складе. "
        "На вопрос «есть ли / сколько стоит?» отвечай: «Сейчас уточню наличие и точную стоимость у кладовщика на складе» "
        "и продолжай сбор параметров. "
        "Если марка не в списке — вежливо откажи и предложи уточнить у менеджера или записать в лист ожидания. "
        "Ответ возвращай СТРОГО в формате валидного JSON-объекта контракта AgentResult: "
        '{{"context_version": 1, "reply_text": "...", "intent": "parts_query", "vehicle_updates": [], "parts": [], "needs_handoff": false, "reason": null}}. '
        "ВАЖНО: если needs_handoff=true, поле reason ОБЯЗАТЕЛЬНО должно быть строкой с причиной передачи (не null!)."
    ),
    "kk": (
        "Сіз «Шрот на 47» автобөлшектер авторазборының консультантысыз (Қарағанды қ., Лиза Чайкина көш., 157/1). "
        "Мамандану: тек Германия жеңіл көліктері ({brands}). "
        "Қазақ тілінде қысқа әрі достық түрде жауап беріңіз (1–3 сөйлем). "
        "Бір хабарламада 1–2 қажетті сұрақтан артық қоймаңыз. "
        "Бөлшектің жағын көліктің жүру бағыты бойынша анықтаңыз (сол жақ = жүргізуші жағы, оң жақ = жолаушы жағы). "
        "Баға мен қоймадағы нақты бар-жоғын ойдан шығаруға қатаң тыйым салынады. "
        "Марка тізімде болмаса — менеджерден нақтылауды немесе күту парағын ұсыныңыз. "
        "Жауапты ТЕК AgentResult келісіміне сәйкес келетін JSON түрінде қайтарыңыз."
    ),
}


def build_system_prompt(lang: str = "ru", supported_brands: tuple[str, ...] = DEFAULT_SUPPORTED_BRANDS) -> str:
    """Генератор системного промпта с актуальным списком брендов."""
    rule_template = _RULES.get(lang, _RULES["ru"])
    brands_str = ", ".join(supported_brands)
    return rule_template.format(brands=brands_str)


class DialogEngine:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        timeout: float = 15.0,
        openai_client: OpenAI | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        if openai_client:
            self.client = openai_client
        elif api_key:
            self.client = OpenAI(api_key=api_key, timeout=timeout)
        else:
            self.client = None

    def _call_llm_raw(self, messages: list[dict[str, str]]) -> str:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("empty response from OpenAI")
        return content

    def run_turn(
        self,
        user_text: str,
        history: list[dict[str, str]],
        lang: str = "ru",
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> AgentResult:
        """Выполнение одного шага диалога с автоматическим retry и handoff при ошибках."""
        system_prompt = build_system_prompt(lang)
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": user_text})

        last_error = "unknown"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                raw_json = self._call_llm_raw(messages)
                data = json.loads(raw_json)
                if data.get("needs_handoff") and not data.get("reason"):
                    data["reason"] = "warehouse_manager_check"
                return AgentResult.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = f"schema_validation_error: {exc}"
                logger.warning(f"DialogEngine attempt {attempt}/{MAX_ATTEMPTS} invalid format: {exc}")
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(f"DialogEngine attempt {attempt}/{MAX_ATTEMPTS} error: {exc}")

            if attempt < MAX_ATTEMPTS:
                sleep_fn(BACKOFF_BASE**attempt)

        # После 3 неудачных попыток — безопасный автоматический handoff на менеджера
        return AgentResult(
            context_version=0,
            reply_text="Сейчас уточняю информацию у менеджера склада в Караганде. Пожалуйста, подождите минутку, специалист ответит вам здесь.",
            intent="error_fallback",
            needs_handoff=True,
            reason=f"llm_exhausted_retries: {last_error}",
        )
