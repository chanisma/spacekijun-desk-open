'use strict';
const paths = {
  desk:'<rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 8h6M9 12h6M9 16h3"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m4 7 8 6 8-6"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a4 4 0 0 1 3 4v2"/>',
  settings:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor" stroke="none"/><circle cx="16" cy="17" r="3" fill="currentColor" stroke="none"/>',
  monitor:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
  external:'<path d="M14 3h7v7M21 3 11 13M10 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  building:'<path d="M5 21V5l7-3 7 3v16M3 21h18M9 7h1M14 7h1M9 11h1M14 11h1M10 21v-6h4v6"/>',
  key:'<circle cx="8" cy="8" r="5"/><path d="m12 12 9 9m-3-3 3-3m-6 0 3-3"/>',
  link:'<path d="m10 13 4-4M8 15l-2 2a3.5 3.5 0 0 0 5 5l4-4a3.5 3.5 0 0 0 0-5M16 9l2-2a3.5 3.5 0 0 0-5-5L9 6a3.5 3.5 0 0 0 0 5" transform="translate(0 -1)"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5M5.5 7a7 7 0 0 1 12-2l2.5 3M4 16l2.5 3a7 7 0 0 0 12-2"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  chevron:'<path d="m8 10 4 4 4-4"/>',
  note:'<path d="M5 3h14a2 2 0 0 1 2 2v9l-7 7H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 21v-5a2 2 0 0 1 2-2h5M7 8h10M7 12h6"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 11h18M7 15h2M13 15h2"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.desk}</svg>`;
document.querySelectorAll('[data-icon]').forEach(el => {el.innerHTML = icon(el.dataset.icon);});
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let ready = false, state = {}, messages = [], people = [], currentPage = 'home', polling = false, optionsLoaded = false, coolmsgShown = '', certName = '', toastTimer;
let soloTitle = '';       // 대시보드 카드 하나만 띄운 창의 제목 (deskSolo)
const loaded = new Set();
const guideDialog = $('guide-dialog');
$('open-guide').addEventListener('click', () => {
  $('guide-frame').src = 'guide/index.html';
  guideDialog.showModal();
});
const closeGuide = () => {
  guideDialog.close();
  $('guide-frame').src = 'about:blank';
  $('open-guide').focus();
};
$('close-guide').addEventListener('click', closeGuide);
guideDialog.addEventListener('cancel', event => {event.preventDefault(); closeGuide();});
window.addEventListener('message', event => {
  if (event.source === $('guide-frame').contentWindow && (event.origin === location.origin || (location.protocol === 'file:' && event.origin === 'null')) && event.data?.type === 'desk-guide-close') closeGuide();
});

function toast(message, error=false) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').classList.toggle('error', error);
  $('toast').hidden = false;
  toastTimer = setTimeout(() => {$('toast').hidden = true;}, error ? 7000 : 4000);
}
async function api(action, payload={}) {
  if (!ready) throw new Error('데스크에 연결 중입니다. 잠시 후 다시 시도해 주세요.');
  const result = await window.pywebview.api.call(action, payload);
  if (!result.ok) throw new Error(result.error || '작업을 완료하지 못했습니다.');
  return result.data;
}
async function perform(button, fn) {
  if (button?.disabled) return;
  if (button) {button.disabled = true; button.setAttribute('aria-busy','true');}
  try {return await fn();}
  catch (error) {toast(error.message, true);}
  finally {if (button) {button.disabled = false; button.removeAttribute('aria-busy');} await refreshState();}
}
function navigate(page) {
  if (!['home','inbox','notes','roster','settings'].includes(page)) return;
  currentPage = page;
  document.querySelectorAll('.page').forEach(el => {el.hidden = el.id !== `page-${page}`;});
  document.querySelectorAll('.nav').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
    if (el.dataset.page === page) el.setAttribute('aria-current','page');
    else el.removeAttribute('aria-current');
  });
  $('breadcrumb').textContent = soloTitle || {home:'업무 홈',inbox:'쪽지함',notes:'스티커 메모',roster:'교직원 명부',settings:'연결 및 설정'}[page];
  // 메모는 웹이나 메모 창에서 바뀌므로 들어올 때마다 새로 읽는다
  if (ready && page === 'notes') loadNotes();
  if (ready && !loaded.has(page)) {
    if (page === 'inbox') loadInbox();
    if (page === 'roster') loadRoster();
    if (page === 'settings') loadCredentialSettings();
  }
  if (ready && page === 'settings') {
    loadDockPicks();                // 독에서 바뀌었을 수 있어 들어올 때마다 새로
    loadDockHotkey();
    loadUpdate();
  }
}
function fillPasswordLogin(formId, prefix, badgeId, savedId, saved) {
  const form = $(formId);
  form.elements[prefix + '_id'].value = savedId || '';
  form.elements[prefix + '_password'].value = '';
  form.elements[prefix + '_password'].required = !saved;
  form.elements[prefix + '_password'].placeholder = saved ? '변경할 때만 입력' : '비밀번호 입력';
  $(badgeId).textContent = saved ? '저장됨' : '미등록';
  $(badgeId).classList.toggle('on', !!saved);
}

