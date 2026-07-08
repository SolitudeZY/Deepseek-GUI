/* app.js — AI Desktop Assistant 主逻辑（会话/气泡/流式/输入/Chat 回调/init）。
   加载顺序见 index.html：vendor → core.js → render.js → drag.js → dialogs.js
   → settings.js → app.js。core.js 提供 state/$/DOM 引用，render.js 提供
   renderMarkdown/escapeHtml/scrollToBottom，本文件依赖它们（运行时解析，安全）。 */
'use strict';

// ── Init ──────────────────────────────────────────────────────────
// ── Scroll speed boost (removed: was blocking native scroll) ─────

window.addEventListener('pywebviewready', async () => {
  state.config = await window.pywebview.api.get_config();
  applyTheme(state.config.theme || 'dark');
  applyFontSize(state.config.font_size || 14);
  populateModelSelect();
  // Restore persistent toggle states
  const uiState = await window.pywebview.api.get_ui_state();
  initThinkingBtn(uiState.thinking);
  initSearchBtn(uiState.search_mode, uiState.search_enabled);
  state.conversations = await window.pywebview.api.list_conversations();
  renderConvList();
  if (state.conversations.length > 0) {
    await openConversation(state.conversations[0].id);
  } else {
    await newConversation();
  }
  // 启动时自动检测云同步新对话
  if (state.config.sync_folder) {
    const newItems = await window.pywebview.api.sync_detect_new();
    if (newItems && newItems.length > 0) {
      document.title = `QuickModel — ${newItems.length} 个云端新对话可导入`;
    }
  }
  // Track page visibility for system notifications
  document.addEventListener('visibilitychange', () => {
    window.pywebview.api.set_window_visible(!document.hidden);
  });
  window.addEventListener('focus', () => window.pywebview.api.set_window_visible(true));
  window.addEventListener('blur', () => window.pywebview.api.set_window_visible(false));
});

// ── Theme / font ──────────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}
function applyFontSize(size) {
  document.documentElement.style.setProperty('--font-size', size + 'px');
}

// ── Model select ──────────────────────────────────────────────────
function populateModelSelect() {
  modelSelect.innerHTML = '';
  const configs = state.config.model_configs || [];
  configs.forEach(mc => {
    const opt = document.createElement('option');
    opt.value = mc.name;
    opt.textContent = mc.name;
    if (mc.name === state.config.active_model_config) opt.selected = true;
    modelSelect.appendChild(opt);
  });
}
modelSelect.addEventListener('change', async () => {
  state.config.active_model_config = modelSelect.value;
  await window.pywebview.api.save_config(state.config);
});

