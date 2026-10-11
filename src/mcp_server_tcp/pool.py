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

from mcp_server_tcp.models import ConnectionInfo
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
        # 预留给 ADR-0002 的残余未读内存队列
        self.drain_buffer = bytearray()

    @property
    def is_active(self) -> bool:
        """连接是否保持活跃且未关闭。"""
        return not self._is_closed and not self.writer.is_closing()

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
        # 未读缓冲字节数：drain_buffer 长度加上 reader 内部缓冲区长度（如有）
        unread = len(self.drain_buffer)
        if hasattr(self.reader, "_buffer"):
            unread += len(self.reader._buffer)  # type: ignore[attr-defined]

        return {
            "conn_id": self.conn_id,
            "host": self.host,
            "port": self.port,
            "created_at": round(self.created_at, 2),
            "idle_seconds": round(self.idle_seconds, 2),
            "unread_bytes": unread,
            "is_active": self.is_active,
        }


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
            # 1. 检查并清理死连接，核验容量配额
            self._prune_inactive()
            if len(self._connections) >= self.max_connections:
                raise MaxConnectionsReachedError(
                    f"Max connections limit ({self.max_connections}) reached."
                )

            # 2. 建立底层 TCP 套接字
            timeout_s = timeout_ms / 1000.0
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout_s,
            )

            # 3. 分配全局唯一标识并登记入池
            conn_id = f"c_{uuid.uuid4().hex[:8]}"
            conn = Connection(conn_id, host, port, reader, writer)
            self._connections[conn_id] = conn
            logger.info("Connection established: %s -> %s:%d", conn_id, host, port)
            return conn

    def register_server_connection(
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
        """关闭连接池中的所有连接并终止回收协程。"""
        if self._reaper_task:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None

        async with self._lock:
            for conn in list(self._connections.values()):
                await conn.close()
            self._connections.clear()
