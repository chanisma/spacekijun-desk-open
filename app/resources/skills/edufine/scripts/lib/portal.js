/**
 * K-에듀파인 업무포털 조작 모듈 (Playwright 드라이버에서 실행)
 *
 * 핵심: 포털 껍데기는 Nexacro지만 **업무화면은 평범한 HTML/JSP**다.
 *       Nexacro를 조작할 필요 없이 화면 URL로 직접 들어가면 된다(세션 쿠키만 있으면 됨).
 *
 *   <baseUrl>/<경로>?MENU_ID=<menuId>     (baseUrl 은 config.json, 화면 목록은 menus.json)
 *
 * 읽기 전용 유틸만 둔다 — 결재/발송/삭제 계열은 넣지 않는다.
 */
const fs = require('fs');
const path = require('path');

const BASE = require('./config.js').config.baseUrl;
const MENUS = JSON.parse(fs.readFileSync(path.join(__dirname, 'menus.json'), 'utf8'));

const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 이름 또는 menuId로 화면 찾기 */
function findScreen(key) {
    return MENUS.find(m => m.이름 === key || m.menuId === key)
        || MENUS.find(m => m.이름.includes(key));
}

function screenUrl(key) {
    const s = findScreen(key);
    if (!s) throw new Error(`화면을 찾을 수 없음: ${key} (menus.json 참고)`);
    return `${BASE}/${s.경로}${s.경로.includes('?') ? '&' : '?'}MENU_ID=${s.menuId}`;
}

/**
 * 업무화면 열기. 포털 셸을 거치지 않는다.
 * 세션이 끊겼으면 로그인 화면이 뜨므로 반환값의 로그인화면 여부를 확인할 것.
 */
async function openScreen(page, key, { timeout = 40000 } = {}) {
    const url = screenUrl(key);
    const res = await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
    await sleep(2500);
    const st = await page.evaluate(() => ({
        title: document.title,
        표: !!document.querySelector('#tbList'),
        행수: document.querySelectorAll('#tbList tbody tr').length,
        총건수: (document.body.innerText.match(/총\s*([\d,]+)\s*건/) || [])[1] || null,
        로그인화면: /로그인/.test(document.title)
    }));
    return { url: url.replace(BASE, ''), status: res ? res.status() : null, ...st };
}

/** 목록 테이블(#tbList)을 객체 배열로 읽는다 */
async function readList(page) {
    return await page.evaluate(() => {
        const t = document.querySelector('#tbList');
        if (!t) return { 헤더: [], 행: [] };
        const head = Array.from(t.querySelectorAll('thead th, tr:first-child th'))
            .map(x => x.textContent.trim());
        const rows = Array.from(t.querySelectorAll('tbody tr')).map(tr =>
            Array.from(tr.querySelectorAll('td')).map(td => td.textContent.replace(/\s+/g, ' ').trim()));
        return { 헤더: head, 행: rows };
    });
}

const 상태 = page => page.evaluate(() => ({
    행수: document.querySelectorAll('#tbList tbody tr').length,
    총건수: (document.body.innerText.match(/총\s*([\d,]+)\s*건/) || [])[1] || null,
    비었음: /조회 결과가 없습니다/.test(document.querySelector('#tbList') ? document.querySelector('#tbList').innerText : '')
}));

/** 목록이 갱신될 때까지 대기 (AJAX라 네비게이션이 없다) */
async function waitList(page, timeoutMs = 30000) {
    const t0 = Date.now();
    let last = -1, stable = 0;
    while (Date.now() - t0 < timeoutMs) {
        const n = await page.evaluate(() => document.querySelectorAll('#tbList tbody tr').length);
        if (n === last) { if (++stable >= 3) return true; } else { stable = 0; last = n; }
        await sleep(400);
    }
    return false;
}

/**
 * 조회 조건 설정 후 재조회.
 *
 * ★ 이 화면들은 **AJAX 조회**다(`fnSearchDataList`). `aform.submit()`으로 직접 제출하면
 *   화면은 다시 그려지지만 "조회 결과가 없습니다"가 나온다 — 반드시 페이지 함수를 호출할 것.
 * 날짜는 표시용(basicReportDe: YYYY-MM-DD)과 전송용(reportDe: YYYYMMDD)이 쌍으로 있어 둘 다 세팅한다.
 * pageUnit 기본 30.
 */
