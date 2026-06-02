# AI Secretary MVP — Codex Agent Instructions

> This file is the single source of truth for building the AI Secretary MVP.
> Read every section before writing any code. Follow the task order strictly.

---

## Project Overview

Build a full-stack AI life secretary web app where users type a natural language sentence (e.g. "remind me to quote the client tomorrow afternoon") and the system automatically:
1. Parses the text via AI (extracts task content, category, reminder time)
2. Saves the task to a database
3. Shows tasks in a categorized list
4. Sends email reminders at the right time
5. Generates a daily AI summary every evening

**Target language**: Chinese users. All UI labels, messages, and AI prompts must be in Chinese.

---

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Frontend | React + Vite + TailwindCSS | Fast to build, mobile-friendly |
| Backend | Python FastAPI | Async support, simple |
| Database + Auth | Supabase | Built-in auth, free tier |
| AI | DeepSeek API (openai-compatible) | Cheap, great Chinese NLU |
| Email | Resend API | Simple SDK, generous free tier |
| Scheduler | APScheduler (in FastAPI) | No extra infra needed for MVP |
| Deployment | Frontend → Vercel / Backend → Railway | Free tier sufficient for MVP |

---

## Environment Variables

Create a `.env` file in `/backend`. Never commit this file.

```env
# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key

# DeepSeek AI
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com

# Resend Email
RESEND_API_KEY=your-resend-api-key
FROM_EMAIL=secretary@yourdomain.com

# App
SECRET_KEY=your-jwt-secret-32chars
FRONTEND_URL=http://localhost:5173
```

Create a `.env.local` file in `/frontend`:

```env
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_BASE_URL=http://localhost:8000
```

---

## Project Structure to Create

```
ai-secretary/
├── AGENTS.md                    # This file
├── README.md
│
├── backend/
│   ├── .env                     # Never commit
│   ├── requirements.txt
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Load env vars
│   ├── database.py              # Supabase client
│   ├── auth.py                  # JWT verification middleware
│   │
│   ├── routers/
│   │   ├── tasks.py             # Task CRUD endpoints
│   │   └── reports.py           # Daily report endpoints
│   │
│   ├── services/
│   │   ├── ai_parser.py         # DeepSeek task parsing
│   │   ├── email_service.py     # Resend email sending
│   │   ├── reminder.py          # Reminder scheduler
│   │   └── daily_report.py     # Daily summary generator
│   │
│   └── models/
│       └── schemas.py           # Pydantic models
│
└── frontend/
    ├── .env.local               # Never commit
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── supabase.js          # Supabase client init
        ├── api.js               # Axios instance + API calls
        │
        ├── pages/
        │   ├── Login.jsx        # Email/password login + signup
        │   ├── Home.jsx         # Input box + recent tasks
        │   └── Tasks.jsx        # Full task list with tabs
        │
        ├── components/
        │   ├── TaskInput.jsx    # Text input + send button
        │   ├── TaskCard.jsx     # Single task display
        │   ├── TaskList.jsx     # Filtered task list
        │   ├── ParsePreview.jsx # AI parse result confirm dialog
        │   ├── TimePickerModal.jsx  # Manual time selection
        │   └── DailyReport.jsx  # Daily summary display
        │
        └── hooks/
            ├── useAuth.js       # Auth state management
            └── useTasks.js      # Task fetch + mutations
```

---

## Database Setup (Run in Supabase SQL Editor)

Run this SQL exactly as written:

```sql
-- Enable UUID extension
create extension if not exists "pgcrypto";

-- Users table (extends Supabase auth.users)
create table public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text unique,
  nickname text,
  timezone text default 'Asia/Shanghai',
  created_at timestamp with time zone default now()
);

-- Auto-create user profile on signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.users (id, email)
  values (new.id, new.email);
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- Tasks table
create table public.tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade not null,
  content text not null,
  category text default '其他',
  remind_time timestamp with time zone,
  status text default 'pending' check (status in ('pending', 'done')),
  reminded boolean default false,
  priority int default 1 check (priority in (1, 2, 3)),
  ai_summary text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

create index idx_tasks_user_id on public.tasks(user_id);
create index idx_tasks_remind on public.tasks(remind_time, status, reminded)
  where remind_time is not null and status = 'pending' and reminded = false;

-- Daily reports table
create table public.daily_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete cascade not null,
  report_date date not null,
  content text,
  done_count int default 0,
  pending_count int default 0,
  created_at timestamp with time zone default now(),
  unique(user_id, report_date)
);

-- Row Level Security
alter table public.tasks enable row level security;
alter table public.daily_reports enable row level security;
alter table public.users enable row level security;

create policy "Users can only see own tasks"
  on public.tasks for all using (auth.uid() = user_id);

create policy "Users can only see own reports"
  on public.daily_reports for all using (auth.uid() = user_id);

create policy "Users can see own profile"
  on public.users for all using (auth.uid() = id);
```

