"""
MCP 服务端实例定义与工具注册。

@author Ateng
@since 2026-10-11
"""

import json
from typing import List, Optional

from mcp.server.mcpserver import MCPServer

from mcp_server_tcp.models import (
    BroadcastResult,
    ConnectionInfo,
    ConnectResult,
    DisconnectResult,
    PingResult,
    PortScanResult,
    RecvHexResult,
    RecvTextResult,
    SendOnceResult,
    SendResult,
    StartServerResult,
    StopServerResult,
    TrafficDumpResult,
)
from mcp_server_tcp.pool import ConnectionPool
from mcp_server_tcp.probe import (
    tcp_ping_port as _tcp_ping_port,
)
from mcp_server_tcp.probe import (
    tcp_port_scan as _tcp_port_scan,
)
from mcp_server_tcp.probe import (
    tcp_send_once as _tcp_send_once,
)

mcp = MCPServer("mcp-server-tcp")

# 全局受管连接池单例（遵循 ADR-0001 混合连接池与 ADR-0003 运行时配置规范）
pool = ConnectionPool()


@mcp.tool()
async def tcp_ping_port(
    host: str,
    port: int,
    timeout_ms: int = 3000,
) -> PingResult:
    """
    测量到目标主机的 TCP 握手时延与端口连通性。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口 (1-65535)
    @param timeout_ms 超时时间（毫秒，默认 3000）
    @return 包含 connected, host, port, latency_ms, error 的检测结果
    """
    return await _tcp_ping_port(host, port, timeout_ms=timeout_ms)


@mcp.tool()
async def tcp_port_scan(
    host: str,
    ports: List[int],
    timeout_ms: int = 1000,
) -> PortScanResult:
    """
    并发扫描目标主机的指定端口列表并返回开放状态。

    @param host 目标主机域名或 IP
    @param ports 待扫描的端口列表
    @param timeout_ms 单个端口探测超时时间（毫秒，默认 1000）
    @return 包含 host, scanned_count, open_ports, results 列表的扫描结果
    """
    return await _tcp_port_scan(host, ports, timeout_ms=timeout_ms)


@mcp.tool()
async def tcp_send_once(
    host: str,
    port: int,
    data: str,
    encoding: str = "utf-8",
    timeout_ms: int = 5000,
) -> SendOnceResult:
    """
    建立短连接、发送单次数据并读取响应，随后立即优雅关闭连接。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口
    @param data 待发送数据（Text Payload 明文字符串或 Hex Payload 十六进制串）
    @param encoding 编码格式，支持 'utf-8' 或 'hex'（默认 'utf-8'）
    @param timeout_ms 操作整体超时时间（毫秒，默认 5000）
    @return 包含 success, sent_bytes, received_bytes, response_data, error 的通信结果
    """
    return await _tcp_send_once(host, port, data, encoding=encoding, timeout_ms=timeout_ms)


@mcp.tool()
async def tcp_connect(
    host: str,
    port: int,
    timeout_ms: int = 5000,
) -> ConnectResult:
    """
    建立持久化 TCP 连接，分配唯一 conn_id 并纳入连接池受管。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口 (1-65535)
    @param timeout_ms 连接超时时间（毫秒，默认 5000）
    @return ConnectResult 字典，包含 connected, conn_id, host, port, error
    """
    # 启动自愈协程（若尚未启动）
    await pool.start_reaper()
    try:
        conn = await pool.connect(host, port, timeout_ms=timeout_ms)
        return {
            "connected": True,
            "conn_id": conn.conn_id,
            "host": host,
            "port": port,
            "error": None,
        }
    except Exception as exc:
        return {
            "connected": False,
            "conn_id": None,
            "host": host,
            "port": port,
            "error": str(exc),
        }


@mcp.tool()
async def tcp_disconnect(
    conn_id: str,
) -> DisconnectResult:
    """
    优雅关闭指定的 TCP 连接并从连接池中注销释放套接字。

    @param conn_id 连接全局唯一标识符
    @return DisconnectResult 字典，包含 conn_id, disconnected, message
    """
    success = await pool.disconnect(conn_id)
    if success:
        return {
            "conn_id": conn_id,
            "disconnected": True,
            "message": f"Connection {conn_id} successfully closed.",
        }
    return {
        "conn_id": conn_id,
        "disconnected": False,
        "message": f"Connection {conn_id} not found or already closed.",
    }


@mcp.tool()
def tcp_list_connections(
    server_id: Optional[str] = None,
) -> List[ConnectionInfo]:
    """
    列出当前连接池中所有活跃连接的状态快照，支持按 Mock Server ID 拓扑过滤。

    @param server_id 可选的 Mock Server 全局唯一标识符过滤
    @return 活跃连接列表，包含 conn_id, host, port, idle_seconds, unread_bytes,
            server_id, is_server_accepted 等
    """
    return pool.list_connections(server_id=server_id)


