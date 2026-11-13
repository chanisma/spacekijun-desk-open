'use strict';
// 독 위 정보 패널 — 독 아이콘(시간표·일정·업무·공지·알림·스티커 메모)을 누르면 그 내용을 여기에 보인다.
// 데스크가 deskPopover.show({key, caret}) 를 부른다 (desktop.py `_popover_open`). 닫기는 X·Esc.

const GLYPHS = {
  clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  check:'<rect x="4" y="3.5" width="16" height="17" rx="3"/><path d="m8 9 1.5 1.5L12 8M8 15l1.5 1.5L12 14M14.5 9.5H17M14.5 15.5H17"/>',
  megaphone:'<path d="M4 10v4a1 1 0 0 0 1 1h2l5 4V5L7 9H5a1 1 0 0 0-1 1ZM16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
  bell:'<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15ZM10 20.5a2 2 0 0 0 4 0"/>',
  note:'<path d="M5 3h14a2 2 0 0 1 2 2v9l-7 7H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 21v-5a2 2 0 0 1 2-2h5M7 8h10M7 12h6"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m4 7 8 6 8-6"/>',
  gear:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
  clipboard:'<rect x="5.5" y="4.5" width="13" height="16.5" rx="2.5"/><path d="M9 4.5V3.8A1.3 1.3 0 0 1 10.3 2.5h3.4A1.3 1.3 0 0 1 15 3.8v.7M9 10h6M9 13.5h6M9 17h3.5"/>',
  photos:'<rect x="7" y="3.5" width="13.5" height="11" rx="2"/><path d="M4.5 7.5v10a2 2 0 0 0 2 2h11"/><path d="m9.5 12 2.5-2.5 2 2 1.5-1.5 2.5 2.5"/>',
  terminal:'<rect x="2.5" y="4" width="19" height="16" rx="3"/><path d="m6.5 9.5 3 2.5-3 2.5M12 15h5"/>',
  wand:'<path d="M4 20 14.5 9.5"/><path d="m12.5 7.5 4 4"/><path d="M18 3v3.5M16.25 4.75h3.5M20.5 9.5v2.5M19.25 10.75h2.5M10 2.5v2.5M8.75 3.75h2.5"/>',
  folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  plug:'<path d="M9 3v5M15 3v5"/><path d="M6.5 8h11v3a5.5 5.5 0 0 1-11 0V8Z"/><path d="M12 16.5V21"/>',
  chat:'<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4h0A2.5 2.5 0 0 1 4 13.5Z"/><path d="M8 9h8M8 12h5"/>'
};
// 제목 · 아이콘 · 색 · 스페이스기전에서 전체 보기 경로 (dock.js 의 같은 아이콘과 짝)
const PANELS = {
  today:         {title: '오늘 시간표', glyph: 'clock', tone: 'cyan', route: '/timetable'},
  week:          {title: '이번 주 일정', calendar: true, tone: 'paper', route: '/schedule'},
  tasks:         {title: '나의 업무', glyph: 'check', tone: 'amber', route: '/tasks'},
  notices:       {title: '학교 공지', glyph: 'megaphone', tone: 'fuchsia', route: '/notices'},
  notifications: {title: '최근 알림', glyph: 'bell', tone: 'red', route: '/notifications'},
  notes:         {title: '스티커 메모', glyph: 'note', tone: 'yellow', page: 'notes'},
  inbox:         {title: '쪽지함', glyph: 'mail', tone: 'sky', page: 'inbox'},
  captures:      {title: '캡처 보관함', glyph: 'photos', tone: 'lavender'},
  clips:         {title: '클립보드', glyph: 'clipboard', tone: 'slate'},
  settings:      {title: '설정', glyph: 'gear', tone: 'silver', page: 'settings'},   // 교사판 '연결 및 설정' — 바닥 단추로 데스크의 큰 화면
  agent:         {title: '에이전트 터미널', glyph: 'terminal', tone: 'terminal'},
  automation:    {title: '자동화 업무', glyph: 'wand', tone: 'teal'},       // 교사판만 — 업무 스킬 폴더 (2026-10-22)
  messages:      {title: '메시지', glyph: 'chat', tone: 'blue'}
};
// 시간표·일정 패널의 보기 — 머리의 단추로 바꾸고, 고른 것을 기억한다 (2026-10-14 요청)
const VIEWS = {
  today: [['day', '오늘', '오늘 시간표'], ['week', '한 주 전체', '한 주 시간표']],
  week:  [['list', '목록', '이번 주 일정'], ['month', '달력', '일정 달력']]
};
const VIEW_KEY = 'desk.popover.views';
const view = {today: 'day', week: 'list'};
try {
  const saved = JSON.parse(localStorage.getItem(VIEW_KEY) || '{}');
  for (const name of Object.keys(view)) if (VIEWS[name].some(([id]) => id === saved[name])) view[name] = saved[name];
} catch {/* 기억이 없어도 기본 보기로 */}
const FRESH = 60000;          // 학교 정보는 1분 동안 다시 묻지 않는다 (대시보드와 같은 간격)
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let key = null, snapshot = null, fetchedAt = 0, loading = null, closing = false, staleNote = '';
let inboxRows = null, inboxAt = 0;          // 쪽지함 — 다시 열면 받아 둔 것부터 보인다

async function api(action, payload) {
  const result = await window.pywebview.api.call(action, payload || {});
  if (!result.ok) throw new Error(result.error || '요청을 처리하지 못했습니다.');
  return result.data;
}

// ── 모양 ─────────────────────────────────────────────────
function paintHead() {
  const panel = PANELS[key];
  $('title').textContent = panel.title;
  $('mark').className = `mark tone-${panel.tone}`;
  if (panel.calendar) {
    const now = new Date();
    $('mark').innerHTML = `<span class="cal"><small>${esc(new Intl.DateTimeFormat('ko-KR', {weekday: 'short'}).format(now))}</small><b>${now.getDate()}</b></span>`;
  } else {
    $('mark').innerHTML = `<svg viewBox="0 0 24 24">${GLYPHS[panel.glyph]}</svg>`;
  }
  // 패널마다 머리·바닥의 단추가 다르다 — 캡처 보관함은 captures.js 가 그리는 제 영역을 쓴다
  const captures = key === 'captures';
  $('add').hidden = key !== 'notes';
  $('new-capture').hidden = $('open-folder').hidden = !captures;
  $('sub').hidden = captures;
  $('summary').hidden = !captures;
  $('body').hidden = captures;
  $('captures-view').hidden = !captures;
  const clips = key === 'clips';
  $('clip-pause').hidden = !clips;
  $('clips-view').hidden = !clips;
  if (clips) $('body').hidden = true;
  $('msg-view').hidden = key !== 'messages';
  if (key === 'messages') $('body').hidden = true;
  $('hint').hidden = !captures;
  $('more').hidden = captures || key === 'settings' || key === 'agent' || key === 'automation' || key === 'messages';
  $('refresh').hidden = key === 'settings';
  $('more').textContent = panel.route ? '스페이스기전에서 전체 보기 →'
    : key === 'notes' ? '메모 목록 크게 보기 →' : key === 'clips' ? '모두 지우기 (고정한 것은 남김)' : '데스크에서 크게 보기 →';
  $('more').classList.remove('confirm');
  paintViews();
}

function paintViews() {
  const choices = VIEWS[key];
  $('views').hidden = !choices;
  if (!choices) return;
  $('title').textContent = choices.find(([id]) => id === view[key])[2];
  $('views').innerHTML = choices.map(([id, label]) =>
    `<button role="tab" data-view="${id}" aria-selected="${view[key] === id}">${esc(label)}</button>`).join('');
}

function place(caret) {
  // 꼭지를 아이콘 쪽에, 펼쳐지는 움직임도 아이콘에서 시작하게
  document.body.dataset.side = caret.side;
  document.body.style.setProperty('--at', `${caret.at}px`);
  const card = $('card'), vertical = caret.side === 'left' || caret.side === 'right';
  const at = vertical ? caret.at - 12 : caret.at - 12;       // 카드 안 좌표 (창 여백 12px)
  card.style.setProperty('--ox', vertical ? (caret.side === 'left' ? '0%' : '100%') : `${at}px`);
  card.style.setProperty('--oy', vertical ? `${at}px` : (caret.side === 'top' ? '0%' : '100%'));
  const shift = {bottom: ['0', '10px'], top: ['0', '-10px'], left: ['-10px', '0'], right: ['10px', '0']}[caret.side];
  card.style.setProperty('--dx', shift[0]);
  card.style.setProperty('--dy', shift[1]);
}

function sub(text) {$('sub').textContent = text;}
const shortDay = value => value ? `${Number(value.slice(5, 7))}.${Number(value.slice(8, 10))}` : '';
const weekday = value => new Intl.DateTimeFormat('ko-KR', {month: 'long', day: 'numeric', weekday: 'short'}).format(new Date(value + 'T00:00:00'));
const row = (lead, title, detail, tag = '', style = '', quiet = false) =>
  `<div class="row ${style}"><span class="lead${quiet ? ' quiet' : ''}">${esc(lead)}</span><div class="copy"><strong>${esc(title)}</strong>`
  + `${detail ? `<p>${esc(detail)}</p>` : ''}</div>${tag ? `<span class="tag">${esc(tag)}</span>` : ''}</div>`;
const empty = (title, text, button = '') => `<div class="empty"><strong>${esc(title)}</strong><span>${esc(text)}</span>${button}</div>`;

function render() {
  const body = $('body');
  if (key === 'notes') return;               // 메모는 loadNotes 가 그린다
  if (!snapshot) {body.innerHTML = '<div class="skeleton"></div>'.repeat(4); return;}
  if (snapshot.error) {
    body.innerHTML = empty('불러오지 못했습니다', snapshot.error,
      '<button class="pill" data-go="settings">연결 및 설정 열기</button>');
    return;
  }
  const data = snapshot, errors = data.errors || {};
  const failed = text => text ? `<div class="empty"><span>${esc(text)}</span></div>` : '';
  if (key === 'today' && view.today === 'week') {
    body.innerHTML = failed(errors.timetable) + weekTable(data);
    return;
  }
  if (key === 'week' && view.week === 'month') {
    body.innerHTML = monthCalendar(data);
    return;
  }
  if (key === 'today') {
    const rows = data.today || [];
    // 지금 진행 중인 것만 강조한다 (시작 뒤 50분 — 한 교시). 다 지난 일정을 '지금'으로 보이지 않게
    const minutes = time => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));
    const nowAt = new Date().getHours() * 60 + new Date().getMinutes();
    const current = rows.findIndex(item => item.time && nowAt >= minutes(item.time) && nowAt < minutes(item.time) + 50);
    body.innerHTML = failed(errors.timetable || errors.meetings) + (rows.length
      ? rows.map((item, index) => row(item.time || item.label, item.title, item.detail, item.time ? item.label : '',
          index === current ? 'now' : '')).join('')
      : empty('오늘은 수업과 일정이 없습니다', '편안한 하루 보내세요.'));
  }
  if (key === 'week') {
    const rows = data.week || [];
    let day = '';
    body.innerHTML = failed(errors.meetings || errors.tasks) + (rows.length ? rows.map(item => {
      const head = item.date !== day ? `<h2 class="day">${esc(weekday(item.date))}</h2>` : '';
      day = item.date;
      return head + row(item.time || '종일', item.title, '', item.label, '', !item.time);
    }).join('') : empty('이번 주 남은 일정이 없습니다', '일정과 업무 마감이 생기면 여기에 보입니다.'));
  }
  if (key === 'tasks') {
    const rows = data.tasks || [];
    body.innerHTML = failed(errors.tasks) + (rows.length
      ? rows.map(item => row(shortDay(item.date) || '—', item.title, item.detail, item.label,
          item.label === '기한 초과' ? 'overdue' : '', !item.date)).join('')
      : empty('진행할 업무가 없습니다', '맡은 업무가 생기면 마감일과 함께 보입니다.'));
    if (!errors.tasks) sub(`진행 중 ${rows.length}건 · ${updatedLabel()}`);
  }
  if (key === 'notices') {
    const rows = data.notices || [];
    body.innerHTML = failed(errors.notices) + (rows.length ? rows.map(item =>
      `<details><summary><span class="tag">${esc(item.department)}</span><strong>${esc(item.title)}</strong>`
      + `<small>${esc(shortDay(item.start_date))}–${esc(shortDay(item.end_date))}</small></summary><p>${esc(item.content)}</p></details>`).join('')
      : empty('게시 중인 학교 공지가 없습니다', '새 공지가 올라오면 여기에 보입니다.'));
  }
  if (key === 'notifications') {
    const rows = data.notifications || [];
    const day = iso => shortDay(new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Seoul'}).format(new Date(iso)));
    body.innerHTML = failed(errors.notifications) + (rows.length
      ? rows.map(item => row(item.is_read ? '확인' : '새 알림', item.title, item.message, day(item.created_at),
          item.is_read ? '' : 'unread', item.is_read)).join('')
      : empty('도착한 알림이 없습니다', '새 알림이 오면 여기에 보입니다.'));
  }
}

// ── 한 주 시간표 ─────────────────────────────────────────
// 요일 × 교시 표. 오늘 열과 지금 교시 칸을 칠한다. 토·일 수업이 있으면 그 열도 보인다.
const DAY_NAMES = ['', '월', '화', '수', '목', '금', '토', '일'];
const toKey = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
const minutesOf = time => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));