// ── Conversation list ─────────────────────────────────────────────
function _fmtConvTime(iso, full = false) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const pad = n => String(n).padStart(2, '0');
  if (full) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const sameYear = d.getFullYear() === now.getFullYear();
  return sameYear ? `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
                  : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function _makeConvLi(conv, idx) {
  const li = document.createElement('li');
  li.dataset.id = conv.id;
  li.dataset.idx = idx;
  if (conv.id === state.currentConvId) {
    li.classList.add('active');
    li.style.borderLeftColor = _randomConvColor();
    li.style.boxShadow = `inset 4px 0 0 ${li.style.borderLeftColor}, 0 0 12px ${li.style.borderLeftColor}33`;
  }

  const titleWrap = document.createElement('div');
  titleWrap.className = 'conv-title-wrap';
  titleWrap.style.flex = '1';
  const titleSpan = document.createElement('span');
  titleSpan.className = 'conv-title';
  titleSpan.textContent = conv.title;
  titleWrap.appendChild(titleSpan);
  const timeSpan = document.createElement('span');
  timeSpan.className = 'conv-time';
  timeSpan.textContent = _fmtConvTime(conv.updated_at);
  titleWrap.appendChild(timeSpan);
  li.appendChild(titleWrap);
  // hover 显示完整创建/更新时间
  const _c = _fmtConvTime(conv.created_at, true);
  const _u = _fmtConvTime(conv.updated_at, true);
  li.title = `创建：${_c || '未知'}\n更新：${_u || '未知'}`;

  const actions = document.createElement('div');
  actions.className = 'conv-actions';
  const btnRename = document.createElement('button');
  btnRename.textContent = '✏';
  btnRename.title = '重命名';
  btnRename.addEventListener('click', e => { e.stopPropagation(); showRenameDialog(conv.id, conv.title); });
  const btnDel = document.createElement('button');
  btnDel.textContent = '🗑';
  btnDel.title = '删除';
  btnDel.addEventListener('click', e => { e.stopPropagation(); deleteConversation(conv.id); });
  actions.appendChild(btnRename);
  actions.appendChild(btnDel);
  li.appendChild(actions);

  li.addEventListener('click', () => {
    // 刚结束一次拖拽时抑制点击（mouseup 与 click 会连续触发）
    if (_drag.justDragged) { _drag.justDragged = false; return; }
    openConversation(conv.id);
  });

  // 手动拖拽排序：WebView2 对 HTML5 原生拖放（draggable/dragstart/drop）支持不可靠
  // （与 CSS transition 失效同源，见 memory css-transition-bug），改用 mouse 事件实现。
  li.draggable = false;
  // ⚠ 关键：阻止 WebView2 启动原生拖放。否则 mousedown 后浏览器接管为原生 drag，
  // mousemove 停止触发（变成 dragover），手动引擎收不到移动 → 只剩「禁止」光标+拖影。
  // 注意不能在 mousedown 上 preventDefault（会连带阻止 click，单击就打不开会话了），
  // 只在 dragstart 上挡；文本选中触发的拖放由 CSS user-select/-webkit-user-drag 兜底。
  li.addEventListener('dragstart', e => e.preventDefault());
  li.addEventListener('mousedown', e => {
    if (e.button !== 0) return;            // 仅左键
    if (e.target.closest('.conv-actions')) return;  // 点重命名/删除按钮不触发拖拽
    _beginDragCandidate(conv.id, li, e);
  });
  return li;
}

function renderConvList(filter = '') {
  convList.innerHTML = '';
  const kw = filter.toLowerCase();

  // 按 project_path 分组（保持 state.conversations 的全局顺序）
  const groups = new Map();  // path -> [{conv, idx}]
  state.conversations.forEach((conv, idx) => {
    if (kw && !(conv.title || '').toLowerCase().includes(kw)) return;
    const key = conv.project_path || '';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ conv, idx });
  });

  if (groups.size === 0) return;

  const projName = path => {
    if (!path) return '未分类';
    return path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || path;
  };

  for (const [path, items] of groups) {
    const group = document.createElement('div');
    group.className = 'conv-group';
    // 搜索时强制展开命中组
    const collapsed = !kw && state.collapsedGroups[path];

    const header = document.createElement('div');
    header.className = 'conv-group-header';
    header.title = path || '未绑定项目的会话';
    header.innerHTML = `<span class="cg-arrow">${collapsed ? '▶' : '▼'}</span>`
                     + `<span class="cg-name">${escapeHtml(projName(path))}</span>`
                     + `<span class="cg-count">${items.length}</span>`;
    header.addEventListener('click', () => {
      state.collapsedGroups[path] = !state.collapsedGroups[path];
      renderConvList(searchInput.value);
    });
    // 真实项目组（path 非空）加「+新对话」按钮：直接在该项目下开新会话。
    // 用 addEventListener + stopPropagation，避免触发折叠；不用内联 onclick（Windows 路径转义坑）。
    if (path) {
      const addBtn = document.createElement('button');
      addBtn.className = 'cg-add';
      addBtn.textContent = '+';
      addBtn.title = '在该项目中新建对话';
      addBtn.addEventListener('click', e => {
        e.stopPropagation();
        startConvWithProject(path);
      });
      header.appendChild(addBtn);
    }
    // 供手动拖拽 _updateDropTarget 命中组标题时读取目标组（拖到组头=归入该组）
    header._groupKey = path;
    group.appendChild(header);

    if (!collapsed) {
      const ul = document.createElement('ul');
      ul.className = 'conv-group-items';
      items.forEach(({ conv, idx }) => ul.appendChild(_makeConvLi(conv, idx)));
      group.appendChild(ul);
    }
    convList.appendChild(group);
  }
}

searchInput.addEventListener('input', () => {
  const kw = searchInput.value.trim();
  // Instant title filter for responsiveness
  renderConvList(kw);
  // Debounced content search for deeper matches
  clearTimeout(searchInput._debounce);
  if (!kw) { _clearSearchHighlights(); return; }
  searchInput._debounce = setTimeout(() => _runContentSearch(kw), 300);
});

async function _runContentSearch(kw) {
  if (!kw) return;
  const results = await window.pywebview.api.search_conversations(kw);
  _applyContentSearchResults(results, kw);
}

function _clearSearchHighlights() {
  convList.querySelectorAll('.conv-snippet').forEach(el => el.remove());
  convList.querySelectorAll('li.search-content-match').forEach(li => li.classList.remove('search-content-match'));
}

function _applyContentSearchResults(results, kw) {
  _clearSearchHighlights();
  if (!results || results.length === 0) return;
  const visibleIds = new Set([...convList.querySelectorAll('li[data-id]')].map(li => li.dataset.id));
  const contentMatches = results.filter(r => r.match === 'content');

  // For already-visible items, add snippet
  for (const r of contentMatches) {
    const li = convList.querySelector(`li[data-id="${r.id}"]`);
    if (li) {
      li.classList.add('search-content-match');
      const snippet = document.createElement('div');
      snippet.className = 'conv-snippet';
      snippet.textContent = r.snippet || '';
      li.appendChild(snippet);
    }
  }

  // For items not visible (title didn't match but content did), append them
  for (const r of contentMatches) {
    if (visibleIds.has(r.id)) continue;
    const li = document.createElement('li');
    li.dataset.id = r.id;
    li.classList.add('search-content-match');

    const titleSpan = document.createElement('span');
    titleSpan.textContent = r.title || '新对话';
    titleSpan.style.flex = '1';
    li.appendChild(titleSpan);

    const snippet = document.createElement('div');
    snippet.className = 'conv-snippet';
    snippet.textContent = r.snippet || '';
    li.appendChild(snippet);

    li.addEventListener('click', () => openConversation(r.id));
    convList.appendChild(li);
  }
}

async function openConversation(convId) {
  const conv = await window.pywebview.api.open_conversation(convId);
  if (!conv) return;
  hideHome();
  state.currentConvId = convId;
  convTitle.textContent = conv.title;
  const kw = searchInput.value.trim();
  renderConvList(kw);
  // Re-apply content search results so the list doesn't disappear
  if (kw) _runContentSearch(kw);
  loadHistory(conv.messages || []);
  // 项目目录在本机不存在时提示（多为跨机器同步导致的绝对路径失效）
  if (conv.project_path && conv.project_exists === false) {
    const banner = document.createElement('div');
    banner.className = 'project-missing-banner';
    banner.innerHTML = `⚠ 该会话绑定的项目目录在本机不存在：<code>${escapeHtml(conv.project_path)}</code>`
                     + `<br>模型读写文件/执行命令可能失败。`
                     + `<button class="btn-reset-project btn-secondary">重设目录</button>`;
    banner.querySelector('.btn-reset-project').addEventListener('click', () => resetConversationProject(convId));
    chatMessages.insertBefore(banner, chatMessages.firstChild);
  }
  // If this conversation is currently streaming, re-attach all stream nodes
  if (_streamingConvId === convId && _streamNodes.length > 0) {
    _streamNodes.forEach(node => chatMessages.appendChild(node));
    if (_typingEl) chatMessages.appendChild(_typingEl);
    scrollToBottom();
  }
  Chat.updateFileOps(conv.file_ops || []);
  // 刷新上下文用量
  const ctx = await window.pywebview.api.get_context_usage(convId);
  updateContextBar(ctx.used, ctx.total);
  // Highlight and scroll to keyword match in chat
  if (kw) {
    requestAnimationFrame(() => _highlightAndScrollTo(kw));
  }
}

// 重设会话绑定的项目目录（用于修复跨机器同步导致的失效路径）
async function resetConversationProject(convId) {
  if (!confirm('重新选择本机的项目目录？\n\n注意：项目目录在系统提示中，重设后下一条消息会重新计算一次上下文（一次性变慢/变贵），之后恢复正常缓存。')) return;
  const r = await window.pywebview.api.set_conversation_project(convId, '');
  if (!r || r.cancelled) return;
  // 更新本地会话的 project_path，使侧边栏重新分组
  const c = state.conversations.find(x => x.id === convId);
  if (c) c.project_path = r.path;
  renderConvList(searchInput.value);
  // 若当前正打开此会话，重新加载以移除失效 banner
  if (state.currentConvId === convId) await openConversation(convId);
}

function _highlightAndScrollTo(keyword) {
  // Remove previous highlights
  chatMessages.querySelectorAll('mark.search-highlight').forEach(m => {
    const parent = m.parentNode;
    parent.replaceChild(document.createTextNode(m.textContent), m);
    parent.normalize();
  });
  if (!keyword) return;

  const regex = new RegExp(`(${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  const walker = document.createTreeWalker(chatMessages, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const p = node.parentNode;
      if (!p) return NodeFilter.FILTER_REJECT;
      const tag = p.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'MARK') return NodeFilter.FILTER_REJECT;
      if (regex.test(node.nodeValue)) { regex.lastIndex = 0; return NodeFilter.FILTER_ACCEPT; }
      return NodeFilter.FILTER_REJECT;
    }
  });

  const nodes = [];
  let n;
  while ((n = walker.nextNode())) nodes.push(n);

  let firstMark = null;
  for (const textNode of nodes) {
    const parts = textNode.nodeValue.split(regex);
    if (parts.length <= 1) continue;
    const frag = document.createDocumentFragment();
    for (const part of parts) {
      if (regex.test(part)) {
        regex.lastIndex = 0;
        const mark = document.createElement('mark');
        mark.className = 'search-highlight';
        mark.textContent = part;
        frag.appendChild(mark);
        if (!firstMark) firstMark = mark;
      } else {
        frag.appendChild(document.createTextNode(part));
      }
    }
    textNode.parentNode.replaceChild(frag, textNode);
  }

  // Scroll to first match
  if (firstMark) {
    firstMark.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// 点击"+ 新对话"：先显示主页选择项目，而非直接建会话
async function newConversation() {
  await showHome();
}

// 真正创建会话（绑定可选的项目目录）并进入
async function startConvWithProject(projectPath = '') {
  const conv = await window.pywebview.api.new_conversation(projectPath);
  state.conversations.unshift({ id: conv.id, title: conv.title, project_path: conv.project_path || '' });
  state.currentConvId = conv.id;
  convTitle.textContent = conv.title;
  hideHome();
  renderConvList(searchInput.value);
  chatMessages.innerHTML = '';
  updateContextBar(0, 80000);
}

// ── 主页（项目选择）────────────────────────────────────────────────
function hideHome() {
  $('home-view').classList.add('hidden');
  chatMessages.style.display = '';
}

async function showHome() {
  $('home-view').classList.remove('hidden');
  chatMessages.style.display = 'none';
  $('home-project-convs').classList.add('hidden');
  await renderHomeProjects();
}

async function renderHomeProjects() {
  const box = $('home-project-list');
  box.innerHTML = '<span class="home-empty">加载中...</span>';
  const projects = await window.pywebview.api.list_recent_projects();
  box.innerHTML = '';
  if (!projects.length) {
    box.innerHTML = '<span class="home-empty">暂无最近项目，点击上方“添加新项目”。</span>';
    return;
  }
  projects.forEach(p => {
    const card = document.createElement('div');
    card.className = 'home-project-card';
    const missing = p.exists === false;
    if (missing) card.classList.add('hp-missing');
    const warn = missing ? '<span class="hp-warn" title="该目录在本机不存在，可能是从其他机器同步而来">⚠ 路径不存在</span>' : '';
    card.innerHTML = `<div class="hp-name">📁 ${escapeHtml(p.name || '')}${warn}</div>`
                   + `<div class="hp-path">${escapeHtml(p.path || '')}</div>`;
    // 单击：展示该项目历史会话；“新建”按钮：直接以该项目开新会话
    card.addEventListener('click', () => showProjectConvs(p.path, p.name));
    const acts = document.createElement('div');
    acts.className = 'hp-actions';
    const startBtn = document.createElement('button');
    startBtn.className = 'hp-start btn-secondary';
    startBtn.textContent = '+ 新对话';
    startBtn.addEventListener('click', e => { e.stopPropagation(); startConvWithProject(p.path); });
    const editBtn = document.createElement('button');
    editBtn.className = 'hp-edit btn-secondary';
    editBtn.textContent = '✏ 改地址';
    editBtn.title = '修改项目目录（该项目下所有会话一并改绑）';
    editBtn.addEventListener('click', e => { e.stopPropagation(); editProjectPath(p.path, p.name); });
    const delBtn = document.createElement('button');
    delBtn.className = 'hp-del btn-danger';
    delBtn.textContent = '🗑 移除';
    delBtn.title = '从最近项目移除（不删会话，会话变为未分类）';
    delBtn.addEventListener('click', e => { e.stopPropagation(); removeProject(p.path, p.name); });
    acts.appendChild(startBtn);
    acts.appendChild(editBtn);
    acts.appendChild(delBtn);
    card.appendChild(acts);
    box.appendChild(card);
  });
}

async function editProjectPath(oldPath, name) {
  // new_path 传空 → 后端弹文件夹选择框
  const r = await window.pywebview.api.update_project_path(oldPath, '');
  if (r && r.cancelled) return;
  if (r && r.ok) {
    // 改了项目目录 = 该项目所有会话缓存失效一次（项目路径在系统提示前缀），下条消息重算
    state.conversations = await window.pywebview.api.list_conversations();
    renderConvList('');
    await renderHomeProjects();
  } else {
    alert('修改失败：' + ((r && r.error) || '未知错误'));
  }
}

async function removeProject(path, name) {
  if (!confirm(`从最近项目移除「${name}」？\n\n该项目下的会话不会被删除，只是变为未分类。`)) return;
  const r = await window.pywebview.api.remove_recent_project(path);
  if (r && r.ok) {
    state.conversations = await window.pywebview.api.list_conversations();
    renderConvList('');
    await renderHomeProjects();
  } else {
    alert('移除失败：' + ((r && r.error) || '未知错误'));
  }
}

async function showProjectConvs(projectPath, projectName) {
  const wrap = $('home-project-convs');
  const list = $('home-conv-list');
  $('home-convs-label').textContent = `“${projectName}” 的历史会话`;
  wrap.classList.remove('hidden');
  list.innerHTML = '<span class="home-empty">加载中...</span>';
  const convs = await window.pywebview.api.get_project_conversations(projectPath);
  list.innerHTML = '';
  if (!convs.length) {
    list.innerHTML = '<span class="home-empty">该项目暂无会话，点击右侧“+ 新对话”开始。</span>';
    return;
  }
  convs.forEach(c => {
    const item = document.createElement('div');
    item.className = 'home-conv-item';
    item.textContent = c.title || '新对话';
    item.addEventListener('click', async () => { hideHome(); await openConversation(c.id); });
    list.appendChild(item);
  });
}

async function deleteConversation(convId) {
  if (!confirm('确定删除这条对话？')) return;
  await window.pywebview.api.delete_conversation(convId);
  state.conversations = state.conversations.filter(c => c.id !== convId);
  if (state.currentConvId === convId) {
    chatMessages.innerHTML = '';
    state.currentConvId = null;
    convTitle.textContent = '';
    if (state.conversations.length > 0) await openConversation(state.conversations[0].id);
    else await newConversation();
  }
  renderConvList(searchInput.value);
}

$('btn-new-conv').addEventListener('click', newConversation);
$('btn-token-heatmap').addEventListener('click', openUsageHeatmap);
$('btn-home-add').addEventListener('click', async () => {
  const proj = await window.pywebview.api.choose_project_folder();
  if (proj && proj.path) await startConvWithProject(proj.path);
});
$('btn-home-noproject').addEventListener('click', () => startConvWithProject(''));

// ── Token 用量热力图 ─────────────────────────────────────────────
let _usageMonth = new Date();
_usageMonth.setDate(1);

function _fmtTokens(n) {
  n = Number(n || 0);
  if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}

async function openUsageHeatmap() {
  $('usage-overlay').classList.remove('hidden');
  await renderUsageHeatmap();
}

function closeUsageHeatmap() {
  hideUsageTooltip();
  $('usage-overlay').classList.add('hidden');
}

async function renderUsageHeatmap() {
  const y = _usageMonth.getFullYear();
  const m = _usageMonth.getMonth() + 1;
  $('usage-month-label').textContent = `${y} 年 ${String(m).padStart(2, '0')} 月`;
  const data = await window.pywebview.api.get_token_usage_month(y, m);
  const stats = data.stats || {};
  $('usage-stats').innerHTML = `
    <div><b>${_fmtTokens(stats.total_tokens)}</b><span>本月总量</span></div>
    <div><b>${_fmtTokens(stats.average_per_day)}</b><span>日均</span></div>
    <div><b>${stats.top_model ? escapeHtml(stats.top_model) : '-'}</b><span>主要模型</span></div>
    <div><b>${stats.peak_date || '-'}</b><span>峰值日期</span></div>`;

  const box = $('usage-heatmap');
  box.innerHTML = '';
  if (data.error) {
    box.innerHTML = `<div class="usage-empty">读取失败：${escapeHtml(data.error)}</div>`;
    return;
  }
  const days = data.days || {};
  const maxVal = Math.max(1, ...Object.values(days).map(d => Number(d.total_tokens || 0)));
  for (let day = 1; day <= (data.days_in_month || 31); day++) {
    const date = `${y}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const item = days[date] || { date, total_tokens: 0, models: {} };
    const total = Number(item.total_tokens || 0);
    let level = 0;
    if (total > 0) level = Math.max(1, Math.ceil((total / maxVal) * 4));
    const cell = document.createElement('div');
    cell.className = 'usage-cell';
    cell.dataset.level = level;
    cell.textContent = day;
    cell.addEventListener('mouseenter', e => showUsageTooltip(e, item));
    cell.addEventListener('mousemove', moveUsageTooltip);
    cell.addEventListener('mouseleave', hideUsageTooltip);
    box.appendChild(cell);
  }
}

function getUsageTooltip() {
  const tip = $('usage-tooltip');
  // Keep the tooltip directly under <body>. A fixed-position element inside
  // the animated modal can be offset because the modal uses CSS transform.
  if (tip && tip.parentElement !== document.body) {
    document.body.appendChild(tip);
  }
  return tip;
}

function showUsageTooltip(e, item) {
  const models = Object.entries(item.models || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([name, tokens]) => `<div><span>${escapeHtml(name)}</span><b>${_fmtTokens(tokens)}</b></div>`)
    .join('') || '<div><span>无调用记录</span><b>0</b></div>';
  const tip = getUsageTooltip();
  tip.innerHTML = `<strong>${escapeHtml(item.date || '')}</strong><p>总计：${_fmtTokens(item.total_tokens || 0)} tokens</p>${models}`;
  tip.classList.remove('hidden');
  moveUsageTooltip(e);
}

function moveUsageTooltip(e) {
  const tip = getUsageTooltip();
  if (!tip) return;
  const offset = 6;
  const rect = tip.getBoundingClientRect();
  const maxLeft = window.innerWidth - rect.width - 8;
  const maxTop = window.innerHeight - rect.height - 8;
  tip.style.left = `${Math.max(8, Math.min(e.clientX + offset, maxLeft))}px`;
  tip.style.top = `${Math.max(8, Math.min(e.clientY + offset, maxTop))}px`;
}

function hideUsageTooltip() {
  const tip = getUsageTooltip();
  if (tip) tip.classList.add('hidden');
}

$('usage-heatmap').addEventListener('mouseleave', hideUsageTooltip);
$('usage-modal').addEventListener('mouseleave', hideUsageTooltip);
$('usage-overlay').addEventListener('mousemove', e => {
  if (!$('usage-overlay').classList.contains('hidden') && !e.target.closest('.usage-cell')) {
    hideUsageTooltip();
  }
});

$('btn-usage-close').addEventListener('click', closeUsageHeatmap);
$('btn-usage-prev').addEventListener('click', async () => {
  _usageMonth.setMonth(_usageMonth.getMonth() - 1);
  await renderUsageHeatmap();
});
$('btn-usage-next').addEventListener('click', async () => {
  _usageMonth.setMonth(_usageMonth.getMonth() + 1);
  await renderUsageHeatmap();
});

// ── History rendering ─────────────────────────────────────────────
function loadHistory(messages) {
  chatMessages.classList.add('no-animate');
  chatMessages.innerHTML = '';
  _resetToolStreak();
  // tool_call_id → 工具名映射：tool 结果消息只带 id，需借此还原真实工具名，
  // 这样回放能复用实时的 addToolCallBubble/addToolResultBubble（按名字匹配），
  // 渲染出和实时一致的「调用气泡（参数+结果可折叠）」。
  const tcNameById = {};
  messages.forEach(msg => {
    const role = msg.role;
    const content = msg.content || '';
    if (role === 'user') {
      addUserBubble(content);
    } else if (role === 'assistant') {
      if (content) addAssistantBubble(content);
      // 还原该轮的工具调用气泡（含参数、占位「等待中…」）
      if (Array.isArray(msg.tool_calls)) {
        msg.tool_calls.forEach(tc => {
          const name = tc.function && tc.function.name || 'tool';
          let args = {};
          try { args = JSON.parse((tc.function && tc.function.arguments) || '{}'); }
          catch { args = {}; }
          if (tc.id) tcNameById[tc.id] = name;
          addToolCallBubble(name, args);
        });
      }
    } else if (role === 'tool') {
      // 用真实工具名匹配上面的占位气泡并填入结果
      const name = tcNameById[msg.tool_call_id] || 'tool';
      addToolResultBubble(name, content);
    }
  });
  scrollToBottom();
  // Re-enable animations after history is rendered
  requestAnimationFrame(() => chatMessages.classList.remove('no-animate'));
}

function addUserBubble(text) {
  _resetToolStreak();
  const div = document.createElement('div');
  div.className = 'bubble bubble-user';
  const collapsible = document.createElement('div');
  collapsible.className = 'bubble-collapsible';
  collapsible.innerHTML = `<div class="bubble-label">You</div><div class="bubble-content">${buildUserContent(text)}</div>`;
  div.appendChild(collapsible);
  chatMessages.appendChild(div);
  // Load image thumbnails + wire doc cards (shared with tool-result bubbles)
  _hydrateImgThumbs(collapsible);
  // Check if content exceeds collapse threshold after render
  requestAnimationFrame(() => {
    if (collapsible.scrollHeight > 130) {
      collapsible.classList.add('needs-collapse');
      const btn = document.createElement('button');
      btn.className = 'bubble-toggle-btn';
      btn.textContent = '展开 ▼';
      btn.addEventListener('click', () => {
        const expanded = collapsible.classList.toggle('expanded');
        btn.textContent = expanded ? '收起 ▲' : '展开 ▼';
      });
      div.appendChild(btn);
    } else {
      collapsible.classList.add('expanded');
    }
  });
  return div;
}

function buildUserContent(text) {
  // Python 用 \n\n 连接各部分。附件标记形如：
  //   [图片: name 路径: abs]\n...提示语...
  //   [附件: name 路径: abs]\n...正文...
  // 图片渲染为缩略图卡片（点击放大），文档渲染为可点击卡片（在文件夹中定位）。
  // 兼容旧格式 [图片: name] / [附件: name]（无路径）。
  const docIcon = name => {
    const ext = (name.split('.').pop() || '').toLowerCase();
    return ({ pdf:'📕', doc:'📄', docx:'📄', xls:'📊', xlsx:'📊', csv:'📊',
              ppt:'📑', pptx:'📑', txt:'📃', md:'📃', json:'🗂', zip:'🗜' })[ext] || '📎';
  };
  // 分离文字段与附件段：文字在上、图片/附件缩略图统一排到气泡下方。
  const textParts = [];
  const attachParts = [];
  text.split(/\n\n/).forEach(seg => {
    const mImg = seg.match(/^\[图片: (.+?)(?: 路径: ([^\]]*))?\]/);
    if (mImg) {
      const fname = mImg[1];
      const fpath = mImg[2] || fname;
      attachParts.push(
        `<span class="attach-card attach-image">`
        + `<img class="chat-img-thumb" data-path="${escapeHtml(fpath)}" src="" alt="${escapeHtml(fname)}">`
        + `<span class="attach-name">🖼 ${escapeHtml(fname)}</span></span>`);
      return;
    }
    const mDoc = seg.match(/^\[附件: (.+?)(?: 路径: ([^\]]*))?\]/);
    if (mDoc) {
      const fname = mDoc[1];
      const fpath = mDoc[2] || '';
      const openable = fpath ? ' attach-openable' : '';
      attachParts.push(
        `<span class="attach-card attach-doc${openable}" data-path="${escapeHtml(fpath)}" title="${fpath ? '在文件夹中定位' : ''}">`
        + `<span class="attach-icon">${docIcon(fname)}</span>`
        + `<span class="attach-name">${escapeHtml(fname)}</span></span>`);
      return;
    }
    textParts.push(escapeHtml(seg).replace(/\n/g, '<br>'));
  });
  let html = textParts.join('<br>');
  if (attachParts.length) {
    html += `<div class="attach-row">${attachParts.join('')}</div>`;
  }
  return html;
}

// 在容器内加载图片缩略图（按 data-path）并绑定点击放大 / 文档卡片定位。
// 供用户气泡和工具结果气泡（generate_image）共用。
function _hydrateImgThumbs(container) {
  container.querySelectorAll('img.chat-img-thumb[data-path]').forEach(async img => {
    const dataUrl = await window.pywebview.api.get_image_data(img.dataset.path);
    if (dataUrl) img.src = dataUrl;
    img.addEventListener('click', () => openLightbox(img.src));
  });
  container.querySelectorAll('.attach-doc.attach-openable[data-path]').forEach(card => {
    card.addEventListener('click', () => {
      if (card.dataset.path) window.pywebview.api.open_file_location(card.dataset.path);
    });
  });
}

function addAssistantBubble(content) {
  _resetToolStreak();
  const div = document.createElement('div');
  div.className = 'bubble bubble-assistant';
  div.innerHTML = `<div class="bubble-label">Assistant</div><div class="bubble-content">${renderMarkdown(content)}</div>`;
  chatMessages.appendChild(div);
  _hydrateImgThumbs(div);
  scrollToBottom();
  return div;
}

// ── 连续工具调用折叠 ──────────────────────────────────────────────
// 同一段连续工具调用超过阈值后，后续气泡收进可展开的折叠块（被 assistant
// 文本气泡打断则重置计数，见各文本气泡入口的 _resetToolStreak 调用）。
const _TOOL_FOLD_THRESHOLD = 5;
let _toolStreak = 0;          // 当前连续工具调用数
let _toolFoldContainer = null; // 当前折叠容器（超阈值后创建）

function _resetToolStreak() {
  _toolStreak = 0;
  _toolFoldContainer = null;
}

function _ensureFoldContainer() {
  if (_toolFoldContainer && _toolFoldContainer.parentNode) return _toolFoldContainer;
  const wrap = document.createElement('div');
  wrap.className = 'tool-fold collapsed';
  wrap.innerHTML =
    `<div class="tool-fold-header">`
    + `<span class="tool-fold-chevron">▶</span>`
    + `<span class="tool-fold-label">已折叠 <b class="tool-fold-count">0</b> 个工具调用</span>`
    + `</div>`
    + `<div class="tool-fold-body"></div>`;
  wrap.querySelector('.tool-fold-header').addEventListener('click', () => {
    wrap.classList.toggle('collapsed');
  });
  chatMessages.appendChild(wrap);
  _toolFoldContainer = wrap;
  return wrap;
}

function _placeToolBubble(div) {
  _toolStreak += 1;
  if (_toolStreak <= _TOOL_FOLD_THRESHOLD) {
    chatMessages.appendChild(div);
    return;
  }
  const wrap = _ensureFoldContainer();
  wrap.querySelector('.tool-fold-body').appendChild(div);
  const cnt = _toolStreak - _TOOL_FOLD_THRESHOLD;
  wrap.querySelector('.tool-fold-count').textContent = cnt;
}

function addToolCallBubble(toolName, args) {
  const div = document.createElement('div');
  div.className = 'bubble bubble-tool-call';
  const argsStr = JSON.stringify(args, null, 2);
  const icons = { web_search:'🔍', read_file:'📄', run_command:'⚙️', write_file:'✏️', list_directory:'📁' };
  const icon = icons[toolName] || '🔧';
  div.innerHTML = `
    <div class="tool-header" onclick="this.parentElement.classList.toggle('tool-expanded')">
      <span class="tool-icon">${icon}</span>
      <span class="tool-name">${escapeHtml(toolName)}</span>
      <span class="tool-args-preview">${escapeHtml(JSON.stringify(args).slice(0,80))}${JSON.stringify(args).length>80?'…':''}</span>
      <span class="tool-chevron">▶</span>
    </div>
    <div class="tool-body">
      <div class="tool-section-label">参数</div>
      <pre class="tool-pre">${escapeHtml(argsStr)}</pre>
      <div class="tool-section-label tool-result-label">结果</div>
      <div class="tool-result-content">等待中…</div>
    </div>`;
  _placeToolBubble(div);
  scrollToBottom();
  return div;
}

// 只有这些工具的结果按图片缩略图渲染（其余工具结果即便文本里含 "[图片: ...]"
// 也按普通文本截断折叠，避免 read_file 读到讲解附件格式的文档时铺开整个文件）。
const _IMAGE_TOOLS = new Set(['generate_image', 'edit_image']);

function addToolResultBubble(toolName, result) {
  // find the last tool-call bubble for this tool and update its result inline
  // Search both attached (chatMessages) and detached (_streamNodes) bubbles
  const attached = Array.from(chatMessages.querySelectorAll('.bubble-tool-call'));
  const detached = _streamNodes.filter(n => n.classList && n.classList.contains('bubble-tool-call') && !n.parentNode);
  const bubbles = [...attached, ...detached];
  for (let i = bubbles.length - 1; i >= 0; i--) {
    const nameEl = bubbles[i].querySelector('.tool-name');
    if (nameEl && nameEl.textContent === toolName) {
      const resultEl = bubbles[i].querySelector('.tool-result-content');
      if (resultEl && resultEl.textContent === '等待中…') {
        // 仅图片生成类工具的结果按缩略图渲染；其他工具（如 read_file 读到含
        // "[图片: ...]" 文本的文件）一律走截断文本路径，避免误判铺开整个文件。
        if (_IMAGE_TOOLS.has(toolName) && /\[图片: .+?(?: 路径: [^\]]*)?\]/.test(result)) {
          resultEl.innerHTML = buildUserContent(result);
          _hydrateImgThumbs(resultEl);
          // 默认展开，让缩略图可见
          bubbles[i].classList.add('tool-expanded');
          return;
        }
        const preview = result.replace(/\n/g,' ').trim().slice(0, 200) + (result.length > 200 ? '…' : '');
        resultEl.textContent = preview;
        // Add file link for write/patch tools
        if (['write_file', 'apply_patch'].includes(toolName)) {
          _appendFileLinks(bubbles[i], result);
        }
        return;
      }
    }
  }
  // fallback: orphaned result bubble
  const div = document.createElement('div');
  div.className = 'bubble bubble-tool-call';
  const icons = { web_search:'🔍', read_file:'📄', run_command:'⚙️', write_file:'✏️', apply_patch:'🩹', list_directory:'📁', glob_files:'🔎', grep_files:'🔎' };
  const icon = icons[toolName] || '🔧';
  // 含图片标记且是图片生成工具 → 展开并渲染缩略图
  if (_IMAGE_TOOLS.has(toolName) && /\[图片: .+?(?: 路径: [^\]]*)?\]/.test(result || '')) {
    div.classList.add('tool-expanded');
    div.innerHTML = `<div class="tool-header"><span class="tool-icon">🖼</span><span class="tool-name">${escapeHtml(toolName)}</span><span class="tool-chevron">▶</span></div>`
      + `<div class="tool-body"><div class="tool-result-content"></div></div>`;
    const rc = div.querySelector('.tool-result-content');
    rc.innerHTML = buildUserContent(result);
    chatMessages.appendChild(div);
    _hydrateImgThumbs(rc);
    scrollToBottom();
    return;
  }
  div.innerHTML = `<div class="tool-header"><span class="tool-icon">${icon}</span><span class="tool-name">${escapeHtml(toolName)}</span></div>`;
  chatMessages.appendChild(div);
  scrollToBottom();
}

function _appendFileLinks(bubble, result) {
  // Extract file paths from write_file/apply_patch results (lines starting with ✅)
  const pathRegex = /[A-Z]:\\[^\n]+|\/[^\n\s]+/g;
  const paths = [];
  for (const line of result.split('\n')) {
    if (line.includes('✅') || line.includes('📁')) {
      const matches = line.match(pathRegex);
      if (matches) {
        for (const m of matches) {
          if (line.includes('✅') && !paths.includes(m)) paths.push(m);
        }
      }
    }
  }
  if (paths.length === 0) return;
  const linkDiv = document.createElement('div');
  linkDiv.className = 'tool-file-links';
  paths.forEach(fp => {
    const a = document.createElement('span');
    a.className = 'file-link';
    a.textContent = `📂 ${fp.split(/[/\\]/).pop()}`;
    a.title = fp;
    a.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      window.pywebview.api.open_file_location(fp);
    });
    linkDiv.appendChild(a);
  });
  bubble.appendChild(linkDiv);
}

function addErrorBubble(msg) {
  const div = document.createElement('div');
  div.className = 'bubble bubble-error';
  div.innerHTML = `<div class="bubble-label">Error</div><div>${escapeHtml(msg)}</div>`;
  chatMessages.appendChild(div);
  scrollToBottom();
}

// ── Streaming assistant bubble ────────────────────────────────────
let _streamBubble = null;
let _streamContent = '';
let _typingEl = null;
let _streamingConvId = null;  // tracks which conv is currently streaming
let _streamNodes = [];        // all DOM nodes added during this streaming session

function startAssistantStream() {
  removeTypingIndicator();
  _streamContent = '';
  _streamingConvId = state.currentConvId;
  _streamNodes = [];
  _streamBubble = document.createElement('div');
  _streamBubble.className = 'bubble bubble-assistant';
  _streamBubble.innerHTML = `<div class="bubble-label">Assistant</div><div class="bubble-content"></div>`;
  chatMessages.appendChild(_streamBubble);
  _streamNodes.push(_streamBubble);
  _typingEl = document.createElement('div');
  _typingEl.className = 'typing-indicator';
  _typingEl.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  chatMessages.appendChild(_typingEl);
  scrollToBottom();
}

// Called from Python via evaluate_js
window.Chat = {
  appendToken(token) {
    removeTypingIndicator();
    // 本轮首个文本 token 到达 → 模型开口说话，打断连续工具调用，重置折叠计数
    if (!_streamContent && token) _resetToolStreak();
    _streamContent += token;
    if (_streamBubble) {
      _streamBubble.querySelector('.bubble-content').innerHTML = renderMarkdown(_streamContent);
      if (state.currentConvId === _streamingConvId) scrollToBottom();
    }
  },
  showToolCall(toolName, args) {
    const el = addToolCallBubble(toolName, args);
    if (_streamingConvId) _streamNodes.push(el);
    // If viewing a different conv, detach immediately (will re-attach on switch back)
    if (state.currentConvId !== _streamingConvId && el.parentNode) {
      el.parentNode.removeChild(el);
    }
  },
  showToolResult(toolName, result) {
    addToolResultBubble(toolName, result);
    if (toolName.startsWith('worktree_')) refreshWorktreePanel();
  },
  updateTodo(items) {
    const panel = $('todo-panel');
    const list = $('todo-list');
    if (!items || items.length === 0) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    list.innerHTML = '';
    items.forEach(item => {
      const li = document.createElement('li');
      const marks = { completed: '✓', in_progress: '▶', pending: '○' };
      const mark = marks[item.status] || '○';
      if (item.status === 'completed') li.classList.add('todo-completed');
      else if (item.status === 'in_progress') li.classList.add('todo-inprogress');
      li.innerHTML = `<span class="todo-mark">${mark}</span><span>${escapeHtml(item.content)}${
        item.status === 'in_progress' ? `<span class="todo-active">${escapeHtml(item.activeForm || '')}</span>` : ''
      }</span>`;
      list.appendChild(li);
    });
  },
  finishMessage() {
    removeTypingIndicator();
    if (_streamBubble) _hydrateImgThumbs(_streamBubble);
    _streamBubble = null;
    _streamContent = '';
    _streamingConvId = null;
    _streamNodes = [];
    _thinkingBubble = null;
    _thinkingContent = '';
    setRunning(false);
    renderConvList(searchInput.value);
  },
  updateFileOps(ops) {
    const panel = $('fileops-panel');
    const list = $('fileops-list');
    if (!ops || ops.length === 0) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    list.innerHTML = '';
    // Show newest first
    const sorted = [...ops].reverse();
    sorted.forEach(op => {
      const li = document.createElement('li');
      li.className = 'fileops-item';
      const fname = op.path.split(/[/\\]/).pop();
      const icon = op.tool === 'apply_patch' ? '🩹' : '✏️';
      // 增删行数（绿/红），无快照时不显示
      let stats = '';
      if (typeof op.added === 'number' || typeof op.removed === 'number') {
        const a = op.added || 0, r = op.removed || 0;
        stats = `<span class="fileops-stats">`
              + (a ? `<span class="fo-add">+${a}</span>` : '')
              + (r ? `<span class="fo-del">-${r}</span>` : '')
              + (!a && !r ? `<span class="fo-none">±0</span>` : '')
              + `</span>`;
      }
      li.innerHTML = `<span class="fileops-icon">${icon}</span>`
                   + `<span class="fileops-name" title="${escapeHtml(op.path)}">${escapeHtml(fname)}</span>`
                   + stats;
      li.addEventListener('click', () => openDiffModal(op.path, fname));
      list.appendChild(li);
    });
  },
  updateConvTitle(convId, title) {
    const conv = state.conversations.find(c => c.id === convId);
    if (conv) conv.title = title;
    if (convId === state.currentConvId) convTitle.textContent = title;
    renderConvList(searchInput.value);
  },
  showTeamNotification(msg) {
    const div = document.createElement('div');
    div.className = 'bubble bubble-tool';
    div.innerHTML = `<div class="bubble-label">Team</div><div class="bubble-content">${escapeHtml(msg)}</div>`;
    chatMessages.appendChild(div);
    scrollToBottom();
    // Refresh worktree panel on team activity
    refreshWorktreePanel();
  },
  updateContext(used, total) {
    updateContextBar(used, total);
  },
  updateUsage(data) {
    const r = data.round || {};
    const s = data.session || {};
    const roundTotal = (r.prompt || 0) + (r.completion || 0);
    const sessionTotal = (s.prompt_tokens || 0) + (s.completion_tokens || 0);
    const cacheHit = s.cache_hit_tokens || 0;
    const cacheMiss = s.cache_miss_tokens || 0;
    const cacheRate = (cacheHit + cacheMiss) > 0
      ? Math.round(cacheHit / (cacheHit + cacheMiss) * 100) + '%'
      : '-';
    const fmt = n => n >= 1000 ? (n/1000).toFixed(1)+'k' : String(n);
    $('cost-round').textContent = `本轮: ${fmt(roundTotal)}`;
    $('cost-session').textContent = `会话: ${fmt(sessionTotal)}`;
    $('cost-cache').textContent = `缓存: ${cacheRate}`;
  },
  appendThinking(token) {
    if (!_thinkingBubble) {
      _thinkingBubble = document.createElement('div');
      _thinkingBubble.className = 'bubble bubble-thinking';
      const toggle = document.createElement('div');
      toggle.className = 'thinking-toggle';
      toggle.textContent = '思考过程';
      const body = document.createElement('div');
      body.className = 'thinking-body';
      toggle.addEventListener('click', () => {
        toggle.classList.toggle('open');
        body.classList.toggle('open');
      });
      _thinkingBubble.appendChild(toggle);
      _thinkingBubble.appendChild(body);
      if (state.currentConvId === _streamingConvId) {
        chatMessages.appendChild(_thinkingBubble);
      }
      if (_streamingConvId) _streamNodes.push(_thinkingBubble);
    }
    _thinkingContent += token;
    _thinkingBubble.querySelector('.thinking-body').textContent = _thinkingContent;
    if (state.currentConvId === _streamingConvId) scrollToBottom();
  },
  showError(msg) {
    removeTypingIndicator();
    _streamBubble = null;
    _streamingConvId = null;
    _streamNodes = [];
    addErrorBubble(msg);
    setRunning(false);
  },
  showConfirmDialog(toolName, args, wildcard) {
    $('confirm-title').textContent = `确认执行：${toolName}`;
    $('confirm-detail').textContent = JSON.stringify(args, null, 2);
    _confirmCommand = args.command || '';
    _confirmWildcard = wildcard || '';
    $('btn-confirm-always').style.display = (toolName === 'run_command' && _confirmCommand) ? '' : 'none';
    // Show wildcard button when backend suggests a pattern
    const btnWild = $('btn-confirm-wildcard');
    if (btnWild) {
      if (_confirmWildcard) {
        btnWild.style.display = '';
        btnWild.textContent = `允许所有 ${_confirmWildcard}`;
      } else {
        btnWild.style.display = 'none';
      }
    }
    _clearCountdown();
    $('confirm-overlay').classList.remove('hidden');
    // Show "开启自动确认" button only in confirm mode
    $('btn-confirm-auto').style.display = (state.config.command_safety === 'confirm') ? '' : 'none';
    // Auto-countdown mode
    if (state.config.command_safety === 'auto_countdown') {
      _startCountdown();
    }
  },
};

function removeTypingIndicator() {
  if (_typingEl) { _typingEl.remove(); _typingEl = null; }
}

// ── Send message ──────────────────────────────────────────────────
function setRunning(running) {
  state.running = running;
  btnSend.disabled = running;
  btnStop.disabled = !running;
}

// Paste image from clipboard into input
msgInput.addEventListener('paste', async e => {
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault();
      const file = item.getAsFile();
      if (file) await addFileChip(file);
    } else if (item.kind === 'file') {
      e.preventDefault();
      const file = item.getAsFile();
      if (file) await addFileChip(file);
    }
  }
  // Handle files from clipboard (e.g. copied file in Explorer)
  if (e.clipboardData.files && e.clipboardData.files.length > 0) {
    e.preventDefault();
    for (const file of Array.from(e.clipboardData.files)) {
      await addFileChip(file);
    }
  }
});

msgInput.addEventListener('keydown', e => {
  if (slashMenuVisible()) {
    if (e.key === 'ArrowDown') { e.preventDefault(); slashMenuMove(1); return; }
    if (e.key === 'ArrowUp')   { e.preventDefault(); slashMenuMove(-1); return; }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); slashMenuConfirm(); return; }
    if (e.key === 'Escape')    { e.preventDefault(); slashMenuHide(); return; }
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
msgInput.addEventListener('input', () => { /* slash menu moved to button */ });
$('btn-slash').addEventListener('click', async (e) => {
  e.stopPropagation();
  if (slashMenuVisible()) { slashMenuHide(); return; }
  await loadSkillCmds();
  slashMenuShow(allCmds());
});
document.addEventListener('click', (e) => {
  if (slashMenuVisible() && !slashMenu.contains(e.target) && e.target !== $('btn-slash')) {
    slashMenuHide();
  }
  // Open all external links in system browser
  const a = e.target.closest('a[href]');
  if (a && a.href && a.href.startsWith('http')) {
    e.preventDefault();
    window.pywebview.api.open_url(a.href);
  }
});
btnSend.addEventListener('click', sendMessage);
btnStop.addEventListener('click', () => window.pywebview.api.stop_generation());

// ── Undo last message ────────────────────────────────────────────
let _undoUsed = false;
$('btn-undo').addEventListener('click', async () => {
  if (!state.currentConvId) return;
  if (_undoUsed) { return; }
  _undoUsed = true;
  $('btn-undo').disabled = true;
  const text = await window.pywebview.api.undo_last_message(state.currentConvId);
  if (text === null || text === undefined) {
    _undoUsed = false;
    $('btn-undo').disabled = false;
    return;
  }
  // Reload conversation to reflect removed messages
  const conv = await window.pywebview.api.open_conversation(state.currentConvId);
  if (conv) {
    loadHistory(conv.messages || []);
    Chat.updateFileOps(conv.file_ops || []);
  }
  // Put user text back in input
  msgInput.value = text;
  msgInput.focus();
  setRunning(false);
  _streamBubble = null;
  _streamContent = '';
  _streamingConvId = null;
  _streamNodes = [];
});

// ── Retry last message ───────────────────────────────────────────
$('btn-retry').addEventListener('click', async () => {
  if (!state.currentConvId || state.running) return;
  // Undo last exchange, then immediately resend
  const text = await window.pywebview.api.undo_last_message(state.currentConvId);
  if (text === null || text === undefined) return;
  // Reload conversation
  const conv = await window.pywebview.api.open_conversation(state.currentConvId);
  if (conv) {
    loadHistory(conv.messages || []);
    Chat.updateFileOps(conv.file_ops || []);
  }
  _streamBubble = null;
  _streamContent = '';
  _streamingConvId = null;
  _streamNodes = [];
  // Resend
  addUserBubble(text);
  startAssistantStream();
  setRunning(true);
  _undoUsed = false;
  $('btn-undo').disabled = false;
  await window.pywebview.api.send_message(state.currentConvId, text, []);
});

// ── Model debate ─────────────────────────────────────────────────
$('btn-debate').addEventListener('click', () => {
  if (!state.currentConvId) return;
  // Populate message list for selection
  const container = $('debate-messages');
  container.innerHTML = '';
  const conv = state.conversations.find(c => c.id === state.currentConvId);
  // Get messages from DOM bubbles
  const bubbles = chatMessages.querySelectorAll('.bubble-user, .bubble-assistant');
  let msgIdx = 0;
  const messages = [];
  // We need actual message indices from the conversation
  // Fetch from backend
  window.pywebview.api.open_conversation(state.currentConvId).then(convData => {
    if (!convData) return;
    const msgs = convData.messages || [];
    msgs.forEach((m, i) => {
      if (m.role !== 'user' && m.role !== 'assistant') return;
      if (!m.content) return;
      const label = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = i;
      cb.checked = true; // default select last few
      if (i >= msgs.length - 4) cb.checked = true;
      else cb.checked = false;
      const role = document.createElement('span');
      role.className = 'debate-role';
      role.textContent = m.role === 'user' ? '用户' : 'AI';
      const preview = document.createElement('span');
      preview.className = 'debate-preview';
      preview.textContent = m.content.slice(0, 120);
      label.appendChild(cb);
      label.appendChild(role);
      label.appendChild(preview);
      container.appendChild(label);
    });
    // Populate model select (exclude current active model)
    const select = $('debate-model-select');
    select.innerHTML = '';
    const configs = state.config.model_configs || [];
    configs.forEach(mc => {
      const opt = document.createElement('option');
      opt.value = mc.name;
      opt.textContent = mc.name;
      // Pre-select first non-active model
      if (mc.name !== state.config.active_model_config) opt.selected = !select.value;
      select.appendChild(opt);
    });
    $('debate-overlay').classList.remove('hidden');
  });
});

$('btn-debate-close').addEventListener('click', () => $('debate-overlay').classList.add('hidden'));
$('btn-debate-cancel').addEventListener('click', () => $('debate-overlay').classList.add('hidden'));
$('btn-debate-send').addEventListener('click', async () => {
  const checkboxes = $('debate-messages').querySelectorAll('input[type="checkbox"]:checked');
  const indices = Array.from(checkboxes).map(cb => parseInt(cb.value));
  const modelName = $('debate-model-select').value;
  const userPrompt = $('debate-user-prompt').value.trim();
  if (indices.length === 0) { alert('请至少选择一条消息'); return; }
  if (!modelName) { alert('请选择评审模型'); return; }
  $('debate-overlay').classList.add('hidden');
  // Show stream bubble for the debate response
  startAssistantStream();
  setRunning(true);
  await window.pywebview.api.debate_review(state.currentConvId, indices, modelName, userPrompt);
});

async function sendMessage() {
  if (state.running) return;
  const text = msgInput.value.trim();
  if (!text && state.attachedFiles.length === 0) return;
  if (!state.currentConvId) await newConversation();

  // Reset undo state — user sent a new message, allow undo again
  _undoUsed = false;
  $('btn-undo').disabled = false;

  msgInput.value = '';
  // 实时构造与后端一致的附件标记，让用户气泡即时显示缩略图（否则要刷新会话、
  // 重新从带标记的历史 JSON 加载才显示）。格式同 webview_app.send_message：
  // [图片: 名称 路径: 绝对路径] / [附件: 名称 路径: 绝对路径]，附件标记在前、文字在后。
  const imgExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'];
  const markers = state.attachedFiles.map(f => {
    const ext = (f.name.split('.').pop() || '').toLowerCase();
    const kind = imgExts.includes(ext) ? '图片' : '附件';
    return f.path ? `[${kind}: ${f.name} 路径: ${f.path}]` : `[${kind}: ${f.name}]`;
  });
  const bubbleText = [...markers, text].filter(Boolean).join('\n\n');
  addUserBubble(bubbleText || '[附件]');
  startAssistantStream();
  setRunning(true);

  const files = state.attachedFiles.map(f => ({ name: f.name, path: f.path, content: f.content }));
  clearFileChips();

  await window.pywebview.api.send_message(state.currentConvId, text, files);
}

// ── Slash command menu ────────────────────────────────────────────
const slashMenu = $('slash-menu');
let _slashIdx = 0;

// Static built-in commands + dynamic skill entries
const BUILTIN_CMDS = [
  { cmd: '/new',     desc: '新建对话（自动读取记忆）', action: async () => { slashMenuHide(); await newConvWithMemory(); } },
  { cmd: '/compact', desc: '手动压缩上下文',           action: () => { slashMenuHide(); msgInput.value = ''; window.pywebview.api.send_message(state.currentConvId, '__slash_compact__', []); } },
  { cmd: '/skills',  desc: '管理技能库',               action: () => { slashMenuHide(); openSkillManager(); } },
  { cmd: '/memory',  desc: '查看记忆文件',             action: () => { slashMenuHide(); msgInput.value = '请列出并总结所有记忆文件内容。'; } },
];

let _skillCmds = [];
let _skillCmdsLoaded = false;
async function loadSkillCmds() {
  if (_skillCmdsLoaded) return;
  _skillCmdsLoaded = true;
  const skills = await window.pywebview.api.list_skills();
  _skillCmds = skills.map(s => ({
    cmd: `/skill:${s.name}`,
    desc: s.description || '技能',
    action: async () => {
      slashMenuHide();
      const content = await window.pywebview.api.read_skill(s.name);
      msgInput.value = content;
      msgInput.focus();
    },
  }));
}

function allCmds() { return [...BUILTIN_CMDS, ..._skillCmds]; }

function slashMenuVisible() { return !slashMenu.classList.contains('hidden'); }

let _slashGen = 0;
function slashMenuHide() { _slashGen++; slashMenu.classList.add('hidden'); }

function slashMenuShow(cmds) {
  slashMenu.innerHTML = '';
  _slashIdx = 0;
  cmds.forEach((c, i) => {
    const li = document.createElement('li');
    if (i === 0) li.classList.add('active');
    li.innerHTML = `<span class="slash-cmd">${escapeHtml(c.cmd)}</span><span class="slash-desc">${escapeHtml(c.desc)}</span>`;
    li.addEventListener('mousedown', e => { e.preventDefault(); c.action(); });
    slashMenu.appendChild(li);
  });
  // close button at bottom
  const closeBtn = document.createElement('li');
  closeBtn.className = 'slash-menu-close';
  closeBtn.textContent = '× 关闭';
  closeBtn.addEventListener('mousedown', e => { e.preventDefault(); slashMenuHide(); });
  slashMenu.appendChild(closeBtn);
  slashMenu._cmds = cmds;
  slashMenu.classList.remove('hidden');
}

function slashMenuMove(dir) {
  const items = slashMenu.querySelectorAll('li');
  if (!items.length) return;
  items[_slashIdx].classList.remove('active');
  _slashIdx = (_slashIdx + dir + items.length) % items.length;
  items[_slashIdx].classList.add('active');
  items[_slashIdx].scrollIntoView({ block: 'nearest' });
}

function slashMenuConfirm() {
  const cmds = slashMenu._cmds;
  if (cmds && cmds[_slashIdx]) cmds[_slashIdx].action();
}

// /new with memory injection
async function newConvWithMemory() {
  await newConversation();
  const mem = await window.pywebview.api.get_memory_summary();
  if (mem) {
    msgInput.value = `[系统：以下是你的记忆文件，请阅读并记住]\n\n${mem}`;
  }
}

// ── Context bar ───────────────────────────────────────────────────
function updateContextBar(used, total) {
  const pct = Math.min(100, Math.round(used / total * 100));
  $('ctx-used').textContent = used >= 1000 ? (used/1000).toFixed(1)+'k' : used;
  $('ctx-total').textContent = total >= 1000 ? (total/1000).toFixed(0)+'k' : total;
  const fill = $('context-bar-fill');
  fill.style.width = pct + '%';
  fill.classList.toggle('warn',   pct >= 60 && pct < 85);
  fill.classList.toggle('danger', pct >= 85);
  const hint = $('context-bar-hint');
  if (pct >= 85) hint.textContent = '⚠ 即将自动压缩';
  else if (pct >= 60) hint.textContent = '上下文使用较多';
  else hint.textContent = '';
}

// ── Skill manager ─────────────────────────────────────────────────
let _editingSkill = null;

async function openSkillManager() {
  await refreshSkillList();
  $('skill-overlay').classList.remove('hidden');
}

async function refreshSkillList() {
  const skills = await window.pywebview.api.list_skills();
  const ul = $('skill-list');
  ul.innerHTML = '';
  skills.forEach(s => {
    const li = document.createElement('li');
    li.style.cssText = 'padding:6px 8px;cursor:pointer;border-radius:4px;font-size:13px';
    li.textContent = s.name;
    li.title = s.description;
    li.addEventListener('click', async () => {
      _editingSkill = s.name;
      $('skill-name').value = s.name;
      $('skill-desc').value = s.description;
      $('skill-content').value = await window.pywebview.api.read_skill(s.name);
    });
    li.addEventListener('mouseenter', () => li.style.background = 'var(--hover)');
    li.addEventListener('mouseleave', () => li.style.background = '');
    ul.appendChild(li);
  });
}

$('btn-skill-close').addEventListener('click', () => $('skill-overlay').classList.add('hidden'));
$('btn-skill-import').addEventListener('click', async () => {
  const skills = await window.pywebview.api.import_skill();
  if (!skills || skills.length === 0) return;
  if (skills.length === 1) {
    // Single skill: populate form for review before saving
    const s = skills[0];
    _editingSkill = null;
    $('skill-name').value = s.name;
    $('skill-desc').value = s.description;
    $('skill-content').value = s.content;
    $('skill-name').focus();
  } else {
    // Batch import: confirm then save all
    if (!confirm(`发现 ${skills.length} 个技能，全部导入？`)) return;
    let count = 0;
    for (const s of skills) {
      if (s.name) {
        await window.pywebview.api.save_skill(s.name, s.description, s.content);
        count++;
      }
    }
    await refreshSkillList();
    // Show first imported skill in form
    if (skills[0]) {
      _editingSkill = skills[0].name;
      $('skill-name').value = skills[0].name;
      $('skill-desc').value = skills[0].description;
      $('skill-content').value = skills[0].content;
    }
    alert(`已导入 ${count} 个技能`);
  }
});
$('btn-skill-new').addEventListener('click', () => {
  _editingSkill = null;
  $('skill-name').value = '';
  $('skill-desc').value = '';
  $('skill-content').value = '';
  $('skill-name').focus();
});
$('btn-skill-save').addEventListener('click', async () => {
  const name = $('skill-name').value.trim();
  const desc = $('skill-desc').value.trim();
  const content = $('skill-content').value;
  if (!name) return;
  try {
    const result = await window.pywebview.api.save_skill(name, desc, content);
    if (result && result.startsWith('错误')) { alert(result); return; }
  } catch (e) { alert('保存失败: ' + e.message); return; }
  _editingSkill = name;
  await refreshSkillList();
});
$('btn-skill-del').addEventListener('click', async () => {
  const name = $('skill-name').value.trim() || _editingSkill;
  if (!name || !confirm(`删除技能 "${name}"？`)) return;
  await window.pywebview.api.delete_skill(name);
  _editingSkill = null;
  $('skill-name').value = '';
  $('skill-desc').value = '';
  $('skill-content').value = '';
  await refreshSkillList();
});
document.addEventListener('dragover', e => { e.preventDefault(); if (state.dragSrcId) return; document.body.classList.add('drag-over'); });
document.addEventListener('dragleave', e => { if (e.relatedTarget === null) document.body.classList.remove('drag-over'); });
document.addEventListener('drop', async e => {
  e.preventDefault();
  document.body.classList.remove('drag-over');
  const files = Array.from(e.dataTransfer.files);
  for (const file of files) {
    await addFileChip(file);
  }
});

async function addFileChip(file) {
  const name = file.name;
  const ext = name.split('.').pop().toLowerCase();
  const icons = { pdf:'📄', docx:'📝', xlsx:'📊', xls:'📊', png:'🖼', jpg:'🖼', jpeg:'🖼', gif:'🖼', webp:'🖼' };
  const icon = icons[ext] || '📎';
  const isImg = ['png','jpg','jpeg','gif','webp','bmp'].includes(ext);

  const chip = document.createElement('div');
  chip.className = 'file-chip';
  chip.innerHTML = `<span>${icon} ${escapeHtml(name)}</span><span class="chip-status"> ⏳</span><button title="移除">✕</button>`;
  fileChips.appendChild(chip);

  const entry = { name, path: '', content: '' };
  state.attachedFiles.push(entry);

  chip.querySelector('button').addEventListener('click', () => {
    state.attachedFiles = state.attachedFiles.filter(f => f !== entry);
    chip.remove();
  });

  // Read as base64, save via Python to get a stable local path with unique suffix
  const base64 = await readFileAsBase64(file);
  const localPath = await window.pywebview.api.save_uploaded_file(name, base64);
  entry.path = localPath;
  chip.querySelector('.chip-status').textContent = '';

  if (isImg) {
    // 不再在附加时预生成通用描述；改由主模型在需要时按问题调用 analyze_image。
    // 这里仅标记图片已就绪。
    chip.querySelector('.chip-status').textContent = ' 🖼';
  } else {
    const content = await window.pywebview.api.read_file_content(localPath);
    entry.content = content;
    chip.querySelector('.chip-status').textContent = content ? ' ✓' : ' ⚠';
  }
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => { resolve(reader.result.split(',')[1]); };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function clearFileChips() {
  state.attachedFiles = [];
  fileChips.innerHTML = '';
}

// ── Todo panel ───────────────────────────────────────────────────────
$('btn-todo-close').addEventListener('click', () => $('todo-panel').classList.add('hidden'));

// ── Worktree panel ──────────────────────────────────────────────────
$('btn-wt-close').addEventListener('click', () => $('wt-panel').classList.add('hidden'));
$('btn-fileops-close').addEventListener('click', () => $('fileops-panel').classList.add('hidden'));
$('btn-diff-close').addEventListener('click', closeDiffModal);
$('diff-overlay').addEventListener('click', e => { if (e.target === $('diff-overlay')) closeDiffModal(); });
$('btn-diff-open-file').addEventListener('click', () => {
  const p = $('diff-path').textContent;
  if (p) window.pywebview.api.open_file_location(p);
});

async function refreshWorktreePanel() {
  try {
    const wts = await window.pywebview.api.get_worktrees();
    const panel = $('wt-panel');
    const list = $('wt-list');
    // Only show active/kept worktrees
    const visible = (wts || []).filter(w => w.status !== 'removed');
    if (visible.length === 0) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    list.innerHTML = '';
    visible.forEach(wt => {
      const li = document.createElement('li');
      const statusCls = wt.status || 'active';
      const labels = { active: 'ACTIVE', kept: 'KEPT' };
      const taskStr = wt.task_id != null ? `task #${wt.task_id}` : '';
      li.innerHTML = `<span class="wt-status ${statusCls}">${labels[statusCls] || statusCls}</span>`
        + `<span class="wt-info"><span class="wt-name">${escapeHtml(wt.name)}</span>`
        + `<span class="wt-detail">${escapeHtml(wt.branch || '')}${taskStr ? ' · ' + taskStr : ''}</span></span>`;
      list.appendChild(li);
    });
  } catch { /* ignore if API not ready */ }
}

