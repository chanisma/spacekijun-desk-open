/**
 * NEIS 학생별시간표조회 일괄 다운로드 (페이지 주입용)
 *
 * 사용법: NEIS가 열린 상태에서 이 파일을 page.addScriptTag()로 주입하면
 *         window.__NEIST / window.__TLOG 가 생성된다.
 *
 * 흐름: 수업시간표 라디오 → 학년/학급 선택 → [조회] → 학생목록 전체선택 → [선택출력]
 *       → Crownix 뷰어(iframe)에 반 전체 시간표가 그려짐 → [저장] → [XLS Data]
 *
 * 다운로드 트리거만 여기서 하고, 파일 저장은 Playwright의 download 이벤트가 받는다.
 *
 * 주의: 읽기 전용 작업이다. 저장/삭제 버튼은 절대 클릭하지 않는다([선택출력]은 인쇄용 조회다).
 */
window.__TLOG = window.__TLOG || [];

window.__NEIST = (() => {
    const delay = ms => new Promise(r => setTimeout(r, ms));
    const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
    const log = m => { window.__TLOG.push(`[${new Date().toISOString().slice(11, 19)}] ${m}`); return m; };

    function fire(el, type) {
        const r = el.getBoundingClientRect();
        el.dispatchEvent(new MouseEvent(type, {
            bubbles: true, cancelable: true, view: window,
            clientX: r.left + r.width / 2, clientY: r.top + r.height / 2
        }));
    }
    function hardClick(el) { fire(el, 'mousedown'); fire(el, 'mouseup'); fire(el, 'click'); }

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
    async function waitLoading(maxMs = 60000) {
        const t0 = Date.now();
        await delay(300);
        while (Date.now() - t0 < maxMs) {
            if (!findLoader()) return true;
            await delay(200);
        }
        log('waitLoading 타임아웃');
        return false;
    }

    // ── 콤보박스 (가상 스크롤 대응) ────────────────────────────
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

    /** ★ 드롭다운은 가상 스크롤이라 보이는 10개 안팎만 렌더링된다. 스크롤 없이 읽으면 조용히 누락된다. */
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

    /**
     * 버튼 찾기 — 이 화면의 [조회]/[선택출력]은 **텍스트가 아니라 aria-label**로 붙는다.
     * 확장의 findButtonByLabel과 같은 방식이되, 텍스트 매칭도 폴백으로 둔다.
     */
    function findButton(label) {
        const all = Array.from(document.querySelectorAll('[role="button"], button'));
        return all.find(b => b.getAttribute('aria-label') === label && vis(b))
            || all.find(b => (b.getAttribute('aria-label') || '').startsWith(label) && vis(b))
            || all.find(b => b.textContent && b.textContent.trim() === label && vis(b));
    }
    async function clickButton(label, wait = true) {
        const b = findButton(label);
        if (!b) { log(`버튼 없음: ${label}`); return false; }
        hardClick(b);
        if (wait) await waitLoading();
        return true;
    }

    // ── 화면 진입 ──────────────────────────────────────────────
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

    /** 부서장(나이스부) → 시간표관리 → 학생별시간표조회 */
    async function goto(tabName) {
        if (!await clickTopTab(tabName)) return log(`상단 탭 없음: ${tabName} (실제: ${listTabs().join(', ')})`);
        if (!await clickDropdownItem('시간표관리')) return log('드롭다운 "시간표관리" 없음');
        if (!await clickSidebarItem('학생별시간표조회')) return log('사이드바 "학생별시간표조회" 없음');
        await delay(800);
        selectClassTimetable();
        return log('학생별시간표조회 진입');
    }

    /**
     * 시간표구분 라디오에서 "수업시간표" 선택.
     * ★ 라벨은 라디오의 aria-label에 있다(전체시간표 / 수업시간표).
     *   확장은 parentElement의 textContent로 찾는데 그 자리는 비어 있어서 항상 폴백(2번째)으로 빠진다.
     *   순서가 바뀌면 조용히 '전체시간표'를 고르게 되므로 aria-label로 찾는다.
     */
    function selectClassTimetable() {
        const group = document.querySelector('[role="radiogroup"]');
        if (!group) return log('라디오 그룹 없음');
        const radios = Array.from(group.querySelectorAll('[role="radio"]'));
        const hit = radios.find(r => (r.getAttribute('aria-label') || '') === '수업시간표')
            || radios.find(r => (r.parentElement?.parentElement?.textContent || '').trim() === '수업시간표')
            || radios.find(r => r.parentElement?.textContent?.trim().includes('수업시간표'));
        if (!hit) return log('수업시간표 라디오 없음');
        if (hit.getAttribute('aria-checked') === 'true') return log('수업시간표 이미 선택됨');
        hardClick(hit);
        return log('수업시간표 선택');
    }

    // ── 학년/학급 ──────────────────────────────────────────────
    // ★ 반 콤보 라벨이 생활기록부 화면과 다르다: 여기는 '학급', 거기는 '반'
    const listGrades = () => listOptions('계열/학년/학과');
    const listClasses = () => listOptions('학급');

    /** 학생목록 그리드 (3열: 번호/성명/…) */
    function studentGrid() {
        const byLabel = document.querySelector('[aria-label="학생목록"]');
        if (byLabel) return byLabel;
        for (const g of document.querySelectorAll('[role="grid"]')) {
            if (!vis(g)) continue;
            for (const row of g.querySelectorAll('[role="row"]')) {
                if (row.querySelectorAll('[role="gridcell"]').length === 3) return g;
            }
        }
        return null;
    }

    /**
     * ★ 그리드는 가상 스크롤이라 이 값은 **렌더된 행 수**다(실제 24명인 반이 18로 나온다).
     *   "빈 반인지" 판정에만 쓰고, 실제 인원 검증은 다운로드된 파일의 학생 블록 수로 한다.
     *   전체선택 체크박스는 렌더 여부와 무관하게 DataSet 전체를 잡으므로 출력에는 영향이 없다.
     */
    function studentCount() {
        const g = studentGrid();
        if (!g) return 0;
        let n = 0;
        for (const row of g.querySelectorAll('[role="row"]')) {
            if (row.querySelectorAll('[role="gridcell"]').length > 0) n++;
        }
        return n;
    }

    /** 헤더행의 전체선택 체크박스 */
    function selectAll() {
        const g = studentGrid();
        if (!g) return log('학생목록 그리드 없음');
        const header = g.querySelector('[role="row"]');
        if (!header) return log('헤더행 없음');
        const cb = header.querySelector('[role="checkbox"], input[type="checkbox"]');
        if (!cb) return log('전체선택 체크박스 없음');
        hardClick(cb);
        return log(`전체선택 (학생 ${studentCount()}명)`);
    }

    /** 학년·학급 선택 후 조회. 학급 목록은 학년에 종속되므로 학년을 바꾼 뒤 다시 읽는다. */
    async function prepare(grade, cls) {
        if (!await selectOption('계열/학년/학과', grade)) return false;
        await delay(600);
        if (!await selectOption('학급', cls)) return false;
        await delay(400);
        if (!await clickButton('조회')) return false;
        await delay(1200);
        log(`조회: ${grade} / ${cls} → 학생 ${studentCount()}명`);
        return true;
    }

    // ── Crownix 리포트 뷰어 ────────────────────────────────────
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

    /**
     * ★ 뷰어가 그려지는 동안 [저장] 버튼은 disable 클래스를 달고 있다.
     *   그 상태에서 누르면 클릭이 조용히 무시되고 다운로드가 영영 시작되지 않는다.
     *   반 전체(25명 안팎)를 한 장에 그리므로 10초 이상 걸리기도 한다.
     */
    async function waitViewerReady(maxMs = 90000) {
        const t0 = Date.now();
        while (Date.now() - t0 < maxMs) {
            const doc = reportDoc();
            if (doc && !findLoader()) {
                const save = doc.querySelector('#crownix-toolbar-save');
                const disabled = save && (save.classList.contains('crownix-toolbar-item-disable')
                    || save.classList.contains('crownix-toolbar-dropitem-disable'));
                if (save && !disabled) { await delay(800); return true; }
            }
            await delay(400);
        }
        log('뷰어 준비 타임아웃');
        return false;
    }

    /** 학생 전체 선택 → [선택출력] → 뷰어 렌더 완료까지 */
    async function printSelected() {
        selectAll();
        await delay(600);
        if (!await clickButton('선택출력')) return false;
        await delay(2000);
        await waitLoading();
        const ok = await waitViewerReady();
        return log(`선택출력 → 뷰어 ${ok ? '준비됨' : '미준비'}`) && ok;
    }

    /**
     * 다운로드 트리거: [저장] → [XLS Data].
     * ★ 클릭만 한다. 파일 저장은 Playwright의 download 이벤트로 받는다.
     */
    async function fireExport(format = 'xls_data') {
        const doc = reportDoc();
        if (!doc) return log('리포트 iframe 접근 불가');

        const save = doc.querySelector('#crownix-toolbar-save button') || doc.querySelector('#crownix-toolbar-save');
        if (!save) return log('저장 버튼 없음');
        save.click();

        const sel = `#crownix-toolbar-${format}`;
        let btn = null;
        for (let i = 0; i < 40 && !btn; i++) {
            btn = doc.querySelector(`${sel} button`) || doc.querySelector(sel);
            if (!btn) await delay(250);
        }
        if (!btn) return log(`포맷 버튼 없음: ${sel}`);
        btn.click();
        return log(`내보내기 클릭: ${format}`);
    }

    /** 확장과 동일한 규칙(확장자만 실제 포맷에 맞춤): Timetable_Grade1_Class1.xlsx */
    function fileName(gradeNum, classNum, ext = 'xlsx') {
        return `Timetable_Grade${gradeNum}_Class${classNum}.${ext}`;
    }

    function status() {
        const doc = reportDoc();
        const save = doc && doc.querySelector('#crownix-toolbar-save');
        return {
            학년: comboValue('계열/학년/학과'),
            학급: comboValue('학급'),
            학생수: studentCount(),
            뷰어준비: !!(save && !save.classList.contains('crownix-toolbar-item-disable')
                && !save.classList.contains('crownix-toolbar-dropitem-disable')),
            로딩중: !!findLoader()
        };
    }

    return {
        delay, waitLoading, listTabs, goto, selectClassTimetable,
        listOptions, selectOption, comboValue, clickButton, findButton,
        listGrades, listClasses, prepare,
        studentGrid, studentCount, selectAll, printSelected,
        reportDoc, waitViewerReady, fireExport, fileName, status
    };
})();
