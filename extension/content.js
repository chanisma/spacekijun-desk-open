if (!window.neisScraperLoaded) {
    window.neisScraperLoaded = true;

    let isRunning = false;
    let configDelay = 2000;

    // Mapping of section keys to [Menu, SubMenu] paths
    const SECTION_MAP = {
        "history": ["학년반이력", "학년반이력"],
        "hakjeok": ["인적·학적사항", "학적사항"],
        "attend": ["출결상황", "출결상황"],
        "volunteer": ["봉사활동상황", "봉사활동상황"],
        "creative": ["창의적체험활동", "창의적체험활동"],
        "subject": ["교과학습발달상황", "교과학습발달상황"],
        "sewteuk": ["교과학습발달상황", "세부능력및특기사항"],
        "reading": ["독서활동상황", "독서활동상황"],
        "behavior": ["행동특성및종합의견", "행동특성및종합의견"]
    };

    // Logger
    function sendLog(msg) {
        chrome.runtime.sendMessage({ action: "log", message: msg });
        console.log("[NEIS Scraper]", msg);
    }

    function delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Message Listener
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "start") {
            if (isRunning) return;
            isRunning = true;
            configDelay = request.delay || 2000;
            const sections = request.sections || [];
            const config = request.config || {};

            sendLog(`Starting automation...`);
            sendLog(`Config: Grade ${config.gradeStart}-${config.gradeEnd}, Class ${config.classStart}-${config.classEnd}`);

            runAutomationLoop(sections, config).then(() => {
                sendLog("Automation Finished.");
                isRunning = false;
            }).catch(e => {
                sendLog("Error: " + e.message);
                isRunning = false;
            });

            sendResponse({ status: "started" });
        } else if (request.action === "stop") {
            isRunning = false;
            sendLog("Stopping automation...");
            sendResponse({ status: "stopped" });
        } else if (request.action === "download_started") {
            sendLog(`[Download] Download started: ${request.downloadId}`);
            window.lastDownloadStarted = true;
        }
    });

    // --- Core Automation Loop ---

    async function runAutomationLoop(selectedSections, config) {
        // 1. Identify Grade Dropdown
        const gradeCombo = findCombobox("계열/학년/학과");
        if (!gradeCombo) {
            throw new Error("Grade combobox ('계열/학년/학과') not found.");
        }

        // Open Grade Combo to get options
        // gradeCombo.click();
        // await delay(1000);

        // const allGradeOptions = Array.from(document.querySelectorAll('[role="option"]'));
        // const visibleGradeOptions = allGradeOptions.filter(el => isVisible(el));
        // sendLog(`Found ${visibleGradeOptions.length} grades.`);

        const visibleGradeOptions = [1, 2, 3];

        // Close Combo
        // gradeCombo.click();
        // await delay(500);

        // Filter Grades
        const targetGrades = [];
        for (let i = 0; i < visibleGradeOptions.length; i++) {
            // Heuristic: check if innerText contains the number? 
            // Or just use index logic (0 -> Grade 1, 1 -> Grade 2, etc.)
            // NEIS usually lists 1학년, 2학년, 3학년 in order.
            // We will use 1-based index logic vs config.
            const gradeNum = i + 1;
            if (gradeNum >= config.gradeStart && gradeNum <= config.gradeEnd) {
                targetGrades.push({ index: i, num: gradeNum });
            }
        }

        if (targetGrades.length === 0) {
            throw new Error(`No grades found in range ${config.gradeStart}-${config.gradeEnd}`);
        }

        // --- Outer Loop: Grades ---
        for (const gradeObj of targetGrades) {
            if (!isRunning) break;

            sendLog(`Processing Grade ${gradeObj.num}...`);
            await selectGrade(gradeObj.index);
            await delay(configDelay);

            // Now handle Classes for this Grade
            const classCombo = findCombobox("반");
            if (!classCombo) {
                sendLog("Class combobox not found for this grade.");
                continue;
            }

            // classCombo.click();
            // await delay(1000);

            // const allClassOptions = Array.from(document.querySelectorAll('[role="option"]'));
            // const visibleClassOptions = allClassOptions.filter(el => isVisible(el));

            // classCombo.click(); // Close
            // await delay(500);


            const visibleClassOptions = [1, 2, 3, 4, 5, 6, 7, 8, 9];
            sendLog(`Found ${visibleClassOptions.length} classes for Grade ${gradeObj.num}.`);

            // --- Inner Loop: Classes ---
            for (let i = 0; i < visibleClassOptions.length; i++) {
                if (!isRunning) break;

                const classNum = i + 1; // 1-based index
                if (classNum < config.classStart || classNum > config.classEnd) continue;

                sendLog(`>>> Processing Grade ${gradeObj.num} - Class ${classNum}`);

                await selectClass(i);

                // Capture Text
                const gradeText = `Grade${gradeObj.num}`;
                const classText = `Class${classNum}`;

                await delay(configDelay);
                await clickMainSearch();
                await delay(configDelay);

                // --- Sections Loop ---
                for (const sectionKey of selectedSections) {
                    if (!isRunning) break;

                    const success = await navigateToSection(sectionKey);
                    if (success) {
                        await delay(configDelay + 2000);
                        const downloadSuccess = await triggerIframeDownload(sectionKey, classNum, gradeText, classText);
                        if (!downloadSuccess) {
                            sendLog(`Failed to download for ${sectionKey}`);
                        }
                    }
                    await delay(1000);
                }
            }
        }
    }

    // --- Helper Functions ---

    async function selectGrade(index) {
        const gradeCombo = findCombobox("계열/학년/학과");
        if (!gradeCombo) return;

        gradeCombo.click();
        await delay(500);

        const allOptions = Array.from(document.querySelectorAll('[role="option"]'));
        const visibleOptions = allOptions.filter(el => isVisible(el));

        if (visibleOptions[index]) {
            visibleOptions[index].click();
            await delay(1000); // Wait for page refresh/class reload
        }
    }

    async function selectClass(index) {
        const classCombo = findCombobox("반");
        if (!classCombo) return;

        classCombo.click();
        await delay(500);

        const allOptions = Array.from(document.querySelectorAll('[role="option"]'));
        const visibleOptions = allOptions.filter(el => isVisible(el));

        if (visibleOptions[index]) {
            visibleOptions[index].click();
            await delay(500);
        }
    }

    async function clickMainSearch() {
        const buttons = Array.from(document.querySelectorAll('button, a[role="button"], [role="button"]'));
        const searchBtn = buttons.find(b => b.textContent && b.textContent.trim() === "조회");
        if (searchBtn && isVisible(searchBtn)) {
            searchBtn.click();
            return true;
        }
        return false;
    }

    async function navigateToSection(key) {
        const path = SECTION_MAP[key];
        if (!path) return false;

        const parentName = path[0];
        const childName = path[1];

        sendLog(`[Nav] Navigating: ${parentName} > ${childName}`);

        const parentXpath = `//div[contains(@class, 'expander') and contains(., '${parentName}')]`;
        const parentResult = document.evaluate(parentXpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        const parentEl = parentResult.singleNodeValue;

        if (!parentEl) {
            sendLog(`[Parent] Menu '${parentName}' not found via XPath: ${parentXpath}`);
            return false;
        }

        if (parentEl.classList.contains('collapsed')) {
            sendLog(`[Parent] Clicking '${parentName}' (Collapsed)...`);
            parentEl.click();
            sendLog(`[Delay] Waiting 3000ms for siblings...`);
            await delay(1000);
        } else {
            sendLog(`[Parent] '${parentName}' already expanded.`);
            await delay(1000);
        }

        // 2. Click Child (Sibling Row)
        // Updated to specifically target 'cl-text' based on user feedback/HTML
        const childXpath = `//div[contains(@class, 'cl-text') and normalize-space(text())='${childName}']`;
        sendLog(`[Child] Searching for '${childName}'...`);

        const childResult = document.evaluate(childXpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        const childEl = childResult.singleNodeValue;

        if (childEl && isVisible(childEl)) {
            sendLog(`[Child] Found '${childName}'.`);
            console.log(">>> CHILD FOUND:", childEl);
            console.log("Inner Text:", childEl.innerText);
            console.log("Classes:", childEl.className);
            console.log("Parent:", childEl.parentElement);

            // Try highlighting it to show user where it is
            childEl.style.border = "3px solid red";

            // The crash indicates the framework expects specific event properties or sequence.
            // Using a proper MouseEvent sequence on the LEAF node (text) is usually safest/most robust.
            sendLog(`[Child] Triggering Mouse Events on text element...`);
            triggerMouseEvent(childEl, "mousedown");
            triggerMouseEvent(childEl, "mouseup");
            triggerMouseEvent(childEl, "click");
            await waitForLoading();
            return true;
        } else {
            sendLog(`[Child] Menu '${childName}' not found (XPath: ${childXpath})`);
            return false;
        }
    }

    // Helper to simulate full mouse event
    function triggerMouseEvent(node, eventType) {
        const clickEvent = new MouseEvent(eventType, {
            bubbles: true,
            cancelable: true,
            view: window
        });
        node.dispatchEvent(clickEvent);
    }

    async function triggerIframeDownload(sectionKey, classIndex, gradeText, classText) {
        sendLog(`[Download] Attempting download for ${sectionKey}...`);

        const iframes = Array.from(document.querySelectorAll('iframe'));
        const targetIframe = iframes.find(f => isVisible(f));

        if (!targetIframe) {
            sendLog("[Download] No visible iframe found.");
            return false;
        }

        try {
            const doc = targetIframe.contentDocument;
            if (!doc) {
                sendLog("[Download] Cannot access iframe content (Cross-origin?).");
                return false;
            }

            const saveBtn = doc.querySelector('#crownix-toolbar-save button') || doc.querySelector('#crownix-toolbar-save');
            if (!saveBtn) {
                sendLog("[Download] Save button (#crownix-toolbar-save) not found in iframe.");
                return false;
            }

            const safeGrade = (gradeText || "Unknown").trim();
            const safeClass = (classText || `Class${classIndex}`).trim();
            const displayName = SECTION_MAP[sectionKey] ? SECTION_MAP[sectionKey][1] : sectionKey;
            const safeSection = displayName.replace(/[ \/]/g, "_");

            const finalFilename = `${safeGrade}_${safeClass}_${safeSection}.xls`;

            chrome.runtime.sendMessage({
                action: "set_filename",
                filename: finalFilename
            });
            sendLog(`[Download] Set target filename: ${finalFilename}`);

            saveBtn.click();
            await delay(3000);

            let btnSelectorId = 'xls_data';
            let btnLabel = 'XLS Data';

            // Special handling for SeTeuk: use "xls" (standard) instead of "xls_data" (raw data)
            // if (sectionKey === 'sewteuk') {
            //     btnSelectorId = 'xls';
            //     btnLabel = 'XLS';
            // }

            const downloadBtn = doc.querySelector(`#crownix-toolbar-${btnSelectorId} button`) || doc.querySelector(`#crownix-toolbar-${btnSelectorId}`);

            if (!downloadBtn) {
                sendLog(`[Download] '${btnLabel}' button (#crownix-toolbar-${btnSelectorId}) not found.`);
                return false;
            }

            window.lastDownloadStarted = false; // Reset flag
            downloadBtn.click();
            sendLog(`[Download] Clicked '${btnLabel}' for ${finalFilename}`);

            // Wait for download to start (max 5 seconds)
            sendLog("[Download] Waiting for download to start...");
            let downloadWait = 0;
            while (downloadWait < 40) { // 40 * 250ms = 10 seconds
                if (window.lastDownloadStarted) {
                    sendLog("[Download] Download start confirmed.");
                    break;
                }
                await delay(250);
                downloadWait++;
            }

            if (!window.lastDownloadStarted) {
                sendLog("[Download] Warning: Download start not confirmed within 30s.");
            }

            return true;

        } catch (e) {
            sendLog("[Download] Iframe interaction error: " + e.message);
            return false;
        }
    }

    async function waitForLoading() {
        // Phase 1: Wait for loader to appear (max 5 seconds)
        // Sometimes the loader takes a moment to show up after the click.
        let loader = null;
        let attempts = 0;
        while (attempts < 8) { // 8 * 125ms = 1 seconds
            loader = findLoader();
            if (loader) {
                break;
            }
            await delay(125);
            attempts++;
        }

        if (!loader) {
            sendLog("[Loading] Loader did not appear within 1 seconds. Assuming loaded.");
            return;
        }

        sendLog("[Loading] Loader found. Waiting for it to disappear...");

        // Phase 2: Wait for loader to disappear (max 60 seconds)
        let waitCount = 0;
        while (waitCount < 120) { // 120 * 250ms = 60 seconds
            loader = findLoader();
            if (!loader) {
                sendLog("[Loading] Loader disappeared. Proceeding.");
                return;
            }
            await delay(250);
            waitCount++;
        }

        sendLog("[Loading] Timed out waiting for loader to disappear.");
    }

    function findLoader() {
        // Check main document
        let loader = document.querySelector('.ers_progress_content');
        if (loader && isVisible(loader)) return loader;

        // Check iframes
        const iframes = Array.from(document.querySelectorAll('iframe'));
        for (const iframe of iframes) {
            try {
                const doc = iframe.contentDocument;
                if (doc) {
                    loader = doc.querySelector('.ers_progress_content');
                    if (loader && isVisible(loader)) return loader;
                }
            } catch (e) {
                // Ignore cross-origin errors
            }
        }
        return null;
    }

    function findCombobox(labelPartial) {
        const all = Array.from(document.querySelectorAll('[role="combobox"]'));
        return all.find(c => {
            const l = c.getAttribute('aria-label') || "";
            return l.includes(labelPartial);
        });
    }

    function isVisible(elem) {
        if (!elem) return false;
        return !!(elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length);
    }
}
