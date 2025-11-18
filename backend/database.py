"""
SQLite数据库管理模块
提供日志索引、查询历史、书签等功能
使用连接池优化性能
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
from queue import Queue, Empty
from threading import Lock
import os

logger = logging.getLogger(__name__)


class ConnectionPool:
    """SQLite连接池"""

    def __init__(self, db_path: str, pool_size: int = 10, timeout: int = 30):
        """
        初始化连接池

        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小
            timeout: 连接超时时间（秒）
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool = Queue(maxsize=pool_size)
        self._lock = Lock()
        self._created_connections = 0

        logger.info(f"初始化数据库连接池: 大小={pool_size}, 超时={timeout}秒")

    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=self.timeout, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # 性能优化配置
        conn.execute('PRAGMA journal_mode=WAL')  # Write-Ahead Logging
        conn.execute('PRAGMA synchronous=NORMAL')  # 平衡性能和安全
        conn.execute('PRAGMA cache_size=-10000')  # 10MB缓存
        conn.execute('PRAGMA temp_store=MEMORY')  # 临时表使用内存
        conn.execute('PRAGMA mmap_size=268435456')  # 256MB内存映射
        conn.execute('PRAGMA foreign_keys=ON')  # 启用外键

        self._created_connections += 1
        logger.debug(f"创建数据库连接 #{self._created_connections}")

        return conn

    def get_connection(self) -> sqlite3.Connection:
        """从连接池获取连接"""
        try:
            # 尝试从池中获取连接
            conn = self._pool.get(block=False)
            logger.debug("从连接池获取连接")
            return conn
        except Empty:
            # 池为空，创建新连接
            with self._lock:
                if self._created_connections < self.pool_size:
                    return self._create_connection()
                else:
                    # 达到连接池大小，阻塞等待
                    logger.debug("连接池已满，等待可用连接...")
                    return self._pool.get(block=True, timeout=self.timeout)

    def return_connection(self, conn: sqlite3.Connection):
        """归还连接到池"""
        try:
            self._pool.put(conn, block=False)
            logger.debug("连接已归还到连接池")
        except:
            # 池已满，关闭连接
            conn.close()
            with self._lock:
                self._created_connections -= 1
            logger.debug("连接池已满，关闭多余连接")

    def close_all(self):
        """关闭所有连接"""
        logger.info("正在关闭所有数据库连接...")
        closed = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get(block=False)
                conn.close()
                closed += 1
            except Empty:
                break

        logger.info(f"已关闭 {closed} 个数据库连接")

    @contextmanager
    def get_connection_context(self):
        """获取数据库连接（上下文管理器）"""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.return_connection(conn)


