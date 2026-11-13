/**
 * 문서 찾기·받기 백엔드 (CLI-Anything 방식 — 화면 클릭 대신 포털 자체 함수를 부른다)
 *
 *   대장 캐시: <데이터폴더>/ledger/대장_*.csv (문서등록대장 CSV, EUC-KR) — 오프라인 검색
 *   대장 갱신: 문서등록대장 화면에서 기간 조회 → fncIseIseXlsDwl('a') CSV 내보내기
 *   문서 정보: Capi.getApprovalInfo(id) → {title, docRegNo, fileNames[], fileObjectIDs[]}
 *   본문:     /bms/cz/cb/wrt/retrieveDocFile.do?UID&DID&apprID=<mk_apprid(id,'01')>&fileType=attach  (ODT)
 *   첨부:     같은 주소, apprID=<fileObjectIDs[i]>   제외: 끝 '060'(이관용 PDF), 'HOX_file'
 *
 * 지키는 것 (공식 [PC저장]과 같은 권한·기록)
 *   - 열람 권한: 목록에서 체크 → doCallFileManagerExtra 가 걸러 준 APPRIDLIST 만 받는다
 *   - 접근 기록: 받을 때마다 createAccesLogHist(id, fileId, 'hwpsave'|'attsave')
 *   - 읽기 전용: 결재·발송·삭제 함수는 부르지 않는다. 한 건씩, 건 사이 0.5~1.2초
 */
const fs = require('fs');
const path = require('path');
const K = require('./portal.js');
const S = require('./session.js');
const { paths } = require('./config.js');
const LEDGER = paths.ledger;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ── 대장 캐시 (오프라인) ───────────────────────────────────────────
let _ledger = null;
function ledger() {
  if (_ledger) return _ledger;
  _ledger = [];
  if (!fs.existsSync(LEDGER)) return _ledger;
  for (const f of fs.readdirSync(LEDGER).filter(f => /^대장_.*\.csv$/.test(f))) {
    let csv; try { csv = K.readCsvEucKr(path.join(LEDGER, f)); } catch (e) { continue; }
    for (const v of csv.행) {
      const r = Object.fromEntries(csv.헤더.map((h, i) => [h, v[i]]));
      const no = String(r['문서번호'] || '');
      if (!no.includes('-')) continue;
      _ledger.push({ 문서번호: no, 번호: no.split('-').pop(), 일자: String(r['등록일자'] || '').slice(0, 10), 제목: r['제목'], 결재유형: r['결재유형'], 상대: r['수신(발신)자'] || '', 담당: r['결재권자'] || '', 공개: r['공개구분'] || '', 처리상태: r['처리상태'] });
    }
  }
  return _ledger;
}
function find(no, year) {
  no = String(no).split('-').pop();
  const seen = new Set();
  return ledger().filter(r => r.번호 === no && (!year || r.일자.startsWith(String(year))))
    .filter(r => { const k = r.문서번호 + r.일자; if (seen.has(k)) return false; seen.add(k); return true; })
    .sort((a, b) => a.일자.localeCompare(b.일자));
}

// "11689:2026-09-17" | "11689" (+ --year) → {번호, 일자}
function parseTarget(t, year) {
  const [n, d] = String(t).split(':');
  const 번호 = n.split('-').pop();
  if (d) return { 번호, 일자: d };
  const hits = find(번호, year);
  if (hits.length === 1) return { 번호, 일자: hits[0].일자 };
  const e = new Error(hits.length ? `${번호}: 같은 번호가 ${hits.length}개 해에 있음 — 번호:날짜 또는 --year 로 고르세요 (${hits.map(h => h.일자 + ' ' + h.제목).join(' / ')})` : `${번호}: 대장 캐시에 없음 — 번호:YYYY-MM-DD 로 날짜를 주세요`);
  e.candidates = hits; throw e;
}

// ── 세션 위의 백엔드 ──────────────────────────────────────────────
class Klef {
  async open() { if (!this.s) this.s = await S.open(); return this; }
  async close() { if (this.bdt) await this.bdt.close().catch(() => { }); if (this.list) await this.list.close().catch(() => { }); if (this.s) await this.s.done(); this.s = null; }
  get ctx() { return this.s.ctx; }

  async listPage() {
    if (this.list && !this.list.isClosed()) return this.list;
    const p = await this.ctx.newPage(); K.autoDialog(p, []);
    await p.route('**/connectWXSClient.do', async r => { this._wxs = r.request().postData(); await r.abort(); });
    await p.route('wxsclient://**', r => r.abort()).catch(() => { });
    await K.openScreen(p, '문서등록대장');
    return (this.list = p);
  }

