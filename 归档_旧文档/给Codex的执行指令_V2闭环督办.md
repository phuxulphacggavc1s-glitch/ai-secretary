# Codex 执行指令 · AI 结果秘书 V2「闭环督办」

> 本文件是给 AI 编码代理（Codex / Claude Code）的可执行规格说明。请**严格按阶段顺序执行**，每个阶段做完先自测、通过再进入下一阶段；不要跳步、不要一次性全改。
> 配套的人类版方案见 `AI结果秘书_V2闭环督办_开发计划.md`（背景与决策依据），本文件为权威执行规格，冲突以本文件为准。

---

## 0. 必读：项目现状与硬性事实（动手前先确认）

**技术栈**：FastAPI(Python) + React/Vite + Supabase(PostgreSQL+Auth) + DeepSeek API。部署在阿里云 ECS（Nginx 反代 + systemd），域名 mede-in-ai.com。

**仓库关键路径**：
```
backend/
  main.py                  # FastAPI 入口 + APScheduler 调度
  config.py                # 读环境变量
  database.py              # supabase 客户端
  auth.py                  # get_current_user 鉴权
  models/schemas.py        # Pydantic 模型
  routers/tasks.py routers/secretary.py routers/reports.py
  services/ai_parser.py    # DeepSeek 解析（现仅抓 content/category/remind_time）
  services/secretary.py    # build_briefing 今日简报
  services/reminder.py     # 【邮件】提醒（本次停用）
  services/email_service.py# Resend 邮件（本次停用）
  services/daily_report.py # 21点日报（邮件）
  tests/
frontend/src/...           # api.js, components/, pages/, hooks/
supabase/schema.sql supabase/upgrade_secretary.sql
```

**必须牢记的事实（容易踩坑）**：
1. 任务表字段名是 `content`（不是 title）、`remind_time`（不是 due_date）、`reminded`（bool 防重复）。
2. 现有 `status` 取值只有 `pending / in_progress / done`。**`done` 即"已完成"，本次不改名**（避免破坏现有数据与代码）。
3. 现有 `priority` 是 int(1/2/3)。本次新增 `priority_level`(S/A/B)，并保持 int 同步（S=3,A=2,B=1）以兼容旧前端。
4. **真正在跑的企业微信提醒不在本仓库**：它在服务器 `/var/www/ai-secretary/` 下的 `notify.py`(早8点晨报) 与 `remind.py`(每分钟到点@人)，内含 Webhook 与 `PHONE_MAP`（按手机号@人）。仓库里 `services/reminder.py` 是另一套**没用上的邮件提醒**。
5. **本次通道决策：只用企业微信，停用邮件**（移除/禁用邮件提醒与邮件日报的调用）。

**所有 AI 调用统一用 DeepSeek**（`config.DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`，`openai` SDK，model=`deepseek-chat`），**必须带 fallback**：调用失败时降级到规则法或固定模板，绝不抛错给用户。

---

## 1. 全局约束（每个阶段都要遵守）

- **模块化**：新逻辑独立成文件（`services/wecom.py`、`services/followup.py`、`constants.py`），不往旧文件硬塞。
- **枚举集中**：在 `backend/constants.py` 定义并全局复用：
  ```python
  from enum import Enum
  class TaskStatus(str, Enum):
      PENDING="pending"; IN_PROGRESS="in_progress"; WAITING_RESPONSE="waiting_response"
      BLOCKED="blocked"; DONE="done"; CANCELLED="cancelled"
  class PriorityLevel(str, Enum):
      S="S"; A="A"; B="B"
  class EventType(str, Enum):
      CREATED="created"; STATUS_CHANGE="status_change"; CHECKIN="checkin"
      AI_PARSE="ai_parse"; AI_JUDGE="ai_judge"; REMINDER_SENT="reminder_sent"
      FOLLOW_GENERATED="follow_generated"
  PRIORITY_INT_MAP={"S":3,"A":2,"B":1}
  ```
  禁止散落魔法字符串。
- **状态变更必留痕**：任何 status 改动都写一条 `task_events(event_type=status_change, from_status, to_status)`。
- **AI 判断可追溯**：`parse_task` / `judge_reply` 的原始返回存入 `task_events.ai_raw`(jsonb)。
- **多用户隔离**：所有任务读写带 `.eq("user_id", user.id)`（沿用现有写法），不得放宽 RLS。
- **铁律**：任务 `status` 不属于 {done, cancelled} 时，**必须**有 `next_follow_time`；任何创建/状态更新后都调用 `ensure_next_follow`。
- 不破坏现有可用功能；改动尽量小、可回滚。

