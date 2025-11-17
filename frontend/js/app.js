// K8s日志查询系统 - 前端应用

const API_BASE = '/api';

// 应用状态
const appState = {
    currentView: 'single-query',
    namespaces: [],
    pods: [],
    batchResults: [],
    currentNamespace: null
};

// 初始化应用
document.addEventListener('DOMContentLoaded', function() {
    initNavigation();
    initSingleQuery();
    initBatchQuery();
    initDownload();
    initStats();
    checkHealth();

    // 定期检查健康状态
    setInterval(checkHealth, 60000);
});

// 导航功能
function initNavigation() {
    const menuItems = document.querySelectorAll('.list-group-item[data-view]');
    menuItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const view = this.getAttribute('data-view');
            switchView(view);
        });
    });
}

function switchView(viewName) {
    // 隐藏所有视图
    document.querySelectorAll('.view-container').forEach(v => v.style.display = 'none');

    // 显示目标视图
    const targetView = document.getElementById(`${viewName}-view`);
    if (targetView) {
        targetView.style.display = 'block';
    }

    // 更新菜单状态
    document.querySelectorAll('.list-group-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-view="${viewName}"]`).classList.add('active');

    appState.currentView = viewName;
}

// 健康检查
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();
        const statusEl = document.getElementById('health-status');

        if (data.success) {
            statusEl.textContent = '正常';
            statusEl.className = 'text-white health-ok';
        } else {
            statusEl.textContent = '异常';
            statusEl.className = 'text-white health-error';
        }
    } catch (error) {
        const statusEl = document.getElementById('health-status');
        statusEl.textContent = '连接失败';
        statusEl.className = 'text-white health-error';
    }
}

// ========== 单Pod查询 ==========

function initSingleQuery() {
    // 加载namespace按钮
    document.getElementById('load-namespaces-btn').addEventListener('click', loadNamespaces);

    // 加载pods按钮
    document.getElementById('load-pods-btn').addEventListener('click', loadPods);

    // namespace选择
    document.getElementById('single-namespace-select').addEventListener('change', function() {
        appState.currentNamespace = this.value;
    });

    // 查询表单
    document.getElementById('single-query-form').addEventListener('submit', function(e) {
        e.preventDefault();
        querySinglePod();
    });

    // 清空按钮
    document.getElementById('clear-single-result').addEventListener('click', function() {
        document.getElementById('single-query-result').style.display = 'none';
        document.getElementById('export-single-result').disabled = true;
    });

    // 导出按钮
    document.getElementById('export-single-result').addEventListener('click', exportSingleResult);
}

