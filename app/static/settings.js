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

async function _downloadAsset(url, filename) {
  if (!confirm(`下载 ${filename}？\n\n下载完成后将自动替换当前版本并重启应用。`)) return;
  $('update-status').textContent = `正在下载 ${filename}...`;
  const result = await window.pywebview.api.download_update(url, filename);
  if (result.error) {
    $('update-status').textContent = `下载失败: ${result.error}`;
    return;
  }
  $('update-status').textContent = '下载完成，正在应用更新...';
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
  });
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
  state.config.sync_auto_upload = $('sync-auto-upload').checked;
  state.config.github_token = $('github-token').value.trim();
  applyTheme(state.config.theme);
  applyFontSize(state.config.font_size);
  await window.pywebview.api.save_config(state.config);
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
  $('sync-status').textContent = `已上传 ${result.conversations_uploaded} 个对话${cfgList}`;
});

// 一键导入全部（对话+配置）
$('btn-sync-import-all').addEventListener('click', async () => {
  $('sync-status').textContent = '正在一键导入...';
  const result = await window.pywebview.api.sync_import_all();
  const cfgList = result.config_imported.length ? `，配置: ${result.config_imported.join(', ')}` : '';
  $('sync-status').textContent = `导入 ${result.conversations_imported} 个对话${cfgList}`;
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

