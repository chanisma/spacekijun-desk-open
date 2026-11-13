/**
 * 학교회계 지출품의: 작성 → (저장) → (결재요청 → 기안기). 화면 클릭 없이 Nexacro 폼 함수·데이터셋을 직접 다룬다.
 *   step: fill(화면만 채움, 저장 안 함) | save(저장 → 상태 101 품의저장) | request(결재요청 → 상태 102 → 기안기)
 *   spec: { budget: { detlBsns: 세부사업, detlIem: 세부항목, cpt: 산출내역(일부) },
 *           title, summary, items: [ { name, spec, qty, price } ] }
 *
 *   흐름: 품의등록(FADMANGEXCN001M01) → 예산선택 팝업(FADMANGEXCN004P01) dsMain.choise=1 → btnCnfirm
 *     → dsCnsulRegist.sj/cnsulPurpsCn → 행추가 + dsPrdlstDtlList(prdlstCn,stndrd,qty,expectUntpc) → fnExpectAmtCreat
 *     → save: fnSaveValidationChk() 후 fnSaveExpdCnsulWrtgList()
 *     → request: fnSanctnRequstChk() (fn_inputChk='Y' 로 확인창 생략) → saveSanctnRequstPrcs.do → wxsclient:// → 기안기
 *   기안기에는 제목·본문(개요)·지출품의서.ozd 가 이미 들어 있다 → draft.ps1 -Only route,task,pub 로 마무리.
 *   ⚠ 결재선·공개여부는 실행 전에 사용자에게 묻는다. 결재올림은 사용자 승인 뒤에만.
 *   ⚠ 삭제·결재취소요청은 구현하지 않는다([결재취소요청]은 '[결재취소] …' 결재문서를 새로 올린다).
 *     결재요청(102) 뒤 되돌리기는 사람이: 업무관리 › 문서관리 › 재정문서 에서 반송 → 품의목록에서 품의 삭제
 */
const U = require('../lib/nexa.js');
const { hookWxs } = require('./drafter.js');
const MENU = 'A00FAA0104001001', FORM = 'FADMANGEXCN001M01', POP = 'FADMANGEXCN004P01';

/** 학교회계 › 품의등록 화면 열기 → 폼 식 */
async function openPumuiForm(page) {
  const FF = U.FF(FORM);
  await page.evaluate(() => { const top = nexacro.getApplication().gv_topFrame.form;
    if (top.cboJobList.value !== 'A00FA') { top.cboJobList.set_value('A00FA'); top.fnCheckFrstMenuId('A00FA'); } });
  await page.waitForTimeout(2500);
  await page.evaluate(m => nexacro.getApplication().gv_topFrame.form.gfnOpenMenu(m), MENU);
  for (let t = 0; t < 40; t++) { await page.waitForTimeout(500); if (await page.evaluate(`!!${FF}`)) { await page.waitForTimeout(2500); return FF; } }
  throw new Error('품의등록 화면을 못 찾음 (학교회계 권한 확인)');
}

/** 예산선택 팝업의 목록(내가 품의할 수 있는 세부사업·산출내역·잔액)을 읽고 팝업을 닫는다 — 조회만 */
async function listBudgets({ page }) {
  const FF = await openPumuiForm(page);
  await page.evaluate(ff => eval(ff).divAuth1_btnBgtDtl_onclick(null, null), FF);
  let rows = null;
  for (let t = 0; t < 20 && !rows; t++) {
    await page.waitForTimeout(500);
    rows = await page.evaluate(p => { try { const ds = nexacro.getPopupFrames()[p].form.dsMain; if (!ds.getRowCount()) return null;
      const out = []; for (let i = 0; i < ds.getRowCount(); i++) { const c = n => ds.getColumn(i, n);
        if (!c('cptBasisCn')) continue;   // 소계 행 제외
        out.push({ 세부사업: c('sclDetlBsnsNm'), 세부항목: c('detlIemNm'), 원가통계비목: c('prmpcStatsExpitmNm'), 산출내역: c('cptBasisCn'), 예산현액: Number(c('bgtCrntam')), 잔액: Number(c('bgtBlce')) }); }
      return out; } catch (e) { return null; } }, POP);
  }
  await page.evaluate(p => { try { nexacro.getPopupFrames()[p].form.btnClose_onclick(null, null); } catch (e) { } }, POP);
  return rows || [];
}