---

## 2. 阶段 0 · 代码归位（最先做，前置）

目的：让"仓库 = 线上"，否则后续改动与线上脱节。

任务：
1. 确认仓库根目录是否已放入从服务器取回的 `notify.py`、`remind.py`（人工提供，见第 9 节）。
   - **若已提供**：阅读这两个脚本，提取其中的企业微信发送逻辑、Webhook 读取方式、`PHONE_MAP`（邮箱→手机号），作为 `services/wecom.py` 的实现基础。
   - **若暂未提供**：以 `WECOM_WEBHOOK_URL` 环境变量为准实现 `wecom.py`，并在代码注释标注 `# TODO: 与服务器 remind.py 的 PHONE_MAP 对齐`，不要卡住后续开发。
2. 厘清"两套提醒"：仓库 `main.py` 的 APScheduler 调 `check_and_send_reminders`(邮件) 与 `generate_daily_reports`(邮件)；线上另有 cron 跑 `notify.py/remind.py`(企业微信)。**按决策停用邮件那套**（见 6.5）。
3. 提交一次 git，使归位后的文件入库。

验收：仓库内可见 `notify.py/remind.py`（或已重构进 `wecom.py`）；明确记录线上提醒由谁负责、邮件已计划停用。

---

## 3. 阶段 0.5 · 数据库迁移 + 配置 + 推送服务

### 3.1 新建 `supabase/upgrade_v2_closeloop.sql`（并同步更新 `supabase/schema.sql`）
```sql
-- 结果导向 + 闭环字段
alter table public.tasks add column if not exists goal text;
alter table public.tasks add column if not exists success_criteria text;
alter table public.tasks add column if not exists related_person text;
alter table public.tasks add column if not exists next_action text;
alter table public.tasks add column if not exists next_follow_time timestamptz;
alter table public.tasks add column if not exists priority_level text default 'B'
  check (priority_level in ('S','A','B'));

-- 状态扩到 6 种（保留 done 作为"已完成"）
alter table public.tasks drop constraint if exists tasks_status_check;
alter table public.tasks add constraint tasks_status_check
  check (status in ('pending','in_progress','waiting_response','blocked','done','cancelled'));

-- 优先级迁移 int -> S/A/B
update public.tasks set priority_level =
  case when priority = 3 then 'S' when priority = 2 then 'A' else 'B' end
  where priority_level is null;

-- 企业微信通道（多用户，每人一个机器人；空则回退环境变量）
alter table public.users add column if not exists wecom_webhook text;

-- 审计日志表（状态变更 / AI 判断可追溯）
create table if not exists public.task_events (
  id uuid primary key default gen_random_uuid(),
  task_id uuid references public.tasks(id) on delete cascade not null,
  user_id uuid references public.users(id) on delete cascade not null,
  event_type text not null,
  from_status text,
  to_status text,
  ai_raw jsonb,
  note text,
  created_at timestamptz default now()
);
create index if not exists idx_task_events_task on public.task_events(task_id, created_at desc);
alter table public.task_events enable row level security;
create policy "Users see own task_events" on public.task_events for all using (auth.uid() = user_id);

-- 督办扫描索引
create index if not exists idx_tasks_followup on public.tasks(next_follow_time, status)
  where status not in ('done','cancelled');
```
> 执行方式：先在 Supabase 后台 SQL Editor 跑，再把同样变更同步进仓库 `schema.sql`。

### 3.2 `backend/config.py`
新增 `WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL")`；同步 `.env.example`。

### 3.3 新建 `backend/services/wecom.py`
```python
def resolve_webhook(user_id: str) -> str | None: ...   # 优先 users.wecom_webhook，否则 WECOM_WEBHOOK_URL
def send_wecom(webhook: str | None, markdown: str, mentioned_mobiles: list[str] | None = None) -> bool:
    """requests POST 到企业微信群机器人, msgtype=markdown, 支持 @手机号。
       webhook 为空或请求异常 -> print + return False, 不抛错。"""
def build_reminder_markdown(task: dict) -> str:
    """按模板：任务 / 目标 / 截止时间 / 当前状态 / 回复指引(1已完成 2已联系等回复 3遇到问题 4延期) + 回 App 链接(FRONTEND_URL)。"""
```
（若阶段 0 拿到 `remind.py`，把其中的发送与 `PHONE_MAP` 逻辑搬进来复用。）

