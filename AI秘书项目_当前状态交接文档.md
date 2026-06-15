# AI 秘书项目 · 当前状态交接文档

## 我是谁
我是一名电商创业者，自己既是老板也是店铺运营，经营渠道包括抖音电商、淘宝、小红书。强项是抓机会和执行落地，数据运营和精细化运营比较弱。

**跟我交流时请：**
- 涉及技术内容，用大白话讲，少用行话，必要时一步步拆解
- 给建议时偏向可直接执行的动作，而不是停留在理论

---

## 项目概述：AI 秘书

一个个人任务管理 Web 应用，主要功能：
- 用一句话自然语言创建任务（AI 解析时间、分类、优先级）
- 秘书简报（每日待办、逾期任务汇总）
- 任务打卡/进度更新
- 企业微信群定时提醒 + 到点@提醒

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React + Vite |
| 后端 | FastAPI + Python |
| 数据库 | Supabase（PostgreSQL + Auth） |
| AI | DeepSeek API |
| 服务器 | 阿里云 ECS（Ubuntu 26.04，北京华北2） |
| Web服务 | Nginx（反向代理） |
| 进程管理 | systemd |

---

## 服务器信息

- **公网 IP**：‹服务器IP已隐藏›
- **域名**：mede-in-ai.com（已备案：冀ICP备2026020767号）
- **SSH 登录**：`ssh root@‹服务器IP已隐藏›`（登录凭据请私下保管，勿写入会传阅的文档）
- **Workbench**：阿里云控制台 → ECS实例 → 远程连接 → Workbench（可粘贴命令）

---

## 部署结构

```
/var/www/ai-secretary/
├── backend/
│   ├── main.py
│   ├── .env                  ← 环境变量（Supabase、DeepSeek Key等）
│   ├── venv/                 ← Python虚拟环境
│   ├── routers/
│   │   ├── tasks.py
│   │   └── secretary.py
│   └── services/
│       └── secretary.py
├── frontend/
│   ├── .env.production       ← VITE_API_BASE_URL=https://mede-in-ai.com/api
│   └── dist/                 ← 打包后的静态文件（Nginx从这里提供服务）
├── notify.py                 ← 每天早上8点发企业微信晨报
└── remind.py                 ← 每分钟检查任务提醒，到点@用户
```

---

## 已完成的所有工作

### 功能开发
- [x] 完成了 8 个截断的源文件（secretary 简报功能）
- [x] `frontend/src/api.js` — 补全 deleteTask、getBriefing、snoozeTask
- [x] `frontend/src/hooks/useTasks.js` — 补全 removeTask
- [x] `frontend/src/components/TaskList.jsx` — 修复截断的 JSX
- [x] `frontend/src/components/TaskCard.jsx` — 完成操作按钮
- [x] `frontend/src/pages/Home.jsx` — 修复 ParsePreview 弹窗不显示的 bug
- [x] `frontend/src/pages/Tasks.jsx` — 修复分类筛选
- [x] `backend/models/schemas.py` — 添加 CheckinBody
- [x] `backend/routers/tasks.py` — 完成 checkin、delete、snooze 接口
- [x] `backend/routers/secretary.py` — 新建秘书简报路由
- [x] `backend/services/secretary.py` — 新建简报构建逻辑

### 服务器部署
- [x] Nginx 配置（HTTP → HTTPS 重定向，/api/ 反向代理到 8000 端口）
- [x] systemd 服务（ai-secretary.service，开机自启）
- [x] SSL 证书（Let's Encrypt，certbot 自动续期）
- [x] 阿里云安全组开放 80/443 端口
- [x] DNS 解析：mede-in-ai.com → ‹服务器IP已隐藏›

### 用户管理
- [x] Supabase URL Configuration 已改为 https://mede-in-ai.com
- [x] Redirect URLs 已添加 https://mede-in-ai.com/**
- [x] 现有用户邮箱验证流程正常

### 企业微信提醒
- [x] 每天早上8点晨报（cron + notify.py）
- [x] 任务到点@提醒（每分钟 cron + remind.py）
- [x] 企业微信群：AI秘书推送（内部群）
- [x] Webhook：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=‹KEY已隐藏·存于密码管理器或服务器remind.py›`

---

## 手机号映射（企业微信@人用）

| 邮箱 | 手机号 | 备注 |
|------|--------|------|
| 13231252391@163.com | 13231252391 | 我（老板） |
| 13112157729@163.com | 13315240007 | 刘颖 |

**修改方法**：`nano /var/www/ai-secretary/remind.py`，找到 `PHONE_MAP` 那块编辑，Ctrl+X → Y → 回车保存。

---

## 数据库关键字段

任务表（`public.tasks`）实际字段名：
- `content` — 任务内容（不是 title！）
- `remind_time` — 提醒时间（不是 due_date！）
- `reminded` — 是否已提醒（Boolean，防重复）
- `status` — pending / in_progress / done
- `category` — 分类
- `priority` — 优先级（数字）
- `progress_note` — 打卡备注
- `snooze_until` — 推迟到何时

---

## 当前在讨论的事情

用户想优化 AI 秘书的 UI 设计，提到想用某个设计工具（Open Design？待确认具体是哪个工具），需要给出适合的设计提示词。

---

## 访问地址

- **网站**：https://mede-in-ai.com
- **API健康检查**：https://mede-in-ai.com/api/health

---

## 常用运维命令

```bash
# 重启后端
systemctl restart ai-secretary

# 查看后端日志
journalctl -u ai-secretary -f

# 重新打包前端
cd /var/www/ai-secretary/frontend && npm run build

# 查看提醒日志
tail -f /var/log/remind.log

# 查看晨报日志
tail -f /var/log/notify.log

# 重载Nginx
systemctl reload nginx
```
