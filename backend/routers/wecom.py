"""企业微信自建应用回调：URL 验证 + 接收消息（双向对话入口）。

此路由不走登录鉴权——企业微信服务器直接调用，安全靠签名校验 + AES 解密。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from config import WECOM_APP_AES_KEY, WECOM_APP_TOKEN, WECOM_CORP_ID
from services.wecom_app import handle_incoming_text
from services.wecom_crypto import WeComCrypto, verify_signature

router = APIRouter(prefix="/wecom", tags=["wecom"])


def _crypto() -> WeComCrypto:
    if not (WECOM_APP_TOKEN and WECOM_APP_AES_KEY and WECOM_CORP_ID):
        raise HTTPException(status_code=503, detail="企业微信自建应用未配置")
    return WeComCrypto(WECOM_APP_AES_KEY, WECOM_CORP_ID)


@router.get("/callback")
async def verify_url(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """企业微信后台保存回调地址时的一次性 URL 验证。"""
    if not verify_signature(WECOM_APP_TOKEN, timestamp, nonce, echostr, msg_signature):
        raise HTTPException(status_code=403, detail="签名校验失败")
    plain = _crypto().decrypt(echostr)
    return PlainTextResponse(plain)


@router.post("/callback")
async def receive_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    """接收用户在企业微信里发给应用的消息，异步处理后用应用消息回复。"""
    body = await request.body()
    try:
        encrypt = ET.fromstring(body.decode("utf-8")).findtext("Encrypt") or ""
    except ET.ParseError:
        raise HTTPException(status_code=400, detail="消息体不是合法 XML")

    if not encrypt or not verify_signature(WECOM_APP_TOKEN, timestamp, nonce, encrypt, msg_signature):
        raise HTTPException(status_code=403, detail="签名校验失败")

    plain_xml = _crypto().decrypt(encrypt)
    message = ET.fromstring(plain_xml)
    msg_type = message.findtext("MsgType") or ""
    from_user = message.findtext("FromUserName") or ""

    if msg_type == "text" and from_user:
        content = message.findtext("Content") or ""
        # 企业微信要求 5 秒内响应；先回空包，后台处理完用应用消息推回去
        background_tasks.add_task(handle_incoming_text, from_user, content)
    elif from_user:
        background_tasks.add_task(_reply_unsupported, from_user, msg_type)

    return PlainTextResponse("")


def _reply_unsupported(wecom_userid: str, msg_type: str) -> None:
    from services.wecom_app import send_app_text

    send_app_text(wecom_userid, f"暂时只支持文字消息（收到的是 {msg_type}），打字告诉我就行。")
