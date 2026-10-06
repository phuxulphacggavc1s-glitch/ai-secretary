from datetime import datetime, timezone
import pytest

from services.private_message_policy import (
    PrivateMessageError, parse_request, parse_time, parse_command, is_private_request,
)

NOW = datetime(2026, 10, 6, 2, 0, tzinfo=timezone.utc)
PEOPLE = [
    {"id": "a", "name": "甲", "aliases": [], "active": True},
    {"id": "b", "name": "乙", "aliases": ["小乙"], "active": True},
    {"id": "c", "name": "丙", "aliases": [], "active": False},
]


def test_request_preserves_body_and_does_not_generate_codes():
    result = parse_request("明天9点给小乙留言：订单备注不要改写，明天不要重复发送", PEOPLE, NOW)
    assert result == {
        "recipient_id": "b", "content": "订单备注不要改写，明天不要重复发送",
        "delivery_mode": "scheduled", "scheduled_at": "2026-10-07T01:00:00+00:00",
    }


@pytest.mark.parametrize("text, expected", [
    ("2028年12月31日23点59分", "2028-12-31T15:59:00+00:00"),
    ("2026-10-07 09:30", "2026-10-07T01:30:00+00:00"),
    ("明天下午3点半", "2026-10-07T07:30:00+00:00"),
    ("后天上午9点", "2026-10-08T01:00:00+00:00"),
    ("十分钟后", "2026-10-06T02:10:00+00:00"),
    ("1小时后", "2026-10-06T03:00:00+00:00"),
])
def test_local_explicit_times(text, expected):
    assert parse_time(text, NOW) == ("scheduled", expected)


def test_immediate_has_no_past_timestamp():
    assert parse_time("立即发送", NOW) == ("immediate", None)
    assert parse_request("给乙留言，立即发送：原文", PEOPLE, NOW)["scheduled_at"] is None


@pytest.mark.parametrize("text", ["明天", "有空", "2026-02-30 09:00", "今天9点", "明天下午13点", "0分钟后"])
def test_ambiguous_invalid_or_past_time_is_rejected(text):
    with pytest.raises(PrivateMessageError):
        parse_time(text, NOW)


@pytest.mark.parametrize("text", [
    "给陌生人留言，立即发送：正文",
    "给丙留言，立即发送：正文",
    "给乙留言：正文",
    "明天9点给乙留言",
    "明天9点给乙留言：",
])
def test_missing_or_unregistered_recipient_and_missing_time_rejected(text):
    with pytest.raises(PrivateMessageError):
        parse_request(text, PEOPLE, NOW)


def test_ambiguous_alias_is_not_guessed():
    people = [*PEOPLE, {"id": "d", "name": "丁", "aliases": ["小乙"], "active": True}]
    with pytest.raises(PrivateMessageError):
        parse_request("给小乙留言，立即发送：正文", people, NOW)


def test_overlong_body_is_not_truncated():
    with pytest.raises(PrivateMessageError):
        parse_request("给乙留言，立即发送：" + "字" * 401, PEOPLE, NOW)


@pytest.mark.parametrize("text, operation", [
    ("确认发送", "confirm"), ("我的留言", "list"), ("查看留言", "view"),
    ("取消留言", "cancel"), ("取消发送", "cancel"), ("留言收到", "ack"),
    ("收到", "ack"), ("修改留言：新正文", "modify"),
    ("改时留言：明天9点", "retime"), ("回复留言：补充", "reply"),
])
def test_commands_require_no_visible_message_code(text, operation):
    assert parse_command(text)["operation"] == operation


def test_timed_reply_preserves_body():
    parsed = parse_command("回复留言，明天9点发送：补充内容")
    assert parsed == {"operation": "reply", "content": "补充内容", "time_text": "明天9点发送"}


def test_private_intent_is_distinct_from_delegation():
    assert is_private_request("给乙留言，立即发送：正文")
    assert not is_private_request("给乙下达任务：整理数据")
    assert parse_command("同意 7859") is None

def test_ascii_body_separator_does_not_split_clock_colon():
    result = parse_request("2026-10-07 09:30给乙留言:正文", PEOPLE, NOW)
    assert result["content"] == "正文"
    assert result["scheduled_at"] == "2026-10-07T01:30:00+00:00"


@pytest.mark.parametrize("text", ["明天上午9点下午3点", "明天晚上12点", "明天上午12点"])
def test_multiple_or_ambiguous_clock_is_not_guessed(text):
    with pytest.raises(PrivateMessageError):
        parse_time(text, NOW)

@pytest.mark.parametrize("text", [
    "提醒我明天给客户留言",
    "7859 进展 已给客户留言",
    "进展：已经给客户留言",
    "我已经给乙留言了",
])
def test_existing_personal_and_delegation_text_is_not_hijacked(text):
    assert not is_private_request(text)


@pytest.mark.parametrize("text", [
    "下周9点", "昨天15点", "去年10月7日9点", "月底15点",
    "明天1小时后", "明天后天9点", "明天2026-10-08 09:00",
    "立即今天15点", "立即明天九点",
])
def test_unsupported_or_conflicting_time_is_rejected(text):
    with pytest.raises(PrivateMessageError):
        parse_time(text, NOW)


def test_incomplete_private_note_stays_in_private_route():
    assert is_private_request("留言：这是私密正文")


@pytest.mark.parametrize("text", ["修改留言：", "回复留言：", "改时留言：", "取消留言 这条"])
def test_malformed_private_command_is_not_legacy_input(text):
    assert is_private_request(text)
