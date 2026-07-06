# AI 秘书 功能升级方案（Plan，只规划不改代码）

> 目标一句话：把现在"被动备忘录"升级成"主动秘书"——你一打开 App，它就先跟你汇报：今天该干啥、哪件最急、有没有逾期（温柔提一下）、进行中的事问你一句进展。

本次确认的方向（你已选）：
- **提醒渠道**：App 内提醒（不做微信/邮件外部推送，省配置、不用梯子）
- **督促强度**：温柔型（提一下，不反复催）
- **优先做**：① 主动问进度 ② 每日梳理 + 优先级

---

## 一、现状 vs 升级后（大白话）

| | 现在（像备忘录） | 升级后（像秘书） |
|---|---|---|
| 任务状态 | 只有「待办 / 已完成」 | 加一个「**进行中**」，能跟踪做了一半的事 |
| 打开 App 看到 | 一个晚上 9 点才生成的"今日总结"，加最近 5 条记录 | 顶部多一块「**秘书简报**」：今日重点、最急的事、逾期提醒、进度问询 |
| 优先级 | 卡片上只显示个数字「优先级 1」，没排序 | 自动**按优先级 + 截止时间排序**，把"今天最该先干的"顶到最上面 |
| 进度 | 没有这个概念 | 进行中的事，秘书主动问"**这个进展咋样了？**"，你点一下就更新 |
| 逾期 | 不管，过期了也躺着 | 温柔提醒"这件逾期了，要处理还是明天再说"，**当天只提一次** |

> 核心地基：给任务加「进行中」状态。没有它，"问进度"就无从谈起。

---

## 二、升级后你打开 App 的样子（举个例子）

```
┌─────────────────────────────────────┐
│  早上好 👋 今天有 3 件重点，1 件逾期      │
│  今天完成 0 · 进行中 2 · 逾期 1          │   ← 一行小数据，养成"先看大盘"的习惯
├─────────────────────────────────────┤
│  🔴 最该先干：联系供应商确认补货          │   ← 优先级最高那条，单独高亮
├─────────────────────────────────────┤
│  ⚠️ 逾期温柔提醒                         │
│   · 给小红书账号回评论（昨天的）          │
│        [我来处理]  [明天再说]            │   ← 温柔型：点"明天再说"今天就不再烦你
├─────────────────────────────────────┤
│  🤔 进度问询                            │
│   「双11活动方案」进展咋样了？           │
│    [已完成] [还在做] [遇到卡点，记一句]   │   ← 点一下就更新状态/记进度
├─────────────────────────────────────┤
│  📋 今日待办（按优先级排好）             │
│   1. ...  2. ...  3. ...               │
└─────────────────────────────────────┘
```

这套东西**全部在打开 App 时实时算出来**，不依赖邮件、不依赖定时推送，所以不用配微信、不用挂梯子。

---

## 三、分三步走（按你的优先级排）

### 第一阶段（核心，你最想要的）—— "会汇报、会问进度"
1. 数据库加「进行中」状态 + 进度相关字段
2. 后端新增「秘书简报」接口（实时计算今日重点 / 逾期 / 待问进度）
3. 后端新增「回复进度」接口
4. 前端 Home 顶部加「秘书简报」卡片：今日重点（按优先级排序）+ 进度问询卡
5. 任务卡片加「进行中」标识 + 一个"开始做"按钮（待办 → 进行中）

### 第二阶段（顺带增强秘书感）—— "会温柔催"
6. 简报里加「逾期温柔提醒」区，带 [我来处理] / [明天再说]
7. 「明天再说」= 推迟（snooze），当天不再打扰
8. 任务列表页支持按「进行中 / 待办 / 已完成」筛选

### 第三阶段（以后想要了再做）—— "走出 App 找你"
9. 到点提醒升级：支持「提前一天 / 提前一小时」多个提醒点
10. 把提醒推到 App 外（微信 Server酱 / 邮件）——等你哪天觉得"光靠打开 App 看不够"再做
> 你这次没选"到点提醒/外部推送"，所以放到最后，先不做。

