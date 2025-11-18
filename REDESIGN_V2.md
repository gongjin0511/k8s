# K8s日志管理系统 - 完全重构方案 V2

基于用户反馈的全新设计，打造最理想的K8s日志管理平台

---

## 🎯 核心问题与解决方案

### 问题1: 日志文件选择受限
**当前**: 只能查看 root.log，无法选择其他日志文件

**解决方案**:
1. **日志文件浏览器** - 展示Pod内所有日志文件
2. **文件树视图** - 层级展示 /applog/ 目录结构
3. **文件元数据** - 显示文件大小、修改时间、类型
4. **智能过滤** - 按文件名、日期、大小筛选

### 问题2: 无法查询历史时间段日志
**当前**: 无时间范围查询功能

**解决方案**:
1. **时间轴视图** - 可视化展示日志文件时间分布
2. **日期范围选择器** - 选择开始和结束日期
3. **自动识别** - 解析文件名中的日期（如 root.log.2025-01-18）
4. **时间段聚合** - 合并查询多个时间段的文件

### 问题3: 数据持久化和性能
**当前**: 无本地数据库，数据不持久化

**解决方案**:
1. **SQLite数据库** - 轻量级本地数据库
2. **日志索引表** - 存储文件路径、元数据
3. **搜索历史表** - 持久化查询记录
4. **收藏夹表** - 保存常用配置
5. **全文检索** - SQLite FTS5全文搜索

---

## 🏗️ 新架构设计

### 架构图
```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Vue.js)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  文件浏览器   │  │  多标签编辑器 │  │  时间轴视图   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  全局搜索     │  │  对比视图     │  │  统计面板     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↕ REST API
┌─────────────────────────────────────────────────────────────┐
│                   Backend (Flask + SQLite)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  日志服务     │  │  文件服务     │  │  搜索服务     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────────────────────────────────────────┐      │
│  │         SQLite Database (日志索引 + 元数据)       │      │
│  └──────────────────────────────────────────────────┘      │
│  ┌──────────────────────────────────────────────────┐      │
│  │         缓存层 (内存缓存 + SessionStorage)        │      │
│  └──────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↕ kubectl
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 数据库设计

### SQLite Schema

```sql
-- 日志文件索引表
CREATE TABLE log_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT NOT NULL,
    pod_name TEXT NOT NULL,
    file_path TEXT NOT NULL,           -- /applog/root.log.2025-01-18
    file_name TEXT NOT NULL,            -- root.log.2025-01-18
    file_size INTEGER,                  -- 文件大小（字节）
    file_date DATE,                     -- 从文件名解析的日期
    last_modified TIMESTAMP,            -- 最后修改时间
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    indexed BOOLEAN DEFAULT 0,          -- 是否已建立索引
    UNIQUE(namespace, pod_name, file_path)
);

-- 查询历史表
CREATE TABLE query_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,               -- 'view_log', 'search', 'download'
    namespace TEXT,
    pod_name TEXT,
    file_path TEXT,
    keywords TEXT,                      -- JSON数组
    parameters TEXT,                    -- JSON对象
    result_count INTEGER,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    execution_time REAL                 -- 执行时间（秒）
);

-- 收藏夹表
CREATE TABLE bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    icon TEXT DEFAULT '⭐',
    namespace TEXT,
    pod_pattern TEXT,                   -- Pod通配符
    file_pattern TEXT,                  -- 文件通配符
    keywords TEXT,                      -- JSON数组
    config TEXT,                        -- JSON配置
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP
);

-- 全文搜索表（使用FTS5）
CREATE VIRTUAL TABLE log_content_fts USING fts5(
    namespace,
    pod_name,
    file_path,
    content,
    tokenize = 'porter unicode61'
);

