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
    initNamespaceExplorer();
    initErrorContext();
    initSingleQuery();
    initBatchQuery();
    initDownload();
    initStats();
    initFileBrowser();
    initLogout();
    checkHealth();

    // 定期检查健康状态
    setInterval(checkHealth, 60000);
});

// 登出功能
function initLogout() {
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async function() {
            if (confirm('确定要退出登录吗？')) {
                try {
                    const response = await fetch(`${API_BASE}/logout`, {
                        method: 'POST',
                        credentials: 'include'
                    });

                    if (response.ok) {
                        // 跳转到登录页
                        window.location.href = '/';
                    } else {
                        alert('登出失败，请重试');
                    }
                } catch (error) {
                    console.error('登出错误:', error);
                    alert('网络错误，请重试');
                }
            }
        });
    }
}

// 处理未授权错误（会话过期）
function handleUnauthorized(response) {
    if (response.status === 401) {
        alert('登录已过期，请重新登录');
        window.location.href = '/';
        return true;
    }
    return false;
}

// 封装fetch调用，自动处理未授权错误
async function apiFetch(url, options = {}) {
    options.credentials = 'include';
    const response = await fetch(url, options);

    if (handleUnauthorized(response)) {
        throw new Error('Unauthorized');
    }

    return response;
}

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

// ========== 命名空间浏览器 ==========

function initNamespaceExplorer() {
    // 加载按钮
    document.getElementById('load-ns-explorer-btn').addEventListener('click', loadNamespaceExplorer);

    // 页面加载时自动加载
    setTimeout(loadNamespaceExplorer, 500);
}

