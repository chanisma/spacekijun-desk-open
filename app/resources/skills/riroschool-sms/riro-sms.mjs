#!/usr/bin/env node
/**
 * 리로스쿨 알림 문자 발송 — Edge 를 CDP 로 직접 조종한다 (의존성 없음, Node 22+, Playwright 불필요).
 *
 *   node riro-sms.mjs config --base https://학교.riroschool.kr     # 학교 주소 저장 (처음 한 번)
 *   node riro-sms.mjs status                                       # 로그인 확인 + 발송 가능 건수
 *   node riro-sms.mjs find --name 홍길동 [--class 3-8]             # 수신자 찾기 (id 확인)
 *   node riro-sms.mjs preview --message "…" --class 3-8 --to mother,father   # 발송 전 미리보기 (보내지 않음)
 *   node riro-sms.mjs send --preview-id <id> --confirmed           # 사용자 승인 뒤 발송
 *   node riro-sms.mjs history [--limit 5]                          # 보낸 내역 읽기
 *
 * 안전 설계 (문자는 회수할 수 없고 학교 잔여 건수를 쓴다)
 *   · preview 는 리로스쿨 화면이 하는 "예상 발송 건수 → 발송하시겠습니까?" 단계까지만 가고 거기서 **취소**한다.
 *     게다가 실제 발송 요청(POST /sms.php)은 **네트워크 단에서 차단**한다 — 화면 스크립트가 어떻게 되든 못 나간다.
 *   · send 는 preview 가 남긴 기록(내용·수신자·유형)과 **같은 것만**, 같은 건수일 때만 승인한다. 한 번 보낸 preview 는 다시 못 쓴다
 *     (같은 문자가 두 번 나가는 것을 막는다). 기록은 30분 안의 것만 쓴다.
 *   · 로그인은 **한 번만** 시도한다. 틀려도 다시 시도하지 않는다 (리로스쿨은 5번 틀리면 계정을 잠근다).
 *   · 비밀번호는 화면·로그·기록 어디에도 남기지 않는다. 미리보기는 비밀번호를 아예 쓰지 않는다.
 *
 * 자료 위치: %LOCALAPPDATA%\RiroSms\  (config.json, previews\, profile\)  — 환경변수 RIRO_SMS_DATA_DIR 로 바꿀 수 있다.
 */
import { spawn, spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = process.env.RIRO_SMS_DATA_DIR || path.join(process.env.LOCALAPPDATA || os.homedir(), 'RiroSms');
const PROFILE = path.join(DATA, 'profile');
const PREVIEWS = path.join(DATA, 'previews');
const CONFIG = path.join(DATA, 'config.json');
const LOCK = path.join(DATA, 'run.lock');
const PREVIEW_MAX_AGE_MS = 30 * 60 * 1000;
const DEFAULT_MAX_RECIPIENTS = 50;

// ── 인자 ──────────────────────────────────────────────────────
const FLAGS = new Set(['confirmed', 'json', 'reveal', 'headed', 'help', 'allow-large', 'reserve', 'teachers']);
function parseArgs(list) {
  const out = { _: [] };
  for (let i = 0; i < list.length; i++) {
    const item = list[i];
    if (!item.startsWith('--')) { out._.push(item); continue; }
    const key = item.slice(2);
    if (FLAGS.has(key)) { out[key] = true; continue; }
    const next = list[i + 1];
    if (next === undefined || next.startsWith('--')) throw new UserError(`--${key} 에 값이 필요합니다.`);
    out[key] = next;
    i++;
  }
  return out;
}

class UserError extends Error {}
const args = (() => { try { return parseArgs(process.argv.slice(2)); } catch (e) { console.error(`오류: ${e.message}`); process.exit(2); } })();
const say = text => console.log(text);
const emit = (human, data) => (args.json ? say(JSON.stringify(data, null, 2)) : say(human));

// ── 개인정보 가림 (기본) ────────────────────────────────────────
const maskText = text => args.reveal ? text
  : String(text).replace(/\d{2,4}-?\d{3,4}-?\d{4}/g, '###-####-####')
      .replace(/[가-힣]{2,4}/g, m => (/^(학급|학년|담임|비담임|선생님|어머니|아버지|학생|교사|교직원|발송|예약|단문|장문|문자|알림|앱|내역|메시지|전체|일반|본인|성공|실패|대기)/.test(m) ? m : m[0] + '○'.repeat(m.length - 1)));

// ── 설정 · 계정 ───────────────────────────────────────────────
function readJson(file, fallback = null) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; } }
function writeJson(file, value) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, JSON.stringify(value, null, 2), 'utf8'); }