-- 日志统计表
CREATE TABLE log_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT NOT NULL,
    pod_name TEXT NOT NULL,
    date DATE NOT NULL,
    error_count INTEGER DEFAULT 0,
    warn_count INTEGER DEFAULT 0,
    total_lines INTEGER DEFAULT 0,
    file_count INTEGER DEFAULT 0,
    UNIQUE(namespace, pod_name, date)
);

-- 索引
CREATE INDEX idx_log_files_namespace_pod ON log_files(namespace, pod_name);
CREATE INDEX idx_log_files_date ON log_files(file_date);
CREATE INDEX idx_query_history_executed_at ON query_history(executed_at);
CREATE INDEX idx_bookmarks_name ON bookmarks(name);
```

---

## 🎨 全新UI设计

### 1. 主界面布局（类似VSCode）

```
┌──────────────────────────────────────────────────────────────────┐
│  [Logo] K8s日志管理平台    [全局搜索...]   [通知] [设置] [登出]  │
├──────┬──────────────────────────────────────────────────┬────────┤
│      │ [Tab1: root.log] [Tab2: app.log] [+]            │ [面板] │
│ 文   │ ┌────────────────────────────────────────────┐  │        │
│ 件   │ │ Namespace: erp-prod / Pod: xxx             │  │ 日志   │
│ 树   │ │ 文件: /applog/root.log.2025-01-18          │  │ 统计   │
│      │ │ ┌──────────────────────────────────────┐   │  │        │
│ 📁NS │ │ │ 2025-01-18 10:30:01 INFO Starting... │   │  │ 错误:  │
│ ├📦Pod│ │ │ 2025-01-18 10:30:02 ERROR Failed...  │   │  │  45   │
│ │├📄log│ │ │ 2025-01-18 10:30:03 WARN Retry...    │   │  │        │
│ ││ root│ │ │ ...                                  │   │  │ 警告:  │
│ ││ app │ │ └──────────────────────────────────────┘   │  │ 128   │
│ ││ err │ │ [行号] [时间戳] [高亮] [导出] [分享]      │  │        │
│      │ └────────────────────────────────────────────┘  │        │
├──────┴──────────────────────────────────────────────────┴────────┤
│ [命令面板] 输入命令或搜索...   Ctrl+K                           │
└──────────────────────────────────────────────────────────────────┘
```

### 2. 文件浏览器（左侧边栏）

```
📁 命名空间
├─ 📦 erp-prod
│  ├─ 🚀 erp-prod-deployment-abc-123
│  │  ├─ 📂 /applog/
│  │  │  ├─ 📄 root.log              (2.5MB, 今天 10:30)
│  │  │  ├─ 📄 root.log.2025-01-18   (45MB, 昨天)
│  │  │  ├─ 📄 root.log.2025-01-17   (50MB, 2天前)
│  │  │  ├─ 📄 app.log               (1.2MB, 今天 10:25)
│  │  │  ├─ 📄 error.log             (500KB, 今天 09:15)
│  │  │  └─ 📂 archive/
│  │  │     ├─ 📄 root.log.2025-01-10.gz
│  │  │     └─ 📄 root.log.2025-01-09.gz
│  │  └─ 📊 资源监控
│  │     ├─ CPU: 45%
│  │     └─ Memory: 1.2GB
│  └─ 🚀 erp-prod-deployment-def-456
├─ 📦 cnnc-service
└─ 📦 erp-staging