// ── Thinking mode toggle (off / high / max) ─────────────────────
let _thinkingBubble = null;
let _thinkingContent = '';
const _thinkingLevels = ['off', 'high', 'max'];
const _thinkingLabels = { off: '关', high: 'high', max: 'max' };

function initThinkingBtn(level) {
  // Migrate old bool values
  if (level === true) level = 'high';
  if (level === false) level = 'off';
  const btn = $('btn-thinking');
  btn.dataset.level = level || 'high';
  btn.textContent = `💭 ${_thinkingLabels[btn.dataset.level] || 'high'}`;
  btn.classList.toggle('active', btn.dataset.level !== 'off');
}

$('btn-thinking').addEventListener('click', () => {
  const btn = $('btn-thinking');
  const cur = btn.dataset.level || 'off';
  const idx = (_thinkingLevels.indexOf(cur) + 1) % _thinkingLevels.length;
  const next = _thinkingLevels[idx];
  btn.dataset.level = next;
  btn.textContent = `💭 ${_thinkingLabels[next]}`;
  btn.classList.toggle('active', next !== 'off');
  window.pywebview.api.set_thinking(next);
});

// ── Toggle tool calls visibility ─────────────────────────────────
$('btn-toggle-tools').addEventListener('click', () => {
  const btn = $('btn-toggle-tools');
  const msgs = $('chat-messages');
  const hidden = msgs.classList.toggle('hide-tools');
  btn.classList.toggle('active', !hidden);
  btn.textContent = hidden ? '🔧 工具(隐)' : '🔧 工具';
});

