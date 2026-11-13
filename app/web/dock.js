'use strict';
// 스페이스기전 독 — 아이콘을 누르면 그 기능의 창을 띄운다.
// 창을 여는 일은 모두 데스크(desktop.py)의 기존 작업을 그대로 부른다. 여기서는 모양과 순서만 정한다.

// 아이콘 목록·그림은 dock-items.js 에 있다 — 데스크 설정의 '독 아이콘'도 같은 것을 쓴다
let ITEMS = window.DOCK_ITEMS;   // 학생판이면 start() 에서 학생 목록으로 바꾼다
let hidden = new Set();       // 설정에서 숨긴 아이콘 id (desktop-preferences.json 의 dock_hidden)

const MAGNIFY = 1.5;      // 가리킨 아이콘의 최대 배율
const REACH = 2.6;        // 몇 칸 떨어진 아이콘까지 함께 커지는가
const ROOM = 70;          // 아이콘이 커지며 독이 길어질 자리 (양 끝, px)
const THICK = {h: 200, v: 340};   // 창 두께 — 가로일 때 높이, 세로일 때 너비 (커진 아이콘 + 말풍선·메뉴 자리)
const ICON = 52;          // 아이콘 제 크기 (dock.css --icon)
const MIN_ICON = 30;      // 화면이 좁아 줄여도 이보다 작게는 하지 않는다
let ICONS = ITEMS.filter(Boolean).length;   // 보이는 아이콘 수 — render 가 다시 센다
const SNAP = 40;          // 화면 끝에서 이만큼 안까지 끌어다 놓으면 그 끝에 붙인다 (px)
const DRAG_START = 5;     // 이만큼 움직여야 끌기로 본다. 그보다 적으면 누르기다
const EDGE_HINT = {left:'왼쪽 끝에 세로로 놓기', right:'오른쪽 끝에 세로로 놓기',
                   top:'위쪽 끝에 가로로 놓기', bottom:'아래쪽 끝에 가로로 놓기'};
const $ = id => document.getElementById(id);
const shelf = $('shelf'), bubble = $('bubble'), menu = $('menu');
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const vertical = anchor => anchor === 'left' || anchor === 'right';
const clamp = (value, low, high) => Math.min(Math.max(value, low), Math.max(low, high));

// layout: 어디에 어떻게 놓였나 — 데스크가 기억한다 (desktop-preferences.json 의 dock_layout)
//   anchor  붙는 쪽 (bottom·top 은 가로, left·right 는 세로)
//   docked  화면 끝에 붙었나. 붙었으면 작업 표시줄이 바뀌어도 그 끝을 따라간다
//   cx·cy   창 가운데 (논리 픽셀). null 이면 화면 가운데
let layout = {anchor: 'bottom', docked: true, cx: null, cy: null};
let win = null;           // 지금 창 자리 {x, y, w, h}
let bubbleTimer = 0, hovered = null, busyMorph = false, drag = null, swallowClick = false, areaKey = '';

const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function render() {
  // 숨긴 아이콘은 빼고, 구분선은 보이는 아이콘 사이에만 (맨 앞·맨 뒤·연달아 있는 것은 뺀다)
  const parts = [];
  ITEMS.forEach((item, index) => {
    if (!item) {
      if (parts.length && parts[parts.length - 1] !== null) parts.push(null);
      return;
    }
    if (!hidden.has(item.id)) parts.push(index);
  });
  while (parts.length && parts[parts.length - 1] === null) parts.pop();
  ICONS = parts.filter(index => index !== null).length;
  shelf.innerHTML = parts.map(index => {
    if (index === null) return '<span class="divider" aria-hidden="true"></span>';
    const item = ITEMS[index];
    return `<button class="item" data-index="${index}" aria-label="${escapeHTML(item.label)}">`
      + `<span class="tile tone-${item.tone}">${window.dockFace(item)}</span><span class="run" aria-hidden="true"></span></button>`;
  }).join('');
}

/** 설정에서 보일 아이콘을 바꾸면 다시 그리고 독 크기를 맞춘다 */
function applyHidden(ids) {
  const next = new Set(ids || []);
  if (next.size === hidden.size && [...next].every(id => hidden.has(id))) return;
  hidden = next;
  if (popKey && ITEMS.some(item => item && item.key === popKey && hidden.has(item.id))) closePop();
  render();
  paintCalendar();
  markPop();
  if (win && !drag && !busyMorph) setWindow(geometry()).then(remember).then(region).catch(() => {});
}

/** 달력 아이콘의 요일·날짜. 자정을 넘기면 다음 갱신 때 바뀐다 */
function paintCalendar() {
  const now = new Date();
  shelf.querySelectorAll('.cal').forEach(cal => {
    cal.querySelector('small').textContent = new Intl.DateTimeFormat('ko-KR', {weekday: 'short'}).format(now);
    cal.querySelector('b').textContent = now.getDate();
  });
}

