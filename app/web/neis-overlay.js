/* NEIS 화면 위에 얹는 도우미 패널. `core/neis_overlay.py` 가 읽어 CDP 로 주입한다.
   설계 이유(표 기반 비동기, Shadow DOM, 재부착)는 그 모듈의 주석을 볼 것.
   index.html 은 이 파일을 부르지 않는다 — 나이스 페이지 안에서만 돈다. */
(() => {
  if (window.top !== window) return;            // 프레임 안에는 만들지 않는다
  if (window.__deskPanel) return;

  const state = { busy: false };

  const host = document.createElement('div');
  host.id = 'spacekijun-desk-panel';
  // 호스트 노드는 나이스의 light DOM 에 있어 페이지 스타일을 맞는다. 나이스는 `!important`
  // 를 자주 쓰므로(예: `div{border:4px dashed ...!important}`) 인라인 `!important` 로 막는다.
  // 인라인 `!important` 는 같은 author 규칙 중 가장 세다. 섀도 안쪽은 이와 별개로 안전하다.
  host.style.cssText = 'all:initial!important;position:fixed!important;right:20px!important;'
    + 'bottom:20px!important;z-index:2147483600!important;display:block!important;'
    + 'width:auto!important;height:auto!important;margin:0!important;padding:0!important;'
    + 'border:0!important;background:none!important;opacity:1!important;'
    + 'visibility:visible!important;transform:none!important;float:none!important';
  const root = host.attachShadow({ mode: 'open' });

  root.innerHTML = `
    <style>
      :host{all:initial}
      *{box-sizing:border-box;font-family:'Malgun Gothic',system-ui,sans-serif}
      /* .panel 과 .launcher 가 display:flex 라 브라우저 기본 [hidden] 규칙을 이긴다. */
      [hidden]{display:none!important}
      .launcher{display:flex;align-items:center;gap:8px;border:0;border-radius:999px;
        padding:11px 17px;background:#4f46e5;color:#fff;font-size:14px;font-weight:700;
        box-shadow:0 8px 22px rgba(31,41,55,.28);cursor:pointer}
      .launcher:hover{background:#4338ca}
      .panel{width:360px;height:520px;display:flex;flex-direction:column;background:#f6f7fb;
        border:1px solid #d9deea;border-radius:16px;overflow:hidden;
        box-shadow:0 18px 46px rgba(31,41,55,.3)}
      .bar{display:flex;align-items:center;justify-content:space-between;gap:10px;
        padding:11px 14px;background:#fff;border-bottom:1px solid #e8ebf2}
      .bar strong{font-size:14px;color:#1e293b}
      .bar small{display:block;color:#64748b;font-size:11px;margin-top:2px}
      .shut{border:0;background:transparent;color:#64748b;font-size:19px;line-height:1;
        cursor:pointer;padding:2px 5px}
      .shut:hover{color:#1e293b}
      .log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
      .msg{max-width:88%;padding:10px 12px;border-radius:13px;font-size:13px;line-height:1.55;
        color:#1e293b;white-space:pre-wrap;word-break:break-word}
      .bot{background:#fff;border:1px solid #e8ebf2;border-bottom-left-radius:4px;align-self:flex-start}
      .me{background:#4f46e5;color:#fff;border-bottom-right-radius:4px;align-self:flex-end}
      .warn{background:#fff7ed;border-color:#fed7aa}
      .fail{background:#fef2f2;border-color:#fecaca}
      .hint{color:#64748b;font-size:11px;margin-top:5px}
      .step{align-self:center;color:#64748b;font-size:11px}
      .options{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
      .options button{background:#eef2ff;border:1px solid #c7d2fe;color:#3730a3;
        border-radius:999px;padding:4px 10px;font-size:11px;cursor:pointer}
      .options button:hover{background:#e0e7ff}
      form{display:flex;gap:7px;padding:11px 14px;background:#fff;border-top:1px solid #e8ebf2}
      input{flex:1;min-width:0;border:1px solid #e8ebf2;border-radius:10px;padding:9px 11px;
        background:#f8fafc;font-size:13px;color:#1e293b}
      input:focus{outline:2px solid #a5b4fc;outline-offset:-1px;background:#fff}
      button.send{border:0;border-radius:10px;padding:9px 14px;background:#4f46e5;color:#fff;
        font-size:13px;font-weight:700;cursor:pointer}
      button.send:disabled{opacity:.5;cursor:default}
      button.send:hover:not(:disabled){background:#4338ca}
    </style>
    <button class="launcher">도우미</button>
    <div class="panel" hidden>
      <div class="bar">
        <div><strong>NEIS 도우미</strong><small class="status">데스크 연결 확인 중…</small></div>
        <button class="shut" title="접기">&times;</button>
      </div>
      <div class="log"></div>
      <form>
        <input placeholder="무엇을 하시겠어요?" maxlength="200">
        <button class="send" type="submit" disabled>보내기</button>
      </form>
    </div>`;

  const $ = sel => root.querySelector(sel);
  const launcher = $('.launcher'), panel = $('.panel'), log = $('.log');
  const field = $('input'), send = $('.send'), status = $('.status');

  const scroll = () => { log.scrollTop = log.scrollHeight; };
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function bubble(text, kind) {
    const node = document.createElement('div');
    node.className = 'msg ' + (kind || 'bot');
    node.textContent = text;        // 항상 글자로 — 화면 내용이 HTML 로 살아나면 안 된다
    log.append(node);
    scroll();
    return node;
  }

  function note(text) {
    const node = document.createElement('div');
    node.className = 'step';
    node.textContent = text;
    log.append(node);
    scroll();
    return node;
  }

  /* 무엇이 화면을 골랐는지. "AI 가 쓰이긴 하나" 를 눈으로 확인할 수 있어야 한다. */
  const DECIDED = {
    model: 'AI가 해석했습니다',
    name: '화면 이름을 그대로 말씀하셔서 AI 없이 찾았습니다',
    fallback: 'AI가 고르지 못해 이름으로 찾았습니다',
    offline: 'AI 키가 없어 이름으로만 찾았습니다',
  };

  /** 답 밑에 붙는 작은 설명. 어떻게 골랐는지와 무엇을 읽어 냈는지. */
  function footnote(node, data) {
    const said = DECIDED[data.source];
    const read = [data.subject && `과목 ${data.subject}`,
                  data.grade && `${data.grade}학년`,
                  data.room && `${data.room}반`].filter(Boolean).join(' · ');
    if (!said && !read) return;
    const line = document.createElement('div');
    line.className = 'hint';
    line.textContent = [said, read && `읽어 낸 조건: ${read}`].filter(Boolean).join(' · ');
    node.append(line);
  }

  /** 되물을 때 쓰는 선택지. row 는 이미 열린 화면의 수업이라 해석을 거치지 않는다. */
  function offer(node, options, kind) {
    if (!options || !options.length) return;
    const box = document.createElement('div');
    box.className = 'options';
    options.slice(0, 10).forEach(name => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = name;
      button.addEventListener('click', () => {
        if (kind === 'row') run(() => window.__deskPick(name), name);
        else run(() => window.__deskAsk(name), name);
      });
      box.append(button);
    });
    node.append(box);
    scroll();
  }

  /** 표를 받아 두고 결과가 나올 때까지 물어본다. 진행 줄은 바뀔 때마다 갈아 끼운다. */
  async function run(start, echo) {
    if (state.busy) return;
    state.busy = true;
    send.disabled = true;
    field.value = '';
    bubble(echo, 'me');
    const step = note('요청을 보내는 중…');
    try {
      const ticket = await start();
      let shown = '';
      for (let i = 0; i < 900; i++) {       // 최대 약 7분 — 첫 요청은 메뉴 수집이 있다
        const answer = await window.__deskPoll(ticket);
        const last = (answer.progress || []).slice(-1)[0];
        if (last && last !== shown) { shown = last; step.textContent = last; }
        if (answer.state === 'pending') { await sleep(500); continue; }
        step.remove();
        if (answer.state === 'error') { bubble(answer.error, 'bot fail'); return; }
        if (answer.state === 'unknown') { bubble('요청 기록을 찾지 못했습니다.', 'bot fail'); return; }
        const data = answer.data || {};
        const node = bubble(data.reply || '완료했습니다.', data.ok === false ? 'bot warn' : 'bot');
        footnote(node, data);
        offer(node, data.options, data.option_kind);
        return;
      }
      step.remove();
      bubble('응답이 너무 늦습니다. 나이스 창 상태를 확인해 주세요.', 'bot fail');
    } catch (error) {
      step.remove();
      bubble(String((error && error.message) || error), 'bot fail');
    } finally {
      state.busy = false;
      send.disabled = false;
      field.focus();
    }
  }

  $('form').addEventListener('submit', event => {
    event.preventDefault();
    const text = field.value.trim();
    if (text) run(() => window.__deskAsk(text), text);
  });

  const show = open => {
    panel.hidden = !open;
    launcher.hidden = open;
    if (open) field.focus();
  };
  launcher.addEventListener('click', () => show(true));
  $('.shut').addEventListener('click', () => show(false));
  show(false);

  const first = bubble('하려는 업무를 그대로 말씀해 주세요. 해당 화면으로 옮겨 드립니다.');
  const hint = document.createElement('div');
  hint.className = 'hint';
  hint.textContent = '예: “인공지능 기초 과목 출결해야 해”, “1학년 5반 시간표 보고 싶어”';
  first.append(hint);

  // 나이스는 화면을 통째로 다시 그리는 일이 잦아 우리 노드가 떨어져 나간다. 지켜본다.
  const attach = () => { if (!host.isConnected && document.body) document.body.append(host); };
  attach();
  const keepAlive = setInterval(attach, 2000);

  // 떼어내는 길을 열어 둔다. 이게 없으면 노드를 지워도 위 타이머가 도로 붙여 놓는다.
  // 개발 중 패널 소스를 고쳐 다시 심을 때 쓴다.
  window.__deskPanelStop = () => {
    clearInterval(keepAlive);
    host.remove();
    delete window.__deskPanel;
    delete window.__deskPanelStop;
  };

  // 다리가 걸릴 때까지 기다렸다가 준비 상태를 알린다.
  (async () => {
    for (let i = 0; i < 60 && typeof window.__deskAsk !== 'function'; i++) await sleep(500);
    const ready = typeof window.__deskAsk === 'function';
    send.disabled = !ready;
    if (!ready) { status.textContent = '데스크에 연결하지 못했습니다'; return; }
    const tell = async () => {
      let info = {};
      try { info = (await window.__deskState()) || {}; } catch { /* 아직 준비 전 */ }
      // AI 로 해석하는지, 아는 화면이 몇 개인지 늘 보이게 둔다.
      status.textContent = [info.ai === false ? 'AI 꺼짐(키 없음)' : 'AI 해석 켜짐',
                            info.screens ? `화면 ${info.screens}개` : '메뉴 읽기 전'].join(' · ');
    };
    await tell();
    setInterval(tell, 15000);
  })();

  window.__deskPanel = true;
})();
