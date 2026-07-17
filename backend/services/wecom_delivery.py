"""企业微信自建应用的用户映射、access token 与文本发送。"""
from __future__ import annotations

import json
import time

import httpx

from config import (
    WECOM_APP_AGENT_ID,
    WECOM_APP_SECRET,
    WECOM_APP_USER_MAP,
    WECOM_CORP_ID,
)


QYAPI = "https://qyapi.weixin.qq.com/cgi-bin"
_token_cache = {"token": None, "expires_at": 0.0}


def is_wecom_app_configured() -> bool:
    return bool(WECOM_CORP_ID and WECOM_APP_SECRET and WECOM_APP_AGENT_ID)


def user_map() -> dict[str, str]:
    try:
        data = json.loads(WECOM_APP_USER_MAP or "{}")
    except json.JSONDecodeError as exc:
        print(f"WECOM_APP_USER_MAP invalid: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(wecom_userid): str(user_id)
        for wecom_userid, user_id in data.items()
        if wecom_userid and user_id
    }


def bound_user_ids() -> list[str]:
    return list(dict.fromkeys(user_map().values()))


def resolve_wecom_userid(user_id: str) -> str | None:
    return next(
        (wecom_userid for wecom_userid, mapped_id in user_map().items() if mapped_id == user_id),
        None,
    )


def resolve_supabase_user_id(wecom_userid: str) -> str | None:
    return user_map().get(wecom_userid)


def get_access_token(force_refresh: bool = False) -> str | None:
    if (
        not force_refresh
        and _token_cache["token"]
        and time.time() < _token_cache["expires_at"]
    ):
        return _token_cache["token"]
    try:
        response = httpx.get(
            f"{QYAPI}/gettoken",
            params={"corpid": WECOM_CORP_ID, "corpsecret": WECOM_APP_SECRET},
            timeout=10,
        )
        result = response.json()
        if result.get("errcode") == 0:
            _token_cache["token"] = result["access_token"]
            _token_cache["expires_at"] = (
                time.time() + int(result.get("expires_in", 7200)) - 200
            )
            return _token_cache["token"]
        print(f"wecom gettoken failed: errcode={result.get('errcode')}")
    except Exception as exc:
        print(f"wecom gettoken error: {exc}")
    return None


def send_app_text(wecom_userid: str, content: str) -> bool:
    token = get_access_token()
    if not token:
        return False

    payload = {
        "touser": wecom_userid,
        "msgtype": "text",
        "agentid": int(WECOM_APP_AGENT_ID),
        "text": {"content": content[:2000]},
    }
    try:
        result = httpx.post(
            f"{QYAPI}/message/send?access_token={token}",
            json=payload,
            timeout=10,
        ).json()
        if result.get("errcode") in (40014, 42001):
            token = get_access_token(force_refresh=True)
            if not token:
                return False
            result = httpx.post(
                f"{QYAPI}/message/send?access_token={token}",
                json=payload,
                timeout=10,
            ).json()
        if result.get("errcode") != 0:
            print(f"wecom send failed: errcode={result.get('errcode')}")
            return False
        return True
    except Exception as exc:
        print(f"wecom send error: {exc}")
        return False
