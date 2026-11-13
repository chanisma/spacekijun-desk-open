const { D } = require('./lib2.js');
module.exports = async (page, nav) => {
  const log = [];
  await nav.waitOverlayGone(page);
  await page.locator('div.cl-text:visible, button:visible, .cl-button:visible').filter({ hasText: /^저장$/ }).first().click(); await page.waitForTimeout(1500);
  const q = await D.read(page); log.push('확인창: ' + JSON.stringify(q));
  if (!q.length || !/저장하시겠습니까/.test(q[0].text)) return log;
  await D.press(page, '확인'); await nav.waitLoading(page); await page.waitForTimeout(1500);
  const r2 = await D.read(page); log.push('결과: ' + JSON.stringify(r2));
  if (r2.length) await D.press(page, '확인');
  return log;
};
