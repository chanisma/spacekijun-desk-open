'use strict';
// 메모 창 하나 = 메모 하나. 데스크가 창을 띄운 뒤 deskSticky.open(id, onTop)을 부른다.
const COLORS = [['#fff176','노랑'],['#f48fb1','분홍'],['#90caf9','파랑'],['#a5d6a7','초록'],['#ce93d8','보라'],['#ffcc80','주황'],['#ffffff','흰색']];
const SAVE_DELAY = 700;      // 입력을 멈추고 이만큼 지나면 저장 (ms)
// 웹에서 고친 내용을 받아 오는 간격 (ms). 메모 창은 바탕화면에 늘 떠 있어 document.hidden 으로는
// 멈추지 않는다 — 20초 고정이면 메모 한 장이 하루 4,320번 서버에 묻는다(2026-10-18 로그: 3장 10,862건/일).
// 그래서 만지는 메모만 자주, 나머지는 드물게, 자리를 비우면 묻지 않는다. 만지는 순간에는 곧바로 받는다.
const SYNC_ACTIVE = 20000;     // 최근 ACTIVE_FOR 안에 만진 메모
const SYNC_RESTING = 300000;   // 그 밖 — 웹에서 고친 것이 늦어도 5분 안에 들어온다
const ACTIVE_FOR = 120000;
const SYNC_TOUCH_GAP = 5000;   // 만질 때 받는 것도 이만큼은 띄운다 (마우스가 드나들 때마다 묻지 않게)
const $ = id => document.getElementById(id);
let noteId = null, note = null, saveTimer = null, saving = false, dirty = false, onTop = false;
let lastTouched = 0, lastSync = 0;

async function api(action, payload={}) {
  const result = await window.pywebview.api.call(action, payload);
  if (!result.ok) throw new Error(result.error || '작업을 완료하지 못했습니다.');
  return result.data;
}
function status(text, error=false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
}
function savedLabel(iso) {
  const when = iso ? new Date(iso) : new Date();
  return '저장됨 · ' + when.toLocaleTimeString('ko-KR', {hour:'numeric', minute:'2-digit'});
}
function darker(hex) {
  const n = parseInt(hex.slice(1), 16), k = hex.toLowerCase() === '#ffffff' ? 0.94 : 0.92;
  return '#' + [n >> 16, (n >> 8) & 255, n & 255].map(c => Math.round(c * k).toString(16).padStart(2, '0')).join('');
}
function paint(color) {
  document.documentElement.style.setProperty('--note', color);
  document.documentElement.style.setProperty('--bar', darker(color));
  document.querySelectorAll('.swatch').forEach(el => el.setAttribute('aria-pressed', String(el.dataset.color === color)));
}
function show(row) {
  note = row;
  paint(COLORS.some(([c]) => c === row.color) ? row.color : COLORS[0][0]);
  if (!dirty) $('content').value = row.content || '';
  if (!editing()) renderView();
  document.title = row.title || '메모';
  status(savedLabel(row.updated_at));
}

