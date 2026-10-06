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


@pytest.mark.parametrize("text, body, scheduled", [
    ("1分钟后给乙发消息提醒他4点下班", "提醒他4点下班", "2026-10-06T02:01:00+00:00"),
    ("1分钟后给小乙发送一条消息，就说明天放假", "明天放假", "2026-10-06T02:01:00+00:00"),
    ("2026-10-07 09:30向乙发送通知：订单1234请跟进", "订单1234请跟进", "2026-10-07T01:30:00+00:00"),
    ("明天9点通知乙：会议改期", "会议改期", "2026-10-07T01:00:00+00:00"),
    ("给乙发提醒，立即发送：订单1234不要改写", "订单1234不要改写", None),
    ("1分钟后给乙发消息订单1234：无需改写", "订单1234：无需改写", "2026-10-06T02:01:00+00:00"),
])
def test_natural_notices_are_private_and_keep_body_clock_separate(text, body, scheduled):
    assert is_private_request(text)
    result = parse_request(text, PEOPLE, NOW)
    assert result["recipient_id"] == "b"
    assert result["content"] == body
    assert result["scheduled_at"] == scheduled


def test_explicit_colon_body_does_not_remove_content_introduction():
    result = parse_request("1分钟后给乙发消息：内容是1234，不要删", PEOPLE, NOW)
    assert result["content"] == "内容是1234，不要删"


def test_userid_is_exact_and_case_insensitive_not_a_fuzzy_name():
    people = [{**p, "wecom_userid": p["id"].upper()} for p in PEOPLE]
    assert parse_request("1分钟后给b发消息：正文", people, NOW)["recipient_id"] == "b"
    with pytest.raises(PrivateMessageError):
        parse_request("1分钟后给乙二发消息：正文", people, NOW)


@pytest.mark.parametrize("text", [
    "提醒我明天给乙发消息", "明天我自己给乙发消息", "明天我来通知乙",
    "我已经给乙发消息了", "不要给乙发消息", "1分钟后给我发消息：正文",
    "明天9点给乙下达任务：给丙发消息",
])
def test_notice_routing_does_not_hijack_personal_or_formal_requests(text):
    assert not is_private_request(text)


def test_task_words_inside_notice_body_do_not_change_route():
    text = "1分钟后给乙发消息：请下达任务给丙"
    assert is_private_request(text)
    assert parse_request(text, PEOPLE, NOW)["content"] == "请下达任务给丙"


@pytest.mark.parametrize("text", ["明天上午通知乙今天加班", "明天下午告知乙会议改期"])
def test_natural_notice_without_separator_or_explicit_clock_fails_privately(text):
    assert is_private_request(text)
    with pytest.raises(PrivateMessageError):
        parse_request(text, PEOPLE, NOW)

@pytest.mark.parametrize("text", ["1分钟后15点", "1小时后14:30"])
def test_relative_and_absolute_send_time_cannot_be_combined(text):
    with pytest.raises(PrivateMessageError):
        parse_time(text, NOW)

@pytest.mark.parametrize("text", [
    "1分钟后，给乙发消息提醒他4点下班",
    "1分钟后,给乙发送一条消息：提醒他4点下班",
])
def test_separator_between_time_and_recipient_is_supported(text):
    assert is_private_request(text)
    data = parse_request(text, PEOPLE, NOW)
    assert data["content"] == "提醒他4点下班"
    assert data["scheduled_at"] == "2026-10-06T02:01:00+00:00"


def test_comma_after_time_keeps_explicit_formal_task_route():
    from services.delegation_parser import is_delegation_request
    text = "明天9点，给乙下达任务：整理数据"
    assert is_delegation_request(text)
    assert not is_private_request(text)

def test_body_starting_digits_and_colon_is_not_send_time():
    parsed = parse_request("立即给乙发消息1234：验证码不要改", PEOPLE, NOW)
    assert parsed["content"] == "1234：验证码不要改"


def test_cancel_sentence_is_claimed_but_never_creates_message():
    text = "取消1分钟后给乙发消息：不要发送"
    assert is_private_request(text)
    with pytest.raises(PrivateMessageError, match="取消留言"):
        parse_request(text, PEOPLE, NOW)


def test_reverse_arrange_task_word_order_is_formal():
    from services.delegation_parser import is_delegation_request
    text = "明天9点安排任务给乙：整理数据"
    assert is_delegation_request(text)
    assert not is_private_request(text)

@pytest.mark.parametrize("text, body", [
    ("立即给乙发消息1234-5678：订单编号不要改", "1234-5678：订单编号不要改"),
    ("1分钟后给乙发消息1234/5678：请核对", "1234/5678：请核对"),
])
def test_hyphenated_or_slashed_body_numbers_are_not_time(text, body):
    assert parse_request(text, PEOPLE, NOW)["content"] == body
