/**
 * NEIS 문항정보표 크롤러 (페이지 주입용)
 *
 * 사용법: 문항정보표관리 화면이 열린 상태에서 이 파일 전체를 page.evaluate()로 주입하면
 *         window.__NEISQ / window.__RESULT / window.__LOG 가 생성된다.
 *
 * 핵심: 그리드 DOM은 가로/세로 가상 스크롤이라 화면에 보이는 셀만 렌더링된다.
 *       따라서 DOM이 아니라 Cleopatra 프레임워크의 DataSet에서 원본 값을 읽는다.
 *
 * 주의: 이 화면은 편집 가능한 폼이다. 저장/마감/삭제 버튼은 절대 클릭하지 않는다.
 */
window.__RESULT = window.__RESULT || [];   // 조회 성공한 (과목 × 고사) 결과 누적
window.__LOG = window.__LOG || [];         // 진행 로그

window.__NEISQ = (() => {
    const delay = ms => new Promise(r => setTimeout(r, ms));
    const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));

    /** dsObt를 가진 app instance = 문항정보표관리 화면 */
    function app() {
        // 같은 화면을 여러 번 열었으면 가장 최근 것
        return cpr.core.Platform.INSTANCE.getAllRunningAppInstances()
            .filter(a => { try { return !!a.lookup('dsObt'); } catch (e) { return false; } }).pop();
    }

    /** NEIS 커스텀 컨트롤은 el.click()만으로는 반응하지 않는 경우가 있어 마우스 시퀀스를 재현한다 */
    function fire(el, type) {
        const r = el.getBoundingClientRect();
        el.dispatchEvent(new MouseEvent(type, {
            bubbles: true, cancelable: true, view: window,
            clientX: r.left + r.width / 2, clientY: r.top + r.height / 2
        }));
    }
    function hardClick(el) { fire(el, 'mousedown'); fire(el, 'mouseup'); fire(el, 'click'); }

    async function waitLoading(maxMs = 40000) {
        const t0 = Date.now();
        await delay(300);
        while (Date.now() - t0 < maxMs) {
            const l = document.querySelector('.ers_progress_content');
            if (!l || !vis(l)) return true;
            await delay(200);
        }
        return false;
    }

    // 콤보박스 aria-label은 "학년도, 2026"처럼 현재값이 붙으므로 prefix로 찾는다
    const combo = lp => Array.from(document.querySelectorAll('[role="combobox"]'))
        .find(c => (c.getAttribute('aria-label') || '').startsWith(lp) && vis(c));

    function comboValue(lp) {
        const c = combo(lp);
        return c ? (c.value ?? c.textContent ?? '').trim() : null;
    }

    async function openCombo(lp) {
        const c = combo(lp);
        if (!c) return false;
        hardClick(c);
        await delay(900);
        return true;
    }
    async function closeCombo(lp) {
        const c = combo(lp);
        if (c) hardClick(c);
        await delay(500);
    }

    const visOpts = () => Array.from(document.querySelectorAll('[role="option"]')).filter(vis);
    const optKey = () => visOpts().map(o => o.textContent.trim()).join('|');
    /** 열린 드롭다운의 가상 스크롤 뷰포트 */
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
     * 옵션 전체 수집.
     * ★ 드롭다운은 가상 스크롤이라 한 번에 10개 안팎만 렌더링된다.
     *   스크롤 없이 읽으면 과목이 조용히 누락된다(실제로 75개 중 24개 누락됨).
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

    /** 화면에 없으면 스크롤하며 찾아서 선택 */
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
                if (optKey() === before) break;   // 바닥
            }
        }
        if (!o) { await closeCombo(lp); return false; }

        o.scrollIntoView({ block: 'nearest' });
        await delay(150);
        hardClick(o);
        await waitLoading();
        await delay(600);
        return true;
    }

    async function clickButton(text) {
        const b = Array.from(document.querySelectorAll('[role="button"]'))
            .find(x => x.textContent.trim() === text && vis(x));
        if (!b) return false;
        hardClick(b);
        await waitLoading();
        await delay(500);
        return true;
    }

    /** 이전 조회 결과가 남아 오염되는 것을 막는다 (조회 직전 호출) */
    function clearData() {
        const a = app();
        ['dsCoranAllot', 'dsObt', 'dsSbjct'].forEach(id => {
            try { a.lookup(id).clearData(); } catch (e) { /* noop */ }
        });
    }

    /** '"3,5",2,4' → ['3,5','2','4'] (복수정답 그룹 보존) */
    function splitCoran(s) {
        if (!s) return [];
        return (s.match(/"[^"]*"|[^,]+/g) || []).map(x => x.replace(/^"|"$/g, '').trim());
    }

    const DFF = { '1': '어려움', '2': '보통', '3': '쉬움' };

    /** 현재 조회된 화면의 문항정보표를 통째로 읽는다 */
    function readCurrent() {
        const a = app();
        if (!a) return { err: 'app not found' };
        const get = id => a.lookup(id);
        const mapObj = d => {
            const o = {};
            d.getColumnNames().forEach(c => { try { o[c] = d.getValue(c); } catch (e) { } });
            return o;
        };
        const meta = mapObj(get('dmSearch'));         // 코드값
        const metaTxt = mapObj(get('dmSearchText'));  // 화면 표시값

        const ca = get('dsCoranAllot');
        const caRow = ca.getRowCount()
            ? (() => { const o = {}; ca.getColumnNames().forEach(c => { o[c] = ca.getValue(0, c); }); return o; })()
            : {};

        // 정답/배점은 dsCoranAllot에 CSV 문자열로 들어있고, 이 길이가 실제 출제 문항 수다.
        // (dsObt는 항상 60행, dsSbjct는 30행 고정이라 빈 행이 섞여 있음)
        const obtAnswers = splitCoran(caRow.obtCoranListCn);
        const obtAllots = splitCoran(caRow.obtAllotListCn);
        const sbjAnswers = splitCoran(caRow.sbjctCoranListCn);
        const sbjAllots = splitCoran(caRow.sbjctAllotListCn);

        const pick = (dsId, cnt, answers, allots, type) => {
            const d = get(dsId);
            const rows = [];
            const n = Math.min(d.getRowCount(), cnt);
            for (let i = 0; i < n; i++) {
                const g = c => { try { return d.getValue(i, c); } catch (e) { return ''; } };
                let ans = answers[i] ?? '';
                if (type === '선택형' && !ans) {
                    // 폴백: col1~col5 체크 상태로 정답 복원
                    ans = [1, 2, 3, 4, 5].filter(k => String(g('col' + k)) === '1').join(',');
                }
                rows.push({
                    구분: type,
                    문항: String(g('quitmNo') || (i + 1)),
                    내용영역: (g('quitmSbmsnCn') || '').trim(),
                    난이도: DFF[String(g('quitmDffly'))] || String(g('quitmDffly') || ''),
                    배점: allots[i] ?? (g('allot') === 0 ? '' : String(g('allot') ?? '')),
                    정답: type === '서답형' ? '' : ans,   // 서답형 정답은 수집 대상 아님(전부 '별지첨부')
                    복수정답: String(g('plsc')) === '1' ? 'Y' : '',
                    성취기준코드: (g('sccesCtrCdList') || '').trim(),
                    성취기준: (g('sccesCtrCn') || '').trim()
                });
            }
            return rows;
        };

        return {
            학년도: metaTxt.ayrNm, 학기: metaTxt.semNm, 고사: metaTxt.exmNm,
            학년: metaTxt.grdNm, 과목: metaTxt.osuCdNm, 과목명: metaTxt.sbjtNm,
            과목코드: meta.sbjtCd, 계열코드: meta.ordScCd, 학과코드: meta.dddepCd, 고사번호: meta.exmNo,
            마감여부: caRow.ddlnYn || '',
            선택형만점: caRow.obtPesScr || '', 서답형만점: caRow.sbjctPesScr || '', 과목만점: caRow.sbjtPesScr || '',
            문항: [
                ...pick('dsObt', obtAllots.length || obtAnswers.length, obtAnswers, obtAllots, '선택형'),
                ...pick('dsSbjct', sbjAllots.length || sbjAnswers.length, sbjAnswers, sbjAllots, '서답형')
            ]
        };
    }

    /** (고사 × 학년) 하나를 돌면서 그 안의 모든 과목을 수집 → window.__RESULT에 누적 */
    async function runChunk(examName, gradeName) {
        const log = [];
        await selectOption('고사', examName);
        await selectOption('계열/학년/학과', gradeName);
        const subjects = await listOptions('과목');   // 과목 목록은 고사/학년에 종속 → 매번 다시 읽는다

        // 이미 수집한 과목은 건너뛴다 (중단 후 재실행 가능)
        const done = window.__RESULT
            .filter(x => x.고사 === examName && String(x.학년) === String(gradeName))
            .map(x => x.과목);

        for (const s of subjects) {
            if (done.includes(s)) continue;
            try {
                if (!await selectOption('과목', s)) { log.push(`${gradeName}/${s}: 과목선택실패`); continue; }
                clearData();
                await clickButton('조회');
                await delay(400);

                const d = readCurrent();
                if (!d.문항 || d.문항.length === 0) { log.push(`${gradeName}/${s}: 데이터없음`); continue; }
                // 이전 조회 결과가 남은 경우를 걸러내는 방어 로직
                if (d.과목 !== s || d.고사 !== examName || String(d.학년) !== String(gradeName)) {
                    log.push(`${gradeName}/${s}: 메타불일치(${d.학년}/${d.과목}/${d.고사}) → 건너뜀`);
                    continue;
                }
                window.__RESULT.push(d);
                log.push(`${gradeName}/${s}: ${d.문항.length}문항 (마감:${d.마감여부})`);
            } catch (e) {
                log.push(`${gradeName}/${s}: 오류 ${e.message}`);
            }
        }
        window.__LOG.push(...log);
        return log;
    }

    /** 누적 결과를 CSV 문자열로 변환 (엑셀용 BOM 포함) */
    function toCSV() {
        const HEAD = ['학년도', '학기', '고사', '학년', '과목', '과목명', '과목코드', '마감여부', '과목만점',
            '구분', '문항', '내용영역', '난이도', '배점', '정답', '복수정답', '성취기준코드', '성취기준'];
        const esc = v => {
            const s = (v ?? '').toString();
            return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
        };
        const lines = [HEAD.join(',')];
        window.__RESULT.forEach(r => r.문항.forEach(q => {
            lines.push([r.학년도, r.학기, r.고사, r.학년, r.과목, r.과목명, r.과목코드, r.마감여부, r.과목만점,
                q.구분, q.문항, q.내용영역, q.난이도, q.배점, q.정답, q.복수정답, q.성취기준코드, q.성취기준]
                .map(esc).join(','));
        }));
        return '﻿' + lines.join('\r\n');
    }

    /** Blob 다운로드 트리거 (Playwright의 download 이벤트로 받아 saveAs) */
    function download(name, content) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([content], { type: 'application/octet-stream' }));
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        return content.length;
    }

    return {
        delay, waitLoading, comboValue, listOptions, selectOption, clickButton,
        clearData, readCurrent, runChunk, toCSV, download
    };
})();
