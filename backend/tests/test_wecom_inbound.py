from services import wecom_inbound


def test_reserve_inbound_rejects_existing_message(monkeypatch):
    class Query:
        def select(self, _cols):
            return self

        def eq(self, _col, _value):
            return self

        def limit(self, _value):
            return self

        def execute(self):
            return type("R", (), {"data": [{"id": "existing"}]})()

    monkeypatch.setattr(
        wecom_inbound,
        "supabase",
        type("DB", (), {"table": lambda _self, _name: Query()})(),
    )

    assert wecom_inbound.reserve_inbound_message(
        "msg-1", "user-1", "User", "完成了"
    ) is False


def test_mark_processed_filters_by_message_and_user(monkeypatch):
    filters = []

    class Query:
        def update(self, _payload):
            return self

        def eq(self, column, value):
            filters.append((column, value))
            return self

        def execute(self):
            return type("R", (), {"data": [{"id": "receipt-1"}]})()

    monkeypatch.setattr(
        wecom_inbound,
        "supabase",
        type("DB", (), {"table": lambda _self, _name: Query()})(),
    )

    wecom_inbound.mark_inbound_processed("msg-1", "user-1")

    assert ("msg_id", "msg-1") in filters
    assert ("user_id", "user-1") in filters
