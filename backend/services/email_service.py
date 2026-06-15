from html import escape

import resend

from config import FROM_EMAIL, RESEND_API_KEY


# Deprecated: V2 reminder channel is Enterprise WeChat. Kept for legacy callers.
def _can_send() -> bool:
    return bool(RESEND_API_KEY and FROM_EMAIL)


def send_reminder_email(to_email: str, task_content: str, remind_time: str):
    if not _can_send():
        print("Resend is not configured; skipped reminder email")
        return None

    safe_task_content = escape(task_content)
    safe_remind_time = escape(remind_time)
    resend.api_key = RESEND_API_KEY
    return resend.Emails.send(
        {
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": f"【AI秘书提醒】{task_content}",
            "html": f"""
            <div style="font-family: sans-serif; padding: 20px;">
                <h2>你有一个待办提醒</h2>
                <p style="font-size: 18px; color: #333;"><strong>{safe_task_content}</strong></p>
                <p style="color: #666;">提醒时间：{safe_remind_time}</p>
                <hr/>
                <p style="color: #999; font-size: 12px;">来自 AI 秘书</p>
            </div>
            """,
        }
    )


def send_daily_report_email(to_email: str, report_content: str, report_date: str):
    if not _can_send():
        print("Resend is not configured; skipped daily report email")
        return None

    safe_report_content = escape(report_content)
    safe_report_date = escape(report_date)
    resend.api_key = RESEND_API_KEY
    return resend.Emails.send(
        {
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": f"【AI秘书日报】{report_date} 每日总结",
            "html": f"""
            <div style="font-family: sans-serif; padding: 20px;">
                <h2>今日总结 · {safe_report_date}</h2>
                <p style="font-size: 16px; line-height: 1.8; color: #333;">{safe_report_content}</p>
                <hr/>
                <p style="color: #999; font-size: 12px;">来自 AI 秘书</p>
            </div>
            """,
        }
    )