async function loadCredentialSettings() {
  loaded.add('settings');
  const form = $('credentials-form');
  const fields = [...form.querySelectorAll('input, button'),
                  ...$('riro-form').querySelectorAll('input, button'),
                  ...$('aiep-form').querySelectorAll('input, button'),
                  ...$('jbstudy-form').querySelectorAll('input, button')];
  fields.forEach(el => {el.disabled = true;});
  try {
    const settings = await api('credential_settings');
    form.elements.user.value = settings.user || '';
    form.elements.cert_name.value = settings.cert_name || '';
    certName = (settings.cert_name || '').trim();     // 나이스·업무포털에 등록한 이름
    form.elements.password.value = '';
    form.elements.password.required = !settings.has_password;
    form.elements.password.placeholder = settings.has_password ? '변경할 때만 입력' : '암호 입력';
    $('credential-badge').textContent = settings.has_password ? '저장됨' : '미등록';
    $('credential-badge').classList.toggle('on', !!settings.has_password);
    // 리로스쿨은 인증서를 쓰지 않아 칸이 따로다. 비밀번호는 받아 오지 않고 있는지만 표시한다.
    fillPasswordLogin('riro-form', 'riro', 'riro-badge', settings.riro_id, settings.has_riro);
    fillPasswordLogin('aiep-form', 'aiep', 'aiep-badge', settings.aiep_id, settings.has_aiep);
    fillPasswordLogin('jbstudy-form', 'jbstudy', 'jbstudy-badge', settings.jbstudy_id, settings.has_jbstudy);
  } catch (error) {loaded.delete('settings'); toast(error.message, true);}
  finally {fields.forEach(el => {el.disabled = false;});}
}

document.querySelectorAll('[data-page]').forEach(el => el.addEventListener('click', () => navigate(el.dataset.page)));
document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => perform(button, async () => {
  if (button.dataset.action === 'portal') {
    button.querySelector('small').textContent = '실행 요청 중…';
    toast('자동 로그인 창을 준비하고 있습니다.');
  }
  toast(await api(button.dataset.action, {target:button.dataset.target, route:button.dataset.route}));
})));

