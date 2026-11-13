'use strict';
// 캡처 보관함 — 데스크가 모아 둔 캡처 파일을 폴더처럼 보여 준다 (desktop.py `_capture_*`).
// 그림은 평범한 파일이라 끌어서 다른 프로그램에 놓을 수 있고, 두 번 누르면 기본 프로그램으로 열린다.
// 제 창(captures.html)에서도, 독 위 패널(popover.html 의 #captures-view) 안에서도 돈다.
// 패널과 한 페이지에 실리므로 이름이 섞이지 않게 통째로 감싼다.
(() => {

const $ = id => document.getElementById(id);
// 독 위 패널 안이면, 패널이 캡처 보관함을 보이는 동안에만 키·주기 확인에 반응한다
const embedded = !!document.getElementById('captures-view');
const active = () => !embedded || !$('captures-view').hidden;
const board = $('board'), groups = $('groups'), menu = $('menu');
const DRAG_START = 6;         // 이만큼 움직여야 끌기로 본다
const POLL = 2500;            // 폴더가 바뀌었는지 묻는 간격 (ms) — 탐색기에서 지운 것도 따라간다
let items = [], signature = '', picked = new Set(), anchor = null, editing = null, press = null, toastTimer = 0;

const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stem = name => name.replace(/\.[^.]+$/, '');

async function api(action, payload) {
  if (!window.pywebview?.api) throw new Error('데스크 프로그램에서 실행해 주세요.');
  const result = await window.pywebview.api.call(action, payload || {});
  if (!result.ok) throw new Error(result.error || '요청을 처리하지 못했습니다.');
  return result.data;
}

function toast(message, error = false) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').classList.toggle('error', error);
  $('toast').hidden = !message;
  toastTimer = setTimeout(() => {$('toast').hidden = true;}, error ? 5000 : 2600);
}
const attempt = work => work().catch(error => toast(error.message, true));

// ── 그리기 ───────────────────────────────────────────────
function dayTitle(date) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(date); day.setHours(0, 0, 0, 0);
  const gap = Math.round((today - day) / 86400000);
  if (gap === 0) return '오늘';
  if (gap === 1) return '어제';
  const options = {month: 'long', day: 'numeric', weekday: 'short'};
  if (day.getFullYear() !== today.getFullYear()) options.year = 'numeric';
  return new Intl.DateTimeFormat('ko-KR', options).format(day);
}

function render(fresh) {
  const names = new Set(items.map(item => item.name));
  picked = new Set([...picked].filter(name => names.has(name)));
  $('empty').hidden = items.length > 0;
  const size = items.reduce((sum, item) => sum + item.size, 0);
  $('summary').textContent = items.length
    ? `캡처 ${items.length}개 · ${(size / 1048576).toFixed(size > 10485760 ? 0 : 1)}MB`
    : '아직 담긴 캡처가 없습니다';
  const byDay = new Map();
  for (const item of items) {
    const key = item.modified.slice(0, 10);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(item);
  }
  groups.innerHTML = [...byDay].map(([day, list]) => `<section class="group">
      <h2>${escapeHTML(dayTitle(day + 'T00:00:00'))}<small>${list.length}개</small></h2>
      <div class="grid">${list.map(item => {
        const time = new Date(item.modified).toLocaleTimeString('ko-KR', {hour: 'numeric', minute: '2-digit'});
        return `<div class="tile${picked.has(item.name) ? ' picked' : ''}${item.name === fresh ? ' fresh' : ''}"
            data-name="${escapeHTML(item.name)}" tabindex="-1" role="option" aria-selected="${picked.has(item.name)}"
            title="${escapeHTML(item.name)}&#10;${item.width}×${item.height}">
          <div class="shot"><img src="${item.thumb}" alt="" draggable="false"></div>
          <div class="name">${escapeHTML(stem(item.name))}</div>
          <div class="meta">${escapeHTML(time)} · ${item.width}×${item.height}</div>
        </div>`;
      }).join('')}</div></section>`).join('');
}

const tiles = () => [...groups.querySelectorAll('.tile')];
const tileOf = name => tiles().find(tile => tile.dataset.name === name);

