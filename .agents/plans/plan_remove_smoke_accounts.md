# 历史 Smoke 账号清理与唯一管理员计划

## 状态

已完成（2026-08-25）。

## 背景与必要性

开发数据库保留 20 个 Stage 4/Stage 5/Codex Smoke 账号，其中两个历史 Smoke 管理员仍为 active；唯一真实 Connect 账号 `yzhang367@connect.hkust-gz.edu.cn` 为 active student，导致管理员入口不可见，也不满足 AUTH-008 的用户表唯一账号自动修正规则。用户已明确要求保留该 Connect 账号并删除其余全部账号。

## 目标与边界

- 精确保留规范化邮箱为 `yzhang367@connect.hkust-gz.edu.cn` 的现有账号、密码哈希和验证状态，把真实角色持久化为 `admin`。
- 精确删除其他 20 个账号，不读取或输出密码哈希、令牌、Cookie、SMTP/MinIO 密钥。
- 删除前核对所有用户外键和关联数据；不得把 Smoke 账号创建的历史资源静默改写为保留账号创建。
- 若物理删除账号必须连带删除作业、赛事、提交、文件或其他正式业务记录，先给出聚合清单并确认授权范围。
- 执行前生成 PostgreSQL 自包含格式备份；所有数据库变更在单个事务中完成，失败则全部回滚。
- 角色提升增加 revision、撤销保留账号旧 Session 并追加脱敏审计；清理完成后由用户重新登录获得管理员 Session。

## 验证

- 备份文件存在、权限受限且可由 `pg_restore --list` 读取。
- 数据库最终恰好一行用户，邮箱为目标 Connect 账号、角色为 `admin`、状态为 `active`。
- 不存在指向已删除用户的外键，Alembic head 保持 `20260825_0007`。
- 六个常驻 Compose 服务健康；5000 端口 Nginx、Backend ready 和 Worker 健康为 200。
- 更新任务、基线、变更与运维记录，说明删除范围、备份位置和恢复方式。

## 完成结果

- 删除前生成 PostgreSQL 17 自包含备份 `/tmp/pnx-training-before-smoke-account-removal-20260825.dump`，权限 `0600`，SHA-256 为 `0bea209172cd12ca3a2d7b0d50c511d6e980edd9664351fd9a26c239e27a9fe0`，并由容器内 `pg_restore --list` 验证。
- 三个 MinIO Smoke 对象已备份到 `/tmp/pnx-training-minio-before-smoke-account-removal-20260825` 并逐项核对 SHA-256；数据库提交后从私有桶删除，桶最终为 0 对象。
- 单事务删除 20 个 Smoke 账号、4 条通知、4 个作业、2 个赛事、5 支队伍、2 个提交、3 个正式版本、2 条评语、6 条文件记录、24 条非目标 Outbox 及关联数据；旧审计保留，已删除操作者由外键置空。
- `yzhang367@connect.hkust-gz.edu.cn` 已持久化为唯一的已验证 `active admin`，revision 已推进，1 个尚未撤销的旧 Session 已撤销，并写入两条维护审计。
- Alembic 保持 `20260825_0007`；六个常驻服务健康，5000 端口 Nginx、Backend ready 和 Worker 均为 200，最近日志无严重错误。