**自测**：写一个临时脚本或 pytest 调 `send_wecom(WECOM_WEBHOOK_URL, "## 测试\nV2 通道联通")`，确认企业微信群收到。通过后再继续。

---

## 4. 阶段 1 · P0 核心闭环（最重要）

### 4.1 升级 `backend/services/ai_parser.py`
扩展 system prompt 的输出 JSON，新增字段：`goal`、`success_criteria`、`related_person`、`missing_fields`(list)、`clarify_question`(string|null)、`is_complete`(bool)。规则：
- 缺少"目标/成功标准/截止时间"任一关键项时，`is_complete=false` 且给出一句中文追问填入 `clarify_question`（例："这件事最终算完成的标准是什么？拿到报价、确认合作、还是完成沟通？"）。
- 保留现有 `_fallback`；`max_tokens` 提到 ~500，temperature 仍 0.1。

### 4.2 新建 `backend/services/followup.py`（核心引擎）
```python
def judge_reply(task: dict, reply_text: str) -> dict:
    """把任务上下文+用户回复给 DeepSeek，返回:
       { new_status, progress_note, next_action, next_follow_time(ISO或None), ai_raw }
       判定准则(写进 prompt): 只看是否拿到【最终结果】，没拿到不得判 done；
       "对方承诺X天后给"->waiting_response 且 next_follow_time=X天后；
       "卡住/缺东西"->blocked。
       【必须 fallback】AI 失败时按关键词粗判:
         含 完成/搞定/拿到/已收到 -> done
         含 等/回头/下周/明天再 -> waiting_response, next_follow_time=now+3天
         其它 -> in_progress, next_follow_time=now+1天 """

def ensure_next_follow(task: dict) -> dict:
    """若 status 不在 {done,cancelled} 且 next_follow_time 为空：
       有 remind_time 用 remind_time，否则 now+1天。返回需更新的字段。"""

def scan_followups() -> None:
    """查 next_follow_time<=now 且 status not in (done,cancelled) 的任务，逐条:
       send_wecom(build_reminder_markdown) -> 写 task_events(REMINDER_SENT)
       -> 把 next_follow_time 顺延一档(如次日同一时间), 防止同一天刷屏。"""

def escalate_s_level() -> None:
    """priority_level='S' 且当天截止仍未 done 的任务，晚间二次提醒(send_wecom)。"""
```

### 4.3 `backend/models/schemas.py`
- `TaskConfirm` / `TaskUpdate` 增字段：`goal`、`success_criteria`、`related_person`、`next_action`、`next_follow_time`、`priority_level`。
- 状态校验集合改为 `TaskStatus` 全 6 种（`CheckinBody.status` 放行 in_progress/waiting_response/blocked/done）。
- 新增 `ReplyBody { reply_text: str = Field(min_length=1, max_length=1000) }`。

### 4.4 `backend/routers/tasks.py`
- **新增** `POST /tasks/{task_id}/reply`(body=ReplyBody)：取任务→`judge_reply`→更新 status/progress_note/next_action/next_follow_time→写 `task_events(AI_JUDGE, from→to, ai_raw)`→返回 AI 判断结果供前端确认。带 `.eq("user_id")`。
- `create_task`：写入新字段；建任务后写 `task_events(CREATED)`，并应用 `ensure_next_follow`；按 `priority_level` 同步 `priority` int。
- `update_task` / `checkin_task`：当 status 变化时写 `task_events(STATUS_CHANGE, from→to)`；更新后再跑 `ensure_next_follow`。

### 4.5 前端（最小可用）
- `frontend/src/api.js`：新增 `replyTask(id,{reply_text})`；创建任务表单提交新字段。
- `TaskInput.jsx`/`ParsePreview.jsx`：解析返回 `clarify_question` 时，弹出追问让用户补"目标/成功标准"再提交。
- `TaskCard.jsx`：展示 6 种状态徽章、`goal`、`next_follow_time`、`related_person`。
- 新增"回复进展"输入框 → 调 `replyTask` → 展示 AI 判断的新状态与下次跟进，让用户确认。

