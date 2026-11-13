
const { selectDept, D } = require('./lib2.js');
// 누가기록 한 학생 줄 삭제 (본 화면 체크 → [삭제]). env: DEPT, DAY, KEY(학년-반-번호), SAVE=1 이면 삭제 확인까지 — 없으면 확인창에서 취소(미리보기)
module.exports = async (page, nav) => {
  const log = [];
  await selectDept(page, nav, process.env.DEPT);
  await page.locator('[role=gridcell]:visible').filter({ hasText: new RegExp('^' + process.env.DAY.replace(/\./g, '\.')) }).first().click(); await page.waitForTimeout(2500); await nav.waitLoading(page);
  const rows = await page.evaluate(() => [...document.querySelectorAll('[role=row]')].filter(r => r.offsetParent && r.querySelector('[aria-label*="활동내용"]')).map(r => {
    const ls = [...r.querySelectorAll('[role=gridcell]')].map(c => c.getAttribute('aria-label') || '');
    const pick = k => { const l = ls.find(l => new RegExp('^[0-9]+행( 마지막 행)? ' + k + ' ').test(l)); return l ? l.trim().split(' ').pop() : ''; };
    const nl = ls.find(l => /읽기전용/.test(l));
    const hl = ls.find(l => / 이수시간 /.test(l)) || ''; const al = ls.find(l => / 활동내용 /.test(l)) || '';
    return { row: parseInt(ls.find(l => /^[0-9]+행/.test(l)) || ''), key: [pick('학년'), pick('반'), nl ? nl.trim().split(' ').pop() : ''].join('-'), h: hl.replace(/^.*이수시간 /, '').replace(/ ?편집창.*$/, ''), a: al.replace(/^.*활동내용 /, '').replace(/ ?편집창.*$/, '') };
  }));
  const t = rows.find(r => r.key === process.env.KEY);
  log.push('행: ' + rows.map(r => `${r.key} ${r.h}h ${r.a}`).join(' / '));
  if (!t) { log.push('대상 없음'); return log; }
  const box = page.locator(`[role=gridcell][aria-label^="${t.row}행 "] .cl-checkbox, [aria-label^="${t.row}행 "][role=checkbox]`).first();
  log.push('체크박스 수: ' + await box.count());
  await box.click({ force: true }); await page.waitForTimeout(500);
  const checked = await page.evaluate(() => [...document.querySelectorAll('[role=checkbox][aria-checked=true]')].filter(e => e.offsetParent && /행선택 체크박스/.test(e.getAttribute('aria-label') || '')).map(e => parseInt(e.getAttribute('aria-label')) + '행'));
  log.push('체크된 행: ' + checked.join(','));
  if (checked.length !== 1 || checked[0] !== t.row + '행') { log.push('선택이 대상 한 줄이 아님 — 중단'); return log; }
  await page.locator('div.cl-text:visible, .cl-button:visible').filter({ hasText: /^삭제$/ }).first().click(); await page.waitForTimeout(1500);
  const q = await D.read(page); log.push('확인창: ' + q.map(x => x.text.slice(-80)).join(' | '));
  if (process.env.SAVE !== '1') { if (q.length) await D.press(page, '취소').catch(() => {}); log.push('취소함(미리보기)'); return log; }
  if (!q.some(x => /삭제/.test(x.text))) return log;
  await D.press(page, '확인'); await nav.waitLoading(page); await page.waitForTimeout(1500);
  const r2 = await D.read(page); log.push('결과: ' + r2.map(x => x.text.slice(-60)).join(' | '));
  if (r2.length) await D.press(page, '확인');
  return log;
};