  /** 그 날짜를 조회해 번호들을 체크하고 [PC저장]을 태워 포털이 허용한 문서 ID 를 받는다 */
  async select(date, nos) {
    const p = await this.listPage();
    await K.search(p, { from: date, to: date, pageUnit: 100 });
    const rows = await p.evaluate(nos => {
      const out = [];
      for (const cb of document.querySelectorAll('#tbList tbody input[name="docinfo"]')) {
        const v = cb.value.split(','); const no = (v[16] || '').split('-').pop();
        cb.checked = nos.includes(no);
        if (cb.checked) { cb.dispatchEvent(new Event('click', { bubbles: true })); cb.checked = true; out.push({ 번호: no, id: v[0], 제목: cb.title || '' }); }
      }
      return out;
    }, nos);
    if (!rows.length) return { rows, allowed: new Set() };
    this._wxs = null;
    await p.evaluate(() => { const a = [...document.querySelectorAll('a,img')].find(x => /doCallFileManagerExtra/.test(x.getAttribute('onclick') || '')); a && a.click(); });
    for (let i = 0; i < 40 && !this._wxs; i++) await sleep(250);
    if (!this._wxs) return { rows, allowed: new Set() };   // 체크가 풀림 = 열람 권한 없음
    const optPath = new URLSearchParams(this._wxs).get('path');
    const qs = new URL('https://x' + optPath).searchParams;
    this.UID = `[type = 1, id = ${qs.get('USERID')}, multiJobID = ${qs.get('APPRDEPTID')}]`;
    this.DID = `[type = 65537, id = ${qs.get('APPRDEPTID')}, multiJobID = 000000000000000]`;
    this.optPath = optPath;
    return { rows, allowed: new Set((qs.get('APPRIDLIST') || '').split(',').filter(Boolean)) };
  }

  /** 공식 다건 저장 페이지 — Capi·createAccesLogHist·mk_apprid 가 있는 문맥 */
  async bdtPage() {
    if (this.bdt && !this.bdt.isClosed()) return this.bdt;
    const o = await this.ctx.newPage(); K.autoDialog(o, []);
    const pop = new Promise(res => { const h = pg => { if (/BdtStre/.test(pg.url())) { this.ctx.off('page', h); res(pg); } }; this.ctx.on('page', h); setTimeout(() => res(null), 20000); });
    await o.goto(K.BASE + this.optPath, { waitUntil: 'domcontentloaded' }); await sleep(1500);
    await o.evaluate(() => {   // 본문만 체크해 연다 (Chrome 에선 ActiveX 저장 루프가 아무것도 쓰지 못한다)
      for (const n of ['hwpsave']) { const e = document.querySelector(`[name=${n}]`); if (e) e.checked = true; }
      for (const n of ['attsave', 'sisave', 'hoxsave']) { const e = document.querySelector(`[name=${n}]`); if (e) e.checked = false; }
      fncVerify();
    });
    let pg = await pop; if (!pg) pg = this.ctx.pages().find(x => /BdtStre/.test(x.url())) || null;
    await o.close().catch(() => { });
    if (!pg) throw new Error('다건 저장 페이지가 열리지 않음');
    K.autoDialog(pg, []); await pg.waitForLoadState('domcontentloaded').catch(() => { }); await sleep(1500);
    return (this.bdt = pg);
  }

  /** 문서 정보 + (선택) 본문·첨부 바이트 */
  async fetchDoc(id, { body = true, att = true } = {}) {
    const pg = await this.bdtPage();
    return pg.evaluate(async ({ id, UID, DID, body, att }) => {
      const b64 = async u => {
        const r = await fetch(u, { credentials: 'include' }); const b = new Uint8Array(await r.arrayBuffer());
        let s = ''; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
        const html = /^\s*</.test(s.slice(0, 200)) && /<html|<script|login/i.test(s.slice(0, 2000));
        return { st: r.status, size: b.length, html, data: html ? '' : btoa(s), head: html ? s.slice(0, 120) : '' };
      };
      const url = fid => `/bms/cz/cb/wrt/retrieveDocFile.do?UID=${encodeURIComponent(UID)}&DID=${encodeURIComponent(DID)}&apprID=${fid}&fileType=attach&fileName=undefined&_NOARG=${Date.now()}`;
      const info = Capi.getApprovalInfo(id);
      const out = { id, 제목: info.title, 문서번호: info.docRegNo, 결재유형: info.approvalType, 첨부: [], 본문: null };
      const names = info.fileNames || [], oids = info.fileObjectIDs || [];
      for (let i = 0; i < names.length; i++) {
        if (!oids[i] || oids[i].slice(-3) === '060' || names[i] === 'HOX_file') continue;
        out.첨부.push({ 이름: names[i], fid: oids[i] });
      }
      if (body) {
        const ap = mk_apprid(id, '01');
        out.본문 = await b64(url(ap));
        if (!out.본문.html) { try { createAccesLogHist(id, ap, 'hwpsave'); } catch (e) { } }
      }
      if (att) for (const a of out.첨부) {
        await new Promise(r => setTimeout(r, 500 + Math.random() * 700));
        Object.assign(a, await b64(url(a.fid.split('|')[0])));
        if (!a.html) { try { createAccesLogHist(id, a.fid, 'attsave'); } catch (e) { } }
      }
      return out;
    }, { id, UID: this.UID, DID: this.DID, body, att });
  }
}