async function runPumui({ ctx, page, log }, S, STEP = 'fill') {
  const FF = U.FF(FORM);
  const ev = (fn, arg) => page.evaluate(fn, [FF, arg]);

  // 0) 학교회계로 바꾸고 품의등록 열기
  await page.evaluate(() => { const top = nexacro.getApplication().gv_topFrame.form;
    if (top.cboJobList.value !== 'A00FA') { top.cboJobList.set_value('A00FA'); top.fnCheckFrstMenuId('A00FA'); } });
  await page.waitForTimeout(2500);
  await page.evaluate(m => nexacro.getApplication().gv_topFrame.form.gfnOpenMenu(m), MENU);
  let ok = false; for (let t = 0; t < 40 && !ok; t++) { await page.waitForTimeout(500); ok = await page.evaluate(`!!${FF}`); }
  if (!ok) return log('품의등록 화면을 못 찾음');
  await page.waitForTimeout(3000);

  // 열려 있던 화면에 기존 품의가 올라와 있으면 덮어쓰지 않는다
  const cur = await ev(([ff]) => eval(ff).dsCnsulRegist.getColumn(0, 'sclCnsulNo'));
  if (cur) return log('품의등록 화면에 기존 품의(' + cur + ')가 열려 있음 — 화면 탭을 닫거나 [신규] 후 다시 실행');

  // 1) 예산선택
  if (await ev(([ff]) => eval(ff).dsBgtDtlList.getRowCount()) === 0) {
    await ev(([ff]) => eval(ff).divAuth1_btnBgtDtl_onclick(null, null));
    let pop = false; for (let t = 0; t < 20 && !pop; t++) { await page.waitForTimeout(500); pop = await page.evaluate(p => { try { return !!nexacro.getPopupFrames()[p].form.dsMain.getRowCount(); } catch (e) { return false; } }, POP); }
    const pick = await page.evaluate(([p, B]) => { const f = nexacro.getPopupFrames()[p].form, ds = f.dsMain; let hit = -1;
      for (let i = 0; i < ds.getRowCount(); i++) {
        if ((ds.getColumn(i, 'sclDetlBsnsNm') || '') === B.detlBsns && (ds.getColumn(i, 'detlIemNm') || '') === B.detlIem && (ds.getColumn(i, 'cptBasisCn') || '').indexOf(B.cpt) >= 0) { hit = i; break; } }
      if (hit < 0) return 'ERR 예산 없음';
      const msg = ds.getColumn(hit, 'sclDetlBsnsNm') + ' / ' + ds.getColumn(hit, 'detlIemNm') + ' / ' + ds.getColumn(hit, 'cptBasisCn') + ' 잔액 ' + ds.getColumn(hit, 'bgtBlce');
      ds.setColumn(hit, 'choise', '1'); f.btnCnfirm_onclick(null, null); return msg; }, [POP, S.budget]);
    log('예산: ' + pick); if (pick.startsWith('ERR')) return;
    await page.waitForTimeout(1500);
  }

  // 2) 제목·개요·품목
  const filled = await ev(([ff, S]) => { const f = eval(ff), m = f.divMain.form;
    f.dsCnsulRegist.setColumn(0, 'sj', S.title); m.edtCnsulSj.set_value(S.title);
    f.dsCnsulRegist.setColumn(0, 'cnsulPurpsCn', S.summary); m.txtareaCnsulSumrCn.set_value(S.summary);
    if (f.dsPrdlstDtlList.getRowCount() === 0) for (const it of S.items) {
      f.divAuth2_btnRowAdit_onclick(null, null); const d = f.dsPrdlstDtlList, r = d.rowposition;
      d.setColumn(r, 'prdlstCn', it.name); d.setColumn(r, 'stndrd', it.spec || ''); d.setColumn(r, 'qty', it.qty); d.setColumn(r, 'expectUntpc', it.price); }
    f.fnExpectAmtCreat();
    const p = f.dsPrdlstDtlList, out = [];
    for (let i = 0; i < p.getRowCount(); i++) out.push(p.getColumn(i, 'prdlstCn') + ' ' + p.getColumn(i, 'qty') + '×' + p.getColumn(i, 'expectUntpc') + '=' + p.getColumn(i, 'expectAmt'));
    return out.join(', ') + ' | 요구금액 ' + f.divAmt.form.mskDmndAmt.value + ' | 예산잔액 ' + f.divAmt.form.mskBgtBlce.value; }, S);
  log('품목: ' + filled);
  if (STEP === 'fill') return log('fill 단계 끝 — 저장하지 않음');

  // 3) 저장
  const v = await ev(([ff]) => { const f = eval(ff); f.fv_saveMsgYn = 'N'; return String(f.fnSaveValidationChk()); });
  if (v !== 'true') return log('저장 검증 실패(화면 알림 확인)');
  await ev(([ff]) => eval(ff).fnSaveExpdCnsulWrtgList());
  let no = null; for (let i = 0; i < 20 && !no; i++) { await page.waitForTimeout(500); no = await ev(([ff]) => eval(ff).dsCnsulRegist.getColumn(0, 'sclCnsulNo')); }
  log('저장: 품의번호 ' + no + ' 상태 ' + await ev(([ff]) => eval(ff).dsCnsulRegist.getColumn(0, 'sclExpdStsSeCd')));
  if (STEP === 'save') return;

  // 4) 결재요청 → 기안기
  const hook = hookWxs(ctx, log, 25000);
  await ev(([ff]) => { const f = eval(ff); f.fv_saveMsgYn = 'N'; f.fn_inputChk = 'Y'; f.fnSanctnRequstChk(); });
  const launched = await hook;
  log('결재요청: 상태 ' + await ev(([ff]) => eval(ff).dsCnsulRegist.getColumn(0, 'sclExpdStsSeCd')) + (launched ? ' — 기안기에서 draft.ps1 -Only route,task,pub' : ' — 기안기 URL 못 받음'));
  await page.waitForTimeout(3000);
}

module.exports = { runPumui, listBudgets, openPumuiForm };