---

## 四、具体技术改动（给 Codex 照着做）

### 4.1 数据库（Supabase，执行一段 SQL）
```sql
-- 1) 允许"进行中"状态
alter table public.tasks drop constraint if exists tasks_status_check;
alter table public.tasks add constraint tasks_status_check
  check (status in ('pending', 'in_progress', 'done'));

-- 2) 进度跟踪 & 温柔推迟字段
alter table public.tasks add column if not exists progress_note text;          -- 最近一次进度说明
alter table public.tasks add column if not exists last_checkin_at timestamptz; -- 秘书最近一次问进度的时间
alter table public.tasks add column if not exists snooze_until timestamptz;    -- 推迟后，在此时间前不再打扰

-- 3) 让"待办进度查询"更快（可选）
create index if not exists idx_tasks_status_user on public.tasks(user_id, status);
```
> 同步更新仓库里的 `supabase/schema.sql`，保持一致。

### 4.2 后端（FastAPI）
**新增文件 `backend/services/secretary.py`** —— 计算简报：
- 函数 `build_briefing(user_id)`，返回结构：
  ```json
  {
    "greeting": "早上好，今天有 3 件重点，1 件逾期",
    "stats": { "today_total": 3, "overdue": 1, "in_progress": 2, "done_today": 0 },
    "top_priority": { ...task },                 // 优先级最高的一条
    "today": [ ...今日待办，按 priority 降序、再按 remind_time 升序 ],
    "overdue": [ ...remind_time<现在 且 status!=done 且 (snooze_until 为空或已过) ],
    "checkins": [ ...status=in_progress 且 按"六、进度问询触发规则"判定该问的任务 ]
  }
  ```
- "今日"判断用用户时区（`users.timezone`，默认 Asia/Shanghai）。
- `greeting` 可调用 DeepSeek 生成一句温柔寄语（**必须带 fallback**：调用失败就用固定模板，参考现有 `daily_report.py` 的 `_fallback_report` 写法）。

**新增路由（`backend/routers/` 下，建议新建 `secretary.py`）**：
- `GET /secretary/briefing` → 调 `build_briefing(user.id)`，按 `user_id` 过滤（沿用现有 `get_current_user` 鉴权）。

**改 `backend/routers/tasks.py`**：
- 新增 `POST /tasks/{task_id}/checkin`，body：`{ progress_note?: str, status?: 'in_progress'|'done' }`
  - 更新 `progress_note`、`last_checkin_at = now`，可选更新 `status`；务必 `.eq("user_id", user.id)`。
- 新增 `POST /tasks/{task_id}/snooze`，把 `snooze_until` 设为"明天早上 8 点"（温柔推迟）。
- `update_task` 已支持改 status，确认放行 `in_progress`。

**改 `backend/models/schemas.py`**：
- `TaskUpdate.status` 校验放行 `'in_progress'`。
- 新增 `CheckinBody { progress_note: Optional[str]; status: Optional[str] }`。

> 定时任务（`main.py` 里的 scheduler）**不用动**：简报是"打开就算"的，不需要新的定时器。晚上 9 点的日报保留。

### 4.3 前端（React）
**改 `frontend/src/api.js`** —— 加 4 个调用：
- `getBriefing()` → `GET /secretary/briefing`
- `checkinTask(id, body)` → `POST /tasks/{id}/checkin`
- `snoozeTask(id)` → `POST /tasks/{id}/snooze`
- `startTask(id)` → `PATCH /tasks/{id}`（status = in_progress）

**新增组件 `frontend/src/components/SecretaryBriefing.jsx`**：
- 顶部：问候语 + 一行小数据（今天完成 X · 进行中 Y · 逾期 Z）
- 「最该先干」高亮卡（top_priority）
- 「逾期温柔提醒」列表：每条带 [我来处理] / [明天再说]
- 「进度问询」卡：`「{content}」进展咋样了？` + 按钮 [已完成] / [还在做] / [遇到卡点（弹个输入框记一句）]
- 「今日待办」按优先级排好

