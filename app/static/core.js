/* core.js — shared state, DOM refs, base helpers.
   必须最先加载：定义 $/state/DOM 引用，供后续 render/drag/dialogs/settings/app 的
   顶层事件绑定与函数使用。纯 <script> 全局作用域，无打包器/模块。 */
'use strict';

// ── State ─────────────────────────────────────────────────────────
let state = {
  config: {},
  conversations: [],
  currentConvId: null,
  running: false,
  attachedFiles: [],   // [{name, path, content}]
  dragSrcId: null,     // 拖拽中会话 id（id-based，重排序后仍稳定）
  selectedMcIdx: null,
  collapsedGroups: {},  // { [project_path]: true } 折叠状态
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
