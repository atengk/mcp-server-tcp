"""
网络探针与单次通信工具集实现。

@author Ateng
@since 2026-10-11
"""

import asyncio
import logging
import time
from typing import List

from mcp_server_tcp.models import PingResult, PortScanItem, PortScanResult, SendOnceResult
from mcp_server_tcp.security import SSRFSecurityError, validate_target

logger = logging.getLogger("mcp_server_tcp.probe")

__all__ = [
    "PingResult",
    "PortScanItem",
    "PortScanResult",
    "SSRFSecurityError",
    "SendOnceResult",
    "tcp_ping_port",
    "tcp_port_scan",
    "tcp_send_once",
]


async def tcp_ping_port(
    host: str,
    port: int,
    timeout_ms: int = 3000,
    skip_validation: bool = False,
) -> PingResult:
    """
    测量到目标主机的 TCP 握手时延与端口可达性。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口
    @param timeout_ms 超时时间（毫秒，默认 3000）
    @param skip_validation 是否跳过安全校验（仅供批量扫描已前置校验场景内部使用）
    @return 探测结果 PingResult
    @throws SSRFSecurityError 若目标命中 SSRF 防御黑名单
    """
    if not skip_validation:
        await validate_target(host, port)

    timeout_s = timeout_ms / 1000.0
    start_time = time.perf_counter()

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_s,
        )
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        writer.close()
        await writer.wait_closed()
        logger.debug("Ping %s:%d success, latency=%.2fms", host, port, latency_ms)
        return {
            "connected": True,
            "host": host,
            "port": port,
            "latency_ms": round(latency_ms, 2),
            "error": None,
        }
    except asyncio.TimeoutError:
        logger.debug("Ping %s:%d timed out after %dms", host, port, timeout_ms)
        return {
            "connected": False,
            "host": host,
            "port": port,
            "latency_ms": None,
            "error": f"Connection timed out after {timeout_ms}ms",
        }
    except Exception as exc:
        logger.debug("Ping %s:%d failed: %s", host, port, exc)
        return {
            "connected": False,
            "host": host,
            "port": port,
            "latency_ms": None,
            "error": str(exc),
        }


async def tcp_port_scan(
    host: str,
    ports: List[int],
    timeout_ms: int = 1000,
) -> PortScanResult:
    """
    并发扫描目标主机的指定端口列表。

    前置进行一次全局 SSRF 安全校验，避免对同主机重复进行多轮 DNS 查询。

    @param host 目标主机域名或 IP
    @param ports 待扫描的端口列表
    @param timeout_ms 单个端口探测超时时间（毫秒，默认 1000）
    @return 扫描结果汇总 PortScanResult
    @throws SSRFSecurityError 若目标命中 SSRF 防御黑名单
    """
    # 1. 前置安全校验目标主机（使用首个合法端口或默认探测）
    if ports:
        await validate_target(host, ports[0])

    # 2. 并发探测所有指定端口（复用前置校验，跳过单次重复 DNS 查询）
    tasks = [tcp_ping_port(host, p, timeout_ms=timeout_ms, skip_validation=True) for p in ports]
    scan_results = await asyncio.gather(*tasks)

    results: List[PortScanItem] = []
    open_ports: List[int] = []

    for res in scan_results:
        port_num = res["port"]
        is_open = res["connected"]
        if is_open:
            open_ports.append(port_num)
        results.append(
            {
                "port": port_num,
                "open": is_open,
                "latency_ms": res["latency_ms"],
                "error": res["error"],
            }
        )

    logger.info(
        "Port scan on %s completed: %d scanned, %d open",
        host,
        len(ports),
        len(open_ports),
    )
    return {
        "host": host,
        "scanned_count": len(ports),
        "open_ports": open_ports,
        "results": results,
    }


async def tcp_send_once(
    host: str,
    port: int,
    data: str,
    encoding: str = "utf-8",
    timeout_ms: int = 5000,
) -> SendOnceResult:
    """
    建立短连接、发送单次负载数据并读取响应，随后立即优雅关闭连接。

    严格适配 Hex Payload 与 Text Payload 双重格式。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口
    @param data 待发送负载（Text Payload 文本或 Hex Payload 十六进制串）
    @param encoding 编码格式，支持 "utf-8" 或 "hex"
    @param timeout_ms 操作整体超时时间（毫秒，默认 5000）
    @return 通信结果 SendOnceResult
    @throws SSRFSecurityError 若目标命中 SSRF 防御黑名单
    """
    await validate_target(host, port)
    timeout_s = timeout_ms / 1000.0

    # 1. 序列化请求负载 (Hex Payload 或 Text Payload)
    normalized_encoding = encoding.lower()
    if normalized_encoding == "hex":
        clean_hex = "".join(data.split())
        payload = bytes.fromhex(clean_hex)
    else:
        payload = data.encode(encoding)

    async def _send_and_recv() -> SendOnceResult:
        # 2. 建立短连接通道并发送数据
        reader, writer = await asyncio.open_connection(host, port)
        try:
            writer.write(payload)
            await writer.drain()

            # 3. 读取响应（单次短连接读取至 EOF 或已就绪缓冲区数据）
            raw_response = await reader.read(65536)

            # 4. 格式化响应输出
            if normalized_encoding == "hex":
                response_str = raw_response.hex(" ")
            else:
                response_str = raw_response.decode(encoding, errors="replace")

            logger.debug(
                "tcp_send_once to %s:%d success (sent=%d, recv=%d)",
                host,
                port,
                len(payload),
                len(raw_response),
            )
            return {
                "success": True,
                "host": host,
                "port": port,
                "sent_bytes": len(payload),
                "received_bytes": len(raw_response),
                "response_data": response_str,
                "error": None,
            }
        finally:
            writer.close()
            await writer.wait_closed()

    try:
        return await asyncio.wait_for(_send_and_recv(), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning("tcp_send_once to %s:%d timed out after %dms", host, port, timeout_ms)
        return {
            "success": False,
            "host": host,
            "port": port,
            "sent_bytes": len(payload),
            "received_bytes": 0,
            "response_data": None,
            "error": f"Operation timed out after {timeout_ms}ms",
        }
    except Exception as exc:
        logger.warning("tcp_send_once to %s:%d failed: %s", host, port, exc)
        return {
            "success": False,
            "host": host,
            "port": port,
            "sent_bytes": len(payload) if "payload" in locals() else 0,
            "received_bytes": 0,
            "response_data": None,
            "error": str(exc),
        }
