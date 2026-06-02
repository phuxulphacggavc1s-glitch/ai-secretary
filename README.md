
# AI Secretary MVP

面向中文用户的 AI 生活/工作秘书 Web MVP。用户输入一句自然语言，系统通过 DeepSeek 解析任务内容、分类和提醒时间，确认后保存到 Supabase，并通过 FastAPI 定时发送邮件提醒和每日总结。

## 技术栈

- 前端：React + Vite + TailwindCSS
- 后端：FastAPI + APScheduler
- 数据库/认证：Supabase
- AI：DeepSeek API（OpenAI-compatible）
- 邮件：Resend

## 目录

```text
backend/       FastAPI API、AI 解析、提醒和日报服务
frontend/      React Web 应用
supabase/      数据库初始化 SQL
docs/          设计和实现计划
```

## Supabase 初始化

在 Supabase SQL Editor 执行：

```text
supabase/schema.sql
```

然后在 Supabase Authentication 中启用 Email 登录。

## 环境变量

复制后填写真实配置：

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.local.example frontend/.env.local
```

## 启动后端

```powershell
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

健康检查：

```text
http://localhost:8000/health
```

## 启动前端

```powershell
cd frontend
npm install
npm run dev
```

访问：

```text
http://localhost:5173
```

## MVP 流程

1. 注册/登录邮箱账号。
2. 在首页输入“明天下午提醒我给客户报价”。
3. 查看 AI 解析结果，必要时编辑内容、分类和提醒时间。
4. 确认保存，任务进入最近记录和待办列表。
5. 到提醒时间后端定时任务发送邮件。
6. 每天 21:00 生成并发送日报。