[过滤] [刷新] [展开全部] [折叠全部]
```

### 3. 多标签页编辑器（中间区域）

```
┌─────────────────────────────────────────────────────────┐
│ [Tab1 •] root.log  [Tab2] app.log  [Tab3] error.log [+]│
├─────────────────────────────────────────────────────────┤
│ 📍 erp-prod / erp-prod-xxx / /applog/root.log          │
│ ┌───────────────────────────────────────────────────┐   │
│ │ [实时] [历史] [搜索] [过滤] [对比] [下载]          │   │
│ ├───────────────────────────────────────────────────┤   │
│ │  1 │ 2025-01-18 10:30:01 INFO  Starting app...    │   │
│ │  2 │ 2025-01-18 10:30:02 ERROR Connection failed  │   │
│ │  3 │ 2025-01-18 10:30:03 WARN  Retrying...        │   │
│ │    │                                               │   │
│ └───────────────────────────────────────────────────┘   │
│ [行: 1234/50000] [大小: 45MB] [更新: 1秒前]            │
└─────────────────────────────────────────────────────────┘
```

### 4. 时间轴视图（新功能）

```
┌──────────────────────────────────────────────────────────┐
│ 时间轴 - erp-prod-xxx                                    │
│                                                          │
│ 2025-01                                                  │
│ │                                                        │
│ ├─ 18日 ████████████ root.log (2.5MB, 3个ERROR)         │
│ │       ██ app.log (1.2MB, 1个ERROR)                    │
│ │                                                        │
│ ├─ 17日 ████████████████ root.log (50MB, 15个ERROR)    │
│ │       ████ app.log (5MB, 2个ERROR)                    │
│ │                                                        │
│ ├─ 16日 ██████████ root.log (30MB, 8个ERROR)           │
│ │                                                        │
│ └─ 15日 ████████ root.log (25MB, 5个ERROR)             │
│                                                          │
│ [选择日期范围: 2025-01-15 至 2025-01-18]                │
│ [合并查看] [批量下载] [统计分析]                         │
└──────────────────────────────────────────────────────────┘
```

### 5. 全局搜索中心

```
┌──────────────────────────────────────────────────────────┐
│ 🔍 全局搜索                                Ctrl+Shift+F  │
│                                                          │
│ 搜索内容: [timeout database________________]  [正则] [大小写]│
│                                                          │
│ 范围:                                                    │
│ ☑ 所有命名空间  ☐ 仅 erp-prod  ☐ 仅 cnnc-*              │
│ ☑ 所有文件类型  ☐ 仅 *.log     ☐ 仅 error.log           │
│                                                          │
│ 时间范围:                                                │
│ ○ 最近7天  ○ 最近30天  ● 自定义                          │
│ [2025-01-10] 至 [2025-01-18]                            │
│                                                          │
│ 结果 (找到 156 处匹配):                                   │
│ ├─ erp-prod-xxx/root.log.2025-01-18 (45处)              │
│ │  Line 123: ... timeout connecting to database ...    │
│ │  Line 456: ... database connection timeout ...       │
│ │                                                        │
│ ├─ erp-prod-yyy/app.log (23处)                          │
│ └─ cnnc-service-zzz/error.log (88处)                    │
│                                                          │
│ [导出结果] [添加到书签] [生成报告]                       │
└──────────────────────────────────────────────────────────┘
```

### 6. 对比视图（新功能）

```
┌──────────────────────────────────────────────────────────┐
│ 对比视图 - 并排显示                                       │
│                                                          │
│ ┌─────────────────────┬─────────────────────┐           │
│ │ root.log (今天)      │ root.log (昨天)      │           │
│ ├─────────────────────┼─────────────────────┤           │
│ │ 10:30:01 Starting.. │ 10:30:05 Starting.. │ ← 时间差异 │
│ │ 10:30:02 ERROR xxx  │ 10:30:06 ERROR yyy  │ ← 不同错误 │
│ │ 10:30:03 Connected  │ 10:30:07 Connected  │           │
│ │                     │ 10:30:08 Warning..  │ ← 仅左侧   │
│ │ 10:30:04 Success    │                     │ ← 仅右侧   │
│ └─────────────────────┴─────────────────────┘           │
│                                                          │
│ [同步滚动] [高亮差异] [导出对比报告]                      │
└──────────────────────────────────────────────────────────┘
```

---

## 🚀 新增核心功能

### 1. 日志文件管理

#### A. 列出所有日志文件
```python
@app.route('/api/logs/files', methods=['GET'])
def list_log_files():
    """
    列出Pod内所有日志文件
    Query参数:
      - namespace: 命名空间
      - pod: Pod名称
      - path: 日志目录路径（默认/applog/）
    """
    namespace = request.args.get('namespace')
    pod = request.args.get('pod')
    log_path = request.args.get('path', '/applog/')

    # 使用 kubectl exec 列出文件
    files = kubectl.exec(namespace, pod, f'ls -lh {log_path}')

    # 解析文件列表
    parsed_files = []
    for line in files.split('\n'):
        # -rw-r--r-- 1 root root 45M Jan 18 10:30 root.log
        match = re.match(r'([d-])([rwx-]{9})\s+\d+\s+\w+\s+\w+\s+(\S+)\s+(\w+\s+\d+\s+[\d:]+)\s+(.+)', line)
        if match:
            is_dir, perms, size, date, name = match.groups()
            parsed_files.append({
                'name': name,
                'path': f'{log_path}/{name}',
                'size': size,
                'date': date,
                'is_directory': is_dir == 'd',
                'permissions': perms
            })

    # 存入数据库索引
    db.index_log_files(namespace, pod, parsed_files)

    return jsonify({
        'success': True,
        'files': parsed_files
    })
