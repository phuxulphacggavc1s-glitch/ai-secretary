from fastapi import APIRouter, Depends, Request

from auth import get_current_user
from database import supabase
from models.schemas import ChatBody
from rate_limit import limiter
from services.secretary import build_briefing
from services.secretary_chat import chat, generate_opening, get_recent_messages


router = APIRouter(prefix="/secretary", tags=["secretary"])


async def get_rate_limited_user(request: Request, user=Depends(get_current_user)):
    request.scope["user"] = user
    return user


@router.get("/briefing")
async def get_briefing(user=Depends(get_current_user)):
    return {"success": True, "briefing": build_briefing(user.id)}


@router.get("/messages")
async def list_messages(limit: int = 30, user=Depends(get_current_user)):
    limit = max(1, min(limit, 100))
    return {"success": True, "messages": get_recent_messages(user.id, limit=limit)}


@router.get("/messages/search")
async def search_messages(q: str = "", user=Depends(get_current_user)):
    """全文搜索历史对话——"上周说的那个报价多少来着"直接查。"""
    q = q.strip()
    if not q:
        return {"success": True, "messages": []}
    result = (
        supabase.table("secretary_messages")
        .select("id, role, content, created_at")
        .eq("user_id", user.id)
        .ilike("content", f"%{q}%")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return {"success": True, "messages": result.data or []}


@router.get("/opening")
@limiter.limit("6/minute")
async def opening(request: Request, user=Depends(get_rate_limited_user)):
    return {"success": True, **generate_opening(user.id)}


@router.post("/chat")
@limiter.limit("10/minute")
async def secretary_chat(request: Request, body: ChatBody, user=Depends(get_rate_limited_user)):
    return {"success": True, **chat(user.id, body.message.strip())}
