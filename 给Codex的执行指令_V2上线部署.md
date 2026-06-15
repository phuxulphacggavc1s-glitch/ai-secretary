# 给 Codex 的执行指令 · V2 闭环督办「上线部署」

> 执行者：Codex（在阿里云 ECS 服务器上操作）
> 目标：把已经开发完成、本地测试全过的 V2 闭环督办版本，安全部署到生产环境，并停掉旧的重复脚本，避免“同一件事提醒两遍”。
> 老板（Yi）是非技术背景，请每完成一个阶段就用一句大白话回报结果。

---

## 0. 背景（先读懂再动手）

当前生产环境 `/var/www/ai-secretary/` 上，企业微信提醒是靠**两个独立脚本 + crontab** 跑的：

- `notify.py` —— 每天早 8 点发晨报（cron）
- `remind.py` —— 每分钟检查、到点 @人提醒（cron），里面有 `PHONE_MAP`（邮箱→手机号）和企业微信 Webhook key

而新版代码（GitHub 仓库里）已经把这些能力**收进了后端主程序 `main.py` 的 APScheduler 定时器**：

- `push_morning_briefing` —— 每天 8:00 晨报
- `scan_followups` —— 每分钟扫描、到期通过企业微信督办提醒，并自动顺延下次跟进时间
- `escalate_s_level` —— 每天 20:00 对未完成的 S 级任务二次提醒
- 新增 `POST /tasks/{id}/reply` 接口：用户回复进展 → AI 判断状态（完成/在做/等回复/受阻）→ 决定下次何时再追

**核心冲突**：新旧两套功能重叠。新代码上线后如果不停掉旧 crontab，用户会被**重复提醒**。所以本次部署 = 上线新代码 + 停掉旧脚本（这就是“代码归位”）。

---

## 1. 安全红线（必须遵守）

- **不要**把任何密钥、Webhook key、`.env` 内容写进会被传阅的文件或回报消息里。
- **不要**改动 Supabase 的数据，除了执行本指令明确给出的迁移 SQL。
- 每个“破坏性操作”（停服务、改 crontab、删文件）前，先按本文档做好备份。
- 如果任何一步的“验证”没通过，**停下来回报**，不要继续往下做。

---

## 阶段 A：部署前的两处代码小修（在仓库里改，改完提交）

> 这两处不修就上线会有问题，必须先做。

### A1. 删掉会发进群的 TODO 残留行（必修）

文件：`backend/services/wecom.py`，函数 `build_reminder_markdown` 的返回字符串里有一行：

```
"# TODO: 与服务器 remind.py 的 PHONE_MAP 对齐"
```

这行会原样出现在发到企业微信群的提醒正文里。**把这一行从返回字符串中删除**（连同它前面多余的换行）。删除后，提醒正文应以 `[打开任务详情](链接)` 结尾。

### A2. @人 功能（请老板二选一，默认选「方案一」）

旧 `remind.py` 会用 `PHONE_MAP` @ 出具体的人。新代码的 `send_wecom()` 已支持 `mentioned_mobiles` 参数，但 `scan_followups` / `escalate_s_level` 调用时没传。

- **方案一（默认，先上线）**：本次不接 @人，督办提醒发到群里 + 带回复链接即可。理由：V2 的回复闭环是“点链接到应用里回复”，不依赖 @人；先把闭环跑通，@人作为下一轮优化。
- **方案二（要 @人）**：在 `services/secretary.py` 或 `followup.py` 里维护一个 `PHONE_MAP`（值从服务器旧 `remind.py` 里抄过来），在 `scan_followups`/`escalate_s_level` 调 `send_wecom()` 时把对应手机号传给 `mentioned_mobiles`。

> 等老板确认选哪个再动 A2。**没确认就只做 A1**。

### A3. 提交代码

```bash
# 在你本地/仓库工作区
git add backend/services/wecom.py
git commit -m "fix: 移除企业微信提醒正文中的TODO残留行，准备V2上线"
git push
```

验证：GitHub 上能看到这次提交。

---

## 阶段 B：数据库迁移（给 Supabase 加新字段）

新代码用到了一批新字段（`goal`、`success_criteria`、`related_person`、`next_action`、`next_follow_time`、`priority_level`），还有审计表 `task_events` 和 `users.wecom_webhook`。不迁移，新代码一跑就会因为“字段不存在”报错。

迁移脚本已在仓库：`supabase/upgrade_v2_closeloop.sql`，**幂等可重复执行**（用了 `if not exists`，重复跑不会坏数据）。

执行方式（二选一）：

- **推荐**：登录 Supabase 控制台 → SQL Editor → 新建查询 → 把 `supabase/upgrade_v2_closeloop.sql` 全文粘进去 → Run。
- 或用 psql 连接生产库执行该文件。

验证（在 SQL Editor 跑）：

```sql
select column_name from information_schema.columns
where table_name = 'tasks'
  and column_name in ('next_follow_time','priority_level','goal','success_criteria','related_person','next_action');
-- 应返回 6 行

select to_regclass('public.task_events');   -- 不为 null 即建表成功
```

> ⚠️ 迁移有改动数据库结构，执行前请在 Supabase 控制台确认当前项目是**生产项目**，不要选错。

---

## 阶段 C：在服务器配置企业微信环境变量

```bash
ssh root@<服务器IP>        # IP 用老板私下给你的，不要写进任何文档
cd /var/www/ai-secretary
```

C1. 先从旧脚本里取出当前在用的企业微信 Webhook 地址（不要打印到回报里）：

