# 企业微信委派任务审批与跟踪设计

## 目标与范围

单人版负责人通过 AI 秘书安排未来给一位同事下达任务。到点先提醒负责人，收到明确批准后发送；同事直接在应用里回复，AI 记录进展并同步负责人。维护姓名、别名和企业微信 UserID 的同事目录。第一阶段只支持应用单聊、文本和单接收人。

## 确认的流程

1. 输入“明天上午9点给张三下达任务：整理本周销售数据，下午5点前完成”。
2. 解析同事、内容、计划时间和截止时间。同名或缺时间时要求补充。
3. 到点发给负责人“待批准下达”，附任务短码。只有一个待审批任务时支持直接回复“同意”；多个时必须携带短码。
4. 支持“同意 1024 / 取消 1024 / 修改 1024 为……”。修改重新展示，必须再次同意。
5. 批准后向同事发送一次任务，并向负责人回执。
6. 同事回复“收到 / 完成 / 延期到…… / 普通进展”后，记录状态并同步负责人，停止当前无回复催办。
7. 未回复时：成功发送30分钟后第一次催办；第一次催办成功1小时后第二次催办。在第二次成功时同时向负责人报告仍未回复，并暂停该轮催办。
8. 每任务每天最多两次催办；这一轮最多两次，跨日不重新开始。收到回复后继续保留任务和进展，等待后续完成或延期回复；第一阶段不自动新建另一轮催办。
9. 审批消息成功送达30分钟未处理，只提醒负责人一次；成功送达24小时未批准则过期。计划时间已过去24小时且尚未发出审批请求的任务也直接过期。

## 数据与模块

- colleagues：owner_user_id、name、wecom_userid、aliases、active、时间戳。每负责人/UserID唯一，同名允许但必须明确选择。
- delegated_tasks：owner_user_id、colleague_id、content、scheduled_at、due_at、approval_code、approval_status、delivery_status、task_status、approval_requested_at、sent_at、next_followup_at、followup_count、daily_reminder_count、reminder_count_date、last_colleague_reply_at、paused_reason、version、时间戳。
- delegated_task_events：owner_user_id、task_id、actor_type、event_type、note、时间戳。用于审计；回调MsgId去重复用现有wecom_inbound_messages。
- delegation_outbox：owner_user_id、task_id、operation_key唯一、recipient_userid、content、kind、status、attempts、时间戳。所有审批、下达、催办、状态通知具有独立幂等键。

审批状态：scheduled / pending_approval / approved / cancelled / expired。
发送状态：not_sent / sending / sent / failed / uncertain。
执行状态：not_started / awaiting_reply / acknowledged / in_progress / completed / delayed / unresponsive / cancelled。

独立委派模块复用现有企业微信发送、入站去重、鉴权、APScheduler和DeepSeek客户端模式。业务服务统一状态转换；调度和回调调用同一服务。网页提供同事目录、委派创建、筛选、审批/取消/修改/完成及历史事件。

## 授权、匹配与隔离

批准和取消使用确定性命令，不让大模型猜测授权。短码在负责人范围内唯一，修改内容后分配新短码，旧码保存在approval_code_history且不再使用，避免旧回复批准新内容。
同事从该负责人的目录匹配，不要求把同事绑定成负责人账号。同事只能回复发给自己的任务，不能批准或读取负责人的其他任务。第一阶段不支持一个同事UserID关联多位负责人，遇到这种情况拒绝自动归属并提示确认。
普通回复只在唯一活跃任务或明确短码下归属；“没完成”“没有收到”不得匹配成完成或接收。
所有新表启用RLS。后端service role读改删显式过滤owner_user_id；定时任务按已绑定负责人分别扫描。关联同事和任务也验证归属。

## 并发、恢复与失败

条件更新version防止重复批准和并发调度。出站消息按唯一operation_key登记，只有一次能从pending领取为sending。
明确失败最多尝试两次；网络超时、发送后进程中断等无法判断对方是否收到时，标记uncertain、通知负责人并暂停，不盲目重发。
外部接口不提供无限期exactly-once保证，数据库幂等和企业微信短期防重组合降低重复。发送成功但本地落库失败时保持不确定状态，由负责人检查后处理。
有效同事回复取消未发送催办；发送前再次检查任务状态。携带正确短码的同事回复可作为收到任务的证据，恢复不确定发送状态；旧催办结果不得覆盖已回复状态。重启扫描未完成出站记录，sending超过5分钟转uncertain。
未完成任务可继续收到同事进展；延期只在时间解析明确时更新due_at，否则要求补充。

## 官方接口约束

2026-10-04核实企业微信官方文档：
- 应用消息POST /cgi-bin/message/send，touser为成员UserID、agentid为应用ID、text.content为正文。
- 检查errcode及invaliduser、unlicenseduser，接收人需在应用可见范围内。
- enable_duplicate_check和duplicate_check_interval提供短期消息防重；不替代本地幂等。
- 文本正文上限2048字节；任务内容限制1200字节，为短码、截止时间和提示留出空间，超长内容明确拒绝而不截断。
- 回调需快速响应，超时会重试；验签解密后通过现有后台任务处理，按MsgId去重。

来源：[发送应用消息](https://developer.work.weixin.qq.com/document/path/90236)、[接收消息与事件](https://developer.work.weixin.qq.com/document/path/90930)。

## 验收与上线

测试覆盖未批准不发送、重复批准、审批歧义、修改后重新批准、取消、过期、同事身份、否定回复、两次催办、跨日上限、回复取消、明确失败一次重试、超时不盲目重试、重启恢复和用户隔离。
先本地测试及前端构建，再执行新增数据库迁移，最后开启功能开关并用一名测试同事验证。线上发送默认关闭，需数据库升级和企业微信可见范围就绪后启用。
