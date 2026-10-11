"""
双工收发与软超时机制测试套件。

@author Ateng
@since 2026-10-11
"""

import asyncio
import pytest

from mcp_server_tcp.pool import ConnectionPool


@pytest.mark.asyncio
async def test_stream_send_and_recv_text() -> None:
    """验证文本双工收发与定界符切包。"""
    server_writers = []

    async def _echo_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        while not reader.at_eof():
            line = await reader.readline()
            if not line:
                break
            writer.write(b"ACK: " + line)
            await writer.drain()

    server = await asyncio.start_server(_echo_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool()

    try:
        conn = await pool.connect("127.0.0.1", port)
        # 1. 发送带 CRLF 的文本
        send_res = await pool.send_text(conn.conn_id, "PING", append_crlf=True)
        assert send_res["success"] is True
        assert send_res["bytes_sent"] == len(b"PING\r\n")

        # 2. 接收响应（以 \r\n 为定界符）
        recv_res = await pool.recv_text(conn.conn_id, timeout_ms=1000, delimiter="\r\n")
        assert recv_res["text"] == "ACK: PING\r\n"
        assert recv_res["timed_out"] is False
        assert recv_res["closed"] is False
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
            await w.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_stream_send_and_recv_hex() -> None:
    """验证 Hex 二进制数据双工收发。"""
    server_writers = []

    async def _hex_echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        data = await reader.read(10)
        writer.write(data)
        await writer.drain()

    server = await asyncio.start_server(_hex_echo, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool()

    try:
        conn = await pool.connect("127.0.0.1", port)
        # 发送 01 02 03 04
        send_res = await pool.send_hex(conn.conn_id, "01 02 03 04")
        assert send_res["success"] is True
        assert send_res["bytes_sent"] == 4

        # 接收 Hex 数据
        recv_res = await pool.recv_hex(conn.conn_id, timeout_ms=1000, max_bytes=4)
        assert recv_res["hex_string"] == "01 02 03 04"
        assert recv_res["bytes_read"] == 4
        assert recv_res["timed_out"] is False
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
            await w.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_stream_soft_timeout() -> None:
    """验证软超时宽容返回当前部分数据且不抛出致命异常。"""
    server_writers = []

    async def _slow_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        # 发送部分未带有换行的数据后暂停
        writer.write(b"PARTIAL_DATA")
        await writer.drain()
        await asyncio.sleep(1.0)

    server = await asyncio.start_server(_slow_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool()

    try:
        conn = await pool.connect("127.0.0.1", port)
        # 请求带 \n 的定界符，但设置极短超时 200ms
        recv_res = await pool.recv_text(conn.conn_id, timeout_ms=200, delimiter="\n")
        assert recv_res["timed_out"] is True
        assert recv_res["text"] == "PARTIAL_DATA"
        assert recv_res["closed"] is False
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
            await w.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_stream_drain_after_peer_closed() -> None:
    """验证对端关闭（FIN/EOF）后仍可优雅读取残余数据并正确标记 closed。"""
    server_writers = []

    async def _close_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        writer.write(b"FINAL_MESSAGE")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(_close_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool()

    try:
        conn = await pool.connect("127.0.0.1", port)
        await asyncio.sleep(0.1)  # 等待对端发送并关闭

        recv_res = await pool.recv_text(conn.conn_id, timeout_ms=1000)
        assert recv_res["text"] == "FINAL_MESSAGE"
        assert recv_res["closed"] is True
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_server_stream_tools() -> None:
    """验证 MCP Tool 层的 tcp_send_text, tcp_send_hex, tcp_recv_text, tcp_recv_hex。"""
    from mcp_server_tcp.server import (
        tcp_connect,
        tcp_disconnect,
        tcp_recv_hex,
        tcp_recv_text,
        tcp_send_hex,
        tcp_send_text,
    )

    server_writers = []

    async def _echo_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        while not reader.at_eof():
            data = await reader.read(1024)
            if not data:
                break
            writer.write(data)
            await writer.drain()

    server = await asyncio.start_server(_echo_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        conn_res = await tcp_connect("127.0.0.1", port)
        conn_id = conn_res["conn_id"]
        assert conn_id is not None

        # 1. 文本测试
        send_t = await tcp_send_text(conn_id, "HELLO", append_crlf=True)
        assert send_t["success"] is True
        recv_t = await tcp_recv_text(conn_id, timeout_ms=1000, delimiter="\r\n")
        assert recv_t["text"] == "HELLO\r\n"

        # 2. Hex 测试
        send_h = await tcp_send_hex(conn_id, "AA BB CC")
        assert send_h["success"] is True
        recv_h = await tcp_recv_hex(conn_id, timeout_ms=1000, max_bytes=3)
        assert recv_h["hex_string"] == "aa bb cc"

        await tcp_disconnect(conn_id)
    finally:
        for w in server_writers:
            w.close()
        server.close()
        await server.wait_closed()