function weekTable(data) {
  const cells = data.timetable_week || [];
  if (!cells.length) return empty('등록된 시간표가 없습니다', '이번 학기 시간표가 올라오면 여기에 한 주 전체가 보입니다.');
  const periods = data.periods || {};
  const days = [1, 2, 3, 4, 5, ...[6, 7].filter(day => cells.some(cell => cell.day === day))];
  const last = Math.max(7, ...cells.map(cell => cell.period));
  const now = new Date(), today = now.getDay() || 7, nowAt = now.getHours() * 60 + now.getMinutes();
  const slot = {};
  for (const cell of cells) (slot[`${cell.day}-${cell.period}`] ||= []).push(cell);
  // 이번 주 날짜 — 머리에 '10.14' 처럼
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - today + 1);
  const dateOf = day => {const d = new Date(monday); d.setDate(monday.getDate() + day - 1); return `${d.getMonth() + 1}.${d.getDate()}`;};
  let html = `<table class="tt"><thead><tr><th class="p" scope="col"><span class="sr">교시</span></th>`
    + days.map(day => `<th scope="col"${day === today ? ' class="today"' : ''}>${DAY_NAMES[day]}<small>${dateOf(day)}</small></th>`).join('')
    + '</tr></thead><tbody>';
  for (let period = 1; period <= last; period++) {
    const start = periods[period];
    const current = start && nowAt >= minutesOf(start) && nowAt < minutesOf(start) + 50;
    html += `<tr><th class="p" scope="row">${period}${start ? `<small>${esc(start)}</small>` : ''}</th>`;
    for (const day of days) {
      const here = slot[`${day}-${period}`] || [];
      const classes = [day === today && 'today', day === today && current && here.length && 'now', !here.length && 'free'].filter(Boolean);
      const title = here.map(cell => [cell.title, cell.detail].filter(Boolean).join(' ')).join(' · ');
      html += `<td${classes.length ? ` class="${classes.join(' ')}"` : ''}${title ? ` title="${esc(title)}"` : ''}>`
        + here.map(cell => `<strong>${esc(cell.title)}</strong>${cell.detail ? `<small>${esc(cell.detail)}</small>` : ''}`).join('')
        + '</td>';
    }
    html += '</tr>';
  }
  return html + '</tbody></table>';
}

// ── 한 달 달력 ───────────────────────────────────────────
// 일요일부터 그달이 걸친 주(4~6주). 날짜를 누르면 아래에 그날 일정이 보인다. 일정은 데스크가 달마다 받아 둔다
// (`dashboard_month`), 업무 마감은 패널이 받아 둔 업무(snapshot.tasks)에서 더한다.
const months = {};             // 'YYYY-MM' → {data, at, error}
let monthAt = '', picked = '', monthLoading = null;
const monthOf = date => toKey(date).slice(0, 7);

function dayItems(dateKey) {
  const month = months[monthAt]?.data;
  const items = [...(month?.days?.[dateKey] || [])];
  for (const task of snapshot?.tasks || []) {
    if ((task.deadlines || []).includes(dateKey)) items.push({title: task.title, time: '', label: '업무 마감', kind: 'task'});
  }
  return items;
}

