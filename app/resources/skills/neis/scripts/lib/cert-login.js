/**
 * NEIS(4세대) 인증서 자동 로그인 (Playwright)
 *
 * [인증서 로그인] → 메인 문서의 KSignCASE 인증서 위젯 → 인증서 선택 → 암호 → 확인
 *
 * 인증서는 브라우저 프로필이 아니라 로컬 NPKI 저장소에서 KSignCASE 에이전트가 읽으므로
 * Playwright가 띄운 브라우저에서도 그대로 보인다(별도 인증서 설치 불필요).
 *
 * ⚠️ 자격증명은 코드에 넣지 않는다. 데이터 폴더의 credentials.json 에서 읽어 인자로 넘긴다(lib/config.js).
 */

const KC = {
    dialog: '#kc_dialog_default',
    list: '#kc_cert_list',
    password: 'input[name="certPassword"]',
    ok: 'button.kc-btn-blue',
    cancel: 'button.kc-btn-gray'
};

const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 인증서 위젯이 안 뜰 때의 원인 안내 — 첫 실행 권한 승인이 가장 흔하다 */
const CERT_HINT = sys => `${sys} 인증서 위젯이 뜨지 않았습니다.
  1) 처음 쓰는 브라우저 프로필이면 **인증서 프로그램 권한 허용**이 필요합니다.
     열려 있는 창에서 허용한 뒤 다시 실행하세요 (승인은 프로필에 저장돼 다음부터는 안 묻습니다).
  2) 인증서 프로그램(KSignCASE)이 설치돼 있는지 확인하세요.
  3) K-에듀파인은 아이디가 틀려도 위젯이 뜨지 않습니다.`;

/**
 * 로딩 오버레이가 걷힐 때까지 대기.
 * ★ 두 시스템 모두 로딩 중 투명 오버레이(.isloading-overlay / .ers_progress_content)를 깔아 두는데,
 *   이게 클릭을 가로채서 Playwright가 "element intercepts pointer events"로 무한 재시도하다 죽는다.
 */
async function waitOverlayGone(ctx, timeoutMs = 40000) {
    const sels = ['.isloading-overlay', '.ers_progress_content'];
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
        let busy = false;
        for (const s of sels) {
            const on = await ctx.locator(s).first().isVisible().catch(() => false);
            if (on) { busy = true; break; }
        }
        if (!busy) { await sleep(300); return true; }
        await sleep(300);
    }
    return false;
}

/**
 * 오버레이를 통과하는 클릭.
 * ★ .isloading-overlay 는 걷히지 않고 계속 남아 있는 경우가 있다(에이전트 연결 대기 중 등).
 *   Playwright의 click()은 "intercepts pointer events"로 30초를 버티다 실패하므로,
 *   DOM에 마우스 시퀀스를 직접 쏴서 가로채기를 우회한다.
 */
async function domClick(ctx, { selector, text }) {
    return await ctx.evaluate((a) => {
        const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
        let el = null;
        if (a.selector) el = document.querySelector(a.selector);
        if (!el && a.text) {
            el = Array.from(document.querySelectorAll('div,span,button,a'))
                .find(e => e.children.length === 0 && (e.textContent || '').trim() === a.text && vis(e));
        }
        if (!el) return false;
        const r = el.getBoundingClientRect();
        for (const t of ['mousedown', 'mouseup', 'click']) {
            el.dispatchEvent(new MouseEvent(t, {
                bubbles: true, cancelable: true, view: window,
                clientX: r.left + r.width / 2, clientY: r.top + r.height / 2
            }));
        }
        return true;
    }, { selector: selector || null, text: text || null });
}

/** 특정 셀렉터가 나타날 때까지 대기 (첫 실행은 캐시가 없어 느리다) */
async function waitFor(ctx, selector, timeoutMs = 60000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
        if (await ctx.locator(selector).count()) return true;
        await sleep(500);
    }
    return false;
}

/** 위젯이 있는 컨텍스트(page 또는 frame)를 찾는다 */
async function findCertRoot(page, timeoutMs = 20000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
        for (const ctx of [page, ...page.frames()]) {
            try {
                if (await ctx.locator(KC.list).count()) {
                    const visible = await ctx.locator(KC.password).first().isVisible().catch(() => false);
                    if (visible) return ctx;
                }
            } catch (e) { /* 프레임 파기 등 */ }
        }
        await page.waitForTimeout(400);
    }
    return null;
}

