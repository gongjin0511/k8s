# K8s日志查询系统

一个轻量级的Kubernetes日志查询和分析工具，基于kubectl命令行工具和Web界面。

## 功能特性

### 核心功能
- **Pod实例面板**: 查看Pod详细信息（状态、IP、容器等）
- **Deployment查询**: 查询整个Deployment下所有Pod的日志
- **单Pod查询**: 查询指定Pod的Console日志和文件日志
- **历史日志查询**: 查询/applog目录下的所有历史日志文件
- **文件复制下载**: 从Pod复制和下载指定文件
- **批量查询**: 支持通配符批量查询多个namespace的日志
- **关键字搜索**: 支持多关键字过滤和正则表达式匹配
- **日志下载**: 将查询结果导出为ZIP文件
- **统计分析**: 错误日志统计和Top Pod排行

### 技术特性
- **后端配置管理**: Kubeconfig通过配置文件管理，安全可靠
- **实时进度**: 批量查询时显示实时进度
- **友好界面**: 现代化的Web UI，响应式设计
- **灵活配置**: 通过config.yaml轻松调整各项参数

## 技术架构

```
┌─────────────────────────────────────────┐
│         前端 (Frontend)                  │
│  - HTML + CSS + JavaScript              │
│  - Bootstrap 5 UI框架                   │
├─────────────────────────────────────────┤
│            ↓ REST API                    │
├─────────────────────────────────────────┤
│         后端 (Backend)                   │
│  - Flask (Python 3.9+)                  │
│  - kubectl命令封装                       │
└─────────────────────────────────────────┘
            ↓ subprocess
┌─────────────────────────────────────────┐
│        kubectl 命令行工具                │
└─────────────────────────────────────────┘
```

## 项目结构

```
k8s-log-viewer/
├── backend/                # 后端代码
│   ├── app.py             # Flask主程序
│   ├── kubectl_helper.py  # kubectl命令封装
│   └── requirements.txt   # Python依赖
├── frontend/               # 前端代码
│   ├── index.html         # 主页面
│   ├── css/
│   │   └── style.css      # 样式文件
│   └── js/
│       └── app.js         # 应用逻辑
├── logs/                   # 日志缓存目录
├── Dockerfile              # Docker镜像
├── k8s-deploy.yaml        # K8s部署配置
└── README.md              # 本文档
```

## 快速开始

### 前提条件

- 已安装 `kubectl` 命令行工具
- 已配置 `kubeconfig`
- 有对K8s集群的访问权限
- Python 3.9+ (本地运行时)
- Docker (Docker部署时)

### 方式1: 本地运行 (开发/测试)

1. **配置kubeconfig**

编辑 `backend/config.yaml`:

```yaml
kubectl:
  kubeconfig_path: ~/.kube/config  # 或指定其他路径
```

2. **安装依赖**

```bash
cd backend
pip install -r requirements.txt
```

3. **启动应用**

```bash
python app.py
```

4. **访问界面**

打开浏览器访问: http://localhost:5000

### 方式2: Docker运行

1. **构建镜像**

```bash
docker build -t k8s-log-viewer:latest .
```

2. **运行容器**

```bash
docker run -d \
  --name k8s-log-viewer \
  -p 5000:5000 \
  -v ~/.kube:/root/.kube:ro \
  k8s-log-viewer:latest
```

3. **访问界面**

打开浏览器访问: http://localhost:5000

### 方式3: K8s集群部署

1. **修改配置**

编辑 `k8s-deploy.yaml`，修改以下内容:

- Ingress的域名: `k8s-logs.example.com`
- IngressClass: 根据你的Ingress Controller修改
- 镜像地址: 如果使用私有镜像仓库，修改镜像地址

2. **构建并推送镜像**

```bash
# 构建镜像
docker build -t your-registry/k8s-log-viewer:latest .

# 推送到镜像仓库
docker push your-registry/k8s-log-viewer:latest
```

3. **部署到K8s**

```bash
kubectl apply -f k8s-deploy.yaml
```

4. **检查部署状态**

```bash
# 查看Pod状态
kubectl get pods -n k8s-log-viewer

# 查看服务
kubectl get svc -n k8s-log-viewer

# 查看Ingress
kubectl get ingress -n k8s-log-viewer
```

5. **访问界面**

根据Ingress配置的域名访问，例如: https://k8s-logs.example.com

## 使用指南

### 1. 单Pod查询

适用于查询特定Pod的日志。

**操作步骤:**

