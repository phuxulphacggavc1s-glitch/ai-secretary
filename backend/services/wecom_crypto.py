"""企业微信自建应用消息加解密（官方 WXBizMsgCrypt 算法的精简实现）。"""
from __future__ import annotations

import base64
import hashlib
import struct

from Crypto.Cipher import AES


def compute_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    items = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()


def verify_signature(token: str, timestamp: str, nonce: str, encrypt: str, signature: str) -> bool:
    return compute_signature(token, timestamp, nonce, encrypt) == signature


class WeComCrypto:
    """解密企业微信回调消息。receive_id 对自建应用回调而言是 CorpID。"""

    def __init__(self, aes_key: str, receive_id: str):
        self.key = base64.b64decode(aes_key + "=")
        if len(self.key) != 32:
            raise ValueError("EncodingAESKey 无效（解码后应为 32 字节）")
        self.receive_id = receive_id

    def decrypt(self, encrypt_b64: str) -> str:
        cipher = AES.new(self.key, AES.MODE_CBC, self.key[:16])
        plain = cipher.decrypt(base64.b64decode(encrypt_b64))
        pad = plain[-1]
        if isinstance(pad, str):
            pad = ord(pad)
        if pad < 1 or pad > 32:
            raise ValueError("解密失败：填充字节非法")
        plain = plain[:-pad]
        content = plain[16:]
        msg_len = struct.unpack(">I", content[:4])[0]
        msg = content[4 : 4 + msg_len].decode("utf-8")
        receive_id = content[4 + msg_len :].decode("utf-8")
        if self.receive_id and receive_id != self.receive_id:
            raise ValueError("解密失败：receive_id 不匹配")
        return msg
