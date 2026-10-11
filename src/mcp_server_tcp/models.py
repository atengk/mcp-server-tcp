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


class ConnectResult(TypedDict):
    """长连接建立结果契约。"""

    connected: bool
    conn_id: Optional[str]
    host: str
    port: int
    error: Optional[str]


class DisconnectResult(TypedDict):
    """关闭长连接操作结果契约。"""

    conn_id: str
    disconnected: bool
    message: str


class ConnectionInfo(TypedDict):
    """活跃连接详情视图契约。"""

    conn_id: str
    host: str
    port: int
    created_at: float
    idle_seconds: float
    unread_bytes: int
    is_active: bool


class SendResult(TypedDict):
    """数据发送操作结果契约。"""

    conn_id: str
    bytes_sent: int
    success: bool
    error: Optional[str]


class RecvTextResult(TypedDict):
    """文本接收操作结果契约（包含软超时与关闭标志）。"""

    conn_id: str
    text: str
    bytes_read: int
    timed_out: bool
    closed: bool
    error: Optional[str]


class RecvHexResult(TypedDict):
    """Hex 二进制接收操作结果契约（包含软超时与关闭标志）。"""

    conn_id: str
    hex_string: str
    bytes_read: int
    timed_out: bool
    closed: bool
    error: Optional[str]