function monthCalendar() {
  const [year, month] = monthAt.split('-').map(Number);
  const first = new Date(year, month - 1, 1);
  const start = new Date(year, month - 1, 1 - first.getDay());
  const todayKey = toKey(new Date());
  const entry = months[monthAt] || {};
  const closed = new Set(entry.data?.closed || []);
  let html = `<div class="cal-nav"><button class="icon" data-month="-1" aria-label="지난달" title="지난달"><svg viewBox="0 0 24 24"><path d="m15 6-6 6 6 6"/></svg></button>`
    + `<strong>${year}년 ${month}월</strong>`
    + `<button class="icon" data-month="1" aria-label="다음달" title="다음달"><svg viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></svg></button>`
    + `${monthAt !== monthOf(new Date()) || picked !== todayKey ? '<button class="pill" data-month="0">오늘</button>' : ''}</div>`;
  html += '<table class="mc"><thead><tr>' + ['일', '월', '화', '수', '목', '금', '토']
    .map((name, index) => `<th scope="col"${index === 0 ? ' class="sun"' : index === 6 ? ' class="sat"' : ''}>${name}</th>`).join('') + '</tr></thead><tbody>';
  const weeks = Math.ceil((first.getDay() + new Date(year, month, 0).getDate()) / 7);   // 그달이 걸친 주만
  for (let week = 0; week < weeks; week++) {
    html += '<tr>';
    for (let index = 0; index < 7; index++) {
      const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + week * 7 + index);
      const dateKey = toKey(date), items = dayItems(dateKey);
      const classes = [date.getMonth() !== month - 1 && 'out', dateKey === todayKey && 'today', dateKey === picked && 'picked',
        (index === 0 || closed.has(dateKey)) && 'sun', index === 6 && !closed.has(dateKey) && 'sat'].filter(Boolean);
      const label = `${date.getMonth() + 1}월 ${date.getDate()}일${items.length ? `, 일정 ${items.length}개` : ''}`;
      html += `<td><button class="${classes.join(' ')}" data-day="${dateKey}" aria-label="${esc(label)}" aria-pressed="${dateKey === picked}">`
        + `<span class="n">${date.getDate()}</span>`
        + items.slice(0, 2).map(item => `<i class="k-${item.kind}">${esc(item.title)}</i>`).join('')
        + (items.length > 2 ? `<em>+${items.length - 2}</em>` : '') + '</button></td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  // 고른 날의 일정
  const items = dayItems(picked);
  html += `<h2 class="day pick">${esc(weekday(picked))}${closed.has(picked) ? ' · 쉬는 날' : ''}</h2>`;
  if (entry.error) html += `<div class="empty"><span>${esc(entry.error)}</span></div>`;
  else if (!entry.data) html += '<div class="skeleton"></div>';
  else if (!items.length) html += '<p class="none">이날은 일정이 없습니다.</p>';
  html += items.map(item => row(item.time || '종일', item.title, '', item.label, item.kind === 'task' ? 'task' : '', !item.time)).join('');
  return html;
}

async function loadMonth(force = false) {
  const asked = monthAt, entry = months[asked];
  if (!force && entry?.data && Date.now() - entry.at < 300000) return;
  if (monthLoading?.month === asked) return monthLoading.done;
  $('refresh').classList.add('spin');
  const done = (async () => {
    try {months[asked] = {data: await api('dashboard_month', {month: asked, force}), at: Date.now()};}
    catch (error) {if (!months[asked]?.data) months[asked] = {error: error.message, at: 0};}
    finally {
      if (monthLoading?.month === asked) {monthLoading = null; $('refresh').classList.remove('spin');}
    }
    if (key === 'week' && view.week === 'month' && monthAt === asked) render();
  })();
  monthLoading = {month: asked, done};
  return done;
}

function resetMonth() {
  picked = toKey(new Date());
  monthAt = picked.slice(0, 7);
}

function updatedLabel() {
  if (!fetchedAt) return '';
  const minutes = Math.round((Date.now() - fetchedAt) / 60000);
  return minutes < 1 ? '방금 확인' : `${minutes}분 전 확인`;
}
function defaultSub() {
  const today = new Intl.DateTimeFormat('ko-KR', {month: 'long', day: 'numeric', weekday: 'long'}).format(new Date());
  const when = [updatedLabel(), staleNote].filter(Boolean).join(' · ');
  if (key === 'today' && view.today === 'week') {
    const hours = (snapshot?.timetable_week || []).length;
    return [hours ? `이번 학기 · 주 ${hours}시간` : '이번 학기 시간표', when].filter(Boolean).join(' · ');
  }
  if (key === 'today') return when ? `${today} · ${when}` : today;
  if (key === 'week' && view.week === 'month') return '날짜를 누르면 그날 일정이 아래에 보입니다';
  return when || '불러오는 중…';
}

// ── 불러오기 ─────────────────────────────────────────────
async function loadSnapshot(force = false) {
  if (!force && snapshot && !snapshot.error && Date.now() - fetchedAt < FRESH) return;
  if (loading) return loading;
  $('refresh').classList.add('spin');
  loading = (async () => {
    try {snapshot = await api('dashboard', {force}); fetchedAt = Date.now(); staleNote = '';}
    catch (error) {
      // 보이던 내용이 있으면 지우지 않는다 — 조금 지난 정보가 빈 화면보다 낫다
      if (snapshot && !snapshot.error) staleNote = '새로 받지 못했습니다';
      else {snapshot = {error: error.message}; fetchedAt = 0;}
    }
    finally {loading = null; $('refresh').classList.remove('spin');}
  })();
  return loading;
}

/** 데스크가 미리 받아 둔 학교 정보를 기다리지 않고 가져온다 (없으면 그대로) */
async function useQuick() {
  try {
    const quick = await api('dashboard_quick');
    if (quick && (!snapshot || snapshot.error || Date.now() - fetchedAt > quick.age * 1000)) {
      snapshot = quick.data;
      fetchedAt = Date.now() - quick.age * 1000;
    }
  } catch {/* 없으면 받아 온다 */}
}

async function loadNotes() {
  $('refresh').classList.add('spin');
  try {
    const notes = await api('sticky_list');
    sub(notes.length ? `메모 ${notes.length}개 · 나만 볼 수 있어요` : '나만 볼 수 있어요');
    $('body').innerHTML = notes.length ? `<div class="notes">${notes.map(item => {
      const when = new Date(item.updated_at).toLocaleString('ko-KR', {month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit'});
      // 메모 서식 표시는 떼고 보인다 — '# 제목' 은 제목만, '- 목록' 은 • 로
      const lines = String(item.content || '').split('\n').map(line => line.trim()).filter(Boolean)
        .map(line => line.replace(/^#{1,3}\s+/, '').replace(/^[-*•]\s+/, '• '));
      const title = (lines[0] || '메모').replace(/^•\s+/, '');
      return `<button class="note" data-note="${esc(item.id)}" data-color="${esc(item.color || '#fff176')}">`
        + `<strong>${esc(title)}</strong><span>${esc(lines.slice(1).join('\n'))}</span><small>${esc(when)}</small></button>`;
    }).join('')}</div>` : empty('아직 메모가 없습니다', '‘＋ 새 메모’를 눌러 바탕화면에 붙여 둘 메모를 만들어 보세요.');
    // 화면 보안 규칙(CSP)이 style 속성을 막아 색은 여기서 칠한다
    $('body').querySelectorAll('.note').forEach(el => el.style.setProperty('--note', el.dataset.color));
  } catch (error) {
    $('body').innerHTML = empty('메모를 불러오지 못했습니다', error.message,
      '<button class="pill" data-go="settings">연결 및 설정 열기</button>');
  } finally {
    $('refresh').classList.remove('spin');
  }
}

function renderInbox() {
  const rows = inboxRows || [];
  sub(rows.length ? `최근 쪽지 ${rows.length}건` : '쪽지');
  $('body').innerHTML = rows.length ? rows.map(item =>
    `<details class="msg"><summary><div class="who"><strong>${esc(item.who)}</strong><span>${esc(item.body)}</span></div>`
    + `<div class="side"><small>${esc(item.time)}</small><span class="tag">${esc(item.kind)}${item.status ? ' · ' + esc(item.status) : ''}</span></div>`
    + `</summary><p>${esc(item.body)}</p></details>`).join('')
    : empty('아직 표시할 쪽지가 없어요', '쿨메신저가 켜져 있는지 확인한 뒤 새로고침해 주세요.');
}

async function loadInbox(force = false) {
  if (inboxRows) renderInbox();                // 받아 둔 것부터 바로
  else $('body').innerHTML = '<div class="skeleton"></div>'.repeat(4);
  if (!force && inboxRows && Date.now() - inboxAt < 30000) return;
  $('refresh').classList.add('spin');
  try {
    const rows = await api('inbox');
    inboxRows = rows; inboxAt = Date.now();
    if (key === 'inbox') renderInbox();
  } catch (error) {
    if (key === 'inbox' && !inboxRows) $('body').innerHTML = empty('쪽지를 불러오지 못했습니다', error.message);
    else sub('새로 받지 못했습니다');
  } finally {
    $('refresh').classList.remove('spin');
  }
}

// ── 클립보드 기록 ─────────────────────────────────────────
// 복사한 것들 (desktop.py `_clips_*`). 누르면 다시 클립보드에 — 그다음 Ctrl+V.
let clipVersion = null, clipQueryWas = null, clipPausedWas = null, clipTimer = 0, clipItems = [];
const CLIP_ICONS = {
  pin: '<path d="M14.5 3.5 20.5 9.5M16 5l-5 5-4-.5-2 2 7 7 2-2-.5-4 5-5M8.5 15.5 3.5 20.5"/>',
  del: '<path d="M7 7l10 10M17 7 7 17"/>',
  file: '<path d="M7 3h7l4 4v14H7Z"/><path d="M14 3v4h4"/>'
};
const svg = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${CLIP_ICONS[name]}</svg>`;

function notify(message, error = false) {
  const toast = $('toast');
  toast.textContent = message;
  toast.classList.toggle('error', error);
  toast.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => {toast.hidden = true;}, error ? 4000 : 2200);
}

function clipWhen(iso) {
  const when = new Date(iso), minutes = Math.round((Date.now() - when) / 60000);
  if (minutes < 1) return '방금';
  if (minutes < 60) return `${minutes}분 전`;
  const today = new Date().toDateString() === when.toDateString();
  return today ? when.toLocaleTimeString('ko-KR', {hour: 'numeric', minute: '2-digit'})
               : `${when.getMonth() + 1}.${when.getDate()}`;
}

function renderClips(paused) {
  const list = $('clip-list');
  const note = paused ? '<p class="paused-note">기록을 멈춰 두었습니다. 위의 ▶ 를 누르면 다시 모읍니다.</p>' : '';
  if (!clipItems.length) {
    list.innerHTML = note + ($('clip-q').value.trim()
      ? empty('찾는 기록이 없습니다', '다른 말로 찾아 보세요.')
      : empty('아직 모인 것이 없습니다', 'Ctrl+C 로 복사한 글·그림·파일이 여기에 차곡차곡 모입니다.'));
    return;
  }
  list.innerHTML = note + clipItems.map(item => {
    let face, kind;
    if (item.kind === 'text') {
      face = `<p class="clip-text">${esc(item.text)}</p>`;
      kind = `글 ${item.length.toLocaleString()}자`;
    } else if (item.kind === 'image') {
      face = `<img src="${item.thumb}" alt="">`;
      kind = `그림 ${item.width}×${item.height}`;
    } else {
      face = `<div class="clip-files">${item.files.map(name => `<span>${svg('file')}${esc(name)}</span>`).join('')}`
        + `${item.count > item.files.length ? `<small>외 ${item.count - item.files.length}개</small>` : ''}</div>`;
      kind = `파일 ${item.count}개`;
    }
    return `<div class="clip${item.pinned ? ' pinned' : ''}" data-id="${esc(item.id)}">`
      + `<button class="clip-main" data-copy title="누르면 다시 복사합니다">${face}</button>`
      + `<div class="clip-meta"><span class="kind">${esc(kind)} · ${esc(clipWhen(item.time))}</span>`
      + `<button class="clip-act" data-pin aria-pressed="${item.pinned}" title="${item.pinned ? '고정 풀기' : '고정 — 지워도 남깁니다'}">${svg('pin')}</button>`
      + `<button class="clip-act" data-del title="이 기록 지우기">${svg('del')}</button></div></div>`;
  }).join('');
}

async function loadClips(force = false) {
  const query = $('clip-q').value.trim();
  try {
    const data = await api('clips_list', force ? {query} : {query, since: clipVersion, query_was: clipQueryWas,
                                                              paused_was: clipPausedWas});
    if (key !== 'clips' || data.same) return;
    clipVersion = data.version; clipQueryWas = query; clipPausedWas = data.paused; clipItems = data.items;
    sub(data.paused ? '기록 멈춤' : `기록 중 · ${clipItems.length}개`);
    $('clip-pause').setAttribute('aria-pressed', String(data.paused));
    $('clip-pause').title = data.paused ? '다시 기록하기' : '기록 멈추기';
    $('clip-pause').innerHTML = data.paused ? '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7Z"/></svg>'
                                            : '<svg viewBox="0 0 24 24"><path d="M9 6v12M15 6v12"/></svg>';
    renderClips(data.paused);
  } catch (error) {
    if (key === 'clips') $('clip-list').innerHTML = empty('기록을 불러오지 못했습니다', error.message);
  }
}

function watchClips() {
  clearInterval(clipTimer);
  // 패널을 보는 동안 새로 복사한 것이 바로 나타나게. 바뀐 것이 없으면 데스크가 목록을 다시 보내지 않는다
  clipTimer = setInterval(() => {
    if (key === 'clips' && !$('card').hidden && !closing) loadClips().catch(() => {});
    else clearInterval(clipTimer);
  }, 1500);
}

$('clip-q').addEventListener('input', () => {
  clearTimeout(loadClips.typing);
  loadClips.typing = setTimeout(() => loadClips(true), 200);
});
$('clip-pause').addEventListener('click', async () => {
  try {notify(await api('clips_pause', {paused: $('clip-pause').getAttribute('aria-pressed') !== 'true'})); await loadClips(true);}
  catch (error) {notify(error.message, true);}
});
$('clip-list').addEventListener('click', async event => {
  const box = event.target.closest('.clip');
  if (!box) return;
  const id = box.dataset.id;
  try {
    if (event.target.closest('[data-pin]')) {
      await api('clips_pin', {id, pinned: !box.classList.contains('pinned')});
    } else if (event.target.closest('[data-del]')) {
      await api('clips_delete', {id});
    } else if (event.target.closest('[data-copy]')) {
      box.classList.remove('copied'); void box.offsetWidth; box.classList.add('copied');
      notify(await api('clips_copy', {id}));
    }
    await loadClips(true);
  } catch (error) {notify(error.message, true);}
});

// ── 설정 (학생판·교사판) ─────────────────────────────────────
// 독 위 패널 하나로 계정 · 자동 로그인 · 독 아이콘 · 단축키 · 자동 실행 · 업데이트를 본다.
// 학생판에서 시작했고 교사판 '연결 및 설정'도 같은 패널이다 (2026-10-19 요청). 교사판은 쿨메신저 ·
// 쪽지 알림 · 인증서를 더 보이고, 바닥 단추로 데스크의 큰 설정 화면을 연다 (desktop.py `_settings_panel`).
let settingsTimer = 0, settingsEdition = 'student', cmNote = '';
const switchRow = (title, note, name, on, disabled = false) =>
  `<div class="set-row"><div class="copy"><strong>${esc(title)}</strong><small>${esc(note)}</small></div>`
  + `<input type="checkbox" class="switch" data-set="${name}"${on ? ' checked' : ''}${disabled ? ' disabled' : ''} aria-label="${esc(title)}"></div>`;
// 저장해 두는 로그인 한 벌 — 누르면 아래에 입력 칸이 펼쳐진다. 비밀번호 칸을 비우고 저장하면 있던 것을 그대로 둔다
const loginBox = (target, label, note, saved, fields) => `<div class="set-login" data-target="${esc(target)}">`
  + `<div class="set-row"><div class="copy"><strong>${esc(label)}</strong><small>${note}</small></div>`
  + (saved ? `<button class="pill quiet" data-set="forget">지우기</button>` : '')
  + `<button class="pill" data-set="edit">${saved ? '바꾸기' : '저장'}</button></div>`
  + `<form class="login-form" hidden autocomplete="off">${fields}`
  + `<div class="login-actions"><button type="button" class="pill quiet" data-set="cancel">취소</button><button type="submit" class="pill">저장</button></div></form></div>`;
const field = (name, placeholder, value = '', secret = false) => secret
  ? `<input name="${name}" type="password" placeholder="${esc(placeholder)}" autocomplete="new-password">`
  : `<input name="${name}" placeholder="${esc(placeholder)}" value="${esc(value)}" autocomplete="off" spellcheck="false">`;

// 나이스·업무포털·에듀파인을 띄울 브라우저 — Chrome 은 테스트 기능 (2026-10-23). 설치 안 된 것은 고를 수 없다
function browserRow(info) {
  if (!info) return '';
  const chrome = info.choice === 'chrome';
  return `<div class="set-gap"></div><div class="set-row"><div class="copy"><strong>브라우저 (테스트)</strong>`
    + `<small>${chrome ? 'Chrome 은 시험 중입니다. 처음 열 때 "로컬 네트워크 접근" 물음에 허용을 눌러 주세요.' : '나이스·업무포털·에듀파인을 여는 브라우저입니다.'}</small></div>`
    + `<select data-set="browser" aria-label="브라우저">${info.choices.map(choice => `<option value="${esc(choice.key)}"`
      + `${choice.key === info.choice ? ' selected' : ''}${choice.installed ? '' : ' disabled'}>`
      + `${esc(choice.label)}${choice.key === 'chrome' ? ' (테스트)' : ''}${choice.installed ? '' : ' — 설치 안 됨'}</option>`).join('')}</select></div>`;
}

function updateRow(info) {
  if (!info) return '';
  const action = info.ready
    ? `<button class="pill" data-set="update-apply"${info.available ? '' : ' disabled'}>지금 업데이트</button>`
    : `<button class="pill" data-set="update-check"${info.available && !info.checking ? '' : ' disabled'}>${info.checking ? '확인하는 중…' : '업데이트 확인'}</button>`;
  const note = info.ready ? `새 판 ${info.ready} 을 받아 두었어요. 누르면 잠깐 꺼졌다가 새 판으로 켜집니다.`
    : info.note || '새 판은 저절로 받아 두었다가 쉬는 틈에 바꿉니다.';
  // 관리자만 — 테스트 판 받기 (2026-10-30)
  const test = info.admin ? `<div class="set-gap"></div>` + switchRow('테스트 판 받기 (관리자)',
    info.test ? '정식 판보다 먼저 나오는 테스트 판도 받습니다.' : '켜면 관리자에게만 먼저 나오는 테스트 판을 받습니다.', 'update-test', info.test) : '';
  return `<section class="set-sec"><h2>프로그램 업데이트</h2><div class="set-row"><div class="copy"><strong>지금 ${esc(info.version)}</strong>`
    + `<small${info.failed ? ' class="bad"' : ''}>${esc(note)}</small></div>${action}</div>${test}</section>`;
}

async function loadSettings() {
  let data;
  try {data = await api('settings_panel');}
  catch (error) {
    // 프로그램은 옛 판인데 화면 파일만 새 판일 때 (소스로 켜 둔 채 코드를 받은 경우, 2026-10-19 학생 PC) —
    // 옛 이름(student_settings, 1.0.7 까지)으로 한 번 더 묻는다. 판은 독이 아는 것을 쓴다
    try {
      const [old, dock] = await Promise.all([api('student_settings'), api('dock_state')]);
      data = {edition: dock.edition || 'student', ...old};
    } catch {
      $('body').innerHTML = empty('설정을 불러오지 못했습니다', error.message);
      return;
    }
  }
  if (key !== 'settings') return;
  const teacher = data.edition === 'teacher';
  settingsEdition = data.edition;
  $('title').textContent = teacher ? '연결 및 설정' : '설정';
  $('more').hidden = !teacher;                 // 교사판 — 데스크의 큰 설정 화면 (활동 기록 등)
  $('more').textContent = '데스크에서 크게 보기 →';
  const hidden = new Set(data.hidden);
  const groups = (window.DOCK_SETS && window.DOCK_SETS[data.edition]) || [];
  const all = groups.flatMap(group => group.items);
  const watch = data.watch || {};
  sub(!data.user ? (teacher ? '스페이스기전 계정을 연결하면 쪽지 알림·답장을 받아요' : '스페이스기전 계정을 연결하면 시간표·일정이 보여요')
    : teacher ? `${data.user} · ${watch.error ? '쪽지 감시 확인 필요' : watch.watching ? '쪽지 감시 중' : '감시 준비 중'}`
    : `${data.user} 계정으로 연결됨`);
  const reach = teacher ? '쪽지 알림·답장과 프로그램 안 스페이스기전·시트온이' : '시간표·일정과 프로그램 안 스페이스기전·시트온이';
  const account = data.user
    ? `<div class="set-row"><div class="copy"><strong>${esc(data.user)}</strong><small>${reach} 이 계정으로 연결됩니다.</small></div><button class="pill" data-set="logout">로그아웃</button></div>`
    : `<div class="set-row"><div class="copy"><strong>연결하지 않음</strong><small>${data.auth_pending ? '브라우저에서 구글 로그인을 마쳐 주세요…' : '학교 구글 계정으로 한 번 로그인하면 이 기기에서 계속 연결됩니다.'}</small></div><button class="pill" data-set="login"${data.auth_pending ? ' disabled' : ''}>로그인</button></div>`;
  // 설정 아이콘은 숨길 수 없다 — 숨기면 이 패널로 돌아올 길이 없다 (desktop.py DOCK_ALWAYS)
  const chips = all.map(item => `<button class="chip" data-chip="${esc(item.id)}" aria-pressed="${!hidden.has(item.id)}"${item.id === 'settings' ? ' disabled title="설정은 늘 독에 둡니다"' : ''}>`
    + `<span class="chip-tile tone-${esc(item.tone)}">${window.dockFace(item)}</span><span>${esc(item.label)}</span></button>`).join('');
  const hotkey = data.hotkey;
  // 리로스쿨·AIEP·연수포털(교사판) — 저장해 두면 독에서 누를 때 자동으로 로그인한다
  const logins = Object.entries(data.accounts || {}).map(([target, info]) => loginBox(target, info.label,
    info.saved ? `${esc(info.id)} · 자동 로그인` : '저장 안 함 · 열기만 합니다', info.saved,
    field('id', target === 'aiep' ? 'AIEP 아이디 (@ai.jbedu.kr 앞부분)' : target === 'jbstudy' ? '연수포털 아이디'
      : teacher ? '리로스쿨 아이디 또는 이메일' : '학교 아이디', info.id || '')
    + field('password', '비밀번호', '', true))).join('');
  let teacherPart = '';
  if (teacher) {
    const cert = data.cert || {};
    const coolmsg = data.coolmsg || {};
    const names = coolmsg.accounts || [];
    const accountNote = coolmsg.ok === false ? coolmsg.why : coolmsg.warn || `${coolmsg.account || '확인 중'} 계정의 쪽지를 읽습니다.`;
    teacherPart = `<section class="set-sec"><h2>쿨메신저</h2><div class="set-row"><div class="copy"><strong>답장 연동</strong>`
      + `<small>${esc(cmNote || '누르면 설치된 쿨메신저를 연동 모드로 실행합니다.')}</small></div>`
      + `<button class="pill quiet" data-set="cm-check">상태 확인</button><button class="pill" data-set="cm-prepare">연결</button></div></section>`
      + `<section class="set-sec"><h2>쪽지 알림</h2>`
      + switchRow('긴 쪽지 요약하기', '긴 본문을 Solar로 요약해 알림에 보입니다.', 'summary', watch.summary !== false)
      + `<div class="set-gap"></div>` + switchRow('알림에 본문 포함', '끄면 보낸 사람만 알림에 보입니다.', 'body', watch.body !== false)
      + `<div class="set-gap"></div><div class="set-row"><div class="copy"><strong>쪽지 계정</strong><small${coolmsg.ok === false || coolmsg.warn ? ' class="bad"' : ''}>${esc(accountNote)}</small></div>`
      + `<select data-set="coolmsg" aria-label="쪽지 계정"><option value="">자동 (최근 사용)</option>`
      + names.map(name => `<option value="${esc(name)}"${name === coolmsg.fixed ? ' selected' : ''}>${esc(name)}</option>`).join('') + `</select></div></section>`
      + `<section class="set-sec"><h2>인증서 자동 로그인 · 나이스·업무포털·에듀파인</h2>`
      + loginBox('cert', cert.saved ? (cert.name || '인증서') : '저장 안 함',
                 cert.saved ? `${esc(cert.id)} · 자동 로그인` : '아이디와 인증서 암호를 저장하면 독에서 바로 로그인합니다.', cert.saved,
                 field('user', '업무포털 아이디', cert.id || '') + field('cert_name', '인증서 사용자 이름 (예: 홍길동)', cert.name || '')
                 + field('password', cert.saved ? '인증서 암호 (바꿀 때만)' : '인증서 암호', '', true))
      + `<p class="set-note">이름이 들어간 인증서를 고릅니다. 비우면 인증서가 하나일 때만 자동으로 고릅니다.</p>`
      + browserRow(data.browser) + `</section>`;
  }
  $('body').innerHTML = `<section class="set-sec"><h2>스페이스기전 계정</h2>${account}</section>`
    + teacherPart
    + (logins ? `<section class="set-sec"><h2>자동 로그인</h2>${logins}<p class="set-note">이 기기에만 암호화해 저장합니다. 비밀번호가 틀리면 한 번만 시도하고 멈춥니다 (리로스쿨은 5번 틀리면 잠깁니다).</p></section>` : '')
    + `<section class="set-sec"><h2>독에 보일 아이콘</h2><div class="chips">${chips}</div></section>`
    + `<section class="set-sec"><h2>독 불러오기 단축키</h2><div class="set-row"><div class="copy"><small>${hotkey.combo !== 'off' && !hotkey.active ? '다른 프로그램이 이 조합을 쓰고 있어요. 다른 조합을 골라 주세요.' : '다른 창에 가려진 독을 어디서든 앞으로 불러요.'}</small></div>`
    + `<select data-set="hotkey">${hotkey.choices.map(choice => `<option value="${esc(choice.key)}"${choice.key === hotkey.combo ? ' selected' : ''}>${esc(choice.label)}</option>`).join('')}</select></div></section>`
    + `<section class="set-sec">${switchRow('Windows 로그인 시 자동 실행', data.startup_managed ? '학교에서 관리합니다 — 컴퓨터를 켤 때 독이 함께 뜹니다.'
        : teacher ? '켜 두면 Windows 에 로그인할 때 트레이에서 조용히 시작합니다.' : '켜 두면 컴퓨터를 켤 때 독이 함께 뜹니다.', 'startup', data.startup, data.startup_managed)}</section>`
    // 별사이 목장 (학생판, 2026-11-06) — 독 위 띠의 아기 동물 목장
    + ('ranch' in data ? `<section class="set-sec">${switchRow('별사이 목장 보이기', '독 위(독이 아래 가로가 아니면 바탕화면 아래)에 작은 목장을 띄웁니다. 수업 시간에는 보기만 돼요.', 'ranch', data.ranch)}</section>` : '')
    + updateRow(data.update)
    + (teacher ? '' : `<p class="set-note">스페이스기전 학생 · 교사용 기능(나이스·업무포털·쪽지 등)은 들어 있지 않습니다.</p>`);
  $('body').querySelectorAll('.cal').forEach(cal => {
    const now = new Date();
    cal.querySelector('small').textContent = new Intl.DateTimeFormat('ko-KR', {weekday: 'short'}).format(now);
    cal.querySelector('b').textContent = now.getDate();
  });
  // 로그인은 브라우저에서, 업데이트 확인은 뒤에서 끝나므로 패널을 보는 동안 가끔 다시 묻는다.
  // 입력 칸을 펼쳐 두었으면 다시 그리지 않는다 — 치던 것이 사라진다
  clearTimeout(settingsTimer);
  if (data.auth_pending || data.update?.checking) settingsTimer = setTimeout(function again() {
    if (key !== 'settings' || $('card').hidden) return;
    if ($('body').querySelector('.login-form:not([hidden])')) {settingsTimer = setTimeout(again, 2000); return;}
    loadSettings();
  }, data.auth_pending ? 2000 : 1000);
}

const DISCONNECT_LABEL = {cert: '인증서', riro: '리로스쿨', aiep: '전북 AIEP', jbstudy: '연수포털'};
$('body').addEventListener('click', async event => {
  if (key !== 'settings') return;
  const chip = event.target.closest('[data-chip]');
  const button = event.target.closest('button[data-set]');
  const action = button?.dataset.set;
  try {
    if (chip) {
      const chips = [...$('body').querySelectorAll('[data-chip]')];
      const turnOff = chip.getAttribute('aria-pressed') === 'true';
      if (turnOff && chips.filter(c => c.getAttribute('aria-pressed') === 'true').length === 1) {
        notify('아이콘을 적어도 하나는 남겨 주세요.', true);
        return;
      }
      chip.setAttribute('aria-pressed', String(!turnOff));
      const hidden = chips.filter(c => c.getAttribute('aria-pressed') === 'false').map(c => c.dataset.chip);
      notify(await api('dock_items_save', {hidden, total: chips.length}));
    } else if (action === 'login') {
      notify(await api('auth', {}));
      await loadSettings();
    } else if (action === 'logout') {
      notify(await api('auth', {logout: true}));
      await loadSettings();
    } else if (action === 'edit' || action === 'cancel') {
      const form = event.target.closest('.set-login').querySelector('.login-form');
      form.hidden = action === 'cancel';
      // 비어 있는 첫 칸으로 — 아이디가 이미 있으면 비밀번호 칸
      if (!form.hidden) ([...form.querySelectorAll('input')].find(input => !input.value) || form.querySelector('input')).focus();
    } else if (action === 'forget') {
      const target = event.target.closest('.set-login').dataset.target;
      if (settingsEdition === 'teacher') {
        // 교사판은 데스크 설정과 같이 브라우저에 남은 로그인까지 지운다 (`_disconnect`) — 한 번 묻는다
        const extra = target === 'cert' ? '' : '\n브라우저에 남은 로그인도 함께 지웁니다.';
        if (!window.confirm(`${DISCONNECT_LABEL[target]} 연결을 해제할까요?\n저장된 아이디와 비밀번호를 이 PC에서 지웁니다.${extra}`)) return;
        notify(await api('disconnect', {target}));
      } else {
        notify(await api('student_account_forget', {target}));
      }
      await loadSettings();
    } else if (action === 'cm-check' || action === 'cm-prepare') {
      button.disabled = true;
      cmNote = action === 'cm-check' ? '쿨메신저 연결을 확인하고 있습니다…' : '쿨메신저 연결을 준비하고 있습니다…';
      button.closest('.set-row').querySelector('small').textContent = cmNote;
      if (action === 'cm-check') cmNote = await api('check_cm');
      else {
        let result = await api('prepare_cm');
        if (result.needs_restart) {
          if (!window.confirm(result.message + '\n\n저장하지 않은 내용은 사라질 수 있습니다. 저장을 마쳤다면 확인을 눌러 다시 실행해 주세요.')) {
            cmNote = result.message;
            await loadSettings();
            return;
          }
          result = await api('prepare_cm', {restart: true});
        }
        cmNote = result.message;
      }
      notify(cmNote);
      await loadSettings();
    } else if (action === 'update-check') {
      await api('update_check');
      await loadSettings();
    } else if (action === 'update-apply') {
      const info = await api('update_status');
      const warn = info.busy ? `${info.busy}. 다시 켜지면서 닫힙니다.\n\n` : '';
      if (!window.confirm(`${warn}새 판 ${info.ready || ''} 으로 바꾸고 다시 켤까요?`)) return;
      button.disabled = true;
      notify(await api('update_apply', {force: true}));
    }
  } catch (error) {
    if (action?.startsWith('cm-')) cmNote = error.message;
    notify(error.message, true);
    loadSettings();
  }
});
$('body').addEventListener('submit', async event => {
  if (key !== 'settings' || !event.target.matches('.login-form')) return;
  event.preventDefault();
  const form = event.target;
  const target = form.closest('.set-login').dataset.target;
  const value = name => form.elements[name].value;
  try {
    notify(target === 'cert'
      ? await api('save_credentials', {user: value('user'), cert_name: value('cert_name'), password: value('password')})
      : await api('student_account_save', {target, id: value('id'), password: value('password')}));
    form.elements.password.value = '';
    await loadSettings();
  } catch (error) {notify(error.message, true);}
});
$('body').addEventListener('change', async event => {
  if (key !== 'settings') return;
  const action = event.target.dataset.set;
  if (!['startup', 'hotkey', 'summary', 'body', 'coolmsg', 'browser', 'update-test'].includes(action)) return;   // 계정 입력 칸은 저장을 누를 때만
  try {
    if (action === 'startup') notify(await api('startup', {enabled: event.target.checked}));
    if (action === 'ranch') notify(await api('ranch_set', {on: event.target.checked}));
    if (action === 'update-test') notify(await api('update_test', {on: event.target.checked}));
    if (action === 'browser') notify(await api('browser_choice', {browser: event.target.value}));
    if (action === 'hotkey') notify(await api('dock_hotkey_save', {combo: event.target.value}));
    if (action === 'coolmsg') notify(await api('coolmsg_account', {account: event.target.value}));
    if (action === 'summary' || action === 'body') {
      const on = name => $('body').querySelector(`[data-set="${name}"]`).checked;
      notify(await api('options', {summary: on('summary'), body: on('body')}));
    }
  } catch (error) {notify(error.message, true);}
  loadSettings();
});

// ── 메시지 (학생 ↔ 선생님, 2026-10-19) ─────────────────────────
// 스페이스기전 알림으로 오간다 (desktop.py `_msg_*`, core/desk_message.py). 목록 → 대화 → 답장,
// '＋ 새 메시지'는 주소록에서 고른다 (학생은 선생님, 선생님은 학생). 받은 것은 대화를 열면 읽음으로.
let msgMode = 'list', msgThread = null, msgThreads = [], msgPeople = null, msgQuery = '', msgTimer = 0, msgSending = false;
// 사진 (2026-10-22) — 붙여넣기·끌어 놓기·사진 단추로 넣고, 여기서 줄여 보낸다. 받은·보낸 사진은 데스크가 이 PC 캡처 보관함에
// 파일로 남긴다(core/desk_message.py) — 지우는 것도 캡처 보관함에서. 서버에는 7일만 있다.
const MSG_PIC_MAX = 4, MSG_PIC_SIDE = 1600, MSG_PIC_BYTES = 1200 * 1024;
let msgPics = [];                       // 보낼 사진 {data, url} — url 은 data: (CSP 가 blob: 그림을 막는다)
const msgPhotos = new Map();            // 사진 id → 받은 결과 (다시 그릴 때 깜빡이지 않게)
// 처음 보낼 때 허락받기 (2026-10-31) — 학생은 대화가 진행 중인 선생님께만 보낸다. 막는 것은 서버이고 여기는 보이는 것만 맞춘다.
// msgSessions 가 null 이면 상태를 못 읽은 것 — 막지 않고 예전처럼 쓰는 칸을 둔다.
let msgRole = '', msgSessions = null, msgDeciding = false;
const msgStatus = id => (msgSessions ? msgSessions[id] || 'none' : 'active');
const msgAsking = () => msgRole === 'student' && msgMode === 'thread' && ['none', 'declined', 'ended'].includes(msgStatus(msgThread.id));
const MSG_CHIP = {student: {pending: '허락 대기', declined: '거절됨', ended: '종료됨'}, teacher: {pending: '허락 요청', ended: '종료됨'}};
const msgTime = value => {
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) return '';
  const clock = at.toLocaleTimeString('ko-KR', {hour: '2-digit', minute: '2-digit', hour12: false});
  return at.toDateString() === new Date().toDateString() ? clock : `${at.getMonth() + 1}.${at.getDate()} ${clock}`;
};
const personLabel = person => person.grade
  ? `${person.grade}학년 ${person.class}반 ${person.number ? person.number + '번 ' : ''}${person.name}` : `${person.name} 선생님`;
const initial = label => esc((label || '?').replace(/^\d+학년 \d+반 (\d+번 )?/, '').trim().charAt(0) || '?');

async function loadMessages(force = false) {
  if (msgMode === 'pick') return paintPeople();
  let data;
  try {data = await api('msg_state');}
  catch (error) {
    if (key === 'messages') {$('msg-list').innerHTML = empty('메시지를 불러오지 못했습니다', error.message); sub('');}
    return;
  }
  if (key !== 'messages') return;
  msgThreads = data.threads;
  msgRole = data.role || '';
  msgSessions = data.sessions || null;
  sub(data.unread ? `안 읽은 메시지 ${data.unread}건` : '선생님과 학생이 주고받는 메시지');
  if (msgMode === 'thread') {
    const found = msgThreads.find(thread => thread.id === msgThread.id);
    if (found) msgThread = {...found};
    paintThread(force);
  } else {
    paintList();
  }
}

// 머리 줄은 보기가 바뀔 때만 다시 그린다 — 찾기 칸을 글자마다 새로 만들면 한글 조합이 끊기고
// 커서가 튄다 (2026-10-19 보고). 목록만 바꿔 그린다.
let msgTopKey = '';
function paintTop() {
  const top = $('msg-top');
  const status = msgMode === 'thread' ? msgStatus(msgThread.id) : '';
  const canEnd = msgRole === 'teacher' && status === 'active' && msgSessions;
  const shape = msgMode + '|' + (msgMode === 'thread' ? `${msgThread.id}|${msgThread.label}|${canEnd ? 'end' : ''}` : '');
  $('msg-compose').hidden = msgMode !== 'thread' || status === 'pending';
  paintSession(status);
  if (shape === msgTopKey && top.childElementCount) return;
  msgTopKey = shape;
  if (msgMode === 'list') {
    top.innerHTML = '<button class="pill" data-msg="new">＋ 새 메시지</button>';
  } else if (msgMode === 'thread') {
    top.innerHTML = `<button class="icon" data-msg="back" aria-label="목록으로" title="목록으로"><svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg></button>`
      + `<strong class="msg-who">${esc(msgThread.label || '이름 없음')}</strong>`
      + (canEnd ? '<button class="pill msg-end" data-msg="end" title="종료하면 학생은 다시 허락을 구해야 메시지를 보낼 수 있습니다">대화 종료</button>' : '');
  } else {
    top.innerHTML = `<button class="icon" data-msg="back" aria-label="목록으로" title="목록으로"><svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg></button>`
      + `<label class="clip-search msg-search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></svg>`
      + `<input id="msg-q" type="search" placeholder="이름 · 학년 반 (예: 2 3)" aria-label="받는 사람 찾기" autocomplete="off" value="${esc(msgQuery)}"></label>`;
    $('msg-q').addEventListener('input', event => {msgQuery = event.target.value; paintPeople();});
    $('msg-q').focus({preventScroll: true});
  }
}

