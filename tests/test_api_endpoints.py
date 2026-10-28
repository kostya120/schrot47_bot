"""Интеграционные тесты FastAPI эндпоинтов app.py."""

import uuid

from fastapi.testclient import TestClient

from app import app, bot_service


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


def test_webhook_endpoint_via_fastapi(monkeypatch):
    monkeypatch.setattr(bot_service, "webhook_secret", "test-webhook-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-token")
    client = TestClient(app)
    unique_id = f"API_TEST_MSG_{uuid.uuid4().hex[:8]}"
    unique_phone = f"7705{uuid.uuid4().int % 10000000:07d}"

    payload = {
        "event": "messages.upsert",
        "instance": "shrot47",
        "data": {
            "key": {
                "remoteJid": f"{unique_phone}@s.whatsapp.net",
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

    res = client.post("/webhook/evolution", json=payload, headers={"apikey": "test-webhook-secret"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "handoff_initiated"

    # Проверка получения сессии через API
    assert client.get(f"/v1/sessions/{unique_phone}").status_code == 403
    res_s = client.get(f"/v1/sessions/{unique_phone}", headers={"x-admin-key": "test-admin-token"})
    assert res_s.status_code == 200
    s_data = res_s.json()
    assert s_data["phone"] == unique_phone
    assert s_data["human_mode"] is True
    assert s_data["history_count"] >= 1


def test_safety_toggle_api(monkeypatch):
    client = TestClient(app)
    payload = {"flag": "production_enabled", "value": True, "confirm": True}

    # Fails closed while the dedicated administrator token is not configured.
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    assert client.post(
        "/v1/safety/toggle", json=payload, headers={"x-admin-key": "any-value"}
    ).status_code == 403

    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-token")
    assert client.post("/v1/safety/toggle", json=payload).status_code == 403
    assert client.post(
        "/v1/safety/toggle", json=payload, headers={"x-admin-key": "wrong"}
    ).status_code == 403

    # Even an authenticated admin needs explicit confirmation to loosen safety.
    hdrs = {"x-admin-key": "test-admin-token"}
    assert client.post(
        "/v1/safety/toggle",
        json={"flag": "production_enabled", "value": True, "confirm": False},
        headers=hdrs,
    ).status_code == 400

    res_ok = client.post("/v1/safety/toggle", json=payload, headers=hdrs)
    assert res_ok.status_code == 200
    assert res_ok.json()["safety"]["production_enabled"] is True

    # Always restore the safe default in this test.
    res_reset = client.post(
        "/v1/safety/toggle",
        json={"flag": "production_enabled", "value": False, "confirm": False},
        headers=hdrs,
    )
    assert res_reset.status_code == 200
    assert res_reset.json()["safety"]["production_enabled"] is False
