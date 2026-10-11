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


class StartServerResult(TypedDict):
    """启动 Mock Server 结果契约。"""

    server_id: Optional[str]
    host: str
    port: int
    started: bool
    error: Optional[str]


class StopServerResult(TypedDict):
    """停止 Mock Server 结果契约。"""

    server_id: str
    stopped: bool
    closed_connections_count: int
    message: str


class BroadcastResult(TypedDict):
    """向 Mock Server 附属客户端广播报文操作结果契约。"""

    server_id: str
    recipients_count: int
    success_count: int
    failed_count: int
    error: Optional[str]


class TrafficRecord(TypedDict):
    """单条流量审计记录项契约。"""

    timestamp: float
    direction: str  # "IN" 或 "OUT"
    bytes_count: int
    hex_preview: str
    text_preview: str


class TrafficDumpResult(TypedDict):
    """流量审计记录回溯结果契约。"""

    conn_id: str
    total_records: int
    records: List[TrafficRecord]