// 이 화면의 CSS 1px 이 실제 몇 픽셀인가 — 창 크기·자리·누를 자리를 셈하는 동작에 함께 보낸다.
// Windows 텍스트 크기가 100% 가 아니면 화면 배율과 달라, 데스크가 이 값으로 맞춘다 (desktop.py _dock_scales, 2026-10-22)
const SIZED = new Set(['dock_place', 'dock_move', 'dock_region', 'dock_preview', 'popover_open']);

async function api(action, payload) {
  if (!window.pywebview?.api) throw new Error('데스크 프로그램에서 실행해 주세요.');
  if (SIZED.has(action)) payload = {...payload, ratio: window.devicePixelRatio};
  const result = await window.pywebview.api.call(action, payload || {});
  if (!result.ok) throw new Error(result.error || '요청을 처리하지 못했습니다.');
  return result.data;
}

// ── 말풍선·메뉴 자리: 독의 화면 안쪽 ─────────────────────────
function placeBeside(el, rect) {
  const gap = 10, w = el.offsetWidth, h = el.offsetHeight;
  let x = rect.left + rect.width / 2 - w / 2, y = rect.top - gap - h;
  if (layout.anchor === 'top') y = rect.bottom + gap;
  if (vertical(layout.anchor)) {
    y = rect.top + rect.height / 2 - h / 2;
    x = layout.anchor === 'left' ? rect.right + gap : rect.left - gap - w;
  }
  el.style.left = `${clamp(x, 6, innerWidth - w - 6)}px`;
  el.style.top = `${clamp(y, 6, innerHeight - h - 6)}px`;
}

function say(target, text, {error = false, hold = 0} = {}) {
  clearTimeout(bubbleTimer);
  bubbleTimer = 0;
  if (!target || !text) {bubble.hidden = true; region(); return;}
  bubble.textContent = text;
  bubble.classList.toggle('error', error);
  bubble.classList.toggle('wrap', text.length > (vertical(layout.anchor) ? 16 : 34));
  bubble.hidden = false;
  const spot = target.classList.contains('item') ? target.querySelector('.tile') : target;
  placeBeside(bubble, spot.getBoundingClientRect());
  region();
  if (hold) bubbleTimer = setTimeout(() => {bubbleTimer = 0; say(hovered && hovered.button, hovered && hovered.label);}, hold);
}

// ── 확대 (맥 독처럼 가리킨 곳 주변이 부드럽게 커진다) ─────────
function magnify(pointer) {
  if (reduceMotion && pointer != null) return;
  const size = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--icon')) || ICON;
  const along = vertical(layout.anchor);
  shelf.querySelectorAll('.item').forEach(el => {
    const box = el.getBoundingClientRect();
    const middle = along ? box.top + box.height / 2 : box.left + box.width / 2;
    const distance = pointer == null ? Infinity : Math.abs(pointer - middle) / size;
    const pull = distance >= REACH ? 0 : Math.cos((distance / REACH) * Math.PI / 2) ** 2;
    el.style.setProperty('--s', (1 + (MAGNIFY - 1) * pull).toFixed(3));
  });
}
shelf.addEventListener('mouseenter', () => {
  pointing = true;
  clearTimeout(shrinkTimer);
  region();                               // 커질 자리를 먼저 편다
});
shelf.addEventListener('mousemove', event => {
  if (!drag?.active && !busyMorph) magnify(vertical(layout.anchor) ? event.clientY : event.clientX);
});
shelf.addEventListener('mouseleave', () => {
  pointing = false;
  shrinkLater();
  if (drag?.active) return;
  magnify(null); hovered = null;
  if (!bubbleTimer) say(null);
});
shelf.addEventListener('mouseover', event => {
  const button = event.target.closest('.item');
  if (!button || drag?.active) return;
  const item = ITEMS[button.dataset.index];
  const label = item.label + (button.querySelector('.badge.dot') ? ' · 새 판 있음' : '');
  hovered = {button, label};
  if (!bubbleTimer) say(button, label);
});
shelf.addEventListener('focusin', event => {
  const button = event.target.closest('.item');
  if (button) say(button, ITEMS[button.dataset.index].label);
});
shelf.addEventListener('focusout', () => {if (!bubbleTimer) say(null);});

