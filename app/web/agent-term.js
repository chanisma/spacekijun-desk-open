'use strict';
// 에이전트 터미널 — Claude Code·Codex 가 도는 진짜 터미널(xterm.js) 위에 초보자용 단추·입력칸·도움말을 붙인 창.
// 한 창(작업 공간)에 에이전트 여럿을 띄우고(2026-10-25 요청, Orca 처럼), 에이전트끼리 서로의 화면을 읽고 말을 건넨다
// (중계는 core/agent_bridge.py — 이 화면은 그 중계가 묻는 '화면 글'·'선택지가 떠 있나'에 답한다: screenOf·choiceOf).
// 데스크가 창을 띄운 뒤 deskTerm.attachAll(ids, focus), 하나 더하면 deskTerm.add(id) 를 부른다 (desktop.py `_term_*`).
// 출력은 세션마다 길게 기다려 받고(term_read), 입력은 차례가 섞이지 않게 세션마다 한 줄로 세워 보낸다(term_write).
//
// ⚠️ 바뀔 수 있는 값 — 아래 COMMANDS 의 빗금 명령(/clear·/model …)과 단축키, CHOICE_* 의 선택지 문구는
//    에이전트 판이 바뀌면 달라질 수 있다. 확인: Claude Code 2.1.310 · Codex 0.163.0 (2026-10-24).
(() => {

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sleep = ms => new Promise(done => setTimeout(done, ms));
const store = {                                     // 창의 편의 설정 — 못 쓰면(사생활 모드 등) 없는 셈 친다
  get(key, fallback) {try {const v = localStorage.getItem('agentTerm.' + key); return v === null ? fallback : JSON.parse(v);} catch {return fallback;}},
  set(key, value) {try {localStorage.setItem('agentTerm.' + key, JSON.stringify(value));} catch {}}
};

const ESC = '\x1b';
const KEYS = {esc: ESC, enter: '\r', up: ESC + '[A', down: ESC + '[B', right: ESC + '[C', left: ESC + '[D',
              tab: '\t', shiftTab: ESC + '[Z', ctrlV: '\x16', altV: ESC + 'v', newline: '\n'};   // Ctrl+J — 두 에이전트 모두 줄바꿈
const COMMAND_GAP = 140;     // 명령 글자를 보낸 뒤 Enter 까지 쉬는 시간 (ms) — 한꺼번에 보내면 붙여넣기로 읽는다
const LIST_POLL = 2000;      // 왼쪽 목록의 상태(일하는 중·기다리는 중 …)를 다시 묻는 간격 (ms)
const LAYOUT_SLOTS = {one: 1, two: 2, four: 4};
const STATES = {working: '일하는 중', idle: '입력 기다림', 'waiting-for-user-choice': '선택 기다림',
                'agent-exited': '에이전트 꺼짐', ended: '끝남'};

// 에이전트마다 단추가 보낼 것. 문자열은 빗금 명령(뒤에 Enter), {keys} 는 키 그대로.
const COMMANDS = {
  claude: {
    clear: '/clear', resume: '/resume', compact: '/compact', model: '/model', rewind: '/rewind',
    mode: {keys: KEYS.shiftTab}, image: KEYS.altV,
    modeLabel: '권한 모드',
    modeTip: '<b>Shift+Tab</b> 과 같아요. 누를 때마다 바뀝니다 — 기본(하나하나 물어봄) → 파일 고치기 자동 허락 → 계획 모드(먼저 계획만 세움). 지금 모드는 터미널 아래쪽에 보여요.',
    more: [
      ['처음 설정', [['/init', '이 폴더 안내서(CLAUDE.md) 만들기'], ['/memory', '기억해 둘 내용 고치기'], ['/config', '설정 열기']]],
      ['상태 보기', [['/context', '대화가 얼마나 찼는지'], ['/usage', '사용량 보기'], ['/status', '계정·모델·버전'], ['/doctor', '설치에 문제가 없는지 점검']]],
      ['그 밖에', [['/help', '전체 명령 목록'], ['/login', '다른 계정으로 로그인'], ['/mcp', '연결된 도구(MCP) 보기'], ['/exit', '에이전트 끝내기']]]
    ]
  },
  codex: {
    clear: '/new', resume: '/resume', compact: '/compact', model: '/model', rewind: null,
    mode: '/permissions', image: KEYS.ctrlV,
    modeLabel: '권한 설정',
    modeTip: '<b>/permissions</b> 를 엽니다 — Codex 가 묻지 않고 해도 되는 일(파일 읽기·고치기·명령 실행)의 범위를 고릅니다.',
    more: [
      ['처음 설정', [['/init', '이 폴더 안내서(AGENTS.md) 만들기']]],
      ['상태 보기', [['/status', '계정·모델·사용량'], ['/diff', '바뀐 파일 보기'], ['/review', '바꾼 내용 검토 받기']]],
      ['그 밖에', [['/quit', '에이전트 끝내기']]]
    ]
  }
};

const DEFAULT_SNIPPETS = [
  {label: '이 폴더 설명해 줘', text: '이 폴더에 어떤 파일들이 있고 각각 무슨 용도인지 쉽게 설명해 줘.'},
  {label: '먼저 계획부터', text: '바로 고치지 말고, 어떻게 할지 계획을 먼저 보여 줘. 내가 확인하면 그때 진행해.'},
  {label: '쉽게 다시 설명', text: '방금 설명을 컴퓨터를 잘 모르는 사람도 알아듣게 다시 설명해 줘.'},
  {label: '방금 한 일 요약', text: '방금 한 작업에서 무엇을 바꿨는지, 어떤 파일이 생기거나 바뀌었는지 짧게 정리해 줘.'},
  {label: '오류 해결', text: '아래 오류가 났어. 원인을 쉽게 설명하고 고쳐 줘.\n\n'},
  {label: '다른 에이전트에게 검토 맡기기', text: '방금 만든 결과를 다른 에이전트에게 보내서 검토해 달라고 하고, 답이 오면 반영해 줘.'},
  {label: '일 나눠 맡기기', text: '이 일을 둘로 나눠서 한쪽은 다른 에이전트에게 맡기고, 끝나면 결과를 합쳐 줘.'}
];

const sessions = new Map();          // id → 세션 (터미널·받기 상태·정보)
let ownData = null, ownRoom = null, ownBusy = false;   // «내 다른 PC» 방 — 아래 «내 다른 PC» 절
let order = [], current = null, snippets = DEFAULT_SNIPPETS, toastTimer = 0, fontSize = store.get('fontSize', 14);
let layout = store.get('layout', 'one'), team = true, eventsLast = 0, eventsToken = 0;

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
  toastTimer = setTimeout(() => {$('toast').hidden = true;}, error ? 5000 : 2400);
}
const attempt = work => Promise.resolve().then(work).catch(error => toast(error.message, true));
const now = () => sessions.get(current);
const tools = (s = now()) => COMMANDS[s?.info.tool] || COMMANDS.claude;
const titleOf = s => s?.info.title || s?.info.agent || '';

// ── 세션 하나 = 칸 하나 ─────────────────────────────────
function makeSession(id) {
  const pane = document.createElement('section');
  pane.className = 'pane';
  pane.dataset.id = id;
  pane.innerHTML = '<div class="pane-head"><span class="dot"></span><b></b><small></small></div><div class="pane-term"></div>'
    + CHAT_MARKUP
    + '<div class="pane-ended" hidden><div><strong>에이전트가 끝났습니다</strong><p>‘다시 시작’을 누르면 하던 대화로 다시 켭니다. 다른 대화는 ‘지난 대화’에서 고를 수 있어요.</p></div>'
    + '<button class="primary" data-do="restart">다시 시작</button></div>'
    + LOGIN_MARKUP;
  $('panes').insertBefore(pane, $('empty'));
  const term = new Terminal({
    fontFamily: "'Cascadia Mono','Cascadia Code',Consolas,'D2Coding','Malgun Gothic',monospace",
    fontSize, lineHeight: 1.15, cursorBlink: true, allowProposedApi: true, scrollback: 8000, rightClickSelectsWord: false,
    theme: {background: '#14151b', foreground: '#e6e8ee', cursor: '#c7d2fe', selectionBackground: '#3b4270',
            black: '#1d1f27', brightBlack: '#5c6370'}
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  try {term.loadAddon(new Unicode11Addon.Unicode11Addon()); term.unicode.activeVersion = '11';} catch {}
  term.loadAddon(new WebLinksAddon.WebLinksAddon((_event, url) => attempt(() => api('term_link', {url}))));
  term.open(pane.querySelector('.pane-term'));
  term.registerLinkProvider({provideLinks: (y, done) => termPathLinks(s, y).then(done, () => done(undefined))});
  const s = {id, pane, term, fit, info: {id, tool: 'claude', title: '', agent: id, folder: '', name: ''},
             cursor: 0, epoch: null, running: null, closed: false, state: '', token: 0, outgoing: '', writing: false, size: '',
             draft: null, focusSent: null, commands: null,
             chat: {rev: 0, conversation: null, items: new Map(), token: 0, supported: true, stick: true, liveSig: '',
                   holding: false, pending: [], shots: new Map()}};
  wireChat(s);
  term.onData(data => {if (data !== FOCUS_IN && data !== FOCUS_OUT) send(s, data);});   // 포커스 알림은 syncFocus 가 보낸다
  term.onResize(({cols, rows}) => scheduleResize(s, cols, rows));
  term.attachCustomKeyEventHandler(event => terminalKey(s, event));
  term.textarea.addEventListener('focus', () => focus(id, {from: 'terminal'}));
  // 글 없이 사진만 복사돼 있으면 에이전트가 클립보드를 직접 읽게 한다
  term.textarea.addEventListener('paste', event => {
    if (clipboardImageOnly(event)) {event.preventDefault(); event.stopImmediatePropagation(); pasteImage(s);}
  }, true);
  pane.querySelector('.pane-term').addEventListener('contextmenu', event => {   // 고른 글이 있으면 복사, 없으면 붙여넣기
    event.preventDefault();
    if (term.hasSelection()) copySelection(s); else pasteClipboard(s);
  });
  pane.addEventListener('mousedown', () => focus(id, {from: 'terminal'}));
  new ResizeObserver(() => refit(s)).observe(pane.querySelector('.pane-term'));
  sessions.set(id, s);
  order.push(id);
  return s;
}

async function attach(id) {
  const s = sessions.get(id) || makeSession(id);
  s.token++;
  s.cursor = 0; s.epoch = null; s.running = null; s.closed = false;
  s.term.reset();
  try {s.info = await api('term_info', {id}); s.state = s.info.state || '';}
  catch (error) {toast(error.message, true); return s;}
  paintPane(s);
  pump(s, s.token);
  paintView(s);
  startChat(s);
  checkLogin(s);
  return s;
}

function dropSession(id) {
  const s = sessions.get(id);
  if (!s) return;
  s.token++;
  s.chat.token++;
  s.term.dispose();
  s.pane.remove();
  sessions.delete(id);
  order = order.filter(other => other !== id);
  if (current === id) current = null;
  focus(current || order[order.length - 1] || null);
}

function paintPane(s) {
  const head = s.pane.querySelector('.pane-head');
  head.querySelector('.dot').className = `dot ${s.state || (s.running ? 'working' : '')}`;
  head.querySelector('b').textContent = titleOf(s);
  head.querySelector('small').textContent = `${s.info.label || ''} · ${s.info.name || ''}`;
  s.pane.title = s.info.folder || '';
}

// ── 고르기 · 칸 나누기 ─────────────────────────────────
function focus(id, {from = ''} = {}) {
  if (id && !sessions.has(id)) return;
  if (current === id && from === 'terminal') return;         // 이미 고른 칸을 눌렀다
  if (ownRoom) closeRoom();                                  // 방에서 쓰던 말은 방에 두고 이 PC 칸의 말로
  if (current !== id) swapDraft(sessions.get(current), sessions.get(id));
  current = id;
  syncFocus();
  for (const s of sessions.values()) s.pane.setAttribute('aria-current', String(s.id === id));
  // 터미널을 눌러 고른 것은 이미 보이는 칸이다 — 칸을 다시 늘어놓지 않는다
  if (from !== 'terminal' || !id || sessions.get(id).pane.hidden) arrange();
  paintHeader();
  paintList();
  loadUsage();
}

function visibleIds() {
  const slots = LAYOUT_SLOTS[layout] || 1;
  if (slots === 1) return current ? [current] : order.slice(0, 1);
  const shown = order.slice(0, slots);
  if (current && !shown.includes(current)) shown[shown.length - 1] = current;   // 고른 것은 늘 보인다
  return shown;
}

function arrange() {
  const shown = new Set(visibleIds());
  $('panes').dataset.layout = shown.size <= 1 ? 'one' : (shown.size === 2 ? 'two' : 'four');
  for (const s of sessions.values()) {
    s.pane.hidden = !shown.has(s.id);
    s.pane.style.order = String(order.indexOf(s.id));
  }
  $('empty').hidden = sessions.size > 0;
  document.querySelectorAll('[data-layout]').forEach(button => {
    if (button.tagName === 'BUTTON') button.setAttribute('aria-pressed', String(button.dataset.layout === layout));
  });
  requestAnimationFrame(() => {for (const id of shown) refit(sessions.get(id));});
}

function setLayout(next) {
  layout = next in LAYOUT_SLOTS ? next : 'one';
  store.set('layout', layout);
  arrange();
}

// ── 터미널 크기 · 키 ───────────────────────────────────
const resizeTimers = new Map();
function refit(s) {
  if (!s || s.pane.hidden) return;
  try {s.fit.fit();} catch {}
}
function scheduleResize(s, cols, rows) {
  clearTimeout(resizeTimers.get(s.id));
  resizeTimers.set(s.id, setTimeout(() => attempt(() => api('term_resize', {id: s.id, cols, rows})), 80));
}

function terminalKey(s, event) {
  if (event.type !== 'keydown') return true;
  const key = event.key.toLowerCase();
  if (event.ctrlKey && !event.altKey && key === 'c' && s.term.hasSelection()) {copySelection(s); return false;}
  if (event.ctrlKey && !event.altKey && key === 'v') return false;      // 브라우저 붙여넣기에 맡긴다 (paste)
  if (event.shiftKey && !event.ctrlKey && event.key === 'Enter') {event.preventDefault(); send(s, KEYS.newline); return false;}
  if (fontKey(event)) return false;
  if (event.key === 'F1') return false;            // 도움말은 문서 쪽에서 연다 — 에이전트에게 F1 을 보내지 않는다
  return true;
}

function fontKey(event) {
  if (!event.ctrlKey || event.altKey) return false;
  if (event.key === '=' || event.key === '+') zoom(1);
  else if (event.key === '-') zoom(-1);
  else if (event.key === '0') zoom(0);
  else return false;
  event.preventDefault();
  return true;
}
function zoom(step) {
  fontSize = step === 0 ? 14 : Math.max(10, Math.min(26, fontSize + step));
  store.set('fontSize', fontSize);
  for (const s of sessions.values()) {s.term.options.fontSize = fontSize; refit(s);}
  toast(`글자 크기 ${fontSize}`);
}

async function copySelection(s) {
  const text = s.term.getSelection();
  s.term.clearSelection();
  try {await navigator.clipboard.writeText(text); toast('복사했습니다.');}
  catch {toast('복사하지 못했습니다.', true);}
}
const clipboardImageOnly = event => !event.clipboardData?.getData('text')
  && [...(event.clipboardData?.items || [])].some(item => item.type.startsWith('image/'));
async function pasteClipboard(s) {                  // 오른쪽 클릭
  let text = '';
  try {text = await navigator.clipboard.readText();}
  catch {toast('여기서는 Ctrl+V 로 붙여 넣어 주세요.'); return;}
  if (text) s.term.paste(text);                     // 에이전트가 붙여넣기 모드를 켰으면 그렇게 감싸 보낸다
  else pasteImage(s);                               // 글이 없으면 사진일 수 있다 — 에이전트가 클립보드를 직접 읽는다
  s.term.focus();
}
function pasteImage(s) {
  if (!alive(s)) return;
  send(s, tools(s).image);
  s.term.focus();
}

// ── 보내기 · 받기 ───────────────────────────────────────
// pywebview 는 부를 때마다 스레드를 따로 쓴다 — 동시에 보내면 순서가 섞이므로 앞의 것이 끝난 뒤 모아 보낸다
function send(s, data) {
  if (!s || !data) return;
  s.outgoing += data;
  if (!s.writing) flush(s);
}
async function flush(s) {
  s.writing = true;
  while (s.outgoing) {
    const chunk = s.outgoing; s.outgoing = '';
    try {await api('term_write', {id: s.id, data: chunk});}
    catch (error) {toast(error.message, true); s.outgoing = ''; break;}
  }
  s.writing = false;
}
async function sendLine(s, text, {paste = false} = {}) {
  if (paste && s.term.modes.bracketedPasteMode) send(s, `${ESC}[200~${text.replace(/\r?\n/g, '\r')}${ESC}[201~`);
  else send(s, text);
  await sleep(COMMAND_GAP);
  send(s, KEYS.enter);
}

async function pump(s, token) {
  let failures = 0;
  while (token === s.token && sessions.get(s.id) === s) {
    let result;
    try {result = await api('term_read', {id: s.id, cursor: s.cursor, epoch: s.epoch});}
    catch (error) {
      if (token !== s.token) return;
      if (/찾을 수 없습니다/.test(error.message)) {dropSession(s.id); return;}   // 데스크 쪽에서 닫혔다
      if (++failures === 3) toast(error.message, true);
      await sleep(Math.min(4000, 400 * failures));
      continue;
    }
    if (token !== s.token) return;
    failures = 0;
    if (result.reset) s.term.reset();               // 처음 붙었거나, 다시 시작했거나, 오래된 출력을 버렸다
    if (result.data) s.term.write(result.data);
    s.cursor = result.cursor;
    s.epoch = result.epoch;
    setRunning(s, result.running, result.closed);
    if (result.closed) await sleep(1000);           // 끝난 세션 — 다시 시작을 기다린다
  }
}

// ── 대화 보기 (2026-11-06 요청, 테스트 판) ─────────────────────────
// «cmd 화면이 최신 UI 와 거리가 있어 어렵게 느끼는 사용자가 있을 수 있음» — 터미널 위에 대화를 말풍선으로 그린다.
// 터미널은 밑에서 그대로 돈다(크기·선택지 읽기를 위해 숨기지 않고 덮는다). 대화는 Claude Code 의 대화 기록을 데스크가 읽어
// 준다(term_chat · core/agent_chat.py). 선택지(허락 묻기 등)는 터미널 화면에서 읽어 단추로 보여 주고, 누르면 그 번호를 보낸다.
// Codex 는 기록 꼴이 달라 터미널로만 본다.
const CHAT_POLL = 900;
const CHAT_MARKUP = '<div class="pane-chat" hidden><div class="chat-scroll"><div class="chat-inner"><div class="chat-list"></div>'
  + '<div class="chat-empty" hidden><div class="ce-mark">✦</div><strong>무엇을 도와드릴까요?</strong><p>아래 입력칸에 할 일을 적고 Enter 를 누르세요.<br>예) “이 폴더의 엑셀 파일을 읽고 반별 평균을 표로 정리해 줘”</p></div>'
  + '<div class="chat-live"></div></div></div>'
  + '<button class="chat-bottom" hidden title="맨 아래로">↓ 새 내용</button></div>'
  + '<div class="view-switch" role="group" aria-label="보기" hidden><button data-view="chat" title="대화를 말풍선으로 봅니다 (테스트)">대화</button>'
  + '<button data-view="term" title="에이전트의 원래 화면(터미널)을 봅니다">터미널</button></div>';
let chatView = store.get('chatView', 'chat');
const chatShown = s => !!s && chatView === 'chat' && s.info.tool === 'claude' && s.chat.supported;

function wireChat(s) {
  const pane = s.pane, scroll = pane.querySelector('.chat-scroll');
  pane.querySelector('.view-switch').addEventListener('click', event => {
    const button = event.target.closest('[data-view]');
    if (!button) return;
    event.stopPropagation();
    setChatView(button.dataset.view);
  });
  // 끌어 고른 글은 놓는 순간 복사된다 (터미널의 «고르면 복사»와 같게). 누르고 있는 동안은 화면 갱신을 멈춘다.
  pane.querySelector('.pane-chat').addEventListener('mousedown', event => {
    if (event.button === 0 && !event.target.closest('button,summary,a,.chat-bottom')) s.chat.holding = true;
  });
  const release = () => {
    if (!s.chat.holding) return;
    s.chat.holding = false;
    const selection = window.getSelection();
    const text = selection?.toString() || '';
    if (!text.trim() || !selection.anchorNode || !pane.querySelector('.pane-chat').contains(selection.anchorNode)) return;
    navigator.clipboard.writeText(text.replace(/ /g, ' ')).then(() => toast('고른 글을 복사했습니다.'),
      () => toast('복사하지 못했습니다.', true));
  };
  document.addEventListener('mouseup', release);
  window.addEventListener('blur', () => {s.chat.holding = false;});
  scroll.addEventListener('scroll', () => {
    s.chat.stick = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 60;
    pane.querySelector('.chat-bottom').hidden = s.chat.stick;
  });
  pane.querySelector('.chat-bottom').addEventListener('click', event => {event.stopPropagation(); chatToBottom(s, true);});
  pane.querySelector('.pane-chat').addEventListener('click', event => {
    const pick = event.target.closest('[data-pick]');
    if (pick) {event.stopPropagation(); pickChoice(s, pick.dataset.pick); return;}
    const shot = event.target.closest('[data-shot]');
    if (shot) {event.stopPropagation(); openShot(s, shot); return;}
    const act = event.target.closest('[data-chat-do]');
    if (act) {
      event.stopPropagation();
      if (act.dataset.chatDo === 'esc') send(s, KEYS.esc);
      else if (act.dataset.chatDo === 'term') setChatView('term');
      return;
    }
    const place = event.target.closest('a[data-path]');
    if (place) {event.preventDefault(); event.stopPropagation(); openPath(s, place.dataset.path, event.shiftKey); return;}
    const link = event.target.closest('a[data-link]');
    if (link) {event.preventDefault(); attempt(() => api('term_link', {url: link.getAttribute('href')})); return;}
    const copy = event.target.closest('[data-copy]');
    if (copy) {event.stopPropagation(); copyChat(copy); return;}
    if (!window.getSelection()?.toString() && !event.target.closest('details,summary,a,pre')) $('input').focus();
  });
}

function setChatView(view) {
  chatView = view === 'term' ? 'term' : 'chat';
  store.set('chatView', chatView);
  for (const s of sessions.values()) paintView(s);
  const s = now();
  if (s && !chatShown(s)) s.term.focus(); else $('input').focus();
}
function paintView(s) {
  const usable = s.info.tool === 'claude' && s.chat.supported;
  const on = chatShown(s);
  s.pane.querySelector('.pane-chat').hidden = !on;
  s.pane.classList.toggle('chat-on', on);
  const sw = s.pane.querySelector('.view-switch');
  sw.hidden = !usable;
  sw.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === (on ? 'chat' : 'term'))));
  if (on) {s.chat.liveSig = ''; chatToBottom(s, true); paintChatLive(s);}
  $('keys-hint').innerHTML = chatView === 'chat'
    ? '선택지가 나오면 대화 아래의 <b>단추</b>로 고르기 · 멈추기 <kbd>Esc</kbd> · 원래 화면은 오른쪽 위 <b>터미널</b>'
    : '선택지가 나오면 <kbd>↑</kbd><kbd>↓</kbd> 로 고르고 <kbd>Enter</kbd> · 멈추기 <kbd>Esc</kbd>';
}

async function startChat(s) {
  const token = ++s.chat.token;
  s.chat.rev = 0; s.chat.conversation = null; s.chat.items.clear();
  s.pane.querySelector('.chat-list').innerHTML = '';
  while (token === s.chat.token && sessions.get(s.id) === s) {
    // 글을 끌어 고르는 동안은 화면을 바꾸지 않는다 (놓으면 복사된다) — 받을 것은 다음 차례에 since 부터 그대로 온다
    if (s.info.tool === 'claude' && !s.chat.holding && (chatShown(s) || s.chat.conversation === null)) {
      let data = null;
      try {data = await api('term_chat', {id: s.id, since: s.chat.rev, conversation: s.chat.conversation});} catch {}
      if (token !== s.chat.token) return;
      if (data) applyChat(s, data);
    }
    paintChatLive(s);
    await sleep(CHAT_POLL);
  }
}

function applyChat(s, data) {
  if (data.supported === false) {
    if (s.chat.supported) {s.chat.supported = false; paintView(s);}
    return;
  }
  const list = s.pane.querySelector('.chat-list');
  if (data.reset || data.conversation !== s.chat.conversation) {
    s.chat.items.clear();
    list.innerHTML = '';
    s.chat.stick = true;
  }
  s.chat.conversation = data.conversation || '';
  s.chat.rev = data.rev || 0;
  const fresh = data.items || [];
  for (const item of fresh) {
    const old = s.chat.items.get(item.i);
    const node = renderChatItem(item);
    if (old) {
      if (old.querySelector('details')?.open) node.querySelector('details')?.setAttribute('open', '');
      old.replaceWith(node);
    } else list.appendChild(node);
    s.chat.items.set(item.i, node);
    loadShots(s, node);
    linkPaths(s, node);
    if (item.k === 'user') settlePending(s, item.text);
  }
  while (s.chat.items.size > 400) {                    // 화면이 무거워지지 않게 오래된 것부터 덜어 낸다
    const first = s.chat.items.keys().next().value;
    s.chat.items.get(first)?.remove();
    s.chat.items.delete(first);
  }
  if (fresh.length) groupTools(list);
  s.pane.querySelector('.chat-empty').hidden = s.chat.items.size > 0;
  if (fresh.length && s.chat.stick) chatToBottom(s);
}

function chatToBottom(s, force = false) {
  if (!force && !s.chat.stick) return;
  const scroll = s.pane.querySelector('.chat-scroll');
  requestAnimationFrame(() => {scroll.scrollTop = scroll.scrollHeight;});
  s.chat.stick = true;
  s.pane.querySelector('.chat-bottom').hidden = true;
}

const TOOL_ICON = {
  Read: 'M6 3h9l4 4v14H6zM14 3v5h5', Write: 'M6 3h9l4 4v14H6zM12 11v6M9 14h6', Edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4',
  Bash: 'M4 6l5 6-5 6M12 18h8', Grep: 'M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zM16 16l5 5',
  Web: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18',
  Agent: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3 3-5 6-5s6 2 6 5M17 11a2.5 2.5 0 1 0 0-5M18 15c2 .5 3 2 3 5',
  TodoWrite: 'M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2',
  other: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5 12 12l8-4.5M12 12v9'
};
const ICON_OF = {MultiEdit: 'Edit', NotebookEdit: 'Edit', PowerShell: 'Bash', Glob: 'Grep', WebFetch: 'Web', WebSearch: 'Web', Task: 'Agent'};
const iconPath = name => TOOL_ICON[ICON_OF[name] || name] || TOOL_ICON.other;

// 사진 — 항목에는 열쇠만 오고, 그림은 term_chat_image 로 하나씩 받는다 (스크린샷·붙여 넣은 사진·도구가 저장한 그림)
const shotsHtml = keys => keys?.length
  ? `<div class="shots">${keys.map(key => `<button class="shot loading" data-shot="${esc(key)}" title="크게 보기"><img alt="사진"></button>`).join('')}</div>`
  : '';

