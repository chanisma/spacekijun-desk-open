// 스페이스기전 교실 — 화면은 1초마다 상태를 받아 그린다(app/classroom.py Api.state).
'use strict';

const $ = (id) => document.getElementById(id);
const views = ['qr', 'offline'];
let lastQr = '';

const api = () => window.pywebview && window.pywebview.api;
const mmss = (s) => {
  if (s == null) return '--:--';
  const v = Math.max(0, s);
  return `${String(Math.floor(v / 60)).padStart(2, '0')}:${String(v % 60).padStart(2, '0')}`;
};

// 겹창 — <dialog>(showModal) 대신 보통 div. 전자칠판 터치에서 <dialog> 안 단추가 눌리지 않았다(2026-10-14)
function openModal(id) {
  $(id).hidden = false;
  const first = $(id).querySelector('input:not([type=checkbox]), button');
  if (first) first.focus();
}
function closeModal(id) { $(id).hidden = true; }
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  for (const id of ['quit-dialog', 'settings']) if (!$(id).hidden) { closeModal(id); break; }
});
// 바깥(어두운 곳)을 누르면 닫는다
for (const id of ['settings', 'quit-dialog']) {
  $(id).addEventListener('click', (e) => { if (e.target === $(id)) closeModal(id); });
}

function show(view) {
  for (const v of views) $(`view-${v}`).hidden = v !== view;
}

function render(s) {
  // 수업 중·정리 중에는 이 창이 숨는다(독이 대신 뜬다)
  const phase = s.phase === 'offline' ? 'offline' : 'qr';
  show(phase);
  if (phase === 'qr') {
    $('device-name').textContent = s.device;
    // 쉬는 중(밤·주말 — 서버를 부르지 않는다): QR 대신 단추. 이 PC 를 만지기만 해도 곧 깨어난다
    const sleeping = s.phase === 'sleep';
    $('qr').hidden = sleeping;
    $('wake').hidden = !sleeping;
    if (sleeping) {
      lastQr = '';
      $('qr').innerHTML = '';
      $('qr-timer').textContent = '쉬는 중 — 화면을 누르면 연결 QR 이 나옵니다';
    }
    if (!sleeping && s.qr && s.qr !== lastQr) {
      lastQr = s.qr;
      $('qr').innerHTML = s.qr;          // 이 PC 의 파이썬이 만든 SVG(segno) — 바깥 내용이 아니다
    }
    if (!sleeping) $('qr-timer').textContent = s.qr_left != null ? `${mmss(s.qr_left)} 뒤 새 QR` : '';
    $('notice').hidden = !s.notice;
    $('notice').textContent = s.notice || '';
  } else if (phase === 'offline') {
    $('offline-text').textContent = s.error || '서버에 연결하는 중입니다.';
  }
}

async function tick() {
  try {
    const s = await api()?.state();
    if (s) render(s);
  } catch { /* 다음 바퀴 */ }
  $('clock').textContent = new Date().toLocaleString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit' });
}

$('wake').addEventListener('click', () => api()?.wake());

$('open-settings').addEventListener('click', async () => {
  const s = await api()?.settings();
  if (!s) return;
  $('name-input').value = s.device_name;
  $('settings-path').textContent = s.settings_path;
  $('app-version').textContent = s.version || '';
  showUpdate(s.update_ready, s.can_update === false ? '이 실행 방식에서는 업데이트를 할 수 없습니다.' : '');
  $('autostart').checked = !!s.autostart;
  $('autostart').disabled = !!s.autostart_managed;
  $('autostart-note').textContent = s.autostart_managed ? '(학교가 이 PC 에 걸어 두었습니다)' : '(교실 PC 는 켜 두는 것을 권합니다)';
  openModal('settings');
});
$('save-name').addEventListener('click', async () => {
  const name = $('name-input').value.trim();
  if (!name) return;
  await api()?.save_name(name);
  closeModal('settings');
});

$('autostart').addEventListener('change', async () => {
  const r = await api()?.set_autostart($('autostart').checked);
  if (r && !r.ok) { $('autostart').checked = !$('autostart').checked; alertLine(r.error); }
});
function alertLine(text) {
  $('notice').hidden = !text;
  $('notice').textContent = text || '';
}

// 새 판 — 손으로 확인하고 바로 바꾸기(2026-10-14). 바꾸면 프로그램이 닫혔다가 새 판으로 다시 켜진다
function showUpdate(ready, error) {
  const note = $('update-note');
  $('update-install').hidden = !ready;
  $('update-check').hidden = !!ready;
  if (error) { note.textContent = error; note.className = 'err'; return; }
  note.textContent = ready ? `새 판 ${ready} 을 받아 두었습니다. [지금 바꾸기]를 누르면 잠깐 닫혔다가 다시 켜집니다.`
    : '새 판은 30분마다 확인해 수업이 없을 때 바꿉니다.';
  note.className = ready ? 'ok' : '';
}
$('update-check').addEventListener('click', async () => {
  const b = $('update-check');
  b.disabled = true;
  b.textContent = '확인하는 중…';
  const r = await api()?.check_update();
  b.disabled = false;
  b.textContent = '새 판 확인';
  if (!r) return;
  if (!r.ok) { showUpdate(null, r.error); return; }
  if (r.version) showUpdate(r.version, '');
  else { $('update-note').textContent = '지금이 가장 새 판입니다.'; $('update-note').className = 'ok'; }
});
$('update-install').addEventListener('click', async () => {
  const b = $('update-install');
  b.disabled = true;
  b.textContent = '바꾸는 중…';
  const r = await api()?.install_update();
  if (r && !r.ok) { b.disabled = false; b.textContent = '지금 바꾸기'; showUpdate(null, r.error); }
});

$('quit-open').addEventListener('click', () => { closeModal('settings'); openModal('quit-dialog'); });
$('quit-yes').addEventListener('click', () => { closeModal('quit-dialog'); api()?.quit_app(); });
$('quit-no').addEventListener('click', () => closeModal('quit-dialog'));
$('settings-close').addEventListener('click', () => closeModal('settings'));

window.addEventListener('pywebviewready', async () => {
  tick();
  setInterval(tick, 1000);
  const setup = await api()?.setup_qr();
  if (setup) $('setup-qr').innerHTML = setup;      // 이 PC 의 파이썬이 만든 SVG(segno)
});