---

## Backend Implementation

### requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-dotenv==1.0.1
supabase==2.4.6
openai==1.30.1
resend==2.0.0
apscheduler==3.10.4
pydantic==2.7.1
python-jose[cryptography]==3.3.0
httpx==0.27.0
```

---

### config.py

```python
from dotenv import load_dotenv
import os

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL")
SECRET_KEY = os.getenv("SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
```

---

### database.py

```python
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
```

---

### models/schemas.py

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TaskCreate(BaseModel):
    raw_input: str

class TaskConfirm(BaseModel):
    content: str
    category: str
    remind_time: Optional[datetime] = None
    priority: int = 1

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    remind_time: Optional[datetime] = None

class ParsedTask(BaseModel):
    content: str
    category: str
    remind_time: Optional[str] = None
    is_time_clear: bool
    original_time_text: Optional[str] = None
```

---

### services/ai_parser.py

Implement the `parse_task(raw_input: str, user_timezone: str = "Asia/Shanghai") -> dict` function.

Use the OpenAI-compatible client pointed at DeepSeek:

```python
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from datetime import datetime
import pytz, json

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

PARSE_SYSTEM_PROMPT = """你是一个智能秘书助手，专门帮用户解析待办事项。

【任务】
从用户输入中提取：
1. 任务内容（去掉时间词和"提醒"等词，保留核心事项）
2. 分类（从以下选择：工作 / 生活 / 灵感 / 财务 / 学习 / 其他）
3. 提醒时间（转换为 ISO 8601 格式，时区：Asia/Shanghai）
4. 时间是否明确（is_time_clear）

【分类规则】
- 工作：客户、报价、发货、直播、抖音、淘宝、小红书、店铺、供应商、合同、会议
- 财务：房租、账单、还款、工资、打款、收款、税务
- 生活：买菜、看病、取快递、家里、约饭、健身
- 灵感：想法、方案、优化思路、创意
- 学习：看书、学习、课程、培训

【时间解析规则】
- "明天下午" → 明天 15:00
- "明天上午" → 明天 09:00
- "后天" → 后天 09:00
- "月底" → 当月最后一天 09:00
- "周五" / "星期五" → 下个周五 09:00
- "下周" → 下周一 09:00
- 只说"提醒我"但没有时间 → is_time_clear = false
- "过几天" / "最近" / "有空" → is_time_clear = false
- 没有提到时间 → is_time_clear = false

【返回格式】只返回合法 JSON，不要加任何解释或 markdown 代码块
{
  "content": "任务内容",
  "category": "分类",
  "remind_time": "2026-06-03T15:00:00+08:00",
  "is_time_clear": true,
  "original_time_text": "明天下午"
}

如果 is_time_clear 为 false，remind_time 设为 null。
"""

def parse_task(raw_input: str) -> dict:
    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M %A")
    
    user_prompt = f"【当前时间】{now}\n\n【用户输入】{raw_input}"
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=300
        )
        text = response.choices[0].message.content.strip()
        # Strip markdown code blocks if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        # Fallback: return unstructured task
        return {
            "content": raw_input,
            "category": "其他",
            "remind_time": None,
            "is_time_clear": False,
            "original_time_text": None,
            "parse_error": str(e)
        }
```

---

### services/email_service.py

```python
import resend
from config import RESEND_API_KEY, FROM_EMAIL

resend.api_key = RESEND_API_KEY

def send_reminder_email(to_email: str, task_content: str, remind_time: str):
    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to_email,
        "subject": f"【AI秘书提醒】{task_content}",
        "html": f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2>📌 你有一个待办提醒</h2>
            <p style="font-size: 18px; color: #333;"><strong>{task_content}</strong></p>
            <p style="color: #666;">提醒时间：{remind_time}</p>
            <hr/>
            <p style="color: #999; font-size: 12px;">来自 AI 秘书</p>
        </div>
        """
    })

def send_daily_report_email(to_email: str, report_content: str, date: str):
    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to_email,
        "subject": f"【AI秘书日报】{date} 每日总结",
        "html": f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2>📋 今日总结 · {date}</h2>
            <p style="font-size: 16px; line-height: 1.8; color: #333;">{report_content}</p>
            <hr/>
            <p style="color: #999; font-size: 12px;">来自 AI 秘书</p>
        </div>
        """
    })
```

---

### services/reminder.py

Implement `check_and_send_reminders()` — scans tasks due for reminder and sends emails.

```python
from database import supabase
from services.email_service import send_reminder_email
from datetime import datetime, timezone

def check_and_send_reminders():
    now = datetime.now(timezone.utc).isoformat()
    
    # Get all tasks that need reminding
    result = supabase.table("tasks") \
        .select("*, users(email)") \
        .lte("remind_time", now) \
        .eq("status", "pending") \
        .eq("reminded", False) \
        .execute()
    
    for task in result.data:
        try:
            user_email = task["users"]["email"]
            remind_time_str = task["remind_time"]
            
            send_reminder_email(
                to_email=user_email,
                task_content=task["content"],
                remind_time=remind_time_str
            )
            
            # Mark as reminded
            supabase.table("tasks") \
                .update({"reminded": True}) \
                .eq("id", task["id"]) \
                .execute()
                
        except Exception as e:
            print(f"Reminder failed for task {task['id']}: {e}")
```

---

### services/daily_report.py

```python
from database import supabase
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from services.email_service import send_daily_report_email
from datetime import datetime, date, timedelta
import pytz

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

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

def generate_daily_reports():
    tz = pytz.timezone("Asia/Shanghai")
    today = date.today()
    tomorrow = today + timedelta(days=1)
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=tz).isoformat()
    today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=tz).isoformat()
    tomorrow_end = datetime.combine(tomorrow, datetime.max.time()).replace(tzinfo=tz).isoformat()
    
    # Get all users
    users = supabase.table("users").select("id, email").execute()
    
    for user in users.data:
        try:
            user_id = user["id"]
            user_email = user["email"]
            
            done = supabase.table("tasks").select("content") \
                .eq("user_id", user_id).eq("status", "done") \
                .gte("updated_at", today_start).lte("updated_at", today_end) \
                .execute()
            
            pending = supabase.table("tasks").select("content") \
                .eq("user_id", user_id).eq("status", "pending") \
                .execute()
            
            tomorrow_tasks = supabase.table("tasks").select("content, remind_time") \
                .eq("user_id", user_id).eq("status", "pending") \
                .gte("remind_time", today_end).lte("remind_time", tomorrow_end) \
                .execute()
            
            done_list = [t["content"] for t in done.data]
            pending_list = [t["content"] for t in pending.data]
            tomorrow_list = [t["content"] for t in tomorrow_tasks.data]
            
            prompt = REPORT_PROMPT.format(
                done_count=len(done_list),
                done_tasks="、".join(done_list) if done_list else "暂无",
                pending_count=len(pending_list),
                pending_tasks="、".join(pending_list) if pending_list else "暂无",
                tomorrow_reminders="、".join(tomorrow_list) if tomorrow_list else "暂无"
            )
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200
            )
            report_content = response.choices[0].message.content.strip()
            
            # Save to DB
            supabase.table("daily_reports").upsert({
                "user_id": user_id,
                "report_date": today.isoformat(),
                "content": report_content,
                "done_count": len(done_list),
                "pending_count": len(pending_list)
            }, on_conflict="user_id,report_date").execute()
            
            # Send email
            send_daily_report_email(user_email, report_content, today.isoformat())
            
        except Exception as e:
            print(f"Daily report failed for user {user_id}: {e}")
```

---

### auth.py

```python
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import supabase

bearer = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    token = credentials.credentials
    try:
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
```

---

### routers/tasks.py

Implement all task endpoints. Each endpoint must verify auth using `get_current_user`.

```python
from fastapi import APIRouter, Depends, HTTPException
from database import supabase
from auth import get_current_user
from models.schemas import TaskCreate, TaskConfirm, TaskUpdate
from services.ai_parser import parse_task
from datetime import datetime, timezone

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/parse")
async def parse_only(body: TaskCreate, user=Depends(get_current_user)):
    """Step 1: Parse input without saving. Returns parsed result for user to confirm."""
    result = parse_task(body.raw_input)
    return {"success": True, "parsed": result}

@router.post("")
async def create_task(body: TaskConfirm, user=Depends(get_current_user)):
    """Step 2: Save confirmed task to DB."""
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
    category: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
    user=Depends(get_current_user)
):
    query = supabase.table("tasks").select("*").eq("user_id", user.id)
    if category and category != "全部":
        query = query.eq("category", category)
    if status:
        query = query.eq("status", status)
    query = query.order("created_at", desc=True)
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)
    result = query.execute()
    return {"success": True, "tasks": result.data, "page": page}

@router.patch("/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, user=Depends(get_current_user)):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = supabase.table("tasks").update(updates) \
        .eq("id", task_id).eq("user_id", user.id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": result.data[0]}

@router.delete("/{task_id}")
async def delete_task(task_id: str, user=Depends(get_current_user)):
    result = supabase.table("tasks").delete() \
        .eq("id", task_id).eq("user_id", user.id).execute()
    return {"success": True}
```

---

### routers/reports.py

```python
from fastapi import APIRouter, Depends
from database import supabase
from auth import get_current_user
from datetime import date

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/daily")
async def get_daily_report(report_date: str = None, user=Depends(get_current_user)):
    target_date = report_date or date.today().isoformat()
    result = supabase.table("daily_reports").select("*") \
        .eq("user_id", user.id).eq("report_date", target_date).execute()
    if result.data:
        return {"success": True, "report": result.data[0]}
    return {"success": True, "report": None}
```

---

### main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from routers import tasks, reports
from services.reminder import check_and_send_reminders
from services.daily_report import generate_daily_reports
from config import FRONTEND_URL

app = FastAPI(title="AI Secretary API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(reports.router)

@app.get("/health")
def health():
    return {"status": "ok"}

# Background jobs
scheduler = BackgroundScheduler()
scheduler.add_job(check_and_send_reminders, "interval", minutes=1)
scheduler.add_job(generate_daily_reports, "cron", hour=21, minute=0, timezone="Asia/Shanghai")
scheduler.start()
```

---

## Frontend Implementation

### package.json dependencies

```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.1",
    "@supabase/supabase-js": "^2.43.4",
    "axios": "^1.7.2",
    "dayjs": "^1.11.11",
    "lucide-react": "^0.383.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "tailwindcss": "^3.4.4",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "vite": "^5.2.13"
  }
}
```

---

### src/supabase.js

```js
import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
)
```

---

### src/api.js

```js
import axios from 'axios'
import { supabase } from './supabase'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL
})

