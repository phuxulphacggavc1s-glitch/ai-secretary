# AI 结果秘书 · V2「闭环督办」开发计划

> 一句话目标：把现在"提醒完就结束"的秘书，升级成"**没有结果就不许结束、会主动追着你要进展**"的秘书。
> 核心理念（来自老板）：老板交代的每一件事，AI 负责盯到有结果为止。

本文档分两层：**上半部分（一～四）给老板看，能看懂、能拍板**；**下半部分（五～十）给 Claude Code / Codex 看，照着做**。

---

## 一、先对齐现状：你现在这套比想象中强

经过通读代码，现状如下（**不用推倒重来，是加一层**）：

技术底子：FastAPI 后端 + React 前端 + Supabase（云数据库）+ DeepSeek（AI 解析），已部署可用。

**已经有的能力（保留）：**
- AI 把人话解析成任务（DeepSeek，已抓"内容 / 分类 / 提醒时间"）
- "今日简报"雏形（打开 App 实时算今日重点、逾期、进度问询）—— 这其实就是老板驾驶舱的早期版
- 进行中状态、问进度（checkin）、温柔推迟（snooze）
- 每晚 21 点自动日报
- 优先级排序（数字 1/2/3）

**两个必须纠正的认知（读了《当前状态交接文档》后修正）：**

1. **企业微信其实早就上线了。** 它跑在你阿里云服务器上的两个独立脚本里：`notify.py`（每早 8 点晨报）、`remind.py`（每分钟到点 @人 提醒），Webhook 和手机号 @人 都配好了。所以"主推送通道"这件事**不用从零做**，已经有了，本次是**升级它推送的内容、并补上闭环**。
2. **代码两地不一致（这是隐患，必须最先解决）。** 项目文件夹（git 仓库）里**没有** `notify.py` / `remind.py`，它们只存在于服务器 `/var/www/ai-secretary/`。同时仓库里还有一套**没用上的邮件提醒**（`services/reminder.py` + `email_service.py`，APScheduler 每分钟发邮件）。也就是说：**Claude Code 能看到的仓库 ≠ 线上真正在跑的东西**。不先把它们对齐，改了也白改。详见【阶段 0：代码归位】。

---

## 二、这次真正要做的：补上"闭环"这一环

下面打 ❌ 的，才是这次的核心工作量。打 ✅ 的已有，基本不动。

| 能力 | 现状 | 这次 |
|---|---|---|
| AI 解析任务 | ✅ 有（只抓内容/分类/时间） | 🔧 升级：再抓**目标、成功标准、相关人**，信息缺了**主动追问** |
| 目标 / 成功标准 字段 | ❌ 没有 | ✅ 新增（"结果导向"的根） |
| 任务状态 | 只有 3 种 | ✅ 扩到 6 种：待办 / 进行中 / **等回复** / **受阻** / 已完成 / **已取消** |
| 看你回复→判断状态→生成下一步 | ❌ 没有 | ✅ 新增（**闭环的灵魂**：AI 读你的回复，自动改状态、自动定下次跟进时间） |
| 自动督办循环（没结果不结束） | ❌ 提醒发一次就停 | ✅ 新增：每天扫描"到了跟进时间还没完成"的任务，自动再催 |
| 提醒通道 | ✅ 企业微信已上线（服务器脚本） | 🔧 升级推送内容（带目标/状态/回复入口）+ 纳入仓库管理 |
| 优先级规则 | 只排序 | 🔧 升级为 S/A/B：S 级当天没完成，**晚上二次提醒** |
| 老板驾驶舱 | ✅ App 内有雏形 | 🔧 升级：每天早 8 点**主动推到企业微信** + 增加"等回复超时 / 受阻"两块 |
| 操作日志 / AI 判断可追溯 | ❌ 没有 | ✅ 新增 `task_events` 日志表（每次状态变更、每次 AI 判断都留痕） |

---

## 三、升级后，一件事是怎么被"盯到有结果"的（举例）