function renderChatItem(item) {
  const el = document.createElement('div');
  el.dataset.i = item.i;
  if (item.k === 'user') {
    el.className = 'msg me' + (item.queued ? ' queued' : '');
    el.innerHTML = `<div class="me-body">${item.queued ? '<span class="me-tag">작업 중에 보낸 말</span>' : ''}`
      + (item.text ? `<div class="bubble">${esc(item.text).replace(/\n/g, '<br>')}</div>` : '')
      + `${shotsHtml(item.images)}</div>`;
    el.dataset.raw = item.text;
  } else if (item.k === 'text') {
    el.className = 'msg ai';
    el.innerHTML = `<div class="ai-mark" aria-hidden="true">✦</div><div class="ai-body"><div class="md">${markdown(item.text)}</div>`
      + `<button class="copy-btn" data-copy title="이 답을 복사">복사</button></div>`;
    el.dataset.raw = item.text;
  } else if (item.k === 'tool') {
    el.className = `tool ${item.status}`;
    el.dataset.tool = '1';
    const state = item.status === 'run' ? '<span class="spin" aria-label="하는 중"></span>'
      : item.status === 'err' ? '<span class="bad" title="실패">!</span>' : '<span class="good" title="끝남">✓</span>';
    const body = item.result ? `<pre>${esc(item.result)}</pre>` : '<pre class="muted">결과를 기다리는 중…</pre>';
    el.innerHTML = `<details><summary><svg viewBox="0 0 24 24"><path d="${iconPath(item.name)}"/></svg>`
      + `<b>${esc(item.label)}</b><span class="detail">${esc(item.detail)}</span>${state}</summary>${body}</details>`
      + shotsHtml(item.images);
    if (item.images?.length) el.dataset.shots = '1';     // 사진이 있는 도구는 «작업 n개»로 묶지 않는다 — 접혀 안 보이지 않게
  } else {
    el.className = 'note';
    el.innerHTML = `<span>${esc(item.text)}</span>`;
  }
  return el;
}

// 이어진 도구 줄이 셋 넘으면 «작업 n개»로 묶는다 — 펼치면 하나하나. 하는 중인 것이 있으면 마지막 것만 밖에 보인다.
// 바뀐 묶음만 다시 짓는다 — 전부 풀었다 다시 묶으면 고르던 글(선택)이 풀리고 읽던 자리가 흔들린다.
function groupTools(list) {
  const flat = [];
  for (const child of list.children) {
    if (child.classList.contains('tool-group')) flat.push(...child.querySelector('.tg-body').children);
    else flat.push(child);
  }
  const wanted = [];
  let run = [];
  const flush = () => {
    if (run.length >= 3) {
      const inside = run[run.length - 1].classList.contains('run') ? run.slice(0, -1) : run;
      if (inside.length >= 2) wanted.push(inside);
    }
    run = [];
  };
  for (const node of flat) {
    if (node.dataset.tool && !node.dataset.shots) run.push(node); else flush();
  }
  flush();
  const keyOf = nodes => nodes.map(n => n.dataset.i).join(',');
  const want = new Map(wanted.map(nodes => [keyOf(nodes), nodes]));
  const open = new Set();
  for (const group of [...list.querySelectorAll(':scope > .tool-group')]) {
    const key = keyOf([...group.querySelector('.tg-body').children]);
    if (want.has(key)) {want.delete(key); paintGroup(group); continue;}
    if (group.open) open.add(group.dataset.first);
    group.replaceWith(...group.querySelector('.tg-body').children);
  }
  for (const inside of want.values()) {
    const group = document.createElement('details');
    group.className = 'tool-group';
    group.dataset.first = inside[0].dataset.i;
    if (open.has(group.dataset.first)) group.open = true;
    group.innerHTML = '<summary></summary><div class="tg-body"></div>';
    inside[0].before(group);
    group.querySelector('.tg-body').append(...inside);
    paintGroup(group);
  }
}
function paintGroup(group) {
  const inside = [...group.querySelector('.tg-body').children];
  const bad = inside.filter(n => n.classList.contains('err')).length;
  const names = [...new Set(inside.map(n => n.querySelector('b')?.textContent || ''))].slice(0, 3).join(' · ');
  const html = `<svg viewBox="0 0 24 24"><path d="M5 7h14M5 12h14M5 17h9"/></svg>`
    + `<b>작업 ${inside.length}개</b><span class="detail">${esc(names)}</span>`
    + `${bad ? `<span class="tg-bad">실패 ${bad}</span>` : '<span class="good">✓</span>'}`;
  if (group.dataset.sig !== html) {group.querySelector(':scope > summary').innerHTML = html; group.dataset.sig = html;}
}

// ── 파일·폴더 주소 누르면 열기 (2026-11-09 요청) ─────────────────────
// Claude Code 처럼 화면에 나온 주소를 눌러 연다. 줄에서 주소 같은 글을 골라 데스크에 묻고(term_paths — 작업 폴더 기준,
// 실제로 있는 것만), 있는 것에만 밑줄을 긋는다. 누르면 파일은 기본 프로그램·폴더는 탐색기, Shift+누르기는 탐색기에서 골라 보이기.
// 실행 파일(.exe·.bat·.ps1 …)은 열지 않고 탐색기에서 보여 준다 (core/agent_paths.py).
const PATH_FIND = new RegExp([
  String.raw`[A-Za-z]:[\\/][^\s"'<>|*?\x60]*(?: +[^\s"'<>|*?\x60]+)*`,                    // C:\… — 빈칸이 든 이름은 데스크가 잘라 본다
  String.raw`~[\\/][^\s"'<>|*?\x60]*(?: +[^\s"'<>|*?\x60]+)*`,
  String.raw`@?[^\s"'<>|*?\x60:()\[\]{},;]*[^\s"'<>|*?\x60:()\[\]{},;.\\/][\\/][^\s"'<>|*?\x60:()\[\]{},;]+`,   // app/web/x.js · 성적\1학기
  String.raw`@?[\w가-힣-][\w가-힣.()\[\]-]*?\.[A-Za-z][A-Za-z0-9]{0,7}(?![\w])`   // 성적.xlsx · README.md (빈칸 든 이름은 경로로 쓸 때만)
].map(part => `(?:${part})`).join('|'), 'gu');
const URL_MASK = /\b(?:https?|file|ftp):\/\/\S+|\bwww\.\S+/gi;
const pathCache = new Map();               // `${폴더}\n${후보}` → Promise<{text, path, dir}|null>

