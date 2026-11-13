// 에듀파인 «바로보기» (2026-11-12 요청) — 문서 목록에서 SPACEKIJUN DB 에 분석 결과가 있는 문서 옆에 단추를 붙이고,
// 누르면 뷰어 프로그램(WXSClient)을 기다리지 않고 요약·판정·본문을 오버레이로 보여 준다. 보기 전용 — 에듀파인에 아무것도 쓰지 않는다.
// 데스크가 core/klef_overlay.py 로 이 파일을 에듀파인 탭에 심는다(모든 프레임). 데이터는 __deskKlefDocs/__deskKlefPoll 로만 받는다.
// 문서번호 = 목록 체크박스 input[name=docinfo] 값의 17번째 칸(klef-portal SKILL 5-10). 없으면 «학교명-번호» 모양의 칸.
(() => {
  if (window.__deskKlefStarted) return;
  if (location.hostname !== 'klef.jbe.go.kr' && !window.__deskKlefTest) return;
  window.__deskKlefStarted = true;

  const MARK = 'data-desk-klef';
  const NO_RE = /^[^\s,]+-\d{1,8}$/;
  const docs = new Map();            // key → 분석 결과
  let busy = false, again = false, timer = 0, failNote = '', failAt = 0;

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const bridge = () => typeof window.__deskKlefDocs === 'function' && typeof window.__deskKlefPoll === 'function';
  const sleep = ms => new Promise(done => setTimeout(done, ms));

  // ── 목록 읽기 ─────────────────────────────────────────────
  function readRows() {
    const rows = [];
    for (const tr of document.querySelectorAll('#tbList tbody tr, table tbody tr')) {
      if (!tr.closest('#tbList') && !tr.querySelector('input[name="docinfo"]')) continue;
      const cb = tr.querySelector('input[name="docinfo"]');
      const cells = [...tr.querySelectorAll('td')];
      if (!cells.length) continue;
      let no = cb ? (cb.value.split(',')[16] || '').trim() : '';
      if (!NO_RE.test(no)) no = (cells.map(td => td.textContent.trim()).find(t => NO_RE.test(t)) || '');
      const link = [...tr.querySelectorAll('a')].find(a => /doCallClientApp/.test(a.getAttribute('onclick') || a.getAttribute('href') || ''));
      const title = ((cb && cb.title) || (link && link.textContent) || '').replace(/\s+/g, ' ').trim();
      const key = no || (title ? 't:' + title : '');
      if (key) rows.push({tr, cells, link, no, title, key});
    }
    return rows;
  }

  // 🚨 에듀파인 목록 화면은 Prototype.js 1.6.1 을 써서 Array·String·Number·Date 에 toJSON 을 덧붙여 둔다
  //    (JSON.stringify([1]) === '"[1]"'). Playwright 바인딩은 부르는 순간 인자를 JSON.stringify 하므로 데스크가
  //    «serializedArgs is not an array» 로 받지 못해 단추가 하나도 안 붙었다(2026-11-12 실제 화면에서 확인).
  //    부르는 그 순간에만 떼었다가 바로 되돌린다 — 직렬화는 부르는 동안 동기로 끝난다.
  const TOJSON = [Array, String, Number, Date];
  function call(fn, ...args) {
    const saved = TOJSON.map(C => [C, Object.getOwnPropertyDescriptor(C.prototype, 'toJSON')]);
    saved.forEach(([C, d]) => { if (d) delete C.prototype.toJSON; });
    try { return fn(...args); } finally { saved.forEach(([C, d]) => { if (d) Object.defineProperty(C.prototype, 'toJSON', d); }); }
  }

  async function lookup(items) {
    let answer = await call(window.__deskKlefDocs, items);
    for (let i = 0; answer && answer.ticket && i < 80; i++) {
      await sleep(i < 10 ? 300 : 800);
      const next = await call(window.__deskKlefPoll, answer.ticket);
      if (!next || !next.pending) answer = next;
    }
    if (!answer || answer.error) throw new Error((answer && answer.error) || '응답 없음');
    return answer.docs || {};
  }

  async function scan() {
    if (!bridge()) return;
    if (failNote && Date.now() - failAt < 30000) return;   // 로그인 안 됨 등 — 30초는 다시 묻지 않는다
    if (busy) { again = true; return; }
    const rows = readRows().filter(r => r.tr.getAttribute(MARK) !== r.key);
    if (!rows.length) return;
    busy = true;
    try {
      const want = rows.filter(r => !docs.has(r.key)).map(r => ({no: r.no, title: r.no ? '' : r.title}));
      if (want.length) Object.entries(await lookup(want)).forEach(([key, doc]) => docs.set(key, doc));
      failNote = '';
      for (const row of rows) {
        row.tr.setAttribute(MARK, row.key);
        row.tr.querySelectorAll('desk-klef-btn').forEach(b => b.remove());
        const doc = docs.get(row.key);
        if (doc) attach(row, doc);
      }
    } catch (error) {
      failNote = error.message; failAt = Date.now();       // 다음 변화 때 다시 묻는다 — 행에 표시를 남기지 않는다
    } finally {
      busy = false;
      legend();
      if (again) { again = false; schedule(); }
    }
  }
  const schedule = () => { clearTimeout(timer); timer = setTimeout(scan, 250); };

  // ── 단추 ─────────────────────────────────────────────────
  const NATURE = {
    제출: ['#dc2626', '#fef2f2'], 추천: ['#7c3aed', '#f5f3ff'], 설문: ['#0d9488', '#f0fdfa'], 참석: ['#2563eb', '#eff6ff'],
    실시: ['#ea580c', '#fff7ed'], 지침: ['#475569', '#f1f5f9'], 기회: ['#16a34a', '#f0fdf4'], 홍보: ['#64748b', '#f8fafc'],
    무관: ['#94a3b8', '#f8fafc'], 업무: ['#2563eb', '#eff6ff'],
  };
  const tone = nature => NATURE[nature] || ['#4f46e5', '#eef2ff'];

  function dday(date) {
    if (!date) return null;
    const d = new Date(String(date).slice(0, 10) + 'T00:00:00');
    if (isNaN(d)) return null;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    return Math.round((d - today) / 86400000);
  }
  const ddayText = n => n === null ? '' : n === 0 ? 'D-DAY' : n > 0 ? `D-${n}` : '기한 지남';

  function attach(row, doc) {
    const host = document.createElement('desk-klef-btn');
    host.style.cssText = 'display:inline-block;vertical-align:middle;margin-left:6px;line-height:0;';
    const root = host.attachShadow({mode: 'open'});
    const t = doc.triage || {};
    const [fg] = tone(t.nature);
    const left = t.needs_action ? dday(t.deadline) : null;
    const urgent = left !== null && left >= 0 && left <= 7;
    root.innerHTML = `<style>
      button{all:unset;box-sizing:border-box;display:inline-flex;align-items:center;gap:5px;height:20px;padding:0 7px 0 6px;border-radius:6px;
        font:500 11px/1 'Pretendard Variable',Pretendard,'Malgun Gothic',system-ui,sans-serif;color:#334155;background:#fff;
        border:1px solid #e2e8f0;box-shadow:0 1px 2px rgba(15,23,42,.05);cursor:pointer;white-space:nowrap;transition:background .15s,border-color .15s}
      button:hover{background:#f8fafc;border-color:#cbd5e1;color:#0f172a}
      button:focus-visible{outline:2px solid #0f172a;outline-offset:1px}
      .dot{width:6px;height:6px;border-radius:50%;background:${fg}}
      .d{margin-left:1px;padding:1px 4px;border-radius:4px;background:#fff1f2;color:#be123c;font-weight:600}
      .w{margin-left:1px;padding:1px 4px;border-radius:4px;background:#eff6ff;color:#1d4ed8;font-weight:600}
    </style><button type="button" title="${esc(t.nature ? `${t.nature} · ` : '')}SPACEKIJUN 분석 결과를 바로 봅니다 (뷰어를 열지 않습니다)">`
      + `<span class="dot"></span>바로보기${urgent ? `<span class="d">${esc(ddayText(left))}</span>` : ''}`
      + `${(doc.pages || []).length ? `<span class="w" title="SPACEKIJUN 업무노트와 이어져 있습니다">업무 ${doc.pages.length}</span>` : ''}</button>`;
    root.querySelector('button').addEventListener('click', event => {
      event.preventDefault(); event.stopPropagation();
      open(row.key);
    });
    host.addEventListener('mousedown', event => event.stopPropagation());
    const place = row.link || row.cells.find(td => td.textContent.trim() === row.title) || null;
    if (place && place.tagName === 'A') place.insertAdjacentElement('afterend', host);
    else if (place) place.appendChild(host);
    else (row.cells.reduce((a, b) => (b.textContent.length > a.textContent.length ? b : a))).appendChild(host);
  }

  // ── 범례 — 목록 표 바로 위 한 줄 (2026-11-12 요청) ──────────────
  // 이 쪽에서 분석된 건수 · 이 쪽에 있는 성격별 점 색과 건수 · D-day 뜻 · 쓰는 법. 행이 없는 화면에는 띄우지 않는다.
  let legendHost = null;
  function legend() {
    const rows = readRows();
    const table = document.querySelector('#tbList') || (rows[0] && rows[0].tr.closest('table'));
    if (!rows.length || !table) { legendHost && legendHost.remove(); return; }
    const found = rows.filter(r => docs.has(r.key));
    if (!found.length && !failNote) { legendHost && legendHost.remove(); return; }
    const count = {};
    let soon = 0;
    for (const r of found) {
      const t = docs.get(r.key).triage || {};
      const n = t.nature || '미판정';
      count[n] = (count[n] || 0) + 1;
      const left = t.needs_action ? dday(t.deadline) : null;
      if (left !== null && left >= 0 && left <= 7) soon++;
    }
    const order = [...Object.keys(NATURE), '미판정'].filter(n => count[n]);
    const anchor = table.closest('.LblockListTable') || table;
    if (!legendHost || !legendHost.isConnected || legendHost.nextElementSibling !== anchor) {
      legendHost && legendHost.remove();
      legendHost = document.createElement('desk-klef-legend');
      legendHost.style.cssText = 'display:block;margin:0 0 6px;';
      legendHost.attachShadow({mode: 'open'});
      anchor.insertAdjacentElement('beforebegin', legendHost);
    }
    legendHost.shadowRoot.innerHTML = `<style>
      .bar{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;padding:7px 12px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;
        font:12px/1.4 'Pretendard Variable',Pretendard,'Malgun Gothic',system-ui,sans-serif;font-feature-settings:'tnum' on;color:#334155}
      b{font-weight:700;letter-spacing:.04em;color:#0f172a;font-size:11.5px}
      .sum{color:#64748b} .sum em{font-style:normal;font-weight:600;color:#0f172a}
      .sep{width:1px;height:14px;background:#e2e8f0}
      .item{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
      .item i{width:7px;height:7px;border-radius:50%} .item small{color:#94a3b8;font-size:11.5px}
      .d{padding:1px 4px;border-radius:4px;background:#fff1f2;color:#be123c;font-weight:600;font-size:11px}
      .how{margin-left:auto;color:#94a3b8}
      .err{color:#be123c}
    </style><div class="bar" role="note" aria-label="SPACEKIJUN 바로보기 범례"><b>SPACEKIJUN</b>`
      + (failNote && !found.length ? `<span class="err">${esc(failNote)}</span>`
        : `<span class="sum">이 쪽 ${rows.length}건 중 <em>${found.length}건</em> 분석됨</span><span class="sep"></span>`
          + order.map(n => `<span class="item"><i style="background:${n === '미판정' ? '#cbd5e1' : tone(n)[0]}"></i>${esc(n)}<small>${count[n]}</small></span>`).join('')
          + `<span class="sep"></span><span class="item"><span class="d">D-3</span>기한 7일 안${soon ? `<small>${soon}</small>` : ''}</span>`
          + '<span class="how">«바로보기»를 누르면 요약·원문 · ↑↓ 다음 문서 · Esc 닫기</span>')
      + '</div>';
  }

  // ── 오버레이 ──────────────────────────────────────────────
  // 목록은 포털 안 iframe 이다. 같은 출처면 맨 위 문서에 띄워 창 전체를 쓴다.
  const stage = (() => { try { return window.top.document.body ? window.top.document : document; } catch { return document; } })();
  let shell = null, current = null;

  // SPACEKIJUN(shadcn slate) 모양에 맞춘다 — 흰 카드·slate 테두리·작은 회색 소제목·bg-*-50/text-*-700 배지·진한 남색 주 단추 (2026-11-12)
  const CSS = `
    :host{all:initial}
    *{box-sizing:border-box}
    .back{position:fixed;inset:0;background:rgba(0,0,0,.4);opacity:0;transition:opacity .2s ease;z-index:0}
    .panel{position:fixed;top:0;right:0;bottom:0;width:min(600px,100vw);background:#fff;display:flex;flex-direction:column;
      border-left:1px solid #e2e8f0;box-shadow:0 25px 50px -12px rgba(0,0,0,.25);transform:translateX(100%);transition:transform .25s cubic-bezier(.32,.72,0,1);
      font:14px/1.6 'Pretendard Variable',Pretendard,-apple-system,'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',system-ui,sans-serif;
      font-feature-settings:'ss03' on,'tnum' on;color:#020817;z-index:1;-webkit-font-smoothing:antialiased}
    .panel:focus{outline:none}
    .on .back{opacity:1} .on .panel{transform:none}
    .top{display:flex;align-items:center;gap:4px;height:56px;padding:0 12px 0 20px;border-bottom:1px solid #e2e8f0}
    .brand{display:flex;align-items:baseline;gap:8px;flex:1;min-width:0}
    .brand b{font-size:13px;font-weight:700;letter-spacing:.04em;color:#0f172a}
    .brand span{font-size:13px;font-weight:500;color:#64748b}
    .nav{font-size:12px;color:#64748b;margin-right:6px;padding:2px 8px;border-radius:999px;background:#f1f5f9}
    .nav:empty{display:none}
    .ib{all:unset;width:32px;height:32px;border-radius:6px;display:grid;place-items:center;color:#64748b;cursor:pointer;transition:background .15s,color .15s}
    .ib:hover{background:#f1f5f9;color:#0f172a} .ib:disabled{opacity:.35;cursor:default;background:none;color:#64748b}
    .ib:focus-visible{outline:2px solid #0f172a;outline-offset:-2px}
    .ib svg{width:16px;height:16px}
    .scroll{flex:1;overflow:auto;padding:20px 24px 32px;scrollbar-width:thin;scrollbar-color:#cbd5e1 transparent}
    .chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
    .chip{display:inline-flex;align-items:center;gap:5px;height:22px;padding:0 8px;border-radius:6px;font-size:12px;font-weight:500;
      background:#f1f5f9;color:#475569;white-space:nowrap}
    .chip.outline{background:#fff;border:1px solid #e2e8f0;color:#0f172a;font-weight:600}
    .chip.outline i{width:6px;height:6px;border-radius:50%}
    .chip.rose{background:#fff1f2;color:#be123c} .chip.amber{background:#fffbeb;color:#92400e} .chip.violet{background:#f5f3ff;color:#6d28d9}
    .chip.sky{background:#f0f9ff;color:#0369a1} .chip.blue{background:#eff6ff;color:#1d4ed8} .chip.emerald{background:#ecfdf5;color:#047857}
    h1{font-size:18px;line-height:1.45;font-weight:700;margin:0 0 12px;letter-spacing:-.02em;word-break:keep-all;color:#0f172a}
    .meta{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px;color:#334155;padding:10px 12px;border-radius:8px;background:#f8fafc}
    .meta b{color:#64748b;font-weight:500;margin-right:6px}
    .card{margin-top:16px;border-radius:12px;background:#fff;border:1px solid #e2e8f0;padding:14px 16px}
    .card.ai{box-shadow:0 1px 2px rgba(15,23,42,.04)}
    .label{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px}
    .label svg{color:#4f46e5}
    .card p{margin:0;white-space:pre-wrap;word-break:keep-all;color:#1e293b}
    .foot{margin-top:8px;font-size:11.5px;color:#94a3b8}
    h2{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:600;color:#64748b;margin:24px 0 8px}
    h2::after{content:'';flex:1;height:1px;background:#f1f5f9}
    dl{display:grid;grid-template-columns:88px 1fr;gap:8px 12px;margin:0;font-size:13.5px}
    dt{color:#64748b} dd{margin:0;word-break:keep-all;color:#1e293b}
    ul{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px;font-size:13.5px;color:#334155}
    li.line{display:flex;gap:10px;align-items:baseline}
    li.line small{color:#94a3b8;font-size:12px;white-space:nowrap}
    .tags{display:flex;flex-wrap:wrap;gap:6px}
    .tag{display:inline-flex;height:28px;align-items:center;padding:0 10px;border-radius:6px;background:#fff;border:1px solid #e2e8f0;font-size:13px;font-weight:500;color:#0f172a}
    .tag small{margin-left:6px;padding:1px 5px;border-radius:4px;background:#f1f5f9;color:#64748b;font-size:11px;font-weight:500}
    .body{border-radius:8px;padding:16px 18px;font-size:14px;line-height:1.85;background:#f8fafc;border:1px solid #f1f5f9;
      word-break:keep-all;overflow-wrap:anywhere;color:#1e293b}
    .body .para{white-space:pre-wrap}
    .body .tbl{margin:10px 0;overflow-x:auto;border:1px solid #e2e8f0;border-radius:8px;background:#fff}
    .body table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.55;white-space:normal}
    .body th,.body td{padding:7px 10px;border-bottom:1px solid #f1f5f9;border-right:1px solid #f1f5f9;text-align:left;vertical-align:top;word-break:keep-all;overflow-wrap:anywhere}
    .body th:last-child,.body td:last-child{border-right:0} .body tbody tr:last-child td{border-bottom:0}
    .body th{background:#f8fafc;color:#334155;font-weight:600;font-size:12.5px}
    .plan{margin-top:12px;padding-top:12px;border-top:1px solid #f1f5f9}
    .plan ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px}
    .plan li{display:grid;grid-template-columns:84px 1fr auto;gap:10px;align-items:baseline;padding:5px 8px;border-radius:6px;font-size:13.5px;color:#1e293b}
    .plan li:hover{background:#f8fafc}
    .plan time{font-weight:600;color:#0f172a;white-space:nowrap}
    .plan .what{word-break:keep-all}
    .plan .dd{font-size:11.5px;font-weight:600;padding:1px 6px;border-radius:4px;background:#f1f5f9;color:#475569;white-space:nowrap}
    .plan .dd:empty{display:none}
    .plan .dd.rose{background:#fff1f2;color:#be123c} .plan .dd.amber{background:#fffbeb;color:#92400e}
    .plan li.past{color:#94a3b8} .plan li.past time{color:#94a3b8;font-weight:500}
    .grow{flex:1}
    .btn[hidden]{display:none}
    .btn .n{min-width:18px;height:18px;padding:0 5px;border-radius:999px;background:#0f172a;color:#fff;font-size:11px;display:inline-grid;place-items:center}
    .pages{display:flex;flex-direction:column;gap:6px}
    .page{all:unset;box-sizing:border-box;display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;cursor:pointer;transition:background .15s,border-color .15s}
    .page:hover{background:#f8fafc;border-color:#cbd5e1} .page:focus-visible{outline:2px solid #0f172a;outline-offset:1px}
    .page .k{flex-shrink:0;font-size:11px;font-weight:600;padding:2px 6px;border-radius:4px;background:#eff6ff;color:#1d4ed8}
    .page .pt{flex:1;min-width:0;display:flex;flex-direction:column}
    .page .pt b{font-size:13.5px;font-weight:600;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .page .pt small{font-size:12px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .page .go{color:#94a3b8;display:grid}
    .pick{position:absolute;inset:0;background:rgba(15,23,42,.35);display:grid;place-items:center;padding:24px;z-index:3}
    .pick[hidden]{display:none}
    .pick-box{width:100%;max-width:440px;background:#fff;border-radius:12px;border:1px solid #e2e8f0;box-shadow:0 20px 40px -12px rgba(0,0,0,.3);padding:18px}
    .pick-head{display:flex;flex-direction:column;gap:2px;margin-bottom:12px} .pick-head b{font-size:15px;color:#0f172a} .pick-head span{font-size:12.5px;color:#64748b}
    .pick-list{display:flex;flex-direction:column;gap:6px;max-height:50vh;overflow:auto}
    .pick-foot{display:flex;justify-content:flex-end;margin-top:14px}
    .toast{position:absolute;left:50%;bottom:72px;transform:translateX(-50%);background:#0f172a;color:#f8fafc;font-size:13px;padding:8px 14px;border-radius:8px;box-shadow:0 8px 20px rgba(0,0,0,.2);z-index:4;white-space:nowrap}
    .toast[hidden]{display:none}
    .card.none{border-style:dashed;text-align:center;padding:18px 16px}
    .empty{font-size:13px;color:#64748b;margin:0}
    .bottom{display:flex;gap:8px;justify-content:flex-end;padding:12px 16px;border-top:1px solid #e2e8f0;background:#fff}
    .btn{all:unset;height:36px;padding:0 16px;border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;gap:6px;transition:background .15s}
    .btn.ghost{color:#0f172a;border:1px solid #e2e8f0;background:#fff} .btn.ghost:hover{background:#f1f5f9}
    .btn.main{color:#f8fafc;background:#0f172a} .btn.main:hover{background:rgba(15,23,42,.9)}
    .btn:focus-visible{outline:2px solid #0f172a;outline-offset:2px}
    .btn:disabled{opacity:.5;cursor:default}
    kbd{font:500 11px/1 inherit;padding:2px 5px;border-radius:4px;border:1px solid #e2e8f0;background:#f8fafc;color:#64748b;margin-left:2px}
    @media (prefers-reduced-motion:reduce){.back,.panel{transition:none}}`;

  const ICON = {
    close: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
    up: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10l4-4 4 4"/></svg>',
    down: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg>',
    cal: '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="2.5" y="3.5" width="11" height="10" rx="2"/><path d="M2.5 7h11M5.5 2v3M10.5 2v3"/></svg>',
    out: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h4v4M13 3L7.5 8.5M11 9.5V12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h2.5"/></svg>',
    spark: '<svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor"><path d="M8 1l1.6 4.4L14 7l-4.4 1.6L8 13l-1.6-4.4L2 7l4.4-1.6z"/></svg>',
  };
  const OBLIGATION = {의무: 'rose', '해당 시': 'amber', 협조: 'violet', 선택: 'sky'};   // 공문 판단함과 같은 색
  const DECISION = {ignore: '무시', info: '참고만', link_work: '업무에 연결', link_task: '할 일에 연결', create_work: '새 업무', reassign: '다른 사람에게'};
  const day = v => (v ? String(v).slice(0, 10) : '');
  const WEEK = '일월화수목금토';
  const md = v => {
    const d = new Date(String(v).slice(0, 10) + 'T00:00:00');
    return isNaN(d) ? String(v || '') : `${d.getMonth() + 1}. ${d.getDate()}.(${WEEK[d.getDay()]})`;
  };

  // 원문 글 → HTML. 서버 PC 수집기(odt-doc.js)가 표를 «| 칸 | 칸 |» 줄로 남긴다 — 이어진 | 줄을 표로 그린다.
  // «| --- | --- |» 줄이 있으면 그 위가 머리줄. 칸 수가 다른 줄은 빈 칸으로 채운다. 나머지 글은 줄바꿈 그대로.
  function bodyToHtml(text) {
    const out = [], lines = String(text).replace(/\r/g, '').split('\n');
    const isRow = line => /^\s*\|.*\|\s*$/.test(line);
    const cells = line => line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
    const isRule = line => cells(line).every(c => /^:?-{2,}:?$/.test(c));
    let plain = [];
    const flush = () => { if (plain.length) out.push(`<div class="para">${esc(plain.join('\n'))}</div>`); plain = []; };
    for (let i = 0; i < lines.length;) {
      if (!isRow(lines[i])) { plain.push(lines[i]); i++; continue; }
      flush();
      const block = [];
      while (i < lines.length && isRow(lines[i])) block.push(lines[i++]);
      const ruleAt = block.findIndex(isRule);
      const head = ruleAt > 0 ? block.slice(0, ruleAt).map(cells) : [];
      const rows = block.filter((_, n) => n !== ruleAt && !(ruleAt > 0 && n < ruleAt)).map(cells);
      const width = Math.max(1, ...head.map(r => r.length), ...rows.map(r => r.length));
      const tr = (r, tag) => `<tr>${Array.from({length: width}, (_, n) => `<${tag}>${esc(r[n] ?? '')}</${tag}>`).join('')}</tr>`;
      out.push(`<div class="tbl"><table>${head.length ? `<thead>${head.map(r => tr(r, 'th')).join('')}</thead>` : ''}<tbody>${rows.map(r => tr(r, 'td')).join('')}</tbody></table></div>`);
    }
    flush();
    return out.join('');
  }

  function keysOnPage() {
    return readRows().filter(r => docs.has(r.key)).map(r => r.key);
  }

  function ensureShell() {
    if (shell && shell.isConnected) return shell;
    shell = stage.createElement('desk-klef-view');
    shell.style.cssText = 'position:fixed;inset:0;z-index:2147483646;';
    const root = shell.attachShadow({mode: 'open'});
    root.innerHTML = `<style>${CSS}</style><div class="wrap"><div class="back"></div>
      <aside class="panel" role="dialog" aria-modal="true" aria-labelledby="t" tabindex="-1">
        <div class="top"><div class="brand"><b>SPACEKIJUN</b><span>공문 바로보기</span></div>
          <span class="nav"></span>
          <button class="ib" data-go="-1" title="위 문서 (↑)">${ICON.up}</button>
          <button class="ib" data-go="1" title="아래 문서 (↓)">${ICON.down}</button>
          <button class="ib" data-close title="닫기 (Esc)">${ICON.close}</button></div>
        <div class="scroll"></div>
        <div class="bottom"><button class="btn ghost" data-close>닫기<kbd>Esc</kbd></button>
          <span class="grow"></span>
          <button class="btn ghost" data-space hidden></button>
          <button class="btn main" data-origin>에듀파인에서 원문 열기</button></div>
        <div class="pick" hidden><div class="pick-box" role="dialog" aria-modal="true" aria-labelledby="pick-t">
          <div class="pick-head"><b id="pick-t">어느 페이지를 열까요?</b><span>이 공문과 이어진 SPACEKIJUN 업무노트</span></div>
          <div class="pick-list"></div>
          <div class="pick-foot"><button class="btn ghost" data-pick-close>취소</button></div></div></div>
        <div class="toast" hidden></div>
      </aside></div>`;
    root.addEventListener('click', event => {
      const el = event.target.closest('[data-close],[data-go],[data-origin],[data-space],[data-route],[data-pick-close],.back,.pick');
      if (!el) return;
      if (el.hasAttribute('data-route')) { openPage(el.dataset.route); return; }
      if (el.hasAttribute('data-space')) { choosePage(); return; }
      if (el.hasAttribute('data-pick-close') || el.classList.contains('pick')) { if (el === event.target || el.hasAttribute('data-pick-close')) pickClose(); return; }
      if (el.classList.contains('back') || el.hasAttribute('data-close')) close();
      else if (el.hasAttribute('data-go')) step(Number(el.dataset.go));
      else if (el.hasAttribute('data-origin')) origin();
    });
    stage.body.appendChild(shell);
    return shell;
  }

  // ── 연결된 SPACEKIJUN 페이지 열기 (2026-11-12 요청) — 하나면 바로, 여럿이면 모달에서 고른다 ──
  const pickOpen = () => !!(shell && !shell.shadowRoot.querySelector('.pick').hidden);
  function pickClose() { if (shell) shell.shadowRoot.querySelector('.pick').hidden = true; }
  function choosePage() {
    const pages = (docs.get(current) || {}).pages || [];
    if (pages.length === 1) { openPage(pages[0].route); return; }
    if (!pages.length) return;
    const root = shell.shadowRoot;
    root.querySelector('.pick-list').innerHTML = pages.map(pageRow).join('');
    root.querySelector('.pick').hidden = false;
    root.querySelector('.pick-list [data-route]')?.focus();
  }
  const pageRow = p => `<button class="page" data-route="${esc(p.route)}"><span class="k">${esc(p.kind)}</span>`
    + `<span class="pt"><b>${esc(p.title)}</b>${p.parent ? `<small>${esc(p.parent)}</small>` : ''}</span><span class="go">${ICON.out}</span></button>`;
  async function openPage(route) {
    pickClose();
    if (typeof window.__deskKlefOpen !== 'function') { toastIn('데스크에서 연 에듀파인에서만 열 수 있습니다.'); return; }
    try {
      const result = await call(window.__deskKlefOpen, route);
      toastIn(result && result.ok ? 'SPACEKIJUN 창에 여는 중입니다…' : (result && result.error) || '열지 못했습니다.');
    } catch { toastIn('열지 못했습니다.'); }
  }
  function toastIn(text) {
    if (!shell) return;
    const box = shell.shadowRoot.querySelector('.toast');
    box.textContent = text; box.hidden = false;
    clearTimeout(box._t); box._t = setTimeout(() => { box.hidden = true; }, 2600);
  }

  function onKey(event) {
    if (!shell || !shell.isConnected) return;
    if (event.key === 'Escape' && pickOpen()) { event.preventDefault(); pickClose(); return; }
    if (pickOpen()) return;
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); step(event.key === 'ArrowDown' ? 1 : -1); }
  }

  function open(key) {
    const doc = docs.get(key);
    if (!doc) return;
    current = key;
    const el = ensureShell();
    paint(el.shadowRoot, doc);
    requestAnimationFrame(() => el.shadowRoot.querySelector('.wrap').classList.add('on'));
    el.shadowRoot.querySelector('.panel').focus();
    stage.addEventListener('keydown', onKey, true);
    if (stage !== document) document.addEventListener('keydown', onKey, true);
  }

  function close() {
    if (!shell) return;
    const el = shell;
    el.shadowRoot.querySelector('.wrap').classList.remove('on');
    stage.removeEventListener('keydown', onKey, true);
    document.removeEventListener('keydown', onKey, true);
    setTimeout(() => el.remove(), 180);
    shell = null;
    const row = readRows().find(r => r.key === current);
    row && row.tr.querySelector('desk-klef-btn')?.shadowRoot?.querySelector('button')?.focus();
  }

  function step(delta) {
    const keys = keysOnPage(), at = keys.indexOf(current);
    const next = keys[at + delta];
    if (next) { current = next; paint(shell.shadowRoot, docs.get(next)); }
  }

  function origin() {
    const row = readRows().find(r => r.key === current);
    if (!row || !row.link) return;
    close();
    row.link.click();                 // 에듀파인이 원래 하던 대로 뷰어를 연다
  }

  function paint(root, doc) {
    const t = doc.triage || {}, d = doc.decision, meta = doc.meta || {};
    const keys = keysOnPage(), at = keys.indexOf(current);
    root.querySelector('.nav').textContent = keys.length > 1 ? `${at + 1} / ${keys.length}` : '';
    root.querySelector('[data-go="-1"]').disabled = at <= 0;
    root.querySelector('[data-go="1"]').disabled = at < 0 || at >= keys.length - 1;
    const row = readRows().find(r => r.key === current);
    root.querySelector('[data-origin]').disabled = !(row && row.link);
    const pages = doc.pages || [];
    const space = root.querySelector('[data-space]');
    space.hidden = !pages.length;
    space.innerHTML = `${ICON.out}SPACEKIJUN에서 열기${pages.length > 1 ? ` <span class="n">${pages.length}</span>` : ''}`;
    pickClose();

    const [fg] = tone(t.nature);
    const left = dday(t.deadline);
    const chips = [
      t.nature && `<span class="chip outline"><i style="background:${fg}"></i>${esc(t.nature)}</span>`,
      t.obligation && `<span class="chip ${OBLIGATION[t.obligation] || ''}">${esc(t.obligation)}</span>`,
      t.needs_action === true && `<span class="chip">할 일 있음</span>`,
      t.deadline && `<span class="chip ${left === null || left < 0 ? '' : left <= 3 ? 'rose' : 'blue'}">기한 ${esc(day(t.deadline))}${left !== null ? ` · ${esc(ddayText(left))}` : ''}</span>`,
      d && `<span class="chip emerald">결정 · ${esc(DECISION[d.decision] || d.decision)}</span>`,
    ].filter(Boolean).join('');
    const metaLine = [
      ['발신', doc.sender], ['등록', day(doc.registered_at)], ['결재권자', doc.approver], ['문서번호', doc.doc_no], ['상태', doc.status],
    ].filter(([, v]) => v).map(([k, v]) => `<span><b>${k}</b>${esc(v)}</span>`).join('');

    const facts = [
      ['대상', t.target],
      ['의무 근거', t.obligation_why],
      ['설문 응답', t.survey_respondent && t.survey_respondent !== '해당 없음' ? t.survey_respondent : ''],
    ].filter(([, v]) => v);
    // 일정 — AI 판정이 본문에서 뽑은 날짜(신청·제출 기한, 행사일 등). 없으면 대표 기한 하나 (2026-11-12 요청: AI 요약과 함께)
    const plan = ((t.deadlines || []).filter(x => x && x.date).length ? t.deadlines.filter(x => x && x.date)
      : t.deadline ? [{date: t.deadline, what: t.needs_action ? '기한' : '날짜'}] : [])
      .slice().sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const works = t.work_candidates || [];
    // 담당 — 데이터에 담당으로 정해진 사람이 기본이다 (2026-11-12 요청).
    //   처리 결정에서 담당을 정했으면 그 사람, 아니면 문서등록대장 결재권자(= 실제 접수 담당, official-doc-triage.md).
    //   AI 의 담당 후보는 데이터에 담당이 없을 때만 보여 준다.
    const decided = (d && d.assignees || []).filter(Boolean);
    const owners = decided.length ? decided.map(name => ({name, why: '처리 결정에서 정한 담당'}))
      : doc.approver ? [{name: doc.approver, why: '문서등록대장 결재권자(접수 담당)'}] : [];
    const people = owners.length ? owners : (t.assignees || []).map(p => ({...p, ai: true}));
    const attach = (meta.붙임 && meta.붙임.length ? meta.붙임 : doc.attachments) || [];
    const parents = t.parent || [];
    const similar = meta.similar || [];

    const section = (title, html) => html ? `<h2>${title}</h2>${html}` : '';
    // 원문 — 서버 PC 가 에듀파인에서 모아 DB(official_doc.body)에 둔 본문 글. 요약 바로 밑에 접지 않고 다 보여 준다 (2026-11-12 요청)
    const bodyHtml = doc.body
      ? `<div class="body">${bodyToHtml(doc.body)}</div>`
        + '<div class="foot">에듀파인 본문에서 글만 옮긴 것입니다. 서식·표 모양·붙임 파일은 «에듀파인에서 원문 열기»로 보세요.</div>'
      : `<div class="card none"><p class="empty">${doc.body_status === 'private' ? '개인정보가 들어 있을 수 있어 원문을 저장하지 않은 공문입니다.'
        : doc.body_status === 'failed' ? '원문을 읽지 못한 공문입니다.' : '아직 원문을 모으지 않은 공문입니다 — 서버 PC 가 곧 모읍니다.'} «에듀파인에서 원문 열기»로 볼 수 있습니다.</p></div>`;

    root.querySelector('.scroll').innerHTML = `
      ${chips ? `<div class="chips">${chips}</div>` : ''}
      <h1 id="t">${esc(doc.title)}</h1>
      <div class="meta">${metaLine}</div>
      ${t.summary || plan.length ? `<div class="card ai">${t.summary ? `<div class="label">${ICON.spark}AI 요약</div><p>${esc(t.summary)}</p>` : ''}
        ${plan.length ? `<div class="plan"><div class="label">${ICON.cal}일정</div><ol>${plan.map(x => {
          const n = dday(x.date), past = n !== null && n < 0;
          return `<li class="${past ? 'past' : ''}"><time>${esc(md(x.date))}</time><span class="what">${esc(x.what || '')}</span>`
            + `<span class="dd ${n === null || past ? '' : n <= 3 ? 'rose' : n <= 7 ? 'amber' : ''}">${esc(n === null ? '' : past ? '지남' : ddayText(n))}</span></li>`;
        }).join('')}</ol></div>` : ''}
        <div class="foot">AI 1차 판정${t.confidence != null ? ` · 확신 ${Math.round(Number(t.confidence) * 100)}%` : ''}${t.at ? ` · ${esc(day(t.at))}` : ''} — 초안이니 중요한 내용은 원문으로 확인하세요.</div></div>`
        : (doc.triage ? '' : '<div class="card"><p class="empty">아직 AI 판정이 없는 공문입니다.</p></div>')}
      <h2>원문</h2>${bodyHtml}
      ${section('판정 근거', facts.length ? `<dl>${facts.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : '')}
      ${section('관련 업무 후보', works.length ? `<div class="tags">${works.map(w => `<span class="tag" title="${esc(w.why)}">${esc(w.name)}</span>`).join('')}</div>` : '')}
      ${section(owners.length ? '담당' : '담당 후보 (AI)', people.length ? `<div class="tags">${people.map(p => `<span class="tag" title="${esc(p.why)}">${esc(p.name)}${p.ai ? '' : `<small>${decided.length ? '처리 결정' : '결재권자'}</small>`}</span>`).join('')}</div>` : '')}
      ${d ? section('처리 결정', `<dl><dt>결정</dt><dd>${esc(DECISION[d.decision] || d.decision)}${d.at ? ` <small style="color:#94a3b8">${esc(day(d.at))}</small>` : ''}</dd>`
        + (d.assignees && d.assignees.length ? `<dt>담당</dt><dd>${esc(d.assignees.join(', '))}</dd>` : '')
        + (d.reason ? `<dt>이유</dt><dd>${esc(d.reason)}</dd>` : '') + '</dl>') : ''}
      ${section('업무노트', pages.length ? `<div class="pages">${pages.map(pageRow).join('')}</div>` : '')}
      ${section('붙임', attach.length ? `<ul>${attach.map(a => `<li>📎 ${esc(a)}</li>`).join('')}</ul>` : '')}
      ${section('관련 공문', parents.length || meta.관련 ? `<ul>${parents.map(p => `<li class="line"><small>${esc(p.doc_no || p.issued_no || '')}</small><span>${esc(p.title || '')}</span></li>`).join('')
        }${!parents.length && meta.관련 ? `<li>${esc(meta.관련)}</li>` : ''}</ul>` : '')}
      ${section('비슷한 지난 공문', similar.length ? `<ul>${similar.slice(0, 5).map(s => `<li class="line"><small>${esc(day(s.date))}</small><span>${esc(s.title)}${s.approver ? ` <small>· ${esc(s.approver)}</small>` : ''}</span></li>`).join('')}</ul>` : '')}`;
    root.querySelector('.scroll').scrollTop = 0;
  }

  // ── 시작 ─────────────────────────────────────────────────
  function start() {
    scan();
    new MutationObserver(records => {
      // 우리 단추가 생긴 변화는 무시한다 — 아니면 끝없이 다시 훑는다
      if (records.every(r => [...r.addedNodes, ...r.removedNodes].every(n => /^DESK-KLEF-(BTN|LEGEND)$/.test(n.nodeName)))) return;
      schedule();
    }).observe(document.documentElement, {childList: true, subtree: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
  window.__deskKlef = {scan, open, docs, status: () => ({rows: readRows().length, found: docs.size, error: failNote})};

  // ══ 품의목록 ↔ SPACEKIJUN 구매 신청 (2026-11-12 요청) ══════════════════════════════
  // 학교회계 › 품의목록은 Nexacro 화면(FADMANGECLI001M01)이라 HTML 표가 없다. 데이터는 폼의 dsMain 에서 읽고
  // (sclCnsulNo 품의번호 · sclCnsulSeq 화면의 품의번호 · sj 제목 · cnsulAmt 금액), 표시는 그리드 위에 따로 얹은 층에
  // 띄운다 — 그리드 칸 안에 넣으면 Nexacro 가 다시 그리며 지우고 누름도 가로챈다. 화면 행 ↔ 데이터 행은 «품의번호» 칸(cell_N_1)
  // 글자로 잇는다(그리드는 보이는 줄만 그리고 스크롤하면 줄을 다시 쓴다).
  // 이음 = 차수의 edufine_no(품의번호) → edufine_title(제목). 없으면 «구매 신청과 연결»에서 담당자가 차수를 한 번 고른다.
  const CNSUL_FORM = 'FADMANGECLI001M01';
  const cnsulLinks = new Map();          // 품의 key → [차수…] (빈 배열 = 이음 없음)
  let cnsulBusy = false, cnsulFail = '', cnsulFailAt = 0, cnsulLayer = null, cnsulModal = null;
  const won = n => (Number(n) || 0).toLocaleString('ko-KR') + '원';

  async function job(kind, payload) {
    if (typeof window.__deskKlefJob !== 'function') throw new Error('데스크로 연 에듀파인에서만 됩니다.');
    let answer = await call(window.__deskKlefJob, kind, payload ?? null);
    for (let i = 0; answer && answer.ticket && i < 80; i++) {
      await sleep(i < 10 ? 250 : 700);
      const next = await call(window.__deskKlefJobPoll, answer.ticket);
      if (!next || !next.pending) answer = next;
    }
    if (!answer || answer.error) throw new Error((answer && answer.error) || '응답 없음');
    return answer.result;
  }

  function cnsulForms() {
    const app = window.nexacro && nexacro.getApplication && nexacro.getApplication();
    if (!app) return [];
    const hits = [], seen = new Set();
    const visit = (f, d) => {
      if (!f || d > 9 || seen.has(f)) return; seen.add(f);
      if (f.name === CNSUL_FORM) { hits.push(f); return; }
      for (const k of Object.keys(f)) {
        let o; try { o = f[k]; } catch { continue; }
        if (!o || typeof o !== 'object') continue;
        if (o.form && o.form !== f) visit(o.form, d + 1);
        else if (/Frame/.test(o._type_name || '')) visit(o, d + 1);
      }
    };
    try { visit(app.gv_workFrame, 0); } catch {}
    for (const k of Object.keys(app)) if (/Frame/.test(k)) { try { visit(app[k].form || app[k], 0); } catch {} }
    return hits;
  }

  function cnsulRows(form) {
    const ds = form.dsMain, out = [];
    if (!ds || !ds.getRowCount) return out;
    const val = (i, c) => { let v = ds.getColumn(i, c); if (v && typeof v === 'object' && 'hi' in v) v = v.hi; return v == null ? '' : String(v); };
    for (let i = 0; i < ds.getRowCount(); i++) {
      const no = val(i, 'sclCnsulNo'), title = val(i, 'sj').replace(/\s+/g, ' ').trim();
      out.push({no, seq: val(i, 'sclCnsulSeq'), title, amount: Number(val(i, 'cnsulAmt')) || 0, date: val(i, 'cnsulDte'),
        status: val(i, 'sclExpdStsSeNm'), key: no || (title ? 't:' + title : '')});
    }
    return out.filter(r => r.key);
  }

  // dsMain 에 묶인 그리드(grdMain)의 HTML 요소 — 폼 속성이 아니라 components 로 찾는다(divWork.form.components.grdMain)
  function gridOf(form) {
    let found = null;
    const look = (o, d) => {
      if (!o || d > 4 || found) return;
      for (const k of Object.keys(o.components || {})) {
        const c = o.components[k];
        if (!c) continue;
        if (c._type_name === 'Grid' && c.binddataset === 'dsMain') { found = c; return; }
        if (c.form) look(c.form, d + 1);
      }
    };
    try { look(form, 0); } catch { return null; }
    const id = found && ((found._control_element && found._control_element.handle && found._control_element.handle.id) || found._unique_id);
    const el = id && document.getElementById(id);
    return el && el.getClientRects().length ? el : null;
  }

  async function cnsulTick() {
    if (!window.nexacro || typeof window.__deskKlefJob !== 'function') return;
    const forms = cnsulForms();
    const views = forms.map(f => {
      let picked = -1; try { picked = f.dsMain.rowposition; } catch {}
      const rows = cnsulRows(f);
      return {form: f, rows, grid: gridOf(f), picked: rows[picked] ? rows[picked].key : ''};
    }).filter(v => v.grid);
    if (!views.length) { cnsulLayer && (cnsulLayer.hidden = true); return; }
    const want = views.flatMap(v => v.rows).filter(r => !cnsulLinks.has(r.key));
    if (want.length && !cnsulBusy && !(cnsulFail && Date.now() - cnsulFailAt < 30000)) {
      cnsulBusy = true;
      try {
        const found = await job('cnsul', want.map(r => ({no: r.no, title: r.title})));
        for (const r of want) cnsulLinks.set(r.key, (found && found[r.key]) || []);
        cnsulFail = '';
      } catch (error) { cnsulFail = error.message; cnsulFailAt = Date.now(); }
      finally { cnsulBusy = false; }
    }
    paintCnsul(views);
  }

  function ensureCnsulLayer() {
    if (cnsulLayer && cnsulLayer.isConnected) return cnsulLayer;
    cnsulLayer = document.createElement('desk-klef-cnsul');
    cnsulLayer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483640;';
    const root = cnsulLayer.attachShadow({mode: 'open'});
    root.innerHTML = `<style>
      .chip{position:fixed;pointer-events:auto;display:inline-flex;align-items:center;gap:4px;height:18px;padding:0 6px;border-radius:5px;
        font:600 11px/1 'Pretendard Variable',Pretendard,'Malgun Gothic',system-ui,sans-serif;cursor:pointer;white-space:nowrap;border:1px solid transparent;
        box-shadow:0 1px 2px rgba(15,23,42,.08);transition:background .15s}
      .chip.on{background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe} .chip.on:hover{background:#dbeafe}
      .chip.off{background:#fff;color:#94a3b8;border-color:#e2e8f0;font-weight:500} .chip.off:hover{color:#334155;border-color:#cbd5e1}
      .chip.mini{width:18px;padding:0;justify-content:center;font-weight:700;font-size:12px}
      .chip svg{width:11px;height:11px}
      .sum{position:fixed;pointer-events:auto;display:flex;align-items:center;gap:8px;padding:3px 9px;border-radius:6px;background:#fff;border:1px solid #e2e8f0;
        font:12px/1.4 'Pretendard Variable',Pretendard,'Malgun Gothic',system-ui,sans-serif;color:#64748b;box-shadow:0 1px 2px rgba(15,23,42,.06)}
      .sum b{color:#0f172a;font-weight:700;letter-spacing:.04em;font-size:11px} .sum em{font-style:normal;color:#0f172a;font-weight:600}
      .sum .err{color:#be123c}
    </style><div class="sum" hidden></div><div class="chips"></div>`;
    root.addEventListener('click', event => {
      const chip = event.target.closest('.chip');
      if (chip) { event.preventDefault(); event.stopPropagation(); openCnsul(chip.dataset.key); }
    });
    root.addEventListener('mousedown', event => event.stopPropagation());
    document.body.appendChild(cnsulLayer);
    return cnsulLayer;
  }

  const cnsulRowsByKey = new Map();
  function paintCnsul(views) {
    const layer = ensureCnsulLayer(), root = layer.shadowRoot;
    layer.hidden = false;
    const chips = [];
    let total = 0, linked = 0, sumAt = null;
    for (const {grid, rows, picked} of views) {
      const bySeq = new Map(rows.map(r => [r.seq, r]));
      rows.forEach(r => { cnsulRowsByKey.set(r.key, r); total++; if ((cnsulLinks.get(r.key) || []).length) linked++; });
      const body = document.getElementById(grid.id + '.body');
      const box = (body || grid).getBoundingClientRect();
      const gbox = grid.getBoundingClientRect();
      if (!sumAt) sumAt = gbox;
      for (const rowEl of grid.querySelectorAll('[id*=".body.gridrow_"]')) {
        if (!/\.gridrow_\d+$/.test(rowEl.id)) continue;
        const n = rowEl.id.match(/gridrow_(\d+)$/)[1];
        const seqEl = document.getElementById(`${rowEl.id}.cell_${n}_1`);
        const titleEl = document.getElementById(`${rowEl.id}.cell_${n}_3`);
        const row = seqEl && bySeq.get(seqEl.textContent.trim());
        if (!row || !titleEl || !cnsulLinks.has(row.key)) continue;
        const r = titleEl.getBoundingClientRect();
        if (r.height < 6 || r.top < box.top - 1 || r.bottom > box.bottom + 1) continue;     // 스크롤로 가려진 줄
        const on = (cnsulLinks.get(row.key) || []).length > 0;
        // 이어지지 않은 품의 — 모든 줄에 작은 «+»(긴 제목을 덜 가리게), 고른 줄은 «+ 연결»로 넓게 (2026-11-12: 고른 줄에만 보이니 다른 줄은 못 잇는 줄 알았다)
        const wide = on || row.key === picked;
        chips.push(`<span class="chip ${on ? 'on' : 'off'}${wide ? '' : ' mini'}" data-key="${esc(row.key)}" title="${on ? 'SPACEKIJUN 구매 신청과 이어진 품의' : 'SPACEKIJUN 구매 신청과 잇기'}"
          style="top:${Math.round(r.top + (r.height - 18) / 2)}px;left:${Math.round(r.right - (on ? 82 : wide ? 52 : 24))}px">${on ? `${ICON.out}구매 신청` : wide ? '+ 연결' : '+'}</span>`);
      }
    }
    root.querySelector('.chips').innerHTML = chips.join('');
    const sum = root.querySelector('.sum');
    if (sumAt) {
      sum.hidden = false;
      sum.style.top = `${Math.max(0, Math.round(sumAt.top - 26))}px`;
      sum.style.left = `${Math.round(sumAt.left)}px`;            // 그리드 왼쪽 위 — 오른쪽 위는 [파일]·[수의계약배제업체] 단추 자리
      sum.innerHTML = cnsulFail ? `<b>SPACEKIJUN</b><span class="err">${esc(cnsulFail)}</span>`
        : `<b>SPACEKIJUN</b><span>구매 신청과 이어진 품의 <em>${linked}</em> / ${total} · 이어지지 않은 품의는 제목 끝 «+»로 잇기</span>`;
    } else sum.hidden = true;
  }

  // ── 품의 한 건 창 — 이어진 차수 보기·열기·끊기 / 차수 골라 잇기 ──
  function ensureCnsulModal() {
    if (cnsulModal && cnsulModal.isConnected) return cnsulModal;
    cnsulModal = document.createElement('desk-klef-cnsul-view');
    cnsulModal.style.cssText = 'position:fixed;inset:0;z-index:2147483646;';
    const root = cnsulModal.attachShadow({mode: 'open'});
    root.innerHTML = `<style>${CSS}
      .wrap{position:fixed;inset:0;display:grid;place-items:center;padding:24px}
      .box{position:relative;width:min(560px,100%);max-height:86vh;display:flex;flex-direction:column;background:#fff;border-radius:12px;border:1px solid #e2e8f0;
        box-shadow:0 25px 50px -12px rgba(0,0,0,.3);font:14px/1.6 'Pretendard Variable',Pretendard,'Malgun Gothic',system-ui,sans-serif;font-feature-settings:'tnum' on;color:#020817;z-index:1}
      .box .top{height:52px}
      .inner{flex:1;overflow:auto;padding:18px 20px 20px}
      .batch{display:flex;flex-direction:column;gap:6px;padding:12px 14px;border:1px solid #e2e8f0;border-radius:10px;background:#fff}
      .batch + .batch{margin-top:8px}
      .batch .h{display:flex;align-items:center;gap:8px} .batch .h b{font-size:14px;color:#0f172a} .batch .h .grow{flex:1}
      .batch .m{font-size:12.5px;color:#64748b} .batch .acts{display:flex;gap:6px;justify-content:flex-end;margin-top:4px}
      .btn.sm{height:30px;padding:0 12px;font-size:13px}
      .cand{all:unset;box-sizing:border-box;display:flex;flex-direction:column;gap:2px;width:100%;padding:10px 12px;border:1px solid #e2e8f0;border-radius:8px;cursor:pointer;transition:background .15s,border-color .15s}
      .cand + .cand{margin-top:6px} .cand:hover{background:#f8fafc;border-color:#cbd5e1} .cand:focus-visible{outline:2px solid #0f172a;outline-offset:1px}
      .cand[disabled]{opacity:.45;cursor:default}
      .cand .h{display:flex;align-items:center;gap:8px;font-size:13.5px} .cand .h b{font-weight:600;color:#0f172a} .cand .h .grow{flex:1}
      .cand small{font-size:12px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .same{font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px;background:#ecfdf5;color:#047857}
      .diff{font-size:11px;font-weight:600;padding:1px 6px;border-radius:4px;background:#fffbeb;color:#92400e}
      .note{font-size:12.5px;color:#64748b;margin:0 0 10px}
      .find{width:100%;box-sizing:border-box;height:34px;border:1px solid #e2e8f0;border-radius:6px;padding:0 10px;font:inherit;font-size:13px;margin-bottom:10px;outline:none}
      .find:focus{border-color:#94a3b8}
    </style><div class="wrap"><div class="back"></div><div class="box" role="dialog" aria-modal="true" aria-labelledby="ct">
      <div class="top"><div class="brand"><b>SPACEKIJUN</b><span>품의 ↔ 구매 신청</span></div><button class="ib" data-x title="닫기 (Esc)">${ICON.close}</button></div>
      <div class="inner"></div><div class="toast" hidden></div></div></div>`;
    root.querySelector('.wrap').classList.add('on');
    root.addEventListener('click', event => {
      const el = event.target.closest('[data-x],.back,[data-route],[data-unlink],[data-link],[data-relink]');
      if (!el) return;
      if (el.hasAttribute('data-x') || el.classList.contains('back')) closeCnsul();
      else if (el.hasAttribute('data-route')) { openPage(el.dataset.route); closeCnsul(); }
      else if (el.hasAttribute('data-unlink')) linkCnsul(el.dataset.unlink, true);
      else if (el.hasAttribute('data-link')) linkCnsul(el.dataset.link, false);
      else if (el.hasAttribute('data-relink')) pickBatch();
    });
    root.addEventListener('input', event => { if (event.target.matches('.find')) filterBatches(event.target.value); });
    document.addEventListener('keydown', cnsulKey, true);
    document.body.appendChild(cnsulModal);
    return cnsulModal;
  }
  function cnsulKey(event) { if (event.key === 'Escape' && cnsulModal && cnsulModal.isConnected) { event.preventDefault(); event.stopPropagation(); closeCnsul(); } }
  function closeCnsul() { document.removeEventListener('keydown', cnsulKey, true); cnsulModal && cnsulModal.remove(); cnsulModal = null; cnsulCurrent = null; }
  function cnsulToast(text) {
    const box = cnsulModal && cnsulModal.shadowRoot.querySelector('.toast'); if (!box) return;
    box.textContent = text; box.hidden = false; clearTimeout(box._t); box._t = setTimeout(() => { box.hidden = true; }, 2600);
  }

  let cnsulCurrent = null, cnsulBatches = [];
  const day8 = v => /^\d{8}$/.test(v) ? `${v.slice(0, 4)}-${v.slice(4, 6)}-${v.slice(6)}` : v;
  function cnsulHead(row) {
    return `<div class="chips"><span class="chip outline">품의 ${esc(row.seq || row.no)}</span>${row.status ? `<span class="chip">${esc(row.status)}</span>` : ''}</div>
      <h1 id="ct">${esc(row.title)}</h1><div class="meta"><span><b>품의액</b>${esc(won(row.amount))}</span><span><b>품의일</b>${esc(day8(row.date))}</span></div>`;
  }
  function openCnsul(key) {
    const row = cnsulRowsByKey.get(key); if (!row) return;
    cnsulCurrent = row;
    const linkedTo = cnsulLinks.get(key) || [];
    if (!linkedTo.length) { pickBatch(); return; }
    const root = ensureCnsulModal().shadowRoot;
    root.querySelector('.inner').innerHTML = cnsulHead(row) + '<h2>이어진 구매 신청 품의 차수</h2>' + linkedTo.map(b => {
      const gap = b.total - row.amount;
      return `<div class="batch"><div class="h"><b>${esc(b.title)}</b><span class="grow"></span><span class="chip ${b.status === 'purchased' ? 'emerald' : b.status === 'submitted' ? 'blue' : ''}">${esc(b.status_label)}</span></div>
        <div class="m">${esc(b.page_title)}</div>
        <div class="m">품목 ${b.line_count}개 · 합계 ${esc(won(b.total))} ${gap === 0 ? '<span class="same">품의액과 같음</span>' : `<span class="diff">품의액과 ${esc(won(Math.abs(gap)))} ${gap > 0 ? '많음' : '적음'}</span>`}</div>
        <div class="acts"><button class="btn ghost sm" data-unlink="${esc(b.id)}">연결 끊기</button>${b.route ? `<button class="btn main sm" data-route="${esc(b.route)}">${ICON.out}구매 신청 열기</button>` : ''}</div></div>`;
    }).join('') + '<p class="note" style="margin-top:12px">다른 차수였다면 <a href="#" data-relink>차수 다시 고르기</a></p>';
  }

  async function pickBatch() {
    const row = cnsulCurrent; if (!row) return;
    const root = ensureCnsulModal().shadowRoot;
    root.querySelector('.inner').innerHTML = cnsulHead(row) + '<h2>어느 구매 신청의 품의 차수인가요?</h2><p class="note">고르면 이 품의의 제목·품의번호를 그 차수에 적어 둡니다. 다음부터는 자동으로 이어집니다. 내가 담당자인 구매 신청만 보입니다.</p><p class="empty">차수를 불러오는 중…</p>';
    try { cnsulBatches = await job('batches'); } catch (error) { root.querySelector('.inner .empty').textContent = error.message; return; }
    const inner = root.querySelector('.inner');
    inner.querySelector('.empty').remove();
    inner.insertAdjacentHTML('beforeend', '<input class="find" placeholder="구매 신청·차수·품목 이름으로 찾기"><div class="cands"></div>');
    filterBatches('');
    inner.querySelector('.find').focus();
  }
  function filterBatches(q) {
    const row = cnsulCurrent, root = cnsulModal && cnsulModal.shadowRoot; if (!row || !root) return;
    const words = String(q || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
    const list = cnsulBatches.filter(b => !words.length || words.every(w => [b.title, b.page_title, ...b.lines].join(' ').toLowerCase().includes(w)))
      .map(b => ({b, same: b.total === row.amount, taken: !!(b.edufine_no && b.edufine_no !== row.no)}))
      .sort((x, y) => (y.same - x.same) || (x.taken - y.taken) || String(y.b.at).localeCompare(String(x.b.at)));
    root.querySelector('.cands').innerHTML = list.length ? list.map(({b, same, taken}) =>
      `<button class="cand" data-link="${esc(b.id)}" ${taken ? 'disabled title="다른 품의와 이어진 차수"' : ''}><span class="h"><b>${esc(b.title)}</b>${same ? '<span class="same">금액 같음</span>' : ''}<span class="grow"></span><span>${esc(won(b.total))}</span></span>`
      + `<small>${esc(b.page_title)} · ${esc(b.status_label)}${taken ? ' · 다른 품의와 이어짐' : ''}</small><small>${esc(b.lines.slice(0, 4).join(', '))}${b.line_count > 4 ? ` 외 ${b.line_count - 4}개` : ''}</small></button>`).join('')
      : '<p class="empty">맞는 차수가 없습니다.</p>';
  }
  async function linkCnsul(batchId, unlink) {
    const row = cnsulCurrent; if (!row) return;
    try {
      await job('link', unlink ? {batch_id: batchId, unlink: true} : {batch_id: batchId, title: row.title, no: row.no});
      cnsulLinks.delete(row.key);
      for (const [key, list] of cnsulLinks) if (list.some(b => b.id === batchId)) cnsulLinks.delete(key);   // 그 차수의 옛 이음도 다시 묻는다
      await cnsulTick();
      if (unlink) { cnsulToast('연결을 끊었습니다.'); pickBatch(); }
      else { openCnsul(row.key); cnsulToast('구매 신청 품의 차수와 이었습니다.'); }
    } catch (error) { cnsulToast(error.message); }
  }

  if (window.top === window) setInterval(() => { cnsulTick().catch(() => {}); }, 700);
  window.__deskKlefCnsul = {tick: cnsulTick, links: cnsulLinks, open: openCnsul};
})();
