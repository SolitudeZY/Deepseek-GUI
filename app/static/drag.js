/* drag.js — 侧边栏会话手动拖拽引擎（鼠标事件，不依赖 HTML5 原生拖放）。
   依赖 core.js 的 state/$/convList/searchInput，及 app.js 的 renderConvList
   （运行时调用，安全）。被 app.js 的 _makeConvLi 在 mousedown 时调用 _beginDragCandidate。 */
'use strict';

// ── 手动拖拽引擎（鼠标事件，不依赖原生 HTML5 拖放）─────────────────
const _drag = {
  active: false,      // 是否已越过阈值进入拖拽
  srcId: null,        // 被拖会话 id
  srcLi: null,        // 被拖会话原 DOM
  startX: 0, startY: 0,
  ghost: null,        // 跟随鼠标的浮动元素
  offX: 0, offY: 0,   // 鼠标在 ghost 内的偏移
  drop: null,         // 当前落点 {targetId, before} 或 {headerGroup}
  justDragged: false, // 供 click 处理判断是否抑制
};
const _DRAG_THRESHOLD = 4;  // px，超过才算拖拽（区分点击）

// 常驻拦截：拖拽候选/进行中时，一律阻止 WebView2 启动任何原生拖放（文本选区/元素），
// 否则原生 drag 抢占后 mousemove 停发，手动引擎失效（表现为禁止光标+原生拖影、无幽灵块）。
document.addEventListener('dragstart', e => {
  if (_drag.srcId) e.preventDefault();
}, true);

let _dragPlaceholder = null;
function _getPlaceholder() {
  if (!_dragPlaceholder) {
    _dragPlaceholder = document.createElement('li');
    _dragPlaceholder.className = 'conv-placeholder';
  }
  const src = _convById(_drag.srcId);
  _dragPlaceholder.textContent = src ? src.title : '';
  return _dragPlaceholder;
}

// mousedown：记录候选，等待移动越过阈值
function _beginDragCandidate(convId, li, e) {
  _drag.justDragged = false;  // 复位，避免上次拖拽残留误抑制本次点击
  _drag.srcId = convId;
  _drag.srcLi = li;
  _drag.startX = e.clientX;
  _drag.startY = e.clientY;
  _drag.active = false;
  document.addEventListener('mousemove', _onDragMove);
  document.addEventListener('mouseup', _onDragUp);
}

function _activateDrag(e) {
  _drag.active = true;
  state.dragSrcId = _drag.srcId;
  _drag.srcLi.classList.add('dragging');
  document.body.classList.add('conv-dragging');  // 全局禁选中
  // 创建跟随鼠标的浮动幽灵
  const r = _drag.srcLi.getBoundingClientRect();
  const ghost = document.createElement('div');
  ghost.className = 'conv-drag-ghost';
  ghost.textContent = _drag.srcLi.textContent.replace(/[✏🗑]/g, '').trim();
  ghost.style.width = r.width + 'px';
  document.body.appendChild(ghost);
  _drag.ghost = ghost;
  _drag.offX = e.clientX - r.left;
  _drag.offY = e.clientY - r.top;
}

function _onDragMove(e) {
  if (!_drag.srcId) return;
  if (!_drag.active) {
    if (Math.abs(e.clientX - _drag.startX) < _DRAG_THRESHOLD &&
        Math.abs(e.clientY - _drag.startY) < _DRAG_THRESHOLD) return;
    _activateDrag(e);
  }
  e.preventDefault();
  // 移动浮动幽灵
  _drag.ghost.style.left = (e.clientX - _drag.offX) + 'px';
  _drag.ghost.style.top  = (e.clientY - _drag.offY) + 'px';
  _updateDropTarget(e.clientX, e.clientY);
}

// 根据鼠标位置决定落点并插入占位块（挤开其他会话）
function _updateDropTarget(x, y) {
  // 命中点下方的元素（ghost 设了 pointer-events:none 不会挡）
  const el = document.elementFromPoint(x, y);
  if (!el) return;
  const header = el.closest('.conv-group-header');
  if (header) {
    const path = header._groupKey || '';
    _drag.drop = { headerGroup: path };
    convList.querySelectorAll('.cg-drop-target').forEach(h => h.classList.remove('cg-drop-target'));
    header.classList.add('cg-drop-target');
    if (_dragPlaceholder && _dragPlaceholder.parentNode) _dragPlaceholder.remove();
    return;
  }
  const li = el.closest('#conv-list li:not(.conv-placeholder)');
  if (li && li.dataset.id && li.dataset.id !== _drag.srcId) {
    const r = li.getBoundingClientRect();
    const before = (y - r.top) < r.height / 2;
    _drag.drop = { targetId: li.dataset.id, before };
    _showPlaceholderAt(li, before);
  }
}

