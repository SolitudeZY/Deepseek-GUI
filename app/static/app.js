/* app.js — AI Desktop Assistant frontend */
'use strict';

// ── marked config ──────────────────────────────────────────────────
marked.setOptions({ breaks: true, gfm: true });

// Fix: only treat ~~text~~ (double tilde) as strikethrough, not single ~
// This prevents false positives like "~5%" ... "~10%" being rendered as <del>
marked.use({
  extensions: [{
    name: 'del',
    level: 'inline',
    start(src) { return src.indexOf('~~'); },
    tokenizer(src) {
      const match = src.match(/^~~(?!~)([\s\S]*?)~~(?!~)/);
      if (match) {
        return { type: 'del', raw: match[0], text: match[1], tokens: [] };
      }
    },
    renderer(token) {
      return `<del>${this.parser.parseInline(token.tokens)}</del>`;
    },
    childTokens: ['tokens'],
  }]
});

// Custom renderer: code blocks with highlight.js + copy button
const renderer = new marked.Renderer();
renderer.code = function(token) {
  // marked v9+ passes a token object; older versions pass (code, lang)
  const code = typeof token === 'object' ? (token.text || token.raw || '') : token;
  const lang = typeof token === 'object' ? (token.lang || '') : (arguments[1] || '');
  const language = (lang && hljs.getLanguage(lang)) ? lang : 'plaintext';
  let highlighted;
  try { highlighted = hljs.highlight(String(code), { language }).value; }
  catch { highlighted = hljs.highlightAuto(String(code)).value; }
  return `<div class="code-block-wrap">
    <div class="code-block-header">
      <span class="code-lang">${lang || ''}</span>
      <button class="btn-copy" onclick="copyCode(this)" data-code="${encodeURIComponent(code)}">复制</button>
    </div>
    <pre><code class="hljs language-${language}">${highlighted}</code></pre>
  </div>`;
};
marked.use({ renderer });

// ── KaTeX render helper ────────────────────────────────────────────
// Walks the rendered DOM and replaces $$...$$ / $...$ in text nodes only,
// skipping <pre>, <code>, and existing KaTeX output. This avoids mangling
// shell snippets like $(...), "$1", $w, etc. inside code blocks.
function renderLatexInDom(root) {
  const SKIP = new Set(['PRE', 'CODE', 'SCRIPT', 'STYLE']);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      let p = node.parentNode;
      while (p && p !== root) {
        if (p.nodeType === 1) {
          if (SKIP.has(p.tagName)) return NodeFilter.FILTER_REJECT;
          if (p.classList && (p.classList.contains('katex') || p.classList.contains('katex-display'))) {
            return NodeFilter.FILTER_REJECT;
          }
        }
        p = p.parentNode;
      }
      return (node.nodeValue && node.nodeValue.indexOf('$') !== -1)
        ? NodeFilter.FILTER_ACCEPT
        : NodeFilter.FILTER_REJECT;
    }
  });
  const targets = [];
  let n;
  while ((n = walker.nextNode())) targets.push(n);

  for (const textNode of targets) {
    const src = textNode.nodeValue;
    // Build a fragment of mixed text + rendered math.
    const frag = document.createDocumentFragment();
    let i = 0;
    let changed = false;
    while (i < src.length) {
      // Display math $$...$$
      if (src[i] === '$' && src[i + 1] === '$') {
        const end = src.indexOf('$$', i + 2);
        if (end !== -1) {
          const tex = src.slice(i + 2, end);
          let html;
          try { html = katex.renderToString(tex, { displayMode: true, throwOnError: false }); }
          catch { html = null; }
          if (html) {
            const span = document.createElement('span');
            span.innerHTML = html;
            frag.appendChild(span);
            i = end + 2;
            changed = true;
            continue;
          }
        }
      }
      // Inline math $...$ — single line, no nested $
      if (src[i] === '$') {
        let j = i + 1;
        while (j < src.length && src[j] !== '$' && src[j] !== '\n') j++;
        if (j < src.length && src[j] === '$' && j > i + 1) {
          const tex = src.slice(i + 1, j);
          // Skip if it looks like CJK prose, or if the inner text contains
          // characters that strongly suggest shell/code rather than math.
          const looksLikeMath = !/[\u4e00-\u9fff]/.test(tex) && !/[\s]{2,}/.test(tex);
          if (looksLikeMath) {
            let html;
            try { html = katex.renderToString(tex, { displayMode: false, throwOnError: false }); }
            catch { html = null; }
            if (html) {
              const span = document.createElement('span');
              span.innerHTML = html;
              frag.appendChild(span);
              i = j + 1;
              changed = true;
              continue;
            }
          }
        }
      }
      // Default: copy one character as plain text. Coalesce runs for speed.
      let k = i + 1;
      while (k < src.length && src[k] !== '$') k++;
      frag.appendChild(document.createTextNode(src.slice(i, k)));
      i = k;
    }
    if (changed) textNode.parentNode.replaceChild(frag, textNode);
  }
}

