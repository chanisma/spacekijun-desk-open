// 동아리 활동 관리 자동화 content script
window._clubActivity = (() => {
    let isRunning = false;
    const report = { processed: [], errors: [] };

    function sendLog(msg, type = 'info') {
        chrome.runtime.sendMessage({ action: "club_log", message: msg, type });
        console.log("[Club]", msg);
    }

    function sendProgress(current, total, detail) {
        chrome.runtime.sendMessage({ action: "club_progress", current, total, detail });
    }

    // ========================================
    // 헬퍼 함수
    // ========================================

    // 콤보박스에서 모든 옵션 텍스트 읽기
    async function getComboboxOptions(ariaLabel) {
        const combo = NEISNavigator.findCombobox(ariaLabel);
        if (!combo) {
            sendLog(`콤보박스 "${ariaLabel}" 찾을 수 없음`, 'error');
            return [];
        }

        await NEISNavigator.openCombobox(combo);
        await NEISNavigator.delay(800);

        const options = Array.from(document.querySelectorAll('[role="option"]'))
            .filter(o => NEISNavigator.isVisible(o))
            .map(o => o.textContent?.trim())
            .filter(t => t && t.length > 0);

        await NEISNavigator.closeCombobox(combo);
        await NEISNavigator.delay(300);

        return options;
    }

    // 페이지 내 탭/링크 클릭 (출석관리, 누가기록 등)
    async function clickPageTab(tabText) {
        // 1) [role="tab"] 시도
        const tabs = document.querySelectorAll('[role="tab"]');
        for (const tab of tabs) {
            if (tab.textContent?.trim() === tabText && NEISNavigator.isVisible(tab)) {
                tab.click();
                await NEISNavigator.waitForLoading();
                await NEISNavigator.delay(1000);
                sendLog(`탭 "${tabText}" 클릭`, 'success');
                return true;
            }
        }

        // 2) 일반 텍스트 요소 클릭 (span, a, div 등)
        const allEls = document.querySelectorAll('a, span, div, [role="button"], [role="link"]');
        for (const el of allEls) {
            if (el.textContent?.trim() === tabText && NEISNavigator.isVisible(el)) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    el.click();
                    await NEISNavigator.waitForLoading();
                    await NEISNavigator.delay(1000);
                    sendLog(`요소 "${tabText}" 클릭`, 'success');
                    return true;
                }
            }
        }

        sendLog(`페이지 탭 "${tabText}" 찾을 수 없음`, 'warning');
        return false;
    }

    // 사이드바에서 N번째 매칭 아이템 클릭 (동일 이름 대응)
    async function clickNthSidebarItem(itemText, n = 0) {
        const items = document.querySelectorAll('.cl-sidenavigation-item .cl-text');
        let count = 0;
        for (const item of items) {
            if (item.textContent?.trim().startsWith(itemText)) {
                if (count === n) {
                    const parent = item.closest('a') || item.parentElement;
                    parent.click();
                    await NEISNavigator.waitForLoading();
                    await NEISNavigator.delay(1000);
                    return true;
                }
                count++;
            }
        }
        return false;
    }

    // 체크박스 찾기 (input 또는 role="checkbox")
    function findCheckbox(container) {
        return container.querySelector('input[type="checkbox"]') ||
            container.querySelector('[role="checkbox"]');
    }

    // 체크박스 상태 설정
    async function setCheckbox(checkbox, checked) {
        if (!checkbox) return false;
        if (checkbox.tagName === 'INPUT') {
            if (checkbox.checked !== checked) {
                checkbox.click();
                await NEISNavigator.delay(300);
            }
        } else {
            const isChecked = checkbox.getAttribute('aria-checked') === 'true';
            if (isChecked !== checked) {
                checkbox.click();
                await NEISNavigator.delay(300);
            }
        }
        return true;
    }

    // ========================================
    // 가이드 오버레이 — NEIS 페이지에 번호 표시
    // ========================================
    function showGuideOverlay(steps) {
        // 기존 가이드 제거
        document.querySelectorAll('.neis-helper-guide').forEach(el => el.remove());

        let count = 0;
        for (const step of steps) {
            let el = null;

            // 요소 찾기
            if (step.ariaLabel) {
                el = document.querySelector(`[aria-label*="${step.ariaLabel}"]`);
                // dateinput 컨테이너면 상위로 올라가기
                if (el && el.closest('.cl-dateinput')) el = el.closest('.cl-dateinput');
            }
            if (!el && step.selector) {
                el = document.querySelector(step.selector);
            }
            if (!el && step.buttonText) {
                const btns = document.querySelectorAll('[role="button"]');
                el = Array.from(btns).find(b => b.textContent?.trim() === step.buttonText);
            }
            if (!el || !(el.offsetWidth || el.offsetHeight)) continue;

            // 오버레이 배지 생성
            const badge = document.createElement('div');
            badge.className = 'neis-helper-guide';
            badge.style.cssText = `
                position: absolute;
                z-index: 99999;
                pointer-events: none;
            `;

            // 번호 원
            const circle = document.createElement('div');
            circle.style.cssText = `
                width: 24px; height: 24px;
                background: #6366f1;
                color: white;
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                font-size: 13px; font-weight: 700;
                box-shadow: 0 2px 8px rgba(99,102,241,0.5);
                position: absolute;
                top: -12px; left: -12px;
            `;
            circle.textContent = step.num;

            // 하이라이트 테두리
            const highlight = document.createElement('div');
            highlight.className = 'neis-helper-guide';
            const rect = el.getBoundingClientRect();
            highlight.style.cssText = `
                position: fixed;
                z-index: 99998;
                pointer-events: none;
                top: ${rect.top - 3}px;
                left: ${rect.left - 3}px;
                width: ${rect.width + 6}px;
                height: ${rect.height + 6}px;
                border: 2.5px solid #6366f1;
                border-radius: 6px;
                box-shadow: 0 0 0 2px rgba(99,102,241,0.2);
            `;

            // 번호 원을 하이라이트 위에 배치
            circle.style.cssText = `
                position: fixed;
                z-index: 99999;
                pointer-events: none;
                top: ${rect.top - 14}px;
                left: ${rect.left - 14}px;
                width: 26px; height: 26px;
                background: #6366f1;
                color: white;
                border-radius: 50%;
                display: flex; align-items: center; justify-content: center;
                font-size: 13px; font-weight: 700;
                box-shadow: 0 2px 8px rgba(99,102,241,0.5);
                font-family: -apple-system, sans-serif;
            `;
            circle.className = 'neis-helper-guide';

            // 설명 라벨
            const label = document.createElement('div');
            label.className = 'neis-helper-guide';
            label.style.cssText = `
                position: fixed;
                z-index: 99999;
                pointer-events: none;
                top: ${rect.top - 14}px;
                left: ${rect.left + 18}px;
                background: #6366f1;
                color: white;
                padding: 3px 10px;
                border-radius: 12px;
                font-size: 11px; font-weight: 600;
                white-space: nowrap;
                box-shadow: 0 2px 8px rgba(99,102,241,0.4);
                font-family: -apple-system, sans-serif;
            `;
            label.textContent = step.label;

            document.body.appendChild(highlight);
            document.body.appendChild(circle);
            document.body.appendChild(label);
            count++;
        }

        // 5초 후 자동 제거
        setTimeout(() => {
            document.querySelectorAll('.neis-helper-guide').forEach(el => el.remove());
        }, 5000);

        return count;
    }

    // 모든 부서명 가져오기
    async function getAllDepartments() {
        const options = await getComboboxOptions('부서');
        if (options.length === 0) {
            // '부서명'으로도 시도
            return await getComboboxOptions('부서명');
        }
        return options;
    }

    // ========================================
    // 네비게이션 함수
    // ========================================

    // 동아리활동관리 기본 페이지 이동
    async function navigateToClubBase() {
        sendLog('동아리담임 탭으로 이동 중...');
        await NEISNavigator.clickTopTab('동아리담임');
        await NEISNavigator.delay(1500);
    }

    // 이수시간기준등록 페이지로 이동
    async function navigateToCreditStandard() {
        await navigateToClubBase();
        sendLog('이수시간기준등록 페이지로 이동 중...');

        // 사이드바에서 동아리활동관리 확장
        await NEISNavigator.clickSidebarItem('동아리활동관리');
        await NEISNavigator.delay(1000);

        // 이수시간기준등록 사이드바 아이템 클릭
        if (!await NEISNavigator.clickSidebarItem('이수시간기준���록')) {
            // 페이지 내 탭으로 시도
            if (!await clickPageTab('이수시간기준등록')) {
                sendLog('이수시간기준등록 페이지를 찾을 수 없습니다', 'error');
                return false;
            }
        }
        await NEISNavigator.delay(2000);
        sendLog('이수시간기준등록 페이지 도착', 'success');
        return true;
    }

    // 동아리활동관리 하위 탭 페이지로 이동 (출석관리, 누가기록, 학생부자료기록)
    async function navigateToClubSubPage(subTabName) {
        await navigateToClubBase();
        sendLog(`${subTabName} 페이지로 이동 중...`);

        // 사이드바에서 동아리활동관리 확장
        await NEISNavigator.clickSidebarItem('동아리활동관리');
        await NEISNavigator.delay(1000);

        // 하위 동아리활동관리 클릭 (두 번째 매칭 시도)
        await clickNthSidebarItem('동아리활동관리', 1);
        await NEISNavigator.delay(1500);

        // 페이지 내 탭 클릭
        if (!await clickPageTab(subTabName)) {
            sendLog(`${subTabName} 탭을 찾을 수 없습니다`, 'error');
            return false;
        }
        await NEISNavigator.delay(2000);
        sendLog(`${subTabName} 페이지 도착`, 'success');
        return true;
    }

    // ========================================
    // Task 1: ��수시간기준등록
    // ========================================
    async function runCreditStandard(config) {
        sendLog('=== ���수시간기준등록 시작 ===');

        if (!await navigateToCreditStandard()) return;

        const departments = await getAllDepartments();
        if (departments.length === 0) {
            sendLog('부서 목록을 가져올 수 없습���다', 'error');
            report.errors.push({ task: 'credit_standard', error: '부서 목록 없음' });
            return;
        }
        sendLog(`부서 ${departments.length}개 발견: ${departments.join(', ')}`);

        for (let i = 0; i < departments.length; i++) {
            if (!isRunning) break;
            const dept = departments[i];
            sendLog(`[${i + 1}/${departments.length}] ${dept} 처리 중...`);

            // 부서명 선택
            const selected = await NEISNavigator.selectComboboxOption('부서', dept) ||
                await NEISNavigator.selectComboboxOption('부서명', dept);
            if (!selected) {
                sendLog(`  부서 "${dept}" 선택 실패`, 'error');
                report.errors.push({ task: 'credit_standard', dept, error: '부서 선택 실패' });
                continue;
            }
            await NEISNavigator.delay(500);

            // 기간은 사용자가 NEIS 페이지에서 직접 설정 (가이드 참고)

            // 조회 클릭 (정확 매칭 실패 시 포함 매칭 fallback)
            let queried = await NEISNavigator.clickButtonByText('조회');
            if (!queried) {
                const btns = document.querySelectorAll('[role="button"]');
                const btn = Array.from(btns).find(b =>
                    b.textContent?.trim().includes('조회') && NEISNavigator.isVisible(b)
                );
                if (btn) {
                    btn.click();
                    await NEISNavigator.waitForLoading();
                    queried = true;
                }
            }
            if (!queried) sendLog(`  조회 버튼을 찾을 수 없습니다`, 'warning');
            await NEISNavigator.delay(2000);

            // 학년 체크박스 클릭 — columnheader 위치 기준으로 아래 체크박스 매칭
            const grids = document.querySelectorAll('[role="grid"]');
            let checkedCount = 0;
            const gradeNames = ['1학년', '2학년', '3학년'];
            for (const grid of grids) {
                if (!(grid.offsetWidth || grid.offsetHeight)) continue;
                const headers = grid.querySelectorAll('[role="columnheader"]');

                for (const gradeName of gradeNames) {
                    let targetHeader = null;
                    for (const h of headers) {
                        if (h.textContent?.trim().includes(gradeName)) {
                            targetHeader = h; break;
                        }
                    }
                    if (!targetHeader) continue;

                    const hRect = targetHeader.getBoundingClientRect();
                    const hCenterX = hRect.left + hRect.width / 2;

                    // 그리드 내 모든 체크박스 중 x좌표가 가장 가까운 것
                    const cbs = grid.querySelectorAll('input[type="checkbox"], [role="checkbox"]');
                    let bestCb = null, bestDist = Infinity;
                    for (const cb of cbs) {
                        if (!(cb.offsetWidth || cb.offsetHeight)) continue;
                        const cRect = cb.getBoundingClientRect();
                        const dist = Math.abs((cRect.left + cRect.width / 2) - hCenterX);
                        if (dist < bestDist) { bestDist = dist; bestCb = cb; }
                    }
                    if (bestCb) {
                        await setCheckbox(bestCb, true);
                        checkedCount++;
                        sendLog(`    ${targetHeader.textContent?.trim()} 체크`);
                    }
                }
                if (checkedCount > 0) break;
            }

            sendLog(`  체크박스 ${checkedCount}개 선택됨`);

            // 저장
            const saved = await NEISNavigator.clickButtonByText('저장');
            if (saved) {
                sendLog(`  ${dept} 저장 완료`, 'success');
                report.processed.push({ task: 'credit_standard', dept });
            } else {
                sendLog(`  ${dept} 저장 실패`, 'error');
                report.errors.push({ task: 'credit_standard', dept, error: '저장 실패' });
            }
            await NEISNavigator.delay(1000);

            sendProgress(i + 1, departments.length, dept);
        }

        sendLog('=== 이수시간기준등록 완료 ===', 'success');
    }

    // ========================================
    // Task 2: 출결 관리 (출석관리 → 마감)
    // ========================================
    async function runAttendance(config) {
        sendLog('=== 출결 관리 시작 ===');

        if (!await navigateToClubSubPage('출석관���')) return;

        const departments = await getAllDepartments();
        if (departments.length === 0) {
            sendLog('부서 목록을 가져올 수 없습니다', 'error');
            report.errors.push({ task: 'attendance', error: '부서 목록 없음' });
            return;
        }
        sendLog(`부서 ${departments.length}개 발견`);

        let totalProcessed = 0;

        for (let di = 0; di < departments.length; di++) {
            if (!isRunning) break;
            const dept = departments[di];
            sendLog(`[부서 ${di + 1}/${departments.length}] ${dept}`);

            // 부서명 선택
            const selected = await NEISNavigator.selectComboboxOption('부서', dept) ||
                await NEISNavigator.selectComboboxOption('부서��', dept);
            if (!selected) {
                sendLog(`  부서 "${dept}" 선택 실패`, 'error');
                report.errors.push({ task: 'attendance', dept, error: '부서 선택 실패' });
                continue;
            }
            await NEISNavigator.delay(500);

            // 일자 콤보박스에서 사용 가능한 날짜 목록 가져오기
            let dates = [];
            const dateCombo = NEISNavigator.findCombobox('일자') || NEISNavigator.findCombobox('활동일');
            if (dateCombo) {
                await NEISNavigator.openCombobox(dateCombo);
                await NEISNavigator.delay(800);

                const opts = Array.from(document.querySelectorAll('[role="option"]'))
                    .filter(o => NEISNavigator.isVisible(o));

                for (const opt of opts) {
                    const text = opt.textContent?.trim() || '';
                    const match = text.match(/(\d{4}\.\d{2}\.\d{2})/);
                    if (match) {
                        const dateStr = match[1];
                        // config 기간 범위 내 필터링
                        if ((!config.startDate || dateStr >= config.startDate) &&
                            (!config.endDate || dateStr <= config.endDate)) {
                            dates.push(dateStr);
                        }
                    }
                }
                await NEISNavigator.closeCombobox(dateCombo);
                await NEISNavigator.delay(300);
            }

            // 콤보박스에서 날짜 못 찾으면 +/- 버튼으로 순회
            if (dates.length === 0 && config.startDate) {
                sendLog(`  날짜 콤보박스 없음, +/- 버튼 방식으로 전환`);
                // 시작일로 이동 시도
                const scrolled = await NEISNavigator.selectDateByScroll(config.startDate);
                if (!scrolled) {
                    sendLog(`  시작일(${config.startDate}) 선택 실패, 현재 날짜부터 시작`, 'warning');
                }

                // 현재 날짜부터 종료일까지 순회
                let guard = 0;
                while (isRunning && guard < 200) {
                    guard++;
                    const currentDate = NEISNavigator.getCurrentDate();
                    if (!currentDate) break;
                    if (config.endDate && currentDate > config.endDate) break;
                    if (config.startDate && currentDate < config.startDate) {
                        await NEISNavigator.clickNextDate();
                        continue;
                    }

                    sendLog(`  일자: ${currentDate}`);

                    // 조회
                    await NEISNavigator.clickButtonByText('조회');
                    await NEISNavigator.delay(2000);

                    // 마감 버튼 클릭
                    const closed = await NEISNavigator.clickButtonByText('마감');
                    if (closed) {
                        sendLog(`    마감 완료`, 'success');
                        report.processed.push({ task: 'attendance', dept, date: currentDate });
                        totalProcessed++;
                    } else {
                        sendLog(`    마감 버튼 없음 (이미 마감됨?)`, 'warning');
                    }

                    sendProgress(totalProcessed, 0, `${dept} - ${currentDate}`);

                    const before = currentDate;
                    const moved = await NEISNavigator.clickNextDate();
                    if (!moved) break;
                    const after = NEISNavigator.getCurrentDate();
                    if (after === before) break;
                }
                continue;
            }

            sendLog(`  날짜 ${dates.length}개 발견`);

            for (let dateIdx = 0; dateIdx < dates.length; dateIdx++) {
                if (!isRunning) break;
                const date = dates[dateIdx];
                sendLog(`  [${dateIdx + 1}/${dates.length}] 일자: ${date}`);

                // 일자 선택
                await NEISNavigator.selectComboboxOption('일자', date) ||
                    await NEISNavigator.selectDateByScroll(date);
                await NEISNavigator.delay(500);

                // 조회
                await NEISNavigator.clickButtonByText('조회');
                await NEISNavigator.delay(2000);

                // 마감
                const closed = await NEISNavigator.clickButtonByText('마감');
                if (closed) {
                    sendLog(`    마감 완료`, 'success');
                    report.processed.push({ task: 'attendance', dept, date });
                    totalProcessed++;
                } else {
                    sendLog(`    마감 버튼 없음 (이미 마감됨?)`, 'warning');
                }

                sendProgress(totalProcessed, 0, `${dept} - ${date}`);
                await NEISNavigator.delay(500);
            }
        }

        sendLog(`=== 출결 관리 완료 (${totalProcessed}건 처리) ===`, 'success');
    }

    // ========================================
    // Task 3: 누���기록
    // ========================================
    async function runCumulative(config) {
        sendLog('=== 누가기록 시작 ===');

        if (!await navigateToClubSubPage('누가기록')) return;

        const departments = await getAllDepartments();
        if (departments.length === 0) {
            sendLog('부서 목록을 가져올 수 없습니다', 'error');
            report.errors.push({ task: 'cumulative', error: '부서 목록 없음' });
            return;
        }
        sendLog(`부서 ${departments.length}개, 활동내용: "${config.content}", 이수시간: ${config.hours}`);

        let totalProcessed = 0;

        for (let di = 0; di < departments.length; di++) {
            if (!isRunning) break;
            const dept = departments[di];
            sendLog(`[부서 ${di + 1}/${departments.length}] ${dept}`);

            // 부서명 선택
            const selected = await NEISNavigator.selectComboboxOption('부서', dept) ||
                await NEISNavigator.selectComboboxOption('부서명', dept);
            if (!selected) {
                sendLog(`  부서 "${dept}" 선택 실패`, 'error');
                report.errors.push({ task: 'cumulative', dept, error: '부서 선택 실패' });
                continue;
            }
            await NEISNavigator.delay(500);

            // 조회
            await NEISNavigator.clickButtonByText('조회');
            await NEISNavigator.delay(2000);

            // 활동일자 목록 가져오기 (콤보박스 또는 그리드에서)
            let activityDates = [];
            const dateOptions = await getComboboxOptions('활동일');
            if (dateOptions.length > 0) {
                activityDates = dateOptions.filter(d => {
                    const match = d.match(/(\d{4}\.\d{2}\.\d{2})/);
                    if (!match) return true; // 날짜 형식이 아니면 일단 포함
                    const dateStr = match[1];
                    return (!config.startDate || dateStr >= config.startDate) &&
                        (!config.endDate || dateStr <= config.endDate);
                });
            }

            // 활동일자 콤보박스 없으면 일자 콤보박스 시도
            if (activityDates.length === 0) {
                const dateOpts2 = await getComboboxOptions('일자');
                activityDates = dateOpts2.filter(d => {
                    const match = d.match(/(\d{4}\.\d{2}\.\d{2})/);
                    if (!match) return true;
                    const dateStr = match[1];
                    return (!config.startDate || dateStr >= config.startDate) &&
                        (!config.endDate || dateStr <= config.endDate);
                });
            }

            if (activityDates.length === 0) {
                sendLog(`  활동일자 없음, 현재 표시된 데이터로 처리`, 'warning');
                // 날짜 없이 현재 그리드 데이터로 처리
                await processStudentGrid(config, dept);
                totalProcessed++;
                sendProgress(totalProcessed, 0, dept);
                continue;
            }

            sendLog(`  활동일자 ${activityDates.length}개`);

            for (let dateIdx = 0; dateIdx < activityDates.length; dateIdx++) {
                if (!isRunning) break;
                const dateText = activityDates[dateIdx];
                sendLog(`  [${dateIdx + 1}/${activityDates.length}] 활동일자: ${dateText}`);

                // 활동일자 선택
                await NEISNavigator.selectComboboxOption('활동일', dateText) ||
                    await NEISNavigator.selectComboboxOption('일자', dateText);
                await NEISNavigator.delay(1000);

                // 학생 그리드 처리
                await processStudentGrid(config, dept, dateText);
                totalProcessed++;
                sendProgress(totalProcessed, 0, `${dept} - ${dateText}`);
            }
        }

        sendLog(`=== 누��기록 완료 (${totalProcessed}건 처리) ===`, 'success');
    }

    // 학생 그리드에 이수시간, 활동내용 입력
    async function processStudentGrid(config, dept, dateText) {
        // 가장 큰 그리드 찾기 (학생 목록)
        const grids = document.querySelectorAll('[role="grid"]');
        let targetGrid = null;
        let maxCols = 0;
        for (const grid of grids) {
            const rows = grid.querySelectorAll('[role="row"]');
            for (const row of rows) {
                const cells = row.querySelectorAll('[role="gridcell"]');
                if (cells.length > maxCols) {
                    maxCols = cells.length;
                    targetGrid = grid;
                }
                break;
            }
        }

        if (!targetGrid) {
            sendLog(`    학생 그리드를 찾을 수 없습니다`, 'warning');
            return;
        }

        const rows = NEISNavigator.readGridRows(targetGrid);
        sendLog(`    학생 ${rows.length}명`);

        if (rows.length === 0) return;

        // 셀 구조 분석 (헤더에서 이수시간, 활동내용 컬럼 찾기)
        const headers = targetGrid.querySelectorAll('[role="columnheader"]');
        let hoursCol = -1;
        let contentCol = -1;

        headers.forEach((h, idx) => {
            const text = h.textContent?.trim() || '';
            if (text.includes('이수시간') && hoursCol === -1) hoursCol = idx;
            if (text.includes('활동내용') || text.includes('내용')) contentCol = idx;
        });

        sendLog(`    컬럼 매핑: 이��시간=${hoursCol}, 활동내용=${contentCol}`);

        if (hoursCol === -1 && contentCol === -1) {
            sendLog(`    이수시간/활동내용 컬럼을 찾을 수 없음. 헤더: ${Array.from(headers).map(h => h.textContent?.trim()).join(', ')}`, 'warning');
            report.errors.push({ task: 'cumulative', dept, date: dateText, error: '컬럼 매핑 실패' });
            return;
        }

        for (const row of rows) {
            if (!isRunning) break;

            // 이수시간 입력
            if (hoursCol >= 0 && hoursCol < row.cellElements.length) {
                const currentVal = row.cells[hoursCol]?.trim();
                if (!currentVal || currentVal === '0') {
                    await NEISNavigator.editGridCellValue(
                        row.cellElements[hoursCol],
                        String(config.hours || 1)
                    );
                    await NEISNavigator.delay(200);
                }
            }

            // 활동내용 입력
            if (contentCol >= 0 && contentCol < row.cellElements.length) {
                const currentVal = row.cells[contentCol]?.trim();
                if (!currentVal && config.content) {
                    await NEISNavigator.editGridCellValue(
                        row.cellElements[contentCol],
                        config.content
                    );
                    await NEISNavigator.delay(200);
                }
            }
        }

        // 저장
        const saved = await NEISNavigator.clickButtonByText('저장');
        if (saved) {
            sendLog(`    저장 완료`, 'success');
            report.processed.push({ task: 'cumulative', dept, date: dateText, students: rows.length });
        } else {
            sendLog(`    저장 실패`, 'error');
            report.errors.push({ task: 'cumulative', dept, date: dateText, error: '저장 실패' });
        }
        await NEISNavigator.delay(1000);
    }

    // ========================================
    // Task 4: 누가기록 (봉사활동 포함) - 일괄등록 방식
    // ========================================
    async function runCumulativeVolunteer(config) {
        sendLog('=== 누��기록 (봉사활동) 시작 ===');

        if (!await navigateToClubSubPage('��가기록')) return;

        const departments = await getAllDepartments();
        if (departments.length === 0) {
            sendLog('부서 목록을 가져올 수 없습니다', 'error');
            report.errors.push({ task: 'cumulative_volunteer', error: '부서 목록 없음' });
            return;
        }
        sendLog(`부서 ${departments.length}개`);

        let totalProcessed = 0;

        for (let di = 0; di < departments.length; di++) {
            if (!isRunning) break;
            const dept = departments[di];
            sendLog(`[부서 ${di + 1}/${departments.length}] ${dept}`);

            // 부서명 선택
            const selected = await NEISNavigator.selectComboboxOption('부서', dept) ||
                await NEISNavigator.selectComboboxOption('부서명', dept);
            if (!selected) {
                sendLog(`  부서 "${dept}" 선택 실패`, 'error');
                report.errors.push({ task: 'cumulative_volunteer', dept, error: '부서 선택 실패' });
                continue;
            }
            await NEISNavigator.delay(500);

            // 조회
            await NEISNavigator.clickButtonByText('조회');
            await NEISNavigator.delay(2000);

            // 일괄등록 버튼 클릭
            const batchOpened = await NEISNavigator.clickButtonByText('일괄등록');
            if (!batchOpened) {
                sendLog(`  일괄등록 버튼을 찾을 수 없습니다`, 'error');
                report.errors.push({ task: 'cumulative_volunteer', dept, error: '일괄등록 버튼 없음' });
                continue;
            }
            await NEISNavigator.delay(2000);

            // 활동일자 목록 가져오기
            let activityDates = await getComboboxOptions('활동일');
            if (activityDates.length === 0) {
                activityDates = await getComboboxOptions('일자');
            }

            // 기간 필터링
            activityDates = activityDates.filter(d => {
                const match = d.match(/(\d{4}\.\d{2}\.\d{2})/);
                if (!match) return true;
                const dateStr = match[1];
                return (!config.startDate || dateStr >= config.startDate) &&
                    (!config.endDate || dateStr <= config.endDate);
            });

            if (activityDates.length === 0) {
                sendLog(`  활동일자 없음`, 'warning');
                continue;
            }

            sendLog(`  활동일자 ${activityDates.length}개`);

            for (let dateIdx = 0; dateIdx < activityDates.length; dateIdx++) {
                if (!isRunning) break;
                const dateText = activityDates[dateIdx];
                sendLog(`  [${dateIdx + 1}/${activityDates.length}] ${dateText}`);

                // 일자 선택
                await NEISNavigator.selectComboboxOption('활동일', dateText) ||
                    await NEISNavigator.selectComboboxOption('일자', dateText);
                await NEISNavigator.delay(1000);

                // 전체 학생 선택 체크박스 (헤더 행의 체크박스)
                const grids = document.querySelectorAll('[role="grid"]');
                for (const grid of grids) {
                    const headerRows = grid.querySelectorAll('[role="row"]');
                    for (const row of headerRows) {
                        const headerCells = row.querySelectorAll('[role="columnheader"]');
                        if (headerCells.length > 0) {
                            const headerCb = findCheckbox(row);
                            if (headerCb) {
                                await setCheckbox(headerCb, true);
                                sendLog(`    전체 학생 선택`);
                                break;
                            }
                        }
                    }
                }
                await NEISNavigator.delay(500);

                // 이수시간 입력 (입력 필드 찾기)
                const hoursInputs = document.querySelectorAll('input[aria-label*="이수시간"], input[placeholder*="이수시간"]');
                if (hoursInputs.length > 0) {
                    const hoursInput = hoursInputs[0];
                    hoursInput.focus();
                    hoursInput.value = String(config.hours || 1);
                    hoursInput.dispatchEvent(new Event('input', { bubbles: true }));
                    hoursInput.dispatchEvent(new Event('change', { bubbles: true }));
                    await NEISNavigator.delay(300);
                } else {
                    sendLog(`    이수시간 입력란을 찾을 수 없음`, 'warning');
                }

                // 활동내용 입력
                const contentInputs = document.querySelectorAll(
                    'input[aria-label*="활동내용"], textarea[aria-label*="활동내용"], ' +
                    'input[aria-label*="내용"], textarea[aria-label*="내용"]'
                );
                if (contentInputs.length > 0 && config.content) {
                    const contentInput = contentInputs[0];
                    contentInput.focus();
                    contentInput.value = config.content;
                    contentInput.dispatchEvent(new Event('input', { bubbles: true }));
                    contentInput.dispatchEvent(new Event('change', { bubbles: true }));
                    await NEISNavigator.delay(300);
                } else if (config.content) {
                    sendLog(`    활동내용 입력란을 찾을 수 없음`, 'warning');
                }

                // 봉사활동실적입력 체크박스 체크
                let volunteerCb = null;
                const allLabels = document.querySelectorAll('label, span, div');
                for (const el of allLabels) {
                    if (el.textContent?.trim().includes('봉사활동실적입력') || el.textContent?.trim().includes('봉사활동')) {
                        volunteerCb = el.querySelector('input[type="checkbox"]') ||
                            el.closest('label')?.querySelector('input[type="checkbox"]');
                        if (!volunteerCb) {
                            // role="checkbox" 시도
                            volunteerCb = el.querySelector('[role="checkbox"]') ||
                                el.parentElement?.querySelector('[role="checkbox"]');
                        }
                        if (volunteerCb) break;
                    }
                }

                if (volunteerCb) {
                    // 1단계: 봉사활동 체크 → 저장
                    await setCheckbox(volunteerCb, true);
                    sendLog(`    봉사활동실적입력 체크`);
                    await NEISNavigator.delay(300);

                    await NEISNavigator.clickButtonByText('저장');
                    await NEISNavigator.delay(2000);
                    sendLog(`    1차 저장 (봉사활동 포함) 완료`, 'success');

                    // 2단계: 봉사활동 체크 해제 → 저장
                    await setCheckbox(volunteerCb, false);
                    sendLog(`    봉사활동실적입력 해제`);
                    await NEISNavigator.delay(300);

                    await NEISNavigator.clickButtonByText('저장');
                    await NEISNavigator.delay(2000);
                    sendLog(`    2차 저장 (봉사활동 해제) 완료`, 'success');
                } else {
                    sendLog(`    봉사활동실적입력 체크박스를 찾을 수 없음`, 'warning');
                    // 봉사활동 없이 저장
                    await NEISNavigator.clickButtonByText('저장');
                    await NEISNavigator.delay(2000);
                }

                report.processed.push({ task: 'cumulative_volunteer', dept, date: dateText });
                totalProcessed++;
                sendProgress(totalProcessed, 0, `${dept} - ${dateText}`);
            }
        }

        sendLog(`=== 누가기록 (봉사활동) 완료 (${totalProcessed}건) ===`, 'success');
    }

    // ========================================
    // Task 5: 이수시간반영
    // ========================================
    async function runCreditApply(config) {
        sendLog('=== 이수��간반영 시작 ===');

        if (!await navigateToClubSubPage('학생부자료기록')) return;

        // 이수시간 기준일 드롭박스에서 "직접입력" 선택
        sendLog('이수시간 기준일 → 직접입력 선택 중...');
        const selected = await NEISNavigator.selectComboboxOption('기준일', '직접입력') ||
            await NEISNavigator.selectComboboxOption('이수��간', '직접입력');
        if (!selected) {
            sendLog('직접입력 옵션을 선택할 수 없습니다', 'error');
            report.errors.push({ task: 'credit_apply', error: '직접입력 선택 실패' });
            return;
        }
        await NEISNavigator.delay(1000);

        // 날짜 등록 (config.creditDate)
        if (config.creditDate) {
            sendLog(`기준일 입력: ${config.creditDate}`);

            // 날짜 입력 필드 찾기
            const dateInputs = document.querySelectorAll(
                'input[type="date"], input[aria-label*="기준일"], input[aria-label*="날짜"]'
            );
            let dateSet = false;

            for (const input of dateInputs) {
                if (NEISNavigator.isVisible(input)) {
                    input.focus();
                    input.value = config.creditDate;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    await NEISNavigator.delay(500);
                    dateSet = true;
                    break;
                }
            }

            // combobox로 날짜 설정 시도
            if (!dateSet) {
                const dateCombo = NEISNavigator.findCombobox('기준일') ||
                    NEISNavigator.findCombobox('날짜');
                if (dateCombo && dateCombo.tagName === 'INPUT') {
                    dateCombo.focus();
                    dateCombo.value = config.creditDate;
                    dateCombo.dispatchEvent(new Event('input', { bubbles: true }));
                    dateCombo.dispatchEvent(new Event('change', { bubbles: true }));
                    await NEISNavigator.delay(500);
                    dateSet = true;
                }
            }

            if (!dateSet) {
                sendLog('기준일 입력란을 찾을 수 없습니다', 'error');
                report.errors.push({ task: 'credit_apply', error: '기준일 입력 실패' });
                return;
            }
        }

        // 이수시간반영 버튼 클릭
        sendLog('이수시간반영 버튼 클릭...');
        const applied = await NEISNavigator.clickButtonByText('이수시간반영');
        if (!applied) {
            sendLog('이수시간반영 버튼을 찾을 수 없습니다', 'error');
            report.errors.push({ task: 'credit_apply', error: '이수시간반영 버튼 없음' });
            return;
        }
        await NEISNavigator.delay(3000);

        // 저장
        const saved = await NEISNavigator.clickButtonByText('저장');
        if (saved) {
            sendLog('이수시간반영 저장 완료', 'success');
            report.processed.push({ task: 'credit_apply', date: config.creditDate });
        } else {
            sendLog('저장 실패', 'error');
            report.errors.push({ task: 'credit_apply', error: '저장 실패' });
        }

        sendLog('=== 이수시간반영 완료 ===', 'success');
    }

    // ========================================
    // 메인 실행 함수
    // ========================================
    async function run(config) {
        try {
            switch (config.task) {
                case 'credit_standard':
                    await runCreditStandard(config);
                    break;
                case 'attendance':
                    await runAttendance(config);
                    break;
                case 'cumulative':
                    await runCumulative(config);
                    break;
                case 'cumulative_volunteer':
                    await runCumulativeVolunteer(config);
                    break;
                case 'credit_apply':
                    await runCreditApply(config);
                    break;
                default:
                    sendLog(`알 수 없는 작업: ${config.task}`, 'error');
            }
        } catch (e) {
            sendLog(`치명적 오류: ${e.message}`, 'error');
            console.error('[Club]', e);
            report.errors.push({ task: config.task, error: e.message });
        }

        sendLog(`처리: ${report.processed.length}건, 오류: ${report.errors.length}건`);
        chrome.runtime.sendMessage({ action: "club_complete", report });
    }

    return {
        start(config) {
            isRunning = true;
            report.processed = [];
            report.errors = [];
            run(config);
        },
        stop() {
            isRunning = false;
            sendLog('중지 요청됨', 'warning');
        }
    };
})();