// ── Search mode button ────────────────────────────────────────────
// state: search_mode = 'auto' | 'manual', search_enabled = bool
let _searchMode = 'auto';
let _searchEnabled = true;

function initSearchBtn(mode, enabled) {
  _searchMode = mode || 'auto';
  _searchEnabled = enabled !== false;
  _renderSearchBtn();
}

function _renderSearchBtn() {
  const btn = $('btn-search');
  const items = document.querySelectorAll('.search-dropdown-item');
  if (_searchMode === 'auto') {
    // Auto mode: button always lit, shows current mode label
    btn.classList.add('active');
    btn.title = '联网搜索：自动（模型决定）';
  } else {
    // Manual mode: button lit/dim based on _searchEnabled
    btn.classList.toggle('active', _searchEnabled);
    btn.title = _searchEnabled ? '联网搜索：已开启（点击关闭）' : '联网搜索：已关闭（点击开启）';
  }
  items.forEach(el => {
    el.classList.toggle('selected', el.dataset.mode === _searchMode);
  });
}

// Main button click: auto mode → no-op (mode is always on); manual mode → toggle enabled
$('btn-search').addEventListener('click', () => {
  if (_searchMode === 'manual') {
    _searchEnabled = !_searchEnabled;
    window.pywebview.api.set_search_enabled(_searchEnabled);
    _renderSearchBtn();
  }
  // auto mode: clicking the main button does nothing (use arrow to change mode)
});