api.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession()
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`
  }
  return config
})

export const parseTask = (rawInput) =>
  api.post('/tasks/parse', { raw_input: rawInput }).then(r => r.data)

export const createTask = (taskData) =>
  api.post('/tasks', taskData).then(r => r.data)

export const listTasks = (params) =>
  api.get('/tasks', { params }).then(r => r.data)

export const updateTask = (id, data) =>
  api.patch(`/tasks/${id}`, data).then(r => r.data)

export const deleteTask = (id) =>
  api.delete(`/tasks/${id}`).then(r => r.data)

export const getDailyReport = (date) =>
  api.get('/reports/daily', { params: { report_date: date } }).then(r => r.data)

export default api
```

---

### Page: Login.jsx

Build a clean login/signup page with:
- Tab toggle: "登录" / "注册"
- Email input + Password input
- Submit button
- On login: call `supabase.auth.signInWithPassword()`
- On signup: call `supabase.auth.signUp()`
- After success: navigate to `/`
- Show error message if auth fails

---

### Page: Home.jsx

The main page. Layout:
```
[Header: "AI 秘书" + user avatar + logout]
[TaskInput component — large text area + "发送" button]
[Recent tasks section — last 5 tasks as TaskCard]
[Link to full task list]
```

Logic:
1. User types in TaskInput and clicks send
2. Call `parseTask(rawInput)` → show `ParsePreview` dialog with the parsed result
3. If `is_time_clear = false` → show `TimePickerModal` for user to set time manually
4. User confirms → call `createTask()` → add to list
5. Show success toast

