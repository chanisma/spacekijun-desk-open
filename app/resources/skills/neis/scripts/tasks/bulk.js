/**
 * 부장(나이스부·정보화부 등) 권한용 일괄 조회·내려받기 — 모두 조회 전용, 저장·마감·삭제 버튼은 누르지 않는다.
 *   records    학생부 항목별 조회 → 학년·반·항목별 XLSX (Crownix 리포트 [저장]→[XLS Data])
 *   timetable  학생별시간표조회 → 반별 XLSX → flat CSV
 *   questions  문항정보표관리 → CSV (DataSet dsObt/dsSbjct/dsCoranAllot)
 *   answers    정기시험학생답관리 → 학생별 답안 CSV (submission 직접 호출)
 * 화면 안 동작은 inject/*.js 를 페이지에 주입해 쓰고, 순회·다운로드 저장은 여기서 한다(내보내기 1회 = 다운로드 1건).
 * ⚠ 결과는 전교생 개인정보다. 필요한 만큼만 받고, 쓰고 나면 지운다. 외부 서비스로 보내지 않는다.
 */
const fs = require('fs');
const path = require('path');
const nav = require('../lib/nav.js');
const { paths } = require('../lib/config.js');
const INJ = n => path.join(__dirname, '..', 'inject', n);
const bom = t => '﻿' + String(t).replace(/^﻿/, '');   // 엑셀용 BOM 하나만
const same = (a, b) => !!a && !!b && (String(a).includes(b) || String(b).includes(a));

/** 이 계정에서 화면이 어느 탭에 있는지 메뉴 검색으로 알아낸다 (탭 이름은 학교·업무분장마다 다르다) */
async function tabOf(page, screen, prefer = '') {
  const rs = await nav.searchMenu(page, screen);
  const hit = rs.filter(r => r.path.includes(screen));
  if (!hit.length) throw new Error(`'${screen}' 이(가) 이 계정 메뉴에 없습니다 (권한 확인)`);
  const pick = (prefer && hit.find(r => r.tab.includes(prefer))) || hit.find(r => /부서장/.test(r.tab)) || hit[0];
  return pick.tab;
}

/** 페이지 주입 — 매번 최신 스크립트로 다시 넣는다(쌓인 결과 window.__RESULT/__SAROWS 는 스크립트가 보존한다) */
async function inject(page, file) {
  await page.addScriptTag({ path: INJ(file) });
}

// ── 학생부 항목별 ─────────────────────────────────────────
const SECTIONS = ['history', 'hakjeok', 'attend', 'volunteer', 'creative', 'subject', 'sewteuk', 'reading', 'behavior'];

async function records(page, { grades, classes, sections, tab, out, log = console.log } = {}) {
  const dir = out || path.join(paths.out, '학생부');
  fs.mkdirSync(dir, { recursive: true });
  await nav.closePopups(page);
  const tabName = tab || await tabOf(page, '학교생활기록부');
  await inject(page, 'records.js', '__NEISR');
  log(`탭: ${tabName}`);
  await page.evaluate(t => window.__NEISR.goto(t), tabName);
  const secs = sections ? sections.split(',') : SECTIONS;
  const allGrades = await page.evaluate(() => window.__NEISR.listGrades());
  const done = [], fail = [];
  for (const g of allGrades.filter(x => !grades || grades.split(',').some(w => same(x, w)))) {
    await page.evaluate(gr => window.__NEISR.selectOption('계열/학년/학과', gr), g);
    const cls = await page.evaluate(() => window.__NEISR.listClasses());
    for (const c of cls.filter(x => !classes || classes.split(',').some(w => same(x, w)))) {
      await page.evaluate(a => window.__NEISR.prepare(a.g, a.c), { g, c });
      for (const key of secs) {
        await page.evaluate(k => window.__NEISR.openSection(k), key);
        await page.waitForTimeout(2000);                   // 렌더 안정화 — 없으면 저장 클릭이 조용히 무시된다
        const st = await page.evaluate(() => window.__NEISR.status());
        if (!st.리포트준비 || !same(st.학년, g) || !same(st.반, c)) { fail.push(`${g}/${c}/${key}: 준비 안 됨`); continue; }
        try {
          const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 180000 }), page.evaluate(() => window.__NEISR.fireExport('xls_data'))]);
          const name = await page.evaluate(a => window.__NEISR.fileName(a.g, a.c, a.k), { g: parseInt(g), c: parseInt(c), k: key });
          await dl.saveAs(path.join(dir, name)); done.push(name); log('✓ ' + name);
        } catch (e) { fail.push(`${g}/${c}/${key}: ${e.message.split('\n')[0]}`); }
      }
    }
  }
  return { 폴더: dir, 받음: done.length, 실패: fail };
}

