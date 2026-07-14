/* settings.js — 设置面板 / 命令白名单 / 更新检查 / 云同步 / 模型配置管理。
   依赖 core.js 的 $/state，dialogs 无关；openSettings/saveSettings/fillSettingsFields
   /renderModelConfigList 等被本文件内的按钮绑定与同步导入调用（均在本文件内）。
   顶层 $('btn-...').addEventListener 在 load 时执行，故须在 core.js 之后加载。 */
'use strict';

// ── Settings ──────────────────────────────────────────────────────
$('btn-settings').addEventListener('click', openSettings);
$('btn-settings-close').addEventListener('click', () => $('settings-overlay').classList.add('hidden'));
$('btn-settings-cancel').addEventListener('click', () => $('settings-overlay').classList.add('hidden'));
$('btn-settings-save').addEventListener('click', saveSettings);
$('btn-allowlist-save').addEventListener('click', async () => {
  const cmds = $('allowlist-cmds').value.split('\n').map(s => s.trim()).filter(Boolean);
  await window.pywebview.api.save_allowed_commands_api(cmds);
  $('allowlist-cmds').value = cmds.join('\n');
  _updateAllowlistCount(cmds.length);
});
$('btn-allowlist-clear').addEventListener('click', async () => {
  if (!confirm('确定清空所有允许的指令？')) return;
  await window.pywebview.api.save_allowed_commands_api([]);
  $('allowlist-cmds').value = '';
  _updateAllowlistCount(0);
});
function _updateAllowlistCount(n) {
  const el = $('allowlist-count');
  if (el) el.textContent = `${n} 条`;
}
// Update count when allowlist textarea changes
$('allowlist-cmds').addEventListener('input', () => {
  const n = $('allowlist-cmds').value.split('\n').filter(s => s.trim()).length;
  _updateAllowlistCount(n);
});

// ── Update checker ───────────────────────────────────────────────
$('btn-check-update').addEventListener('click', async () => {
  $('update-status').textContent = '正在检查更新...';
  $('update-releases').innerHTML = '';
  const result = await window.pywebview.api.check_for_updates();
  $('update-current-ver').textContent = result.current_version || '-';
  if (result.error) {
    $('update-status').textContent = result.error;
    if (result.rate_limited) {
      const btn = document.createElement('button');
      btn.className = 'update-asset-btn';
      btn.textContent = '直接前往 GitHub Releases 页面';
      btn.style.marginTop = '8px';
      btn.addEventListener('click', () => window.pywebview.api.open_url('https://github.com/SolitudeZY/Deepseek-GUI/releases'));
      $('update-releases').appendChild(btn);
    }
    return;
  }
  const releases = result.releases || [];
  if (releases.length === 0) {
    $('update-status').textContent = '未找到任何发布版本。';
    return;
  }
  // Compare versions
  const current = result.current_version;
  const latest = releases[0].tag.replace(/^v/, '');
  if (latest === current) {
    $('update-status').textContent = `已是最新版本 (${current})`;
  } else {
    $('update-status').textContent = `发现新版本: ${releases[0].tag}`;
  }
  // Render release cards
  const container = $('update-releases');
  releases.forEach(r => {
    const tag = r.tag.replace(/^v/, '');
    const isNew = _compareVersions(tag, current) > 0;
    const card = document.createElement('div');
    card.className = 'update-card' + (isNew ? ' is-new' : '');
    const date = r.published ? new Date(r.published).toLocaleDateString('zh-CN') : '';
    card.innerHTML = `
      <div class="update-card-header">
        <span class="update-card-tag">${escapeHtml(r.tag)}</span>
        ${isNew ? '<span class="update-card-badge">新版本</span>' : ''}
        <span class="update-card-date">${date}</span>
      </div>
      <div class="update-card-body">${escapeHtml(r.body || '无说明')}</div>
      <div class="update-card-assets"></div>
    `;
    const assetsEl = card.querySelector('.update-card-assets');
    if (r.assets && r.assets.length > 0) {
      r.assets.forEach(a => {
        const btn = document.createElement('button');
        btn.className = 'update-asset-btn';
        const sizeMB = (a.size / 1048576).toFixed(1);
        btn.textContent = `${a.name} (${sizeMB}MB)`;
        btn.addEventListener('click', () => _downloadAsset(a.url, a.name));
        assetsEl.appendChild(btn);
      });
    } else {
      const link = document.createElement('button');
      link.className = 'update-asset-btn';
      link.textContent = '前往 GitHub 下载';
      link.addEventListener('click', () => window.pywebview.api.open_url(r.html_url));
      assetsEl.appendChild(link);
    }
    container.appendChild(card);
  });
});

function _compareVersions(a, b) {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = pa[i] || 0, nb = pb[i] || 0;
    if (na > nb) return 1;
    if (na < nb) return -1;
  }
  return 0;
}

