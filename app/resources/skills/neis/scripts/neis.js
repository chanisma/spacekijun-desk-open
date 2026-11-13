#!/usr/bin/env node
/**
 * neis — 나이스(4세대) 조회 전용 CLI. 저장·마감·삭제 같은 «자료를 바꾸는» 버튼은 누르지 않는다.
 *
 * 준비·세션
 *   node neis.js setup [--from-edufine]                  데이터 폴더·설정 틀 (edufine 의 인증서 암호 가져오기)
 *   node neis.js session start|status|stop               로그인 세션(start 는 백그라운드로)
 *
 * 지식(로그인 없이)
 *   node neis.js find <하고 싶은 말> [--role 교과|학급|동아리] [--limit N]   어느 화면에서 하나
 *   node neis.js guide <화면이름>                         화면 사용법(먼저 할 일·순서·주의)
 *   node neis.js rules <낱말>                             «A 안 하면 B 가 비어 보임» 규칙
 *   node neis.js workflow <낱말|월>                       시기별 업무 달력
 *
 * 화면
 *   node neis.js tabs                                    상단 탭(이 계정 업무분장)
 *   node neis.js menu <낱말>                              메뉴 검색 결과(경로 포함)
 *   node neis.js open <화면이름> [--path "탭 > … 일부"]     화면 열기
 *   node neis.js text [--limit N]                        지금 화면 글자
 *   node neis.js buttons                                 화면 버튼과 성격(조회/출력/이동/쓰기)
 *   node neis.js click <버튼>                             조회·출력 계열만 누른다(쓰기 버튼은 거절)
 *   node neis.js date <2026.09.10.>                      일자 칸 맞추기
 *   node neis.js tab <화면 안 탭이름>                      화면 안쪽 큰 탭
 *   node neis.js data [--app id일부] [--rows N] [--only ds1,ds2] [--cols c1,c2]   화면 뒤 DataSet 구조/값
 *   node neis.js popups | close-screens | shot <파일.png>
 *
 * 교사용
 *   node neis.js attendance --list                              내 과목 목록
 *   node neis.js attendance --subject <과목(반) 일부> [--until YYYYMMDD] [--out 파일]   과목별출결
 *   node neis.js absence --date YYYY-MM-DD [--out 파일]          일일근무상황
 *
 * 부장용(권한 필요)
 *   node neis.js records [--grades 1,2] [--classes 1,3] [--sections sewteuk,behavior] [--tab 탭] [--out 폴더]
 *   node neis.js records-merge <폴더>                       받은 학생부 XLSX → 항목별 정리 엑셀
 *   node neis.js timetable [--grades 1] [--classes 1,2] [--tab 탭] [--out 폴더]  (+ 자동 flat CSV)
 *   node neis.js questions --exams "1차 정기시험,2차 정기시험" --grades 1,2,3 [--out 파일.csv]
 *   node neis.js answers   --exams "1차 정기시험" --grades 1 [--long] [--out 폴더]
 *   공통: --json
 */
const fs = require('fs');
const cfg = require('./lib/config.js');

const VALUE = new Set(['--subject', '--role', '--limit', '--path', '--app', '--rows', '--only', '--cols', '--until', '--out', '--date', '--grades', '--classes', '--sections', '--tab', '--exams']);
function parse(argv) {
  const o = { json: false }, rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') o.json = true; else if (a === '--from-edufine') o.fromEdufine = true; else if (a === '--long') o.long = true; else if (a === '--list') o.list = true;
    else if (VALUE.has(a)) o[a.slice(2)] = argv[++i]; else rest.push(a);
  }
  return { cmd: rest[0], args: rest.slice(1), o };
}
const show = (o, data, text) => console.log(o.json ? JSON.stringify(data, null, 1) : text ? text(data) : (typeof data === 'string' ? data : JSON.stringify(data, null, 1)));

async function withPage(fn) {
  const S = require('./lib/session.js');
  const { page } = await S.attach();
  page.on('dialog', d => d.dismiss().catch(() => { }));        // 브라우저 기본 confirm/alert 는 취소
  return fn(page);
}

