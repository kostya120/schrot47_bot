"""Веб-сервер FastAPI для schrot47_bot (WhatsApp автоконсультант через Evolution API v2).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from core.dialog import DialogEngine
from core.evolution_client import EvolutionClient
from core.safety import SafetyManager
from core.service import BotService
from core.sessions import SessionManager

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("schrot47_bot")

# ── Переменные окружения ────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EVOLUTION_BASE_URL = os.getenv("EVOLUTION_BASE_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "shrot47")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
DB_PATH = os.getenv("DB_PATH", "schrot47_bot.db")

# Инициализация компонентов с fail-closed безопасностью
safety_manager = SafetyManager(
    production_enabled=os.getenv("PRODUCTION_ENABLED", "false").lower() == "true",
    outbound_enabled=os.getenv("OUTBOUND_ENABLED", "false").lower() == "true",
    owner_only=True,
    kill_switch=os.getenv("KILL_SWITCH", "true").lower() == "true",
)

session_manager = SessionManager(db_path=DB_PATH)
dialog_engine = DialogEngine(api_key=OPENAI_API_KEY, model=OPENAI_MODEL)
evolution_client = EvolutionClient(
    base_url=EVOLUTION_BASE_URL,
    api_key=EVOLUTION_API_KEY,
    instance=EVOLUTION_INSTANCE,
    safety=safety_manager,
)
bot_service = BotService(
    session_manager=session_manager,
    dialog_engine=dialog_engine,
    evolution_client=evolution_client,
    safety_manager=safety_manager,
    webhook_secret=WEBHOOK_SECRET,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🤖 schrot47_bot (Evolution API WhatsApp) starting up...")
    logger.info(f"Safety status: {safety_manager.snapshot()}")
    yield
    logger.info("🛑 schrot47_bot shutting down...")


app = FastAPI(
    title="schrot47_bot API",
    description="WhatsApp-консультант по автозапчастям («Шрот на 47») через Evolution API v2",
    version="2.0.0",
    lifespan=lifespan,
)


class SafetyToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flag: str
    value: bool
    actor: str = Field(min_length=1)
    is_owner: bool = False
    confirm: bool = False


@app.get("/")
def root():
    return {
        "service": "schrot47_bot",
        "description": "WhatsApp-консультант по немецким автозапчастям («Шрот на 47 Караганда»)",
        "version": "2.0.0",
        "transport": "Evolution API v2",
        "safety": safety_manager.snapshot(),
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "safety": safety_manager.snapshot(),
        "openai_configured": bool(OPENAI_API_KEY),
        "outbound_allowed": safety_manager.outbound_allowed(),
    }


@app.post("/webhook/evolution")
@app.post("/webhook/whatsapp")
@app.post("/v1/events/whatsapp")
async def evolution_webhook(
    request: Request,
    apikey: str | None = Header(None, alias="apikey"),
    x_api_key: str | None = Header(None, alias="x-api-key"),
):
    """Приём вебхуков от Evolution API v2."""
    token = apikey or x_api_key or ""
    try:
        body = await request.json()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Invalid JSON in webhook request: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    result = bot_service.process_webhook(body, apikey_header=token)
    if result.get("status") == "unauthorized":
        raise HTTPException(status_code=401, detail="Unauthorized webhook caller")

    return result


@app.get("/v1/sessions/{phone}")
def get_session_info(phone: str):
    """Инспекция сессии и истории сообщений клиента (read-only)."""
    session = session_manager.get_or_create_session(phone)
    history = session_manager.get_history(phone)
    return {
        "phone": phone,
        "session_id": session.session_id,
        "push_name": session.push_name,
        "human_mode": session.human_mode,
        "started_at": session.started_at,
        "last_activity": session.last_activity,
        "context": session.context,
        "history_count": len(history),
        "history": history,
    }


@app.post("/v1/safety/toggle")
def toggle_safety(req: SafetyToggleRequest):
    """Безопасное переключение рубильника (только для владельца)."""
    try:
        updated = safety_manager.toggle(
            flag=req.flag,
            value=req.value,
            actor=req.actor,
            is_owner=req.is_owner,
            confirm=req.confirm,
        )
        return {"status": "success", "safety": updated}
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
