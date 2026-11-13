// 누가기록 일괄등록. env: DEPT, DAY(2026.09.18.), TEXT, HOURS(''=최대 이수시간), ONLY / EXCLUDE (학년-반-번호, 쉼표),
//   EXPECT(선택될 학생 수, 저장 조건), VOL=1(봉사활동실적 — 장소 자동, PLACE 주면 일치 검사), SAVE=1 이면 검사 통과 시 저장·닫기
const { selectDept, D } = require('./lib2.js');
module.exports = async (page, nav) => {
  const log = [];
  await selectDept(page, nav, process.env.DEPT);
  await page.locator('[role=gridcell]:visible').filter({ hasText: new RegExp('^' + process.env.DAY.replace(/\./g, '\.')) }).first().click(); await page.waitForTimeout(2000); await nav.waitLoading(page);
  await page.locator('.cl-button:visible, div.cl-text:visible').filter({ hasText: /^일괄등록$/ }).first().click(); await page.waitForTimeout(3000); await nav.waitLoading(page);
  const dlg = page.locator('.cl-dialog:visible, [role=dialog]:visible').last();
  const days = await dlg.locator('input[aria-label="일자"]').evaluateAll(es => es.filter(e => e.offsetParent).map(e => e.value));
  if (!days.includes(process.env.DAY)) { await D.press(page, '닫기'); return ['일자 불일치 — 중단: ' + days]; }
  // 창 안 학생 행: 학년-반-번호 → 행 번호
  const students = await dlg.evaluate(d => [...d.querySelectorAll('[role=row]')].map(r => {
    const cells = [...r.querySelectorAll('[role=gridcell]')].map(c => (c.innerText || '').trim());
    const box = r.querySelector('[aria-label$="행선택 체크박스"]'); if (!box) return null;
    const nums = cells.filter(x => /^\d+$/.test(x));
    return { row: parseInt(box.getAttribute('aria-label')), key: nums.slice(0, 3).join('-'), note: cells.find(x => /결|인정|조퇴|지각/.test(x)) || '' };
  }).filter(Boolean));
  const only = (process.env.ONLY || '').split(',').filter(Boolean), ex = (process.env.EXCLUDE || '').split(',').filter(Boolean);
  const want = students.filter(s => (only.length ? only.includes(s.key) : true) && !ex.includes(s.key));
  for (const s of want) await dlg.locator(`[aria-label^="${s.row}행 "][aria-label$="행선택 체크박스"]`).first().click();
  await page.waitForTimeout(400);
  const maxBox = dlg.locator('[aria-label="최대 이수시간 적용"]').first();
  const isOn = async () => maxBox.evaluate(e => /cl-checked/.test(e.closest('.cl-checkbox')?.className || ''));
  const H = process.env.HOURS || '';
  if (H) { if (await isOn()) { await maxBox.click(); await page.waitForTimeout(800); }   // 해제 직후 숫자칸이 0 으로 바뀌므로 기다린 뒤 입력
    const hi = dlg.locator('input[aria-label="이수시간"]').first(); await hi.click(); await page.waitForTimeout(300); await page.keyboard.press('Control+A'); await page.keyboard.type(H, { delay: 80 }); await page.waitForTimeout(300); await page.keyboard.press('Tab'); await page.waitForTimeout(500); }
  else if (!await isOn()) { await maxBox.click(); await page.waitForTimeout(400); }
  const ta = dlg.locator('textarea[aria-label="활동내용"]').first(); await ta.click(); await page.keyboard.press('Control+A'); await page.keyboard.type(process.env.TEXT); await page.keyboard.press('Tab');
  if (process.env.VOL === '1') {
    // «봉사활동실적입력» 글자와 같은 줄 오른쪽 체크박스. 켜면 장소(«(학교)학교명»)가 자동으로 채워지고 잠긴다.
    await dlg.evaluate(d => { const t = [...d.querySelectorAll('.cl-text')].find(e => e.innerText.trim() === '봉사활동실적입력'); const ty = t.getBoundingClientRect().y;
      const o = [...d.querySelectorAll('.cl-checkbox')].filter(c => c.offsetParent).map(c => ({ c, r: c.getBoundingClientRect() })).find(o => Math.abs(o.r.y - ty) < 15 && o.r.x > t.getBoundingClientRect().x);
      o.c.setAttribute('data-vol', '1'); });
    const vb = dlg.locator('[data-vol="1"]');
    for (let i = 0; i < 3 && !/cl-checked/.test(await vb.getAttribute('class')); i++) { await vb.locator('.cl-checkbox-icon').first().click({ force: true }); await page.waitForTimeout(1200); }
  }
  await page.waitForTimeout(500);
  const st = await dlg.evaluate(d => {
    const on = c => /cl-checked/.test(c.className);
    const rows = [...d.querySelectorAll('[aria-label$="행선택 체크박스"]')].filter(b => on(b.closest('.cl-checkbox'))).map(b => parseInt(b.getAttribute('aria-label')));
    const flags = Object.fromEntries([...d.querySelectorAll('.cl-checkbox')].filter(c => c.offsetParent).map(c => [(c.querySelector('[aria-label]')?.getAttribute('aria-label') || c.innerText.trim() || '?'), on(c)]).filter(([k]) => !/행선택|전체선택/.test(k)));
    const vals = Object.fromEntries([...d.querySelectorAll('input, textarea')].filter(e => e.offsetParent).map(e => [e.getAttribute('aria-label') || '?', e.value]));
    return { rows, flags, vals };
  });
  const chosen = students.filter(s => st.rows.includes(s.row)).map(s => s.key + (s.note ? '(' + s.note + ')' : ''));
  log.push({ 창학생: students.map(s => s.key + (s.note ? '(' + s.note + ')' : '')).join(' '), 선택: chosen.join(' '), 선택수: chosen.length, flags: st.flags, 이수시간: st.vals['이수시간'], 활동내용: st.vals['활동내용'], 장소: st.vals['장소 또는 주관 기관명'] });
  const okCount = !process.env.EXPECT || chosen.length === Number(process.env.EXPECT);
  const okText = st.vals['활동내용'] === process.env.TEXT;
  const okVol = process.env.VOL !== '1' || (!!st.vals['장소 또는 주관 기관명'] && (!process.env.PLACE || st.vals['장소 또는 주관 기관명'] === process.env.PLACE));
  const okHours = H ? st.vals['이수시간'] === H && !st.flags['최대 이수시간 적용'] : !!st.flags['최대 이수시간 적용'];
  if (process.env.SAVE !== '1' || !okCount || !okText || !okHours || !okVol) { log.push(`저장 안 함 (SAVE=${process.env.SAVE || ''}, 학생수 ${okCount}, 문구 ${okText}, 시간 ${okHours}, 봉사 ${okVol})`); await D.press(page, '닫기'); return log; }
  await dlg.locator('.cl-button:visible, div.cl-text:visible').filter({ hasText: /^저장$/ }).last().click(); await page.waitForTimeout(1500);
  const q = await D.read(page);
  if (!q.some(x => /저장하시겠습니까/.test(x.text))) { log.push('확인창 없음: ' + JSON.stringify(q.map(x => x.text.slice(-80)))); return log; }
  await D.press(page, '확인'); await nav.waitLoading(page); await page.waitForTimeout(2000);
  const r2 = await D.read(page); log.push('결과: ' + r2.map(x => x.text.slice(-40)).join(' | '));
  if (r2.some(x => /^알림/.test(x.text))) await D.press(page, '확인');
  if ((await D.read(page)).some(x => /일괄등록/.test(x.text))) await D.press(page, '닫기');
  return log;
};
