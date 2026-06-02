# AI Secretary — 部署到云端指令（Codex 执行）

> 目标：把本地运行的 AI 秘书部署到 Vercel（前端）+ Railway（后端），让手机可以访问。
> 前提：本地代码已跑通，.env 文件已配置好真实密钥。

---

## 执行前检查

在开始之前，确认以下文件存在且正确：
- `backend/.env` — 包含真实的 SUPABASE_URL、SUPABASE_SERVICE_KEY、DEEPSEEK_API_KEY 等
- `frontend/.env.local` — 包含真实的 VITE_SUPABASE_URL、VITE_SUPABASE_ANON_KEY
- `.gitignore` — 必须包含 `.env` 和 `.env.local`（绝对不能把密钥推到 GitHub）

---

## Task 1：补全部署所需配置文件

### 1.1 创建 `backend/Procfile`（Railway 用来知道怎么启动后端）

创建文件 `backend/Procfile`，内容：

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

### 1.2 创建 `backend/railway.toml`（告诉 Railway 根目录和启动命令）

创建文件 `backend/railway.toml`，内容：

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
```

### 1.3 创建 `frontend/vercel.json`（告诉 Vercel 这是 SPA，所有路由都指向 index.html）

创建文件 `frontend/vercel.json`，内容：

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/" }
  ]
}
```

### 1.4 确认 `backend/requirements.txt` 包含所有依赖

确认文件存在且包含以下包（如果缺少就补上）：

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-dotenv==1.0.1
supabase==2.4.6
openai==1.30.1
resend==2.0.0
apscheduler==3.10.4
pydantic==2.12.4
python-jose[cryptography]==3.3.0
httpx==0.27.0
```

### 1.5 更新 `backend/main.py` 的 CORS 配置

修改 `backend/main.py`，让 CORS 支持从环境变量读取多个允许域名：

```python
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from config import FRONTEND_URL
from database import is_supabase_configured
from routers import reports, tasks
from services.daily_report import generate_daily_reports
from services.reminder import check_and_send_reminders

app = FastAPI(title="AI Secretary API")

# 允许的前端域名：本地开发 + 生产环境
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
```

---

## Task 2：初始化 Git 仓库并推送到 GitHub

> ⚠️ 重要：执行前确认 .gitignore 正确，绝不能把 .env 文件推上去

```bash
cd D:\项目\AI_Secretary

# 初始化 Git
git init
git add .

# 验证 .env 文件没有被包含（应该看不到 .env 相关文件）
git status | grep -i "\.env" || echo "OK - no .env files staged"

# 提交
git commit -m "feat: AI Secretary MVP - ready for deployment"
```

然后在 GitHub 创建新仓库（名称建议：`ai-secretary`），复制仓库地址后运行：

```bash
git remote add origin https://github.com/用户名/ai-secretary.git
git branch -M main
git push -u origin main
```

---

## Task 3：生成部署环境变量清单文件

创建文件 `DEPLOY_ENV.txt`（不要提交到 git，仅供本地参考），列出部署时需要在 Railway 和 Vercel 填写的变量名：

```
=== Railway（后端）需要填写的变量 ===
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
RESEND_API_KEY=
FROM_EMAIL=onboarding@resend.dev
SECRET_KEY=
FRONTEND_URL=（等 Vercel 部署完后填 Vercel 给的域名）

=== Vercel（前端）需要填写的变量 ===
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_BASE_URL=（填 Railway 给的后端域名，格式：https://xxx.up.railway.app）
```

同时把 `DEPLOY_ENV.txt` 加入 `.gitignore`：

```bash
echo "DEPLOY_ENV.txt" >> .gitignore
```

---

## Task 4：验证推送结果

```bash
# 确认推送成功
git log --oneline -3

# 确认敏感文件没有被推上去
git show HEAD --name-only | grep -E "\.env$|\.env\.local$" && echo "⚠️ 警告：env文件被推上去了！" || echo "✅ 安全：没有env文件"
```

---

## Task 5：输出部署操作手册

在控制台打印以下提示，告知用户接下来的手动操作步骤：

```
====================================
✅ 代码已推送到 GitHub，接下来手动操作：

【第一步：Railway 部署后端】
1. 打开 https://railway.app，用 GitHub 登录
2. New Project → Deploy from GitHub repo → 选 ai-secretary
3. Settings → Root Directory → 填 backend
4. Variables → 把 DEPLOY_ENV.txt 里 Railway 那段的变量逐条填入（值从本地 backend/.env 复制）
5. 等待部署完成，复制 Railway 给的域名（如 https://xxx.up.railway.app）

【第二步：Vercel 部署前端】
1. 打开 https://vercel.com，用 GitHub 登录
2. Add New Project → 选 ai-secretary
3. Root Directory → 填 frontend
4. Environment Variables → 把 DEPLOY_ENV.txt 里 Vercel 那段填入
   VITE_API_BASE_URL 填第一步 Railway 给的域名
5. 等待部署完成，复制 Vercel 给的域名（如 https://xxx.vercel.app）

【第三步：回填前端地址到 Railway】
1. 回到 Railway → Variables
2. 把 FRONTEND_URL 填成 Vercel 给的域名
3. Railway 自动重启后端

【完成】用手机浏览器打开 Vercel 域名，即可使用 AI 秘书
====================================
```

---

## 完成标准

- [ ] `backend/Procfile` 已创建
- [ ] `backend/railway.toml` 已创建
- [ ] `frontend/vercel.json` 已创建
- [ ] 代码已推送到 GitHub，无 .env 文件泄露
- [ ] `DEPLOY_ENV.txt` 已生成（仅本地，不在 git 中）
- [ ] 控制台输出了部署操作手册
