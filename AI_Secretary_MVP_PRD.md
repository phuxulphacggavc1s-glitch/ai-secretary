
# AI Secretary MVP 开发文档

> **核心原则：最快上线 > 功能最全**
> 目标：4周内上线可用版本，先跑通核心链路，再迭代。

---

## 项目定位

一个支持手机 + 电脑同步的 AI 生活/工作秘书系统。

用户只需要说一句话：
- "明天下午提醒我给客户报价"
- "月底提醒我交房租"
- "记一下直播优化方案"

系统自动完成：时间解析 → 分类 → 保存 → 提醒 → AI总结

---

## MVP 最小上线范围（优先级排序）

> ⚠️ 以下功能按"必须上线"排序。括号内是建议阶段。

| 优先级 | 功能 | 说明 |
|--------|------|------|
| P0 必须 | 文字输入 + AI解析 | 核心体验，没有这个就没有产品 |
| P0 必须 | 待办列表展示 | 能看到才有用 |
| P0 必须 | 完成/删除任务 | 基本操作 |
| P0 必须 | 登录（手机号或邮箱） | 数据不能丢 |
| P1 重要 | 提醒（先用邮件/短信，不用Push） | Push太复杂，先跑通提醒逻辑 |
| P1 重要 | AI 每日总结 | 差异化卖点 |
| P2 以后 | 语音输入 | 后续迭代 |
| P2 以后 | 微信登录 | 后续迭代 |
| P2 以后 | 手机原生Push通知 | 后续迭代 |

---

## 技术选型建议（为了最快上线）

> ⚠️ 原方案用 Flutter，开发调试周期长。建议改用以下方案，可节省2-3周。

### 推荐方案：Web优先

```
前端：React（Web网页，手机浏览器也能用）
后端：Python FastAPI
数据库：Supabase（自带登录系统，省去自己写Auth）
AI：DeepSeek API（便宜，中文理解好）
提醒：邮件用 Resend / 短信用阿里云短信（比Firebase Push简单10倍）
部署：前端 Vercel / 后端 Railway 或 Render
```

### 如果坚持Flutter方案

```
前端：Flutter（Web + iOS + Android）
后端：Python FastAPI
数据库：Supabase
AI：DeepSeek API
提醒：MVP阶段先用邮件，Push留到后期
部署：后端 Railway，前端 Vercel（Flutter Web）
```

---

## MVP 功能详细设计

### 1. 登录系统

支持：
- 邮箱 + 密码（MVP首选，最简单）
- 手机号（需要短信服务，略复杂）
- 微信登录（后期再加）

**直接用 Supabase Auth，不要自己写，省1周时间。**

---

### 2. 快速记录（核心功能）

支持：
- 文字输入（MVP必须）
- 语音输入（后期）

**用户体验流程：**
```
用户输入 → AI解析 → 展示解析结果 → 用户确认/修改 → 保存
```

> ⚠️ 重要：加一步"用户确认"，AI解析不一定100%准确，用户看到解析结果后可以手动改，体验更好，也不会因为AI出错让用户愤怒。

**AI 解析逻辑：**

输入：
```
"明天下午提醒我给客户报价"
```

输出：
```json
{
  "content": "给客户报价",
  "category": "工作",
  "remind_time": "2026-06-03 15:00",
  "is_time_clear": true,
  "original_time_text": "明天下午"
}
```

**is_time_clear 字段说明：**
- `true`：AI能明确解析出时间，直接展示
- `false`：时间模糊（如"过两天"），前端弹出时间选择器让用户手动选

---

### 3. 提醒系统

**MVP阶段只做邮件提醒，不做手机Push（Push太复杂）**

提醒触发逻辑：
- 后端每分钟扫描一次数据库
- 找到 `remind_time <= 当前时间` 且 `status = pending` 且 `reminded = false` 的任务
- 发送邮件提醒
- 标记 `reminded = true`

邮件内容示例：
```
主题：【AI秘书提醒】给客户报价
内容：你设置了一个提醒：给客户报价
      提醒时间：2026-06-03 15:00
```

> 短信提醒可以用阿里云短信，注册后接入很快，备选方案。

---

### 4. 待办列表

分类（导航栏tab）：
- 全部 / 工作 / 生活 / 灵感 / 财务 / 已完成

每条任务显示：
- 任务内容
- 分类标签
- 提醒时间（如果有）
- 完成/删除按钮

支持：
- 搜索
- 修改
- 删除
- 标记完成

---

### 5. AI 每日总结

每天晚上 21:00 自动生成，发到用户邮箱或在App内展示。

内容：
- 今日完成事项（几条）
- 未完成事项（几条，需关注）
- 明日有提醒的任务

---

## 数据库设计

### users 表

```sql
create table users (
  id uuid primary key default gen_random_uuid(),
  email text unique,
  phone text,
  nickname text,
  timezone text default 'Asia/Shanghai',
  created_at timestamp with time zone default now()
);
```

### tasks 表

```sql
create table tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  content text not null,
  category text default '未分类',
  remind_time timestamp with time zone,
  status text default 'pending',       -- pending / done
  reminded boolean default false,      -- 是否已发送提醒
  priority int default 1,              -- 1低 2中 3高
  ai_summary text,                     -- AI对这条任务的补充说明
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- 加索引，提醒扫描用
create index idx_tasks_remind_time on tasks(remind_time, status, reminded);
create index idx_tasks_user_id on tasks(user_id);
```

### daily_reports 表

```sql
create table daily_reports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  report_date date not null,
  content text,
  created_at timestamp with time zone default now(),
  unique(user_id, report_date)
);
```