function paintSession(status) {
  const bar = $('msg-session');
  const asking = msgAsking();
  let html = '';
  if (status && msgRole === 'student') {
    html = {pending: '<span>선생님의 허락을 기다리고 있습니다. 허락하면 메시지를 보낼 수 있습니다.</span>',
            none: '<span>이 선생님께 처음 보내려면 허락이 필요합니다. 용건을 써서 요청하세요.</span>',
            declined: '<span>선생님이 요청을 거절했습니다. 필요하면 용건을 써서 다시 요청할 수 있습니다.</span>',
            ended: '<span>선생님이 대화를 종료했습니다. 다시 보내려면 용건을 써서 허락을 요청하세요.</span>'}[status] || '';
  } else if (status && msgRole === 'teacher') {
    html = {pending: '<span>이 학생이 메시지를 보내도 되는지 묻고 있습니다.</span><button class="pill" data-msg="approve">허락</button><button class="pill" data-msg="decline">거절</button>',
            declined: '<span>거절한 요청입니다. 메시지를 보내면 대화가 다시 열립니다.</span>',
            ended: '<span>종료한 대화입니다. 메시지를 보내면 대화가 다시 열립니다.</span>'}[status] || '';
  }
  bar.hidden = !html;
  if (bar.innerHTML !== html) bar.innerHTML = html;
  if (asking) clearPics();
  $('msg-attach').hidden = asking;
  $('msg-go').textContent = msgSending ? '보내는 중…' : asking ? '허락 요청' : '보내기';
  $('msg-text').placeholder = asking ? '선생님께 메시지를 보내려는 용건을 쓰세요 (Ctrl+Enter 요청)'
    : '메시지를 쓰세요 (Ctrl+Enter 보내기 · 사진은 붙여넣기·끌어 놓기)';
}

