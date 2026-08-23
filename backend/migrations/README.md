# 数据库迁移

只通过 Alembic 修改 PostgreSQL 结构。升级使用 `alembic upgrade head`，降级当前阶段使用 `alembic downgrade base`。
