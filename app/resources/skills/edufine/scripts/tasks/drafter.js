/**
 * 공용서식 목록에서 서식 이름으로 기안기(WXSClient)를 연다. 저장·상신은 하지 않는다.
 *   공용서식 화면의 fncFormDraft(formId, 분류, 이름) 링크를 찾아 그대로 부르고,
 *   포털이 여는 wxsclient:// 주소를 가로채 WXSClient.exe 에 넘긴다(브라우저가 Chrome 이라 직접 못 연다).
 */
const { spawn } = require('child_process');
const fs = require('fs');
const K = require('../lib/portal.js');
const { config } = require('../lib/config.js');

/** 포털 컨텍스트의 wxsclient:// 요청을 WXSClient.exe 로 넘긴다 → 실행되면 resolve(true) */
function hookWxs(ctx, log, timeoutMs = 20000) {
  if (!fs.existsSync(config.wxsClient)) throw new Error(`WXSClient.exe 가 없음: ${config.wxsClient} (에듀파인 기안기 설치 확인, config.json 의 wxsClient)`);
  let done = false, resolve;
  const p = new Promise(r => { resolve = r; });
  const onReq = r => {
    const u = r.url();
    if (u.startsWith('wxsclient://') && !done) {
      done = true; const c = spawn(config.wxsClient, [u], { detached: true, stdio: 'ignore' }); c.unref();
      log('기안기 실행 pid=' + c.pid); resolve(true);
    }
  };
  ctx.on('request', onReq); for (const pg of ctx.pages()) pg.on('request', onReq); ctx.on('page', pg => pg.on('request', onReq));
  setTimeout(() => resolve(done), timeoutMs);
  return p;
}

async function listForms(ctx) {
  const p = await ctx.newPage(); K.autoDialog(p, []);
  try {
    await K.openScreen(p, '공용서식');
    return await p.evaluate(() => [...document.querySelectorAll('[onclick*="fncFormDraft"]')].map(a => {
      const m = (a.getAttribute('onclick') || '').match(/fncFormDraft\('([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'/);
      return m ? { formId: m[1], 분류: m[2], 이름: m[3] } : null;
    }).filter(Boolean));
  } finally { await p.close().catch(() => { }); }
}

async function openDrafter(ctx, formName, log = console.log) {
  const p = await ctx.newPage(); K.autoDialog(p, []);
  try {
    await K.openScreen(p, '공용서식');
    const f = await p.evaluate(name => {
      const all = [...document.querySelectorAll('[onclick*="fncFormDraft"]')].map(a => (a.getAttribute('onclick') || '').match(/fncFormDraft\('([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'/)).filter(Boolean);
      const hit = all.find(m => m[3] === name) || all.find(m => m[3].includes(name));
      return hit ? { formId: hit[1], 분류: hit[2], 이름: hit[3] } : { 없음: all.map(m => m[3]) };
    }, formName);
    if (!f.formId) throw new Error(`공용서식에 '${formName}' 없음. 있는 것: ${f.없음.join(', ')}`);
    const launched = hookWxs(ctx, log);
    await p.evaluate(f => fncFormDraft(f.formId, f.분류, f.이름), f);
    const ok = await launched;
    if (!ok) throw new Error('wxsclient 주소를 받지 못함');
    await new Promise(r => setTimeout(r, 6000));
    return f;
  } finally { await p.close().catch(() => { }); }
}

module.exports = { openDrafter, listForms, hookWxs };
