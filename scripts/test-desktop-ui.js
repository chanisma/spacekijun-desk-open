// Isolated UI checks: all Python calls are mocked, no real messages or accounts.
const { chromium } = require('playwright');
const { pathToFileURL } = require('url');
const path = require('path');
const os = require('os');
const assert = require('assert');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: {width:1180, height:820}, deviceScaleFactor:1 });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => {
      window.testCalls = [];
      window.testFail = false;
      window.testRows = [];
      const state = {user:null, credentials:false, watching:false, summary:true, body:true, logs:[{time:'09:00:00',text:'데스크가 준비되었습니다.'}]};
      window.pywebview = {api:{call:async (action,payload) => {
        window.testCalls.push({action,payload});
        if (action === 'state') return {ok:true,data:state};
        if (action === 'credential_settings') return {ok:true,data:{user:'existing-id',cert_name:'기존이름',has_password:true,riro_id:'saved-riro',has_riro:true,aiep_id:'saved-aiep',has_aiep:true}};
        if (action === 'inbox') return window.testFail ? {ok:false,error:'연결 실패'} : {ok:true,data:window.testRows};
        if (action === 'roster' || action === 'sync_roster') return {ok:true,data:[{display:'보건실',note:'테스트 교직원',text:'보건실 테스트 교직원'}]};
        if (action === 'options') {state.summary = payload.summary; state.body = payload.body;}
        if (action === 'startup') state.startup = payload.enabled;
        if (action === 'prepare_cm') return {ok:true,data:{needs_restart:!payload.restart,message:payload.restart?'연동 준비 완료':'다시 실행 필요'}};
        if (action === 'auth') {state.user = payload.logout ? null : 'teacher@example.test'; state.watching = !!state.user;}
        if (action === 'save_credentials') state.credentials = true;
        if (action === 'save_riro') return {ok:true,data:'리로스쿨 정보를 저장했습니다.'};
        if (action === 'save_aiep') return {ok:true,data:'AIEP 정보를 저장했습니다.'};
        if (action === 'disconnect') return {ok:true,data:'연결을 해제했습니다.'};
        return {ok:true,data:'작업을 완료했습니다.'};
      }}};
      window.addEventListener('DOMContentLoaded', () => window.dispatchEvent(new Event('pywebviewready')));
    });
    await page.goto(pathToFileURL(path.resolve('app/web/index.html')).href);
    await page.waitForFunction(() => document.getElementById('side-status').textContent === '데스크 연결됨');
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({path:path.join(os.tmpdir(),'spacekijun-web-home.png'),fullPage:true,animations:'disabled'});
    await page.locator('[data-action="portal"][data-target="neis"]').click();
    assert(await page.evaluate(() => testCalls.some(x => x.action === 'portal' && x.payload.target === 'neis')));
    await page.locator('[data-action="portal"][data-target="klef"]').click();
    assert(await page.evaluate(() => testCalls.some(x => x.action === 'portal' && x.payload.target === 'klef')));
    await page.locator('.nav[data-page="inbox"]').click();
    await page.getByText('아직 표시할 쪽지가 없어요').waitFor();
    await page.evaluate(() => {testRows = [{who:'테스트 교직원',kind:'받음',status:'안읽음',body:'<img src=x onerror="window.injected=true">',time:'09-10 09:00',when:'2026/09/10 09:00'}];});
    await page.locator('#refresh-inbox').click();
    await page.locator('.message').click();
    assert((await page.locator('#detail-body').textContent()).includes('<img'));
    assert.strictEqual(await page.evaluate(() => !!window.injected), false);
    await page.evaluate(() => {testFail = true;});
    await page.locator('#refresh-inbox').click();
    await page.getByText('쪽지를 불러오지 못했습니다.').waitFor();
    await page.locator('.nav[data-page="roster"]').click();
    await page.locator('#roster-rows tr').waitFor();
    await page.locator('#search').fill('없는이름');
    await page.getByText('검색 결과가 없습니다. 다른 이름으로 검색해 주세요.').waitFor();
    await page.locator('#search').fill('보건실');
    assert.strictEqual(await page.locator('#roster-rows tr').count(),1);
    await page.locator('#alias-form [name="source"]').fill('보건실');
    await page.locator('#alias-form [name="target"]').fill('테스트 교직원');
    await page.locator('#alias-form button').click();
    assert(await page.evaluate(() => testCalls.some(x => x.action === 'alias')));
    await page.locator('.nav[data-page="settings"]').click();
    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('#prepare-cm').click();
    await page.waitForFunction(() => !document.getElementById('prepare-cm').disabled);
    assert(!(await page.evaluate(() => testCalls.some(x => x.action === 'prepare_cm' && x.payload.restart))));
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#prepare-cm').click();
    await page.waitForFunction(() => testCalls.some(x => x.action === 'prepare_cm' && x.payload.restart));
    await page.locator('#windows-startup').check();
    await page.waitForFunction(() => !document.getElementById('windows-startup').disabled);
    assert(await page.locator('#windows-startup').isChecked());
    await page.locator('#windows-startup').uncheck();
    await page.waitForFunction(() => !document.getElementById('windows-startup').disabled);
    await page.waitForFunction(() => document.querySelector('[name="cert_name"]').value === '기존이름');
    await page.locator('#credentials-form [name="user"]').fill('test-only');
    await page.locator('#credentials-form [name="cert_name"]').fill('홍길동');
    await page.locator('#credentials-form [name="password"]').fill('test-password');
    await page.locator('#credentials-form button[type=submit]').click();
    await page.waitForFunction(() => document.querySelector('#credentials-form [name="password"]').value === '');
    assert.strictEqual(await page.locator('[name="cert_name"]').inputValue(), '홍길동');
    await page.locator('#credentials-form button[type=submit]').click();
    assert(await page.evaluate(() => testCalls.some(x => x.action === 'save_credentials' && x.payload.cert_name === '홍길동' && x.payload.password === '')));

    // 리로스쿨은 인증서를 쓰지 않아 칸이 따로다. 저장된 비밀번호는 화면에 오지 않는다.
    assert(await page.locator('#riro-form [name="riro_id"]').inputValue() === 'saved-riro');
    assert(await page.locator('#riro-badge').textContent() === '저장됨');
    assert(await page.evaluate(() =>
        document.querySelector('#riro-form [name="riro_password"]').value === ''));
    await page.locator('#riro-form [name="riro_password"]').fill('test-only-riro');
    await page.locator('#riro-form button[type=submit]').click();
    await page.waitForFunction(() =>
        document.querySelector('#riro-form [name="riro_password"]').value === '');
    assert(await page.evaluate(() => testCalls.some(x => x.action === 'save_riro'
        && x.payload.riro_id === 'saved-riro' && x.payload.riro_password === 'test-only-riro')));
    // 아이디만 고칠 때 비밀번호를 다시 치게 만들지 않는다.
    await page.locator('#riro-form button[type=submit]').click();
    assert(await page.evaluate(() => testCalls.some(x => x.action === 'save_riro'
        && x.payload.riro_password === '')));

    // AIEP 도 같은 규칙이다. 아이디는 @ai.jbedu.kr 앞부분만 받는다.
    assert(await page.locator('#aiep-form [name="aiep_id"]').inputValue() === 'saved-aiep');
    assert(await page.locator('#aiep-badge').textContent() === '저장됨');
    await page.locator('#aiep-form [name="aiep_password"]').fill('test-only-aiep');
    await page.locator('#aiep-form button[type=submit]').click();
    await page.waitForFunction(() =>
        document.querySelector('#aiep-form [name="aiep_password"]').value === '');
    assert(await page.evaluate(() => testCalls.some(x => x.action === 'save_aiep'
        && x.payload.aiep_id === 'saved-aiep' && x.payload.aiep_password === 'test-only-aiep')));

    // 연결 해제 — 되돌릴 수 없으니 묻고 나서 지운다. 취소하면 아무 일도 없어야 한다.
    page.once('dialog', d => d.dismiss());
    await page.locator('[data-disconnect="riro"]').click();
    await page.waitForTimeout(400);
    assert(!(await page.evaluate(() => testCalls.some(x => x.action === 'disconnect'))));
    page.on('dialog', d => d.accept());
    for (const target of ['cert', 'riro', 'aiep']) {
      await page.locator(`[data-disconnect="${target}"]`).click();
      await page.waitForFunction(t => testCalls.some(
          x => x.action === 'disconnect' && x.payload.target === t), target);
    }
    await page.locator('#auth-toggle').click();
    await page.getByText('자동 감시 중',{exact:true}).waitFor();
    assert.strictEqual(await page.locator('#watch-toggle').count(),0);
    await page.locator('#summary').uncheck();
    await page.waitForFunction(() => !document.getElementById('summary').disabled);
    await page.locator('#include-body').uncheck();
    await page.waitForFunction(() => !document.getElementById('include-body').disabled);
    assert(await page.evaluate(() => testCalls.some(x => x.action === 'options' && !x.payload.summary && !x.payload.body)));
    await page.locator('#auth-toggle').click();
    await page.getByText('계정 연결 대기',{exact:true}).waitFor();
    await page.evaluate(() => {document.activeElement.blur(); window.scrollTo(0,0);});
    await page.screenshot({path:path.join(os.tmpdir(),'spacekijun-web-settings.png'),fullPage:true,animations:'disabled'});
    for (const width of [1180,860,640]) {
      await page.setViewportSize({width,height:620});
      for (const section of ['home','inbox','roster','settings']) {
        await page.locator(`.nav[data-page="${section}"]`).click();
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Overflow: ${section} at ${width}`);
      }
    }
    assert.deepStrictEqual(errors,[]);
    console.log('PASS: navigation, action bridge, empty/error states, message escaping, search, forms (인증서·리로스쿨·AIEP), 연결 해제, watch controls, 3 viewport sizes');
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
