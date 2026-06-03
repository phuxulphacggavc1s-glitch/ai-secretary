from services import email_service


def test_reminder_email_escapes_user_controlled_html(monkeypatch):
    sent = {}

    monkeypatch.setattr(email_service, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(email_service, "FROM_EMAIL", "from@example.com")
    monkeypatch.setattr(email_service.resend.Emails, "send", lambda payload: sent.update(payload))

    email_service.send_reminder_email(
        to_email="to@example.com",
        task_content="<b>报价</b>",
        remind_time="<script>alert(1)</script>",
    )

    assert "<b>报价</b>" not in sent["html"]
    assert "&lt;b&gt;报价&lt;/b&gt;" in sent["html"]
    assert "<script>" not in sent["html"]


def test_daily_report_email_escapes_report_html(monkeypatch):
    sent = {}

    monkeypatch.setattr(email_service, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(email_service, "FROM_EMAIL", "from@example.com")
    monkeypatch.setattr(email_service.resend.Emails, "send", lambda payload: sent.update(payload))

    email_service.send_daily_report_email(
        to_email="to@example.com",
        report_content="<img src=x onerror=alert(1)>",
        report_date="<b>2026-06-03</b>",
    )

    assert "<img" not in sent["html"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in sent["html"]
    assert "<b>2026-06-03</b>" not in sent["html"]
