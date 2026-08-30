# 当前任务

## 当前状态

2026-08-30 已完成并部署管理员删除队伍，正式计划继续使用唯一的 `.agents/plans/plan_competitions_teams.md`。原 `team-delete-20260830` 候选以 `help-delete-20260829` 为基线并明确排除用户搜索源码，随后覆盖了已上线搜索修复；现已改用合并固定标签 `team-user-search-20260830`，同时保留队伍删除和管理员全量用户搜索。部署前 PostgreSQL 17 快照已复核，纠正发布未运行 migrate、未重建 PostgreSQL/MinIO，六服务 healthy、重启 0，未携带认证调用真实 DELETE 或读取用户列表。

2026-08-30 已完成并重新部署管理员用户全量搜索与分页修复，正式计划为 `.agents/plans/plan_admin_user_search.md`。根因不是数据库只有 100 个，而是后续 `team-delete-20260830` Frontend/Backend 从旧基线构建，把用户 API 回退为只传 `page_size=100`。当前 `team-user-search-20260830` 以队伍删除镜像为基线合并 users 两个后端文件，并无缓存重建包含全部已上线功能的 Frontend；运行编译 chunk 已确认 `pageSize:20` 且传递 `page/search`。六服务 healthy、匿名管理员页/API 为 307/401；未使用管理员登录态、未读取用户列表、未调用业务写接口。

2026-08-29 已完成并部署管理员永久删除账号与用户自助注销，正式计划为 `.agents/plans/plan_account_deletion.md`。固定标签为 `account-deletion-20260829`，运行库为 `20260829_0015 (head)`；加密完整备份、从空环境恢复和 `0014 ↔ 0015` 往返均通过，生产验收未调用真实账号删除接口，账号清理 Outbox 仍为 0。详细结果已移入完成记录、变更记录与生产运维报告。

2026-08-29 已完成并部署真实管理员删除反馈答疑，正式计划继续使用唯一的 `.agents/plans/plan_feedback_help_requests.md`。固定标签为 `help-delete-20260829`，删除会物理移除工单并同步退出学生本人/公开读取，相关未读提醒标为已读并保留脱敏审计；运行验收未调用带认证的真实 DELETE，本轮无迁移。

本次答疑删除候选以已上线账号删除为基线，继续保留通知/作业删除、注册唯一约束修复、飞书 KaTeX 公式和账号删除能力；运行 OpenAPI 同时包含账号与答疑 DELETE，Alembic 保持 `20260829_0015 (head)`，最近成功知识库快照为 213 篇文档、1006 个媒体。

部署备份和临时 GPG 密钥环目前位于本机 `/tmp`，需要迁移到受控独立介质并分离保存；Docker socket 临时 `user:pnx:rw-` ACL 也需在完成所有 Docker 收尾后尝试撤销并复核。