// ── 학생별 시간표 ─────────────────────────────────────────
async function timetable(page, { grades, classes, tab, out, log = console.log } = {}) {
  const dir = out || path.join(paths.out, '시간표');
  fs.mkdirSync(dir, { recursive: true });
  await nav.closePopups(page);
  const tabName = tab || await tabOf(page, '학생별시간표조회');
  await inject(page, 'timetable.js', '__NEIST');
  log(`탭: ${tabName}`);
  await page.evaluate(t => window.__NEIST.goto(t), tabName);
  const allGrades = await page.evaluate(() => window.__NEIST.listGrades());
  const files = [], fail = [];
  for (const g of allGrades.filter(x => !grades || grades.split(',').some(w => same(x, w)))) {
    await page.evaluate(gr => window.__NEIST.selectOption('계열/학년/학과', gr), g);
    const cls = await page.evaluate(() => window.__NEIST.listClasses());
    for (const c of cls.filter(x => !classes || classes.split(',').some(w => same(x, w)))) {
      if (!await page.evaluate(a => window.__NEIST.prepare(a.g, a.c), { g, c })) { fail.push(`${g}/${c}: 조회 실패`); continue; }
      const st = await page.evaluate(() => window.__NEIST.status());
      if (!st.학생수 || !same(st.학년, g) || !same(st.학급, c)) continue;      // 빈 반
      if (!await page.evaluate(() => window.__NEIST.printSelected())) { fail.push(`${g}/${c}: 선택출력 실패`); continue; }
      try {
        const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 180000 }), page.evaluate(() => window.__NEIST.fireExport('xls_data'))]);
        const ext = dl.suggestedFilename().split('.').pop() || 'xlsx';
        const name = await page.evaluate(a => window.__NEIST.fileName(a.g, a.c, a.e), { g: parseInt(g), c: parseInt(c), e: ext });
        const f = path.join(dir, name); await dl.saveAs(f); files.push(f); log('✓ ' + name);
      } catch (e) { fail.push(`${g}/${c}: ${e.message.split('\n')[0]}`); }
    }
  }
  return { 폴더: dir, 받음: files.length, 실패: fail, files };
}

/** 받은 시간표 XLSX 들 → flat CSV (학년,반,번호,성명,요일,교시,과목,교사,교실) */
function timetableCsv(dir, outCsv) {
  global.XLSX = require('xlsx');
  const TP = eval(fs.readFileSync(path.join(__dirname, '..', 'vendor', 'timetable-preprocessor.js'), 'utf8') + '; TimetablePreprocessor');
  const rs = fs.readdirSync(dir).filter(f => /^Timetable_Grade\d+_Class\d+\.xlsx?$/i.test(f))
    .map(f => TP.preprocess(new Uint8Array(fs.readFileSync(path.join(dir, f))), f));
  const merged = TP.mergeResults(rs);
  const file = outCsv || path.join(dir, 'timetable.csv');
  fs.writeFileSync(file, TP.toCSV(merged));            // toCSV 가 BOM 을 붙인다
  return { 파일: file, 반: rs.length };
}

