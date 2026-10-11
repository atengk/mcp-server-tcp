"""
基础冒烟测试。

@author Ateng
@since 2026-10-11
"""

from mcp_server_tcp import __version__


def test_version() -> None:
    """验证版本号导出正常。"""
    assert __version__ == "1.1.0"
