# 当前任务

## 状态

已完成：Markdown 展示统一、蓝白圆角主题换肤、管理员命令栏统一、侧边栏导航及 CI 类型检查修复。

## 完成内容

- 管理员作业编辑页保留 Markdown 源文本框，保存后的说明通过与用户详情相同的安全 HTML 渲染展示，不暴露内部实现标签。
- 全局切换为蓝白配色，增加浅蓝背景、蓝色主操作、蓝灰边框、圆角控件/容器和柔和层次阴影。
- 富文本预览补充标题、列表、链接、表格、代码块和引用样式，继续通过 `SafeHtml` 呈现，不新增前端 Markdown 解析器。
- 增加管理员页面回归测试，覆盖预览结构、作业入口、个人资料保存和登录人员视图。

## 验证结果

- 前端 14 个测试文件、43 项测试通过；ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- Frontend 已重建并替换，Nginx 已重启；`/health/live`、`/health/ready`、`/health/worker` 和 `/nginx-health` 均返回 200。
- 匿名访问 `/api/v1/auth/admin/sessions` 返回 401；本次未修改业务 API、权限、数据库或迁移。

## 本次追加：按钮视觉优化

- 主操作按钮改为浅蓝底深蓝字，统一圆角、阴影和悬停反馈；保留深蓝状态标签以维持对比度。
- 学生端筛选/上传，以及管理员新建通知、新建作业、新建赛事入口接入共享按钮样式。
- 管理员创建入口增加加号图标和清晰的按钮语义。
- 管理员通知、作业和赛事列表页统一复用紧凑命令栏，创建链接使用浅蓝 `h-9`/`rounded-lg` 按钮样式，表单主按钮保持原有尺寸。
- 修复 `test_auth_login.py` 的 `AuthenticatedContext` 测试类型标注，以及 `test_notifications.py` 的 `RecordingSender` 属性推断；不改变运行时逻辑。

## 本轮验证结果

- 后端定向认证/通知测试 14 项、严格 Mypy（127 个源文件）、Ruff 检查与格式检查通过。
- 前端 14 个测试文件 42 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建通过。

## 本次追加：侧边栏与统一 Markdown 展示

- 顶部横向导航改为响应式侧边栏：桌面端可折叠，移动端使用抽屉入口；管理员和学生共享布局组件并保持各自的权限入口。
- Markdown 源文本仅在编辑表单中可见；通知、作业、赛事和提交详情统一展示服务端清洗后的安全 HTML，管理员编辑区与学生详情复用同一渲染组件。
- 删除编辑区中的内部实现标签和预览标题，保留必要的“保存后可查看内容”状态提示。

## 本轮验证结果

- 前端 14 个测试文件、43 项测试通过；ESLint、严格 TypeScript 和 Next.js 生产构建通过。

## 本次追加：作业源码默认收起

- 管理员作业编辑页对已有安全 HTML 的作业先展示渲染结果，Markdown 源文改为通过“编辑 Markdown 源文”按需展开；新建或尚未生成 HTML 的草稿仍默认显示编辑框。
- 用户详情页和管理员已保存内容继续复用同一 `RenderedMarkdown`/`SafeHtml` 渲染路径，未修改 API、权限或数据结构。

## 本轮验证结果

- 管理员界面回归测试 7 项、完整前端 14 个测试文件 43 项测试、ESLint、严格 TypeScript 和 Next.js 生产构建均通过。
- Frontend 镜像已重建并替换，Frontend 与 Nginx 已重启；Backend、Worker、PostgreSQL、MinIO 保持健康。
- `/health/live`、`/health/ready`、`/health/worker`、`/nginx-health` 均返回 200；匿名访问 `/admin/assignments/new` 正确重定向到 `/login`。

## 正式计划

- .agents/plans/plan_markdown_preview_blue_white_theme.md
- .agents/plans/plan_button_visual_polish.md
- .agents/plans/plan_sidebar_markdown_rendering.md
- .agents/plans/plan_assignment_editor_visibility.md