const safe = s => String(s).replace(/[\\/:*?"<>|]/g, '_').replace(/[・･∙]/g, '·').trim();


function reloadLedger() { _ledger = null; return ledger(); }

/** 제목 검색 (낱말 여러 개는 모두 포함 = AND, 'A|B' 는 정규식 OR) */
function search(words, { from, to, type } = {}) {
  const res = words.map(w => /[|()\[\]]/.test(w) ? new RegExp(w) : null);
  const seen = new Set();
  return ledger().filter(r => {
    if (from && r.일자 < from) return false;
    if (to && r.일자 > to) return false;
    if (type && r.결재유형 !== type) return false;
    return words.every((w, i) => res[i] ? res[i].test(r.제목 || '') : (r.제목 || '').includes(w));
  }).filter(r => { const k = r.문서번호 + r.일자; if (seen.has(k)) return false; seen.add(k); return true; })
    .sort((a, b) => a.일자.localeCompare(b.일자));
}

function ledgerRange() {
  const d = ledger().map(r => r.일자).filter(Boolean).sort();
  return { 건수: ledger().length, 처음: d[0] || null, 마지막: d[d.length - 1] || null };
}

/** 문서등록대장 CSV 를 기간으로 받아 캐시에 더한다 (조회만) */
async function updateLedger({ from, to }) {
  const s = await S.open();
  const p = await s.ctx.newPage();
  try {
    K.autoDialog(p);
    await K.openScreen(p, '문서등록대장');
    const r = await K.search(p, { from, to, pageUnit: 100 });
    const out = path.join(LEDGER, `대장_${from}_${to}.csv`);
    await K.exportCsv(p, out);
    reloadLedger();
    return { 기간: `${from} ~ ${to}`, 총건수: r.총건수, 파일: out };
  } finally { await p.close().catch(() => { }); await s.done(); }
}


async function cmdGet(k, targets, o) {
  const out = path.resolve(o.out || paths.docs);
  const byDate = {};
  for (const t of targets) { const x = parseTarget(t, o.year); (byDate[x.일자] = byDate[x.일자] || []).push(x.번호); }
  const result = [];
  await k.open();
  for (const [date, nos] of Object.entries(byDate)) {
    const { rows, allowed } = await k.select(date, nos);
    for (const no of nos) {
      const r = rows.find(x => x.번호 === no);
      if (!r) { result.push({ 번호: no, 일자: date, 상태: '목록에 없음' }); continue; }
      if (!allowed.has(r.id)) { result.push({ 번호: no, 일자: date, 제목: r.제목, 상태: '열람 권한 없음' }); continue; }
      const d = await k.fetchDoc(r.id, { body: o.body, att: o.att });
      const dir = o.flat ? out : path.join(out, safe(`${d.문서번호 || no}_${d.제목}`).slice(0, 120));
      fs.mkdirSync(dir, { recursive: true });
      const files = [];
      const write = (name, part) => {
        if (!part || part.html || !part.data) return files.push({ 이름: name, 상태: part && part.html ? '세션/권한 응답(파일 아님)' : '실패', 응답: part && part.st });
        const f = path.join(dir, safe(name)); fs.writeFileSync(f, Buffer.from(part.data, 'base64'));
        files.push({ 이름: path.basename(f), 크기: part.size, 경로: f });
      };
      if (o.body) write(`(${d.문서번호} (본문)) ${d.제목}.odt`, d.본문);
      if (o.att) for (const a of d.첨부) write(`(${d.문서번호} (첨부)) ${a.이름}`, a);
      result.push({ 번호: no, 일자: date, 제목: d.제목, 문서번호: d.문서번호, 상태: files.every(f => f.경로) ? 'ok' : '일부 실패', 파일: files });
      await sleep(500 + Math.random() * 700);
    }
  }
  return result;
}

async function cmdInfo(k, targets, o) {
  const res = [];
  await k.open();
  for (const t of targets) {
    const x = parseTarget(t, o.year);
    const { rows, allowed } = await k.select(x.일자, [x.번호]);
    const r = rows[0];
    if (!r) { res.push({ ...x, 상태: '목록에 없음' }); continue; }
    if (!allowed.has(r.id)) { res.push({ ...x, 제목: r.제목, 상태: '열람 권한 없음' }); continue; }
    const d = await k.fetchDoc(r.id, { body: false, att: false });
    res.push({ ...x, 제목: d.제목, 문서번호: d.문서번호, 첨부: d.첨부.map(a => a.이름) });
  }
  return res;
}


module.exports = { Klef, ledger, reloadLedger, find, search, parseTarget, ledgerRange, updateLedger, cmdGet, cmdInfo };