// Arrow button: toggle dropdown
let _searchDropdownOpen = false;
function _openSearchDropdown() {
  _searchDropdownOpen = true;
  $('search-dropdown').classList.remove('hidden');
}
function _closeSearchDropdown() {
  _searchDropdownOpen = false;
  $('search-dropdown').classList.add('hidden');
}

$('btn-search-arrow').addEventListener('click', (e) => {
  e.stopPropagation();
  _searchDropdownOpen ? _closeSearchDropdown() : _openSearchDropdown();
});

// Dropdown item click
document.querySelectorAll('.search-dropdown-item').forEach(el => {
  el.addEventListener('click', (e) => {
    e.stopPropagation();
    _searchMode = el.dataset.mode;
    if (_searchMode === 'auto') _searchEnabled = true;
    window.pywebview.api.set_search_mode(_searchMode);
    window.pywebview.api.set_search_enabled(_searchEnabled);
    _closeSearchDropdown();
    _renderSearchBtn();
  });
});

// Close dropdown on outside click
document.addEventListener('click', (e) => {
  if (_searchDropdownOpen && !$('search-btn-wrap').contains(e.target)) {
    _closeSearchDropdown();
  }
});

// ── Export & Import ──────────────────────────────────────────────
$('btn-export').addEventListener('click', () => {
  if (state.currentConvId) window.pywebview.api.export_conversation(state.currentConvId);
});