@mcp.tool()
async def tcp_send_text(
    conn_id: str,
    text: str,
    append_crlf: bool = False,
) -> SendResult:
    """
    向指定长连接发送 UTF-8 文本数据（Text Payload），支持可选行尾 CRLF。

    @param conn_id 连接全局唯一标识符
    @param text 待发送的文本内容
    @param append_crlf 是否在末尾自动追加 \\r\\n（默认 False）
    @return SendResult 字典，包含 conn_id, bytes_sent, success, error
    """
    return await pool.send_text(conn_id, text, append_crlf=append_crlf)


@mcp.tool()
async def tcp_send_hex(
    conn_id: str,
    hex_string: str,
) -> SendResult:
    """
    向指定长连接发送十六进制编码的原始二进制字节流（Hex Payload）。

    @param conn_id 连接全局唯一标识符
    @param hex_string 十六进制字符串（支持形如 '01 02 03' 或 '010203'）
    @return SendResult 字典，包含 conn_id, bytes_sent, success, error
    """
    return await pool.send_hex(conn_id, hex_string)


@mcp.tool()
async def tcp_recv_text(
    conn_id: str,
    timeout_ms: int = 5000,
    delimiter: Optional[str] = None,
) -> RecvTextResult:
    """
    从指定长连接接收文本数据（Text Payload），具备定界符切包与软超时宽容返回能力。

    @param conn_id 连接全局唯一标识符
    @param timeout_ms 超时毫秒数（默认 5000）
    @param delimiter 报文定界符（如 '\\r\\n' 或 '\\n'，可选）
    @return RecvTextResult 字典，包含 text, bytes_read, timed_out, closed, error
    """
    return await pool.recv_text(conn_id, timeout_ms=timeout_ms, delimiter=delimiter)


@mcp.tool()
async def tcp_recv_hex(
    conn_id: str,
    timeout_ms: int = 5000,
    max_bytes: Optional[int] = None,
) -> RecvHexResult:
    """
    从指定长连接接收原始二进制字节并格式化为 Hex Payload，支持限制字节数与软超时。

    @param conn_id 连接全局唯一标识符
    @param timeout_ms 超时毫秒数（默认 5000）
    @param max_bytes 最大接收字节数上限（可选）
    @return RecvHexResult 字典，包含 hex_string, bytes_read, timed_out, closed, error
    """
    return await pool.recv_hex(conn_id, timeout_ms=timeout_ms, max_bytes=max_bytes)


@mcp.tool()
async def tcp_start_server(
    host: str = "127.0.0.1",
    port: int = 0,
) -> StartServerResult:
    """
    启动本地 Mock TCP 服务端监听器，被动接受外部客户端连入并统一分配 conn_id。

    @param host 绑定监听的本地地址（默认 127.0.0.1）
    @param port 绑定监听的本地端口（默认 0，系统随机分配可用端口）
    @return StartServerResult 字典，包含 server_id, host, port, started, error
    """
    return await pool.start_server(host=host, port=port)


@mcp.tool()
async def tcp_stop_server(
    server_id: str,
) -> StopServerResult:
    """
    安全停止指定的 Mock TCP 服务端监听器，并级联断开所有该服务端接受的客户端连接。

    @param server_id Mock Server 全局唯一标识符
    @return StopServerResult 字典，包含 server_id, stopped, closed_connections_count, message
    """
    return await pool.stop_server(server_id)


@mcp.tool()
async def tcp_broadcast(
    server_id: str,
    text: Optional[str] = None,
    hex_string: Optional[str] = None,
    append_crlf: bool = False,
) -> BroadcastResult:
    """
    向指定 Mock Server 下的所有连入活跃客户端同时多路广播数据。

    @param server_id Mock Server 全局唯一标识符
    @param text 待广播的文本数据（Text Payload）
    @param hex_string 待广播的十六进制二进制数据（Hex Payload）
    @param append_crlf 广播文本时是否自动追加 \\r\\n（默认 False）
    @return BroadcastResult 字典，包含 server_id, recipients_count, success_count, failed_count
    """
    return await pool.broadcast(
        server_id=server_id,
        text=text,
        hex_string=hex_string,
        append_crlf=append_crlf,
    )


@mcp.tool()
def tcp_dump_traffic(
    conn_id: str,
    limit: int = 100,
) -> TrafficDumpResult:
    """
    回溯指定连接的最近 Traffic Ring Buffer 内存审计记录（最多 100 条）。

    @param conn_id 连接全局唯一标识符
    @param limit 最大返回记录数（默认 100）
    @return TrafficDumpResult 字典，包含 conn_id, total_records, records
    """
    return pool.dump_traffic(conn_id=conn_id, limit=limit)


@mcp.resource("tcp://connection/{conn_id}/traffic", mime_type="application/json")
def get_connection_traffic_resource(conn_id: str) -> str:
    """
    提供指定 TCP 连接的 Traffic Ring Buffer 流量审计数据资源订阅。

    @param conn_id 连接全局唯一标识符
    @return JSON 序列化的 TrafficDumpResult
    """
    dump = pool.dump_traffic(conn_id=conn_id)
    return json.dumps(dump, ensure_ascii=False, indent=2)