```
你说：「下周三下午三点提醒我联系山东供应商确认聚氨酯杠铃片报价」
   ↓ AI 解析
任务：联系山东供应商确认报价
目标：拿到聚氨酯杠铃片正式报价单   ← 新增，AI 自动补；补不全就追问你
状态：待办   优先级：A
   ↓ 到周三下午三点
【企业微信群机器人】叮你：
   「任务：联系山东供应商确认报价
     目标：拿到正式报价单
     请回复进展：1已完成 2已联系等回复 3遇到问题 4延期」
   （消息里带一个链接，点开回到 App 回复）
   ↓ 你在 App 回复：「李总说下周给报价」
AI 判断：
   状态 → 等回复
   下一步 → 下周跟进李总报价
   下次跟进时间 → 7 天后
   ↓ 7 天后系统自动扫描到「到点了还没完成」
【企业微信】再次叮你：「上次李总说这周给报价，收到了吗？」
   ↓ ……循环，直到
状态 = 已完成 ✅   才停止追。
```

**关键规则（系统的铁律）：** 只要一个任务状态不是"已完成 / 已取消"，系统就**必须**给它定一个"下次跟进时间"。没有结果，就一直有下一次。

---

## 四、一个你需要知道的技术现实（重要）

企业微信"**群机器人**"是**只能往外发消息、不能接收你的回复**的（这是企业微信的限制，不是我们能改的）。

所以本次的闭环是这样跑的：
- **往外催**：群机器人推送提醒到你手机 ✅
- **你回复**：在 App 里回复（提醒消息里带链接，点一下回到 App）✅
- **AI 判断 + 定下次** ✅

**想做到"直接在企业微信里打字回复，AI 就接住"**，需要换成更重的"企业微信自建应用 + 回调服务器"，配置复杂。**这一项放到第二阶段**，先不做。它不影响闭环成立，只是回复入口从 App 变成 IM 的区别。

> ✅ 这个前置条件**已经满足**：群机器人 Webhook 早已配好（在服务器 `remind.py` / `notify.py` 里），还做了按手机号 @人。本次直接复用，无需你再操作。

---
---

# 以下为技术执行部分（给 Claude Code / Codex）

## 五、数据模型改动（Supabase）

新建迁移文件 `supabase/upgrade_v2_closeloop.sql`，并同步更新 `supabase/schema.sql` 保持一致。

### 5.1 `tasks` 表新增字段（结果导向 + 闭环）
```sql
alter table public.tasks add column if not exists goal text;              -- 目标/想要的结果
alter table public.tasks add column if not exists success_criteria text;  -- 成功标准(怎样算完成)
alter table public.tasks add column if not exists related_person text;    -- 相关的人(供应商/李总…)
alter table public.tasks add column if not exists next_action text;       -- 下一步该做什么
alter table public.tasks add column if not exists next_follow_time timestamptz; -- 下一次跟进时间(闭环核心)
alter table public.tasks add column if not exists priority_level text default 'B'
  check (priority_level in ('S','A','B'));                                 -- 新优先级
```

### 5.2 扩展状态枚举（3 → 6）
**决策：保留现有 `done` 作为"已完成"的值**（避免改动现有数据和大量代码；`done` 即 PRD 的 COMPLETED）。新增 3 个状态：
```sql
alter table public.tasks drop constraint if exists tasks_status_check;
alter table public.tasks add constraint tasks_status_check
  check (status in ('pending','in_progress','waiting_response','blocked','done','cancelled'));
```
状态对照（代码值 ↔ PRD 名 ↔ 中文）：
`pending`=PENDING=待办 · `in_progress`=IN_PROGRESS=进行中 · `waiting_response`=WAITING_RESPONSE=等回复 · `blocked`=BLOCKED=受阻 · `done`=COMPLETED=已完成 · `cancelled`=CANCELLED=已取消。

### 5.3 优先级迁移（int → S/A/B，保留 int 向后兼容）
```sql
update public.tasks set priority_level =
  case when priority = 3 then 'S' when priority = 2 then 'A' else 'B' end
  where priority_level is null;
```
> 新逻辑一律以 `priority_level` 为准；写任务时 API 层把 S/A/B 同步回 int（S=3,A=2,B=1），保证旧前端不崩。

### 5.4 `users` 表新增企业微信通道（支持多用户，每人一个机器人）
```sql
alter table public.users add column if not exists wecom_webhook text;
```
> 没配的用户回退到环境变量 `WECOM_WEBHOOK_URL`（单用户期先用 env 即可）。

