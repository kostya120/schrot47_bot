"""Тесты логики подбора автозапчастей и правил цен (SHROT47):
- Определение стороны строго по ходу движения (лево = водитель, право = пассажир)
- Валидация OEM-кодов
- Фильтрация сомнительных цен и гарантия is_actual_stock_price=False
"""

from core.contracts import PriceResult
from core.parts_orientation import resolve_side, validate_oem
from core.price import aggregate_prices


def test_parts_orientation_explicit():
    # Явная сторона
    res_l = resolve_side("Нужно левое переднее крыло на Гольф 3")
    assert res_l.status == "resolved"
    assert res_l.side == "left"

    res_r = resolve_side("Фара правая на Мерседес W210")
    assert res_r.status == "resolved"
    assert res_r.side == "right"


def test_parts_orientation_driver_passenger():
    # Сторона от водителя/пассажира для авто с левым рулем (LHD)
    res_drv = resolve_side("Дверь водительская передняя", drive_hand="left")
    assert res_drv.status == "resolved"
    assert res_drv.side == "left"

    res_pas = resolve_side("Стеклоподъемник пассажирский", drive_hand="left")
    assert res_pas.status == "resolved"
    assert res_pas.side == "right"


def test_parts_orientation_conflict_and_missing():
    # Конфликтная сторона
    res_conf = resolve_side("Крыло левое правое")
    assert res_conf.status == "needs_photo_or_oem"
    assert res_conf.reason == "conflicting_sides"

    # Не указана сторона
    res_none = resolve_side("Нужен суппорт на Ауди")
    assert res_none.status == "needs_photo_or_oem"
    assert res_none.reason == "side_not_stated"

    # При наличии OEM или фото статус переходит в ревью
    res_oem = resolve_side("Суппорт", oem="4B0615123")
    assert res_oem.status == "needs_review_by_oem"


def test_oem_validation():
    assert validate_oem("06A-133-064J") == "06A133064J"
    assert validate_oem("8D0 820 043 M") == "8D0820043M"
    # Менее 3 цифр или недопустимые знаки
    assert validate_oem("ABC") is None
    assert validate_oem("12") is None
    assert validate_oem("") is None


def test_price_aggregation_safeguard():
    # Цены рынка/истории НЕ ДОЛЖНЫ выдаваться за складское наличие
    samples = [
        PriceResult(source="history", price=25000, evidence_ref="call_1", note="Оригинал б/у"),
        PriceResult(source="history", price=28000, evidence_ref="call_2", note="Хорошее состояние"),
        PriceResult(source="market", price=30000, evidence_ref="kolesa_1", note="Шрот"),
        # Китайский дубликат (должен отфильтроваться)
        PriceResult(source="market", price=5000, evidence_ref="kolesa_bad", note="китайский аналог"),
    ]

    agg = aggregate_prices(samples)
    assert agg is not None
    assert agg.n == 3
    assert agg.low == 25000
    assert agg.high == 30000
    assert agg.median == 28000
    # КРИТИЧЕСКИЙ ИНВАРИАНТ: расчетные цены никогда не объявляются ценой фактического склада
    assert agg.is_actual_stock_price is False