// 下载进度回调入口（后端 download_update 通过 evaluate_js 调用）
window.Update = {
  onProgress(pct, downloaded, total) {
    const wrap = $('update-progress');
    if (wrap) wrap.classList.remove('hidden');
    const fill = $('update-progress-fill');
    const text = $('update-progress-text');
    if (pct >= 0) {
      if (fill) fill.style.width = pct + '%';
      if (text) {
        const mb = n => (n / 1048576).toFixed(1);
        text.textContent = total ? `${pct}%（${mb(downloaded)}/${mb(total)} MB）` : `${pct}%`;
      }
    } else {
      // 无 Content-Length，无法算百分比，显示已下载量 + 不确定态
      if (fill) fill.style.width = '100%';
      if (text) text.textContent = downloaded ? `已下载 ${(downloaded/1048576).toFixed(1)} MB` : '下载中...';
    }
  }
};

async function _downloadAsset(url, filename) {
  if (!confirm(`下载 ${filename}？\n\n下载完成后将自动替换当前版本并重启应用。`)) return;
  $('update-status').textContent = `正在下载 ${filename}...`;
  const wrap = $('update-progress');
  if (wrap) wrap.classList.remove('hidden');
  Update.onProgress(0, 0, 0);
  const result = await window.pywebview.api.download_update(url, filename);
  if (result.error) {
    $('update-status').textContent = `下载失败: ${result.error}`;
    if (wrap) wrap.classList.add('hidden');
    return;
  }
  $('update-status').textContent = '下载完成，正在应用更新...';
  if (wrap) wrap.classList.add('hidden');
  const applyResult = await window.pywebview.api.apply_update_and_restart(result.path);
  if (applyResult.error) {
    $('update-status').textContent = `更新失败: ${applyResult.error}`;
  }
}

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'memory') renderMemoryList();
    if (btn.dataset.tab === 'mcp') renderMcpServers();
  });
});

// ── MCP server management ───────────────────────────────────────
let _mcpEditingIndex = -1;
let _mcpDiscoveredTools = [];
let _mcpDraftId = '';
let _mcpServersDraft = [];

