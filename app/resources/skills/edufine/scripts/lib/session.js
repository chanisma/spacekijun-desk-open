/**
 * K-에듀파인을 한 번만 로그인해 열어 두고 여러 작업이 그 창에 붙어 쓴다.
 *   node edufine.js session start    열어 두기(백그라운드로) — 20분마다 [연장], 로그아웃되면 다시 로그인
 *   node edufine.js session status   상태
 *   node edufine.js session stop     닫기
 * 다른 코드에서: const s = await require('./session.js').open(); ... await s.done();
 *   (열려 있으면 붙고, 없으면 새로 띄워 로그인 — 그 경우 done() 이 창을 닫는다)
 * ⚠ 같은 프로필은 브라우저 하나만 쓸 수 있다 — 반드시 open() 을 거친다.
 * ⚠ 열어 둔 창에 Nexacro 모달(공지 팝업 등)이 남아 있으면 [연장] 클릭이 막혀 세션이 끊길 수 있다 — 팝업은 쓰고 닫는다.
 */
const fs = require('fs');
const http = require('http');
const { config, paths, credentials, host } = require('./config.js');
const { loginKlef, klefState, extendKlefSession, launchPortalBrowser } = require('./cert-login.js');
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

/** 우리 세션이 떠 있나 — 포트가 응답하고, 표식 파일의 주소와 같아야 한다(다른 앱에 붙지 않도록) */
async function running() {
  const v = await version();
  if (!v) return false;
  const m = fs.existsSync(paths.sessionMark) ? JSON.parse(fs.readFileSync(paths.sessionMark, 'utf8')) : null;
  if (!m || m.ws !== v.webSocketDebuggerUrl) throw new Error(`포트 ${PORT}에 다른 프로그램(${v.Browser})이 떠 있음 — config.json 의 cdpPort 를 바꾸세요`);
  return true;
}

const portalOf = ctx => ctx.pages().find(p => p.url().includes(host() + '/keris_ui')) || ctx.pages()[0];

async function ensureLogin(page) {
  let st = await klefState(page).catch(() => ({ ok: false }));
  if (!st.ok) {
    const c = credentials();
    st = await loginKlef(page, { id: c.id, certPassword: c.certPassword, certMatch: c.certMatch || null, baseUrl: config.baseUrl });
  }
  return st;
}

const launch = extraArgs => launchPortalBrowser({ userDataDir: paths.profile, playwright: pw(), channel: config.browserChannel || undefined, extraArgs });

async function open() {
  if (await running()) {
    const browser = await pw().chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
    const ctx = browser.contexts()[0];
    const portal = portalOf(ctx);
    await ensureLogin(portal);
    return { ctx, portal, attached: true, done: async () => { await browser.close().catch(() => { }); } };
  }
  const ctx = await launch();
  const portal = ctx.pages()[0] || await ctx.newPage();
  await ensureLogin(portal);
  return { ctx, portal, attached: false, done: async () => { await ctx.close().catch(() => { }); } };
}

async function keep() {
  if (await running()) { console.log('이미 열려 있음 — 그대로 씀'); return; }
  if (await version()) throw new Error(`포트 ${PORT}을 다른 프로그램이 쓰는 중`);
  const ctx = await launch([`--remote-debugging-port=${PORT}`]);
  const v = await version();
  fs.mkdirSync(paths.home, { recursive: true });
  fs.writeFileSync(paths.sessionMark, JSON.stringify({ ws: v && v.webSocketDebuggerUrl, pid: process.pid, 시작: new Date().toISOString() }), 'utf8');
  const portal = ctx.pages()[0] || await ctx.newPage();
  const st = await ensureLogin(portal);
  console.log(`[${now()}] 로그인 ${st.ok ? 'OK' : '실패'} ${st.user || ''} — 열어 둠 (포트 ${PORT})`);
  let closed = false;
  ctx.on('close', () => { closed = true; });
  while (!closed) {
    for (let t = 0; t < 240 && !closed; t++) await sleep(5000);
    if (closed) break;
    try {
      const p = portalOf(ctx);
      const s = await klefState(p);
      if (s.ok) { await extendKlefSession(p); console.log(`[${now()}] 연장`); }
      else { const r = await ensureLogin(p); console.log(`[${now()}] 다시 로그인 ${r.ok ? 'OK' : '실패'}`); }
    } catch (e) { console.log(`[${now()}] 점검 오류: ${e.message}`); }
  }
  try { fs.unlinkSync(paths.sessionMark); } catch (e) { }
  console.log(`[${now()}] 창이 닫혀 종료`);
}

async function status() {
  if (!await running()) return { 열림: false };
  const browser = await pw().chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  try { const st = await klefState(portalOf(browser.contexts()[0])).catch(e => ({ ok: false, err: e.message })); return { 열림: true, ...st }; }
  finally { await browser.close().catch(() => { }); }
}

async function stop() {
  if (!await running()) return '열려 있지 않음';
  const browser = await pw().chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  for (const p of browser.contexts()[0].pages()) await p.close().catch(() => { });
  await browser.close().catch(() => { });
  return '닫음';
}

module.exports = { open, running, keep, status, stop, PORT };
