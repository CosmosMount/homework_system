# 当前任务

## 当前状态

2026-08-31 已完成仓库 MIT License 与分步提交治理：用户确认版权主体为 `HKUST(GZ) RoboMaster PNX Team`，根目录新增标准 MIT `LICENSE`，README 增加许可证入口；既有改动已拆为持久登录、问卷范围邮件、管理端删除可见性、知识库目录文件与响应式媒体、项目记录五个提交，许可证及治理记录作为第六个独立提交。本轮无业务、API、数据库或部署变化，不涉及数据迁移。

2026-08-31 已修复并部署“成功同步后目录文件仍不可下载、真实图片序列未并排”。生产只读证据确认 17:04 最新同步为 `succeeded/217/1057`，但 16 个 `file` 节点全部无资源；同一令牌的 `medias` 端点被飞书拒绝而 `files` 端点可读取，因此目录独立文件现显式使用 Drive `files`，正文媒体继续使用 `medias`。前端画廊现跨过空段落并展开纯媒体容器，可见内容仍终止分组。后端定向 31 项、完整 322 项、Ruff/格式、受影响 4 文件严格 Mypy；前端定向 2 文件/17 项、完整 25 文件/121 项、ESLint、严格 TypeScript、主机与镜像内生产构建全部通过。固定标签 `knowledge-file-gallery-fix-20260831` 已两阶段上线，Backend/Worker 为 `sha256:2b1c9079e5dc9f2079acdb063cd7a0e2d88c52c68be045a346f180054d692141`，Frontend 为 `sha256:a5ad5927756819aeedbe4931b4921a60831d11fcaced9ea9530ded90f04446d3`；六服务 healthy、重启 0，Alembic 保持 `20260831_0018 (head)`，PostgreSQL/MinIO 未重建。新加密备份 `pnx-backup-20260831T102419Z-daily` 完整验证通过。当前 16 个文件仍属于旧代码生成的成功快照，须真实管理员在新版本上再次手动同步后验收资源关联。

2026-08-31 已按用户截图完成并部署知识库默认根层视图热修：无有效 `?doc` 时不再自动读取第一篇文档，只展示根层条目且所有根文件夹保持收起；显式进入文档后只展开当前祖先链，浏览器历史退出文档后清空正文并恢复根层收起视图。知识库定向 2 文件/16 项、完整前端 25 文件/120 项 Vitest、ESLint、严格 TypeScript、主机与镜像内 Next.js 生产构建全部通过。固定标签为 `knowledge-root-view-20260831`，Frontend 镜像 `sha256:9a76b96ca85d67a0364cf939fd5528bbfb42b6d4633d143b75a61ad2443b811f` 已仅替换 Frontend/Nginx；Backend 新标签只是现有 `sha256:77f58286fe7434a970d9656f8a5801ce470af628745e992f513dffb69cb2796f` 的别名，Backend/Worker、PostgreSQL、MinIO 容器 ID 保持不变。六服务 healthy、重启 0，Alembic 保持 `20260831_0018 (head)`，知识库页面/API/虚假资源下载匿名为 307/401/401，发布窗口日志无异常。本热修无迁移、无飞书同步或业务写入。

2026-08-31 已完成并部署培训知识库“目录根层默认、当前文档路径跟随与旧路径收缩、目录独立文件受保护下载、图片当前页浮层及连续图片自适应并排”，正式计划继续使用唯一的 `.agents/plans/plan_feishu_knowledge_sync.md`。固定标签为 `knowledge-directory-media-20260831`，Backend/Worker 镜像 `sha256:77f58286fe7434a970d9656f8a5801ce470af628745e992f513dffb69cb2796f`、Frontend 镜像 `sha256:f523e338e44c0788fb61c1f8378f73940f1bdc00d907a8a1ef770dfbe3883e65` 已两阶段上线；生产 Alembic 为 `20260831_0018 (head)`，112 个历史目录文件已转为 `file:file` 且等待下次成功同步关联资源。六服务 healthy、重启 0，PostgreSQL/MinIO 未重建，迁移前后全表行数哈希一致，运行产物、匿名权限和日志验收通过。加密同点备份 `pnx-backup-20260831T073443Z-daily` 已完整校验；本次未触发飞书同步，仍须真实管理员在 `/admin/knowledge` 手动成功同步一次。

2026-08-31 已完成并部署“通知/作业删除后退出常规管理页面，并允许手工归档通知继续删除”，正式计划继续使用唯一的 `.agents/plans/plan_admin_content_removal.md`。固定标签为 `admin-content-visibility-20260831`，Backend/Worker 镜像 `sha256:589290276cd2ab01b283dc227e3effffe9548df4235a8965fa2c2f3c97145772`、Frontend 镜像 `sha256:8d5ea4a60f04cbf7be44b22b438a1a5c60aef40a0ebf37cf6786ceec2fca116b` 已两阶段上线；生产 Alembic 为 `20260831_0017 (head)`，两列与两项检查约束有效。六服务 healthy、重启 0，PostgreSQL/MinIO 未重建；未调用真实业务 DELETE，运行 OpenAPI、匿名权限、业务聚合和日志验收通过。Docker socket 临时 ACL 仍需部署方交互式 sudo 撤销。

2026-08-30 已完成并部署“问卷按手动成员、技术组或全部激活学生发送邮件”，正式计划继续使用唯一的 `.agents/plans/plan_student_teams_auto_assignment_intentions.md`。固定标签为 `questionnaire-email-scopes-20260830`，Backend/Worker 镜像 `sha256:af1d520399115abad815f84100c5e34c961a29003087d3088eccf54eb7106cbd`、Frontend 镜像 `sha256:8d4ba40349833834a713a6af4b5ea90c572343dd26e6ab58a9d78aeef75e75fe` 已两阶段上线；六服务 healthy、重启 0，运行 OpenAPI 为 115 条路径且包含 `manual/direction/all`。未运行 migrate，PostgreSQL/MinIO 未重建，部署前后用户、问卷五表、状态、知识库和 Outbox 聚合一致；匿名邮件 POST 为 401，未触发真实 SMTP、飞书同步或其他业务写入，部署窗口日志无异常。