/**
 * 인증서 목록의 행들 — probe 면 개수·내용만, 아니면 (certMatch 로 거른) 한 행을 고른다.
 * 행은 KSignCASE 커스텀 테이블뷰라 마우스 시퀀스를 직접 보내야 선택된다. core/portal.py _PICK_CERT 와 같다.
 * ⚠️ 머리글·바깥 상자를 행으로 세지 않는다 — 예전에는 «가장 짧은 글»을 골라 머리글 칸을 누르기도 했다.
 */
async function pickCert(root, certMatch, probe = false) {
    return await root.evaluate((args) => {
        const list = document.querySelector(args.list);
        if (!list) return { status: 'no-list', total: 0 };
        const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
        let rows = Array.from(list.querySelectorAll('tr, li, [role="row"]'))
            .filter(el => visible(el) && (el.textContent || '').trim() && !el.querySelector('th, [role="columnheader"]'));
        if (!list.querySelector('table, tr, li, [role="row"]'))          // div 로 그리는 판
            rows = Array.from(list.querySelectorAll('div')).filter(visible);
        rows = rows.filter(el => (el.textContent || '').trim());
        if (args.probe) return { total: rows.length, signature: rows.map(el => el.textContent).join('\u001f') };
        if (args.match) rows = rows.filter(el => new RegExp(args.match).test(el.textContent || ''));
        rows = rows.filter(el => !rows.some(other => other !== el && el.contains(other)));   // 같은 글을 품은 조상은 빼고
        if (!rows.length) return { status: 'no-row' };
        if (rows.length !== 1) return { status: 'ambiguous', count: rows.length };
        const row = rows[0];
        const cand = Array.from(row.querySelectorAll('.kc-tableview-cell'))
            .find(el => !args.match || new RegExp(args.match).test(el.textContent || '')) || row;
        const r = cand.getBoundingClientRect();
        for (const t of ['mousedown', 'mouseup', 'click']) {
            cand.dispatchEvent(new MouseEvent(t, {
                bubbles: true, cancelable: true, view: window,
                clientX: r.left + r.width / 2, clientY: r.top + r.height / 2
            }));
        }
        return { status: 'selected', text: cand.textContent.replace(/\s+/g, ' ').trim().slice(0, 40) };
    }, { list: KC.list, match: certMatch || null, probe });
}

/**
 * 인증서 목록이 다 찰 때까지 기다린다.
 * ★ 암호 칸이 인증서 프로그램이 목록을 채우기 **전에** 먼저 뜬다. 그때 고르고 암호를 넣으면 목록이 다시 그려지며
 *   선택·암호가 날아가 «암호를 못 넣는» 것처럼 보인다 (데스크 자동 로그인은 이렇게 고쳐 둠 — core/portal.py submit_cert).
 *   행이 있고 0.6초 동안 그대로일 때까지 기다린다.
 */
async function waitCertList(page, root, timeoutMs = 15000) {
    const end = Date.now() + timeoutMs;
    let signature = null, since = 0;
    while (Date.now() < end) {
        const snap = await pickCert(root, null, true).catch(() => ({ total: 0 }));
        if (snap.total) {
            if (snap.signature !== signature) { signature = snap.signature; since = Date.now(); }
            else if (Date.now() - since >= 600) return true;
        } else signature = null;
        await page.waitForTimeout(150);
    }
    return false;
}

/** 암호 칸에 넣고, 정말 들어갔는지 길이로 확인한다 — 안 들어갔으면 눌러서 한 글자씩 다시 친다. */
async function typePassword(page, root, certPassword) {
    const box = root.locator(KC.password).first();
    const length = () => box.evaluate(el => el.value.length).catch(() => -1);
    await box.fill(certPassword);
    await page.waitForTimeout(300);
    if (await length() === certPassword.length) return;
    await box.click({ force: true }).catch(() => {});
    await box.fill('');
    await box.pressSequentially(certPassword, { delay: 60 });
    await page.waitForTimeout(300);
    if (await length() !== certPassword.length) throw new Error('인증서 암호 칸에 암호가 들어가지 않았습니다 — 열린 창에서 직접 넣어 주세요.');
}

