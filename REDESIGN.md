# K8s日志查询系统 - 重新设计方案

## 架构升级方案

### 1. 缓存系统设计

#### 后端缓存层（多级缓存）
```
┌─────────────────────────────────────────────────┐
│           前端请求                                │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  L1: 内存缓存（短期、热数据）                      │
│  - Namespace列表（TTL: 60s）                      │
│  - Deployment列表（TTL: 30s）                     │
│  - Pod列表（TTL: 10s）                            │
│  - 使用Python的cachetools或functools.lru_cache   │
└─────────────────┬───────────────────────────────┘
                  │ Cache Miss
                  ▼
┌─────────────────────────────────────────────────┐
│  L2: Redis缓存（可选，跨实例共享）                 │
│  - 更长的TTL                                      │
│  - 支持分布式部署                                  │
└─────────────────┬───────────────────────────────┘
                  │ Cache Miss
                  ▼
┌─────────────────────────────────────────────────┐
│  L3: K8s API（源数据）                            │
└─────────────────────────────────────────────────┘
```

**优点**：
- 减少K8s API压力
- 提升响应速度10-100倍
- 支持后台自动刷新

#### 前端缓存策略
```javascript
// LocalStorage - 持久化数据
{
  "user_preferences": {
    "default_namespace": "erp-prod",
    "theme": "dark",
    "layout": "tabs"
  },
  "bookmarks": [
    {
      "name": "ERP生产环境错误",
      "namespace": "erp-prod",
      "keywords": ["error", "exception"],
      "type": "error-context"
    }
  ],
  "history": [
    {
      "timestamp": "2025-01-18T10:30:00",
      "action": "query_logs",
      "params": {...}
    }
  ]
}

// SessionStorage - 临时数据
{
  "current_workspace": {
    "tabs": [
      {"id": "tab1", "pod": "erp-prod-xxx", "logs": [...]},
      {"id": "tab2", "pod": "cnnc-service-yyy", "logs": [...]}
    ]
  },
  "cached_ns_list": ["erp-prod", "cnnc-service", ...],
  "last_refresh": "2025-01-18T10:35:00"
}
```

---

### 2. 功能增强方案

#### A. 实时日志流（WebSocket）
```python
# 后端实现
@socketio.on('stream_logs')
def handle_log_stream(data):
    namespace = data['namespace']
    pod = data['pod']

    # kubectl logs -f 实时流
    for line in kubectl.stream_logs(namespace, pod):
        emit('log_line', {'line': line, 'timestamp': datetime.now()})
```

```javascript
// 前端实现
const socket = io();
socket.emit('stream_logs', {namespace: 'erp-prod', pod: 'xxx'});
socket.on('log_line', (data) => {
    appendLogLine(data.line);
});
```

**功能**：
- ✅ 实时追踪日志输出
- ✅ 自动滚动到底部
- ✅ 暂停/恢复流
- ✅ 日志高亮和过滤

#### B. 多标签页日志查看
```
┌─────────────────────────────────────────────────┐
│  [Tab1: erp-prod-xxx] [Tab2: cnnc-yyy] [+新建]   │
├─────────────────────────────────────────────────┤
│  Pod: erp-prod-deployment-abc-123               │
│  ┌─────────────────────────────────────────┐   │
│  │ [实时] [历史] [搜索] [过滤] [导出]        │   │
│  ├─────────────────────────────────────────┤   │
│  │ 2025-01-18 10:30:01 INFO Starting...    │   │
│  │ 2025-01-18 10:30:02 ERROR Connection... │   │
│  │ ...                                     │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

**优势**：
- 同时查看多个pod日志
- 对比不同环境的日志
- 独立的过滤和搜索设置

#### C. 高级日志分析工具

**1. 智能搜索**
```javascript
// 正则表达式搜索
searchPattern: /ERROR.*timeout.*database/i

// 时间范围过滤
timeRange: {
  from: "2025-01-18 10:00:00",
  to: "2025-01-18 11:00:00"
}

// 日志级别过滤
logLevel: ["ERROR", "FATAL", "WARN"]

