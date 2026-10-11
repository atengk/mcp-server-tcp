"""
MCP 服务端实例定义与工具注册。

@author Ateng
@since 2026-10-11
"""

from typing import List

from mcp.server.mcpserver import MCPServer

from mcp_server_tcp.models import (
    ConnectionInfo,
    ConnectResult,
    DisconnectResult,
    PingResult,
    PortScanResult,
    SendOnceResult,
)
from mcp_server_tcp.pool import ConnectionPool
from mcp_server_tcp.probe import (
    tcp_ping_port as _tcp_ping_port,
    tcp_port_scan as _tcp_port_scan,
    tcp_send_once as _tcp_send_once,
)

mcp = MCPServer("mcp-server-tcp")

# 全局受管连接池单例（遵循 ADR-0001 混合连接池规范）
pool = ConnectionPool(max_connections=10, idle_timeout_s=300.0)


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
def tcp_list_connections() -> List[ConnectionInfo]:
    """
    列出当前连接池中所有活跃连接的状态快照。

    @return 活跃连接的列表，包含 conn_id, host, port, idle_seconds, unread_bytes 等
    """
    return pool.list_connections()