// 把占位块插到 li 之前/之后
function _showPlaceholderAt(li, before) {
  convList.querySelectorAll('.cg-drop-target')
    .forEach(el => el.classList.remove('cg-drop-target'));
  const ph = _getPlaceholder();
  const ref = before ? li : li.nextSibling;
  if (ref === ph) return;
  if (li.nextSibling === ph && !before) return;
  li.parentNode.insertBefore(ph, ref);
}

function _onDragUp() {
  document.removeEventListener('mousemove', _onDragMove);
  document.removeEventListener('mouseup', _onDragUp);
  const wasActive = _drag.active;
  const drop = _drag.drop;
  // 复位拖拽态
  if (_drag.srcLi) _drag.srcLi.classList.remove('dragging');
  if (_drag.ghost) _drag.ghost.remove();
  document.body.classList.remove('conv-dragging');
  _clearDropIndicators();
  _drag.active = false; _drag.ghost = null; _drag.drop = null;
  _drag.srcId = null; _drag.srcLi = null;

  if (!wasActive) { state.dragSrcId = null; return; }  // 未越阈值=普通点击，交给 click
  _drag.justDragged = true;  // 抑制随后的 click
  if (drop && drop.headerGroup !== undefined) {
    _handleHeaderDrop(drop.headerGroup);
  } else if (drop && drop.targetId) {
    _handleConvDrop(drop.targetId, drop.before);
  } else {
    state.dragSrcId = null;
  }
}

// 清除占位块与组标题高亮
function _clearDropIndicators() {
  if (_dragPlaceholder && _dragPlaceholder.parentNode) _dragPlaceholder.remove();
  convList.querySelectorAll('.cg-drop-target')
    .forEach(el => el.classList.remove('cg-drop-target'));
}

const _convById = id => state.conversations.find(c => c.id === id);

// 当前分组顺序（按 state.conversations 首次出现）
function _groupOrder() {
  const order = [], seen = new Set();
  state.conversations.forEach(c => {
    const k = c.project_path || '';
    if (!seen.has(k)) { seen.add(k); order.push(k); }
  });
  return order;
}

// 重排 state.conversations 为「按 groupOrder 连续分组」，组内保持相对顺序。
// 保证持久化的 sort_order 也是分组连续的，下次启动 list_conversations 按 sort_order
// 升序读取时分组顺序不被打乱（根治旧版「整组沉底」bug）。
function _regroupContiguous(groupOrder) {
  const buckets = new Map();
  groupOrder.forEach(k => buckets.set(k, []));
  state.conversations.forEach(c => {
    const k = c.project_path || '';
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(c);
  });
  const flat = [];
  for (const arr of buckets.values()) flat.push(...arr);
  state.conversations = flat;
}

// 拖到某会话前/后：跨组则改 project_path 归入目标组，再在组内定位
async function _handleConvDrop(targetId, before) {
  const srcId = state.dragSrcId;
  state.dragSrcId = null;
  if (!srcId || srcId === targetId) return;
  const src = _convById(srcId), tgt = _convById(targetId);
  if (!src || !tgt) return;
  const targetGroup = tgt.project_path || '';
  const groupOrder = _groupOrder();  // 改 project_path 前捕获组顺序

  if ((src.project_path || '') !== targetGroup) {
    src.project_path = targetGroup;
    // 先 await 改组（整文件 load→改→save），再 reorder，避免字段互相覆盖
    await window.pywebview.api.move_conversation_to_project(srcId, targetGroup);
  }
  state.conversations.splice(state.conversations.indexOf(src), 1);
  const ti = state.conversations.indexOf(tgt);
  state.conversations.splice(before ? ti : ti + 1, 0, src);
  _regroupContiguous(groupOrder);
  renderConvList(searchInput.value);
  await window.pywebview.api.reorder_conversations(state.conversations.map(c => c.id));
}

// 拖到分组标题：归入该组并落到组末尾（折叠的组也可作为投放目标）
async function _handleHeaderDrop(groupKey) {
  const srcId = state.dragSrcId;
  state.dragSrcId = null;
  if (!srcId) return;
  const src = _convById(srcId);
  if (!src) return;
  const groupOrder = _groupOrder();
  if ((src.project_path || '') !== groupKey) {
    src.project_path = groupKey;
    await window.pywebview.api.move_conversation_to_project(srcId, groupKey);
  }
  state.conversations.splice(state.conversations.indexOf(src), 1);
  state.conversations.push(src);  // 移到末尾，regroup 后即为该组组内末位
  _regroupContiguous(groupOrder);
  renderConvList(searchInput.value);
  await window.pywebview.api.reorder_conversations(state.conversations.map(c => c.id));
}
