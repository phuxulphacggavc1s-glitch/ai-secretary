"""Private text delivery with explicit rejection versus unknown outcome."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re

import httpx

from services import wecom_delivery


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    error_code: str | None = None


def _result(status: str, error_code: str | None = None) -> DeliveryResult:
    if error_code is not None:
        logger.warning("private message delivery status=%s error_code=%s", status, error_code)
    return DeliveryResult(status, error_code)


def _send_once(token: str, payload: dict) -> DeliveryResult:
    # A response lost after connecting may represent an accepted message.
    try:
        response = httpx.post(
            f"{wecom_delivery.QYAPI}/message/send",
            params={"access_token": token},
            json=payload,
            timeout=10,
        )
    except httpx.ConnectTimeout:
        return _result("failed", "CONNECT_TIMEOUT")
    except httpx.ConnectError:
        return _result("failed", "CONNECT_ERROR")
    except httpx.ReadTimeout:
        return _result("uncertain", "READ_TIMEOUT")
    except httpx.WriteTimeout:
        return _result("uncertain", "WRITE_TIMEOUT")
    except Exception:
        return _result("uncertain", "REQUEST_ERROR")

    status = response.status_code
    if type(status) is not int or not 100 <= status <= 599:
        return _result("uncertain", "INVALID_RESPONSE")
    if 400 <= status < 500:
        return _result("failed", f"HTTP_{status}")
    if status != 200:
        return _result("uncertain", f"HTTP_{status}")

    try:
        body = response.json()
    except Exception:
        return _result("uncertain", "INVALID_RESPONSE")
    if not isinstance(body, dict):
        return _result("uncertain", "INVALID_RESPONSE")
    errcode = body.get("errcode")
    if type(errcode) is not int or not -1 <= errcode <= 99999999:
        return _result("uncertain", "INVALID_RESPONSE")
    if errcode != 0:
        return _result("failed", f"WECOM_{errcode}")
    for field, error_code in (("invaliduser", "INVALID_USER"), ("unlicenseduser", "UNLICENSED_USER")):
        value = body.get(field, "")
        if not isinstance(value, str):
            return _result("uncertain", "INVALID_RESPONSE")
        if value:
            return _result("failed", error_code)
    return DeliveryResult("sent")


def send_private_text(userid: str, content: str) -> DeliveryResult:
    if (
        not isinstance(userid, str)
        or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", userid)
        or userid.lower() == "@all"
    ):
        return _result("failed", "INVALID_USERID")
    if not isinstance(content, str) or not content.strip():
        return _result("failed", "INVALID_CONTENT")
    try:
        content_bytes = content.encode("utf-8")
    except UnicodeEncodeError:
        return _result("failed", "INVALID_CONTENT")
    if len(content_bytes) > 2048:
        return _result("failed", "CONTENT_TOO_LONG")

    agent_id = wecom_delivery.WECOM_APP_AGENT_ID
    if type(agent_id) not in (str, int) or not re.fullmatch(r"[0-9]+", str(agent_id)):
        return _result("failed", "INVALID_AGENT_ID")
    try:
        agent_id = int(agent_id)
    except ValueError:
        return _result("failed", "INVALID_AGENT_ID")
    if agent_id <= 0:
        return _result("failed", "INVALID_AGENT_ID")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (wecom_delivery.WECOM_CORP_ID, wecom_delivery.WECOM_APP_SECRET)
    ):
        return _result("failed", "NOT_CONFIGURED")

    payload = {
        "touser": userid,
        "msgtype": "text",
        "agentid": agent_id,
        "text": {"content": content},
        # Content-based dedup would hide separately confirmed identical notes.
        # Persistent operation claims, not body equality, prevent replays.
        "enable_duplicate_check": 0,
    }
    # Only an official token rejection permits another HTTP request here.
    for force_refresh in (False, True):
        try:
            token = (
                wecom_delivery.get_access_token(force_refresh=True)
                if force_refresh else wecom_delivery.get_access_token()
            )
        except Exception:
            return _result("failed", "TOKEN_ERROR")
        if not isinstance(token, str) or not token.strip():
            return _result("failed", "TOKEN_UNAVAILABLE")
        result = _send_once(token, payload)
        if force_refresh or result.status != "failed" or result.error_code not in ("WECOM_40014", "WECOM_42001"):
            return result