2026-08-30 已完成并部署已关闭问卷重新开启，正式计划继续使用唯一的 `.agents/plans/plan_student_teams_auto_assignment_intentions.md`。固定标签为 `questionnaire-reopen-20260830`，Backend/Worker 镜像 `sha256:f613c227e74b67b8c3f1257cb7dca2b2d80b2273168bad13df80ba923331e016`、Frontend 镜像 `sha256:35bed3d14aef08f213df7b14510c2623af5944d3639a3e2788175944a6d7bb75` 已两阶段上线；六服务 healthy、重启 0，未运行 migrate，PostgreSQL/MinIO 未重建。部署前后用户、问卷五表、问卷状态、知识库和 Outbox 聚合一致；验收未调用真实问卷状态接口、未触发飞书同步或其他业务写入，部署窗口日志无异常。

2026-08-30 已完成并部署学生知识库飞书原文入口关闭，正式计划继续使用唯一的 `.agents/plans/plan_feishu_knowledge_sync.md`。真实学生与管理员学生视图不再显示标题原文、未映射飞书文档或附件失败回退链接；当前快照内部文档跳转和 `/api/v1/knowledge/assets/{id}/content` 附件下载保持可用，真实管理员普通视图保留排障入口。部署时同时修复 `/knowledge` 匿名登录回跳竞速；最终知识库定向 2 文件/12 项、完整前端 25 文件/111 项 Vitest、ESLint、严格 TypeScript 和镜像内生产构建通过。该阶段 Frontend 固定标签为 `knowledge-student-links-20260830`、镜像为 `sha256:a67211cda8d65afeb34bbdde630609cd7c50aff974cc99ddbb9f6852ac26c652`；未运行 migrate，未替换 Backend/Worker/PostgreSQL/MinIO，未触发飞书同步或业务写入。

2026-08-30 已完成持久登录部署后跳转回归热修复，正式计划为 `.agents/plans/plan_persistent_login.md`。Next.js 服务端 API 现同时向内部 Backend 转发 Cookie 与 Nginx 已覆盖的单值来源 IP，缺失时不伪造；Frontend/Nginx 已定向替换为 `persistent-login-ip-forwarding-20260830`，未运行 migrate、未替换 Backend/Worker、未重建 PostgreSQL/MinIO。六服务 healthy、重启 0；回归期间已撤销的持久 Session 需用户重新勾选登录一次。

2026-08-30 已完成并部署管理员删除队伍，正式计划继续使用唯一的 `.agents/plans/plan_competitions_teams.md`。原 `team-delete-20260830` 候选以 `help-delete-20260829` 为基线并明确排除用户搜索源码，随后覆盖了已上线搜索修复；现已改用合并固定标签 `team-user-search-20260830`，同时保留队伍删除和管理员全量用户搜索。部署前 PostgreSQL 17 快照已复核，纠正发布未运行 migrate、未重建 PostgreSQL/MinIO，六服务 healthy、重启 0，未携带认证调用真实 DELETE 或读取用户列表。

2026-08-30 已完成并重新部署管理员用户全量搜索与分页修复，正式计划为 `.agents/plans/plan_admin_user_search.md`。根因不是数据库只有 100 个，而是后续 `team-delete-20260830` Frontend/Backend 从旧基线构建，把用户 API 回退为只传 `page_size=100`。当前 `team-user-search-20260830` 以队伍删除镜像为基线合并 users 两个后端文件，并无缓存重建包含全部已上线功能的 Frontend；运行编译 chunk 已确认 `pageSize:20` 且传递 `page/search`。六服务 healthy、匿名管理员页/API 为 307/401；未使用管理员登录态、未读取用户列表、未调用业务写接口。

2026-08-29 已完成并部署管理员永久删除账号与用户自助注销，正式计划为 `.agents/plans/plan_account_deletion.md`。固定标签为 `account-deletion-20260829`，运行库为 `20260829_0015 (head)`；加密完整备份、从空环境恢复和 `0014 ↔ 0015` 往返均通过，生产验收未调用真实账号删除接口，账号清理 Outbox 仍为 0。详细结果已移入完成记录、变更记录与生产运维报告。

2026-08-29 已完成并部署真实管理员删除反馈答疑，正式计划继续使用唯一的 `.agents/plans/plan_feedback_help_requests.md`。固定标签为 `help-delete-20260829`，删除会物理移除工单并同步退出学生本人/公开读取，相关未读提醒标为已读并保留脱敏审计；运行验收未调用带认证的真实 DELETE，本轮无迁移。

本次答疑删除候选以已上线账号删除为基线，继续保留通知/作业删除、注册唯一约束修复、飞书 KaTeX 公式和账号删除能力；运行 OpenAPI 同时包含账号与答疑 DELETE，Alembic 保持 `20260829_0015 (head)`，最近成功知识库快照为 213 篇文档、1006 个媒体。

部署备份和临时 GPG 密钥环目前位于本机 `/tmp`，需要迁移到受控独立介质并分离保存。Docker socket 临时 `user:pnx:rw-` ACL 已尝试撤销，但普通用户无权限且 `sudo -n` 要求密码；仍需部署方交互执行 `sudo setfacl -x u:pnx /var/run/docker.sock` 并复核基础 ACL。
