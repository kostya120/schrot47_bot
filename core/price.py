"""Ценообразование и защита от галлюцинаций цен/наличия (SHROT47).
Ключевое бизнес-правило:
- Рыночные или исторические цены никогда не выдаются за подтверждённое наличие на складе.
- Актуальный остаток и подтверждённую цену на Лизы Чайкиной, 157/1 (Караганда) называет только кладовщик.
- is_actual_stock_price всегда False для любых расчётных/рыночных агрегатов.
"""

from __future__ import annotations

import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .contracts import PriceQuery, PriceResult

MIN_SAMPLES = 3
PLACEHOLDER_MARKERS = ("китайск", "неоригинал", "аналог новый", "copy")
PLACEHOLDER_PRICE_FLOOR = 1000  # KZT


class BasePriceAdapter(ABC):
    name: str

    @abstractmethod
    def search(self, query: PriceQuery) -> list[PriceResult]:
        ...


class FixturePriceAdapter(BasePriceAdapter):
    """Адаптер тестовых фикстур цен."""
    def __init__(self, name: str, results: list[PriceResult]):
        self.name = name
        self._results = results

    def search(self, query: PriceQuery) -> list[PriceResult]:
        return list(self._results)


@dataclass
class AgentOutcome:
    results: list[PriceResult] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class PriceAggregate:
    low: float
    median: float
    high: float
    n: int
    is_actual_stock_price: bool = False  # ВСЕГДА False: не подтверждает физический склад!


def filter_results(results: list[PriceResult]) -> list[PriceResult]:
    """Фильтрация недостоверных, несоответствующих или заниженных цен."""
    seen: set[tuple] = set()
    kept = []
    for r in results:
        if r.vehicle_match is False or r.generation_match is False:
            continue
        if r.side_match is False or r.engine_match is False or r.oem_match is False:
            continue
        note = (r.note or "").lower()
        if r.price < PLACEHOLDER_PRICE_FLOOR or any(m in note for m in PLACEHOLDER_MARKERS):
            continue
        key = (r.source, r.evidence_ref, r.price)
        if key in seen:
            continue
        seen.add(key)
        kept.append(r)
    return kept


def aggregate_prices(results: list[PriceResult]) -> PriceAggregate | None:
    """Агрегация рыночных/исторических цен с гарантией is_actual_stock_price=False."""
    clean = filter_results(results)
    if len(clean) < MIN_SAMPLES:
        return None
    prices = [r.price for r in clean]
    return PriceAggregate(
        low=min(prices),
        median=float(statistics.median(prices)),
        high=max(prices),
        n=len(prices),
        is_actual_stock_price=False,
    )
