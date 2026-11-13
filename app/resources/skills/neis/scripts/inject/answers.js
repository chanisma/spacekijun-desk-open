/**
 * NEIS 정기시험학생답관리 크롤러 (페이지 주입용)
 *
 * 사용법: 정기시험학생답관리 화면이 열린 상태에서 page.addScriptTag({path}) 로 주입.
 *         window.__SA / window.__SAROWS / window.__SALOG 가 생성된다.
 *
 * 핵심: 학생 답안은 학생 행을 클릭할 때마다 서버에서 한 명씩 내려온다.
 *       UI 클릭 대신 subStuAnswr submission을 직접 호출하면 학생당 ~100ms로 끝난다.
 *
 * 주의: 편집 가능한 화면이다. 저장/삭제/마감 버튼은 절대 클릭하지 않는다.
 *       개인정보(학생 성명·학번·점수)를 다루므로 산출물 관리에 주의.
 */
window.__SAROWS = window.__SAROWS || [];   // 학생 단위 결과 누적
window.__SALOG = window.__SALOG || [];

window.__SA = (() => {
    const delay = ms => new Promise(r => setTimeout(r, ms));
    const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));

    /** dsStu를 가진 app instance = 정기시험학생답관리 화면 */
    function app() {
        // 다른 화면(앞서 연 화면)에도 dsStu 가 있을 수 있다 → 이 화면의 고사 목록(dsScrExm)까지 가진 **가장 최근** 앱
        return cpr.core.Platform.INSTANCE.getAllRunningAppInstances()
            .filter(a => { try { return !!a.lookup('dsStu') && !!a.lookup('dsScrExm'); } catch (e) { return false; } }).pop();
    }
    const ds = id => app().lookup(id);

    // ---------- 공통 UI 유틸 (문항정보표 크롤러와 동일 패턴) ----------
    function fire(el, type) {
        const r = el.getBoundingClientRect();
        el.dispatchEvent(new MouseEvent(type, {
            bubbles: true, cancelable: true, view: window,
            clientX: r.left + r.width / 2, clientY: r.top + r.height / 2
        }));
    }
    const hardClick = el => { fire(el, 'mousedown'); fire(el, 'mouseup'); fire(el, 'click'); };

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

    const combo = lp => Array.from(document.querySelectorAll('[role="combobox"]'))
        .find(c => (c.getAttribute('aria-label') || '').startsWith(lp) && vis(c));

    /** aria-label은 "강의실, 3학년 고급화학" 형태 → 현재 선택값을 되읽는다 */
    function comboCurrent(lp) {
        const c = combo(lp);
        if (!c) return null;
        const label = c.getAttribute('aria-label') || '';
        const i = label.indexOf(',');
        return i < 0 ? '' : label.slice(i + 1).trim();
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
     * ★ 콤보박스 클릭은 토글이다.
     *   이미 닫힌 드롭다운을 '닫으려고' 한 번 더 클릭하면 오히려 열리고,
     *   그 상태에서 다음 '열기' 클릭이 도리어 닫아버려 옵션을 못 찾는 desync가 생긴다.
     *   (실제로 이 때문에 과목/강의실 선택이 산발적으로 실패했다.)
     *   → 클릭 후 옵션이 실제로 보이는지/사라졌는지 확인하고 재시도한다.
     */
    async function openCombo(lp) {
        const c = combo(lp); if (!c) return false;
        for (let i = 0; i < 3; i++) {
            if (visOpts().length) return true;
            hardClick(combo(lp) || c);
            await delay(900);
            if (visOpts().length) return true;
        }
        return false;
    }
    async function closeCombo(lp) {
        for (let i = 0; i < 3; i++) {
            if (!visOpts().length) return true;
            const c = combo(lp); if (c) hardClick(c);
            await delay(450);
        }
        return !visOpts().length;
    }

    /** ★ 드롭다운은 가상 스크롤이다. 스크롤 없이 읽으면 10개만 잡히고 나머지는 조용히 누락된다 */
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
            wheel(vp, 200); await delay(90);
        }
        await closeCombo(lp);
        return seen;
    }

    async function selectOption(lp, text, attempt = 0) {
        if (!await openCombo(lp)) {
            if (attempt < 2) { await closeCombo(lp); await delay(500); return selectOption(lp, text, attempt + 1); }
            return false;
        }
        const find = () => visOpts().find(x => x.textContent.trim() === text);
        let o = find();
        const vp = viewport();
        if (!o && vp) {
            await scrollTop(vp);
            for (let step = 0; step < 200; step++) {
                o = find();
                if (o) break;
                const before = optKey();
                wheel(vp, 200); await delay(90);
                if (optKey() === before) break;
            }
        }
        if (!o) {
            await closeCombo(lp);
            if (attempt < 2) { await delay(600); return selectOption(lp, text, attempt + 1); }
            return false;
        }
        o.scrollIntoView({ block: 'nearest' });
        await delay(150);
        hardClick(o);
        await waitLoading(); await delay(600);
        return true;
    }

    async function clickButton(text) {
        const b = Array.from(document.querySelectorAll('[role="button"]'))
            .find(x => x.textContent.trim() === text && vis(x));
        if (!b) return false;
        hardClick(b);
        await waitLoading(); await delay(500);
        return true;
    }

    // ---------- 데이터 ----------
    const AFE = { '0': '응시', '1': '인정결', '2': '질병결', '5': '미인정결', '6': '기타결' };

    /** '"3,5",2,,4' → ['3,5','2','','4'] — 복수답 그룹 보존, 빈 칸 유지 */
    function splitList(s) {
        if (!s) return [];
        const out = [];
        let cur = '', inQ = false;
        for (const ch of s) {
            if (ch === '"') { inQ = !inQ; continue; }
            if (ch === ',' && !inQ) { out.push(cur); cur = ''; continue; }
            cur += ch;
        }
        out.push(cur);
        return out;
    }

    /**
     * 현재 조회된 강의실의 전 학생 답안을 수집.
     * 학생 클릭 대신 subStuAnswr를 직접 send() → 학생당 ~100ms
     */
    async function readClassroom(meta) {
        const A = app();
        const dmS = A.lookup('dmSearch'), dm = A.lookup('dmStuAnswr');
        const sb = A.lookup('dmSbjctStuAnswr'), stu = A.lookup('dsStu'), sub = A.lookup('subStuAnswr');
        const sbCols = sb.getColumnNames();          // sbjctSeq1..30 = 서답형 문항별 점수
        const rows = [];

        for (let i = 0; i < stu.getRowCount(); i++) {
            const id = stu.getValue(i, 'stuInvlNo');

            // 이전 학생 값이 남아 오염되지 않도록 비우고 → 학번이 바뀌는 것으로 완료를 감지
            dm.setValue('stuInvlNo', '');
            sbCols.forEach(c => sb.setValue(c, ''));
            dmS.setValue('stuInvlNo', id);
            dmS.setValue('idx', String(i));
            sub.send();

            let ok = false;
            for (let t = 0; t < 60; t++) {
                if (dm.getValue('stuInvlNo') === id) { ok = true; break; }
                await delay(100);
            }
            if (!ok) {
                window.__SALOG.push(`${meta.과목}/${meta.강의실}/${stu.getValue(i, 'stuFlnm')}: 응답없음`);
                continue;
            }

            // ★ 미응답 문항은 빈 칸으로 온다. 빈 칸을 걸러내면 뒤 문항이 앞으로 밀려
            //   답안이 엉뚱한 문항 번호에 붙는다. 반드시 자리(빈 칸)를 유지해야 한다.
            //   문항 수는 항상 문항 수만큼 채워지는 정오(icaDtlCn)로 판단한다.
            const marks = splitList(dm.getValue('icaDtlCn')).filter(x => x !== '');
            const answersAll = splitList(dm.getValue('obtAnswrListCn'));
            let n = marks.length;
            if (!n) {                                   // 채점 전이면 뒤쪽 빈 칸만 잘라낸다
                const t = answersAll.slice();
                while (t.length && t[t.length - 1] === '') t.pop();
                n = t.length;
            }
            const answers = answersAll.slice(0, n);
            const sbjctAns = splitList(dm.getValue('sbjctAnswrListCn')).filter(x => x !== '');
            const itemScores = sbCols.map(c => {
                const v = sb.getValue(c);
                return (v === null || v === undefined) ? '' : String(v);
            });
            const filled = itemScores.filter(x => x !== '');

            rows.push({
                ...meta,
                반: stu.getValue(i, 'clsNm'), 번호: stu.getValue(i, 'clsNoDisplay'),
                성명: stu.getValue(i, 'stuFlnm'), 학번: id,
                타반수강: stu.getValue(i, 'otrClsYn') === 'Y' ? 'Y' : '',
                결시: AFE[String(dm.getValue('afeCd'))] || String(dm.getValue('afeCd') || ''),
                선택형점수: dm.getValue('obtScr'),
                서답형점수: dm.getValue('sbjctScr'),
                기타점수: dm.getValue('etcScr'),
                지필총점: dm.getValue('papEvlScr'),
                // 화면 하단 '서답형점수/문항별점수합'의 오른쪽 값
                문항별점수합: filled.length ? filled.reduce((a, b) => a + (parseFloat(b) || 0), 0) : 0,
                문항별점수: itemScores.slice(0, 30).join('|').replace(/\|+$/, ''),
                답안: answers.join('|'),
                정오: marks.join('|'),
                서답형답안: sbjctAns.join('|'),
                문항수: answers.length
            });
        }
        return rows;
    }

    // ---------- 조회 조건 목록은 DOM 드롭다운이 아니라 DataSet에서 읽는다 ----------
    // 가상 스크롤을 신경 쓸 필요가 없고, 갱신 여부도 즉시 확인할 수 있다.
    const dsList = (id, col = 'nm') => {
        const d = ds(id), out = [];
        for (let i = 0; i < d.getRowCount(); i++) out.push(d.getValue(i, col));
        return out;
    };
    const examList = () => dsList('dsScrExm');
    const gradeList = () => dsList('dsScrOrdGrdDddepCdByGedIacosByExam');
    const subjectList = () => dsList('dsScrOsuCdByGedIacosNestBnByExam');
    const classroomList = () => dsList('dsScrClrmCdByGedIacosByExamSbjt');

    /**
     * ★ 상위 조건을 바꾸면 하위 목록(과목·강의실)이 서버에서 다시 내려온다.
     *   그 갱신을 기다리지 않으면 **이전 학년의 과목 목록**을 그대로 읽어
     *   존재하지도 않는 조합을 계속 조회하게 된다 (실제로 발생했다).
     *   → dmSearch의 코드값이 실제로 바뀔 때까지 폴링한다.
     */
    async function selectVerified(lp, text, field, expected, tries = 3) {
        for (let t = 0; t < tries; t++) {
            if (!await selectOption(lp, text)) { await delay(600); continue; }
            for (let i = 0; i < 40; i++) {
                if (String(ds('dmSearch').getValue(field)) === String(expected)) { await delay(400); return true; }
                await delay(200);
            }
        }
        return false;
    }

    /** 고사/학년 선택 — 반영될 때까지 확인 */
    async function selectExam(examName) {
        const d = ds('dsScrExm');
        let no = null;
        for (let i = 0; i < d.getRowCount(); i++) if (d.getValue(i, 'nm') === examName) no = d.getValue(i, 'exmNo');
        if (no === null) return false;
        return selectVerified('고사', examName, 'exmNo', no);
    }
    async function selectGrade(grade) {
        return selectVerified('계열/학년/학과', grade, 'grd', grade);
    }

    /** (고사 × 학년 × 과목)의 모든 강의실을 순회 */
    async function runSubject(exam, grade, subject) {
        const log = [];
        if (!await selectOption('과목', subject)) { log.push(`${grade}/${subject}: 과목선택실패`); window.__SALOG.push(...log); return log; }
        await delay(600);
        const clrms = classroomList();   // 강의실 목록은 과목에 종속

        let prevSig = '';   // 직전 강의실의 학생 구성 — 조회가 갱신됐는지 판별용

        for (const clrm of clrms) {
            const key = `${exam}|${grade}|${subject}|${clrm}`;
            if (window.__SAROWS.some(r => r._key === key)) continue;   // 재실행 시 건너뛰기
            try {
                /**
                 * ★ 강의실 선택이 반영되지 않은 채 조회되면
                 *   직전 강의실 학생들이 그대로 내려와 '엉뚱한 강의실'로 기록된다.
                 *   (한 학생이 같은 과목의 두 강의실에 잡히는 오귀속이 실제로 발생했다.)
                 *   → ① 콤보 표시값이 실제로 바뀌었는지 ② 학생 구성이 직전과 다른지 두 번 확인한다.
                 */
                let loaded = false, sig = '';
                for (let attempt = 0; attempt < 3 && !loaded; attempt++) {
                    if (!await selectOption('강의실', clrm)) { await delay(500); continue; }
                    if (comboCurrent('강의실') !== clrm) { await delay(500); continue; }

                    ds('dsStu').clearData();
                    await clickButton('조회');
                    await delay(300);

                    const s = ds('dsStu');
                    if (s.getRowCount() === 0) { await delay(600); continue; }
                    sig = Array.from({ length: s.getRowCount() }, (_, k) => s.getValue(k, 'stuInvlNo')).join(',');
                    if (sig === prevSig) { await delay(800); continue; }   // 갱신 안 됨
                    loaded = true;
                }
                if (!loaded) { log.push(`${key}: 조회실패(선택 미반영 또는 학생없음)`); continue; }
                prevSig = sig;

                const meta = {
                    _key: key,
                    학년도: ds('dmSearch').getValue('ayr'), 학기: ds('dmSearch').getValue('sem'),
                    고사: exam, 학년: grade, 과목: subject, 강의실: clrm,
                    과목코드: ds('dmSearch').getValue('sbjtCd')
                };
                const rows = await readClassroom(meta);
                window.__SAROWS.push(...rows);
                log.push(`${key}: ${rows.length}명`);
            } catch (e) {
                log.push(`${key}: 오류 ${e.message}`);
            }
        }
        window.__SALOG.push(...log);
        return log;
    }

    /** (고사 × 학년)의 모든 과목 순회 */
    async function runChunk(exam, grade) {
        if (!await selectExam(exam)) return [`${exam}: 고사선택 반영실패`];
        if (!await selectGrade(grade)) return [`${exam}/${grade}: 학년선택 반영실패`];
        const subjects = subjectList();     // 학년 반영이 확인된 뒤에 읽어야 안전
        const log = [`${exam}/${grade}학년 과목 ${subjects.length}개`];
        for (const s of subjects) log.push(...await runSubject(exam, grade, s));
        window.__SALOG.push(...log);
        return log;
    }

    function toCSV() {
        const HEAD = ['학년도', '학기', '고사', '학년', '과목', '과목코드', '강의실', '반', '번호', '성명', '학번',
            '타반수강', '결시', '선택형점수', '서답형점수', '기타점수', '지필총점', '문항별점수합',
            '문항수', '답안', '정오', '문항별점수', '서답형답안'];
        const esc = v => {
            const s = (v ?? '').toString();
            return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
        };
        const lines = [HEAD.join(',')];
        window.__SAROWS.forEach(r => lines.push(HEAD.map(h => esc(r[h])).join(',')));
        return '﻿' + lines.join('\r\n');
    }

    /** 문항 단위 long 포맷 — 문항정보표(내용영역/난이도/배점/정답)와 조인하기 좋다 */
    function toLongCSV() {
        const HEAD = ['학년도', '학기', '고사', '학년', '과목', '강의실', '반', '번호', '성명', '학번', '문항', '답안', '정오'];
        const esc = v => {
            const s = (v ?? '').toString();
            return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
        };
        const lines = [HEAD.join(',')];
        window.__SAROWS.forEach(r => {
            const a = r.답안 ? r.답안.split('|') : [];
            const m = r.정오 ? r.정오.split('|') : [];
            a.forEach((ans, i) => lines.push([r.학년도, r.학기, r.고사, r.학년, r.과목, r.강의실,
                r.반, r.번호, r.성명, r.학번, i + 1, ans, m[i] ?? ''].map(esc).join(',')));
        });
        return '﻿' + lines.join('\r\n');
    }

    function download(name, content) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([content], { type: 'application/octet-stream' }));
        a.download = name;
        document.body.appendChild(a); a.click(); a.remove();
        return content.length;
    }

    return {
        delay, waitLoading, listOptions, selectOption, clickButton, comboCurrent,
        examList, gradeList, subjectList, classroomList, selectExam, selectGrade,
        readClassroom, runSubject, runChunk, toCSV, toLongCSV, download,
        restore(rows) { window.__SAROWS = rows; return window.__SAROWS.length; }   // 세션 끊김 후 복구용
    };
})();
