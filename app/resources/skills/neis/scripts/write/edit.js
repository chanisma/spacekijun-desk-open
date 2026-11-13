// 본 화면 누가기록 그리드 직접 편집. env: DEPT, DAY, KEYS(학년-반-번호, 쉼표 | all), HOURS(선택), TEXT(선택), SAVE=1
const { selectDept, D } = require('./lib2.js');
module.exports = async (page, nav) => {
  const log = [];
  await selectDept(page, nav, process.env.DEPT);
  await page.locator('[role=gridcell]:visible').filter({ hasText: new RegExp('^' + process.env.DAY.replace(/\./g, '\.')) }).first().click(); await page.waitForTimeout(2000); await nav.waitLoading(page);
  const rows = await page.evaluate(() => [...document.querySelectorAll('[role=row]')].filter(r => r.offsetParent && r.querySelector('[aria-label*="활동내용"]')).map(r => {
    const cs = [...r.querySelectorAll('[role=gridcell]')]; const lab = c => c.getAttribute('aria-label') || '';
    const ls = cs.map(lab);
    const pick = k => { const l = ls.find(l => new RegExp('^[0-9]+행( 마지막 행)? ' + k + ' ').test(l)); return l ? l.trim().split(' ').pop() : ''; };
    const nl = ls.find(l => /읽기전용/.test(l)); const no = nl ? nl.trim().split(' ').pop() : '';
    if (!cs.length) return null;
    return { row: parseInt(lab(cs[1] || cs[0])), key: [pick('학년'), pick('반'), no].join('-') };
  }).filter(x => x && x.row));
  const keys = process.env.KEYS === 'all' ? rows.map(r => r.key) : process.env.KEYS.split(',');
  const targets = rows.filter(r => keys.includes(r.key));
  log.push('대상: ' + targets.map(t => t.key + '(' + t.row + '행)').join(' '));
  if (targets.length !== keys.length) { log.push('대상 불일치 — 중단'); return log; }
  const setCell = async (row, col, val) => {
    const cell = page.locator(`[role=gridcell][aria-label^="${row}행 "][aria-label*=" ${col} "]`).first();
    await cell.scrollIntoViewIfNeeded().catch(() => {});
    await cell.click(); await page.waitForTimeout(500);   // 한 번 누르면 칸 안 textarea/input 에 포커스(두 번 누르면 풀림)
    await page.keyboard.press('Control+A'); await page.keyboard.type(val, { delay: 30 }); await page.waitForTimeout(200); await page.keyboard.press('Tab'); await page.waitForTimeout(400);
  };
  for (const t of targets) {
    if (process.env.HOURS) await setCell(t.row, '이수시간', process.env.HOURS);
    if (process.env.TEXT) await setCell(t.row, '활동내용', process.env.TEXT);
  }
  await page.waitForTimeout(500);   // Escape 를 누르면 마지막 칸 편집이 취소된다
  const now = await page.evaluate(rs => rs.map(r => {
    const cs = [...document.querySelectorAll(`[role=gridcell][aria-label^="${r}행 "]`)];
    // 편집 뒤 칸 글자는 다시 그려지기 전엔 비어 보인다 → aria-label('N행 열이름 값 [편집창]')에서 값을 읽는다
    const v = k => { const c = cs.find(c => (c.getAttribute('aria-label') || '').includes(' ' + k + ' ')); if (!c) return '?';
      return (c.getAttribute('aria-label') || '').replace(/^[0-9]+행( 마지막 행)? /, '').replace(k + ' ', '').replace(/ ?편집창 ?$/, '').trim(); };
    return r + '행 ' + v('이수시간') + 'h ' + v('활동내용');
  }), targets.map(t => t.row));
  log.push(now);
  const ok = now.every(s => (!process.env.HOURS || s.includes(' ' + process.env.HOURS + 'h ')) && (!process.env.TEXT || s.endsWith(process.env.TEXT)));
  if (process.env.SAVE !== '1' || !ok) { log.push(`저장 안 함 (SAVE=${process.env.SAVE || ''}, 값 확인 ${ok}) — 화면 편집은 [조회]로 되돌린다`); return log; }
  await nav.waitOverlayGone(page);
  await page.locator('div.cl-text:visible, .cl-button:visible').filter({ hasText: /^저장$/ }).first().click(); await page.waitForTimeout(1500);
  const q = await D.read(page); log.push('확인창: ' + q.map(x => x.text.slice(-60)).join(' | '));
  if (!q.some(x => /저장하시겠습니까/.test(x.text))) return log;
  await D.press(page, '확인'); await nav.waitLoading(page); await page.waitForTimeout(1500);
  const r2 = await D.read(page); log.push('결과: ' + r2.map(x => x.text.slice(-60)).join(' | '));
  if (r2.length) await D.press(page, '확인');
  return log;
};