### 5.5 新增日志表 `task_events`（满足 PRD"状态变更必须记录日志 + AI 判断可追溯"）
```sql
create table if not exists public.task_events (
  id uuid primary key default gen_random_uuid(),
  task_id uuid references public.tasks(id) on delete cascade not null,
  user_id uuid references public.users(id) on delete cascade not null,
  event_type text not null,        -- created/status_change/checkin/ai_parse/ai_judge/reminder_sent/follow_generated
  from_status text,
  to_status text,
  ai_raw jsonb,                     -- 保留 AI 原始输出，可追溯
  note text,
  created_at timestamptz default now()
);
create index if not exists idx_task_events_task on public.task_events(task_id, created_at desc);
alter table public.task_events enable row level security;
create policy "Users see own task_events" on public.task_events for all using (auth.uid() = user_id);
```
新增 `next_follow_time` 督办扫描索引：
```sql
create index if not exists idx_tasks_followup on public.tasks(next_follow_time, status)
  where status not in ('done','cancelled');
```

---

## 六、后端改动（FastAPI，模块化）

### 6.1 配置 `backend/config.py`
新增：`WECOM_WEBHOOK_URL = os.getenv("WECOM_WEBHOOK_URL")`，同步更新 `.env.example`。

### 6.2 整理推送服务 `backend/services/wecom.py`（**基于线上 `remind.py` 重构，不是从零写**）
- 先把服务器 `remind.py`/`notify.py` 里现成的企业微信发送 + `@人`（`PHONE_MAP`）逻辑搬进来、整理成可复用函数。
- `send_wecom(webhook, content, mentioned_mobiles=None)`：用 `requests` POST，`msgtype="markdown"`（手机排版好看），支持按手机号 @人。**必须带 fallback**：webhook 为空或失败只 print + 返回 None，不抛错（参考 `email_service._can_send`）。
- `resolve_webhook(user_id)`：优先取 `users.wecom_webhook`，否则回退 `WECOM_WEBHOOK_URL`（即现有那个 key）。
- 提醒消息模板按 PRD 模块4：任务 / 目标 / 截止 / 当前状态 / "请回复进展：1已完成 2已联系等回复 3遇到问题 4延期" + 一个回 App 的链接（`FRONTEND_URL`）。

### 6.3 升级 AI 解析 `backend/services/ai_parser.py`
在现有 `parse_task` 基础上扩展 prompt 输出字段，并**新增追问能力**：
- 返回新增：`goal`、`success_criteria`、`related_person`、`missing_fields`（缺失的关键信息列表）、`clarify_question`（当缺目标/标准/截止时间时，给一句追问，如"这件事最终算完成的标准是什么？拿到报价、确认合作、还是完成沟通？"）、`is_complete`。
- 保留现有 `_fallback`（DeepSeek 不可用时降级，不崩）。
- temperature 维持 0.1，`max_tokens` 适当调大到 ~500。

### 6.4 新增闭环督办引擎 `backend/services/followup.py`（**核心**）
- `judge_reply(task, user_reply) -> dict`：把任务上下文 + 用户回复给 DeepSeek，要求返回 `{new_status, progress_note, next_action, next_follow_time, ai_raw}`。判断准则写进 prompt（PRD 第四节）：**只看是否拿到最终结果，没拿到就不能判完成**；"对方承诺X天后给" → `waiting_response` + `next_follow_time = X天后`。**必须带规则化 fallback**（AI 挂了就按关键词粗判：含"完成/搞定/拿到"→done；含"等/回头/下周"→waiting_response + 默认 3 天后）。
- `ensure_next_follow(task)`：铁律落地——若 `status not in (done,cancelled)` 且 `next_follow_time` 为空，则补一个默认值（有 remind_time 用它，否则 now+1天）。
- `scan_followups()`：查 `next_follow_time <= now AND status not in (done,cancelled)` → 逐个 `send_wecom` → 写 `task_events(event_type='reminder_sent')` → 把 `next_follow_time` 顺延一档（防止同一条一天刷屏；例如顺延到次日同一时间，等用户回复后再由 `judge_reply` 重定）。
- `escalate_s_level()`：S 级任务当天到截止仍未完成 → 晚上二次提醒（PRD 模块6）。

