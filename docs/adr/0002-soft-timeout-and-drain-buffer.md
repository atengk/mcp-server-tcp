# 0002: TCP 流式截断与软超时宽容返回机制

针对 TCP 裸流中粘包、半包及网络延迟导致的读取卡死问题，决定在 `tcp_recv_*` 工具中采用“软超时宽容返回（Soft Timeout）”与“优雅残余排出（Drain Buffer）”策略。

> 📌 **架构演进注记 (Amended by ADR-0005)**：关于定界符（Delimiter）截断模式下的半包缓冲保全与 10MB 防 OOM 熔断机制，已在 [ADR-0005](./0005-full-duplex-buffering-and-security-hardening.md) 中进一步修订扩展：定界符模式下软超时返回空载荷并保全半包，裸流分片模式继续执行本 ADR 宽容返回。


## 背景与问题

TCP 是基于字节流（Byte Stream）而非报文流（Message Stream）的传输协议。在实际联调中：
1. 若对端传输未对齐定界符（Delimiter）或发送速度缓慢，严格超时抛错会导致 LLM 任务直接崩溃并死锁；
2. 若对端发完数据后立即关闭连接（发送 FIN），如果 MCP 服务端立刻销毁连接，LLM 将丢失最后一包关键数据。

## 决策内容

1. **软超时机制 (Soft Timeout)**：当读取到达 `timeout_ms` 仍未凑齐完整定界符或字节数时，不抛出致命异常，而是将内部当前已收到的字节返回给调用方，并标记元数据 `timed_out: true, closed: false`；
2. **残余数据排空 (Drain Before Close)**：当底层检测到对端关闭（Peer EOF/FIN）时，连接状态变更为 `closed_by_peer`，但连接对象与未读缓冲队列继续保留。允许 LLM 进行最终排空读取，直到缓冲区清空后再行物理销毁。
