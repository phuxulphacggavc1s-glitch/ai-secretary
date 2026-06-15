import importlib


def test_config_uses_frontend_default(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    config = importlib.reload(importlib.import_module("config"))
    assert config.FRONTEND_URL == "http://localhost:5173"


def test_config_reads_wecom_webhook(monkeypatch):
    monkeypatch.setenv("WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test")
    config = importlib.reload(importlib.import_module("config"))
    assert config.WECOM_WEBHOOK_URL.endswith("key=test")
