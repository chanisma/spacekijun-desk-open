document.addEventListener('DOMContentLoaded', () => {
    // ========================================
    // 페이지 네비게이션
    // ========================================
    function navigateTo(pageName) {
        document.querySelectorAll('[data-page]').forEach(p => p.classList.remove('active'));
        const target = document.querySelector(`[data-page="${pageName}"]`);
        if (target) target.classList.add('active');
        chrome.storage.local.set({ currentPage: pageName });
    }

    // 메뉴 카드 클릭
    document.querySelectorAll('.menu-card[data-target]').forEach(card => {
        card.addEventListener('click', () => navigateTo(card.dataset.target));
    });

    // 뒤로가기 버튼
    document.querySelectorAll('.back-btn[data-target]').forEach(btn => {
        btn.addEventListener('click', () => navigateTo(btn.dataset.target));
    });

    // 마지막 페이지 상태 복원
    chrome.storage.local.get(['currentPage'], (result) => {
        if (result.currentPage) {
            navigateTo(result.currentPage);
        }
    });

    // ========================================
    // DOM 요소 참조
    // ========================================
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const statusSpan = document.getElementById('status');
    const statusIndicator = document.getElementById('statusIndicator');
    const logDiv = document.getElementById('log');
    const delayInput = document.getElementById('delay');
    const gradeStartInput = document.getElementById('gradeStart');
    const gradeEndInput = document.getElementById('gradeEnd');
    const classStartInput = document.getElementById('classStart');
    const classEndInput = document.getElementById('classEnd');

    // 새로운 UI 요소들
    const progressContainer = document.getElementById('progressContainer');
    const progressFill = document.getElementById('progressFill');
    const progressLabel = document.getElementById('progressLabel');
    const progressStats = document.getElementById('progressStats');
    const progressDetail = document.getElementById('progressDetail');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');
    const selectionBadge = document.getElementById('selectionBadge');
    const clearLogBtn = document.getElementById('clearLogBtn');
    const rangeSummary = document.getElementById('rangeSummary');
    const presetChips = document.querySelectorAll('.preset-chip');

    // ========================================
    // 상태 관리
    // ========================================
    let logMessages = [];
    let isRunning = false;

    // ========================================
    // 상태 업데이트 함수들
    // ========================================
    function updateStatus(text, state = 'idle') {
        statusSpan.textContent = text;
        statusIndicator.classList.remove('active', 'error');
        if (state === 'active') {
            statusIndicator.classList.add('active');
            isRunning = true;
        } else if (state === 'error') {
            statusIndicator.classList.add('error');
            isRunning = false;
        } else {
            isRunning = false;
        }
        updateButtonStates();
    }

    function updateButtonStates() {
        startBtn.disabled = isRunning;
        stopBtn.disabled = !isRunning;
    }

    // ========================================
    // 프로그레스 바 함수들
    // ========================================
    function showProgress() {
        progressContainer.classList.add('visible');
        progressContainer.setAttribute('aria-valuenow', '0');
    }

    function hideProgress() {
        progressContainer.classList.remove('visible');
    }

    function updateProgress(current, total, detail = '') {
        const percentage = Math.round((current / total) * 100);
        progressFill.style.width = `${percentage}%`;
        progressStats.textContent = `${percentage}%`;
        progressLabel.textContent = `${current} / ${total}`;
        progressDetail.textContent = detail;
        progressContainer.setAttribute('aria-valuenow', percentage.toString());
    }

    // ========================================
    // 선택 카운트 업데이트
    // ========================================
    function updateSelectionBadge() {
        const checkboxes = document.querySelectorAll('#sections input[type="checkbox"]');
        const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
        selectionBadge.textContent = `${checkedCount}개 선택`;

        // 선택된 항목이 없으면 경고 스타일
        if (checkedCount === 0) {
            selectionBadge.style.background = 'var(--danger)';
        } else {
            selectionBadge.style.background = 'var(--primary)';
        }
    }

    // ========================================
    // 범위 요약 업데이트
    // ========================================
    function updateRangeSummary() {
        const gradeStart = parseInt(gradeStartInput.value, 10);
        const gradeEnd = parseInt(gradeEndInput.value, 10);
        const classStart = parseInt(classStartInput.value, 10);
        const classEnd = parseInt(classEndInput.value, 10);

        // 범위 유효성 검사
        if (gradeStart > gradeEnd) {
            gradeEndInput.value = gradeStart;
        }
        if (classStart > classEnd) {
            classEndInput.value = classStart;
        }

        const actualGradeEnd = parseInt(gradeEndInput.value, 10);
        const actualClassEnd = parseInt(classEndInput.value, 10);

        const totalGrades = actualGradeEnd - gradeStart + 1;
        const totalClasses = actualClassEnd - classStart + 1;
        const totalCount = totalGrades * totalClasses;

        let gradeText = gradeStart === actualGradeEnd
            ? `${gradeStart}학년`
            : `${gradeStart}~${actualGradeEnd}학년`;
        let classText = classStart === actualClassEnd
            ? `${classStart}반`
            : `${classStart}~${actualClassEnd}반`;

        rangeSummary.textContent = `${gradeText}, ${classText} (총 ${totalCount}개 반)`;

        // 프리셋 활성화 상태 업데이트
        updatePresetActiveState();
    }

    // ========================================
    // 프리셋 활성화 상태 업데이트
    // ========================================
    function updatePresetActiveState() {
        const gradeStart = parseInt(gradeStartInput.value, 10);
        const gradeEnd = parseInt(gradeEndInput.value, 10);
        const classStart = parseInt(classStartInput.value, 10);
        const classEnd = parseInt(classEndInput.value, 10);

        presetChips.forEach(chip => {
            chip.classList.remove('active');
            const preset = chip.dataset.preset;

            if (preset === 'grade1' && gradeStart === 1 && gradeEnd === 1) {
                chip.classList.add('active');
            } else if (preset === 'grade2' && gradeStart === 2 && gradeEnd === 2) {
                chip.classList.add('active');
            } else if (preset === 'grade3' && gradeStart === 3 && gradeEnd === 3) {
                chip.classList.add('active');
            } else if (preset === 'all' && gradeStart === 1 && gradeEnd === 3) {
                chip.classList.add('active');
            }
        });
    }

    // ========================================
    // 프리셋 적용
    // ========================================
    function applyPreset(preset) {
        const classStart = parseInt(classStartInput.value, 10);
        const classEnd = parseInt(classEndInput.value, 10);

        switch (preset) {
            case 'grade1':
                gradeStartInput.value = '1';
                gradeEndInput.value = '1';
                break;
            case 'grade2':
                gradeStartInput.value = '2';
                gradeEndInput.value = '2';
                break;
            case 'grade3':
                gradeStartInput.value = '3';
                gradeEndInput.value = '3';
                break;
            case 'all':
                gradeStartInput.value = '1';
                gradeEndInput.value = '3';
                break;
        }

        updateRangeSummary();
        saveState();
        log(`프리셋 적용: ${preset === 'all' ? '전교생' : preset.replace('grade', '') + '학년'}`);
    }

    // ========================================
    // 로그 함수 (타입 지원)
    // ========================================
    function log(message, type = 'info') {
        const p = document.createElement('div');
        p.className = 'log-entry';

        // 타입별 스타일 적용
        if (type === 'success' || message.includes('완료') || message.includes('성공')) {
            p.classList.add('success');
        } else if (type === 'error' || message.includes('오류') || message.includes('Error') || message.includes('실패')) {
            p.classList.add('error');
        } else if (type === 'warning' || message.includes('경고') || message.includes('Warning')) {
            p.classList.add('warning');
        }

        const msgStr = (typeof message === 'string') ? message : JSON.stringify(message);
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] ${msgStr}`;
        p.textContent = logEntry;
        logDiv.appendChild(p);
        logDiv.scrollTop = logDiv.scrollHeight;

        // 로그 저장 (최대 100개 유지)
        logMessages.push({ entry: logEntry, type });
        if (logMessages.length > 100) logMessages.shift();
        saveState();
    }

    function clearLog() {
        logDiv.innerHTML = '';
        logMessages = [];
        saveState();
        log('로그가 초기화되었습니다.', 'info');
    }

    // ========================================
    // 상태 저장/복원
    // ========================================
    function saveState() {
        const selectedSections = [];
        document.querySelectorAll('#sections input[type="checkbox"]').forEach(cb => {
            if (cb.checked) selectedSections.push(cb.value);
        });

        chrome.storage.local.set({
            sidebarState: {
                gradeStart: gradeStartInput.value,
                gradeEnd: gradeEndInput.value,
                classStart: classStartInput.value,
                classEnd: classEndInput.value,
                delay: delayInput.value,
                selectedSections: selectedSections,
                status: statusSpan.textContent,
                logMessages: logMessages
            }
        });
    }

    function restoreState() {
        chrome.storage.local.get(['sidebarState'], (result) => {
            const state = result.sidebarState;
            if (!state) {
                updateSelectionBadge();
                return;
            }

            // 입력 필드 복원
            if (state.gradeStart) gradeStartInput.value = state.gradeStart;
            if (state.gradeEnd) gradeEndInput.value = state.gradeEnd;
            if (state.classStart) classStartInput.value = state.classStart;
            if (state.classEnd) classEndInput.value = state.classEnd;
            if (state.delay) delayInput.value = state.delay;

            // 체크박스 복원
            if (state.selectedSections) {
                document.querySelectorAll('#sections input[type="checkbox"]').forEach(cb => {
                    cb.checked = state.selectedSections.includes(cb.value);
                });
            }

            // 상태 복원
            if (state.status) statusSpan.textContent = state.status;

            // 로그 복원
            if (state.logMessages && state.logMessages.length > 0) {
                logMessages = state.logMessages;
                logDiv.innerHTML = '';
                logMessages.forEach(item => {
                    const p = document.createElement('div');
                    p.className = 'log-entry';
                    if (item.type === 'success') p.classList.add('success');
                    else if (item.type === 'error') p.classList.add('error');
                    else if (item.type === 'warning') p.classList.add('warning');
                    p.textContent = typeof item === 'string' ? item : item.entry;
                    logDiv.appendChild(p);
                });
                logDiv.scrollTop = logDiv.scrollHeight;
            }

            updateSelectionBadge();
            updateRangeSummary();
        });
    }

    // ========================================
    // 이벤트 리스너 - 프리셋 칩
    // ========================================
    presetChips.forEach(chip => {
        chip.addEventListener('click', () => {
            applyPreset(chip.dataset.preset);
        });
    });

    // ========================================
    // 이벤트 리스너 - 범위 드롭다운
    // ========================================
    [gradeStartInput, gradeEndInput, classStartInput, classEndInput].forEach(input => {
        input.addEventListener('change', () => {
            updateRangeSummary();
            saveState();
        });
    });

    // ========================================
    // 이벤트 리스너 - 딜레이 입력
    // ========================================
    delayInput.addEventListener('change', saveState);

    // ========================================
    // 이벤트 리스너 - 체크박스
    // ========================================
    document.querySelectorAll('#sections input[type="checkbox"]').forEach(cb => {
        cb.addEventListener('change', () => {
            saveState();
            updateSelectionBadge();
        });
    });

    // ========================================
    // 이벤트 리스너 - 전체 선택/해제 버튼
    // ========================================
    selectAllBtn.addEventListener('click', () => {
        document.querySelectorAll('#sections input[type="checkbox"]').forEach(cb => {
            cb.checked = true;
        });
        updateSelectionBadge();
        saveState();
        log('모든 항목이 선택되었습니다.');
    });

    deselectAllBtn.addEventListener('click', () => {
        document.querySelectorAll('#sections input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
        updateSelectionBadge();
        saveState();
        log('모든 항목이 해제되었습니다.');
    });

    // ========================================
    // 이벤트 리스너 - 로그 클리어 버튼
    // ========================================
    clearLogBtn.addEventListener('click', clearLog);

    // ========================================
    // 페이지 로드 시 초기화
    // ========================================
    restoreState();
    updateButtonStates();
    updateRangeSummary();

    // ========================================
    // 스크래퍼 페이지 이동
    // ========================================
    const scraperNavBtn = document.getElementById('scraperNavBtn');
    if (scraperNavBtn) {
        scraperNavBtn.addEventListener('click', async () => {
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) { log('활성 탭을 찾을 수 없습니다.', 'error'); return; }

                scraperNavBtn.disabled = true;
                log('학생부 항목별 조회 페이지로 이동 중...');

                await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    files: ['neis-navigator.js']
                });

                const results = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: async () => {
                        if (!await NEISNavigator.clickTopTab("부서장(정보화부)")) return '부서장(정보화부) 탭을 찾을 수 없습니다';
                        if (!await NEISNavigator.clickDropdownItem("학교생활기록부")) return '학교생활기록부 메뉴를 찾을 수 없습니다';
                        if (!await NEISNavigator.clickSidebarItem("학교생활기록부")) return '학교생활기록부 사이드바를 찾을 수 없습니다';
                        // "학생부 항목별 조회"는 사이드바가 아닌 페이지 내 프로세스 플로우 링크
                        const links = document.querySelectorAll('a, [role="link"], [role="button"], span');
                        let found = false;
                        for (const el of links) {
                            if (el.textContent?.trim() === '학생부 항목별 조회' && NEISNavigator.isVisible(el)) {
                                el.click();
                                await NEISNavigator.waitForLoading();
                                found = true;
                                break;
                            }
                        }
                        if (!found) return '학생부 항목별 조회 링크를 찾을 수 없습니다';
                        return null;
                    }
                });

                const error = results?.[0]?.result;
                if (error) {
                    log(error, 'error');
                } else {
                    log('페이지 이동 완료', 'success');
                }
            } catch (e) {
                log('페이지 이동 오류: ' + e.message, 'error');
            } finally {
                scraperNavBtn.disabled = false;
            }
        });
    }

    // ========================================
    // 스크래핑 시작
    // ========================================
    startBtn.addEventListener('click', async () => {
        log("스크래핑을 시작합니다...");

        try {
            const delay = parseInt(delayInput.value, 10) || 2000;
            const config = {
                gradeStart: parseInt(gradeStartInput.value, 10) || 1,
                gradeEnd: parseInt(gradeEndInput.value, 10) || 3,
                classStart: parseInt(classStartInput.value, 10) || 1,
                classEnd: parseInt(classEndInput.value, 10) || 99
            };

            // 총 작업량 계산
            const totalGrades = config.gradeEnd - config.gradeStart + 1;
            const totalClasses = config.classEnd - config.classStart + 1;
            const totalIterations = totalGrades * totalClasses;

            log(`설정: ${config.gradeStart}~${config.gradeEnd}학년, ${config.classStart}~${config.classEnd}반`);

            // 선택된 섹션 수집
            const selectedSections = [];
            const checkboxes = document.querySelectorAll('#sections input[type="checkbox"]');
            checkboxes.forEach(cb => {
                if (cb.checked) selectedSections.push(cb.value);
            });

            if (selectedSections.length === 0) {
                log("오류: 수집 항목을 선택하세요.", "error");
                return;
            }

            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

            if (!tab) {
                log("오류: 활성 탭을 찾을 수 없습니다.", "error");
                return;
            }

            // 프로그레스 바 표시
            showProgress();
            updateProgress(0, totalIterations, '준비 중...');

            // 메시지 전송 함수
            function sendMessageWithRetry() {
                chrome.tabs.sendMessage(tab.id, {
                    action: "start",
                    delay: delay,
                    config: config,
                    sections: selectedSections
                }, (response) => {
                    if (chrome.runtime.lastError) {
                        const err = chrome.runtime.lastError.message;
                        if (err.includes("Receiving end does not exist") || err.includes("Could not establish connection")) {
                            log("연결 실패. 콘텐츠 스크립트를 주입합니다...", "warning");
                            chrome.scripting.executeScript({
                                target: { tabId: tab.id },
                                files: ['content.js']
                            }, () => {
                                if (chrome.runtime.lastError) {
                                    log("주입 오류: " + chrome.runtime.lastError.message, "error");
                                    hideProgress();
                                } else {
                                    chrome.tabs.sendMessage(tab.id, {
                                        action: "start",
                                        delay: delay,
                                        config: config,
                                        sections: selectedSections
                                    }, (resp2) => {
                                        if (chrome.runtime.lastError) {
                                            log("재시도 실패: " + chrome.runtime.lastError.message, "error");
                                            hideProgress();
                                        } else {
                                            log(`${selectedSections.length}개 항목 수집을 시작합니다.`, "success");
                                            updateStatus("실행 중...", "active");
                                        }
                                    });
                                }
                            });
                        } else {
                            log("메시지 전송 오류: " + err, "error");
                            hideProgress();
                        }
                    } else {
                        log(`${selectedSections.length}개 항목 수집을 시작합니다.`, "success");
                        updateStatus("실행 중...", "active");
                    }
                });
            }

            sendMessageWithRetry();

        } catch (e) {
            log("치명적 오류: " + e.message, "error");
            console.error(e);
            hideProgress();
        }
    });

    // ========================================
    // 스크래핑 중지
    // ========================================
    stopBtn.addEventListener('click', async () => {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab) {
            chrome.tabs.sendMessage(tab.id, { action: "stop" }, (response) => {
                updateStatus("중지됨", "error");
                hideProgress();
                log("스크래핑이 중지되었습니다.", "warning");
            });
        }
    });

    // ========================================
    // 콘텐츠 스크립트로부터 메시지 수신
    // ========================================
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "log") {
            log(request.message, request.type || 'info');
        }

        // 프로그레스 업데이트
        if (request.action === "progress") {
            updateProgress(request.current, request.total, request.detail);
        }

        // 완료 메시지
        if (request.action === "complete") {
            updateStatus("완료", "idle");
            hideProgress();
            log("스크래핑이 완료되었습니다!", "success");
        }

        // 오류 메시지
        if (request.action === "error") {
            updateStatus("오류 발생", "error");
            hideProgress();
            log(request.message, "error");
        }

        // 출결 관리 메시지
        if (request.action === "attendance_log") {
            attendLog_add(request.message, request.type || 'info');
        }

        if (request.action === "attendance_progress") {
            if (attendProgressContainer) {
                if (request.total > 0) {
                    const percentage = Math.round((request.current / request.total) * 100);
                    attendProgressFill.style.width = `${percentage}%`;
                    attendProgressStats.textContent = `${percentage}%`;
                    attendProgressLabel.textContent = `${request.current} / ${request.total}`;
                } else {
                    // total 미확정 (날짜 +/- 버튼 방식) → 처리 건수만 표시
                    attendProgressFill.style.width = '100%';
                    attendProgressStats.textContent = `${request.current}일`;
                    attendProgressLabel.textContent = `${request.current}일 처리`;
                }
                attendProgressDetail.textContent = request.detail || '';
            }
        }

        if (request.action === "attendance_complete") {
            updateAttendStatus('완료', 'idle');
            attendProgressContainer.classList.remove('visible');
            attendLog_add('처리가 완료되었습니다!', 'success');
            showAttendanceReport(request.report);
        }

        // 시간표 메시지
        if (request.action === "timetable_log") {
            ttLog(request.message, request.type || 'info');
        }

        if (request.action === "timetable_progress") {
            if (ttProgressContainer) {
                const percentage = request.total > 0 ? Math.round((request.current / request.total) * 100) : 0;
                ttProgressFill.style.width = `${percentage}%`;
                ttProgressStats.textContent = `${percentage}%`;
                ttProgressLabel.textContent = `${request.current} / ${request.total}`;
                ttProgressDetail.textContent = request.detail || '';
            }
        }

        if (request.action === "timetable_complete") {
            updateTtStatus('완료', 'idle');
            ttProgressContainer.classList.remove('visible');
            ttLog(`완료! 처리: ${request.report.processed}건, 오류: ${request.report.errors.length}건`, 'success');
        }

        // 동아리 활동 메시지
        if (request.action === "club_log") {
            clubLog_add(request.message, request.type || 'info');
        }

        if (request.action === "club_progress") {
            if (clubProgressContainer) {
                if (request.total > 0) {
                    const percentage = Math.round((request.current / request.total) * 100);
                    clubProgressFill.style.width = `${percentage}%`;
                    clubProgressStats.textContent = `${percentage}%`;
                    clubProgressLabel.textContent = `${request.current} / ${request.total}`;
                } else {
                    clubProgressFill.style.width = '100%';
                    clubProgressStats.textContent = `${request.current}건`;
                    clubProgressLabel.textContent = `${request.current}건 처리`;
                }
                if (clubProgressDetail) clubProgressDetail.textContent = request.detail || '';
            }
        }

        if (request.action === "club_complete") {
            updateClubStatus('완료', 'idle');
            if (clubProgressContainer) clubProgressContainer.classList.remove('visible');
            clubLog_add(`처리 완료! 성공: ${request.report.processed.length}건, 오류: ${request.report.errors.length}건`, 'success');
            if (request.report.errors.length > 0) {
                request.report.errors.forEach(e => {
                    clubLog_add(`  오류: ${e.dept || ''} ${e.date || ''} - ${e.error}`, 'error');
                });
            }
        }
    });

    // ========================================
    // 전처리 기능
    // ========================================
    const fileInput = document.getElementById('fileInput');
    const selectFilesBtn = document.getElementById('selectFilesBtn');
    const selectedFilesDiv = document.getElementById('selectedFiles');
    const preprocessBtn = document.getElementById('preprocessBtn');
    const preprocessResult = document.getElementById('preprocessResult');

    let selectedFiles = [];

    selectFilesBtn.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        selectedFiles = Array.from(e.target.files);

        if (selectedFiles.length > 0) {
            selectedFilesDiv.style.display = 'block';
            selectedFilesDiv.innerHTML = '<strong>선택된 파일:</strong><br>' +
                selectedFiles.map(f => `- ${f.name}`).join('<br>');

            preprocessBtn.style.display = 'block';
            preprocessResult.style.display = 'none';

            log(`${selectedFiles.length}개 파일이 선택되었습니다.`);
        } else {
            selectedFilesDiv.style.display = 'none';
            preprocessBtn.style.display = 'none';
        }
    });

    // 전처리 단계 UI 관리
    const preprocessSteps = document.getElementById('preprocessSteps');
    const stepsList = document.getElementById('stepsList');
    const stepPreview = document.getElementById('stepPreview');
    const previewTitle = document.getElementById('previewTitle');
    const previewThead = document.getElementById('previewThead');
    const previewTbody = document.getElementById('previewTbody');
    const previewInfo = document.getElementById('previewInfo');
    const previewDownloadBtn = document.getElementById('previewDownloadBtn');
    const previewCloseBtn = document.getElementById('previewCloseBtn');

    let lastSnapshots = null;
    let lastFilename = '';
    const PREVIEW_MAX_ROWS = 20;

    function initStepsUI() {
        const defs = Preprocessor.getStepDefinitions();
        preprocessSteps.style.display = 'block';
        stepPreview.style.display = 'none';
        lastSnapshots = null;
        stepsList.innerHTML = defs.map(step =>
            `<div class="step-item" id="step-${step.id}" data-step="${step.id}">
                <span class="step-icon"><span class="pending-dot"></span></span>
                <span class="step-content">
                    <span class="step-label">${step.label}</span>
                    <span class="step-detail">${step.desc}</span>
                </span>
            </div>`
        ).join('');
    }

    function updateStepUI(stepId, detail) {
        const el = document.getElementById(`step-${stepId}`);
        if (!el) return;

        // 이전 active 상태 제거
        stepsList.querySelectorAll('.step-item.active').forEach(item => {
            item.classList.remove('active');
            item.classList.add('done');
            item.querySelector('.step-icon').innerHTML =
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        });

        // 현재 단계 active
        el.classList.add('active');
        if (detail) {
            el.querySelector('.step-detail').textContent = detail;
        }
    }

    function finalizeStepsUI(snapshots) {
        lastSnapshots = snapshots;
        stepsList.querySelectorAll('.step-item.active').forEach(item => {
            item.classList.remove('active');
            item.classList.add('done');
            item.querySelector('.step-icon').innerHTML =
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        });

        // extract 단계는 테이블 데이터가 없으므로 제외
        stepsList.querySelectorAll('.step-item.done').forEach(item => {
            const stepId = item.dataset.step;
            if (stepId !== 'extract' && snapshots && snapshots[stepId]) {
                item.classList.add('clickable');
            }
        });
    }

    function escapeHtml(str) {
        const val = String(str ?? '');
        return val.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function showStepPreview(stepId) {
        if (!lastSnapshots || !lastSnapshots[stepId]) return;
        const snap = lastSnapshots[stepId];
        const defs = Preprocessor.getStepDefinitions();
        const def = defs.find(d => d.id === stepId);

        // 선택 표시
        stepsList.querySelectorAll('.step-item.selected').forEach(el => el.classList.remove('selected'));
        const stepEl = document.getElementById(`step-${stepId}`);
        if (stepEl) stepEl.classList.add('selected');

        previewTitle.textContent = def ? def.label : stepId;

        // 헤더
        const headers = snap.headers || [];
        previewThead.innerHTML = '<tr><th class="row-num">#</th>' +
            headers.map(h => `<th>${escapeHtml(h)}</th>`).join('') +
            '</tr>';

        // 본문 (최대 PREVIEW_MAX_ROWS행)
        const showRows = snap.rows.slice(0, PREVIEW_MAX_ROWS);
        previewTbody.innerHTML = showRows.map((row, i) => {
            const cells = Array.isArray(row) ? row : Object.values(row);
            return '<tr><td class="row-num">' + (i + 1) + '</td>' +
                cells.map(c => {
                    const val = String(c ?? '');
                    const display = val.length > 80 ? val.slice(0, 80) + '...' : val;
                    return `<td title="${escapeHtml(val)}">${escapeHtml(display)}</td>`;
                }).join('') +
                '</tr>';
        }).join('');

        // 하단 정보
        if (snap.totalRows > PREVIEW_MAX_ROWS) {
            previewInfo.textContent = `${PREVIEW_MAX_ROWS}행 미리보기 / 전체 ${snap.totalRows}행`;
        } else {
            previewInfo.textContent = `전체 ${snap.totalRows}행`;
        }

        // 다운로드 버튼에 현재 단계 기억
        previewDownloadBtn.dataset.stepId = stepId;

        stepPreview.style.display = 'block';
    }

    // 단계 클릭 이벤트 (이벤트 위임)
    stepsList.addEventListener('click', (e) => {
        const item = e.target.closest('.step-item.clickable');
        if (!item) return;
        showStepPreview(item.dataset.step);
    });

    // 미리보기 닫기
    previewCloseBtn.addEventListener('click', () => {
        stepPreview.style.display = 'none';
        stepsList.querySelectorAll('.step-item.selected').forEach(el => el.classList.remove('selected'));
    });

    // 중간 결과 Excel 다운로드
    previewDownloadBtn.addEventListener('click', () => {
        const stepId = previewDownloadBtn.dataset.stepId;
        if (!lastSnapshots || !lastSnapshots[stepId]) return;

        const snap = lastSnapshots[stepId];
        const headers = snap.headers || [];
        const aoa = [headers, ...snap.rows.map(r => Array.isArray(r) ? r : Object.values(r))];

        const ws = XLSX.utils.aoa_to_sheet(aoa);
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
        const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
        const blob = new Blob([wbout], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });

        const defs = Preprocessor.getStepDefinitions();
        const def = defs.find(d => d.id === stepId);
        const stepLabel = def ? def.label.replace(/\s/g, '_') : stepId;
        const fname = lastFilename.replace(/\.xlsx?$/i, '') + `_step_${stepLabel}.xlsx`;
        downloadBlob(blob, fname);
    });

    preprocessBtn.addEventListener('click', async () => {
        if (selectedFiles.length === 0) {
            log('파일을 먼저 선택하세요.', 'warning');
            return;
        }

        preprocessBtn.disabled = true;
        preprocessBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="animation: spin 1s linear infinite;" aria-hidden="true"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg> 처리 중...';
        log('전처리를 시작합니다...');

        // 전처리 단계 UI 초기화
        initStepsUI();

        try {
            const results = [];
            let totalOriginal = 0;
            let totalFinal = 0;
            const allStudents = new Set();
            const allSubjects = new Set();
            let latestSnapshots = null;

            for (let i = 0; i < selectedFiles.length; i++) {
                const file = selectedFiles[i];
                log(`처리 중: ${file.name} (${i + 1}/${selectedFiles.length})`);

                const isLastFile = i === selectedFiles.length - 1;
                const buffer = await file.arrayBuffer();
                const result = Preprocessor.preprocess(buffer, file.name, isLastFile ? updateStepUI : null);

                if (isLastFile) {
                    latestSnapshots = result.snapshots;
                    lastFilename = file.name;
                }

                results.push({
                    filename: file.name,
                    data: result.data,
                    stats: result.stats
                });

                totalOriginal += result.stats.originalRows;
                totalFinal += result.stats.finalRows;
                result.stats.students.forEach(s => allStudents.add(s));
                result.stats.subjects.forEach(s => allSubjects.add(s));

                log(`  ${file.name}: ${result.stats.originalRows}행 → ${result.stats.finalRows}행`, 'success');
            }

            finalizeStepsUI(latestSnapshots);

            // 결과 표시
            preprocessResult.style.display = 'block';
            preprocessResult.style.background = 'var(--success-light)';
            preprocessResult.style.borderColor = 'var(--success)';
            preprocessResult.style.color = 'var(--success-hover)';
            preprocessResult.innerHTML = `
                <strong>전처리 완료!</strong><br>
                파일: ${results.length}개<br>
                원본: ${totalOriginal}행 → 최종: ${totalFinal}행<br>
                학생: ${allStudents.size}명 / 과목: ${allSubjects.size}개
            `;

            log('전처리가 완료되었습니다!', 'success');

            // 파일 다운로드
            if (results.length === 1) {
                const blob = Preprocessor.toExcel(results[0].data, results[0].filename);
                downloadBlob(blob, results[0].filename.replace(/\.xlsx?$/i, '_preprocessed.xlsx'));
            } else {
                for (const r of results) {
                    const blob = Preprocessor.toExcel(r.data, r.filename);
                    downloadBlob(blob, r.filename.replace(/\.xlsx?$/i, '_preprocessed.xlsx'));
                    await new Promise(resolve => setTimeout(resolve, 500));
                }

                const merged = Preprocessor.mergeResults(results);
                const mergedBlob = Preprocessor.toExcel(merged, 'merged');
                downloadBlob(mergedBlob, 'All_Classes_preprocessed.xlsx');
                log('합쳐진 파일도 다운로드됨: All_Classes_preprocessed.xlsx', 'success');
            }

        } catch (error) {
            log('전처리 오류: ' + error.message, 'error');
            console.error(error);
            preprocessResult.style.display = 'block';
            preprocessResult.style.background = 'var(--danger-light)';
            preprocessResult.style.borderColor = 'var(--danger)';
            preprocessResult.style.color = 'var(--danger-hover)';
            preprocessResult.innerHTML = `<strong>오류 발생:</strong><br>${error.message}`;
        } finally {
            preprocessBtn.disabled = false;
            preprocessBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg> 전처리 실행';
        }
    });

    function downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        log(`다운로드: ${filename}`, 'success');
    }

    // ========================================
    // 출결 관리 기능
    // ========================================
    const attendStartBtn = document.getElementById('attendStartBtn');
    const attendStopBtn = document.getElementById('attendStopBtn');
    const attendStatus = document.getElementById('attendStatus');
    const attendStatusIndicator = document.getElementById('attendStatusIndicator');
    const attendStartDate = document.getElementById('attendStartDate');
    const attendEndDate = document.getElementById('attendEndDate');
    const attendProgressContainer = document.getElementById('attendProgressContainer');
    const attendProgressFill = document.getElementById('attendProgressFill');
    const attendProgressLabel = document.getElementById('attendProgressLabel');
    const attendProgressStats = document.getElementById('attendProgressStats');
    const attendProgressDetail = document.getElementById('attendProgressDetail');
    const attendLog = document.getElementById('attendLog');
    const attendClearLogBtn = document.getElementById('attendClearLogBtn');
    const attendCheckClosed = document.getElementById('attendCheckClosed');
    const attendReadOnly = document.getElementById('attendReadOnly');
    const attendReport = document.getElementById('attendReport');
    const attendReportContent = document.getElementById('attendReportContent');

    let attendRunning = false;

    // 날짜 초기값 설정 (이번 달 첫날 ~ 마지막날)
    function formatDateForInput(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }

    // 주말이면 평일로 보정 (시작일→다음 월요일, 종료일→이전 금요일)
    function adjustToWeekday(dateStr, preferNext) {
        const d = new Date(dateStr + 'T00:00:00');
        const day = d.getDay();
        if (day === 0) d.setDate(d.getDate() + (preferNext ? 1 : -2));
        else if (day === 6) d.setDate(d.getDate() + (preferNext ? 2 : -1));
        return formatDateForInput(d);
    }

    if (attendStartDate && attendEndDate) {
        const now = new Date();
        const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
        const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        attendStartDate.value = adjustToWeekday(formatDateForInput(firstDay), true);
        attendEndDate.value = adjustToWeekday(formatDateForInput(lastDay), false);

        attendStartDate.addEventListener('change', () => {
            attendStartDate.value = adjustToWeekday(attendStartDate.value, true);
        });
        attendEndDate.addEventListener('change', () => {
            attendEndDate.value = adjustToWeekday(attendEndDate.value, false);
        });
    }

    function attendLog_add(message, type = 'info') {
        if (!attendLog) return;
        const p = document.createElement('div');
        p.className = 'log-entry';
        if (type === 'success' || message.includes('완료') || message.includes('성공')) {
            p.classList.add('success');
        } else if (type === 'error' || message.includes('오류') || message.includes('실패')) {
            p.classList.add('error');
        } else if (type === 'warning' || message.includes('경고')) {
            p.classList.add('warning');
        }
        const timestamp = new Date().toLocaleTimeString();
        p.textContent = `[${timestamp}] ${message}`;
        attendLog.appendChild(p);
        attendLog.scrollTop = attendLog.scrollHeight;
    }

    function updateAttendStatus(text, state = 'idle') {
        if (!attendStatus) return;
        attendStatus.textContent = text;
        attendStatusIndicator.classList.remove('active', 'error');
        if (state === 'active') {
            attendStatusIndicator.classList.add('active');
            attendRunning = true;
        } else if (state === 'error') {
            attendStatusIndicator.classList.add('error');
            attendRunning = false;
        } else {
            attendRunning = false;
        }
        if (attendStartBtn) attendStartBtn.disabled = attendRunning;
        if (attendStopBtn) attendStopBtn.disabled = !attendRunning;
    }

    let lastAttendReport = null;

    function showAttendanceReport(report) {
        if (!attendReport || !attendReportContent) return;
        lastAttendReport = report;
        attendReport.style.display = 'block';

        let html = '<div class="report-summary">';
        html += `<span class="report-badge success">입력: ${report.processed.length}건</span>`;
        html += `<span class="report-badge warning">기록: ${report.needsReview.length}건</span>`;
        if (report.errors.length > 0) {
            html += `<span class="report-badge error">오류: ${report.errors.length}건</span>`;
        }
        html += `<button id="attendDownloadBtn" class="log-clear-btn" style="margin-left:auto;font-size:11px;padding:4px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);">Excel 다운로드</button>`;
        html += '</div>';

        // 출석인정 전체 기록
        if (report.needsReview.length > 0) {
            html += '<div class="report-section-title">출석인정 기록</div>';
            html += '<div style="max-height:300px;overflow-y:auto;">';
            html += '<table class="report-table"><thead><tr>';
            html += '<th>날짜</th><th>교시</th><th>학년</th><th>반</th><th>번호</th><th>이름</th><th>상태</th><th>비고</th><th>일출결사유</th><th>과목</th><th>마감</th>';
            html += '</tr></thead><tbody>';
            for (const item of report.needsReview) {
                html += `<tr><td>${escHtml(item.date)}</td><td>${escHtml(item.period || '')}</td><td>${escHtml(item.grade)}</td><td>${escHtml(item.class)}</td><td>${escHtml(item.num)}</td><td>${escHtml(item.name)}</td><td>${escHtml(item.status)}</td><td>${escHtml(item.bigo || '')}</td><td>${escHtml(item.reason || '')}</td><td>${escHtml(item.subject || '')}</td><td>${escHtml(item.closed || '')}</td></tr>`;
            }
            html += '</tbody></table></div>';
        }

        // 자동 입력 완료 목록
        if (report.processed.length > 0) {
            html += '<div class="report-section-title">자동 입력 완료</div>';
            html += '<div style="max-height:200px;overflow-y:auto;">';
            html += '<table class="report-table"><thead><tr>';
            html += '<th>날짜</th><th>학년</th><th>반</th><th>번호</th><th>이름</th><th>과목</th>';
            html += '</tr></thead><tbody>';
            for (const item of report.processed) {
                html += `<tr><td>${escHtml(item.date)}</td><td>${escHtml(item.grade)}</td><td>${escHtml(item.class)}</td><td>${escHtml(item.num)}</td><td>${escHtml(item.name)}</td><td>${escHtml(item.subject || '')}</td></tr>`;
            }
            html += '</tbody></table></div>';
        }

        attendReportContent.innerHTML = html;

        // 다운로드 버튼 이벤트
        const dlBtn = document.getElementById('attendDownloadBtn');
        if (dlBtn) {
            dlBtn.addEventListener('click', () => downloadAttendReport(lastAttendReport));
        }
    }

    function downloadAttendReport(report) {
        if (!report) return;
        const headers = ['날짜', '교시', '학년', '반', '번호', '이름', '상태', '비고', '일출결사유', '과목', '마감', '구분'];
        const rows = [];
        for (const item of report.needsReview) {
            rows.push([item.date, item.period || '', item.grade, item.class, item.num, item.name, item.status, item.bigo || '', item.reason || '', item.subject || '', item.closed || '', '기록']);
        }
        for (const item of report.processed) {
            rows.push([item.date, item.period || '', item.grade, item.class, item.num, item.name, item.status, item.bigo || '', item.reason || '', item.subject || '', item.closed || '', '자동입력']);
        }
        const aoa = [headers, ...rows];
        const ws = XLSX.utils.aoa_to_sheet(aoa);
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, '출석인정기록');
        const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
        const blob = new Blob([wbout], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
        const now = new Date();
        const dateStr = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}`;
        downloadBlob(blob, `출석인정기록_${dateStr}.xlsx`);
    }

    function escHtml(str) {
        const val = String(str ?? '');
        return val.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // 페이지 이동 버튼
    const attendNavBtn = document.getElementById('attendNavBtn');
    if (attendNavBtn) {
        attendNavBtn.addEventListener('click', async () => {
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) { attendLog_add('활성 탭을 찾을 수 없습니다.', 'error'); return; }

                attendNavBtn.disabled = true;
                attendLog_add('과목별출결관리 페이지로 이동 중...');

                await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    files: ['neis-navigator.js']
                });

                const results = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: async () => {
                        if (!await NEISNavigator.clickTopTab("교과담임")) return '교과담임 탭을 찾을 수 없습니다';
                        if (!await NEISNavigator.clickDropdownItem("출결관리")) return '출결관리 메뉴를 찾을 수 없습니다';
                        if (!await NEISNavigator.clickSidebarItem("과목별출결관리")) return '과목별출결관리를 찾을 수 없습니다';
                        return null;
                    }
                });

                const error = results?.[0]?.result;
                if (error) {
                    attendLog_add(error, 'error');
                } else {
                    attendLog_add('페이지 이동 완료', 'success');
                }
            } catch (e) {
                attendLog_add('페이지 이동 오류: ' + e.message, 'error');
            } finally {
                attendNavBtn.disabled = false;
            }
        });
    }

    // 시작 버튼
    if (attendStartBtn) {
        attendStartBtn.addEventListener('click', async () => {
            if (!attendStartDate.value || !attendEndDate.value) {
                attendLog_add('시작일과 종료일을 설정하세요.', 'warning');
                return;
            }

            attendLog_add('출결 비고 자동 관리를 시작합니다...');
            updateAttendStatus('실행 중...', 'active');
            attendReport.style.display = 'none';
            attendProgressContainer.classList.add('visible');

            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) {
                    attendLog_add('활성 탭을 찾을 수 없습니다.', 'error');
                    updateAttendStatus('오류', 'error');
                    return;
                }

                // neis-navigator.js + attendance-content.js 순서대로 주입
                await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    files: ['neis-navigator.js', 'attendance-content.js']
                });

                const startDateStr = attendStartDate.value.replace(/-/g, '.');
                const endDateStr = attendEndDate.value.replace(/-/g, '.');

                chrome.tabs.sendMessage(tab.id, {
                    action: "attendance_start",
                    config: {
                        startDate: startDateStr,
                        endDate: endDateStr,
                        checkClosed: attendCheckClosed?.checked || false,
                        readOnly: attendReadOnly?.checked || false
                    }
                }, (response) => {
                    if (chrome.runtime.lastError) {
                        attendLog_add('메시지 전송 실패: ' + chrome.runtime.lastError.message, 'error');
                        updateAttendStatus('오류', 'error');
                        attendProgressContainer.classList.remove('visible');
                    } else {
                        attendLog_add(`범위: ${startDateStr} ~ ${endDateStr}`, 'success');
                    }
                });
            } catch (e) {
                attendLog_add('오류: ' + e.message, 'error');
                updateAttendStatus('오류', 'error');
                attendProgressContainer.classList.remove('visible');
            }
        });
    }

    // 중지 버튼
    if (attendStopBtn) {
        attendStopBtn.addEventListener('click', async () => {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                chrome.tabs.sendMessage(tab.id, { action: "attendance_stop" });
            }
            updateAttendStatus('중지됨', 'error');
            attendProgressContainer.classList.remove('visible');
            attendLog_add('중지되었습니다.', 'warning');
        });
    }

    // 로그 클리어 버튼
    if (attendClearLogBtn) {
        attendClearLogBtn.addEventListener('click', () => {
            if (attendLog) attendLog.innerHTML = '';
            attendLog_add('로그가 초기화되었습니다.');
        });
    }

    // ========================================
    // 시간표 추출 페이지
    // ========================================
    const ttStartBtn = document.getElementById('ttStartBtn');
    const ttStopBtn = document.getElementById('ttStopBtn');
    const ttStatus = document.getElementById('ttStatus');
    const ttStatusIndicator = document.getElementById('ttStatusIndicator');
    const ttGradeStart = document.getElementById('ttGradeStart');
    const ttGradeEnd = document.getElementById('ttGradeEnd');
    const ttClassStart = document.getElementById('ttClassStart');
    const ttClassEnd = document.getElementById('ttClassEnd');
    const ttProgressContainer = document.getElementById('ttProgressContainer');
    const ttProgressFill = document.getElementById('ttProgressFill');
    const ttProgressLabel = document.getElementById('ttProgressLabel');
    const ttProgressStats = document.getElementById('ttProgressStats');
    const ttProgressDetail = document.getElementById('ttProgressDetail');
    const ttLogDiv = document.getElementById('ttLog');
    const ttClearLogBtn = document.getElementById('ttClearLogBtn');
    const ttRangeSummary = document.getElementById('ttRangeSummary');
    const ttNavBtn = document.getElementById('ttNavBtn');

    let ttRunning = false;

    function ttLog(message, type = 'info') {
        if (!ttLogDiv) return;
        const p = document.createElement('div');
        p.className = 'log-entry';
        if (type === 'success') p.classList.add('success');
        else if (type === 'error') p.classList.add('error');
        else if (type === 'warning') p.classList.add('warning');
        const timestamp = new Date().toLocaleTimeString();
        p.textContent = `[${timestamp}] ${message}`;
        ttLogDiv.appendChild(p);
        ttLogDiv.scrollTop = ttLogDiv.scrollHeight;
    }

    function updateTtStatus(text, state = 'idle') {
        if (!ttStatus) return;
        ttStatus.textContent = text;
        ttStatusIndicator.classList.remove('active', 'error');
        if (state === 'active') {
            ttStatusIndicator.classList.add('active');
            ttRunning = true;
        } else if (state === 'error') {
            ttStatusIndicator.classList.add('error');
            ttRunning = false;
        } else {
            ttRunning = false;
        }
        if (ttStartBtn) ttStartBtn.disabled = ttRunning;
        if (ttStopBtn) ttStopBtn.disabled = !ttRunning;
    }

    function updateTtRangeSummary() {
        if (!ttRangeSummary) return;
        const gs = parseInt(ttGradeStart.value);
        const ge = parseInt(ttGradeEnd.value);
        const cs = parseInt(ttClassStart.value);
        const ce = parseInt(ttClassEnd.value);
        if (gs > ge) ttGradeEnd.value = String(gs);
        if (cs > ce) ttClassEnd.value = String(cs);
        const actualGe = parseInt(ttGradeEnd.value);
        const actualCe = parseInt(ttClassEnd.value);
        const gradeText = gs === actualGe ? `${gs}학년` : `${gs}~${actualGe}학년`;
        const classText = cs === actualCe ? `${cs}반` : `${cs}~${actualCe}반`;
        ttRangeSummary.textContent = `${gradeText}, ${classText}`;
    }

    if (ttGradeStart) {
        [ttGradeStart, ttGradeEnd, ttClassStart, ttClassEnd].forEach(el => {
            el.addEventListener('change', updateTtRangeSummary);
        });
        updateTtRangeSummary();
    }

    // 페이지 이동 버튼
    if (ttNavBtn) {
        ttNavBtn.addEventListener('click', async () => {
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) { ttLog('활성 탭을 찾을 수 없습니다.', 'error'); return; }

                ttNavBtn.disabled = true;
                ttLog('학생별시간표조회 페이지로 이동 중...');

                await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    files: ['neis-navigator.js']
                });

                const results = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: async () => {
                        try {
                            await NEISNavigator.clickTopTab("부서장(나이스부)");
                            await NEISNavigator.clickDropdownItem("시간표관리");
                            await NEISNavigator.clickSidebarItem("학생별시간표조회");
                            return null;
                        } catch (e) {
                            return '학생별시간표조회 페이지로 이동할 수 없습니다: ' + e.message;
                        }
                    }
                });

                const error = results?.[0]?.result;
                if (error) {
                    ttLog(error, 'error');
                } else {
                    ttLog('페이지 이동 완료', 'success');
                }
            } catch (e) {
                ttLog('페이지 이동 오류: ' + e.message, 'error');
            } finally {
                ttNavBtn.disabled = false;
            }
        });
    }

    // 시작 버튼
    if (ttStartBtn) {
        ttStartBtn.addEventListener('click', async () => {
            ttLog('학생별 시간표 추출을 시작합니다...');
            updateTtStatus('실행 중...', 'active');
            if (ttProgressContainer) ttProgressContainer.classList.add('visible');

            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) {
                    ttLog('활성 탭을 찾을 수 없습니다.', 'error');
                    updateTtStatus('오류', 'error');
                    return;
                }

                await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    files: ['neis-navigator.js', 'timetable-content.js']
                });

                const config = {
                    gradeStart: parseInt(ttGradeStart.value),
                    gradeEnd: parseInt(ttGradeEnd.value),
                    classStart: parseInt(ttClassStart.value),
                    classEnd: parseInt(ttClassEnd.value)
                };

                chrome.tabs.sendMessage(tab.id, {
                    action: "timetable_start",
                    config: config
                }, (response) => {
                    if (chrome.runtime.lastError) {
                        ttLog('메시지 전송 실패: ' + chrome.runtime.lastError.message, 'error');
                        updateTtStatus('오류', 'error');
                        if (ttProgressContainer) ttProgressContainer.classList.remove('visible');
                    } else {
                        ttLog(`범위: ${config.gradeStart}~${config.gradeEnd}학년 ${config.classStart}~${config.classEnd}반`, 'success');
                    }
                });
            } catch (e) {
                ttLog('오류: ' + e.message, 'error');
                updateTtStatus('오류', 'error');
                if (ttProgressContainer) ttProgressContainer.classList.remove('visible');
            }
        });
    }

    // 중지 버튼
    if (ttStopBtn) {
        ttStopBtn.addEventListener('click', async () => {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                chrome.tabs.sendMessage(tab.id, { action: "timetable_stop" });
            }
            updateTtStatus('중지됨', 'error');
            if (ttProgressContainer) ttProgressContainer.classList.remove('visible');
            ttLog('중지되었습니다.', 'warning');
        });
    }

    // 로그 클리어
    if (ttClearLogBtn) {
        ttClearLogBtn.addEventListener('click', () => {
            if (ttLogDiv) ttLogDiv.innerHTML = '';
            ttLog('로그가 초기화되었습니다.');
        });
    }

    // ========================================
    // 시간표 CSV 변환 (전처리)
    // ========================================
    const ttFileInput = document.getElementById('ttFileInput');
    const ttSelectFilesBtn = document.getElementById('ttSelectFilesBtn');
    const ttSelectedFiles = document.getElementById('ttSelectedFiles');
    const ttPreprocessBtn = document.getElementById('ttPreprocessBtn');
    const ttPreprocessResult = document.getElementById('ttPreprocessResult');

    let ttFiles = [];

    if (ttSelectFilesBtn) {
        ttSelectFilesBtn.addEventListener('click', () => ttFileInput?.click());
    }

    if (ttFileInput) {
        ttFileInput.addEventListener('change', (e) => {
            ttFiles = Array.from(e.target.files);
            if (ttSelectedFiles) {
                ttSelectedFiles.innerHTML = ttFiles.map(f =>
                    `<div style="font-size:11px;padding:4px 0;color:var(--text-secondary);">📄 ${f.name}</div>`
                ).join('');
            }
            if (ttPreprocessBtn) {
                ttPreprocessBtn.style.display = ttFiles.length > 0 ? 'flex' : 'none';
            }
            if (ttPreprocessResult) ttPreprocessResult.innerHTML = '';
        });
    }

    if (ttPreprocessBtn) {
        ttPreprocessBtn.addEventListener('click', async () => {
            if (ttFiles.length === 0) return;

            ttPreprocessBtn.disabled = true;
            ttPreprocessBtn.innerHTML = '변환 중...';
            if (ttPreprocessResult) ttPreprocessResult.innerHTML = '';

            try {
                const processedArray = [];
                let totalRecords = 0;
                let totalStudents = 0;

                for (const file of ttFiles) {
                    const buf = await file.arrayBuffer();
                    const result = TimetablePreprocessor.preprocess(new Uint8Array(buf), file.name);
                    processedArray.push(result);
                    totalRecords += result.stats.recordCount;
                    totalStudents += result.stats.studentCount;
                }

                const merged = TimetablePreprocessor.mergeResults(processedArray);
                const csv = TimetablePreprocessor.toCSV(merged);

                // CSV 다운로드
                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `timetable_${new Date().toISOString().slice(0, 10)}.csv`;
                a.click();
                URL.revokeObjectURL(url);

                // Excel도 다운로드
                const xlsxBlob = TimetablePreprocessor.toExcel(merged);
                const xlsxUrl = URL.createObjectURL(xlsxBlob);
                const a2 = document.createElement('a');
                a2.href = xlsxUrl;
                a2.download = `timetable_${new Date().toISOString().slice(0, 10)}.xlsx`;
                a2.click();
                URL.revokeObjectURL(xlsxUrl);

                // 결과 표시
                const subjects = new Set(merged.map(r => r.과목));
                if (ttPreprocessResult) {
                    ttPreprocessResult.innerHTML = `
                        <div style="background:var(--success-light);color:#065f46;padding:var(--space-md);border-radius:var(--radius-md);margin-top:var(--space-sm);font-size:12px;">
                            <strong>변환 완료!</strong><br>
                            파일: ${ttFiles.length}개 | 학생: ${totalStudents}명 | 레코드: ${merged.length}건<br>
                            과목: ${subjects.size}개 (${Array.from(subjects).slice(0, 5).join(', ')}${subjects.size > 5 ? '...' : ''})<br>
                            CSV, XLSX 파일이 다운로드되었습니다.
                        </div>`;
                }

                ttLog(`CSV 변환 완료: ${ttFiles.length}개 파일 → ${merged.length}레코드`, 'success');
            } catch (e) {
                if (ttPreprocessResult) {
                    ttPreprocessResult.innerHTML = `
                        <div style="background:var(--danger-light);color:#991b1b;padding:var(--space-md);border-radius:var(--radius-md);margin-top:var(--space-sm);font-size:12px;">
                            <strong>오류:</strong> ${e.message}
                        </div>`;
                }
                ttLog('CSV 변환 오류: ' + e.message, 'error');
            } finally {
                ttPreprocessBtn.disabled = false;
                ttPreprocessBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg> CSV 변환 실행`;
            }
        });
    }

    // ========================================
    // 동아리 활동 관리
    // ========================================
    const clubStartBtn = document.getElementById('clubStartBtn');
    const clubStopBtn = document.getElementById('clubStopBtn');
    const clubStatus = document.getElementById('clubStatus');
    const clubStatusIndicator = document.getElementById('clubStatusIndicator');
    const clubProgressContainer = document.getElementById('clubProgressContainer');
    const clubProgressFill = document.getElementById('clubProgressFill');
    const clubProgressLabel = document.getElementById('clubProgressLabel');
    const clubProgressStats = document.getElementById('clubProgressStats');
    const clubProgressDetail = document.getElementById('clubProgressDetail');
    const clubLogDiv = document.getElementById('clubLog');
    const clubClearLogBtn = document.getElementById('clubClearLogBtn');
    const clubNavBtn = document.getElementById('clubNavBtn');

    let clubRunning = false;
    let clubCurrentTask = 'credit_standard';

    // 동아리 날짜 초기값 (이번 달 첫날 ~ 마지막날)
    {
        const now = new Date();
        const firstDay = formatDateForInput(new Date(now.getFullYear(), now.getMonth(), 1));
        const lastDay = formatDateForInput(new Date(now.getFullYear(), now.getMonth() + 1, 0));
        const clubDateIds = [
            ['clubAttStartDate', 'clubAttEndDate'],
            ['clubCumStartDate', 'clubCumEndDate'],
            ['clubVolStartDate', 'clubVolEndDate']
        ];
        for (const [startId, endId] of clubDateIds) {
            const s = document.getElementById(startId);
            const e = document.getElementById(endId);
            if (s && !s.value) s.value = firstDay;
            if (e && !e.value) e.value = lastDay;
        }
        const creditDate = document.getElementById('clubCreditDate');
        if (creditDate && !creditDate.value) creditDate.value = lastDay;
    }

    // 탭 전환
    document.querySelectorAll('.club-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.club-tab').forEach(t => {
                t.classList.remove('active');
                t.setAttribute('aria-selected', 'false');
            });
            tab.classList.add('active');
            tab.setAttribute('aria-selected', 'true');

            clubCurrentTask = tab.dataset.clubTask;

            document.querySelectorAll('.club-task-config').forEach(c => c.classList.remove('active'));
            const config = document.querySelector(`[data-club-config="${clubCurrentTask}"]`);
            if (config) config.classList.add('active');
        });
    });

    function clubLog_add(message, type = 'info') {
        if (!clubLogDiv) return;
        const p = document.createElement('div');
        p.className = 'log-entry';
        if (type === 'success' || message.includes('완료') || message.includes('성공')) {
            p.classList.add('success');
        } else if (type === 'error' || message.includes('오류') || message.includes('실패')) {
            p.classList.add('error');
        } else if (type === 'warning' || message.includes('경고')) {
            p.classList.add('warning');
        }
        const timestamp = new Date().toLocaleTimeString();
        p.textContent = `[${timestamp}] ${message}`;
        clubLogDiv.appendChild(p);
        clubLogDiv.scrollTop = clubLogDiv.scrollHeight;
    }

    function updateClubStatus(text, state = 'idle') {
        if (!clubStatus) return;
        clubStatus.textContent = text;
        clubStatusIndicator.classList.remove('active', 'error');
        if (state === 'active') {
            clubStatusIndicator.classList.add('active');
            clubRunning = true;
        } else if (state === 'error') {
            clubStatusIndicator.classList.add('error');
            clubRunning = false;
        } else {
            clubRunning = false;
        }
        if (clubStartBtn) clubStartBtn.disabled = clubRunning;
        if (clubStopBtn) clubStopBtn.disabled = !clubRunning;
    }

    // 현재 탭의 config 값 읽기
    function getClubConfig() {
        const task = clubCurrentTask;
        const config = { task };

        switch (task) {
            case 'credit_standard': {
                // 날짜는 NEIS 페이지에서 직접 설정
                break;
            }
            case 'attendance': {
                const s = document.getElementById('clubAttStartDate');
                const e = document.getElementById('clubAttEndDate');
                config.startDate = s?.value?.replace(/-/g, '.') || '';
                config.endDate = e?.value?.replace(/-/g, '.') || '';
                break;
            }
            case 'cumulative': {
                const s = document.getElementById('clubCumStartDate');
                const e = document.getElementById('clubCumEndDate');
                config.startDate = s?.value?.replace(/-/g, '.') || '';
                config.endDate = e?.value?.replace(/-/g, '.') || '';
                config.hours = parseInt(document.getElementById('clubCumHours')?.value) || 1;
                config.content = document.getElementById('clubCumContent')?.value || '';
                break;
            }
            case 'cumulative_volunteer': {
                const s = document.getElementById('clubVolStartDate');
                const e = document.getElementById('clubVolEndDate');
                config.startDate = s?.value?.replace(/-/g, '.') || '';
                config.endDate = e?.value?.replace(/-/g, '.') || '';
                config.hours = parseInt(document.getElementById('clubVolHours')?.value) || 1;
                config.content = document.getElementById('clubVolContent')?.value || '';
                break;
            }
            case 'credit_apply': {
                const d = document.getElementById('clubCreditDate');
                config.creditDate = d?.value?.replace(/-/g, '.') || '';
                break;
            }
        }

        return config;
    }

    // 가이드 표시 — executeScript로 직접 실행 (메시지 포트 문제 회피)
    const clubGuideBtn = document.getElementById('clubGuideBtn');
    if (clubGuideBtn) {
        clubGuideBtn.addEventListener('click', async () => {
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) { clubLog_add('활성 탭을 찾을 수 없습니다.', 'error'); return; }

                clubGuideBtn.disabled = true;
                const task = clubCurrentTask;

                const results = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: (task) => {
                        // 기존 가이드 제거
                        document.querySelectorAll('.nh-guide-badge').forEach(el => el.remove());
                        document.querySelectorAll('[data-nh-guide]').forEach(el => {
                            el.style.removeProperty('outline');
                            el.style.removeProperty('outline-offset');
                            el.removeAttribute('data-nh-guide');
                        });

                        // 이미 표시 중이었으면 제거만 하고 끝
                        if (window._nhGuideActive) {
                            window._nhGuideActive = false;
                            return -1; // 토글 off
                        }

                        const guideSteps = {
                            credit_standard: [
                                { ariaLabel: '부서명', label: '부서명 (자동)' },
                                { ariaLabel: '기간시작일자', label: '시작일 설정' },
                                { ariaLabel: '기간종료일자', label: '종료일 설정' },
                                { buttonText: '조회', label: '조회 (자동)' },
                                { gradeCheckbox: '1학년', label: '1학년 체크 (자동)' },
                                { gradeCheckbox: '2학년', label: '2학년 체크 (자동)' },
                                { gradeCheckbox: '3학년', label: '3학년 체크 (자동)' },
                                { buttonText: '저장', label: '저장 (자동)' }
                            ],
                            attendance: [
                                { ariaLabel: '부서명', label: '부서명 (자동)' },
                                { ariaLabel: '일자', label: '일자 (자동)' },
                                { buttonText: '조회', label: '조회 (자동)' },
                                { buttonText: '마감', label: '마감 (자동)' }
                            ],
                            cumulative: [
                                { ariaLabel: '부서명', label: '부서명 (자동)' },
                                { buttonText: '조회', label: '조회 (자동)' },
                                { ariaLabel: '활동일', label: '활동일자 (자동)' },
                                { buttonText: '저장', label: '저장 (자동)' }
                            ],
                            cumulative_volunteer: [
                                { ariaLabel: '부서명', label: '부서명 (자동)' },
                                { buttonText: '조회', label: '조회 (자동)' },
                                { buttonText: '일괄등록', label: '일괄등록 (자동)' },
                                { buttonText: '저장', label: '저장 (자동)' }
                            ],
                            credit_apply: [
                                { ariaLabel: '기준일', label: '기준일 직접입력 (자동)' },
                                { buttonText: '이수시간반영', label: '이수시간반영 (자동)' },
                                { buttonText: '저장', label: '저장 (자동)' }
                            ]
                        };

                        const steps = guideSteps[task] || guideSteps.credit_standard;
                        const nums = ['\u2776','\u2777','\u2778','\u2779','\u277a','\u277b','\u277c','\u277d','\u277e','\u277f'];
                        let count = 0;

                        function renderBadges() {
                            // 배지만 다시 그리기 (스크롤/리사이즈 대응)
                            document.querySelectorAll('.nh-guide-badge').forEach(el => el.remove());

                            for (let i = 0; i < steps.length; i++) {
                                const step = steps[i];
                                let el = null;

                                if (step.ariaLabel) {
                                    el = document.querySelector(`[aria-label*="${step.ariaLabel}"]`);
                                    if (el) {
                                        const container = el.closest('.cl-dateinput') || el.closest('.cl-combobox') || el.parentElement;
                                        if (container && container !== document.body) el = container;
                                    }
                                }
                                if (!el && step.buttonText) {
                                    const btns = document.querySelectorAll('[role="button"]');
                                    el = Array.from(btns).find(b => b.textContent?.trim() === step.buttonText && (b.offsetWidth || b.offsetHeight));
                                }
                                if (!el && step.gradeCheckbox) {
                                    // columnheader에서 "1학년" 등을 찾고, x좌표 기준으로 아래 체크박스 매칭
                                    const grids = document.querySelectorAll('[role="grid"]');
                                    for (const grid of grids) {
                                        if (!(grid.offsetWidth || grid.offsetHeight)) continue;
                                        const headers = grid.querySelectorAll('[role="columnheader"]');
                                        let targetHeader = null;
                                        for (const h of headers) {
                                            if (h.textContent?.trim().includes(step.gradeCheckbox)) {
                                                targetHeader = h; break;
                                            }
                                        }
                                        if (!targetHeader) continue;
                                        const hRect = targetHeader.getBoundingClientRect();
                                        const hCenterX = hRect.left + hRect.width / 2;
                                        // 그리드 내 모든 체크박스를 찾아 x좌표가 가장 가까운 것 선택
                                        const cbs = grid.querySelectorAll('input[type="checkbox"], [role="checkbox"]');
                                        let bestCb = null, bestDist = Infinity;
                                        for (const cb of cbs) {
                                            if (!(cb.offsetWidth || cb.offsetHeight)) continue;
                                            const cRect = cb.getBoundingClientRect();
                                            const dist = Math.abs((cRect.left + cRect.width / 2) - hCenterX);
                                            if (dist < bestDist) { bestDist = dist; bestCb = cb; }
                                        }
                                        if (bestCb) { el = bestCb.closest('[role="gridcell"]') || bestCb; break; }
                                    }
                                }
                                if (!el || !(el.offsetWidth || el.offsetHeight)) continue;

                                const isManual = !step.label.includes('자동');

                                // outline 스타일
                                el.setAttribute('data-nh-guide', '');
                                el.style.outline = isManual ? '2.5px solid #ef4444' : '2.5px solid #6366f1';
                                el.style.outlineOffset = '2px';

                                // 배지
                                const rect = el.getBoundingClientRect();
                                const badge = document.createElement('span');
                                badge.className = 'nh-guide-badge';
                                badge.textContent = `${nums[i] || (i+1)} ${step.label}`;
                                const color = isManual ? '#ef4444' : '#6366f1';
                                badge.style.cssText = `
                                    position: fixed; z-index: 99999;
                                    top: ${rect.top - 16}px;
                                    left: ${rect.left}px;
                                    background: ${color};
                                    color: #fff; padding: 1px 8px; border-radius: 10px;
                                    font-size: 11px; font-weight: 600; white-space: nowrap;
                                    pointer-events: none; font-family: -apple-system, sans-serif;
                                    line-height: 18px;
                                `;
                                document.body.appendChild(badge);
                                count++;
                            }
                        }

                        renderBadges();
                        window._nhGuideActive = true;

                        // 스크롤/리사이즈 시 배지 위치 갱신
                        function onLayoutChange() {
                            if (!window._nhGuideActive) {
                                window.removeEventListener('scroll', onLayoutChange, true);
                                window.removeEventListener('resize', onLayoutChange);
                                return;
                            }
                            renderBadges();
                        }
                        window.addEventListener('scroll', onLayoutChange, true);
                        window.addEventListener('resize', onLayoutChange);

                        return count;
                    },
                    args: [task]
                });

                const count = results?.[0]?.result || 0;
                if (count === -1) {
                    clubLog_add('가이드 해제', 'info');
                    clubGuideBtn.textContent = 'NEIS 페이지에 가이드 표시';
                } else if (count > 0) {
                    clubLog_add(`가이드 ${count}개 표시 (빨강=수동, 보라=자동)`, 'success');
                    clubGuideBtn.textContent = '가이드 해제';
                } else {
                    clubLog_add('표시할 요소를 찾지 못했습니다. 해당 페이지인지 확인하세요.', 'warning');
                }
            } catch (e) {
                clubLog_add('가이드 오류: ' + e.message, 'error');
            } finally {
                clubGuideBtn.disabled = false;
            }
        });
    }

    // 이수시간기준 전용 페이지 이동 버튼
    const clubCsNavBtn = document.getElementById('clubCsNavBtn');
    if (clubCsNavBtn) {
        clubCsNavBtn.addEventListener('click', () => clubNavBtn?.click());
    }

    // 이수시간기준 전용 시작/중지 버튼
    const clubCsStartBtn = document.getElementById('clubCsStartBtn');
    const clubCsStopBtn = document.getElementById('clubCsStopBtn');
    if (clubCsStartBtn) {
        clubCsStartBtn.addEventListener('click', () => clubStartBtn?.click());
    }
    if (clubCsStopBtn) {
        clubCsStopBtn.addEventListener('click', () => clubStopBtn?.click());
    }

    // 상태 변경 시 이수시간기준 버튼도 동기화
    const origUpdateClubStatus = updateClubStatus;
    updateClubStatus = function(text, state) {
        origUpdateClubStatus(text, state);
        if (clubCsStartBtn) clubCsStartBtn.disabled = clubRunning;
        if (clubCsStopBtn) clubCsStopBtn.disabled = !clubRunning;
    };

    // 공통 페이지 이동 버튼
    if (clubNavBtn) {
        clubNavBtn.addEventListener('click', async () => {
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) { clubLog_add('활성 탭을 찾을 수 없습니다.', 'error'); return; }

                clubNavBtn.disabled = true;
                clubLog_add('동아리활동관리 페이지로 이동 중...');

                await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    files: ['neis-navigator.js']
                });

                const results = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: async () => {
                        try {
                            await NEISNavigator.clickTopTab('동아리담임');
                            await NEISNavigator.delay(1000);
                            await NEISNavigator.clickSidebarItem('동아리활동관리');
                            return null;
                        } catch (e) {
                            return '동아리활동관리 페이지로 이동할 수 없습니다: ' + e.message;
                        }
                    }
                });

                const error = results?.[0]?.result;
                if (error) {
                    clubLog_add(error, 'error');
                } else {
                    clubLog_add('페이지 이동 완료', 'success');
                }
            } catch (e) {
                clubLog_add('페이지 이동 오류: ' + e.message, 'error');
            } finally {
                clubNavBtn.disabled = false;
            }
        });
    }

    // 시작 버튼
    if (clubStartBtn) {
        clubStartBtn.addEventListener('click', async () => {
            const config = getClubConfig();

            // 입력 유효성 검사
            if (config.task === 'credit_apply' && !config.creditDate) {
                clubLog_add('이수시간 기준일을 설정하세요.', 'warning');
                return;
            }
            if ((config.task === 'cumulative' || config.task === 'cumulative_volunteer') && !config.content) {
                clubLog_add('활동내용을 입력하세요.', 'warning');
                return;
            }

            const taskNames = {
                credit_standard: '이수시간기준등록',
                attendance: '출결관리',
                cumulative: '누가기록',
                cumulative_volunteer: '누가기록(봉사활동)',
                credit_apply: '이수시간반영'
            };
            clubLog_add(`[${taskNames[config.task]}] 시작합니다...`);
            updateClubStatus('실행 중...', 'active');
            if (clubProgressContainer) clubProgressContainer.classList.add('visible');

            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) {
                    clubLog_add('활성 탭을 찾을 수 없습니다.', 'error');
                    updateClubStatus('오류', 'error');
                    return;
                }

                // 스크립트 주입
                await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    files: ['neis-navigator.js', 'club-content.js']
                });

                // 메시지 전송
                chrome.tabs.sendMessage(tab.id, {
                    action: "club_start",
                    config: config
                }, (response) => {
                    if (chrome.runtime.lastError) {
                        clubLog_add('메시지 전송 실패: ' + chrome.runtime.lastError.message, 'error');
                        updateClubStatus('오류', 'error');
                        if (clubProgressContainer) clubProgressContainer.classList.remove('visible');
                    } else {
                        clubLog_add(`설정: ${JSON.stringify(config)}`, 'success');
                    }
                });
            } catch (e) {
                clubLog_add('오류: ' + e.message, 'error');
                updateClubStatus('오류', 'error');
                if (clubProgressContainer) clubProgressContainer.classList.remove('visible');
            }
        });
    }

    // 중지 버튼
    if (clubStopBtn) {
        clubStopBtn.addEventListener('click', async () => {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                chrome.tabs.sendMessage(tab.id, { action: "club_stop" });
            }
            updateClubStatus('중지됨', 'error');
            if (clubProgressContainer) clubProgressContainer.classList.remove('visible');
            clubLog_add('중지되었습니다.', 'warning');
        });
    }

    // 로그 클리어
    if (clubClearLogBtn) {
        clubClearLogBtn.addEventListener('click', () => {
            if (clubLogDiv) clubLogDiv.innerHTML = '';
            clubLog_add('로그가 초기화되었습니다.');
        });
    }

    // ========================================
    // 키보드 단축키 지원
    // ========================================
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + Enter: 시작
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !startBtn.disabled) {
            e.preventDefault();
            startBtn.click();
        }
        // Escape: 중지
        if (e.key === 'Escape' && !stopBtn.disabled) {
            e.preventDefault();
            stopBtn.click();
        }
        // Ctrl/Cmd + A (섹션 영역에서): 전체 선택
        if ((e.ctrlKey || e.metaKey) && e.key === 'a' && document.activeElement.closest('#sections')) {
            e.preventDefault();
            selectAllBtn.click();
        }
    });
});
