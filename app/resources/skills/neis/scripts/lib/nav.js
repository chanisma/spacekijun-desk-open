/**
 * NEIS(4세대, Cleopatra `cl-*`) 화면 이동·조회 도우미 — 모두 조회 전용.
 *
 * 실측으로 확인된 것(2026-09~10):
 *  · 화면 열기는 **왼쪽 '메뉴 검색'** 이 가장 튼튼하다. 결과마다 전체 경로(탭 > … > 화면)가 붙는다.
 *    검색 아이콘은 토글이라 이미 열려 있으면 누르지 않는다. 검색칸은 보이는 입력칸 중 **가장 왼쪽**.
 *  · 메가메뉴는 "다른 탭 → 대상 탭" 순으로 눌러야 열린다(활성 탭 재클릭 무시). 항목 텍스트는 "이름 N단계( 메뉴항목)".
 *  · 로그인 직후 공지 팝업이 여러 겹 — 닫기 버튼은 `div.cl-text` 일 때가 있고 **맨 위(last)부터** 닫는다.
 *  · 모달(`.cl-dialog`)은 되묻는 창이면 **취소**를 누른다(모르는 채로 확인 금지). 2차 인증 창은 사람이 한다.
 *  · 화면 탭이 **20개 차면 더 안 열리고 오류도 없다** → 14개쯤에서 '탭 아이템 전체 닫기'.
 *  · 로딩은 `.ers_progress_content`, 왼쪽 패널 덮개는 `.cl-overlay` 가 사라질 때까지 기다린다.
 *  · 일자 칸은 `2026.09.10.` 을 **한 글자씩 타이핑 + Enter** 만 먹는다(fill 은 되돌아간다). 넣고 다시 읽어 확인.
 *  · 실제 마우스 클릭이 필요한 곳이 많다(dispatchEvent 무시) — Playwright click 을 쓴다.
 */
const { assertSafe } = require('./safety.js');

const LOADING = '.ers_progress_content';
const DIALOG = '.cl-dialog:visible';
const DISMISS_ORDER = ['취소', '아니오', '닫기', '확인'];
const AUTH_RX = /2차\s*인증|OTP|인증번호/;
const SCREEN_TAB = '.cl-tabfolder-item.type-M';
const SCREEN_CLOSE = '.cl-tabfolder-button';
const CLOSE_ALL = '.btn-close-mdi[title*="전체 닫기"]:visible';
const SEARCH_BUTTON = '[class*="cl-button"][class*="search"]:visible';
const SEARCH_ROW = '.menu-find-grp';
const TAB = '.cl-navigationbar-text.cl-text';
const esc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const exact = s => new RegExp('^' + esc(s) + '$');

async function waitLoading(page, ms = 45000) {
  await page.evaluate(async ([sel, limit]) => {
    const d = t => new Promise(r => setTimeout(r, t)); const t0 = Date.now(); await d(300);
    while (Date.now() - t0 < limit) { const b = document.querySelector(sel); if (!b || b.offsetParent === null) return; await d(400); }
  }, [LOADING, ms]).catch(() => { });
}

async function waitOverlayGone(page, ms = 8000) {
  await page.evaluate(async limit => {
    const d = t => new Promise(r => setTimeout(r, t)); const t0 = Date.now();
    while (Date.now() - t0 < limit) { if (![...document.querySelectorAll('.cl-overlay')].some(e => e.offsetParent !== null)) return; await d(250); }
  }, ms).catch(() => { });
}

async function authRequired(page) {
  const texts = await page.evaluate(() => [...document.querySelectorAll('.cl-dialog')].filter(e => e.offsetParent !== null)
    .map(e => (e.textContent || '').replace(/\s+/g, ' ').trim())).catch(() => []);
  return texts.some(t => AUTH_RX.test(t));
}

/** 모달을 안전하게 치운다(취소 우선). 2차 인증 창은 건드리지 않는다. 치운 문구 목록을 돌려준다. */
async function dismissDialogs(page) {
  const closed = [];
  for (let i = 0; i < 8; i++) {
    const dialogs = page.locator(DIALOG);
    if (!await dialogs.count().catch(() => 0)) break;
    const top = dialogs.last();
    const text = ((await top.textContent().catch(() => '')) || '').replace(/\s+/g, ' ').trim();
    if (AUTH_RX.test(text)) break;
    let pressed = false;
    for (const label of DISMISS_ORDER) {
      const b = top.locator('div.cl-text:visible, button:visible').filter({ hasText: exact(label) }).first();
      if (await b.count().catch(() => 0)) { await b.click({ timeout: 5000 }).catch(() => { }); pressed = label; break; }
    }
    if (!pressed) break;
    closed.push(`${text.slice(0, 80)} → ${pressed}`);
    await page.waitForTimeout(700);
  }
  return closed;
}

