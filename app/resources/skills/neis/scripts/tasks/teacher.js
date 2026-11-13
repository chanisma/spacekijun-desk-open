/**
 * 교사용 조회 작업 (저장·마감 없음)
 *   attendance — 과목별출결관리: 지금 화면에서 고른 과목의 수업일별 학생 출결(`/` 입력 + 일일출결 정보)
 *   absence    — 일일근무상황조회: 그날 교직원 출장·연가·외출·조퇴 등
 */
const fs = require('fs');
const path = require('path');
const nav = require('../lib/nav.js');
const { paths } = require('../lib/config.js');
const DOW = ['일', '월', '화', '수', '목', '금', '토'];

// ── 과목별출결 ────────────────────────────────────────────
const ATT_APP = 'edu/sw/his/srg/aa/his_srgaa04_m01';   // ...m00 은 화면 위 탭 껍데기

/**
 * 과목별출결관리 화면을 열고(이미 열려 있으면 그대로), **화면에서 고른 과목**의 수업일을 하나씩 실제 클릭해
 * dsListCurrHrAtteStu 를 모은다. 과목 고르기(과목순·과목·[조회])는 사람이 하거나 미리 해 둔다.
 *  - 수업일 선택은 실제 마우스 클릭만 먹는다(selectRows·dispatchEvent 무시) — 클릭 뒤 cmbAtteYmd 값으로 검증
 *  - 목록에는 미래 수업일도 있다 → until(yyyymmdd) 까지만
 *  - 학생 이름(stuFlnm)은 저장하지 않는다
 */
/** 과목순으로 바꾸고 내 과목 목록(dsListSbjt) — [{코드, 과목}] */
async function attendanceSubjects(page) {
  const rdb = await page.evaluate(app => cpr.core.Platform.INSTANCE.getAllRunningAppInstances().filter(x => x.id.startsWith(app)).pop().lookup('rdbSelect').value, ATT_APP);
  if (rdb !== '2') {   // 1 = 일자순, 2 = 과목순 — 라디오는 실제 클릭
    await page.locator('.cl-radiobutton .cl-text, div.cl-text').filter({ hasText: /^과목순$/ }).locator('visible=true').first().click({ timeout: 10000 });
    await page.waitForTimeout(2000); await nav.waitLoading(page);
  }
  return page.evaluate(app => cpr.core.Platform.INSTANCE.getAllRunningAppInstances().filter(x => x.id.startsWith(app)).pop()
    .lookup('dsListSbjt').getRowDataRanged().map(r => ({ 코드: r.etbSbjtCd, 과목: r.etbSbjtNm })), ATT_APP);
}

