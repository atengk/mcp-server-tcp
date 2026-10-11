"""
TCP MCP Server 入口模块定义。

@author Ateng
@since 2026-10-11
"""

__version__ = "0.1.0"


def main() -> None:
    """服务主入口点。"""
    from mcp_server_tcp.server import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