$('btn-import').addEventListener('click', async () => {
  const result = await window.pywebview.api.import_conversation();
  if (result) {
    // 刷新对话列表并打开导入的对话
    state.conversations = await window.pywebview.api.list_conversations();
    renderConvList('');
    await openConversation(result.id);
  }
});

// ── Chat nav buttons ──────────────────────────────────────────────
function smoothScrollTo(targetScrollTop, duration = 320) {
  const area = $('chat-area');
  const start = area.scrollTop;
  const delta = targetScrollTop - start;
  if (Math.abs(delta) < 2) return;
  const startTime = performance.now();
  function step(now) {
    const t = Math.min((now - startTime) / duration, 1);
    const ease = t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t+2, 3) / 2;
    area.scrollTop = start + delta * ease;
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

$('btn-nav-bottom').addEventListener('click', () => {
  smoothScrollTo($('chat-area').scrollHeight);
});

$('btn-nav-prev').addEventListener('click', () => {
  const bubbles = Array.from(chatMessages.querySelectorAll('.bubble-user, .bubble-assistant'));
  if (!bubbles.length) return;
  const area = $('chat-area');
  const areaScrollTop = area.scrollTop;
  for (let i = bubbles.length - 1; i >= 0; i--) {
    const bubbleTop = bubbles[i].offsetTop - chatMessages.offsetTop;
    if (bubbleTop < areaScrollTop - 10) {
      smoothScrollTo(bubbleTop - 8);
      return;
    }
  }
});

$('btn-nav-next').addEventListener('click', () => {
  const bubbles = Array.from(chatMessages.querySelectorAll('.bubble-user, .bubble-assistant'));
  if (!bubbles.length) return;
  const area = $('chat-area');
  const areaScrollTop = area.scrollTop;
  for (let i = 0; i < bubbles.length; i++) {
    const bubbleTop = bubbles[i].offsetTop - chatMessages.offsetTop;
    if (bubbleTop > areaScrollTop + 10) {
      smoothScrollTo(bubbleTop - 8);
      return;
    }
  }
});
