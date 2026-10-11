"""
长连接会话池与生命周期管理器测试套件。

@author Ateng
@since 2026-10-11
"""

import asyncio
import pytest

from mcp_server_tcp.pool import ConnectionPool, MaxConnectionsReachedError
from mcp_server_tcp.security import SSRFSecurityError


@pytest.mark.asyncio
async def test_pool_connect_and_disconnect() -> None:
    """验证长连接建立、分配唯一 conn_id 以及断开释放。"""
    # 1. 启动本地回环服务器并安全收集连接
    server_writers = []

    async def _handle(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        server_writers.append(w)

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool(max_connections=5, idle_timeout_s=60.0)

    try:
        # 2. 建立长连接
        conn = await pool.connect("127.0.0.1", port, timeout_ms=1000)
        assert conn.conn_id.startswith("c_")
        assert conn.host == "127.0.0.1"
        assert conn.port == port
        assert conn.is_active is True

        # 3. 检查列表中存在该连接
        conns_info = pool.list_connections()
        assert len(conns_info) == 1
        assert conns_info[0]["conn_id"] == conn.conn_id
        assert conns_info[0]["host"] == "127.0.0.1"
        assert conns_info[0]["port"] == port
        assert conns_info[0]["unread_bytes"] == 0

        # 4. 断开连接并验证释放
        disconnected = await pool.disconnect(conn.conn_id)
        assert disconnected is True
        assert len(pool.list_connections()) == 0
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
        server.close()
        await server.wait_closed()



@pytest.mark.asyncio
async def test_pool_max_connections_limit() -> None:
    """验证超过最大连接数配额时抛出 MaxConnectionsReachedError。"""
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool(max_connections=2, idle_timeout_s=60.0)

    try:
        conn1 = await pool.connect("127.0.0.1", port, timeout_ms=1000)
        conn2 = await pool.connect("127.0.0.1", port, timeout_ms=1000)
        assert len(pool.list_connections()) == 2

        with pytest.raises(MaxConnectionsReachedError, match="Max connections"):
            await pool.connect("127.0.0.1", port, timeout_ms=1000)

        # 断开一个后可再连
        await pool.disconnect(conn1.conn_id)
        conn3 = await pool.connect("127.0.0.1", port, timeout_ms=1000)
        assert conn3.conn_id != conn1.conn_id
        assert len(pool.list_connections()) == 2
    finally:
        await pool.close_all()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_pool_idle_reaper() -> None:
    """验证后台协程自动回收超期未活动连接。"""
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    # 设置极短空闲超时 0.2 秒，并在 0.1 秒轮询一次
    pool = ConnectionPool(max_connections=5, idle_timeout_s=0.2, reaper_interval_s=0.1)

    try:
        await pool.start_reaper()
        conn = await pool.connect("127.0.0.1", port, timeout_ms=1000)
        assert len(pool.list_connections()) == 1

        # 等待超过 0.3 秒，应被自动回收
        await asyncio.sleep(0.35)
        assert len(pool.list_connections()) == 0
    finally:
        await pool.close_all()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_pool_ssrf_intercept() -> None:
    """验证长连接建立时同样触发 SSRF 安全拦截。"""
    pool = ConnectionPool(max_connections=5, idle_timeout_s=60.0)
    try:
        with pytest.raises(SSRFSecurityError, match="SSRF"):
            await pool.connect("169.254.169.254", 80)
    finally:
        await pool.close_all()


@pytest.mark.asyncio
async def test_server_connection_tools() -> None:
    """验证暴露给 MCP Client 的 tcp_connect, tcp_disconnect, tcp_list_connections 工具。"""
    from mcp_server_tcp.server import tcp_connect, tcp_disconnect, tcp_list_connections

    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        # 1. 调用 tcp_connect
        conn_res = await tcp_connect("127.0.0.1", port, timeout_ms=1000)
        assert conn_res["connected"] is True
        conn_id = conn_res["conn_id"]
        assert conn_id is not None
        assert conn_res["error"] is None

        # 2. 调用 tcp_list_connections
        conns = tcp_list_connections()
        assert len(conns) >= 1
        matched = [c for c in conns if c["conn_id"] == conn_id]
        assert len(matched) == 1
        assert matched[0]["host"] == "127.0.0.1"
        assert matched[0]["port"] == port

        # 3. 调用 tcp_disconnect
        dis_res = await tcp_disconnect(conn_id)
        assert dis_res["disconnected"] is True
        assert dis_res["conn_id"] == conn_id

        # 再次断开已关闭的连接
        dis_res_again = await tcp_disconnect(conn_id)
        assert dis_res_again["disconnected"] is False
    finally:
        server.close()
        await server.wait_closed()