async function refreshState() {
  if (!ready || polling) return;
  polling = true;
  try {
    state = await api('state');
    window.dispatchEvent(new Event('desk-state'));
    document.querySelectorAll('[data-action="portal"]').forEach(button => {
      const target = button.dataset.target;
      const stage = state.portal_status?.[target];
      button.querySelector('small').textContent = stage || {neis:'교육행정 업무시스템', eduptl:'전자결재 · 학교 행정', klef:'인증서 자동 로그인'}[target];
      const running = (state.portals || []).includes(target);
      button.disabled = running || button.getAttribute('aria-busy') === 'true';
    });
    $('side-dot').classList.add('on');
    $('side-status').textContent = state.watching ? '쪽지 감시 중' : '데스크 연결됨';
    $('home-watch').textContent = state.watch_error ? '활동 기록에서 오류를 확인해 주세요.' : state.watching ? '새 쪽지를 확인하고 있습니다.' : state.user ? '자동 감시를 준비하고 있습니다.' : '계정을 연결하면 자동으로 감시합니다.';
    $('watch-badge').textContent = state.watch_error ? '확인 필요' : state.watching ? '감시 중' : '대기';
    $('watch-badge').classList.toggle('on', !!state.watching);
    $('home-auth').textContent = state.user || '계정을 연결해 주세요.';
    $('settings-auth').textContent = state.user ? `${state.user} · 로그인됨` : '알림과 답장을 사용하려면 계정을 연결해 주세요.';
    $('auth-toggle').textContent = state.auth_pending ? '로그인 진행 중…' : state.user ? '로그아웃' : '구글 로그인';
    $('auth-toggle').disabled = !!state.auth_pending;
    $('watch-status').textContent = state.watching ? '자동 감시 중' : state.user ? '감시 준비 중' : '계정 연결 대기';
    $('watch-status').classList.toggle('on', !!state.watching);
    if (!optionsLoaded) {$('summary').checked = state.summary; $('include-body').checked = state.body; optionsLoaded = true;}
    if (!$('windows-startup').disabled) $('windows-startup').checked = !!state.startup;
    $('credential-badge').textContent = state.credentials ? '저장됨' : '미등록';
    $('credential-badge').classList.toggle('on', !!state.credentials);
    $('credential-title').textContent = state.credentials ? '자동 로그인 준비 완료' : '처음 사용하시나요?';
    $('credential-help').textContent = state.credentials ? '저장된 인증서로 나이스와 업무포털에 로그인하세요.' : '설정에서 인증서 정보를 저장하면 자동 로그인할 수 있어요.';
    renderCoolmsg(state.coolmsg || {});
    const logs = state.logs || [];
    $('last-log').textContent = logs.at(-1)?.text || '준비되었습니다.';
    $('logs').innerHTML = logs.slice().reverse().map(log => `<li><time>${escapeHTML(log.time)}</time><span>${escapeHTML(log.text)}</span></li>`).join('');
  } catch (error) {
    $('side-status').textContent = '연결 확인 필요';
    $('side-dot').classList.remove('on');
    $('last-log').textContent = error.message;
  } finally {polling = false;}
}
function renderCoolmsg(info) {
  const select = $('coolmsg-account'), accounts = info.accounts || [];
  // 목록·설정이 그대로면 손대지 않는다 — 2초마다 도는 갱신이 고르던 값을 되돌리면 안 된다.
  const shape = accounts.join('') + '|' + (info.fixed || '');
  if (shape !== coolmsgShown) {
    coolmsgShown = shape;
    select.innerHTML = ['<option value="">자동 (최근 사용)</option>']
      .concat(accounts.map(name => `<option value="${escapeHTML(name)}">${escapeHTML(name)}</option>`)).join('');
    select.value = info.fixed || '';
  }
  $('coolmsg-badge').textContent = info.ok === false ? '확인 필요' : (info.account || '확인 중');
  $('coolmsg-badge').classList.toggle('on', info.ok !== false && !info.warn);
  const help = info.ok === false ? (info.why || '쪽지 파일을 찾지 못했습니다.')
    : info.warn ? info.warn
    : (!info.fixed && certName && accounts.includes(certName) && certName !== info.account)
      ? `인증서에 등록한 이름 '${certName}' 계정의 쪽지도 이 PC에 있습니다. 그쪽이 맞다면 직접 골라 주세요.`
    : `지금은 '${info.account || '-'}' 계정의 쪽지를 ${info.source || ''} 읽고 있습니다.`;
  $('coolmsg-help').textContent = help;
}
function empty(title, description, name='mail') {
  return `<div class="empty">${icon(name)}<strong>${escapeHTML(title)}</strong>${escapeHTML(description)}</div>`;
}
async function loadInbox() {
  await perform($('refresh-inbox'), async () => {
    $('messages').innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
    $('detail-title').textContent = '쪽지를 선택해 주세요';
    $('detail-meta').textContent = '';
    $('detail-body').textContent = '목록에서 쪽지를 선택하면 전체 내용을 확인할 수 있습니다.';
    try {messages = await api('inbox');}
    catch (error) {$('messages').innerHTML = empty('쪽지를 불러오지 못했습니다.', '연결 상태를 확인한 후 새로고침해 주세요.'); throw error;}
    loaded.add('inbox');
    $('inbox-count').textContent = `${messages.length}건`;
    $('nav-count').textContent = messages.length;
    $('nav-count').hidden = !messages.length;
    const who = state.coolmsg?.account;
    $('inbox-note').textContent = (who ? `${who} 계정 · ` : '') + (state.user ? '최근 60건' : '답장은 계정 연결 후 표시됩니다.');
    $('messages').innerHTML = messages.length ? messages.map((row,index) => `<button class="message" data-index="${index}" aria-pressed="false"><span class="message-avatar">${icon(row.kind === '답장' ? 'arrow' : 'mail')}</span><div><strong>${escapeHTML(row.who)}</strong><span class="badge">${escapeHTML(row.kind)}${row.status ? ' · '+escapeHTML(row.status) : ''}</span><p>${escapeHTML(row.body)}</p></div><time>${escapeHTML(row.time)}</time></button>`).join('') : empty('아직 표시할 쪽지가 없어요', '쿨메신저 연결 상태를 확인한 뒤 새로고침해 주세요.');
  });
}
$('refresh-inbox').addEventListener('click', loadInbox);
$('messages').addEventListener('click', event => {
  const button = event.target.closest('[data-index]');
  if (!button) return;
  const row = messages[Number(button.dataset.index)];
  document.querySelectorAll('.message').forEach(el => {el.classList.toggle('selected', el === button); el.setAttribute('aria-pressed', String(el === button));});
  $('detail-title').textContent = row.who;
  $('detail-meta').textContent = `${row.kind} · ${row.when} ${row.status || ''}`;
  $('detail-body').textContent = row.body;
});
let notes = [];
function renderNotes() {
  const query = $('note-search').value.trim().toLocaleLowerCase();
  const rows = notes.filter(row => (row.content || '').toLocaleLowerCase().includes(query));
  $('note-count').textContent = `${rows.length}개`;
  $('notes').innerHTML = rows.length ? rows.map(row => `<button class="note-card" data-note="${escapeHTML(row.id)}" data-color="${escapeHTML(row.color)}"><p class="${row.content?.trim() ? '' : 'blank'}">${escapeHTML(row.content?.trim() || '빈 메모')}</p><time>${escapeHTML(new Date(row.updated_at).toLocaleString('ko-KR', {month:'numeric', day:'numeric', hour:'numeric', minute:'2-digit'}))}</time></button>`).join('')
    : empty(query ? '검색 결과가 없습니다.' : '아직 메모가 없어요', query ? '다른 단어로 검색해 주세요.' : '‘새 메모’를 누르면 바탕화면에 메모 창이 열립니다.', 'note');
  // CSP 가 style 속성을 막는다 — 색은 스크립트로 칠한다
  document.querySelectorAll('.note-card').forEach(el => {el.style.background = /^#[0-9a-f]{6}$/i.test(el.dataset.color) ? el.dataset.color : '#fff176';});
}
async function loadNotes() {
  if (!state.user) {
    notes = [];
    $('note-count').textContent = '';
    $('notes').innerHTML = empty('SPACEKIJUN 계정을 연결해 주세요', '메모는 계정의 협업노트에 저장됩니다. 설정에서 로그인한 뒤 사용할 수 있습니다.', 'note');
    return;
  }
  await perform($('refresh-notes'), async () => {
    try {notes = await api('sticky_list');}
    catch (error) {$('notes').innerHTML = empty('메모를 불러오지 못했습니다.', '연결 상태를 확인한 후 새로고침해 주세요.', 'note'); throw error;}
    renderNotes();
  });
}
$('refresh-notes').addEventListener('click', loadNotes);
$('note-search').addEventListener('input', renderNotes);
$('new-note').addEventListener('click', event => perform(event.currentTarget, async () => {
  await api('sticky_create', {});
  await loadNotes();
}));
$('notes').addEventListener('click', event => {
  const card = event.target.closest('[data-note]');
  if (card) perform(null, async () => {await api('sticky_open', {id: card.dataset.note});});
});
window.addEventListener('focus', () => {if (currentPage === 'notes') loadNotes();});
window.deskNavigate = navigate;

// ── 독 아이콘 (설정) ─────────────────────────────────────
// 독에 보일 아이콘을 켜고 끈다. 목록·그림은 독과 같은 dock-items.js (2026-10-12 요청).
async function loadDockPicks() {
  const box = $('dock-picks');
  if (!box || !window.DOCK_GROUPS) return;
  let data;
  try {data = await api('dock_items');}
  catch (error) {box.innerHTML = ''; $('dock-badge').textContent = '확인 실패'; return;}
  const hidden = new Set(data.hidden);
  box.innerHTML = window.DOCK_GROUPS.map(group => `<div class="dock-group"><h3>${escapeHTML(group.name)}</h3><div class="dock-row">`
    // 설정 아이콘은 숨길 수 없다 — 숨기면 다시 켤 길이 없다 (desktop.py DOCK_ALWAYS)
    + group.items.map(item => `<label class="dock-pick"><input type="checkbox" data-dock="${escapeHTML(item.id)}"${hidden.has(item.id) ? '' : ' checked'}${item.id === 'settings' ? ' disabled title="설정은 늘 독에 둡니다"' : ''}>`
      + `<span class="dock-mini tone-${escapeHTML(item.tone)}">${window.dockFace(item)}</span><span class="dock-name">${escapeHTML(item.label)}</span></label>`).join('')
    + '</div></div>').join('');
  const now = new Date();
  box.querySelectorAll('.cal').forEach(cal => {
    cal.querySelector('small').textContent = new Intl.DateTimeFormat('ko-KR', {weekday: 'short'}).format(now);
    cal.querySelector('b').textContent = now.getDate();
  });
  paintDockBadge(data.dock);
}
async function loadDockHotkey() {
  try {
    const data = await api('dock_hotkey');
    $('dock-hotkey').innerHTML = data.choices.map(choice =>
      `<option value="${escapeHTML(choice.key)}"${choice.key === data.combo ? ' selected' : ''}>${escapeHTML(choice.label)}</option>`).join('');
    paintHotkeyNote(data.combo, data.active);
  } catch {/* 데스크 밖에서 연 화면 */}
}
function paintHotkeyNote(combo, active) {
  const note = $('dock-hotkey-note');
  note.classList.toggle('error', combo !== 'off' && !active);
  note.textContent = combo === 'off' ? '단축키를 쓰지 않습니다. 트레이 메뉴의 ‘독 앞으로 가져오기’로 부를 수 있습니다.'
    : active ? '다른 창에 가려진 독을 어디서든 앞으로 부릅니다. 독이 꺼져 있으면 켭니다.'
    : '다른 프로그램이 이 조합을 쓰고 있어 켜지 못했습니다. 다른 조합을 골라 주세요.';
}
$('dock-hotkey').addEventListener('change', async event => {
  const combo = event.target.value;
  try {toast(await api('dock_hotkey_save', {combo})); paintHotkeyNote(combo, true);}
  catch (error) {toast(error.message, true); paintHotkeyNote(combo, false);}
});
function paintDockBadge(dockOn) {
  const all = $('dock-picks').querySelectorAll('input[data-dock]');
  const shown = [...all].filter(input => input.checked).length;
  $('dock-badge').textContent = `${shown} / ${all.length}개 표시`;
  $('dock-badge').classList.toggle('on', shown > 0);
  if (dockOn === false) $('dock-help').textContent = '독이 꺼져 있습니다. 트레이 메뉴의 ‘독 표시’로 켜면 여기서 고른 대로 보입니다.';
}
$('dock-picks').addEventListener('change', async event => {
  const input = event.target.closest('input[data-dock]');
  if (!input) return;
  const all = [...$('dock-picks').querySelectorAll('input[data-dock]')];
  if (!all.some(box => box.checked)) {
    input.checked = true;           // 마지막 하나는 끌 수 없다 — 빈 독이 되지 않게
    toast('아이콘을 적어도 하나는 남겨 주세요.', true);
    return;
  }
  const hidden = all.filter(box => !box.checked).map(box => box.dataset.dock);
  try {
    toast(await api('dock_items_save', {hidden, total: all.length}));
    paintDockBadge();
  } catch (error) {
    input.checked = !input.checked;
    toast(error.message, true);
  }
});
// 독에서 연 창 — 옆 메뉴 없이 그 화면 하나만 보인다 (desktop.py `_open_page`)
// 'card:today' 처럼 부르면 업무 홈 대시보드의 그 카드 하나만 보인다
window.deskSolo = page => {
  document.body.classList.add('solo');
  const card = /^card:(today|week|tasks|notices|notifications)$/.exec(page);
  if (!card) {navigate(page); return;}
  document.body.classList.add('solo-card');
  const article = $(`dash-${card[1]}`).closest('article');
  article.classList.add('solo-target');
  soloTitle = article.querySelector('h3').firstChild.textContent.trim();
  navigate('home');
};
function renderRoster() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const rows = people.filter(row => `${row.display} ${row.note} ${row.text || ''}`.toLocaleLowerCase().includes(query));
  $('roster-count').textContent = `${rows.length}명`;
  $('roster-rows').innerHTML = rows.map(row => `<tr><td>${escapeHTML(row.display)}</td><td>${escapeHTML(row.note)}</td></tr>`).join('');
  $('roster-empty').hidden = !!rows.length;
  $('roster-empty').textContent = query ? '검색 결과가 없습니다. 다른 이름으로 검색해 주세요.' : '명부가 비어 있습니다. 조직도 새로 읽기로 교직원을 불러오세요.';
}
async function loadRoster(sync=false) {
  await perform($('sync-roster'), async () => {
    people = await api(sync ? 'sync_roster' : 'roster');
    loaded.add('roster'); renderRoster();
    if (sync) toast(`교직원 ${people.length}명을 불러왔습니다.`);
  });
}
$('search').addEventListener('input', renderRoster);
$('sync-roster').addEventListener('click', () => loadRoster(true));
$('alias-form').addEventListener('submit', event => {
  event.preventDefault();
  perform(event.submitter, async () => {toast(await api('alias', Object.fromEntries(new FormData(event.target)))); event.target.reset();});
});
// 아이디·비밀번호로 들어가는 서비스는 다루는 방법이 같다. 한 함수로 묶는다.
function wirePasswordLogin(formId, action, badgeId, passwordField) {
  $(formId).addEventListener('submit', event => {
    event.preventDefault();
    perform(event.submitter, async () => {
      toast(await api(action, Object.fromEntries(new FormData(event.target))));
      const pw = event.target.elements[passwordField];
      pw.value = ''; pw.required = false; pw.placeholder = '변경할 때만 입력';
      $(badgeId).textContent = '저장됨';
      $(badgeId).classList.add('on');
    });
  });
}
// 연결 해제 — 저장된 로그인 정보를 지운다. 되돌릴 수 없으니 한 번 묻는다.
const DISCONNECT_LABEL = {cert: '인증서', riro: '리로스쿨', aiep: '전북 AIEP', jbstudy: '연수포털'};
document.querySelectorAll('[data-disconnect]').forEach(button => {
  button.addEventListener('click', () => {
    const target = button.dataset.disconnect;
    const label = DISCONNECT_LABEL[target] || target;
    const extra = target === 'cert' ? '' : '\n브라우저에 남은 로그인도 함께 지웁니다.';
    if (!window.confirm(`${label} 연결을 해제할까요?\n` +
        `저장된 아이디와 비밀번호를 이 PC에서 지웁니다.${extra}`)) return;
    perform(button, async () => {
      toast(await api('disconnect', {target}));
      loaded.delete('settings');
      await loadCredentialSettings();
    });
  });
});

wirePasswordLogin('riro-form', 'save_riro', 'riro-badge', 'riro_password');
wirePasswordLogin('aiep-form', 'save_aiep', 'aiep-badge', 'aiep_password');
wirePasswordLogin('jbstudy-form', 'save_jbstudy', 'jbstudy-badge', 'jbstudy_password');

$('credentials-form').addEventListener('submit', event => {
  event.preventDefault();
  perform(event.submitter, async () => {toast(await api('save_credentials', Object.fromEntries(new FormData(event.target)))); event.target.elements.password.value = ''; event.target.elements.password.required = false; event.target.elements.password.placeholder = '변경할 때만 입력';});
});
$('coolmsg-form').addEventListener('submit', event => {
  event.preventDefault();
  perform(event.submitter, async () => {
    toast(await api('coolmsg_account', {account: $('coolmsg-account').value}));
    coolmsgShown = ''; loaded.delete('inbox');
    await refreshState();
    if (currentPage === 'inbox') await loadInbox();
  });
});
// ── 프로그램 업데이트 (손으로) ─────────────────────────────
// 확인을 누르면 데스크가 뒤에서 확인·받기를 하고(update_check), 여기서는 끝날 때까지 상태를 다시 묻는다.
let updateTimer = 0;
function renderUpdate(info) {
  $('update-version').textContent = `현재 ${info.version}`;
  $('update-version').classList.toggle('on', !!info.ready);
  if (info.ready) $('update-version').textContent = `새 판 ${info.ready}`;
  $('update-note').textContent = info.ready ? `새 판 ${info.ready} 을 받아 두었습니다. «지금 업데이트»를 누르면 바로 바꿉니다.`
    : info.note || '새 판은 저절로 받아 두었다가 쉬는 틈에 바꿉니다. 지금 바로 확인하고 바꿀 수도 있습니다.';
  $('update-note').classList.toggle('error', !!info.failed);
  $('update-check').disabled = !info.available || info.checking;
  $('update-check').textContent = info.checking ? '확인하는 중…' : '업데이트 확인';
  $('update-check').hidden = !!info.ready;
  $('update-apply').hidden = !info.ready;
  $('update-apply').disabled = !info.available;
}
async function loadUpdate() {
  clearTimeout(updateTimer);
  try {
    const info = await api('update_status');
    renderUpdate(info);
    if (info.checking) updateTimer = setTimeout(loadUpdate, 1000);
  } catch (error) {$('update-note').textContent = error.message;}
}
$('update-check').addEventListener('click', async () => {
  try {renderUpdate(await api('update_check')); loadUpdate();}
  catch (error) {toast(error.message, true);}
});
$('update-apply').addEventListener('click', async event => {
  const button = event.currentTarget;
  const info = await api('update_status').catch(() => ({}));
  const warn = info.busy ? `${info.busy}. 데스크가 다시 켜지면서 닫힙니다.\n\n` : '';
  if (!window.confirm(`${warn}새 판 ${info.ready || ''} 으로 바꾸고 데스크를 다시 켤까요?`)) return;
  button.disabled = true;
  try {toast(await api('update_apply', {force: true})); button.textContent = '다시 켜는 중…';}
  catch (error) {toast(error.message, true); button.disabled = false;}
});

$('windows-startup').addEventListener('change', async event => {
  const control = event.target;
  const enabled = control.checked;
  control.disabled = true;
  try {toast(await api('startup', {enabled}));}
  catch (error) {control.checked = !!state.startup; toast(error.message, true);}
  finally {control.disabled = false; await refreshState();}
});
for (const id of ['summary', 'include-body']) {
  $(id).addEventListener('change', async () => {
    const summary = $('summary').checked, body = $('include-body').checked;
    $('summary').disabled = $('include-body').disabled = true;
    try {toast(await api('options', {summary, body}));}
    catch (error) {toast(error.message, true); $('summary').checked = state.summary; $('include-body').checked = state.body;}
    finally {$('summary').disabled = $('include-body').disabled = false; await refreshState();}
  });
}
$('auth-toggle').addEventListener('click', event => perform(event.currentTarget, async () => {
  toast(await api('auth', {logout:!!state.user})); loaded.delete('inbox');
}));
$('prepare-cm').addEventListener('click', event => perform(event.currentTarget, async () => {
  $('cm-status').textContent = '쿨메신저 연결을 준비하고 있습니다…';
  try {
    let result = await api('prepare_cm');
    if (result.needs_restart) {
      $('cm-status').textContent = result.message;
      if (!window.confirm(result.message + '\n\n저장하지 않은 내용은 사라질 수 있습니다. 저장을 마쳤다면 확인을 눌러 다시 실행해 주세요.')) return;
      result = await api('prepare_cm', {restart:true});
    }
    $('cm-status').textContent = result.message;
    toast(result.message);
  } catch (error) { $('cm-status').textContent = error.message; throw error; }
}));
$('check-cm').addEventListener('click', event => perform(event.currentTarget, async () => {
  $('cm-status').textContent = '쿨메신저 연결을 확인하고 있습니다…';
  try {$('cm-status').textContent = await api('check_cm');}
  catch (error) {$('cm-status').textContent = '연결 확인에 실패했습니다. 다시 시도해 주세요.'; throw error;}
}));
$('activity-toggle').addEventListener('click', () => {
  $('logs').hidden = !$('logs').hidden;
  $('activity-toggle').setAttribute('aria-expanded', String(!$('logs').hidden));
});
window.addEventListener('pywebviewready', async () => {
  ready = true;
  await refreshState();
  navigate(currentPage);
  setInterval(refreshState, 2000);
});
setTimeout(() => {if (!ready) {$('side-status').textContent = '데스크 앱에서 열어 주세요'; $('last-log').textContent = '스페이스기전-데스크.bat로 실행하면 업무 기능이 연결됩니다.';}}, 6000);