// ── 독 위 패널 ────────────────────────────────────────────
// 시간표·일정·업무·공지·알림·메모는 아이콘 위로 패널을 펼친다. 패널 창은 데스크가 하나 두고 다시 쓴다
// (desktop.py `_popover_open`). 자리는 여기서 셈한다 — 판의 화면 안쪽, 누른 아이콘 바로 위.
// 패널 창 크기 (카드 + 둘레 12px — 꼭지·그림자 자리). 캡처 보관함은 썸네일이 보이게 넓게
// 시간표(한 주 표)·일정(한 달 달력)은 칸이 많아 조금 넓게
// 설정은 항목이 많아 세로로 길게 (교사판 '연결 및 설정'까지 2026-10-19)
const POP_SIZE = {captures: {w: 584, h: 584}, today: {w: 492, h: 584}, week: {w: 492, h: 584}, settings: {w: 432, h: 620},
                  messages: {w: 452, h: 620}, automation: {w: 452, h: 640}};
const POP_DEFAULT = {w: 404, h: 504};
const POP_GAP = 30;             // 판과 패널 사이 — 가리키면 커지는 아이콘이 들어갈 자리
let popKey = null;

function popoverPlace(button, key) {
  const POP = POP_SIZE[key] || POP_DEFAULT;
  const a = area(), tile = button.querySelector('.tile').getBoundingClientRect(), s = shelf.getBoundingClientRect();
  const icon = {x: win.x + tile.left + tile.width / 2, y: win.y + tile.top + tile.height / 2};
  const box = {left: win.x + s.left, top: win.y + s.top, right: win.x + s.right, bottom: win.y + s.bottom};
  let x = icon.x - POP.w / 2, y = box.top - POP_GAP - POP.h;
  if (layout.anchor === 'top') y = box.bottom + POP_GAP;
  if (layout.anchor === 'left') {x = box.right + POP_GAP; y = icon.y - POP.h / 2;}
  if (layout.anchor === 'right') {x = box.left - POP_GAP - POP.w; y = icon.y - POP.h / 2;}
  x = clamp(x, a.left, a.right - POP.w);
  y = clamp(y, a.top, a.bottom - POP.h);
  const along = vertical(layout.anchor) ? icon.y - y : icon.x - x;
  const span = vertical(layout.anchor) ? POP.h : POP.w;
  return {rect: [x, y, POP.w, POP.h].map(Math.round),
          caret: {side: layout.anchor, at: Math.round(clamp(along, 34, span - 34))}};
}

function markPop() {
  shelf.querySelectorAll('.item').forEach(el => el.classList.toggle('open', !!popKey && ITEMS[el.dataset.index].key === popKey));
}

async function togglePop(button, item) {
  if (popKey === item.key) {closePop(); return;}      // 같은 아이콘을 다시 누르면 접는다
  popKey = item.key;
  markPop();
  say(null);
  try {
    await api('popover_open', {key: item.key, ...popoverPlace(button, item.key)});
  } catch (error) {
    popKey = null;
    markPop();
    say(button, error.message, {error: true, hold: 4200});
  }
}

function closePop() {
  if (!popKey) return;
  popKey = null;
  markPop();
  api('popover_close').catch(() => {});
}

// 패널의 X·Esc 로 닫히면 데스크가 알려 준다
window.deskDock = {
  popClosed() {popKey = null; markPop();},
  /** 데스크 설정에서 '독 아이콘'을 바꾸면 곧바로 알려 준다 */
  setHidden(ids) {applyHidden(ids);},
  /** 단축키로 불렀다 — 화면 안쪽으로 살짝 튀어 자리를 알린다 */
  nudge() {
    if (reduceMotion || busyMorph || drag?.active) return;
    const hop = {bottom: 'translateY(-12px)', top: 'translateY(12px)', left: 'translateX(12px)', right: 'translateX(-12px)'}[layout.anchor];
    nudging = true;
    region();                             // 튀어 오를 자리를 먼저 편다
    shelf.animate([{transform: 'none'}, {transform: hop}, {transform: 'none'}, {transform: hop.replace('12', '4')}, {transform: 'none'}],
                  {duration: 520, easing: 'ease-out'}).finished.catch(() => {}).then(() => {nudging = false; shrinkLater();});
  },
  /** 데스크가 패널을 연다 — 캡처를 마치면 캡처 보관함을 그 아이콘 위로 */
  openPop(key) {
    const index = ITEMS.findIndex(item => item && item.key === key);
    const button = shelf.querySelector(`.item[data-index="${index}"]`);
    if (!button || busyMorph || drag?.active) return false;
    popKey = key;
    markPop();
    api('popover_open', {key, ...popoverPlace(button, key)}).catch(() => {popKey = null; markPop();});
    return true;
  },
};