```bash
grep -o 'https://qyapi.weixin.qq.com[^"'"'"' ]*' remind.py | head -1
```

C2. 把它写进后端 `.env`（追加一行，注意别覆盖原文件）：

```bash
# 用上一步拿到的完整 webhook 地址替换 <粘贴webhook>
echo 'WECOM_WEBHOOK_URL=<粘贴webhook>' >> backend/.env
grep -c 'WECOM_WEBHOOK_URL' backend/.env   # 应输出 1
```

> 代码读取的变量名就是 `WECOM_WEBHOOK_URL`（见 `backend/config.py`）。多用户可在 Supabase 的 `users.wecom_webhook` 单独配置，缺省时回退到这个环境变量。

---

## 阶段 D：拉新代码 + 重装依赖 + 重启后端 + 重建前端

D1. 先备份当前可回退点：

```bash
cd /var/www/ai-secretary
git rev-parse HEAD > /root/ai-secretary-last-good-commit.txt   # 记下当前版本号，回退用
cat /root/ai-secretary-last-good-commit.txt
```

D2. 拉新代码、更新后端：

```bash
git pull

cd backend
source venv/bin/activate
pip install -r requirements.txt
systemctl restart ai-secretary
systemctl status ai-secretary --no-pager
curl http://127.0.0.1:8000/health      # 期望看到 {"status":"ok"} 之类
```

D3. 重建前端（本次有 UI 改版，必须重新 build）：

```bash
cd /var/www/ai-secretary/frontend
npm ci
npm run build
systemctl reload nginx
```

验证：

```bash
curl -i https://mede-in-ai.com/api/health     # 200 且返回健康状态
```

浏览器打开 `https://mede-in-ai.com`，应能看到**新版界面**（顶部深紫渐变问候卡、三个数据格子、逾期数字红色突出）。

---

## 阶段 E：停掉旧脚本（代码归位 / 防重复提醒）—— 关键一步

> 做完 D 并验证后端正常，才做这一步。顺序不能反，否则中间会出现“谁都不提醒”的空窗。

E1. 先看现在 crontab 里挂了什么：

```bash
crontab -l
```

应能看到类似 `notify.py` 和 `remind.py` 的两条（每分钟 / 每天8点）。

E2. 备份后注释掉这两条（不要删，留着可回退）：

```bash
crontab -l > /root/crontab-backup-$(date +%F).txt    # 备份
crontab -l | sed -e '/notify.py/s/^/#／／停用-改由后端定时器/' \
                 -e '/remind.py/s/^/#／／停用-改由后端定时器/' | crontab -
crontab -l      # 确认那两行前面已带 # 注释
```

> 如果上面的 sed 不好用，改为手动执行 `crontab -e`，在 `notify.py` 和 `remind.py` 两行最前面各加一个 `#`，保存退出。

E3. 验证新定时器在工作（看后端日志里有没有每分钟扫描 / 企业微信发送的记录）：

```bash
journalctl -u ai-secretary -n 50 --no-pager
```

---

## 阶段 F：上线后冒烟测试（验证“真追问”闭环跑通）

请在手机或电脑浏览器，用真实账号在 `https://mede-in-ai.com` 上走一遍：

1. 用一句话建一个**1~2 分钟后就要提醒**的任务，例如：“两分钟后提醒我给家莹回电话，目标是确认 C 电报价”。
2. 等到点，确认**企业微信群收到督办提醒**（正文不应再出现 `# TODO` 字样），且消息里有“打开任务详情”链接。
3. 点链接进应用，在任务卡片里**回复进展**，比如填“对方说下周给报价”。
4. 确认页面提示 AI 判断的新状态（应为“等回复”之类），任务卡片上出现**“下次跟进”时间**。
5. 再建一个 S 级任务、设一个已过去的时间，确认它进入“最该先干/逾期”区域。
6. 把第 1 个任务回复“已经搞定了”，确认状态变“已完成”、不再继续追。

全部通过 = 闭环上线成功。

---

## 回退方案（万一出问题）

- **后端起不来 / 接口报错**：
  ```bash
  cd /var/www/ai-secretary
  git checkout $(cat /root/ai-secretary-last-good-commit.txt)
  cd backend && source venv/bin/activate && pip install -r requirements.txt
  systemctl restart ai-secretary
  ```
- **想恢复旧的提醒脚本**：
  ```bash
  crontab /root/crontab-backup-<日期>.txt
  ```
- 数据库迁移是“只加不删”的，无需回退；即使回退代码，新加的字段也不会影响旧代码。

---

## 验收清单（全部打勾才算完成）

- [ ] A1 已删除 wecom.py 里的 TODO 残留行并提交
- [ ] （如老板选方案二）A2 @人已接好
- [ ] B 迁移已执行，6 个新字段 + task_events 表都在
- [ ] C 后端 .env 里有 WECOM_WEBHOOK_URL
- [ ] D 后端重启正常、`/api/health` 通、前端是新界面
- [ ] E 旧 crontab 的 notify.py / remind.py 已注释停用
- [ ] F 冒烟测试 6 步全过，提醒不重复、能追问、回复后能判断状态

---

## 给老板的一句话说明

这次上线做三件事：① 把“会自己追问、不完成不结束”的新版正式发到线上；② 给数据库补上新版需要的字段；③ 把旧的重复提醒脚本关掉，避免一件事提醒你两遍。做完你在手机上建个两分钟后的任务，就能在企业微信里看到它真的来追你了。
