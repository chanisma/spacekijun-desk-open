// 스페이스기전 교실 — 전자칠판 화면. 1초마다 상태를 받아 그린다(Controller.state). 앱과는 api() 로만(Bridge.kt).
'use strict';

const $ = (id) => document.getElementById(id);
const FOLDER = 'application/vnd.google-apps.folder';

// ── 앱 다리 ──────────────────────────────────────────────────
const waiting = new Map();
let seq = 0;
window.__bridgeDone = (id, value) => {
  const done = waiting.get(id);
  if (done) { waiting.delete(id); done(value); }
};
function api(method, ...args) {
  return new Promise((resolve) => {
    if (!window.AndroidBridge) { resolve(null); return; }
    const id = 'c' + (++seq);
    waiting.set(id, resolve);
    window.AndroidBridge.invoke(id, method, JSON.stringify(args));
  });
}

// ── 공통 ─────────────────────────────────────────────────────
const mmss = (s) => {
  const v = Math.max(0, s || 0);
  return `${Math.floor(v / 60)}:${String(v % 60).padStart(2, '0')}`;
};
let toastTimer = 0;
function toast(text, error = false) {
  if (!text) return;
  const box = $('toast');
  box.textContent = text;
  box.classList.toggle('error', !!error);
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, error ? 9000 : 5000);
}
const show = (id, on) => { $(id).hidden = !on; };
// 옛 WebView(칠판에 따라 Chrome 70대)에도 있는 것만 — replaceChildren·?.·?? 를 쓰지 않는다
function fill(el, nodes) {
  while (el.firstChild) el.removeChild(el.firstChild);
  nodes.forEach((n) => el.appendChild(n));
}
const modalOpen = () => ['google', 'drive-link', 'confirm', 'prompt', 'settings'].find((id) => !$(id).hidden);

function confirmBox(title, body, ok = '확인', danger = false) {
  return new Promise((resolve) => {
    $('confirm-title').textContent = title;
    $('confirm-body').textContent = body;
    $('confirm-yes').textContent = ok;
    $('confirm-yes').className = danger ? 'danger' : 'primary';
    show('confirm', true);
    const done = (value) => { show('confirm', false); $('confirm-yes').onclick = $('confirm-no').onclick = null; resolve(value); };
    $('confirm-yes').onclick = () => done(true);
    $('confirm-no').onclick = () => done(false);
  });
}

function promptBox(title, value, ok) {
  return new Promise((resolve) => {
    $('prompt-title').textContent = title;
    $('prompt-yes').textContent = ok;
    $('prompt-input').value = value;
    show('prompt', true);
    setTimeout(() => { $('prompt-input').focus(); $('prompt-input').select(); }, 50);
    const done = (v) => { show('prompt', false); $('prompt-yes').onclick = $('prompt-no').onclick = null; resolve(v); };
    $('prompt-yes').onclick = () => done($('prompt-input').value.trim());
    $('prompt-no').onclick = () => done(null);
  });
}

// ── 아이콘(웹 iconSources.ts · Windows 교실 독과 같은 값) ───────────────
const GOOGLE_APPS = [
  ['classroom', '클래스룸'], ['drive', '드라이브(웹)'], ['docs', '문서'], ['sheets', '시트'], ['slides', '슬라이드'], ['forms', '설문지'],
  ['calendar', '캘린더'], ['meet', 'Meet'], ['gmail', 'Gmail'], ['keep', 'Keep'], ['sites', '사이트'], ['youtube', 'YouTube'],
];
const GOOGLE = {
  classroom: ['C', '#188038'], drive: ['D', '#1a73e8'], docs: ['문', '#4285f4'], sheets: ['시', '#0f9d58'],
  slides: ['슬', '#f4b400'], forms: ['설', '#7248b9'], calendar: ['31', '#1967d2'], meet: ['M', '#00897b'],
  gmail: ['M', '#ea4335'], keep: ['K', '#f6bf26'], sites: ['S', '#3f51b5'], youtube: ['▶', '#ff0000'],
};
const PROGRAM = {
  powerpoint: ['P', '#ea580c'], word: ['W', '#1d4ed8'], excel: ['X', '#15803d'], hwp: ['한', '#0284c7'],
  whiteboard: ['WB', '#0f766e'], notepad: ['메', '#475569'], paint: ['그', '#db2777'], calculator: ['계', '#1f2937'],
  snipping: ['캡', '#7e22ce'], osk: ['키', '#6b7280'],
};
const PROGRAM_IMAGES = new Set(['powerpoint', 'word', 'excel', 'notepad', 'calculator', 'osk']);
const SITE_IMAGES = new Set(['padlet', 'chatgpt', 'gemini', 'claude', 'canva', 'miricanvas', 'tkbell', 'kahoot', 'classcard', 'mentimeter', 'quizizz', 'riroschool', 'jinnote']);

