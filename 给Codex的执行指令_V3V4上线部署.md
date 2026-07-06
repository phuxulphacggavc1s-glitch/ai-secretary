# 给 Codex 的执行指令 · V3/V4「对话流 + 企业微信双向」上线部署

> 执行者：Codex（在阿里云 ECS 服务器上操作）
> 目标：把已开发完成、本地测试全过的 V3/V4 版本安全部署到生产环境 https://mede-in-ai.com
> 老板（Yi）是非技术背景，每完成一个阶段用一句大白话回报结果。

---

## 0. 背景（先读懂再动手）

本次要上线的内容**已经全部开发完成并验证**（后端 34 个 pytest 全过、前端 vite build 成功），你的任务**只是部署，不是开发**：

**V3：**
- 首页改为秘书对话流（新组件 `SecretaryChat.jsx`、`SecretaryAvatar.jsx`）
- 新接口：`GET /secretary/opening`、`POST /secretary/chat`、`GET /secretary/messages`、`GET /secretary/messages/search`
- 记忆层：`services/memory.py`（每周日 21:00 提炼画像 + 首次懒加载）
- 删除了任务的 goal / success_criteria / related_person 三个字段（前后端已同步删除）

**V4：**
- 企业微信自建应用双向对话：`routers/wecom.py`、`services/wecom_app.py`、`services/wecom_crypto.py`
- 随聊随记忆：`user_memory` 表新增 `facts` 字段
- 秘书人设「小e」：`services/persona.py`
- 新增 Python 依赖：`pycryptodome`（已写进 `backend/requirements.txt`）

**数据库迁移脚本**：`supabase/upgrade_v3_chat_memory.sql`（删三列 + 建 `secretary_messages`、`user_memory` 两张表）

---

## 1. 安全红线（必须遵守）

1. **禁止修改任何业务代码、禁止重构、禁止"顺手优化"**。代码已测试通过，你发现任何觉得"不对"的地方，先停下回报，不许自己改。
2. 不把密钥、`.env` 内容写进回报消息或任何文件。
3. 新增的 6 个 `WECOM_*` 环境变量的**值必须由老板提供**，你不许编造占位值填进去（配错了回调验证会失败且难排查）。
4. 每步的"验证"不通过就停下回报，不要硬往下走。
5. 破坏性操作前先备份（本指令已写明备份点）。
6. 如确需改代码（老板批准后），遵守 AGENTS.md 数据访问铁律：任何 tasks/daily_reports/users/user_memory/secretary_messages 查询必须带 `user_id` 过滤。

---

## 阶段 A：确认代码已入库（前置，可能由老板完成）

新代码在老板本地电脑上。老板需要先在本地执行（或授权你在本地仓库执行）：

```bash
git add -A
git commit -m "V3/V4: 对话流+记忆层+企业微信双向+人设小e+删冗余字段"
git push
```

**验证**：GitHub 仓库最新 commit 包含 `backend/services/secretary_chat.py` 和 `backend/routers/wecom.py`。没有就停下等老板 push。

## 阶段 B：服务器更新后端

```bash
# 备份点：记下当前 commit，用于回滚
cd /var/www/ai-secretary && git log -1 --format=%H > /root/rollback_commit_v2.txt && cat /root/rollback_commit_v2.txt

git pull
cd backend && source venv/bin/activate && pip install -r requirements.txt
systemctl restart ai-secretary
sleep 3
systemctl status ai-secretary --no-pager | head -5
curl -s http://127.0.0.1:8000/health
journalctl -u ai-secretary -n 30 --no-pager
```

**验证**：health 返回 `{"status":"ok"}`，journalctl 最近日志无 Traceback。
**回报话术**：「新后端已上线，健康检查正常。」

## 阶段 C：数据库迁移（老板在网页操作，你等确认）

这步你干不了：老板打开 Supabase 后台 → SQL Editor → 粘贴运行仓库里的
`supabase/upgrade_v3_chat_memory.sql` → 显示 Success。

**你要做的**：把 SQL 文件内容原样发给老板，等他回复"跑完了"再进入阶段 D。
**注意顺序**：必须在阶段 B 之后执行（老后端还在写那三个旧字段，先删列会报错）。

## 阶段 D：重建前端

```bash
cd /var/www/ai-secretary/frontend
npm ci && npm run build
ls -la dist/assets | head -5
```

**验证**：dist/assets 里的 js/css 文件时间戳是刚刚。
**回报话术**：「新界面已发布，请手机打开网站强制刷新看效果。」

## 阶段 E：线上验收（和老板一起过一遍）

1. 打开 https://mede-in-ai.com 强制刷新 → 首页顶部出现对话卡片，秘书「小e」主动说话（首次会慢几秒，在生成画像）
2. 输入「明天下午3点提醒我给供应商打款」→ 弹确认框，字段只有：内容、分类、优先级、时间
3. 输入「今天先做什么」→ 得到对话回复而不是弹框
4. 聊天卡片右上角放大镜 → 搜「打款」→ 能搜到刚才的记录
5. 秘书头像会眨眼；发消息时头像眼睛转圈

全过 → 回报「V3 验收通过」。任何一条不过 → 停下，把浏览器 F12 Console 红字和 `journalctl -u ai-secretary -n 50` 贴给老板。

## 阶段 F：企业微信双向对话（人机配合）

**老板做**（照《企业微信双向对话_配置手册.md》）：企业微信后台建自建应用、拿 6 个值、配可信 IP。这是网页人工操作，你不许代填任何值。

**你做**：拿到老板给的 6 个真实值后：

```bash
# 追加到 /var/www/ai-secretary/backend/.env（值用老板提供的，一个都不许编）
systemctl restart ai-secretary
journalctl -u ai-secretary -n 10 --no-pager
```

然后告诉老板「可以回企业微信后台点保存了」。他点保存 → 显示成功 → 让他在企业微信给应用发「在吗」测试。

**验证**：老板收到小e的回复。
**排错线索**：保存失败查 Token/AESKey 是否有多余空格；收不到回复查 journalctl 里 `wecom` 相关报错，60020 = 可信 IP 没配对。

## 回滚方案（出大问题时）

```bash
cd /var/www/ai-secretary
git checkout $(cat /root/rollback_commit_v2.txt)
cd backend && source venv/bin/activate && pip install -r requirements.txt
systemctl restart ai-secretary
cd ../frontend && npm ci && npm run build
```

数据库迁移不用回滚（新表不影响旧代码；三个被删的列旧代码只在保存时用，回滚代码后如需恢复列，告诉老板找 AI 秘书助手处理）。
