/**
 * 쿨메신저(CEF 91) 원격 디버깅 클라이언트 — 의존성 없음(Node 22 내장 WebSocket 사용).
 *
 * Playwright의 connectOverCDP 는 CEF 91에서 실패한다
 * ("Browser.setDownloadBehavior: Browser context management is not supported").
 * 브라우저 레벨 CDP가 없으므로 **페이지 타깃 WebSocket에 직접** 붙어야 한다.
 *
 *   node cdp.js                       # 타깃 목록
 *   node cdp.js eval "location.href"  # 첫 페이지에서 JS 실행
 *   node cdp.js dom                   # 페이지 구조 요약
 *
 * 사전 조건: 앱이 --remote-debugging-port=9222 로 실행돼 있어야 한다.
 *   Stop-Process -Name CoolMessenger -Force
 *   Start-Process "C:\Program Files (x86)\CoolMessenger Gentoo\CoolMessenger.exe" -ArgumentList "--remote-debugging-port=9222"
 */
const PORT = process.env.CM_CDP_PORT || 9222;

async function targets() {
    const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
    return await r.json();
}

/** 페이지 타깃에 붙어 CDP 명령을 보낸다 */
function connect(wsUrl) {
    return new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl);
        let id = 0;
        const waiting = new Map();
        ws.addEventListener('message', ev => {
            let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
            if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); }
        });
        ws.addEventListener('error', e => reject(new Error('WS 오류: ' + (e.message || 'unknown'))));
        ws.addEventListener('open', () => resolve({
            send: (method, params = {}) => new Promise(res => {
                const mid = ++id;
                waiting.set(mid, res);
                ws.send(JSON.stringify({ id: mid, method, params }));
            }),
            close: () => ws.close()
        }));
    });
}

/** 페이지에서 JS 평가 (문자열 결과로 반환) */
async function evaluate(cdp, expr) {
    const r = await cdp.send('Runtime.evaluate', {
        expression: expr, returnByValue: true, awaitPromise: true
    });
    if (r.result && r.result.exceptionDetails) return { 오류: r.result.exceptionDetails.text };
    return r.result && r.result.result ? r.result.result.value : r;
}

async function main() {
    const cmd = process.argv[2] || 'list';
    const list = await targets();
    if (cmd === 'list') {
        console.log(`타깃 ${list.length}개`);
        list.forEach(t => console.log(` [${t.type}] ${t.title}\n   ${t.url}\n   ws: ${t.webSocketDebuggerUrl}`));
        return;
    }
    // --url=<부분문자열> 로 타깃 선택 (쪽지 작성창은 coolmsgrichtext.html)
    const want = (process.argv.find(a => a.startsWith('--url=')) || '').slice(6);
    const pages = list.filter(t => t.type === 'page');
    const page = want ? pages.find(t => (t.url + t.title).includes(want)) : pages[0];
    if (!page) return console.error('page 타깃 없음' + (want ? ` (--url=${want} 불일치)` : ''));
    const cdp = await connect(page.webSocketDebuggerUrl);

    if (cmd === 'eval') {
        console.log(JSON.stringify(await evaluate(cdp, process.argv[3] || '1+1'), null, 1));
    } else if (cmd === 'dom') {
        const info = await evaluate(cdp, `(() => ({
      url: location.href,
      title: document.title,
      본문길이: document.body ? document.body.innerText.length : 0,
      본문앞: document.body ? document.body.innerText.replace(/\\s+/g,' ').slice(0,200) : '',
      HTML크기: document.documentElement.outerHTML.length,
      스크립트: Array.from(document.querySelectorAll('script[src]')).map(s=>s.src).slice(0,10),
      jQuery: (typeof jQuery !== 'undefined') ? jQuery.fn.jquery : null,
      네이티브후보: Object.keys(window).filter(k => /cef|native|cool|bridge|host|external|invoke|msg/i.test(k)).slice(0,30),
      폼: Array.from(document.querySelectorAll('form')).map(f=>f.name||f.id).slice(0,5),
      입력: Array.from(document.querySelectorAll('input,textarea')).map(i=>i.name||i.id||i.type).slice(0,15)
    }))()`);
        console.log(JSON.stringify(info, null, 1));
    }
    cdp.close();
}

main().catch(e => { console.error('ERR:', e.message); process.exit(1); });