async function loadNamespaces() {
    try {
        const pattern = document.getElementById('single-namespace-input').value;
        const url = pattern ? `${API_BASE}/namespaces?pattern=${encodeURIComponent(pattern)}` : `${API_BASE}/namespaces`;

        const response = await fetch(url);
        const data = await response.json();

        if (data.success) {
            appState.namespaces = data.data;
            const select = document.getElementById('single-namespace-select');
            select.innerHTML = data.data.map(ns =>
                `<option value="${ns}">${ns}</option>`
            ).join('');

            showToast('success', `加载了 ${data.count} 个namespace`);
        } else {
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function loadPods() {
    const namespace = appState.currentNamespace || document.getElementById('single-namespace-select').value;

    if (!namespace) {
        showToast('warning', '请先选择namespace');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/pods?namespace=${encodeURIComponent(namespace)}`);
        const data = await response.json();

        if (data.success) {
            appState.pods = data.data;
            const select = document.getElementById('single-pod-select');
            select.innerHTML = data.data.map(pod =>
                `<option value="${pod.name}">${pod.name} (${pod.status})</option>`
            ).join('');

            showToast('success', `加载了 ${data.count} 个pod`);
        } else {
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function querySinglePod() {
    const namespace = document.getElementById('single-namespace-select').value;
    const pod = document.getElementById('single-pod-select').value;
    const logType = document.getElementById('single-log-type').value;
    const tail = parseInt(document.getElementById('single-tail').value);
    const keywordsStr = document.getElementById('single-keywords').value;
    const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : [];

    if (!namespace || !pod) {
        showToast('warning', '请选择namespace和pod');
        return;
    }

    // 显示加载状态
    document.getElementById('single-query-loading').style.display = 'block';
    document.getElementById('single-query-result').style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/logs/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ namespace, pod, type: logType, tail, keywords })
        });

        const data = await response.json();

        if (data.success) {
            displaySingleQueryResult(data.data);
            document.getElementById('export-single-result').disabled = false;
            showToast('success', `查询完成，找到 ${data.data.total_matches} 条匹配`);
        } else {
            showToast('error', `查询失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    } finally {
        document.getElementById('single-query-loading').style.display = 'none';
    }
}

function displaySingleQueryResult(result) {
    const container = document.getElementById('single-result-content');
    let html = '';

    // 统计信息
    html += `
        <div class="log-stats">
            <strong>Namespace:</strong> ${result.namespace} &nbsp;|&nbsp;
            <strong>Pod:</strong> ${result.pod} &nbsp;|&nbsp;
            <strong>Console匹配:</strong> ${result.console_matches} &nbsp;|&nbsp;
            <strong>文件匹配:</strong> ${result.file_matches} &nbsp;|&nbsp;
            <strong>总匹配:</strong> ${result.total_matches}
        </div>
    `;

    // Console日志
    if (result.logs.console_log && result.logs.console_log.length > 0) {
        html += `
            <div class="log-filepath">
                <i class="bi bi-terminal"></i> Console日志 (${result.logs.console_log.length} 行)
            </div>
            <div class="log-viewer">
                ${highlightLogs(result.logs.console_log)}
            </div>
        `;
    }

    // 文件日志
    if (result.logs.file_logs) {
        for (const [filepath, lines] of Object.entries(result.logs.file_logs)) {
            if (lines.length > 0) {
                html += `
                    <div class="log-filepath">
                        <i class="bi bi-file-text"></i> ${filepath} (${lines.length} 行)
                    </div>
                    <div class="log-viewer">
                        ${highlightLogs(lines)}
                    </div>
                `;
            }
        }
    }

    // 如果没有结果
    if (result.total_matches === 0) {
        html = `
            <div class="empty-state">
                <i class="bi bi-inbox"></i>
                <p>未找到匹配的日志</p>
            </div>
        `;
    }

    container.innerHTML = html;
    document.getElementById('single-query-result').style.display = 'block';

    // 保存结果用于导出
    appState.lastSingleResult = result;
}

function highlightLogs(lines) {
    return lines.map((line, index) => {
        let highlighted = escapeHtml(line);

        // 高亮ERROR
        highlighted = highlighted.replace(/(ERROR|Exception|FATAL)/gi, '<span class="error-highlight">$1</span>');

        // 高亮WARN
        highlighted = highlighted.replace(/(WARN|WARNING)/gi, '<span class="warning-highlight">$1</span>');

        // 高亮其他关键字
        const keywords = document.getElementById('single-keywords').value;
        if (keywords) {
            const keywordList = keywords.split(',').map(k => k.trim()).filter(k => k);
            keywordList.forEach(kw => {
                const regex = new RegExp(`(${escapeRegex(kw)})`, 'gi');
                highlighted = highlighted.replace(regex, '<span class="keyword-highlight">$1</span>');
            });
        }

        return `<div class="log-line">${index + 1}: ${highlighted}</div>`;
    }).join('');
}

function exportSingleResult() {
    if (!appState.lastSingleResult) {
        showToast('warning', '没有可导出的结果');
        return;
    }

    const result = appState.lastSingleResult;
    let content = `K8s日志查询结果\n`;
    content += `Namespace: ${result.namespace}\n`;
    content += `Pod: ${result.pod}\n`;
    content += `查询时间: ${new Date().toLocaleString()}\n`;
    content += `\n${'='.repeat(80)}\n\n`;

    // Console日志
    if (result.logs.console_log && result.logs.console_log.length > 0) {
        content += `[Console日志]\n`;
        content += result.logs.console_log.join('\n');
        content += `\n\n`;
    }

    // 文件日志
    if (result.logs.file_logs) {
        for (const [filepath, lines] of Object.entries(result.logs.file_logs)) {
            content += `[${filepath}]\n`;
            content += lines.join('\n');
            content += `\n\n`;
        }
    }

    downloadTextFile(content, `logs-${result.namespace}-${result.pod}.txt`);
    showToast('success', '导出成功');
}

// ========== 批量查询 ==========

function initBatchQuery() {
    // 快速选择pattern
    document.querySelectorAll('[data-pattern]').forEach(badge => {
        badge.addEventListener('click', function() {
            document.getElementById('batch-namespaces').value = this.getAttribute('data-pattern');
        });
    });

    // 快速选择关键字
    document.querySelectorAll('[data-keyword]').forEach(badge => {
        badge.addEventListener('click', function() {
            const input = document.getElementById('batch-keywords');
            const keyword = this.getAttribute('data-keyword');
            const current = input.value;
            if (current) {
                input.value = current + ',' + keyword;
            } else {
                input.value = keyword;
            }
        });
    });

    // 批量查询表单
    document.getElementById('batch-query-form').addEventListener('submit', function(e) {
        e.preventDefault();
        batchQueryLogs();
    });

    // 清空按钮
    document.getElementById('clear-batch-result').addEventListener('click', function() {
        document.getElementById('batch-query-result').style.display = 'none';
        appState.batchResults = [];
    });
}

async function batchQueryLogs() {
    const namespacesStr = document.getElementById('batch-namespaces').value;
    const keywordsStr = document.getElementById('batch-keywords').value;
    const logType = document.getElementById('batch-log-type').value;
    const tail = parseInt(document.getElementById('batch-tail').value);
    const maxPods = parseInt(document.getElementById('batch-max-pods').value);

    if (!namespacesStr) {
        showToast('warning', '请输入namespace模式');
        return;
    }

    const namespaces = namespacesStr.split(',').map(n => n.trim()).filter(n => n);
    const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : [];

    // 显示进度
    document.getElementById('batch-query-progress').style.display = 'block';
    document.getElementById('batch-progress-text').textContent = '正在查询...';
    document.getElementById('batch-query-result').style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/logs/batch-query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ namespaces, keywords, tail, type: logType, max_pods: maxPods })
        });

        const data = await response.json();

        if (data.success) {
            appState.batchResults = data.data;
            displayBatchQueryResult(data);
            showToast('success', `批量查询完成，${data.matched_pods}/${data.total_pods} 个pod有匹配`);
        } else {
            showToast('error', `查询失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    } finally {
        document.getElementById('batch-query-progress').style.display = 'none';
    }
}

function displayBatchQueryResult(data) {
    const summary = document.getElementById('batch-result-summary');
    summary.textContent = `总计: ${data.total_pods} 个pod, 匹配: ${data.matched_pods} 个`;

    const tbody = document.querySelector('#batch-result-table tbody');
    tbody.innerHTML = '';

    // 只显示有匹配的结果
    const matchedResults = data.data.filter(r => r.total_matches > 0);

    if (matchedResults.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted">未找到匹配的日志</td>
            </tr>
        `;
    } else {
        matchedResults.forEach((result, index) => {
            const row = `
                <tr>
                    <td>${result.namespace}</td>
                    <td>${result.pod}</td>
                    <td><span class="badge bg-primary">${result.console_matches}</span></td>
                    <td><span class="badge bg-success">${result.file_matches}</span></td>
                    <td><span class="badge bg-info">${result.total_matches}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="viewBatchDetail(${index})">
                            <i class="bi bi-eye"></i> 查看
                        </button>
                    </td>
                </tr>
            `;
            tbody.innerHTML += row;
        });
    }

    document.getElementById('batch-query-result').style.display = 'block';
}

