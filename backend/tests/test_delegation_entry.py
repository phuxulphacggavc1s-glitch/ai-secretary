from types import SimpleNamespace

def test_api_requires_timezone_on_scheduled_time(monkeypatch, env):
    prepare(monkeypatch, env)
    app = FastAPI()
    app.include_router(delegation.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1")
    client = TestClient(app)
    response = client.post("/delegation/tasks", json={
        "colleague_id":"1", "content":"整理数据", "scheduled_at":"2026-10-05T09:00:00"})
    assert response.status_code == 422

from fastapi import FastAPI
from fastapi.testclient import TestClient
from auth import get_current_user
from routers import delegation
from services import delegation_entry as entry
from test_delegation import env, create

def prepare(monkeypatch, env):
    service, _, _, _, _ = env
    monkeypatch.setattr(entry, "WECOM_DELEGATION_ENABLED", True)
    monkeypatch.setattr(entry, "get_service", lambda: service)
    monkeypatch.setattr(entry, "resolve_supabase_user_id", lambda wid: "u1" if wid == "Owner" else None)
    monkeypatch.setattr(entry, "bound_user_ids", lambda: ["u1"])
    monkeypatch.setattr(entry, "reserve_inbound_message", lambda *_: True)
    monkeypatch.setattr(entry, "mark_inbound_processed", lambda *_: None)
    monkeypatch.setattr(entry, "mark_inbound_failed", lambda *_: None)
    monkeypatch.setattr(entry, "send_app_text", lambda *_: True)
    return service

def test_colleague_reply_does_not_require_owner_binding(monkeypatch, env):
    service = prepare(monkeypatch, env)
    task = create(env); service.scan("u1"); service.action("u1", task["id"], "approve")
    assert entry.handle_delegation_message("ZhangSan", "完成", "msg-1")
    assert service.get_task("u1", task["id"])["task_status"] == "completed"

def test_duplicate_callback_does_not_repeat_approval(monkeypatch, env):
    service = prepare(monkeypatch, env)
    task = create(env); service.scan("u1")
    monkeypatch.setattr(entry, "reserve_inbound_message", lambda *_: False)
    entry.handle_delegation_message("Owner", "同意", "msg-1")
    assert service.get_task("u1", task["id"])["delivery_status"] == "not_sent"

def test_api_is_authenticated_and_approve_is_disabled_by_default(monkeypatch, env):
    service = prepare(monkeypatch, env)
    app = FastAPI()
    app.include_router(delegation.router)
    client = TestClient(app)
    assert client.get("/delegation/tasks").status_code in (401, 403)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1")
    task = create(env); service.scan("u1")
    monkeypatch.setattr(entry, "WECOM_DELEGATION_ENABLED", False)
    response = client.post(f"/delegation/tasks/{task['id']}/action", json={"action":"approve"})
    assert response.status_code == 409
    assert service.get_task("u1", task["id"])["delivery_status"] == "not_sent"
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u2")
    assert client.get(f"/delegation/tasks/{task['id']}/events").status_code == 400

def test_unknown_sender_falls_back_without_access(monkeypatch, env):
    prepare(monkeypatch, env)
    assert not entry.handle_delegation_message("Stranger", "完成", "msg-x")
