"""用于持久化委派队列的发送结果判定。"""
import httpx

def send_delegation_text(wecom_userid: str, content: str) -> str:
    from services import wecom_delivery as delivery
    if len(content.encode("utf-8")) > 2048:
        return "failed"

    token = delivery.get_access_token()
    if not token:
        return "failed"
    payload = {
        # 仅文本发送；空白或无效应用ID也属于明确失败。
        "touser": wecom_userid, "msgtype": "text",
        "agentid": int(delivery.WECOM_APP_AGENT_ID or 0),
        "text": {"content": content}, "enable_duplicate_check": 0,
    }
    try:
        result = httpx.post(
            f"{delivery.QYAPI}/message/send?access_token={token}", json=payload, timeout=10,
        ).json()
        if result.get("errcode") in (40014, 42001):
            token = delivery.get_access_token(force_refresh=True)
            if not token: return "failed"
            result = httpx.post(
                f"{delivery.QYAPI}/message/send?access_token={token}", json=payload, timeout=10,
            ).json()
        if result.get("errcode") != 0 or result.get("invaliduser") or result.get("unlicenseduser"):
            return "failed"
        return "sent"
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return "failed"
    except Exception:
        return "uncertain"
