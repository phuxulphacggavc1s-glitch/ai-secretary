from services import wecom_delivery


def test_bound_users_and_reverse_lookup(monkeypatch):
    monkeypatch.setattr(
        wecom_delivery,
        "WECOM_APP_USER_MAP",
        '{"User":"user-uuid","Colleague":"other-uuid"}',
    )

    assert wecom_delivery.bound_user_ids() == ["user-uuid", "other-uuid"]
    assert wecom_delivery.resolve_wecom_userid("user-uuid") == "User"
    assert wecom_delivery.resolve_supabase_user_id("User") == "user-uuid"


def test_send_app_text_refreshes_expired_token(monkeypatch):
    token_calls = []
    payloads = []
    replies = iter(
        [
            {"errcode": 42001},
            {"errcode": 0, "errmsg": "ok"},
        ]
    )

    class Response:
        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    def fake_token(force_refresh=False):
        token_calls.append(force_refresh)
        return "new-token" if force_refresh else "old-token"

    def fake_post(_url, json, timeout):
        payloads.append(json)
        return Response(next(replies))

    monkeypatch.setattr(wecom_delivery, "get_access_token", fake_token)
    monkeypatch.setattr(wecom_delivery.httpx, "post", fake_post)
    monkeypatch.setattr(wecom_delivery, "WECOM_APP_AGENT_ID", "1000005")

    assert wecom_delivery.send_app_text("User", "测试提醒") is True
    assert token_calls == [False, True]
    assert payloads[-1]["touser"] == "User"
    assert payloads[-1]["text"]["content"] == "测试提醒"
