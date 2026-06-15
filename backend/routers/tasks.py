from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from constants import EventType, PRIORITY_INT_MAP, PriorityLevel, TaskStatus
from auth import get_current_user
from database import supabase
from models.schemas import CheckinBody, ReplyBody, TaskConfirm, TaskCreate, TaskUpdate
from rate_limit import limiter
from services.ai_parser import parse_task
from services.followup import ensure_next_follow, judge_reply

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def get_rate_limited_user(request: Request, user=Depends(get_current_user)):
    request.scope["user"] = user
    return user


@router.post("/parse")
@limiter.limit("10/minute")
async def parse_only(request: Request, body: TaskCreate, user=Depends(get_rate_limited_user)):
    result = parse_task(body.raw_input)
    return {"success": True, "parsed": result}


@router.post("")
async def create_task(body: TaskConfirm, user=Depends(get_current_user)):
    priority_level = body.priority_level.value if isinstance(body.priority_level, PriorityLevel) else body.priority_level
    priority = body.priority if body.priority else PRIORITY_INT_MAP.get(priority_level or "B", 1)
    data = {
        "user_id": user.id,
        "content": body.content,
        "category": body.category,
        "remind_time": body.remind_time.isoformat() if body.remind_time else None,
        "priority": priority,
        "priority_level": priority_level or "B",
        "goal": body.goal,
        "success_criteria": body.success_criteria,
        "related_person": body.related_person,
        "next_action": body.next_action,
        "next_follow_time": body.next_follow_time.isoformat() if body.next_follow_time else None,
    }
    data.update(ensure_next_follow(data))
    result = supabase.table("tasks").insert(data).execute()
    if result.data:
        supabase.table("task_events").insert(
            {
                "task_id": result.data[0]["id"],
                "user_id": user.id,
                "event_type": EventType.CREATED.value,
                "note": "task created",
            }
        ).execute()
    return {"success": True, "task": result.data[0]}


@router.get("")
async def list_tasks(
    category: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user=Depends(get_current_user),
):
    query = supabase.table("tasks").select("*").eq("user_id", user.id)
    if category and category != "全部":
        query = query.eq("category", category)
    if status:
        query = query.eq("status", status)
    offset = (page - 1) * page_size
    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return {"success": True, "tasks": result.data, "page": page}


@router.patch("/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, user=Depends(get_current_user)):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "priority_level" in updates and updates["priority_level"] is not None:
        updates["priority_level"] = updates["priority_level"].value if isinstance(updates["priority_level"], PriorityLevel) else updates["priority_level"]
        updates["priority"] = PRIORITY_INT_MAP.get(updates["priority_level"], 1)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("tasks")
        .update(updates)
        .eq("id", task_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    if "status" in updates:
        supabase.table("task_events").insert(
            {
                "task_id": task_id,
                "user_id": user.id,
                "event_type": EventType.STATUS_CHANGE.value,
                "from_status": None,
                "to_status": updates["status"],
                "note": "status updated",
            }
        ).execute()
    ensure_updates = ensure_next_follow(result.data[0])
    if ensure_updates:
        result = (
            supabase.table("tasks")
            .update(ensure_updates)
            .eq("id", task_id)
            .eq("user_id", user.id)
            .execute()
        )
    return {"success": True, "task": result.data[0]}


@router.delete("/{task_id}")
async def delete_task(task_id: str, user=Depends(get_current_user)):
    result = (
        supabase.table("tasks")
        .delete()
        .eq("id", task_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}


@router.post("/{task_id}/checkin")
async def checkin_task(task_id: str, body: CheckinBody, user=Depends(get_current_user)):
    updates = {
        "last_checkin_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.progress_note is not None:
        updates["progress_note"] = body.progress_note
    if body.status is not None:
        updates["status"] = body.status
    result = (
        supabase.table("tasks")
        .update(updates)
        .eq("id", task_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.status is not None:
        supabase.table("task_events").insert(
            {
                "task_id": task_id,
                "user_id": user.id,
                "event_type": EventType.STATUS_CHANGE.value,
                "from_status": None,
                "to_status": body.status,
                "note": "checkin status updated",
            }
        ).execute()
    ensure_updates = ensure_next_follow(result.data[0])
    if ensure_updates:
        result = (
            supabase.table("tasks")
            .update(ensure_updates)
            .eq("id", task_id)
            .eq("user_id", user.id)
            .execute()
        )
    return {"success": True, "task": result.data[0]}


@router.post("/{task_id}/reply")
async def reply_task(task_id: str, body: ReplyBody, user=Depends(get_current_user)):
    task_result = (
        supabase.table("tasks")
        .select("*")
        .eq("id", task_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not task_result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    task = task_result.data[0]
    judged = judge_reply(task, body.reply_text)
    updates = {
        "status": judged["new_status"],
        "progress_note": judged.get("progress_note"),
        "next_action": judged.get("next_action"),
        "next_follow_time": judged.get("next_follow_time"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = (
        supabase.table("tasks")
        .update(updates)
        .eq("id", task_id)
        .eq("user_id", user.id)
        .execute()
    )
    supabase.table("task_events").insert(
        {
            "task_id": task_id,
            "user_id": user.id,
            "event_type": EventType.AI_JUDGE.value,
            "from_status": task.get("status"),
            "to_status": judged["new_status"],
            "ai_raw": judged.get("ai_raw"),
            "note": body.reply_text,
        }
    ).execute()
    return {"success": True, "task": result.data[0], "judged": judged}


@router.post("/{task_id}/snooze")
async def snooze_task(task_id: str, user=Depends(get_current_user)):
    """把逾期提醒推迟到明天早上 8 点（当天不再烦你）"""
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    tomorrow_8am = datetime.combine(
        now.date() + timedelta(days=1),
        time(8, 0),
        tzinfo=tz,
    )
    updates = {
        "snooze_until": tomorrow_8am.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = (
        supabase.table("tasks")
        .update(updates)
        .eq("id", task_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": result.data[0]}
