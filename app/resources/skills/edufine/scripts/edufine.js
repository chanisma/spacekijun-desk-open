#!/usr/bin/env node
/**
 * edufine — K-에듀파인 업무포털 CLI (화면 클릭 대신 포털 자체 함수·백엔드를 부른다)
 *
 *   node edufine.js setup                                  데이터 폴더·설정 틀 만들기
 *   node edufine.js session start|status|stop              로그인 세션 열어 두기(start 는 백그라운드로)
 *   node edufine.js ledger status | update [--from D] [--to D]   문서등록대장 캐시 현황 / 받기
 *   node edufine.js search <낱말...> [--from D] [--to D] [--type 접수|생산] [--limit N]
 *   node edufine.js find <번호> [--year YYYY]              번호 → 날짜·제목 (번호는 해마다 다시 시작)
 *   node edufine.js info <번호[:YYYY-MM-DD]> ...           제목·첨부 목록
 *   node edufine.js get  <번호[:YYYY-MM-DD]> ... [--out 폴더] [--no-att] [--no-body] [--flat]
 *   node edufine.js forms                                  공용서식 목록
 *   node edufine.js draft-open [--form "표준서식(결재4인,협조4인)"]   기안기 열기 → 이어서 draft.ps1
 *   node edufine.js budgets                                품의할 수 있는 예산(산출내역·잔액)
 *   node edufine.js pumui <spec.json> [--step fill|save|request]
 *   node edufine.js run <작업.js>                           열어 둔 세션에서 사용자 작업 실행 (module.exports = async ({ctx,page,log}) => {})
 *   공통: --json
 */
const fs = require('fs');
const path = require('path');
const cfg = require('./lib/config.js');

const VALUE = new Set(['--from', '--to', '--type', '--limit', '--year', '--out', '--form', '--step']);
function parse(argv) {
  const o = { json: false, body: true, att: true, flat: false }, rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') o.json = true; else if (a === '--no-att') o.att = false; else if (a === '--no-body') o.body = false; else if (a === '--flat') o.flat = true;
    else if (VALUE.has(a)) o[a.slice(2)] = argv[++i];
    else rest.push(a);
  }
  return { cmd: rest[0], sub: rest[1], args: rest.slice(1), o };
}
const today = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
const daysAgo = n => new Date(Date.now() + 9 * 3600e3 - n * 86400e3).toISOString().slice(0, 10);

function out(o, data, text) {
  if (o.json) return console.log(JSON.stringify(data, null, 1));
  if (text) return console.log(text(data));
  console.log(typeof data === 'string' ? data : JSON.stringify(data, null, 1));
}

/** 세션에 붙어 fn({ctx, page, log}) 실행 */
async function withSession(fn) {
  const S = require('./lib/session.js');
  const s = await S.open();
  const log = (...a) => console.log(...a);
  const onDialog = d => { log('[대화상자]', d.message().slice(0, 120)); d.accept().catch(() => { }); };
  s.portal.on('dialog', onDialog);
  try { return await fn({ ctx: s.ctx, page: s.portal, log }); }
  finally { s.portal.off('dialog', onDialog); await s.done(); }
}

const fmtDocs = rows => rows.length ? rows.map(r => `${r.일자} ${r.번호.padStart(5)} ${r.결재유형 || ''}  ${r.제목}${r.상대 ? '  | ' + r.상대.slice(0, 30) : ''}`).join('\n') + `\n(${rows.length}건)` : '(없음)';

