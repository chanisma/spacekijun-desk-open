// 항상 최신 코드로 덮어쓰기 (개발 중 재주입 허용)
window.NEISNavigator = (() => {
    function delay(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    function isVisible(el) {
        return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
    }

    // NEIS 로딩 인디케이터 대기
    async function waitForLoading(maxMs = 30000) {
        let loader = null;
        let attempts = 0;
        while (attempts < 8) {
            loader = document.querySelector('.ers_progress_content');
            if (loader && isVisible(loader)) break;
            loader = null;
            await delay(125);
            attempts++;
        }
        if (!loader) return;

        const maxWait = maxMs / 250;
        let waitCount = 0;
        while (waitCount < maxWait) {
            loader = document.querySelector('.ers_progress_content');
            if (!loader || !isVisible(loader)) return;
            await delay(250);
            waitCount++;
        }
    }

    // 상단 탭 클릭
    async function clickTopTab(tabName) {
        const divs = document.querySelectorAll('.cl-navigationbar-text.cl-text');
        for (const div of divs) {
            const text = Array.from(div.childNodes)
                .filter(n => n.nodeType === Node.TEXT_NODE)
                .map(n => n.textContent.trim()).join('');
            if (text === tabName) {
                const parent = div.closest('a') || div.parentElement;
                parent.click();
                await delay(1500);
                return true;
            }
        }
        return false;
    }

    // 드롭다운 메뉴 아이템 클릭
    async function clickDropdownItem(itemText) {
        const items = document.querySelectorAll('.cl-navigationbar-listitem');
        for (const item of items) {
            const text = item.textContent?.trim();
            if (text && text.startsWith(itemText)) {
                const rect = item.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    item.click();
                    await waitForLoading();
                    return true;
                }
            }
        }
        return false;
    }

    // 사이드바 아이템 클릭
    async function clickSidebarItem(itemText) {
        const items = document.querySelectorAll('.cl-sidenavigation-item .cl-text');
        for (const item of items) {
            if (item.textContent?.trim().startsWith(itemText)) {
                const parent = item.closest('a') || item.parentElement;
                parent.click();
                await waitForLoading();
                return true;
            }
        }
        return false;
    }

    // 콤보박스 찾기
    function findCombobox(ariaLabel) {
        const all = Array.from(document.querySelectorAll('[role="combobox"]'));
        return all.find(c => {
            const label = c.getAttribute('aria-label') || '';
            return label.includes(ariaLabel);
        });
    }

    // 콤보박스의 부모 컨테이너 찾기 (INPUT 타입용)
    function findComboContainer(combo) {
        let el = combo.parentElement;
        for (let i = 0; i < 5 && el; i++) {
            if (el.querySelector('.cl-combobox-button')) return el;
            if (el.classList?.contains('cl-combobox')) return el;
            el = el.parentElement;
        }
        return combo.parentElement;
    }

    // 콤보박스 열기
    async function openCombobox(combo) {
        if (combo.tagName === 'INPUT') {
            const container = findComboContainer(combo);
            const btn = container?.querySelector('.cl-combobox-button');
            if (btn) {
                btn.click();
                await delay(1000);
            } else {
                combo.focus();
                await delay(300);
                combo.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'ArrowDown', code: 'ArrowDown', keyCode: 40, bubbles: true
                }));
                await delay(1000);
            }
        } else {
            combo.click();
            await delay(800);
        }
    }

    // 콤보박스 닫기
    async function closeCombobox(combo) {
        if (combo.tagName === 'INPUT') {
            const container = findComboContainer(combo);
            const btn = container?.querySelector('.cl-combobox-button');
            if (btn) {
                btn.click();
                await delay(300);
                return;
            }
        }
        combo.click();
        await delay(300);
    }

    // DIV 타입 콤보박스 옵션 선택 (학년도, 학기 등)
    async function selectComboboxOption(ariaLabel, optionText) {
        const combo = findCombobox(ariaLabel);
        if (!combo) return false;

        await openCombobox(combo);

        const options = Array.from(document.querySelectorAll('[role="option"]'));
        const target = options.find(opt =>
            isVisible(opt) && opt.textContent?.trim() === optionText
        );

        if (target) {
            target.scrollIntoView({ block: 'nearest' });
            await delay(100);
            target.click();
            await waitForLoading();
            return true;
        }

        await closeCombobox(combo);
        return false;
    }

    // ========================================
    // 일자 콤보박스 가상 스크롤 기반 날짜 선택
    // ========================================

    // 일자 콤보박스를 열고 가상 스크롤로 특정 날짜 옵션 선택
    async function selectDateByScroll(targetDateStr) {
        const combo = findCombobox('일자');
        if (!combo) { console.log('[NAV] 일자 콤보박스 없음'); return false; }

        await openCombobox(combo);
        await delay(500);

        // listbox 내부 .cl-viewport 찾기
        const listbox = document.querySelector('[role="listbox"]');
        if (!listbox) { console.log('[NAV] listbox 없음'); await closeCombobox(combo); return false; }

        const viewport = listbox.querySelector('.cl-viewport') || listbox;

        // 1단계: 맨 위로 스크롤
        for (let i = 0; i < 30; i++) {
            viewport.dispatchEvent(new WheelEvent('wheel', {
                deltaY: -300, bubbles: true, cancelable: true
            }));
            await delay(80);
        }
        await delay(300);

        // 2단계: 아래로 스크롤하며 대상 날짜 찾기
        const maxScrollSteps = 100;
        let lastSeenDate = '';
        for (let step = 0; step < maxScrollSteps; step++) {
            const options = Array.from(document.querySelectorAll('[role="option"]'));
            const visibleOptions = options.filter(o => isVisible(o));

            for (const opt of visibleOptions) {
                const text = opt.textContent?.trim() || '';
                const match = text.match(/(\d{4}\.\d{2}\.\d{2})/);
                if (match && match[1] === targetDateStr) {
                    opt.scrollIntoView({ block: 'nearest' });
                    await delay(100);
                    opt.click();
                    await waitForLoading();
                    console.log(`[NAV] 날짜 선택 완료: ${targetDateStr}`);
                    return true;
                }
            }

            // 마지막 보이는 옵션의 날짜가 대상보다 크면 → 없는 날짜
            const lastVisible = visibleOptions[visibleOptions.length - 1];
            if (lastVisible) {
                const lastMatch = lastVisible.textContent?.trim().match(/(\d{4}\.\d{2}\.\d{2})/);
                if (lastMatch) {
                    if (lastMatch[1] > targetDateStr) {
                        console.log(`[NAV] 대상(${targetDateStr})을 지나침. 마지막: ${lastMatch[1]}`);
                        await closeCombobox(combo);
                        return false;
                    }
                    if (lastMatch[1] === lastSeenDate) {
                        console.log(`[NAV] 더 이상 스크롤 안됨. 마지막: ${lastMatch[1]}`);
                        await closeCombobox(combo);
                        return false;
                    }
                    lastSeenDate = lastMatch[1];
                }
            }

            // 아래로 스크롤
            viewport.dispatchEvent(new WheelEvent('wheel', {
                deltaY: 150, bubbles: true, cancelable: true
            }));
            await delay(150);
        }

        console.log(`[NAV] 스크롤 완료 후에도 날짜 못 찾음: ${targetDateStr}`);
        await closeCombobox(combo);
        return false;
    }

    // ========================================
    // 일자 +/- 버튼 기반 날짜 네비게이션
    // ========================================

    // aria-label로 버튼 찾기
    function findButtonByLabel(label) {
        return Array.from(document.querySelectorAll('[role="button"]'))
            .find(btn => btn.getAttribute('aria-label') === label && isVisible(btn));
    }

    // 현재 선택된 일자 읽기 (콤보박스 value)
    function getCurrentDate() {
        const combo = findCombobox('일자');
        if (!combo) return null;
        const val = combo.value || combo.textContent?.trim() || '';
        // "2025.09.18.(목)" -> "2025.09.18"
        const match = val.match(/(\d{4}\.\d{2}\.\d{2})/);
        return match ? match[1] : null;
    }

    // 일자더하기 버튼 클릭 → 다음 날짜로 이동
    async function clickNextDate() {
        const btn = findButtonByLabel('일자더하기');
        if (!btn) return false;
        btn.click();
        await waitForLoading();
        await delay(500);
        return true;
    }

    // 일자빼기 버튼 클릭 → 이전 날짜로 이동
    async function clickPrevDate() {
        const btn = findButtonByLabel('일자빼기');
        if (!btn) return false;
        btn.click();
        await waitForLoading();
        await delay(500);
        return true;
    }

    // 전체 네비게이션: 탭 -> 드롭다운 -> 사이드바
    async function navigateTo(tabName, dropdownItem, sidebarItem) {
        await clickTopTab(tabName);
        if (dropdownItem) await clickDropdownItem(dropdownItem);
        if (sidebarItem) await clickSidebarItem(sidebarItem);
    }

    // 그리드 행 데이터 읽기 (레거시 — 모든 행 반환)
    function getGridRows(gridElement) {
        if (!gridElement) return [];
        const rows = gridElement.querySelectorAll('[role="row"]');
        return Array.from(rows).map((row, rowIndex) => {
            const cells = row.querySelectorAll('[role="gridcell"]');
            return {
                rowIndex,
                element: row,
                cells: Array.from(cells).map(cell => cell.textContent?.trim() || ''),
                cellElements: Array.from(cells)
            };
        });
    }

    // 셀 수로 그리드 찾기 (데이터행 기준)
    // exact=true: 정확히 cellCount개, exact=false: cellCount개 이상
    function findGridByColumnCount(cellCount, exact = false) {
        const grids = document.querySelectorAll('[role="grid"]');
        for (const grid of grids) {
            const rows = grid.querySelectorAll('[role="row"]');
            for (const row of rows) {
                const cells = row.querySelectorAll('[role="gridcell"]');
                if (cells.length === 0) continue;
                const match = exact
                    ? cells.length === cellCount
                    : cells.length >= cellCount;
                if (match) return grid;
            }
        }
        return null;
    }

    // 그리드 전체 행 읽기 (헤더행 자동 제외, gridcell이 1개 이상인 행만)
    function readGridRows(gridElement) {
        if (!gridElement) return [];
        const rows = gridElement.querySelectorAll('[role="row"]');
        const result = [];
        let dataIndex = 0;
        rows.forEach(row => {
            const cellElements = row.querySelectorAll('[role="gridcell"]');
            if (cellElements.length === 0) return; // 헤더행(columnheader만 있는 행) 제외
            result.push({
                rowIndex: dataIndex++,
                element: row,
                cells: Array.from(cellElements).map(c => c.textContent?.trim() || ''),
                cellElements: Array.from(cellElements)
            });
        });
        return result;
    }

    // 그리드 셀 편집 (더블클릭 → input 찾기 → 값 입력 → Tab 확정)
    async function editGridCellValue(cellElement, value) {
        if (!cellElement) return false;

        const rect = cellElement.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;

        // 더블클릭으로 편집 모드 진입
        cellElement.dispatchEvent(new MouseEvent('dblclick', {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y
        }));
        await delay(500);

        // input/textarea 탐색
        let input = cellElement.querySelector('input, textarea');
        if (!input) {
            // contentEditable 대응
            if (cellElement.isContentEditable || cellElement.contentEditable === 'true') {
                cellElement.textContent = value;
                cellElement.dispatchEvent(new Event('input', { bubbles: true }));
                cellElement.dispatchEvent(new Event('change', { bubbles: true }));
                await delay(300);
                cellElement.dispatchEvent(new Event('blur', { bubbles: true }));
                await delay(300);
                return true;
            }

            // 한 번 더 클릭 시도
            await clickGridCell(cellElement);
            await delay(500);
            input = cellElement.querySelector('input, textarea');
        }

        if (input) {
            input.focus();
            input.value = value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            await delay(200);

            // Tab 키로 확정
            input.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Tab', code: 'Tab', keyCode: 9, bubbles: true
            }));
            await delay(300);
            return true;
        }

        return false;
    }

    // 텍스트로 버튼 찾아 클릭
    async function clickButtonByText(text) {
        const btns = document.querySelectorAll('[role="button"]');
        const target = Array.from(btns).find(b => b.textContent?.trim() === text);
        if (target) {
            target.click();
            await waitForLoading();
            return true;
        }
        return false;
    }

    // 그리드 셀 클릭 (편집 모드 진입)
    async function clickGridCell(cellElement) {
        if (!cellElement) return;
        const rect = cellElement.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;

        cellElement.dispatchEvent(new MouseEvent('mousedown', {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y
        }));
        cellElement.dispatchEvent(new MouseEvent('mouseup', {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y
        }));
        cellElement.dispatchEvent(new MouseEvent('click', {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y
        }));
        await delay(300);
    }

    return {
        delay, isVisible, waitForLoading,
        clickTopTab, clickDropdownItem, clickSidebarItem,
        navigateTo, findCombobox, selectComboboxOption,
        openCombobox, closeCombobox,
        selectDateByScroll,
        getCurrentDate, clickNextDate, clickPrevDate,
        findButtonByLabel,
        getGridRows, clickGridCell,
        findGridByColumnCount, readGridRows,
        editGridCellValue, clickButtonByText
    };
})();