// ── 에이전트 터미널 ──────────────────────────────────────────
// 지금 보던 창의 폴더가 하나면 패널 맨 위에서 '이 폴더에서 열까요?'를 묻는다 ('앞으로 묻지 않기'면 곧바로 연다, 2026-10-25).
// 여럿이거나 없거나 설치가 안 됐으면 패널에서 고른다.
// 패널(폴더 고르기·자주 쓰는 폴더·설정)은 오른쪽 클릭으로 언제든 연다.
async function agentClick(button, item) {
  if (popKey === item.key) {closePop(); return;}
  button.classList.add('launching');
  region();
  try {
    const result = await api('agent_quick');
    if (result.launched) {say(button, `${result.message} (오른쪽 클릭: 폴더 고르기)`, {hold: 3400}); return;}
  } catch (error) {
    say(button, error.message, {error: true, hold: 4200});
    return;
  } finally {
    button.classList.remove('launching');
    shrinkLater();
  }
  togglePop(button, item);
}

// ── 누르기 ───────────────────────────────────────────────
// 끌다 놓은 자리에서 생기는 click 은 누르기가 아니다 — 먼저 가로챈다
shelf.addEventListener('click', event => {
  if (swallowClick) {event.stopImmediatePropagation(); event.preventDefault();}
}, true);
shelf.addEventListener('click', async event => {
  const button = event.target.closest('.item');
  if (!button || button.classList.contains('launching')) return;
  hideMenu();
  const item = ITEMS[button.dataset.index];
  if (item.action === 'pop') {togglePop(button, item); return;}
  if (item.action === 'agent') {agentClick(button, item); return;}
  if (item.quiet) {
    say(null);
    magnify(null);
    hovered = null;
    api(item.action).catch(error => say(button, error.message, {error: true, hold: 4200}));
    return;
  }
  button.classList.add('launching');
  region();
  const started = Date.now();
  try {
    const message = await api(item.action, {target: item.target, page: item.page, route: item.route});
    await new Promise(done => setTimeout(done, Math.max(0, 700 - (Date.now() - started))));
    if (message) say(button, message, {hold: 2600});
  } catch (error) {
    say(button, error.message, {error: true, hold: 4200});
  } finally {
    button.classList.remove('launching');
    shrinkLater();
  }
});

// ── 누를 자리 (창 모양) ───────────────────────────────────
// 창은 투명한 유리라 그대로 두면 빈 곳도 클릭을 막는다. 판(+그림자)과 말풍선·메뉴 자리만
// 남기고 나머지는 아래 창이 받게 한다 (desktop.py `_dock_region`).
// 아이콘이 커지고 튈 자리는 **판을 가리키는 동안·튀는 동안만** 더한다 — 늘 남겨 두면 독 위 빈
// 곳(약 60px)이 클릭을 막는다 (2026-10-12 요청). 창 모양은 그림도 자르므로 접을 때는 커졌던
// 아이콘이 제 크기로 돌아온 뒤에 접는다 (SHRINK_AFTER).
const SHADOW = 30;        // 판 둘레 그림자 자리 (px)
const SHADOW_UP = 16;     // 그림자는 아래로 치우쳐 있어(0 8px 22px) 위로는 이만큼만 번진다
const SHRINK_AFTER = 260; // 가리키기를 멈추고 이만큼(ms) 뒤에 접는다 — 아이콘이 줄어드는 시간(.12s) 넉넉히
let regionKey = '', pointing = false, nudging = false, grownUntil = 0, shrinkTimer = 0;
const growing = () => pointing || nudging || Date.now() < grownUntil || !!shelf.querySelector('.item.launching');
/** 커질 일이 끝났다 — 아이콘이 다 줄어든 뒤에 접는다 (그 사이 다른 데서 region() 을 불러도 접지 않는다) */
function shrinkLater() {
  grownUntil = Date.now() + SHRINK_AFTER;
  clearTimeout(shrinkTimer);
  shrinkTimer = setTimeout(region, SHRINK_AFTER + 20);
}
function region() {
  if (!window.pywebview?.api || !win) return;
  let rects = null;                       // null = 창 전체 (끌기·접었다 펴기·처음 펴기 동안)
  if (!drag?.active && !busyMorph && !document.body.classList.contains('booting')) {
    const size = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--icon')) || ICON;
    const box = shelf.getBoundingClientRect();
    let [left, top, right, bottom] = [box.left - SHADOW, box.top - SHADOW_UP, box.right + SHADOW, box.bottom + SHADOW];
    if (growing()) {
      const rise = Math.ceil(size * (MAGNIFY - 1) + 20) + SHADOW;   // 화면 안쪽으로 커지고 튀는 아이콘
      const along = size;                 // 가리키면 판이 길어지는 만큼
      if (vertical(layout.anchor)) {top -= along; bottom += along;} else {left -= along; right += along;}
      if (layout.anchor === 'bottom') top = box.top - rise;
      if (layout.anchor === 'top') bottom = box.bottom + rise;
      if (layout.anchor === 'left') right = box.right + rise;
      if (layout.anchor === 'right') left = box.left - rise;
    }
    rects = [[left, top, right - left, bottom - top]];
    for (const el of [bubble, menu]) {
      if (el.hidden) continue;
      const e = el.getBoundingClientRect();
      rects.push([e.left - 10, e.top - 10, e.width + 20, e.height + 20]);
    }
    rects = rects.map(rect => rect.map(Math.round));
  }
  // 판 자리·붙는 쪽도 함께 — 독이 가려지면 데스크가 그 가장자리에 손잡이 줄을 띄운다
  const box = shelf.getBoundingClientRect();
  const at = [box.left, box.top, box.width, box.height].map(Math.round);
  const key = JSON.stringify([rects, at, layout.anchor]);
  if (key === regionKey) return;
  regionKey = key;
  api('dock_region', {rects, shelf: at, anchor: layout.anchor}).catch(() => {regionKey = '';});
}