const favicon = (url) => {
  try { return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(new URL(url).hostname)}&sz=128`; } catch (e) { return null; }
};
const driveType = (mime) => `https://drive-thirdparty.googleusercontent.com/128/type/${mime || 'application/octet-stream'}`;

function lookOf(item) {
  switch (item.kind) {
    case 'url': {
      if (item.app && GOOGLE[item.app]) return { img: `icons/google/${item.app}.png`, text: GOOGLE[item.app][0], color: GOOGLE[item.app][1] };
      const host = (() => { try { return new URL(item.url).hostname.replace(/^www\./, ''); } catch (e) { return '?'; } })();
      return { img: SITE_IMAGES.has(item.site) ? `icons/sites/${item.site}.png` : favicon(item.url), plate: true, text: host[0].toUpperCase(), color: '#0891b2' };
    }
    case 'drive':
      return item.folder ? { img: driveType(FOLDER), plate: true, text: '폴', color: '#d97706' }
        : { img: driveType(item.mime), plate: true, text: '파', color: '#2563eb' };
    case 'program': {
      const [text, color] = PROGRAM[item.program] || ['앱', '#64748b'];
      return { img: PROGRAM_IMAGES.has(item.program) ? `icons/programs/${item.program}.png` : null, text, color };
    }
    case 'space':
      return { img: 'icons/spacekijun.png', plate: true, text: 'S', color: '#4f46e5' };
    default:
      return { img: null, text: '?', color: '#64748b' };
  }
}
const KIND = { url: '사이트', drive: '드라이브', program: '앱', space: '스페이스기전' };

function icon(look) {
  const box = document.createElement('span');
  const letter = () => { box.className = 'ic'; box.style.background = look.color; box.textContent = look.text; };
  if (!look.img) { letter(); return box; }
  box.className = 'ic' + (look.plate ? ' plate' : '');
  const img = new Image();
  img.alt = '';
  img.onerror = letter;
  img.src = look.img;
  box.append(img);
  return box;
}

// ── 그리기 ───────────────────────────────────────────────────
let current = null;
let lastQr = '';
let lastTiles = '';
let lastNotice = '';
let linkShown = false;

function render(s) {
  current = s;
  const phase = s.phase;
  show('view-qr', phase === 'qr' || phase === 'sleep');
  show('view-offline', phase === 'offline');
  show('view-session', phase === 'session');
  show('view-ending', phase === 'ending');
  if (phase !== 'session') {
    if (!$('gtools').hidden) { show('gtools', false); window.GTools.reset(); }
    show('drive', false);
    show('google', false);
    show('drive-link', false);
    linkShown = false;
    lastTiles = '';
  }
  if (phase === 'qr' || phase === 'sleep') renderQr(s);
  else if (phase === 'offline') $('offline-text').textContent = s.error || '서버에 연결하는 중입니다.';
  else if (phase === 'session') renderSession(s);
  else if (phase === 'ending') $('ending-text').textContent = s.progress || '정리하는 중입니다.';
}

function renderQr(s) {
  $('device-name').textContent = s.device;
  // 쉬는 중(밤·주말 — 서버를 부르지 않는다): QR 대신 단추. 화면 어디를 눌러도 깨어난다
  const sleeping = s.phase === 'sleep';
  $('qr').hidden = sleeping;
  $('wake').hidden = !sleeping;
  if (sleeping) {
    lastQr = '';
    $('qr').innerHTML = '';
    $('qr-timer').textContent = '쉬는 중 — 화면을 누르면 연결 QR 이 나옵니다';
    $('qr-bar').style.width = '0%';
  } else if (s.qr && s.qr !== lastQr) {
    lastQr = s.qr;
    $('qr').innerHTML = s.qr;          // 이 앱이 만든 SVG(Qr.kt) — 바깥 내용이 아니다
  } else if (!s.qr && lastQr) {
    lastQr = '';                       // 이름을 바꿔 QR 을 새로 만드는 중 — 옛 QR 을 찍지 않게 지운다
    $('qr').innerHTML = '';
  }
  if (!sleeping) {
    $('qr-timer').textContent = s.qr ? (s.qr_left != null ? `${mmss(s.qr_left)} 뒤 새 QR` : '') : 'QR 을 새로 만드는 중…';
    // QR 은 10분마다 새로 — 남은 시간을 막대로
    $('qr-bar').style.width = s.qr && s.qr_left != null ? `${Math.max(0, Math.min(100, (s.qr_left / 600) * 100))}%` : '0%';
  }
  $('notice').hidden = !s.notice;
  $('notice').textContent = s.notice || '';
  $('update-bar').hidden = !s.update;
  if (s.update) $('update-text').textContent = `새 판 ${s.update.version} 을 받아 두었습니다.`;
}

function renderSession(s) {
  const se = s.session || {};
  const teacher = se.teacher || {};
  $('s-title').textContent = se.title || '수업';
  $('s-sub').textContent = [s.device, se.section, teacher.name || teacher.email].filter(Boolean).join(' · ');
  const chip = $('s-left');
  chip.textContent = s.remaining != null ? `남은 시간 ${mmss(s.remaining)}` : '수업 중';
  chip.classList.toggle('warn', !!s.warn);
  const drive = se.drive || {};
  $('s-drive-off').hidden = !(drive.ever && !drive.connected) || !!s.drive_link;

  const items = se.items || [];
  const key = JSON.stringify([items, drive.connected, drive.ever]);
  if (key !== lastTiles) {
    lastTiles = key;
    const tiles = [];
    tiles.push(tile({ look: { img: 'icons/google/google.png', plate: true, text: 'G', color: '#4285f4' }, label: '구글', kind: '구글 앱',
      onClick: () => openGoogle() }));
    if (drive.ever || drive.connected) {
      tiles.push(tile({ look: { img: 'icons/google/drive.png', text: 'D', color: '#1a73e8' },
        label: drive.connected ? '내 드라이브' : '드라이브 다시 연결', kind: '드라이브',
        badge: drive.connected ? '' : '!', onClick: () => (drive.connected ? openDrive() : reconnect()) }));
    }
    items.forEach((item, index) => {
      tiles.push(tile({ look: lookOf(item), label: item.name, kind: item.app ? '구글 앱' : KIND[item.kind] || '',
        badge: item.state === 'failed' ? '!' : '', failed: item.state === 'failed', title: item.message,
        missing: item.available === false, onClick: (el) => openTile(index, item, el) }));
    });
    fill($('tiles'), tiles);
  }

  const opened = se.opened || [];
  const busy = opened.filter((o) => o.state === 'pending' || o.state === 'uploading').length;
  const failed = opened.filter((o) => o.state === 'failed').length;
  $('s-opened').hidden = !opened.length;
  $('s-opened').textContent = `열어 둔 파일 ${opened.length}개` + (busy ? ` · ${busy}개 올리는 중` : '') + (failed ? ` · ${failed}개 못 올림` : '');
  $('s-opened').classList.toggle('busy', !!(busy || failed));
  renderOpened(opened);

  const text = se.notice || s.notice;
  if (text && text !== lastNotice) toast(text);
  lastNotice = text || '';

  if (s.drive_link) {
    if (!linkShown) { $('link-qr').innerHTML = s.drive_link.qr; linkShown = true; }
    $('link-left').textContent = `${mmss(s.drive_link.left)} 남음`;
    show('drive-link', true);
  } else if (linkShown) {
    linkShown = false;
    show('drive-link', false);
  }
}

function tile({ look, label, kind, badge, failed, missing, title, onClick }) {
  const li = document.createElement('li');
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'tile' + (failed ? ' failed' : '') + (missing ? ' missing' : '');
  if (title) b.title = title;
  if (kind) b.setAttribute('aria-label', `${label} (${kind})`);
  const name = document.createElement('span');
  name.className = 'label';
  name.textContent = label || '';
  b.append(icon(look), name);
  if (missing) {
    const why = document.createElement('span');
    why.className = 'why';
    why.textContent = '이 칠판에 없음';
    b.append(why);
  }
  if (badge) {
    const mark = document.createElement('span');
    mark.className = 'badge';
    mark.textContent = badge;
    b.append(mark);
  }
  b.addEventListener('click', () => onClick(b));
  li.append(b);
  return li;
}

async function openTile(index, item, el) {
  if (el.classList.contains('busy')) return;
  el.classList.add('busy');
  if (item.kind === 'drive' && !item.folder) toast(`«${item.name}» 을(를) 받는 중입니다…`);
  const r = await api('open_item', index);
  el.classList.remove('busy');
  if (!r) return;
  if (r.ok === false) {
    toast(r.error, true);
    if (r.auth) reconnect();
    return;
  }
  if (r.folder) openDrive(r.folder.id, r.folder.name);
  if (r.gtools) openGTools(r.gtools);
}

// ── 구글 수업 도구(gtools.js) ─────────────────────────────────
let gtoolsMounted = false;
function openGTools(tab) {
  show('google', false);
  if (!gtoolsMounted) {
    gtoolsMounted = true;
    window.GTools.mount($('gt-root'), {
      call: (name, ...args) => api(name, ...args),
      close: () => show('gtools', false),
      fullscreen: () => {},                // 칠판 화면은 이미 전체 화면
    });
  }
  show('gtools', true);
  window.GTools.open(tab);
}
$('login-forget').addEventListener('click', async () => {
  const yes = await confirmBox('이 칠판의 로그인을 지울까요?',
    '열린 웹 화면이 닫히고, 지금 로그인과 이 칠판에 보관한 로그인(구글·패들렛 등)을 지웁니다.\n다시 로그인하면 수업이 끝날 때 새로 보관합니다.', '지우기', true);
  if (!yes) return;
  const r = await api('forget_login');
  toast(r && r.ok ? '이 칠판의 로그인을 지웠습니다. 다시 로그인하면 수업이 끝날 때 보관합니다.' : (r && r.error) || '지우지 못했습니다.', !(r && r.ok));
  show('google', false);
});
document.querySelectorAll('[data-tool]').forEach((b) => b.addEventListener('click', () => openGTools(b.dataset.tool)));

async function reconnect() {
  const r = await api('drive_reconnect');
  if (r && r.ok === false) toast(r.error, true);
}

// ── 구글 앱 ─────────────────────────────────────────────────
function openGoogle() {
  const teacher = (current && current.session && current.session.teacher) || {};
  $('google-sub').textContent = teacher.email ? `${teacher.email} 로 로그인` : '';
  // 로그인 보관(②) — 구글·패들렛 같은 사이트 로그인을 이 칠판에 암호화해 남긴다(열쇠는 서버, 이 선생님 QR 승인 때만)
  const login = (current && current.session && current.session.login) || {};
  $('login-note').textContent = !login.supported
    ? '웹은 앱 안 브라우저로 열립니다. 이 칠판(안드로이드 8)은 로그인 보관을 지원하지 않아 수업이 끝나면 지웁니다.'
    : login.kept
      ? (login.cleared ? '로그인을 지웠습니다. 다시 로그인하면 수업이 끝날 때 보관합니다.'
        : login.restored
          ? (login.google === false
            ? '보관본을 불러왔지만 구글 로그인은 없었습니다. 구글은 다시 로그인해 주세요. 수업이 끝나면 다시 잠가 둡니다.'
            : '보관해 둔 로그인을 불러왔습니다(구글·패들렛 등). 수업이 끝나면 다시 잠가 둡니다.')
          : '여기서 한 번 로그인하면(구글로 계속하기 등) 수업이 끝날 때 이 칠판에 암호화해 보관합니다. 다음 수업엔 로그인된 채 열립니다.')
      : '이번 수업만 로그인합니다. 수업이 끝나면 지웁니다(승인 화면에서 «로그인 보관»을 켜면 남깁니다).';
  $('login-forget').hidden = !(login.supported && login.kept);
  fill($('google-apps'), GOOGLE_APPS.map(([key, label]) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'app';
    const name = document.createElement('span');
    name.textContent = label;
    b.append(icon({ img: `icons/google/${key}.png`, text: GOOGLE[key][0], color: GOOGLE[key][1] }), name);
    b.addEventListener('click', async () => {
      show('google', false);
      const r = await api('open_google_app', key);
      if (r && r.ok === false) toast(r.error, true);
    });
    return b;
  }));
  show('google', true);
}

