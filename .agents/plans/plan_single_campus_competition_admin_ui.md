# 单一校内赛管理入口与管理员页头统一计划

## 背景

管理员当前在通知、作业和赛事列表页看到的命令栏与其它管理员页面层级不一致；赛事管理仍以“多赛事”列表和“新建赛事”作为主要入口。产品实际只需要一条校内赛公告、报名和组队流程，管理员进入赛事管理后应直接查看当前校内赛及队伍。

## 必要性与决策

- 统一管理员页面头部的容器、间距、标题层级、说明文字和操作区，减少不同入口之间的视觉跳变。
- 管理员赛事入口固定称为“校内赛”，默认展示当前未归档赛事及其队伍；不再展示“新建赛事”操作。
- 历史已归档赛事、旧创建路由和赛题 API 保留兼容，不删除数据；服务层阻止在已有未归档校内赛时再创建第二条赛事。
- 赛事详情继续保留公告配置、阶段控制和队伍纠错能力，但页面主导航聚焦队伍列表。

## 影响范围

- `frontend/app/admin/announcements/page.tsx`
- `frontend/app/admin/assignments/page.tsx`
- `frontend/app/admin/competitions/page.tsx`
- `frontend/app/admin/competitions/[competitionId]/page.tsx`
- `frontend/app/admin/competitions/new/page.tsx`（兼容重定向/不可用提示）
- `frontend/components/admin/admin-page-header.tsx` 及赛事列表展示组件
- `backend/app/competitions/repository.py`、`service.py`（当前赛事查询与重复创建冲突）
- 相关前后端测试及产品/页面/API/决策/变更文档

## 验证方式

- 前端回归验证三个管理员入口使用同一页头结构，赛事页无“新建赛事”且能展示当前队伍；ESLint、严格 TypeScript、Vitest、生产构建。
- 后端验证已有未归档赛事时创建第二条返回稳定 409，历史归档赛事不阻塞兼容创建路径；运行 Ruff、格式、Mypy、赛事定向与完整测试。
- 重建 Backend、Worker、Frontend，重启 Nginx，检查六个 Compose 服务与健康端点。

## 回滚

回滚本次代码与文档提交即可恢复原多赛事管理入口；不删除赛事、队伍或赛题数据，不需要数据库迁移。