/** 인증서 선택 → 암호 입력 → 확인 */
async function submitCert(page, root, certPassword, certMatch) {
    if (!await waitCertList(page, root))
        throw new Error('인증서 창은 열렸지만 목록을 불러오지 못했습니다. 열린 창에서 저장매체와 인증서 목록을 확인해 주세요.');
    const picked = await pickCert(root, certMatch);
    if (picked.status === 'ambiguous')
        throw new Error(`조건에 맞는 인증서가 ${picked.count}개입니다 — certMatch 에 인증서를 구분할 이름(전체 또는 일부)을 적어 주세요.`);
    if (picked.status !== 'selected') throw new Error('인증서 목록에서 인증서를 찾지 못함: ' + picked.status);
    await page.waitForTimeout(500);
    await typePassword(page, root, certPassword);
    await waitOverlayGone(page, 10000);
    await waitOverlayGone(root, 10000);
    // 확인 버튼도 오버레이에 막힐 수 있어 DOM 클릭을 먼저 시도한다
    const clicked = await root.evaluate((sel) => {
        const btn = Array.from(document.querySelectorAll(sel))
            .find(b => (b.textContent || '').trim() === '확인');
        if (!btn) return false;
        const r = btn.getBoundingClientRect();
        for (const t of ['mousedown', 'mouseup', 'click']) {
            btn.dispatchEvent(new MouseEvent(t, {
                bubbles: true, cancelable: true, view: window,
                clientX: r.left + r.width / 2, clientY: r.top + r.height / 2
            }));
        }
        return true;
    }, KC.ok);
    if (!clicked) await root.locator(KC.ok, { hasText: '확인' }).first().click({ force: true });
    return picked.text;
}

/**
 * NEIS 로그인.
 * @returns {Promise<{ok:boolean, user?:string, tabs?:string[]}>}
 */
async function loginNeis(page, { certPassword, certMatch, baseUrl } = {}) {
    if (!baseUrl) throw new Error('baseUrl 필요 (예: https://jbe.neis.go.kr)');
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(4000);

    // 이미 로그인된 세션이면 바로 통과
    if (await page.locator('.cl-navigationbar-text.cl-text').count()) return await neisState(page);

    await waitOverlayGone(page, 15000);
    if (!await domClick(page, { text: '인증서 로그인' }))
        throw new Error('[인증서 로그인] 버튼을 찾지 못함');
    const root = await findCertRoot(page, 40000);
    if (!root) throw new Error(CERT_HINT('NEIS'));

    const picked = await submitCert(page, root, certPassword, certMatch);
    await page.waitForTimeout(10000);
    const st = await neisState(page);
    return { ...st, picked };
}

async function neisState(page) {
    return await page.evaluate(() => {
        const tabs = Array.from(document.querySelectorAll('.cl-navigationbar-text.cl-text'))
            .map(d => Array.from(d.childNodes).filter(n => n.nodeType === 3)
                .map(n => n.textContent.trim()).join('')).filter(Boolean);
        const m = document.body.innerText.match(/([가-힣]+)\(([a-zA-Z0-9_]+)\)/);
        return { ok: tabs.length > 0, user: m ? `${m[1]}(${m[2]})` : null, tabs };
    });
}

/**
 * 포털용 브라우저 실행.
 * ★ 반드시 고정 프로필(persistent context)로 띄운다 — 처음 한 번 하는 인증서 프로그램 권한 허용이 프로필에 남는다.
 * headless 는 쓰지 않는다(인증서 에이전트 연동이 깨진다).
 */
async function launchPortalBrowser({ userDataDir, playwright, channel, viewport, extraArgs } = {}) {
    const pw = playwright || require('playwright');
    if (!userDataDir) throw new Error('userDataDir 필수 — 고정 프로필이어야 권한 승인이 유지된다');
    const opts = {
        headless: false,
        viewport: viewport === undefined ? { width: 1680, height: 1000 } : viewport,   // null = 창 크기에 맞춤
        args: ['--disable-features=IsolateOrigins,site-per-process', ...(extraArgs || [])]
    };
    if (channel) opts.channel = channel;          // 예: 'chrome' — 설치된 크롬 사용
    return await pw.chromium.launchPersistentContext(userDataDir, opts);
}

module.exports = {
    KC, waitOverlayGone, domClick, waitFor, findCertRoot, pickCert, waitCertList, submitCert,
    loginNeis, neisState, launchPortalBrowser
};
