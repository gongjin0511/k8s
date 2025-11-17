# 构建说明

## 多架构支持

本项目的 Docker 镜像支持多种 CPU 架构：
- **amd64** (x86_64) - Intel/AMD 64位处理器
- **arm64** (aarch64) - ARM 64位处理器 (如 Apple Silicon, AWS Graviton)
- **arm** (armv7) - ARM 32位处理器

## 构建方法

### 方法1: 普通构建 (单架构)

在当前平台架构下构建镜像：

```bash
# 直接构建
docker build -t k8s-log-viewer:latest .

# 构建时指定 kubectl 版本
docker build --build-arg KUBECTL_VERSION=v1.29.0 -t k8s-log-viewer:latest .
```

### 方法2: 使用 Docker Buildx (多架构)

推荐使用 Docker Buildx 进行多架构构建：

```bash
# 1. 创建并使用 buildx 构建器
docker buildx create --name mybuilder --use

# 2. 启动构建器
docker buildx inspect --bootstrap

# 3. 构建多架构镜像并推送
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t your-registry/k8s-log-viewer:latest \
  --push \
  .

# 4. 仅构建本地架构（不推送）
docker buildx build \
  --platform linux/arm64 \
  -t k8s-log-viewer:latest \
  --load \
  .
```

### 方法3: 在 aarch64 (ARM64) 平台直接构建

```bash
# 在 ARM64 机器上（如 Apple Silicon Mac, 树莓派 4, AWS Graviton）
# 方式1: 自动检测（推荐）
docker build --platform linux/arm64 -t k8s-log-viewer:latest .

# 方式2: 不指定平台（可能会有问题）
docker build -t k8s-log-viewer:latest .

# Dockerfile 会自动检测架构并下载对应的 kubectl
# 构建时会输出: "Detected architecture: aarch64"
# 和: "Downloading kubectl for architecture: arm64"
```

**重要提示**：
- 如果你在 aarch64 机器上构建但下载了 amd64 的 kubectl，请明确使用 `--platform linux/arm64` 参数
- 这通常发生在 Docker Desktop 或某些配置默认使用 amd64 模拟的情况下

## 架构检测机制

Dockerfile 使用以下逻辑自动检测和适配架构：

1. 优先使用 Docker Buildx 提供的 `TARGETARCH` 参数
2. 如果 `TARGETARCH` 不存在，使用 `uname -m` 检测当前架构
3. 映射关系：
   - `x86_64` → `amd64`
   - `aarch64` → `arm64`
   - `armv7l` → `arm`

## 验证构建

构建完成后验证：

```bash
# 检查镜像架构
docker inspect k8s-log-viewer:latest | grep Architecture

# 运行容器验证
docker run --rm k8s-log-viewer:latest kubectl version --client

# 查看构建日志中的架构信息
# 构建时会输出: "Downloading kubectl for architecture: arm64"
```

## 常见问题

### Q1: 在 aarch64 机器上构建但下载了 amd64 的 kubectl

**原因**: Docker 可能默认使用了 amd64 模拟，或者拉取了错误架构的基础镜像

**解决**:
```bash
# 方法1: 明确指定平台（推荐）
docker build --platform linux/arm64 -t k8s-log-viewer:latest .

# 方法2: 检查 Docker 默认平台
docker version --format '{{.Server.Arch}}'

# 方法3: 检查构建日志，确认检测到的架构
# 构建时应该看到：
# "Detected architecture: aarch64"
# "Downloading kubectl for architecture: arm64"
```

### Q2: 构建时提示 "exec format error"

**原因**: 尝试在不兼容的架构上运行镜像

**解决**:
```bash
# 确保构建的是当前平台的架构
docker build --platform linux/arm64 -t k8s-log-viewer:latest .
```

### Q3: kubectl 下载失败

**原因**: 网络问题或架构不支持

**解决**:
```bash
# 1. 检查网络连接
curl -I https://dl.k8s.io/release/v1.28.0/bin/linux/arm64/kubectl

# 2. 使用代理构建
docker build --build-arg HTTP_PROXY=http://proxy:port -t k8s-log-viewer:latest .

# 3. 手动指定 kubectl 版本
docker build --build-arg KUBECTL_VERSION=v1.29.0 -t k8s-log-viewer:latest .
```

### Q4: 在 Apple Silicon Mac 上构建

```bash
# Apple Silicon (M1/M2/M3/M4) 是 ARM64 架构
# 推荐明确指定平台
docker build --platform linux/arm64 -t k8s-log-viewer:latest .

# 或使用 buildx
docker buildx build --platform linux/arm64 -t k8s-log-viewer:latest --load .

# 如果遇到架构问题，检查 Docker Desktop 的设置
# Settings -> Features in development -> Use Rosetta for x86/amd64 emulation (应关闭)
```

## 构建参数

可用的构建参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `KUBECTL_VERSION` | `v1.28.0` | kubectl 版本 |
| `TARGETARCH` | 自动检测 | 目标架构 (amd64/arm64/arm) |

示例：

```bash
docker build \
  --build-arg KUBECTL_VERSION=v1.29.0 \
  --build-arg TARGETARCH=arm64 \
  -t k8s-log-viewer:latest \
  .
```

## 推送到镜像仓库

### Docker Hub

```bash
# 登录
docker login

# 标记镜像
docker tag k8s-log-viewer:latest yourusername/k8s-log-viewer:latest

# 推送
docker push yourusername/k8s-log-viewer:latest
```

### 私有镜像仓库

```bash
# 标记
docker tag k8s-log-viewer:latest registry.example.com/k8s-log-viewer:latest

# 推送
docker push registry.example.com/k8s-log-viewer:latest
```

### 多架构镜像 Manifest

```bash
# 使用 buildx 自动创建 manifest
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t yourusername/k8s-log-viewer:latest \
  --push \
  .

# 验证 manifest
docker buildx imagetools inspect yourusername/k8s-log-viewer:latest
```

## 性能优化

### 使用镜像缓存

```bash
# 启用 BuildKit 缓存
export DOCKER_BUILDKIT=1
docker build -t k8s-log-viewer:latest .
```

### 减小镜像大小

Dockerfile 已经做了以下优化：
- 使用 `python:3.9-slim` 基础镜像
- 清理 apt 缓存 (`rm -rf /var/lib/apt/lists/*`)
- 使用 `--no-cache-dir` 安装 Python 包
- 多阶段构建的最小化设计

当前镜像大小约为 **200-250MB**。

## CI/CD 集成

### GitHub Actions 示例

```yaml
name: Build Multi-Arch Docker Image

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v2

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Login to DockerHub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: yourusername/k8s-log-viewer:latest
```

## 参考资料

- [Docker Buildx 文档](https://docs.docker.com/buildx/working-with-buildx/)
- [Kubernetes kubectl 下载](https://kubernetes.io/docs/tasks/tools/)
- [多架构镜像构建最佳实践](https://docs.docker.com/build/building/multi-platform/)
