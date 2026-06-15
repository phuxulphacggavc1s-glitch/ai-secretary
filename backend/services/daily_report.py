from datetime import date, datetime, timedelta

from openai import OpenAI
import pytz

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from database import supabase

REPORT_PROMPT = """你是用户的AI秘书，帮用户生成今天的工作总结。

【今日数据】
完成任务（{done_count}条）：{done_tasks}
未完成任务（{pending_count}条）：{pending_tasks}
明日提醒：{tomorrow_reminders}

【要求】
- 用轻松、鼓励的语气，像朋友一样
- 100字以内
- 重点提示未完成中最紧急的事项
- 如果今天全部完成了，给用户真诚的鼓励

直接输出总结文字，不要加任何标题或格式。"""


def _fallback_report(done_count: int, pending_count: int) -> str:
    if pending_count == 0:
        return f"今天完成了 {done_count} 件事，待办都清空了。今晚可以轻松收尾，明天继续保持节奏。"
    return f"今天完成了 {done_count} 件事，还有 {pending_count} 件待处理。建议先处理有提醒时间的事项，避免明天堆积。"


def _generate_report_text(prompt: str, done_count: int, pending_count: int) -> str:
    if not DEEPSEEK_API_KEY:
        return _fallback_report(done_count, pending_count)
    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"Daily report AI failed: {exc}")
        return _fallback_report(done_count, pending_count)


def generate_daily_reports():
    tz = pytz.timezone("Asia/Shanghai")
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=tz).isoformat()
    today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=tz).isoformat()
    tomorrow_end = datetime.combine(tomorrow, datetime.max.time()).replace(tzinfo=tz).isoformat()

    users = supabase.table("users").select("id, email").execute()

    for user in users.data or []:
        user_id = user["id"]
        try:
            done = (
                supabase.table("tasks")
                .select("content")
                .eq("user_id", user_id)
                .eq("status", "done")
                .gte("updated_at", today_start)
                .lte("updated_at", today_end)
                .execute()
            )
            pending = (
                supabase.table("tasks")
                .select("content")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )
            tomorrow_tasks = (
                supabase.table("tasks")
                .select("content, remind_time")
                .eq("user_id", user_id)
                .eq("status", "pending")
                .gte("remind_time", today_end)
                .lte("remind_time", tomorrow_end)
                .execute()
            )

            done_list = [task["content"] for task in done.data or []]
            pending_list = [task["content"] for task in pending.data or []]
            tomorrow_list = [task["content"] for task in tomorrow_tasks.data or []]
            prompt = REPORT_PROMPT.format(
                done_count=len(done_list),
                done_tasks="、".join(done_list) if done_list else "暂无",
                pending_count=len(pending_list),
                pending_tasks="、".join(pending_list) if pending_list else "暂无",
                tomorrow_reminders="、".join(tomorrow_list) if tomorrow_list else "暂无",
            )
            report_content = _generate_report_text(prompt, len(done_list), len(pending_list))

            supabase.table("daily_reports").upsert(
                {
                    "user_id": user_id,
                    "report_date": today.isoformat(),
                    "content": report_content,
                    "done_count": len(done_list),
                    "pending_count": len(pending_list),
                },
                on_conflict="user_id,report_date",
            ).execute()

            # V2 only stores the report; email delivery is disabled.
        except Exception as exc:
            print(f"Daily report failed for user {user_id}: {exc}")
