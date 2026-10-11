"""
安全防御模块，提供目标地址与端口的异步非阻塞 SSRF 检测机制。

@author Ateng
@since 2026-10-11
"""

import asyncio
import ipaddress
import logging
import socket
from typing import List

logger = logging.getLogger("mcp_server_tcp.security")

# 云厂商元数据以及常见危险敏感 IP 网段
BLOCKED_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("169.254.169.254/32"),  # AWS/GCP/Azure/OpenStack 元数据服务
    ipaddress.ip_network("100.100.100.200/32"),  # 阿里云元数据服务
]


class SSRFSecurityError(ValueError):
    """当目标地址触发 SSRF 安全防御规则时抛出。"""

    pass


async def validate_target(host: str, port: int) -> None:
    """
    异步校验目标主机与端口的合法性，拦截 SSRF 风险目标。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口 (1-65535)
    @throws SSRFSecurityError 当目标主机命中黑名单时抛出
    @throws ValueError 当端口范围非法时抛出
    """
    if not (1 <= port <= 65535):
        raise ValueError(f"Port out of range (1-65535): {port}")

    # 1. 尝试直接解析为 IP 地址进行黑名单匹配
    try:
        ip_obj = ipaddress.ip_address(host)
        for network in BLOCKED_NETWORKS:
            if ip_obj in network:
                logger.warning(
                    "Blocked connection to dangerous IP %s (matched %s)",
                    host,
                    network,
                )
                raise SSRFSecurityError(f"Target IP {host} is blocked by SSRF defense policy.")
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
            for network in BLOCKED_NETWORKS:
                if ip_obj in network:
                    logger.warning(
                        "Blocked host %s resolved to dangerous IP %s (matched %s)",
                        host,
                        ip_str,
                        network,
                    )
                    raise SSRFSecurityError(
                        f"Resolved IP {ip_str} for host '{host}' is blocked by SSRF defense policy."
                    )
    except socket.gaierror:
        # DNS 解析失败留给底层连接逻辑抛出网络异常
        pass