**改 `frontend/src/pages/Home.jsx`**：
- 用 `getBriefing()` 替代/补充现在的 `getDailyReport()`，把 `<SecretaryBriefing>` 放到 `TaskInput` 下面（替换现在的 `<DailyReport>` 位置，或并存）。
- 接好 checkin / snooze / start 的回调，操作后刷新简报和任务列表。

**改 `frontend/src/components/TaskCard.jsx`**：
- 加「进行中」状态徽章；待办状态时多一个"开始做"按钮（→ in_progress）。

**改 `frontend/src/pages/Tasks.jsx`**：
- 筛选项加「进行中」。

---

## 五、给 Codex 的执行顺序（建议一步步来，别一次全上）
1. 跑 4.1 的数据库 SQL（先在 Supabase 后台执行，再同步 schema.sql）
2. 后端：schemas → secretary.py（服务）→ routers（secretary + tasks 两个新接口）
3. 本地起后端，用 `/secretary/briefing` 和 `/tasks/{id}/checkin` 各测一次（curl 或 Swagger）
4. 前端：api.js → SecretaryBriefing 组件 → 接进 Home → TaskCard/Tasks 收尾
5. 本地全流程跑一遍：新建任务 → 标记"进行中" → 简报里出现进度问询 → 回复 → 状态更新
6. 部署：后端推 Railway、前端推 Vercel（沿用你现在的部署方式）

---

## 六、已确认的决策（已锁定）
1. **"进行中"怎么触发？** → **手动点"开始做"**（待办 → 进行中，最可控）。以后想要"过期自动算进行中"再加。
2. **进度问询/督促的节奏** → 规则如下：

### 进度问询触发规则（重要）
对一件"进行中"的任务：
- **标记进行中当天**：不打扰。
- **次日起，到截止日前**：每天问一次进度（每天第一次打开 App 时出现；当天回复过/看过就不再重复，次日再问）。
- **截止日当天**：分两个时间点各问一次 —— **过了上午 11:30** 打开 App 问一次，**过了下午 17:00** 打开 App 再问一次（更紧）。
- 没有截止日期的任务：次日起，每天一次。

> ⚠️ **"App 内提醒"的限制（必须知道）**：以上提醒**只在你打开 App 时才会出现**，系统不会在 11:30 自己"叮"地推到手机上。那两个时间点的真实效果是"过了这个点之后你打开 App 会再问一次"。
> 如果以后希望"不打开 App 也能主动叮你"（像闹钟/微信消息那样），需要做第三阶段的外部推送（微信 Server酱 / 邮件）。本次不做。

### 技术上怎么实现这套节奏
- 用 `last_checkin_at`（时间戳）记录"上次问过/回复过"的时间。
- 简报接口计算"这条要不要问进度"：
  - 普通日：`last_checkin_at` 为空 或 其日期 < 今天 → 问。
  - 截止日当天：`(现在≥11:30 且 last_checkin_at 早于今天11:30)` 或 `(现在≥17:00 且 last_checkin_at 早于今天17:00)` → 问。
- 简报把某条进度问询展示出来时，就把它的 `last_checkin_at` 更新为"现在"（这样同一窗口内不重复问）；用户点回复时也更新。

---

## 七、顺手补一句"数据思维"（养习惯用）
简报顶部那行小数据，其实就是你该养成天天扫一眼的几个关键数：
- **完成数 / 进行中 / 逾期**：一眼看出今天负荷重不重、有没有积压。
- **逾期数**：这是"拖延信号"——如果某周逾期越来越多，说明要么任务排太满、要么优先级没排对。
- 以后可以再加一个**周完成率**（这周做完的 ÷ 这周该做的），用来判断自己执行节奏稳不稳。

这些不用你算，系统会自动显示，你只要每天扫一眼、对逾期那条多留心就行。