// ── 자리 계산 ─────────────────────────────────────────────
// 모든 좌표는 논리 픽셀(CSS px)이다. 데스크의 window.move·resize 가 같은 단위를 쓴다.
function area() {
  const left = screen.availLeft, top = screen.availTop;
  return {left, top, right: left + screen.availWidth, bottom: top + screen.availHeight};
}

function applyAnchor(anchor) {
  document.body.dataset.anchor = anchor;
  $('menu-turn').textContent = vertical(anchor) ? '가로로 놓기' : '세로로 놓기';
}

/** 독 판의 길이 — 아이콘이 모두 제 크기일 때 */
function shelfLength() {
  document.body.classList.add('measuring');
  magnify(null);
  const length = vertical(layout.anchor) ? shelf.offsetHeight : shelf.offsetWidth;
  document.body.classList.remove('measuring');
  return length;
}

/** 화면에 다 들어가지 않으면 아이콘을 줄인다 (맥 독처럼). 화면이 넉넉하면 제 크기로 */
function fitIcons(anchor) {
  const a = area();
  const room = (vertical(anchor) ? a.bottom - a.top : a.right - a.left) - ROOM * 2;
  const root = document.documentElement.style;
  let size = ICON;
  root.setProperty('--icon', `${size}px`);
  // 판 길이는 아이콘 크기에 거의 비례한다 (간격·여백만 고정). 두 번이면 들어맞는다
  for (let tries = 0; tries < 2 && shelfLength() > room; tries++) {
    const length = shelfLength(), fixed = length - ICONS * size;
    size = Math.max(MIN_ICON, Math.floor((room - fixed) / ICONS));
    root.setProperty('--icon', `${size}px`);
  }
}

/** layout 대로 놓을 창 자리. 화면 밖으로는 나가지 않는다 */
function geometry(next = layout) {
  fitIcons(next.anchor);
  return placement(next, shelfLength());
}

/** 판 길이가 shelfSize 일 때 next 대로 놓을 창 자리 — 판을 건드리지 않는 셈만 한다 */
function placement(next, shelfSize) {
  const length = shelfSize + ROOM * 2;
  const w = vertical(next.anchor) ? THICK.v : length;
  const h = vertical(next.anchor) ? length : THICK.h;
  const a = area();
  let x = (next.cx ?? (a.left + a.right) / 2) - w / 2;
  let y = (next.cy ?? (a.top + a.bottom) / 2) - h / 2;
  x = clamp(x, a.left, a.right - w);
  y = clamp(y, a.top, a.bottom - h);
  if (next.docked) {
    if (next.anchor === 'bottom') y = a.bottom - h;
    if (next.anchor === 'top') y = a.top;
    if (next.anchor === 'left') x = a.left;
    if (next.anchor === 'right') x = a.right - w;
  }
  return {x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h)};
}

// ── 놓일 자리 미리보기 ─────────────────────────────────────
// 끄는 독이 화면 끝에 닿으면, 놓았을 때 판이 설 자리·방향·크기를 반투명하게 보인다
// (desktop.py `_dock_preview_show`). 끄는 판은 그대로 두고 셈만 한다.
const SHELF_EXTRA = 25;   // 판 두께 = 아이콘 + 25px (dock.css #shelf)
const SHELF_RADIUS = 22;
const STAGE_PAD = 8;      // 창 가장자리와 판 사이 (dock.css #stage)