async function search(page, { from, to, pageUnit } = {}) {
    const how = await page.evaluate((a) => {
        const f = document.forms['aform'];
        if (!f) return 'no-form';
        const set = (n, v) => { if (f[n] && v != null) f[n].value = v; };
        if (a.from) { set('basicReportDe', a.from); set('reportDe', a.from.replace(/-/g, '')); }
        if (a.to) { set('basicReportDe3', a.to); set('reportDe3', a.to.replace(/-/g, '')); }
        if (f['retrieveAt']) f['retrieveAt'].value = 'Y';

        // 페이지당 건수는 <select id="pageUnit"> + onchange 핸들러다 (폼 값만 바꾸면 무시된다)
        if (a.pageUnit) {
            const sel = document.getElementById('pageUnit');
            if (sel) {
                sel.value = a.pageUnit;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                if (typeof window.fncPageUnitChange === 'function') window.fncPageUnitChange();
            }
        }
        // 화면별 조회 함수 → 없으면 [조회] 버튼 클릭
        if (typeof window.fncRealSearch === 'function') { window.fncRealSearch(); return 'fncRealSearch'; }
        const btn = document.querySelector('#searchDocBtn, a[title="조회"]');
        if (btn) { btn.click(); return 'searchDocBtn'; }
        return 'no-trigger';
    }, { from, to, pageUnit: pageUnit != null ? String(pageUnit) : null });
    await sleep(2000);
    await waitList(page);
    return { 방식: how, ...(await 상태(page)) };
}

/**
 * 페이지 이동. 페이징 UI는 fncSetPageLiTag가 그리므로 링크를 직접 눌러 옮긴다.
 */
async function gotoPage(page, index) {
    const how = await page.evaluate((i) => {
        const links = Array.from(document.querySelectorAll('a'))
            .filter(a => a.textContent.trim() === String(i) && /page|Page/i.test((a.getAttribute('href') || '') + (a.getAttribute('onclick') || '') + (a.className || '')));
        if (links.length) { links[0].click(); return 'page-link'; }
        const any = Array.from(document.querySelectorAll('#pageList a, .paginate a, .paging a'))
            .find(a => a.textContent.trim() === String(i));
        if (any) { any.click(); return 'page-link2'; }
        return 'no-page-link';
    }, index);
    await sleep(1500);
    await waitList(page);
    return { 방식: how, ...(await 상태(page)) };
}

/**
 * CSV 일괄 내보내기.
 * 화면의 [엑셀다운로드]는 레이어 팝업을 거치지만, 실제 동작은 fncIseIseXlsDwl('a')이며
 * 서버의 *CsvDwld.do 로 요청한다. **현재 조회 조건 전체**를 내보낸다(페이지 단위 아님).
 * 파일 인코딩은 EUC-KR.
 */
async function exportCsv(page, outPath, { timeout = 180000, arg = 'a' } = {}) {
    const has = await page.evaluate(() => typeof window.fncIseIseXlsDwl === 'function');
    if (!has) throw new Error('이 화면에는 CSV 내보내기(fncIseIseXlsDwl)가 없다');
    const [dl] = await Promise.all([
        page.waitForEvent('download', { timeout }),
        page.evaluate(a => window.fncIseIseXlsDwl(a), arg)
    ]);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    await dl.saveAs(outPath);
    return { 파일: outPath, suggested: dl.suggestedFilename() };
}

/** EUC-KR CSV 읽기 (Node 22는 TextDecoder가 euc-kr을 지원한다) */
function readCsvEucKr(file) {
    const buf = fs.readFileSync(file);
    let text;
    try { text = new TextDecoder('euc-kr').decode(buf); }
    catch (e) { text = buf.toString('utf8'); }
    const lines = text.split(/\r?\n/).filter(Boolean);
    const split = l => l.match(/("([^"]|"")*"|[^,]*)(,|$)/g)
        .map(s => s.replace(/,$/, '').replace(/^"|"$/g, '').replace(/""/g, '"'));
    const 헤더 = lines.length ? split(lines[0]) : [];
    const 행 = lines.slice(1).map(split);
    return { 헤더, 행 };
}

/** 알림창(alert/confirm)을 자동으로 받아 넘긴다 — 조회 검증 메시지가 흐름을 막지 않도록 */
function autoDialog(page, sink) {
    page.on('dialog', async d => {
        if (sink) sink.push({ type: d.type(), msg: d.message().slice(0, 200) });
        await d.accept().catch(() => { });
    });
}

module.exports = { BASE, MENUS, findScreen, screenUrl, openScreen, readList, search, gotoPage, waitList, exportCsv, readCsvEucKr, autoDialog };