function viewBatchDetail(index) {
    const results = appState.batchResults.filter(r => r.total_matches > 0);
    const result = results[index];

    if (!result) return;

    const modal = new bootstrap.Modal(document.getElementById('log-detail-modal'));
    document.getElementById('log-detail-title').textContent = `${result.namespace} / ${result.pod}`;

    let html = `
        <div class="log-stats">
            <strong>Console匹配:</strong> ${result.console_matches} &nbsp;|&nbsp;
            <strong>文件匹配:</strong> ${result.file_matches} &nbsp;|&nbsp;
            <strong>总匹配:</strong> ${result.total_matches}
        </div>
    `;

    // Console日志
    if (result.logs.console_log && result.logs.console_log.length > 0) {
        html += `
            <div class="log-filepath">
                <i class="bi bi-terminal"></i> Console日志 (${result.logs.console_log.length} 行)
            </div>
            <div class="log-viewer">
                ${highlightBatchLogs(result.logs.console_log)}
            </div>
        `;
    }

    // 文件日志
    if (result.logs.file_logs) {
        for (const [filepath, lines] of Object.entries(result.logs.file_logs)) {
            if (lines.length > 0) {
                html += `
                    <div class="log-filepath">
                        <i class="bi bi-file-text"></i> ${filepath} (${lines.length} 行)
                    </div>
                    <div class="log-viewer">
                        ${highlightBatchLogs(lines)}
                    </div>
                `;
            }
        }
    }

    document.getElementById('log-detail-content').innerHTML = html;
    modal.show();
}

