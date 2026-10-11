# 0005: 全双工锁解耦、半包缓冲保全与服务防御加固

针对全双工并发瓶颈、定界符软超时半包截断、批量扫描并发风暴及 Mock Server 监听安全隐患，决定实施读写锁分离、定界符半包无损暂存、探针限流及服务绑定安全校验。

## 背景与问题

在前期 v1.0.0 实现中，运行期暴露了若干架构与健壮性短板：
1. **读写互斥阻塞**：`Connection` 使用单一 `_io_lock` 保护底层 I/O，导致长超时 `recv` 操作将并发的 `send` 完全饿死，破坏了 TCP 原生全双工通信能力；
2. **定界符半包丢失**：当调用方指定 `delimiter` 时，软超时会强行清空 `drain_buffer`，导致未能闭合定界符的前半截数据被丢弃，下一次读取无法还原真实报文；且缓冲区无上限，存在 OOM 风险；
3. **探针并发风暴**：`tcp_port_scan` 对任意规模的端口列表无节制并发建立套接字，极易耗尽系统句柄并导致崩溃；
4. **拓扑感知缺失**：`tcp_list_connections` 尚未兑现 ADR-0001 规定的 `server_id` 过滤与拓扑标识字段；
5. **服务暴露风险**：`tcp_start_server` 缺乏地址校验，存在将测试端口意外绑定至 `0.0.0.0` 公网的风险。

## 决策内容

1. **全双工锁解耦与穿透关闭**：
   - 将 `Connection._io_lock` 解耦为独立的 `_read_lock` 与 `_write_lock`，读写操作互不干扰；
   - `Connection.close()` 采用穿透式即时关闭，无需阻塞等待 `_read_lock`，快速释放套接字。
2. **定界符原子保全与防 OOM 熔断**：
   - 当指定 `delimiter` 时，若发生软超时（`timed_out=True`），返回空数据载荷并完整保留 `drain_buffer` 内的数据，供后续读取连续拼接；
   - 设定 `MAX_BUFFER_SIZE = 10MB` 门禁，超出上限时抛出 `BufferOverflowError` 并主动熔断连接。
3. **网络探针双重流控门禁**：
   - 限制 `tcp_port_scan` 单次入参端口上限为 128 个（超出抛出 `ValueError`）；
   - 使用 `asyncio.Semaphore(32)` 对底层握手探针进行并发度平滑。
4. **混合连接池拓扑契约闭环**：
   - `ConnectionInfo` 补充 `server_id` 与 `is_server_accepted` 属性；
   - `tcp_list_connections(server_id=...)` 支持按 Mock Server 归属进行过滤。
5. **Mock Server 监听绑定安全门禁**：
   - 默认仅允许绑定回环地址（`127.0.0.1`、`::1`、`localhost`）；
   - 仅当 `ServerConfig.allow_private_networks=True` 时允许绑定 `0.0.0.0` 或私有局域网网卡并记录告警日志，否则予以阻断。
