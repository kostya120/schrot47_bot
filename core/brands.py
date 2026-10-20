"""Политика специализации по автомобильным маркам («Шрот на 47 Караганда»).
Специализация: только легковые немецкие автомобили (Audi, Volkswagen, Mercedes-Benz, BMW, Opel).
По нецелевым маркам (ВАЗ, японские, корейские, китайские) — вежливый отказ без сухого «нет».
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_SUPPORTED_BRANDS = (
    "Audi",
    "Volkswagen",
    "Mercedes-Benz",
    "BMW",
    "Opel",
    "SEAT",
    "Skoda",
)

NON_PROFILE_BRANDS = (
    "ваз", "лада", "lada", "vaz", "газ", "уаз", "москвич",
    "toyota", "тойота", "lexus", "лексус", "nissan", "ниссан",
    "honda", "хонда", "mitsubishi", "митсубиси", "subaru", "субару",
    "hyundai", "хендай", "хёндай", "kia", "киа", "daewoo", "дэу",
    "chevrolet", "шевроле", "renault", "рено", "peugeot", "пежо",
    "citroen", "ситроен", "chery", "чери", "geely", "джили", "haval", "хавал",
)


@dataclass(frozen=True)
class BrandPolicyResult:
    supported: bool
    brand_detected: str = ""
    suggested_reply: str = ""


def check_brand_policy(text: str, supported: Sequence[str] = DEFAULT_SUPPORTED_BRANDS) -> BrandPolicyResult:
    """Проверка текста запроса на поддерживаемую марку или непрофильную марку."""
    lower = text.lower()

    # Сначала проверяем поддерживаемые немецкие марки
    for b in supported:
        if b.lower() in lower:
            return BrandPolicyResult(supported=True, brand_detected=b)

    # Проверяем явные непрофильные марки
    for non_prof in NON_PROFILE_BRANDS:
        if non_prof in lower:
            msg = (
                "Мы специализируемся исключительно на немецких автомобилях "
                "(Audi, Volkswagen, Mercedes-Benz, BMW, Opel). "
                f"По марке {non_prof.title()} деталей в наличии нет, "
                "но я могу передать запрос менеджеру или записать вас в лист ожидания."
            )
            return BrandPolicyResult(supported=False, brand_detected=non_prof, suggested_reply=msg)

    # Марка пока не указана явно
    return BrandPolicyResult(supported=True, brand_detected="")