async function main() {
  const { cmd, sub, args, o } = parse(process.argv.slice(2));
  if (!cmd || cmd === 'help' || cmd === '--help') {
    return console.log(fs.readFileSync(__filename, 'utf8').split('*/')[0].replace(/^#!.*\n\/\*\*\n?/, '').replace(/^ \* ?/gm, ''));
  }
  if (cmd === 'setup') {
    const r = cfg.setup();
    return out(o, r, r => `데이터 폴더: ${r.home}\n${r.made.length ? '만든 파일:\n  ' + r.made.join('\n  ') + '\n→ credentials.json 에 아이디·인증서 암호를 직접 적으세요.' : '이미 준비됨'}`);
  }
  if (cmd === 'session') {
    const S = require('./lib/session.js');
    if (sub === 'start') return S.keep();
    if (sub === 'stop') return out(o, await S.stop());
    return out(o, await S.status());
  }
  const D = require('./lib/docs.js');
  if (cmd === 'ledger') {
    if (sub === 'update') {
      const range = D.ledgerRange();
      const from = o.from || (range.마지막 ? range.마지막 : daysAgo(90)), to = o.to || today();
      return out(o, await D.updateLedger({ from, to }), r => `대장 ${r.기간} 총 ${r.총건수}건 → ${r.파일}`);
    }
    return out(o, D.ledgerRange(), r => `대장 캐시 ${r.건수}건 (${r.처음 || '-'} ~ ${r.마지막 || '-'}) — ${cfg.paths.ledger}`);
  }
  if (cmd === 'search') {
    if (!args.length) throw new Error('찾을 낱말을 주세요');
    let rows = D.search(args, { from: o.from, to: o.to, type: o.type });
    if (o.limit) rows = rows.slice(-Number(o.limit));
    return out(o, rows, fmtDocs);
  }
  if (cmd === 'find') return out(o, D.find(args[0], o.year), fmtDocs);
  if (cmd === 'info' || cmd === 'get') {
    const k = new D.Klef();
    try {
      const r = cmd === 'info' ? await D.cmdInfo(k, args, o) : await D.cmdGet(k, args, o);
      return out(o, r, rows => rows.map(r => r.파일
        ? `${r.번호} ${r.일자} ${r.상태}  ${r.제목 || ''}\n` + r.파일.map(f => `   ${f.경로 ? '✓' : '✗'} ${f.이름}${f.크기 ? ` (${Math.round(f.크기 / 1024)}KB)` : ''}${f.상태 ? ' — ' + f.상태 : ''}`).join('\n')
        : r.첨부 ? `${r.번호} ${r.일자} ${r.제목}\n   첨부: ${r.첨부.join(' / ') || '(없음)'}` : `${r.번호} ${r.일자} ${r.상태 || ''} ${r.제목 || ''}`).join('\n'));
    } finally { await k.close(); }
  }
  if (cmd === 'forms') return out(o, await withSession(({ ctx }) => require('./tasks/drafter.js').listForms(ctx)), rows => rows.map(r => `${r.분류}  ${r.이름}`).join('\n'));
  if (cmd === 'draft-open') {
    const name = o.form || '표준서식(결재4인,협조4인)';
    return out(o, await withSession(({ ctx, log }) => require('./tasks/drafter.js').openDrafter(ctx, name, log)), f => `기안기 열림: ${f.이름} — 이어서 draft.ps1 -Spec <spec.json>`);
  }
  if (cmd === 'budgets') {
    const rows = await withSession(x => require('./tasks/pumui.js').listBudgets(x));
    return out(o, rows, rows => rows.map(r => `${r.세부사업} / ${r.세부항목} / ${r.산출내역}  잔액 ${r.잔액.toLocaleString()}원`).join('\n') + `\n(${rows.length}건)`);
  }
  if (cmd === 'pumui') {
    if (!args[0]) throw new Error('spec.json 경로를 주세요');
    const spec = JSON.parse(fs.readFileSync(args[0], 'utf8').replace(/^﻿/, ''));
    return withSession(x => require('./tasks/pumui.js').runPumui(x, spec, o.step || 'fill'));
  }
  if (cmd === 'run') {
    const task = require(path.resolve(args[0]));
    return withSession(task);
  }
  throw new Error('모르는 명령: ' + cmd + ' (node edufine.js help)');
}

main().catch(e => { console.log('오류:', e.message); process.exitCode = 1; });
