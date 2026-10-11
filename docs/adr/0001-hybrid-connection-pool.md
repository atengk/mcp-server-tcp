# 0001: 统一混合连接池与全局会话模型

针对 TCP MCP 服务端中主动客户端连接与被动接受的入站客户端连接的管理，决定采用统一的混合连接池模型。所有连接统一分配全局唯一的 `conn_id`，共享统一的读取队列、生命周期自愈与收发工具契约。

## 背景与问题

LLM 既需要作为客户端主动连入目标服务（如 Redis、IoT 设备网关），又需要作为服务端监听端口（Mock Server）捕获外部设备连入。若将主动连接与被动接受的客户端连接拆分为不同的管理器和工具集合（如 `client_send` 与 `server_send`），会导致工具数量倍增、增加 LLM 的决策负荷与参数混淆。

## 决策内容

1. **统一标识体系**：无论出站（Client）还是入站（Server-accepted Client），一律在 `Connection Pool` 中分配全局唯一的 `conn_id`；
2. **通用收发契约**：底层 `tcp_send_text`、`tcp_send_hex`、`tcp_recv_text`、`tcp_recv_hex` 工具完全通用，只认 `conn_id`，对上层调用透明；
3. **入站感知**：Mock Server 接收到新连接时静默入池，LLM 通过 `tcp_list_connections(server_id=...)` 进行状态探查与拓扑关联。
