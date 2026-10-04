# 企业微信委派任务上线说明

核实日期：2026-10-04。当前为本地实现完成，生产数据库升级和真实企业微信联调尚未执行。

## 上线顺序

1. 保留服务器现有配置和版本记录，暂时保持 WECOM_DELEGATION_ENABLED=false。
2. 在正确的 Supabase 项目的 SQL Editor 中执行 supabase/upgrade_v7_delegation.sql 全文。脚本以事务新增四张表、索引、关联约束、RLS和权限，不修改现有个人任务表。Supabase 官方说明支持 Dashboard SQL Editor 建表，并要求 SQL 创建的表显式开启 RLS：[Tables and data](https://supabase.com/docs/guides/database/tables)。
3. 执行下面的只读查询，确认返回四张表且 rowsecurity 全部为 true：

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename in ('colleagues', 'delegated_tasks', 'delegated_task_events', 'delegation_outbox')
order by tablename;

select tablename, policyname, cmd, roles
from pg_policies
where schemaname = 'public'
  and tablename in ('colleagues', 'delegated_tasks', 'delegated_task_events', 'delegation_outbox')
order by tablename, policyname;
```

前面三张表应仅有 authenticated 的本人只读策略；出站队列表不向客户端开放，不需要 authenticated 策略。四表写入均通过后台服务，后台查询同时显式过滤负责人身份。

4. 部署本次后台和前端代码，先保持发送关闭，登录后检查“委派任务”及“同事目录”页面。
5. 确认负责人现有企业微信账号映射正确；添加一名知情测试同事，使用其准确 UserID。接收人需要在应用可见范围内：[企业微信发送应用消息](https://developer.work.weixin.qq.com/document/path/90236)。不要把同事绑定为负责人。
6. 只在数据库、页面、现有企业微信回调都正常后，在后台配置加入 WECOM_DELEGATION_ENABLED=true 并重启服务。不要开启第二个后台进程运行同一调度器。
7. 按下面的验收流程完成真实联调，再扩大使用。

## 真实联调

- 创建几分钟后下达的测试任务；确认同事在你批准前没有收到任务。
- 到点后负责人收到“待批准下达”；直接回复“同意 短码”，确认同事只收到一次任务。
- 同事回复“短码 收到”，负责人收到进展回执；确认30分钟后不再催办。
- 另建知情同事的无回复测试任务，确认第一次在下达30分钟后，第二次在第一次成功1小时后；第二次后向负责人报告并暂停，跨日也不重启该轮。
- 修改待审批任务后，旧短码的批准不能生效；必须以新短码明确批准。
- 完成后检查任务记录；真实联调不要把测试任务发给未告知的同事。

任务时间统一按北京时间显示和输入。收到进展或延期回复后停止这一轮“无回复”催办；任务仍可继续接收后续进展和完成回复。第一阶段没有自动到期再催、新一轮催办、多人下达或群聊功能。

## 关闭与异常处理

关闭 WECOM_DELEGATION_ENABLED 后，委派调度和出站队列暂停，网页保留目录及记录。恢复开关前先查看过期审批和发送不确定任务；重新开启可能处理仍有效的待发送记录。

发送结果不确定时不盲目重发，先联系同事核实。若同事已经收到，可回复携带任务短码的“收到/完成”，系统将恢复相应状态。明确失败最多两次尝试。旧发送结果不能覆盖同事已经回复的状态。

首次发布失败时可关掉该开关并恢复原代码；保留新增表和审计记录，不删除数据。此功能的关闭不影响已有个人任务提醒。

## 本地验证记录

后端完整测试、前端构建、桌面1280x900和手机375x812浏览器流程均通过。自动测试使用替身数据库、模拟AI和模拟发送，没有发出真实企业微信任务。生产迁移及真实消息联调不能由本地测试替代。

后台验证：在 backend 运行 .venv/Scripts/python.exe -m pytest tests -q。
前端验证：在 frontend 运行 npm run build。
浏览器验证：先在5175启动前端，安装Playwright并提供Chrome，再运行 node tests/delegations.smoke.cjs；测试会模拟登录及委派接口，不读取真实业务数据。

现有Python 3.14环境的OpenAI/Pydantic兼容提示仍存在，尚未在本次功能中更换运行环境。