function baseUrl() {
  const url = (process.env.RIRO_BASE_URL || readJson(CONFIG, {}).baseUrl || '').replace(/\/+$/, '');
  if (!url) throw new UserError('학교 리로스쿨 주소가 없습니다. 먼저:  node riro-sms.mjs config --base https://학교.riroschool.kr');
  checkBase(url);
  return url;
}
// 🚨 아이디·비밀번호를 넣는 곳이므로 리로스쿨 주소가 아니면 절대 쓰지 않는다 (오타·잘못된 주소로 계정이 새는 것을 막는다)
function checkBase(url) {
  if (!/^https:\/\/[a-z0-9-]+\.riroschool\.kr$/i.test(url)) throw new UserError(`리로스쿨 주소가 아닙니다: ${url}  (예: https://학교.riroschool.kr)`);
}

function getAccount() {
  const script = path.join(HERE, 'credentials.ps1');
  const done = spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, 'get'],
    { encoding: 'utf8', windowsHide: true });
  if (done.status !== 0) return null;
  try { return JSON.parse(done.stdout.trim()); } catch { return null; }
}

// ── 한 번에 하나만 ─────────────────────────────────────────────
function acquireLock() {
  fs.mkdirSync(DATA, { recursive: true });
  const old = readJson(LOCK);
  if (old && old.pid) {
    try { process.kill(old.pid, 0); throw new UserError(`다른 riro-sms 가 실행 중입니다 (pid ${old.pid}). 끝난 뒤 다시 실행하세요.`); }
    catch (e) { if (e instanceof UserError) throw e; }
  }
  writeJson(LOCK, { pid: process.pid, at: new Date().toISOString() });
}
const releaseLock = () => { try { fs.rmSync(LOCK, { force: true }); } catch { /* 무시 */ } };

// ── Edge 띄우기 · CDP ─────────────────────────────────────────
function findEdge() {
  const found = [process.env['ProgramFiles(x86)'], process.env.ProgramFiles, process.env.LOCALAPPDATA]
    .filter(Boolean).map(r => path.join(r, 'Microsoft', 'Edge', 'Application', 'msedge.exe')).find(p => fs.existsSync(p));
  if (!found) throw new UserError('Microsoft Edge 를 찾지 못했습니다.');
  return found;
}

const killTree = pid => { try { spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true }); } catch { /* 무시 */ } };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function launchEdge() {
  fs.mkdirSync(PROFILE, { recursive: true });
  const portFile = path.join(PROFILE, 'DevToolsActivePort');
  fs.rmSync(portFile, { force: true });
  const flags = ['--remote-debugging-port=0', `--user-data-dir=${PROFILE}`, '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--window-size=1400,1000', ...(args.headed ? [] : ['--headless=new']), 'about:blank'];
  const child = spawn(findEdge(), flags, { stdio: 'ignore', windowsHide: !args.headed });
  const started = Date.now();
  while (!fs.existsSync(portFile)) {
    if (Date.now() - started > 25000) { killTree(child.pid); throw new Error('Edge 를 시작하지 못했습니다 (디버깅 포트가 열리지 않음).'); }
    await sleep(150);
  }
  const port = Number(fs.readFileSync(portFile, 'utf8').split(/\r?\n/)[0]);
  return { child, port };
}