// ── 드라이브 탐색기 ───────────────────────────────────────────
const nav = { stack: [], selected: new Map(), files: [], loading: false };
const atFolder = () => nav.stack[nav.stack.length - 1];
const SOURCES = { root: '내 드라이브', shared: '공유 문서함', drives: '공유 드라이브' };

async function openDrive(folderId, name) {
  show('drive', true);
  api('drive_start').then((r) => { $('d-email').textContent = (r && r.email) || ''; });
  if (folderId && folderId !== 'root') {
    nav.stack = [{ id: 'root', name: SOURCES.root, source: 'root' }, { id: folderId, name: name || '폴더' }];
    markSource('root');
    nav.selected.clear();
    load();
  } else {
    setSource('root');
  }
}

function markSource(source) {
  document.querySelectorAll('.source').forEach((b) => b.classList.toggle('on', b.dataset.source === source));
}

function setSource(source) {
  markSource(source);
  nav.stack = [{ id: source, name: SOURCES[source], source }];
  nav.selected.clear();
  load();
}

function message(text, kind = '') {
  const box = $('d-message');
  box.hidden = !text;
  box.className = 'banner' + (kind ? ' ' + kind : '');
  box.textContent = text || '';
}

async function load() {
  const here = atFolder();
  nav.loading = true;
  message('');
  fill($('d-list'), [emptyRow('불러오는 중…')]);
  renderPath();
  let r;
  if (here.id === 'drives') {
    r = await api('drive_shared_drives');
    if (r && r.ok !== false) r.files = (r.drives || []).map((d) => ({ id: d.id, name: d.name, mimeType: FOLDER, driveRoot: true }));
  } else {
    r = await api('drive_list', here.id, here.driveId || '');
  }
  nav.loading = false;
  if (atFolder() !== here) return;
  if (!r || r.ok === false) {
    fill($('d-list'), []);
    message((r && r.error) || '불러오지 못했습니다.', 'error');
    if (r && r.auth) reconnect();
    return;
  }
  nav.files = r.files || [];
  renderList();
}