function pathCandidates(text) {
  const masked = text.replace(URL_MASK, found => ' '.repeat(found.length));
  const found = [];
  for (const match of masked.matchAll(PATH_FIND)) {
    let piece = match[0], index = match.index;
    const lead = piece.length - piece.trimStart().length;      // 이름 맞추기 갈래가 앞 빈칸을 물지 않게
    piece = piece.trimStart(); index += lead;
    if (piece.length > 1 && !/^\d[\d.]*$/.test(piece.replace(/^@/, ''))) found.push({index, text: piece});
    if (found.length >= 30) break;
  }
  return found;
}
async function checkPaths(s, texts) {
  const folder = s.info.folder || '';
  if (pathCache.size > 3000) pathCache.clear();
  const missing = [...new Set(texts.filter(text => !pathCache.has(`${folder}\n${text}`)))];
  if (missing.length) {
    const asked = api('term_paths', {id: s.id, items: missing}).catch(() => missing.map(() => null));
    missing.forEach((text, n) => pathCache.set(`${folder}\n${text}`, asked.then(rows => rows[n] || null)));
  }
  return Promise.all(texts.map(text => pathCache.get(`${folder}\n${text}`)));
}
function openPath(s, path, reveal) {
  attempt(async () => {const note = await api('term_path_open', {id: s.id, path, reveal}); if (note) toast(note);});
}
// 터미널 — 줄바꿈으로 이어진 한 줄을 모아, 글자 위치 ↔ 칸 위치(한글은 두 칸)를 맞춘다
async function termPathLinks(s, y) {
  const buffer = s.term.buffer.active;
  let top = y - 1;
  while (top > 0 && buffer.getLine(top)?.isWrapped) top--;
  let text = '';
  const cells = [];
  for (let row = top; row < top + 12; row++) {
    const line = buffer.getLine(row);
    if (!line || (row > top && !line.isWrapped)) break;
    for (let x = 0; x < s.term.cols; x++) {
      const cell = line.getCell(x);
      if (!cell || cell.getWidth() === 0) continue;
      const chars = cell.getChars() || ' ';
      for (let k = 0; k < chars.length; k++) cells.push({x: x + 1, y: row + 1, w: cell.getWidth()});
      text += chars;
    }
  }
  const found = pathCandidates(text.replace(/\s+$/, ''));
  if (!found.length) return undefined;
  const rows = await checkPaths(s, found.map(item => item.text));
  const links = [];
  found.forEach((item, n) => {
    const hit = rows[n];
    if (!hit) return;
    const first = cells[item.index], last = cells[item.index + hit.text.length - 1];
    if (!first || !last || last.y < y && first.y < y || first.y > y) return;
    links.push({range: {start: {x: first.x, y: first.y}, end: {x: last.x + last.w - 1, y: last.y}}, text: hit.text,
                decorations: {underline: true, pointerCursor: true},
                hover: () => {s.term.element.title = `${hit.path}\n누르기: ${hit.dir ? '폴더 열기' : '열기'} · Shift+누르기: 탐색기에서 보기`;},
                leave: () => {s.term.element.removeAttribute('title');},
                activate: event => openPath(s, hit.path, event.shiftKey)});
  });
  return links.length ? links : undefined;
}
// 대화 보기 — 그린 답의 글(코드 블록 포함)에서 주소를 찾아 링크로 바꾼다
async function linkPaths(s, node) {
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, {acceptNode: text =>
    text.parentElement.closest('a,button,summary,.me-tag') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
  const spots = [];
  for (let text = walker.nextNode(); text; text = walker.nextNode())
    for (const item of pathCandidates(text.data)) spots.push({node: text, ...item});
  if (!spots.length) return;
  const rows = await checkPaths(s, spots.map(spot => spot.text));
  for (let n = spots.length - 1; n >= 0; n--) {                 // 뒤에서부터 — 앞의 위치가 바뀌지 않게
    const hit = rows[n], spot = spots[n];
    if (!hit || !spot.node.isConnected) continue;
    const range = document.createRange();
    range.setStart(spot.node, spot.index);
    range.setEnd(spot.node, spot.index + hit.text.length);
    const link = document.createElement('a');
    link.href = '#';
    link.className = 'path-link';
    link.dataset.path = hit.path;
    link.title = `${hit.path}\n누르기: ${hit.dir ? '폴더 열기' : '열기'} · Shift+누르기: 탐색기에서 보기`;
    try {range.surroundContents(link);} catch {}
  }
}

// 아주 작은 마크다운 — 먼저 이스케이프하고, 코드 블록·표·제목·목록·인용·굵게·기울임·인라인 코드·링크만
const MD_ITEM = /^(\s*)([-*•]|\d+[.)])\s+(.*)$/;
const MD_ROW = /^\s*\|.*\|\s*$/;
const MD_RULE = /^\s*\|[\s:|-]+\|\s*$/;
function markdown(source) {
  const blocks = [];
  const text = String(source).replace(/```([\w+-]*)[^\n]*\n([\s\S]*?)```/g, (_m, lang, code) => {
    blocks.push(`<pre class="code"${lang ? ` data-lang="${esc(lang)}"` : ''}><code>${esc(code.replace(/\n$/, ''))}</code></pre>`);
    return `\u0001${blocks.length - 1}\u0001`;
  });
  const inline = line => esc(line)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\w)/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" data-link>$1</a>');
  const out = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const block = line.trim().match(/^\u0001(\d+)\u0001$/);
    if (block) {out.push(blocks[+block[1]]); continue;}
    if (MD_ROW.test(line)) {
      const rows = [];
      while (i < lines.length && MD_ROW.test(lines[i])) rows.push(lines[i++]);
      i--;
      const cells = row => row.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
      const headed = rows.length > 1 && MD_RULE.test(rows[1]);
      const body = rows.filter(r => !MD_RULE.test(r));
      out.push('<div class="table"><table>' + body.map((r, n) => `<tr>${cells(r).map(c =>
        n === 0 && headed ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`).join('')}</tr>`).join('') + '</table></div>');
      continue;
    }
    const head = line.match(/^(#{1,4})\s+(.*)$/);
    if (head) {const h = Math.min(6, head[1].length + 2); out.push(`<h${h}>${inline(head[2])}</h${h}>`); continue;}
    if (MD_ITEM.test(line)) {
      const tag = /\d/.test(line.match(MD_ITEM)[2]) ? 'ol' : 'ul';
      const items = [];
      while (i < lines.length) {
        const m = lines[i].match(MD_ITEM);
        if (m) {items.push({depth: Math.min(3, Math.floor(m[1].length / 2)), text: m[3]}); i++; continue;}
        if (/^\s{2,}\S/.test(lines[i]) && items.length) {items[items.length - 1].text += ' ' + lines[i].trim(); i++; continue;}
        break;
      }
      i--;
      out.push(`<${tag}>${items.map(it => `<li style="--d:${it.depth}">${inline(it.text)}</li>`).join('')}</${tag}>`);
      continue;
    }
    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {out.push('<hr>'); continue;}
    if (/^>\s?/.test(line)) {out.push(`<blockquote>${inline(line.replace(/^>\s?/, ''))}</blockquote>`); continue;}
    if (!line.trim()) continue;
    const para = [line];
    while (i + 1 < lines.length && lines[i + 1].trim() && !MD_ITEM.test(lines[i + 1]) && !MD_ROW.test(lines[i + 1])
           && !/^(#{1,4}\s|>|\s*\u0001)/.test(lines[i + 1])) para.push(lines[++i]);
    out.push(`<p>${para.map(inline).join('<br>')}</p>`);
  }
  return out.join('');
}

// ── 사진 (스크린샷 등) ── 작은 그림으로 보이고, 누르면 크게
const SHOT_CACHE = 60;
async function shotUrl(s, key) {
  const cacheKey = `${s.chat.conversation}|${key}`;
  if (s.chat.shots.has(cacheKey)) return s.chat.shots.get(cacheKey);
  const job = api('term_chat_image', {id: s.id, key})
    .then(found => found?.ok && found.data ? `data:${found.type || 'image/png'};base64,${found.data}` : '')
    .catch(() => '');
  s.chat.shots.set(cacheKey, job);
  while (s.chat.shots.size > SHOT_CACHE) s.chat.shots.delete(s.chat.shots.keys().next().value);
  const url = await job;
  if (!url) s.chat.shots.delete(cacheKey);       // 다음에 다시 해 본다 (아직 못 읽었을 수 있다)
  return url;
}
function loadShots(s, node) {
  for (const button of node.querySelectorAll('[data-shot]')) {
    shotUrl(s, button.dataset.shot).then(url => {
      button.classList.remove('loading');
      if (!url) {button.classList.add('gone'); button.title = '사진을 찾지 못했습니다 (작업 뒤 지웠을 수 있습니다)'; return;}
      const img = button.querySelector('img');
      img.addEventListener('load', () => {if (s.chat.stick) chatToBottom(s);}, {once: true});
      img.src = url;
    });
  }
}

let shotView = null;
function openShot(s, button) {
  if (button.classList.contains('gone') || button.classList.contains('loading')) return;
  const all = [...s.pane.querySelectorAll('.chat-list [data-shot]:not(.gone):not(.loading)')];
  let at = Math.max(0, all.indexOf(button));
  if (!shotView) {
    shotView = document.createElement('div');
    shotView.className = 'shot-view';
    shotView.tabIndex = -1;
    shotView.innerHTML = '<div class="sv-stage"><img alt="사진"></div>'
      + '<button class="sv-btn sv-prev" data-sv="-1" title="앞 사진 (←)">‹</button><button class="sv-btn sv-next" data-sv="1" title="다음 사진 (→)">›</button>'
      + '<div class="sv-bar"><span class="sv-count"></span><span class="sv-hint">그림을 누르면 원래 크기 · Esc 닫기</span>'
      + '<button class="sv-close" title="닫기 (Esc)">✕</button></div>';
    document.body.appendChild(shotView);
  }
  const img = shotView.querySelector('img');
  const show = () => {
    img.src = all[at].querySelector('img').src;
    shotView.classList.remove('actual');
    shotView.querySelector('.sv-count').textContent = all.length > 1 ? `${at + 1} / ${all.length}` : '';
    shotView.querySelector('.sv-prev').hidden = shotView.querySelector('.sv-next').hidden = all.length < 2;
  };
  const close = () => {shotView.hidden = true; shotView.onclick = shotView.onkeydown = null; $('input').focus();};
  const move = step => {at = (at + step + all.length) % all.length; show();};
  shotView.onclick = event => {
    const step = event.target.closest('[data-sv]');
    if (step) {move(+step.dataset.sv); return;}
    if (event.target === img) {shotView.classList.toggle('actual'); return;}
    close();
  };
  shotView.onkeydown = event => {
    event.stopPropagation();
    if (event.key === 'Escape') close();
    else if (event.key === 'ArrowLeft') move(-1);
    else if (event.key === 'ArrowRight') move(1);
  };
  show();
  shotView.hidden = false;
  shotView.focus();
}

// ── 보낸 말 — 에이전트 기록에 오르기 전까지 «보냄» 말풍선으로 (일하는 중에 보낸 말은 하던 일 사이에 읽힌다)
const PENDING_TTL = 15 * 60 * 1000;
const sameWords = text => String(text || '').replace(/\s+/g, ' ').trim().slice(0, 300);
function addPending(s, text) {
  if (!chatShown(s) || /^\//.test(text.trim())) return;        // /명령은 기록에 말로 남지 않는다
  s.chat.pending.push({text, at: Date.now(), busy: s.state === 'working'});
  s.chat.liveSig = '';
  s.chat.stick = true;
  paintChatLive(s);
}
function settlePending(s, text) {
  const words = sameWords(text);
  const index = s.chat.pending.findIndex(p => sameWords(p.text) === words);
  if (index >= 0) {s.chat.pending.splice(index, 1); s.chat.liveSig = '';}
}
function pendingHtml(s) {
  s.chat.pending = s.chat.pending.filter(p => Date.now() - p.at < PENDING_TTL);
  return s.chat.pending.map(p => `<div class="msg me pending"><div class="me-body">`
    + `<span class="me-tag">${p.busy ? '보냄 · 하던 일 사이에 읽습니다' : '보내는 중'}</span>`
    + `<div class="bubble">${esc(p.text).replace(/\n/g, '<br>')}</div></div></div>`).join('');
}

async function copyChat(button) {
  try {await navigator.clipboard.writeText(button.closest('.msg')?.dataset.raw || ''); toast('복사했습니다.');}
  catch {toast('복사하지 못했습니다.', true);}
}

// 선택지 읽기 — 터미널 아래쪽에서 «1. 2. 3.» 이 이어진 줄과 그 위의 물음
function readChoice(s) {
  const lines = screenText(s, 40).split('\n');          // 글이 있는 마지막 줄에서 거슬러 — 스크롤 자리와 상관없이
  let options = [], first = -1;
  lines.forEach((line, n) => {
    const m = line.match(/^[\s│|]*([❯›>])?\s*(\d+)\.\s+(.+?)[\s│|]*$/);
    if (!m) return;
    if (+m[2] === 1) {options = []; first = n;}                   // 새 목록이 시작됐다 — 아래쪽 것을 쓴다
    if (options.length && +m[2] !== options[options.length - 1].n + 1) return;
    if (!options.length && +m[2] !== 1) return;
    options.push({n: +m[2], text: m[3].trim(), on: !!m[1]});
  });
  const question = [];
  for (let n = first - 1; n >= 0 && question.length < 6; n--) {
    const t = lines[n].replace(/[│╭╮╰╯─┌┐└┘╌]/g, '').trim();
    if (!t) {if (question.length) break; continue;}
    question.unshift(t);
  }
  return {question: question.join('\n'), options: options.length >= 2 ? options : []};
}

// 자주 나오는 Claude Code 물음·선택지는 우리말로 (원문은 단추 위에 마우스를 올리면 보인다). 모르는 문구는 그대로 둔다.
// ⚠️ 바뀔 수 있는 값 — Claude Code 판이 바뀌면 문구가 달라진다(그래도 번호를 보내므로 고르기는 된다). 확인: 2.1.318 (2026-11-06)
const CHOICE_KO = [
  [/^Do you want to proceed\?$/i, '진행할까요?'],
  [/^Do you want to make this edit to (.+)\?$/i, '$1 을(를) 이렇게 고칠까요?'],
  [/^Do you want to create (.+)\?$/i, '$1 을(를) 만들까요?'],
  [/^Yes$/i, '예'],
  [/^Yes, allow all edits during this session.*$/i, '예, 이번 세션 동안 파일 고치기는 모두 허락'],
  [/^Yes, and don'?t ask again for (.+?) commands?.*$/i, '예, 앞으로 $1 명령은 묻지 않기'],
  [/^Yes, and don'?t ask again.*$/i, '예, 앞으로 묻지 않기'],
  [/^Yes, I trust this folder$/i, '예, 이 폴더를 믿습니다'],
  [/^No, and tell Claude what to do differently.*$/i, '아니요, 다르게 하라고 말하기'],
  [/^No, exit$/i, '아니요, 끝내기'],
  [/^No$/i, '아니요'],
  [/^Bash command$/i, '명령 실행'],
  [/^Edit file$/i, '파일 고치기'],
  [/^Create file$/i, '파일 만들기']
];
const choiceKo = text => {
  for (const [pattern, ko] of CHOICE_KO) if (pattern.test(text)) return text.replace(pattern, ko);
  return text;
};

// 대화 아래의 살아 있는 줄 — 일하는 중 · 고르기 카드 · 꺼짐
function paintChatLive(s) {
  if (!chatShown(s)) return;
  const live = s.pane.querySelector('.chat-live');
  const key = s.state || (s.running ? 'working' : 'ended');
  let html = '', sig = key + ':' + s.running;
  if (s.running === false) {
    html = '<div class="live ended">에이전트가 꺼져 있습니다 — <b>다시 시작</b>을 눌러 주세요.</div>';
  } else if (key === 'waiting-for-user-choice' || waitingChoice(s)) {
    const choice = readChoice(s);
    sig = 'choice:' + JSON.stringify(choice);
    html = '<div class="live choice-card"><div class="cc-head"><span class="cc-dot"></span>에이전트가 고르기를 기다립니다</div>'
      + (choice.question ? `<p class="cc-q">${choice.question.split('\n').map(l => esc(choiceKo(l))).join('<br>')}</p>` : '')
      + (choice.options.length
        ? `<div class="cc-opts">${choice.options.map(o => `<button data-pick="${o.n}" class="${o.on ? 'on' : ''}" title="${esc(o.text)}">`
          + `<span class="n">${o.n}</span><span>${esc(choiceKo(o.text))}</span></button>`).join('')}</div>`
        : '<p class="cc-q">선택지를 읽지 못했습니다. 터미널에서 골라 주세요.</p>')
      + '<div class="cc-foot"><button class="link" data-chat-do="term">터미널에서 보기</button><button class="link" data-chat-do="esc">취소 (Esc)</button></div></div>';
  } else if (key === 'working') {
    html = '<div class="live working"><span class="dots"><i></i><i></i><i></i></span>일하는 중 · 멈추려면 위의 <b>멈추기</b></div>';
  }
  const pending = pendingHtml(s);
  sig += '|' + s.chat.pending.map(p => p.at).join(',');
  if (sig === s.chat.liveSig) return;
  s.chat.liveSig = sig;
  live.innerHTML = pending + html;
  if (s.chat.stick) chatToBottom(s);
}

async function pickChoice(s, number) {
  if (!alive(s)) return;
  send(s, String(number));                 // Claude Code 의 번호 선택지는 숫자 하나로 바로 고른다
  s.chat.liveSig = '';
  await sleep(400);
  paintChatLive(s);
}

function setRunning(s, running, closed) {
  if (running === s.running && closed === s.closed) return;
  s.running = running; s.closed = closed;
  s.pane.querySelector('.pane-ended').hidden = running;
  if (!running && !s.state) s.state = closed ? 'ended' : 'agent-exited';
  paintPane(s);
  if (s.id === current) paintHeader();
}

// 에이전트가 선택지(허락 묻기·폴더 믿기·목록)를 띄워 두었나 — 그때 단추가 글자+Enter 를 보내면 글자는 무시되고
// Enter 가 **골라져 있던 답을 눌러 버린다** (2026-10-24 시험: Codex 의 '이 폴더를 믿나요?'가 그렇게 승인됐다).
// 화면 아래쪽에서 번호 매긴 선택지 앞의 커서나 '확인·취소' 안내를 찾는다. 다른 에이전트가 보내는 말도 이것으로 막는다.
const CHOICE_CURSOR = /^\s*[❯›>]\s*\d+\.\s/;
const CHOICE_HINT = /(Esc to (cancel|go back|exit)|Enter to (confirm|select|continue)|enter (select|continue|confirm)|esc (back|quit|cancel))/i;
function waitingChoice(s) {
  const buffer = s.term.buffer.active, bottom = buffer.viewportY + s.term.rows;
  for (let row = Math.max(0, bottom - 30); row < bottom; row++) {
    const line = buffer.getLine(row)?.translateToString(true) || '';
    if (CHOICE_CURSOR.test(line) || CHOICE_HINT.test(line)) return true;
  }
  return false;
}
function choiceGuard(s) {
  if (!waitingChoice(s)) return false;
  toast(chatShown(s) ? `${titleOf(s)} 가 선택을 기다리고 있어요. 대화 아래의 선택지에서 먼저 골라 주세요.`
    : `${titleOf(s)} 가 선택을 기다리고 있어요. 먼저 ↑↓ 와 Enter 로 고르거나 Esc 로 닫은 뒤 다시 해 주세요.`, true);
  focus(s.id);
  if (!chatShown(s)) s.term.focus();
  return true;
}
function screenText(s, lines = 0) {
  // lines 를 주면 글이 있는 마지막 줄에서 거슬러 그만큼(스크롤해 올려 보던 자리와 상관없이), 아니면 지금 보이는 만큼
  const buffer = s.term.buffer.active, rows = [];
  const line = row => buffer.getLine(row)?.translateToString(true) || '';
  let to = lines ? buffer.length : buffer.viewportY + s.term.rows;
  if (lines) while (to > 0 && !line(to - 1).trim()) to--;     // 커서 아래 빈 줄은 세지 않는다
  const from = lines ? Math.max(0, to - lines) : buffer.viewportY;
  for (let row = from; row < to; row++) rows.push(line(row));
  while (rows.length && !rows[rows.length - 1].trim()) rows.pop();
  return rows.join('\n');
}

const alive = (s = now()) => {
  if (!s) {toast('열린 에이전트가 없습니다. 왼쪽의 ‘새 에이전트’를 눌러 주세요.', true); return false;}
  if (s.running) return true;
  toast(s.closed ? '터미널이 끝났습니다. ‘다시 시작’을 눌러 주세요.' : '에이전트가 켜져 있지 않습니다. ‘다시 시작’을 눌러 주세요.', true);
  return false;
};

// ── 위쪽 · 왼쪽 그리기 ─────────────────────────────────
$('tool-name').addEventListener('click', () => {if (current) renameAgent(current);});
function paintHeader() {
  const s = now();
  const c = tools(s);
  $('tool-name').textContent = s ? `${titleOf(s)} · ${s.info.label}` : '에이전트 터미널';
  $('folder').textContent = s ? s.info.folder : '열린 에이전트가 없습니다';
  $('folder').title = s ? `${s.info.folder}\n누르면 탐색기로 엽니다` : '';
  if ((s?.info.folder || '') !== paintHeader.folder) {paintHeader.folder = s?.info.folder || ''; if (knowData) paintKnowPanel();}
  const state = $('state');
  state.hidden = !s;
  if (s) {
    const key = s.state || (s.running ? 'working' : 'ended');
    state.textContent = STATES[key] || key;
    state.className = 'state ' + (s.running ? 'on' : 'off');
  }
  $('skip').hidden = !s?.info.skip;
  $('mode-label').textContent = c.modeLabel;
  $('mode-btn').dataset.tip = c.modeTip;
  document.querySelectorAll('[data-only]').forEach(el => {el.hidden = el.dataset.only !== (s?.info.tool || 'claude');});
  $('target-name').textContent = ownRoom ? `내 다른 PC · ${ownRoomTitle()}` : $('to-all').checked ? '모두' : (s ? titleOf(s) : '-');
  $('composer').classList.toggle('own-mode', !!ownRoom);
  document.title = s ? `${titleOf(s)} · 에이전트 터미널` : '에이전트 터미널';
  if (!$('help').hidden) renderHelp();
}

// 목록은 내용이 바뀔 때만 다시 그린다 — 고르기만 바뀌면 표시만 옮긴다 (다시 그리면 두 번 누르기가 끊긴다)
let listHtml = '';
let renaming = '';            // 이름을 고치는 중인 에이전트 — 그동안은 목록을 다시 그리지 않는다 (입력칸이 사라진다)
// 자식 에이전트(에이전트가 연 것)는 부모 바로 아래에 — [{id, depth}]
function treeOrder() {
  const byAgent = new Map([...sessions.values()].map(s => [s.info.agent, s.id]));
  const kids = new Map();
  const roots = [];
  for (const id of order) {
    const parent = byAgent.get(sessions.get(id).info.parent || '');
    if (parent && parent !== id) {(kids.get(parent) || kids.set(parent, []).get(parent)).push(id);}
    else roots.push(id);
  }
  const out = [];
  const walk = (id, depth) => {
    if (out.some(item => item.id === id)) return;
    out.push({id, depth});
    for (const child of kids.get(id) || []) walk(child, depth + 1);
  };
  roots.forEach(id => walk(id, 0));
  order.forEach(id => walk(id, 0));             // 고리처럼 엉킨 것도 빠지지 않게
  return out;
}

function paintList() {
  const list = $('agents');
  if (renaming) return;
  const html = treeOrder().map(({id, depth}) => {
    const s = sessions.get(id);
    const key = s.state || (s.running ? 'working' : '');
    const parent = s.info.parent ? [...sessions.values()].find(other => other.info.agent === s.info.parent) : null;
    return `<li class="agent${depth ? ' child' : ''}" data-id="${esc(id)}" title="${esc(s.info.folder)}"`
      + `${depth ? ` style="--depth:${Math.min(depth, 3)}"` : ''}>`
      + `<span class="dot ${esc(key)}"></span><div class="copy"><strong>${esc(titleOf(s))}</strong>`
      + `<small>${esc(STATES[key] || '준비 중')} · ${parent ? `도우미 · ${esc(titleOf(parent))}` : esc(s.info.name || '')}</small></div>`
      + `${s.info.team ? '' : '<span class="tag" title="다른 에이전트를 볼 수 없게 열었습니다">혼자</span>'}`
      // 상주·메인은 꼬리표로만 보이고, 바꾸기는 ⋯ 메뉴나 ⚙ 설정 → «상주 · 메인 에이전트» (2026-10-30 정리)
      + `${s.info.main ? '<span class="tag main-tag" title="메인 상주 에이전트 — 맡긴 일(쪽지 분석 …)을 합니다">메인</span>'
          : s.info.resident ? '<span class="tag resident-tag" title="상주 에이전트 — «모두 끄고 닫기»에도 남고 데스크가 켜질 때 다시 열립니다">상주</span>' : ''}`
      + `<button class="x more" data-row-menu="${esc(id)}" title="상주·메인·이름 바꾸기" aria-label="더 보기" aria-haspopup="menu">⋯</button>`
      + `<button class="x" data-close="${esc(id)}" title="이 에이전트 닫기" aria-label="닫기">✕</button></li>`;
  }).join('');
  if (html !== listHtml) list.innerHTML = listHtml = html;
  list.querySelectorAll('.agent').forEach(row => row.setAttribute('aria-current', String(row.dataset.id === current)));
}

$('agents').addEventListener('click', event => {
  const close = event.target.closest('[data-close]');
  if (close) {closeAgent(close.dataset.close); return;}
  const more = event.target.closest('[data-row-menu]');
  if (more) {openRowMenu(more); return;}
  const pen = event.target.closest('[data-rename]');
  if (pen) {renameAgent(pen.dataset.rename); return;}
  if (event.target.closest('.rename')) return;
  const row = event.target.closest('[data-id]');
  if (row) {focus(row.dataset.id); sessions.get(row.dataset.id)?.term.focus();}
});
$('agents').addEventListener('dblclick', event => {
  const row = event.target.closest('[data-id]');
  if (row && !event.target.closest('.rename, .x')) renameAgent(row.dataset.id);
});

// 이름 바꾸기 — 목록의 그 줄에서 바로 고친다. Enter·다른 곳 누르기는 저장, Esc 는 그대로 (비우면 claude-1 같은 원래 이름)
function renameAgent(id) {
  const s = sessions.get(id);
  if (!s || renaming) return;
  focus(id);
  const row = $('agents').querySelector(`.agent[data-id="${CSS.escape(id)}"]`);
  if (!row) return;
  renaming = id;
  const before = s.info.title === s.info.agent ? '' : s.info.title;
  const box = document.createElement('input');
  box.className = 'rename';
  box.maxLength = 30;
  box.value = before;
  box.placeholder = s.info.agent;
  box.setAttribute('aria-label', `‘${titleOf(s)}’ 의 새 이름`);
  box.title = '다른 에이전트도 이 이름으로 부를 수 있어요. 비우면 ' + s.info.agent;
  row.querySelector('strong').replaceWith(box);
  box.focus();
  box.select();
  let done = false;
  const finish = async save => {
    if (done) return;
    done = true;
    const title = box.value.trim();
    renaming = '';
    listHtml = '';                                   // 입력칸을 걷고 다시 그린다
    if (save && title !== before) {
      try {
        s.info = await api('term_rename', {id, title});
        toast((title ? `이름을 ‘${title}’ 로 바꿨어요.` : `이름을 ${s.info.agent} 로 되돌렸어요.`) + (s.info.remoteNote ? ' ' + s.info.remoteNote : ''));
      } catch (error) {toast(error.message || String(error), true);}
    }
    paintPane(s); paintList(); paintHeader();
  };
  box.addEventListener('keydown', event => {
    event.stopPropagation();
    if (event.key === 'Enter') {event.preventDefault(); finish(true);}
    else if (event.key === 'Escape') {event.preventDefault(); finish(false);}
  });
  box.addEventListener('blur', () => finish(true));
}

function setResident(id) {
  const s = sessions.get(id);
  if (!s) return;
  const on = !s.info.resident;
  attempt(async () => {
    toast(await api('term_resident', {id, on}));
    s.info.resident = on;
    if (!on) s.info.main = false;
    listHtml = '';
    paintList();
    paintMain();
  });
}

function openRowMenu(button) {
  const s = sessions.get(button.dataset.rowMenu);
  if (!s) return;
  openMenu(button, `<button data-row="rename">이름 바꾸기</button>`
    + `<button data-row="resident">${s.info.resident ? '상주 풀기' : '상주시키기'}<small>${s.info.resident ? '' : '창을 닫아도 남게'}</small></button>`
    + `<button data-row="main">${s.info.main ? '메인 풀기' : '메인으로 정하기'}<small>${s.info.main ? '' : '맡긴 일을 하게'}</small></button>`
    + `<hr><button data-row="settings">상주 · 메인 설정 열기</button>`, picked => {
    if (picked.row === 'rename') renameAgent(s.id);
    if (picked.row === 'resident') setResident(s.id);
    if (picked.row === 'main') setMain(s.id);
    if (picked.row === 'settings') $('main-btn').click();
  });
}

function setMain(id) {
  const s = sessions.get(id);
  if (!s) return;
  const on = !s.info.main;
  attempt(async () => {
    toast(await api('term_main', {id, on}));
    for (const other of sessions.values()) other.info.main = on ? other === s : (other === s ? false : other.info.main);
    if (on) s.info.resident = true;
    listHtml = '';
    paintList();
    paintMain();
  });
}

async function closeAgent(id) {
  const s = sessions.get(id);
  if (!s) return;
  if (s.info.resident && !confirm(`‘${titleOf(s)}’ 는 상주 에이전트입니다.\n닫으면 상주가 풀리고 꺼집니다. 닫을까요?`)) return;
  if (!s.info.resident && s.running && !confirm(`‘${titleOf(s)}’ 를 닫을까요?\n하던 일이 멈춥니다. 대화는 저장되어 있어 ‘지난 대화’로 다시 불러올 수 있어요.`)) return;
  attempt(async () => {toast(await api('term_close', {id})); dropSession(id);});
}

// 상태(일하는 중·선택 기다림 …)와 이름은 데스크가 안다 — 가끔 묻는다
async function pollList() {
  while (true) {
    await sleep(LIST_POLL);
    if (document.hidden) continue;                  // 칸이 없어도 묻는다 — 예약 업무가 새 칸을 열 수 있다 (2026-11-07)
    let data;
    try {data = await api('term_list');} catch {continue;}
    team = data.team;
    $('team').checked = team;
    // 에이전트가 연 자식 에이전트·닫은 자식 — 화면이 모르는 칸은 붙이고(앞에 두지 않는다), 없어진 칸은 뗀다
    const known = new Set(data.sessions.map(row => row.id));
    for (const id of [...sessions.keys()]) if (!known.has(id)) dropSession(id);
    const fresh = data.sessions.filter(row => !sessions.has(row.id));
    for (const row of fresh) await attach(row.id);
    if (fresh.length) arrange();
    for (const row of data.sessions) {
      const s = sessions.get(row.id);
      if (!s) continue;
      const before = `${s.state}|${s.info.title}`;
      s.state = row.state;
      s.info = {...s.info, ...row};
      if (before !== `${s.state}|${s.info.title}`) {paintPane(s); if (s.id === current) paintHeader();}
    }
    paintList();
  }
}

// ── 에이전트 대화 (중계로 오간 것) ──────────────────────
const feedItems = [];
async function pollEvents(token) {
  while (token === eventsToken) {
    let data;
    try {data = await api('term_events', {after: eventsLast, wait: 4});}
    catch {await sleep(2000); continue;}
    if (token !== eventsToken) return;
    eventsLast = data.last;
    for (const event of data.events) addEvent(event);
  }
}
function addEvent(event) {
  const last = feedItems[feedItems.length - 1];
  if (event.kind === 'request') loadRequests();
  if (!['send', 'computer', 'peer-in', 'peer-out', 'spawn', 'close', 'analysis', 'request'].includes(event.kind) && last && last.kind === event.kind && last.from === event.from && last.to === event.to) {
    last.count = (last.count || 1) + 1;
    last.time = event.time;
  } else feedItems.push({...event});
  feedItems.splice(0, Math.max(0, feedItems.length - 500));
  paintFeed();
  if (event.kind === 'send') {
    const target = sessions.get(event.to);
    if (target) {target.pane.classList.remove('ping'); void target.pane.offsetWidth; target.pane.classList.add('ping');}
  }
}
// 대화 기록은 데스크가 쌓아 둔다(core/agent_term.py events.jsonl) — 오늘 것이 아니면 날짜도 붙인다
function feedWhen(item) {
  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  return item.day && item.day !== today ? `${item.day.slice(5).replace('-', '.')} ${item.time.slice(0, 5)}` : item.time;
}
function paintFeed() {
  const feed = $('feed');
  if (!feedItems.length) {
    feed.innerHTML = `<li class="none">${team ? '에이전트끼리 화면을 보거나 말을 건네면 여기에 보입니다. “다른 에이전트에게 검토해 달라고 해 줘”처럼 시켜 보세요.'
      : '‘에이전트끼리 보기’가 꺼져 있습니다. 켜고 새로 연 에이전트부터 서로를 볼 수 있어요.'}</li>`;
    return;
  }
  feed.innerHTML = feedItems.map((item, index) => {
    if (item.kind === 'send') {
      return `<li class="msg"><span class="when">${esc(feedWhen(item))}</span><span class="who">${esc(item.fromName)}</span> → <span class="who">${esc(item.toName)}</span>`
        + `<span class="body">${esc(item.text)}</span></li>`;
    }
    if (item.kind === 'peer-in' || item.kind === 'peer-out') {   // 다른 PC 와 오간 메시지
      const mine = /^내 (휴대폰|다른 PC)/.test(item.fromName || '') || /^내 (휴대폰|다른 PC)/.test(item.toName || '');
      return `<li class="peer"><span class="when">${esc(feedWhen(item))}</span><span class="tag${mine ? ' mine' : ''}">${mine ? '내 기기' : '다른 선생님'}</span>`
        + `<span class="who">${esc(item.fromName)}</span> → <span class="who">${esc(item.toName)}</span>`
        + `<span class="body">${esc(item.text)}</span>`
        + (item.kind === 'peer-in' && !mine ? `<button class="fwd" data-fwd-feed="${index}" title="이 메시지를 고른 에이전트의 입력칸에 넣습니다 — 확인하고 Enter 로 보내세요">내 에이전트에게 전달</button>` : '')
        + `</li>`;
    }
    if (item.kind === 'spawn' || item.kind === 'close') {   // 에이전트가 자식 에이전트를 열었다·닫았다
      return `<li class="spawn"><span class="when">${esc(feedWhen(item))}</span><span class="who">${esc(item.fromName)}</span>`
        + ` ${item.kind === 'spawn' ? '⊕' : '⊖'} <span class="who">${esc(item.toName)}</span>`
        + `<span class="body">${item.kind === 'spawn' ? (esc(item.text) || '새 에이전트를 열었습니다') : '자식 에이전트를 닫았습니다'}</span></li>`;
    }
    if (item.kind === 'analysis') {                 // 메인 에이전트의 쪽지 분석 결과 (본문은 없다)
      return `<li class="spawn"><span class="when">${esc(feedWhen(item))}</span><span class="who">${esc(item.fromName)}</span> · 쪽지 분석`
        + `<span class="body">${esc(item.text)}</span>${handButton(item.data)}</li>`;
    }
    if (item.kind === 'request') {                  // 다른 선생님의 작업 요청이 왔다 (2026-11-11) — 본문은 없다
      const id = item.data?.request;
      return `<li class="spawn"><span class="when">${esc(feedWhen(item))}</span><span class="who">작업 요청</span>`
        + `<span class="body">${esc(item.text)}</span>`
        + (typeof id === 'string' ? `<button class="hand" data-req-hand="${esc(id)}" title="요청과 수행 안내를 고른 에이전트의 입력칸에 넣습니다">에이전트에게 맡기기</button>` : '')
        + `</li>`;
    }
    if (item.kind === 'memory') {                   // 기억을 고쳤다 — 에이전트가 바로, 또는 밤 12시 지식 업데이트 (2026-11-11)
      return `<li class="spawn"><span class="when">${esc(feedWhen(item))}</span><span class="who">${esc(item.fromName)}</span> · 기억`
        + `<span class="body">${esc(item.text)}</span></li>`;
    }
    if (item.kind === 'cron') {                     // 예약 업무가 돌았다 (2026-11-07)
      return `<li class="spawn"><span class="when">${esc(feedWhen(item))}</span><span class="who">${esc(item.toName || '예약')}</span>`
        + `<span class="body">${esc(item.text)}</span></li>`;
    }
    if (item.kind === 'computer') {                 // 화면 조작 — 무엇을 눌렀고 쳤는지 사람이 따라 볼 수 있게
      return `<li class="cu"><span class="when">${esc(feedWhen(item))}</span><span class="who">${esc(item.fromName)}</span> ⇢ `
        + `<span class="who app">${esc(item.toName)}</span><span class="body">${esc(item.text)}</span></li>`;
    }
    const verb = item.kind === 'read' ? '화면을 봤습니다' : '일이 끝나기를 기다립니다';
    return `<li class="quiet">${esc(item.fromName)} 가 ${esc(item.toName)} 의 ${verb}${item.count > 1 ? ` ×${item.count}` : ''} · ${esc(feedWhen(item))}</li>`;
  }).join('');
  feed.scrollTop = feed.scrollHeight;
}
$('feed-clear').addEventListener('click', () => attempt(async () => {
  if (feedItems.length && !confirm('쌓아 둔 에이전트 대화 기록을 모두 지울까요?')) return;
  await api('term_events_clear');
  feedItems.length = 0;
  paintFeed();
}));

// 쪽지 분석 → 지금 고른 에이전트 (2026-10-30 요청) — 메인이 아니어도. 쪽지 원문은 데스크가 쿨메신저에서 다시 읽어
// 분석과 함께 입력칸에 넣는다(보내지는 않는다). 개인정보로 건너뛴 쪽지는 단추가 없다. desktop.py `_term_analysis_prompt`.
function handButton(data) {
  return data?.handoff && Number.isInteger(data.key)
    ? `<button class="hand" data-hand="${data.key}" title="쪽지 원문과 분석을 고른 에이전트의 입력칸에 넣습니다">에이전트에게 맡기기</button>` : '';
}
async function handOff(key) {
  const s = now();
  if (!s) {toast('먼저 왼쪽 목록에서 맡길 에이전트를 고르세요.', true); return;}
  const data = await api('term_analysis_prompt', {key});
  if (!$('main-settings').hidden) closeMain();
  input.setSelectionRange(input.value.length, input.value.length);
  insertText(input.value.trim() ? '\n\n' + data.text : data.text);
  input.scrollTop = 0;
  toast(`${titleOf(s)} 의 입력칸에 넣었습니다 — 확인하고 Enter 로 보내세요.`);
}
for (const id of ['feed', 'main-recent']) {
  $(id).addEventListener('click', event => {
    const button = event.target.closest('[data-hand]');
    if (button) attempt(() => handOff(Number(button.dataset.hand)));
    const req = event.target.closest('[data-req-hand]');
    if (req) attempt(() => handRequest(req.dataset.reqHand));
    const fwd = event.target.closest('[data-fwd-feed]');
    if (fwd) {
      const item = feedItems[Number(fwd.dataset.fwdFeed)];
      if (item) forwardToAgent(String(item.text || '').replace(/^\(거절함\) /, ''), item.fromName || '다른 선생님');
    }
  });
}

$('team').addEventListener('change', event => attempt(async () => {
  team = event.target.checked;
  toast(await api('term_team_set', {on: team}));
  paintFeed();
}));

// ── 새 에이전트 ─────────────────────────────────────────
async function openNewAgent() {
  let data;
  try {data = await api('term_list', {tools: true});} catch (error) {toast(error.message, true); return;}
  let pick = (now()?.info.tool) || data.tool;
  const s = now();
  const draw = () => {
    $('new-tools').innerHTML = Object.entries(data.tools).map(([name, info]) =>
      `<button data-tool="${esc(name)}" aria-pressed="${name === pick}"${info.installed ? '' : ' disabled'}>${esc(info.label)}`
      + `${info.installed ? '' : '<small>설치 필요</small>'}</button>`).join('');
    const folder = (where, title, sub) => `<button class="choice" data-folder="${esc(where)}">`
      + '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg>'
      + `<div class="copy"><strong>${esc(title)}</strong><small>${esc(sub)}</small></div></button>`;
    $('new-folders').innerHTML = (s ? folder(s.info.folder, `${titleOf(s)} 와 같은 폴더에서`, s.info.folder) : '')
      + folder('pick', '다른 폴더 고르기…', '폴더 고르기 창이 열립니다');
  };
  draw();
  $('new-tools').onclick = event => {
    const button = event.target.closest('[data-tool]');
    if (button && !button.disabled) {pick = button.dataset.tool; draw();}
  };
  $('new-folders').onclick = event => {
    const button = event.target.closest('[data-folder]');
    if (!button) return;
    $('new-agent').hidden = true;
    attempt(async () => {
      const message = await api('term_new', {tool: pick, folder: button.dataset.folder, near: s?.info.folder || ''});
      if (message) toast(message);
    });
  };
  $('new-agent').hidden = false;
}
$('add-agent').addEventListener('click', () => openNewAgent());
$('new-cancel').addEventListener('click', () => {$('new-agent').hidden = true;});

// ── 단추 ────────────────────────────────────────────────
async function runCommand(name) {
  const s = now();
  const command = tools(s)[name];
  if (!command || !alive(s)) return;
  if (typeof command === 'string') {if (choiceGuard(s)) return; await sendLine(s, command);}
  else send(s, command.keys);
  s.term.focus();
}

const ACTIONS = {
  reveal: () => now() && attempt(() => api('term_reveal', {id: current})),
  external: () => now() && attempt(async () => toast(await api('term_external', {id: current}))),
  clear: () => runCommand('clear'),
  resume: () => runCommand('resume'),
  compact: () => runCommand('compact'),
  rewind: () => runCommand('rewind'),
  model: () => runCommand('model'),
  mode: () => runCommand('mode'),
  stop: () => {const s = now(); if (s) {send(s, KEYS.esc); s.term.focus();}},
  restart: button => {
    const id = button?.closest('.pane')?.dataset.id || current;
    const s = sessions.get(id);
    if (!s) return;
    attempt(async () => {
      if (s.running && !confirm(`‘${titleOf(s)}’ 를 끄고 다시 켤까요?\n하던 대화로 다시 켭니다.`)) return;
      toast(await api('term_restart', {id}));     // 새 세션의 epoch 를 보고 읽기가 처음부터 다시 그린다
      s.state = '';
      setTimeout(() => scheduleResize(s, s.term.cols, s.term.rows), 300);
    });
  },
  more: button => openMore(button)
};

document.addEventListener('click', event => {
  const button = event.target.closest('[data-do]');
  if (button && !button.disabled) {
    hideTip();
    ACTIONS[button.dataset.do]?.(button);
    return;
  }
  const layoutButton = event.target.closest('button[data-layout]');
  if (layoutButton) setLayout(layoutButton.dataset.layout);
});
$('folder').addEventListener('click', () => ACTIONS.reveal());

// ── 메뉴 (더 보기 · 자주 쓰는 말) ───────────────────────
let menuOwner = null;
function openMenu(owner, html, onPick) {
  if (menuOwner === owner) {closeMenu(); return;}
  closeMenu();
  const menu = $('menu');
  menu.innerHTML = html;
  menu.hidden = false;
  const box = owner.getBoundingClientRect();
  const width = menu.offsetWidth, height = menu.offsetHeight;
  let top = box.bottom + 6;
  if (top + height > innerHeight - 8) top = Math.max(8, box.top - height - 6);
  menu.style.top = `${top}px`;
  menu.style.left = `${Math.max(8, Math.min(box.left, innerWidth - width - 8))}px`;
  owner.setAttribute('aria-expanded', 'true');
  menuOwner = owner;
  menu.onclick = event => {
    const item = event.target.closest('button');
    if (!item) return;
    closeMenu();
    onPick(item.dataset);
  };
  menu.querySelector('button')?.focus();
}
function closeMenu() {
  $('menu').hidden = true;
  menuOwner?.setAttribute('aria-expanded', 'false');
  menuOwner = null;
}
document.addEventListener('mousedown', event => {
  if (menuOwner && !$('menu').contains(event.target) && !menuOwner.contains(event.target)) closeMenu();
});

function openMore(button) {
  const groups = tools().more.map(([title, items]) => `<div class="label">${esc(title)}</div>`
    + items.map(([command, label]) => `<button data-command="${esc(command)}">${esc(label)}<small>${esc(command)}</small></button>`).join('')).join('');
  openMenu(button, groups + '<hr><div class="label">화면</div>'
    + '<button data-view="rename">이 에이전트 이름 바꾸기</button>'
    + '<button data-view="bigger">글자 크게<small>Ctrl +</small></button>'
    + '<button data-view="smaller">글자 작게<small>Ctrl -</small></button>'
    + '<button data-view="clear">화면 지우기 (대화는 그대로)</button>'
    + '<button data-view="external">바깥 터미널로도 열기</button>'
    + '<button data-view="welcome">처음 안내 다시 보기</button>', picked => {
    const s = now();
    if (picked.command) {if (alive(s) && !choiceGuard(s)) {sendLine(s, picked.command); s.term.focus();}}
    else if (picked.view === 'rename') {if (s) renameAgent(s.id);}
    else if (picked.view === 'bigger') zoom(1);
    else if (picked.view === 'smaller') zoom(-1);
    else if (picked.view === 'clear') {if (s) {s.term.clear(); s.term.focus();}}
    else if (picked.view === 'external') ACTIONS.external();
    else if (picked.view === 'welcome') showWelcome();
  });
}

$('snippets-btn').addEventListener('click', event => {
  const items = snippets.map((item, index) => `<button data-index="${index}" title="${esc(item.text)}">${esc(item.label)}</button>`).join('');
  openMenu(event.currentTarget, (items || '<div class="label">아직 없습니다</div>') + '<hr><button data-edit="1">✎ 목록 고치기</button>', picked => {
    if (picked.edit) openEditor();
    else insertText(snippets[+picked.index].text);
  });
});

// ── 입력칸 ──────────────────────────────────────────────
const input = $('input');
function grow() {
  input.style.height = 'auto';
  input.style.height = `${Math.min(180, input.scrollHeight + 3)}px`;
}
function insertText(text, {space = false} = {}) {
  const start = input.selectionStart ?? input.value.length, end = input.selectionEnd ?? start;
  const before = input.value.slice(0, start);
  const pad = space && before && !/\s$/.test(before) ? ' ' : '';
  input.value = before + pad + text + input.value.slice(end);
  const at = start + pad.length + text.length;
  input.focus();
  input.setSelectionRange(at, at);
  grow();
}
async function submit() {
  closeComplete();
  if (ownRoom) return sendOwn();                             // «내 다른 PC» 방 — 같은 입력칸으로 그 PC 의 에이전트에게
  // Claude Code 는 @파일 바로 뒤의 Enter 를 «목록에서 고르기»로 읽는다 — 칸을 하나 띄워 보낸다
  const text = /(^|\s)@\S+$/.test(input.value) ? input.value + ' ' : input.value;
  const all = $('to-all').checked;
  if (!text.trim()) {if (!all && now()) send(now(), KEYS.enter); return;}
  if (all) {
    const ready = [...sessions.values()].filter(s => s.running && !waitingChoice(s));
    const skipped = [...sessions.values()].filter(s => !ready.includes(s));
    if (!ready.length) {toast('보낼 수 있는 에이전트가 없습니다 — 모두 꺼졌거나 선택을 기다리고 있어요.', true); return;}
    input.value = ''; grow();
    ready.forEach(s => addPending(s, text));
    await Promise.all(ready.map(s => sendLine(s, text, {paste: /\n/.test(text)})));
    toast(`${ready.length}개 에이전트에게 보냈습니다.` + (skipped.length ? ` (못 보냄: ${skipped.map(titleOf).join(', ')})` : ''), !!skipped.length);
    return;
  }
  const s = now();
  if (!alive(s) || choiceGuard(s)) return;
  input.value = '';
  grow();
  addPending(s, text);
  await sendLine(s, text, {paste: /\n/.test(text)});
}
input.addEventListener('input', () => {grow(); updateComplete(); paintGhost();});
input.addEventListener('click', () => updateComplete());
input.addEventListener('blur', () => setTimeout(() => {if (document.activeElement !== input) closeComplete();}, 150));
input.addEventListener('keydown', event => {
  if (event.isComposing || event.keyCode === 229) return;      // 한글 조합 중의 Enter 는 글자를 마치는 것
  if (fontKey(event)) return;
  if (completeKey(event)) return;
  if (event.key === 'Tab' && !event.shiftKey && !input.value && ghostText) {      // Claude Code 가 추천한 다음 말 받기
    event.preventDefault(); input.value = ghostText; grow(); paintGhost(); return;
  }
  if (event.key === 'Enter' && !event.shiftKey) {event.preventDefault(); submit(); return;}
  if (ownRoom) {                                             // 방에서는 이 PC 터미널로 키를 넘기지 않는다 — 빈칸 Esc 는 방 닫기
    if (event.key === 'Escape' && !input.value) {event.preventDefault(); closeRoom();}
    return;
  }
  // 입력칸이 비었을 때는 고르기 키를 고른 에이전트의 터미널로 넘긴다 — 선택지를 여기서도 고를 수 있게
  // 대화 보기에서는 PageUp·PageDown 이 대화를 넘긴다 (Ctrl+Home·End 는 맨 위·맨 아래)
  const chat = now() && chatShown(now()) ? now().pane.querySelector('.chat-scroll') : null;
  const page = chat && {PageUp: -0.85, PageDown: 0.85}[event.key];
  if (page) {event.preventDefault(); chat.scrollBy({top: page * chat.clientHeight}); return;}
  if (chat && event.ctrlKey && (event.key === 'Home' || event.key === 'End')) {
    event.preventDefault(); chat.scrollTop = event.key === 'Home' ? 0 : chat.scrollHeight; return;
  }
  if (input.value || !now()) return;
  const forward = {ArrowUp: KEYS.up, ArrowDown: KEYS.down, ArrowLeft: KEYS.left, ArrowRight: KEYS.right, Escape: KEYS.esc,
                   Tab: event.shiftKey ? KEYS.shiftTab : KEYS.tab}[event.key];
  if (forward) {event.preventDefault(); send(now(), forward);}
});
input.addEventListener('paste', event => {
  if (clipboardImageOnly(event) && now() && !ownRoom) {
    event.preventDefault();
    pasteImage(now());
    toast('사진을 에이전트에게 붙여 넣었습니다.');
  }
});
$('to-all').addEventListener('change', paintHeader);
$('send').addEventListener('click', () => submit());
$('image-btn').addEventListener('click', () => {
  if (!now() || ownRoom) return;
  pasteImage(now());
  toast('클립보드의 사진을 붙여 넣었습니다. 사진이 없으면 아무 일도 없어요.');
});
$('files-btn').addEventListener('click', () => now() && !ownRoom && attempt(async () => {
  const paths = await api('term_pick_files', {id: current});
  if (paths?.length) addPaths(paths);
}));

const quote = path => /\s/.test(path) ? `"${path}"` : path;
function addPaths(paths) {
  insertText(paths.map(quote).join(' ') + ' ', {space: true});
  toast(paths.length === 1 ? '파일 경로를 넣었습니다.' : `파일 ${paths.length}개의 경로를 넣었습니다.`);
}

// ── 에이전트마다 따로 쓰는 입력칸 (2026-11-08 요청) ───────────────
// 1번에 쓰다가 2번으로 바꾸면 2번이 쓰던 말(없었으면 빈칸)이 나오고, 1번으로 돌아오면 그대로 이어 쓴다.
function swapDraft(from, to) {
  if (from) from.draft = {text: input.value, start: input.selectionStart, end: input.selectionEnd};
  const draft = to?.draft;
  input.value = draft?.text || '';
  if (draft) input.setSelectionRange(draft.start, draft.end);
  grow();
  closeComplete();
  paintGhost();
}

// ── 포커스 알림 ───────────────────────────────────────
// 에이전트는 터미널을 «보고 있는지» 알림(ESC[I·ESC[O)으로 안다. Claude Code 는 보고 있지 않으면 다음 말 추천을 만들지 않는다.
// 이 창에서는 아래 입력칸도 그 에이전트의 입력이다 — 창이 앞에 있고 고른 칸이면 «보고 있음», 아니면 «안 보고 있음».
const FOCUS_IN = ESC + '[I', FOCUS_OUT = ESC + '[O';
function syncFocus() {
  const shown = document.hasFocus();
  for (const s of sessions.values()) {
    if (!s.running || !s.term.modes.sendFocusMode) {s.focusSent = null; continue;}
    const want = shown && s.id === current;
    if (s.focusSent !== want) {s.focusSent = want; send(s, want ? FOCUS_IN : FOCUS_OUT);}
  }
}
window.addEventListener('focus', syncFocus);
window.addEventListener('blur', syncFocus);

// ── Claude Code 의 다음 말 추천 ─────────────────────────
// 일을 마치면 Claude Code 가 입력 줄(❯)에 흐린 글씨로 다음에 할 말을 추천한다. 그 글을 입력칸에 흐리게 보이고 Tab 으로 받는다
// (빈 입력칸에서 Enter 는 지금처럼 터미널로 가서, Claude Code 가 추천을 그대로 보낸다).
// 터미널 화면에서 읽는다 — «❯ » 뒤 글이 모두 흐린(dim) 글씨면 추천이다. 사람이 터미널에 직접 쓴 글은 흐리지 않다.
// ⚠️ 바뀔 수 있는 값 — 입력 줄 표시 «❯ »(뒤는 줄바꿈 없는 빈칸 U+00A0), 흐린 글씨(SGR 2), 첫 화면 안내 «Try "…"».
//    확인: Claude Code 2.1.319 (2026-11-08).
const GHOST_POLL = 700;
const PLACEHOLDER = input.placeholder;
let ghostText = '';
function readGhost(s) {
  if (!s || s.info.tool !== 'claude' || !s.running || s.state !== 'idle') return '';
  const buffer = s.term.buffer.active, cell = buffer.getNullCell();
  for (let y = buffer.baseY + s.term.rows - 1; y >= buffer.baseY; y--) {
    const line = buffer.getLine(y);
    if (!line || !/^❯ /.test(line.translateToString(true))) continue;
    let text = '';
    for (let x = 2; x < line.length; x++) {
      line.getCell(x, cell);
      const chars = cell.getChars();
      if (!chars) {if (cell.getWidth()) text += ' '; continue;}
      if (!cell.isDim()) return '';
      text += chars;
    }
    text = text.trim();
    return /^Try "/.test(text) ? '' : text;
  }
  return '';
}
function paintGhost() {
  const next = !input.value && !$('to-all').checked && !ownRoom ? readGhost(now()) : '';
  if (next === ghostText) return;
  ghostText = next;
  input.classList.toggle('ghost', !!next);
  input.placeholder = next ? `${next}   — Tab 으로 받기` : PLACEHOLDER;
}
setInterval(() => {syncFocus(); paintGhost();}, GHOST_POLL);

// ── 자동 완성 — / 명령 · @ 파일 (2026-11-08 요청) ─────────────────
// 터미널에서 / 나 @ 를 쓰면 에이전트가 목록을 띄우듯, 입력칸에서도 같은 목록을 띄운다. 목록은 데스크가 만든다
// (term_complete · core/agent_complete.py). ↑↓ 고르기 · Tab/Enter 넣기 · Esc 닫기.
const COMPLETE_LIMIT = 60;
const COMMAND_TTL = 15000;
const KIND_LABEL = {builtin: '기본', command: '내 명령', skill: '스킬'};
const complete = {open: false, kind: '', items: [], index: 0, start: 0, end: 0, token: 0, timer: 0};

function completeContext() {
  const caret = input.selectionStart, text = input.value;
  if (caret !== input.selectionEnd) return null;
  const before = text.slice(0, caret), tail = text.slice(caret).match(/^\S*/)[0].length;
  const slash = /^\/(\S*)$/.exec(before);
  if (slash) return {kind: 'commands', query: slash[1], start: 0, end: caret + tail};
  const at = /(^|\s)@("?)([^\s"]*)$/.exec(before);
  if (at) return {kind: 'files', query: at[3], start: caret - at[3].length - at[2].length - 1, end: caret + tail};
  return null;
}

async function commandList(s) {
  if (s.commands && Date.now() - s.commands.at < COMMAND_TTL) return s.commands.items;
  const items = await api('term_complete', {id: s.id, kind: 'commands'});
  s.commands = {at: Date.now(), items};
  return items;
}

function rankCommands(items, query) {
  const q = query.toLowerCase();
  if (!q) return items;
  const rank = item => {
    const name = item.name.toLowerCase();
    if (name.startsWith(q)) return 0;
    if (name.split(/[:\-_]/).some(part => part.startsWith(q))) return 1;
    if (name.includes(q)) return 2;
    return (item.desc || '').toLowerCase().includes(q) ? 3 : -1;
  };
  return items.map(item => [rank(item), item]).filter(([score]) => score >= 0)
    .sort((a, b) => a[0] - b[0]).map(([, item]) => item);
}

function updateComplete() {
  const s = now(), context = s && !ownRoom && completeContext();
  clearTimeout(complete.timer);
  if (!context) {closeComplete(); return;}
  const token = ++complete.token;
  const run = async () => {
    let items;
    try {
      items = context.kind === 'commands' ? rankCommands(await commandList(s), context.query)
        : await api('term_complete', {id: s.id, kind: 'files', query: context.query});
    } catch {items = [];}
    if (token !== complete.token || now() !== s) return;
    Object.assign(complete, {open: true, kind: context.kind, items: items.slice(0, COMPLETE_LIMIT), index: 0,
                             start: context.start, end: context.end});
    paintComplete();
  };
  if (context.kind === 'files') complete.timer = setTimeout(run, 120); else run();
}

function paintComplete() {
  const box = $('complete');
  if (!complete.open) {box.hidden = true; return;}
  const files = complete.kind === 'files';
  const head = `<div class="cp-head">${files ? '파일 — 에이전트가 연 폴더 안' : '명령'}<span>↑↓ 고르기 · Tab/Enter 넣기 · Esc 닫기</span></div>`;
  const rows = complete.items.map((item, index) => `<button class="cp-item" role="option" tabindex="-1" data-index="${index}" aria-selected="${index === complete.index}">`
    + (files ? `<span class="cp-name">${esc(item.path)}</span><span class="cp-kind">${item.dir ? '폴더' : ''}</span>`
       : `<span class="cp-name">/${esc(item.name)}</span><span class="cp-desc">${esc(item.desc)}</span><span class="cp-kind">${KIND_LABEL[item.kind] || ''}</span>`)
    + '</button>').join('');
  box.innerHTML = head + (rows || `<div class="cp-empty">${files ? '맞는 파일이 없습니다' : '맞는 명령이 없습니다'}</div>`);
  box.hidden = false;
  box.querySelector('[aria-selected="true"]')?.scrollIntoView({block: 'nearest'});
}

function closeComplete() {
  clearTimeout(complete.timer);
  complete.token++;
  complete.open = false;
  $('complete').hidden = true;
}

// 고른 것을 입력칸에 넣을 글. Claude Code 는 «@경로»(빈칸이 있으면 @"경로"), Codex 는 경로만 넣는다. 폴더는 이어서 고른다.
function insertionOf(item) {
  if (complete.kind === 'commands') return {text: `/${item.name} `, again: false};
  const claude = (now()?.info.tool || 'claude') !== 'codex';
  const spaced = /\s/.test(item.path);
  if (item.dir && claude && !spaced) return {text: `@${item.path}`, again: true};
  const quoted = spaced ? `"${item.path}"` : item.path;
  return {text: (claude ? '@' : '') + quoted + ' ', again: false};
}

function acceptComplete(index = complete.index) {
  const item = complete.items[index];
  if (!item) return;
  const {text, again} = insertionOf(item);
  const value = input.value;
  input.value = value.slice(0, complete.start) + text + value.slice(complete.end);
  const at = complete.start + text.length;
  input.focus();
  input.setSelectionRange(at, at);
  grow();
  closeComplete();
  if (again) updateComplete();
}

function completeKey(event) {
  if (!complete.open) return false;
  const count = complete.items.length;
  if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && count) {
    event.preventDefault();
    complete.index = (complete.index + (event.key === 'ArrowDown' ? 1 : -1) + count) % count;
    paintComplete();
    return true;
  }
  if (event.key === 'Escape') {event.preventDefault(); closeComplete(); return true;}
  if ((event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey)) && count) {
    // 이미 다 쓴 것에서 Enter 는 그대로 보낸다 (예: «/clear» 를 다 쓰고 Enter)
    const {text} = insertionOf(complete.items[complete.index]);
    if (event.key === 'Enter' && input.value.slice(complete.start, complete.end) === text.trimEnd()) {closeComplete(); return false;}
    event.preventDefault();
    acceptComplete();
    return true;
  }
  return false;
}

input.addEventListener('keyup', event => {
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) updateComplete();
});
$('complete').addEventListener('mousedown', event => {
  event.preventDefault();                           // 입력칸의 포커스를 빼앗지 않는다
  const item = event.target.closest('.cp-item');
  if (item) acceptComplete(+item.dataset.index);
});

// 끌어 놓기 — 경로는 데스크가 알려 준다 (dropped). 여기서는 놓을 자리만 보인다
let dragDepth = 0;
const hasFiles = event => [...(event.dataTransfer?.types || [])].includes('Files');
document.addEventListener('dragenter', event => {if (hasFiles(event)) {event.preventDefault(); if (++dragDepth === 1) $('drop').hidden = false;}});
document.addEventListener('dragover', event => {if (hasFiles(event)) {event.preventDefault(); event.dataTransfer.dropEffect = 'copy';}});
document.addEventListener('dragleave', event => {if (hasFiles(event) && --dragDepth <= 0) {dragDepth = 0; $('drop').hidden = true;}});
document.addEventListener('drop', event => {if (hasFiles(event)) {event.preventDefault(); dragDepth = 0; $('drop').hidden = true;}});

// ── 말풍선 (단추 설명) ──────────────────────────────────
let tipTimer = 0;
function hideTip() {clearTimeout(tipTimer); $('tip').hidden = true;}
document.addEventListener('mouseover', event => {
  const target = event.target.closest('[data-tip]');
  if (!target) return;
  clearTimeout(tipTimer);
  tipTimer = setTimeout(() => {
    if (!target.dataset.tip) return;
    const tip = $('tip');
    tip.innerHTML = target.dataset.tip;
    tip.hidden = false;
    const box = target.getBoundingClientRect();
    tip.style.top = `${Math.min(box.bottom + 8, innerHeight - tip.offsetHeight - 8)}px`;
    tip.style.left = `${Math.max(8, Math.min(box.left, innerWidth - tip.offsetWidth - 8))}px`;
  }, 380);
});
document.addEventListener('mouseout', event => {if (event.target.closest('[data-tip]')) hideTip();});

// ── 도움말 ──────────────────────────────────────────────
const HELP_TABS = [['start', '처음이라면'], ['team', '여러 에이전트'], ['computer', '화면 조작'], ['buttons', '단추'], ['keys', '키보드'], ['commands', '명령어'],
                   ['safe', '안전하게'], ['trouble', '문제 해결']];
let helpTab = store.get('helpTab', 'start');

function helpBody(tab) {
  const s = now(), c = tools(s), claude = (s?.info.tool || 'claude') !== 'codex', label = s?.info.label || '에이전트';
  if (tab === 'start') return `
    <h2>에이전트는 무엇인가요?</h2>
    <p>${esc(label)}는 <b>연 폴더 안의 파일을 읽고, 만들고, 고치는 AI 도우미</b>입니다. 사람에게 부탁하듯 한국어로 적으면 됩니다.</p>
    <h3>이렇게 부탁해 보세요</h3>
    <ul>
      <li>“이 폴더에 무엇이 있는지 설명해 줘”</li>
      <li>“성적.xlsx 에서 반별 평균을 구해 새 시트에 정리해 줘”</li>
      <li>“회의록.hwpx 내용을 다섯 줄로 요약해 줘”</li>
    </ul>
    <h3>잘 시키는 요령</h3>
    <ul>
      <li><b>무엇을, 어느 파일로, 어떤 모양으로</b> 원하는지 함께 적으면 결과가 좋아요.</li>
      <li>큰일은 “먼저 계획부터 보여 줘”라고 하고, 계획을 본 뒤 진행시키세요.</li>
      <li>다른 일을 시킬 때는 <b>새 대화</b>를 눌러 앞 이야기와 섞이지 않게 하세요.</li>
      <li>파일은 창에 <b>끌어다 놓으면</b> 경로가 입력칸에 들어갑니다.</li>
    </ul>
    <h3>대답을 기다리는 동안</h3>
    <p>에이전트가 일하는 동안 터미널에 진행 상황이 흘러갑니다. 엉뚱한 쪽으로 가면 <b>멈추기</b>(Esc)를 누르고 다시 설명하세요.</p>`;
  if (tab === 'team') return `
    <h2>여러 에이전트 함께 쓰기</h2>
    <p>왼쪽의 <b>새 에이전트</b>로 Claude Code·Codex 를 여럿 띄울 수 있습니다. 위쪽 단추와 아래 입력칸은 <b>고른 에이전트</b>(파란 테두리, 목록에서 강조된 것)에게 갑니다.</p>
    <ul>
      <li>왼쪽 위 칸 단추로 <b>하나 · 나란히 둘 · 네 칸</b>을 고릅니다.</li>
      <li>목록의 <b>✎</b> 를 누르거나 이름을 <b>두 번 누르면</b> 그 자리에서 이름을 바꿀 수 있어요 (예: “작성 담당”, “검토 담당”). 위쪽 이름을 눌러도 됩니다.</li>
      <li>창을 닫을 때 켜진 에이전트가 있으면 <b>모두 끌지</b> 묻습니다. <b>켜 두면</b> 창만 닫히고 하던 일을 계속하며, 독의 에이전트 터미널을 누르면 그대로 다시 보여요.</li>
      <li>점 색: <span class="dot working" style="display:inline-block"></span> 일하는 중 · <span class="dot idle" style="display:inline-block"></span> 입력 기다림 · <span class="dot waiting-for-user-choice" style="display:inline-block"></span> <b>내가 골라 줘야 함</b> · <span class="dot ended" style="display:inline-block"></span> 꺼짐</li>
      <li>아래 <b>모두에게</b>를 켜면 같은 말을 열린 에이전트 모두에게 보냅니다.</li>
    </ul>
    <h3>에이전트끼리 보기</h3>
    <p>위쪽 <b>에이전트끼리 보기</b>가 켜져 있으면, 새로 연 에이전트는 다른 에이전트의 <b>화면을 읽고 말을 건넬</b> 수 있습니다. 이렇게 시켜 보세요:</p>
    <ul>
      <li>“만든 보고서를 codex-1 에게 보내서 검토해 달라고 하고, 의견을 반영해 줘”</li>
      <li>“claude-2 가 하는 일이 끝나면 그 결과를 받아서 표로 정리해 줘”</li>
      <li>“이 일을 둘로 나눠 한쪽은 다른 에이전트에게 맡겨 줘”</li>
    </ul>
    <p>오간 말은 왼쪽 아래 <b>에이전트 대화</b>에 보입니다. 에이전트는 데스크 안 중계(이 PC 안에서만 열림)를 <code>curl</code> 로 부릅니다 — 각자 받은 열쇠로만.</p>
    <div class="callout">상대 에이전트가 <b>허락을 묻는 중</b>(주황 점)이면 말을 넣지 않습니다. 고르는 일은 언제나 사람이 합니다. 그래도 에이전트끼리 일을 주고받으면 생각보다 많이 움직이니, 결과는 꼭 확인하세요.</div>
    <h3>에이전트가 여는 도우미 에이전트</h3>
    <p>일을 나눠 맡기면 좋을 때 에이전트가 <b>도우미 에이전트</b>를 새 칸으로 직접 엽니다. 목록에서 연 에이전트 아래에 들여 써서 보이고, 사람이 그 칸을 보거나 말을 걸 수도 있어요. 예:</p>
    <ul>
      <li>“1학년·2학년 자료를 도우미 에이전트 둘에게 나눠 정리하게 하고, 결과를 모아 줘”</li>
    </ul>
    <p>도우미는 연 에이전트와 <b>같은 권한 모드</b>로, 그 폴더 안에서만 일합니다. 한 에이전트가 4개까지, 도우미의 도우미까지만 열 수 있어요. 일을 마치면 결과를 연 에이전트에게 보내고, 연 에이전트가 닫습니다. 새 폴더면 ‘이 폴더를 믿나요?’를 사람이 골라 줘야 합니다.</p>
    ${peerState.available ? `<h3>다른 PC 의 에이전트</h3>
    <p>위쪽 <b>다른 PC</b> 를 켜면, 다른 선생님(또는 내 다른 PC)의 데스크에 열린 에이전트에게 <b>메시지를 보내고 결과를 돌려받을</b> 수 있습니다. SPACEKIJUN 이 중계하고, 교직원끼리만 됩니다. 예:</p>
    <ul>
      <li>“다른 PC 목록을 보고, 김○○ 선생님의 에이전트에게 이 표를 검토해 달라고 보낸 뒤 결과를 기다려 줘”</li>
    </ul>
    <p>받는 쪽에서는 처음 보내온 선생님마다 <b>이번만 / 이 선생님은 항상 / 거절</b>을 묻습니다. 내가 보낸 메시지의 <b>결과</b>는 묻지 않고 보낸 에이전트에게 들어옵니다. 메시지만 오가고, 서로의 화면을 읽거나 앱을 다루지는 못합니다. 10분 안에 받아 가지 않은 메시지는 사라지고, 주고받은 글은 서버에 7일 남습니다.</p>
    <p><b>내 휴대폰에서도</b> 보낼 수 있어요 — 스페이스기전 모바일(<b>/m</b>)의 «에이전트» 탭에서 이 PC 에 열린 에이전트를 골라 일을 맡기면, 묻지 않고 바로 넣고 결과를 휴대폰으로 돌려받습니다(위쪽 <b>휴대폰</b> 스위치를 켜야 합니다 — «다른 PC» 와는 따로 켜고 끕니다. <b>에이전트끼리 보기</b>를 켜고 연 에이전트만 휴대폰에 보여요).</p>` : ''}`;
  if (tab === 'computer') return `
    <h2>다른 앱 다루게 하기</h2>
    <p>에이전트끼리 보기가 켜져 있으면, 에이전트가 이 PC 의 <b>다른 앱 창을 읽고 누르고 글자를 입력</b>할 수 있습니다. 예:</p>
    <ul>
      <li>“쿨메신저에서 받은 쪽지 목록을 읽어서 정리해 줘”</li>
      <li>“열려 있는 엑셀의 2반 성적을 보고 평균을 알려 줘”</li>
      <li>“메모장에 방금 만든 안내문을 붙여 넣어 줘”</li>
    </ul>
    <h3>허락</h3>
    <p>에이전트가 어떤 앱을 <b>처음</b> 다루려 하면 이 창에 <b>허락 / 거절</b>을 묻습니다. 2분 안에 답하지 않으면 거절됩니다. 허락할 때 범위를 고릅니다.</p>
    <ul>
      <li><b>이번만</b> — 그 에이전트 · 그 앱에만, 이 창을 닫을 때까지.</li>
      <li><b>이 앱은 항상</b> — 어느 에이전트든 그 앱은 다음부터 묻지 않습니다 (데스크를 다시 켜도).</li>
      <li><b>모든 앱 항상</b> — 어떤 앱이든 묻지 않습니다.</li>
    </ul>
    <p>항상 허락은 위쪽 <b>화면 조작</b> 단추에서 켜고 끄고, 열린 앱을 골라 미리 더하거나 뺄 수 있습니다. 항상 허락이어도 이 창이 열려 있을 때만 쓰입니다.</p>
    <h3>멈추기</h3>
    <p>허락해 둔 동안 화면 맨 위에 빨간 <b>멈추기</b> 막대가 떠 있습니다. 누르면 모든 허락을 거두고 에이전트가 더는 다른 앱을 만지지 못합니다. 항상 허락도 <b>다시 켜기</b>를 누를 때까지 쉬고, 그동안은 다시 묻습니다. 위쪽 <b>화면 조작</b> 단추로 하나씩 거둘 수도 있어요.</p>
    <h3>지키는 것</h3>
    <ul>
      <li>에이전트는 <b>데스크 창</b>과 비밀번호 관리자·Windows 로그인·권한 확인 창을 다룰 수 없습니다.</li>
      <li>비밀번호·인증번호 칸은 값이 가려지고, 입력하지 않습니다.</li>
      <li>누를 자리를 다른 창이 가리고 있으면 누르지 않습니다.</li>
      <li>에이전트가 다루는 동안 마우스·키보드가 움직입니다. 그동안은 손을 떼고 지켜봐 주세요.</li>
    </ul>
    <div class="callout safe">쪽지·문자 보내기, 제출, 삭제처럼 되돌리기 어려운 일은 “보내기 전에 내용을 나에게 먼저 보여 줘”라고 꼭 덧붙이세요. 한 일은 왼쪽 아래 <b>에이전트 대화</b>에 하나하나 남습니다.</div>`;
  if (tab === 'buttons') return `
    <h2>위쪽 단추 — 고른 에이전트에게</h2>
    <table>
      <tr><td><b>폴더 열기</b></td><td>그 에이전트가 열린 폴더를 탐색기로 엽니다.</td></tr>
      <tr><td><b>새 대화</b></td><td>대화를 비우고 새로 시작합니다 <code>${esc(c.clear)}</code></td></tr>
      <tr><td><b>지난 대화</b></td><td>예전 대화를 골라 이어서 합니다 <code>${esc(c.resume)}</code></td></tr>
      <tr><td><b>대화 줄이기</b></td><td>긴 대화를 요약해 줄입니다 <code>${esc(c.compact)}</code></td></tr>
      ${claude ? `<tr><td><b>되돌리기</b></td><td>대화·파일을 앞 지점으로 되돌립니다 <code>/rewind</code></td></tr>` : ''}
      <tr><td><b>모델</b></td><td>AI 모델을 고릅니다 <code>${esc(c.model)}</code></td></tr>
      <tr><td><b>${esc(c.modeLabel)}</b></td><td>${c.modeTip}</td></tr>
      <tr><td><b>멈추기</b></td><td>하던 일을 멈춥니다 (Esc)</td></tr>
      <tr><td><b>다시 시작</b></td><td>에이전트를 껐다 켭니다</td></tr>
    </table>
    <h2>왼쪽 · 아래쪽</h2>
    <table>
      <tr><td><b>새 에이전트</b></td><td>에이전트를 하나 더 띄웁니다 (같은 폴더 · 다른 폴더).</td></tr>
      <tr><td><b>✕</b></td><td>그 에이전트를 닫습니다.</td></tr>
      <tr><td><b>입력칸</b></td><td>Enter 로 보내고 Shift+Enter 로 줄을 바꿉니다. 비어 있을 때 ↑↓·Enter·Esc 는 터미널로 갑니다.</td></tr>
      <tr><td><b>모두에게</b></td><td>입력칸의 말을 열린 에이전트 모두에게 보냅니다.</td></tr>
      <tr><td><b>자주 쓰는 말</b></td><td>자주 하는 부탁을 골라 넣습니다. ‘목록 고치기’로 바꿀 수 있어요.</td></tr>
      <tr><td><b>파일 넣기</b></td><td>파일을 골라 경로를 넣습니다.</td></tr>
      <tr><td><b>사진 붙여넣기</b></td><td>캡처(Win+Shift+S)한 사진을 에이전트에게 보여 줍니다.</td></tr>
    </table>`;
  if (tab === 'keys') return `
    <h2>키보드</h2>
    <table>
      <tr><td><kbd>Enter</kbd></td><td>보내기 · 선택지 고르기</td></tr>
      <tr><td><kbd>Shift</kbd>+<kbd>Enter</kbd></td><td>줄 바꾸기</td></tr>
      <tr><td><kbd>↑</kbd> <kbd>↓</kbd></td><td>선택지 옮기기 · (터미널에서) 앞서 보낸 말 다시 불러오기</td></tr>
      <tr><td><kbd>Esc</kbd></td><td>하던 일 멈추기${claude ? ' · 두 번 누르면 앞 메시지로 되돌리기' : ''}</td></tr>
      ${claude ? '<tr><td><kbd>Shift</kbd>+<kbd>Tab</kbd></td><td>권한 모드 바꾸기</td></tr>' : ''}
      <tr><td><kbd>Ctrl</kbd>+<kbd>C</kbd></td><td>고른 글이 있으면 복사, 없으면 입력 지우기 (두 번이면 에이전트가 꺼져요)</td></tr>
      <tr><td><kbd>Ctrl</kbd>+<kbd>V</kbd> · 오른쪽 클릭</td><td>붙여넣기 (글이 없고 사진이 있으면 사진)</td></tr>
      <tr><td>마우스로 끌기</td><td>글 고르기 — ${claude ? 'Claude Code 는 고르자마자 클립보드에 복사합니다. ' : ''}잘 안 골라지면 <kbd>Shift</kbd> 를 누른 채 끄세요.</td></tr>
      <tr><td><kbd>Ctrl</kbd>+<kbd>+</kbd> / <kbd>-</kbd> / <kbd>0</kbd></td><td>글자 크게 / 작게 / 원래대로</td></tr>
      <tr><td><kbd>F1</kbd></td><td>이 도움말 열고 닫기</td></tr>
    </table>
    <h3>입력할 때 쓰는 기호</h3>
    <table>
      <tr><td><code>/</code></td><td>맨 앞에 쓰면 입력칸 위에 명령 목록이 나옵니다 (내 명령·스킬 포함) — <kbd>↑</kbd><kbd>↓</kbd> 고르고 <kbd>Tab</kbd>·<kbd>Enter</kbd></td></tr>
      <tr><td><code>@</code></td><td>에이전트가 연 폴더에서 파일을 찾아 넣습니다 (예: <code>@성적</code> 까지 쓰면 맞는 파일이 나와요)</td></tr>
      ${claude ? '<tr><td>흐린 글씨</td><td>일을 마친 뒤 Claude Code 가 추천하는 다음 말 — 빈 입력칸에서 <kbd>Tab</kbd> 으로 받습니다</td></tr>' : ''}
      ${claude ? '<tr><td><code>!</code></td><td>맨 앞에 쓰면 명령 창 명령을 바로 실행합니다</td></tr>' : ''}
    </table>`;
  if (tab === 'commands') {
    const list = [...(claude
      ? [['/clear', '새 대화'], ['/resume', '지난 대화 이어 하기'], ['/compact', '대화 줄이기'], ['/rewind', '되돌리기'], ['/model', '모델 고르기']]
      : [['/new', '새 대화'], ['/resume', '지난 대화 이어 하기'], ['/compact', '대화 줄이기'], ['/model', '모델 고르기'], ['/permissions', '권한 설정']]),
      ...c.more.flatMap(([, items]) => items)];
    return `<h2>명령어 모음</h2>
      <p>누르면 입력칸에 넣습니다. 확인하고 Enter 를 누르세요. 터미널에 <code>/</code> 만 쳐도 전체 목록이 나옵니다.</p>
      ${list.map(([command, text]) => `<button class="cmd" data-insert="${esc(command)}"><code>${esc(command)}</code><span>${esc(text)}</span></button>`).join('')}`;
  }
  if (tab === 'safe') return `
    <h2>안전하게 쓰기</h2>
    <div class="callout safe"><b>권한 묻지 않기</b>가 켜져 있으면 에이전트가 묻지 않고 파일을 고치고 명령을 실행합니다. 중요한 자료가 있는 폴더에서는 끄고 쓰세요 (독의 에이전트 터미널 패널). 에이전트끼리 보기와 함께 켜면 한 에이전트의 부탁으로 다른 에이전트가 묻지 않고 움직일 수 있습니다.</div>
    <ul>
      <li>허락을 물을 때는 <b>무엇을 하려는지 읽고</b> 고르세요. 모르겠으면 거절하고 “무슨 뜻이야?” 라고 물어도 됩니다.</li>
      <li>원본 파일은 먼저 <b>복사본을 만들어 두고</b> 시키면 마음이 편합니다.</li>
      <li>학생·교직원 <b>개인정보</b>가 담긴 파일은 꼭 필요한 것만 다루게 하세요. 대화 내용은 AI 회사 서버로 보내집니다.</li>
      <li>에이전트도 틀립니다. 숫자·이름·날짜는 결과 파일을 열어 <b>직접 확인</b>하세요.</li>
      <li>데스크가 꺼졌다 켜지면(업데이트·PC 재시작 포함) 켜 두었던 에이전트들이 <b>하던 대화 그대로</b> 다시 열립니다. ✕ 로 닫은 에이전트와 창을 닫으며 ‘모두 끄기’한 것은 다시 열지 않아요.</li>
      <li>위쪽 <b>⚙ 설정 → 상주 · 메인 에이전트</b>에서(또는 목록 줄의 <b>⋯</b>) 에이전트를 <b>상주</b>시킵니다(여럿). ‘모두 끄기’에도 남고, 데스크가 켜질 때 창 없이 자동으로 열리고, 꺼지면 데스크가 하던 대화로 되살립니다.</li>
      <li>같은 곳에서 상주 에이전트 하나를 <b>메인</b>으로 고르고 맡길 일을 켭니다 — 지금은 <b>쿨메신저 쪽지 분석</b>: 새 쪽지마다 처리할 일·나와 관련 있는지·AI 가 할 수 있는지를 Haiku 로 따로 보고, 할 일이 있으면 스페이스기전 알림으로 보냅니다. 개인정보가 보이는 쪽지는 분석하지 않아요.</li>
      <li>분석 결과는 왼쪽 <b>에이전트 대화</b>와 «상주 · 메인 에이전트»의 최근 분석에 남습니다. <b>에이전트에게 맡기기</b>를 누르면 쪽지 원문과 분석이 <b>지금 고른 에이전트</b>의 입력칸에 들어가요(메인이 아니어도). 확인하고 Enter.</li>
      <li>오른쪽 패널의 <b>폴더</b>에서 에이전트가 함께 쓰는 <b>작업 폴더</b>(저장소·업무 폴더)를 고릅니다. 줄을 누르면 그 폴더가 열리고, <b>＋ 작업 폴더로</b>는 지금 에이전트의 폴더를 바로 더해요. 폴더마다 <b>지식 파일</b>이 있어, 에이전트가 읽고 알게 된 것을 쌓아 갑니다.</li>
      <li>위쪽 <b>보기</b>(▥)로 화면 배치를 고릅니다. 양쪽 패널 가장자리의 <b>‹ ›</b> 손잡이로도 접고 폅니다 — 오른쪽 <b>스킬 패널</b>(Ctrl+Alt+B)에서 스킬을 펼쳐 할 수 있는 일을 누르면 입력칸에 들어가요. ☆ 로 즐겨찾기. 왼쪽 목록은 Ctrl+B.</li>
      <li>오른쪽 패널의 <b>현황</b>에서 고른 에이전트의 <b>컨텍스트</b>(얼마나 찼는지), <b>사용량</b>(5시간·7일 한도, 이 대화의 비용), <b>결과물</b>(Claude 가 만들거나 고친 파일 — 누르면 열고 📂 는 폴더에서 보기)을 봅니다. Claude Code 에이전트만.</li>
    </ul>`;
  return `
    <h2>문제가 생기면</h2>
    <details open><summary>처음 열었더니 영어로 뭔가 물어봐요</summary><p><b>Trust this folder?</b> — 이 폴더의 파일을 다뤄도 되는지 묻는 것입니다. 내 자료 폴더가 맞으면 ↑↓ 로 <b>Yes / Trust</b> 를 고르고 Enter. 그 뒤 로그인을 물으면 안내대로 고르면 브라우저가 열립니다.${claude ? '' : ' Codex 는 이어서 <b>샌드박스 설정</b>을 물을 수 있어요 — 관리자 권한이 없으면 2번(non-admin)을 고르세요.'}</p></details>
    <details><summary>화면이 멈춘 것 같아요</summary><p>먼저 <b>멈추기</b>를 눌러 보세요. 그래도 그대로면 <b>다시 시작</b>을 누릅니다.</p></details>
    <details><summary>“에이전트가 끝났습니다”가 떠요</summary><p>에이전트가 꺼진 것입니다 (Ctrl+C 를 두 번 눌렀거나 오류). <b>다시 시작</b>을 누르면 하던 대화로 다시 켭니다.</p></details>
    <details><summary>로그인하라고 해요</summary><p>처음 한 번은 로그인이 필요합니다. 터미널에 나온 안내대로 고르면 브라우저가 열립니다. 로그인을 마치고 이 창으로 돌아오세요.</p></details>
    <details><summary>대답이 느리거나 앞 이야기를 잊어요</summary><p>대화가 길어지면 생깁니다. <b>대화 줄이기</b>나 <b>새 대화</b>를 쓰세요.</p></details>
    <details><summary>단추를 눌러도 반응이 없어요</summary><p>에이전트가 일하는 중이면 끝날 때까지 기다리거나 <b>멈추기</b> 뒤에 누르세요. 에이전트 판이 바뀌어 명령 이름이 달라졌을 수도 있습니다 — 터미널에 <code>/</code> 를 쳐서 목록을 보세요.</p></details>
    <details><summary>에이전트가 다른 에이전트를 못 찾아요</summary><p><b>에이전트끼리 보기</b>를 켠 뒤에 <b>새로 연</b> 에이전트만 서로를 봅니다 (목록에 ‘혼자’ 표시가 있으면 끄고 연 것). 닫고 새로 열어 주세요. Codex 는 샌드박스 때문에 중계를 부를 때 허락을 물을 수 있습니다.</p></details>
    <details><summary>한글이 깨지거나 칸이 어긋나요</summary><p>창 크기를 한 번 바꾸거나 <b>더 보기 → 화면 지우기</b>를 누르면 다시 그립니다.</p></details>
    <details><summary>예전처럼 검은 명령 창이 편해요</summary><p><b>더 보기 → 바깥 터미널로도 열기</b>를 누르거나, 독의 에이전트 터미널 패널에서 ‘데스크 안 터미널로 열기’를 끄세요.</p></details>`;
}

function renderHelp() {
  $('help').innerHTML = `<div class="tabs" role="group" aria-label="도움말 주제">${HELP_TABS.map(([key, title]) =>
    `<button data-help-tab="${key}" aria-pressed="${key === helpTab}">${title}</button>`).join('')}</div>${helpBody(helpTab)}`;
}
function toggleHelp(force) {
  const open = force ?? $('help').hidden;
  $('help').hidden = !open;
  $('help-toggle').setAttribute('aria-expanded', String(open));
  store.set('helpOpen', open);
  if (open) renderHelp();
  setTimeout(() => {for (const s of sessions.values()) refit(s);}, 30);
  if (typeof placeHandles === 'function') requestAnimationFrame(placeHandles);
}
$('help-toggle').addEventListener('click', () => toggleHelp());
$('help').addEventListener('click', event => {
  const tab = event.target.closest('[data-help-tab]');
  if (tab) {helpTab = tab.dataset.helpTab; store.set('helpTab', helpTab); renderHelp(); return;}
  const insert = event.target.closest('[data-insert]');
  if (insert) {input.value = ''; insertText(insert.dataset.insert);}
});

// ── 처음 안내 ───────────────────────────────────────────
function showWelcome() {$('welcome').hidden = false; $('welcome-ok').focus();}
$('welcome-ok').addEventListener('click', () => {
  $('welcome').hidden = true;
  store.set('welcomed', $('welcome-hide').checked);
  input.focus();
});

// ── 자주 쓰는 말 고치기 ─────────────────────────────────
function editorRow(item = {label: '', text: ''}) {
  const row = document.createElement('div');
  row.className = 'editor-row';
  row.innerHTML = `<input maxlength="40" placeholder="이름" value="${esc(item.label)}"><textarea rows="2" placeholder="입력칸에 넣을 말">${esc(item.text)}</textarea>`
    + '<button title="빼기" aria-label="빼기">✕</button>';
  row.querySelector('button').onclick = () => row.remove();
  return row;
}
function openEditor(items = snippets) {
  $('editor-rows').replaceChildren(...items.map(editorRow));
  $('editor').hidden = false;
}
$('editor-add').addEventListener('click', () => {const row = editorRow(); $('editor-rows').append(row); row.querySelector('input').focus();});
$('editor-reset').addEventListener('click', () => openEditor(DEFAULT_SNIPPETS));
$('editor-cancel').addEventListener('click', () => {$('editor').hidden = true;});
$('editor-save').addEventListener('click', () => attempt(async () => {
  const items = [...$('editor-rows').children].map(row => ({label: row.querySelector('input').value.trim(), text: row.querySelector('textarea').value}))
    .filter(item => item.text.trim());
  toast(await api('term_snippets_save', {items}));
  snippets = items.map(item => ({label: item.label || item.text.trim().slice(0, 40), text: item.text}));
  $('editor').hidden = true;
}));
document.addEventListener('keydown', event => {
  if (event.key === 'F1') {event.preventDefault(); toggleHelp(); return;}     // 어디에 있든 (붙잡는 단계라 한 번만)
  if (event.key !== 'Escape') return;
  if (!$('menu').hidden) {closeMenu(); event.stopPropagation();}
  else if (!$('ask-computer').hidden) answerAsk(false);                    // Esc 는 거절 — 묻는 창은 안전한 쪽으로 닫는다
  else if (!$('ask-peer').hidden) answerPeer('deny');
  else if (!$('peer-settings').hidden) closePeerSettings();
  else if (!$('computer-settings').hidden) closeComputerSettings();
  else if (!$('leave').hidden) $('leave-cancel').click();                   // Esc 는 닫지 않기
  else if (!$('editor').hidden) $('editor').hidden = true;
  else if (!$('new-agent').hidden) $('new-agent').hidden = true;
  else if (!$('welcome').hidden) $('welcome-ok').click();
}, true);

// ── 창을 닫을 때 (2026-10-25 요청) ──────────────────────
// 켜진 에이전트가 있으면 데스크가 창을 닫지 않고 묻는다(askLeave) — 모두 끄기 · 켜 두고 창만 닫기 · 닫지 않기.
// 켜 두면 에이전트는 하던 일을 계속하고, 독의 에이전트 터미널을 누르면 그대로 다시 보인다.
function askLeave() {
  const open = order.map(id => sessions.get(id)).filter(s => s && !s.closed);
  const resident = open.find(s => s.info.resident);
  $('leave-resident').hidden = !resident;
  if (resident) $('leave-resident').innerHTML = `<b>${esc(titleOf(resident))}</b> 는 <b>상주 에이전트</b>라 «모두 끄고 닫기»를 골라도 켜 둡니다.`;
  $('leave-count').textContent = String(open.length || sessions.size);
  $('leave-list').innerHTML = open.map(s => {
    const key = s.state || (s.running ? 'working' : '');
    return `<li><span class="dot ${esc(key)}"></span><b>${esc(titleOf(s))}</b><small>${esc(STATES[key] || '준비 중')} · ${esc(s.info.name || '')}</small></li>`;
  }).join('');
  $('leave').hidden = false;
  $('leave-keep').focus();                          // Enter 를 그냥 눌러도 하던 일이 끊기지 않는 쪽
  return true;
}
function answerLeave(keep) {
  $('leave').hidden = true;
  attempt(async () => api('term_window_close', {keep}));
}
$('leave-stop').addEventListener('click', () => answerLeave(false));
$('leave-keep').addEventListener('click', () => answerLeave(true));
$('leave-cancel').addEventListener('click', () => {$('leave').hidden = true; now()?.term.focus();});

// ── 화면 조작 허락 (2026-10-25) ─────────────────────────
// 에이전트가 처음 다루는 앱마다 데스크가 묻는다(askComputer) — 답은 term_computer_answer. 여럿이면 차례로.
// 2분 안에 답이 없으면 데스크가 거절로 끝내고 askDone 으로 알린다. 허락 목록은 머리의 '화면 조작' 단추.
const asks = [];
let askTimer = 0;
function showAsk() {
  const ask = asks[0];
  $('ask-computer').hidden = !ask;
  clearInterval(askTimer);
  if (!ask) return;
  $('ask-agent').textContent = ask.agent;
  $('ask-app').textContent = ask.app;
  $('ask-app2').textContent = ask.app;
  document.querySelector('input[name="ask-scope"][value=""]').checked = true;   // 넓은 허락은 늘 사람이 골라서
  $('ask-window').textContent = ask.title || '(제목 없음)';
  if (sessions.has(ask.session)) focus(ask.session);
  const started = Date.now();
  const tick = () => {$('ask-left').textContent = `${Math.max(0, 120 - Math.round((Date.now() - started) / 1000))}초 안에 답하지 않으면 거절됩니다.`;};
  tick();
  askTimer = setInterval(tick, 1000);
  $('ask-deny').focus();                            // 실수로 Enter 를 눌러도 거절 쪽
}
function answerAsk(allow) {
  const always = allow && document.querySelector('input[name="ask-scope"]:checked')?.value || null;
  const ask = asks.shift();
  showAsk();
  if (ask) attempt(async () => {
    toast(await api('term_computer_answer', {request: ask.id, allow, always}), !allow);
    paintGrants();
  });
}
$('ask-allow').addEventListener('click', () => answerAsk(true));
$('ask-deny').addEventListener('click', () => answerAsk(false));

// 머리의 '화면 조작' 단추는 늘 보인다 — 지금 방식(앱마다 묻기 · 고른 앱 항상 · 모든 앱 항상 · 멈춤)과 허락 수.
// 누르면 설정 창: 항상 허락(모든 앱 / 앱 목록 — 열린 앱에서 골라 더하기), 지금 허락 거두기, 모두 멈추기 (2026-10-26 요청).
function paintMode(data) {
  const mode = $('computer-mode');
  const label = data.halted && (data.all || data.apps.length) ? '멈춤' : data.all ? '모든 앱 항상 허락'
    : data.apps.length ? `${data.apps.length}개 앱 항상 허락` : '앱마다 묻기';
  mode.textContent = label;
  mode.className = 'cu-mode' + (label === '멈춤' ? ' halted' : data.all || data.apps.length ? ' on' : '');
  $('computer-count').hidden = !data.grants.length;
  $('computer-count').textContent = String(data.grants.length);
  computerState = data;
  paintStatus();
}
async function paintGrants() {
  let data = {grants: [], all: false, apps: [], halted: false};
  try {data = await api('term_computer_list');} catch {}
  paintMode(data);
  if (!$('computer-settings').hidden) paintComputerSettings();
  return data.grants;
}
async function paintComputerSettings() {
  const data = await api('term_computer_options');
  paintMode(data);
  $('cu-team-off').hidden = data.team !== false;
  $('cu-halted').hidden = !(data.halted && (data.all || data.apps.length));
  $('cu-all').checked = data.all;
  $('cu-apps-box').classList.toggle('off', data.all);
  $('cu-apps').innerHTML = data.apps.length
    ? data.apps.map(app => `<li><span>${esc(app)}</span><button data-remove="${esc(app)}">빼기</button></li>`).join('')
    : '<li class="empty">아직 없습니다 — 아래에서 고르거나, 묻는 창에서 ‘항상’을 고르세요.</li>';
  const have = new Set(data.apps.map(app => app.toLowerCase()));
  const choices = data.open.filter(row => !have.has(row.app.toLowerCase()));
  $('cu-open').innerHTML = choices.length
    ? choices.map(row => `<option value="${esc(row.app)}">${esc(row.app)} — ${esc(row.title || '(제목 없음)')}</option>`).join('')
    : '<option value="">더할 수 있는 열린 앱이 없습니다</option>';
  $('cu-add').disabled = !choices.length;
  $('cu-grants').innerHTML = data.grants.length
    ? data.grants.map(item => `<li><span>${esc(item.agent)} → ${esc(item.app)}</span><small>${item.always ? '항상 허락 · ' : ''}${esc(item.since)}</small>`
      + `<button data-session="${esc(item.session)}" data-app="${esc(item.app)}">거두기</button></li>`).join('')
    : '<li class="empty">없습니다</li>';
  $('cu-stop').disabled = !data.grants.length && (data.halted || !(data.all || data.apps.length));
  $('cu-clear').disabled = !(data.all || data.apps.length);
}
function closeComputerSettings() {
  $('computer-settings').hidden = true;
  $('computer-btn').setAttribute('aria-expanded', 'false');
  now()?.term.focus();
}
const cuDo = (action, payload) => attempt(async () => {
  toast(await api(action, payload));
  await paintComputerSettings();
});
$('computer-btn').addEventListener('click', () => attempt(async () => {
  $('computer-settings').hidden = false;
  $('computer-btn').setAttribute('aria-expanded', 'true');
  await paintComputerSettings();
  $('cu-close').focus();
}));
$('cu-close').addEventListener('click', closeComputerSettings);
$('computer-settings').addEventListener('mousedown', event => {if (event.target === event.currentTarget) closeComputerSettings();});
$('cu-all').addEventListener('change', event => {
  const on = event.target.checked;
  if (on && !confirm('모든 앱을 묻지 않고 허락할까요?\n\n에이전트가 어떤 앱이든 바로 누르고 입력할 수 있게 됩니다. (막아 둔 앱·데스크 창은 빼고)')) {
    event.target.checked = false;
    return;
  }
  cuDo('term_computer_always', {all: on});
});
$('cu-add').addEventListener('click', () => {if ($('cu-open').value) cuDo('term_computer_always', {add: $('cu-open').value});});
$('cu-apps').addEventListener('click', event => {
  const app = event.target.closest('button')?.dataset.remove;
  if (app) cuDo('term_computer_always', {remove: app});
});
$('cu-grants').addEventListener('click', event => {
  const item = event.target.closest('button')?.dataset;
  if (item?.session) cuDo('term_computer_stop', {session: item.session, app: item.app});
});
$('cu-stop').addEventListener('click', () => cuDo('term_computer_stop', {}));
$('cu-clear').addEventListener('click', () => cuDo('term_computer_always', {clear: true}));
$('cu-resume').addEventListener('click', () => cuDo('term_computer_resume', {}));

// ── 다른 PC 와 메시지 (2026-10-27) ─────────────────────
// 머리의 '다른 PC' 단추 = 켜고 끄기 · 연결 상태 · '항상' 허락한 사람. 다른 PC 에서 새 요청이 오면 데스크가 묻는다(askPeer) —
// 답은 term_peer_answer (once · always · deny). 2분 안에 답이 없으면 데스크가 거절로 끝내고 askDone 으로 알린다.
const peerAsks = [];
let peerTimer = 0, peerState = {available: false};
function paintPeerMode(data) {
  peerState = data;
  $('peer-btn').hidden = !data.available;
  $('phone-switch').hidden = !data.available;
  if (!data.available) return;
  $('peer-phone').checked = data.phone === true;
  paintStatus();
  const mode = $('peer-mode');
  mode.textContent = !data.on ? '꺼짐' : data.connected ? '연결됨' : '연결 중';
  mode.className = 'cu-mode' + (data.on && data.connected ? ' on' : data.on ? ' halted' : '');
}
async function paintPeer() {
  try {paintPeerMode(await api('term_peer_state'));} catch {}
  if (!$('peer-settings').hidden) paintPeerSettings();
}
function paintPeerSettings() {
  const data = peerState;
  $('peer-on').checked = !!data.on;
  $('peer-team-off').hidden = data.team !== false;
  $('peer-status').textContent = !data.on ? '꺼져 있습니다. 켜면 이 PC 와 열린 에이전트 이름이 다른 선생님의 목록에 보입니다.'
    : data.connected ? `연결됨 — ${data.me || ''} · ${data.label}. 이 창이 열려 있는 동안 다른 PC 의 목록에 보입니다.`
    : `연결 중… ${data.error ? '(' + data.error + ')' : '에이전트를 하나 이상 열어 두어야 목록에 보입니다.'}`;
  $('peer-trusted').innerHTML = (data.trusted || []).length
    ? data.trusted.map(item => `<li><span>${esc(item.name)} 선생님</span><button data-remove="${esc(item.id)}">빼기</button></li>`).join('')
    : '<li class="empty">없습니다 — 메시지가 왔을 때 ‘이 선생님은 항상’을 고르면 여기에 들어옵니다.</li>';
}
function closePeerSettings() {
  $('peer-settings').hidden = true;
  $('peer-btn').setAttribute('aria-expanded', 'false');
  now()?.term.focus();
}
$('peer-btn').addEventListener('click', () => attempt(async () => {
  $('peer-settings').hidden = false;
  $('peer-btn').setAttribute('aria-expanded', 'true');
  await paintPeer();
  paintPeerSettings();
  $('peer-close').focus();
}));
$('peer-close').addEventListener('click', closePeerSettings);
$('peer-settings').addEventListener('mousedown', event => {if (event.target === event.currentTarget) closePeerSettings();});
$('peer-on').addEventListener('change', event => attempt(async () => {
  toast(await api('term_peer_set', {on: event.target.checked}));
  await paintPeer();
  setTimeout(paintPeer, 5000);                       // 연결은 몇 초 뒤에 잡힌다
}));
$('peer-phone').addEventListener('change', event => attempt(async () => {
  toast(await api('term_peer_set', {phone: event.target.checked}));
  await paintPeer();
}));
$('peer-trusted').addEventListener('click', event => {
  const id = event.target.closest('button')?.dataset.remove;
  if (id) attempt(async () => {toast(await api('term_peer_set', {remove: id})); await paintPeer();});
});
setInterval(() => {if (peerState.available && (peerState.on || peerState.phone)) paintPeer();}, 15000);

// ── 오른쪽 패널 «현황» (2026-10-30 요청) ─────────────────────
// 고른 에이전트의 지금 대화 — 컨텍스트 크기, 사용량(5시간·7일 한도·이 대화의 비용), 결과물(Claude 가 만들거나 고친 파일).
// 패널이 열려 있고 «현황»일 때만 USAGE_EVERY 마다 묻는다. desktop.py `_term_usage`·`_term_output_open`, core/agent_usage.py.
const USAGE_EVERY = 5000;
let panelTab = store.get('panelTab', 'usage'), usageTimer = 0, usageHtml = '';
function setPanelTab(tab) {
  panelTab = ['skills', 'folders', 'cron', 'memory'].includes(tab) && !(tab === 'cron' && $('cron-tab').hidden) ? tab : 'usage';
  store.set('panelTab', panelTab);
  document.querySelectorAll('[data-panel-tab]').forEach(button => button.setAttribute('aria-selected', String(button.dataset.panelTab === panelTab)));
  $('panel-skills').hidden = panelTab !== 'skills';
  $('panel-usage').hidden = panelTab !== 'usage';
  $('panel-folders').hidden = panelTab !== 'folders';
  $('panel-cron').hidden = panelTab !== 'cron';
  $('panel-memory').hidden = panelTab !== 'memory';
  if (panelTab === 'folders' && skillsReady) paintKnow();
  if (panelTab === 'cron' && skillsReady) loadCron();
  if (panelTab === 'memory' && skillsReady) loadMemory();
  loadUsage();
}
document.querySelector('.panel-tabs').addEventListener('click', event => {
  const tab = event.target.closest('[data-panel-tab]');
  if (tab) setPanelTab(tab.dataset.panelTab);
});
const tokens = n => n >= 1000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k` : String(n || 0);
const level = percent => percent >= 90 ? 'bad' : percent >= 70 ? 'warn' : '';
function resetText(value) {
  if (!value) return '';
  const date = new Date(typeof value === 'number' ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) return '';
  const time = date.toTimeString().slice(0, 5);
  return date.toDateString() === new Date().toDateString() ? `${time} 초기화` : `${date.getMonth() + 1}.${date.getDate()} ${time} 초기화`;
}
function within(path, folder) {
  const clean = text => String(text || '').replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase();
  const p = clean(path), f = clean(folder);
  return f && p.startsWith(f + '\\') ? String(path).slice(f.length + 1).replace(/\//g, '\\') : '';
}
function paintUsage(data) {
  let html;
  if (!data) html = '<p class="sk-empty">에이전트를 고르면 그 에이전트의 현황이 보입니다.</p>';
  else if (!data.supported) html = `<p class="us-who"><b>${esc(data.title)}</b></p><p class="sk-empty">${esc(data.tool)} 에이전트는 아직 현황을 읽지 못합니다 — Claude Code 에이전트에서 보입니다.</p>`;
  else if (!data.ready) html = `<p class="us-who"><b>${esc(data.title)}</b></p><p class="sk-empty">첫 메시지를 보내면 컨텍스트와 결과물이 여기에 보입니다.</p>`;
  else {
    const c = data.context;
    const limits = data.limits.map(limit => `<div class="us-row"><span>${esc(limit.label)}</span><b>${limit.percent}%</b></div>`
      + `<div class="meter ${level(limit.percent)}"><span style="width:${limit.percent}%"></span></div>`
      + (resetText(limit.resets) ? `<p class="us-note">${esc(resetText(limit.resets))}</p>` : '')).join('');
    const facts = [];
    if (typeof data.cost === 'number') facts.push(`비용 약 $${data.cost.toFixed(2)}`);
    if (data.output_tokens) facts.push(`답한 토큰 ${tokens(data.output_tokens)}`);
    if (typeof data.lines.added === 'number') facts.push(`고친 줄 +${data.lines.added} −${data.lines.removed || 0}`);
    const files = data.outputs.map(item => {
      const rel = within(item.path, data.folder);
      const where = rel ? rel.slice(0, Math.max(0, rel.length - item.name.length - 1)) : item.folder;
      return `<li class="${item.exists ? '' : 'gone'}"><button class="us-file" data-out-open="${esc(item.path)}" title="${esc(item.path)}${item.exists ? '' : ' — 지금은 없습니다'}">`
        + `<span class="badge ${item.created ? 'new' : ''}">${item.created ? '만듦' : '고침'}</span><span class="nm">${esc(item.name)}</span>`
        + `<small>${esc(where || '에이전트 폴더')}${item.count > 1 ? ` · ${item.count}번` : ''}</small></button>`
        + `<button class="us-reveal" data-out-reveal="${esc(item.path)}" title="폴더에서 보기" aria-label="폴더에서 보기"${item.exists ? '' : ' disabled'}>📂</button></li>`;
    }).join('');
    html = `<p class="us-who"><b>${esc(data.title)}</b><small>${esc(data.model || '')}</small></p>`
      + `<section class="us-sec"><h3>컨텍스트</h3><div class="us-row"><span>${tokens(c.used)} / ${tokens(c.size)} 토큰${c.guessed ? ' (크기 어림)' : ''}</span><b>${c.percent}%</b></div>`
      + `<div class="meter ${level(c.percent)}"><span style="width:${c.percent}%"></span></div>`
      + (c.percent >= 80 ? '<p class="us-note warn">곧 가득 찹니다 — 자동으로 줄이기 전에 <code>/compact</code> 나 새 대화(<code>/clear</code>)를 생각해 보세요.</p>' : '')
      + `</section><section class="us-sec"><h3>사용량</h3>${limits || '<p class="us-note">사용 한도(5시간·7일)는 Claude 구독 계정에서, 응답을 받은 뒤 보입니다.</p>'}`
      + (facts.length ? `<p class="us-note">이 대화 — ${esc(facts.join(' · '))}</p>` : '') + '</section>'
      + `<section class="us-sec"><h3>결과물 <small>${data.outputs.length}</small></h3>`
      + (files ? `<ul class="us-files">${files}</ul>` : '<p class="us-note">아직 없습니다 — Claude 가 파일을 만들거나 고치면 여기에 모입니다.</p>')
      + '<p class="us-note">지금 대화에서 Claude 가 쓰기·고치기 도구로 다룬 파일입니다. 명령으로 만든 파일은 빠질 수 있어요. 누르면 엽니다.</p></section>'
      + `<p class="us-note faint">${esc(data.checked)} 확인</p>`;
  }
  if (html === usageHtml) return;               // 그대로면 다시 그리지 않는다 — 스크롤이 튀지 않게
  usageHtml = html;
  $('panel-usage').innerHTML = html;
}
async function loadUsage() {
  clearTimeout(usageTimer);
  if (!skillsReady || $('skills').hidden || panelTab !== 'usage') return;
  const s = now();
  if (!s) paintUsage(null);
  else {
    try {
      const data = await api('term_usage', {id: s.id});
      if (now() === s) paintUsage(data);
    } catch (error) {
      usageHtml = '';
      $('panel-usage').innerHTML = `<p class="sk-empty">${esc(error.message)}</p>`;
    }
  }
  clearTimeout(usageTimer);
  usageTimer = setTimeout(loadUsage, USAGE_EVERY);
}
$('panel-usage').addEventListener('click', event => {
  const open = event.target.closest('[data-out-open]'), reveal = event.target.closest('[data-out-reveal]');
  const s = now();
  if (!s || !(open || reveal)) return;
  attempt(() => api('term_output_open', {id: s.id, path: (open || reveal).dataset[open ? 'outOpen' : 'outReveal'], reveal: !!reveal}));
});

// ── 오른쪽 스킬 패널 (2026-10-30) ─────────────────────────
// 즐겨찾기 · 기본 스킬(어느 폴더에서나 — 바탕화면 정리 …) · 자동화 업무 스킬(깔려 있고 켜 둔 것). 스킬 = 폴더처럼 펼친다.
// 할 수 있는 일을 누르면 입력칸에 넣는다(보내지는 않는다). desktop.py `_term_skills`·`_term_skill_favorite`.
let skillsData = null, skillsReady = false;    // skillsReady — start() 뒤(데스크 연결이 준비됨)
const skillsOpen = new Set(store.get('skillsOpen', ['__fav']));
const favKey = (skill, label) => `${skill}\u0001${label}`;
const groupKey = (skill, label) => `${skill}\u0002${label}`;   // 펼친 기능 묶음 (skillsOpen 에 함께 기억)
function skillRows(skill, favs) {
  const open = skillsOpen.has(skill.name);
  const note = skill.scope === 'automation'
    ? (skill.usable ? '자동화 업무 폴더에서 연 에이전트가 씁니다' : '자동화 업무에 아직 깔리지 않았어요 — 독의 «자동화 업무»에서 열면 깔립니다')
    : '어느 폴더에서 연 에이전트든 씁니다';
  const row = action => `<li class="sk-action"><button class="do" data-prompt="${esc(action.prompt)}" title="${esc(action.prompt)}">${esc(action.label)}</button>`
    + `<button class="fav${favs.has(favKey(skill.name, action.label)) ? ' on' : ''}" data-fav-skill="${esc(skill.name)}" data-fav-label="${esc(action.label)}"`
    + ` data-fav-prompt="${esc(action.prompt)}" title="즐겨찾기" aria-label="즐겨찾기">${favs.has(favKey(skill.name, action.label)) ? '★' : '☆'}</button></li>`;
  // 기능별 묶음 (2026-11-05) — SPACEKIJUN 처럼 할 수 있는 일이 많은 스킬은 기능마다 한 번 더 펼친다. 펼치면 그 기능의 쓰임새부터
  const groups = (skill.groups || []).filter(group => group.actions.length);
  const body = groups.length
    ? '<ul class="sk-actions sk-groups">' + groups.map(group => {
      const key = groupKey(skill.name, group.label), on = skillsOpen.has(key);
      return `<li><button class="sk-sub" data-skill="${esc(key)}" aria-expanded="${on}" title="${esc(group.summary)}">`
        + `<span class="caret">▸</span>${esc(group.label)}<small>${group.actions.length}</small></button>`
        + (on ? (group.summary ? `<p class="sk-desc">${esc(group.summary)}</p>` : '')
          + '<ul class="sk-actions">' + group.actions.map(row).join('') + '</ul>' : '') + '</li>';
    }).join('') + '</ul>'
    : '<ul class="sk-actions">' + (skill.actions.length ? skill.actions.map(row).join('')
      : '<li class="sk-empty">정해 둔 일이 없습니다 — 스킬 이름으로 직접 시켜 보세요.</li>') + '</ul>';
  return `<button class="sk-skill${skill.usable ? '' : ' off'}" data-skill="${esc(skill.name)}" aria-expanded="${open}" title="${esc(skill.summary)}">`
    + `<span class="caret">▸</span><span class="folder">${open ? '📂' : '📁'}</span>${esc(skill.title)}<small>${skill.actions.length}</small></button>`
    + (open ? `<p class="sk-note">${esc(note)}</p>` + (groups.length && skill.summary ? `<p class="sk-desc top">${esc(skill.summary)}</p>` : '') + body : '');
}
function paintSkills() {
  const data = skillsData;
  if (!data) return;
  const favs = new Set(data.favorites.map(item => favKey(item.skill, item.label)));
  const favOpen = skillsOpen.has('__fav');
  const favHtml = `<button class="sk-skill" data-skill="__fav" aria-expanded="${favOpen}"><span class="caret">▸</span><span class="folder">⭐</span>즐겨찾기<small>${data.favorites.length}</small></button>`
    + (favOpen ? '<ul class="sk-actions">' + (data.favorites.length ? data.favorites.map(item =>
      `<li class="sk-action"><button class="do" data-prompt="${esc(item.prompt)}" title="${esc(item.prompt)}">${esc(item.label)}</button>`
      + `<button class="fav on" data-fav-skill="${esc(item.skill)}" data-fav-label="${esc(item.label)}" data-fav-prompt="${esc(item.prompt)}" title="즐겨찾기에서 빼기" aria-label="즐겨찾기에서 빼기">★</button></li>`).join('')
      : '<li class="sk-empty">자주 쓰는 일의 ☆ 를 누르면 여기에 모입니다.</li>') + '</ul>' : '');
  $('skills-tree').innerHTML = favHtml
    + `<div class="sk-group">기본 스킬</div>` + (data.general.map(skill => skillRows(skill, favs)).join('') || '<p class="sk-empty">없습니다.</p>')
    + `<div class="sk-group">자동화 업무 스킬</div>` + (data.automation.map(skill => skillRows(skill, favs)).join('') || '<p class="sk-empty">켜 둔 스킬이 없습니다.</p>');
}
async function loadSkills() {
  try {skillsData = await api('term_skills');} catch (error) {$('skills-tree').innerHTML = `<p class="sk-empty">${esc(error.message)}</p>`; return;}
  paintSkills();
}
$('skills-tree').addEventListener('click', event => {
  const fav = event.target.closest('[data-fav-skill]');
  if (fav) {
    const on = !fav.classList.contains('on');
    attempt(async () => {
      skillsData.favorites = await api('term_skill_favorite', {skill: fav.dataset.favSkill, label: fav.dataset.favLabel, prompt: fav.dataset.favPrompt, on});
      paintSkills();
    });
    return;
  }
  const action = event.target.closest('[data-prompt]');
  if (action) {
    input.value = '';
    insertText(action.dataset.prompt);
    input.focus();
    const hole = input.value.indexOf('○');                 // 고칠 자리(○○)가 있으면 거기를 골라 둔다
    if (hole >= 0) input.setSelectionRange(hole, input.value.lastIndexOf('○') + 1);
    return;
  }
  const skill = event.target.closest('[data-skill]');
  if (skill) {
    const name = skill.dataset.skill;
    if (skillsOpen.has(name)) skillsOpen.delete(name); else skillsOpen.add(name);
    store.set('skillsOpen', [...skillsOpen]);
    paintSkills();
  }
});
$('skills-close').addEventListener('click', () => setView({skills: false}));

// ── 보기 — 화면 배치 (2026-10-30, VS Code 의 보기 메뉴처럼) ────────
// 왼쪽 목록(Ctrl+B) · 오른쪽 스킬 패널(Ctrl+Alt+B) · 도움말(F1) · 도구 줄 · 입력창을 켜고 끄고, 배치를 한 번에 고른다. 이 PC 에 기억한다.
const VIEW_DEFAULT = {side: true, skills: true, tools: true, composer: true};
const VIEW_PRESETS = {
  default: ['기본', {side: true, skills: false, tools: true, composer: true, help: false}],
  skills: ['스킬과 함께', {side: true, skills: true, tools: true, composer: true, help: false}],
  focus: ['터미널에 집중', {side: false, skills: false, tools: false, composer: true, help: false}],
  all: ['모두 보기', {side: true, skills: true, tools: true, composer: true, help: true}],
};
let view = {...VIEW_DEFAULT, ...store.get('view', {}), side: true, skills: true};
function setView(change) {
  if ('help' in change) toggleHelp(change.help);
  view = {...view, ...change};
  delete view.help;
  store.set('view', view);
  document.body.classList.toggle('hide-side', !view.side);
  document.body.classList.toggle('hide-tools', !view.tools);
  document.body.classList.toggle('hide-composer', !view.composer);
  $('skills').hidden = !view.skills;
  if (view.skills && !skillsData && skillsReady) loadSkills();  // 데스크 연결이 준비되기 전에는 start() 가 부른다
  loadUsage();
  if (skillsReady && view.skills && panelTab === 'cron') loadCron();
  setTimeout(() => {for (const s of sessions.values()) refit(s);}, 30);
  requestAnimationFrame(placeHandles);
}
function openView(button) {
  const row = (key, label, keys, on) => `<button data-toggle="${key}"><span class="check">${on ? '✓' : ''}</span>${esc(label)}${keys ? `<small>${keys}</small>` : ''}</button>`;
  openMenu(button, '<div class="label">보이기</div>'
    + row('side', '왼쪽 — 에이전트 목록·대화', 'Ctrl+B', view.side)
    + row('skills', '오른쪽 — 현황·스킬 패널', 'Ctrl+Alt+B', view.skills)
    + row('help', '오른쪽 — 도움말', 'F1', !$('help').hidden)
    + row('tools', '위 — 도구 줄', '', view.tools)
    + row('composer', '아래 — 입력창', '', view.composer)
    + '<hr><div class="label">배치 한 번에</div>'
    + Object.entries(VIEW_PRESETS).map(([key, [label]]) => `<button data-preset="${key}">${esc(label)}</button>`).join(''), picked => {
    if (picked.preset) setView(VIEW_PRESETS[picked.preset][1]);
    else if (picked.toggle === 'help') toggleHelp();
    else if (picked.toggle) setView({[picked.toggle]: !view[picked.toggle]});
  });
}
$('view-btn').addEventListener('click', event => openView(event.currentTarget));
document.addEventListener('keydown', event => {
  if (!event.ctrlKey || event.shiftKey || event.code !== 'KeyB') return;
  event.preventDefault();
  if (event.altKey) setView({skills: !view.skills}); else setView({side: !view.side});
}, true);
setView({});

// ── 상단 정리 (2026-10-30, 테스트 판) ─────────────────────────
// 위쪽 오른쪽 = 켜져 있거나 살펴볼 것만 작은 표시(누르면 그 설정) + ⚙ 설정(서로 보기·작업 폴더·상주·휴대폰·다른 PC·화면 조작)
// + 보기·도움말 단추. 고른 에이전트에게 하는 일은 아래 도구 줄에.
let computerState = null, mainState = null;
let requestState = {available: false, requests: []};   // 에이전트 작업 요청 (아래 loadRequests)
function paintStatus() {
  const chips = [];
  if (computerState?.grants?.length) chips.push(['computer', 'danger', `화면 조작 중 ${computerState.grants.length}`, '에이전트가 앱을 다루도록 허락해 둔 것 — 눌러서 거두기']);
  const waiting = (requestState.requests || []).filter(r => r.status === 'sent').length;
  if (waiting) chips.push(['requests', 'main', `작업 요청 ${waiting}`, '다른 선생님이 보낸 작업 요청 — 눌러서 에이전트에게 맡기기']);
  if (mainState?.main) chips.push(['main', 'main', `★ ${mainState.main.title}${mainState.tasks?.coolmsg ? ' · 쪽지 분석' : ''}`, '메인 상주 에이전트']);
  if (peerState?.phone) chips.push(['phone', peerState.connected ? 'ok' : '', '내 기기', peerState.connected ? '내 휴대폰·내 다른 PC 와 주고받는 중' : '내 기기 — 연결 중']);
  if (peerState?.on) chips.push(['peer', peerState.connected ? 'ok' : '', '다른 PC', peerState.connected ? '다른 PC 와 연결됨' : '다른 PC — 연결 중']);
  $('status-chips').innerHTML = chips.map(([key, tone, label, tip]) =>
    `<button class="st-chip ${tone}" data-status="${key}" title="${esc(tip)}"><span class="dot"></span>${esc(label)}</button>`).join('');
}
$('status-chips').addEventListener('click', event => {
  const key = event.target.closest('[data-status]')?.dataset.status;
  if (key === 'computer') $('computer-btn').click();
  else if (key === 'main') $('main-btn').click();
  else if (key === 'requests') openRequests();
  else if (key === 'peer') $('peer-btn').click();
  else if (key === 'phone') openSettings(true);
});
function openSettings(force) {
  const open = force ?? $('settings-pop').hidden;
  $('settings-pop').hidden = !open;
  $('settings-btn').setAttribute('aria-expanded', String(open));
  if (open) {paintKnow(); paintMain(); paintPeer();}
}
$('settings-btn').addEventListener('click', () => openSettings());
$('settings-pop').addEventListener('click', event => {
  if (event.target.closest('button.sp-row')) openSettings(false);          // 설정 창을 열면 펼친 것은 닫는다
});
document.addEventListener('mousedown', event => {
  if (!$('settings-pop').hidden && !event.target.closest('.settings-wrap')) openSettings(false);
});
document.addEventListener('keydown', event => {if (event.key === 'Escape' && !$('settings-pop').hidden) openSettings(false);});

// 양쪽 패널의 여닫이 손잡이 — 패널 안쪽 가장자리 가운데, 닫혀 있으면 창 끝에 남는다 (2026-10-30 요청)
function placeHandles() {
  const side = document.querySelector('.side'), skills = $('skills'), help = $('help');
  const leftOpen = view.side, rightOpen = view.skills;
  $('side-handle').style.left = `${leftOpen ? side.offsetWidth : 0}px`;
  $('side-handle').textContent = leftOpen ? '‹' : '›';
  $('side-handle').classList.toggle('closed', !leftOpen);
  const helpWidth = help.hidden ? 0 : help.offsetWidth;
  $('skills-handle').style.right = `${(rightOpen ? skills.offsetWidth : 0) + helpWidth}px`;
  $('skills-handle').textContent = rightOpen ? '›' : '‹';
  $('skills-handle').classList.toggle('closed', !rightOpen);
}
$('side-handle').addEventListener('click', () => setView({side: !view.side}));
$('skills-handle').addEventListener('click', () => setView({skills: !view.skills}));
addEventListener('resize', placeHandles);

// ── 작업 폴더 · 지식 (2026-10-30) ──────────────────────────
// 새로 여는 에이전트가 함께 쓰는 작업 폴더 — 폴더마다 지식 파일(데스크 자료 폴더). desktop.py `_term_knowledge*`, core/knowledge.py
// 오른쪽 패널 «폴더»(2026-10-30 요청 — ⚙ 설정의 창에서 옮김): 줄을 누르면 폴더를 바로 열고, 지금 에이전트의 폴더는 한 번에 더한다.
var knowData = null, knowArmed = '', knowArmTimer = 0;   // var — paintHeader 가 이 줄보다 먼저 불릴 수 있다
const sameFolder = (a, b) => String(a || '').replace(/[\/]+$/, '').toLowerCase() === String(b || '').replace(/[\/]+$/, '').toLowerCase();
const bytes = n => n >= 1024 ? `${(n / 1024).toFixed(n >= 10240 ? 0 : 1)}KB` : `${n || 0}B`;
function dayText(seconds) {
  if (!seconds) return '';
  const date = new Date(seconds * 1000);
  return date.toDateString() === new Date().toDateString() ? `오늘 ${date.toTimeString().slice(0, 5)}` : `${date.getMonth() + 1}.${date.getDate()}`;
}
async function paintKnow() {
  try {knowData = await api('term_knowledge');} catch {return;}
  $('know-count').textContent = String(knowData.folders.length);
  $('know-count').className = 'cu-mode' + (knowData.folders.length ? ' on' : '');
  paintKnowPanel();
}
function paintKnowPanel() {
  const data = knowData;
  if (!data) return;
  const here = now()?.info.folder || '';
  const full = data.folders.length >= data.limit;
  $('know-add').disabled = full;
  $('know-limit').textContent = `${data.folders.length} / ${data.limit}`;
  const listed = data.folders.some(row => sameFolder(row.folder, here));
  $('know-current').innerHTML = here && !listed
    ? `<div class="kf-here"><span><small>지금 에이전트의 폴더</small><b title="${esc(here)}">${esc(here.split(/[\/]/).filter(Boolean).pop() || here)}</b></span>`
      + `<button class="ghost" data-know-add-here="${esc(here)}"${full ? ' disabled' : ''}>＋ 작업 폴더로</button></div>`
    : '';
  $('know-list').innerHTML = data.folders.length ? data.folders.map(row => {
    const mine = sameFolder(row.folder, here);
    const facts = [row.size > 0 ? `지식 ${bytes(row.size)}` : '지식 아직 없음', dayText(row.updated) && `${dayText(row.updated)} 고침`].filter(Boolean).join(' · ');
    const armed = knowArmed === row.folder;
    return `<li class="kf-item${row.exists ? '' : ' gone'}${mine ? ' here' : ''}">`
      + `<button class="kf-open" data-know-reveal="${esc(row.folder)}" title="${esc(row.folder)}${row.exists ? '\n누르면 탐색기로 엽니다' : '\n폴더를 찾을 수 없습니다'}"${row.exists ? '' : ' disabled'}>`
      + `<span class="kf-icon" aria-hidden="true">📁</span><span class="kf-name">${esc(row.name)}${mine ? '<em>지금 에이전트</em>' : ''}${row.exists ? '' : '<em class="bad">폴더 없음</em>'}</span>`
      + `<small class="kf-path">${esc(row.folder)}</small><small class="kf-facts">${esc(facts)}</small></button>`
      + `<div class="kf-tools"><button data-know-open="${esc(row.folder)}" title="지식 파일을 열어 직접 고칩니다">지식</button>`
      + `<button class="${armed ? 'armed' : ''}" data-know-remove="${esc(row.folder)}" title="작업 폴더에서 뺍니다 — 지식 파일은 남겨 둡니다">${armed ? '빼기?' : '빼기'}</button></div></li>`;
  }).join('') : '<li class="sk-empty">아직 없습니다 — 저장소·업무 폴더를 더해 보세요.</li>';
}
$('know-btn').addEventListener('click', () => {setView({skills: true}); setPanelTab('folders');});
$('panel-folders').addEventListener('click', event => {
  const target = event.target.closest('button');
  if (!target || target.disabled) return;
  const {knowReveal, knowOpen, knowRemove, knowAddHere} = target.dataset;
  if (target.id === 'know-add' || knowAddHere) attempt(async () => {
    const message = await api('term_knowledge_add', knowAddHere ? {folder: knowAddHere} : {});
    if (message) toast(message);
    await paintKnow();
  });
  else if (knowReveal) attempt(() => api('term_knowledge_reveal', {folder: knowReveal}));
  else if (knowOpen) attempt(() => api('term_knowledge_open', {folder: knowOpen}));
  else if (knowRemove && knowArmed !== knowRemove) {           // 한 번 더 눌러야 뺀다 — 잘못 누르기 방지
    knowArmed = knowRemove;
    clearTimeout(knowArmTimer);
    knowArmTimer = setTimeout(() => {knowArmed = ''; paintKnowPanel();}, 3000);
    paintKnowPanel();
  } else if (knowRemove) attempt(async () => {
    knowArmed = '';
    toast(await api('term_knowledge_remove', {folder: knowRemove}));
    await paintKnow();
  });
});

// ── 에이전트 작업 요청 (2026-11-11) ─────────────────────────
// 다른 선생님의 에이전트가 SPACEKIJUN MCP send_agent_request 로 «이 일을 이렇게 해 달라»를 보낸다. 맡길 말은 서버가 만든다
// (모바일·웹에서 넘길 때와 같은 글) — 여기서는 고른 에이전트의 입력칸에 넣기만 한다(보내지 않는다). desktop.py `_term_request_*`.
const REQ_REF = {document_generation: '문서 생성 방식', action: '업무 작업', work: '업무', task: '할 일', skill: '스킬'};
async function loadRequests() {
  try {requestState = await api('term_requests');} catch {return;}
  const waiting = requestState.requests.filter(r => r.status === 'sent').length;
  $('req-btn').hidden = !requestState.available;
  $('req-mode').textContent = String(requestState.requests.length);
  $('req-mode').className = 'cu-mode' + (waiting ? ' on' : '');
  paintStatus();
  if (!$('req-sheet').hidden) paintRequests();
}
function paintRequests() {
  const rows = requestState.requests;
  $('req-list').innerHTML = rows.length ? rows.map(r => {
    const steps = (r.steps || []).map(step => `<li>${esc(step)}</li>`).join('');
    const refs = (r.refs || []).map(ref => `<li>${esc(REQ_REF[ref.kind] || ref.kind)} «${esc(ref.title || '')}»</li>`).join('');
    const handed = r.status === 'handed' && r.handed_to
      ? ` · ${esc([r.handed_to.label, r.handed_to.agent].filter(Boolean).join(' '))}에게 넘김` : '';
    return `<li data-req="${esc(r.id)}"><div class="rq-head"><b>${esc(r.title)}</b><small>${esc(r.from)} · ${esc(r.at || '')}`
      + `${r.due_date ? ` · 기한 ${esc(r.due_date)}` : ''}</small><span class="rq-state ${esc(r.status)}">${esc(r.status_text || r.status)}</span></div>`
      + `<div class="rq-body">${esc(r.body || '')}</div>`
      + (steps ? `<div class="rq-label">수행 안내</div><ol>${steps}</ol>` : '')
      + (refs ? `<div class="rq-label">연결 항목</div><ul class="rq-refs">${refs}</ul>` : '')
      + (handed ? `<div class="rq-label">${handed}</div>` : '')
      + `<div class="rq-actions"><button class="hand" data-req-hand="${esc(r.id)}">에이전트에게 맡기기</button>`
      + `<button data-req-show="${esc(r.id)}">맡길 말 보기</button></div></li>`;
  }).join('') : '<li class="empty">열려 있는 작업 요청이 없습니다.</li>';
}
async function openRequests() {
  openSettings(false);
  $('req-sheet').hidden = false;
  $('req-btn').setAttribute('aria-expanded', 'true');
  paintRequests();
  await loadRequests();
  $('req-close').focus();
}
function closeRequests() {$('req-sheet').hidden = true; $('req-btn').setAttribute('aria-expanded', 'false'); now()?.term.focus();}
async function handRequest(id) {
  const s = now();
  if (!s) {toast('먼저 왼쪽 목록에서 맡길 에이전트를 고르세요.', true); return;}
  const data = await api('term_request_prompt', {id});
  if (!$('req-sheet').hidden) closeRequests();
  if (!$('main-settings').hidden) closeMain();
  input.setSelectionRange(input.value.length, input.value.length);
  insertText(input.value.trim() ? '\n\n' + data.text : data.text);
  input.scrollTop = 0;
  toast(`${titleOf(s)} 의 입력칸에 넣었습니다 — 확인하고 Enter 로 보내세요.`);
  try {await api('term_request_handed', {id, agent: titleOf(s)});} catch {/* 넣은 것은 그대로 — 상태만 못 바꿨다 */}
  loadRequests();
}
$('req-btn').addEventListener('click', () => attempt(openRequests));
$('req-close').addEventListener('click', closeRequests);
$('req-refresh').addEventListener('click', () => attempt(loadRequests));
$('req-sheet').addEventListener('mousedown', event => {if (event.target === event.currentTarget) closeRequests();});
$('req-list').addEventListener('click', event => {
  const hand = event.target.closest('[data-req-hand]');
  if (hand) {attempt(() => handRequest(hand.dataset.reqHand)); return;}
  const show = event.target.closest('[data-req-show]');
  if (!show) return;
  const item = show.closest('li');
  const open = item.querySelector('pre.rq-prompt');
  if (open) {open.remove(); show.textContent = '맡길 말 보기'; return;}
  attempt(async () => {
    const data = await api('term_request_prompt', {id: show.dataset.reqShow});
    const pre = document.createElement('pre');
    pre.className = 'rq-prompt';
    pre.textContent = data.text;
    item.append(pre);
    show.textContent = '맡길 말 접기';
  });
});
document.addEventListener('keydown', event => {if (event.key === 'Escape' && !$('req-sheet').hidden) closeRequests();});
loadRequests();
setInterval(loadRequests, 120000);

// ── 메인 상주 에이전트의 할 일 (2026-10-30) ─────────────────
// 메인 = 목록의 ★. 맡길 일 = 쿨메신저 쪽지 분석(Haiku, core/resident_tasks.py). 결과는 스페이스기전 알림으로.
const MAIN_STATE = {working: '일하는 중', idle: '입력 기다림', 'waiting-for-user-choice': '선택 기다림', 'agent-exited': '꺼짐', ended: '꺼짐'};
const VERDICT = {yes: '내 일(담당)', audience: '나도 해야 함(대상자)', unclear: '확인 필요', no: '내 일 아님'};
async function paintMain() {
  let data;
  try {data = await api('term_main_state');} catch {return;}
  mainState = data;
  const residents = [...sessions.values()].filter(s => s.info.resident).length;
  $('main-mode').textContent = data.main ? `메인 ${data.main.title}` : residents ? `상주 ${residents}` : '없음';
  $('main-mode').className = 'cu-mode' + (data.main ? ' on' : '');
  paintStatus();
  if ($('main-settings').hidden) return;
  const rows = order.map(id => sessions.get(id)).filter(Boolean);
  $('resident-list').innerHTML = rows.length ? rows.map(s => `<li><span>${esc(titleOf(s))}<small> · ${esc(s.info.name || '')}</small></span>`
      + `<label class="res-toggle"><input type="checkbox" class="switch" data-res="${esc(s.id)}"${s.info.resident ? ' checked' : ''}> 상주</label>`
      + `<label class="res-main"><input type="radio" name="main-pick" data-main-pick="${esc(s.id)}"${s.info.main ? ' checked' : ''}> 메인</label></li>`).join('')
    : '<li class="empty">열린 에이전트가 없습니다 — 왼쪽 «새 에이전트»로 연 뒤 상주시키세요.</li>';
  $('main-who').innerHTML = data.main
    ? `메인: <b>${esc(data.main.title)}</b> · ${esc(MAIN_STATE[data.main.state] || '준비 중')} · ${esc(data.main.folder)} · 작업 폴더 ${data.knowledge}개의 지식을 씁니다.`
    : '메인이 없습니다 — 위에서 «메인»을 고르면 상주도 함께 켜집니다.';
  document.querySelectorAll('.main-only').forEach(el => {el.hidden = !data.available;});
  $('main-coolmsg').checked = !!data.tasks.coolmsg;
  $('main-coolmsg').disabled = !data.main;
  $('main-watch-off').hidden = !(data.tasks.coolmsg && !data.watching);
  // 길면 … 로 자르고(마우스를 올리면 전체), 처음엔 RECENT_SHOWN 개만 — 시트가 길어지지 않게 (2026-10-30 요청)
  const recent = recentAll ? data.recent : data.recent.slice(0, RECENT_SHOWN);
  $('main-recent').classList.toggle('all', recentAll);
  $('main-recent').innerHTML = data.recent.length ? recent.map(row => {
    const what = row.skipped ? `건너뜀 — ${row.skipped}` : row.error ? `실패 — ${row.error}`
      : row.has_task ? `${row.task} · ${VERDICT[row.related] || ''}${row.notified ? ' · 알림 보냄' : ''}` : '처리할 일 없음';
    const line = `${row.sender || '쪽지'} — ${what}`;
    return `<li><span title="${esc(line)}">${esc(line)}</span><small>${esc((row.time || '').slice(5, 16))}</small>`
      + `${handButton({key: row.key, handoff: !row.skipped && !row.error})}</li>`;
  }).join('') : '<li class="empty">아직 없습니다.</li>';
  $('main-recent-more').hidden = data.recent.length <= RECENT_SHOWN;
  $('main-recent-more').textContent = recentAll ? '접기' : `더 보기 (${data.recent.length - RECENT_SHOWN}건)`;
}
const RECENT_SHOWN = 5;
let recentAll = false;
$('main-recent-more').addEventListener('click', () => {recentAll = !recentAll; paintMain();});
$('main-btn').addEventListener('click', () => attempt(async () => {
  $('main-settings').hidden = false;
  $('main-btn').setAttribute('aria-expanded', 'true');
  await paintMain();
  $('main-close').focus();
}));
function closeMain() {$('main-settings').hidden = true; $('main-btn').setAttribute('aria-expanded', 'false'); now()?.term.focus();}
$('main-close').addEventListener('click', closeMain);
$('main-settings').addEventListener('mousedown', event => {if (event.target === event.currentTarget) closeMain();});
$('resident-list').addEventListener('change', event => {
  const res = event.target.closest('[data-res]');
  if (res) {setResident(res.dataset.res); return;}
  const pick = event.target.closest('[data-main-pick]');
  if (pick) setMain(pick.dataset.mainPick);
});
$('main-coolmsg').addEventListener('change', event => attempt(async () => {
  try {toast(await api('term_main_set', {coolmsg: event.target.checked}));}
  finally {await paintMain();}
}));
setInterval(() => {if (!$('main-settings').hidden) paintMain();}, 10000);

function showPeerAsk() {
  const ask = peerAsks[0];
  $('ask-peer').hidden = !ask;
  clearInterval(peerTimer);
  if (!ask) return;
  $('peer-ask-name').textContent = ask.name;
  $('peer-ask-target').textContent = ask.target;
  $('peer-ask-from').textContent = `${ask.name} 선생님 · ${ask.label} 의 ${ask.agent}`;
  $('peer-ask-body').textContent = ask.body + (ask.long ? '\n…(뒷부분 생략 — 넣으면 전부 들어갑니다)' : '');
  $('peer-ask-skip').hidden = !ask.skip;
  document.querySelector('input[name="peer-scope"][value="once"]').checked = true;   // 넓은 허락은 늘 사람이 골라서
  if (sessions.has(ask.session)) focus(ask.session);
  const started = Date.now();
  const tick = () => {$('peer-ask-left').textContent = `${Math.max(0, 120 - Math.round((Date.now() - started) / 1000))}초 안에 답하지 않으면 거절됩니다.`;};
  tick();
  peerTimer = setInterval(tick, 1000);
  $('peer-ask-deny').focus();                       // 실수로 Enter 를 눌러도 거절 쪽
}
function answerPeer(answer) {
  const ask = peerAsks.shift();
  showPeerAsk();
  if (ask) attempt(async () => {
    toast(await api('term_peer_answer', {request: ask.id, answer}), answer === 'deny');
    paintPeer();
  });
}
$('peer-ask-allow').addEventListener('click', () => answerPeer(document.querySelector('input[name="peer-scope"]:checked')?.value || 'once'));
$('peer-ask-deny').addEventListener('click', () => answerPeer('deny'));

// ── 에이전트 로그인 안내 (2026-11-07 요청) ─────────────────────
// Claude Code·Codex 가 로그인되어 있지 않으면 칸 위를 «로그인이 필요합니다» 로 덮는다 — 터미널의 영어 안내 대신.
// [로그인하기] = 데스크가 보이는 콘솔 창에서 `claude auth login` / `codex login` 을 돌린다(브라우저가 열린다). 화면은 LOGIN_POLL 마다
// 다시 보고(term_auth fresh), 로그인되면 안내를 걷고 안내를 띄웠던 칸을 다시 켠다. desktop.py `_term_auth`·`_term_login`.
const LOGIN_MARKUP = '<div class="pane-login" hidden><div class="pl-card" role="alertdialog" aria-live="polite">'
  + '<span class="pl-badge">🔑 로그인 필요</span><h3 class="pl-title"></h3><p class="pl-lead"></p>'
  + '<ol><li><b>로그인하기</b>를 누르면 로그인 창(검은 창)과 브라우저가 열립니다.</li>'
  + '<li>브라우저에서 계정으로 로그인하고 허용을 누릅니다. <small>브라우저가 열리지 않으면 검은 창에 나온 주소를 열고, 코드를 붙여 넣으라고 하면 검은 창에 붙여 넣으세요.</small></li>'
  + '<li>끝나면 이 화면이 저절로 이어지고 에이전트를 다시 켭니다.</li></ol>'
  + '<div class="pl-actions"><button class="primary" data-do="login">로그인하기</button><button class="ghost" data-do="login-check">다시 확인</button>'
  + '<button class="link" data-do="login-skip" title="이 안내를 닫고 터미널에 나온 영어 안내대로 직접 합니다">터미널에서 직접 하기</button></div>'
  + '<p class="pl-wait" hidden>로그인을 기다리는 중… 브라우저에서 마치면 저절로 이어집니다.</p></div></div>';
const LOGIN_TEXT = {
  claude: ['Claude Code 에 로그인해 주세요', 'Claude Code 는 Claude 구독 계정(claude.ai)으로 한 번 로그인해야 씁니다. 로그인하기 전에는 에이전트가 답하지 않고, 예약 업무도 돌지 않습니다.'],
  codex: ['Codex 에 로그인해 주세요', 'Codex 는 ChatGPT 계정으로 한 번 로그인해야 씁니다. 로그인하기 전에는 에이전트가 답하지 않습니다.']
};
const LOGIN_POLL = 4000, LOGIN_FRESH = 60000;
const loginState = {};      // 도구 → {installed, logged_in(true·false·null=모름), detail, login_open, label, checked}
let loginTimer = 0;
async function authOf(tool, fresh = false) {
  const known = loginState[tool];
  if (!fresh && known && Date.now() - known.checked < LOGIN_FRESH) return known;
  const state = await api('term_auth', {tool, fresh});
  loginState[tool] = {...state, checked: Date.now()};
  return loginState[tool];
}
async function checkLogin(s) {
  try {await authOf(s.info.tool);} catch {return;}
  paintLogin(s.info.tool);
}
function paintLogin(tool) {
  const state = loginState[tool];
  let waiting = false;
  for (const s of sessions.values()) {
    if (s.info.tool !== tool) continue;
    const box = s.pane.querySelector('.pane-login');
    const need = state?.logged_in === false && !s.loginSkipped;
    if (state?.logged_in === false) s.loginShown = true;      // 로그인 전에 뜬 칸 — 로그인되면 다시 켠다
    box.hidden = !need;
    if (!need) continue;
    const [title, lead] = LOGIN_TEXT[tool] || LOGIN_TEXT.claude;
    box.querySelector('.pl-title').textContent = title;
    box.querySelector('.pl-lead').textContent = lead;
    box.querySelector('.pl-wait').hidden = !state.login_open;
    box.querySelector('[data-do="login"]').textContent = state.login_open ? '로그인 창 다시 열기' : '로그인하기';
    waiting = true;
  }
  if (waiting || state?.login_open) {clearTimeout(loginTimer); loginTimer = setTimeout(pollLogin, LOGIN_POLL);}
  if (cronReady) paintCronBanner();
}
async function pollLogin() {
  for (const tool of Object.keys(loginState).filter(name => loginState[name].logged_in === false)) {
    let state;
    try {state = await authOf(tool, true);} catch {continue;}
    if (state.logged_in) loggedIn(tool); else paintLogin(tool);
  }
}
function loggedIn(tool) {
  const stale = [...sessions.values()].filter(s => s.info.tool === tool && s.loginShown);
  paintLogin(tool);
  toast(`${loginState[tool]?.label || tool} 에 로그인했습니다${stale.length ? ' — 에이전트를 다시 켭니다' : ''}.`);
  for (const s of stale) {          // 로그인 전에 뜬 에이전트는 첫 화면(로그인 안내)에 머물러 있다 — 하던 대화로 다시 켠다
    s.loginShown = s.loginSkipped = false;
    attempt(async () => {
      await api('term_restart', {id: s.id});
      s.state = '';
      setTimeout(() => scheduleResize(s, s.term.cols, s.term.rows), 300);
    });
  }
  if (cronReady) loadCron();
}
const loginTool = button => sessions.get(button?.closest('.pane')?.dataset.id)?.info.tool || button?.dataset.tool || 'claude';
ACTIONS.login = button => {
  const tool = loginTool(button);
  attempt(async () => {
    toast(await api('term_login', {tool}));
    loginState[tool] = {...(loginState[tool] || {}), logged_in: false, login_open: true, checked: Date.now()};
    paintLogin(tool);
  });
};
ACTIONS['login-check'] = button => {
  const tool = loginTool(button);
  attempt(async () => {
    const state = await authOf(tool, true);
    if (state.logged_in) loggedIn(tool);
    else {paintLogin(tool); toast(state.logged_in === false ? '아직 로그인되지 않았습니다 — 브라우저에서 로그인을 마쳐 주세요.' : '로그인 상태를 알아내지 못했습니다.', state.logged_in !== false);}
  });
};
ACTIONS['login-skip'] = button => {
  const s = sessions.get(button?.closest('.pane')?.dataset.id);
  if (!s) return;
  s.loginSkipped = true;
  paintLogin(s.info.tool);
  s.term.focus();
};

// ── 오른쪽 패널 «예약» (2026-11-07 요청) ─────────────────────
// 정한 시각에 고른 Claude Code 에이전트에게 일을 시키고 결과를 휴대폰으로 받는다. 목록·켜기·지금 한 번·최근 실행, 줄을 누르면 고치기.
// 데스크가 켜져 있으면 돈다(이 창은 닫아도 됨). desktop.py `_term_cron_*`, core/agent_cron.py. 학생판에는 없다(탭을 숨긴다).
const CRON_POLL = 5000;
const DAY_LETTERS = '일월화수목금토';
let cronData = null, cronTimer = 0, cronEditing = null, cronKind = 'weekdays', cronReady = false, previewTimer = 0;
let cronListHtml = '', cronRunsHtml = '';
const cronDays = new Set([1, 2, 3, 4, 5]), cronOpenRuns = new Set();
const cronStatus = status => cronData?.status_text?.[status] || status || '';
function whenText(value) {
  const date = new Date(String(value || '').replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return '';
  const time = date.toTimeString().slice(0, 5), today = new Date();
  const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  if (date.toDateString() === today.toDateString()) return `오늘 ${time}`;
  if (date.toDateString() === tomorrow.toDateString()) return `내일 ${time}`;
  return `${date.getMonth() + 1}.${date.getDate()}(${DAY_LETTERS[date.getDay()]}) ${time}`;
}
function cronLine(row) {
  if (row.running) return ['live', `▶ ${row.running.step || '도는 중'}`];
  if (row.pending) return ['wait', '⏳ 승인 대기 — 켜면 확정됩니다'];
  const last = row.last ? ` · 지난번 ${cronStatus(row.last.status)}${row.last.late ? '(늦게)' : ''}` : '';
  if (!row.on) return ['', (row.when.kind === 'once' && row.last ? '끝남 (한 번)' : '꺼 둠') + last];
  return [row.last && row.last.status !== 'done' ? 'bad' : '', (row.next ? `다음 ${whenText(row.next)}` : '다음 실행 없음') + last];
}
// ── 오른쪽 패널 «기억» (2026-11-11 요청 — 헤르메스 방식) ─────────────────
// 기억(MEMORY)·사용자 프로필(USER)은 짧은 항목들 — 글자 수 상한이 있고, 새로 여는 에이전트가 처음에 받는다(얼린 사본).
// 배운 스킬은 에이전트가 만든 SKILL.md. 밤 12시에 데스크가 그날 대화를 읽어 고치고(놓쳤으면 켜진 뒤), 바꾸기 전 모양으로 되돌릴 수 있다.
// desktop.py `_term_memory*`, core/agent_memory.py.
const MEM_TITLES = {user: ['사용자 프로필', '나에 대해 — 하는 일·선호·답하는 방식'], memory: ['기억', '환경·규칙·요령 — 모든 대화에 필요한 것']};
let memoryData = null, memoryTimer = 0;
async function loadMemory() {
  clearTimeout(memoryTimer);
  if (!skillsReady) return;
  try {memoryData = await api('term_memory');}
  catch (error) {
    $('mem-review').innerHTML = `<p class="sk-empty">${esc(error.message)}</p>`;
    return;
  }
  if (!memoryData?.stores) {memoryData = null; return;}          // 옛 데스크·점검용 가짜 응답
  paintMemory();
  if (panelTab === 'memory') memoryTimer = setTimeout(loadMemory, memoryData.review?.running ? 4000 : 30000);
}
const memWhen = value => value ? String(value).slice(0, 16).replace('T', ' ') : '';
const MEM_ACTIONS = {add: '더함', patch: '고침', remove: '지움', create: '새 스킬', edit: '다시 씀', delete: '지움', restore: '되돌림'};
function paintMemory() {
  const data = memoryData, review = data.review || {}, last = (review.history || [])[0];
  const status = review.running ? '<b class="mem-run">지금 업데이트하는 중…</b>'
    : last ? `마지막 업데이트 ${esc(memWhen(last.at))} · ${esc({done: '마침', idle: '바꿀 것 없음', failed: '실패'}[last.status] || last.status)}`
      : '아직 업데이트한 적이 없습니다 — 오늘 밤 12시에 처음 합니다.';
  const changes = (last?.changes || []).map(change => `<li class="${change.ok ? '' : 'bad'}"><span class="badge">${esc(change.kind === 'skill' ? '스킬' : MEM_TITLES[change.kind]?.[0] || change.kind)}</span>`
    + `${esc(MEM_ACTIONS[change.action] || change.action)} — ${esc(change.text)}`
    + (change.why ? `<small>${esc(change.why)}</small>` : '') + (change.ok ? '' : `<small>안 됨: ${esc(change.error || '')}</small>`) + '</li>').join('');
  $('mem-review').innerHTML = `<div class="mem-card">
      <div class="mem-status">${status}</div>
      ${last?.summary && !review.running ? `<p class="mem-summary">${esc(last.summary)}</p>` : ''}
      ${changes ? `<ul class="mem-done">${changes}</ul>` : ''}
      <div class="mem-actions">
        <button class="ghost" data-mem-run ${review.running ? 'disabled' : ''}>지금 업데이트</button>
        ${data.undo && !review.running ? `<button class="link" data-mem-undo="${esc(data.undo)}" title="지난 업데이트가 바꾸기 전의 기억·스킬로 되돌립니다">지난 업데이트 되돌리기</button>` : ''}
        <label class="mem-auto"><input type="checkbox" class="switch" data-mem-auto ${data.auto ? 'checked' : ''}> 매일 밤 12시</label>
      </div></div>`;
  $('mem-stores').innerHTML = ['user', 'memory'].map(target => {
    const s = data.stores[target], [title, hint] = MEM_TITLES[target];
    const items = s.entries.map((entry, index) => `<li><span>${esc(entry)}</span><button class="link" data-mem-remove="${target}:${index}" title="이 항목 지우기">✕</button></li>`).join('');
    return `<section class="mem-store"><div class="mem-head"><b>${title}</b><small>${hint}</small><small class="mem-count">${s.used.toLocaleString()}/${s.limit.toLocaleString()}자</small></div>
      <div class="meter ${level(s.percent)}"><span style="width:${Math.min(100, s.percent)}%"></span></div>
      <ul class="mem-list">${items || '<li class="sk-empty">아직 없습니다 — 에이전트가 알게 되면 적습니다.</li>'}</ul></section>`;
  }).join('');
  $('mem-skills').innerHTML = data.skills.length ? data.skills.map(skill => `<li><details data-mem-skill="${esc(skill.name)}"><summary><b>${esc(skill.name)}</b><small>${esc(skill.description)}</small></summary>`
      + `<pre class="mem-skill-text">불러오는 중…</pre><button class="link danger-text" data-mem-skill-delete="${esc(skill.name)}">이 스킬 지우기</button></details></li>`).join('')
    : '<li class="sk-empty">아직 없습니다 — 되풀이할 만한 절차를 해 보면 에이전트가 스킬로 남깁니다.</li>';
  $('mem-changes').innerHTML = (data.changes || []).map(change => `<li><small>${esc(change.at)}</small> ${esc(change.source)} · `
    + `${esc(change.kind === 'skill' ? `스킬 ${change.target}` : change.kind === 'restore' ? '백업' : MEM_TITLES[change.target]?.[0] || change.target)} `
    + `${esc(MEM_ACTIONS[change.action] || change.action)}${change.content ? ` — ${esc(change.content)}` : ''}</li>`).join('') || '<li class="sk-empty">없음</li>';
}
$('panel-memory').addEventListener('click', event => {
  const target = event.target.closest('[data-mem-run],[data-mem-undo],[data-mem-remove],[data-mem-skill-delete]');
  if (!target) return;
  attempt(async () => {
    if (target.dataset.memRun !== undefined) {
      toast(await api('term_memory_review'));
    } else if (target.dataset.memUndo) {
      if (!confirm('지난 지식 업데이트가 바꾸기 전의 기억·프로필·배운 스킬로 되돌릴까요?')) return;
      toast(await api('term_memory_undo', {name: target.dataset.memUndo}));
    } else if (target.dataset.memRemove) {
      const [store, index] = target.dataset.memRemove.split(':');
      const entry = memoryData?.stores?.[store]?.entries?.[Number(index)] || '';
      if (!confirm(`이 항목을 지울까요?\n\n${entry}`)) return;
      toast(await api('term_memory_remove', {target: store, index: Number(index)}));
    } else if (target.dataset.memSkillDelete) {
      if (!confirm(`배운 스킬 «${target.dataset.memSkillDelete}»을 지울까요? 에이전트가 더는 쓰지 않습니다.`)) return;
      toast(await api('term_memory_skill_delete', {name: target.dataset.memSkillDelete}));
    }
    loadMemory();
  });
});
$('panel-memory').addEventListener('change', event => {
  if (event.target.dataset.memAuto === undefined) return;
  attempt(async () => {toast(await api('term_memory_auto', {on: event.target.checked})); loadMemory();});
});
$('panel-memory').addEventListener('toggle', event => {
  const box = event.target.closest?.('[data-mem-skill]');
  if (!box || !box.open) return;
  const pre = box.querySelector('pre');
  api('term_memory_skill', {name: box.dataset.memSkill}).then(data => {pre.textContent = data.text;}, error => {pre.textContent = error.message;});
}, true);

async function loadCron() {
  clearTimeout(cronTimer);
  if (!skillsReady) return;
  try {cronData = await api('term_cron_list');}
  catch (error) {
    if (/교직원판에서만/.test(error.message)) {        // 학생판 — 예약은 교사판만 (desktop.py CRON_STUDENT)
      $('cron-tab').hidden = true;
      if (panelTab === 'cron') setPanelTab('usage');
      return;
    }
    $('cron-list').innerHTML = `<li class="sk-empty">${esc(error.message)}</li>`;
    cronListHtml = '';
    return;
  }
  if (!Array.isArray(cronData?.schedules)) {cronData = null; return;}      // 옛 데스크·점검용 가짜 응답
  cronReady = true;
  if (cronData.auth) {
    const before = loginState.claude?.logged_in;
    loginState.claude = {...(loginState.claude || {}), ...cronData.auth, label: 'Claude Code', checked: Date.now()};
    if (before !== loginState.claude.logged_in) paintLogin('claude');      // 로그인이 풀렸거나 됐다 — 칸의 안내도 맞춘다
  }
  paintCron();
  try {paintRuns(await api('term_cron_runs', {limit: 15}));} catch {}
  if (!$('skills').hidden && panelTab === 'cron') cronTimer = setTimeout(loadCron, CRON_POLL);
}
function paintCronBanner() {
  const auth = loginState.claude, notes = [];
  if (auth?.installed === false) notes.push(['bad', 'Claude Code 가 이 PC 에 설치되어 있지 않습니다 — 예약 업무는 Claude Code 에이전트에게 맡깁니다.', '']);
  else if (auth?.logged_in === false) notes.push(['bad', 'Claude Code 에 로그인되어 있지 않아 예약이 돌지 않습니다.', '<button class="primary" data-do="login" data-tool="claude">로그인하기</button>']);
  if (cronData && !cronData.linked) notes.push(['', '스페이스기전 계정이 연결되어 있지 않아 결과를 휴대폰으로 보내지 못합니다 — 독의 «연결 및 설정»에서 로그인해 주세요.', '']);
  $('cron-banner').innerHTML = notes.map(([tone, text, extra]) => `<div class="cr-banner ${tone}">${esc(text)}${extra ? `<div>${extra}</div>` : ''}</div>`).join('');
}
function paintCron() {
  const data = cronData;
  if (!data) return;
  paintCronBanner();
  $('cron-limit').textContent = `${data.schedules.length} / ${data.limit}`;
  $('cron-add').disabled = data.schedules.length >= data.limit;
  const html = data.schedules.length ? data.schedules.map(row => {
    const [tone, text] = cronLine(row);
    return `<li class="cr-item${row.on ? '' : ' off'}${row.running ? ' run' : ''}">`
      + `<button class="cr-open" data-cron-edit="${esc(row.id)}" title="${esc(row.prompt)}\n\n누르면 고칩니다">`
      + `<b>${esc(row.title)}</b><small>${esc(row.describe)} · ${esc(row.target.title || row.target.name)}${row.by ? ` · ${esc(row.by)} 가 만듦` : ''}</small>`
      + `<small class="cr-state ${tone}">${esc(text)}</small></button>`
      + `<div class="cr-tools"><input type="checkbox" class="switch" data-cron-on="${esc(row.id)}"${row.on ? ' checked' : ''} aria-label="${esc(row.title)} 켜기" title="켜기 · 끄기">`
      + `<button data-cron-run="${esc(row.id)}"${row.running ? ' disabled' : ''} title="시각과 상관없이 지금 한 번 돌립니다 (정해 둔 다음 시각은 그대로)">지금 한 번</button></div></li>`;
  }).join('') : '<li class="sk-empty">아직 없습니다 — «＋ 예약 만들기»로 «평일 아침 8시에 오늘 마감 공문 정리» 같은 일을 맡겨 보세요.</li>';
  if (html !== cronListHtml) {cronListHtml = html; $('cron-list').innerHTML = html;}
}
function paintRuns(runs) {
  const html = runs.length ? runs.map(run => {
    const tone = run.status === 'done' ? 'done' : 'bad';
    return `<li><details data-run="${esc(run.id)}"${cronOpenRuns.has(run.id) ? ' open' : ''}><summary>`
      + `<span class="badge ${tone}">${esc(cronStatus(run.status))}</span>${run.late ? '<span class="badge late">늦게</span>' : ''}`
      + `<span title="${esc(run.title)}">${esc(run.title)}${run.manual ? ' · 지금 한 번' : ''}</span><small>${esc(whenText(run.finished || run.started))}</small></summary>`
      + `<pre>${esc(run.result || '')}</pre></details></li>`;
  }).join('') : '<li class="sk-empty">아직 돈 예약이 없습니다.</li>';
  if (html !== cronRunsHtml) {cronRunsHtml = html; $('cron-runs').innerHTML = html;}
}
$('cron-runs').addEventListener('toggle', event => {
  const id = event.target.dataset?.run;
  if (!id) return;
  if (event.target.open) cronOpenRuns.add(id); else cronOpenRuns.delete(id);
  cronRunsHtml = '';                                    // 다음에 다시 그릴 때 펼친 상태를 반영하게
}, true);
$('panel-cron').addEventListener('click', event => {
  const target = event.target.closest('button');
  if (!target || target.disabled) return;
  if (target.id === 'cron-add') openCronEdit(null);
  else if (target.dataset.cronEdit) openCronEdit(cronData?.schedules.find(row => row.id === target.dataset.cronEdit));
  else if (target.dataset.cronRun) attempt(async () => {toast(await api('term_cron_run', {id: target.dataset.cronRun})); await loadCron();});
});
$('panel-cron').addEventListener('change', event => {
  const id = event.target.dataset?.cronOn;
  if (id) attempt(async () => {
    try {toast(await api('term_cron_toggle', {id, on: event.target.checked}));}
    finally {cronListHtml = ''; await loadCron();}
  });
});

// 편집 창
function setCronKind(kind) {
  cronKind = kind;
  document.querySelectorAll('.cr-kinds [data-kind]').forEach(button => button.setAttribute('aria-checked', String(button.dataset.kind === kind)));
  document.querySelectorAll('.cr-when [data-for]').forEach(el => {el.hidden = !el.dataset.for.split(' ').includes(kind);});
  previewCron();
}
function paintCronDays() {
  $('cron-days').innerHTML = [1, 2, 3, 4, 5, 6, 0].map(day =>
    `<button type="button" data-day="${day}" aria-pressed="${cronDays.has(day)}">${DAY_LETTERS[day]}</button>`).join('');
}
function whenFromForm() {
  const time = $('cron-time').value;
  if (cronKind === 'once') return {kind: 'once', date: $('cron-date').value, time};
  if (cronKind === 'daily' || cronKind === 'weekdays') return {kind: cronKind, time};
  if (cronKind === 'weekly') return {kind: 'weekly', time, days: [...cronDays].sort()};
  if (cronKind === 'interval') return {kind: 'interval', hours: Number($('cron-hours').value),
                                       minute: Math.max(0, Math.min(59, parseInt($('cron-minute').value, 10) || 0))};
  return {kind: 'cron', expr: $('cron-expr').value};
}
function previewCron() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const box = $('cron-preview');
    try {
      const result = await api('term_cron_preview', {when: whenFromForm()});
      box.className = 'cr-preview';
      box.innerHTML = `<b>${esc(result.describe)}</b>` + (result.next.length
        ? ` — 다음: ${result.next.map(value => esc(whenText(value))).join(', ')}` : ' — 앞으로 돌 시각이 없습니다');
    } catch (error) {
      box.className = 'cr-preview bad';
      box.textContent = error.message;
    }
  }, 180);
}
function cronAgentNote() {
  const agentRow = cronData?.agents.find(row => row.name === $('cron-agent').value);
  const notes = [];
  if (agentRow?.skip) notes.push('이 에이전트는 «권한 묻지 않기»로 열려 있어, 예약 시각에 사람에게 묻지 않고 파일을 고치거나 명령을 실행합니다.');
  if (agentRow && !agentRow.team) notes.push('«에이전트끼리 보기»를 끄고 연 에이전트라 휴대폰에서 이어서 시킬 수는 없습니다(결과는 받습니다).');
  if (!agentRow && cronEditing && $('cron-agent').value === cronEditing.target.name) notes.push('이 에이전트는 지금 닫혀 있습니다 — 시각이 되면 같은 폴더에 새로 엽니다.');
  $('cron-agent-note').hidden = !notes.length;
  $('cron-agent-note').textContent = notes.join(' ');
}
function openCronEdit(row) {
  if (!cronData) return;
  cronEditing = row || null;
  $('cron-edit-title').textContent = row ? '예약 고치기' : '예약 만들기';
  $('cron-title').value = row?.title || '';
  $('cron-prompt').value = row?.prompt || '';
  const agents = cronData.agents.filter(item => !item.closed || item.name === row?.target.name);
  const options = agents.map(item => `<option value="${esc(item.name)}">${esc(item.title)} · ${esc(item.folder.split(/[\\/]/).filter(Boolean).pop() || item.folder)}</option>`);
  if (row && !agents.some(item => item.name === row.target.name)) {
    options.unshift(`<option value="${esc(row.target.name)}">${esc(row.target.title || row.target.name)} (지금 닫혀 있음)</option>`);
  }
  $('cron-agent').innerHTML = options.join('') || '<option value="">열려 있는 Claude Code 에이전트가 없습니다 — 먼저 에이전트를 여세요</option>';
  const here = now();
  $('cron-agent').value = row?.target.name || (here?.info.tool === 'claude' ? here.info.agent : agents[0]?.name || '');
  $('cron-save').disabled = !options.length;
  const when = row?.when || {kind: 'weekdays', time: '08:00'};
  const tomorrow = new Date(Date.now() + 86400000);
  $('cron-time').value = when.time || '08:00';
  $('cron-date').value = when.date || `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`;
  $('cron-hours').value = String(when.hours || 2);
  $('cron-minute').value = String(when.minute ?? 0);
  $('cron-expr').value = when.expr || '';
  cronDays.clear();
  (when.days || [1, 2, 3, 4, 5]).forEach(day => cronDays.add(day));
  paintCronDays();
  $('cron-on').checked = row ? !!row.on : true;
  $('cron-delete').hidden = !row;
  $('cron-delete').textContent = '지우기';
  delete $('cron-delete').dataset.armed;
  cronAgentNote();
  $('cron-edit').hidden = false;
  setCronKind(when.kind);
  $('cron-title').focus();
}
function closeCronEdit() {$('cron-edit').hidden = true; cronEditing = null; now()?.term.focus();}
$('cron-hours').innerHTML = Array.from({length: 12}, (_, n) => `<option value="${n + 1}">${n + 1}시간마다</option>`).join('');
document.querySelector('.cr-kinds').addEventListener('click', event => {
  const button = event.target.closest('[data-kind]');
  if (button) setCronKind(button.dataset.kind);
});
$('cron-days').addEventListener('click', event => {
  const button = event.target.closest('[data-day]');
  if (!button) return;
  const day = Number(button.dataset.day);
  if (cronDays.has(day)) cronDays.delete(day); else cronDays.add(day);
  paintCronDays();
  previewCron();
});
['cron-date', 'cron-time', 'cron-hours', 'cron-minute', 'cron-expr'].forEach(id => $(id).addEventListener('input', previewCron));
$('cron-agent').addEventListener('change', cronAgentNote);
$('cron-cancel').addEventListener('click', closeCronEdit);
$('cron-edit').addEventListener('mousedown', event => {if (event.target === event.currentTarget) closeCronEdit();});
$('cron-edit').addEventListener('keydown', event => {if (event.key === 'Escape') {event.stopPropagation(); closeCronEdit();}});
$('cron-form').addEventListener('submit', event => {
  event.preventDefault();
  attempt(async () => {
    toast(await api('term_cron_save', {id: cronEditing?.id, title: $('cron-title').value, prompt: $('cron-prompt').value,
                                       agent: $('cron-agent').value, when: whenFromForm(), on: $('cron-on').checked}));
    closeCronEdit();
    cronListHtml = '';
    await loadCron();
  });
});
$('cron-delete').addEventListener('click', () => {
  const button = $('cron-delete');
  if (!cronEditing) return;
  if (!button.dataset.armed) {button.dataset.armed = '1'; button.textContent = '정말 지울까요?'; return;}   // 한 번 더 눌러야 지운다
  const id = cronEditing.id;
  attempt(async () => {
    toast(await api('term_cron_remove', {id}));
    closeCronEdit();
    cronListHtml = '';
    await loadCron();
  });
});