/** 공지 팝업 + 모달 전부 치우기 */
async function closePopups(page) {
  const closed = await dismissDialogs(page);
  for (let i = 0; i < 20; i++) {
    const b = page.locator('div.cl-text:visible, button:visible').filter({ hasText: /^닫기$/ });
    if (!await b.count().catch(() => 0)) break;
    try { await b.last().click({ timeout: 5000 }); } catch (e) { break; }
    await page.waitForTimeout(700); closed.push('공지 닫기');
  }
  return closed;
}

const openScreens = page => page.locator(SCREEN_TAB).count().catch(() => 0);
async function activeScreen(page) {
  const s = page.locator(SCREEN_TAB + '.cl-selected').first();
  return (await s.count().catch(() => 0)) ? ((await s.textContent()) || '').replace(/\s+/g, ' ').trim() : '';
}

/** 열어 둔 화면 탭 닫기 (keep=0 이면 전체 닫기 단추) */
async function closeScreens(page, keep = 0) {
  if (keep <= 0) {
    const before = await openScreens(page);
    const btn = page.locator(CLOSE_ALL).first();
    if (before && await btn.count().catch(() => 0)) {
      await btn.click({ timeout: 8000 }).catch(() => { }); await page.waitForTimeout(800); await dismissDialogs(page);
      if (!await openScreens(page)) return before;
    }
  }
  let n = 0;
  for (let i = 0; i < 30; i++) {
    const bs = page.locator(SCREEN_CLOSE); const before = await bs.count().catch(() => 0);
    if (before <= keep) break;
    await bs.last().click({ timeout: 5000 }).catch(() => { }); await page.waitForTimeout(400); await dismissDialogs(page);
    if (await openScreens(page) >= before) break; n++;
  }
  return n;
}

async function tabs(page) {
  return (await page.locator(TAB).allTextContents()).map(t => t.trim().replace(/\s+\d단계(\s+메뉴항목)?$/, '')).filter(Boolean);
}

// ── 메뉴 검색 ─────────────────────────────────────────────
const searchOpen = page => page.evaluate(() => [...document.querySelectorAll('input:not([type=hidden])')]
  .some(e => e.offsetParent !== null && e.getBoundingClientRect().x < 300)).catch(() => false);

async function searchMenu(page, word, { waitMs = 2500, tries = 2 } = {}) {
  for (let a = 0; a < tries; a++) {
    if (!await searchOpen(page)) { await page.locator(SEARCH_BUTTON).first().click({ timeout: 15000 }); await page.waitForTimeout(900); }
    for (let i = 0; i < 20 && !await searchOpen(page); i++) await page.waitForTimeout(300);
    const idx = await page.evaluate(() => {
      const b = [...document.querySelectorAll('input:not([type=hidden])')].map((e, i) => ({ i, x: e.getBoundingClientRect().x, on: e.offsetParent !== null })).filter(b => b.on);
      return b.length ? b.sort((p, q) => p.x - q.x)[0].i : -1;
    });
    if (idx < 0) throw new Error('메뉴 검색 입력칸을 찾지 못했습니다');
    const box = page.locator('input:not([type=hidden])').nth(idx);
    await box.click({ timeout: 10000 }); await box.fill(word); await box.press('Enter');
    await page.waitForTimeout(waitMs); await waitLoading(page);
    const raw = await page.evaluate(sel => [...document.querySelectorAll(sel)].filter(r => r.offsetParent !== null).map(r => {
      const a = r.querySelector('a');
      const path = [...r.querySelectorAll('div.cl-text')].map(e => (e.textContent || '').replace(/\s+/g, ' ').trim()).find(t => t.includes(' > ')) || '';
      return { name: (a ? a.textContent : '').replace(/\s+/g, ' ').trim(), path };
    }), SEARCH_ROW);
    const seen = new Set(), out = [];
    for (const r of raw) if (r.name && r.path.includes(' > ') && !seen.has(r.path)) { seen.add(r.path); out.push({ name: r.name, tab: r.path.split(' > ')[0].trim(), path: r.path }); }
    if (out.length || a === tries - 1) return out;
    await page.waitForTimeout(1200);
  }
  return [];
}