function renderPath() {
  const parts = [];
  nav.stack.forEach((step, i) => {
    if (i) { const sep = document.createElement('span'); sep.className = 'sep'; sep.textContent = '›'; parts.push(sep); }
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = step.name;
    b.addEventListener('click', () => { if (i < nav.stack.length - 1) { nav.stack = nav.stack.slice(0, i + 1); nav.selected.clear(); load(); } });
    parts.push(b);
  });
  fill($('d-path'), parts);
  const here = atFolder();
  const writable = here && here.id !== 'shared' && here.id !== 'drives';
  $('d-mkdir').hidden = !writable;
  $('d-upload').hidden = !writable;
  renderSelection();
}

function emptyRow(text) {
  const li = document.createElement('li');
  li.className = 'd-empty';
  li.textContent = text;
  return li;
}

const sizeText = (n) => {
  const v = Number(n || 0);
  if (!v) return '';
  if (v < 1024 * 1024) return `${Math.max(1, Math.round(v / 1024))}KB`;
  return `${(v / 1024 / 1024).toFixed(v < 10 * 1024 * 1024 ? 1 : 0)}MB`;
};
const dateText = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  return d.toDateString() === now.toDateString()
    ? d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('ko-KR', { year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric', month: 'long', day: 'numeric' });
};

function renderList() {
  if (!nav.files.length) {
    fill($('d-list'), [emptyRow('비어 있습니다.')]);
    return;
  }
  const opened = new Map(((current && current.session && current.session.opened) || []).map((o) => [o.source_id, o]));
  fill($('d-list'), nav.files.map((f) => {
    const li = document.createElement('li');
    const folder = f.mimeType === FOLDER;
    li.className = 'row-item' + (nav.selected.has(f.id) ? ' sel' : '');
    if (!f.driveRoot) {
      const pick = document.createElement('button');
      pick.type = 'button';
      pick.className = 'pick';
      pick.textContent = '✓';
      pick.setAttribute('aria-label', `${f.name} 고르기`);
      pick.addEventListener('click', () => {
        if (nav.selected.has(f.id)) nav.selected.delete(f.id); else nav.selected.set(f.id, f);
        li.classList.toggle('sel', nav.selected.has(f.id));
        renderSelection();
      });
      li.append(pick);
    }
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'open';
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = f.name;
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = folder ? '' : [dateText(f.modifiedTime), sizeText(f.size)].filter(Boolean).join(' · ');
    open.append(icon(folder ? { img: driveType(FOLDER), plate: true, text: '폴', color: '#d97706' }
      : { img: driveType(f.mimeType), plate: true, text: '파', color: '#2563eb' }), name);
    const mine = opened.get(f.id);
    if (mine) {
      const st = document.createElement('span');
      st.className = 'state';
      st.textContent = '열어 둠';
      open.append(st);
    }
    open.append(meta);
    open.addEventListener('click', () => (folder ? enter(f) : openFile(f, open)));
    li.append(open);
    return li;
  }));
}

function enter(f) {
  const here = atFolder();
  const driveId = f.driveRoot ? f.id : here.driveId;
  nav.stack.push({ id: f.id, name: f.name, driveId });
  nav.selected.clear();
  load();
}

async function openFile(f, el) {
  if (el.disabled) return;
  el.disabled = true;
  toast(`«${f.name}» 을(를) 받는 중입니다…`);
  const r = await api('drive_open', f.id);
  el.disabled = false;
  if (!r || r.ok === false) {
    toast((r && r.error) || '열지 못했습니다.', true);
    if (r && r.auth) reconnect();
    return;
  }
  toast('열었습니다. 고치고 저장하면 드라이브에 올립니다.');
}

function renderSelection() {
  const n = nav.selected.size;
  $('d-selected').hidden = !n;
  $('d-selected').textContent = `${n}개 고름`;
  $('d-save').hidden = !n;
  $('d-clear').hidden = !n;
}

function renderOpened(opened) {
  const box = $('d-opened');
  box.hidden = !opened.length;
  if (!opened.length) return;
  const label = document.createElement('b');
  label.textContent = '열어 둔 파일';
  const STATE = { synced: (o) => (o.uploaded_at ? '✓ 올림' : '열림'), pending: () => '↑ 저장 감지', uploading: () => '↑ 올리는 중', failed: () => '! 못 올림' };
  const key = JSON.stringify(opened);
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  fill(box, [label].concat(opened.map((o) => {
    const pill = document.createElement('span');
    pill.className = 'pill ' + o.state;
    if (o.message) pill.title = o.message;
    const name = document.createElement('span');
    name.textContent = o.name;
    const st = document.createElement('small');
    st.textContent = (STATE[o.state] || STATE.synced)(o);
    pill.append(name, st);
    return pill;
  })));
}

$('d-back').addEventListener('click', () => show('drive', false));
document.querySelectorAll('.source').forEach((b) => b.addEventListener('click', () => setSource(b.dataset.source)));
$('d-clear').addEventListener('click', () => { nav.selected.clear(); renderList(); renderSelection(); });
$('d-save').addEventListener('click', async () => {
  const items = [...nav.selected.values()].map((f) => ({ id: f.id, name: f.name, mimeType: f.mimeType, shortcutDetails: f.shortcutDetails }));
  toast('저장할 폴더를 고르세요.');
  const r = await api('drive_save', items);
  if (!r) return;
  if (r.ok === false) { toast(r.error, true); return; }
  if (r.cancelled) return;
  nav.selected.clear();
  renderList();
  renderSelection();
  const extra = (r.errors && r.errors.length) ? ` (${r.errors.length}개 실패: ${r.errors[0]})` : '';
  toast(`${r.copied}개를 이 기기에 저장했습니다. 수업이 끝나도 지우지 않습니다.${extra}`, !!extra);
});
$('d-mkdir').addEventListener('click', async () => {
  const name = await promptBox('새 폴더', '새 폴더', '만들기');
  if (!name) return;
  const r = await api('drive_mkdir', atFolder().id, name);
  if (r && r.ok === false) { toast(r.error, true); return; }
  load();
});
$('d-upload').addEventListener('click', async () => {
  const r = await api('drive_upload', atFolder().id);
  if (!r) return;
  if (r.ok === false) { toast(r.error, true); return; }
  if (!r.count && !(r.errors && r.errors.length)) return;
  toast(r.errors && r.errors.length ? `${r.count}개 올림, ${r.errors.length}개 실패: ${r.errors[0]}` : `${r.count}개를 올렸습니다.`, !!(r.errors && r.errors.length));
  load();
});

// ── 수업 단추 ─────────────────────────────────────────────────
$('s-extend').addEventListener('click', async () => {
  const r = await api('extend', 10);
  if (r && r.ok === false) toast(r.error, true); else toast('수업을 10분 늘렸습니다.');
});
$('s-finish').addEventListener('click', async () => {
  const yes = await confirmBox('수업을 끝낼까요?', '고친 파일은 드라이브에 올리고, 연 화면·받은 파일·로그인을 지운 뒤 QR 화면으로 돌아갑니다.', '수업 끝', true);
  if (!yes) return;
  show('drive', false);
  const r = await api('finish');
  if (r && r.ok === false) toast(r.error, true);
});
$('s-reconnect').addEventListener('click', reconnect);
// 열어 둔 파일 → 드라이브 탐색기(아래에 열어 둔 파일과 올림 상태가 보인다)
$('s-opened').addEventListener('click', () => {
  const drive = (current && current.session && current.session.drive) || {};
  if (drive.connected) openDrive(); else reconnect();
});
$('link-cancel').addEventListener('click', () => { show('drive-link', false); linkShown = false; api('drive_reconnect_cancel'); });
document.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => show(b.dataset.close, false)));

