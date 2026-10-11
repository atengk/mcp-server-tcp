"""
网络探针与单次通信相关测试套件。

@author Ateng
@since 2026-10-11
"""

import asyncio

import pytest

from mcp_server_tcp.probe import (
    SSRFSecurityError,
    tcp_ping_port,
    tcp_port_scan,
    tcp_send_once,
)


@pytest.mark.asyncio
async def test_tcp_ping_port_success() -> None:
    """验证探测本地开放端口成功并返回时延。"""
    # 1. 启动本地回环监听服务
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        # 2. 执行 ping 检测
        result = await tcp_ping_port("127.0.0.1", port, timeout_ms=1000)
        assert result["connected"] is True
        assert result["host"] == "127.0.0.1"
        assert result["port"] == port
        assert result["latency_ms"] >= 0.0
        assert result["error"] is None
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_tcp_ping_port_closed() -> None:
    """验证探测未开放端口返回失败。"""
    result = await tcp_ping_port("127.0.0.1", 65530, timeout_ms=200)
    assert result["connected"] is False
    assert result["error"] is not None
    assert result["latency_ms"] is None


@pytest.mark.asyncio
async def test_tcp_ping_port_ssrf_protection() -> None:
    """验证对云元数据敏感 IP 的 SSRF 拦截防御。"""
    with pytest.raises(SSRFSecurityError, match="SSRF"):
        await tcp_ping_port("169.254.169.254", 80)


@pytest.mark.asyncio
async def test_tcp_port_scan() -> None:
    """验证批量端口扫描能正确区分开放与关闭端口。"""
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    open_port = server.sockets[0].getsockname()[1]
    closed_port = 65531

    try:
        scan_res = await tcp_port_scan("127.0.0.1", [open_port, closed_port], timeout_ms=500)
        assert scan_res["host"] == "127.0.0.1"
        assert scan_res["scanned_count"] == 2
        assert open_port in scan_res["open_ports"]
        assert closed_port not in scan_res["open_ports"]
        assert len(scan_res["results"]) == 2
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_tcp_send_once_text() -> None:
    """验证单次短连接文本收发。"""

    async def echo_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(1024)
        writer.write(b"ECHO: " + data)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(echo_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        res = await tcp_send_once("127.0.0.1", port, "Hello TCP", encoding="utf-8", timeout_ms=1000)
        assert res["success"] is True
        assert res["sent_bytes"] == len("Hello TCP")
        assert res["response_data"] == "ECHO: Hello TCP"
        assert res["error"] is None
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_tcp_send_once_hex() -> None:
    """验证单次短连接十六进制 Hex 收发。"""

    async def hex_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(1024)
        # 反转字节作为回显
        writer.write(bytes(reversed(data)))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(hex_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    try:
        # 发送 01 02 03
        res = await tcp_send_once("127.0.0.1", port, "01 02 03", encoding="hex", timeout_ms=1000)
        assert res["success"] is True
        assert res["sent_bytes"] == 3
        assert res["response_data"] == "03 02 01"
        assert res["error"] is None
    finally:
        server.close()
        await server.wait_closed()
