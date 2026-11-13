'use strict';
// 독 아이콘 목록 — 독(dock.js)과 데스크 설정(app.js 의 '독 아이콘')이 함께 쓴다.
// 🚨 id 는 설정(desktop-preferences.json 의 dock_hidden)에 저장된다. 이미 쓰는 id 는 바꾸지 않는다.

window.DOCK_GLYPHS = {
  planet:'<circle cx="12" cy="12" r="5.5"/><path d="M3.5 15.5c-1.8 2.4 4.2 1.6 9.6-1.5s9-6.8 7-7.6c-.9-.3-2.4.1-4.1.9"/>',
  building:'<path d="M5 21V5l7-3 7 3v16M3 21h18M9 7h1M14 7h1M9 11h1M14 11h1M10 21v-6h4v6"/>',
  seat:'<path d="M7 4h10v8H7zM5 12h14v3H5zM7 15v5M17 15v5"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m4 7 8 6 8-6"/>',
  note:'<path d="M5 3h14a2 2 0 0 1 2 2v9l-7 7H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 21v-5a2 2 0 0 1 2-2h5M7 8h10M7 12h6"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  check:'<rect x="4" y="3.5" width="16" height="17" rx="3"/><path d="m8 9 1.5 1.5L12 8M8 15l1.5 1.5L12 14M14.5 9.5H17M14.5 15.5H17"/>',
  megaphone:'<path d="M4 10v4a1 1 0 0 0 1 1h2l5 4V5L7 9H5a1 1 0 0 0-1 1ZM16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
  bell:'<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15ZM10 20.5a2 2 0 0 0 4 0"/>',
  snip:'<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3.2"/>',
  photos:'<rect x="7" y="3.5" width="13.5" height="11" rx="2"/><path d="M4.5 7.5v10a2 2 0 0 0 2 2h11"/><path d="m9.5 12 2.5-2.5 2 2 1.5-1.5 2.5 2.5"/>',
  clipboard:'<rect x="5.5" y="4.5" width="13" height="16.5" rx="2.5"/><path d="M9 4.5V3.8A1.3 1.3 0 0 1 10.3 2.5h3.4A1.3 1.3 0 0 1 15 3.8v.7M9 10h6M9 13.5h6M9 17h3.5"/>',
  classroom:'<rect x="3" y="4" width="18" height="12" rx="2"/><circle cx="12" cy="9" r="2.2"/><path d="M8.5 16a3.5 3.5 0 0 1 7 0M7 20h10"/>',
  academy:'<path d="M2.5 10 12 5.5l9.5 4.5-9.5 4.5Z"/><path d="M6.5 12v4c1.5 1.5 3.5 2.3 5.5 2.3s4-.8 5.5-2.3v-4M21.5 10v5"/><path d="M18.5 1.8l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6Z"/>',
  egg:'<path d="M12 3c4.4 0 7 4.6 7 9.3 0 4.5-3.1 8.2-7 8.2s-7-3.7-7-8.2C5 7.6 7.6 3 12 3Z"/><rect x="8.5" y="8.5" width="7" height="5.5" rx="1.2"/><path d="M9.5 17h.01M12 17.6h.01M14.5 17h.01"/>',
  tower:'<path d="M12 2.5l1.1 2.3 2.5.3-1.8 1.7.5 2.5L12 8.1l-2.3 1.2.5-2.5-1.8-1.7 2.5-.3Z"/><rect x="8" y="11" width="8" height="3.2" rx=".8"/><rect x="6.5" y="14.6" width="11" height="3" rx=".8"/><rect x="5" y="18" width="14" height="3" rx=".8"/>',
  planner:'<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5Z"/><path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5Z"/><path d="m6 9.5 1.3 1.3L9.5 8.5M15 8.5h3M15 12h3M15 15.5h2M6.5 15h2.5"/>',
  compass:'<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5 13.5 10.5 20.5 12 13.5 13.5 12 20.5 10.5 13.5 3.5 12 10.5 10.5Z"/>',
  wand:'<path d="M4 20 14.5 9.5"/><path d="m12.5 7.5 4 4"/><path d="M18 3v3.5M16.25 4.75h3.5M20.5 9.5v2.5M19.25 10.75h2.5M10 2.5v2.5M8.75 3.75h2.5"/>',
  terminal:'<rect x="2.5" y="4" width="19" height="16" rx="3"/><path d="m6.5 9.5 3 2.5-3 2.5M12 15h5"/>',
  chat:'<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4h0A2.5 2.5 0 0 1 4 13.5Z"/><path d="M8 9h8M8 12h5"/>',
  gear:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>'
};