// ── 기기 설정 ─────────────────────────────────────────────────
async function fillSettings() {
  const s = await api('settings');
  if (!s) return;
  if (document.activeElement !== $('name-input')) $('name-input').value = s.device_name;
  $('overlay-open').textContent = s.overlay ? '허용됨' : '허용하기';
  $('overlay-open').disabled = !!s.overlay;
  $('version-text').textContent = `${s.version}` + (s.update ? ` · 새 판 ${s.update.version} 받아 둠` : '');
  // 받아 둔 새 판이 있으면 단추가 [지금 설치]
  const ub = $('update-check');
  ub.textContent = s.update ? `지금 설치 (${s.update.version})` : '새 판 확인';
  ub.className = s.update ? 'primary small' : 'ghost small';
  if (s.update) ub.dataset.ready = '1'; else delete ub.dataset.ready;
  const major = parseInt(String(s.webview || '').split('.')[0], 10) || 0;
  $('engine-text').textContent = s.webview
    ? `웹 엔진 ${s.webview}` + (major && major < 100 ? ' — 오래되어 요즘 사이트가 깨질 수 있습니다. 칠판 관리자에게 «Android System WebView» 업데이트를 부탁하세요.' : '')
    : '';
  $('engine-text').className = major && major < 100 ? 'warn-text' : '';
}
async function openSettings() {
  await fillSettings();
  show('settings', true);
}
$('open-settings').addEventListener('click', openSettings);
$('offline-settings').addEventListener('click', openSettings);
// 쉬는 중 — 단추든 화면 어디든 누르면 깨운다(QR 화면에서 누르면 쉬는 시간 10분을 다시 센다)
$('wake').addEventListener('click', () => api('wake'));
document.addEventListener('pointerdown', () => {
  if (current && (current.phase === 'sleep' || current.phase === 'qr')) api('wake');
}, true);
$('overlay-open').addEventListener('click', () => api('open_overlay_settings'));
$('save-name').addEventListener('click', async () => {
  const name = $('name-input').value.trim();
  if (!name) return;
  await api('save_name', name);
  show('settings', false);
  toast('기기 이름을 저장했습니다. 새 이름으로 QR 을 다시 만듭니다.');
});
// 기기 설정에서 바로 — [새 판 확인] 으로 받으면 같은 단추가 [지금 설치](2026-10-14 요청)
$('update-check').addEventListener('click', async () => {
  const b = $('update-check');
  if (b.dataset.ready) {
    const r = await api('install_update');
    if (r) toast(r.ok === false ? r.error : r.message, r.ok === false);
    return;
  }
  b.disabled = true;
  b.textContent = '확인하는 중…';
  const r = await api('check_update');
  b.disabled = false;
  b.textContent = '새 판 확인';
  if (!r || r.ok === false) { toast((r && r.error) || '새 판을 확인하지 못했습니다.', true); return; }
  if (!r.version) toast('지금이 가장 새 판입니다.');
  fillSettings();
});
$('update-install').addEventListener('click', async () => {
  const r = await api('install_update');
  if (r) toast(r.ok === false ? r.error : r.message, r.ok === false);
});
$('quit-open').addEventListener('click', async () => {
  show('settings', false);
  const yes = await confirmBox('앱을 끝낼까요?', '끝내면 이 칠판에 QR 이 뜨지 않아 선생님들이 연결할 수 없습니다.\n다시 쓰려면 칠판의 앱 목록에서 «스페이스기전 교실»을 여세요.', '끝내기', true);
  if (yes) api('quit');
});