function highlightBatchLogs(lines) {
    return lines.map((line, index) => {
        let highlighted = escapeHtml(line);

        // 高亮ERROR
        highlighted = highlighted.replace(/(ERROR|Exception|FATAL)/gi, '<span class="error-highlight">$1</span>');

        // 高亮WARN
        highlighted = highlighted.replace(/(WARN|WARNING)/gi, '<span class="warning-highlight">$1</span>');

        // 高亮关键字
        const keywords = document.getElementById('batch-keywords').value;
        if (keywords) {
            const keywordList = keywords.split(',').map(k => k.trim()).filter(k => k);
            keywordList.forEach(kw => {
                const regex = new RegExp(`(${escapeRegex(kw)})`, 'gi');
                highlighted = highlighted.replace(regex, '<span class="keyword-highlight">$1</span>');
            });
        }

        return `<div class="log-line">${index + 1}: ${highlighted}</div>`;
    }).join('');
}

// ========== 日志下载 ==========

function initDownload() {
    document.getElementById('download-form').addEventListener('submit', async function(e) {
        e.preventDefault();

        const namespace = document.getElementById('download-namespace').value;
        const podsStr = document.getElementById('download-pods').value;
        const logType = document.getElementById('download-log-type').value;
        const tail = parseInt(document.getElementById('download-tail').value);
        const keywordsStr = document.getElementById('download-keywords').value;

        if (!namespace || !podsStr) {
            showToast('warning', '请输入namespace和pod名称');
            return;
        }

        const pods = podsStr.split(',').map(p => p.trim()).filter(p => p);
        const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : [];

        // 显示下载状态
        const statusEl = document.getElementById('download-status');
        statusEl.textContent = '正在准备下载...';
        statusEl.style.display = 'block';

        try {
            const response = await fetch(`${API_BASE}/logs/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ namespace, pods, type: logType, tail, keywords, format: 'zip' })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `logs-${namespace}-${Date.now()}.zip`;
                a.click();
                window.URL.revokeObjectURL(url);

                statusEl.className = 'alert alert-success';
                statusEl.textContent = '下载成功！';
                setTimeout(() => { statusEl.style.display = 'none'; }, 3000);
            } else {
                const error = await response.json();
                throw new Error(error.error || '下载失败');
            }
        } catch (error) {
            statusEl.className = 'alert alert-danger';
            statusEl.textContent = `下载失败: ${error.message}`;
        }
    });
}

// ========== 统计分析 ==========

function initStats() {
    document.getElementById('stats-form').addEventListener('submit', function(e) {
        e.preventDefault();
        generateStats();
    });
}

async function generateStats() {
    const namespacesStr = document.getElementById('stats-namespaces').value;
    const keywordsStr = document.getElementById('stats-keywords').value;

    if (!namespacesStr || !keywordsStr) {
        showToast('warning', '请输入namespace模式和关键字');
        return;
    }

    const namespaces = namespacesStr.split(',').map(n => n.trim()).filter(n => n);
    const keywords = keywordsStr.split(',').map(k => k.trim()).filter(k => k);

    // 显示加载状态
    document.getElementById('stats-loading').style.display = 'block';
    document.getElementById('stats-result').style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/stats`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ namespaces, keywords })
        });

        const result = await response.json();

        if (result.success) {
            displayStats(result.data);
            showToast('success', '统计分析完成');
        } else {
            showToast('error', `统计失败: ${result.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    } finally {
        document.getElementById('stats-loading').style.display = 'none';
    }
}

function displayStats(data) {
    // 基本统计
    document.getElementById('stats-total-pods').textContent = data.total_pods;
    document.getElementById('stats-matched-pods').textContent = data.matched_pods;
    document.getElementById('stats-total-matches').textContent = data.total_matches;

    const matchRate = data.total_pods > 0 ? ((data.matched_pods / data.total_pods) * 100).toFixed(1) : 0;
    document.getElementById('stats-match-rate').textContent = `${matchRate}%`;

    // Namespace分布
    const nsTbody = document.querySelector('#stats-namespace-table tbody');
    nsTbody.innerHTML = '';

    const totalMatches = Object.values(data.by_namespace).reduce((a, b) => a + b, 0);

    for (const [ns, count] of Object.entries(data.by_namespace)) {
        const percentage = totalMatches > 0 ? ((count / totalMatches) * 100).toFixed(1) : 0;
        nsTbody.innerHTML += `
            <tr>
                <td>${ns}</td>
                <td><span class="badge bg-primary">${count}</span></td>
                <td>${percentage}%</td>
            </tr>
        `;
    }

    // Top Pods
    const topTbody = document.querySelector('#stats-top-pods-table tbody');
    topTbody.innerHTML = '';

    data.top_pods.forEach((pod, index) => {
        topTbody.innerHTML += `
            <tr>
                <td>${index + 1}</td>
                <td>${pod.namespace}</td>
                <td>${pod.pod}</td>
                <td><span class="badge bg-danger">${pod.count}</span></td>
            </tr>
        `;
    });

    document.getElementById('stats-result').style.display = 'block';
}

// ========== 工具函数 ==========

function showToast(type, message) {
    // 简单的toast通知
    const colors = {
        success: '#28a745',
        error: '#dc3545',
        warning: '#ffc107',
        info: '#17a2b8'
    };

    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        background: ${colors[type] || colors.info};
        color: white;
        padding: 15px 20px;
        border-radius: 5px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        z-index: 9999;
        animation: slideInRight 0.3s;
    `;
    toast.textContent = message;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function downloadTextFile(content, filename) {
    const blob = new Blob([content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
}

// CSS动画
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from { transform: translateX(100%); }
        to { transform: translateX(0); }
    }
    @keyframes slideOutRight {
        from { transform: translateX(0); }
        to { transform: translateX(100%); }
    }
`;
document.head.appendChild(style);
