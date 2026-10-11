# 议题追踪器规范：GitHub Issues

本仓库的所有需求、缺陷与规格说明统一以 GitHub Issues 形式追踪管理。所有操作均使用 `gh` 命令行工具完成。

## 常用操作与规范

- **创建 Issue**：`gh issue create --title "..." --body "..."`（多行正文推荐使用 Heredoc 语法）
- **查看 Issue 详情**：`gh issue view <number> --comments`（配合 `jq` 解析并提取标签与评论）
- **列出 Issue**：
  ```bash
  gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'
  ```
- **发表评论**：`gh issue comment <number> --body "..."`
- **编辑标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭 Issue**：`gh issue close <number> --comment "..."`

> 💡 仓库地址会自动根据当前 Git 目录的 `git remote -v` 解析推导，无需手动拼接。

## Pull Requests 审查与分类分流

**将外部 PR 作为需求入口：否 (PRs as a request surface: no)**  
*(若后续需要让外部贡献者的 PR 作为功能需求进入分类队列，可将此项修改为 `yes`)*

## 技能协作触发契约

- **当技能提示“发布至议题追踪器 (publish to the issue tracker)”时**：  
  在 GitHub 仓库中创建对应的 Issue。
- **当技能提示“获取关联工单 (fetch the relevant ticket)”时**：  
  执行 `gh issue view <number> --comments` 获取上下文。

## 路线规划与工单拓扑 (Wayfinding)

由 `/wayfinder` 技能消费。**地图 (Map)** 为单个汇总 Issue，**子任务工单 (Child)** 作为具体分支任务。

- **地图 (Map)**：带有 `wayfinder:map` 标签的顶层 Issue，记录阶段总结、当前决策沉淀与迷雾区：`gh issue create --label wayfinder:map`。
- **子任务工单 (Child Ticket)**：作为 GitHub 子议题（Sub-issue）挂载于 Map 之下。若未启用子议题功能，则在 Map 正文中维护任务列表，并在子 Issue 开头注明 `Part of #<map>`。关联标签：`wayfinder:<type>`（可选 `research`/`prototype`/`grilling`/`task`）。
- **阻塞依赖 (Blocking)**：使用 GitHub 原生 Issue 依赖契约：
  `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`（注意：此处为数据库 ID 而非编号）。若无原生依赖支持，在子 Issue 顶部标注 `Blocked by: #<n>`。所有阻塞项 Closed 后解除阻塞。
- **认领 (Claim)**：`gh issue edit <n> --add-assignee @me`。
- **归档 (Resolve)**：`gh issue comment <n> --body "<answer>"`，执行 `gh issue close <n>`，并将决策结论同步回填至 Map 的 Decisions-so-far 章节。
