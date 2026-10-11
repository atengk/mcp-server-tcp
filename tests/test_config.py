"""
服务端环境配置与分级 SSRF 安全策略测试套件。

@author Ateng
@since 2026-10-11
"""

import os
from unittest import mock

import pytest

from mcp_server_tcp.config import ServerConfig
from mcp_server_tcp.security import SSRFSecurityError, validate_target


def test_server_config_defaults() -> None:
    """验证配置项默认值符合规范。"""
    with mock.patch.dict(os.environ, {}, clear=True):
        cfg = ServerConfig.from_env()
        assert cfg.max_connections == 10
        assert cfg.idle_timeout_seconds == 300.0
        assert cfg.allow_private_networks is True


def test_server_config_override() -> None:
    """验证环境变量能够成功覆盖默认配置。"""
    env = {
        "MCP_TCP_MAX_CONNECTIONS": "25",
        "MCP_TCP_IDLE_TIMEOUT_SECONDS": "60.5",
        "MCP_TCP_ALLOW_PRIVATE_NETWORKS": "false",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        cfg = ServerConfig.from_env()
        assert cfg.max_connections == 25
        assert cfg.idle_timeout_seconds == 60.5
        assert cfg.allow_private_networks is False


@pytest.mark.asyncio
async def test_ssrf_strict_private_blocking() -> None:
    """验证当 MCP_TCP_ALLOW_PRIVATE_NETWORKS=false 时阻断私有/回环网段。"""
    strict_cfg = ServerConfig(allow_private_networks=False)

    # 1. 尝试连接本地回环 127.0.0.1 应该被拦截
    with pytest.raises(SSRFSecurityError, match="private network"):
        await validate_target("127.0.0.1", 80, config=strict_cfg)

    # 2. 尝试连接内网 192.168.1.1 应该被拦截
    with pytest.raises(SSRFSecurityError, match="private network"):
        await validate_target("192.168.1.1", 80, config=strict_cfg)

    # 3. 云元数据仍必须绝对拦截
    with pytest.raises(SSRFSecurityError, match="cloud metadata"):
        await validate_target("169.254.169.254", 80, config=strict_cfg)


@pytest.mark.asyncio
async def test_ssrf_default_permits_private_but_blocks_metadata() -> None:
    """验证默认配置允许内网/回环联调，但依然绝对阻断云元数据。"""
    default_cfg = ServerConfig(allow_private_networks=True)

    # 回环允许通过
    await validate_target("127.0.0.1", 80, config=default_cfg)

    # 云元数据强制阻断
    with pytest.raises(SSRFSecurityError, match="cloud metadata"):
        await validate_target("169.254.169.254", 80, config=default_cfg)