### 阶段 1 验收（必须整圈跑通）
建测试任务 → 到 `remind_time` 企业微信收到提醒 → 在 App 用"回复进展"提交"对方下周给报价" → 状态自动变 `waiting_response`、自动生成约 7 天后 `next_follow_time` → 到期 `scan_followups` 再次自动推送。`task_events` 中能查到 created / reminder_sent / ai_judge 全链路记录。

---

## 5. 阶段 2 · P0 收尾 + 驾驶舱增强

### 5.1 优先级规则
`escalate_s_level()` 接入调度（每天 20:00）；S 级当天未完成晚间二次提醒。

### 5.2 老板驾驶舱 `backend/services/secretary.py` + `routers/secretary.py`
- `build_briefing` 增两块：`waiting_overdue`(status=waiting_response 且超过预期跟进时间)、`blocked`(status=blocked)。
- 新增 `push_morning_briefing()`：每天 08:00 把"今日必须完成(S级)/已超期/等回复超时/今日需跟进"格式化后 `send_wecom`。
- 前端 `SecretaryBriefing.jsx` 增"等回复超时""受阻"两区；`Tasks.jsx` 筛选补齐 6 状态。

---

## 6. 调度器与通道收口 `backend/main.py`

- 将每分钟任务从 `check_and_send_reminders`(邮件) 改为 `scan_followups()`(企业微信)。
- 新增 cron：`08:00` → `push_morning_briefing`；`20:00` → `escalate_s_level`。
- **停用邮件**：移除/注释 `generate_daily_reports` 的邮件发送与 `check_and_send_reminders` 邮件调用；`services/reminder.py`、`email_service.py` 标记为弃用（保留文件但不在调度中引用）。如需日报可改为 `send_wecom` 推送。
- 线上 cron 跑的 `notify.py/remind.py` 与新调度**不要重复发**：归位后二选一（推荐统一由 FastAPI 内 APScheduler 负责，停掉服务器 cron；或反之，但只能留一套）。在 PR 描述里写清最终方案。

---

## 7. 测试要求 `backend/tests/`

新增/补充用例（pytest，沿用 `conftest.py` 风格，外部调用 mock）：
- `ai_parser`：缺信息时返回 `clarify_question` 且 `is_complete=false`；DeepSeek 失败走 fallback 不抛错。
- `followup.judge_reply`：fallback 关键词分支（done / waiting_response / in_progress）正确。
- `followup.ensure_next_follow`：非终态且无 next_follow_time 时被补齐；终态不补。
- `followup.scan_followups`：到期任务被推送且 next_follow_time 顺延、写入 reminder_sent 事件。
- 状态机：每次 status 变更产生 status_change 事件。
- 全部带 `user_id` 隔离断言。

---

## 8. 部署（阿里云 ECS，**非 Railway/Vercel**）

SSH 上服务器（IP/凭据见你的密码管理器，文档中已隐藏）后：
```bash
cd /var/www/ai-secretary && git pull
# 在 Supabase 后台先执行 upgrade_v2_closeloop.sql
cd backend && source venv/bin/activate && pip install -r requirements.txt
systemctl restart ai-secretary
cd ../frontend && npm ci && npm run build
systemctl reload nginx
# 若改了提醒归属：相应更新/停用服务器 crontab 里的 notify.py/remind.py
```
排错：`journalctl -u ai-secretary -f`、`tail -f /var/log/remind.log`。新增环境变量 `WECOM_WEBHOOK_URL` 写入 `backend/.env`。

---

## 9. 需人工提供 / 确认（Codex 无法自取）

1. `WECOM_WEBHOOK_URL`：企业微信群机器人 Webhook（已存在于服务器，填入 `backend/.env`）。
2. 服务器上 `notify.py`、`remind.py` 的内容（用于阶段 0 归位与 `wecom.py` 复用）。
3. 确认"已完成"沿用代码值 `done`（不改名）。
4. 确认提醒最终归属：FastAPI 内 APScheduler 统一负责、停用服务器 cron（推荐）。
5. S 级二次提醒时间默认 20:00、晨报 08:00（如需调整在此说明）。

---

## 10. 交付物（完成后输出）

- 改动文件清单 + 每个 commit 说明（按阶段分 commit）。
- `task_events` 一条完整闭环的样例记录（created→reminder_sent→ai_judge→follow_generated）。
- 更新后的 `supabase/schema.sql`、`.env.example`、本仓库 README 中"提醒通道=企业微信、邮件已停用"的说明。
- 一次端到端验收录屏或日志（建任务→提醒→回复→AI判断→再督办）。
