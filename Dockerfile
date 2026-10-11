# ==============================================================================
# Dockerfile: TCP MCP Server 容器构建规范
# 采用轻量安全 Python 3.11-slim 基础镜像，非 root 用户运行
# ==============================================================================

FROM python:3.11-slim AS runtime

# 设置环境不变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 安装基础系统依赖（保持镜像极简）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 创建非 root 运行账号
RUN useradd -m -u 1000 -s /bin/bash appuser

# 复制工程声明文件并安装依赖
COPY pyproject.toml README.md ./
# 提前建立源码骨架目录，保证本地包可编辑/自包含安装
COPY src/ ./src/

RUN pip install --upgrade pip && \
    pip install .

# 切换为安全非 root 账号
USER appuser

# 默认入口命令：启动 TCP MCP Server
ENTRYPOINT ["mcp-server-tcp"]
