# TCP MCP Server

<p align="center">
  <strong>通用 TCP 协议代理与自动化测试 Model Context Protocol (MCP) 服务端</strong>
</p>

<p align="center">
  <a href="https://github.com/atengk/mcp-server-tcp/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/atengk/mcp-server-tcp/ci.yml?branch=main&label=CI&style=flat-square" alt="CI Status" />
  </a>
  <a href="https://github.com/atengk/mcp-server-tcp/releases">
    <img src="https://img.shields.io/github/v/release/atengk/mcp-server-tcp?style=flat-square" alt="Release" />
  </a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square" alt="License" />
  </a>
  <a href="./CONTRIBUTING.md">
    <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome" />
  </a>
</p>

---

## 📖 项目简介

`mcp-server-tcp` 是一个基于 Python 3.10+、Model Context Protocol 官方 SDK (`mcp`) 与 `asyncio` 的高性能通用 TCP 协议 MCP 服务端。赋能大语言模型（LLM）与任意 TCP 目标服务、IoT 工业硬件及私有二进制协议（如 Modbus、自定义二进制 RPC）进行全双工收发与自动化联调。

---

## ✨ 核心特性

- 🎯 **双向通信全能**：不仅支持作为 TCP 客户端主动向外连接，还支持动态启动本地 **Mock Server** 被动捕获外部设备连入并模拟应答；
- ⚡ **原生全双工并发**：采用读写锁分离架构（ADR-0005），长轮询等待接收（`recv`）时绝不阻塞并发指令下发（`send`）；
- 🧩 **原子定界与半包保全**：独创软超时机制（Soft Timeout），定界符未达时不破坏报文流，无损保留半包缓冲（Drain Buffer）静默等待后续拼接；内置 10MB 缓冲区防 OOM 熔断门禁；
- 🛡️ **探针并发平滑门禁**：端口批量扫描限制单次上限 128 个端口，内置 32 并发信号量，彻底规避系统套接字句柄耗尽崩溃；
- 🔍 **内存环形流量审计**：每个连接独享 100 条环形缓冲区（Traffic Ring Buffer），提供时间戳、传输方向及 Hex/文本快照，零磁盘污染；支持标准 MCP Resource 挂载读取；
- 🔒 **工业级安全防线**：默认拦截云厂商元数据（`169.254.169.254`）及高危保留网段，Mock Server 监听绑定受分级安全策略管辖，全方位防范 SSRF 攻击；
- 🚀 **开箱即用与容器分发**：支持 `uvx` 零配置即开即用，同时发布多架构容器镜像至 GitHub Packages (`ghcr.io`)。

---

## 🛠️ 工具清单 (Tools)

| 分类 | 工具名称 | 核心职责说明 |
| :--- | :--- | :--- |
| **网络探针** | `tcp_ping_port` | 测试指定主机端口的 TCP SYN 握手时延（毫秒）与可达性 |
| | `tcp_port_scan` | 并发探测目标主机端口开放状态（上限 128 端口，32 信号量平滑限流） |
| | `tcp_send_once` | 一次性短连接发收探针（自动完成连接、发送、读取与优雅关闭） |
| **会话管理** | `tcp_connect` | 建立长连接并加入会话池，返回唯一 `conn_id` |
| | `tcp_disconnect` | 安全断开指定长连接并穿透式释放套接字 |
| | `tcp_list_connections` | 列出活跃连接（支持 `server_id` 拓扑过滤，展示入站/出站标识与待读缓冲） |
| **精准收发** | `tcp_send_text` | 发送 UTF-8 文本数据（可选追加 `\r\n`，全双工独立写锁保护） |
| | `tcp_send_hex` | 发送原始十六进制字节序列（Hex Payload） |
| | `tcp_recv_text` | 接收文本，支持定界符截断（定界符未达保全半包）、软超时返回与 10MB 防 OOM 熔断 |
| | `tcp_recv_hex` | 接收二进制字节流并格式化为 Hex 视图，支持最大字节数限制与防 OOM 熔断 |
| **Mock 服务** | `tcp_start_server` | 启动本地 TCP 服务监听器，外部连入客户端自动分配 `conn_id` 入池（受绑定安全门禁保护） |
| | `tcp_broadcast` | 向指定 Mock Server 连入的所有活跃客户端同时群发数据 |
| | `tcp_stop_server` | 停止服务监听并释放端口绑定，级联断开所有附属客户端 |
| **调试审计** | `tcp_dump_traffic` | 回溯指定连接最近的收发报文记录（含时间戳与方向快照） |

---

## 📊 资源清单 (Resources)

服务端提供标准 MCP Resource 资源订阅能力，便于客户端与大模型挂载并实时回溯链路流量快照：

| 资源 URI 模式 | MIME 类型 | 说明 |
| :--- | :--- | :--- |
| `tcp://connection/{conn_id}/traffic` | `application/json` | 读取或订阅指定长连接的 Traffic Ring Buffer 流量审计数据（最多 100 条双工收发记录） |


---

## 🚀 快速开始

### 1. 通用 MCP 客户端配置 (推荐)

在任意支持 Model Context Protocol (MCP) 的客户端配置文件中，添加如下标准通用配置。你可以根据部署喜好选择 `tcp`（基于 `uvx`，零安装即开即用）或 `tcp-docker`（基于容器隔离）：

