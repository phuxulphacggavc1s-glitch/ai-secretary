from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import get_current_user
from database import supabase
from models.schemas import CheckinBody, TaskConfirm, TaskCreate, TaskUpdate
from rate_limit import limiter
from services.ai_parser import parse_task

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
    data = {
        "user_id": user.id,
        "content": body.content,
        "category": body.category,
        "remind_time": body.remind_time.isoformat() if body.remind_time else None,
        "priority": body.priority,
    }
    result = supabase.table("tasks").insert(data).execute()
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
    return {"success": True, "task": result.data[0]}


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
