// 스페이스기전 교실 — 수업 중 독. 1초마다 상태를 받아 그린다(app/classroom.py Api.state).
// 아무것도 저절로 열지 않는다 — 누르면 연다(2026-10-13 사용자 결정).
'use strict';

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview && window.pywebview.api;
const mmss = (s) => {
  if (s == null) return '--:--';
  const v = Math.max(0, s);
  return `${String(Math.floor(v / 60)).padStart(2, '0')}:${String(v % 60).padStart(2, '0')}`;
};

const GLYPH = {
  drive: '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2.5h6.5A2.5 2.5 0 0 1 21 10v7.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5Z"/>',
  file: '<path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 3.6 5.4 3.6 8.5s-1.1 5.9-3.6 8.5c-2.5-2.6-3.6-5.4-3.6-8.5s1.1-5.9 3.6-8.5Z"/>',
  planet: '<circle cx="12" cy="12" r="5.5"/><path d="M3.5 15.5c-1.8 2.4 4.2 1.6 9.6-1.5s9-6.8 7-7.6c-.9-.3-2.4.1-4.1.9"/>',
  board: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4M7 9l3 3 5-5"/>',
  note: '<path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 15h7M9 7h4"/>',
  paint: '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.6-1 1.1-1.9-.6-1.1.1-2.6 1.4-2.6H17a4 4 0 0 0 4-4c0-5-4-9.5-9-9.5Z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7.5" r="1"/>',
  calc: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 12h.01M12 12h.01M16 12h.01M8 16h.01M12 16h.01M16 16h.01"/>',
  snip: '<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3.2"/>',
  keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M9 10h.01M12 10h.01M15 10h.01M18 10h.01M7 14h10"/>',
  app: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
};
// 프로그램 키(웹 CLASSROOM_PROGRAMS) → 독 모양
const PROGRAM_LOOK = {
  powerpoint: { text: 'P', tone: 'orange' }, word: { text: 'W', tone: 'blue' }, excel: { text: 'X', tone: 'green' },
  hwp: { text: '한', tone: 'sky' }, whiteboard: { glyph: 'board', tone: 'teal' }, notepad: { glyph: 'note', tone: 'slate' },
  paint: { glyph: 'paint', tone: 'pink' }, calculator: { glyph: 'calc', tone: 'graphite' },
  snipping: { glyph: 'snip', tone: 'violet' }, osk: { glyph: 'keyboard', tone: 'silver' },
};

// 세팅의 구글 앱 타일(웹사이트 항목 + app) — 키는 core/classroom_setup.py GOOGLE_APPS
const GOOGLE_LOOK = {
  classroom: { text: 'C', tone: 'green' }, drive: { glyph: 'drive', tone: 'blue' }, docs: { text: '문', tone: 'blue' },
  sheets: { text: '시', tone: 'emerald' }, slides: { text: '슬', tone: 'amber' }, forms: { text: '설', tone: 'violet' },
  calendar: { text: '31', tone: 'sky' }, meet: { text: 'M', tone: 'teal' }, gmail: { text: 'M', tone: 'red' },
  keep: { text: 'K', tone: 'yellow' }, sites: { text: 'S', tone: 'indigo' }, youtube: { text: '▶', tone: 'red' },
};

function look(item) {
  if (item.kind === 'drive') return item.folder ? { glyph: 'drive', tone: 'amber' } : { glyph: 'file', tone: 'blue' };
  if (item.kind === 'url' && item.app) return GOOGLE_LOOK[item.app] || { text: 'G', tone: 'paper' };
  if (item.kind === 'url') return { glyph: 'globe', tone: 'cyan' };
  if (item.kind === 'space') return { glyph: 'planet', tone: 'indigo' };
  if (item.kind === 'program') return PROGRAM_LOOK[item.program] || { glyph: 'app', tone: 'slate' };
  return { glyph: 'app', tone: 'slate' };
}