class Database:
    """SQLite数据库管理器"""

    def __init__(self, db_path: str = 'k8s_logs.db', pool_size: int = 10, timeout: int = 30):
        """
        初始化数据库

        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小
            timeout: 连接超时时间
        """
        self.db_path = db_path
        self._pool = ConnectionPool(db_path, pool_size, timeout)

        # 初始化数据库结构
        self.init_database()

        logger.info(f"数据库管理器初始化完成: {db_path}")

    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        with self._pool.get_connection_context() as conn:
            yield conn

    def init_database(self):
        """初始化数据库表结构"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 日志文件索引表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS log_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    pod_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    file_date DATE,
                    last_modified TIMESTAMP,
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    indexed BOOLEAN DEFAULT 0,
                    UNIQUE(namespace, pod_name, file_path)
                )
            ''')

            # 查询历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    namespace TEXT,
                    pod_name TEXT,
                    file_path TEXT,
                    keywords TEXT,
                    parameters TEXT,
                    result_count INTEGER,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    execution_time REAL
                )
            ''')

            # 收藏夹表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    icon TEXT DEFAULT '⭐',
                    namespace TEXT,
                    pod_pattern TEXT,
                    file_pattern TEXT,
                    keywords TEXT,
                    config TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP
                )
            ''')

            # 日志统计表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS log_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    pod_name TEXT NOT NULL,
                    date DATE NOT NULL,
                    error_count INTEGER DEFAULT 0,
                    warn_count INTEGER DEFAULT 0,
                    total_lines INTEGER DEFAULT 0,
                    file_count INTEGER DEFAULT 0,
                    UNIQUE(namespace, pod_name, date)
                )
            ''')

            # 全文搜索表（FTS5）
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS log_content_fts USING fts5(
                    namespace,
                    pod_name,
                    file_path,
                    content,
                    tokenize = 'porter unicode61'
                )
            ''')

            # 创建索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_log_files_namespace_pod
                ON log_files(namespace, pod_name)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_log_files_date
                ON log_files(file_date)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_query_history_executed_at
                ON query_history(executed_at)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_bookmarks_name
                ON bookmarks(name)
            ''')

            logger.info(f"数据库初始化完成: {self.db_path}")

    # ==================== 日志文件管理 ====================

    def index_log_file(self, namespace: str, pod_name: str, file_info: Dict):
        """
        索引单个日志文件

        Args:
            namespace: 命名空间
            pod_name: Pod名称
            file_info: 文件信息字典
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO log_files
                (namespace, pod_name, file_path, file_name, file_size, file_date, last_modified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                namespace,
                pod_name,
                file_info['path'],
                file_info['name'],
                file_info.get('size_bytes', 0),
                file_info.get('date'),
                file_info.get('modified')
            ))

            logger.debug(f"索引文件: {namespace}/{pod_name}/{file_info['name']}")

    def index_log_files_batch(self, namespace: str, pod_name: str, files: List[Dict]):
        """批量索引日志文件"""
        for file_info in files:
            self.index_log_file(namespace, pod_name, file_info)

        logger.info(f"批量索引完成: {namespace}/{pod_name} - {len(files)}个文件")

    def get_log_files(self, namespace: str, pod_name: str,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None) -> List[Dict]:
        """
        获取日志文件列表

        Args:
            namespace: 命名空间
            pod_name: Pod名称
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            文件列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT * FROM log_files
                WHERE namespace = ? AND pod_name = ?
            '''
            params = [namespace, pod_name]

            if start_date and end_date:
                query += ' AND file_date BETWEEN ? AND ?'
                params.extend([start_date, end_date])

            query += ' ORDER BY file_date DESC, file_name DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    def get_file_by_path(self, namespace: str, pod_name: str, file_path: str) -> Optional[Dict]:
        """根据路径获取单个文件信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM log_files
                WHERE namespace = ? AND pod_name = ? AND file_path = ?
            ''', (namespace, pod_name, file_path))

            row = cursor.fetchone()
            return dict(row) if row else None

    # ==================== 查询历史管理 ====================

    def add_query_history(self, action: str, **kwargs):
        """
        添加查询历史记录

        Args:
            action: 操作类型（view_log, search, download等）
            **kwargs: 其他参数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO query_history
                (action, namespace, pod_name, file_path, keywords, parameters, result_count, execution_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                action,
                kwargs.get('namespace'),
                kwargs.get('pod_name'),
                kwargs.get('file_path'),
                json.dumps(kwargs.get('keywords', [])),
                json.dumps(kwargs.get('parameters', {})),
                kwargs.get('result_count', 0),
                kwargs.get('execution_time', 0)
            ))

            logger.debug(f"添加查询历史: {action}")

    def get_query_history(self, limit: int = 100) -> List[Dict]:
        """获取查询历史（最近N条）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM query_history
                ORDER BY executed_at DESC
                LIMIT ?
            ''', (limit,))

            rows = cursor.fetchall()
            results = []

            for row in rows:
                item = dict(row)
                # 解析JSON字段
                if item.get('keywords'):
                    item['keywords'] = json.loads(item['keywords'])
                if item.get('parameters'):
                    item['parameters'] = json.loads(item['parameters'])
                results.append(item)

            return results

    def clear_query_history(self, older_than_days: int = 30):
        """清理旧的查询历史"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                DELETE FROM query_history
                WHERE executed_at < date('now', ? || ' days')
            ''', (f'-{older_than_days}',))

            deleted = cursor.rowcount
            logger.info(f"清理了 {deleted} 条旧查询历史")

    # ==================== 书签管理 ====================

    def add_bookmark(self, name: str, **kwargs) -> int:
        """添加书签"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO bookmarks
                (name, icon, namespace, pod_pattern, file_pattern, keywords, config)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                name,
                kwargs.get('icon', '⭐'),
                kwargs.get('namespace'),
                kwargs.get('pod_pattern'),
                kwargs.get('file_pattern'),
                json.dumps(kwargs.get('keywords', [])),
                json.dumps(kwargs.get('config', {}))
            ))

            bookmark_id = cursor.lastrowid
            logger.info(f"添加书签: {name} (ID: {bookmark_id})")
            return bookmark_id

    def get_bookmarks(self) -> List[Dict]:
        """获取所有书签"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM bookmarks
                ORDER BY last_used DESC, created_at DESC
            ''')

            rows = cursor.fetchall()
            results = []

            for row in rows:
                item = dict(row)
                if item.get('keywords'):
                    item['keywords'] = json.loads(item['keywords'])
                if item.get('config'):
                    item['config'] = json.loads(item['config'])
                results.append(item)

            return results

    def delete_bookmark(self, bookmark_id: int):
        """删除书签"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM bookmarks WHERE id = ?', (bookmark_id,))
            logger.info(f"删除书签: ID {bookmark_id}")

    def update_bookmark_last_used(self, bookmark_id: int):
        """更新书签最后使用时间"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE bookmarks
                SET last_used = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (bookmark_id,))

    # ==================== 日志统计 ====================

    def update_log_stats(self, namespace: str, pod_name: str, date: str, stats: Dict):
        """更新日志统计"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO log_stats
                (namespace, pod_name, date, error_count, warn_count, total_lines, file_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                namespace,
                pod_name,
                date,
                stats.get('error_count', 0),
                stats.get('warn_count', 0),
                stats.get('total_lines', 0),
                stats.get('file_count', 0)
            ))

    def get_log_stats(self, namespace: str, pod_name: str,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> List[Dict]:
        """获取日志统计"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT * FROM log_stats
                WHERE namespace = ? AND pod_name = ?
            '''
            params = [namespace, pod_name]

            if start_date and end_date:
                query += ' AND date BETWEEN ? AND ?'
                params.extend([start_date, end_date])

            query += ' ORDER BY date DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    # ==================== 全文搜索 ====================

    def index_log_content(self, namespace: str, pod_name: str, file_path: str, content: str):
        """索引日志内容到FTS5表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 删除旧索引
            cursor.execute('''
                DELETE FROM log_content_fts
                WHERE namespace = ? AND pod_name = ? AND file_path = ?
            ''', (namespace, pod_name, file_path))

            # 插入新索引
            cursor.execute('''
                INSERT INTO log_content_fts (namespace, pod_name, file_path, content)
                VALUES (?, ?, ?, ?)
            ''', (namespace, pod_name, file_path, content))

            logger.debug(f"索引日志内容: {namespace}/{pod_name}/{file_path}")

    def fts_search(self, query: str, namespace: Optional[str] = None,
                   pod_name: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        全文搜索

        Args:
            query: 搜索关键词
            namespace: 过滤命名空间（可选）
            pod_name: 过滤Pod名称（可选）
            limit: 结果数量限制

        Returns:
            搜索结果列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            sql = '''
                SELECT namespace, pod_name, file_path,
                       snippet(log_content_fts, 3, '<mark>', '</mark>', '...', 30) as snippet
                FROM log_content_fts
                WHERE log_content_fts MATCH ?
            '''
            params = [query]

            if namespace:
                sql += ' AND namespace = ?'
                params.append(namespace)

            if pod_name:
                sql += ' AND pod_name = ?'
                params.append(pod_name)

            sql += ' LIMIT ?'
            params.append(limit)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]

    # ==================== 工具方法 ====================

    def get_database_stats(self) -> Dict:
        """获取数据库统计信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # 各表的记录数
            tables = ['log_files', 'query_history', 'bookmarks', 'log_stats']
            for table in tables:
                cursor.execute(f'SELECT COUNT(*) as count FROM {table}')
                stats[table] = cursor.fetchone()['count']

            # 数据库大小
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            stats['db_size_mb'] = round(db_size / 1024 / 1024, 2)

            return stats

    def vacuum(self):
        """优化数据库（压缩空间）"""
        with self.get_connection() as conn:
            conn.execute('VACUUM')
            logger.info("数据库优化完成")


# 全局数据库实例
db = Database('k8s_logs.db')


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)

    # 测试索引文件
    db.index_log_file('erp-prod', 'test-pod-xxx', {
        'path': '/applog/root.log',
        'name': 'root.log',
        'size_bytes': 1024000,
        'date': '2025-01-18',
        'modified': '2025-01-18 10:30:00'
    })

    # 测试获取文件
    files = db.get_log_files('erp-prod', 'test-pod-xxx')
    print(f"找到 {len(files)} 个文件:")
    for f in files:
        print(f"  - {f['file_name']} ({f['file_size']} bytes)")

    # 测试查询历史
    db.add_query_history('view_log', namespace='erp-prod', pod_name='test-pod-xxx',
                        file_path='/applog/root.log', result_count=100, execution_time=0.5)

    history = db.get_query_history(10)
    print(f"\n查询历史 ({len(history)} 条):")
    for h in history:
        print(f"  - {h['action']}: {h['namespace']}/{h['pod_name']}")

    # 测试书签
    bookmark_id = db.add_bookmark('ERP生产错误', namespace='erp-prod',
                                 keywords=['error', 'exception'])
    bookmarks = db.get_bookmarks()
    print(f"\n书签 ({len(bookmarks)} 个):")
    for b in bookmarks:
        print(f"  - {b['icon']} {b['name']}")

    # 数据库统计
    stats = db.get_database_stats()
    print(f"\n数据库统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