/** 메뉴 검색으로 화면 열기. path(일부)를 주면 그 경로의 결과를 고른다. 여러 개가 맞으면 고르지 않고 목록을 돌려준다. */
async function openScreen(page, name, { path = '' } = {}) {
  await dismissDialogs(page); await waitOverlayGone(page);
  if (await authRequired(page)) throw new Error('2차 인증 창이 떠 있습니다. 사람이 인증하거나 닫은 뒤 다시 시도하세요.');
  if (await openScreens(page) >= 14) await closeScreens(page);        // 20개 차면 조용히 안 열린다
  const results = await searchMenu(page, name);
  if (!results.length) throw new Error(`'${name}' 을(를) 메뉴 검색에서 찾지 못했습니다 (이 계정 권한에 없는 화면일 수 있음)`);
  let cands = path ? results.filter(r => r.path.includes(path)) : results.filter(r => r.name === name);
  if (!cands.length) cands = results;
  if (cands.length > 1) {
    const e = new Error(`'${name}' 이(가) 여러 경로에 있습니다. --path 로 고르세요:\n  ` + cands.map(r => r.path).join('\n  '));
    e.candidates = cands; throw e;
  }
  const want = cands[0];
  await page.locator(SEARCH_ROW + ':visible').filter({ hasText: want.path }).first().locator('a').first().click({ timeout: 15000 });
  await page.waitForTimeout(2000); await waitLoading(page); await page.waitForTimeout(1500);
  const notes = await dismissDialogs(page); await waitOverlayGone(page);
  return { screen: await activeScreen(page), path: want.path, auth: await authRequired(page), 알림: notes };
}

/** 상단 탭 → 단계 메뉴를 차례로 눌러 들어가기(메뉴 검색이 안 될 때). 한 프로세스 안에서 끝까지 간다. */
async function gotoMenu(page, tabName, chain, { log = () => { } } = {}) {
  await closePopups(page);
  const all = await tabs(page);
  const detour = all.find(t => t !== tabName && !t.includes(tabName)) || all[0];
  const tabLoc = n => page.locator(TAB, { hasText: n }).first();
  if (detour) { await tabLoc(detour).click({ timeout: 20000 }); await page.waitForTimeout(2000); }
  await tabLoc(tabName).click({ timeout: 20000 }); await page.waitForTimeout(2500);
  const itemRx = n => new RegExp('^' + esc(n) + '\\s+\\d단계(\\s+메뉴항목)?$');
  const visible = n => page.evaluate(([src]) => { const re = new RegExp(src); return [...document.querySelectorAll('div.cl-text')].some(e => re.test((e.textContent || '').trim()) && e.offsetParent !== null); }, [itemRx(n).source]);
  for (let i = 0; i < chain.length; i++) {
    const name = chain[i], next = chain[i + 1]; let ok = false;
    for (let k = 0; k < 4; k++) {
      await page.locator('div.cl-text').filter({ hasText: itemRx(name) }).locator('visible=true').first().click({ timeout: 20000 });
      await page.waitForTimeout(2500);
      if (!next || await visible(next)) { ok = true; break; }
      log(`재시도: ${name}`);
    }
    if (!ok) throw new Error(`"${name}" 을 눌렀지만 "${next}" 가 나타나지 않았습니다`);
  }
  await waitLoading(page); await page.waitForTimeout(2000);
  return { screen: await activeScreen(page) };
}

/**
 * 왼쪽 사이드바(기본 메뉴 — 복무 같은 개인 메뉴)에서 열기. 메뉴 검색에 안 나오는 화면이 여기 있다.
 * 항목 텍스트: "복무 0단계 메뉴항목", "일일근무상황조회 1단계". 메가메뉴가 열려 있으면 가로막으므로 Esc 로 닫는다.
 */
async function openSidebar(page, chain) {
  await closePopups(page); await page.keyboard.press('Escape').catch(() => { }); await waitOverlayGone(page);
  const rx = n => new RegExp('^' + esc(n) + '\\s+\\d단계(\\s+메뉴항목)?$');
  // 왼쪽 아이콘 줄의 '기본메뉴 및 승인사항'(mymenu) 패널을 연다 — 다른 패널(메뉴 검색 등)이 열려 있으면 항목이 숨어 있다
  const first = page.locator('.cl-sidenavigation-item div.cl-text').filter({ hasText: rx(chain[0]) }).locator('visible=true');
  if (!await first.count()) {
    await page.locator('[class*="cl-button"][class*="mymenu"]:visible').first().click({ timeout: 10000 }).catch(() => { });
    await page.waitForTimeout(1200); await waitOverlayGone(page);
  }
  for (let i = 0; i < chain.length; i++) {
    const name = chain[i], next = chain[i + 1];
    const item = page.locator('.cl-sidenavigation-item div.cl-text').filter({ hasText: rx(name) }).locator('visible=true').first();
    if (!await item.count()) throw new Error(`사이드바에 '${name}' 이(가) 없습니다`);
    const nextVisible = async () => next && await page.locator('.cl-sidenavigation-item div.cl-text').filter({ hasText: rx(next) }).locator('visible=true').count();
    if (next && await nextVisible()) continue;                 // 이미 펼쳐져 있음
    await item.click({ timeout: 15000 }); await page.waitForTimeout(1500);
  }
  await waitLoading(page); await page.waitForTimeout(1500);
  return { screen: await activeScreen(page), 알림: await dismissDialogs(page) };
}

