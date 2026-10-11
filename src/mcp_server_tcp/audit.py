"""
双工收发内存环形流量审计缓冲区（Traffic Ring Buffer，遵循 CONTEXT.md 规范）。

@author Ateng
@since 2026-10-11
"""

import collections
import time
from typing import List

from mcp_server_tcp.models import TrafficRecord


class TrafficRingBuffer:
    """
    固定容量（默认 100 条）内存环形审计记录缓冲区。
    """

    def __init__(self, capacity: int = 100) -> None:
        """
        初始化环形缓冲区。

        @param capacity 最大保存记录数（默认 100）
        """
        self.capacity = capacity
        self._buffer: collections.deque[TrafficRecord] = collections.deque(maxlen=capacity)

    def record(self, direction: str, data: bytes) -> None:
        """
        记录一条网络收发报文快照。

        @param direction 传输方向 ("IN" 或 "OUT")
        @param data 报文原始字节数据
        """
        # 截取前 32 字节生成 Hex 和 Text 预览
        preview_bytes = data[:32]
        hex_preview = preview_bytes.hex(" ")
        if len(data) > 32:
            hex_preview += "..."

        text_preview = preview_bytes.decode("utf-8", errors="replace")
        if len(data) > 32:
            text_preview += "..."

        entry: TrafficRecord = {
            "timestamp": round(time.time(), 3),
            "direction": direction,
            "bytes_count": len(data),
            "hex_preview": hex_preview,
            "text_preview": text_preview,
        }
        self._buffer.append(entry)

    def dump(self, limit: int = 100) -> List[TrafficRecord]:
        """
        获取最近的审计记录快照列表（由旧到新）。

        @param limit 最大返回条数
        @return 审计记录列表
        """
        items = list(self._buffer)
        if limit and limit < len(items):
            return items[-limit:]
        return items

    def __len__(self) -> int:
        return len(self._buffer)