---

### Page: Tasks.jsx

Full task list with category filter tabs:
- Tabs: 全部 / 工作 / 生活 / 灵感 / 财务 / 学习 / 已完成
- Each task rendered as `TaskCard`
- Search bar at top (filter client-side)
- On tab change, fetch tasks with `category` filter

---

### Component: TaskCard.jsx

Display a single task:
```
[Category badge] [Priority dot]
Task content text (large)
Reminder time (if any) — formatted as "6月3日 下午3:00"
[✓ 完成] [✕ 删除] buttons
```

On complete: call `updateTask(id, { status: 'done' })`
On delete: confirm then call `deleteTask(id)`

---

### Component: ParsePreview.jsx

A modal/drawer showing AI parse result before saving:
```
AI 已解析：
内容：[editable input]
分类：[dropdown selector]
提醒时间：[show parsed time or "未识别，点击设置"]
[确认保存] [取消]
```

All fields should be editable in case AI made mistakes.

---

### Component: TimePickerModal.jsx

Simple date + time picker modal:
- Date picker (native `<input type="date">` is fine for MVP)
- Time picker (native `<input type="time">`)
- 快捷选项: 明天上午9点 / 明天下午3点 / 后天上午9点 / 月底
- [确认] [跳过] buttons

---

### Component: DailyReport.jsx

