// 스페이스기전 교실 — 독 위에 따로 뜨는 작은 창. body[data-mode] = toast(알림) · dialog(확인) · google(구글 앱)
// 독은 높이가 112 라 그 안에 그린 confirm·알림 글이 잘렸다(2026-10-14 사용자 보고) — 그래서 창으로 뺐다.
'use strict';

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview && window.pywebview.api;
const mode = document.body.dataset.mode;

// 구글 앱 모양 — 키는 core/classroom_setup.py GOOGLE_APPS
const APP_LOOK = {
  classroom: ['C', '#188038'], drive: ['D', '#1a73e8'], docs: ['문', '#4285f4'], sheets: ['시', '#0f9d58'],
  slides: ['슬', '#f4b400'], forms: ['설', '#7248b9'], calendar: ['31', '#1967d2'], meet: ['M', '#00897b'],
  gmail: ['M', '#ea4335'], keep: ['K', '#f6bf26'], sites: ['S', '#3f51b5'], youtube: ['▶', '#ff0000'],
};

async function toast() {
  const t = await api()?.popup('toast');
  if (!t) return;
  $('toast').classList.toggle('error', !!t.error);
  $('toast-text').textContent = t.text;
}

async function dialog() {
  const d = await api()?.popup('dialog');
  if (!d) return;
  $('d-title').textContent = d.title;
  $('d-body').textContent = d.body;
  $('d-ok').textContent = d.ok;
  $('d-cancel').textContent = d.cancel;
  $('d-ok').className = `btn ${d.danger ? 'danger' : 'primary'}`;
  $('d-ok').onclick = () => api()?.answer(d.token, true);
  $('d-cancel').onclick = () => api()?.answer(d.token, false);
  document.onkeydown = (e) => { if (e.key === 'Escape') api()?.answer(d.token, false); };
  $('d-cancel').focus();
}

// 구글 로그인 상태 한 줄(2026-10-14 사용자 요청 — 로그인됐는지 알 수 없었다)
const LOGIN_TEXT = {
  restored: ['ok', '보관해 둔 구글 로그인을 불러왔습니다.'],
  restored_empty: ['warn', '보관본에 구글 로그인이 없었습니다. 다시 로그인해 주세요.'],
  cleared: ['warn', '로그인을 지웠습니다. 다시 로그인하면 수업이 끝날 때 보관합니다.'],
  phone: ['ok', '휴대폰으로 비밀번호를 넣었습니다. 구글 확인을 마치면 로그인됩니다.'],
  none: ['', '구글에 로그인되어 있지 않습니다.'],
};
function loginStatus(g, email) {
  const el = $('g-status');
  let [kind, text] = LOGIN_TEXT[g.login] || LOGIN_TEXT.none;
  if (email === '') {
    kind = 'warn';
    text = '구글에 로그인되어 있지 않습니다. [휴대폰으로 로그인]으로 로그인하세요.';
  } else if (email) {
    const same = !g.email || email === g.email.toLowerCase();
    kind = same ? 'ok' : 'warn';
    text = same ? `✓ 로그인됨 · ${email}` : `다른 계정으로 로그인됨 · ${email}`;
  }
  el.textContent = text;
  el.className = 'g-status' + (kind ? ' ' + kind : '');
  el.hidden = false;
}

async function google() {
  const s = await api()?.state();
  const g = s?.session?.google;
  if (!g) return;
  $('g-who').textContent = g.email || '';
  loginStatus(g, null);
  $('g-note').textContent = g.kept
    ? '수업이 끝나면 이 PC 에 암호화해 보관합니다.'
    : '보관하지 않습니다. 수업이 끝나면 지웁니다.';
  // 수업용 Edge 앞 탭에 구글 계정이 보이면 «로그인됨» — 접근성으로 읽어 1초쯤 걸린다
  api()?.google_status().then((r) => { if (r && r.ok && r.email != null) loginStatus(g, r.email); });
  $('g-forget').hidden = !g.saved;           // 보관 모드여도 아직 이 PC 에 남긴 로그인이 없으면 숨긴다
  if (!$('apps').children.length) {
    $('apps').replaceChildren(...g.apps.map((app) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'app';
      const [text, color] = APP_LOOK[app.key] || [app.label[0], '#64748b'];
      const ic = document.createElement('span');
      ic.className = 'ic';
      ic.style.background = color;
      ic.textContent = text;
      const img = new Image();                 // 구글 공식 아이콘(web/icons/google) — 못 읽으면 글자 타일
      img.alt = '';
      img.onload = () => { ic.style.background = 'none'; ic.replaceChildren(img); };
      img.src = `icons/google/${app.key}.png`;
      const label = document.createElement('span');
      label.textContent = app.label;
      b.append(ic, label);
      b.addEventListener('click', async () => {
        const r = await api()?.open_google_app(app.key);
        if (r && r.ok === false) api()?.notify(r.error, true);
      });
      return b;
    }));
  }
}

window.refresh = () => ({ toast, dialog, google }[mode] || (() => {}))();

if (mode === 'toast') $('toast-close').addEventListener('click', () => api()?.close_popup('toast'));
if (mode === 'google') {
  $('g-close').addEventListener('click', () => api()?.close_popup('google'));
  document.querySelectorAll('[data-tool]').forEach((b) => b.addEventListener('click', async () => {
    const r = await api()?.open_gtools(b.dataset.tool);
    if (r && r.ok === false) api()?.notify(r.error, true);
  }));
  // 휴대폰으로 구글 비밀번호 입력 — 칠판에서 비밀번호를 치지 않게(2026-10-14)
  $('g-phone').addEventListener('click', async () => {
    const r = await api()?.open_type();
    if (r && r.ok === false) api()?.notify(r.error, true);
  });
  $('g-login').addEventListener('click', async () => {
    const r = await api()?.open_google();
    if (r && r.ok === false) api()?.notify(r.error, true);
    else api()?.close_popup('google');
  });
  $('g-forget').addEventListener('click', async () => {
    const yes = await api()?.ask({
      title: '이 PC 의 구글 로그인 지우기', danger: true, ok: '지우기',
      body: '열린 구글 창이 닫히고, 지금 로그인과 이 PC 에 보관한 로그인을 지웁니다.\n다시 로그인하면 수업이 끝날 때 새로 보관합니다.',
    });
    if (!yes) return;
    const r = await api()?.forget_google();
    api()?.notify(r && r.ok ? '이 PC 의 구글 로그인을 지웠습니다.' : (r && r.error) || '지우지 못했습니다.', !(r && r.ok));
    google();
  });
}
window.addEventListener('pywebviewready', () => window.refresh());
