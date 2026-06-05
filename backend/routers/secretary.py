from fastapi import APIRouter, Depends

from auth import get_current_user
from services.secretary import build_briefing


router = APIRouter(prefix="/secretary", tags=["secretary"])


@router.get("/briefing")
async def get_briefing(user=Depends(get_current_user)):
    return {"success": True, "briefing": build_briefing(user.id)}
