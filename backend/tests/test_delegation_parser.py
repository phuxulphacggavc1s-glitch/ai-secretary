from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from services import delegation_parser as parser
from services.delegation import DelegationError

def test_candidate_requires_delegation_intent():
    assert parser.is_delegation_request("明天上午给张三下达任务：整理数据")
    assert parser.is_delegation_request("明天给张三安排一个任务")
    assert not parser.is_delegation_request("提醒我给张三打电话")

def test_parser_resolves_only_supplied_colleague(monkeypatch):
    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=
                '{"colleague_name":"张三","content":"整理数据","scheduled_at":"2026-10-05T09:00:00+08:00","due_at":null}'))])
    monkeypatch.setattr(parser, "DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(parser, "OpenAI", lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    result = parser.parse_delegation("明天给张三下达任务", [{"id":"c1","name":"张三","aliases":[],"active":True}],
                                     datetime(2026,10,4,tzinfo=timezone.utc))
    assert result["colleague_id"] == "c1"
    assert result["scheduled_at"].endswith("+00:00")
    with pytest.raises(DelegationError):
        parser.parse_delegation("明天给张三下达任务", [
            {"id":"c1","name":"张三","active":True},{"id":"c2","name":"张三","active":True}])
