from datetime import date

from fastapi import APIRouter, Depends

from auth import get_current_user
from database import supabase
from services.summary_report import build_summary_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily")
async def get_daily_report(report_date: str | None = None, user=Depends(get_current_user)):
    target_date = report_date or date.today().isoformat()
    result = (
        supabase.table("daily_reports")
        .select("*")
        .eq("user_id", user.id)
        .eq("report_date", target_date)
        .execute()
    )
    if result.data:
        return {"success": True, "report": result.data[0]}
    return {"success": True, "report": None}


@router.get("/summary")
async def get_summary_report(period: str = "week", user=Depends(get_current_user)):
    return {"success": True, "report": build_summary_report(user.id, period)}
