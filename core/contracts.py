"""Строгие контракты данных schrot47_bot (Pydantic v2, extra='forbid').
Согласованы со стандартом SHROT47.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentResult(_Strict):
    """Контракт ответа диалогового агента v1."""
    customer_id: str | None = None
    conversation_id: str | None = None
    context_version: StrictInt
    reply_text: str | None = None
    intent: str | None = None
    vehicle_updates: list[dict[str, Any]] = Field(default_factory=list)
    parts: list[dict[str, Any]] = Field(default_factory=list)
    request_action: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    needs_handoff: StrictBool
    reason: str | None = None

    @model_validator(mode="after")
    def _handoff_needs_reason(self) -> AgentResult:
        if self.needs_handoff and not self.reason:
            raise ValueError("needs_handoff=true requires reason")
        return self


class PriceQuery(_Strict):
    """Запрос цены запчасти."""
    vehicle: str = Field(min_length=1)
    part: str = Field(min_length=1)
    oem: str | None = None
    condition: str | None = None
    currency: Literal["KZT"] = "KZT"
    region: str | None = None


class PriceResult(_Strict):
    """Результат оценки цены из истории или рынка (не является подтверждённым наличием склада)."""
    source: Literal["history", "market"]
    price: float = Field(ge=0)
    currency: Literal["KZT"] = "KZT"
    fx_rate: float | None = Field(default=None, gt=0)
    fx_date: str | None = None
    evidence_ref: str = Field(min_length=1)
    url: str | None = None
    vehicle_match: bool | None = None
    generation_match: bool | None = None
    side_match: bool | None = None
    engine_match: bool | None = None
    oem_match: bool | None = None
    note: str | None = None


class EvolutionMessageKey(_Strict):
    remoteJid: str = Field(min_length=1)
    fromMe: bool
    id: str = Field(min_length=1)
    participant: str | None = None


class EvolutionWebhookPayload(BaseModel):
    """Схема входящего вебхука Evolution API v2 (messages.upsert)."""
    model_config = ConfigDict(extra="ignore")  # вебхук может содержать доп. поля Evolution API

    event: str
    instance: str
    data: dict[str, Any]
    destination: str | None = None
    date_time: str | None = None
    sender: str | None = None
    server_url: str | None = None
    apikey: str | None = None


class NormalizedMessage(_Strict):
    """Нормализованное входящее сообщение для контура обработки."""
    provider_message_id: str = Field(min_length=1)
    remote_jid: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    push_name: str = ""
    text: str = ""
    from_me: bool = False
    is_group: bool = False
    timestamp: int = Field(default_factory=lambda: int(datetime.now(UTC).timestamp()))
    raw_event: dict[str, Any] | None = None


def normalize_phone_number(raw: str) -> str:
    """Нормализация телефонного номера клиента (E.164 без +)."""
    clean = re.sub(r"[^\d]", "", raw)
    if clean.startswith("8") and len(clean) == 11:
        clean = "7" + clean[1:]
    return clean
