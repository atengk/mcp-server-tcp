"""
ADR-0005 全双工锁分离、半包缓冲保全、探针限流与安全加固验证测试。

@author Ateng
@since 2026-10-11
"""

import asyncio

import pytest

from mcp_server_tcp.config import ServerConfig
from mcp_server_tcp.pool import BufferOverflowError, ConnectionPool
from mcp_server_tcp.probe import tcp_port_scan
from mcp_server_tcp.security import SSRFSecurityError, validate_bind_host
from mcp_server_tcp.server import tcp_list_connections


@pytest.mark.asyncio
async def test_full_duplex_concurrent_send_and_recv() -> None:
    """验证读写锁分离后，挂起的 recv 不会阻塞并发的 send 操作。"""
    server_writers = []
    received_on_server = []

    async def _echo_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        # 持续等待客户端发送，延迟下发数据
        data = await reader.read(1024)
        received_on_server.append(data)
        await asyncio.sleep(0.5)
        writer.write(b"SERVER_REPLY\n")
        await writer.drain()

    server = await asyncio.start_server(_echo_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool()

    try:
        conn = await pool.connect("127.0.0.1", port)

        # 1. 启动一个长超时 recv_text 协程（挂起等待数据）
        recv_task = asyncio.create_task(
            pool.recv_text(conn.conn_id, timeout_ms=3000, delimiter="\n")
        )
        await asyncio.sleep(0.05)  # 确保 recv 已经获取 _read_lock

        # 2. 并发调用 send_text，应立即完成（无需等待 recv 结束）
        start_send = asyncio.get_running_loop().time()
        send_res = await pool.send_text(conn.conn_id, "CLIENT_HELLO\n")
        send_elapsed = asyncio.get_running_loop().time() - start_send

        assert send_res["success"] is True
        assert send_res["bytes_sent"] > 0
        # send 应在极短时间内完成（< 0.1s），未受 _read_lock 阻塞
        assert send_elapsed < 0.2

        # 3. 等待 recv_task 完成并校验全双工应答
        recv_res = await recv_task
        assert recv_res["timed_out"] is False
        assert recv_res["text"] == "SERVER_REPLY\n"
        assert b"CLIENT_HELLO\n" in received_on_server[0]
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
            await w.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_immediate_close_unblocks_active_recv() -> None:
    """验证穿透式 close 能够在挂起 recv 时即时打断并优雅释放资源。"""
    server_writers = []

    async def _hanging_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        await asyncio.sleep(5.0)

    server = await asyncio.start_server(_hanging_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool()

    try:
        conn = await pool.connect("127.0.0.1", port)

        # 启动一个 5000ms 超时的 recv
        recv_task = asyncio.create_task(pool.recv_text(conn.conn_id, timeout_ms=5000))
        await asyncio.sleep(0.05)

        # 主动关闭连接
        start_close = asyncio.get_running_loop().time()
        await pool.disconnect(conn.conn_id)
        recv_res = await recv_task
        elapsed = asyncio.get_running_loop().time() - start_close

        # recv 应该迅速被唤醒返回或退出（< 0.3s），而不是卡死 5s
        assert elapsed < 0.5
        assert recv_res["closed"] is True
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
            await w.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_buffer_overflow_defense(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证累积未定界报文超过安全阈值时触发 BufferOverflowError 熔断。"""
    import mcp_server_tcp.pool as pool_module

    # 将防 OOM 阈值临时设置为 256 字节以供测试
    monkeypatch.setattr(pool_module, "MAX_BUFFER_SIZE", 256)

    server_writers = []

    async def _flood_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        server_writers.append(writer)
        # 发送 500 字节无定界符的数据流
        writer.write(b"A" * 500)
        await writer.drain()

    server = await asyncio.start_server(_flood_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    pool = ConnectionPool()

    try:
        conn = await pool.connect("127.0.0.1", port)
        with pytest.raises(BufferOverflowError):
            await pool.recv_text(conn.conn_id, timeout_ms=2000, delimiter="\n")

        # 验证连接已被主动熔断
        assert conn.is_active is False
    finally:
        await pool.close_all()
        for w in server_writers:
            w.close()
            await w.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_port_scan_limit_and_semaphore() -> None:
    """验证 tcp_port_scan 针对 128 端口上限拦截及并发信号量。"""
    # 1. 超过 128 端口请求触发 ValueError
    oversized_ports = list(range(1, 131))
    with pytest.raises(ValueError, match="exceeds maximum limit of 128"):
        await tcp_port_scan("127.0.0.1", oversized_ports)

    # 2. 正常并发扫描（32 端口以内平滑执行）
    valid_ports = [1024, 1025, 1026]
    res = await tcp_port_scan("127.0.0.1", valid_ports, timeout_ms=200)
    assert res["scanned_count"] == 3
    assert len(res["results"]) == 3


@pytest.mark.asyncio
async def test_topology_metadata_and_filtering() -> None:
    """验证 ConnectionInfo 拓扑字段与 tcp_list_connections 的 server_id 过滤。"""
    pool = ConnectionPool()
    server_res = await pool.start_server(host="127.0.0.1", port=0)
    assert server_res["started"] is True
    server_id = server_res["server_id"]

    try:
        # 外部连入 Mock Server
        reader, writer = await asyncio.open_connection("127.0.0.1", server_res["port"])
        await asyncio.sleep(0.05)

        # 检查连接拓扑信息
        all_conns = pool.list_connections()
        assert len(all_conns) == 1
        accepted_conn = all_conns[0]
        assert accepted_conn["is_server_accepted"] is True
        assert accepted_conn["server_id"] == server_id

        # 按 server_id 过滤
        matched = pool.list_connections(server_id=server_id)
        assert len(matched) == 1
        unmatched = pool.list_connections(server_id="mock_other")
        assert len(unmatched) == 0

        # 测试 MCP 工具封装
        mcp_res = tcp_list_connections(server_id="mock_nonexistent")
        assert len(mcp_res) == 0

        writer.close()
        await writer.wait_closed()
    finally:
        await pool.close_all()


def test_validate_bind_host_security() -> None:
    """验证 Mock Server 绑定地址安全门禁策略。"""
    cfg_strict = ServerConfig(allow_private_networks=False)
    cfg_permissive = ServerConfig(allow_private_networks=True)

    # 回环地址始终允许
    validate_bind_host("127.0.0.1", config=cfg_strict)
    validate_bind_host("localhost", config=cfg_strict)
    validate_bind_host("::1", config=cfg_strict)

    # 元数据服务任何时候均禁止
    with pytest.raises(SSRFSecurityError):
        validate_bind_host("169.254.169.254", config=cfg_permissive)

    # 当禁止私有网络时，禁止绑定 0.0.0.0 或局域网 IP
    with pytest.raises(SSRFSecurityError):
        validate_bind_host("0.0.0.0", config=cfg_strict)
    with pytest.raises(SSRFSecurityError):
        validate_bind_host("192.168.1.100", config=cfg_strict)

    # 当允许私有网络时，允许绑定 0.0.0.0
    validate_bind_host("0.0.0.0", config=cfg_permissive)
