import base64
import struct

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

from services import memory
from services.wecom_crypto import WeComCrypto, compute_signature, verify_signature


AES_KEY_43 = base64.b64encode(b"0" * 32).decode()[:43]
CORP_ID = "ww1234567890"


def _encrypt(plain: str, aes_key: str, receive_id: str) -> str:
    key = base64.b64decode(aes_key + "=")
    msg = plain.encode("utf-8")
    payload = get_random_bytes(16) + struct.pack(">I", len(msg)) + msg + receive_id.encode()
    pad = 32 - (len(payload) % 32)
    payload += bytes([pad]) * pad
    cipher = AES.new(key, AES.MODE_CBC, key[:16])
    return base64.b64encode(cipher.encrypt(payload)).decode()


def test_signature_roundtrip():
    sig = compute_signature("tok", "123", "456", "abc")
    assert verify_signature("tok", "123", "456", "abc", sig)
    assert not verify_signature("tok", "123", "456", "abc", "bad")


def test_crypto_decrypt_roundtrip():
    plain = "<xml><MsgType>text</MsgType><Content>明天提醒我发货</Content></xml>"
    encrypted = _encrypt(plain, AES_KEY_43, CORP_ID)
    crypto = WeComCrypto(AES_KEY_43, CORP_ID)
    assert crypto.decrypt(encrypted) == plain


def test_crypto_rejects_wrong_receive_id():
    encrypted = _encrypt("<xml/>", AES_KEY_43, "other-corp")
    crypto = WeComCrypto(AES_KEY_43, CORP_ID)
    try:
        crypto.decrypt(encrypted)
        assert False, "应当抛出 receive_id 不匹配"
    except ValueError:
        pass


class FakeMemoryTable:
    def __init__(self, store):
        self.store = store

    def select(self, _cols):
        return self

    def eq(self, _col, _val):
        return self

    def execute(self):
        return type("R", (), {"data": [dict(self.store)]})()

    def upsert(self, row):
        self.store.update(row)
        return self


class FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        assert name == "user_memory"
        return FakeMemoryTable(self.store)


def test_add_fact_dedupes_and_trims(monkeypatch):
    store = {"user_id": "u1", "profile_text": None, "facts": ["供应商老张每月15号结款"]}
    monkeypatch.setattr(memory, "supabase", FakeSupabase(store))

    assert memory.add_fact("u1", "供应商老张每月15号结款") is False
    assert memory.add_fact("u1", "客户小王只在晚上直播后回消息") is True
    assert "客户小王只在晚上直播后回消息" in store["facts"]

    for i in range(20):
        memory.add_fact("u1", f"事实编号{i}用于测试上限填充")
    assert len(store["facts"]) <= memory.MAX_FACTS