// 무리마다 독에서 구분선으로 나뉜다. 숨긴 아이콘만 남은 무리는 구분선도 함께 빠진다.
// run: 데스크가 '열려 있다'고 알려 주는 이름 (dock_state.running)
// busy: 자동 로그인이 진행 중인 업무시스템 (dock_state.busy)
// badge: 아이콘 모서리 표시 (dock_state.badges — 안 읽은 메시지 수, 받아 둔 업데이트는 점)
// action 'pop': 새 창 대신 독 위로 패널을 펼친다 (web/popover.html)
// 에이전트 터미널 (2026-10-13 요청, 교사·학생 모두) — 누르면 지금 보던 창의 폴더가 하나일 때 곧바로
// Claude Code·Codex 를 열고, 여럿이거나 없으면 패널에서 고른다. 켜 둔 에이전트가 있으면 새로 열지 않고 에이전트 터미널부터
// (2026-10-30 — 창이 열려 있어도). 오른쪽 클릭은 언제나 패널 (dock.js agentClick).
// 메시지 (2026-10-19 요청, 교사·학생 모두) — 학생 ↔ 선생님. 스페이스기전 알림으로 오가고, 안 읽은 수는 배지(badge)
const MESSAGES = {id: 'messages', label: '메시지', action: 'pop', key: 'messages', glyph: 'chat', tone: 'blue', badge: 'messages'};
// 자동화 업무 (2026-10-22 요청, 교사판만) — 업무 스킬(쿨메신저 쪽지·리로스쿨 문자 …)을 한 폴더에 깔고 거기서 에이전트를 연다
const AUTOMATION = {id: 'automation', label: '자동화 업무', action: 'pop', key: 'automation', glyph: 'wand', tone: 'teal'};
const AGENT = {id: 'agent', label: '에이전트 터미널', action: 'agent', key: 'agent', glyph: 'terminal', tone: 'terminal'};
const TEACHER_GROUPS = [
  {name: '업무시스템', items: [
    {id: 'space', label: '스페이스기전', action: 'open_space', glyph: 'planet', tone: 'indigo', run: 'space'},
    {id: 'neis', label: '나이스', action: 'portal', target: 'neis', text: 'N', tone: 'green', busy: 'neis'},
    {id: 'eduptl', label: '업무포털', action: 'portal', target: 'eduptl', glyph: 'building', tone: 'blue', busy: 'eduptl'},
    {id: 'klef', label: 'K-에듀파인', action: 'portal', target: 'klef', text: 'K', tone: 'teal', busy: 'klef'},
    {id: 'aiep', label: '전북 AIEP', action: 'open_aiep', text: 'AI', mini: true, tone: 'violet', run: 'aiep', busy: 'aiep'},
    {id: 'riro', label: '리로스쿨', action: 'open_riro', text: 'R', tone: 'orange', run: 'riro', busy: 'riro'},
    {id: 'jbstudy', label: '연수포털', action: 'open_jbstudy', text: '연', tone: 'amber', run: 'jbstudy', busy: 'jbstudy'},
    {id: 'seaton', label: '기전시트온', action: 'open_seaton', glyph: 'seat', tone: 'rose', run: 'seaton'}]},
  {name: '학교 정보', items: [
    {id: 'today', label: '오늘 시간표', action: 'pop', key: 'today', glyph: 'clock', tone: 'cyan'},
    {id: 'week', label: '이번 주 일정', action: 'pop', key: 'week', calendar: true, tone: 'paper'},
    {id: 'tasks', label: '나의 업무', action: 'pop', key: 'tasks', glyph: 'check', tone: 'amber'},
    {id: 'notices', label: '학교 공지', action: 'pop', key: 'notices', glyph: 'megaphone', tone: 'fuchsia'},
    {id: 'notifications', label: '최근 알림', action: 'pop', key: 'notifications', glyph: 'bell', tone: 'red'}]},
  {name: '도구', items: [
    {id: 'inbox', label: '쪽지함', action: 'pop', key: 'inbox', glyph: 'mail', tone: 'sky'},
    MESSAGES,
    {id: 'notes', label: '스티커 메모', action: 'pop', key: 'notes', glyph: 'note', tone: 'yellow', run: 'page:notes'},
    // 캡처는 화면을 얼려 찍으므로 말풍선·튀기를 남기지 않는다 (quiet)
    {id: 'capture', label: '캡처', action: 'capture', glyph: 'snip', tone: 'graphite', quiet: true},
    {id: 'captures', label: '캡처 보관함', action: 'pop', key: 'captures', glyph: 'photos', tone: 'lavender'},
    {id: 'clips', label: '클립보드', action: 'pop', key: 'clips', glyph: 'clipboard', tone: 'slate'},
    // 교실 세팅 (2026-10-14 요청) — 교실 PC(스페이스기전 교실)에서 QR 로 펼칠 반별 세팅을 만든다. 스페이스기전 /classroom
    {id: 'classroom-setup', label: '교실 세팅', action: 'open_space', route: '/classroom', glyph: 'classroom', tone: 'emerald'},
    AGENT,
    AUTOMATION]},
  {name: '데스크', items: [
    {id: 'desk', label: '데스크', action: 'open_page', page: 'home', glyph: 'grid', tone: 'ink', run: 'desk'},
    // 연결 및 설정 — 학생판처럼 독 위 패널로 펼친다 (2026-10-19 요청). 큰 설정 화면은 패널 바닥 단추·데스크 창에서
    {id: 'settings', label: '연결 및 설정', action: 'pop', key: 'settings', glyph: 'gear', tone: 'silver', badge: 'update'}]}
];