```

#### B. 按时间范围筛选文件
```python
@app.route('/api/logs/files/by-date', methods=['GET'])
def get_files_by_date():
    """
    按日期范围筛选日志文件
    Query参数:
      - namespace
      - pod
      - start_date: 2025-01-10
      - end_date: 2025-01-18
    """
    files = db.query("""
        SELECT * FROM log_files
        WHERE namespace = ? AND pod_name = ?
        AND file_date BETWEEN ? AND ?
        ORDER BY file_date DESC
    """, [namespace, pod, start_date, end_date])

    return jsonify({'success': True, 'files': files})
```

### 2. 文件内容查看

```python
@app.route('/api/logs/content', methods=['GET'])
def get_log_content():
    """
    获取指定日志文件内容
    Query参数:
      - namespace
      - pod
      - file_path: /applog/root.log.2025-01-18
      - offset: 起始行号（分页）
      - limit: 返回行数（默认1000）
    """
    namespace = request.args.get('namespace')
    pod = request.args.get('pod')
    file_path = request.args.get('file_path')
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 1000))

    # 使用 sed 读取指定行范围
    start = offset + 1
    end = offset + limit
    cmd = f"sed -n '{start},{end}p' {file_path}"

    content = kubectl.exec(namespace, pod, cmd)

    # 获取总行数
    total_lines = kubectl.exec(namespace, pod, f"wc -l < {file_path}")

    return jsonify({
        'success': True,
        'content': content.split('\n'),
        'total_lines': int(total_lines),
        'offset': offset,
        'limit': limit
    })
```

### 3. 全文搜索（使用SQLite FTS5）

```python
@app.route('/api/logs/search/global', methods=['POST'])
def global_search():
    """
    全局搜索日志内容
    Body:
    {
        "query": "timeout database",
        "namespaces": ["erp-*"],
        "file_patterns": ["*.log"],
        "start_date": "2025-01-10",
        "end_date": "2025-01-18",
        "limit": 100
    }
    """
    data = request.get_json()
    query = data.get('query')

    # FTS5 全文搜索
    results = db.fts_search(query, filters=data)

    return jsonify({
        'success': True,
        'results': results,
        'total': len(results)
    })
```

### 4. 文件对比

```python
@app.route('/api/logs/compare', methods=['POST'])
def compare_logs():
    """
    对比两个日志文件
    Body:
    {
        "file1": {
            "namespace": "erp-prod",
            "pod": "xxx",
            "path": "/applog/root.log"
        },
        "file2": {
            "namespace": "erp-prod",
            "pod": "xxx",
            "path": "/applog/root.log.2025-01-17"
        }
    }
    """
    # 使用 diff 命令对比
    diff_result = kubectl.exec_with_diff(file1, file2)

    return jsonify({
        'success': True,
        'diff': diff_result
    })
