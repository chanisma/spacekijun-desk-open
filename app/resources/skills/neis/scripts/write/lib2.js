const D = require('./dlg.js');
async function selectDept(page, nav, name) {
  await page.keyboard.press('Escape').catch(() => {});
  const dept = page.locator('[role=combobox][aria-label^="부서명"]:visible').first();   // 부서명 콤보
  const cur = ((await dept.getAttribute('aria-label')) || '').replace(/^부서명,\s*/, '').trim();
  if (!(cur === name || cur.startsWith(name + ' '))) {
    let hit = false;
    for (let tries = 0; tries < 3 && !hit; tries++) {          // 목록이 한 번에 안 열릴 때가 있다
      await dept.click(); await page.waitForTimeout(800);
      const opts = page.locator('[role=option]:visible'); const n = await opts.count();
      for (let i = 0; i < n; i++) { const t = (await opts.nth(i).innerText()).trim(); if (t === name || t.startsWith(name + ' ')) { await opts.nth(i).click(); hit = true; break; } }
      if (!hit) { await page.keyboard.press('Escape').catch(() => {}); await page.waitForTimeout(500); }
    }
    if (!hit) throw new Error('부서 옵션 없음: ' + name);
    await page.waitForTimeout(600);
  }
  await nav.clickButton(page, '조회'); await page.waitForTimeout(1000);
}
module.exports = { selectDept, D };