---

## API 设计

### 认证方式

所有接口（除登录外）需要在请求头带 token：
```
Authorization: Bearer <token>
```

---

### 创建任务

`POST /tasks`

请求：
```json
{
  "raw_input": "明天下午提醒我给客户报价"
}
```

返回：
```json
{
  "success": true,
  "task": {
    "id": "abc-123",
    "content": "给客户报价",
    "category": "工作",
    "remind_time": "2026-06-03 15:00:00",
    "is_time_clear": true,
    "status": "pending"
  }
}
```

> 如果 `is_time_clear = false`，前端弹出时间选择器，用户选完再调"确认创建"接口。

---

### 获取任务列表

`GET /tasks?category=工作&status=pending&page=1&page_size=20`

返回：
```json
{
  "success": true,
  "total": 12,
  "tasks": [
    {
      "id": "abc-123",
      "content": "给客户报价",
      "category": "工作",
      "remind_time": "2026-06-03 15:00:00",
      "status": "pending"
    }
  ]
}
```

---

### 完成任务

`PATCH /tasks/{task_id}`

请求：
```json
{
  "status": "done"
}
```

返回：
```json
{
  "success": true
}
```

---

### 删除任务

`DELETE /tasks/{task_id}`

返回：
```json
{
  "success": true
}
```

---

### 获取每日总结

`GET /reports/daily?date=2026-06-02`

返回：
```json
{
  "success": true,
  "report": {
    "date": "2026-06-02",
    "done_count": 3,
    "pending_count": 2,
    "content": "今日完成3项任务，还有2项未完成，明日有1个提醒。"
  }
}
```

---

## AI Prompt 设计

### 任务解析 Prompt

```
你是一个智能秘书助手，专门帮用户解析待办事项。

【任务】
从用户输入中提取：
1. 任务内容（去掉时间词和"提醒"等词）
2. 分类（从以下选择：工作 / 生活 / 灵感 / 财务 / 学习 / 其他）
3. 提醒时间（转换为 ISO 格式，用户所在时区：Asia/Shanghai）
4. 时间是否明确（is_time_clear）

【当前时间】
{current_datetime}（Asia/Shanghai）

【分类规则】
- 工作：客户、报价、发货、直播、抖音、淘宝、小红书、店铺、供应商
- 财务：房租、账单、还款、工资、打款、收款
- 生活：买菜、看病、取快递、家里、约饭
- 灵感：想法、方案、优化思路
- 学习：看书、学习、课程

【时间解析规则】
- "明天下午" → 明天 15:00
- "后天上午" → 后天 09:00
- "月底" → 当月最后一天 09:00
- "周五" → 下个周五 09:00
- "过几天" / "最近" → is_time_clear = false，remind_time 留空
- 没有提到时间 → is_time_clear = false，remind_time 留空

【返回格式】（只返回JSON，不要其他文字）
{
  "content": "任务内容",
  "category": "分类",
  "remind_time": "2026-06-03T15:00:00+08:00 或 null",
  "is_time_clear": true或false,
  "original_time_text": "用户原始时间描述"
}

【用户输入】
{user_input}
```

---

### 每日总结 Prompt

```
你是用户的AI秘书，帮用户生成今天的工作总结。

【今日数据】
完成任务：{done_tasks}
未完成任务：{pending_tasks}
明日提醒：{tomorrow_reminders}

【要求】
- 用轻松、鼓励的语气
- 100字以内
- 重点提示未完成中最紧急的事项
- 如果今天全部完成，给用户鼓励

直接输出总结文字，不要加标题。
```

---

## 开发顺序（按最快上线排列）

### 第一周：跑通核心链路
1. 搭建后端（FastAPI + Supabase）
2. 接入 DeepSeek API，测试任务解析
3. 实现创建任务、获取列表、完成/删除接口
4. 搭建前端基础页面（首页输入 + 任务列表）
5. 接入 Supabase Auth 登录

### 第二周：完整可用
6. 提醒系统（定时扫描 + 邮件发送）
7. 前端任务分类tab、搜索、修改
8. 部署上线（Vercel + Railway）
9. 测试主要流程，修bug

### 第三周：差异化功能
10. AI 每日总结生成 + 展示
11. 每日总结邮件推送
12. 页面细节优化、加载状态、错误提示

### 第四周：收尾
13. 用户测试，收集反馈
14. 修复主要问题
15. 正式对外开放

---

## 错误处理（不能跳过）

| 场景 | 处理方式 |
|------|---------|
| AI解析失败 | 提示"解析失败，请手动填写"，显示表单让用户填 |
| 时间不明确 | 弹出日期时间选择器 |
| 网络超时 | 提示重试，不要白屏 |
| 登录过期 | 跳转登录页，不要报错 |
| 任务创建失败 | 提示"创建失败，请重试" |

---

## MVP 验收标准

> 上线了不等于成功，要达到以下标准才算MVP跑通：

- [ ] 用户能在10秒内输入一句话并看到解析结果
- [ ] 提醒时间到了，邮件能准时到达
- [ ] 任务列表加载不超过2秒
- [ ] 10个真实用户连续使用3天，无严重Bug
- [ ] AI解析准确率 > 80%（时间 + 分类都对算准确）

---

## 后期迭代方向（MVP之后再做）

- 语音输入
- 微信登录
- 手机原生Push通知
- AI 主动提醒（根据历史习惯）
- AI 工作规划 / 周报
- AI 灵感整理
- AI 个人记忆系统
- 和抖音/淘宝/小红书数据打通
