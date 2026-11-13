// Local fixtures only. Verifies the new home and account-change races.
const {chromium} = require('playwright');
const {pathToFileURL} = require('url');
const path = require('path');
const os = require('os');
const assert = require('assert');
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1180,height:900}});
    const errors=[]; page.on('pageerror', e=>errors.push(e.message));
    await page.addInitScript(() => {
      window.fixtureUser = 'sample@example.test';
      window.fixtureFail = false;
      window.fixtureHold = false;
      window.calls = [];
      const data = {name:'테스트',date:'2026-09-10',updated_at:'2026-09-10T09:15:00+09:00',errors:{},
        today:[{time:'09:00',title:'공통수학1 1-3',label:'1교시',detail:'수업'},{time:'11:00',title:'교과 협의회',label:'일정',detail:'회의실'}],
        week:[{date:'2026-09-11',time:'',title:'평가 계획 제출',label:'업무 마감'}],
        tasks:[{date:'2026-09-09',title:'학년별 평가 자료 확인',detail:'2학기 평가 운영',label:'기한 초과'},{date:'2026-09-10',title:'학교 행사 준비',detail:'운영 자료 작성',label:'오늘 마감'}],
        notices:[{title:'2학기 교육과정 안내',department:'교무부',start_date:'2026-09-01',end_date:'2026-09-30',content:'자세한 운영 안내입니다.\n<img src=x onerror="window.injected=true">'}],
        notifications:[{title:'새 쪽지가 도착했습니다.',message:'업무 관련 자료를 확인해 주세요.',is_read:false,created_at:'2026-09-10T00:15:00Z'}]};
      window.pywebview={api:{call:async(action,payload)=>{
        calls.push({action,payload});
        if(action==='state') return {ok:true,data:{user:fixtureUser,credentials:true,summary:true,body:true,logs:[]}};
        if(action==='dashboard') {
          if(fixtureHold) await new Promise(resolve=>{window.releaseDashboard=resolve;});
          return fixtureFail ? {ok:false,error:'연결 실패: 다시 시도해 주세요.'} : {ok:true,data};
        }
        return {ok:true,data:'완료'};
      }}};
      window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));
    });
    await page.goto(pathToFileURL(path.resolve('app/web/index.html')).href);
    await page.locator('#dashboard-grid').waitFor({state:'visible'});
    assert.strictEqual(await page.locator('#dash-task-count').textContent(),'2');
    await page.locator('#dash-notices summary').click();
    assert.strictEqual(await page.locator('#dash-notices img').count(),0);
    await page.locator('[data-route="/timetable"]').click();
    assert(await page.evaluate(()=>calls.some(c=>c.action==='open_space'&&c.payload.route==='/timetable')));
    for(const width of [1180,860,640]) {
      await page.setViewportSize({width,height:900});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await page.screenshot({path:path.join(os.tmpdir(),`spacekijun-dashboard-${width}.png`),fullPage:true});
    }
    await page.evaluate(()=>{fixtureFail=true;});
    await page.locator('#refresh-dashboard').click();
    await page.getByText('연결 실패: 다시 시도해 주세요.').waitFor();
    assert(await page.locator('#dashboard-grid').isHidden());
    await page.evaluate(()=>{fixtureFail=false;fixtureHold=true;});
    await page.locator('#refresh-dashboard').click();
    await page.waitForFunction(()=>!!window.releaseDashboard);
    await page.evaluate(()=>{fixtureUser=null;});
    await page.waitForFunction(()=>document.getElementById('dashboard-sync').textContent==='계정 연결 필요');
    await page.evaluate(()=>releaseDashboard());
    assert(await page.locator('#dashboard-grid').isHidden());
    assert.strictEqual(await page.locator('#dash-today').textContent(),'');
    assert.deepStrictEqual(errors,[]);
    console.log('PASS: dashboard data, escaping, navigation, 3 widths, errors and logout race');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