async function attendance(page, { until, out, subject, list = false, log = console.log } = {}) {
  const has = await page.evaluate(app => !!(window.cpr && cpr.core.Platform.INSTANCE.getAllRunningAppInstances().some(x => x.id.startsWith(app))), ATT_APP);
  if (!has) { log('과목별출결관리 화면을 엽니다'); await nav.openScreen(page, '과목별출결관리', { path: '교과담임' }); }
  if (list || subject) {
    const subs = await attendanceSubjects(page);
    if (list) return { 과목: subs };
    const norm = s => String(s).replace(/\s+/g, '');
    const hit = subs.filter(s => norm(s.과목).includes(norm(subject)));
    if (hit.length !== 1) throw new Error(hit.length ? `'${subject}' 에 맞는 과목이 여럿입니다: ${hit.map(h => h.과목).join(', ')}` : `'${subject}' 과목이 없습니다. 내 과목: ${subs.map(s => s.과목).join(', ')}`);
    await page.evaluate(([app, cd]) => { cpr.core.Platform.INSTANCE.getAllRunningAppInstances().filter(x => x.id.startsWith(app)).pop().lookup('cmbAtteSbjt').value = cd; }, [ATT_APP, hit[0].코드]);
    await nav.clickButton(page, '조회');
    log(`과목 선택: ${hit[0].과목}`);
  }
  const info = await page.evaluate(app => {
    const A = cpr.core.Platform.INSTANCE.getAllRunningAppInstances().filter(x => x.id.startsWith(app)).pop();
    const sb = A.lookup('cmbAtteSbjt');
    return { 과목: sb ? (sb.text || sb.value) : '', dates: A.lookup('dsListChrgeTcrPir').getRowDataRanged().map(r => ({ ymd: r.allTiYmd, pir: r.pir, grd: r.grd, sbjt: r.etbSbjtNm, cls: r.clsNm })) };
  }, ATT_APP);
  const last = until || new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, '');
  const targets = info.dates.filter(d => d.ymd <= last);
  if (!info.dates.length) throw new Error('수업일 목록이 비어 있습니다. 화면에서 [과목순]·과목을 고르고 [조회]한 뒤 다시 실행하세요.');
  log(`과목: ${info.과목 || info.dates[0].sbjt} — 수업일 ${info.dates.length} 중 ${last} 까지 ${targets.length}일`);
  const result = [];
  for (const d of targets) {
    const y = +d.ymd.slice(0, 4), m = +d.ymd.slice(4, 6), dd = +d.ymd.slice(6, 8);
    const label = `${y}.${String(m).padStart(2, '0')}.${String(dd).padStart(2, '0')}.(${DOW[new Date(y, m - 1, dd).getDay()]})`;
    const rx = new RegExp('^' + label.replace(/[.()]/g, '\\$&') + '$');
    const loc = page.locator('div.cl-text').filter({ hasText: rx }).first();
    if (!await loc.count()) { result.push({ ...d, error: '행 없음' }); continue; }
    await loc.scrollIntoViewIfNeeded({ timeout: 8000 }).catch(() => { });
    await loc.click({ timeout: 10000 });
    await page.waitForTimeout(1800); await nav.waitLoading(page);
    const rec = await page.evaluate(app => {
      const A = cpr.core.Platform.INSTANCE.getAllRunningAppInstances().filter(x => x.id.startsWith(app)).pop();
      return { ymd: A.lookup('cmbAtteYmd').value, rows: A.lookup('dsListCurrHrAtteStu').getRowDataRanged().map(r => ({
        학번: r.stuInvlNo, 반: r.clsNm, 번호: r.clsNo, 결과입력: (r.chulScCd || '').trim(), 출결정보: r.atteScNm || '', 비고: r.atteRmkCn || '', 일일비고: r.dayAtteRmkCn || '', 마감: r.atteDdlnYn || '' })) };
    }, ATT_APP);
    if (rec.ymd !== d.ymd) { result.push({ ...d, error: `날짜 불일치(${rec.ymd})` }); continue; }
    result.push({ ...d, n: rec.rows.length, rows: rec.rows });
    log(`${d.ymd} ${d.pir}교시 학생 ${rec.rows.length} · 결과(/) ${rec.rows.filter(r => r.결과입력).length} · 정보 ${rec.rows.filter(r => r.출결정보).length}`);
  }
  // 요약: 출결 정보 종류별, '/' 있음/없음
  const sum = {}; let slash = 0, infoOnly = 0;
  for (const d of result) for (const r of d.rows || []) {
    if (r.결과입력) slash++; else if (r.출결정보) infoOnly++;
    if (r.출결정보) sum[r.출결정보] = (sum[r.출결정보] || 0) + 1;
  }
  const file = out || path.join(paths.out, `과목별출결_${last}.json`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ 과목: info.과목, 기준일: last, 수업일: result }, null, 1));
  return { 파일: file, 수업일: result.length, 오류: result.filter(r => r.error).length, '결과(/)': slash, '정보만': infoOnly, 종류별: sum };
}

// ── 일일근무상황 ──────────────────────────────────────────
const ABS_APP = 'edu/ga/srv/mym/mm/srv_mymmm01_m00';

/** 날짜(YYYY-MM-DD) 하나의 일일근무상황. 일자 칸은 마스크라 타이핑 대신 컨트롤 값으로 넣는다. */
async function absence(page, { date, out, log = console.log } = {}) {
  const ymd = String(date).replace(/-/g, '');
  const has = await page.evaluate(app => !!(window.cpr && cpr.core.Platform.INSTANCE.getAllRunningAppInstances().some(x => x.id.startsWith(app))), ABS_APP);
  if (!has) {
    log('일일근무상황조회 화면을 엽니다');
    try { await nav.openScreen(page, '일일근무상황조회'); }
    catch (e) { await nav.openSidebar(page, ['복무', '일일근무상황조회']); }   // 기본 메뉴(개인)는 메뉴 검색에 안 나온다
  }
  await page.evaluate(([app, ymd]) => {
    const A = cpr.core.Platform.INSTANCE.getAllRunningAppInstances().filter(x => x.id.startsWith(app)).pop();
    A.lookup('dtiWorkYmd').value = ymd;
  }, [ABS_APP, ymd]);
  await nav.clickButton(page, '조회');
  const r = await page.evaluate(([app]) => {
    const A = cpr.core.Platform.INSTANCE.getAllRunningAppInstances().filter(x => x.id.startsWith(app)).pop();
    const set = A.lookup('dtiWorkYmd').value;
    // 결과 그리드 DataSet: 행이 가장 많은 것
    const ds = (A.getAllDataControls ? A.getAllDataControls() : []).filter(d => d.getRowCount).sort((p, q) => q.getRowCount() - p.getRowCount())[0];
    return { set, rows: ds ? ds.getRowDataRanged() : [] };
  }, [ABS_APP]);
  if (r.set !== ymd) throw new Error(`일자가 바뀌지 않았습니다(${r.set})`);
  const text = await nav.screenText(page, 8000);
  const file = out || path.join(paths.out, `일일근무상황_${ymd}.json`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ 일자: ymd, 행: r.rows, 화면: text }, null, 1));
  // 이름·사유는 파일에만 — 화면에는 근무상황별 건수만 (건강 정보가 섞여 있다)
  const 요약 = {};
  for (const row of r.rows) { const k = row.workSittnNm || row.근무상황 || '기타'; 요약[k] = (요약[k] || 0) + 1; }
  return { 파일: file, 일자: ymd, 건수: r.rows.length, 요약 };
}

module.exports = { attendance, absence };