1. 在"单Pod查询"页面，输入namespace通配符 (如: `erp-*`) 或直接输入namespace名称
2. 点击"加载"按钮，获取匹配的namespace列表
3. 从列表中选择一个namespace
4. 点击"加载Pods"按钮，获取该namespace下的Pod列表
5. 选择要查询的Pod
6. 设置查询条件:
   - 日志类型: Console、文件或全部
   - 行数: 每个日志源获取的行数 (默认2000)
   - 关键字: 多个关键字用逗号分隔 (如: `HikariPool,timeout,error`)
7. 点击"查询日志"
8. 查看结果，可以导出为文本文件

**示例场景:**

查询`erp-prod`命名空间下某个Pod的HikariCP连接超时日志:

- Namespace: `erp-prod`
- Pod: `erp-service-xxx-123`
- 关键字: `HikariPool,Connection is not available,timeout`
- 日志类型: `全部`

### 2. 批量查询

适用于批量扫描多个namespace下的Pod日志。

**操作步骤:**

1. 在"批量查询"页面，输入namespace模式 (多个用逗号分隔)
   - 示例: `erp-*,cnnc-*,ccs-*`
   - 可以点击快捷按钮快速填充
2. 输入关键字 (多个用逗号分隔)
   - 示例: `HikariPool,timeout,error`
   - 可以点击常用关键字快速添加
3. 设置查询参数:
   - 日志类型: Console、文件或全部
   - 每个Pod行数: 默认2000
   - 最大查询Pod数: 防止查询时间过长 (默认100)
4. 点击"开始批量查询"
5. 等待查询完成，查看结果表格
6. 点击"查看"按钮，展开查看详细日志

**示例场景:**

在所有ERP和CNNC相关的namespace中查找JDBC连接超时问题:

- Namespace模式: `erp-*,cnnc-*`
- 关键字: `HikariPool,Connection is not available,JDBC`
- 最大查询Pod数: `100`

### 3. 日志下载

将查询到的日志打包下载。

**操作步骤:**

1. 在"日志下载"页面，输入namespace
2. 输入Pod名称 (多个用逗号分隔)
3. 设置日志类型、行数和关键字过滤
4. 点击"下载日志ZIP"
5. 浏览器会自动下载ZIP文件

**下载文件结构:**

```
logs-20240101-100000.zip
├── namespace-pod1/
│   ├── console.log
│   └── service_root.log
├── namespace-pod2/
│   ├── console.log
│   └── service_root.log
```

### 4. 统计分析

生成日志统计报告。

**操作步骤:**

1. 在"统计分析"页面，输入namespace模式
2. 输入要统计的关键字
3. 点击"生成统计"
4. 查看统计结果:
   - 总Pod数、匹配Pod数、匹配率
   - 各Namespace的错误分布
   - Top 10错误Pod排行

**示例场景:**

统计所有namespace中的错误日志分布:

- Namespace模式: `erp-*,cnnc-*,ccs-*`
- 关键字: `error,exception,timeout`

## API接口文档

### 获取Namespace列表

```
GET /api/namespaces?pattern=erp-*,cnnc-*

Response:
{
  "success": true,
  "data": ["erp-prod", "erp-test", ...],
  "count": 10
}
```

### 获取Pod列表

```
GET /api/pods?namespace=erp-prod

Response:
{
  "success": true,
  "data": [
    {"name": "pod-1", "status": "Running", "ready": true},
    ...
  ],
  "count": 5
}
```

### 查询单个Pod日志

```
POST /api/logs/query

Body:
{
  "namespace": "erp-prod",
  "pod": "pod-1",
  "type": "all",
  "tail": 2000,
  "keywords": ["error", "timeout"]
}

Response:
{
  "success": true,
  "data": {
    "namespace": "erp-prod",
    "pod": "pod-1",
    "console_matches": 10,
    "file_matches": 5,
    "total_matches": 15,
    "logs": {
      "console_log": [...],
      "file_logs": {...}
    }
  }
}
```

### 批量查询日志

```
POST /api/logs/batch-query

Body:
{
  "namespaces": ["erp-*", "cnnc-*"],
  "keywords": ["error", "timeout"],
  "tail": 2000,
  "type": "all",
  "max_pods": 100
}

Response:
{
  "success": true,
  "data": [
    {
      "namespace": "erp-prod",
      "pod": "pod-1",
      "console_matches": 10,
      "file_matches": 5,
      "total_matches": 15,
      "logs": {...}
    },
    ...
  ],
  "total_pods": 50,
  "matched_pods": 10
}
```

### 下载日志

```
POST /api/logs/download

Body:
{
  "namespace": "erp-prod",
  "pods": ["pod-1", "pod-2"],
  "type": "all",
  "keywords": ["error"],
  "format": "zip"
}

Response:
文件流 (application/zip)
```