async function main() {
  const { cmd, args, o } = parse(process.argv.slice(2));
  if (!cmd || cmd === 'help' || cmd === '--help')
    return console.log(fs.readFileSync(__filename, 'utf8').split('*/')[0].replace(/^#!.*\n\/\*\*\n?/, '').replace(/^ \* ?/gm, ''));

  if (cmd === 'setup') {
    const r = cfg.setup({ fromEdufine: o.fromEdufine });
    return show(o, r, r => `데이터 폴더: ${r.home}\n${r.made.length ? '만든 파일:\n  ' + r.made.join('\n  ') + '\n→ credentials.json 의 인증서 암호를 확인·작성하세요.' : '이미 준비됨'}`);
  }
  if (cmd === 'session') {
    const S = require('./lib/session.js');
    if (args[0] === 'start') return S.keep();
    if (args[0] === 'stop') return show(o, await S.stop());
    return show(o, await S.status());
  }

  // ── 지식 ──
  const K = () => require('./lib/know.js');
  if (cmd === 'find') return show(o, K().findScreens(args.join(' '), { limit: Number(o.limit || 10), role: o.role || '' }),
    rs => rs.length ? rs.map(r => `${r.화면}  [${r.역할}]\n   ${r.경로}\n   ${r.용도}${r.안내 ? '  (guide 있음)' : ''}`).join('\n') : '(없음)');
  if (cmd === 'guide') {
    const gs = K().getGuide(args.join(' '));
    return show(o, gs, gs => gs.length ? gs.map(g => [
      `■ ${g.key.replace(/›/g, ' › ')}`, `목적: ${g.purpose}`, g.context && `맥락: ${g.context}`, g.who && `누가: ${g.who}`,
      g.before && g.before.length && '먼저 할 일:\n  - ' + g.before.join('\n  - '),
      ...(g.flows || []).map(f => `[${f.title}]${f.when ? ' (' + f.when + ')' : ''}\n` + (f.steps || []).map((s, i) => `  ${i + 1}. ${s.text}${s.detail ? '\n     ' + s.detail : ''}`).join('\n')),
      g.cautions && g.cautions.length && '주의:\n  - ' + g.cautions.map(c => typeof c === 'string' ? c : c.text).join('\n  - '),
      g.after && g.after.length && '다음 할 일:\n  - ' + g.after.join('\n  - '),
      g.faq && g.faq.length && 'FAQ:\n' + g.faq.map(f => `  Q. ${f.q}\n  A. ${f.a}`).join('\n'),
    ].filter(Boolean).join('\n')).join('\n\n') : '(안내 없음 — find 로 화면 이름을 먼저 확인)');
  }
  if (cmd === 'rules') return show(o, K().grepDoc('RULES.md', args.join(' ')), b => b.join('\n\n') || '(없음)');
  if (cmd === 'workflow') return show(o, K().grepDoc('WORKFLOW.md', args.join(' ')), b => b.join('\n') || '(없음)');

  // ── 화면 ──
  const nav = require('./lib/nav.js');
  if (cmd === 'tabs') return withPage(async p => show(o, await nav.tabs(p)));
  if (cmd === 'menu') return withPage(async p => show(o, await nav.searchMenu(p, args.join(' ')), rs => rs.map(r => `${r.name}\n   ${r.path}`).join('\n') || '(없음)'));
  if (cmd === 'open') return withPage(async p => {
    try { show(o, await nav.openScreen(p, args.join(' '), { path: o.path || '' })); }
    catch (e) { if (e.candidates) { console.log(e.message); process.exitCode = 2; } else throw e; }
  });
  if (cmd === 'text') return withPage(async p => show(o, await nav.screenText(p, Number(o.limit || 6000))));
  if (cmd === 'buttons') return withPage(async p => show(o, await nav.listButtons(p), bs => bs.map(b => `${b.성격.padEnd(8)} ${b.버튼}`).join('\n')));
  if (cmd === 'click') return withPage(async p => show(o, await nav.clickButton(p, args.join(' '))));
  if (cmd === 'date') return withPage(async p => show(o, await nav.setDate(p, args[0])));
  if (cmd === 'tab') return withPage(async p => show(o, await nav.clickInnerTab(p, args.join(' '))));
  if (cmd === 'popups') return withPage(async p => show(o, await nav.closePopups(p)));
  if (cmd === 'close-screens') return withPage(async p => show(o, `${await nav.closeScreens(p)}개 닫음`));
  if (cmd === 'shot') return withPage(async p => { await p.screenshot({ path: args[0] || 'neis-shot.png' }); show(o, '저장: ' + (args[0] || 'neis-shot.png') + '  (학생 정보가 보이면 쓰고 나서 지울 것)'); });
  if (cmd === 'data') return withPage(async p => show(o, await require('./lib/cleo.js').dumpData(p, { app: o.app || '', rows: Number(o.rows || 0), only: o.only || '', cols: o.cols || '' })));

  // ── 교사용 ──
  const T = () => require('./tasks/teacher.js');
  if (cmd === 'attendance') return withPage(async p => show(o, await T().attendance(p, { until: o.until, out: o.out, subject: o.subject, list: o.list })));
  if (cmd === 'absence') { if (!o.date) throw new Error('--date YYYY-MM-DD'); return withPage(async p => show(o, await T().absence(p, { date: o.date, out: o.out }), r => `${r.일자} ${r.건수}건 → ${r.파일}\n` + Object.entries(r.요약).map(([k, v]) => `  ${k} ${v}`).join('\n'))); }

  // ── 부장용 ──
  const B = () => require('./tasks/bulk.js');
  if (cmd === 'records') return withPage(async p => show(o, await B().records(p, { grades: o.grades, classes: o.classes, sections: o.sections, tab: o.tab, out: o.out })));
  if (cmd === 'records-merge') return show(o, B().recordsMerge(args[0]));
  if (cmd === 'timetable') return withPage(async p => { const r = await B().timetable(p, { grades: o.grades, classes: o.classes, tab: o.tab, out: o.out }); if (r.받음) r.csv = B().timetableCsv(r.폴더); show(o, r); });
  if (cmd === 'questions') { if (!o.exams || !o.grades) throw new Error('--exams, --grades 필요'); return withPage(async p => show(o, await B().questions(p, { exams: o.exams, grades: o.grades, out: o.out }))); }
  if (cmd === 'answers') { if (!o.exams || !o.grades) throw new Error('--exams, --grades 필요'); return withPage(async p => show(o, await B().answers(p, { exams: o.exams, grades: o.grades, out: o.out, long: o.long }))); }

  throw new Error('모르는 명령: ' + cmd + ' (node neis.js help)');
}

main().then(() => process.exit(process.exitCode || 0))       // 붙은 브라우저는 닫지 않고 프로세스만 끝낸다
  .catch(e => { console.log('오류:', e.message); process.exit(1); });
