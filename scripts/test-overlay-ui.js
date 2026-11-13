// NEIS 화면에 얹는 도우미 패널을 따로 확인한다. 데스크 호출은 흉내라 실제 나이스는 건드리지 않는다.
// 주입하는 파일은 `core/neis_overlay.py` 가 읽는 것과 같은 app/web/neis-overlay.js 다.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');
const assert = require('assert');

const SOURCE = fs.readFileSync(path.resolve('app/web/neis-overlay.js'), 'utf8');

// 나이스 화면을 흉내 낸 문서. 전역 스타일이 촘촘한 상황을 만들어 섀도 격리를 확인한다.
const HOST_PAGE = `<!doctype html><meta charset="utf-8"><title>NEIS 흉내</title>
<style>
  *{font-family:serif!important;color:#900!important}
  button{width:400px!important;height:90px!important;background:#900!important}
  div{border:4px dashed #900!important}
</style>
<body><div class="cl-text">출결관리 2단계</div><p>나이스 본문</p></body>`;

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1100, height: 760 } });
    const tickets = new Map();
    let nextTicket = 0;

    await context.exposeFunction('__deskAsk', async text => {
      const id = 'job-' + (++nextTicket);
      tickets.set(id, { state: 'pending', progress: ['메뉴 목록을 수집하는 중'], kind: 'ask', text });
      return id;
    });
    await context.exposeFunction('__deskPick', async row => {
      const id = 'job-' + (++nextTicket);
      tickets.set(id, { state: 'pending', progress: [], kind: 'pick', row });
      return id;
    });
    await context.exposeFunction('__deskPoll', async id => tickets.get(id) || { state: 'unknown' });
    await context.exposeFunction('__deskState', async () => ({ open: true, screens: 46, ai: true }));
    await context.addInitScript(SOURCE);

    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('data:text/html;charset=utf-8,' + encodeURIComponent(HOST_PAGE));

    const panel = page.locator('#spacekijun-desk-panel');
    await panel.locator('.launcher').waitFor();
    assert.strictEqual(await panel.locator('.panel').isVisible(), false, '처음에는 접혀 있어야 한다');

    // 섀도 격리: 나이스의 전역 스타일이 패널 버튼을 덮지 않아야 한다.
    const box = await panel.locator('.launcher').boundingBox();
    assert(box.width < 200 && box.height < 60,
      `전역 스타일이 새어 들어왔다 (${Math.round(box.width)}x${Math.round(box.height)})`);

    // 호스트 노드는 light DOM 에 있어 페이지의 `!important` 를 맞는다. 인라인으로 막아야 한다.
    const hostStyle = await page.evaluate(() => {
      const s = getComputedStyle(document.getElementById('spacekijun-desk-panel'));
      return { border: s.borderTopWidth, position: s.position, float: s.float };
    });
    assert.strictEqual(hostStyle.border, '0px', '페이지 테두리가 호스트에 그려졌다');
    assert.strictEqual(hostStyle.position, 'fixed', '호스트가 고정 위치를 잃었다');

    await panel.locator('.launcher').click();
    await panel.locator('.panel').waitFor({ state: 'visible' });
    // 상태줄은 AI 로 해석하는지와 아는 화면 수를 늘 보여야 한다.
    await page.waitForFunction(() => {
      const p = document.getElementById('spacekijun-desk-panel');
      return p && p.shadowRoot.querySelector('.status').textContent.includes('AI 해석 켜짐');
    });
    assert((await panel.locator('.status').textContent()).includes('화면 46개'));

    // 1) 보낸 뒤 진행 상황이 바뀌면 그대로 보여야 한다.
    await panel.locator('input').fill('인공지능 기초 과목 출결해야 해');
    await panel.locator('.send').click();
    await panel.getByText('메뉴 목록을 수집하는 중').waitFor();
    await page.evaluate(() => { });
    await (async () => {
      const id = 'job-1';
      await page.evaluate(() => { });
      tickets.get(id).progress.push('과목별출결관리 진입');
    })();
    await panel.getByText('과목별출결관리 진입').waitFor();

    // 2) 끝나면 답과 선택지를 보여야 한다.
    tickets.get('job-1').state = 'done';
    tickets.get('job-1').data = {
      ok: true, option_kind: 'row', source: 'model', subject: '인공지능 기초',
      reply: '교과담임 · 출결관리 > 과목별출결관리 화면을 열었습니다. 맞는 수업이 3개라 선택하지 않았습니다.',
      options: ['1학년 5(인공지능 기초)', '1학년 7(인공지능 기초)', '1학년 9(인공지능 기초)']
    };
    await panel.getByText('맞는 수업이 3개라').waitFor();
    // 무엇이 골랐는지 눈에 보여야 한다 — "AI 가 쓰이긴 하나" 를 확인할 수 있게.
    await panel.getByText('AI가 해석했습니다 · 읽어 낸 조건: 과목 인공지능 기초').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(os.tmpdir(), 'spacekijun-overlay.png') });

    // 3) 수업을 누르면 해석을 거치지 않고 pick 으로 가야 한다.
    await panel.getByRole('button', { name: '1학년 7(인공지능 기초)' }).click();
    await page.waitForFunction(() => true);
    await (async () => {
      for (let i = 0; i < 40 && !tickets.get('job-2'); i++) await new Promise(r => setTimeout(r, 100));
    })();
    assert(tickets.get('job-2'), '수업 선택이 데스크로 전달되지 않았다');
    assert.strictEqual(tickets.get('job-2').kind, 'pick', '수업 선택은 pick 이어야 한다');
    assert.strictEqual(tickets.get('job-2').row, '1학년 7(인공지능 기초)');
    tickets.get('job-2').state = 'done';
    tickets.get('job-2').data = { ok: true, reply: '1학년 7(인공지능 기초) 을 선택했습니다.', options: [] };
    await panel.getByText('1학년 7(인공지능 기초) 을 선택했습니다.').waitFor();

    // 4) 화면 내용은 글자로만 들어가야 한다.
    await panel.locator('input').fill('<img src=x onerror="window.injected=true">');
    await panel.locator('.send').click();
    await (async () => {
      for (let i = 0; i < 40 && !tickets.get('job-3'); i++) await new Promise(r => setTimeout(r, 100));
    })();
    tickets.get('job-3').state = 'done';
    tickets.get('job-3').data = { ok: true, reply: '<b>열었습니다</b>', options: [] };
    await panel.getByText('<b>열었습니다</b>').waitFor();
    assert(await page.evaluate(() => !window.injected), '입력이 HTML 로 실행되면 안 된다');

    // 5) 오류는 그대로 보여야 한다.
    await panel.locator('input').fill('없는 업무');
    await panel.locator('.send').click();
    await (async () => {
      for (let i = 0; i < 40 && !tickets.get('job-4'); i++) await new Promise(r => setTimeout(r, 100));
    })();
    tickets.get('job-4').state = 'error';
    tickets.get('job-4').error = 'NEIS 창이 닫혔습니다.';
    await panel.getByText('NEIS 창이 닫혔습니다.').waitFor();

    // 6) 나이스가 화면을 갈아 끼워도 다시 붙어야 한다. 열려 있던 상태도 그대로 남아야 한다.
    await page.evaluate(() => { document.body.innerHTML = '<p>다시 그린 화면</p>'; });
    assert.strictEqual(await page.locator('#spacekijun-desk-panel').count(), 0,
      '화면을 갈아 끼우면 일단 떨어져 나가야 한다 (전제 확인)');
    await page.waitForFunction(() => !!document.getElementById('spacekijun-desk-panel'),
      null, { timeout: 8000 });
    assert(await panel.locator('.panel').isVisible(), '다시 붙은 뒤에도 열려 있어야 한다');
    await panel.getByText('NEIS 창이 닫혔습니다.').waitFor();   // 대화 내용도 남아 있어야 한다

    // 7) 개발 중 다시 심기 — 떼고 새로 넣으면 패널은 하나만 남아야 한다.
    assert.strictEqual(await page.locator('#spacekijun-desk-panel').count(), 1);
    await page.evaluate(() => window.__deskPanelStop());
    assert.strictEqual(await page.locator('#spacekijun-desk-panel').count(), 0,
      '떼어내기가 동작하지 않았다');
    await page.waitForTimeout(2500);        // 옛 재부착 타이머가 살아 있으면 여기서 되살아난다
    assert.strictEqual(await page.locator('#spacekijun-desk-panel').count(), 0,
      '떼어낸 뒤에도 재부착 타이머가 돌고 있다');
    await page.evaluate(SOURCE);
    assert.strictEqual(await page.locator('#spacekijun-desk-panel').count(), 1,
      '다시 심은 뒤 패널이 하나여야 한다');
    await panel.locator('.launcher').waitFor();

    // 8) 프레임 안에는 만들지 않는다.
    await page.evaluate(() => {
      const frame = document.createElement('iframe');
      frame.srcdoc = '<p>프레임</p>';
      document.body.append(frame);
    });
    await page.waitForTimeout(1500);
    assert.strictEqual(page.frames().length, 2, '프레임이 만들어져야 한다');
    const inFrame = await page.frames()[1].evaluate(() => !!document.getElementById('spacekijun-desk-panel'));
    assert(!inFrame, '프레임 안에는 패널을 만들면 안 된다');

    assert.deepStrictEqual(errors, [], '자바스크립트 오류: ' + errors.join(' | '));
    console.log('NEIS 오버레이 패널 확인 완료 · 스크린샷: ' + path.join(os.tmpdir(), 'spacekijun-overlay.png'));
  } finally {
    await browser.close();
  }
})().catch(e => { console.error('실패: ' + e.message); process.exit(1); });