function paintPicks() {
  tiles().forEach(tile => {
    const on = picked.has(tile.dataset.name);
    tile.classList.toggle('picked', on);
    tile.setAttribute('aria-selected', on);
  });
}

async function reload(force = false) {
  const data = await api('capture_list', {signature: force ? '' : signature});
  if (data.same) return;
  signature = data.signature;
  items = data.items;
  if (editing && !items.some(item => item.name === editing)) editing = null;
  if (editing) return;                  // 이름을 고치는 중에는 다시 그리지 않는다
  if (data.fresh) picked = new Set([data.fresh]), anchor = data.fresh;
  render(data.fresh);
  if (data.fresh) {
    const tile = tileOf(data.fresh);
    tile?.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    toast('캡처를 보관함에 담았습니다. 끌어서 원하는 곳에 놓아 보세요.');
  }
}
window.deskCaptures = {reload: () => attempt(() => reload(true))};

// ── 고르기 ───────────────────────────────────────────────
function pick(name, {toggle = false, range = false} = {}) {
  if (range && anchor) {
    const names = tiles().map(tile => tile.dataset.name);
    const [from, to] = [names.indexOf(anchor), names.indexOf(name)].sort((a, b) => a - b);
    if (from >= 0) {
      if (!toggle) picked.clear();
      names.slice(from, to + 1).forEach(each => picked.add(each));
      paintPicks();
      return;
    }
  }
  if (toggle) picked.has(name) ? picked.delete(name) : picked.add(name);
  else picked = new Set([name]);
  anchor = name;
  paintPicks();
}
const chosen = () => tiles().map(tile => tile.dataset.name).filter(name => picked.has(name));

groups.addEventListener('pointerdown', event => {
  if (event.button !== 0 || editing) return;
  const tile = event.target.closest('.tile');
  if (!tile) return;
  const name = tile.dataset.name;
  if (event.ctrlKey || event.shiftKey) pick(name, {toggle: event.ctrlKey, range: event.shiftKey});
  else if (!picked.has(name)) pick(name);
  tile.focus({preventScroll: true});
  press = {x: event.clientX, y: event.clientY, name, keep: event.ctrlKey || event.shiftKey};
});
window.addEventListener('pointermove', event => {
  if (!press || Math.hypot(event.clientX - press.x, event.clientY - press.y) < DRAG_START) return;
  // 끌기 — 고른 것 모두를 Windows 파일로 넘긴다. 이후는 Windows 가 마우스를 맡는다
  const names = picked.has(press.name) ? chosen() : [press.name];
  press = null;
  names.forEach(name => tileOf(name)?.classList.add('dragging'));
  api('capture_drag', {names})
    .catch(error => toast(error.message, true))
    .finally(() => setTimeout(() => tiles().forEach(tile => tile.classList.remove('dragging')), 400));
});
window.addEventListener('pointerup', event => {
  if (press && !press.keep) {
    const tile = event.target.closest('.tile');
    if (tile && tile.dataset.name === press.name) pick(press.name);   // 여럿 중 하나를 누르면 그것만
  }
  press = null;
});
board.addEventListener('pointerdown', event => {
  if (event.button === 0 && !event.target.closest('.tile') && !editing) {picked.clear(); anchor = null; paintPicks();}
});
groups.addEventListener('dblclick', event => {
  const tile = event.target.closest('.tile');
  if (!tile || editing) return;
  if (event.target.closest('.name')) startRename(tile.dataset.name);
  else attempt(() => api('capture_open', {name: tile.dataset.name}));
});

