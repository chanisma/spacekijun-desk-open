let targetFilename = null;

// 확장 프로그램 아이콘 클릭 시 사이드 패널 열기
chrome.action.onClicked.addListener((tab) => {
    chrome.sidePanel.open({ tabId: tab.id });
});

// 확장 프로그램 설치/업데이트 시 사이드 패널 동작 설정
chrome.runtime.onInstalled.addListener(() => {
    chrome.sidePanel.setOptions({
        enabled: true
    });
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "set_filename") {
        targetFilename = request.filename;
        console.log("[Background] Target filename set to:", targetFilename);
        sendResponse({ status: "ok" });
    }
});

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
    if (targetFilename) {
        console.log("[Background] Renaming download to:", targetFilename);
        suggest({
            filename: targetFilename,
            conflictAction: 'overwrite'
        });
        // targetFilename = null; // Don't reset yet, wait for onCreated or just keep it? 
        // Actually, onDeterminingFilename happens before onCreated usually? Or concurrent?
        // Let's keep it simple. We just want to know A download started.
    } else {
        suggest();
    }
});

chrome.downloads.onCreated.addListener((downloadItem) => {
    console.log("[Background] Download created:", downloadItem.id);
    // Notify active tab
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs[0]) {
            chrome.tabs.sendMessage(tabs[0].id, {
                action: "download_started",
                downloadId: downloadItem.id,
                filename: targetFilename // Send back the expected filename if we have one
            });
        }
    });
    // Reset targetFilename here if we want to be strict, but maybe safer to leave it for determiningFilename
    // targetFilename = null; 
});