/** 화면 안 버튼 누르기 — 자료를 바꿀 수 있는 버튼은 거절한다 */
async function clickButton(page, label) {
  const effect = assertSafe(label);
  await waitOverlayGone(page);
  const b = page.locator('div.cl-text:visible, button:visible, .cl-button:visible').filter({ hasText: exact(label) }).first();
  if (!await b.count()) throw new Error(`[${label}] 버튼을 화면에서 찾지 못했습니다`);
  if (/cl-disabled/.test((await b.getAttribute('class').catch(() => '')) || '')) throw new Error(`[${label}] 은(는) 비활성(권한 없음)입니다`);
  await b.click({ timeout: 15000 }); await page.waitForTimeout(1500); await waitLoading(page); await page.waitForTimeout(1000);
  return { effect, 알림: await dismissDialogs(page) };
}

/** 일자 칸 맞추기 (값 예: 2026.09.10.) — 칸이 여럿이면 모두 같은 날 */
async function setDate(page, value) {
  const got = await page.evaluate(() => {
    let found = 0, locked = 0;
    document.querySelectorAll('input').forEach(el => {
      el.removeAttribute('data-neis-date'); if (el.offsetParent === null) return;
      const label = el.getAttribute('aria-label') || ''; const looks = /^\d{4}\.\d{2}\.\d{2}\./.test(el.value || '');
      if (!(label.includes('일자') || looks)) return;
      if (el.disabled || el.readOnly || el.closest('.cl-disabled') || getComputedStyle(el).pointerEvents === 'none') { locked++; return; }
      el.setAttribute('data-neis-date', String(found++));
    });
    return { found, locked };
  });
  const set = [], failed = [];
  for (let i = 0; i < got.found; i++) {
    const h = page.locator(`input[data-neis-date="${i}"]`);
    try {
      await h.click({ timeout: 8000 }); await page.keyboard.press('Control+A'); await page.keyboard.type(value, { delay: 50 }); await page.keyboard.press('Enter');
      await page.waitForTimeout(700); const now = await h.inputValue();
      (now.startsWith(value) ? set : failed).push({ i, value: now });
    } catch (e) { failed.push({ i, why: String(e.message).split('\n')[0] }); }
  }
  await waitLoading(page);
  return { set, failed, locked: got.locked };
}

/** 화면 안쪽 큰 탭(하위 업무) 누르기 */
async function clickInnerTab(page, label) {
  await waitOverlayGone(page);
  const b = page.locator('.cl-button:visible, button:visible').filter({ hasText: exact(label) }).first();
  if (!await b.count()) throw new Error(`'${label}' 탭을 찾지 못했습니다`);
  if (/cl-disabled/.test((await b.getAttribute('class')) || '')) throw new Error(`'${label}' 은(는) 이 계정에서 쓸 수 없습니다`);
  await b.click({ timeout: 10000 }); await page.waitForTimeout(1500); await waitLoading(page);
  return { 알림: await dismissDialogs(page) };
}

/** 현재 화면 글자 (월간일정 등 바탕 화면 글자는 잘라 냄) */
async function screenText(page, limit = 6000) {
  const t = await page.evaluate(() => {
    // 지금 화면 = 보이는 것 중 **가장 바깥** embeddedapp (안쪽 것은 제목줄 같은 부품이다)
    const roots = [...document.querySelectorAll('.cl-mdifolder .cl-tabfolder-body .cl-embeddedapp')]
      .filter(e => e.offsetParent !== null && !e.parentElement.closest('.cl-embeddedapp'));
    const el = roots.length ? roots[roots.length - 1] : document.body;
    return el.innerText;
  });
  return t.replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').slice(0, limit);
}

/** 화면 안 버튼 목록 + 성격(조회/출력/이동/쓰기) */
async function listButtons(page) {
  const { buttonEffect } = require('./safety.js');
  const labels = await page.evaluate(() => {
    // 지금 화면 = 보이는 것 중 **가장 바깥** embeddedapp (안쪽 것은 제목줄 같은 부품이다)
    const roots = [...document.querySelectorAll('.cl-mdifolder .cl-tabfolder-body .cl-embeddedapp')]
      .filter(e => e.offsetParent !== null && !e.parentElement.closest('.cl-embeddedapp'));
    const el = roots.length ? roots[roots.length - 1] : document.body;
    return [...new Set([...el.querySelectorAll('.cl-button')].filter(b => b.offsetParent !== null)
      .map(b => (b.textContent || b.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim()).filter(Boolean))];
  });
  return labels.map(l => ({ 버튼: l, 성격: buttonEffect(l) }));
}

module.exports = { waitLoading, waitOverlayGone, authRequired, dismissDialogs, closePopups, openScreens, activeScreen, closeScreens,
  tabs, searchMenu, openScreen, openSidebar, gotoMenu, clickButton, setDate, clickInnerTab, screenText, listButtons };
