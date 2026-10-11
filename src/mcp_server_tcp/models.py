"""
网络探针与单次通信相关的数据模型定义。

@author Ateng
@since 2026-10-11
"""

from typing import List, Optional, TypedDict


class PingResult(TypedDict):
    """TCP 端口握手时延与连通性检测结果。"""

    connected: bool
    host: str
    port: int
    latency_ms: Optional[float]
    error: Optional[str]


class PortScanItem(TypedDict):
    """单个端口扫描详情项。"""

    port: int
    open: bool
    latency_ms: Optional[float]
    error: Optional[str]


class PortScanResult(TypedDict):
    """目标主机多端口批量扫描结果汇总。"""

    host: str
    scanned_count: int
    open_ports: List[int]
    results: List[PortScanItem]


class SendOnceResult(TypedDict):
    """单次短连接请求-响应通信结果。"""

    success: bool
    host: str
    port: int
    sent_bytes: int
    received_bytes: int
    response_data: Optional[str]
    error: Optional[str]