function renderMarkdown(text) {
  // Pre-process LaTeX delimiters: \[...\] → $$...$$, \(...\) → $...$.
  // Must NOT touch fenced code blocks or inline code spans, otherwise shell
  // snippets containing literal \( ... \) get rewritten before marked sees them.
  const placeholders = [];
  const stash = (m) => {
    placeholders.push(m);
    return `\u0000QM_CODE_${placeholders.length - 1}\u0000`;
  };
  // Order matters: fenced ``` first, then ~~~ fenced, then inline `...`.
  text = text.replace(/```[\s\S]*?```/g, stash);
  text = text.replace(/~~~[\s\S]*?~~~/g, stash);
  text = text.replace(/`[^`\n]*`/g, stash);

  text = text.replace(/\\\[\s*([\s\S]*?)\s*\\\]/g, (m, inner) =>
    /[\u4e00-\u9fff]/.test(inner) ? m : `$$${inner}$$`);
  text = text.replace(/\\\(\s*([\s\S]*?)\s*\\\)/g, (m, inner) =>
    /[\u4e00-\u9fff]/.test(inner) ? m : `$${inner}$`);

  // Stash math blocks to protect them from marked's backslash escaping.
  // Use a separate placeholder prefix so we can restore them WITH $ delimiters.
  const mathPlaceholders = [];
  const stashMath = (m) => {
    mathPlaceholders.push(m);
    return `\u0000QM_MATH_${mathPlaceholders.length - 1}\u0000`;
  };
  text = text.replace(/\$\$([\s\S]*?)\$\$/g, stashMath);
  text = text.replace(/\$([^\$\n]+?)\$/g, stashMath);

  // Restore code spans/blocks.
  text = text.replace(/\u0000QM_CODE_(\d+)\u0000/g, (_, idx) => placeholders[+idx]);

  const html = marked.parse(text);

  // Restore math placeholders (with original $ delimiters intact) after marked.
  let finalHtml = html.replace(/\u0000QM_MATH_(\d+)\u0000/g, (_, idx) => mathPlaceholders[+idx]);

  // Render math against a detached container so we can walk the DOM safely.
  const container = document.createElement('div');
  container.innerHTML = finalHtml;
  renderLatexInDom(container);
  return container.innerHTML;
}

function copyCode(btn) {
  const code = decodeURIComponent(btn.dataset.code);
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = '已复制';
    setTimeout(() => btn.textContent = '复制', 1500);
  });
}

// ── State ─────────────────────────────────────────────────────────
let state = {
  config: {},
  conversations: [],
  currentConvId: null,
  running: false,
  attachedFiles: [],   // [{name, path, content}]
  dragSrcIdx: null,
  selectedMcIdx: null,
};

// ── DOM refs ──────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const convList      = $('conv-list');
const chatMessages  = $('chat-messages');
const msgInput      = $('msg-input');
const btnSend       = $('btn-send');
const btnStop       = $('btn-stop');
const modelSelect   = $('model-select');
const convTitle     = $('conv-title');
const fileChips     = $('file-chips');
const searchInput   = $('search-input');

// ── Random accent colors for conversation border ─────────────────
const _convColors = [
  '#7aa2f7', '#bb9af7', '#7dcfff', '#9ece6a', '#e0af68',
  '#f7768e', '#ff9e64', '#73daca', '#b4f9f8', '#c0caf5',
  '#2ac3de', '#a9b1d6', '#ff007c', '#d18616', '#41a6b5',
];
function _randomConvColor() {
  return _convColors[Math.floor(Math.random() * _convColors.length)];
}

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
function renderConvList(filter = '') {
  convList.innerHTML = '';
  const kw = filter.toLowerCase();
  state.conversations.forEach((conv, idx) => {
    if (kw && !conv.title.toLowerCase().includes(kw)) return;
    const li = document.createElement('li');
    li.dataset.id = conv.id;
    li.dataset.idx = idx;
    if (conv.id === state.currentConvId) {
      li.classList.add('active');
      li.style.borderLeftColor = _randomConvColor();
      li.style.boxShadow = `inset 4px 0 0 ${li.style.borderLeftColor}, 0 0 12px ${li.style.borderLeftColor}33`;
    }

    const titleSpan = document.createElement('span');
    titleSpan.textContent = conv.title;
    titleSpan.style.flex = '1';
    li.appendChild(titleSpan);

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

    li.addEventListener('click', () => openConversation(conv.id));

    // Drag sort
    li.draggable = true;
    li.addEventListener('dragstart', e => { state.dragSrcIdx = idx; e.dataTransfer.effectAllowed = 'move'; });
    li.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; });
    li.addEventListener('drop', e => {
      e.preventDefault();
      if (state.dragSrcIdx === null || state.dragSrcIdx === idx) return;
      const moved = state.conversations.splice(state.dragSrcIdx, 1)[0];
      state.conversations.splice(idx, 0, moved);
      state.dragSrcIdx = null;
      renderConvList(searchInput.value);
      window.pywebview.api.reorder_conversations(state.conversations.map(c => c.id));
    });

    convList.appendChild(li);
  });
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
  state.currentConvId = convId;
  convTitle.textContent = conv.title;
  const kw = searchInput.value.trim();
  renderConvList(kw);
  // Re-apply content search results so the list doesn't disappear
  if (kw) _runContentSearch(kw);
  loadHistory(conv.messages || []);
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

async function newConversation() {
  const conv = await window.pywebview.api.new_conversation();
  state.conversations.unshift({ id: conv.id, title: conv.title });
  state.currentConvId = conv.id;
  convTitle.textContent = conv.title;
  renderConvList(searchInput.value);
  chatMessages.innerHTML = '';
  updateContextBar(0, 80000);
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

// ── Rename dialog ─────────────────────────────────────────────────
let _renameConvId = null;
function showRenameDialog(convId, currentTitle) {
  _renameConvId = convId;
  $('rename-input').value = currentTitle;
  $('rename-overlay').classList.remove('hidden');
  $('rename-input').focus();
  $('rename-input').select();
}
$('btn-rename-cancel').addEventListener('click', () => $('rename-overlay').classList.add('hidden'));
$('btn-rename-ok').addEventListener('click', doRename);
$('rename-input').addEventListener('keydown', e => { if (e.key === 'Enter') doRename(); });
async function doRename() {
  const newTitle = $('rename-input').value.trim();
  if (!newTitle || !_renameConvId) { $('rename-overlay').classList.add('hidden'); return; }
  await window.pywebview.api.rename_conversation(_renameConvId, newTitle);
  const conv = state.conversations.find(c => c.id === _renameConvId);
  if (conv) conv.title = newTitle;
  if (_renameConvId === state.currentConvId) convTitle.textContent = newTitle;
  renderConvList(searchInput.value);
  $('rename-overlay').classList.add('hidden');
}

// ── History rendering ─────────────────────────────────────────────
function loadHistory(messages) {
  chatMessages.classList.add('no-animate');
  chatMessages.innerHTML = '';
  messages.forEach(msg => {
    const role = msg.role;
    const content = msg.content || '';
    if (role === 'user') addUserBubble(content);
    else if (role === 'assistant' && content) addAssistantBubble(content);
    else if (role === 'tool') addToolResultBubble('tool', content);
  });
  scrollToBottom();
  // Re-enable animations after history is rendered
  requestAnimationFrame(() => chatMessages.classList.remove('no-animate'));
}

function addUserBubble(text) {
  const div = document.createElement('div');
  div.className = 'bubble bubble-user';
  const collapsible = document.createElement('div');
  collapsible.className = 'bubble-collapsible';
  collapsible.innerHTML = `<div class="bubble-label">You</div><div class="bubble-content">${buildUserContent(text)}</div>`;
  div.appendChild(collapsible);
  chatMessages.appendChild(div);
  // Load image thumbnails async
  collapsible.querySelectorAll('img.chat-img-thumb[data-filename]').forEach(async img => {
    const dataUrl = await window.pywebview.api.get_image_data(img.dataset.filename);
    if (dataUrl) img.src = dataUrl;
  });
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
  // Parts are joined by \n\n in Python; each image block is "[图片: name]\ndescription"
  // Split by double newline, render image blocks as thumbnails (hide verbose description)
  return text.split(/\n\n/).map(seg => {
    const m = seg.match(/^\[图片: ([^\]]+)\]([\s\S]*)$/);
    if (m) {
      const fname = m[1];
      return `<img class="chat-img-thumb" data-filename="${escapeHtml(fname)}" src="" alt="${escapeHtml(fname)}" onclick="openLightbox(this.src)">`;
    }
    return escapeHtml(seg).replace(/\n/g, '<br>');
  }).join('<br>');
}

function addAssistantBubble(content) {
  const div = document.createElement('div');
  div.className = 'bubble bubble-assistant';
  div.innerHTML = `<div class="bubble-label">Assistant</div><div class="bubble-content">${renderMarkdown(content)}</div>`;
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
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
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

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
      li.innerHTML = `<span class="fileops-icon">${icon}</span><span class="fileops-name" title="${escapeHtml(op.path)}">${escapeHtml(fname)}</span>`;
      li.addEventListener('click', () => {
        window.pywebview.api.open_file_location(op.path);
      });
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

// ── Confirm dialog ────────────────────────────────────────────────
let _confirmCommand = '';
let _confirmWildcard = '';
let _countdownTimer = null;
let _countdownSeconds = 0;

function _clearCountdown() {
  if (_countdownTimer) { clearInterval(_countdownTimer); _countdownTimer = null; }
  $('confirm-countdown-wrap').classList.add('hidden');
  $('confirm-countdown-fill').style.width = '100%';
}

function _startCountdown() {
  _countdownSeconds = 5;
  $('confirm-countdown-wrap').classList.remove('hidden');
  $('confirm-countdown-text').textContent = `${_countdownSeconds} 秒后自动执行`;
  $('confirm-countdown-fill').style.transition = 'none';
  $('confirm-countdown-fill').style.width = '100%';
  // Force reflow then animate
  void $('confirm-countdown-fill').offsetWidth;
  $('confirm-countdown-fill').style.transition = 'width 1s linear';

  _countdownTimer = setInterval(() => {
    _countdownSeconds--;
    const pct = (_countdownSeconds / 5) * 100;
    $('confirm-countdown-fill').style.width = pct + '%';
    $('confirm-countdown-text').textContent = `${_countdownSeconds} 秒后自动执行`;
    if (_countdownSeconds <= 0) {
      _clearCountdown();
      $('confirm-overlay').classList.add('hidden');
      window.pywebview.api.confirm_tool(true);
    }
  }, 1000);
}

$('btn-confirm-yes').addEventListener('click', () => {
  _clearCountdown();
  $('confirm-overlay').classList.add('hidden');
  window.pywebview.api.confirm_tool(true);
});
$('btn-confirm-no').addEventListener('click', () => {
  _clearCountdown();
  $('confirm-overlay').classList.add('hidden');
  window.pywebview.api.confirm_tool(false);
});
$('btn-confirm-always').addEventListener('click', () => {
  _clearCountdown();
  $('confirm-overlay').classList.add('hidden');
  window.pywebview.api.confirm_tool_always(_confirmCommand);
});
$('btn-confirm-auto').addEventListener('click', () => {
  // Switch to auto_countdown mode and start countdown for current dialog
  state.config.command_safety = 'auto_countdown';
  window.pywebview.api.save_config(state.config);
  $('btn-confirm-auto').style.display = 'none';
  _startCountdown();
});
$('btn-confirm-wildcard').addEventListener('click', () => {
  _clearCountdown();
  $('confirm-overlay').classList.add('hidden');
  window.pywebview.api.confirm_tool_always(_confirmWildcard);
});
// Keyboard shortcuts: Enter = allow, Shift+Enter = always allow (wildcard if available, else exact)
document.addEventListener('keydown', e => {
  if ($('confirm-overlay').classList.contains('hidden')) return;
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    _clearCountdown();
    $('confirm-overlay').classList.add('hidden');
    window.pywebview.api.confirm_tool(true);
  } else if (e.key === 'Enter' && e.shiftKey) {
    e.preventDefault();
    _clearCountdown();
    $('confirm-overlay').classList.add('hidden');
    if (_confirmWildcard && !$('btn-confirm-wildcard').classList.contains('hidden')) {
      window.pywebview.api.confirm_tool_always(_confirmWildcard);
    } else {
      window.pywebview.api.confirm_tool_always(_confirmCommand);
    }
  } else if (e.key === 'Escape') {
    e.preventDefault();
    _clearCountdown();
    $('confirm-overlay').classList.add('hidden');
    window.pywebview.api.confirm_tool(false);
  }
});

// ── Ask user question dialog ─────────────────────────────────────
let _askSelectedIdx = -1;
let _askOptions = [];
let _askMultiSelect = false;
let _askSelected = new Set();

function showAskDialog(question, options, multiSelect) {
  _askOptions = options || [];
  _askMultiSelect = !!multiSelect;
  _askSelectedIdx = _askOptions.length > 0 ? 0 : -1;
  _askSelected = new Set();
  $('ask-question').textContent = question || '(AI 需要你的输入才能继续)';
  $('ask-hint').textContent = _askOptions.length > 0
    ? `↑↓ 选择 · Enter ${_askMultiSelect ? '切换选中' : '确认'} · ${_askMultiSelect ? 'Tab 提交 · ' : ''}下方可自由输入`
    : '';
  _renderAskOptions();
  $('ask-input').value = '';
  $('ask-input').style.display = '';
  $('ask-overlay').classList.remove('hidden');
  if (_askOptions.length > 0) {
    $('ask-options').focus();
  } else {
    $('ask-input').focus();
  }
}

function _renderAskOptions() {
  const ul = $('ask-options');
  ul.innerHTML = '';
  if (_askOptions.length === 0) { ul.style.display = 'none'; return; }
  ul.style.display = '';
  _askOptions.forEach((opt, i) => {
    const li = document.createElement('li');
    li.textContent = (_askMultiSelect ? (_askSelected.has(i) ? '☑ ' : '☐ ') : '') + opt;
    if (i === _askSelectedIdx) li.classList.add('ask-active');
    if (_askSelected.has(i)) li.classList.add('ask-checked');
    li.addEventListener('click', () => {
      _askSelectedIdx = i;
      if (_askMultiSelect) {
        _askSelected.has(i) ? _askSelected.delete(i) : _askSelected.add(i);
      }
      _renderAskOptions();
      if (!_askMultiSelect) _submitAskAnswer();
    });
    ul.appendChild(li);
  });
}

function _submitAskAnswer() {
  // Free-text input takes priority — if user typed something, use that
  const freeText = $('ask-input').value.trim();
  let answer = '';
  if (freeText) {
    answer = freeText;
  } else if (_askOptions.length > 0) {
    if (_askMultiSelect) {
      answer = [..._askSelected].map(i => _askOptions[i]).join(', ');
    } else {
      answer = _askSelectedIdx >= 0 ? _askOptions[_askSelectedIdx] : '';
    }
  }
  if (!answer) answer = '(无回答)';
  $('ask-overlay').classList.add('hidden');
  window.pywebview.api.answer_question(answer);
}

$('btn-ask-submit').addEventListener('click', _submitAskAnswer);

document.addEventListener('keydown', e => {
  if ($('ask-overlay').classList.contains('hidden')) return;
  // Enter in the free-input box always submits (regardless of whether options exist)
  if (e.key === 'Enter' && e.target === $('ask-input')) {
    e.preventDefault();
    _submitAskAnswer();
    return;
  }
  if (_askOptions.length === 0) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _askSelectedIdx = Math.min(_askSelectedIdx + 1, _askOptions.length - 1);
    _renderAskOptions();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _askSelectedIdx = Math.max(_askSelectedIdx - 1, 0);
    _renderAskOptions();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (_askMultiSelect) {
      if (_askSelectedIdx >= 0) {
        _askSelected.has(_askSelectedIdx) ? _askSelected.delete(_askSelectedIdx) : _askSelected.add(_askSelectedIdx);
        _renderAskOptions();
      }
    } else {
      _submitAskAnswer();
    }
  } else if (e.key === 'Tab' && _askMultiSelect) {
    e.preventDefault();
    _submitAskAnswer();
  } else if (e.key === 'Escape') {
    e.preventDefault();
    $('ask-overlay').classList.add('hidden');
    window.pywebview.api.answer_question('(用户取消)');
  }
});

// ── Plan approval dialog ─────────────────────────────────────────
function showPlanApproval(summary) {
  $('plan-summary').textContent = summary || '(模型已在上方输出计划内容，请查看后决定是否批准执行)';
  $('plan-overlay').classList.remove('hidden');
}
$('btn-plan-approve').addEventListener('click', () => {
  $('plan-overlay').classList.add('hidden');
  window.pywebview.api.approve_plan(true);
});
$('btn-plan-reject').addEventListener('click', () => {
  $('plan-overlay').classList.add('hidden');
  window.pywebview.api.approve_plan(false);
});

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
  addUserBubble(text || '[附件]');
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
document.addEventListener('dragover', e => { e.preventDefault(); document.body.classList.add('drag-over'); });
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

async function openSettings() {
  const cfg = state.config;
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
  $('ui-theme').value = cfg.theme || 'dark';
  $('ui-fontsize').value = String(cfg.font_size || 14);
  // Sync tab
  $('sync-folder').value = cfg.sync_folder || '';
  $('sync-auto-upload').checked = cfg.sync_auto_upload !== false;
  $('sync-list').innerHTML = '';
  $('sync-import-actions').style.display = 'none';
  $('sync-status').textContent = cfg.sync_folder ? '' : '未配置同步文件夹';
  // Update tab
  $('github-token').value = cfg.github_token || '';
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
  configs.push({ name: `新配置 ${configs.length + 1}`, api_key: '', base_url: '', model: '', system_prompt: 'You are a helpful assistant.', context_length: 1000000, compact_threshold: 600000 });
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

// ── Utilities ─────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function scrollToBottom() {
  const area = $('chat-area');
  const threshold = 80;
  const distFromBottom = area.scrollHeight - area.scrollTop - area.clientHeight;
  if (distFromBottom <= threshold) {
    area.scrollTop = area.scrollHeight;
  }
}

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

// ── Image lightbox ────────────────────────────────────────────────
function openLightbox(src) {
  if (!src) return;
  $('lightbox-img').src = src;
  $('lightbox-overlay').classList.remove('hidden');
}
function closeLightbox() {
  $('lightbox-overlay').classList.add('hidden');
  $('lightbox-img').src = '';
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeLightbox();
});
$('lightbox-img').addEventListener('click', e => e.stopPropagation());