// 메시지 리스너는 한 번만 등록
if (!window._clubActivityListenerRegistered) {
    window._clubActivityListenerRegistered = true;
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "club_start") {
            window._clubActivity.start(request.config);
            sendResponse({ status: "started" });
        } else if (request.action === "club_stop") {
            window._clubActivity.stop();
            sendResponse({ status: "stopped" });
        } else if (request.action === "club_show_guide") {
            // 작업별 가이드 표시
            const guideSteps = {
                credit_standard: [
                    { num: '1', ariaLabel: '부서명', label: '부서명 선택 (자동)' },
                    { num: '2', ariaLabel: '기간시작일자', label: '시작일 설정' },
                    { num: '3', ariaLabel: '기���종료일자', label: '종료일 설정' },
                    { num: '4', buttonText: '조회', label: '조회 (자동)' },
                    { num: '5', buttonText: '저장', label: '저장 (자동)' }
                ],
                attendance: [
                    { num: '1', ariaLabel: '부서명', label: '부서명 (자동)' },
                    { num: '2', ariaLabel: '일자', label: '일자 (자동)' },
                    { num: '3', buttonText: '조회', label: '조회 (��동)' },
                    { num: '4', buttonText: '���감', label: '마감 (자��)' }
                ],
                cumulative: [
                    { num: '1', ariaLabel: '부서명', label: '부서명 (자동)' },
                    { num: '2', buttonText: '조회', label: '조회 (자동)' },
                    { num: '3', ariaLabel: '활동일', label: '활동일자 (자동)' },
                    { num: '4', buttonText: '저장', label: '저장 (자동)' }
                ],
                cumulative_volunteer: [
                    { num: '1', ariaLabel: '부서명', label: '부서명 (자동)' },
                    { num: '2', buttonText: '조회', label: '조회 (자동)' },
                    { num: '3', buttonText: '일괄등록', label: '일괄등록 (자동)' },
                    { num: '4', buttonText: '저장', label: '저장 (자동)' }
                ],
                credit_apply: [
                    { num: '1', ariaLabel: '기준일', label: '기준일 직접입력 (��동)' },
                    { num: '2', buttonText: '이수시간반영', label: '이수시간반영 (자동)' },
                    { num: '3', buttonText: '저장', label: '저장 (자동)' }
                ]
            };

            const steps = guideSteps[request.task] || guideSteps.credit_standard;
            const count = showGuideOverlay(steps);
            sendResponse({ count });
        }
    });
}