// 학생판 (2026-10-12 요청) — 학생이 쓰는 바로가기와 스페이스기전의 학생 기능만. 교사만 쓰는 것은 없다.
// 클래스룸은 기본 브라우저로 연다 — 구글은 프로그램 안 창(임베디드 웹뷰)에서의 로그인을 막는다.
// 리로스쿨·AIEP 는 프로그램 안 창으로 열고, 설정에 계정을 저장하면 학생 계정으로 자동 로그인한다.
const STUDENT_GROUPS = [
  {name: '바로가기', items: [
    {id: 'space', label: '스페이스기전', action: 'open_space', glyph: 'planet', tone: 'indigo', run: 'space'},
    {id: 'classroom', label: 'Google 클래스룸', action: 'open_classroom', glyph: 'classroom', tone: 'emerald'},
    {id: 'seaton', label: '기전시트온', action: 'open_seaton', glyph: 'seat', tone: 'rose', run: 'seaton'},
    {id: 'riro', label: '리로스쿨', action: 'open_riro', text: 'R', tone: 'orange', run: 'riro', busy: 'riro'},
    {id: 'aiep', label: '전북 AIEP', action: 'open_aiep', text: 'AI', mini: true, tone: 'violet', run: 'aiep', busy: 'aiep'}]},
  {name: '스페이스기전', items: [
    // 별빛 아카데미 (2026-10-22 요청) — 스페이스기전 /academy: 생기부 활동에서 질문을 찾아 탐구를 설계하는 게임형 학습 공간
    {id: 'academy', label: '별빛 아카데미', action: 'open_space', route: '/academy', glyph: 'academy', tone: 'violet'},
    {id: 'tamagotchi', label: '다마고찌', action: 'open_space', route: '/tamagotchi', glyph: 'egg', tone: 'pink'},
    {id: 'star-tower', label: '별까지 쌓기', action: 'open_space', route: '/star-tower', glyph: 'tower', tone: 'night'},
    // 플래너 (2026-10-14 요청) — 스페이스기전 /planner: 이번 주·하루 계획·월별 일정·나의 목표 (아카데미 플래너와 같은 기록)
    {id: 'planner', label: '플래너', action: 'open_space', route: '/planner', glyph: 'planner', tone: 'teal'},
    // 이세계 사회인 (2026-10-19 요청) — 이 PC 안에서 도는 게임 (core/isekai3d_server.py). 캐릭터는 Intune 캐릭터 팩
    {id: 'isekai3d', label: '고등학생이었던 내가 이세계에서는 사회인?', action: 'open_isekai3d', glyph: 'compass', tone: 'night', run: 'isekai3d'}]},
  {name: '학교 정보', items: [
    {id: 'today', label: '오늘 시간표', action: 'pop', key: 'today', glyph: 'clock', tone: 'cyan'},
    {id: 'week', label: '이번 주 일정', action: 'pop', key: 'week', calendar: true, tone: 'paper'}]},
  {name: '도구', items: [
    MESSAGES,
    {id: 'capture', label: '캡처', action: 'capture', glyph: 'snip', tone: 'graphite', quiet: true},
    {id: 'captures', label: '캡처 보관함', action: 'pop', key: 'captures', glyph: 'photos', tone: 'lavender'},
    {id: 'clips', label: '클립보드', action: 'pop', key: 'clips', glyph: 'clipboard', tone: 'slate'},
    AGENT]},
  {name: '설정', items: [
    {id: 'settings', label: '설정', action: 'pop', key: 'settings', glyph: 'gear', tone: 'silver', badge: 'update'}]}
];

window.DOCK_SETS = {teacher: TEACHER_GROUPS, student: STUDENT_GROUPS};
/** 독이 쓰는 한 줄 목록 — 무리 사이에 구분선(null) */
window.dockItemsOf = groups => groups.flatMap((group, index) => (index ? [null] : []).concat(group.items));
// 기본은 교사판 — 학생판 독은 데스크가 알려 주는 판(dock_state.edition)으로 갈아 낀다
window.DOCK_GROUPS = TEACHER_GROUPS;
window.DOCK_ITEMS = window.dockItemsOf(TEACHER_GROUPS);

/** 아이콘 겉모습 (그림·글자·달력) — 독과 설정이 같은 것을 그린다 */
window.dockFace = item => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  if (item.calendar) return '<span class="cal" aria-hidden="true"><small></small><b></b></span>';
  if (item.glyph) return `<svg viewBox="0 0 24 24" aria-hidden="true">${window.DOCK_GLYPHS[item.glyph]}</svg>`;
  return `<span class="${item.mini ? 'mini' : ''}" aria-hidden="true">${esc(item.text)}</span>`;
};
