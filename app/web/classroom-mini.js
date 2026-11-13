// 스페이스기전 교실 — 작은 위젯(QR 창을 내렸을 때). 2초마다 상태를 받아 QR 을 바꿔 그린다(app/classroom.py Api.state).
'use strict';

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview && window.pywebview.api;
let lastQr = '';

const mmss = (s) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.max(0, s) % 60).padStart(2, '0')}`;

function render(s) {
  $('device').textContent = s.device || '';
  if (s.phase === 'qr' && s.qr) {
    if (s.qr !== lastQr) {
      lastQr = s.qr;
      $('qr').classList.remove('wait');
      $('qr').innerHTML = s.qr;          // 이 PC 의 파이썬이 만든 SVG(segno) — 바깥 내용이 아니다
    }
    $('line').textContent = s.qr_left != null ? `휴대폰으로 찍어 연결 · ${mmss(s.qr_left)}` : '휴대폰으로 찍어 연결';
  } else if (s.phase === 'sleep') {
    lastQr = '';
    $('qr').classList.add('wait');
    $('qr').textContent = '쉬는 중';
    $('line').textContent = '누르면 연결 QR 이 나옵니다';
  } else {
    lastQr = '';
    $('qr').classList.add('wait');
    $('qr').textContent = '연결 기다리는 중';
    $('line').textContent = s.phase === 'offline' ? '서버에 연결하는 중입니다' : '수업을 펼치는 중입니다';
  }
}

async function tick() {
  try {
    const s = await api()?.state();
    if (s) render(s);
  } catch { /* 다음 바퀴 */ }
}

const open = () => api()?.restore_main();
$('open').addEventListener('click', open);
$('qr').addEventListener('dblclick', open);

window.addEventListener('pywebviewready', () => {
  tick();
  setInterval(tick, 2000);
});