Display today's AI summary:
- Show `report.content` as text
- Show `done_count` and `pending_count` as stats
- If no report yet: show "今日总结将在晚上9点生成"

---

### hooks/useAuth.js

```js
import { useState, useEffect } from 'react'
import { supabase } from '../supabase'

export function useAuth() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null)
      setLoading(false)
    })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
    })
    return () => subscription.unsubscribe()
  }, [])

  const signOut = () => supabase.auth.signOut()
  return { user, loading, signOut }
}
```

---

### App.jsx routing

```jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import Login from './pages/Login'
import Home from './pages/Home'
import Tasks from './pages/Tasks'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="flex h-screen items-center justify-center">加载中...</div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<ProtectedRoute><Home /></ProtectedRoute>} />
        <Route path="/tasks" element={<ProtectedRoute><Tasks /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}
```

---

## UI Design Rules

- Color scheme: White background, `#4F46E5` (indigo) as primary color
- Font: System default, readable on mobile
- Mobile-first: all layouts must work on 375px width screen
- Category badge colors:
  - 工作 → blue
  - 财务 → green
  - 生活 → orange
  - 灵感 → purple
  - 学习 → teal
  - 其他 → gray
- All buttons must have loading state (disable + spinner while API call is in flight)
- All errors must show a toast or inline error message — never fail silently

---

## Error Handling Rules

Every API call must be wrapped with try/catch. Handle these cases:

| Scenario | UI Behavior |
|----------|-------------|
| AI parse fails | Show "解析失败，请手动填写" + show manual input form |
| is_time_clear = false | Auto-open TimePickerModal |
| Network error | Toast: "网络错误，请重试" |
| 401 Unauthorized | Redirect to /login |
| Task create fails | Toast: "创建失败，请重试" |
| Task list empty | Show empty state illustration with "还没有待办，输入一句话开始吧" |

---

## Build & Run Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## Execution Order for Codex

Implement in exactly this order. Complete and test each step before moving to the next.

1. Create project directory structure
2. Set up backend: `config.py`, `database.py`, `requirements.txt`
3. Implement `services/ai_parser.py` — test with sample inputs before continuing
4. Implement `models/schemas.py`
5. Implement `auth.py`
6. Implement `routers/tasks.py`
7. Implement `routers/reports.py`
8. Implement `services/email_service.py`
9. Implement `services/reminder.py`
10. Implement `services/daily_report.py`
11. Implement `main.py` (wire everything together, start scheduler)
12. Test all backend endpoints with curl or httpie
13. Set up frontend: Vite + React + Tailwind
14. Implement `supabase.js`, `api.js`
15. Implement `hooks/useAuth.js`
16. Implement `Login.jsx`
17. Implement `TaskCard.jsx`, `ParsePreview.jsx`, `TimePickerModal.jsx`
18. Implement `Home.jsx`
19. Implement `Tasks.jsx`
20. Implement `DailyReport.jsx`
21. Wire up `App.jsx` routing
22. End-to-end test: login → type task → confirm parse → view list → mark done

---

## Definition of Done

The MVP is complete when:
- [ ] User can sign up and log in with email/password
- [ ] User types "明天下午提醒我给客户报价" and sees parsed result within 3 seconds
- [ ] User can confirm, edit, and save the parsed task
- [ ] Task appears in the list immediately after saving
- [ ] Email reminder is sent within 2 minutes of the reminder time
- [ ] Daily report is generated at 21:00 and sent to user's email
- [ ] All pages work on mobile (375px width)
- [ ] No crashes on empty states or network errors