// ── 보기와 고치기 ─────────────────────────────────────────
// 고칠 때는 글자 그대로(textarea), 다 쓰고 나면 서식을 입혀 보인다 — # 제목은 크게, - 는 목록,
// 웹 주소는 누르면 열리는 링크 (2026-10-11 요청). textarea 는 줄마다 글자 크기를 달리할 수 없어서
// 두 겹으로 둔다. 보기를 누르면 누른 글자 자리에서 고치기로 바뀐다.
const URL_RE = /\b(?:https?:\/\/|www\.)[^\s<>"']+/gi;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const editing = () => !$('content').hidden;

function linkify(text) {
  let html = '', last = 0;
  for (const match of text.matchAll(URL_RE)) {
    const url = match[0].replace(/[)\].,;:!?'"]+$/, '');       // 문장 끝 문장부호는 주소가 아니다
    html += esc(text.slice(last, match.index)) + `<a data-url="${esc(url)}" title="${esc(url)} — 브라우저로 열기">${esc(url)}</a>`;
    last = match.index + url.length;
  }
  return html + esc(text.slice(last));
}

function renderView() {
  let offset = 0;
  $('view').innerHTML = $('content').value.split('\n').map(line => {
    const start = offset;
    offset += line.length + 1;
    const heading = /^(#{1,3})\s+/.exec(line);
    const bullet = !heading && /^\s*[-*•]\s+/.exec(line);
    const prefix = heading ? heading[0].length : bullet ? bullet[0].length : 0;
    const kind = heading ? `h${heading[1].length}` : bullet ? 'li' : 'p';
    const body = line.slice(prefix);
    // data-start·data-prefix: 누른 글자를 원래 글의 몇 번째 글자인지 되짚는 데 쓴다
    return `<div class="ln ${kind}" data-start="${start}" data-prefix="${prefix}">${body ? linkify(body) : '<br>'}</div>`;
  }).join('');
}

function toView() {
  if (!$('content').value.trim()) return;      // 빈 메모는 바로 쓸 수 있게 고치기로 둔다
  renderView();
  $('content').hidden = true;
  $('view').hidden = false;
}

function toEdit(position) {
  const area = $('content');
  $('view').hidden = true;
  area.hidden = false;
  area.focus();
  const at = Math.min(Math.max(position ?? area.value.length, 0), area.value.length);
  area.setSelectionRange(at, at);
}

/** 보기에서 누른 점 → 원래 글의 글자 위치 */
function positionAt(x, y) {
  const range = document.caretRangeFromPoint?.(x, y);
  const node = range?.startContainer;
  const line = (node?.nodeType === 3 ? node.parentElement : node)?.closest?.('.ln');
  if (!line) return undefined;
  let inside = 0;
  if (node.nodeType === 3) {
    const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
    for (let text = walker.nextNode(); text && text !== node; text = walker.nextNode()) inside += text.length;
    inside += range.startOffset;
  }
  return Number(line.dataset.start) + Number(line.dataset.prefix) + inside;
}

$('view').addEventListener('mousedown', event => {
  if (event.button !== 0 || event.target.closest('a')) return;
  event.preventDefault();
  toEdit(positionAt(event.clientX, event.clientY));
});
$('view').addEventListener('click', event => {
  const link = event.target.closest('a[data-url]');
  if (!link) return;
  event.preventDefault();
  api('open_link', {url: link.dataset.url}).catch(error => status(error.message, true));
});
$('view').addEventListener('keydown', event => {
  if (event.key === 'Enter' || event.key.length === 1) {event.preventDefault(); toEdit();}
});

async function save() {
  clearTimeout(saveTimer);
  if (!dirty || saving || !noteId) return;
  saving = true; dirty = false;
  const content = $('content').value;
  status('저장 중…');
  try {
    const row = await api('sticky_update', {id: noteId, content});
    note = row;
    document.title = row.title || '메모';
    status(dirty ? '저장 중…' : savedLabel(row.updated_at));
  } catch (error) {
    dirty = true;
    status(error.message, true);
  } finally {
    saving = false;
    if (dirty) saveTimer = setTimeout(save, SAVE_DELAY);
  }
}
async function sync(force=false) {
  if (!noteId || dirty || saving || document.hidden) return;
  const now = Date.now(), recent = now - lastTouched < ACTIVE_FOR;
  if (now - lastSync < (force ? SYNC_TOUCH_GAP : recent ? SYNC_ACTIVE : SYNC_RESTING)) return;
  if (!force && !recent) {
    try {if (await api('away')) return;} catch {/* 모르면 종전처럼 받는다 */}
  }
  lastSync = now;
  try {
    const row = await api('sticky_get', {id: noteId});
    if (!dirty && row.updated_at !== note?.updated_at) show(row);
  } catch (error) {
    status(error.message, true);
  }
}

$('content').addEventListener('input', () => {
  dirty = true;
  status('입력 중…');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, SAVE_DELAY);
});
$('content').addEventListener('blur', () => {save(); toView();});
window.addEventListener('beforeunload', save);

$('new-note').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {await save(); await api('sticky_create', {color: note?.color || COLORS[0][0]});}
  catch (error) {status(error.message, true);}
  finally {button.disabled = false;}
});
document.addEventListener('keydown', event => {
  if (event.ctrlKey && event.key.toLowerCase() === 'n') {event.preventDefault(); $('new-note').click();}
  if (event.ctrlKey && event.key.toLowerCase() === 's') {event.preventDefault(); save();}
  if (event.key === 'Escape' && !$('menu').hidden) toggleMenu(false);
});

