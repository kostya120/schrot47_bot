"""Интеграционные тесты FastAPI эндпоинтов app.py."""

import uuid

from fastapi.testclient import TestClient

from app import app


def test_root_and_health():
    client = TestClient(app)

    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["service"] == "schrot47_bot"
    assert res.json()["transport"] == "Evolution API v2"

    res_h = client.get("/health")
    assert res_h.status_code == 200
    assert res_h.json()["status"] == "healthy"
    assert res_h.json()["outbound_allowed"] is False


def test_webhook_endpoint_via_fastapi():
    client = TestClient(app)
    unique_id = f"API_TEST_MSG_{uuid.uuid4().hex[:8]}"

    payload = {
        "event": "messages.upsert",
        "instance": "shrot47",
        "data": {
            "key": {
                "remoteJid": "77053334455@s.whatsapp.net",
                "fromMe": False,
                "id": unique_id,
            },
            "pushName": "Диас",
            "message": {
                "conversation": "Позови человека",
            },
            "messageType": "conversation",
        },
    }

    res = client.post("/webhook/evolution", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "handoff_initiated"

    # Проверка получения сессии через API
    res_s = client.get("/v1/sessions/77053334455")
    assert res_s.status_code == 200
    s_data = res_s.json()
    assert s_data["phone"] == "77053334455"
    assert s_data["human_mode"] is True
    assert s_data["history_count"] >= 1


def test_safety_toggle_api():
    client = TestClient(app)

    # Несанкционированная попытка переключения
    res_fail = client.post(
        "/v1/safety/toggle",
        json={
            "flag": "production_enabled",
            "value": True,
            "actor": "guest",
            "is_owner": False,
            "confirm": False,
        },
    )
    assert res_fail.status_code == 400

    # Санкционированное переключение с подтверждением
    res_ok = client.post(
        "/v1/safety/toggle",
        json={
            "flag": "production_enabled",
            "value": True,
            "actor": "owner",
            "is_owner": True,
            "confirm": True,
        },
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["safety"]["production_enabled"] is True

    # Возвращаем в безопасный дефолт
    client.post(
        "/v1/safety/toggle",
        json={
            "flag": "production_enabled",
            "value": False,
            "actor": "owner",
            "is_owner": True,
            "confirm": False,
        },
    )