### 6.5 调度器 `backend/main.py`
- 现有 `check_and_send_reminders`（邮件）→ 改为调用 `scan_followups()`（企业微信），仍每分钟跑。首次提醒逻辑：任务到 `remind_time` 时若 `next_follow_time` 为空，先用 `remind_time` 当第一次跟进点。
- 新增 cron：每天 `08:00` 推送老板驾驶舱到企业微信（见 6.7）；每天 `20:00` 跑 `escalate_s_level()`。
- 保留 21:00 日报（可顺带也推企业微信）。

### 6.6 路由改动 `backend/routers/tasks.py`
- `POST /tasks/{id}/reply`（新）：body `{ reply_text }` → 调 `judge_reply` → 更新任务（status/progress_note/next_action/next_follow_time）→ 写 `task_events(ai_judge)` → 返回 AI 判断结果给前端确认。
- `create_task`：写入新字段（goal/success_criteria/related_person/priority_level）；建任务即写 `task_events(created)` 并调 `ensure_next_follow`。
- `update_task` / `checkin_task`：状态变更时写 `task_events(status_change, from→to)`。
- 所有写操作维持 `.eq("user_id", user.id)`（安全，沿用现有写法）。

### 6.7 老板驾驶舱 `backend/services/secretary.py`
- 复用现有 `build_briefing`，**新增两块**：`waiting_overdue`（status=waiting_response 且超过预期跟进时间）、`blocked`（status=blocked）。
- 新增 `push_morning_briefing()`：早 8 点把"今日必须完成(S级) / 已超期 / 等回复超时 / 今日需跟进"格式化后 `send_wecom`。

### 6.8 数据模型 `backend/models/schemas.py`
- `TaskConfirm` / `TaskUpdate` 增加：`goal`、`success_criteria`、`related_person`、`next_action`、`next_follow_time`、`priority_level`。
- 状态校验集合更新为 6 种。
- 新增 `ReplyBody { reply_text: str }`。

---

## 七、前端改动（React，最小可用）

- `frontend/src/api.js`：新增 `replyTask(id, {reply_text})`、`getBriefing` 已有则复用；任务创建表单传新字段。
- 创建任务流（`TaskInput.jsx` / `ParsePreview.jsx`）：当解析返回 `clarify_question` 时，弹出追问让用户补"目标/成功标准"，再提交。
- `TaskCard.jsx`：展示 6 种状态徽章、`goal`、`next_follow_time`、`related_person`。
- 新增"回复进展"入口：自由输入框 → `replyTask` → 展示 AI 判断的新状态和下次跟进，让用户确认。
- `SecretaryBriefing.jsx`：增加"等回复超时""受阻"两区。
- `Tasks.jsx`：筛选项补齐 6 种状态。

---

## 八、分阶段计划（按老板的 P0/P1）

### 阶段 0 · 代码归位（**必须最先做，否则全是空中楼阁**）
线上真正在跑的逻辑（`notify.py` / `remind.py`）不在仓库里，必须先拉回来统一管理：
1. SSH 上服务器（`ssh root@‹服务器IP已隐藏›`），把 `/var/www/ai-secretary/` 下的 `notify.py`、`remind.py`、以及实际在用的 `.env`（脱敏后）拷回本地仓库。
2. 读懂这两个脚本现在到底怎么发企业微信、怎么 @人（`PHONE_MAP`），作为本次升级的真实起点。
3. 厘清"**两套提醒**"：仓库里 `main.py` 的 APScheduler 还在发邮件（`reminder.py`/`daily_report.py`），而线上靠 cron 跑 `notify.py`/`remind.py` 发企业微信。**确认线上是否两套都在跑**（可能导致重复提醒），决定保留哪套——建议：**统一收口到企业微信，邮件那套停用或降级为备份**。
4. 把归位后的代码提交 git，让"仓库 = 线上"。**这一步通了，后面才有意义。**

### 阶段 0.5 · 技术地基（约占 10%）
数据库迁移（5.1–5.5）+ `config` + 把企业微信发送整理成统一服务 `wecom.py`（复用线上 webhook 与 `PHONE_MAP`）+ 自测："手动调一次 `send_wecom` 能在企业微信群里收到测试消息"。**通了再往下。**

