"""
Mock Server 服务端监听、客户端纳管与广播机制测试套件。

@author Ateng
@since 2026-10-11
"""

import asyncio
import pytest

from mcp_server_tcp.pool import ConnectionPool


@pytest.mark.asyncio
async def test_mock_server_start_accept_and_stop() -> None:
    """验证 Mock Server 启动、外部客户端连入纳管与停服清理。"""
    pool = ConnectionPool()

    try:
        # 1. 启动 Mock Server
        server_res = await pool.start_server(host="127.0.0.1", port=0)
        assert server_res["started"] is True
        server_id = server_res["server_id"]
        assert server_id is not None
        assigned_port = server_res["port"]
        assert assigned_port > 0

        # 2. 外部客户端连入
        reader, writer = await asyncio.open_connection("127.0.0.1", assigned_port)
        await asyncio.sleep(0.1)  # 等待 accept 并注册入池

        # 3. 验证连接池已自动收纳该入站客户端连接
        conns = pool.list_connections()
        inbound = [c for c in conns if c["conn_id"].startswith(f"srv_{server_id}_")]
        assert len(inbound) == 1
        client_conn_id = inbound[0]["conn_id"]

        # 4. 服务端向该连入客户端发送数据，客户端验证接收
        await pool.send_text(client_conn_id, "WELCOME", append_crlf=True)
        received_line = await reader.readline()
        assert received_line == b"WELCOME\r\n"

        # 5. 客户端向服务端回送数据，服务端通过常规 recv_text 接收
        writer.write(b"CLIENT_MSG\r\n")
        await writer.drain()

        recv_res = await pool.recv_text(client_conn_id, timeout_ms=1000, delimiter="\r\n")
        assert recv_res["text"] == "CLIENT_MSG\r\n"

        # 6. 关闭外部客户端并停止 Mock Server
        writer.close()
        await writer.wait_closed()

        stop_res = await pool.stop_server(server_id)
        assert stop_res["stopped"] is True
    finally:
        await pool.close_all()


@pytest.mark.asyncio
async def test_mock_server_broadcast() -> None:
    """验证向 Mock Server 附属的所有活跃客户端多路广播报文。"""
    pool = ConnectionPool()

    try:
        # 1. 启动 Mock Server
        server_res = await pool.start_server(host="127.0.0.1", port=0)
        server_id = server_res["server_id"]
        assert server_id is not None
        port = server_res["port"]

        # 2. 连接 2 个外部客户端
        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        r2, w2 = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.1)

        # 3. 广播文本消息
        b_res = await pool.broadcast(server_id, text="BROADCAST_ALL\r\n")
        assert b_res["recipients_count"] == 2
        assert b_res["success_count"] == 2
        assert b_res["failed_count"] == 0

        # 4. 两个客户端均成功收到广播
        msg1 = await r1.readline()
        msg2 = await r2.readline()
        assert msg1 == b"BROADCAST_ALL\r\n"
        assert msg2 == b"BROADCAST_ALL\r\n"

        # 5. 清理外部客户端
        w1.close()
        w2.close()
        await w1.wait_closed()
        await w2.wait_closed()
    finally:
        await pool.close_all()


@pytest.mark.asyncio
async def test_server_mock_tools() -> None:
    """验证 MCP Tool 层的 tcp_start_server, tcp_stop_server, tcp_broadcast。"""
    from mcp_server_tcp.server import tcp_broadcast, tcp_start_server, tcp_stop_server

    start_res = await tcp_start_server("127.0.0.1", 0)
    assert start_res["started"] is True
    server_id = start_res["server_id"]
    assert server_id is not None
    port = start_res["port"]

    try:
        r, w = await asyncio.open_connection("127.0.0.1", port)
        await asyncio.sleep(0.1)

        b_res = await tcp_broadcast(server_id, text="TEST_BCAST", append_crlf=True)
        assert b_res["success_count"] == 1
        line = await r.readline()
        assert line == b"TEST_BCAST\r\n"

        w.close()
        await w.wait_closed()
    finally:
        stop_res = await tcp_stop_server(server_id)
        assert stop_res["stopped"] is True