// 에이전트가 만든 예약 승인 (2026-11-07) — 중계 /cron 이 데스크를 거쳐 묻는다(desktop.py `_cron_ask`, CRON_ASK_WAIT 초).
// 답하지 않거나 창을 닫으면 승인 대기로 저장되고 예약 탭에서 켜면 확정된다. 실수로 Enter 를 눌러도 거절 쪽에 둔다.
const CRON_ASK_WAIT = 180;
const cronAsks = [];
let cronAskTimer = 0;
function showCronAsk() {
  const ask = cronAsks[0];
  $('ask-cron').hidden = !ask;
  clearInterval(cronAskTimer);
  if (!ask) return;
  $('cron-ask-agent').textContent = ask.agent;
  $('cron-ask-verb').textContent = ask.turn_on ? '예약을 켜려고' : ask.edit ? '예약을 고치려고' : '예약을 만들려고';
  $('cron-ask-name').textContent = ask.title;
  $('cron-ask-when').textContent = ask.describe;
  $('cron-ask-next').textContent = ask.next?.length ? `다음: ${ask.next.map(whenText).join(', ')}` : '';
  $('cron-ask-target').textContent = ask.target || ask.agent;
  $('cron-ask-skip').hidden = !ask.skip;
  $('cron-ask-prompt').textContent = ask.prompt;
  $('cron-ask-before').hidden = !ask.before;
  if (ask.before) $('cron-ask-before').textContent = `지금: «${ask.before.title}» · ${ask.before.describe}${ask.before.prompt !== ask.prompt ? ' — 시킬 일도 바뀝니다' : ''}`;
  const started = Date.now();
  const tick = () => {
    const left = Math.max(0, CRON_ASK_WAIT - Math.round((Date.now() - started) / 1000));
    $('cron-ask-left').textContent = `${left}초 안에 답하지 않으면 꺼진 채 «승인 대기»로 저장됩니다 — 예약 탭에서 켜면 확정.`;
  };
  tick();
  cronAskTimer = setInterval(tick, 1000);
  $('cron-ask-deny').focus();
}
function answerCron(allow) {
  const ask = cronAsks.shift();
  showCronAsk();
  if (ask) attempt(async () => {
    toast(await api('term_cron_answer', {request: ask.id, allow}), !allow);
    cronListHtml = '';
    if (cronReady) setTimeout(loadCron, 400);
  });
}
$('cron-ask-allow').addEventListener('click', () => answerCron(true));
$('cron-ask-deny').addEventListener('click', () => answerCron(false));

