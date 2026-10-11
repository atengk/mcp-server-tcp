# 安全策略与漏洞披露指南 (Security Policy)

本项目十分重视代码与系统安全。如果你在本项目中发现了疑似安全漏洞或隐患，请**切勿在公开的 GitHub Issue 或讨论区直接披露**，以防在漏洞修复前造成安全风险。

---

## 1. 支持的版本 (Supported Versions)

我们通常仅对最新的主干分支 (`main`) 及最新发布的正式版本提供安全补丁支持：

| 版本系列 | 是否支持安全补丁 | 说明 |
| :--- | :--- | :--- |
| `main` / 最新 Release | :white_check_mark: 支持 | 优先接收安全补丁与热修复 |
| 历史旧版本 | :x: 不再支持 | 建议尽快升级至最新版本 |

---

## 2. 系统内置安全机制与威胁模型 (Threat Model & Defenses)

作为通用 TCP 协议代理，本项目在网络底层构建了深度防御（Defense in Depth）体系（遵循 [ADR-0003](./docs/adr/0003-runtime-configuration-and-security-posture.md) 与 [ADR-0005](./docs/adr/0005-full-duplex-buffering-and-security-hardening.md)）：

1. **分级 SSRF 防御体系**：
   - **绝对拦截（不可覆盖）**：公有云敏感元数据端点（AWS/GCP/Azure `169.254.169.254`、阿里云 `100.100.100.200` 等），任何环境变量配置下均强制拦截；
   - **条件管控**：本地回环与私有网络（RFC 1918）受环境变量 `MCP_TCP_ALLOW_PRIVATE_NETWORKS` 控制。高安全生产环境可将其置为 `false`，一键阻断对内网基础设施的探测与访问。
2. **Mock Server 监听绑定防护**：
   - 动态服务端监听默认严格限定于本地回环网段（`127.0.0.1`, `::1`, `localhost`）；
   - 若指定非回环地址或 `0.0.0.0`，受 `MCP_TCP_ALLOW_PRIVATE_NETWORKS` 安全策略前置拦截，放行时强制输出安全暴露告警。
3. **网络与内存 DoS 韧性防护**：
   - **探针流量平滑**：`tcp_port_scan` 限制单次最大扫描 128 个端口，内置 32 信号量并发流控，规避操作系统套接字句柄耗尽崩溃；
   - **缓冲区防 OOM 熔断**：未消费的残余缓冲队列（Drain Buffer）上限设为 10MB，持续未达成报文定界符时触发 `BufferOverflowError` 防御性主动熔断断开。
4. **机密脱敏与内存审计沙箱**：
   - 流量审计记录（Traffic Ring Buffer）仅驻留于固定容量（100 条）内存环形缓冲区，绝不进行磁盘文件写入，杜绝凭据落地留痕。

---

## 3. 漏洞报告渠道 (Reporting a Vulnerability)


推荐通过以下方式安全、私密地向维护者报告漏洞：

### 方式一：GitHub 私密安全报告 (推荐首选)
1. 前往本仓库的 **[Security -> Advisories](https://github.com/atengk/mcp-server-tcp/security/advisories/new)** 页面；
2. 点击 **「Report a vulnerability」**；
3. 详细填写漏洞描述、复现步骤及潜在影响后提交。该报告仅仓库维护者可见。

### 方式二：安全联络邮箱
若无法访问 GitHub Advisories，请直接发送加密邮件至安全联系人：
- **安全联系邮箱**：`security@example.com`（*请在邮件主题中注明 `[SECURITY VULNERABILITY]`*）

---

## 4. 漏洞响应流程 (Response Process)


- **初步确认**：我们将在 **48 小时内** 确认收到你的安全报告并启动技术研判；
- **补丁研发**：确认漏洞存在后，维护团队将在私有分支中编写修复补丁并验证防御效果；
- **安全发布**：修复补丁合并后，我们将发布全新的补丁版本（Patch Release），并在 GitHub Security Advisories 中公开致谢发现者（若你希望保持匿名，亦可提前说明）；
- **负责任披露**：在补丁正式发布前，维护者与报告人双方承诺遵守协同披露原则，避免提前公开 PoC 细节。