function paintList() {
  paintTop();
  $('msg-list').innerHTML = msgThreads.length ? msgThreads.map(thread => {
    const last = thread.messages[thread.messages.length - 1] || {};
    const chip = MSG_CHIP[msgRole]?.[msgStatus(thread.id)];
    return `<button class="msg-thread${thread.unread ? ' unread' : ''}" data-thread="${esc(thread.id)}">`
      + `<span class="msg-face">${initial(thread.label)}</span>`
      + `<span class="copy"><strong>${esc(thread.label || '이름 없음')}</strong><small>${last.mine ? '나: ' : ''}${esc((last.body || '').slice(0, 80))}</small></span>`
      + `<span class="msg-meta"><small>${esc(msgTime(last.time))}</small>${chip ? `<em class="msg-chip">${chip}</em>` : ''}${thread.unread ? `<b>${thread.unread}</b>` : ''}</span></button>`;
  }).join('') : empty('주고받은 메시지가 없습니다', '‘＋ 새 메시지’를 눌러 받는 사람을 고르세요.');
}

function paintThread(stick = false) {
  paintTop();
  const list = $('msg-list');
  const atBottom = stick || list.scrollHeight - list.scrollTop - list.clientHeight < 40;
  const messages = msgThread.messages || [];
  list.innerHTML = messages.length ? messages.map(message => message.kind === 'session_event'
    ? `<div class="msg-system">${esc(message.mine ? message.body.replace(/ (이제 메시지를 보낼 수 있습니다|다시 메시지를 보내려면 허락을 요청해 주세요)\.$/, '') : message.body)}<small>${esc(msgTime(message.time))}</small></div>`
    : `<div class="bubble${message.mine ? ' mine' : ''}">`
    + (message.kind === 'session_request' ? '<em>메시지 요청</em>' : '')
    + (message.quote ? `<q>${esc(message.quote)}</q>` : '')
    + photosHtml(message.images)
    + (message.photo_only ? '' : `<p>${esc(message.body)}</p>`)
    + `<small>${esc(msgTime(message.time))}${message.mine ? '' : message.replied ? ' · 답장함' : ''}</small></div>`).join('')
    : msgAsking() ? empty('먼저 허락을 요청하세요', '용건을 쓰고 ‘허락 요청’을 누르면 선생님이 보고 허락하거나 거절합니다.')
    : empty('첫 메시지를 보내 보세요', '아래 칸에 쓰고 보내기를 누르면 상대의 스페이스기전 알림으로 갑니다. 사진은 붙여넣거나 끌어 놓으세요.');
  fillPhotos(list);
  if (atBottom) list.scrollTop = list.scrollHeight;
  // 열어 본 받은 메시지는 읽음으로
  const unread = messages.filter(message => !message.mine && !message.read).map(message => message.id);
  if (unread.length) {
    messages.forEach(message => {if (unread.includes(message.id)) message.read = true;});
    api('msg_read', {ids: unread}).catch(() => {});
  }
}

async function paintPeople() {
  paintTop();
  const list = $('msg-list');
  if (!msgPeople) {
    list.innerHTML = '<div class="skeleton"></div>'.repeat(4);
    try {msgPeople = await api('msg_directory');}
    catch (error) {list.innerHTML = empty('주소록을 불러오지 못했습니다', error.message); return;}
    if (key !== 'messages' || msgMode !== 'pick') return;
  }
  sub(msgPeople.role === 'student' ? '선생님을 고르세요' : '학생을 고르세요 — 학년·반·이름으로 찾기');
  // 숫자는 쓴 차례대로 학년 → 반 → 번호 ('2 3' = 2학년 3반), 글자는 이름·'2학년' 같은 표시에서 찾는다
  const words = msgQuery.trim().split(/\s+/).filter(Boolean);
  const numbers = words.filter(word => /^\d+$/.test(word)).map(Number), names = words.filter(word => !/^\d+$/.test(word));
  const shown = msgPeople.people.filter(person => {
    const text = [person.grade && `${person.grade}학년`, person.class && `${person.class}반`, person.number && `${person.number}번`, person.name].filter(Boolean).join(' ');
    const slots = [person.grade, person.class, person.number].map(Number);
    return numbers.every((number, index) => index < 3 && slots[index] === number) && names.every(word => text.includes(word));
  });
  list.innerHTML = shown.length ? shown.slice(0, 150).map(person => `<button class="msg-thread" data-person="${esc(person.id)}" data-label="${esc(personLabel(person))}">`
    + `<span class="msg-face">${initial(person.name)}</span><span class="copy"><strong>${esc(personLabel(person))}</strong></span></button>`).join('')
    + (shown.length > 150 ? `<p class="set-note">${shown.length - 150}명 더 — 이름이나 학년·반을 더 넣어 좁혀 주세요.</p>` : '')
    : empty('찾는 사람이 없습니다', words.length ? '이름이나 학년·반을 다시 확인해 주세요.' : '');
}

// ── 말풍선 속 사진 ──
function photosHtml(images) {
  if (!images || !images.length) return '';
  return `<div class="msg-photos${images.length === 1 ? ' one' : ''}">` + images.map(pic =>
    `<button type="button" class="msg-photo" data-photo="${esc(pic.id)}" data-w="${pic.w || 0}" data-h="${pic.h || 0}" title="크게 보기">불러오는 중…</button>`).join('') + '</div>';
}
function showPhoto(el, result) {
  if (result.src) {
    el.innerHTML = `<img alt="" src="${esc(result.src)}">`;
    el.title = `크게 보기 — 캡처 보관함의 ‘${result.name}’`;
  } else {
    el.classList.add('gone');
    el.textContent = result.removed ? '캡처 보관함에서 지운 사진' : result.expired ? '7일이 지나 서버에서 지워진 사진' : '사진을 불러오지 못했습니다';
    el.title = '';
  }
}
function fillPhotos(list) {
  list.querySelectorAll('.msg-photo').forEach(el => {
    const w = Number(el.dataset.w), h = Number(el.dataset.h);
    if (w > 0 && h > 0) el.style.setProperty('--ratio', `${w}/${h}`);   // CSP 가 style 속성을 막아 여기서
    const id = el.dataset.photo;
    const known = msgPhotos.get(id);
    if (known && !(known instanceof Promise)) {showPhoto(el, known); return;}
    const job = known || api('msg_image', {id, label: msgThread?.label || ''})
      .catch(error => ({error: error.message}));
    msgPhotos.set(id, job);
    job.then(result => {
      if (!result.error) msgPhotos.set(id, result); else msgPhotos.delete(id);   // 실패는 다음에 다시
      const now = $('msg-list').querySelector(`.msg-photo[data-photo="${CSS.escape(id)}"]`);
      if (now) showPhoto(now, result);
    });
  });
}

// ── 사진 크게 보기 — 누르면 패널 안에서 크게, ‹ › 로 대화의 다른 사진, '사진 앱으로 열기' 로 원래 크기 ──
let viewerIds = [], viewerAt = 0, viewerAsk = 0;
function openViewer(id) {
  viewerIds = [...$('msg-list').querySelectorAll('.msg-photo')].filter(el => el.querySelector('img')).map(el => el.dataset.photo);
  viewerAt = Math.max(0, viewerIds.indexOf(id));
  $('msg-viewer').hidden = false;
  showViewer();
}
async function showViewer() {
  const id = viewerIds[viewerAt], ask = ++viewerAsk, img = $('msg-viewer-img');
  const known = msgPhotos.get(id);
  img.src = known && known.src ? known.src : '';                 // 미리보기를 먼저, 원본이 오면 바꾼다
  $('msg-viewer-count').textContent = viewerIds.length > 1 ? `${viewerAt + 1} / ${viewerIds.length}` : '';
  $('msg-viewer').querySelector('.prev').hidden = $('msg-viewer').querySelector('.next').hidden = viewerIds.length < 2;
  try {
    const full = await api('msg_image_full', {id});
    if (ask === viewerAsk && full.src) img.src = full.src;
    else if (ask === viewerAsk && full.removed) {closeViewer(); notify('캡처 보관함에서 지운 사진입니다.', true);}
  } catch (error) {if (ask === viewerAsk) notify(error.message, true);}
}
function stepViewer(by) {
  if (viewerIds.length < 2) return;
  viewerAt = (viewerAt + by + viewerIds.length) % viewerIds.length;
  showViewer();
}
function closeViewer() {
  viewerAsk++;
  $('msg-viewer').hidden = true;
  $('msg-viewer-img').removeAttribute('src');
}
$('msg-list').addEventListener('click', event => {
  const photo = event.target.closest('.msg-photo');
  if (photo && photo.querySelector('img')) openViewer(photo.dataset.photo);
});
$('msg-viewer').addEventListener('click', async event => {
  const action = event.target.closest('[data-viewer]')?.dataset.viewer;
  if (action === 'prev') stepViewer(-1);
  else if (action === 'next') stepViewer(1);
  else if (action === 'close' || event.target === $('msg-viewer') || event.target === $('msg-viewer-img')) closeViewer();   // 단추 말고 어디를 눌러도 닫는다
  else if (action === 'app') {
    try {await api('msg_image_open', {id: viewerIds[viewerAt]});}
    catch (error) {notify(error.message, true);}
  }
});
document.addEventListener('keydown', event => {
  if ($('msg-viewer').hidden) return;
  if (event.key === 'ArrowLeft') stepViewer(-1);
  else if (event.key === 'ArrowRight') stepViewer(1);
});

