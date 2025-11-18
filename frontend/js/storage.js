/**
 * 前端本地存储管理器
 * 使用LocalStorage存储用户偏好和历史记录
 */

const StorageManager = {
    // 存储键名
    KEYS: {
        USER_PREFS: 'k8s_user_preferences',
        HISTORY: 'k8s_query_history',
        BOOKMARKS: 'k8s_bookmarks',
        CACHED_NS: 'k8s_cached_namespaces',
        CACHED_PODS: 'k8s_cached_pods',
        LAST_REFRESH: 'k8s_last_refresh'
    },

    // ========== 用户偏好 ==========

    /**
     * 获取用户偏好
     */
    getUserPreferences() {
        const defaultPrefs = {
            defaultNamespace: '',
            theme: 'light',
            layout: 'default',
            autoRefresh: false,
            refreshInterval: 30,  // 秒
            logsPageSize: 100,
            showTimestamp: true,
            highlightErrors: true,
            defaultLogType: 'all'
        };

        const stored = localStorage.getItem(this.KEYS.USER_PREFS);
        if (!stored) {
            return defaultPrefs;
        }

        try {
            return { ...defaultPrefs, ...JSON.parse(stored) };
        } catch (e) {
            console.error('解析用户偏好失败:', e);
            return defaultPrefs;
        }
    },

    /**
     * 保存用户偏好
     */
    saveUserPreferences(prefs) {
        try {
            const current = this.getUserPreferences();
            const updated = { ...current, ...prefs };
            localStorage.setItem(this.KEYS.USER_PREFS, JSON.stringify(updated));
            console.log('用户偏好已保存:', updated);
            return true;
        } catch (e) {
            console.error('保存用户偏好失败:', e);
            return false;
        }
    },

    // ========== 历史记录 ==========

    /**
     * 获取查询历史（最近20条）
     */
    getHistory(limit = 20) {
        const stored = localStorage.getItem(this.KEYS.HISTORY);
        if (!stored) {
            return [];
        }

        try {
            const history = JSON.parse(stored);
            return history.slice(0, limit);
        } catch (e) {
            console.error('解析历史记录失败:', e);
            return [];
        }
    },

    /**
     * 添加历史记录
     */
    addHistory(item) {
        try {
            const history = this.getHistory(100);  // 保持最多100条

            // 添加时间戳和ID
            const record = {
                id: Date.now(),
                timestamp: new Date().toISOString(),
                ...item
            };

            // 添加到开头
            history.unshift(record);

            // 限制数量
            const limited = history.slice(0, 100);

            localStorage.setItem(this.KEYS.HISTORY, JSON.stringify(limited));
            console.log('已添加历史记录:', record);
            return record;
        } catch (e) {
            console.error('添加历史记录失败:', e);
            return null;
        }
    },

    /**
     * 清空历史记录
     */
    clearHistory() {
        try {
            localStorage.removeItem(this.KEYS.HISTORY);
            console.log('历史记录已清空');
            return true;
        } catch (e) {
            console.error('清空历史记录失败:', e);
            return false;
        }
    },

    /**
     * 删除单条历史记录
     */
    deleteHistoryItem(id) {
        try {
            const history = this.getHistory(100);
            const filtered = history.filter(item => item.id !== id);
            localStorage.setItem(this.KEYS.HISTORY, JSON.stringify(filtered));
            console.log('已删除历史记录:', id);
            return true;
        } catch (e) {
            console.error('删除历史记录失败:', e);
            return false;
        }
    },

    // ========== 书签/收藏 ==========

    /**
     * 获取所有书签
     */
    getBookmarks() {
        const stored = localStorage.getItem(this.KEYS.BOOKMARKS);
        if (!stored) {
            return [];
        }

        try {
            return JSON.parse(stored);
        } catch (e) {
            console.error('解析书签失败:', e);
            return [];
        }
    },

    /**
     * 添加书签
     */
    addBookmark(item) {
        try {
            const bookmarks = this.getBookmarks();

            const bookmark = {
                id: Date.now(),
                createdAt: new Date().toISOString(),
                icon: '⭐',
                ...item
            };

            bookmarks.push(bookmark);
            localStorage.setItem(this.KEYS.BOOKMARKS, JSON.stringify(bookmarks));
            console.log('已添加书签:', bookmark);
            return bookmark;
        } catch (e) {
            console.error('添加书签失败:', e);
            return null;
        }
    },

    /**
     * 删除书签
     */
    deleteBookmark(id) {
        try {
            const bookmarks = this.getBookmarks();
            const filtered = bookmarks.filter(item => item.id !== id);
            localStorage.setItem(this.KEYS.BOOKMARKS, JSON.stringify(filtered));
            console.log('已删除书签:', id);
            return true;
        } catch (e) {
            console.error('删除书签失败:', e);
            return false;
        }
    },

    /**
     * 更新书签
     */
    updateBookmark(id, updates) {
        try {
            const bookmarks = this.getBookmarks();
            const index = bookmarks.findIndex(item => item.id === id);
            if (index === -1) {
                console.error('书签不存在:', id);
                return false;
            }

            bookmarks[index] = { ...bookmarks[index], ...updates };
            localStorage.setItem(this.KEYS.BOOKMARKS, JSON.stringify(bookmarks));
            console.log('已更新书签:', bookmarks[index]);
            return true;
        } catch (e) {
            console.error('更新书签失败:', e);
            return false;
        }
    },

    // ========== 临时缓存（SessionStorage） ==========

    /**
     * 缓存namespace列表（会话级别）
     */
    cacheNamespaces(namespaces) {
        try {
            sessionStorage.setItem(this.KEYS.CACHED_NS, JSON.stringify({
                data: namespaces,
                timestamp: Date.now()
            }));
            return true;
        } catch (e) {
            console.error('缓存namespace失败:', e);
            return false;
        }
    },

    /**
     * 获取缓存的namespace列表
     */
    getCachedNamespaces(maxAge = 60000) {  // 默认60秒过期
        try {
            const stored = sessionStorage.getItem(this.KEYS.CACHED_NS);
            if (!stored) {
                return null;
            }

            const { data, timestamp } = JSON.parse(stored);
            const age = Date.now() - timestamp;

            if (age > maxAge) {
                console.log('Namespace缓存已过期');
                return null;
            }

            return data;
        } catch (e) {
            console.error('获取缓存namespace失败:', e);
            return null;
        }
    },

    /**
     * 缓存Pod列表
     */
    cachePods(namespace, pods) {
        try {
            const cached = JSON.parse(sessionStorage.getItem(this.KEYS.CACHED_PODS) || '{}');
            cached[namespace] = {
                data: pods,
                timestamp: Date.now()
            };
            sessionStorage.setItem(this.KEYS.CACHED_PODS, JSON.stringify(cached));
            return true;
        } catch (e) {
            console.error('缓存pods失败:', e);
            return false;
        }
    },

    /**
     * 获取缓存的Pod列表
     */
    getCachedPods(namespace, maxAge = 30000) {  // 默认30秒过期
        try {
            const cached = JSON.parse(sessionStorage.getItem(this.KEYS.CACHED_PODS) || '{}');
            if (!cached[namespace]) {
                return null;
            }

            const { data, timestamp } = cached[namespace];
            const age = Date.now() - timestamp;

            if (age > maxAge) {
                console.log(`Pod缓存已过期: ${namespace}`);
                return null;
            }

            return data;
        } catch (e) {
            console.error('获取缓存pods失败:', e);
            return null;
        }
    },

    /**
     * 清空所有缓存
     */
    clearAllCache() {
        try {
            sessionStorage.removeItem(this.KEYS.CACHED_NS);
            sessionStorage.removeItem(this.KEYS.CACHED_PODS);
            sessionStorage.removeItem(this.KEYS.LAST_REFRESH);
            console.log('所有缓存已清空');
            return true;
        } catch (e) {
            console.error('清空缓存失败:', e);
            return false;
        }
    },

    // ========== 实用工具 ==========

    /**
     * 获取存储使用情况
     */
    getStorageStats() {
        try {
            const stats = {
                localStorage: {
                    used: 0,
                    items: {}
                },
                sessionStorage: {
                    used: 0,
                    items: {}
                }
            };

            // LocalStorage
            for (let key in localStorage) {
                if (localStorage.hasOwnProperty(key) && key.startsWith('k8s_')) {
                    const value = localStorage.getItem(key);
                    const size = new Blob([value]).size;
                    stats.localStorage.used += size;
                    stats.localStorage.items[key] = size;
                }
            }

            // SessionStorage
            for (let key in sessionStorage) {
                if (sessionStorage.hasOwnProperty(key) && key.startsWith('k8s_')) {
                    const value = sessionStorage.getItem(key);
                    const size = new Blob([value]).size;
                    stats.sessionStorage.used += size;
                    stats.sessionStorage.items[key] = size;
                }
            }

            return stats;
        } catch (e) {
            console.error('获取存储统计失败:', e);
            return null;
        }
    },

    /**
     * 导出所有数据
     */
    exportData() {
        try {
            const data = {
                preferences: this.getUserPreferences(),
                history: this.getHistory(100),
                bookmarks: this.getBookmarks(),
                exportedAt: new Date().toISOString()
            };

            return JSON.stringify(data, null, 2);
        } catch (e) {
            console.error('导出数据失败:', e);
            return null;
        }
    },

    /**
     * 导入数据
     */
    importData(jsonString) {
        try {
            const data = JSON.parse(jsonString);

            if (data.preferences) {
                this.saveUserPreferences(data.preferences);
            }

            if (data.history) {
                localStorage.setItem(this.KEYS.HISTORY, JSON.stringify(data.history));
            }

            if (data.bookmarks) {
                localStorage.setItem(this.KEYS.BOOKMARKS, JSON.stringify(data.bookmarks));
            }

            console.log('数据导入成功');
            return true;
        } catch (e) {
            console.error('导入数据失败:', e);
            return false;
        }
    }
};

// 导出到全局
window.StorageManager = StorageManager;
