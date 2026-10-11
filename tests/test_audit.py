"""
Traffic Ring Buffer 内存流量审计与综合测试套件。

@author Ateng
@since 2026-10-11
"""

import asyncio
import json

import pytest

from mcp_server_tcp.pool import ConnectionPool


@pytest.mark.asyncio
async def test_traffic_ring_buffer_record_and_dump() -> None:
    """验证收发流量自动被记录至 Traffic Ring Buffer 并支持按 limit 回溯。"""
    server_writers = []

    async def _echo_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        while not reader.at_eof():
            data = await reader.read(1024)
            if not data:
                break
            writer.write(b"ECHO:" + data)
            await writer.drain()

    server = await asyncio.start_server(_echo_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool()

    try:
        conn = await pool.connect("127.0.0.1", port)

        # 1. 初始状态下无流量记录
        init_dump = pool.dump_traffic(conn.conn_id)
        assert init_dump["total_records"] == 0
        assert len(init_dump["records"]) == 0

        # 2. 发送文本
        await pool.send_text(conn.conn_id, "TEST_OUT")
        dump_after_send = pool.dump_traffic(conn.conn_id)
        assert dump_after_send["total_records"] == 1
        rec_out = dump_after_send["records"][0]
        assert rec_out["direction"] == "OUT"
        assert rec_out["bytes_count"] == len(b"TEST_OUT")
        assert "TEST_OUT" in rec_out["text_preview"]

        # 3. 接收响应
        recv_res = await pool.recv_text(conn.conn_id, timeout_ms=1000)
        assert recv_res["text"] == "ECHO:TEST_OUT"

        dump_after_recv = pool.dump_traffic(conn.conn_id)
        assert dump_after_recv["total_records"] == 2
        rec_in = dump_after_recv["records"][1]
        assert rec_in["direction"] == "IN"
        assert rec_in["bytes_count"] == len(b"ECHO:TEST_OUT")
        assert "ECHO:TEST_OUT" in rec_in["text_preview"]

        # 4. 验证 limit 参数限制
        limited_dump = pool.dump_traffic(conn.conn_id, limit=1)
        assert len(limited_dump["records"]) == 1
        assert limited_dump["records"][0]["direction"] == "IN"
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
            await w.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_traffic_dump_and_resource_tools() -> None:
    """验证 MCP Tool tcp_dump_traffic 与 MCP Resource 资源订阅返回有效 JSON。"""
    from mcp_server_tcp.server import (
        get_connection_traffic_resource,
        tcp_connect,
        tcp_disconnect,
        tcp_dump_traffic,
        tcp_send_text,
    )

    server_writers = []

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        conn_res = await tcp_connect("127.0.0.1", port)
        conn_id = conn_res["conn_id"]
        assert conn_id is not None

        await tcp_send_text(conn_id, "RESOURCE_CHECK")

        # 1. 验证 Tool tcp_dump_traffic
        dump_tool = tcp_dump_traffic(conn_id)
        assert dump_tool["total_records"] == 1
        assert dump_tool["records"][0]["direction"] == "OUT"

        # 2. 验证 Resource get_connection_traffic_resource
        res_content = get_connection_traffic_resource(conn_id)
        parsed = json.loads(res_content)
        assert parsed["conn_id"] == conn_id
        assert parsed["total_records"] == 1
        assert parsed["records"][0]["direction"] == "OUT"

        await tcp_disconnect(conn_id)
    finally:
        for w in server_writers:
            w.close()
            await w.wait_closed()
        server.close()
        await server.wait_closed()