### 统计分析

```
POST /api/stats

Body:
{
  "namespaces": ["erp-*", "cnnc-*"],
  "keywords": ["error", "timeout"]
}

Response:
{
  "success": true,
  "data": {
    "total_pods": 100,
    "matched_pods": 25,
    "total_matches": 500,
    "by_namespace": {
      "erp-prod": 300,
      "cnnc-prod": 200
    },
    "top_pods": [
      {"namespace": "erp-prod", "pod": "pod-1", "count": 50},
      ...
    ]
  }
}
```

## 配置说明

### Kubeconfig配置

在 `backend/config.yaml` 中配置kubeconfig文件路径：

```yaml
kubectl:
  # kubeconfig文件路径 (可选，留空则使用默认~/.kube/config)
  kubeconfig_path: /path/to/your/kubeconfig

  # 或使用用户目录符号
  kubeconfig_path: ~/.kube/config
```

**重要说明**:
- 留空 `kubeconfig_path:` 将使用kubectl的默认配置（通常是 `~/.kube/config`）
- 支持 `~` 符号表示用户目录
- 推荐将kubeconfig文件放在安全的位置，并设置适当的文件权限（如 `chmod 600`）

### 限制配置

在 `backend/config.yaml` 中可以修改以下限制:

```yaml
limits:
  max_tail_lines: 10000           # 单次查询最大行数
  max_batch_pods: 100             # 批量查询最大Pod数
  max_download_size_mb: 100       # 下载文件最大大小(MB)
  query_timeout_seconds: 300      # 查询超时时间(秒)

kubectl:
  default_timeout: 300            # kubectl命令默认超时(秒)
  log_directory: /applog          # Pod内日志目录
  log_file_pattern: root.log      # 日志文件名模式
```

### 资源限制 (K8s部署)

在 `k8s-deploy.yaml` 中修改:

```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

## 故障排查

### kubectl命令不可用

**问题**: 启动时提示 "kubectl命令不可用"

**解决**:
1. 确保已安装kubectl: `kubectl version --client`
2. 检查kubeconfig配置: `kubectl cluster-info`
3. Docker运行时，确保挂载了kubeconfig: `-v ~/.kube:/root/.kube:ro`

### 权限不足

**问题**: 查询时提示权限错误

**解决**:
1. 检查ServiceAccount权限: `kubectl auth can-i list pods --as=system:serviceaccount:k8s-log-viewer:k8s-log-viewer`
2. 确认ClusterRole和ClusterRoleBinding已正确创建
3. 查看Pod日志: `kubectl logs -n k8s-log-viewer <pod-name>`

### 查询超时

**问题**: 批量查询时超时

**解决**:
1. 减少 `max_pods` 参数
2. 减少 `tail` 行数
3. 增加超时时间配置
4. 使用更精确的namespace模式，减少查询范围

### Ingress无法访问

**问题**: 部署到K8s后无法通过域名访问

**解决**:
1. 检查Ingress状态: `kubectl get ingress -n k8s-log-viewer`
2. 确认Ingress Controller已安装
3. 检查DNS解析: `nslookup k8s-logs.example.com`
4. 查看Ingress Controller日志

## 安全建议

1. **访问控制**: 在生产环境中，建议配置认证和授权
2. **网络隔离**: 使用NetworkPolicy限制Pod网络访问
3. **最小权限**: ServiceAccount只授予必需的权限
4. **日志脱敏**: 避免在日志中暴露敏感信息
5. **HTTPS**: 在生产环境中启用TLS加密

## 性能优化

1. **并发控制**: 批量查询时限制并发数
2. **结果缓存**: 相同查询条件缓存结果
3. **虚拟滚动**: 前端使用虚拟列表展示大量日志
4. **增量查询**: 支持分页或流式返回

## 限制说明

- 单次查询最大行数: 10,000
- 批量查询最大Pod数: 100
- 单个查询超时: 5分钟
- 下载文件最大: 100MB
- 支持的日志文件名: `root.log`
- 默认日志目录: `/applog`

## 贡献指南

欢迎提交Issue和Pull Request!

1. Fork本仓库
2. 创建特性分支: `git checkout -b feature/xxx`
3. 提交更改: `git commit -am 'Add xxx feature'`
4. 推送到分支: `git push origin feature/xxx`
5. 提交Pull Request

## 许可证

MIT License

## 联系方式

如有问题或建议，请提交Issue。

---

**注意**: 本系统仅用于日志查询和分析，不会修改任何K8s资源。请确保在使用前已获得相应的集群访问权限。