// ── 보낼 사진 ──
async function shrinkPicture(file) {
  // 긴 변 1600px, 1.2MB 안쪽으로. PNG(화면 캡처 등)는 그대로 들어가면 PNG 로, 안 되면 JPEG 로 줄인다
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) throw new Error('그림 파일이 아닙니다.');
  let scale = Math.min(1, MSG_PIC_SIDE / Math.max(bitmap.width, bitmap.height));
  let type = file.type === 'image/png' ? 'image/png' : 'image/jpeg';
  for (let tries = 0; tries < 8; tries++) {
    const w = Math.max(1, Math.round(bitmap.width * scale)), h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const g = canvas.getContext('2d');
    if (type === 'image/jpeg') {g.fillStyle = '#fff'; g.fillRect(0, 0, w, h);}   // 투명한 곳은 흰 바탕
    g.drawImage(bitmap, 0, 0, w, h);
    const blob = await new Promise(done => canvas.toBlob(done, type, 0.85));
    if (blob && blob.size <= MSG_PIC_BYTES) {
      const data = await new Promise((done, fail) => {
        const reader = new FileReader();
        reader.onload = () => done(String(reader.result).split(',')[1]);
        reader.onerror = () => fail(new Error('사진을 읽지 못했습니다.'));
        reader.readAsDataURL(blob);
      });
      bitmap.close();
      return {data, url: `data:${type};base64,${data}`};
    }
    if (type === 'image/png') type = 'image/jpeg'; else scale *= 0.8;
  }
  bitmap.close();
  throw new Error('사진을 충분히 줄이지 못했습니다.');
}
async function addPictures(files) {
  const images = [...files].filter(file => file && file.type.startsWith('image/'));
  if (!images.length) return;
  const room = MSG_PIC_MAX - msgPics.length;
  if (images.length > room) notify(`사진은 한 번에 ${MSG_PIC_MAX}장까지 보낼 수 있습니다.`, true);
  for (const file of images.slice(0, Math.max(0, room))) {
    try {msgPics.push(await shrinkPicture(file));}
    catch (error) {notify(error.message, true);}
  }
  paintPics();
}
function paintPics() {
  const strip = $('msg-pics');
  strip.hidden = !msgPics.length;
  strip.innerHTML = msgPics.map((pic, index) =>
    `<span class="msg-pic"><img alt="" src="${esc(pic.url)}"><button type="button" data-unpic="${index}" aria-label="이 사진 빼기" title="빼기">×</button></span>`).join('');
}
function clearPics() {
  msgPics = [];
  paintPics();
}
const msgTyping = () => key === 'messages' && msgMode === 'thread' && !$('card').hidden && !$('msg-compose').hidden && !msgAsking();
$('msg-pics').addEventListener('click', event => {
  const index = event.target.closest('[data-unpic]')?.dataset.unpic;
  if (index == null) return;
  msgPics.splice(Number(index), 1);
  paintPics();
});
$('msg-attach').addEventListener('click', () => $('msg-file').click());
$('msg-file').addEventListener('change', event => {addPictures(event.target.files); event.target.value = '';});
// 붙여넣기 — 대화를 보고 있으면 어디서 붙여도 (CLI 처럼 캡처한 그림을 바로)
document.addEventListener('paste', event => {
  if (!msgTyping()) return;
  const files = [...(event.clipboardData?.items || [])].filter(item => item.kind === 'file' && item.type.startsWith('image/'))
    .map(item => item.getAsFile());
  if (!files.length) return;
  event.preventDefault();
  addPictures(files);
});
// 끌어 놓기 — 패널 어디에 놓아도. 다른 화면에서는 파일을 놓아도 창이 그 파일로 넘어가지 않게만 막는다
let msgDrag = 0;
const hasFiles = event => [...(event.dataTransfer?.types || [])].includes('Files');
document.addEventListener('dragenter', event => {
  if (!hasFiles(event)) return;
  event.preventDefault();
  if (msgTyping() && ++msgDrag === 1) $('msg-view').classList.add('dropping');
});
document.addEventListener('dragover', event => {
  if (!hasFiles(event)) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = msgTyping() ? 'copy' : 'none';
});
document.addEventListener('dragleave', event => {
  if (hasFiles(event) && --msgDrag <= 0) {msgDrag = 0; $('msg-view').classList.remove('dropping');}
});
document.addEventListener('drop', event => {
  if (!hasFiles(event)) return;
  event.preventDefault();
  msgDrag = 0;
  $('msg-view').classList.remove('dropping');
  if (msgTyping()) addPictures(event.dataTransfer.files);
});

function openThread(id, label) {
  closeViewer();
  if (msgThread?.id !== id) clearPics();
  const found = msgThreads.find(thread => thread.id === id);
  msgThread = found ? {...found} : {id, label, messages: []};
  msgMode = 'thread';
  paintThread(true);
  $('msg-text').focus({preventScroll: true});
}

async function msgSessionAct(action) {
  if (msgDeciding || !msgThread) return;
  if (action === 'end' && !window.confirm(`${msgThread.label || '이 학생'}과의 대화를 종료할까요?\n학생은 다시 허락을 구해야 메시지를 보낼 수 있습니다.`)) return;
  msgDeciding = true;
  try {
    notify(await (action === 'end' ? api('msg_end', {to: msgThread.id})
      : api('msg_decide', {to: msgThread.id, approve: action === 'approve'})));
  } catch (error) {notify(error.message, true);}
  finally {msgDeciding = false;}
  await loadMessages(true);
}

$('msg-view').addEventListener('click', event => {
  const action = event.target.closest('[data-msg]')?.dataset.msg;
  const thread = event.target.closest('[data-thread]');
  const person = event.target.closest('[data-person]');
  if (action === 'approve' || action === 'decline' || action === 'end') {msgSessionAct(action); return;}
  if (action === 'new') {msgMode = 'pick'; msgQuery = ''; paintPeople();}
  else if (action === 'back') {msgMode = 'list'; msgThread = null; loadMessages();}
  else if (thread) {const found = msgThreads.find(item => item.id === thread.dataset.thread); openThread(found.id, found.label);}
  else if (person) openThread(person.dataset.person, person.dataset.label);
});
$('msg-text').addEventListener('input', () => {$('msg-count').textContent = `${$('msg-text').value.length}/1000`;});
$('msg-text').addEventListener('keydown', event => {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {event.preventDefault(); $('msg-compose').requestSubmit();}
});
$('msg-compose').addEventListener('submit', async event => {
  event.preventDefault();
  const body = $('msg-text').value.trim();
  if ((!body && !msgPics.length) || msgSending || !msgThread) return;
  // 답장이면 상대가 마지막으로 보낸 것을 인용한다 (그 알림에 '답장함'이 남는다)
  const replyTo = [...(msgThread.messages || [])].reverse().find(message => !message.mine && message.kind !== 'session_event')?.id;
  msgSending = true;
  $('msg-go').disabled = true;
  try {
    if (msgPics.length) $('msg-go').textContent = '보내는 중…';
    notify(await (msgAsking() ? api('msg_request', {to: msgThread.id, body})
      : api('msg_send', {to: msgThread.id, body, label: msgThread.label, reply_to: replyTo || null,
                         images: msgPics.length ? msgPics.map(pic => ({data: pic.data})) : null})));
    clearPics();
    $('msg-text').value = '';
    $('msg-count').textContent = '0/1000';
  } catch (error) {notify(error.message, true);}   // 그사이 종료됐을 수 있다 — 아래에서 상태를 다시 읽는다. 쓴 글은 둔다
  finally {msgSending = false; $('msg-go').disabled = false; paintTop();}
  await loadMessages(true);
});

// 새 메시지가 Realtime 으로 오면 데스크가 부른다 (desktop.py `_msg_changed`) — 보고 있으면 바로 다시 읽는다
window.deskMessages = {changed() {if (key === 'messages' && !$('card').hidden && !closing && msgMode !== 'pick') loadMessages().catch(() => {});}};

function watchMessages() {
  clearInterval(msgTimer);
  // 패널을 보는 동안 30초마다 새로 온 것을 본다 (고르는 중에는 쉰다)
  msgTimer = setInterval(() => {
    if (key === 'messages' && !$('card').hidden && !closing) {if (msgMode !== 'pick') loadMessages().catch(() => {});}
    else clearInterval(msgTimer);
  }, 30000);
}

// ── 에이전트 터미널 ─────────────────────────────────────────
// 지금 보던 창의 폴더·자주 쓰는 폴더·열린 탐색기 창 가운데 하나를 눌러 Claude Code·Codex 를 연다
// (desktop.py `_agent_*`). 설치가 안 됐으면 설치 창을 띄우고, 끝날 때까지 가끔 다시 본다.
let agentTimer = 0, agentInstalling = 0;
// 독을 왼쪽 클릭했는데 보던 창의 폴더가 하나면 '이 폴더에서 열까요?'를 맨 위에 묻는다 (2026-10-25 요청).
// 데스크는 한 번만 알려 주므로(agent_state 의 ask) 패널이 열려 있는 동안 여기 붙들어 둔다. 패널을 새로 열면 지운다.
let agentAsk = null;
const folderName = path => path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || path;