/** 받은 학생부 XLSX 들 → 항목별 정리 엑셀 (반,학년,학기,번호,성명,과목,내용) */
function recordsMerge(dir, outXlsx) {
  global.XLSX = require('xlsx');
  const PP = eval(fs.readFileSync(path.join(__dirname, '..', 'vendor', 'record-preprocessor.js'), 'utf8') + '; Preprocessor');
  const files = fs.readdirSync(dir).filter(f => /^Grade\d+_Class\d+_.+\.xlsx?$/i.test(f));
  const bySection = {};
  for (const f of files) {
    const sec = f.replace(/^Grade\d+_Class\d+_/, '').replace(/\.xlsx?$/i, '');
    const r = PP.preprocess(new Uint8Array(fs.readFileSync(path.join(dir, f))), f);
    (bySection[sec] = bySection[sec] || []).push(r);
  }
  const outs = [];
  for (const [sec, rs] of Object.entries(bySection)) {
    const merged = PP.mergeResults(rs);
    if (!merged.length) { outs.push({ 항목: sec, 행: 0, 비고: '정리 대상 아님(과목·내용형 항목만 정리됨: 세특·창체·교과 등) — 원본 XLSX 를 쓴다' }); continue; }
    const head = ['반', '학년', '학기', '번호', '성명', '과목', '내용'];
    const ws = XLSX.utils.aoa_to_sheet([head, ...merged.map(r => head.map(h => r[h]))]);
    ws['!cols'] = [5, 5, 5, 5, 10, 15, 100].map(wch => ({ wch }));
    const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, sec.slice(0, 31));
    const f = path.join(outXlsx || dir, `정리_${sec}.xlsx`);
    XLSX.writeFile(wb, f); outs.push({ 파일: f, 행: merged.length });
  }
  return { 파일: outs };
}

// ── 문항정보표 / 학생답 ───────────────────────────────────
async function questions(page, { exams, grades, tab, out, log = console.log } = {}) {
  await nav.closePopups(page);
  await nav.openScreen(page, '문항정보표관리', { path: tab || await tabOf(page, '문항정보표관리') });   // 부서장 탭 우선(전 과목), 없으면 교과담임(내 과목)
  await inject(page, 'questions.js', '__NEISQ');
  for (const exam of exams.split(',')) for (const grade of grades.split(',')) {
    const r = await page.evaluate(a => window.__NEISQ.runChunk(a.exam, a.grade).then(x => JSON.stringify(x)), { exam, grade });
    log(`${exam} ${grade}학년: ${String(r).slice(0, 200)}`);
  }
  const csv = await page.evaluate(() => window.__NEISQ.toCSV());
  const file = out || path.join(paths.out, '문항정보표.csv');
  fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, bom(csv));
  return { 파일: file, 과목고사: await page.evaluate(() => window.__RESULT.length) };
}

async function answers(page, { exams, grades, tab, out, long = false, log = console.log } = {}) {
  await nav.closePopups(page);
  await nav.openScreen(page, '정기시험학생답관리', { path: tab || await tabOf(page, '정기시험학생답관리') });
  await inject(page, 'answers.js', '__SA');
  const dir = out || paths.out; fs.mkdirSync(dir, { recursive: true });
  for (const exam of exams.split(',')) for (const grade of grades.split(',')) {
    const r = await page.evaluate(a => window.__SA.runChunk(a.exam, a.grade).then(x => JSON.stringify(x)), { exam, grade });
    log(`${exam} ${grade}학년: ${String(r).slice(0, 200)}`);
    // 청크마다 백업 — 세션이 끊기면 메모리 결과가 날아간다 (복구: __SA.restore(rows))
    fs.writeFileSync(path.join(dir, '학생답_백업.json'), JSON.stringify(await page.evaluate(() => window.__SAROWS)));
  }
  const file = path.join(dir, '정기시험학생답.csv');
  fs.writeFileSync(file, bom(await page.evaluate(() => window.__SA.toCSV())));
  const res = { 파일: file, 학생행: await page.evaluate(() => window.__SAROWS.length) };
  if (long) { const lf = path.join(dir, '정기시험학생답_문항별.csv'); fs.writeFileSync(lf, bom(await page.evaluate(() => window.__SA.toLongCSV()))); res.문항별 = lf; }
  return res;
}

module.exports = { records, recordsMerge, timetable, timetableCsv, questions, answers, SECTIONS };
