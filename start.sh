#!/bin/bash

# K8s日志查询系统 - 启动脚本

set -e

echo "========================================="
echo "  K8s日志查询系统 - 启动脚本"
echo "========================================="
echo ""

# 检查kubectl是否可用
if ! command -v kubectl &> /dev/null; then
    echo "错误: kubectl命令未找到，请先安装kubectl"
    exit 1
fi

echo "✓ kubectl已安装: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"

# 检查kubeconfig
if [ ! -f ~/.kube/config ]; then
    echo "警告: 未找到kubeconfig文件 (~/.kube/config)"
    echo "请确保已配置好K8s集群访问权限"
fi

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "错误: python3未找到，请先安装Python 3.9+"
    exit 1
fi

echo "✓ Python已安装: $(python3 --version)"

# 进入backend目录
cd "$(dirname "$0")/backend"

# 检查是否已安装依赖
if [ ! -d "venv" ]; then
    echo ""
    echo "创建Python虚拟环境..."
    python3 -m venv venv
    echo "✓ 虚拟环境已创建"
fi

# 激活虚拟环境
source venv/bin/activate

# 安装/更新依赖
echo ""
echo "安装Python依赖..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✓ 依赖已安装"

# 启动应用
echo ""
echo "========================================="
echo "  启动K8s日志查询系统..."
echo "========================================="
echo ""
echo "访问地址: http://localhost:5000"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python app.py
