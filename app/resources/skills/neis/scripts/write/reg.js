// 이수시간기준등록: env DEPT, ROWS(그리드 행 번호, 쉼표), GRADES(1,2,3), SAVE=1 이면 저장까지
const { selectDept, D } = require('./lib2.js');
module.exports = async (page, nav) => {
  const dept = process.env.DEPT, rows = process.env.ROWS.split(','), grades = process.env.GRADES.split(',');
  await selectDept(page, nav, dept);
  const log = [];
  for (const r of rows) for (const g of grades) {
    const cell = page.locator(`[role=gridcell][aria-label^="${r}행 ${g}학년 선택"]`).first();
    if (!await cell.count()) { log.push(`${r}행 ${g}학년: 칸 없음`); continue; }
    await cell.scrollIntoViewIfNeeded().catch(() => {});
    const before = await cell.getAttribute('aria-label');
    const dis = await cell.evaluate(c => !!c.querySelector('.cl-disabled') || /cl-disabled/.test(c.className));
    if (dis) { log.push(`${r}행 ${g}학년: 비활성`); continue; }
    if (/선택 해제/.test(before)) { await cell.locator('.cl-checkbox-field, .cl-checkbox').first().click(); await page.waitForTimeout(250); }
    log.push(`${r}행 ${g}학년: ${await cell.getAttribute('aria-label')}`);
  }
  if (process.env.SAVE !== '1') return log;
  await nav.waitOverlayGone(page);
  await page.locator('div.cl-text:visible, button:visible, .cl-button:visible').filter({ hasText: /^저장$/ }).first().click(); await page.waitForTimeout(1500);
  const q = await D.read(page); log.push('확인창: ' + JSON.stringify(q));
  if (!q.length || !/저장하시겠습니까/.test(q[0].text)) return log;
  await D.press(page, '확인'); await nav.waitLoading(page); await page.waitForTimeout(1500);
  const r2 = await D.read(page); log.push('결과: ' + JSON.stringify(r2));
  if (r2.length) await D.press(page, '확인');
  await nav.clickButton(page, '조회'); await page.waitForTimeout(1000);
  const t = (await nav.screenText(page)).replace(/\s+/g, ' ');
  log.push((t.match(/1학년 \(\d+\) 2학년 \(\d+\) 3학년 \(\d+\)/) || [])[0]);
  log.push((t.match(/23 2026\.08\.21.*?(?=33 2026\.10)/) || [])[0]);
  return log;
};
