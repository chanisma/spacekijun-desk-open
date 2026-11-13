/**
 * NEIS 학교생활기록부(학생부 항목별 조회) 일괄 다운로드 (페이지 주입용)
 *
 * 사용법: NEIS가 열린 상태에서 이 파일을 page.addScriptTag()로 주입하면
 *         window.__NEISR / window.__RLOG 가 생성된다.
 *
 * 핵심: 이 화면의 데이터는 DataSet이 아니라 **Crownix 리포트 뷰어(iframe)** 안에 그려진다.
 *       그래서 값을 읽는 게 아니라 뷰어 툴바의 [저장] → [XLS Data] 를 눌러 XLS로 내려받는다.
 *       다운로드 트리거만 여기서 하고, 파일 저장은 Playwright의 download 이벤트가 받는다.
 *       따라서 항목 순회 루프는 이 스크립트가 아니라 드라이버(Playwright) 쪽에 있어야 한다.
 *
 * 주의: 읽기 전용 작업이다. 저장/마감/삭제 버튼은 절대 클릭하지 않는다.
 */
window.__RLOG = window.__RLOG || [];   // 진행 로그

window.__NEISR = (() => {
    const delay = ms => new Promise(r => setTimeout(r, ms));
    const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
    const log = m => { window.__RLOG.push(`[${new Date().toISOString().slice(11, 19)}] ${m}`); return m; };

    /** 좌측 트리 항목 key → [부모 카테고리, 자식 항목] (extension/content.js의 SECTION_MAP과 동일) */
    const SECTIONS = {
        history:   ['학년반이력',         '학년반이력'],
        hakjeok:   ['인적·학적사항',      '학적사항'],
        attend:    ['출결상황',           '출결상황'],
        volunteer: ['봉사활동상황',       '봉사활동상황'],
        creative:  ['창의적체험활동',     '창의적체험활동'],
        subject:   ['교과학습발달상황',   '교과학습발달상황'],
        sewteuk:   ['교과학습발달상황',   '세부능력및특기사항'],
        reading:   ['독서활동상황',       '독서활동상황'],
        behavior:  ['행동특성및종합의견', '행동특성및종합의견']
    };

    /** NEIS 커스텀 컨트롤은 el.click()에 반응하지 않거나 프레임워크가 죽는 경우가 있어 마우스 시퀀스를 재현한다 */
    function fire(el, type) {
        const r = el.getBoundingClientRect();
        el.dispatchEvent(new MouseEvent(type, {
            bubbles: true, cancelable: true, view: window,
            clientX: r.left + r.width / 2, clientY: r.top + r.height / 2
        }));
    }
    function hardClick(el) { fire(el, 'mousedown'); fire(el, 'mouseup'); fire(el, 'click'); }

    /** 로딩 인디케이터가 사라질 때까지 대기 (메인 문서 + 접근 가능한 iframe) */
    function findLoader() {
        let l = document.querySelector('.ers_progress_content');
        if (l && vis(l)) return l;
        for (const f of document.querySelectorAll('iframe')) {
            try {
                const d = f.contentDocument;
                if (!d) continue;
                l = d.querySelector('.ers_progress_content');
                if (l && vis(l)) return l;
            } catch (e) { /* cross-origin */ }
        }
        return null;
    }
    async function waitLoading(maxMs = 40000) {
        const t0 = Date.now();
        await delay(300);
        while (Date.now() - t0 < maxMs) {
            if (!findLoader()) return true;
            await delay(200);
        }
        log('waitLoading 타임아웃');
        return false;
    }

    // ── 콤보박스 ───────────────────────────────────────────────
    // aria-label에는 현재값이 붙는다("계열/학년/학과, 1학년") → prefix 매칭
    const combo = lp => Array.from(document.querySelectorAll('[role="combobox"]'))
        .find(c => (c.getAttribute('aria-label') || '').startsWith(lp) && vis(c));

    function comboValue(lp) {
        const c = combo(lp);
        return c ? (c.value ?? c.textContent ?? '').trim() : null;
    }

    function comboButton(c) {
        let el = c.parentElement;
        for (let i = 0; i < 5 && el; i++) {
            const b = el.querySelector('.cl-combobox-button');
            if (b) return b;
            el = el.parentElement;
        }
        return null;
    }

    async function openCombo(lp) {
        const c = combo(lp);
        if (!c) return false;
        const b = c.tagName === 'INPUT' ? comboButton(c) : null;
        hardClick(b || c);
        await delay(900);
        return true;
    }
    async function closeCombo(lp) {
        const c = combo(lp);
        if (c) { const b = c.tagName === 'INPUT' ? comboButton(c) : null; hardClick(b || c); }
        await delay(400);
    }

    const visOpts = () => Array.from(document.querySelectorAll('[role="option"]')).filter(vis);
    const optKey = () => visOpts().map(o => o.textContent.trim()).join('|');
    const viewport = () => {
        const lb = Array.from(document.querySelectorAll('[role="listbox"]')).find(vis);
        return lb ? (lb.querySelector('.cl-viewport') || lb) : null;
    };
    const wheel = (vp, dy) => vp.dispatchEvent(new WheelEvent('wheel', { deltaY: dy, bubbles: true, cancelable: true }));
    async function scrollTop(vp) {
        for (let i = 0; i < 40; i++) { wheel(vp, -300); await delay(40); }
        await delay(300);
    }

    /**
     * 콤보 옵션 전체 수집.
     * ★ 드롭다운은 가상 스크롤이라 보이는 10개 안팎만 렌더링된다. 스크롤하지 않으면 조용히 누락된다.
     *   (extension은 이 함정을 피하려고 학년 1~3 / 반 1~9를 하드코딩했다. 여기서는 실제로 읽는다.)
     */
    async function listOptions(lp) {
        if (!await openCombo(lp)) return [];
        const vp = viewport();
        if (!vp) { const o = visOpts().map(x => x.textContent.trim()); await closeCombo(lp); return o; }

        await scrollTop(vp);
        const seen = [];
        let lastKey = '', stale = 0;
        for (let step = 0; step < 200; step++) {
            visOpts().forEach(o => {
                const t = o.textContent.trim();
                if (t && !seen.includes(t)) seen.push(t);
            });
            const cur = optKey();
            if (cur === lastKey) { if (++stale >= 3) break; } else { stale = 0; lastKey = cur; }
            wheel(vp, 200);
            await delay(90);
        }
        await closeCombo(lp);
        return seen;
    }

    /** 화면에 없으면 스크롤하며 찾아 선택 */
    async function selectOption(lp, text) {
        if (!await openCombo(lp)) return false;
        const find = () => visOpts().find(x => x.textContent.trim() === text);

        let o = find();
        const vp = viewport();
        if (!o && vp) {
            await scrollTop(vp);
            for (let step = 0; step < 200; step++) {
                o = find();
                if (o) break;
                const before = optKey();
                wheel(vp, 200);
                await delay(90);
                if (optKey() === before) { wheel(vp, 400); await delay(150); if (optKey() === before) break; }
            }
        }
        if (!o) { await closeCombo(lp); log(`옵션 없음: ${lp}=${text}`); return false; }
        o.scrollIntoView({ block: 'nearest' });
        await delay(100);
        hardClick(o);
        await waitLoading();
        return true;
    }

    /** 텍스트로 버튼 찾아 클릭 (조회 등) */
    async function clickButton(text) {
        const b = Array.from(document.querySelectorAll('button, a[role="button"], [role="button"]'))
            .find(x => x.textContent && x.textContent.trim() === text && vis(x));
        if (!b) { log(`버튼 없음: ${text}`); return false; }
        hardClick(b);
        await waitLoading();
        return true;
    }

    // ── 화면 진입 ──────────────────────────────────────────────
    /** 상단 탭 목록 (텍스트 노드만 — "0단계 메뉴항목" 접미사 제외) */
    function listTabs() {
        return Array.from(document.querySelectorAll('.cl-navigationbar-text.cl-text'))
            .map(d => Array.from(d.childNodes).filter(n => n.nodeType === Node.TEXT_NODE)
                .map(n => n.textContent.trim()).join(''))
            .filter(Boolean);
    }

    async function clickTopTab(name) {
        for (const div of document.querySelectorAll('.cl-navigationbar-text.cl-text')) {
            const text = Array.from(div.childNodes).filter(n => n.nodeType === Node.TEXT_NODE)
                .map(n => n.textContent.trim()).join('');
            if (text === name) { hardClick(div.closest('a') || div.parentElement); await delay(1500); return true; }
        }
        return false;
    }
    async function clickDropdownItem(prefix) {
        for (const it of document.querySelectorAll('.cl-navigationbar-listitem')) {
            const t = it.textContent?.trim();
            if (t && t.startsWith(prefix) && vis(it)) { hardClick(it); await waitLoading(); return true; }
        }
        return false;
    }
    async function clickSidebarItem(prefix) {
        for (const it of document.querySelectorAll('.cl-sidenavigation-item .cl-text')) {
            if (it.textContent?.trim().startsWith(prefix)) {
                hardClick(it.closest('a') || it.parentElement);
                await waitLoading();
                return true;
            }
        }
        return false;
    }

    /**
     * 부서장 탭 → 학교생활기록부 → 학교생활기록부 → [학생부 항목별 조회]
     * ★ 마지막 단계는 사이드바가 아니라 **페이지 안의 프로세스 플로우 링크**다.
     * 탭 이름은 학교마다 다르다(부서장(정보화부) / 부서장(나이스부) …). listTabs()로 확인할 것.
     */
    async function goto(tabName) {
        if (!await clickTopTab(tabName)) return log(`상단 탭 없음: ${tabName} (실제: ${listTabs().join(', ')})`);
        if (!await clickDropdownItem('학교생활기록부')) return log('드롭다운 "학교생활기록부" 없음');
        if (!await clickSidebarItem('학교생활기록부')) return log('사이드바 "학교생활기록부" 없음');

        const link = Array.from(document.querySelectorAll('a, [role="link"], [role="button"], span'))
            .find(e => e.textContent?.trim() === '학생부 항목별 조회' && vis(e));
        if (!link) return log('"학생부 항목별 조회" 링크 없음');
        hardClick(link);
        await waitLoading();
        return log('학생부 항목별 조회 진입');
    }

    // ── 학년/반 선택 + 조회 ────────────────────────────────────
    const listGrades = () => listOptions('계열/학년/학과');
    const listClasses = () => listOptions('반');

    /** 학년·반 선택 후 조회. 반 목록은 학년에 종속되므로 학년을 바꾼 뒤 다시 읽어야 한다. */
    async function prepare(grade, cls) {
        if (!await selectOption('계열/학년/학과', grade)) return false;
        await delay(600);
        if (!await selectOption('반', cls)) return false;
        await delay(400);
        if (!await clickButton('조회')) return false;
        await delay(600);
        log(`조회: ${grade} / ${cls}`);
        return true;
    }

    // ── 좌측 항목 트리 ─────────────────────────────────────────
    const xp = q => document.evaluate(q, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;

    /** 트리도 가상 스크롤이다. 안 보이면 그리드 뷰포트를 굴리며 다시 찾는다. */
    function treeViewport() {
        const grids = Array.from(document.querySelectorAll('[role="grid"], [role="treegrid"]')).filter(vis);
        for (const g of grids) {
            if (g.querySelector('div.expander')) return g.querySelector('.cl-viewport') || g;
        }
        return grids[0] ? (grids[0].querySelector('.cl-viewport') || grids[0]) : null;
    }

    async function findInTree(finder) {
        let el = finder();
        if (el) return el;
        const vp = treeViewport();
        if (!vp) return null;
        for (let i = 0; i < 30; i++) { wheel(vp, -300); await delay(40); }
        for (let i = 0; i < 60; i++) {
            el = finder();
            if (el) return el;
            wheel(vp, 200);
            await delay(90);
        }
        return null;
    }

    /**
     * 좌측 트리에서 항목을 연다.
     * 부모 행은 `<div class="expander collapsed|expanded">`를 가진 그리드 행,
     * 자식 행은 `.cl-text` 리프. 리프에 mousedown → mouseup → click 을 순서대로 보내야 한다
     * (그냥 el.click() 하면 Cleopatra 이벤트 처리에서 죽는 경우가 있다).
     */
    async function openSection(key) {
        const path = SECTIONS[key];
        if (!path) return log(`알 수 없는 항목 key: ${key}`);
        const [parent, child] = path;

        const parentEl = await findInTree(() =>
            xp(`//div[contains(@class,'expander') and contains(., '${parent}')]`));
        if (!parentEl) return log(`부모 항목 없음: ${parent}`);

        if (parentEl.classList.contains('collapsed')) {
            hardClick(parentEl);
            await delay(1000);
        }

        const childEl = await findInTree(() => {
            const e = xp(`//div[contains(@class,'cl-text') and normalize-space(text())='${child}']`);
            return e && vis(e) ? e : null;
        });
        if (!childEl) return log(`자식 항목 없음: ${parent} > ${child}`);

        hardClick(childEl);
        await waitLoading();
        const ready = await waitReport();
        // ★ 툴바가 보여도 리포트가 아직 그려지는 중이면 [저장] 클릭이 그냥 먹히지 않는다
        //   (다운로드 이벤트가 영영 안 와서 타임아웃난다). 렌더 안정화 대기 필수.
        await delay(1500);
        return log(`항목 열기: ${parent} > ${child}${ready ? '' : ' (리포트 미확인)'}`);
    }

    // ── Crownix 리포트 뷰어(iframe) ────────────────────────────
    /** 툴바가 있는(=리포트가 그려진) iframe의 document. 접근 불가면 null */
    function reportDoc() {
        for (const f of document.querySelectorAll('iframe')) {
            if (!vis(f)) continue;
            try {
                const d = f.contentDocument;
                if (d && d.querySelector('#crownix-toolbar-save')) return d;
            } catch (e) { /* cross-origin */ }
        }
        return null;
    }

    async function waitReport(maxMs = 30000) {
        const t0 = Date.now();
        while (Date.now() - t0 < maxMs) {
            if (reportDoc() && !findLoader()) return true;
            await delay(300);
        }
        return false;
    }

    /**
     * 다운로드 트리거: [저장] 클릭 → 포맷 메뉴에서 [XLS Data] 클릭.
     * format: 'xls_data'(원본 데이터, 기본) | 'xls'(서식 포함) | 'pdf' | 'hwp' …
     * ★ 이 함수는 클릭만 한다. 파일 저장은 Playwright의 download 이벤트로 받는다.
     *   반드시 page.waitForEvent('download')를 먼저 걸어두고 호출할 것.
     */
    async function fireExport(format = 'xls_data') {
        const doc = reportDoc();
        if (!doc) return log('리포트 iframe 접근 불가 (렌더 전이거나 cross-origin)');

        const save = doc.querySelector('#crownix-toolbar-save button') || doc.querySelector('#crownix-toolbar-save');
        if (!save) return log('저장 버튼(#crownix-toolbar-save) 없음');
        save.click();

        const sel = `#crownix-toolbar-${format}`;
        let btn = null;
        for (let i = 0; i < 40 && !btn; i++) {         // 최대 10초 폴링 (포맷 메뉴가 늦게 뜬다)
            btn = doc.querySelector(`${sel} button`) || doc.querySelector(sel);
            if (!btn) await delay(250);
        }
        if (!btn) return log(`포맷 버튼 없음: ${sel}`);
        btn.click();
        return log(`내보내기 클릭: ${format}`);
    }

    /**
     * extension과 동일한 파일명 규칙: Grade1_Class1_세부능력및특기사항.xlsx
     * ★ 확장은 .xls로 저장했지만 xls_data가 실제로 내보내는 건 xlsx다(2026-08-31 확인).
     *   .xls로 두면 엑셀이 "형식이 확장자와 다르다"고 경고한다.
     */
    function fileName(gradeNum, classNum, key, ext = 'xlsx') {
        const label = (SECTIONS[key] ? SECTIONS[key][1] : key).replace(/[ /]/g, '_');
        return `Grade${gradeNum}_Class${classNum}_${label}.${ext}`;
    }

    /** 현재 화면 상태 — 다운로드 전 학년/반이 의도한 값인지 대조하는 용도 */
    function status() {
        return {
            학년: comboValue('계열/학년/학과'),
            반: comboValue('반'),
            리포트준비: !!reportDoc(),
            로딩중: !!findLoader()
        };
    }

    return {
        SECTIONS, delay, waitLoading, listTabs, goto,
        listOptions, selectOption, comboValue, clickButton,
        listGrades, listClasses, prepare,
        openSection, reportDoc, waitReport, fireExport,
        fileName, status
    };
})();