// 复合条件
filter: {
  and: [
    {field: "level", operator: "in", value: ["ERROR", "FATAL"]},
    {field: "message", operator: "contains", value: "timeout"},
    {field: "timestamp", operator: ">=", value: "2025-01-18 10:00:00"}
  ]
}
```

**2. 日志高亮和美化**
```javascript
// 语法高亮
highlightRules: {
  ERROR: 'text-red-600 bg-red-50',
  WARN: 'text-yellow-600 bg-yellow-50',
  INFO: 'text-blue-600',
  timestamp: 'text-gray-500',
  json: 'syntax-highlight-json'
}

// JSON自动格式化
if (isJSON(line)) {
  displayFormatted(JSON.parse(line));
}
```

**3. 日志统计分析**
```javascript
// 实时统计
stats: {
  totalLines: 15234,
  errorCount: 45,
  warnCount: 128,
  errorsPerMinute: [12, 8, 15, 9, ...],
  topErrors: [
    {message: "Connection timeout", count: 23},
    {message: "Database deadlock", count: 12}
  ]
}
```

#### D. 运维工具集成

**1. Pod管理**
```python
@app.route('/api/pod/restart', methods=['POST'])
@login_required
def restart_pod():
    """重启Pod"""
    namespace = data['namespace']
    pod = data['pod']
    kubectl.delete_pod(namespace, pod)
    return jsonify({'success': True, 'message': 'Pod重启中'})

@app.route('/api/pod/describe', methods=['GET'])
@login_required
def describe_pod():
    """获取Pod详细信息"""
    info = kubectl.describe_pod(namespace, pod)
    return jsonify({
        'cpu_usage': info['cpu'],
        'memory_usage': info['memory'],
        'status': info['status'],
        'events': info['events']
    })
```

**2. 快速执行命令**
```python
@app.route('/api/pod/exec', methods=['POST'])
@login_required
def exec_command():
    """在Pod中执行命令"""
    result = kubectl.exec(namespace, pod, command)
    return jsonify({'output': result})
```

**3. 资源监控**
```javascript
// 实时CPU/内存图表
{
  pod: "erp-prod-xxx",
  metrics: {
    cpu: [45, 52, 48, 50, ...],  // %
    memory: [1.2, 1.3, 1.25, ...],  // GB
    timestamps: [...]
  }
}
```

#### E. 智能功能

**1. 错误模式识别**
```python
# AI辅助错误分析
def analyze_error_pattern(logs):
    patterns = {
        'database_timeout': r'timeout.*database|database.*timeout',
        'oom_error': r'OutOfMemory|OOM|memory.*exceed',
        'connection_refused': r'connection refused|refused.*connection'
    }

    detected = []
    for pattern_name, regex in patterns.items():
        if re.search(regex, '\n'.join(logs), re.I):
            detected.append({
                'type': pattern_name,
                'solution': get_solution(pattern_name),
                'severity': get_severity(pattern_name)
            })

    return detected
```

**2. 自动告警**
```python
# 错误率超过阈值自动告警
if error_rate > threshold:
    send_alert(
        title=f"错误率异常: {namespace}/{pod}",
        message=f"错误率 {error_rate}% 超过阈值 {threshold}%",
        level="critical"
    )
```

---

### 3. 灵活界面设计

#### A. 可定制化工作区

```
┌──────────────────────────────────────────────────────────────┐
│  [保存工作区] [加载工作区: ERP监控 ▼]  [新建]                   │
├──────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐  ┌─────────────────────────────┐   │
│  │ Panel 1: 实时日志    │  │ Panel 2: 错误统计           │   │
│  │ erp-prod-xxx        │  │ ┌─────────────────────────┐ │   │
│  │ [streaming...]      │  │ │  ████ ERROR: 45        │ │   │
│  │                     │  │ │  ███  WARN: 128        │ │   │
│  └─────────────────────┘  │ └─────────────────────────┘ │   │
│                           └─────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Panel 3: 资源监控                                     │   │
│  │ CPU: ████████░░ 52%    Memory: ██████░░░░ 65%       │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**工作区配置示例**：
```json
{
  "name": "ERP生产环境监控",
  "layout": "grid",
  "panels": [
    {
      "type": "log_stream",
      "position": {"x": 0, "y": 0, "w": 6, "h": 4},
      "config": {
        "namespace": "erp-prod",
        "pod_pattern": "erp-prod-*",
        "filters": ["ERROR", "FATAL"]
      }
    },
    {
      "type": "error_chart",
      "position": {"x": 6, "y": 0, "w": 6, "h": 2},
      "config": {
        "namespaces": ["erp-prod", "erp-staging"]
      }
    },
    {
      "type": "resource_monitor",
      "position": {"x": 6, "y": 2, "w": 6, "h": 2},
      "config": {
        "pods": ["erp-prod-xxx", "erp-prod-yyy"]
      }
    }
  ]
}
```