function previewRect(edge, px, py) {
  const now = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--icon')) || ICON;
  const fixed = shelfLength() - ICONS * now;           // 간격·여백 — 아이콘 크기와 상관없다
  const a = area();
  const room = (vertical(edge) ? a.bottom - a.top : a.right - a.left) - ROOM * 2;
  const size = fixed + ICONS * ICON <= room ? ICON : Math.max(MIN_ICON, Math.floor((room - fixed) / ICONS));
  const length = fixed + ICONS * size, thick = size + SHELF_EXTRA;
  const g = placement({anchor: edge, docked: true, cx: px, cy: py}, length);
  if (vertical(edge)) {
    const x = edge === 'left' ? g.x + STAGE_PAD : g.x + g.w - STAGE_PAD - thick;
    return [x, g.y + (g.h - length) / 2, thick, length].map(Math.round);
  }
  const y = edge === 'top' ? g.y + STAGE_PAD : g.y + g.h - STAGE_PAD - thick;
  return [g.x + (g.w - length) / 2, y, length, thick].map(Math.round);
}

let previewing = false, nextPreview, previewKey = 'null';
function preview(rect) {
  const key = JSON.stringify(rect);
  if (key === previewKey) return;
  previewKey = key;
  nextPreview = {rect, radius: SHELF_RADIUS};
  if (!previewing) pumpPreview();
}
async function pumpPreview() {
  previewing = true;
  while (nextPreview) {
    const payload = nextPreview;
    nextPreview = null;
    try {await api('dock_preview', payload);} catch {/* 다음 움직임에서 다시 */}
  }
  previewing = false;
}

async function setWindow(g) {
  win = g;
  areaKey = JSON.stringify(area());
  await api('dock_place', {x: g.x, y: g.y, width: g.w, height: g.h});
}

function remember() {
  layout.cx = Math.round(win.x + win.w / 2);
  layout.cy = Math.round(win.y + win.h / 2);
  api('dock_layout', layout).catch(() => {});
}

// ── 접었다 펴기 (가로 ↔ 세로, 다른 끝으로 옮길 때) ─────────────
const frame = () => new Promise(done => requestAnimationFrame(() => done()));

