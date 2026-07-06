from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Request
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import FRONTEND_URL
from database import is_supabase_configured
from rate_limit import limiter
from routers import reports, secretary, tasks, wecom
from services.followup import escalate_s_level, scan_followups
from services.memory import refresh_all_memories
from services.secretary import push_morning_briefing

app = FastAPI(title="AI Secretary API")
app.state.limiter = limiter

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
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "操作太频繁，请稍后再试"},
    )

app.include_router(tasks.router)
app.include_router(reports.router)
app.include_router(secretary.router)
app.include_router(wecom.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if is_supabase_configured():
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(scan_followups, "interval", minutes=1, id="followups", replace_existing=True)
    scheduler.add_job(push_morning_briefing, "cron", hour=8, minute=0, id="morning_briefing", replace_existing=True)
    scheduler.add_job(escalate_s_level, "cron", hour=20, minute=0, id="s_level_escalation", replace_existing=True)
    scheduler.add_job(refresh_all_memories, "cron", day_of_week="sun", hour=21, minute=0, id="memory_refresh", replace_existing=True)
    scheduler.start()