### 阶段 1 · P0 核心闭环（最重要）
1. AI 解析升级（6.3，抓目标/标准 + 追问）
2. 闭环引擎 `followup.py`（6.4：judge_reply + ensure_next_follow + scan_followups）
3. 提醒通道切到企业微信、调度器改造（6.5）
4. `/tasks/{id}/reply` + 创建/更新接 AI 判断与事件日志（6.6）
5. `task_events` 日志贯穿所有状态变更与 AI 判断
6. 前端：追问填目标 + 回复进展 UI + 6 状态展示（七）

> 阶段 1 验收标准：建一个测试任务 → 到点企业微信收到提醒 → App 回复"对方下周给" → 状态自动变"等回复"、自动生成 7 天后跟进 → 到期再次自动催。**完整跑通一圈 = P0 达成。**

### 阶段 2 · P0 收尾 + 增强
7. S/A/B 优先级规则，S 级当晚二次提醒（6.4 `escalate_s_level`）
8. 老板驾驶舱早 8 点推企业微信 + 等回复超时/受阻区（6.7）

### 阶段 3 · P1（以后）
项目分类、联系人档案、历史任务记录、风险分析；以及"**企业微信自建应用**"（实现 IM 内直接回复，免回 App，见第四节）。

---

## 九、给 Claude Code 的执行顺序（对应老板的 5 步）

1. **数据库 & 架构**：执行第五节 SQL（先 Supabase 后台跑，再同步 `schema.sql`），建 `task_events`。
2. **后端 API**：schemas → wecom 服务 → ai_parser 升级 → followup 引擎 → 路由（reply/create/checkin 事件日志）。
3. **接企业微信**：切换调度器通道，自测推送一条真实提醒。
4. **AI 任务解析 & 闭环督办**：跑通"建任务→提醒→回复→AI判断→生成下次→再催"整圈。
5. **测试 & 部署**：补 `backend/tests/` 用例（解析、judge_reply 的 fallback、scan_followups、状态机），本地全流程联调。部署=**阿里云 ECS**（非 Railway/Vercel）：SSH 上 `‹服务器IP已隐藏›` → 拉最新代码 → `systemctl restart ai-secretary` 重启后端 → `cd frontend && npm run build` 重打包前端 → 必要时 `systemctl reload nginx`；提醒脚本若改了 cron 也一并更新。日志：`journalctl -u ai-secretary -f`、`tail -f /var/log/remind.log`。

> 建议每完成一个阶段就本地验证一次，别一次性全上。

---

## 十、技术规范（对齐 PRD"代码要求"）

- **模块化**：新逻辑各自成文件（`wecom.py` / `followup.py`），不往现有文件硬塞。
- **枚举**：状态、优先级、事件类型集中定义为常量/枚举，杜绝散落的魔法字符串。
- **状态变更必留痕**：任何 status 改动写 `task_events(from→to)`。
- **AI 判断可追溯**：`judge_reply` / `parse_task` 的原始输出存 `task_events.ai_raw`（jsonb）。
- **AI 必有 fallback**：所有 DeepSeek 调用失败都要降级到规则法，绝不让用户卡住（沿用现有 `_fallback` 风格）。
- **多用户就绪**：所有查询/写入按 `user_id` 隔离（现有 RLS + `.eq("user_id")` 已具备）。
- **API 可扩展**：通道做成接口（今天企业微信，明天加飞书/钉钉只需加一个 sender）。

---

## 十一、需要老板确认/提供的事项

1. ✅ 提醒通道 = 企业微信群机器人（**已上线**，复用现成 webhook + @人）
2. ✅ Webhook 已有，无需再提供
3. ⏳ **同意先做【阶段 0 代码归位】**：把服务器上的 `notify.py`/`remind.py` 拉回仓库统一管理（这是后续一切的前提）
4. ⏳ "两套提醒"如何收口：建议统一到企业微信、停用邮件那套——确认
5. ⏳ 确认状态"已完成"沿用代码值 `done`（不改名，省风险）
6. ⏳ S 级"晚上二次提醒"时间点（建议 20:00）；驾驶舱晨报沿用早 8 点（现状）

> 安全提醒：交接文档里写了服务器 SSH、Webhook key 等敏感信息，这些是你的凭据，注意别外传。

---

> 本计划只规划、未改动任何代码。老板确认后，从【阶段 0 地基】开始动手。