async function loadNamespaceExplorer() {
    const pattern = document.getElementById('ns-explorer-pattern').value;
    const url = pattern ? `${API_BASE}/pods/grouped?pattern=${encodeURIComponent(pattern)}` : `${API_BASE}/pods/grouped`;

    // 显示加载状态
    document.getElementById('ns-explorer-loading').style.display = 'block';
    document.getElementById('ns-explorer-result').style.display = 'none';

    try {
        const response = await fetch(url);
        const data = await response.json();

        if (data.success) {
            displayNamespaceExplorer(data.data);
            showToast('success', `加载了 ${data.namespace_count} 个命名空间`);
        } else {
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    } finally {
        document.getElementById('ns-explorer-loading').style.display = 'none';
    }
}

function displayNamespaceExplorer(groupedPods) {
    const contentDiv = document.getElementById('ns-explorer-content');
    let html = '';

    // 统计
    let totalPods = 0;
    const nsCount = Object.keys(groupedPods).length;

    if (nsCount === 0) {
        html = `
            <div class="alert alert-warning">
                <i class="bi bi-inbox"></i> 未找到任何命名空间或Pods
            </div>
        `;
    } else {
        // 按命名空间分组展示
        for (const [namespace, pods] of Object.entries(groupedPods)) {
            totalPods += pods.length;

            html += `
                <div class="card mb-3">
                    <div class="card-header bg-primary text-white">
                        <h5 class="mb-0">
                            <i class="bi bi-box"></i> ${namespace}
                            <span class="badge bg-light text-dark float-end">${pods.length} Pods</span>
                        </h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-sm table-hover">
                                <thead>
                                    <tr>
                                        <th>Pod名称</th>
                                        <th>状态</th>
                                        <th>就绪</th>
                                        <th>操作</th>
                                    </tr>
                                </thead>
                                <tbody>
            `;

            pods.forEach(pod => {
                const statusBadge = pod.status === 'Running' ? 'bg-success' : 'bg-warning';
                const readyIcon = pod.ready ? '<i class="bi bi-check-circle-fill text-success"></i>' : '<i class="bi bi-x-circle-fill text-danger"></i>';

                html += `
                    <tr>
                        <td><code>${pod.name}</code></td>
                        <td><span class="badge ${statusBadge}">${pod.status}</span></td>
                        <td>${readyIcon}</td>
                        <td>
                            <button class="btn btn-sm btn-outline-primary" onclick="quickViewPodLogs('${namespace}', '${pod.name}')">
                                <i class="bi bi-eye"></i> 查看日志
                            </button>
                        </td>
                    </tr>
                `;
            });

            html += `
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `;
        }
    }

    contentDiv.innerHTML = html;

    // 更新统计信息
    document.getElementById('ns-explorer-stats').textContent = `${nsCount} 个命名空间, 共 ${totalPods} 个Pods`;
    document.getElementById('ns-explorer-result').style.display = 'block';
}

function quickViewPodLogs(namespace, pod) {
    // 快速查看Pod日志（切换到单Pod查询视图并自动填充）
    switchView('single-query');
    document.getElementById('single-namespace-input').value = namespace;

    // 模拟加载namespace
    setTimeout(() => {
        const select = document.getElementById('single-namespace-select');
        select.innerHTML = `<option value="${namespace}" selected>${namespace}</option>`;
        appState.currentNamespace = namespace;

        // 模拟加载pod
        setTimeout(() => {
            const podSelect = document.getElementById('single-pod-select');
            podSelect.innerHTML = `<option value="${pod}" selected>${pod}</option>`;
        }, 100);
    }, 100);
}

// ========== 错误上下文查询 ==========

function initErrorContext() {
    // 加载命名空间按钮
    document.getElementById('ec-load-ns-btn').addEventListener('click', loadECNamespaces);

    // Namespace选择变化时加载deployments/pods
    document.getElementById('ec-namespace').addEventListener('change', function() {
        const namespace = this.value;
        const queryType = document.getElementById('ec-query-type').value;
        if (namespace) {
            if (queryType === 'deployment') {
                loadECDeployments(namespace);
            } else {
                loadECPods(namespace);
            }
        }
    });

    // 查询类型切换
    document.getElementById('ec-query-type').addEventListener('change', function() {
        const isDeployment = this.value === 'deployment';
        document.getElementById('ec-deployment-group').style.display = isDeployment ? 'block' : 'none';
        document.getElementById('ec-pod-group').style.display = isDeployment ? 'none' : 'block';

        // 重新加载对应的列表
        const namespace = document.getElementById('ec-namespace').value;
        if (namespace) {
            if (isDeployment) {
                loadECDeployments(namespace);
            } else {
                loadECPods(namespace);
            }
        }
    });

    // 表单提交
    document.getElementById('error-context-form').addEventListener('submit', function(e) {
        e.preventDefault();
        queryErrorContext();
    });

    // 清空结果
    document.getElementById('clear-ec-result').addEventListener('click', function() {
        document.getElementById('ec-result').style.display = 'none';
    });

    // 页面加载时自动加载命名空间
    setTimeout(loadECNamespaces, 500);
}

async function loadECNamespaces() {
    try {
        const response = await fetch(`${API_BASE}/namespaces`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('ec-namespace');
            select.innerHTML = '<option value="">-- 请选择 --</option>' +
                data.data.map(ns => `<option value="${ns}">${ns}</option>`).join('');
            showToast('success', `加载了 ${data.count} 个命名空间`);
        } else {
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function loadECDeployments(namespace) {
    try {
        const response = await fetch(`${API_BASE}/deployments?namespace=${encodeURIComponent(namespace)}`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('ec-deployment');
            select.innerHTML = '<option value="">-- 请选择 --</option>' +
                data.data.map(d => `<option value="${d.name}">${d.name} (${d.type}, ${d.replicas} replicas)</option>`).join('');
        } else {
            showToast('error', `加载deployment失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function loadECPods(namespace) {
    try {
        const response = await fetch(`${API_BASE}/pods?namespace=${encodeURIComponent(namespace)}`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('ec-pod');
            select.innerHTML = '<option value="">-- 请选择 --</option>' +
                data.data.map(p => `<option value="${p.name}">${p.name} (${p.status})</option>`).join('');
        } else {
            showToast('error', `加载pods失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function queryErrorContext() {
    const namespace = document.getElementById('ec-namespace').value;
    const queryType = document.getElementById('ec-query-type').value;
    const deployment = document.getElementById('ec-deployment').value;
    const pod = document.getElementById('ec-pod').value;
    const keywordsStr = document.getElementById('ec-keywords').value;
    const contextLines = parseInt(document.getElementById('ec-context-lines').value);
    const logType = document.getElementById('ec-log-type').value;

    if (!namespace) {
        showToast('warning', '请输入namespace');
        return;
    }

    if (queryType === 'deployment' && !deployment) {
        showToast('warning', '请输入deployment名称');
        return;
    }

    if (queryType === 'pod' && !pod) {
        showToast('warning', '请输入pod名称');
        return;
    }

    const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : ['error', 'exception', 'fatal'];

    // 显示加载状态
    document.getElementById('ec-loading').style.display = 'block';
    document.getElementById('ec-result').style.display = 'none';

    try {
        const requestBody = {
            namespace,
            error_keywords: keywords,
            context_lines: contextLines,
            type: logType
        };

        if (queryType === 'deployment') {
            requestBody.deployment = deployment;
        } else {
            requestBody.pod = pod;
        }

        const response = await fetch(`${API_BASE}/logs/error-context`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();

        if (data.success) {
            displayErrorContext(data);
            showToast('success', `找到 ${data.pods_with_errors}/${data.total_pods} 个Pods有错误`);
        } else {
            showToast('error', `查询失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    } finally {
        document.getElementById('ec-loading').style.display = 'none';
    }
}

function displayErrorContext(data) {
    const summaryEl = document.getElementById('ec-summary');
    summaryEl.textContent = `查询了 ${data.total_pods} 个Pods, 发现 ${data.pods_with_errors} 个Pods有错误`;

    const contentDiv = document.getElementById('ec-content');
    let html = '';

    if (data.pods_with_errors === 0) {
        html = `
            <div class="alert alert-success">
                <i class="bi bi-check-circle"></i> 太好了！未发现任何错误
            </div>
        `;
    } else {
        // 按Pod展示错误上下文
        data.data.forEach((podResult, index) => {
            html += `
                <div class="card mb-3">
                    <div class="card-header bg-danger text-white">
                        <h5 class="mb-0">
                            <i class="bi bi-exclamation-triangle"></i> ${podResult.namespace} / ${podResult.pod}
                            <span class="badge bg-light text-dark float-end">
                                ${podResult.total_error_count} 个错误
                            </span>
                        </h5>
                    </div>
                    <div class="card-body">
            `;

            // Console错误
            if (podResult.error_context.console_errors && podResult.error_context.console_errors.length > 0) {
                html += `
                    <h6 class="text-danger"><i class="bi bi-terminal"></i> Console日志错误 (${podResult.error_context.console_errors.length})</h6>
                `;

                podResult.error_context.console_errors.forEach((errorCtx, idx) => {
                    html += displayErrorContextBlock(errorCtx, `console-${index}-${idx}`);
                });
            }

            // 文件错误
            if (podResult.error_context.file_errors) {
                for (const [filepath, errors] of Object.entries(podResult.error_context.file_errors)) {
                    if (errors.length > 0) {
                        html += `
                            <h6 class="text-danger mt-3"><i class="bi bi-file-text"></i> ${filepath} (${errors.length})</h6>
                        `;

                        errors.forEach((errorCtx, idx) => {
                            html += displayErrorContextBlock(errorCtx, `file-${index}-${idx}`);
                        });
                    }
                }
            }

            html += `
                    </div>
                </div>
            `;
        });
    }

    contentDiv.innerHTML = html;
    document.getElementById('ec-result').style.display = 'block';
}

function displayErrorContextBlock(errorCtx, id) {
    let html = `
        <div class="error-context-block mb-3 p-3 border rounded">
            <div class="mb-2">
                <strong>错误行 #${errorCtx.line_number}:</strong>
                <div class="log-viewer error-line">
                    ${escapeHtml(errorCtx.error_line)}
                </div>
            </div>
    `;

    // 展开/收起按钮
    html += `
        <button class="btn btn-sm btn-outline-secondary mb-2" onclick="toggleContext('${id}')">
            <i class="bi bi-arrows-expand"></i> 查看上下文 (前${errorCtx.before.length}行, 后${errorCtx.after.length}行)
        </button>
        <div id="context-${id}" class="context-content" style="display: none;">
    `;

    // 前置上下文
    if (errorCtx.before.length > 0) {
        html += `<div class="text-muted small">--- 前 ${errorCtx.before.length} 行 ---</div>`;
        html += '<div class="log-viewer context-before">';
        errorCtx.before.forEach((line, idx) => {
            html += `<div class="log-line text-muted">${errorCtx.line_number - errorCtx.before.length + idx}: ${escapeHtml(line)}</div>`;
        });
        html += '</div>';
    }

    // 错误行 (重复显示高亮)
    html += `
        <div class="log-viewer error-highlight-block">
            <div class="log-line text-danger fw-bold">
                ${errorCtx.line_number}: ${escapeHtml(errorCtx.error_line)}
            </div>
        </div>
    `;

    // 后置上下文
    if (errorCtx.after.length > 0) {
        html += `<div class="text-muted small">--- 后 ${errorCtx.after.length} 行 ---</div>`;
        html += '<div class="log-viewer context-after">';
        errorCtx.after.forEach((line, idx) => {
            html += `<div class="log-line text-muted">${errorCtx.line_number + idx + 1}: ${escapeHtml(line)}</div>`;
        });
        html += '</div>';
    }

    html += `
        </div>
        </div>
    `;

    return html;
}

function toggleContext(id) {
    const element = document.getElementById(`context-${id}`);
    if (element.style.display === 'none') {
        element.style.display = 'block';
    } else {
        element.style.display = 'none';
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
    // 加载命名空间按钮
    document.getElementById('batch-load-ns-btn').addEventListener('click', loadBatchNamespaces);

    // 快速选择pattern - 选择以特定前缀开头的namespace
    document.querySelectorAll('[data-pattern]').forEach(badge => {
        badge.addEventListener('click', function() {
            const pattern = this.getAttribute('data-pattern');
            const select = document.getElementById('batch-namespaces-select');
            Array.from(select.options).forEach(opt => {
                if (opt.value.startsWith(pattern)) {
                    opt.selected = true;
                }
            });
        });
    });

    // 全选
    document.getElementById('batch-select-all').addEventListener('click', function() {
        const select = document.getElementById('batch-namespaces-select');
        Array.from(select.options).forEach(opt => opt.selected = true);
    });

    // 清空选择
    document.getElementById('batch-clear-all').addEventListener('click', function() {
        const select = document.getElementById('batch-namespaces-select');
        Array.from(select.options).forEach(opt => opt.selected = false);
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

    // 页面加载时自动加载命名空间
    setTimeout(loadBatchNamespaces, 500);
}

async function loadBatchNamespaces() {
    try {
        const response = await fetch(`${API_BASE}/namespaces`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('batch-namespaces-select');
            select.innerHTML = data.data.map(ns => `<option value="${ns}">${ns}</option>`).join('');
            showToast('success', `加载了 ${data.count} 个命名空间`);
        } else {
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function batchQueryLogs() {
    const select = document.getElementById('batch-namespaces-select');
    const selectedNamespaces = Array.from(select.selectedOptions).map(opt => opt.value);
    const keywordsStr = document.getElementById('batch-keywords').value;
    const logType = document.getElementById('batch-log-type').value;
    const tail = parseInt(document.getElementById('batch-tail').value);
    const maxPods = parseInt(document.getElementById('batch-max-pods').value);

    if (selectedNamespaces.length === 0) {
        showToast('warning', '请选择至少一个namespace');
        return;
    }

    const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : [];

    // 显示进度
    document.getElementById('batch-query-progress').style.display = 'block';
    document.getElementById('batch-progress-text').textContent = '正在查询...';
    document.getElementById('batch-query-result').style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/logs/batch-query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ namespaces: selectedNamespaces, keywords, tail, type: logType, max_pods: maxPods })
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
    // 加载命名空间按钮
    document.getElementById('download-load-ns-btn').addEventListener('click', loadDownloadNamespaces);

    // Namespace选择变化时加载pods
    document.getElementById('download-namespace').addEventListener('change', function() {
        const namespace = this.value;
        if (namespace) {
            loadDownloadPods(namespace);
        }
    });

    // 表单提交
    document.getElementById('download-form').addEventListener('submit', async function(e) {
        e.preventDefault();

        const namespace = document.getElementById('download-namespace').value;
        const podSelect = document.getElementById('download-pods');
        const selectedPods = Array.from(podSelect.selectedOptions).map(opt => opt.value);
        const logType = document.getElementById('download-log-type').value;
        const tail = parseInt(document.getElementById('download-tail').value);
        const keywordsStr = document.getElementById('download-keywords').value;

        if (!namespace || selectedPods.length === 0) {
            showToast('warning', '请选择namespace和至少一个pod');
            return;
        }

        const keywords = keywordsStr ? keywordsStr.split(',').map(k => k.trim()).filter(k => k) : [];

        // 显示下载状态
        const statusEl = document.getElementById('download-status');
        statusEl.textContent = '正在准备下载...';
        statusEl.style.display = 'block';

        try {
            const response = await fetch(`${API_BASE}/logs/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ namespace, pods: selectedPods, type: logType, tail, keywords, format: 'zip' })
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

    // 页面加载时自动加载命名空间
    setTimeout(loadDownloadNamespaces, 500);
}

async function loadDownloadNamespaces() {
    try {
        const response = await fetch(`${API_BASE}/namespaces`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('download-namespace');
            select.innerHTML = '<option value="">-- 请选择 --</option>' +
                data.data.map(ns => `<option value="${ns}">${ns}</option>`).join('');
            showToast('success', `加载了 ${data.count} 个命名空间`);
        } else {
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function loadDownloadPods(namespace) {
    try {
        const response = await fetch(`${API_BASE}/pods?namespace=${encodeURIComponent(namespace)}`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('download-pods');
            select.innerHTML = data.data.map(p =>
                `<option value="${p.name}">${p.name} (${p.status})</option>`
            ).join('');
        } else {
            showToast('error', `加载pods失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

// ========== 统计分析 ==========

function initStats() {
    // 加载命名空间按钮
    document.getElementById('stats-load-ns-btn').addEventListener('click', loadStatsNamespaces);

    // 快速选择pattern
    document.querySelectorAll('[data-stats-pattern]').forEach(badge => {
        badge.addEventListener('click', function() {
            const pattern = this.getAttribute('data-stats-pattern');
            const select = document.getElementById('stats-namespaces-select');
            Array.from(select.options).forEach(opt => {
                if (opt.value.startsWith(pattern)) {
                    opt.selected = true;
                }
            });
        });
    });

    // 全选
    document.getElementById('stats-select-all').addEventListener('click', function() {
        const select = document.getElementById('stats-namespaces-select');
        Array.from(select.options).forEach(opt => opt.selected = true);
    });

    // 清空选择
    document.getElementById('stats-clear-all').addEventListener('click', function() {
        const select = document.getElementById('stats-namespaces-select');
        Array.from(select.options).forEach(opt => opt.selected = false);
    });

    // 快速选择关键字
    document.querySelectorAll('[data-stats-keyword]').forEach(badge => {
        badge.addEventListener('click', function() {
            const input = document.getElementById('stats-keywords');
            const keyword = this.getAttribute('data-stats-keyword');
            const current = input.value;
            if (current) {
                input.value = current + ',' + keyword;
            } else {
                input.value = keyword;
            }
        });
    });

    document.getElementById('stats-form').addEventListener('submit', function(e) {
        e.preventDefault();
        generateStats();
    });

    // 页面加载时自动加载命名空间
    setTimeout(loadStatsNamespaces, 500);
}

async function loadStatsNamespaces() {
    try {
        const response = await fetch(`${API_BASE}/namespaces`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('stats-namespaces-select');
            select.innerHTML = data.data.map(ns => `<option value="${ns}">${ns}</option>`).join('');
            showToast('success', `加载了 ${data.count} 个命名空间`);
        } else {
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function generateStats() {
    const select = document.getElementById('stats-namespaces-select');
    const selectedNamespaces = Array.from(select.selectedOptions).map(opt => opt.value);
    const keywordsStr = document.getElementById('stats-keywords').value;

    if (selectedNamespaces.length === 0 || !keywordsStr) {
        showToast('warning', '请选择至少一个namespace并输入关键字');
        return;
    }

    const keywords = keywordsStr.split(',').map(k => k.trim()).filter(k => k);

    // 显示加载状态
    document.getElementById('stats-loading').style.display = 'block';
    document.getElementById('stats-result').style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/stats`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ namespaces: selectedNamespaces, keywords })
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

// ========== 文件浏览器 ==========

// 文件浏览器状态
const fileBrowserState = {
    currentNamespace: null,
    currentPod: null,
    files: [],
    openTabs: [],
    activeTabId: null,
    tabCounter: 0
};

function initFileBrowser() {
    // 加载命名空间按钮
    const loadNsBtn = document.getElementById('fb-load-ns-btn');
    if (loadNsBtn) {
        loadNsBtn.addEventListener('click', loadFBNamespaces);
    }

    // Namespace选择变化
    const nsSelect = document.getElementById('fb-namespace');
    if (nsSelect) {
        nsSelect.addEventListener('change', function() {
            const namespace = this.value;
            if (namespace) {
                fileBrowserState.currentNamespace = namespace;
                loadFBPods(namespace);
            }
        });
    }

    // Pod选择变化
    const podSelect = document.getElementById('fb-pod');
    if (podSelect) {
        podSelect.addEventListener('change', function() {
            fileBrowserState.currentPod = this.value;
        });
    }

    // 加载文件列表按钮
    const loadFilesBtn = document.getElementById('fb-load-files-btn');
    if (loadFilesBtn) {
        loadFilesBtn.addEventListener('click', loadFiles);
    }

    // 页面加载时自动加载命名空间
    setTimeout(loadFBNamespaces, 500);
}

async function loadFBNamespaces() {
    try {
        const response = await apiFetch(`${API_BASE}/namespaces`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('fb-namespace');
            select.innerHTML = '<option value="">-- 请选择Namespace --</option>' +
                data.data.map(ns => `<option value="${ns}">${ns}</option>`).join('');
            showToast('success', `加载了 ${data.count} 个命名空间`);
        } else {
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function loadFBPods(namespace) {
    try {
        const response = await apiFetch(`${API_BASE}/pods?namespace=${encodeURIComponent(namespace)}`);
        const data = await response.json();

        if (data.success) {
            const select = document.getElementById('fb-pod');
            select.innerHTML = '<option value="">-- 请选择Pod --</option>' +
                data.data.map(p => `<option value="${p.name}">${p.name} (${p.status})</option>`).join('');
        } else {
            showToast('error', `加载pods失败: ${data.error}`);
        }
    } catch (error) {
        showToast('error', `请求失败: ${error.message}`);
    }
}

async function loadFiles() {
    const namespace = fileBrowserState.currentNamespace;
    const pod = fileBrowserState.currentPod;

    if (!namespace || !pod) {
        showToast('warning', '请先选择Namespace和Pod');
        return;
    }

    // 显示加载状态
    const container = document.getElementById('fb-files-container');
    container.innerHTML = '<div class="text-center p-3"><div class="spinner-border spinner-border-sm"></div> 加载中...</div>';

    try {
        const response = await apiFetch(`${API_BASE}/logs/files?namespace=${encodeURIComponent(namespace)}&pod=${encodeURIComponent(pod)}`);
        const data = await response.json();

        if (data.success) {
            fileBrowserState.files = data.data;
            displayFileList(data.data);
            document.getElementById('fb-file-count').textContent = data.count;
            showToast('success', `找到 ${data.count} 个文件`);
        } else {
            container.innerHTML = `
                <div class="alert alert-danger m-2">
                    <i class="bi bi-exclamation-triangle"></i> ${data.error}
                </div>
            `;
            showToast('error', `加载失败: ${data.error}`);
        }
    } catch (error) {
        container.innerHTML = `
            <div class="alert alert-danger m-2">
                <i class="bi bi-exclamation-triangle"></i> ${error.message}
            </div>
        `;
        showToast('error', `请求失败: ${error.message}`);
    }
}

function displayFileList(files) {
    const container = document.getElementById('fb-files-container');

    if (!files || files.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="bi bi-inbox"></i>
                <p>未找到日志文件</p>
            </div>
        `;
        return;
    }

    let html = '<div class="list-group list-group-flush">';

    files.forEach(file => {
        if (file.is_directory) {
            // 目录
            html += `
                <div class="list-group-item">
                    <i class="bi bi-folder-fill text-warning"></i>
                    <strong>${escapeHtml(file.name)}/</strong>
                </div>
            `;
        } else {
            // 文件
            const icon = getFileIcon(file.name);
            html += `
                <a href="#" class="list-group-item list-group-item-action" onclick="openFileInTab('${escapeHtml(file.name)}', '${escapeHtml(file.path)}'); return false;">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="bi ${icon}"></i>
                            <strong>${escapeHtml(file.name)}</strong>
                        </div>
                        <div class="text-muted small">
                            ${file.size_human || ''}
                            ${file.date ? '<br>' + file.date : ''}
                        </div>
                    </div>
                </a>
            `;
        }
    });

    html += '</div>';
    container.innerHTML = html;
}

function getFileIcon(filename) {
    if (filename.endsWith('.log')) return 'bi-file-text text-primary';
    if (filename.endsWith('.txt')) return 'bi-file-text text-secondary';
    if (filename.endsWith('.gz')) return 'bi-file-zip text-warning';
    if (filename.endsWith('.zip')) return 'bi-file-zip text-warning';
    return 'bi-file-earmark text-muted';
}

function openFileInTab(fileName, filePath) {
    const namespace = fileBrowserState.currentNamespace;
    const pod = fileBrowserState.currentPod;

    if (!namespace || !pod) {
        showToast('error', '无效的namespace或pod');
        return;
    }

    // 检查是否已打开
    const existingTab = fileBrowserState.openTabs.find(t => t.filePath === filePath);
    if (existingTab) {
        switchTab(existingTab.id);
        return;
    }

    // 创建新标签页
    const tabId = `tab-${++fileBrowserState.tabCounter}`;
    const tab = {
        id: tabId,
        fileName: fileName,
        filePath: filePath,
        namespace: namespace,
        pod: pod
    };

    fileBrowserState.openTabs.push(tab);
    createTabElement(tab);
    switchTab(tabId);
    loadFileContent(tab);
}

function createTabElement(tab) {
    const tabsNav = document.getElementById('log-tabs');
    const tabsContent = document.getElementById('log-tabs-content');

    // 创建Tab导航
    const tabNav = document.createElement('li');
    tabNav.className = 'nav-item';
    tabNav.setAttribute('role', 'presentation');
    tabNav.innerHTML = `
        <button class="nav-link" id="${tab.id}-tab" data-bs-toggle="tab" data-bs-target="#${tab.id}-pane"
                type="button" role="tab" onclick="switchTab('${tab.id}')">
            <i class="bi bi-file-text"></i> ${escapeHtml(tab.fileName)}
            <button class="btn-close btn-close-white ms-2" onclick="closeTab('${tab.id}'); event.stopPropagation();" aria-label="Close"></button>
        </button>
    `;
    tabsNav.appendChild(tabNav);

    // 创建Tab内容
    const tabPane = document.createElement('div');
    tabPane.className = 'tab-pane fade';
    tabPane.id = `${tab.id}-pane`;
    tabPane.setAttribute('role', 'tabpanel');
    tabPane.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-2 border-bottom pb-2">
            <div>
                <strong>${escapeHtml(tab.namespace)} / ${escapeHtml(tab.pod)}</strong>
                <span class="text-muted"> - ${escapeHtml(tab.filePath)}</span>
            </div>
            <div>
                <button class="btn btn-sm btn-outline-secondary" onclick="refreshTabContent('${tab.id}')">
                    <i class="bi bi-arrow-clockwise"></i> 刷新
                </button>
                <button class="btn btn-sm btn-outline-primary" onclick="downloadTabContent('${tab.id}')">
                    <i class="bi bi-download"></i> 下载
                </button>
            </div>
        </div>
        <div id="${tab.id}-content" class="log-viewer" style="max-height: 600px; overflow-y: auto;">
            <div class="text-center p-3">
                <div class="spinner-border spinner-border-sm"></div> 加载中...
            </div>
        </div>
        <div id="${tab.id}-pagination" class="mt-2"></div>
    `;
    tabsContent.appendChild(tabPane);

    // 移除空状态提示
    const emptyState = tabsContent.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }
}

function switchTab(tabId) {
    fileBrowserState.activeTabId = tabId;
    const tabButton = document.getElementById(`${tabId}-tab`);
    if (tabButton) {
        const tab = new bootstrap.Tab(tabButton);
        tab.show();
    }
}

function closeTab(tabId) {
    // 移除Tab数据
    const index = fileBrowserState.openTabs.findIndex(t => t.id === tabId);
    if (index !== -1) {
        fileBrowserState.openTabs.splice(index, 1);
    }

    // 移除DOM元素
    const tabNav = document.querySelector(`#${tabId}-tab`).parentElement;
    const tabPane = document.getElementById(`${tabId}-pane`);

    tabNav.remove();
    tabPane.remove();

    // 如果没有标签页了，显示空状态
    if (fileBrowserState.openTabs.length === 0) {
        const tabsContent = document.getElementById('log-tabs-content');
        tabsContent.innerHTML = `
            <div class="empty-state">
                <i class="bi bi-inbox"></i>
                <p>请从左侧选择文件查看</p>
            </div>
        `;
        fileBrowserState.activeTabId = null;
    } else {
        // 切换到最后一个标签页
        const lastTab = fileBrowserState.openTabs[fileBrowserState.openTabs.length - 1];
        switchTab(lastTab.id);
    }
}

async function loadFileContent(tab, offset = 0, limit = 1000) {
    const contentDiv = document.getElementById(`${tab.id}-content`);
    contentDiv.innerHTML = '<div class="text-center p-3"><div class="spinner-border spinner-border-sm"></div> 加载中...</div>';

    try {
        const url = `${API_BASE}/logs/content?namespace=${encodeURIComponent(tab.namespace)}&pod=${encodeURIComponent(tab.pod)}&file_path=${encodeURIComponent(tab.filePath)}&offset=${offset}&limit=${limit}`;
        const response = await apiFetch(url);
        const data = await response.json();

        if (data.success) {
            displayFileContent(tab.id, data);
        } else {
            contentDiv.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> 加载失败: ${data.error}
                </div>
            `;
        }
    } catch (error) {
        contentDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> ${error.message}
            </div>
        `;
    }
}

function displayFileContent(tabId, data) {
    const contentDiv = document.getElementById(`${tabId}-content`);
    const paginationDiv = document.getElementById(`${tabId}-pagination`);

    if (!data.content || data.content.length === 0) {
        contentDiv.innerHTML = `
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> 文件为空
            </div>
        `;
        return;
    }

    // 显示日志内容
    let html = '';
    data.content.forEach((line, index) => {
        const lineNum = data.offset + index + 1;
        let highlighted = escapeHtml(line);

        // 高亮ERROR
        highlighted = highlighted.replace(/(ERROR|Exception|FATAL)/gi, '<span class="error-highlight">$1</span>');

        // 高亮WARN
        highlighted = highlighted.replace(/(WARN|WARNING)/gi, '<span class="warning-highlight">$1</span>');

        html += `<div class="log-line">${lineNum}: ${highlighted}</div>`;
    });

    contentDiv.innerHTML = html;

    // 显示分页
    const currentPage = Math.floor(data.offset / data.limit) + 1;
    const totalPages = Math.ceil(data.total_lines / data.limit);

    let paginationHtml = `
        <div class="d-flex justify-content-between align-items-center">
            <div class="text-muted small">
                第 ${data.offset + 1}-${data.offset + data.content.length} 行 / 共 ${data.total_lines} 行
            </div>
            <div>
    `;

    if (data.offset > 0) {
        paginationHtml += `
            <button class="btn btn-sm btn-outline-secondary" onclick="loadTabPage('${tabId}', ${data.offset - data.limit})">
                <i class="bi bi-chevron-left"></i> 上一页
            </button>
        `;
    }

    paginationHtml += `
        <span class="mx-2">第 ${currentPage} / ${totalPages} 页</span>
    `;

    if (data.has_more) {
        paginationHtml += `
            <button class="btn btn-sm btn-outline-secondary" onclick="loadTabPage('${tabId}', ${data.offset + data.limit})">
                下一页 <i class="bi bi-chevron-right"></i>
            </button>
        `;
    }

    paginationHtml += `
            </div>
        </div>
    `;

    paginationDiv.innerHTML = paginationHtml;
}

function loadTabPage(tabId, offset) {
    const tab = fileBrowserState.openTabs.find(t => t.id === tabId);
    if (tab) {
        loadFileContent(tab, offset);
    }
}

function refreshTabContent(tabId) {
    const tab = fileBrowserState.openTabs.find(t => t.id === tabId);
    if (tab) {
        loadFileContent(tab, 0);
        showToast('success', '已刷新');
    }
}

function downloadTabContent(tabId) {
    const tab = fileBrowserState.openTabs.find(t => t.id === tabId);
    if (!tab) return;

    // 获取当前显示的内容
    const contentDiv = document.getElementById(`${tabId}-content`);
    const lines = Array.from(contentDiv.querySelectorAll('.log-line')).map(el => el.textContent);

    const content = lines.join('\n');
    downloadTextFile(content, tab.fileName);
    showToast('success', '下载成功');
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