// ── 이름 바꾸기 ───────────────────────────────────────────
function startRename(name) {
  const tile = tileOf(name);
  if (!tile) return;
  hideMenu();
  editing = name;
  pick(name);
  const label = tile.querySelector('.name');
  const input = document.createElement('input');
  input.className = 'rename';
  input.value = stem(name);
  input.maxLength = 120;
  input.setAttribute('aria-label', '새 파일 이름');
  label.replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const finish = async save => {
    if (done) return;
    done = true;
    const to = input.value.trim();
    if (save && to && to !== stem(name)) {
      try {
        const result = await api('capture_rename', {name, to});
        editing = null;
        picked = new Set([result.name]);
        anchor = result.name;
        await reload(true);
        tileOf(result.name)?.focus({preventScroll: true});
        return;
      } catch (error) {
        toast(error.message, true);
      }
    }
    editing = null;
    render();
    tileOf(name)?.focus({preventScroll: true});
  };
  input.addEventListener('keydown', event => {
    event.stopPropagation();
    if (event.key === 'Enter') finish(true);
    if (event.key === 'Escape') finish(false);
  });
  input.addEventListener('blur', () => finish(true));
}

// ── 할 일 ────────────────────────────────────────────────
async function act(action) {
  const names = chosen();
  if (!names.length) return;
  if (action === 'open') {
    for (const name of names.slice(0, 10)) await api('capture_open', {name});
  }
  if (action === 'copy') toast(await api('capture_copy', {names}));
  if (action === 'rename') startRename(names[0]);
  if (action === 'reveal') await api('capture_reveal', {name: names[0]});
  if (action === 'delete') {
    const message = await api('capture_delete', {names});
    picked.clear();
    await reload(true);
    toast(message);
  }
}

function hideMenu() {menu.hidden = true;}
groups.addEventListener('contextmenu', event => {
  const tile = event.target.closest('.tile');
  if (!tile || editing) return;
  event.preventDefault();
  if (!picked.has(tile.dataset.name)) pick(tile.dataset.name);
  const many = picked.size > 1;
  menu.querySelectorAll('[data-one]').forEach(button => {button.hidden = many;});
  menu.querySelector('[data-do="delete"]').textContent = many ? `${picked.size}개 휴지통으로 옮기기` : '휴지통으로 옮기기';
  menu.hidden = false;
  menu.style.left = `${Math.min(event.clientX, innerWidth - menu.offsetWidth - 8)}px`;
  menu.style.top = `${Math.min(event.clientY, innerHeight - menu.offsetHeight - 8)}px`;
  menu.querySelector('button:not([hidden])').focus();
});
document.addEventListener('contextmenu', event => {if (!event.target.closest('.tile')) event.preventDefault();});
document.addEventListener('pointerdown', event => {if (!menu.contains(event.target)) hideMenu();});
window.addEventListener('blur', hideMenu);
menu.addEventListener('click', event => {
  const action = event.target.closest('[data-do]')?.dataset.do;
  hideMenu();
  if (action) attempt(() => act(action));
});

document.addEventListener('keydown', event => {
  if (editing || !active()) return;
  if (event.key === 'Escape') {hideMenu(); return;}
  if (!menu.hidden) return;
  const list = tiles();
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {
    event.preventDefault();
    picked = new Set(list.map(tile => tile.dataset.name));
    paintPicks();
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c') {event.preventDefault(); attempt(() => act('copy')); return;}
  if (event.key === 'Enter') {event.preventDefault(); attempt(() => act('open')); return;}
  if (event.key === 'F2') {event.preventDefault(); attempt(() => act('rename')); return;}
  if (event.key === 'Delete') {event.preventDefault(); attempt(() => act('delete')); return;}
  const step = {ArrowRight: 1, ArrowLeft: -1}[event.key];
  if (step && list.length) {
    event.preventDefault();
    const at = list.findIndex(tile => tile.dataset.name === anchor);
    const next = list[Math.min(Math.max(at + step, 0), list.length - 1)];
    pick(next.dataset.name, {range: event.shiftKey});
    next.focus();
  }
});

$('new-capture').addEventListener('click', () => attempt(async () => {
  // 패널은 접고 찍는다 — 캡처 화면에 패널이 찍히지 않게. 다 찍으면 데스크가 패널을 다시 연다
  if (embedded) await api('popover_close');
  await api('capture');
}));
$('open-folder').addEventListener('click', () => attempt(async () => {await api('capture_folder');}));

window.addEventListener('pywebviewready', () => {
  attempt(() => reload(true));
  setInterval(() => {if (active() && !document.hidden && !editing && !press) reload().catch(() => {});}, POLL);
});

})();
