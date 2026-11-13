// 누가기록 읽기(이름 가림 — 데이터셋에서 학년·반·번호·이수시간·활동내용만). env: DEPT, DAYS(쉼표)
const { selectDept } = require('./lib2.js');
module.exports = async (page, nav) => {
  await selectDept(page, nav, process.env.DEPT);
  const out = {};
  for (const d of process.env.DAYS.split(',')) {
    const c = page.locator('[role=gridcell]:visible').filter({ hasText: new RegExp('^' + d.replace(/\./g, '\.')) }).first();
    if (!await c.count()) { out[d] = '날짜 없음'; continue; }
    await c.click(); await page.waitForTimeout(2000); await nav.waitLoading(page);
    const rows = await page.evaluate(() => [...document.querySelectorAll('[role=row]')].filter(r => r.offsetParent && r.querySelector('[aria-label*="활동내용"]')).map(r => {
      const g = l => [...r.querySelectorAll('[role=gridcell]')].find(c => (c.getAttribute('aria-label') || '').includes(' ' + l + ' '));
      const v = l => { const c = g(l); if (!c) return ''; const i = c.querySelector('input, textarea'); return (i ? i.value : c.innerText).trim(); };
      return [v('학년'), v('반'), v('번호')].join('-') + ' ' + v('이수시간') + 'h ' + v('활동내용');
    }));
    const agg = {}; for (const r of rows) { const k = r.replace(/^\S+ /, ''); agg[k] = (agg[k] || []).concat(r.split(' ')[0]); }
    out[d] = Object.fromEntries(Object.entries(agg).map(([k, v]) => [k, v.length + '명' + (v.length <= 3 ? ' ' + v.join(',') : '')]));
  }
  return out;
};
