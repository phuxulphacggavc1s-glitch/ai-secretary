"""私人留言的有限命令和本地时间解析，不处理AI或发送。"""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


class PrivateMessageError(ValueError):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def as_time(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise PrivateMessageError("请提供带时区的时间")
    return result.astimezone(timezone.utc)


def validate_content(content):
    content = str(content or "").strip()
    if not content or "\x00" in content:
        raise PrivateMessageError("请填写留言正文")
    if len(content.encode("utf-8")) > 1200:
        raise PrivateMessageError("留言过长，请缩短到400个汉字以内")
    return content


def _number(text):
    if text.isdigit():
        return int(text)
    digits = {char: n for n, char in enumerate("零一二三四五六七八九")}
    if text == "两":
        return 2
    if "十" in text and text.count("十") == 1:
        left, right = text.split("十")
        if (not left or left in digits) and (not right or right in digits):
            return digits.get(left, 1) * 10 + digits.get(right, 0)
    if text in digits:
        return digits[text]
    raise PrivateMessageError("请把时间改为明确数字")


def parse_time(text, now=None):
    now = as_time(now or utcnow())
    text = str(text or "").strip()
    if re.search(r"昨天|前天|去年|明年|周|星期|月底|月初|下月|下个月|上月|下年", text):
        raise PrivateMessageError("请把发送时间写成具体日期和时刻")
    date_words = re.findall(r"今天|明天|后天", text)
    explicit_dates = re.findall(r"20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?", text)
    month_dates = re.findall(r"(?<!\d)\d{1,2}月\d{1,2}日", text) if not explicit_dates else []
    date_count = len(date_words) + len(explicit_dates) + len(month_dates)
    if date_count > 1:
        raise PrivateMessageError("请只填写一个日期")
    if date_count and re.search(r"(分钟|小时)后", text):
        raise PrivateMessageError("具体日期和相对时间不能同时使用")
    if re.search(r"立即|现在|马上", text):
        if date_count or re.search(r"[0-9零一二两三四五六七八九十]+[年月日点时]|[:：]\d{2}|后", text):
            raise PrivateMessageError("立即和定时时间不能同时使用")
        return "immediate", None
    if len(re.findall(r"([0-9零一二两三四五六七八九十]+)(分钟|小时)后", text)) > 1:
        raise PrivateMessageError("请只填写一个发送时间")
    clocks = re.findall(r"(?<!\d)\d{1,2}[:：]\d{2}(?!\d)|[0-9零一二两三四五六七八九十]+[点时]", text)
    if len(clocks) > 1 or sum(word in text for word in ("上午", "下午", "晚上")) > 1:
        raise PrivateMessageError("请只填写一个明确时刻")
    relative = re.search(r"([0-9零一二两三四五六七八九十]+)(分钟|小时)后", text)
    if relative:
        if clocks:
            raise PrivateMessageError("具体时刻和相对时间不能同时使用")
        amount = _number(relative[1])
        if amount <= 0:
            raise PrivateMessageError("定时时间必须在未来")
        result = now + timedelta(**{"minutes" if relative[2] == "分钟" else "hours": amount})
        return "scheduled", result.isoformat()
    local = now.astimezone(SHANGHAI)
    day = local.date()
    explicit = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})(?:日)?", text)
    month_day = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日", text)
    try:
        if explicit:
            day = datetime(int(explicit[1]), int(explicit[2]), int(explicit[3])).date()
        elif month_day:
            day = datetime(local.year, int(month_day[1]), int(month_day[2])).date()
        elif "后天" in text:
            day += timedelta(days=2)
        elif "明天" in text:
            day += timedelta(days=1)
        time_match = re.search(r"(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)", text)
        if time_match:
            hour, minute = int(time_match[1]), int(time_match[2])
        else:
            time_match = re.search(r"([0-9零一二两三四五六七八九十]+)[点时](?:(半)|([0-9零一二两三四五六七八九十]+)分?)?", text)
            if not time_match:
                raise PrivateMessageError("请补充具体时间，例如明天9点，或明确说立即发送")
            hour = _number(time_match[1])
            minute = 30 if time_match[2] else _number(time_match[3]) if time_match[3] else 0
        if hour == 12 and ("晚上" in text or "上午" in text):
            raise PrivateMessageError("这个时刻有歧义，请使用24小时制时间，如00:00或12:00")
        if "下午" in text or "晚上" in text:
            if not 1 <= hour <= 12:
                raise PrivateMessageError("请使用下午1点到12点，或24小时制时间")
            if hour < 12:
                hour += 12
        elif "上午" in text:
            if not 1 <= hour <= 12:
                raise PrivateMessageError("上午时间不明确")
            if hour == 12:
                hour = 0
        result = datetime(day.year, day.month, day.day, hour, minute, tzinfo=SHANGHAI).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, PrivateMessageError):
            raise
        raise PrivateMessageError("日期或时间不合法，请重新填写") from None
    if result <= now:
        raise PrivateMessageError("这个时间已经过去，请重新设置未来时间")
    return "scheduled", result.isoformat()


_MESSAGE_PATTERN = re.compile(
    r"(?:给|向)(?P<name>[^：:\n，,]{1,100}?)(?P<verb>留言|发(?:送)?(?:一条|条|个)?(?:消息|信息|通知|提醒))")
_NOTICE_PATTERN = re.compile(r"(?:通知|告知)(?P<name>(?!我|自己)[^：:\n，,]{1,100})")
_TASK_PATTERNS = (
    r"(?:给|让|向)[^：:\n，,]{1,100}?(?:下达|委派|安排)(?:一个|一项|项|个)?(?:任务|事项)",
    r"(?:下达|委派|安排)(?:一个|一项|项|个)?(?:任务|事项)[^：:\n，,]*给",
)


