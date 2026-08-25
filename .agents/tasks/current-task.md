# 当前任务

## 状态

已完成：Markdown 说明预览缺失修复及蓝白圆角主题换肤。

## 完成内容

- 管理员作业编辑页新增“Markdown 渲染预览”，复用后端清洗后的 HTML；新建或未保存时明确提示预览对应最近一次保存版本。
- 全局切换为蓝白配色，增加浅蓝背景、蓝色主操作、蓝灰边框、圆角控件/容器和柔和层次阴影。
- 富文本预览补充标题、列表、链接、表格、代码块和引用样式，继续通过 `SafeHtml` 呈现，不新增前端 Markdown 解析器。
- 增加管理员页面回归测试，覆盖预览结构、作业入口、个人资料保存和登录人员视图。

## 验证结果

- 前端 14 个测试文件、41 项测试通过；ESLint、严格 TypeScript 和 Next.js 生产构建通过。
- Frontend 已重建并替换，Nginx 已重启；`/health/live`、`/health/ready`、`/health/worker` 和 `/nginx-health` 均返回 200。
- 匿名访问 `/api/v1/auth/admin/sessions` 返回 401；本次未修改业务 API、权限、数据库或迁移。

## 本次追加：按钮视觉优化

- 主操作按钮改为浅蓝底深蓝字，统一圆角、阴影和悬停反馈；保留深蓝状态标签以维持对比度。
- 学生端筛选/上传，以及管理员新建通知、新建作业、新建赛事入口接入共享按钮样式。
- 管理员创建入口增加加号图标和清晰的按钮语义。

## 正式计划

- .agents/plans/plan_markdown_preview_blue_white_theme.md
- .agents/plans/plan_button_visual_polish.md