// ── 데스크가 부르는 것 ──────────────────────────────────
let started = false;
function start() {
  if (started) return;
  started = true;
  pollList();
  eventsToken++;
  pollEvents(eventsToken);
  api('term_snippets').then(saved => {if (Array.isArray(saved)) snippets = saved;}).catch(() => {});
  api('term_list').then(data => {team = data.team; $('team').checked = team; paintFeed();}).catch(() => {});
  if (!store.get('welcomed', false)) showWelcome(); else input.focus();
  paintGrants();
  paintPeer();
  paintKnow();
  paintMain();
  skillsReady = true;
  if (view.skills) loadSkills();
  setPanelTab(panelTab);
  if (panelTab !== 'cron') loadCron();       // 한 번 — 학생판이면 탭을 숨기고, 로그인 상태를 받아 둔다
}

window.deskTerm = {
  /** 창을 (다시) 불러왔다 — 데스크가 아는 세션 모두에 붙는다 */
  async attachAll(ids, focusId) {
    for (const id of [...sessions.keys()]) if (!ids.includes(id)) dropSession(id);
    for (const id of ids) await attach(id);
    focus(ids.includes(focusId) ? focusId : ids[ids.length - 1] || null);
    start();
    now()?.term.focus();
  },
  /** 에이전트를 하나 더 띄웠다 */
  async add(id) {
    await attach(id);
    focus(id);
    start();
    sessions.get(id)?.term.focus();
  },
  /** 하나만 띄우던 예전 이름 — 점검 스크립트가 부른다 */
  attach(id) {return this.attachAll([id], id);},
  dropped(paths) {
    if (Array.isArray(paths) && paths.length) addPaths(paths);
  },
  /** 중계가 묻는다 — 그 에이전트 화면의 마지막 lines 줄 (사람이 보는 그대로) */
  screenOf(id, lines) {
    const s = sessions.get(id);
    return s ? screenText(s, Math.max(1, Math.min(400, lines | 0 || 60))) : null;
  },
  /** 중계가 묻는다 — 그 에이전트가 선택지를 띄워 두었나 */
  choiceOf(id) {
    const s = sessions.get(id);
    return s ? waitingChoice(s) : null;
  },
  /** 에이전트가 앱을 다뤄도 되는지 묻는다 — {id, session, agent, app, title} */
  askComputer(ask) {
    if (!ask?.id || asks.some(item => item.id === ask.id)) return;
    asks.push(ask);
    if (asks.length === 1) showAsk();
  },
  /** 창의 ✕ 를 눌렀는데 켜진 에이전트가 있다 — 모두 끌지 묻는다 (보였으면 true) */
  askLeave() {return askLeave();},
  /** 그 질문이 끝났다 (답했거나 시간이 지났거나 창을 닫는다) */
  askDone(id) {
    const index = asks.findIndex(item => item.id === id);
    if (index >= 0) {
      asks.splice(index, 1);
      if (index === 0) showAsk();
    }
    const peer = peerAsks.findIndex(item => item.id === id);
    if (peer >= 0) {
      peerAsks.splice(peer, 1);
      if (peer === 0) showPeerAsk();
    }
    const cron = cronAsks.findIndex(item => item.id === id);
    if (cron >= 0) {
      cronAsks.splice(cron, 1);
      if (cron === 0) showCronAsk();
      cronListHtml = '';
      if (cronReady) setTimeout(loadCron, 400);           // 답이 없어 승인 대기로 저장됐을 수 있다
    }
  },
  /** 에이전트가 예약을 만들거나 고치거나 켜려 한다 — {id, agent, edit, title, prompt, describe, next, target, skip, before} */
  askCron(ask) {
    if (!ask?.id || cronAsks.some(item => item.id === ask.id)) return;
    cronAsks.push(ask);
    if (cronAsks.length === 1) showCronAsk();
  },
  /** 다른 PC 에서 새 요청이 왔다 — {id, session, target, skip, name, label, agent, body, long} */
  askPeer(ask) {
    if (!ask?.id || peerAsks.some(item => item.id === ask.id)) return;
    peerAsks.push(ask);
    if (peerAsks.length === 1) showPeerAsk();
  },
  /** 허락 목록이 바뀌었다 */
  grantsChanged() {paintGrants();},
  /** 고른 에이전트의 지금 화면 (점검용) */
  screenText() {return now() ? screenText(now()) : '';}
};

