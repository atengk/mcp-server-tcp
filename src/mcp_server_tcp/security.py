"""
安全防御模块，提供目标地址与端口的异步非阻塞 SSRF 检测机制。

@author Ateng
@since 2026-10-11
"""

import asyncio
import ipaddress
import logging
import socket
from typing import List, Optional

from mcp_server_tcp.config import ServerConfig

logger = logging.getLogger("mcp_server_tcp.security")

# 云厂商元数据服务（任何情况下均绝对强制拦截）
METADATA_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("169.254.169.254/32"),  # AWS/GCP/Azure/OpenStack 元数据服务
    ipaddress.ip_network("100.100.100.200/32"),  # 阿里云元数据服务
]

# RFC 1918 私有内网与回环网段（当配置不允许私有网络时拦截）
PRIVATE_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),  # IPv4 回环
    ipaddress.ip_network("10.0.0.0/8"),  # 私有 A 类
    ipaddress.ip_network("172.16.0.0/12"),  # 私有 B 类
    ipaddress.ip_network("192.168.0.0/16"),  # 私有 C 类
    ipaddress.ip_network("::1/128"),  # IPv6 回环
]


class SSRFSecurityError(ValueError):
    """当目标地址触发 SSRF 安全防御规则时抛出。"""

    pass


def _check_ip_blocked(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    allow_private: bool,
) -> None:
    """内部核验单个 IP 是否被封禁。"""
    # 1. 检查云元数据黑名单（绝对拦截）
    for network in METADATA_NETWORKS:
        if ip_obj in network:
            logger.warning(
                "Blocked connection to cloud metadata IP %s (matched %s)", ip_obj, network
            )
            raise SSRFSecurityError(
                f"Target IP {ip_obj} is blocked by cloud metadata SSRF defense policy."
            )

    # 2. 若关闭了私有网段访问权限，检查是否命中私有网段
    if not allow_private:
        for network in PRIVATE_NETWORKS:
            if ip_obj in network:
                logger.warning(
                    "Blocked connection to private network IP %s (matched %s)", ip_obj, network
                )
                raise SSRFSecurityError(
                    f"Target IP {ip_obj} is a private network address and "
                    "blocked by security policy."
                )


async def validate_target(
    host: str,
    port: int,
    config: Optional[ServerConfig] = None,
) -> None:
    """
    异步校验目标主机与端口的合法性，拦截 SSRF 风险目标。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口 (1-65535)
    @param config 运行时配置实例（若为空则实时从环境变量加载）
    @throws SSRFSecurityError 当目标主机命中黑名单时抛出
    @throws ValueError 当端口范围非法时抛出
    """
    if not (1 <= port <= 65535):
        raise ValueError(f"Port out of range (1-65535): {port}")

    cfg = config or ServerConfig.from_env()

    # 1. 尝试直接解析为 IP 地址进行黑名单匹配
    try:
        ip_obj = ipaddress.ip_address(host)
        _check_ip_blocked(ip_obj, allow_private=cfg.allow_private_networks)
        return
    except ValueError:
        pass

    # 2. 若是主机名/域名，通过 asyncio 执行非阻塞 DNS 解析并校验解析出的地址
    loop = asyncio.get_running_loop()
    try:
        resolved_ips = await loop.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        for entry in resolved_ips:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            _check_ip_blocked(ip_obj, allow_private=cfg.allow_private_networks)
    except socket.gaierror:
        # DNS 解析失败留给底层连接逻辑抛出网络异常
        pass


def validate_bind_host(
    host: str,
    config: Optional[ServerConfig] = None,
) -> None:
    """
    核验 Mock Server 本地监听绑定地址的安全性。

    @param host 待绑定的主机名或 IP
    @param config 运行时配置实例（若为空则实时从环境变量加载）
    @throws SSRFSecurityError 当绑定地址违反安全策略时抛出
    """
    cfg = config or ServerConfig.from_env()
    cleaned = host.strip().lower()
    if cleaned in ("localhost", "127.0.0.1", "::1"):
        return

    try:
        ip_obj = ipaddress.ip_address(cleaned)
    except ValueError:
        ip_obj = None

    if ip_obj:
        if ip_obj.is_loopback:
            return
        for network in METADATA_NETWORKS:
            if ip_obj in network:
                raise SSRFSecurityError(
                    f"Binding to cloud metadata IP {ip_obj} is forbidden."
                )

    if not cfg.allow_private_networks:
        logger.warning(
            "Blocked binding to non-loopback host %s due to private network policy",
            host,
        )
        raise SSRFSecurityError(
            f"Binding Mock Server to non-loopback host '{host}' is forbidden by security policy."
        )

    logger.warning(
        "Mock Server is binding to non-loopback host '%s'. Ensure network exposure is intended.",
        host,
    )

