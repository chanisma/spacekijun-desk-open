const { D } = require('./lib2.js');
module.exports = async (page, nav) => {
  const log = [];
  const dlg = page.locator('.cl-dialog:visible, [role=dialog]:visible').last();
  const v = await dlg.locator('textarea[aria-label="활동내용"]').first().inputValue(); log.push('활동내용=' + v);
  await dlg.locator('.cl-button:visible, div.cl-text:visible').filter({ hasText: /^저장$/ }).last().click(); await page.waitForTimeout(1500);
  const q = await D.read(page); log.push('확인창: ' + JSON.stringify(q.map(x => x.text)));
  if (!q.find(x => /저장하시겠습니까/.test(x.text))) return log;
  await D.press(page, '확인'); await nav.waitLoading(page); await page.waitForTimeout(2000);
  const r2 = await D.read(page); log.push('결과: ' + JSON.stringify(r2.map(x => x.text)));
  if (r2.some(x => /^알림/.test(x.text))) await D.press(page, '확인');
  const left = await D.read(page); if (left.some(x => /일괄등록/.test(x.text))) { await D.press(page, '닫기'); log.push('팝업 닫음'); }
  return log;
};