// ── 뒤로 · 돌아옴 · 바퀴 ─────────────────────────────────────────
window.onBack = () => {
  if (!$('gtools').hidden) {
    if (!window.GTools.back()) show('gtools', false);
    return true;
  }
  const open = modalOpen();
  if (open) {
    if (open === 'confirm') $('confirm-no').click();
    else if (open === 'prompt') $('prompt-no').click();
    else if (open === 'drive-link') $('link-cancel').click();
    else show(open, false);
    return true;
  }
  if (!$('drive').hidden) {
    if (nav.stack.length > 1) { nav.stack.pop(); nav.selected.clear(); load(); } else show('drive', false);
    return true;
  }
  return false;
};
window.onResumeApp = () => {
  if (!$('settings').hidden) fillSettings();
  tick();
};

let ticking = false;
async function tick() {
  if (ticking) return;
  ticking = true;
  try {
    const s = await api('state');
    if (s && s.phase) render(s);
  } catch (e) { /* 다음 바퀴 */ }
  ticking = false;
}

function clock() {
  const now = new Date();
  $('clock-time').textContent = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  $('clock-date').textContent = now.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' });
}

async function start() {
  tick();
  setInterval(tick, 1000);
  clock();
  setInterval(clock, 5000);
  const setup = await api('setup_qr');
  if (typeof setup === 'string') $('setup-qr').innerHTML = setup;      // 이 앱이 만든 SVG(Qr.kt)
}
start();
