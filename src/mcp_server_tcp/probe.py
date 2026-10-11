"""
网络探针与单次通信工具集实现。

@author Ateng
@since 2026-10-11
"""

import asyncio
import time
from typing import Any, Dict, List

from mcp_server_tcp.security import SSRFSecurityError, validate_target

__all__ = [
    "SSRFSecurityError",
    "tcp_ping_port",
    "tcp_port_scan",
    "tcp_send_once",
]


async def tcp_ping_port(
    host: str,
    port: int,
    timeout_ms: int = 3000,
) -> Dict[str, Any]:
    """
    测量到目标主机的 TCP 握手时延与端口可达性。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口
    @param timeout_ms 超时时间（毫秒，默认 3000）
    @return 探测结果字典，包含 connected、latency_ms、error 等字段
    @throws SSRFSecurityError 若目标命中 SSRF 防御黑名单
    """
    validate_target(host, port)
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
        return {
            "connected": True,
            "host": host,
            "port": port,
            "latency_ms": round(latency_ms, 2),
            "error": None,
        }
    except asyncio.TimeoutError:
        return {
            "connected": False,
            "host": host,
            "port": port,
            "latency_ms": None,
            "error": f"Connection timed out after {timeout_ms}ms",
        }
    except Exception as exc:
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
) -> Dict[str, Any]:
    """
    并发扫描目标主机的指定端口列表。

    @param host 目标主机域名或 IP
    @param ports 待扫描的端口列表
    @param timeout_ms 单个端口探测超时时间（毫秒，默认 1000）
    @return 扫描结果字典，包含 host、results 及 open_ports 汇总
    @throws SSRFSecurityError 若目标命中 SSRF 防御黑名单
    """
    tasks = [tcp_ping_port(host, p, timeout_ms=timeout_ms) for p in ports]
    scan_results = await asyncio.gather(*tasks)

    results: List[Dict[str, Any]] = []
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
) -> Dict[str, Any]:
    """
    建立短连接、发送单次数据并读取响应，随后立即优雅关闭连接。

    @param host 目标主机域名或 IP
    @param port 目标 TCP 端口
    @param data 待发送数据（文本或 Hex 字符串）
    @param encoding 编码格式，支持 "utf-8" 或 "hex"
    @param timeout_ms 操作整体超时时间（毫秒，默认 5000）
    @return 通信结果字典，包含 sent_bytes、received_bytes、response_data、error 等
    @throws SSRFSecurityError 若目标命中 SSRF 防御黑名单
    """
    validate_target(host, port)
    timeout_s = timeout_ms / 1000.0

    # 1. 序列化请求负载
    normalized_encoding = encoding.lower()
    if normalized_encoding == "hex":
        clean_hex = "".join(data.split())
        payload = bytes.fromhex(clean_hex)
    else:
        payload = data.encode(encoding)

    async def _send_and_recv() -> Dict[str, Any]:
        reader, writer = await asyncio.open_connection(host, port)
        try:
            # 2. 发送请求数据并刷入网络
            writer.write(payload)
            await writer.drain()

            # 3. 读取响应（单次短连接读取至 EOF 或缓冲区数据）
            # 读取最大 65536 字节
            raw_response = await reader.read(65536)

            # 4. 格式化响应输出
            if normalized_encoding == "hex":
                response_str = raw_response.hex(" ")
            else:
                response_str = raw_response.decode(encoding, errors="replace")

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
        return {
            "success": False,
            "host": host,
            "port": port,
            "sent_bytes": len(payload) if "payload" in locals() else 0,
            "received_bytes": 0,
            "response_data": None,
            "error": str(exc),
        }
