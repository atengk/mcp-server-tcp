"""
长连接会话池与生命周期自愈管理器实现。

@author Ateng
@since 2026-10-11
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional

from mcp_server_tcp.models import (
    BroadcastResult,
    ConnectionInfo,
    RecvHexResult,
    RecvTextResult,
    SendResult,
    StartServerResult,
    StopServerResult,
)
from mcp_server_tcp.security import SSRFSecurityError, validate_target


logger = logging.getLogger("mcp_server_tcp.pool")

__all__ = [
    "Connection",
    "ConnectionPool",
    "MaxConnectionsReachedError",
]


class MaxConnectionsReachedError(RuntimeError):
    """当活跃连接数达到配置的配额上限时抛出。"""

    pass


class Connection:
    """
    受管 TCP 长连接抽象，封装套接字读写器、唯一标识符与生命周期状态。
    """

    def __init__(
        self,
        conn_id: str,
        host: str,
        port: int,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        is_server_accepted: bool = False,
    ) -> None:
        """
        初始化连接实例。

        @param conn_id 全局唯一连接标识符
        @param host 目标/对端地址
        @param port 目标/对端端口
        @param reader asyncio 流读取器
        @param writer asyncio 流写入器
        @param is_server_accepted 是否为服务端入站接受的连接
        """
        self.conn_id = conn_id
        self.host = host
        self.port = port
        self.reader = reader
        self.writer = writer
        self.is_server_accepted = is_server_accepted
        self.created_at = time.time()
        self.last_active_at = time.time()
        self._is_closed = False
        self._peer_closed = False
        # 遵循 ADR-0002 的残余未读内存队列
        self.drain_buffer = bytearray()
        self._io_lock = asyncio.Lock()

    @property
    def is_active(self) -> bool:
        """连接是否保持活跃且未物理关闭。"""
        return not self._is_closed and not self.writer.is_closing()

    @property
    def is_peer_closed(self) -> bool:
        """对端是否已经发送 FIN/EOF 关闭写通道。"""
        return self._peer_closed or self.reader.at_eof()

    @property
    def idle_seconds(self) -> float:
        """当前空闲持续时长（秒）。"""
        return time.time() - self.last_active_at

    def touch(self) -> None:
        """刷新最近活跃时间戳。"""
        self.last_active_at = time.time()

    async def close(self) -> None:
        """安全关闭底层 TCP 套接字并等待资源释放。"""
        if self._is_closed:
            return
        self._is_closed = True
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception as exc:
            logger.debug("Error while closing connection %s: %s", self.conn_id, exc)

    def to_info(self) -> ConnectionInfo:
        """转换为只读快照字典视图。"""
        unread = len(self.drain_buffer)
        return {
            "conn_id": self.conn_id,
            "host": self.host,
            "port": self.port,
            "created_at": round(self.created_at, 2),
            "idle_seconds": round(self.idle_seconds, 2),
            "unread_bytes": unread,
            "is_active": self.is_active,
        }

    async def send(self, payload: bytes) -> SendResult:
        """
        发送原始字节流到对端。

        @param payload 待发送字节数据
        @return SendResult 发送结果
        """
        if not self.is_active:
            return {
                "conn_id": self.conn_id,
                "bytes_sent": 0,
                "success": False,
                "error": f"Connection {self.conn_id} is already closed.",
            }

        async with self._io_lock:
            try:
                self.writer.write(payload)
                await self.writer.drain()
                self.touch()
                return {
                    "conn_id": self.conn_id,
                    "bytes_sent": len(payload),
                    "success": True,
                    "error": None,
                }
            except Exception as exc:
                logger.warning("Send failed on %s: %s", self.conn_id, exc)
                return {
                    "conn_id": self.conn_id,
                    "bytes_sent": 0,
                    "success": False,
                    "error": str(exc),
                }

    async def recv(
        self,
        timeout_ms: int = 5000,
        delimiter: Optional[bytes] = None,
        max_bytes: Optional[int] = None,
    ) -> tuple[bytes, bool, bool, Optional[str]]:
        """
        底层流式读取，具备软超时 (Soft Timeout) 与优雅排空 (Drain Buffer) 机制。

        @param timeout_ms 超时时间（毫秒）
        @param delimiter 报文切包定界符（可选）
        @param max_bytes 最大读取字节数（可选）
        @return (数据字节, 是否超时 timed_out, 是否对端已关闭 closed, 错误信息 error)
        """
        self.touch()
        timeout_s = timeout_ms / 1000.0

        async with self._io_lock:
            # 1. 优先从当前已有的 drain_buffer 中尝试匹配定界符或字节数
            if delimiter and delimiter in self.drain_buffer:
                idx = self.drain_buffer.index(delimiter) + len(delimiter)
                extracted = bytes(self.drain_buffer[:idx])
                del self.drain_buffer[:idx]
                return extracted, False, self.is_peer_closed, None

            if max_bytes and len(self.drain_buffer) >= max_bytes:
                extracted = bytes(self.drain_buffer[:max_bytes])
                del self.drain_buffer[:max_bytes]
                return extracted, False, self.is_peer_closed, None

            # 若对端已关闭且 drain_buffer 有残余数据，直接取出排空
            if self.is_peer_closed and self.drain_buffer:
                extracted = bytes(self.drain_buffer)
                self.drain_buffer.clear()
                return extracted, False, True, None

            if self.is_peer_closed and not self.drain_buffer:
                return b"", False, True, None

            # 2. 启动异步读取循环
            end_time = time.perf_counter() + timeout_s

            while True:
                remaining_time = end_time - time.perf_counter()
                if remaining_time <= 0:
                    # 软超时：不抛错，宽容返回当前累积的残余数据
                    partial = bytes(self.drain_buffer)
                    self.drain_buffer.clear()
                    return partial, True, self.is_peer_closed, None

                try:
                    chunk = await asyncio.wait_for(
                        self.reader.read(4096),
                        timeout=max(remaining_time, 0.001),
                    )
                except asyncio.TimeoutError:
                    partial = bytes(self.drain_buffer)
                    self.drain_buffer.clear()
                    return partial, True, self.is_peer_closed, None
                except Exception as exc:
                    return bytes(self.drain_buffer), False, True, str(exc)

                if not chunk:
                    # 对端发送了 FIN/EOF
                    self._peer_closed = True
                    partial = bytes(self.drain_buffer)
                    self.drain_buffer.clear()
                    return partial, False, True, None

                self.drain_buffer.extend(chunk)
                if self.reader.at_eof():
                    self._peer_closed = True

                # 3. 检查是否达成定界符条件
                if delimiter and delimiter in self.drain_buffer:
                    idx = self.drain_buffer.index(delimiter) + len(delimiter)
                    extracted = bytes(self.drain_buffer[:idx])
                    del self.drain_buffer[:idx]
                    return extracted, False, self.is_peer_closed, None

                # 4. 检查是否达成最大字节数条件
                if max_bytes and len(self.drain_buffer) >= max_bytes:
                    extracted = bytes(self.drain_buffer[:max_bytes])
                    del self.drain_buffer[:max_bytes]
                    return extracted, False, self.is_peer_closed, None

                # 若未指定 delimiter 且未指定 max_bytes，则首个有效分片即返回
                if not delimiter and not max_bytes:
                    extracted = bytes(self.drain_buffer)
                    self.drain_buffer.clear()
                    return extracted, False, self.is_peer_closed, None



class ConnectionPool:
    """
    集中式连接池管理器，管理活跃连接注册表、空闲回收协程与配额保护。
    """

    def __init__(
        self,
        max_connections: int = 10,
        idle_timeout_s: float = 300.0,
        reaper_interval_s: float = 10.0,
    ) -> None:
        """
        初始化连接池。

        @param max_connections 最大并发连接数配额
        @param idle_timeout_s 空闲超时阈值（秒，默认 300 秒/5分钟）
        @param reaper_interval_s 定期回收协程轮询间隔（秒）
        """
        self.max_connections = max_connections
        self.idle_timeout_s = idle_timeout_s
        self.reaper_interval_s = reaper_interval_s
        self._connections: Dict[str, Connection] = {}
        self._servers: Dict[str, asyncio.Server] = {}
        self._reaper_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()


    async def connect(
        self,
        host: str,
        port: int,
        timeout_ms: int = 5000,
    ) -> Connection:
        """
        发起出站连接，分配唯一 conn_id 并纳入连接池受管。

        @param host 目标主机域名或 IP
        @param port 目标 TCP 端口
        @param timeout_ms 连接建立超时（毫秒）
        @return Connection 实例
        @throws SSRFSecurityError 若触发 SSRF 拦截
        @throws MaxConnectionsReachedError 若连接数已达上限
        """
        await validate_target(host, port)

        async with self._lock:
            self._prune_inactive()
            if len(self._connections) >= self.max_connections:
                raise MaxConnectionsReachedError(
                    f"Max connections limit ({self.max_connections}) reached."
                )

            timeout_s = timeout_ms / 1000.0
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout_s,
            )

            conn_id = f"c_{uuid.uuid4().hex[:8]}"
            conn = Connection(conn_id, host, port, reader, writer)
            self._connections[conn_id] = conn
            logger.info("Connection established: %s -> %s:%d", conn_id, host, port)
            return conn

    async def register_server_connection(
        self,
        server_id: str,
        host: str,
        port: int,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Connection:
        """
        将 Mock Server 接收到的入站客户端连接登记入池（预留给 Issue #5）。

        @param server_id 服务端标识符
        @param host 客户端 IP
        @param port 客户端端口
        @param reader asyncio 流读取器
        @param writer asyncio 流写入器
        @return Connection 实例
        """
        async with self._lock:
            self._prune_inactive()
            if len(self._connections) >= self.max_connections:
                raise MaxConnectionsReachedError(
                    f"Max connections limit ({self.max_connections}) reached."
                )

            conn_id = f"srv_{server_id}_c_{uuid.uuid4().hex[:6]}"
            conn = Connection(conn_id, host, port, reader, writer, is_server_accepted=True)
            self._connections[conn_id] = conn
            logger.info("Inbound connection registered: %s from %s:%d", conn_id, host, port)
            return conn

    async def disconnect(self, conn_id: str) -> bool:
        """
        关闭指定连接并从池中移除。

        @param conn_id 连接全局唯一标识符
        @return 是否成功找到并关闭连接
        """
        async with self._lock:
            conn = self._connections.pop(conn_id, None)
            if conn is None:
                return False
            await conn.close()
            logger.info("Connection closed and removed: %s", conn_id)
            return True

    def get(self, conn_id: str) -> Optional[Connection]:
        """
        获取指定连接并自动更新活跃时间戳。

        @param conn_id 连接唯一标识
        @return Connection 实例或 None
        """
        conn = self._connections.get(conn_id)
        if conn and conn.is_active:
            conn.touch()
            return conn
        return None

    def list_connections(self) -> List[ConnectionInfo]:
        """
        获取当前所有受管连接的视图快照列表。

        @return ConnectionInfo 列表
        """
        self._prune_inactive()
        return [c.to_info() for c in self._connections.values()]

    def _prune_inactive(self) -> None:
        """清理已自然关闭的失效连接。"""
        dead_ids = [cid for cid, c in self._connections.items() if not c.is_active]
        for cid in dead_ids:
            self._connections.pop(cid, None)

    async def reap_idle(self) -> int:
        """
        扫描并回收超过空闲超时阈值的连接。

        @return 被回收的连接数
        """
        async with self._lock:
            reaped_count = 0
            to_remove: List[str] = []
            for cid, conn in self._connections.items():
                if not conn.is_active or conn.idle_seconds >= self.idle_timeout_s:
                    to_remove.append(cid)

            for cid in to_remove:
                conn = self._connections.pop(cid, None)
                if conn:
                    await conn.close()
                    reaped_count += 1
                    logger.info("Reaped idle connection: %s", cid)
            return reaped_count

    async def start_reaper(self) -> None:
        """启动后台自愈协程。"""
        if self._reaper_task and not self._reaper_task.done():
            return

        async def _loop() -> None:
            while True:
                try:
                    await asyncio.sleep(self.reaper_interval_s)
                    await self.reap_idle()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Error during reaper iteration: %s", exc)

        self._reaper_task = asyncio.create_task(_loop())

    async def close_all(self) -> None:
        """关闭连接池中的所有连接、停止所有 Mock Server 并终止回收协程。"""
        if self._reaper_task:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None

        async with self._lock:
            for srv_id, srv in list(self._servers.items()):
                srv.close()
                await srv.wait_closed()
            self._servers.clear()

            for conn in list(self._connections.values()):
                await conn.close()
            self._connections.clear()

    async def start_server(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> StartServerResult:
        """
        启动动态 Mock Server 监听器，被动接受外部客户端连入并自动分配 conn_id 入池。

        @param host 监听绑定的本地主机或 IP（默认 127.0.0.1）
        @param port 监听绑定的本地端口（默认 0，系统随机分配空闲端口）
        @return StartServerResult 启动结果契约
        """
        server_id = f"mock_{uuid.uuid4().hex[:6]}"

        async def _client_connected_cb(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            peer_name = writer.get_extra_info("peername")
            peer_host = peer_name[0] if peer_name else "unknown"
            peer_port = peer_name[1] if peer_name else 0
            try:
                await self.register_server_connection(
                    server_id=server_id,
                    host=peer_host,
                    port=peer_port,
                    reader=reader,
                    writer=writer,
                )
            except Exception as exc:
                logger.error(
                    "Failed to register inbound client for server %s: %s",
                    server_id,
                    exc,
                )
                writer.close()
                await writer.wait_closed()

        try:
            server = await asyncio.start_server(_client_connected_cb, host=host, port=port)
            # 获取实际绑定的端口
            assigned_port = server.sockets[0].getsockname()[1]
            async with self._lock:
                self._servers[server_id] = server

            logger.info("Mock Server %s started on %s:%d", server_id, host, assigned_port)
            return {
                "server_id": server_id,
                "host": host,
                "port": assigned_port,
                "started": True,
                "error": None,
            }
        except Exception as exc:
            logger.error("Failed to start Mock Server on %s:%d: %s", host, port, exc)
            return {
                "server_id": None,
                "host": host,
                "port": port,
                "started": False,
                "error": str(exc),
            }

    async def stop_server(self, server_id: str) -> StopServerResult:
        """
        安全停止指定的 Mock Server 并断开所有归属于该服务端的入站客户端连接。

        @param server_id Mock Server 唯一标识
        @return StopServerResult 停止结果契约
        """
        async with self._lock:
            server = self._servers.pop(server_id, None)
            if not server:
                return {
                    "server_id": server_id,
                    "stopped": False,
                    "closed_connections_count": 0,
                    "message": f"Server {server_id} not found or already stopped.",
                }

            # 1. 停止监听接收新连接
            server.close()
            await server.wait_closed()

            # 2. 级联断开所有该服务端接受的客户端
            closed_count = 0
            prefix = f"srv_{server_id}_"
            for cid in list(self._connections.keys()):
                if cid.startswith(prefix):
                    conn = self._connections.pop(cid)
                    await conn.close()
                    closed_count += 1

            logger.info(
                "Mock Server %s stopped. Closed %d attached clients.",
                server_id,
                closed_count,
            )
            return {
                "server_id": server_id,
                "stopped": True,
                "closed_connections_count": closed_count,
                "message": f"Server {server_id} successfully stopped.",
            }

    async def broadcast(
        self,
        server_id: str,
        text: Optional[str] = None,
        hex_string: Optional[str] = None,
        append_crlf: bool = False,
    ) -> BroadcastResult:
        """
        向指定 Mock Server 下的所有连入活跃客户端同时多路广播报文。

        @param server_id Mock Server 唯一标识
        @param text 待广播的文本数据（Text Payload）
        @param hex_string 待广播的十六进制数据（Hex Payload）
        @param append_crlf 发送文本时是否自动追加 \\r\\n
        @return BroadcastResult 广播结果统计
        """
        if text is None and hex_string is None:
            return {
                "server_id": server_id,
                "recipients_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "error": "Either text or hex_string must be provided.",
            }

        # 准备数据负载
        if hex_string is not None:
            try:
                clean_hex = "".join(hex_string.split())
                payload = bytes.fromhex(clean_hex)
            except ValueError as exc:
                return {
                    "server_id": server_id,
                    "recipients_count": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "error": f"Invalid Hex Payload format: {exc}",
                }
        else:
            payload = text.encode("utf-8")  # type: ignore[union-attr]
            if append_crlf and not payload.endswith(b"\r\n"):
                payload += b"\r\n"

        prefix = f"srv_{server_id}_"
        # 筛选出属于该 server_id 的活跃客户端
        target_conns = [
            conn
            for cid, conn in self._connections.items()
            if cid.startswith(prefix) and conn.is_active
        ]

        if not target_conns:
            return {
                "server_id": server_id,
                "recipients_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "error": None,
            }

        tasks = [conn.send(payload) for conn in target_conns]
        results = await asyncio.gather(*tasks)

        success_count = sum(1 for r in results if r["success"])
        failed_count = len(results) - success_count

        return {
            "server_id": server_id,
            "recipients_count": len(target_conns),
            "success_count": success_count,
            "failed_count": failed_count,
            "error": None,
        }


    async def send_text(
        self,
        conn_id: str,
        text: str,
        append_crlf: bool = False,
    ) -> SendResult:
        """
        发送 UTF-8 文本数据（Text Payload），支持追加 CRLF 行尾符。

        @param conn_id 连接标识
        @param text 待发送文本
        @param append_crlf 是否自动追加 \\r\\n
        @return SendResult 字典
        """
        conn = self.get(conn_id)
        if not conn:
            return {
                "conn_id": conn_id,
                "bytes_sent": 0,
                "success": False,
                "error": f"Connection {conn_id} not found or inactive.",
            }

        payload = text.encode("utf-8")
        if append_crlf and not payload.endswith(b"\r\n"):
            payload += b"\r\n"
        return await conn.send(payload)

    async def send_hex(
        self,
        conn_id: str,
        hex_string: str,
    ) -> SendResult:
        """
        发送十六进制编码的原始二进制字节流（Hex Payload）。

        @param conn_id 连接标识
        @param hex_string 十六进制字符串（支持包含空格）
        @return SendResult 字典
        """
        conn = self.get(conn_id)
        if not conn:
            return {
                "conn_id": conn_id,
                "bytes_sent": 0,
                "success": False,
                "error": f"Connection {conn_id} not found or inactive.",
            }

        try:
            clean_hex = "".join(hex_string.split())
            payload = bytes.fromhex(clean_hex)
        except ValueError as exc:
            return {
                "conn_id": conn_id,
                "bytes_sent": 0,
                "success": False,
                "error": f"Invalid Hex Payload format: {exc}",
            }

        return await conn.send(payload)

    async def recv_text(
        self,
        conn_id: str,
        timeout_ms: int = 5000,
        delimiter: Optional[str] = None,
    ) -> RecvTextResult:
        """
        从连接接收文本数据（Text Payload），支持定界符与软超时宽容返回。

        @param conn_id 连接标识
        @param timeout_ms 超时毫秒数（默认 5000）
        @param delimiter 定界符字符串（如 '\\r\\n' 或 '\\n'）
        @return RecvTextResult 字典
        """
        conn = self.get(conn_id)
        if not conn:
            return {
                "conn_id": conn_id,
                "text": "",
                "bytes_read": 0,
                "timed_out": False,
                "closed": True,
                "error": f"Connection {conn_id} not found or inactive.",
            }

        delimiter_bytes = delimiter.encode("utf-8") if delimiter else None
        data, timed_out, closed, error = await conn.recv(
            timeout_ms=timeout_ms,
            delimiter=delimiter_bytes,
        )

        text_val = data.decode("utf-8", errors="replace")
        return {
            "conn_id": conn_id,
            "text": text_val,
            "bytes_read": len(data),
            "timed_out": timed_out,
            "closed": closed,
            "error": error,
        }

    async def recv_hex(
        self,
        conn_id: str,
        timeout_ms: int = 5000,
        max_bytes: Optional[int] = None,
    ) -> RecvHexResult:
        """
        从连接接收十六进制原始字节流（Hex Payload），支持限制最大字节数与软超时。

        @param conn_id 连接标识
        @param timeout_ms 超时毫秒数（默认 5000）
        @param max_bytes 最大接收字节数
        @return RecvHexResult 字典
        """
        conn = self.get(conn_id)
        if not conn:
            return {
                "conn_id": conn_id,
                "hex_string": "",
                "bytes_read": 0,
                "timed_out": False,
                "closed": True,
                "error": f"Connection {conn_id} not found or inactive.",
            }

        data, timed_out, closed, error = await conn.recv(
            timeout_ms=timeout_ms,
            max_bytes=max_bytes,
        )

        hex_val = data.hex(" ")
        return {
            "conn_id": conn_id,
            "hex_string": hex_val,
            "bytes_read": len(data),
            "timed_out": timed_out,
            "closed": closed,
            "error": error,
        }