function _newMcpId() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
  return `mcp-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function _mcpDefaultServer() {
  return {
    id: _newMcpId(), name: '', enabled: true, transport: 'stdio', trusted: false,
    connect_timeout: 15, call_timeout: 60, tool_policy: 'all', enabled_tools: [],
    stdio: {command: '', args: [], cwd: '', env: {}},
    http: {url: '', headers: {}},
  };
}

function _addMcpKvRow(containerId, key = '', value = '') {
  const row = document.createElement('div');
  row.className = 'mcp-kv-row';
  const keyInput = document.createElement('input');
  keyInput.type = 'text'; keyInput.placeholder = 'KEY'; keyInput.value = key;
  const valueInput = document.createElement('input');
  valueInput.type = 'password'; valueInput.placeholder = '值或 ${ENV_VAR}'; valueInput.value = value;
  const removeBtn = document.createElement('button');
  removeBtn.type = 'button'; removeBtn.className = 'btn-ghost'; removeBtn.textContent = '×'; removeBtn.title = '删除';
  removeBtn.addEventListener('click', () => row.remove());
  row.appendChild(keyInput); row.appendChild(valueInput); row.appendChild(removeBtn);
  $(containerId).appendChild(row);
}

function _fillMcpKvRows(containerId, values) {
  $(containerId).innerHTML = '';
  Object.entries(values || {}).forEach(([key, value]) => _addMcpKvRow(containerId, key, value));
}

function _collectMcpKvRows(containerId) {
  const values = {};
  $(containerId).querySelectorAll('.mcp-kv-row').forEach(row => {
    const inputs = row.querySelectorAll('input');
    const key = inputs[0].value.trim();
    if (key) values[key] = inputs[1].value;
  });
  return values;
}

function _updateMcpTransportFields() {
  const isStdio = $('mcp-transport').value === 'stdio';
  $('mcp-stdio-fields').classList.toggle('hidden', !isStdio);
  $('mcp-http-fields').classList.toggle('hidden', isStdio);
}

function _renderMcpToolList(server) {
  const box = $('mcp-tool-box');
  const list = $('mcp-tool-list');
  if (!_mcpDiscoveredTools.length) {
    box.classList.add('hidden');
    list.innerHTML = '';
    return;
  }
  box.classList.remove('hidden');
  list.innerHTML = '';
  const allow = new Set(server.enabled_tools || []);
  const allMode = server.tool_policy !== 'allowlist';
  _mcpDiscoveredTools.forEach(tool => {
    const row = document.createElement('label');
    row.className = 'mcp-tool-item';
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.dataset.toolName = tool.name; cb.checked = allMode || allow.has(tool.name);
    const info = document.createElement('div');
    info.className = 'mcp-tool-info';
    info.innerHTML = `<div class="mcp-tool-name">${escapeHtml(tool.name)}</div>`
      + `<div class="mcp-tool-desc">${escapeHtml(tool.description || '')}</div>`;
    row.appendChild(cb); row.appendChild(info); list.appendChild(row);
  });
  $('mcp-tool-count').textContent = `${_mcpDiscoveredTools.length} 个`;
}

function _collectMcpEditor() {
  const existing = _mcpEditingIndex >= 0 ? _mcpServersDraft[_mcpEditingIndex] : {id: _mcpDraftId};
  const checkedTools = [...$('mcp-tool-list').querySelectorAll('input[type="checkbox"]:checked')].map(cb => cb.dataset.toolName);
  const hasToolSnapshot = _mcpDiscoveredTools.length > 0;
  const allToolsSelected = hasToolSnapshot && checkedTools.length === _mcpDiscoveredTools.length;
  return {
    id: existing.id || _newMcpId(),
    name: $('mcp-name').value.trim(),
    enabled: $('mcp-enabled').checked,
    transport: $('mcp-transport').value,
    trusted: $('mcp-trusted').checked,
    connect_timeout: parseInt($('mcp-connect-timeout').value) || 15,
    call_timeout: parseInt($('mcp-call-timeout').value) || 60,
    tool_policy: hasToolSnapshot ? (allToolsSelected ? 'all' : 'allowlist') : (existing.tool_policy || 'all'),
    enabled_tools: hasToolSnapshot ? (allToolsSelected ? [] : checkedTools) : (existing.enabled_tools || []),
    stdio: {
      command: $('mcp-command').value.trim(),
      args: $('mcp-args').value.split('\n').map(v => v.trim()).filter(Boolean),
      cwd: $('mcp-cwd').value.trim(),
      env: _collectMcpKvRows('mcp-env-rows'),
    },
    http: {
      url: $('mcp-url').value.trim(),
      headers: _collectMcpKvRows('mcp-header-rows'),
    },
  };
}

function _validateMcpDraft(server) {
  if (!server.name) return '请填写服务器名称';
  const duplicate = _mcpServersDraft.some((item, index) =>
    index !== _mcpEditingIndex && (item.name || '').toLowerCase() === server.name.toLowerCase());
  if (duplicate) return '服务器名称不能重复';
  if (server.enabled && server.transport === 'stdio' && !server.stdio.command) return '请填写 stdio Command';
  if (server.enabled && server.transport === 'http' && !/^https?:\/\//i.test(server.http.url)) return '请填写有效的 HTTP Endpoint URL';
  return '';
}

async function renderMcpServers() {
  const container = $('mcp-server-list');
  const servers = _mcpServersDraft;
  const statuses = await window.pywebview.api.get_mcp_statuses();
  const statusMap = new Map((statuses || []).map(item => [item.id, item]));
  container.innerHTML = '';
  if (!servers.length) {
    container.innerHTML = '<div class="mcp-server-empty">尚未配置 MCP 服务器</div>';
    return;
  }
  servers.forEach((server, index) => {
    const persisted = (state.config.mcp_servers || []).find(item => item.id === server.id);
    const isDraft = !persisted || JSON.stringify(persisted) !== JSON.stringify(server);
    const runtimeStatus = statusMap.get(server.id) || {state: 'disconnected', tool_count: 0};
    const status = isDraft
      ? {...runtimeStatus, state: 'draft', tool_count: 0}
      : (server.enabled ? runtimeStatus : {...runtimeStatus, state: 'disabled'});
    const item = document.createElement('div');
    item.className = 'mcp-server-item';
    const main = document.createElement('div');
    main.className = 'mcp-server-main';
    const endpoint = server.transport === 'stdio' ? (server.stdio?.command || '') : (server.http?.url || '');
    main.innerHTML = `<div class="mcp-server-name">${escapeHtml(server.name)}</div>`
      + `<div class="mcp-server-meta">${escapeHtml(server.transport)} · ${escapeHtml(endpoint)}</div>`;
    const stateEl = document.createElement('div');
    stateEl.className = `mcp-state ${status.state || ''}`;
    const stateLabels = {connected: '已连接', connecting: '连接中', error: '错误', disconnected: '未连接', disabled: '已禁用', draft: '待保存'};
    stateEl.textContent = `${stateLabels[status.state] || status.state}${status.tool_count ? ` · ${status.tool_count}` : ''}`;
    stateEl.title = status.last_error || status.server_info || '';
    const actions = document.createElement('div');
    actions.className = 'mcp-server-actions';
    const editBtn = document.createElement('button');
    editBtn.className = 'btn-secondary'; editBtn.textContent = '编辑';
    editBtn.addEventListener('click', () => openMcpEditor(index));
    const reconnectBtn = document.createElement('button');
    reconnectBtn.className = 'btn-ghost'; reconnectBtn.textContent = '重连'; reconnectBtn.disabled = !server.enabled || isDraft;
    reconnectBtn.addEventListener('click', async () => {
      reconnectBtn.disabled = true; reconnectBtn.textContent = '连接中';
      await window.pywebview.api.reconnect_mcp_server(server.id);
      await renderMcpServers();
    });
    actions.appendChild(editBtn); actions.appendChild(reconnectBtn);
    item.appendChild(main); item.appendChild(stateEl); item.appendChild(actions); container.appendChild(item);
  });
}

function openMcpEditor(index) {
  _mcpEditingIndex = Number.isInteger(index) ? index : -1;
  const server = _mcpEditingIndex >= 0 ? _mcpServersDraft[_mcpEditingIndex] : _mcpDefaultServer();
  _mcpDraftId = server.id || _newMcpId();
  _mcpDiscoveredTools = [];
  $('mcp-name').value = server.name || '';
  $('mcp-enabled').checked = server.enabled !== false;
  $('mcp-transport').value = server.transport || 'stdio';
  $('mcp-trusted').checked = server.trusted === true;
  $('mcp-connect-timeout').value = server.connect_timeout || 15;
  $('mcp-call-timeout').value = server.call_timeout || 60;
  $('mcp-command').value = server.stdio?.command || '';
  $('mcp-args').value = (server.stdio?.args || []).join('\n');
  $('mcp-cwd').value = server.stdio?.cwd || '';
  $('mcp-url').value = server.http?.url || '';
  _fillMcpKvRows('mcp-env-rows', server.stdio?.env || {});
  _fillMcpKvRows('mcp-header-rows', server.http?.headers || {});
  $('mcp-test-status').textContent = '';
  $('mcp-test-status').className = 'mcp-status-text';
  $('mcp-tool-box').classList.add('hidden');
  $('btn-mcp-editor-delete').classList.toggle('hidden', _mcpEditingIndex < 0);
  _updateMcpTransportFields();
  $('mcp-editor').classList.remove('hidden');
  $('mcp-name').focus();
}

async function _testMcpDraft() {
  const draft = _collectMcpEditor();
  const error = _validateMcpDraft({...draft, enabled: true});
  if (error) { $('mcp-test-status').textContent = error; $('mcp-test-status').className = 'mcp-status-text error'; return; }
  const btn = $('btn-mcp-test');
  btn.disabled = true; btn.textContent = '测试中';
  $('mcp-test-status').textContent = '正在初始化并读取工具列表...';
  $('mcp-test-status').className = 'mcp-status-text';
  try {
    const result = await window.pywebview.api.test_mcp_server(draft);
    if (!result.ok) {
      $('mcp-test-status').textContent = result.error || '连接失败';
      $('mcp-test-status').className = 'mcp-status-text error';
      return;
    }
    _mcpDiscoveredTools = result.tools || [];
    $('mcp-test-status').textContent = `连接成功 · ${result.server_info || 'MCP Server'} · ${result.protocol_version || ''}`;
    $('mcp-test-status').className = 'mcp-status-text ok';
    _renderMcpToolList(draft);
  } catch (err) {
    $('mcp-test-status').textContent = String(err);
    $('mcp-test-status').className = 'mcp-status-text error';
  } finally {
    btn.disabled = false; btn.textContent = '测试连接';
  }
}

$('btn-mcp-add').addEventListener('click', () => openMcpEditor(-1));
$('btn-mcp-refresh').addEventListener('click', renderMcpServers);
$('mcp-transport').addEventListener('change', _updateMcpTransportFields);
$('btn-mcp-env-add').addEventListener('click', () => _addMcpKvRow('mcp-env-rows'));
$('btn-mcp-header-add').addEventListener('click', () => _addMcpKvRow('mcp-header-rows'));
$('btn-mcp-test').addEventListener('click', _testMcpDraft);
$('btn-mcp-editor-cancel').addEventListener('click', () => $('mcp-editor').classList.add('hidden'));
$('btn-mcp-editor-save').addEventListener('click', async () => {
  const draft = _collectMcpEditor();
  const error = _validateMcpDraft(draft);
  if (error) { alert(error); return; }
  if (_mcpEditingIndex >= 0) _mcpServersDraft[_mcpEditingIndex] = draft;
  else _mcpServersDraft.push(draft);
  $('mcp-editor').classList.add('hidden');
  await renderMcpServers();
});
$('btn-mcp-editor-delete').addEventListener('click', async () => {
  if (_mcpEditingIndex < 0) return;
  const server = _mcpServersDraft[_mcpEditingIndex];
  if (!confirm(`确定删除 MCP 服务器「${server.name}」？`)) return;
  _mcpServersDraft.splice(_mcpEditingIndex, 1);
  $('mcp-editor').classList.add('hidden');
  await renderMcpServers();
});

// ── 跨会话记忆管理 ────────────────────────────────────────────────
async function renderMemoryList() {
  const ul = $('memory-list');
  ul.innerHTML = '<li class="memory-empty">加载中…</li>';
  const items = await window.pywebview.api.list_memory();
  if (!items || items.length === 0) {
    ul.innerHTML = '<li class="memory-empty">暂无记忆。模型在完成任务后会询问是否记入，或点「+ 新增记忆」手动添加。</li>';
    return;
  }
  ul.innerHTML = '';
  items.forEach(it => {
    const li = document.createElement('li');
    li.className = 'memory-item';
    const info = document.createElement('div');
    info.className = 'memory-info';
    info.innerHTML = `<div class="memory-key">${escapeHtml(it.key)}</div>`
                   + `<div class="memory-preview">${escapeHtml(it.preview || '')}</div>`;
    const actions = document.createElement('div');
    actions.className = 'memory-actions';
    const editBtn = document.createElement('button');
    editBtn.className = 'btn-secondary'; editBtn.textContent = '编辑';
    editBtn.addEventListener('click', () => openMemoryEditor(it.key));
    const delBtn = document.createElement('button');
    delBtn.className = 'btn-danger'; delBtn.textContent = '删除';
    delBtn.addEventListener('click', async () => {
      if (!confirm(`确定删除记忆「${it.key}」？新会话将不再带上它。`)) return;
      await window.pywebview.api.delete_memory(it.key);
      renderMemoryList();
    });
    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    li.appendChild(info);
    li.appendChild(actions);
    ul.appendChild(li);
  });
}

async function openMemoryEditor(key) {
  const editor = $('memory-editor');
  editor.classList.remove('hidden');
  $('memory-key').value = key || '';
  $('memory-key').readOnly = !!key;  // 编辑已有条目时 key 不可改（改名等于新建）
  $('memory-content').value = key ? await window.pywebview.api.read_memory(key) : '';
  $('memory-content').focus();
}

$('btn-memory-new').addEventListener('click', () => openMemoryEditor(''));
$('btn-memory-cancel').addEventListener('click', () => $('memory-editor').classList.add('hidden'));
$('btn-memory-save').addEventListener('click', async () => {
  const key = $('memory-key').value.trim();
  const content = $('memory-content').value;
  if (!key) { alert('请填写记忆名称'); return; }
  await window.pywebview.api.write_memory(key, content);
  $('memory-editor').classList.add('hidden');
  renderMemoryList();
});

// Sub-tab switching (图片工具内：图片理解 / 图片生成)
document.querySelectorAll('.subtab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const bar = btn.closest('.tab-panel');
    bar.querySelectorAll('.subtab-btn').forEach(b => b.classList.remove('active'));
    bar.querySelectorAll('.subtab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    bar.querySelector('#subtab-' + btn.dataset.subtab).classList.add('active');
  });
});

// 读取模型列表（图片理解 / 图片生成共用）
async function fetchModelList(keyId, urlId, modelId, boxId, btn) {
  const box = $(boxId);
  const key = $(keyId).value.trim();
  const url = $(urlId).value.trim();
  if (!key || !url) { box.innerHTML = '<span class="model-list-err">请先填写 API Key 和 Base URL</span>'; return; }
  const oldLabel = btn.textContent;
  btn.disabled = true; btn.textContent = '读取中...';
  box.innerHTML = '<span class="model-list-loading">正在拉取模型列表...</span>';
  try {
    const r = await window.pywebview.api.list_models(key, url);
    if (!r.ok) { box.innerHTML = `<span class="model-list-err">${escapeHtml(r.error || '读取失败')}</span>`; return; }
    box.innerHTML = `<div class="model-list-head">共 ${r.models.length} 个模型（点击填入模型名）</div>`;
    const wrap = document.createElement('div');
    wrap.className = 'model-list-items';
    r.models.forEach(id => {
      const chip = document.createElement('span');
      chip.className = 'model-chip';
      chip.textContent = id;
      chip.title = '点击填入模型名';
      chip.addEventListener('click', () => { $(modelId).value = id; });
      wrap.appendChild(chip);
    });
    box.appendChild(wrap);
  } catch (e) {
    box.innerHTML = `<span class="model-list-err">${escapeHtml(String(e))}</span>`;
  } finally {
    btn.disabled = false; btn.textContent = oldLabel;
  }
}
$('btn-vision-models').addEventListener('click', e =>
  fetchModelList('vision-key', 'vision-url', 'vision-model', 'vision-models-box', e.currentTarget));
$('btn-imagegen-models').addEventListener('click', e =>
  fetchModelList('imagegen-key', 'imagegen-url', 'imagegen-model', 'imagegen-models-box', e.currentTarget));
$('btn-mc-models').addEventListener('click', e =>
  fetchModelList('mc-key', 'mc-url', 'mc-model', 'mc-models-box', e.currentTarget));

async function openSettings() {
  _mcpServersDraft = JSON.parse(JSON.stringify(state.config.mcp_servers || []));
  _mcpEditingIndex = -1;
  $('mcp-editor').classList.add('hidden');
  fillSettingsFields(state.config);
  $('sync-list').innerHTML = '';
  $('sync-import-actions').style.display = 'none';
  $('sync-status').textContent = state.config.sync_folder ? '' : '未配置同步文件夹';
  renderModelConfigList();
  // load allowlist
  const cmds = await window.pywebview.api.get_allowed_commands();
  $('allowlist-cmds').value = cmds.join('\n');
  _updateAllowlistCount(cmds.length);
  // load current version
  const ver = await window.pywebview.api.get_app_version();
  $('update-current-ver').textContent = ver || '-';
  $('settings-overlay').classList.remove('hidden');
}

// 用 cfg 填充设置面板各输入框（openSettings 与导入配置后共用）
function fillSettingsFields(cfg) {
  $('search-engine').value = cfg.search_engine || 'tavily';
  $('search-fallback').checked = cfg.search_fallback !== false;
  $('tavily-key').value = cfg.tavily_api_key || '';
  $('brave-key').value = cfg.brave_api_key || '';
  $('firecrawl-key').value = cfg.firecrawl_api_key || '';
  $('google-key').value = cfg.google_api_key || '';
  $('google-cx').value = cfg.google_cx || '';
  $('searxng-url').value = cfg.searxng_url || '';
  $('cmd-safety').value = cfg.command_safety || 'confirm';
  $('cmd-timeout').value = cfg.command_timeout || 30;
  $('max-rounds').value = cfg.max_rounds || 50;
  $('vision-key').value = cfg.vision_api_key || '';
  $('vision-url').value = cfg.vision_base_url || '';
  $('vision-model').value = cfg.vision_model || '';
  $('imagegen-key').value = cfg.imagegen_api_key || '';
  $('imagegen-url').value = cfg.imagegen_base_url || '';
  $('imagegen-model').value = cfg.imagegen_model || '';
  $('imagegen-format').value = cfg.imagegen_format || 'openai';
  $('imagegen-use-full-url').checked = cfg.imagegen_use_full_url || false;
  $('ui-theme').value = cfg.theme || 'dark';
  $('ui-fontsize').value = String(cfg.font_size || 14);
  $('starfield-enabled').checked = cfg.starfield_enabled === true;
  $('starfield-mode').value = cfg.starfield_mode || 'twinkle';
  $('sync-folder').value = cfg.sync_folder || '';
  $('sync-auto-upload').checked = cfg.sync_auto_upload !== false;
  $('github-token').value = cfg.github_token || '';
}

async function saveSettings() {
  saveCurrentMc();
  state.config.search_engine = $('search-engine').value;
  state.config.search_fallback = $('search-fallback').checked;
  state.config.tavily_api_key = $('tavily-key').value.trim();
  state.config.brave_api_key = $('brave-key').value.trim();
  state.config.firecrawl_api_key = $('firecrawl-key').value.trim();
  state.config.google_api_key = $('google-key').value.trim();
  state.config.google_cx = $('google-cx').value.trim();
  state.config.searxng_url = $('searxng-url').value.trim();
  state.config.command_safety = $('cmd-safety').value;
  state.config.command_timeout = parseInt($('cmd-timeout').value) || 30;
  state.config.max_rounds = parseInt($('max-rounds').value) || 50;
  state.config.vision_api_key = $('vision-key').value.trim();
  state.config.vision_base_url = $('vision-url').value.trim();
  state.config.vision_model = $('vision-model').value.trim();
  state.config.imagegen_api_key = $('imagegen-key').value.trim();
  state.config.imagegen_base_url = $('imagegen-url').value.trim();
  state.config.imagegen_model = $('imagegen-model').value.trim();
  state.config.imagegen_format = $('imagegen-format').value;
  state.config.imagegen_use_full_url = $('imagegen-use-full-url').checked;
  state.config.theme = $('ui-theme').value;
  state.config.font_size = parseInt($('ui-fontsize').value) || 14;
  state.config.starfield_enabled = $('starfield-enabled').checked;
  state.config.starfield_mode = $('starfield-mode').value;
  state.config.sync_auto_upload = $('sync-auto-upload').checked;
  state.config.github_token = $('github-token').value.trim();
  applyTheme(state.config.theme);
  applyFontSize(state.config.font_size);
  if (typeof applyStarfieldSettings === 'function') applyStarfieldSettings(state.config);
  const previousMcpServers = state.config.mcp_servers || [];
  state.config.mcp_servers = JSON.parse(JSON.stringify(_mcpServersDraft));
  const saved = await window.pywebview.api.save_config(state.config);
  if (saved && saved.ok === false) {
    state.config.mcp_servers = previousMcpServers;
    alert(`保存设置失败：${saved.error || 'MCP 配置无效'}`);
    return;
  }
  populateModelSelect();
  $('settings-overlay').classList.add('hidden');
}

// ── Sync handlers ────────────────────────────────────────────────
$('btn-sync-choose').addEventListener('click', async () => {
  const folder = await window.pywebview.api.sync_choose_folder();
  if (folder) {
    $('sync-folder').value = folder;
    state.config.sync_folder = folder;
    $('sync-status').textContent = '已配置';
  }
});

$('btn-sync-upload-all').addEventListener('click', async () => {
  $('sync-status').textContent = '正在上传...';
  const result = await window.pywebview.api.sync_upload_all();
  $('sync-status').textContent = `已上传 ${result.uploaded} 个对话`;
});

$('btn-sync-detect').addEventListener('click', async () => {
  $('sync-status').textContent = '正在检测...';
  const items = await window.pywebview.api.sync_detect_new();
  if (!items || items.length === 0) {
    $('sync-status').textContent = '没有发现新对话';
    $('sync-list').innerHTML = '';
    $('sync-import-actions').style.display = 'none';
    return;
  }
  $('sync-status').textContent = `发现 ${items.length} 个可导入的对话：`;
  const list = $('sync-list');
  list.innerHTML = '';
  items.forEach(item => {
    const div = document.createElement('div');
    div.style.cssText = 'display:flex; align-items:center; gap:8px; padding:4px 0; font-size:13px;';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.dataset.filename = item.filename;
    const label = document.createElement('span');
    const badge = item.is_new ? '<span style="color:var(--accent);font-size:11px;">[新]</span> ' : '<span style="color:#e0af68;font-size:11px;">[更新]</span> ';
    label.innerHTML = `${badge}${item.title} <span style="color:var(--text-muted);font-size:11px;">${item.updated_at ? item.updated_at.slice(0,16).replace('T',' ') : ''}</span>`;
    div.appendChild(cb);
    div.appendChild(label);
    list.appendChild(div);
  });
  $('sync-import-actions').style.display = '';
});

$('btn-sync-select-all').addEventListener('click', () => {
  const cbs = $('sync-list').querySelectorAll('input[type="checkbox"]');
  const allChecked = [...cbs].every(cb => cb.checked);
  cbs.forEach(cb => cb.checked = !allChecked);
});

$('btn-sync-import').addEventListener('click', async () => {
  const cbs = $('sync-list').querySelectorAll('input[type="checkbox"]:checked');
  const filenames = [...cbs].map(cb => cb.dataset.filename);
  if (!filenames.length) return;
  $('sync-status').textContent = '正在导入...';
  const result = await window.pywebview.api.sync_import_selected(filenames);
  $('sync-status').textContent = `成功导入 ${result.imported} 个对话`;
  $('sync-list').innerHTML = '';
  $('sync-import-actions').style.display = 'none';
  // 刷新对话列表
  state.conversations = await window.pywebview.api.list_conversations();
  renderConvList('');
});

// 一键上传全部（对话+配置）
$('btn-sync-all').addEventListener('click', async () => {
  $('sync-status').textContent = '正在同步上传...';
  const result = await window.pywebview.api.sync_all();
  const cfgList = result.config_uploaded.length ? `，配置: ${result.config_uploaded.join(', ')}` : '';
  const memUp = result.memory_uploaded ? `，记忆: ${result.memory_uploaded} 条` : '';
  const skillUp = result.skills_uploaded ? `，技能: ${result.skills_uploaded} 条` : '';
  $('sync-status').textContent = `已上传 ${result.conversations_uploaded} 个对话${cfgList}${memUp}${skillUp}`;
});

// 一键导入全部（对话+配置）
$('btn-sync-import-all').addEventListener('click', async () => {
  $('sync-status').textContent = '正在一键导入...';
  const result = await window.pywebview.api.sync_import_all();
  const cfgList = result.config_imported.length ? `，配置: ${result.config_imported.join(', ')}` : '';
  const memIn = result.memory_imported ? `，记忆: ${result.memory_imported} 条` : '';
  const skillIn = result.skills_imported ? `，技能: ${result.skills_imported} 条` : '';
  $('sync-status').textContent = `导入 ${result.conversations_imported} 个对话${cfgList}${memIn}${skillIn}`;
  // 刷新对话列表和配置
  state.conversations = await window.pywebview.api.list_conversations();
  renderConvList('');
  if (result.config_imported.length) {
    state.config = await window.pywebview.api.get_config();
    populateModelSelect();
    fillSettingsFields(state.config);  // 即时刷新设置面板输入框（vision/imagegen/github 等）
    applyTheme(state.config.theme);
    applyFontSize(state.config.font_size);
  }
});

// Model config list
function renderModelConfigList() {
  const ul = $('model-config-list');
  ul.innerHTML = '';
  (state.config.model_configs || []).forEach((mc, i) => {
    const li = document.createElement('li');
    if (i === state.selectedMcIdx) li.classList.add('active');

    const nameSpan = document.createElement('span');
    nameSpan.className = 'mc-item-name';
    nameSpan.textContent = mc.name;
    li.appendChild(nameSpan);

    const delBtn = document.createElement('button');
    delBtn.className = 'mc-item-del';
    delBtn.textContent = '×';
    delBtn.title = '删除此配置';
    delBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const configs = state.config.model_configs || [];
      if (configs.length <= 1) { alert('至少保留一个模型配置'); return; }
      if (!confirm(`确定删除配置「${mc.name}」？`)) return;
      configs.splice(i, 1);
      if (state.selectedMcIdx === i) {
        state.selectedMcIdx = null;
        ['mc-name','mc-key','mc-url','mc-model'].forEach(id => $(id).value = '');
        $('mc-system').value = '';
      } else if (state.selectedMcIdx > i) {
        state.selectedMcIdx--;
      }
      renderModelConfigList();
    });
    li.appendChild(delBtn);

    li.addEventListener('click', () => selectMc(i));
    ul.appendChild(li);
  });
}

function selectMc(idx) {
  state.selectedMcIdx = idx;
  const mc = state.config.model_configs[idx];
  $('mc-name').value = mc.name || '';
  $('mc-key').value = mc.api_key || '';
  $('mc-url').value = mc.base_url || '';
  $('mc-model').value = mc.model || '';
  $('mc-system').value = mc.system_prompt || '';
  $('mc-use-full-url').checked = mc.use_full_url || false;
  // 上下文长度和压缩阈值（自动选择 K/M 单位）
  const ctxLen = mc.context_length || 600000;
  if (ctxLen >= 1000000 && ctxLen % 1000000 === 0) {
    $('mc-context-length').value = ctxLen / 1000000;
    $('mc-context-unit').value = 'M';
  } else {
    $('mc-context-length').value = Math.round(ctxLen / 1000);
    $('mc-context-unit').value = 'K';
  }
  const threshold = mc.compact_threshold || 600000;
  if (threshold >= 1000000 && threshold % 1000000 === 0) {
    $('mc-compact-threshold').value = threshold / 1000000;
    $('mc-compact-unit').value = 'M';
  } else {
    $('mc-compact-threshold').value = Math.round(threshold / 1000);
    $('mc-compact-unit').value = 'K';
  }
  renderModelConfigList();
}

function saveCurrentMc() {
  if (state.selectedMcIdx === null) return;
  const mc = state.config.model_configs[state.selectedMcIdx];
  mc.name = $('mc-name').value.trim() || mc.name;
  mc.api_key = $('mc-key').value.trim();
  mc.base_url = $('mc-url').value.trim();
  mc.model = $('mc-model').value.trim();
  mc.system_prompt = $('mc-system').value.trim();
  mc.use_full_url = $('mc-use-full-url').checked;
  // 上下文长度和压缩阈值
  const ctxVal = parseFloat($('mc-context-length').value) || 600;
  const ctxUnit = $('mc-context-unit').value;
  mc.context_length = Math.round(ctxVal * (ctxUnit === 'M' ? 1000000 : 1000));
  const compVal = parseFloat($('mc-compact-threshold').value) || 600;
  const compUnit = $('mc-compact-unit').value;
  mc.compact_threshold = Math.round(compVal * (compUnit === 'M' ? 1000000 : 1000));
  renderModelConfigList();
}

$('btn-save-mc').addEventListener('click', saveCurrentMc);
$('btn-add-model').addEventListener('click', () => {
  const configs = state.config.model_configs || [];
  configs.push({ name: `新配置 ${configs.length + 1}`, api_key: '', base_url: '', model: '', system_prompt: 'You are a helpful assistant.', context_length: 1000000, compact_threshold: 600000, use_full_url: false });
  state.config.model_configs = configs;
  selectMc(configs.length - 1);
});
$('btn-del-mc').addEventListener('click', () => {
  const configs = state.config.model_configs || [];
  if (configs.length <= 1) { alert('至少保留一个模型配置'); return; }
  if (state.selectedMcIdx === null) return;
  configs.splice(state.selectedMcIdx, 1);
  state.selectedMcIdx = null;
  ['mc-name','mc-key','mc-url','mc-model'].forEach(id => $(id).value = '');
  $('mc-system').value = '';
  renderModelConfigList();
});

