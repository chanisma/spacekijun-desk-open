// 휴대폰으로 구글 비밀번호 입력 창 — QR 을 띄우고 1.5초마다 묻는다. 받으면 이 PC 가 구글 로그인 칸에 넣는다(classroom.py).
'use strict';

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview && window.pywebview.api;
let timer = 0;
let busy = false;

function status(text, kind) {
  $('t-status').textContent = text;
  $('t-status').className = 'type-status' + (kind ? ' ' + kind : '');
}

async function start() {
  clearInterval(timer);
  $('t-retry').hidden = true;
  $('t-qr').innerHTML = '';
  status('QR 을 만드는 중…');
  const r = await api()?.type_start();
  if (!r || r.ok === false) { status((r && r.error) || 'QR 을 만들지 못했습니다.', 'err'); $('t-retry').hidden = false; return; }
  $('t-qr').innerHTML = r.qr;                 // 이 PC 의 파이썬이 만든 SVG(segno)
  status('휴대폰에서 보내기를 기다리는 중…');
  timer = setInterval(poll, 1500);
}

async function poll() {
  if (busy) return;
  busy = true;
  try {
    const r = await api()?.type_poll();
    if (!r) return;
    if (r.status === 'expired') {
      clearInterval(timer);
      $('t-qr').innerHTML = '';
      status('QR 이 만료됐습니다. 새 QR 을 만들어 다시 찍어 주세요.', 'err');
      $('t-retry').hidden = false;
    } else if (r.status === 'filled') {
      clearInterval(timer);
      $('t-qr').innerHTML = '';
      status(r.manual ? '비밀번호를 넣었습니다. 구글 로그인 창에서 [다음]을 눌러 주세요.'
        : '구글 로그인 칸에 넣었습니다. 휴대폰에 구글 확인 알림이 오면 «예»를 누르세요.', 'ok');
      setTimeout(() => api()?.close_popup('type'), 6000);
    } else if (r.status === 'error') {
      clearInterval(timer);
      status(r.error || '넣지 못했습니다.', 'err');
      $('t-retry').hidden = false;
    }
  } finally {
    busy = false;
  }
}

$('t-close').addEventListener('click', () => { clearInterval(timer); api()?.type_cancel(); });
$('t-retry').addEventListener('click', start);
window.addEventListener('pywebviewready', start);