```

---

## 💡 智能功能

### 1. 自动发现和索引
```python
# 定时任务：每小时自动发现新日志文件
@scheduler.task('interval', hours=1)
def auto_discover_logs():
    """自动发现所有Pod的日志文件"""
    namespaces = kubectl.get_namespaces()
    for ns in namespaces:
        pods = kubectl.get_pods(ns)
        for pod in pods:
            try:
                files = discover_log_files(ns, pod)
                db.index_log_files(ns, pod, files)
            except Exception as e:
                logger.error(f"发现日志文件失败: {ns}/{pod} - {e}")
```

### 2. 智能日志归档建议
```python
@app.route('/api/logs/archive-suggestions', methods=['GET'])
def get_archive_suggestions():
    """
    推荐可归档的旧日志文件
    - 超过30天
    - 大小超过100MB
    - 未被访问过
    """
    suggestions = db.query("""
        SELECT * FROM log_files
        WHERE file_date < date('now', '-30 days')
        AND file_size > 100000000
        AND file_path NOT IN (
            SELECT DISTINCT file_path FROM query_history
            WHERE executed_at > date('now', '-7 days')
        )
    """)

    return jsonify({'success': True, 'suggestions': suggestions})
```

### 3. 错误趋势分析
```python
@app.route('/api/logs/error-trends', methods=['GET'])
def get_error_trends():
    """
    分析错误趋势
    - 过去7天每天的错误数量
    - 高频错误类型
    - 异常峰值时段
    """
    trends = db.query("""
        SELECT date, error_count, warn_count
        FROM log_stats
        WHERE namespace = ? AND pod_name = ?
        AND date >= date('now', '-7 days')
        ORDER BY date
    """, [namespace, pod])

    return jsonify({
        'success': True,
        'trends': trends,
        'chart_data': format_for_chart(trends)
    })
```

---

## 📦 技术栈升级

### 后端
```python
# 新增依赖
pip install:
  - flask-sqlalchemy  # ORM
  - flask-apscheduler # 定时任务
  - flask-socketio    # WebSocket
  - sqlite3           # 数据库
  - python-magic      # 文件类型检测
  - chardet           # 编码检测
```

### 前端
```javascript
// 升级到Vue.js 3（或继续用Vanilla JS但组件化）
new dependencies:
  - monaco-editor     # 代码编辑器（支持语法高亮）
  - splitpanes        # 分屏布局
  - vue-virtual-scroller # 虚拟滚动（大文件性能优化）
  - date-fns          # 日期处理
  - chart.js          # 图表
  - fuse.js           # 模糊搜索
```

---

## 🎯 实施计划

### Phase 1: 核心基础（1-2天）
✅ **已完成**:
- 后端缓存系统
- 前端存储管理

🔄 **进行中**:
- SQLite数据库设计和初始化
- 文件浏览API实现

### Phase 2: 文件管理（2-3天）
- [ ] 文件列表API
- [ ] 文件内容读取API
- [ ] 时间范围筛选
- [ ] 文件树UI组件
- [ ] 文件元数据展示

### Phase 3: 搜索和对比（2-3天）
- [ ] 全文搜索引擎（FTS5）
- [ ] 全局搜索UI
- [ ] 文件对比功能
- [ ] 搜索结果高亮

### Phase 4: 高级功能（2-3天）
- [ ] 多标签页管理
- [ ] 时间轴视图
- [ ] 错误趋势分析
- [ ] 自动索引和归档建议

---

## 🚀 立即开始？

我建议按以下顺序实现：

**第一步**: 创建SQLite数据库和基础表结构
**第二步**: 实现文件列表和浏览功能
**第三步**: 重构UI为文件树+多标签页布局
**第四步**: 添加全文搜索和对比功能

**您同意这个方案吗？需要调整哪些部分？我现在就可以开始实现！** 💪
