from __future__ import annotations

from collections import Counter
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from constants import TaskStatus
from database import supabase


DEFAULT_TIMEZONE = "Asia/Shanghai"


def _now() -> datetime:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE))


def _parse_datetime(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _period_range(period: str, now: datetime) -> tuple[datetime, datetime]:
    if period == "week":
        start = datetime.combine(now.date() - timedelta(days=now.weekday()), time.min, tzinfo=now.tzinfo)
        return start, now
    if period == "month":
        start = datetime.combine(now.date().replace(day=1), time.min, tzinfo=now.tzinfo)
        return start, now
    raise ValueError("period must be week or month")


def _is_overdue(task: dict, now: datetime) -> bool:
    if task.get("status") in {TaskStatus.DONE.value, TaskStatus.CANCELLED.value}:
        return False
    remind_at = _parse_datetime(task.get("remind_time"))
    next_follow_at = _parse_datetime(task.get("next_follow_time"))
    if not remind_at or remind_at >= now:
        return False
    return not next_follow_at or next_follow_at <= now


def _task_names(tasks: list[dict], limit: int = 8) -> list[str]:
    return [task.get("content", "未命名任务") for task in tasks[:limit]]


def _fallback_suggestions(stats: dict, risks: list[str], category_stats: list[dict]) -> list[str]:
    suggestions = []
    if stats["overdue"]:
        suggestions.append("先把逾期事项单独清一遍，每天固定一个时间处理到期提醒。")
    if category_stats:
        top_category = category_stats[0]["category"]
        suggestions.append(f"本期任务集中在「{top_category}」，建议把同类事项批量处理，减少来回切换。")
    if risks:
        suggestions.append("对反复拖延的事项，补一句下一步动作和明确跟进时间，避免只记录不推进。")
    while len(suggestions) < 3:
        suggestions.append("保持少量重点任务在前面，优先处理能直接产生结果的事项。")
    return suggestions[:3]


def _fallback_summary(period_label: str, stats: dict, highlights: list[str], risks: list[str]) -> str:
    done_text = "、".join(highlights[:3]) if highlights else "暂无明显完成项"
    risk_text = "、".join(risks[:3]) if risks else "暂无明显风险项"
    return (
        f"{period_label}共记录 {stats['total']} 件事，完成 {stats['done']} 件，"
        f"逾期 {stats['overdue']} 件。主要完成：{done_text}。需要关注：{risk_text}。"
    )


def _ai_summary(period_label: str, stats: dict, highlights: list[str], risks: list[str], category_stats: list[dict]):
    if not DEEPSEEK_API_KEY:
        return None
    prompt = f"""你是一个结果导向的 AI 秘书，请给老板生成{period_label}复盘。

数据：
- 总任务：{stats['total']}
- 已完成：{stats['done']}
- 进行中：{stats['in_progress']}
- 等回复：{stats['waiting_response']}
- 受阻：{stats['blocked']}
- 逾期：{stats['overdue']}
- 完成事项：{'、'.join(highlights) if highlights else '暂无'}
- 风险事项：{'、'.join(risks) if risks else '暂无'}
- 分类分布：{category_stats}

输出 JSON，不要 markdown：
{{
  "summary": "120字以内总结",
  "suggestions": ["改进建议1", "改进建议2", "改进建议3"]
}}
"""
    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=500,
        )
        import json

        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1].removeprefix("json").strip()
        parsed = json.loads(text)
        if isinstance(parsed.get("suggestions"), list) and parsed.get("summary"):
            return {"summary": parsed["summary"], "suggestions": parsed["suggestions"][:3]}
    except Exception as exc:
        print(f"Summary report AI failed: {exc}")
    return None


def build_summary_report(user_id: str, period: str = "week") -> dict:
    now = _now()
    start, end = _period_range(period, now)
    period_label = "周汇报" if period == "week" else "月总结"

    result = (
        supabase.table("tasks")
        .select("id,content,category,status,priority_level,remind_time,next_follow_time,created_at,updated_at")
        .eq("user_id", user_id)
        .gte("created_at", start.isoformat())
        .lte("created_at", end.isoformat())
        .order("created_at", desc=True)
        .execute()
    )
    tasks = result.data or []

    done_tasks = [task for task in tasks if task.get("status") == TaskStatus.DONE.value]
    risks = [
        task
        for task in tasks
        if _is_overdue(task, now) or task.get("status") in {TaskStatus.BLOCKED.value, TaskStatus.WAITING_RESPONSE.value}
    ]
    category_counts = Counter(task.get("category") or "其他" for task in tasks)
    category_stats = [
        {"category": category, "count": count}
        for category, count in category_counts.most_common()
    ]
    stats = {
        "total": len(tasks),
        "done": len(done_tasks),
        "pending": sum(1 for task in tasks if task.get("status") == TaskStatus.PENDING.value),
        "in_progress": sum(1 for task in tasks if task.get("status") == TaskStatus.IN_PROGRESS.value),
        "waiting_response": sum(1 for task in tasks if task.get("status") == TaskStatus.WAITING_RESPONSE.value),
        "blocked": sum(1 for task in tasks if task.get("status") == TaskStatus.BLOCKED.value),
        "overdue": sum(1 for task in tasks if _is_overdue(task, now)),
    }
    highlights = _task_names(done_tasks)
    risk_names = _task_names(risks)
    ai_result = _ai_summary(period_label, stats, highlights, risk_names, category_stats)

    return {
        "period": period,
        "period_label": period_label,
        "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(),
        "stats": stats,
        "category_stats": category_stats,
        "highlights": highlights,
        "risks": risk_names,
        "summary": (ai_result or {}).get("summary") or _fallback_summary(period_label, stats, highlights, risk_names),
        "suggestions": (ai_result or {}).get("suggestions") or _fallback_suggestions(stats, risk_names, category_stats),
    }