```json
{
  "mcpServers": {
    "tcp": {
      "command": "uvx",
      "args": ["mcp-server-tcp"],
      "env": {
        "MCP_TCP_MAX_CONNECTIONS": "10",
        "MCP_TCP_IDLE_TIMEOUT_SECONDS": "300.0",
        "MCP_TCP_ALLOW_PRIVATE_NETWORKS": "true"
      }
    },
    "tcp-docker": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "MCP_TCP_MAX_CONNECTIONS=10",
        "-e", "MCP_TCP_IDLE_TIMEOUT_SECONDS=300.0",
        "-e", "MCP_TCP_ALLOW_PRIVATE_NETWORKS=true",
        "ghcr.io/atengk/mcp-server-tcp:latest"
      ]
    }
  }
}
```

> 💡 **提示**：上述 `env` 字段中的环境变量均为可选调优项；若使用默认参数，仅需保留 `command` 与 `args` 即可。

### 2. 命令行独立调试 (CLI / Docker)

若需要在本地终端中直接测试 stdio 通信或验证服务健康状况，可执行以下命令：

```bash
# 方式 A：通过 uvx 直接启动
uvx mcp-server-tcp

# 方式 B：通过 Docker 运行
docker run -i --rm ghcr.io/atengk/mcp-server-tcp:latest
```


---

## ⚙️ 运行时环境变量配置 (Runtime Configuration)

服务端支持通过系统环境变量进行无代码入侵式参数调优（遵循 [ADR-0003](./docs/adr/0003-runtime-configuration-and-security-posture.md)）：

| 环境变量名称 | 默认值 | 作用说明 |
| :--- | :--- | :--- |
| `MCP_TCP_MAX_CONNECTIONS` | `10` | 连接池最大允许的并发连接数配额上限 |
| `MCP_TCP_IDLE_TIMEOUT_SECONDS` | `300.0` | 连接空闲自愈阈值（秒），超过此时间未活动的连接将被后台协程自动回收 |
| `MCP_TCP_ALLOW_PRIVATE_NETWORKS` | `true` | 是否允许连接本地回环（`127.0.0.1`）与私有网段（RFC 1918）。企业安全受限环境可置为 `false` 一键拦截 |

> 🔒 **强制安全防线**：无论如何配置，公有云敏感元数据端点（AWS/GCP/Azure `169.254.169.254`、阿里云 `100.100.100.200` 等）均被绝对硬性阻断，保障宿主网络免受 SSRF 渗透。


---

## 💻 本地开发与测试

```bash
# 1. 检出仓库并激活 Git 规范提交守护钩子
git clone https://github.com/atengk/mcp-server-tcp.git
cd mcp-server-tcp
git config core.hooksPath .githooks

# 2. 安装开发依赖（推荐使用现代化 uv 工具链）
uv sync --all-extras
# 或使用传统 pip 模式：pip install -e ".[test]" && pip install ruff

# 3. 静态代码检查与格式校验
uv run ruff check .
uv run ruff format --check .

# 4. 运行全量单元测试与覆盖率统计
uv run pytest --cov

```

---

## 📦 自动发版与分发流水线

本项目内置双通道自动化发版体系：
1. **GitHub 网页端发版**：在 Actions 中选择 **GitHub Release** 输入版本号（如 `v1.0.0`），自动提取更新日志、创建 Tag 并级联触发 PyPI 与 Docker 镜像发布；
2. **本地脚本发版**：
   ```bash
   bash scripts/release.sh v1.0.0 -y
   ```


---

## 📂 仓库目录结构

```text
.
├── .github/
│   ├── ISSUE_TEMPLATE/             # Issue 缺陷与需求模版
│   ├── workflows/
│   │   ├── ci.yml                  # PR 标题校验、Shell 脚本守门与 Python 矩阵测试
│   │   ├── release.yml             # 双通道发版与 git-cliff 更新日志提取
│   │   ├── publish.yml             # PyPI 发行包自动发布
│   │   └── docker.yml              # 多架构 GHCR 容器镜像构建与发布
│   ├── CODEOWNERS                  # 代码所有者自动审阅配置
│   ├── dependabot.yml              # Actions、Python 与 Docker 依赖月度自动巡检
│   └── PULL_REQUEST_TEMPLATE.md    # PR 提交规范模版
├── .githooks/
│   └── commit-msg                  # 原生 Git 提交规范守门钩子
├── scripts/
│   ├── commit.sh                   # 规范化交互式提交助手
│   └── release.sh                  # 全生命周期发版防呆脚本
├── src/
│   └── mcp_server_tcp/             # TCP MCP Server 核心实现
├── tests/                          # 自动化端到端与单元测试集
├── docs/
│   ├── adr/                        # 关键架构决策记录 (ADR)
│   └── agents/                     # 智能体协作与规范文档
├── .cliff.toml                     # git-cliff 变更日志分类配置
├── CONTEXT.md                      # 核心领域模型与术语词汇表
├── Dockerfile                      # 生产级多架构轻量镜像构建
├── pyproject.toml                  # 现代 Python 打包与依赖配置
├── CONTRIBUTING.md                 # 贡献指南
└── LICENSE                         # Apache-2.0 许可证
```

---

## 🤝 参与贡献

欢迎任何形式的贡献！提交代码前请仔细阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。
