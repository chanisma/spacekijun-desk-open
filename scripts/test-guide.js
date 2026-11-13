const {chromium}=require('playwright');
const {pathToFileURL}=require('url');
const path=require('path'),fs=require('fs'),os=require('os'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:960}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const out=path.join(os.tmpdir(),'desk-guide-review');fs.mkdirSync(out,{recursive:true});
 const url=pathToFileURL(path.resolve('app/web/guide/index.html')).href;
 for(let step=0;step<10;step++) {
   for(const t of [1.5,7.3,12]) {
     await page.goto(`${url}?step=${step}&t=${t}`);
     await page.locator('aside h2').waitFor();await page.evaluate(()=>document.fonts.ready);
     await page.screenshot({path:path.join(out,`step-${step+1}-${t}.png`),fullPage:true});
   }
 }
 await page.goto(url);await page.locator('aside h2').waitFor();
 await page.getByRole('button',{name:'다음 →',exact:true}).click();
 assert((await page.locator('aside h2').textContent()).includes('계정'));
 await page.getByRole('button',{name:'↻ 다시 재생',exact:true}).click();
 await page.keyboard.press('ArrowRight');
 assert((await page.locator('aside h2').textContent()).includes('인증서'));
 for(const width of [1180,860,640]){
   await page.setViewportSize({width,height:820});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 }
 await page.goto(pathToFileURL(path.resolve('app/web/index.html')).href);
 await page.locator('#open-guide').click();
 await page.frameLocator('#guide-frame').getByRole('heading',{name:'화면으로 익히는 업무 데스크'}).waitFor();
 await page.frameLocator('#guide-frame').getByRole('button',{name:'안내 닫기',exact:true}).click();
 await page.waitForFunction(()=>!document.getElementById('guide-dialog').open);
 assert.deepStrictEqual(errors,[]);await browser.close();console.log('PASS guide: 30 frames, navigation/replay, responsive widths, modal open/close. '+out);
})().catch(e=>{console.error(e);process.exit(1)});
