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


def parse_request(text, participants, now=None):
    text = str(text)
    clocks = [m.span() for m in re.finditer(r"\d{1,2}[:：]\d{2}", text)]
    delimiters = [m.start() for m in re.finditer(r"[：:]", text)
                  if not any(start <= m.start() < end for start, end in clocks)]
    if not delimiters:
        raise PrivateMessageError("请用冒号分开时间、接收人和正文")
    position = delimiters[0]
    header, body = text[:position], text[position + 1:]
    recipient = re.search(r"(?:给|向)(.+?)留言", header)
    if not recipient:
        raise PrivateMessageError("请明确给哪位同事留言")
    name = recipient[1].strip()
    matches = [p for p in participants if p.get("active", True)
               and name in [p["name"], *(p.get("aliases") or [])]]
    if len(matches) != 1:
        raise PrivateMessageError("接收人未登记、已停用或有同名，请明确姓名")
    time_header = header[:recipient.start()] + header[recipient.end():]
    mode, scheduled = parse_time(time_header, now)
    return {"recipient_id": matches[0]["id"], "content": validate_content(body),
            "delivery_mode": mode, "scheduled_at": scheduled}


def parse_command(text):
    text = str(text or "").strip()
    exact = {"确认发送": "confirm", "确认留言": "confirm", "我的留言": "list",
             "查看留言": "view", "取消留言": "cancel", "取消发送": "cancel",
             "留言收到": "ack", "收到": "ack"}
    if text in exact:
        return {"operation": exact[text]}
    for prefix, operation in (("修改留言", "modify"), ("改时留言", "retime"), ("回复留言", "reply"), ("回复", "reply")):
        match = re.fullmatch(re.escape(prefix) + r"(?:[，,](.+?))?[：:](.+)", text, re.S)
        if match:
            result = {"operation": operation, "content": match[2].strip()}
            if match[1]:
                result["time_text"] = match[1].strip()
            return result
    return None


def is_private_request(text):
    text = str(text).strip()
    command = parse_command(text)
    if command and text != "收到":
        return True
    if re.match(r"^\d{4}\s", text):
        return False
    recipient = re.search(r"(?:给|向)([^：:\n]{1,100}?)留言", text)
    if not recipient:
        return text.startswith(("私人留言", "留言", "修改留言", "回复留言", "改时留言",
                                "取消留言", "确认留言"))
    prefix = text[:recipient.start()]
    return not re.search(r"提醒(?:一下|下)?我|已经|刚才|刚刚|已$|不要|别|(?<!\d)[：:]|[：:](?!\d)", prefix)
