"""
服务端运行期环境配置模块。

@author Ateng
@since 2026-10-11
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerConfig:
    """
    TCP MCP 服务端运行时核心配置类。
    """

    max_connections: int = 10
    idle_timeout_seconds: float = 300.0
    allow_private_networks: bool = True

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """
        从系统环境变量中加载配置，支持安全回退默认值。

        @return ServerConfig 实例
        """
        # 1. 最大并发连接数
        raw_max_conns = os.getenv("MCP_TCP_MAX_CONNECTIONS", "10")
        try:
            max_connections = int(raw_max_conns)
            if max_connections <= 0:
                max_connections = 10
        except ValueError:
            max_connections = 10

        # 2. 空闲超时秒数
        raw_idle_timeout = os.getenv("MCP_TCP_IDLE_TIMEOUT_SECONDS", "300.0")
        try:
            idle_timeout_seconds = float(raw_idle_timeout)
            if idle_timeout_seconds <= 0:
                idle_timeout_seconds = 300.0
        except ValueError:
            idle_timeout_seconds = 300.0

        # 3. 是否允许私有网段/本地回环连接
        raw_allow_private = os.getenv("MCP_TCP_ALLOW_PRIVATE_NETWORKS", "true").lower()
        allow_private_networks = raw_allow_private not in ("false", "0", "no", "off")

        return cls(
            max_connections=max_connections,
            idle_timeout_seconds=idle_timeout_seconds,
            allow_private_networks=allow_private_networks,
        )