def _first_separator(text, punctuation="：:"):
    clocks = [m.span() for m in re.finditer(r"\d{1,2}[:：]\d{2}", text)]
    for match in re.finditer("[" + re.escape(punctuation) + "]", text):
        if not any(start <= match.start() < end for start, end in clocks):
            return match.start()
    return -1


def _message_match(text):
    matches = [m for pattern in (_MESSAGE_PATTERN, _NOTICE_PATTERN)
               if (m := pattern.search(text))]
    return min(matches, key=lambda m: m.start()) if matches else None


def _valid_prefix(text):
    return not re.search(
        r"提醒(?:一下|下)?我|我(?:自己|来)|已经|刚才|刚刚|已$|不要|不用|别|取消|"
        r"(?<!\d)[：:]|[：:](?!\d)", text)


def is_formal_task_request(text):
    text = str(text or "").strip()
    boundary = _first_separator(text, "：:。；;\n")
    header = text[:boundary] if boundary >= 0 else text
    tasks = [m for pattern in _TASK_PATTERNS if (m := re.search(pattern, header))]
    if not tasks:
        return False
    task = min(tasks, key=lambda m: m.end())
    message = _message_match(header)
    if message and message.start() <= task.start() and message.end() < task.end():
        return False
    return _valid_prefix(header[:task.start()])


def _time_suffix(text):
    if not text.strip(" ，,\t"):
        return False
    leftover = re.sub(r"立即|现在|马上|今天|明天|后天|上午|下午|晚上|发送|分钟|小时", "", text)
    recognizable = re.search(
        r"立即|现在|马上|今天|明天|后天|[0-9零一二两三四五六七八九十]+[点时]|"
        r"(?<!\d)\d{1,2}[:：]\d{2}(?!\d)|[0-9零一二两三四五六七八九十]+(?:分钟|小时)后|"
        r"20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?|(?<!\d)\d{1,2}月\d{1,2}日", text)
    return bool(recognizable) and not re.search(
        r"[^0-9零一二两三四五六七八九十年/月日点时分半后:：\-\s，,]", leftover)


def parse_request(text, participants, now=None):
    text = str(text)
    if is_formal_task_request(text):
        raise PrivateMessageError("正式任务请使用委派入口，消息请明确说发消息或留言")
    recipient = _message_match(text)
    if not recipient:
        raise PrivateMessageError("请明确给哪位同事留言")
    if not _valid_prefix(text[:recipient.start()]):
        raise PrivateMessageError("取消留言请直接回复“取消留言”，其他操作请明确写收件人和发送时间")
    name = recipient["name"].strip()
    matches = [p for p in participants if p.get("active", True) and (
        name in [p["name"], *(p.get("aliases") or [])]
        or (p.get("wecom_userid") and name.lower() == p["wecom_userid"].lower()))]
    if len(matches) != 1:
        raise PrivateMessageError("接收人未登记、已停用或有同名，请明确姓名")
    suffix = text[recipient.end():]
    position = _first_separator(suffix)
    time_header = text[:recipient.start()]
    explicit_body = False
    if position >= 0:
        tail_header = suffix[:position]
        if not tail_header.strip(" ，,\t") or _time_suffix(tail_header):
            time_header += tail_header
            body = suffix[position + 1:]
            explicit_body = True
    if not explicit_body:
        if recipient.re is _NOTICE_PATTERN:
            raise PrivateMessageError("请用冒号分开接收人和正文，例如明天9点通知同事：内容")
        body = suffix.lstrip(" ，,\t")
        body = re.sub(r"^(?:就说|内容是|内容为)[：:]?", "", body, count=1)
    mode, scheduled = parse_time(time_header, now)
    return {"recipient_id": matches[0]["id"], "content": validate_content(body),
            "delivery_mode": mode, "scheduled_at": scheduled}


def parse_command(text):
    text = str(text or "").strip()
    exact = {"确认发送": "confirm", "确认留言": "confirm", "我的留言": "list",
             "查看留言": "view", "取消留言": "cancel", "取消发送": "cancel",
             "留言收到": "ack", "收到": "ack"}
    exact_text = text[:-1].rstrip() if text.endswith(("。", ".", "！", "!")) else text
    if exact_text in exact:
        return {"operation": exact[exact_text]}
    for prefix, operation in (("修改留言", "modify"), ("改时留言", "retime"), ("回复留言", "reply"), ("回复", "reply")):
        match = re.fullmatch(re.escape(prefix) + r"(?:[，,](.+?))?[：:](.+)", text, re.S)
        if match:
            result = {"operation": operation, "content": match[2].strip()}
            if match[1]:
                result["time_text"] = match[1].strip()
            return result
    return None


def is_private_request(text):
    text = str(text or "").strip()
    command = parse_command(text)
    if command and not (command["operation"] == "ack" and re.fullmatch(r"收到\s*[。.!！]?", text)):
        return True
    if re.match(r"^\d{4}\s", text) or is_formal_task_request(text):
        return False
    boundary = _first_separator(text, "：:。；;\n")
    header = text[:boundary] if boundary >= 0 else text
    recipient = _message_match(header)
    if not recipient:
        return text.startswith(("私人留言", "留言", "修改留言", "回复留言", "改时留言",
                                "取消留言", "确认留言"))
    prefix = header[:recipient.start()]
    return (recipient["name"].strip() not in ("我", "自己")
            and (_valid_prefix(prefix) or prefix.strip().startswith("取消")))