async function loadAgent() {
  let data;
  try {data = await api('agent_state');}
  catch (error) {$('body').innerHTML = empty('불러오지 못했습니다', error.message); return;}
  if (key !== 'agent') return;
  if (data.ask) agentAsk = data.ask;
  const tool = data.tools[data.tool];
  const active = data.active || {folders: []};
  sub(active.app ? `지금 보던 창 · ${active.app}${active.title && active.title !== active.app ? ` — ${active.title}` : ''}` : '지금 보던 창을 알 수 없습니다');
  const starred = new Set(data.favorites.map(item => item.path.toLowerCase()));
  const icon = `<span class="glyph"><svg viewBox="0 0 24 24">${GLYPHS.folder}</svg></span>`;
  const folder = (path, {remove = false, missing = false} = {}) => {
    const on = starred.has(path.toLowerCase());
    const star = remove
      ? `<button class="star" data-agent="unfav" title="자주 쓰는 폴더에서 빼기" aria-label="자주 쓰는 폴더에서 빼기">✕</button>`
      : `<button class="star${on ? ' on' : ''}" data-agent="${on ? 'unfav' : 'fav'}" title="${on ? '자주 쓰는 폴더에서 빼기' : '자주 쓰는 폴더에 넣기'}" aria-label="자주 쓰는 폴더">${on ? '★' : '☆'}</button>`;
    return `<div class="folder${missing ? ' missing' : ''}" data-folder="${esc(path)}" title="${esc(path)}">${icon}`
      + `<div class="copy"><strong>${esc(folderName(path))}</strong><small>${esc(path)}</small></div>${star}`
      + `<button class="pill" data-agent="run"${tool.installed && !missing ? '' : ' disabled'}>열기</button></div>`;
  };
  const tabs = Object.entries(data.tools).map(([name, info]) =>
    `<button data-agent-tool="${esc(name)}" aria-pressed="${name === data.tool}">${esc(info.label)}${info.installed ? '' : '<small>설치 필요</small>'}</button>`).join('');
  const install = tool.installed ? ''
    : `<div class="set-row agent-row warn"><div class="copy"><strong>${esc(tool.label)} 가 설치되어 있지 않습니다</strong>`
      + `<small>${data.tool === 'claude' ? 'Anthropic 공식 설치 스크립트로 이 사용자에게 설치합니다 (관리자 권한 없이).' : 'winget 으로 설치합니다 (없으면 npm).'}`
      + `${agentInstalling ? ' 설치 창에서 진행 중… 끝나면 여기가 바뀝니다.' : ''}</small></div>`
      + `<button class="pill" data-agent="install">${agentInstalling ? '다시 열기' : '설치하기'}</button></div>`;
  const skip = `<div class="set-row agent-row"><div class="copy"><strong>권한 묻지 않기</strong>`
    + `<small${data.skip ? ' class="skip-on"' : ''}><code>${esc(tool.skip_flag)}</code> — 묻지 않고 파일을 고치고 명령을 실행합니다. 믿는 폴더에서만 켜세요.</small></div>`
    + `<input type="checkbox" class="switch" data-agent="skip"${data.skip ? ' checked' : ''} aria-label="권한 묻지 않기"></div>`
    + `<div class="set-row agent-row"><div class="copy"><strong>데스크 안 터미널로 열기</strong>`
    + `<small>새 대화·모델·멈추기 단추와 입력칸·도움말이 붙은 창입니다. 끄면 Windows Terminal(없으면 명령 창)로 엽니다.</small></div>`
    + `<input type="checkbox" class="switch" data-agent="embed"${data.embed !== false ? ' checked' : ''} aria-label="데스크 안 터미널로 열기"></div>`
    + `<div class="set-row agent-row"><div class="copy"><strong>열기 전에 묻기</strong>`
    + `<small>독을 누르면 보던 폴더에서 열지 먼저 묻습니다. 끄면 묻지 않고 바로 엽니다.</small></div>`
    + `<input type="checkbox" class="switch" data-agent="ask"${data.askOn !== false ? ' checked' : ''} aria-label="열기 전에 묻기"></div>`
    // 원격 제어 자동 연결 (2026-10-30 요청 — 자동화 업무 패널에서 옮김). 자동화 업무 에이전트(Claude Code)에 붙는다. 설정 값 automation_rc
    + (data.tool !== 'claude' || typeof data.rc !== 'boolean' ? '' : `<div class="set-row agent-row"><div class="copy"><strong>원격 제어 자동 연결 (자동화 업무)</strong>`
      + `<small>자동화 업무에서 연 Claude Code 를 휴대폰·웹에서 이어 씁니다. claude.ai 구독 로그인이 필요하고, 대화가 claude.ai 를 거치므로 학생 개인정보를 다루는 일에는 꺼 두세요.</small>`
      + (data.skip && data.rc ? '<small class="skip-on">권한 묻지 않기가 켜져 있습니다 — 함께 쓰면 휴대폰에서 이 PC 를 묻지 않고 조작할 수 있습니다.</small>' : '')
      + `</div><input type="checkbox" class="switch" data-agent="rc"${data.rc ? ' checked' : ''} aria-label="원격 제어 자동 연결"></div>`);
  const ask = agentAsk && tool.installed
    ? `<section class="set-sec ask-card" role="group" aria-label="이 폴더에서 열까요?">`
      + `<div class="ask-q">${icon}<div class="copy"><strong>‘${esc(agentAsk.name)}’ 에서 ${esc(tool.label)} 를 열까요?</strong>`
      + `<small title="${esc(agentAsk.path)}">${esc(agentAsk.path)}</small></div></div>`
      + `<label class="ask-hide"><input type="checkbox" data-ask-hide> 앞으로 묻지 않기</label>`
      + `<div class="ask-actions"><button class="pill ghost" data-ask="no">아니요, 설정 보기</button>`
      + `<button class="pill" data-ask="yes">이 폴더에서 열기</button></div></section>` : '';
  // 창만 닫고 켜 둔 에이전트 (2026-10-25) — 다시 보기. 독 아이콘을 눌러도 그 창부터 연다 (desktop.py `_agent_quick`).
  const kept = data.kept
    ? `<section class="set-sec ask-card" role="group" aria-label="켜 둔 에이전트">`
      + `<div class="ask-q"><span class="glyph"><svg viewBox="0 0 24 24">${GLYPHS.terminal}</svg></span><div class="copy">`
      + `<strong>켜 둔 에이전트 ${data.kept}개가 일하고 있어요</strong><small>터미널 창만 닫았습니다. 다시 열면 그대로 보입니다.</small></div></div>`
      + `<div class="ask-actions"><button class="pill" data-agent="resume">에이전트 터미널 다시 보기</button></div></section>` : '';
  const here = active.folders.length
    ? `<div class="folders">${active.folders.map(path => folder(path)).join('')}</div>`
    : `<p class="none">${active.app ? '이 창에서는 폴더를 찾지 못했습니다.' : '독을 누르기 전에 보던 창이 없습니다.'} 아래에서 고르거나 폴더를 넣어 주세요.</p>`;
  const favorites = data.favorites.length
    ? `<div class="folders">${data.favorites.map(item => folder(item.path, {remove: true, missing: !item.exists})).join('')}</div>`
    : '<p class="none">☆ 를 눌러 넣거나 아래 단추로 폴더를 고르세요.</p>';
  const explorer = data.explorer.length
    ? `<section class="set-sec"><h2>열린 탐색기 창</h2><div class="folders">${data.explorer.map(path => folder(path)).join('')}</div></section>` : '';
  $('body').innerHTML = kept + ask + `<section class="set-sec"><div class="seg" role="group" aria-label="에이전트">${tabs}</div>${install}${skip}</section>`
    + `<section class="set-sec"><h2>지금 보던 창의 폴더${active.folders.length > 1 ? ' — 하나를 고르세요' : ''}</h2>${here}</section>`
    + `<section class="set-sec"><h2>자주 쓰는 폴더</h2>${favorites}<button class="pill add-folder" data-agent="pick">＋ 폴더 넣기</button></section>`
    + explorer;
  clearTimeout(agentTimer);
  if (tool.installed) agentInstalling = 0;
  else if (agentInstalling && Date.now() - agentInstalling < 15 * 60000) {
    agentTimer = setTimeout(() => {if (key === 'agent' && !$('card').hidden) loadAgent();}, 3000);
  }
}

$('body').addEventListener('click', async event => {
  if (key !== 'agent') return;
  const toolButton = event.target.closest('[data-agent-tool]');
  const action = event.target.closest('[data-agent]')?.dataset.agent;
  const row = event.target.closest('[data-folder]');
  const answer = event.target.closest('[data-ask]')?.dataset.ask;
  try {
    if (answer === 'yes') {
      const folder = agentAsk.path;
      if ($('body').querySelector('[data-ask-hide]')?.checked) await api('agent_settings', {ask: false});
      agentAsk = null;
      notify(await api('agent_run', {folder}));
      setTimeout(close, 700);
    } else if (answer === 'no') {
      agentAsk = null;                         // 묻는 칸만 걷고 설정·폴더 고르기를 그대로 보인다
      $('body').querySelector('.ask-card')?.remove();
    } else if (action === 'resume') {
      notify(await api('term_show'));
      setTimeout(close, 700);
    } else if (toolButton) {
      await api('agent_settings', {tool: toolButton.dataset.agentTool});
      await loadAgent();
    } else if (action === 'install') {
      notify(await api('agent_install', {tool: $('body').querySelector('[data-agent-tool][aria-pressed="true"]').dataset.agentTool}));
      agentInstalling = Date.now();
      await loadAgent();
    } else if (action === 'fav' || action === 'unfav') {
      notify(await api('agent_favorite', {folder: row.dataset.folder, on: action === 'fav'}));
      await loadAgent();
    } else if (action === 'pick') {
      const message = await api('agent_pick');
      if (message) {notify(message); await loadAgent();}
    } else if (row && !row.classList.contains('missing') && action !== 'skip'
               && !row.querySelector('[data-agent="run"]').disabled) {
      notify(await api('agent_run', {folder: row.dataset.folder}));
      setTimeout(close, 700);                  // 터미널이 뜨는 것을 보이고 접는다
    }
  } catch (error) {notify(error.message, true);}
});
$('body').addEventListener('change', async event => {
  const setting = event.target.dataset.agent;
  if (key !== 'agent' || !['skip', 'embed', 'ask', 'rc'].includes(setting)) return;
  try {notify(await api(setting === 'rc' ? 'automation_settings' : 'agent_settings', {[setting]: event.target.checked}));}
  catch (error) {notify(error.message, true);}
  loadAgent();
});

// ── 자동화 업무 (교사판, 2026-10-22) ─────────────────────────────
// 독의 제 아이콘. 업무용 스킬(쿨메신저 쪽지·리로스쿨 문자 …)을 한 폴더에 깔아 두고 거기서 에이전트를 연다
// (desktop.py `_automation_*`, core/automation.py). 스킬은 카드 목록, 설치는 카드마다 스위치 — 끄면 빼고 다시 깔지 않는다.
// 열 에이전트(Claude Code·Codex)는 에이전트 터미널과 같은 설정이다.
const SKILL_LOOKS = {                     // 스킬마다 카드 아이콘 — 모르는 스킬은 첫 글자
  'coolmessenger-send': {glyph: 'mail', tone: 'sky'},
  'riroschool-sms': {glyph: 'chat', tone: 'orange'},
  'spacekijun-mcp': {glyph: 'plug', tone: 'teal'}
};
let automationTimer = 0;
let mcpTimer = 0;
let mcpLabel = '';
let mcpSeen = null;                       // 마지막으로 받은 SPACEKIJUN 연결 상태 — 다시 그릴 때 «확인 중»으로 깜빡이지 않게