function toggleMenu(open) {
  $('menu').hidden = !open;
  $('menu-toggle').setAttribute('aria-expanded', String(open));
}
$('menu-toggle').addEventListener('click', () => toggleMenu($('menu').hidden));
document.addEventListener('click', event => {
  if (!$('menu').hidden && !event.target.closest('#menu, #menu-toggle')) toggleMenu(false);
});
$('colors').innerHTML = COLORS.map(([color, label]) => `<button class="swatch" data-color="${color}" title="${label}" aria-label="${label}" aria-pressed="false"></button>`).join('');
document.querySelectorAll('.swatch').forEach(el => {el.style.background = el.dataset.color;});
$('colors').addEventListener('click', async event => {
  const swatch = event.target.closest('.swatch');
  if (!swatch || !noteId) return;
  const before = note?.color;
  paint(swatch.dataset.color);
  try {note = await api('sticky_update', {id: noteId, color: swatch.dataset.color}); status(savedLabel(note.updated_at));}
  catch (error) {paint(before || COLORS[0][0]); status(error.message, true);}
});
$('pin').addEventListener('click', async () => {
  try {
    await api('sticky_pin', {id: noteId, on_top: !onTop});
    onTop = !onTop;
    $('pin').setAttribute('aria-pressed', String(onTop));
  } catch (error) {status(error.message, true);}
});
$('show-list').addEventListener('click', async () => {
  toggleMenu(false);
  try {await save(); await api('show_notes');}
  catch (error) {status(error.message, true);}
});
$('delete-note').addEventListener('click', async () => {
  toggleMenu(false);
  // 확인 창은 데스크가 메모 창 바깥에 띄운다 — 페이지 안 confirm 은 작은 창에서 잘린다
  try {
    await save();          // 묻는 동안 자동 저장이 끼어들지 않게 먼저 저장한다
    const result = await api('sticky_delete', {id: noteId, ask: true});   // 지우면 창은 데스크가 닫는다
    if (result.deleted) {clearTimeout(saveTimer); dirty = false;}
  } catch (error) {status(error.message, true);}
});

$('close').addEventListener('click', async () => {
  try {await save(); await api('sticky_close', {id: noteId});}
  catch (error) {status(error.message, true);}
});

// 오른쪽 아래 손잡이로 크기 바꾸기 — 제목 표시줄이 없는 창이라 테두리로는 못 바꾼다
let resizing = null, resizeBusy = false, resizeNext = null;
async function pumpResize() {
  resizeBusy = true;
  while (resizeNext) {
    const size = resizeNext;
    resizeNext = null;
    try {await api('sticky_resize', {id: noteId, ...size});} catch {/* 다음 움직임에서 다시 */}
  }
  resizeBusy = false;
}
$('grip').addEventListener('pointerdown', event => {
  if (event.button !== 0 || !noteId) return;
  event.preventDefault();
  $('grip').setPointerCapture(event.pointerId);
  resizing = {x: event.screenX, y: event.screenY, w: window.innerWidth, h: window.innerHeight};
});
$('grip').addEventListener('pointermove', event => {
  if (!resizing) return;
  resizeNext = {width: Math.round(resizing.w + event.screenX - resizing.x),
                height: Math.round(resizing.h + event.screenY - resizing.y)};
  if (!resizeBusy) pumpResize();
});
$('grip').addEventListener('pointerup', () => {resizing = null;});
$('grip').addEventListener('pointercancel', () => {resizing = null;});

window.deskSticky = {
  async open(id, pinned) {
    // 창이 다 그려진 직후라 Python 연결이 아직 안 붙었을 수 있다
    if (!window.pywebview?.api) await new Promise(resolve => window.addEventListener('pywebviewready', resolve, {once:true}));
    noteId = id; onTop = !!pinned;
    $('pin').setAttribute('aria-pressed', String(onTop));
    try {
      show(await api('sticky_get', {id}));
      lastSync = Date.now();
      $('content').disabled = false;
      if ($('content').value.trim()) toView();
      else toEdit();
    } catch (error) {status(error.message, true);}
  },
};
const touched = () => {lastTouched = Date.now();};
// 만지는 순간(창을 누르거나 마우스를 올림) 곧바로 받는다 — 웹에서 고친 내용 위에 덮어쓰지 않게
const touchSync = () => {touched(); sync(true);};
window.addEventListener('focus', touchSync);
document.documentElement.addEventListener('pointerenter', touchSync);   // window 에서는 pointerenter 가 나지 않는다
for (const name of ['pointerdown', 'keydown', 'input']) document.addEventListener(name, touched, true);
setInterval(() => sync(), SYNC_ACTIVE);
document.addEventListener('visibilitychange', () => sync(true));