function fold() {
  return shelf.animate([{transform: 'none', opacity: 1}, {transform: 'scale(.55)', opacity: 0}],
    {duration: 170, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards'}).finished;
}

function unfold() {
  // 접힌 채 멈춰 있던 움직임을 지우고 같은 순간에 펴기를 건다 — 그 사이 한 장면도 비치지 않게
  shelf.getAnimations().forEach(animation => animation.cancel());
  document.body.classList.remove('booting');
  const inward = {bottom: 'translateY(26px)', top: 'translateY(-26px)',
                  left: 'translateX(-26px)', right: 'translateX(26px)'}[layout.anchor];
  const stretch = vertical(layout.anchor) ? 'scaleY(.2)' : 'scaleX(.2)';
  const opening = shelf.animate(
    [{transform: `${inward} ${stretch}`, opacity: 0}, {transform: 'none', opacity: 1}],
    {duration: 520, easing: 'cubic-bezier(.2,1.25,.35,1)', fill: 'backwards'});
  shelf.querySelectorAll('.tile').forEach((tile, index) => tile.animate(
    [{transform: 'scale(.3)', opacity: 0}, {transform: 'none', opacity: 1}],
    {duration: 380, delay: 110 + index * 28, easing: 'cubic-bezier(.2,1.5,.4,1)', fill: 'backwards'}));
  return opening.finished;
}

/** 새 자리·방향으로 옮긴다. 방향이나 붙는 끝이 바뀌면 접었다 편다 */
async function settle(next) {
  closePop();
  const turning = next.anchor !== layout.anchor || (next.docked && !layout.docked);
  busyMorph = true;
  say(null); hideMenu();
  region();
  try {
    if (turning && !reduceMotion) await fold();
    layout = {...layout, ...next};
    applyAnchor(layout.anchor);
    await setWindow(geometry());
    remember();
    if (turning && !reduceMotion) {
      await frame(); await frame();          // 창이 새 자리에 그려진 다음에 편다
      await unfold();
    }
  } catch (error) {
    shelf.getAnimations().forEach(animation => animation.cancel());
    document.body.classList.remove('booting');
  } finally {
    busyMorph = false;
    region();
  }
}

function turn() {
  // 끝에 붙어 있었으면 새 끝의 가운데로, 떠 있었으면 그 자리에서 방향만 바꾼다
  const a = area(), cx = win.x + win.w / 2, cy = win.y + win.h / 2;
  const anchor = vertical(layout.anchor)
    ? (cy > (a.top + a.bottom) / 2 ? 'bottom' : 'top')
    : (cx <= (a.left + a.right) / 2 ? 'left' : 'right');
  settle(layout.docked ? {anchor, docked: true, cx: null, cy: null} : {anchor, cx, cy});
}

// ── 끌어 옮기기 ───────────────────────────────────────────
let moving = false, nextMove = null;
async function pumpMoves() {
  if (moving) return;
  moving = true;
  while (nextMove) {
    const point = nextMove;
    nextMove = null;
    try {await api('dock_move', point);} catch {/* 다음 움직임에서 다시 */}
  }
  moving = false;
}
const movesDone = async () => {while (moving || nextMove) await frame();};

/** 놓을 곳이 화면 끝 가까이면 그 끝 */
function edgeAt(px, py) {
  const a = area();
  const gaps = {left: px - a.left, right: a.right - px, top: py - a.top, bottom: a.bottom - py};
  const [edge, gap] = Object.entries(gaps).sort((one, two) => one[1] - two[1])[0];
  return gap <= SNAP ? edge : null;
}

shelf.addEventListener('pointerdown', event => {
  if (event.button !== 0 || busyMorph || !win) return;
  drag = {id: event.pointerId, sx: event.screenX, sy: event.screenY,
          gx: event.screenX - win.x, gy: event.screenY - win.y, active: false, edge: null};
});
window.addEventListener('pointermove', event => {
  if (!drag || event.pointerId !== drag.id) return;
  if (!drag.active) {
    if (Math.hypot(event.screenX - drag.sx, event.screenY - drag.sy) < DRAG_START) return;
    drag.active = true;
    closePop();
    try {shelf.setPointerCapture(drag.id);} catch {/* 이미 놓았다 */}
    document.body.classList.add('dragging');
    hideMenu(); magnify(null); say(null);
    region();
    hovered = null;
  }
  let x = Math.round(event.screenX - drag.gx), y = Math.round(event.screenY - drag.gy);
  // 🚨 포인터가 이 화면 안에 있는 동안은 독 창을 화면(작업 영역) 밖으로 내밀지 않는다. 우리 창이
  //    화면 위로 크게 삐져나가면 Windows 가 같은 프로그램의 미리보기 창을 화면에 그리지 않았다
  //    (2026-10-11 확인 — 위쪽 끝으로 끌 때만 미리보기가 안 보였다). 포인터가 다른 모니터로
  //    넘어가면 막지 않는다 — 독을 그 모니터로 옮길 수 있게.
  const a = area();
  const monitor = {left: screen.left ?? a.left, top: screen.top ?? a.top};
  const onThisScreen = event.screenX >= monitor.left && event.screenX < monitor.left + screen.width
    && event.screenY >= monitor.top && event.screenY < monitor.top + screen.height;
  if (onThisScreen) {
    x = clamp(x, a.left, a.right - win.w);
    y = clamp(y, a.top, a.bottom - win.h);
  }
  win = {...win, x, y};
  nextMove = {x: win.x, y: win.y};
  pumpMoves();
  const edge = edgeAt(event.screenX, event.screenY);
  if (edge !== drag.edge) {
    drag.edge = edge;
    shelf.classList.toggle('snapping', !!edge);
    say(edge ? shelf : null, edge && EDGE_HINT[edge]);
  }
  // 끝에 닿아 있는 동안은 놓을 자리를 따라 미리보기도 움직인다. 놓을 때도 이 점을 쓴다 —
  // 미리보기와 실제로 놓이는 자리가 어긋나지 않게
  drag.point = {x: event.screenX, y: event.screenY};
  preview(edge ? previewRect(edge, drag.point.x, drag.point.y) : null);
});
async function drop(event) {
  if (!drag || event.pointerId !== drag.id) return;
  const done = drag;
  drag = null;
  if (!done.active) return;
  swallowClick = true;
  setTimeout(() => {swallowClick = false;}, 0);
  document.body.classList.remove('dragging');
  shelf.classList.remove('snapping');
  say(null);
  preview(null);                          // 놓는 순간 미리보기는 걷고, 독이 그 자리에서 펴진다
  await movesDone();
  if (done.edge) {
    // 놓은 자리에 맞춰 그 끝에 붙인다 — 왼쪽 끝이면 세로로, 놓은 높이에
    const at = done.point || {x: event.screenX, y: event.screenY};
    settle({anchor: done.edge, docked: true, cx: at.x, cy: at.y});
  } else {
    settle({docked: false, cx: win.x + win.w / 2, cy: win.y + win.h / 2});
  }
}
window.addEventListener('pointerup', drop);
window.addEventListener('pointercancel', drop);

// ── 오른쪽 클릭 메뉴 ─────────────────────────────────────
function hideMenu() {
  if (menu.hidden) return;
  menu.hidden = true;
  region();
}
document.addEventListener('contextmenu', event => {
  event.preventDefault();
  if (busyMorph || drag?.active) return;
  // 에이전트 아이콘의 오른쪽 클릭은 폴더 고르기 패널
  const agent = event.target.closest('.item');
  if (agent && ITEMS[agent.dataset.index]?.action === 'agent') {
    hideMenu();
    const item = ITEMS[agent.dataset.index];
    if (popKey !== item.key) togglePop(agent, item);
    return;
  }
  say(null);
  menu.hidden = false;
  const box = shelf.getBoundingClientRect();
  const at = vertical(layout.anchor)
    ? {left: box.left, right: box.right, width: box.width, top: event.clientY, bottom: event.clientY, height: 0}
    : {left: event.clientX, right: event.clientX, width: 0, top: box.top, bottom: box.bottom, height: box.height};
  placeBeside(menu, at);
  region();
  menu.querySelector('button').focus();
});
document.addEventListener('mousedown', event => {if (!menu.contains(event.target)) hideMenu();});
document.addEventListener('keydown', event => {if (event.key === 'Escape') hideMenu();});
window.addEventListener('blur', hideMenu);
menu.addEventListener('click', event => {
  const choice = event.target.closest('[data-menu]')?.dataset.menu;
  hideMenu();
  if (choice === 'desk') api('open_page', {page: 'home'}).catch(() => {});
  if (choice === 'turn') turn();
  if (choice === 'hide') api('dock_hide').catch(() => {});
});

// ── 상태 ─────────────────────────────────────────────────
/** 아이콘 모서리 표시 — 숫자(안 읽은 메시지), true 면 점(받아 둔 업데이트). 없으면 없앤다 */
function paintBadge(el, count) {
  let badge = el.querySelector('.badge');
  if (!count) {badge?.remove(); return;}
  if (!badge) {
    badge = document.createElement('span');
    badge.setAttribute('aria-hidden', 'true');
    el.append(badge);
  }
  badge.className = count === true ? 'badge dot' : 'badge';
  badge.textContent = count === true ? '' : count > 99 ? '99+' : String(count);
}

async function refresh() {
  paintCalendar();
  try {
    const state = await api('dock_state');
    applyHidden(state.hidden);
    const running = new Set(state.running), busy = new Set(state.busy), badges = state.badges || {};
    shelf.querySelectorAll('.item').forEach(el => {
      const item = ITEMS[el.dataset.index];
      el.classList.toggle('running', !!item.run && running.has(item.run));
      if (item.badge) paintBadge(el, badges[item.badge]);
      if (item.busy && busy.has(item.busy)) el.classList.add('launching');
      else if (item.busy && el.dataset.waiting) el.classList.remove('launching');
      el.dataset.waiting = item.busy && busy.has(item.busy) ? '1' : '';
    });
    region();                             // 로그인 중(튀는 아이콘)이 시작되거나 끝났으면 창 모양도 따라간다
  } catch {/* 데스크가 바쁠 때는 다음 차례에 다시 묻는다 */}
  // 작업 표시줄을 옮기거나 해상도를 바꾸면 같은 끝을 따라간다. 기억한 자리는 덮어쓰지 않는다 —
  // 모니터를 잠깐 뺐다 꽂거나 켤 때 화면 정보가 늦게 와도, 사용자가 놓은 자리로 돌아올 수 있게
  if (win && !drag && !busyMorph && JSON.stringify(area()) !== areaKey) {
    setWindow(geometry()).then(region).catch(() => {});
  }
}

/** 다른 모니터에 두었던 독 — 데스크가 창을 먼저 그 모니터로 옮겨 둔다 (desktop.py `_dock_to_saved_screen`).
 *  창이 옮겨 간 것을 화면 정보(screen)가 알아챌 때까지 잠깐 기다린다. 그 모니터가 없으면 그냥 지나간다 */
async function onSavedScreen() {
  if (layout.cx == null || layout.cy == null) return;
  for (let tries = 0; tries < 30; tries++) {
    const a = area();
    if (layout.cx >= a.left && layout.cx < a.right && layout.cy >= a.top && layout.cy < a.bottom) return;
    await new Promise(done => setTimeout(done, 50));
  }
}

async function start() {
  try {
    const state = await api('dock_state');
    if (state.edition === 'student') ITEMS = window.dockItemsOf(window.DOCK_SETS.student);   // 학생판 아이콘
    if (state.layout) layout = {...layout, ...state.layout};
    hidden = new Set(state.hidden || []);
    render();
    paintCalendar();
  } catch {/* 기억한 자리가 없으면 아래 가운데 */}
  applyAnchor(layout.anchor);
  await onSavedScreen();
  try {await setWindow(geometry());} catch {/* 그래도 보이기는 한다 */}
  await frame(); await frame();
  if (reduceMotion) document.body.classList.remove('booting');
  else await unfold().catch(() => document.body.classList.remove('booting'));
  region();
  refresh();
  setInterval(refresh, 1500);
}

render();
paintCalendar();
applyAnchor(layout.anchor);
window.addEventListener('pywebviewready', start);
