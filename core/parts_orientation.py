"""Определение стороны детали строго по ходу движения автомобиля (SHROT47).
Сторона детали определяется по ходу движения: лево = водительская сторона, право = пассажирская.
Никогда не выдумываем сторону: при сомнениях требуем фото шильдика или OEM-код.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LEFT = re.compile(r"(?<!\w)(лев(?:ая|ый|ое|ые|ую|ой|ого)|слева|сол\s+жақ|сол)(?!\w)", re.IGNORECASE)
_RIGHT = re.compile(r"(?<!\w)(прав(?:ая|ый|ое|ые|ую|ой|ого)|справа|оң\s+жақ|оң)(?!\w)", re.IGNORECASE)
_DRIVER = re.compile(r"(?<!\w)(водител\w*)", re.IGNORECASE)
_PASSENGER = re.compile(r"(?<!\w)(пассажир\w*)", re.IGNORECASE)
_OEM = re.compile(r"^[A-Z0-9]{5,20}$")


@dataclass(frozen=True)
class SideResult:
    status: str
    side: str | None = None
    oem: str | None = None
    reason: str = ""


def validate_oem(oem: str | None) -> str | None:
    """Нормализованный OEM или None; обязательно буквы/цифры, минимум 3 цифры."""
    if not oem:
        return None
    norm = re.sub(r"[\s\-]", "", oem).upper()
    if not _OEM.match(norm) or sum(c.isdigit() for c in norm) < 3:
        return None
    return norm


def _from_driver_wording(text: str, drive_hand: str | None) -> str | None:
    if drive_hand not in ("left", "right"):
        return None
    other = "right" if drive_hand == "left" else "left"
    d, p = bool(_DRIVER.search(text)), bool(_PASSENGER.search(text))
    if d == p:
        return None
    return drive_hand if d else other


def resolve_side(
    text: str,
    has_photo: bool = False,
    oem: str | None = None,
    drive_hand: str | None = "left",
) -> SideResult:
    """Разрешение стороны детали по тексту сообщения, признаку фото и OEM."""
    norm_oem = validate_oem(oem)
    left, right = bool(_LEFT.search(text)), bool(_RIGHT.search(text))
    if left != right:
        return SideResult("resolved", "left" if left else "right", norm_oem, "explicit")
    if not (left or right):
        side = _from_driver_wording(text, drive_hand)
        if side:
            return SideResult("resolved", side, norm_oem, "driver_wording+drive_hand")
    reason = "conflicting_sides" if left and right else "side_not_stated"
    if norm_oem:
        return SideResult("needs_review_by_oem", None, norm_oem, reason)
    if has_photo:
        return SideResult("needs_review_by_photo", None, None, reason)
    return SideResult("needs_photo_or_oem", None, None, reason)
