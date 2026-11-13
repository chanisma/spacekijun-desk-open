/**
 * NEIS 를 한 번만 로그인해 열어 두고 여러 명령이 그 창(CDP)에 붙어 쓴다.
 *   node neis.js session start    열어 두기(백그라운드로) — 5분마다 확인, 로그아웃(약 50분)되면 다시 로그인
 *   node neis.js session status | stop
 * ⚠ 붙은 쪽에서 browser.close() 를 부르지 않는다 — 실제 브라우저가 닫힐 수 있다. 명령은 끝날 때 프로세스를 끝낸다.
 * ⚠ page.reload() 금지 — NEIS 는 언로드 때 세션을 파기해 로그아웃된다.
 */
const fs = require('fs');
const http = require('http');
const { config, paths, credentials, host } = require('./config.js');
const { loginNeis, neisState, launchPortalBrowser } = require('./cert-login.js');
const PORT = config.cdpPort;
const pw = () => require('playwright');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = () => new Date().toTimeString().slice(0, 8);

function version() {
  return new Promise(res => {
    const req = http.get({ host: '127.0.0.1', port: PORT, path: '/json/version', timeout: 1500 }, r => {
      let b = ''; r.on('data', d => b += d); r.on('end', () => { try { res(JSON.parse(b)); } catch (e) { res(null); } });
    });
    req.on('error', () => res(null));
    req.on('timeout', () => { req.destroy(); res(null); });
  });
}

async function running() {
  const v = await version();
  if (!v) return false;
  const m = fs.existsSync(paths.sessionMark) ? JSON.parse(fs.readFileSync(paths.sessionMark, 'utf8')) : null;
  if (!m || m.ws !== v.webSocketDebuggerUrl) throw new Error(`포트 ${PORT}에 다른 프로그램(${v.Browser})이 떠 있음 — config.json 의 cdpPort 를 바꾸세요`);
  return true;
}

const neisPage = ctx => ctx.pages().find(p => p.url().includes(host())) || ctx.pages()[0];

async function ensureLogin(page) {
  let st = await neisState(page).catch(() => ({ ok: false }));
  if (!st.ok || /Logout|logout/.test(page.url())) {
    const c = credentials();
    st = await loginNeis(page, { certPassword: c.certPassword, certMatch: c.certMatch || null, baseUrl: config.baseUrl });
  }
  return st;
}

/** 열린 세션에 붙는다 → { ctx, page }. 없으면 먼저 session start 를 하라고 알린다. */
async function attach() {
  if (!await running()) throw new Error('NEIS 세션이 열려 있지 않습니다. 먼저 `node neis.js session start` 를 백그라운드로 실행하세요.');
  const browser = await pw().chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  const ctx = browser.contexts()[0];
  const page = neisPage(ctx);
  const st = await neisState(page).catch(() => ({ ok: false }));
  if (!st.ok) await ensureLogin(page);
  return { browser, ctx, page };
}

async function keep() {
  if (await running()) { console.log('이미 열려 있음 — 그대로 씀'); return; }
  if (await version()) throw new Error(`포트 ${PORT}을 다른 프로그램이 쓰는 중`);
  const ctx = await launchPortalBrowser({
    userDataDir: paths.profile, playwright: pw(), channel: config.browserChannel || undefined, viewport: null,
    extraArgs: ['--start-maximized', `--remote-debugging-port=${PORT}`]
  });
  const v = await version();
  fs.mkdirSync(paths.home, { recursive: true });
  fs.writeFileSync(paths.sessionMark, JSON.stringify({ ws: v && v.webSocketDebuggerUrl, pid: process.pid, 시작: new Date().toISOString() }), 'utf8');
  const page = ctx.pages()[0] || await ctx.newPage();
  let st = { ok: false };
  try { st = await ensureLogin(page); } catch (e) { console.log(`[${now()}] 로그인 실패: ${e.message}`); }
  console.log(`[${now()}] 로그인 ${st.ok ? 'OK' : '실패'} ${st.user || ''} — 열어 둠 (포트 ${PORT})`);
  let closed = false;
  ctx.on('close', () => { closed = true; });
  while (!closed) {
    for (let t = 0; t < 60 && !closed; t++) await sleep(5000);      // 5분마다
    if (closed) break;
    try {
      const p = neisPage(ctx);
      const s = await neisState(p).catch(() => ({ ok: false }));
      if (!s.ok || /Logout|logout/.test(p.url())) { const r = await ensureLogin(p); console.log(`[${now()}] 다시 로그인 ${r.ok ? 'OK' : '실패'}`); }
    } catch (e) { console.log(`[${now()}] 점검 오류: ${e.message}`); }
  }
  try { fs.unlinkSync(paths.sessionMark); } catch (e) { }
  console.log(`[${now()}] 창이 닫혀 종료`);
}

async function status() {
  if (!await running()) return { 열림: false };
  const browser = await pw().chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  const st = await neisState(neisPage(browser.contexts()[0])).catch(e => ({ ok: false, err: e.message }));
  return { 열림: true, ...st };
}

async function stop() {
  if (!await running()) return '열려 있지 않음';
  const browser = await pw().chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  for (const p of browser.contexts()[0].pages()) await p.close().catch(() => { });
  await browser.close().catch(() => { });
  return '닫음';
}

module.exports = { attach, keep, status, stop, running, PORT };
