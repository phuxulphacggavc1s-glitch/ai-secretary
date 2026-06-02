from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import FRONTEND_URL
from database import is_supabase_configured
from routers import reports, tasks
from services.daily_report import generate_daily_reports
from services.reminder import check_and_send_reminders

app = FastAPI(title="AI Secretary API")

allowed_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]
if FRONTEND_URL and FRONTEND_URL not in allowed_origins:
    allowed_origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(reports.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if is_supabase_configured():
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(check_and_send_reminders, "interval", minutes=1, id="reminders", replace_existing=True)
    scheduler.add_job(generate_daily_reports, "cron", hour=21, minute=0, id="daily_reports", replace_existing=True)
    scheduler.start()
