# 企业微信委派任务实施计划

**目标：** 到点提醒负责人批准后下达同事任务，并按30分钟、再1小时最多催办两次。
**架构：** 独立委派模块，复用应用消息和现有回调。持久化出站操作与条件更新保证重复执行不重复发送。
**技术：** FastAPI、Supabase/PostgreSQL、APScheduler、React、Vite、DeepSeek。

## 执行任务

- [x] 1. 在 backend/tests/test_delegation_policy.py 写确定性审批、否定回复、催办时间、跨日和过期测试；运行pytest确认缺少模块；新增 services/delegation_policy.py 并通过测试。
- [x] 2. 在 backend/tests/test_delegation.py 写内存数据库替身的服务测试：创建、重复批准、修改、归属隔离、回复取消、两次催办、失败和恢复。新增 services/delegation.py 和 supabase/upgrade_v7_delegation.sql；显式owner过滤，关联约束和RLS。
- [x] 3. 在 backend/tests/test_delegation_delivery.py 写成功、invaliduser、明确错误、网络超时测试；新增委派专用发送结果，保留现有send_app_text兼容。
- [x] 4. 新增 services/delegation_parser.py、routers/delegation.py；测试时间明确性、同事匹配、API鉴权、未知成员和状态错误。注册main路由与每分钟调度，新增WECOM_DELEGATION_ENABLED开关。
- [x] 5. 测试企业微信负责人命令先于普通待办解析、同事回调不要求负责人绑定、重复消息不再处理；接入wecom_app。
- [x] 6. 新增frontend/src/pages/Delegations.jsx，提供同事目录、创建、筛选、审批、取消、修改和事件；新增api和路由，在Home加入口。375px布局检查，npm run build。
- [x] 7. 运行完整pytest与前端构建；检查git diff、用户过滤、敏感数据、迁移。文档记录上线所需迁移和开关，保持真实发送关闭。
- [x] 8. 提交本功能文件，提供变更和验证结果；数据库与生产部署作为明确的下一步骤。

## 核心接口约定

POST /delegation/parse：raw_input，返回colleague_id、content、scheduled_at、due_at。
GET/POST /delegation/colleagues、PATCH /delegation/colleagues/{id}：同事目录。
GET/POST /delegation/tasks：委派列表及创建。
POST /delegation/tasks/{id}/action：approve/cancel/modify/complete/reopen及可选content。
GET /delegation/tasks/{id}/events：审计时间线。
业务错误返回中文400，关闭发送时批准返回409，数据库未升级返回503，关闭开关时读目录允许、真实发送暂停。

## 验证命令

在backend运行 .venv/Scripts/python.exe -m pytest tests -q。
在frontend运行 npm run build。
所有自动测试隔离数据库、AI与企业微信外网，不能向真实同事发送测试消息。

## 最终验证

2026-10-04：后台115项测试通过；前端生产构建通过；桌面1280x900和手机375x812浏览器验收通过，涵盖审批、事件、同事添加及停用、结构化校验错误和任务创建。生产迁移及真实联调尚未执行，上线顺序见 docs/wecom-delegation-rollout.md。