class Cdp {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.waiting = new Map(); this.handlers = new Map();
    ws.addEventListener('message', ev => {
      const m = JSON.parse(ev.data);
      if (m.id && this.waiting.has(m.id)) {
        const { resolve, reject } = this.waiting.get(m.id); this.waiting.delete(m.id);
        m.error ? reject(new Error(m.error.message)) : resolve(m.result);
      } else if (m.method) (this.handlers.get(m.method) || []).forEach(h => h(m.params));
    });
  }
  static async connect(port) {
    let target;
    for (let i = 0; i < 40 && !target; i++) {
      try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t => t.type === 'page'); } catch { /* 재시도 */ }
      if (!target) await sleep(150);
    }
    if (!target) throw new Error('Edge 페이지에 붙지 못했습니다.');
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { ws.addEventListener('open', resolve); ws.addEventListener('error', () => reject(new Error('CDP 연결 실패'))); });
    return new Cdp(ws);
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => { const id = ++this.id; this.waiting.set(id, { resolve, reject }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
  on(method, handler) { this.handlers.set(method, [...(this.handlers.get(method) || []), handler]); }
  close() { try { this.ws.close(); } catch { /* 무시 */ } }
}

/** 페이지 안에서 식을 실행한다. 오류 메시지에는 식(비밀번호가 들어 있을 수 있다)을 싣지 않는다. */
async function ev(cdp, expression) {
  const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) {
    const text = (r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text || '';
    throw new Error('화면 스크립트 오류: ' + String(text).split('\n')[0].slice(0, 200));
  }
  return r.result.value;
}
async function waitFor(cdp, expression, ms = 30000, label = '화면') {
  const started = Date.now();
  while (Date.now() - started < ms) {
    try { if (await ev(cdp, expression)) return true; } catch { /* 이동 중 */ }
    await sleep(150);
  }
  throw new Error(`${label} 을(를) 기다리다 시간이 지났습니다.`);
}
async function go(cdp, url) { await cdp.send('Page.navigate', { url }); await sleep(300); await waitFor(cdp, `document.readyState !== 'loading'`, 30000, '페이지 불러오기'); }

async function withBrowser(work) {
  acquireLock();
  let child;
  const cleanup = () => { if (child) killTree(child.pid); releaseLock(); };
  process.once('exit', cleanup);
  try {
    const launched = await launchEdge();
    child = launched.child;
    const cdp = await Cdp.connect(launched.port);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    // 방어선: 화면이 진짜 대화상자(alert/confirm)를 띄우면 무조건 취소한다. 우리가 덮어쓴 함수가 먼저 가로채야 정상이다.
    cdp.on('Page.javascriptDialogOpening', () => { cdp.send('Page.handleJavaScriptDialog', { accept: false }).catch(() => {}); });
    try { return await work(cdp); } finally { cdp.close(); }
  } finally { cleanup(); }
}

// ── 로그인 ────────────────────────────────────────────────────
const SIGNED_IN = `(() => { const t = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
  return !/로그인이 필요합니다|접근 가능한 메뉴가 없습니다/.test(t) && /로그아웃/.test(t); })()`;
const FORM_READY = `(() => { const t = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
  if (!/로그인이 필요합니다|접근 가능한 메뉴가 없습니다/.test(t) && /로그아웃/.test(t)) return true;
  const id = document.querySelector('#id'), pw = document.querySelector('#pw');
  return !!(id && pw && id.getClientRects().length > 0 && !id.disabled); })()`;

/** 이미 로그인돼 있으면 그대로, 아니면 저장된 계정으로 **한 번만** 로그인한다. */
async function login(cdp, base) {
  await go(cdp, `${base}/user.php?action=signin`);
  await waitFor(cdp, FORM_READY, 30000, '로그인 화면');
  if (await ev(cdp, SIGNED_IN)) return { already: true };
  const account = getAccount();
  if (!account) throw new UserError('저장된 리로스쿨 계정이 없습니다.  powershell -File credentials.ps1 save  (또는 스페이스기전 데스크에 리로스쿨 계정을 저장)');
  const fill = `((id, pw) => {
    const set = (el, v) => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; s.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
    set(document.querySelector('#id'), id); set(document.querySelector('#pw'), pw);
    // 🚨 '로그인' 글자가 든 단추가 여럿이고 숨은 것이 섞여 있다 — 보이는 것만 누른다
    const btn = [...document.querySelectorAll('button')].filter(b => b.getClientRects().length && /로그인/.test(b.innerText))[0];
    if (!btn) return false; btn.click(); return true; })(${JSON.stringify(account.id)}, ${JSON.stringify(account.password)})`;
  if (!(await ev(cdp, fill))) throw new Error('로그인 단추를 찾지 못했습니다.');
  try { await waitFor(cdp, SIGNED_IN, 30000, '로그인 결과'); }
  catch { throw new UserError('리로스쿨 로그인이 끝나지 않았습니다. 아이디·비밀번호를 확인하세요. (잠김을 막으려고 다시 시도하지 않았습니다)'); }
  return { already: false, source: account.source };
}

// ── 문자 발송 화면 ─────────────────────────────────────────────
const sendFormUrl = base => `${base}/sms.php?db=&action=send_form`;

async function openSendForm(cdp, base) {
  await go(cdp, sendFormUrl(base));
  await waitFor(cdp, `!!document.querySelector('#msg_id') && document.querySelectorAll('input[name="members[]"]').length > 0 && typeof select_member === 'function'`, 40000, '문자 발송 화면');
  await sleep(500);
}

const QUOTA = `(() => { const t = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
  const n = re => { const m = t.match(re); return m ? Number(m[1].replace(/,/g, '')) : null; };
  const who = t.match(/([가-힣]{2,4})\\s+[가-힣]+부\\s+로그아웃/);
  return { available: n(/현재 발송 가능\\s*([\\d,]+)\\s*건/), school: n(/학교 잔여\\s*([\\d,]+)\\s*건/), monthly: n(/월별 허용\\s*([\\d,]+)\\s*건/), user: who ? who[1] : null }; })()`;

const SNAPSHOT = `(() => {
  const own = li => [...li.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\\s+/g, ' ').trim();
  const out = [];
  for (const e of document.querySelectorAll('input[name="members[]"]')) {
    const li = e.closest('li'); const grp = li && li.parentElement && li.parentElement.closest('li');
    const label = ((li && li.querySelector('label')) || {}).innerText || '';
    const m = label.match(/^\\s*(\\d+)\\.\\s*(.+?)\\s*$/);
    const icons = [...(li ? li.querySelectorAll('.callapp_wrap span') : [])].map(s => (String(s.className).match(/callapp_(\\w+)/) || [])[1] || '');
    out.push({ id: e.value, name: e.getAttribute('data-name') || (m ? m[2] : ''), role: (e.getAttribute('data') || '').split('|')[0], no: m ? m[1] : '', group: grp ? own(grp) : '', icons });
  }
  return out; })()`;

const classLabel = spec => {
  const m = String(spec).trim().match(/^(\d)\s*[-학년\s]\s*(\d{1,2})\s*(반)?$/) || String(spec).trim().match(/^(\d)(\d{2})$/);
  if (!m) throw new UserError(`학급 형식이 올바르지 않습니다: ${spec}  (예: 3-8)`);
  return `${m[1]}${String(m[2]).padStart(2, '0')}학급`;
};
const classOf = group => { const m = /^(\d)(\d{2})학급$/.exec(group); return m ? `${m[1]}-${Number(m[2])}` : group; };
const ROLE = { S: '학생', T: '교사' };
const TO_IDS = { student: 'to_student', mother: 'to_parent2', father: 'to_parent1', teacher: 'to_teacher' };
const TYPE_IDS = { appsms: 'plus', allsms: 'allsms', app: 'app', sms: 'sms' };
const TYPE_LABEL = { appsms: '앱 또는 문자', allsms: '모두 문자', app: '앱만', sms: '문자만(앱 사용자 제외)' };
const TO_LABEL = { student: '학생(본인)', mother: '어머니', father: '아버지', teacher: '선생님' };

/** 수신자 id 목록 만들기 — 이름은 **한 명으로 특정될 때만** 받는다. */
function resolveMembers(all, a) {
  const ids = new Set();
  if (a.member) for (const id of String(a.member).split(',').map(s => s.trim()).filter(Boolean)) {
    if (!all.some(m => m.id === id)) throw new UserError(`수신자 id 를 찾지 못했습니다: ${id}  (find 로 확인)`);
    ids.add(id);
  }
  if (a.class) {
    const label = classLabel(a.class);
    const inClass = all.filter(m => m.group === label);
    if (!inClass.length) throw new UserError(`학급을 찾지 못했습니다: ${a.class}`);
    inClass.forEach(m => ids.add(m.id));
  }
  if (a.name) for (const name of String(a.name).split(',').map(s => s.trim()).filter(Boolean)) {
    let found = all.filter(m => m.name === name);
    if (a['name-class']) found = found.filter(m => m.group === classLabel(a['name-class']));
    if (found.length === 0) throw new UserError(`이름을 찾지 못했습니다: ${name}`);
    if (found.length > 1) throw new UserError(`동명이인이 ${found.length}명입니다: ${name} — ${found.map(m => `${m.group ? classOf(m.group) : ''} ${m.no}번 [${m.id}]`).join(', ')}\n  --member <id> 로 하나를 지정하거나 --name-class 3-8 로 학급을 지정하세요.`);
    ids.add(found[0].id);
  }
  return [...ids];
}

function buildSpec(a, all) {
  const message = a['message-file'] ? fs.readFileSync(a['message-file'], 'utf8').replace(/\r\n/g, '\n').trimEnd() : (a.message || '');
  if (!message.trim()) throw new UserError('--message(또는 --message-file) 이 비어 있습니다.');
  const stray = (message.match(/\{[^{}]*\}/g) || []).filter(v => v !== '{성명}');
  if (stray.length) throw new UserError(`치환 변수는 {성명} 만 쓸 수 있습니다: ${stray.join(' ')}`);
  if (!a.to) throw new UserError('--to 가 필요합니다 (student, mother, father, teacher 중 쉼표로).  예: --to mother,father');
  const to = String(a.to).split(',').map(s => s.trim()).filter(Boolean);
  const badTo = to.filter(t => !TO_IDS[t]);
  if (badTo.length) throw new UserError(`--to 값이 올바르지 않습니다: ${badTo.join(', ')} (student, mother, father, teacher)`);
  const type = a.type || 'appsms';
  if (!TYPE_IDS[type]) throw new UserError(`--type 은 appsms, allsms, app, sms 중 하나입니다: ${type}`);
  const sender = a.sender || 'default';
  if (!['default', 'school', 'phone'].includes(sender)) throw new UserError('--sender 는 school 또는 phone 입니다 (생략하면 화면의 기본값).');
  const ids = resolveMembers(all, a);
  if (!ids.length) throw new UserError('수신자가 없습니다. --class, --name, --member 중 하나가 필요합니다.');
  const max = a['max-recipients'] ? Number(a['max-recipients']) : DEFAULT_MAX_RECIPIENTS;
  if (ids.length > max && !a['allow-large']) throw new UserError(`수신자가 ${ids.length}명으로 한도(${max}명)를 넘습니다. 정말 필요하면 사용자 승인을 받은 뒤 --allow-large 를 붙이세요.`);
  return { message, ids: ids.sort(), to: to.sort(), type, sender };
}
const specId = spec => crypto.createHash('sha256').update(JSON.stringify(spec)).digest('hex').slice(0, 10);

// 화면 채우기 — 수신자 체크, 수신 구분, 발송 유형, 즉시 발송, 메시지, (발송 때만) 비밀번호
const APPLY = `((a) => {
  const df = document.form1;
  document.querySelectorAll('input[name="members[]"]').forEach(e => { e.checked = false; });
  const want = new Set(a.ids); let hit = 0;
  // 한 사람이 학급·동아리 등 여러 그룹에 있으면 같은 id 의 체크박스가 여러 개다 — 하나만 체크
  document.querySelectorAll('input[name="members[]"]').forEach(e => { if (want.has(e.value)) { want.delete(e.value); e.checked = true; hit++; } });
  for (const id of Object.values(a.toIds)) { const e = document.getElementById(id); if (e) e.checked = a.to.includes(id); }
  $('#' + a.typeId).trigger('click');
  $('#atonce').trigger('click');
  if (a.sender === 'school') $('#sch').trigger('click'); else if (a.sender === 'phone') $('#ph').trigger('click');
  df.add_msg.value = a.message; $(df.add_msg).trigger('input').trigger('keyup'); cntByte();
  df.admin_pass.value = a.pass;
  select_member();
  const bytes = getEucKrByteLength(df.add_msg.value);
  const reserve = document.querySelector('#reserve'), atonce = document.querySelector('#atonce');
  return { hit, selected: df.sms_member.value.split('|').filter(Boolean).length, bytes, kind: bytes > 90 ? '장문(LMS)' : '단문(SMS)',
           typeValue: df.sms_chk.value, immediate: !!(atonce && atonce.checked) && !(reserve && reserve.checked),
           sender: ($('input[name=return]:checked').attr('id') || ''), senderNumber: (document.querySelector('#admin_phone') || {}).value || '' }; })`;

// 가로채기 — alert/confirm 을 모아 두고, confirm 은 **우리가 정한 규칙으로만** 승인한다
const HOOKS = `(() => {
  window.__rs = { alerts: [], confirms: [], blockedSend: false, expect: null, accept: false, submitCalled: false };
  window.alert = m => { __rs.alerts.push(String(m)); };
  window.confirm = m => {
    const text = String(m); __rs.confirms.push(text);
    if (!__rs.accept) return false;                                   // 미리보기 — 늘 취소
    const num = re => { const x = text.match(re); return x ? Number(x[1].replace(/,/g, '')) : null; };
    const targets = num(/총 선택 대상:\\s*([\\d,]+)\\s*건/), total = num(/총\\s*([\\d,]+)\\s*건 차감/);
    const ok = __rs.expect && targets === __rs.expect.targets && total === __rs.expect.total;
    if (!ok) __rs.mismatch = { targets, total };
    return !!ok;                                                       // 미리보기와 건수가 다르면 취소
  };
  window.onbeforeunload = null;
  return true; })()`;

/** 발송 요청(POST /sms.php)을 네트워크 단에서 막는다 — 미리보기 때만. 건수 확인·잔여 조회는 통과시킨다. */
async function guardSends(cdp, enabled) {
  if (!enabled) return;
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*sms.php*', requestStage: 'Request' }] });
  cdp.on('Fetch.requestPaused', async p => {
    const req = p.request; let safe = true;
    try {
      const u = new URL(req.url);
      if (req.method === 'POST' && u.pathname === '/sms.php') {
        safe = u.searchParams.get('header') === 'sms_check_cnt' || /(^|&)action=sms_cnt(&|$)/.test(req.postData || '');
      }
    } catch { safe = false; }
    if (safe) { cdp.send('Fetch.continueRequest', { requestId: p.requestId }).catch(() => {}); return; }
    await ev(cdp, 'window.__rs && (window.__rs.blockedSend = true)').catch(() => {});
    cdp.send('Fetch.failRequest', { requestId: p.requestId, errorReason: 'BlockedByClient' }).catch(() => {});
  });
}

const parseConfirm = text => {
  const num = re => { const m = text.match(re); return m ? Number(m[1].replace(/,/g, '')) : 0; };
  return {
    targets: num(/총 선택 대상:\s*([\d,]+)\s*건/), duplicates: num(/중복 제외:\s*([\d,]+)\s*건/), app: num(/앱\s*([\d,]+)\s*건/),
    sms: num(/단문\s*([\d,]+)\s*건/), lms: num(/장문\s*([\d,]+)\s*건/), total: num(/총\s*([\d,]+)\s*건 차감/),
  };
};

/** 화면을 채우고 발송 단추를 눌러 "발송하시겠습니까?" 까지 간다. mode: 'preview'(취소) | 'send'(건수가 같을 때만 승인) */
async function runForm(cdp, base, spec, { mode, expect, password }) {
  await openSendForm(cdp, base);
  await ev(cdp, HOOKS);
  await guardSends(cdp, mode === 'preview');
  const quota = await ev(cdp, QUOTA);
  const filled = await ev(cdp, `(${APPLY})(${JSON.stringify({
    ids: spec.ids, to: spec.to.map(t => TO_IDS[t]), toIds: TO_IDS, typeId: TYPE_IDS[spec.type], sender: spec.sender,
    message: spec.message, pass: mode === 'send' ? password : 'preview-only' })})`);
  if (filled.hit !== spec.ids.length || filled.selected !== spec.ids.length) throw new Error(`수신자 선택이 맞지 않습니다 (요청 ${spec.ids.length}명, 선택 ${filled.selected}명).`);
  if (!filled.immediate) throw new Error('즉시 발송으로 맞추지 못했습니다 (예약 상태가 켜져 있음).');
  if (mode === 'send') await ev(cdp, `window.__rs.accept = true; window.__rs.expect = ${JSON.stringify(expect)}; true`);
  await ev(cdp, `$('#btn_sms').trigger('click'); true`);
  const first = await (async () => {
    const started = Date.now();
    while (Date.now() - started < 40000) {
      const s = await ev(cdp, `({ confirms: __rs.confirms, alerts: __rs.alerts, mismatch: __rs.mismatch || null, blocked: __rs.blockedSend })`);
      if (s.confirms.length || s.alerts.length) return s;
      await sleep(200);
    }
    throw new Error('발송 확인 단계가 나타나지 않았습니다.');
  })();
  if (!first.confirms.length) throw new UserError(`리로스쿨이 거부했습니다: ${first.alerts.join(' / ')}`);
  return { quota, filled, confirmText: first.confirms[0], counts: parseConfirm(first.confirms[0]), mismatch: first.mismatch, blocked: first.blocked };
}

// ── 보낸 내역 읽기 ─────────────────────────────────────────────
// 내역 표: 순번 · 유형 · 수신번호 · 이름(학번) · 등급 · 발신인 · 날짜 · 유형 · 발송결과 · 재사용 (기본 최근 6개월)
const HISTORY = `(() => {
  const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
  const table = document.querySelector('table.table_box') || document.querySelector('table');
  if (!table) return { head: [], rows: [], empty: false };
  const head = [...table.rows[0].cells].map(c => clean(c.innerText));
  const rows = [...table.rows].slice(1).map(tr => [...tr.cells].map(td => clean(td.innerText))).filter(cells => cells.length >= 5 && cells.some(Boolean));
  const empty = /발송 내역이 없습니다/.test(document.body.innerText);
  return { head, rows, empty }; })()`;

async function readHistory(cdp, base, kind = 'history_all', limit = 5) {
  await go(cdp, `${base}/sms.php?db=&action=${kind}`);
  await sleep(2500);
  const h = await ev(cdp, HISTORY);
  return { head: h.head, total: h.rows.length, empty: h.empty, rows: h.rows.slice(0, limit) };
}
const showHistory = h => h.empty || !h.rows.length ? '(발송 내역이 없습니다)'
  : [h.head.join(' | '), ...h.rows.map(r => maskText(r.join(' | ')).slice(0, 180))].join('\n  ');

// ── 명령 ──────────────────────────────────────────────────────
const commands = {
  async config() {
    if (args.base) {
      checkBase(String(args.base).replace(/\/+$/, ''));
      writeJson(CONFIG, { ...readJson(CONFIG, {}), baseUrl: String(args.base).replace(/\/+$/, '') });
      say(`저장했습니다: ${args.base}`);
    } else {
      say(`학교 주소: ${readJson(CONFIG, {}).baseUrl || '(없음)'}\n자료 폴더: ${DATA}`);
    }
  },

  async status() {
    const base = baseUrl();
    await withBrowser(async cdp => {
      const how = await login(cdp, base);
      await openSendForm(cdp, base);
      const q = await ev(cdp, QUOTA);
      emit(`로그인: 성공${how.already ? ' (저장된 로그인 사용)' : ''}${q.user ? ` · ${q.user}` : ''}\n`
        + `현재 발송 가능 ${q.available?.toLocaleString()}건 · 학교 잔여 ${q.school?.toLocaleString()}건 · 월별 허용 ${q.monthly?.toLocaleString()}건\n`
        + `(단문 1건 · 장문 3건 차감, 90byte 초과 시 장문)`, { ok: true, ...q });
    });
  },

  async find() {
    const base = baseUrl();
    await withBrowser(async cdp => {
      await login(cdp, base);
      await openSendForm(cdp, base);
      const all = await ev(cdp, SNAPSHOT);
      let list = all;
      if (args.class) list = list.filter(m => m.group === classLabel(args.class));
      if (args.name) list = list.filter(m => String(args.name).split(',').map(s => s.trim()).includes(m.name));
      if (args.teachers) list = list.filter(m => m.role === 'T');
      if (!args.class && !args.name && !args.teachers) throw new UserError('--name, --class 중 하나가 필요합니다.');
      if (list.length > 60) { say(`${list.length}명입니다 — 60명까지만 보여 드립니다. --class 로 좁히세요.`); list = list.slice(0, 60); }
      const rows = list.map(m => ({ id: m.id, class: classOf(m.group), no: m.no, name: m.name, role: ROLE[m.role] || m.role, contact: m.icons }));
      emit(rows.map(r => `[${r.id}] ${r.class} ${r.no}번 ${args.reveal || !args.json ? r.name : maskText(r.name)} (${r.role}) 연락처표시: 본인/어머니/아버지=${r.contact.join('/') || '-'}`).join('\n') || '(없음)', rows);
    });
  },

  async preview() {
    const base = baseUrl();
    await withBrowser(async cdp => {
      await login(cdp, base);
      await openSendForm(cdp, base);
      const all = await ev(cdp, SNAPSHOT);
      const spec = buildSpec(args, all);
      const r = await runForm(cdp, base, spec, { mode: 'preview' });
      const id = specId(spec);
      fs.mkdirSync(PREVIEWS, { recursive: true });
      writeJson(path.join(PREVIEWS, `${id}.json`), { id, createdAt: Date.now(), used: false, spec, counts: r.counts, quota: r.quota, bytes: r.filled.bytes });
      const names = all.filter(m => spec.ids.includes(m.id));
      const data = { previewId: id, sent: false, recipients: spec.ids.length, to: spec.to, type: spec.type, ...r.counts, bytes: r.filled.bytes, kind: r.filled.kind,
        available: r.quota.available, blockedSendAttempt: r.blocked };
      emit([
        '── 미리보기 (아직 보내지 않았습니다) ──',
        `받는 사람: ${spec.ids.length}명 — ${names.slice(0, 6).map(m => `${classOf(m.group)} ${m.no}번 ${args.reveal ? m.name : maskText(m.name)}`).join(', ')}${spec.ids.length > 6 ? ` 외 ${spec.ids.length - 6}명` : ''}`,
        `수신 구분: ${spec.to.map(t => TO_LABEL[t]).join(' + ')} · 발송 유형: ${TYPE_LABEL[spec.type]} · 발신: ${r.filled.sender === 'sch' ? '학교' : r.filled.sender === 'ph' ? '휴대폰' : r.filled.sender || '기본'}`,
        `메시지: ${r.filled.bytes}byte → ${r.filled.kind}`,
        `총 선택 대상 ${r.counts.targets}건${r.counts.duplicates ? ` · 중복 제외 ${r.counts.duplicates}건` : ''} → 실제 발송: ${[r.counts.app && `앱 ${r.counts.app}건`, r.counts.sms && `단문 ${r.counts.sms}건`, r.counts.lms && `장문 ${r.counts.lms}건`].filter(Boolean).join(' / ') || '없음'} (총 ${r.counts.total}건 차감)`,
        `현재 발송 가능 ${r.quota.available?.toLocaleString()}건 · 학교 잔여 ${r.quota.school?.toLocaleString()}건`,
        `미리보기 id: ${id}   (30분 안에, 사용자 승인 뒤:  node riro-sms.mjs send --preview-id ${id} --confirmed)`,
      ].join('\n'), data);
    });
  },

  async send() {
    const base = baseUrl();
    if (!args.confirmed) throw new UserError('발송하려면 사용자가 미리보기를 확인·승인한 뒤 --confirmed 를 붙여야 합니다.');
    if (!args['preview-id']) throw new UserError('--preview-id 가 필요합니다 (preview 가 알려 준 값).');
    const file = path.join(PREVIEWS, `${String(args['preview-id']).replace(/[^a-f0-9]/gi, '')}.json`);
    const record = readJson(file);
    if (!record) throw new UserError('그 미리보기 기록이 없습니다. 먼저 preview 를 실행하세요.');
    if (record.used) throw new UserError('이 미리보기는 이미 발송에 썼습니다. 같은 문자를 또 보내려면 preview 부터 다시 하세요. (중복 발송 방지)');
    if (Date.now() - record.createdAt > PREVIEW_MAX_AGE_MS) throw new UserError('미리보기가 30분이 지났습니다. 다시 preview 하고 사용자에게 확인받으세요.');
    if (specId(record.spec) !== record.id) throw new UserError('미리보기 기록이 손상됐습니다. 다시 preview 하세요.');
    const account = getAccount();
    if (!account) throw new UserError('저장된 리로스쿨 계정이 없어 발송 비밀번호를 쓸 수 없습니다.');
    await withBrowser(async cdp => {
      await login(cdp, base);
      const before = await readHistory(cdp, base, 'history_all', 0);      // 발송 전 내역 수 — 나중에 늘었는지 본다
      const r = await runForm(cdp, base, record.spec, { mode: 'send', expect: { targets: record.counts.targets, total: record.counts.total }, password: account.password });
      if (r.mismatch) {
        throw new UserError(`건수가 미리보기와 달라 발송하지 않았습니다 (미리보기: 대상 ${record.counts.targets}건·차감 ${record.counts.total}건 / 지금: 대상 ${r.mismatch.targets}건·차감 ${r.mismatch.total}건). 다시 preview 하세요.`);
      }
      // 승인이 나갔다 — 같은 기록으로 또 보내지 못하게 먼저 표시한다
      record.used = true; record.sentAt = Date.now(); writeJson(file, record);
      const outcome = await (async () => {
        const started = Date.now();
        while (Date.now() - started < 60000) {
          const s = await ev(cdp, `({ alerts: __rs.alerts, popup: (() => { const p = document.querySelector('.confirm_popup'); return p && p.getClientRects().length ? (p.querySelector('.content1') || p).innerText.replace(/\\s+/g, ' ').trim() : ''; })() })`);
          if (s.popup || s.alerts.length) return s;
          await sleep(300);
        }
        return { popup: '', alerts: [] };
      })();
      if (outcome.alerts.length && !outcome.popup) throw new UserError(`발송이 완료되지 않았습니다: ${outcome.alerts.join(' / ')}  (미리보기 기록은 사용 처리됐습니다 — 내역을 확인한 뒤 필요하면 다시 preview 하세요)`);
      // 내역 화면은 발송 직후가 아니라 **몇 초 뒤에** 반영된다(2026-10-22 실측: 바로 읽으면 0건) — 늘 때까지 기다려 다시 읽는다
      let after = await readHistory(cdp, base, 'history_all', Math.min(Math.max(record.counts.targets, 1), 8));
      for (let i = 0; i < 6 && after.total <= before.total; i++) {
        await sleep(4000);
        after = await readHistory(cdp, base, 'history_all', Math.min(Math.max(record.counts.targets, 1), 8));
      }
      const q = await (async () => { await openSendForm(cdp, base); return ev(cdp, QUOTA); })();
      const delta = after.total - before.total;
      emit([
        '── 발송했습니다 ──',
        `결과: ${maskText(outcome.popup) || '(결과 창 내용을 읽지 못했습니다 — 발송 내역을 확인하세요)'}`,
        `차감 ${record.counts.total}건 · 현재 발송 가능 ${q.available?.toLocaleString()}건 (발송 전 ${record.quota.available?.toLocaleString()}건) · 학교 잔여 ${q.school?.toLocaleString()}건`,
        `발송 내역: 발송 전 ${before.total}건 → 후 ${after.total}건 (${delta >= 0 ? '+' : ''}${delta})${delta <= 0 ? ' ⚠️ 아직 반영되지 않았을 수 있습니다 — 잠시 뒤 history 로 다시 확인하세요' : ''} — 최근 ${after.rows.length}건(가림):\n  ${showHistory(after)}`,
      ].join('\n'), { sent: true, counts: record.counts, result: outcome.popup, available: q.available, school: q.school, historyDelta: delta,
        history: after.rows.map(row => row.map(maskText)) });
    });
  },

  async history() {
    const base = baseUrl();
    await withBrowser(async cdp => {
      await login(cdp, base);
      const h = await readHistory(cdp, base, args.reserve ? 'history_reserve' : 'history_all', Number(args.limit || 5));
      emit(`${args.reserve ? '예약 발송 내역' : '발송 내역(최근 6개월)'} — 전체 ${h.total}건 중 ${h.rows.length}건\n  ${showHistory(h)}`,
        { total: h.total, head: h.head, rows: h.rows.map(r => r.map(maskText)) });
    });
  },

  /** 진단: 미리보기에서 발송 요청이 네트워크 단에서 실제로 막히는지 본다. 가짜 비밀번호를 쓰므로 막힘이 뚫려도 서버가 거부한다. */
  async selftest() {
    const base = baseUrl();
    await withBrowser(async cdp => {
      await login(cdp, base);
      await openSendForm(cdp, base);
      const all = await ev(cdp, SNAPSHOT);
      const spec = buildSpec(args, all);
      await ev(cdp, HOOKS);
      await guardSends(cdp, true);
      await ev(cdp, `(${APPLY})(${JSON.stringify({ ids: spec.ids, to: spec.to.map(t => TO_IDS[t]), toIds: TO_IDS, typeId: TYPE_IDS[spec.type], sender: spec.sender, message: spec.message, pass: 'preview-only' })})`);
      await ev(cdp, `smsSubmit(); true`);           // 화면의 실제 발송 함수를 직접 부른다
      await sleep(4000);
      const s = await ev(cdp, `({ blocked: __rs.blockedSend, alerts: __rs.alerts })`);
      emit(`발송 요청 차단: ${s.blocked ? '작동함 ✅' : '작동하지 않음 ❌ (차단 못 함)'}\n화면 반응: ${s.alerts.join(' / ') || '(없음)'}`, s);
      if (!s.blocked) process.exitCode = 1;
    });
  },
};

function help() {
  say(fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('*/')[0].replace(/^#!.*\n\/\*\*\n?/, '').replace(/^ \* ?/gm, ''));
}

const command = args._[0];
if (!command || args.help || !commands[command]) { help(); process.exit(command && !args.help ? 2 : 0); }
commands[command]().then(() => process.exit(0)).catch(error => {
  console.error(`오류: ${error.message}`);
  process.exit(error instanceof UserError ? 2 : 1);
});