// ── 내 다른 PC (2026-11-12 요청) ─────────────────────────
// 내 계정으로 연 다른 PC 의 데스크 에이전트를 왼쪽 목록 «내 다른 PC» 에 방으로 보이고(SPACEKIJUN «에이전트»처럼),
// 누르면 가운데에 그 방의 대화 — 여기서 보낸 말과 그 에이전트의 답. 다른 선생님과의 연결(«다른 선생님»)과 따로,
// «내 기기» 스위치를 따른다. 서버 = spacekijun 20261112150000 (desk_agent_own_send · desk_agent_own_overview).
const ownSeen = new Map(Object.entries(store.get('ownSeen', {}) || {}));
const ownKey = (device, name) => `${device}/${name}`;
function ownAgents() {
  const out = [];
  for (const pc of ownData?.pcs || []) for (const agent of pc.agents || []) out.push({pc, agent, key: ownKey(pc.device, agent.name)});
  return out;
}
function ownMessages(device, name) {
  return (ownData?.messages || []).filter(m => m.to_device === device && m.to_agent === name)
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
}
function ownUnseen(key, device, name) {
  const seen = ownSeen.get(key) || '';
  return ownMessages(device, name).flatMap(m => m.replies || []).filter(r => String(r.created_at) > seen).length;
}
async function loadOwn() {
  if (ownBusy || document.hidden) return;
  ownBusy = true;
  try { ownData = await api('term_own', {}); } catch { ownData = null; }
  finally { ownBusy = false; }
  if (ownRoom) paintRoom();                 // 방을 먼저 — 읽은 답은 목록의 «새 답» 수에서 빠진다
  paintOwn();
}
function paintOwn() {
  const head = $('own-head'), list = $('own');
  if (!ownData) { head.hidden = list.hidden = true; return; }
  head.hidden = list.hidden = false;
  const pcs = ownData.pcs || [];
  $('own-note').textContent = !ownData.on ? '꺼짐' : pcs.length ? `${pcs.filter(p => p.online).length}대 연결` : '';
  if (!ownData.on || ownData.reason && !pcs.length) {
    list.innerHTML = `<li class="empty-own">${esc(ownData.reason || '«내 기기»를 켜면 내 다른 PC 의 에이전트가 여기 보입니다.')}</li>`;
    return;
  }
  if (!pcs.length) {
    list.innerHTML = '<li class="empty-own">내 계정으로 데스크를 켠 다른 PC 가 없습니다. 그 PC 에서도 에이전트 터미널을 열고 «내 기기»를 켜 두면 여기 보입니다.</li>';
    return;
  }
  list.innerHTML = pcs.map(pc => `<li class="pc"><span class="dot ${pc.online ? 'idle' : ''}"></span>${esc(pc.label)}${pc.online ? '' : ' · 꺼짐'}</li>`
    + (pc.agents || []).map(agent => {
      const key = ownKey(pc.device, agent.name), unseen = ownUnseen(key, pc.device, agent.name);
      const state = pc.online ? (agent.status || '') : '';
      return `<li class="agent" data-own="${esc(key)}" aria-current="${ownRoom && ownRoom.key === key}">`
        + `<span class="dot ${esc(state)}"></span><div class="copy"><strong>${esc(agent.title || agent.name)}</strong>`
        + `<small>${esc(pc.online ? (STATES[state] || state || '연결됨') : 'PC 꺼짐')} · ${esc(agent.name)}</small></div>`
        + (unseen ? `<span class="badge" title="새 답">${unseen}</span>` : '') + '</li>';
    }).join('')).join('');
}
// 입력칸은 아래 하나를 같이 쓴다 (2026-11-13 요청 — 방에 따로 있던 입력칸이 겹쳐 보였다). 방에서 쓰던 말은 방마다,
// 이 PC 칸에서 쓰던 말은 칸마다 따로 남는다(swapDraft). 방이 열려 있는 동안 Enter 는 그 PC 의 에이전트에게 보낸다(submit).
const ownDrafts = new Map();
const ownHolder = key => { if (!ownDrafts.has(key)) ownDrafts.set(key, {}); return ownDrafts.get(key); };
function ownRoomTitle() {
  const found = ownRoom && ownAgents().find(a => a.key === ownRoom.key);
  return found ? (found.agent.title || found.agent.name) : (ownRoom?.name || '');
}
function openRoom(key) {
  const found = ownAgents().find(a => a.key === key);
  if (!found) return;
  swapDraft(ownRoom ? ownHolder(ownRoom.key) : now(), ownHolder(key));
  ownRoom = {key, device: found.pc.device, name: found.agent.name};
  $('own-room').hidden = false;
  paintGhost();                             // 이 PC 칸의 다음 말 추천을 걷는다 — 자리표시는 paintRoom 이 쓴다
  paintRoom();
  paintOwn();
  paintHeader();
  input.focus();
}
function closeRoom() {
  if (!ownRoom) return;
  const left = ownRoom;
  ownRoom = null;
  swapDraft(ownHolder(left.key), now());
  $('own-room').hidden = true;
  input.placeholder = PLACEHOLDER;
  ghostText = '';
  paintGhost();
  paintOwn();
  paintHeader();
}
const ownStatus = m => ({sent: '보냄 — 그 PC 가 받기를 기다립니다', delivered: '에이전트에게 넣음', refused: '넣지 못함', expired: '그 PC 가 받지 않음'}[m.status] || m.status);
const ownWhen = v => { const d = new Date(v); return isNaN(d) ? '' : d.toLocaleString('ko-KR', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'}); };
const ownReplies = new Map();
function paintRoom() {
  const room = ownRoom; if (!room) return;
  const found = ownAgents().find(a => a.key === room.key);
  const pc = found?.pc, agent = found?.agent;
  $('or-title').textContent = agent ? (agent.title || agent.name) : room.name;
  $('or-sub').textContent = pc ? `${pc.label} · ${agent.name} · ${pc.online ? (STATES[agent.status] || '연결됨') : 'PC 꺼짐'}` : '이 에이전트는 이제 열려 있지 않습니다';
  $('or-dot').className = `dot ${pc?.online ? esc(agent?.status || 'idle') : ''}`;
  const ready = !!(pc && pc.online && agent);
  input.placeholder = ready ? `${pc.label} 의 ${agent.title || agent.name} 에게 보낼 말 — Enter 보내기 · Shift+Enter 줄바꿈 · Esc 방 닫기`
    : '그 PC 가 연결되어 있지 않아 지금은 보낼 수 없습니다 — Esc 로 방 닫기';
  $('target-name').textContent = `내 다른 PC · ${agent ? (agent.title || agent.name) : room.name}`;
  const list = $('or-list');
  const stick = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
  const messages = ownMessages(room.device, room.name);
  let older = false;
  const html = messages.map(m => {
    const old = !!(agent && m.thread && agent.thread && m.thread !== agent.thread);
    const sep = old && !older ? (older = true, '<li class="or-sep">이전 대화 — 그 칸을 다시 열거나 /clear 했습니다</li>') : (!old && older ? (older = false, '<li class="or-sep">지금 대화</li>') : '');
    return sep + `<li class="or-msg me${old ? ' old' : ''}">${esc(m.body)}</li>`
      + `<li class="or-meta">${esc(ownWhen(m.created_at))} · ${esc(ownStatus(m))}${m.status === 'refused' && m.note ? ` — ${esc(m.note)}` : ''}</li>`
      + (m.replies || []).map(r => { ownReplies.set(r.id, {body: r.body, from: `${r.label || pc?.label || 'PC'} 의 ${r.agent || room.name}`});
        return `<li class="or-msg ai${old ? ' old' : ''}">${esc(r.body)}<br><button class="fwd" data-fwd="${esc(r.id)}" title="이 답을 이 PC 에서 고른 에이전트의 입력칸에 넣습니다">이 PC 의 에이전트에게 전달</button></li>`
          + `<li class="or-meta">${esc(ownWhen(r.created_at))} · ${esc(r.agent || room.name)}</li>`; }).join('');
  }).join('');
  const next = html || '<li class="none">아직 주고받은 말이 없습니다.<br>아래에 적어 보내면 그 PC 의 이 에이전트에게 바로 들어가고(묻지 않음), 에이전트가 답을 돌려보내면 여기에 보입니다.</li>';
  if (list.dataset.html !== next) { list.innerHTML = next; list.dataset.html = next; if (stick) list.scrollTop = list.scrollHeight; }
  const last = messages.flatMap(m => m.replies || []).map(r => String(r.created_at)).sort().pop();
  if (last && last > (ownSeen.get(room.key) || '')) {
    ownSeen.set(room.key, last);
    store.set('ownSeen', Object.fromEntries([...ownSeen].slice(-80)));
  }
}
let ownSending = false;
async function sendOwn() {
  const room = ownRoom, text = input.value.trim();
  if (!room || !text || ownSending) return;
  const found = ownAgents().find(a => a.key === room.key);
  if (!(found && found.pc.online)) { toast('그 PC 가 연결되어 있지 않아 지금은 보낼 수 없습니다.', true); return; }
  ownSending = true;
  $('send').disabled = true;
  try {
    await api('term_own_send', {device: room.device, agent: room.name, body: text, thread: found?.agent?.thread || ''});
    if (ownRoom === room) { input.value = ''; grow(); } else ownHolder(room.key).draft = null;
    toast('보냈습니다 — 그 PC 의 에이전트에게 들어갑니다.');
    await loadOwn();
    $('or-list').scrollTop = $('or-list').scrollHeight;
  } catch (error) { toast(error.message || String(error), true); }
  finally { ownSending = false; $('send').disabled = false; }
}
/** 받은 메시지·답을 이 PC 에서 고른 에이전트의 입력칸에 넣는다 — 보내지는 않는다(확인하고 Enter). */
function forwardToAgent(text, from) {
  const s = now();
  if (!s) { toast('먼저 왼쪽 목록에서 전달할 에이전트를 고르세요.', true); return; }
  closeRoom();
  input.setSelectionRange(input.value.length, input.value.length);
  insertText((input.value.trim() ? '\n\n' : '') + `[${from} 에게서 받은 메시지]\n${text}`);
  input.scrollTop = 0;
  toast(`${titleOf(s)} 의 입력칸에 넣었습니다 — 확인하고 Enter 로 보내세요.`);
}
$('own').addEventListener('click', event => { const row = event.target.closest('[data-own]'); if (row) openRoom(row.dataset.own); });
$('agents').addEventListener('click', () => closeRoom());
$('or-close').addEventListener('click', closeRoom);
$('or-list').addEventListener('click', event => {
  const fwd = event.target.closest('[data-fwd]');
  const got = fwd && ownReplies.get(fwd.dataset.fwd);
  if (got) forwardToAgent(got.body, got.from);
});
setInterval(() => { loadOwn(); }, 5000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) loadOwn(); });
loadOwn();

if (store.get('helpOpen', false)) toggleHelp(true);
arrange();
paintHeader();
paintFeed();
})();