#### B. 快捷操作

**1. 键盘快捷键**
```javascript
shortcuts: {
  'Ctrl+K': 'openCommandPalette',      // 命令面板
  'Ctrl+T': 'newTab',                   // 新标签页
  'Ctrl+W': 'closeTab',                 // 关闭标签页
  'Ctrl+F': 'search',                   // 搜索
  'Ctrl+L': 'clearLogs',                // 清空日志
  'Ctrl+D': 'download',                 // 下载日志
  'Ctrl+R': 'refresh',                  // 刷新
  'Ctrl+B': 'toggleBookmark',           // 切换书签
  'Ctrl+H': 'showHistory',              // 显示历史
  'Ctrl+1-9': 'switchTab',              // 切换标签页
  'Esc': 'cancel'                       // 取消
}
```

**2. 命令面板（类似VSCode）**
```
┌────────────────────────────────────────────────┐
│ > 搜索命令或操作...                             │
├────────────────────────────────────────────────┤
│ > 查询 erp-prod 错误日志                        │
│ > 重启 Pod: erp-prod-deployment-xxx            │
│ > 下载日志: cnnc-service-yyy                   │
│ > 切换到标签页 2                                │
│ > 打开工作区: ERP监控                           │
└────────────────────────────────────────────────┘
```

**3. 历史记录和收藏**
```javascript
// 历史记录（最近20条）
history: [
  {
    timestamp: "2025-01-18 10:30",
    action: "查询日志",
    namespace: "erp-prod",
    pod: "erp-prod-xxx",
    quickReplay: true  // 一键重放
  }
]

// 收藏夹
bookmarks: [
  {
    name: "⭐ ERP生产错误",
    icon: "🔴",
    namespace: "erp-prod",
    keywords: ["ERROR", "exception"],
    autoRefresh: true
  }
]
```

---

### 4. 技术栈升级

#### 后端
```python
# 原有：Flask
# 新增：
- Flask-SocketIO：WebSocket实时通信
- Flask-Caching：内存缓存
- Redis：分布式缓存（可选）
- APScheduler：定时任务（缓存刷新）
- Prometheus Client：监控指标
```

#### 前端
```javascript
// 原有：Vanilla JS + Bootstrap
// 新增：
- Socket.IO：实时日志流
- Chart.js：图表展示
- Monaco Editor：高级日志查看（支持语法高亮）
- GridStack.js：拖拽式布局
- Fuse.js：模糊搜索
- Split.js：可调整大小的面板
```

---

### 5. 实现优先级

**Phase 1: 核心优化（1-2天）**
- ✅ 后端内存缓存实现
- ✅ 前端LocalStorage历史记录
- ✅ 快速刷新机制

**Phase 2: 实时功能（2-3天）**
- ✅ WebSocket实时日志流
- ✅ 多标签页管理
- ✅ 日志搜索和过滤

**Phase 3: 高级分析（2-3天）**
- ✅ 日志统计图表
- ✅ 错误模式识别
- ✅ 资源监控集成

**Phase 4: 用户体验（1-2天）**
- ✅ 可定制化工作区
- ✅ 快捷键支持
- ✅ 命令面板

**Phase 5: 运维工具（1-2天）**
- ✅ Pod重启功能
- ✅ 快速执行命令
- ✅ Events查看

---

## 预期效果

### 性能提升
- ⚡ 列表加载速度：从3-5秒 → 100-300ms
- ⚡ 缓存命中率：90%+
- ⚡ API请求减少：70%+

### 功能增强
- 🚀 实时日志追踪
- 🚀 多pod并行查看
- 🚀 智能错误分析
- 🚀 一键运维操作

### 用户体验
- ⭐ 操作效率提升50%+
- ⭐ 学习曲线降低
- ⭐ 个性化定制
- ⭐ 快捷键操作

---

## 下一步行动

请确认以上设计方案是否符合您的期望，我将开始按照优先级逐步实现。

建议先实现：
1. **Phase 1: 核心优化** - 立即可见的性能提升
2. **Phase 2: 实时功能** - 最有价值的新功能

您认为如何？是否需要调整某些部分？
