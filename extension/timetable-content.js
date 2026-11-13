// 항상 최신 코드로 덮어쓰기 (개발 중 재주입 허용)
window._timetable = (() => {
    let isRunning = false;
    const report = { processed: 0, errors: [] };

    function sendLog(msg, type = 'info') {
        chrome.runtime.sendMessage({ action: "timetable_log", message: msg, type });
        console.log("[Timetable]", msg);
    }

    function sendProgress(current, total, detail) {
        chrome.runtime.sendMessage({ action: "timetable_progress", current, total, detail });
    }

    // 수업시간표 라디오 선택
    function selectClassTimetable() {
        const radioGroup = document.querySelector('[role="radiogroup"]');
        if (radioGroup) {
            const radios = radioGroup.querySelectorAll('[role="radio"]');
            for (const radio of radios) {
                if (radio.parentElement?.textContent?.trim()?.includes('수업시간표')) {
                    radio.click();
                    sendLog('수업시간표 선택됨');
                    return true;
                }
            }
            // fallback: 두 번째 라디오
            if (radios.length >= 2) {
                radios[1].click();
                sendLog('수업시간표 선택됨 (fallback)');
                return true;
            }
        }
        sendLog('수업시간표 라디오를 찾을 수 없음', 'warning');
        return false;
    }

    // 조회 버튼 클릭
    async function clickSearch() {
        const btn = NEISNavigator.findButtonByLabel('조회');
        if (btn) {
            btn.click();
            await NEISNavigator.delay(2000);
            await NEISNavigator.waitForLoading();
            await NEISNavigator.delay(1000);
            return true;
        }
        sendLog('조회 버튼을 찾을 수 없음', 'warning');
        return false;
    }

    // 전체선택 체크박스 클릭
    function clickSelectAll() {
        const grid = document.querySelector('[aria-label="학생목록"]') ||
            NEISNavigator.findGridByColumnCount(3, true);
        if (!grid) return false;

        // 헤더의 전체선택 체크박스 찾기
        const headerRow = grid.querySelector('[role="row"]');
        if (!headerRow) return false;
        const checkbox = headerRow.querySelector('[role="checkbox"], input[type="checkbox"]');
        if (checkbox) {
            checkbox.click();
            sendLog('전체선택 체크');
            return true;
        }
        return false;
    }

    // 선택출력 버튼 클릭
    async function clickSelectPrint() {
        const btn = NEISNavigator.findButtonByLabel('선택출력');
        if (btn) {
            btn.click();
            sendLog('선택출력 클릭');
            await NEISNavigator.delay(3000);
            await NEISNavigator.waitForLoading();
            // Crownix 뷰어 로딩 대기 (25명이면 시간이 좀 걸림)
            await NEISNavigator.delay(5000);
            return true;
        }
        sendLog('선택출력 버튼을 찾을 수 없음', 'warning');
        return false;
    }

    // iframe 내 Crownix 뷰어에서 XLS data 다운로드
    async function downloadFromViewer(filename) {
        const iframes = Array.from(document.querySelectorAll('iframe'));
        const targetIframe = iframes.find(f => NEISNavigator.isVisible(f));

        if (!targetIframe) {
            sendLog('[Download] 보이는 iframe 없음', 'warning');
            return false;
        }

        try {
            const doc = targetIframe.contentDocument;
            if (!doc) {
                sendLog('[Download] iframe 접근 불가', 'warning');
                return false;
            }

            // Crownix 뷰어가 완전히 로드될 때까지 대기
            let retries = 0;
            while (retries < 10) {
                const saveBtn = doc.querySelector('#crownix-toolbar-save');
                if (saveBtn && !saveBtn.classList.contains('crownix-toolbar-item-disable') &&
                    !saveBtn.classList.contains('crownix-toolbar-dropitem-disable')) {
                    break;
                }
                await NEISNavigator.delay(1000);
                retries++;
            }

            const saveBtn = doc.querySelector('#crownix-toolbar-save button') || doc.querySelector('#crownix-toolbar-save');
            if (!saveBtn) {
                sendLog('[Download] 저장 버튼을 찾을 수 없음', 'warning');
                return false;
            }

            chrome.runtime.sendMessage({
                action: "set_filename",
                filename: filename
            });

            saveBtn.click();
            await NEISNavigator.delay(2000);

            const downloadBtn = doc.querySelector('#crownix-toolbar-xls_data button') || doc.querySelector('#crownix-toolbar-xls_data');
            if (!downloadBtn) {
                sendLog('[Download] XLS data 버튼을 찾을 수 없음', 'warning');
                return false;
            }

            window.lastDownloadStarted = false;
            downloadBtn.click();
            sendLog(`[Download] ${filename}`);

            // 다운로드 시작 대기 (반 전체 파일이므로 넉넉히)
            let waitCount = 0;
            while (waitCount < 60) {
                if (window.lastDownloadStarted) {
                    sendLog('[Download] 다운로드 확인됨', 'success');
                    break;
                }
                await NEISNavigator.delay(500);
                waitCount++;
            }

            if (!window.lastDownloadStarted) {
                sendLog('[Download] 다운로드 시작 미확인 (타임아웃)', 'warning');
            }

            // 다운로드 완료 대기
            await NEISNavigator.delay(2000);
            return true;
        } catch (e) {
            sendLog('[Download] 오류: ' + e.message, 'error');
            return false;
        }
    }

    // 학생 수 확인 (그리드 데이터 행 수로 카운트)
    function getStudentCount() {
        const grid = document.querySelector('[aria-label="학생목록"]') ||
            NEISNavigator.findGridByColumnCount(3, true);
        if (!grid) return 0;
        const rows = grid.querySelectorAll('[role="row"]');
        // gridcell이 있는 행만 카운트 (헤더행 제외)
        let count = 0;
        for (const row of rows) {
            if (row.querySelectorAll('[role="gridcell"]').length > 0) count++;
        }
        return count;
    }

    // 메인 자동화 루프
    async function run(config) {
        isRunning = true;
        report.processed = 0;
        report.errors = [];

        const { gradeStart, gradeEnd, classStart, classEnd } = config;
        const totalClasses = (gradeEnd - gradeStart + 1) * (classEnd - classStart + 1);
        let processedClasses = 0;

        sendLog(`시작: ${gradeStart}~${gradeEnd}학년, ${classStart}~${classEnd}반 (${totalClasses}개 반)`);

        // 수업시간표 선택
        selectClassTimetable();
        await NEISNavigator.delay(500);

        for (let grade = gradeStart; grade <= gradeEnd; grade++) {
            if (!isRunning) break;

            sendLog(`--- ${grade}학년 처리 시작 ---`);

            // 학년 선택
            const gradeSelected = await NEISNavigator.selectComboboxOption("계열/학년/학과", String(grade));
            if (gradeSelected) {
                await NEISNavigator.delay(1000);
                await NEISNavigator.waitForLoading();
            } else {
                sendLog('학년 콤보박스를 찾을 수 없음', 'error');
                continue;
            }

            for (let cls = classStart; cls <= classEnd; cls++) {
                if (!isRunning) break;

                sendLog(`>> ${grade}학년 ${cls}반 처리 중...`);

                // 반 선택
                const classSelected = await NEISNavigator.selectComboboxOption("학급", String(cls));
                if (classSelected) {
                    await NEISNavigator.delay(1000);
                    await NEISNavigator.waitForLoading();
                } else {
                    sendLog('반 콤보박스를 찾을 수 없음', 'error');
                    continue;
                }

                // 조회
                await clickSearch();

                // 학생 수 확인
                const count = getStudentCount();
                if (count === 0) {
                    sendLog(`${grade}학년 ${cls}반: 학생 없음`, 'warning');
                    continue;
                }
                sendLog(`${grade}학년 ${cls}반: 학생 ${count}명`);

                // 전체선택
                clickSelectAll();
                await NEISNavigator.delay(500);

                // 선택출력
                await clickSelectPrint();

                // XLS data 다운로드
                const filename = `Timetable_Grade${grade}_Class${cls}.xls`;
                const success = await downloadFromViewer(filename);

                processedClasses++;
                if (success) {
                    report.processed++;
                    sendLog(`${grade}학년 ${cls}반 다운로드 완료`, 'success');
                } else {
                    report.errors.push(`${grade}학년 ${cls}반`);
                }

                sendProgress(processedClasses, totalClasses, `${grade}학년 ${cls}반`);
                await NEISNavigator.delay(1000);
            }
        }

        isRunning = false;
        sendLog(`완료! 처리: ${report.processed}건, 오류: ${report.errors.length}건`, 'success');
        if (report.errors.length > 0) {
            sendLog(`오류 목록: ${report.errors.join(', ')}`, 'warning');
        }
        chrome.runtime.sendMessage({
            action: "timetable_complete",
            report: report
        });
    }

    function stop() {
        isRunning = false;
        sendLog('중지 요청됨', 'warning');
    }

    // 메시지 리스너
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "timetable_start") {
            if (isRunning) {
                sendResponse({ status: "already_running" });
                return;
            }
            run(request.config).catch(e => {
                sendLog('치명적 오류: ' + e.message, 'error');
                isRunning = false;
            });
            sendResponse({ status: "started" });
        } else if (request.action === "timetable_stop") {
            stop();
            sendResponse({ status: "stopped" });
        } else if (request.action === "download_started") {
            window.lastDownloadStarted = true;
        }
    });

    return { run, stop };
})();
