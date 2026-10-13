# 0006: PyPI 发行包命名规范与模块解耦

将 PyPI 官方注册表中的分发包名规范化为 `atengk-mcp-server-tcp`，同时保持内部 Python 源码模块与协议层解耦。

## 背景与问题

1. **命名空间与分发规范**：在 PyPI 生态中，直接占用顶级通用名称 `mcp-server-tcp` 容易引发命名冲突或不符合发布者统一的命名空间规范，需要固定为 `https://pypi.org/project/atengk-mcp-server-tcp/`；
2. **CLI 入口与生态兼容**：用户通过 `uvx atengk-mcp-server-tcp` 调用时，包管理器默认执行与包名同名的 Console Script；
3. **架构侵入性防御**：若为迎合外部 PyPI 包名而强行将工程内部模块（`src/mcp_server_tcp`）及 MCP 握手名称全量重构，会造成大面积 Git Diff 扰动与不必要的向后不兼容。

## 决策内容

1. **PyPI 分发包名规范化**：
   - 在 `pyproject.toml` 中将 `[project] name` 明确为 `atengk-mcp-server-tcp`；
   - 构建产物对齐为 `atengk_mcp_server_tcp-*.whl`，PyPI 官方地址为 `https://pypi.org/project/atengk-mcp-server-tcp/`。
2. **CLI 命令行入口与容器入口对齐**：
   - 在 `pyproject.toml` 的 `[project.scripts]` 中声明 `atengk-mcp-server-tcp = "mcp_server_tcp:main"`；
   - 同步将 `Dockerfile` 中的 `ENTRYPOINT` 更新为 `["atengk-mcp-server-tcp"]`，确保 `uvx` 与容器行为一致。
3. **源码模块与协议标识解耦**：
   - 内部源码目录保持 `src/mcp_server_tcp/`（通过 `tool.hatch.build.targets.wheel.packages` 指定打包），Python 内部调用保持 `import mcp_server_tcp`；
   - MCP 协议握手名称保持 `MCPServer("mcp-server-tcp")`，容器镜像命名空间维持 `ghcr.io/atengk/mcp-server-tcp`。
