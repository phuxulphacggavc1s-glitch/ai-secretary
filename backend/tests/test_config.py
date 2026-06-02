import importlib


def test_config_uses_frontend_default(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    config = importlib.reload(importlib.import_module("config"))
    assert config.FRONTEND_URL == "http://localhost:5173"