function tile({ label, look: lk, title, state, badge, badgeErr, badgeOk, off, onClick, onContext }) {
  const li = document.createElement('li');
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `tile${state ? ` ${state}` : ''}${off ? ' off' : ''}`;
  btn.title = title || label;
  const glyph = document.createElement('span');
  glyph.className = `glyph tone-${lk.tone}`;
  if (lk.glyph) glyph.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${GLYPH[lk.glyph]}</svg>`;
  else glyph.textContent = lk.text;
  // 실제 아이콘(구글 공식·설치된 프로그램·파비콘·드라이브 형식) — 못 받으면 위의 글자 타일 그대로
  if (lk.img) {
    const img = new Image();
    img.alt = '';
    img.onload = () => { glyph.className = 'glyph img'; glyph.replaceChildren(img, ...glyph.querySelectorAll('.badge')); };
    img.src = lk.img;
  }
  if (badge) {
    const b = document.createElement('span');
    b.className = `badge${badgeErr ? ' err' : badgeOk ? ' ok' : ''}`;
    b.textContent = badge;
    glyph.append(b);
  }
  const name = document.createElement('span');
  name.className = 'label';
  name.textContent = label;
  btn.append(glyph, name);
  btn.addEventListener('click', onClick);
  if (onContext) btn.addEventListener('contextmenu', (e) => { e.preventDefault(); onContext(); });
  li.append(btn);
  return li;
}

let lastKey = '';
let iconsVersion = -1;
let icons = [];
// 알림은 독 위에 따로 뜨는 창으로 — 독(높이 112) 안에 쓰면 잘린다(2026-10-14 사용자 보고)
const say = (text, error = false) => { if (text) api()?.notify(text, error); };

function render(s) {
  const session = s.session;
  $('ending').hidden = s.phase !== 'ending';
  if (s.phase === 'ending') $('progress').textContent = s.progress || '정리하는 중입니다.';
  if (!session) return;
  $('teacher').textContent = session.teacher ? `${session.teacher} 선생님` : '수업 중';
  $('title').textContent = [session.title, session.section].filter(Boolean).join(' · ');
  $('remaining').textContent = mmss(s.remaining);
  $('extend').classList.toggle('warn', !!s.warn);

  const drive = session.drive || {};
  const pending = (session.files || []).filter((f) => f.state === 'pending' || f.state === 'uploading').length;
  const failed = (session.files || []).filter((f) => f.state === 'failed').length;
  const google = session.google || {};
  if (session.icons_version !== iconsVersion) {
    iconsVersion = session.icons_version;
    api()?.item_icons().then((list) => { icons = list || []; lastKey = ''; });
  }
  const key = JSON.stringify([session.items, drive.connected, drive.ever, Math.floor((drive.left || 0) / 60) < 10, pending, failed, google, icons]);
  if (key !== lastKey) {
    lastKey = key;
    const tiles = [];
    // 구글 — 누르면 구글 앱 창(클래스룸·문서·설문지…·로그인·로그인 지우기). 보관(A+) 중이면 다음 수업에도 로그인된 채
    tiles.push(tile({
      label: '구글',
      look: { text: 'G', tone: 'paper', img: 'icons/google/google.png' },
      title: google.restored ? '구글 앱 — 보관해 둔 로그인으로 열립니다' : '구글 앱 — 클래스룸·문서·설문지 등, 로그인',
      badge: google.restored ? '✓' : '', badgeOk: true,
      onClick: () => api()?.open_google_launcher(),
    }));
    if (drive.ever || drive.connected) {
      const soon = drive.connected && drive.left < 600;
      tiles.push(tile({
        label: drive.connected ? '내 드라이브' : '드라이브 연결',
        look: { glyph: 'drive', tone: 'blue', img: 'icons/google/drive.png' },
        title: drive.connected ? `구글 드라이브 — ${Math.max(0, Math.floor(drive.left / 60))}분 남음` : '드라이브 연결이 끝났습니다 — 눌러서 QR 로 다시 연결',
        off: !drive.connected,
        badge: failed ? '!' : pending ? '↑' : soon ? `${Math.max(0, Math.floor(drive.left / 60))}분` : '',
        badgeErr: failed > 0,
        onClick: () => api()?.open_drive('root', '내 드라이브'),
      }));
    }
    session.items.forEach((item, index) => {
      tiles.push(tile({
        label: item.name, look: { ...look(item), img: icons[index] || null }, state: item.state,
        title: item.state === 'failed' ? `${item.name} — ${item.message}` : item.name,
        badge: item.state === 'failed' ? '!' : '', badgeErr: true,
        onClick: async () => {
          const r = await api()?.open_item(index);
          if (r && r.ok === false) say(r.error, true);
        },
      }));
    });
    $('items').replaceChildren(...tiles);
  }

  // 왼쪽 아래 한 줄 — 짧은 상태만(긴 글은 알림 창으로)
  const off = drive.ever && !drive.connected;
  $('line').textContent = off ? '드라이브 연결 끝 — 다시 연결' : '';
  $('line').classList.toggle('error', off);
}

async function tick() {
  try {
    const s = await api()?.state();
    if (s) render(s);
  } catch { /* 다음 바퀴 */ }
}

$('extend').addEventListener('click', async () => {
  $('extend').disabled = true;
  try {
    const r = await api()?.extend(10);
    say(r && r.ok ? '10분 연장했습니다.' : (r && r.error) || '연장하지 못했습니다.', !(r && r.ok));
  } finally { $('extend').disabled = false; }
});
$('finish').addEventListener('click', async () => {
  const yes = await api()?.ask({
    title: '수업을 끝낼까요?', ok: '수업 끝', danger: true,
    body: '열린 창과 프로그램을 닫고(고친 문서는 저장할지 묻습니다), 고친 드라이브 파일을 올린 뒤 이 PC 의 사본과 로그인을 지웁니다.\n\n'
      + '«컴퓨터로 복사»·«이 PC 에 저장» 한 파일은 지우지 않습니다. 구글 로그인 보관을 켰다면 암호화해 남깁니다.',
  });
  if (yes) api()?.finish();
});

window.addEventListener('pywebviewready', () => { tick(); setInterval(tick, 1000); });
