from datetime import datetime, timezone

from database import supabase
from services.email_service import send_reminder_email


def check_and_send_reminders():
    now = datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("tasks")
        .select("*, users(email)")
        .lte("remind_time", now)
        .eq("status", "pending")
        .eq("reminded", False)
        .execute()
    )

    for task in result.data or []:
        try:
            user_email = task.get("users", {}).get("email")
            if not user_email:
                continue
            send_reminder_email(
                to_email=user_email,
                task_content=task["content"],
                remind_time=task["remind_time"],
            )
            supabase.table("tasks").update({"reminded": True}).eq("id", task["id"]).execute()
        except Exception as exc:
            print(f"Reminder failed for task {task.get('id')}: {exc}")
