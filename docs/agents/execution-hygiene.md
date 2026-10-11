# 执行卫生与后台生命周期契约 (Execution Hygiene)

本项目在推进多切片研发与子智能体协作时，严格遵循以下卫生规范，防止异步命令挂起与后台任务堆积：

## 1. 子智能体即用即销 (Subagent Lifecycle)

- **使用时机**：代码审查（`code-review`）等独立上下文任务派发子智能体。
- **完成闭环**：子智能体回传报告并完成当前轮次审查后，主智能体必须立即调用 `manage_subagents(Action='kill', ...)` 显式销毁，严禁让子智能体以 `idle` 状态跨切片常驻。

## 2. 命令同步守门 (Synchronous Command Execution)

- **充足等待时间**：短执行命令（`pytest`、`ruff`、`git status`、`git commit` 等）在调用 `run_command` 时，必须提供充足的 `WaitMsBeforeAsync`（建议 `8000~10000` 毫秒），确保命令在单步骤内同步完成，避免非预期切入后台造成虚假挂起。
- **非守护进程约束**：常规验证与测试脚本严格保持 `IsDaemon: false`。

## 3. 套接字与测试服务生命周期防御 (Socket Hygiene)

- **显式资源清理**：在编写涉及 `asyncio.start_server` 的回环测试用例时，服务端不仅须调用 `server.close()`，还必须在连接回调中追踪并显式关闭入站客户端写入器（`writer.close(); await writer.wait_closed()`），防止 `await server.wait_closed()` 因残留对端连接永久死锁。

## 4. 工单交付门禁自检 (Pre-flight Sanitization)

每个任务工单在执行提交、推送及关闭 Issue 前，必须通过检查清单：
1. `manage_subagents(Action='list')` 确认当前活跃子智能体数为 0；
2. `manage_task(Action='list')` 确认无未处理的残留挂起后台任务；
3. `uv run --with ruff ruff check .` 与 `pytest` 全量通过；
4. 提交信息规范（Conventional Commits），精准暂存文件。
