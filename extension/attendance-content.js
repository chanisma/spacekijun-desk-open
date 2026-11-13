// 항상 최신 코드로 덮어쓰기 (개발 중 재주입 허용)
window._attendance = (() => {
    let isRunning = false;
    const report = { processed: [], needsReview: [], errors: [] };

    function sendLog(msg, type = 'info') {
        chrome.runtime.sendMessage({ action: "attendance_log", message: msg, type });
        console.log("[Attendance]", msg);
    }

    function sendProgress(current, total, detail) {
        chrome.runtime.sendMessage({ action: "attendance_progress", current, total, detail });
    }

    // 좌측 그리드에서 과목 목록 읽기
    function getSubjectList() {
        const leftGrid = NEISNavigator.findGridByColumnCount(3, true);

        if (!leftGrid) {
            sendLog(`[진단] 좌측 그리드(3셀) 찾지 못함`, "warning");
            return [];
        }

        const rows = NEISNavigator.readGridRows(leftGrid);
        const subjects = [];
        for (const row of rows) {
            if (row.cells.length >= 2) {
                subjects.push({
                    rowIndex: row.rowIndex,
                    period: row.cells[0] || '',
                    text: row.cells[1] || '',
                    isClosed: row.cells[2] === '마감',
                    element: row.element
                });
            }
        }
        sendLog(`[진단] 과목 ${subjects.length}개: ${subjects.map(s => s.text + (s.isClosed ? '(마감)' : '')).join(', ')}`);
        return subjects;
    }

    // 과목 행 클릭
    async function clickSubjectRow(subject) {
        const cells = subject.element.querySelectorAll('[role="gridcell"]');
        if (cells.length >= 2) {
            await NEISNavigator.clickGridCell(cells[1]);
            await NEISNavigator.delay(3000);
        }
    }

    // 우측 그리드에서 학생 데이터 읽기 (행당 10셀 이상)
    function readStudentGrid() {
        const rightGrid = NEISNavigator.findGridByColumnCount(10);

        if (!rightGrid) {
            sendLog(`[진단] 우측 그리드(10+셀) 찾지 못함`, "warning");
            return [];
        }

        const students = NEISNavigator.readGridRows(rightGrid)
            .filter(row => row.cells.length >= 10);

        sendLog(`[진단] 학생 ${students.length}명`);
        if (students.length > 0) {
            sendLog(`[진단] 첫 학생 셀: ${JSON.stringify(students[0].cells)}`);
        }
        // 출석인정 학생 로깅
        const attendStudents = students.filter(s => s.cells[7] && s.cells[7].startsWith('출석인정'));
        if (attendStudents.length > 0) {
            sendLog(`[진단] 출석인정 학생 ${attendStudents.length}명`);
            attendStudents.forEach(s => {
                sendLog(`[진단]   ${s.cells[4]} - cells[6]="${s.cells[6]}" cells[7]="${s.cells[7]}" cells[8]="${s.cells[8]}" cells[9]="${s.cells[9]}"`);
            });
        } else {
            sendLog(`[진단] 출석인정 학생 없음 (cells[7] 값들: ${students.slice(0, 3).map(s => `"${s.cells[7]}"`).join(', ')})`);
        }

        return students;
    }

    // 비고 셀 편집 (셀 인덱스 9)
    async function editBigoCell(student, value) {
        const bigoCell = student.cellElements[9];
        if (!bigoCell) return false;

        // 범용 셀 편집 시도
        const edited = await NEISNavigator.editGridCellValue(bigoCell, value);
        if (edited) return true;

        // 대안: 비고일괄 입력창 활용 (출결관리 전용 fallback)
        const bulkInput = document.querySelector('input[aria-label*="비고"]');
        if (bulkInput) {
            sendLog("비고 셀 직접 편집 실패, 일괄 입력창 시도...", "warning");
            const checkbox = student.cellElements[0]?.querySelector('input[type="checkbox"]');
            if (checkbox && !checkbox.checked) {
                checkbox.click();
                await NEISNavigator.delay(300);
            }
            bulkInput.focus();
            bulkInput.value = value;
            bulkInput.dispatchEvent(new Event('input', { bubbles: true }));
            bulkInput.dispatchEvent(new Event('change', { bubbles: true }));
            await NEISNavigator.delay(200);

            await NEISNavigator.clickButtonByText('적용') ||
                await NEISNavigator.clickButtonByText('비고적용');

            if (checkbox && checkbox.checked) {
                checkbox.click();
                await NEISNavigator.delay(200);
            }
            return true;
        }

        return false;
    }

    // 저장 버튼 클릭
    async function clickSaveButton() {
        const saved = await NEISNavigator.clickButtonByText('저장');
        if (saved) {
            await NEISNavigator.delay(1000);
        }
        return saved;
    }

    // 메인 루프
    async function runAttendanceLoop(config) {
        const { startDate, endDate, checkClosed, readOnly } = config;

        try {
            // 1. 스크롤 방식으로 시작일 선택
            sendLog(`시작일(${startDate}) 선택 중...`);
            const selected = await NEISNavigator.selectDateByScroll(startDate);
            if (!selected) {
                // 정확한 시작일이 없으면 (휴일 등) 가장 가까운 이후 날짜 찾기
                sendLog(`${startDate} 정확히 없음. 가장 가까운 날짜를 찾는 중...`, "warning");
                // +버튼으로 시작일 이후 첫 날짜까지 이동 시도
                let currentDate = NEISNavigator.getCurrentDate();
                if (!currentDate) {
                    sendLog("현재 일자를 읽을 수 없습니다.", "error");
                    report.errors.push({ error: "현재 일자 읽기 실패" });
                    chrome.runtime.sendMessage({ action: "attendance_complete", report });
                    return;
                }
                // 현재가 시작일 이전이면 앞으로 이동
                let navCount = 0;
                while (currentDate < startDate && navCount < 200) {
                    if (!isRunning) break;
                    const moved = await NEISNavigator.clickNextDate();
                    if (!moved) break;
                    currentDate = NEISNavigator.getCurrentDate();
                    if (!currentDate) break;
                    navCount++;
                }
                if (!currentDate || currentDate > endDate) {
                    sendLog(`범위 내 일자 없음. 현재: ${currentDate}, 범위: ${startDate}~${endDate}`, "error");
                    report.errors.push({ error: `범위 내 일자 없음` });
                    chrome.runtime.sendMessage({ action: "attendance_complete", report });
                    return;
                }
            }

            let currentDate = NEISNavigator.getCurrentDate();
            sendLog(`시작일 도착: ${currentDate}`, "success");
            let datesProcessed = 0;

            // 2. 시작일부터 종료일까지 순회 (+버튼으로 다음 날짜 이동)
            while (isRunning) {
                currentDate = NEISNavigator.getCurrentDate();
                if (!currentDate || currentDate > endDate) break;

                sendLog(`날짜: ${currentDate}`);

                await NEISNavigator.delay(2000);
                const subjects = getSubjectList();
                const targetSubjects = subjects.filter(s =>
                    s.text.startsWith('1학년') || s.text.startsWith('2학년')
                );

                if (targetSubjects.length === 0) {
                    sendLog(`  과목 없음 (${currentDate})`, "warning");
                }

                for (const subject of targetSubjects) {
                    if (!isRunning) break;

                    const isClosed = subject.isClosed;
                    if (isClosed && !checkClosed) {
                        sendLog(`  [건너뜀] ${subject.text} - 이미 마감`, "warning");
                        continue;
                    }

                    sendLog(`  과목: ${subject.text}${isClosed ? ' (마감 - 읽기 전용)' : ''}`);
                    await clickSubjectRow(subject);

                    const students = readStudentGrid();
                    let modified = false;

                    for (const student of students) {
                        if (!isRunning) break;

                        const attend = student.cells[7];
                        if (!attend || !attend.startsWith('출석인정')) continue;

                        const record = {
                            date: currentDate,
                            grade: student.cells[1],
                            class: student.cells[2],
                            num: student.cells[3],
                            name: student.cells[4],
                            period: subject.period,
                            status: attend,
                            bigo: student.cells[9] || '',
                            reason: student.cells[10] || '',
                            subject: subject.text,
                            closed: isClosed ? '마감' : ''
                        };

                        // 출석인정결석 + 비고 비어있음 + 미마감 → 자동 입력
                        if (attend === '출석인정결석' && !student.cells[9] && !isClosed && !readOnly) {
                            const success = await editBigoCell(student, "출석인정결과");
                            if (success) {
                                modified = true;
                                record.bigo = '출석인정결과';
                                report.processed.push(record);
                                sendLog(`    [입력] ${student.cells[1]}학년 ${student.cells[2]}반 ${student.cells[3]}번 ${student.cells[4]} - 출석인정결과`, "success");
                            } else {
                                report.errors.push({ date: currentDate, name: student.cells[4], error: "비고 셀 편집 실패" });
                                sendLog(`    [오류] ${student.cells[4]} - 비고 셀 편집 실패`, "error");
                            }
                        } else {
                            // 그 외 모든 출석인정 (결석/조퇴/지각, 비고 유무 무관) → 기록
                            report.needsReview.push(record);
                            const bigoNote = student.cells[9] ? `, 비고: "${student.cells[9]}"` : '';
                            sendLog(`    [기록] ${student.cells[4]} - ${attend}${bigoNote}`);
                        }
                    }

                    if (modified) {
                        const saved = await clickSaveButton();
                        if (saved) {
                            sendLog(`  저장 완료: ${subject.text}`, "success");
                        } else {
                            sendLog(`  저장 실패: ${subject.text}`, "error");
                        }
                    }
                }

                datesProcessed++;
                sendProgress(datesProcessed, 0, currentDate);

                const beforeDate = currentDate;
                const moved = await NEISNavigator.clickNextDate();
                if (!moved) {
                    sendLog("더 이상 다음 일자가 없습니다.", "warning");
                    break;
                }
                const afterDate = NEISNavigator.getCurrentDate();
                if (afterDate === beforeDate) {
                    sendLog(`마지막 일자(${afterDate})에 도달했습니다.`, "warning");
                    break;
                }
            }
        } catch (e) {
            sendLog(`오류 발생: ${e.message}`, "error");
            report.errors.push({ error: e.message });
        }

        sendLog("처리 완료!", "success");
        sendLog(`  입력: ${report.processed.length}건, 기록: ${report.needsReview.length}건, 오류: ${report.errors.length}건`);
        chrome.runtime.sendMessage({ action: "attendance_complete", report });
    }

    return {
        start(config) {
            isRunning = true;
            report.processed = [];
            report.needsReview = [];
            report.errors = [];
            runAttendanceLoop(config);
        },
        stop() {
            isRunning = false;
        }
    };
})();

// 메시지 리스너는 한 번만 등록
if (!window._attendanceListenerRegistered) {
    window._attendanceListenerRegistered = true;
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "attendance_start") {
            window._attendance.start(request.config);
            sendResponse({ status: "started" });
        } else if (request.action === "attendance_stop") {
            window._attendance.stop();
            sendResponse({ status: "stopped" });
        }
    });
}
