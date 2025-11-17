FROM python:3.9-slim

LABEL maintainer="K8s Log Viewer"
LABEL description="K8s日志查询系统 - 支持多架构(amd64/arm64)"

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 安装kubectl
ARG KUBECTL_VERSION=v1.28.0
ARG TARGETARCH

# 检测架构并下载对应的kubectl
RUN set -ex && \
    # 如果TARGETARCH未设置（非buildx构建），则检测当前架构
    if [ -z "$TARGETARCH" ]; then \
        ARCH=$(uname -m); \
        echo "Detected architecture: $ARCH"; \
        case $ARCH in \
            x86_64) TARGETARCH=amd64 ;; \
            aarch64) TARGETARCH=arm64 ;; \
            armv7l) TARGETARCH=arm ;; \
            *) echo "Unsupported architecture: $ARCH"; exit 1 ;; \
        esac; \
    fi && \
    echo "Downloading kubectl for architecture: $TARGETARCH" && \
    curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/ && \
    kubectl version --client

# 复制requirements.txt并安装Python依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# 创建必要的目录
RUN mkdir -p /app/logs /app/files && \
    chmod 777 /app/logs /app/files

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=backend/app.py

# 暴露端口
EXPOSE 5000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# 启动应用
WORKDIR /app/backend
CMD ["python", "app.py"]