// SPACEKIJUN 에이전트 연결(MCP, 2026-10-25) — 열 에이전트에 서버를 등록하고 인증 창을 띄운다 (desktop.py `_automation_mcp_*`).
// 상태 확인은 서버에 붙어 보느라 몇 초 걸려 패널을 먼저 그리고 따로 채운다. 로그인·승인은 선생님이 브라우저에서 직접 한다.
const MCP_LOOKS = {
  none: ['off', '에이전트 없음', '열 에이전트가 설치되어 있지 않습니다.', ''],
  missing: ['off', '연결 안 함', '[연결하기]를 누르면 이 폴더의 {tool} 에 SPACEKIJUN 을 등록하고 인증 창을 엽니다.', 'connect:연결하기'],
  auth: ['new', '인증 필요', '등록되어 있습니다. [인증하기]를 누르고 브라우저에서 SPACEKIJUN 에 로그인해 [승인]하세요.', 'connect:인증하기'],
  authorizing: ['wait', '인증 중', '인증 창에서 진행 중입니다 — 브라우저에서 로그인하고 [승인]을 누르면 여기가 바뀝니다.', ''],
  ok: ['ok', '연결됨', '{tool} 가 선생님 권한으로 SPACEKIJUN 업무·일정·문서 도구를 씁니다.', 'disconnect:연결 해제'],
  error: ['foreign', '연결 실패', '등록은 되어 있지만 서버에 붙지 못했습니다. 인터넷을 확인하고 다시 인증해 보세요.', 'connect:다시 인증'],
  foreign: ['foreign', '직접 등록한 것 있음', '같은 이름(spacekijun)으로 다른 주소가 등록되어 있어 건드리지 않습니다.', '']
};
function mcpHtml(found, label) {
  if (!found) return '<div class="mcp-card"><span class="skill-icon tone-teal"><svg viewBox="0 0 24 24">' + GLYPHS.plug + '</svg></span>'
    + '<div class="skill-main"><div class="skill-head"><strong>SPACEKIJUN 연결</strong><span class="chip">확인 중…</span></div>'
    + '<p>이 PC 의 에이전트 설정을 확인하고 있습니다.</p></div></div>';
  const [kind, chip, text, action] = MCP_LOOKS[found.state] || MCP_LOOKS.error;
  const [verb, title] = action.split(':');
  const button = verb ? `<button class="pill${verb === 'connect' ? ' solid' : ' ghost'}" data-auto="mcp-${verb}">${esc(title)}</button>` : '';
  return `<div class="mcp-card"><span class="skill-icon tone-teal"><svg viewBox="0 0 24 24">${GLYPHS.plug}</svg></span>`
    + `<div class="skill-main"><div class="skill-head"><strong>SPACEKIJUN 연결</strong><span class="chip ${kind}">${esc(chip)}</span></div>`
    + `<p>${esc(text.replace('{tool}', label))}</p>`
    + `<p class="mcp-note">로그인은 선생님이 직접 합니다. 쓸 수 있는 도구는 학교 관리자가 정하고, `
    + `<a href="#" data-auto="mcp-manage">SPACEKIJUN 웹에서 연결을 끊을 수</a> 있습니다.</p></div>${button}</div>`;
}
async function loadMcp(label, fresh = false) {
  clearTimeout(mcpTimer);
  mcpLabel = label;
  let found;
  try {found = await api('automation_mcp_state', fresh ? {fresh: true} : {});}
  catch (error) {found = {state: 'error'};}
  if (key !== 'automation' || !$('mcp-slot')) return;
  mcpSeen = found;
  $('mcp-slot').innerHTML = mcpHtml(found, label);
  document.querySelectorAll('[data-needs-mcp]').forEach(chip => {
    chip.className = 'need ' + (found.state === 'ok' ? 'ok' : 'miss');
    chip.textContent = (found.state === 'ok' ? '✓' : '!') + ' SPACEKIJUN 연결' + (found.state === 'ok' ? '' : ' — 위에서 연결');
  });
  if (found.state === 'authorizing') {              // 인증 창이 끝나기를 본다
    mcpTimer = setTimeout(() => {if (key === 'automation' && !$('card').hidden) loadMcp(label, true);}, 3000);
  }
}
async function loadAutomation() {
  let data, auto;
  try {[data, auto] = await Promise.all([api('agent_state'), api('automation_state')]);}
  catch (error) {$('body').innerHTML = empty('불러오지 못했습니다', error.message); return;}
  if (key !== 'automation') return;
  const tool = data.tools[data.tool];
  const on = auto.skills.filter(item => item.state === 'current' || item.state === 'outdated').length;
  sub(`업무 스킬 ${auto.skills.length}개 · 설치 ${on}개`);
  const picker = `<div class="seg pick" role="group" aria-label="열 에이전트">` + Object.entries(data.tools).map(([name, info]) =>
    `<button data-auto-tool="${esc(name)}" aria-pressed="${name === data.tool}">${esc(info.label)}</button>`).join('') + '</div>';
  const sandbox = data.tool === 'codex' && !data.skip
    ? '<small>Codex 는 쿨메신저 같은 내 화면의 창을 조작하려고 샌드박스 없이(승인은 유지) 엽니다.</small>' : '';
  const missing = tool.installed ? ''
    : `<small class="bad">${esc(tool.label)} 가 설치되어 있지 않습니다 — 에이전트 터미널에서 설치하세요.</small>`;
  // 켜 둔 스킬이 쓰는데 없는 프로그램(Node.js·Python) — 열기·스킬 켜기에서 데스크가 저절로 깐다 (desktop.py `_automation_prepare`)
  const lacking = new Map();
  auto.skills.filter(item => item.on && item.state !== 'foreign').forEach(item => item.needs
    .filter(need => !need.found && need.installable).forEach(need => lacking.set(need.program, need.label)));
  const preparing = (auto.preparing || []).length
    ? `<small class="busy">${esc(auto.preparing.join(', '))} 설치 중 — 설치 창에서 진행합니다. 끝나면 여기가 바뀝니다.</small>`
    : lacking.size ? `<div class="auto-prep"><small>${esc([...lacking.values()].join(', '))} 이(가) 없습니다. 열기를 누르면 먼저 설치하고 엽니다`
        + ` (이 사용자에게만, 관리자 권한 없이).</small><button class="pill" data-auto="prepare">지금 설치</button></div>` : '';
  const remote = !auto.rcTool ? '' : `<small>원격 제어(휴대폰·웹) 자동 연결: <b>${auto.rc ? '켬' : '끔'}</b> — 독의 에이전트 터미널 설정(오른쪽 클릭)에서 바꿉니다.</small>`;
  const hero = `<section class="auto-hero"><div class="auto-where"><span class="glyph"><svg viewBox="0 0 24 24">${GLYPHS.folder}</svg></span>`
    + `<div class="copy"><strong>${esc(folderName(auto.folder))}</strong><small>${esc(auto.folder)}</small></div></div>`
    + `<div class="auto-go">${picker}<button class="pill solid" data-auto="open"${tool.installed ? '' : ' disabled'}>${esc(tool.label)} 열기</button></div>`
    + missing + preparing + sandbox + remote + '</section>';
  const chip = item => item.state === 'foreign' ? ['foreign', '직접 만든 것 있음']
    : item.state === 'current' ? ['ok', '설치됨'] : item.state === 'outdated' ? ['new', '새 판 — 열 때 갱신']
    : item.on ? ['wait', '열 때 설치'] : ['off', '꺼 둠'];
  const cards = auto.skills.map(item => {
    const look = SKILL_LOOKS[item.name];
    const mark = look ? `<span class="skill-icon tone-${look.tone}"><svg viewBox="0 0 24 24">${GLYPHS[look.glyph]}</svg></span>`
      : `<span class="skill-icon tone-slate"><b>${esc((item.title || '?').charAt(0))}</b></span>`;
    const [kind, label] = chip(item);
    const installed = item.state === 'current' || item.state === 'outdated';
    const lack = item.needs.some(need => !need.found && !need.optional);
    const needs = item.needs.map(need => `<span class="need ${need.found ? 'ok' : need.optional ? 'maybe' : 'miss'}">`
      + `${need.found ? '✓' : need.optional ? '○' : '!'} ${esc(need.label)}`
      + `${need.found ? '' : need.installable && item.on ? ' — 열 때 설치' : need.optional ? ' (있으면 좋음)' : ''}</span>`).join('');
    return `<article class="skill-card${installed ? '' : ' off'}${lack ? ' warn' : ''}">${mark}<div class="skill-main">`
      + `<div class="skill-head"><strong>${esc(item.title)}</strong><span class="chip ${kind}">${esc(label)}</span>`
      + `${item.sensitive ? '<span class="chip sens" title="학생·학부모 정보를 다룹니다">개인정보</span>' : ''}</div>`
      + `<p>${esc(item.summary)}</p>${needs || item.mcp ? `<div class="needs">${needs}`
        + `${item.mcp ? '<span class="need maybe" data-needs-mcp>○ SPACEKIJUN 연결</span>' : ''}</div>` : ''}</div>`
      + `<input type="checkbox" class="switch" data-auto-skill="${esc(item.name)}"${installed ? ' checked' : ''}`
      + `${item.state === 'foreign' ? ' disabled title="같은 이름으로 직접 만든 스킬이 있어 건드리지 않습니다"' : ''} aria-label="${esc(item.title)} 설치"></article>`;
  }).join('') || '<p class="none">실린 업무 스킬이 없습니다.</p>';
  $('body').innerHTML = hero
    + `<section class="set-sec"><h2>SPACEKIJUN 에이전트 연결 (MCP)</h2><div id="mcp-slot">${mcpHtml(mcpSeen, tool.label)}</div></section>`
    + `<section class="set-sec"><h2>스킬 — 스위치를 켜면 이 폴더에 설치, 끄면 뺍니다</h2><div class="skill-cards">${cards}</div>`
    + `<button class="pill add-folder" data-auto="install">켜 둔 스킬 최신 판으로 갱신</button></section>`;
  loadMcp(tool.label);
  clearTimeout(automationTimer);
  if ((auto.preparing || []).length) {          // 설치 창이 끝나기를 본다
    automationTimer = setTimeout(() => {if (key === 'automation' && !$('card').hidden) loadAutomation();}, 3000);
  }
}

$('body').addEventListener('click', async event => {
  if (key !== 'automation') return;
  const pick = event.target.closest('[data-auto-tool]');
  const auto = event.target.closest('[data-auto]')?.dataset.auto;
  try {
    if (auto === 'open') {
      notify(await api('automation_open'));
      setTimeout(close, 700);                  // 터미널이 뜨는 것을 보이고 접는다
    } else if (auto === 'install') {
      notify(await api('automation_install'));
      await loadAutomation();
    } else if (auto === 'prepare') {
      notify(await api('automation_prepare'));
      await loadAutomation();
    } else if (auto === 'mcp-connect' || auto === 'mcp-disconnect') {
      const button = event.target.closest('button');
      if (button) button.disabled = true;
      notify(await api('automation_' + auto.replace('-', '_')));
      await loadMcp(mcpLabel, true);
    } else if (auto === 'mcp-manage') {
      event.preventDefault();
      await api('automation_mcp_manage');
    } else if (pick && pick.getAttribute('aria-pressed') !== 'true') {
      await api('agent_settings', {tool: pick.dataset.autoTool});
      mcpSeen = null;                          // 에이전트마다 연결이 따로다
      await loadAutomation();
    }
  } catch (error) {notify(error.message, true);}
});
$('body').addEventListener('change', async event => {
  if (key !== 'automation') return;
  const skill = event.target.dataset.autoSkill;
  if (!skill) return;
  event.target.disabled = true;
  try {
    notify(await api('automation_skill', {name: skill, on: event.target.checked}));
  } catch (error) {notify(error.message, true);}
  loadAutomation();
});

async function fill(force = false) {
  const asked = key;
  if (key === 'settings') return loadSettings();
  if (key === 'agent') return loadAgent();
  if (key === 'automation') return loadAutomation();
  if (key === 'messages') {await loadMessages(true); watchMessages(); return;}
  if (key === 'clips') {await loadClips(true); watchClips(); return;}
  if (key === 'captures') {window.deskCaptures?.reload(); return;}
  if (key === 'inbox') return loadInbox(force);
  if (key === 'notes') {
    if (!$('body').querySelector('.notes, .empty')) $('body').innerHTML = '<div class="skeleton"></div>'.repeat(3);
    return loadNotes();
  }
  // 1) 받아 둔 것을 바로 그린다 — '불러오는 중' 없이 (2026-10-11 요청)
  if (!snapshot || snapshot.error || Date.now() - fetchedAt >= FRESH) await useQuick();
  if (asked !== key) return;
  sub(defaultSub());
  render();
  if (key === 'week' && view.week === 'month') loadMonth(force).catch(() => {});
  // 2) 오래됐으면 뒤에서 새로 받아 바꿔 그린다. 처음 한 번만 빈 틀(skeleton)이 보인다
  if (!force && snapshot && !snapshot.error && Date.now() - fetchedAt < FRESH) return;
  await loadSnapshot(force);
  if (asked !== key) return;                  // 그사이 다른 아이콘을 눌렀다
  sub(defaultSub());
  render();
}

// ── 열고 닫기 ────────────────────────────────────────────
window.deskPopover = {
  show(request) {
    closing = false;
    const changed = key !== request.key;
    key = request.key;
    if (key === 'week') resetMonth();          // 다시 열면 이번 달·오늘부터
    if (key === 'messages' && changed) {msgMode = 'list'; msgThread = null; msgPeople = null; msgTopKey = '';}   // 다른 패널에서 오면 목록부터
    if (key === 'agent') agentAsk = null;      // 물을 것이 있으면 데스크가 이번 agent_state 에 다시 싣는다
    place(request.caret);
    paintHead();
    if (changed) $('body').innerHTML = '';
    const card = $('card');
    card.hidden = false;
    card.classList.remove('in', 'out');
    void card.offsetWidth;                    // 같은 움직임을 다시 걸기 위해
    card.classList.add('in');
    $('body').scrollTop = 0;
    if (changed) $('toast').hidden = $('menu').hidden = true;   // 다른 패널의 알림·메뉴가 남지 않게
    fill().catch(() => {});
    if (key === 'captures') $('board').focus({preventScroll: true});   // 바로 화살표·Delete 를 쓸 수 있게
    if (key === 'clips') {$('clip-list').scrollTop = 0; $('clip-q').focus({preventScroll: true});}
  }
};

async function close() {
  if (closing) return;
  closing = true;
  const card = $('card');
  card.classList.remove('in');
  card.classList.add('out');
  await new Promise(done => setTimeout(done, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 130));
  try {await api('popover_close');} catch {/* 데스크가 이미 닫았다 */}
  card.hidden = true;
  card.classList.remove('out');
}

$('close').addEventListener('click', close);
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!$('msg-viewer').hidden) {closeViewer(); return;}        // 사진을 크게 보던 중이면 그것만 닫는다
  close();
});
$('refresh').addEventListener('click', () => fill(true).catch(() => {}));
$('more').addEventListener('click', async () => {
  if (key === 'clips') {
    // 두 번 눌러야 지운다 — 실수로 모아 둔 것을 잃지 않게
    if (!$('more').classList.contains('confirm')) {
      $('more').classList.add('confirm');
      $('more').textContent = '한 번 더 누르면 지웁니다';
      setTimeout(() => {if (key === 'clips') {$('more').classList.remove('confirm'); $('more').textContent = '모두 지우기 (고정한 것은 남김)';}}, 3000);
      return;
    }
    $('more').classList.remove('confirm');
    $('more').textContent = '모두 지우기 (고정한 것은 남김)';
    try {notify(await api('clips_clear')); await loadClips(true);} catch (error) {notify(error.message, true);}
    return;
  }
  const panel = PANELS[key];
  const done = panel.route ? api('open_space', {route: panel.route}) : api('open_page', {page: panel.page});
  done.catch(error => sub(error.message));
});
$('add').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {await api('sticky_create', {}); await loadNotes();}       // 새 메모 창이 바로 뜬다
  catch (error) {sub(error.message);}
  finally {button.disabled = false;}
});
$('views').addEventListener('click', event => {
  const button = event.target.closest('[data-view]');
  if (!button || !VIEWS[key] || view[key] === button.dataset.view) return;
  view[key] = button.dataset.view;
  try {localStorage.setItem(VIEW_KEY, JSON.stringify(view));} catch {/* 기억 못 해도 지금은 바뀐다 */}
  paintViews();
  $('body').scrollTop = 0;
  fill().catch(() => {});
});
$('body').addEventListener('click', event => {
  const step = event.target.closest('[data-month]');
  if (step && key === 'week') {
    const move = Number(step.dataset.month);
    if (move === 0) resetMonth();
    else {
      const [year, month] = monthAt.split('-').map(Number);
      monthAt = monthOf(new Date(year, month - 1 + move, 1));
      // 넘긴 달에서는 오늘이 있으면 오늘, 없으면 1일을 고른다
      picked = monthAt === monthOf(new Date()) ? toKey(new Date()) : `${monthAt}-01`;
    }
    render();
    $('body').querySelector(`[data-month="${move}"]`)?.focus({preventScroll: true});
    loadMonth().catch(() => {});
    return;
  }
  const day = event.target.closest('[data-day]');
  if (day && key === 'week') {
    picked = day.dataset.day;
    if (picked.slice(0, 7) !== monthAt) {monthAt = picked.slice(0, 7); loadMonth().catch(() => {});}
    render();
    $('body').querySelector(`[data-day="${picked}"]`)?.focus({preventScroll: true});
    $('body').querySelector('h2.pick')?.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    return;
  }
  const note = event.target.closest('[data-note]');
  if (note) api('sticky_open', {id: note.dataset.note}).catch(error => sub(error.message));
  const go = event.target.closest('[data-go]');
  if (go) api('open_page', {page: go.dataset.go}).catch(error => sub(error.message));
});
// 메모는 메모 창·웹에서 바뀌므로 패널을 다시 볼 때마다 새로 읽는다
window.addEventListener('focus', () => {if (key === 'notes' && !$('card').hidden) loadNotes();});
