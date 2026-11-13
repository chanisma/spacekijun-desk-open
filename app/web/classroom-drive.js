// 스페이스기전 교실 — 선생님 구글 드라이브를 일반 폴더처럼(app/classroom.py Api.drive_*).
// 두 번 누르면(또는 Enter) 폴더는 들어가고 파일은 이 PC 의 프로그램으로 연다. 고쳐 저장하면 드라이브에 되올린다.
// 누르기 = 고르기(Ctrl 은 더하기, Shift 는 범위). 고른 것은 [열기]·[컴퓨터로 복사](2026-10-14 요청).
// 왼쪽 «이 PC 에 복사한 파일» — 지난 수업에 복사해 둔 것을 드라이브 연결 없이 바로 연다(2026-10-15 요청, api.pc_*).
'use strict';

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview && window.pywebview.api;
const ICON = {
  up: '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2.5h6.5A2.5 2.5 0 0 1 21 10v7.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5Z"/>',
  home: '<path d="M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1Z"/>',
  people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6"/>',
  pc: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  drives: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
};
const svg = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const FOLDER = 'application/vnd.google-apps.folder';
const SHORTCUT = 'application/vnd.google-apps.shortcut';
const ST = { synced: '드라이브와 같음', pending: '저장 확인 중', uploading: '올리는 중', failed: '못 올림' };

// 지금 자리: 경로(조상들) + 공유 드라이브 id
let path = [{ id: 'root', name: '내 드라이브' }];
let driveId = null;
let loading = 0;
let items = [];                 // 지금 폴더의 목록
const selected = new Set();     // 고른 id
let anchor = null;              // Shift 범위의 시작
let files = [];                 // 열어 둔 파일(state.session.files)
const PC = 'pc';
const PC_NAME = '이 PC 에 복사한 파일';
const inPc = () => path[0].id === PC;    // 지금 «이 PC» 를 보는 중

function kindOf(item) {
  const m = item.mimeType || '';
  const n = (item.name || '').toLowerCase();
  if (m === FOLDER) return ['k-folder', ''];
  // 오피스 형식은 모두 «officedocument» 를 품는다 — 슬라이드·시트를 문서보다 먼저 본다
  if (m.includes('presentation') || /\.pptx?$/.test(n)) return ['k-slide', 'P'];
  if (m.includes('spreadsheet') || /\.(xlsx?|csv)$/.test(n)) return ['k-sheet', 'X'];
  if (m.includes('document') || /\.docx?$/.test(n)) return ['k-doc', 'W'];
  if (m === 'application/pdf') return ['k-pdf', 'PDF'];
  if (/\.(hwpx?|hwt)$/.test(n)) return ['k-hwp', '한'];
  if (m.startsWith('image/')) return ['k-img', ''];
  if (m === SHORTCUT) return ['k-file', '↗'];
  return ['k-file', ''];
}
const isFolder = (item) => item.mimeType === FOLDER
  || (item.mimeType === SHORTCUT && item.shortcutDetails?.targetMimeType === FOLDER);
const sizeText = (b) => !b ? '' : b < 1024 ? `${b} B` : b < 1 << 20 ? `${(b / 1024).toFixed(0)} KB` : `${(b / (1 << 20)).toFixed(1)} MB`;
const dateText = (t) => t ? new Date(t).toLocaleString('ko-KR', { year: '2-digit', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
const timeText = (sec) => new Date(sec * 1000).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });

function banner(text, error = false, action = null) {
  const el = $('banner');
  el.hidden = !text;
  el.className = `banner${error ? ' error' : ''}`;
  el.textContent = text || '';
  if (action) {
    const b = document.createElement('button');
    b.className = 'btn';
    b.type = 'button';
    b.textContent = action.label;
    b.addEventListener('click', action.run);
    el.append(b);
  }
}

function renderCrumbs() {
  $('crumbs').replaceChildren(...path.map((p, i) => {
    const li = document.createElement('li');
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = p.name;
    b.addEventListener('click', () => { path = path.slice(0, i + 1); load(); });
    li.append(b);
    return li;
  }));
  $('up').disabled = path.length < 2;
  for (const b of document.querySelectorAll('.side nav button')) {
    b.setAttribute('aria-current', String(b.dataset.id === path[0].id && path.length === 1));
  }
}

async function load() {
  renderCrumbs();
  const here = path[path.length - 1];
  const ticket = ++loading;
  selected.clear();
  anchor = null;
  items = [];
  renderSelection();
  $('empty').hidden = false;
  $('empty').textContent = '불러오는 중…';
  $('rows').replaceChildren();
  renderMode();
  const pc = inPc();
  const r = pc ? await api()?.pc_list(here.id) : await api()?.drive_list(here.id, driveId);
  if (ticket !== loading) return;
  if (!r || !r.ok) {
    $('empty').textContent = (r && r.error) || '불러오지 못했습니다.';
    if (r && r.auth) showReconnect(true);
    return;
  }
  items = r.items || [];
  if (pc && path.length === 1) setPcCount(items.length);
  $('empty').hidden = items.length > 0;
  $('empty').textContent = !pc ? '빈 폴더입니다.' : path.length > 1 ? '빈 폴더입니다.'
    : '아직 복사해 둔 파일이 없습니다. 드라이브에서 파일을 고르고 [컴퓨터로 복사]를 누르면 여기에 모여, 다음 수업에도 바로 열 수 있습니다.';
  $('rows').replaceChildren(...items.map(row));
  renderOpened();
}

// 이 수업에서 연 파일인가 — 원본 id 또는 «(교실에서 고침)» 새 파일 id
function openedOf(id) {
  return files.find((f) => f.source_id === id || f.upload_id === id) || null;
}

function row(item, index) {
  const el = document.createElement('div');
  el.className = 'row';
  el.tabIndex = 0;
  el.dataset.id = item.id;
  el.setAttribute('role', 'row');
  el.setAttribute('aria-selected', 'false');

  const pick = document.createElement('input');
  pick.type = 'checkbox';
  pick.className = 'pick';
  pick.setAttribute('aria-label', `${item.name} 고르기`);
  pick.addEventListener('click', (e) => { e.stopPropagation(); toggle(item.id, pick.checked); anchor = index; });

  const [kind, text] = kindOf(item);
  const name = document.createElement('span');
  name.className = 'name';
  const k = document.createElement('span');
  k.className = `kind ${kind}`;
  if (kind === 'k-folder') k.innerHTML = svg(ICON.up);
  else k.textContent = text;
  // 구글 드라이브의 실제 형식 아이콘 — 못 받으면 위의 글자 타일 그대로
  const mime = item.mimeType === SHORTCUT ? item.shortcutDetails?.targetMimeType : item.mimeType;
  if (mime) {
    const img = new Image();
    img.alt = '';
    img.onload = () => { k.className = 'kind real'; k.replaceChildren(img); };
    img.src = `https://drive-thirdparty.googleusercontent.com/32/type/${mime}`;
  }
  const label = document.createElement('span');
  label.className = 'label';
  label.textContent = item.name;
  label.title = item.place || item.name;
  const pill = document.createElement('span');
  pill.className = 'opened';
  pill.hidden = true;
  name.append(k, label, pill);
  const date = document.createElement('span');
  date.className = 'date';
  date.textContent = dateText(item.modifiedTime);
  const size = document.createElement('span');
  size.className = 'size';
  size.textContent = isFolder(item) ? '' : sizeText(Number(item.size));
  el.append(pick, name, date, size);

  el.addEventListener('click', (e) => clickRow(e, item, index));
  el.addEventListener('dblclick', () => openItem(item, el));
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') openItem(item, el);
    else if (e.key === ' ') { e.preventDefault(); toggle(item.id, !selected.has(item.id)); anchor = index; }
  });
  return el;
}

// 고르기 --------------------------------------------------------------------
function clickRow(e, item, index) {
  if (e.shiftKey && anchor !== null) {
    const [a, b] = [Math.min(anchor, index), Math.max(anchor, index)];
    if (!e.ctrlKey) selected.clear();
    items.slice(a, b + 1).forEach((i) => selected.add(i.id));
  } else if (e.ctrlKey || e.metaKey) {
    if (selected.has(item.id)) selected.delete(item.id); else selected.add(item.id);
    anchor = index;
  } else {
    selected.clear();
    selected.add(item.id);
    anchor = index;
  }
  renderSelection();
}
function toggle(id, on) {
  if (on) selected.add(id); else selected.delete(id);
  renderSelection();
}
function renderSelection() {
  for (const el of $('rows').children) {
    const on = selected.has(el.dataset.id);
    el.classList.toggle('selected', on);
    el.setAttribute('aria-selected', String(on));
    el.querySelector('.pick').checked = on;
  }
  const n = selected.size;
  $('select-all').checked = n > 0 && n === items.length;
  $('select-all').indeterminate = n > 0 && n < items.length;
  const pc = inPc();
  $('selbar').hidden = n === 0;
  $('tools').hidden = n > 0 || pc;
  $('pc-note').hidden = n > 0 || !pc;
  $('sel-count').textContent = `${n}개 선택`;
  const picked = items.filter((i) => selected.has(i.id));
  $('sel-open').disabled = !picked.some((i) => !isFolder(i));
  $('sel-copy').hidden = pc;
  $('sel-reveal').hidden = !pc;
  $('sel-reveal').disabled = n !== 1;
  $('sel-forget').hidden = !pc || path.length > 1;      // 복사한 것 단위로만 — 폴더 안 파일은 [지우기]
  $('sel-trash').hidden = !pc;
}
function renderMode() {
  const pc = inPc();
  $('date-head').textContent = pc && path.length === 1 ? '복사한 때' : '수정한 날';
  $('files').hidden = pc || files.length === 0;
}
$('select-all').addEventListener('change', () => {
  selected.clear();
  if ($('select-all').checked) items.forEach((i) => selected.add(i.id));
  renderSelection();
});
$('sel-clear').addEventListener('click', () => { selected.clear(); renderSelection(); });
$('sel-open').addEventListener('click', async () => {
  const picked = items.filter((i) => selected.has(i.id) && !isFolder(i));
  if (picked.length > 5 && !(await api()?.ask({ title: '한꺼번에 열기', ok: '모두 열기',
    body: `파일 ${picked.length}개를 받아 한꺼번에 엽니다. 계속할까요?` }))) return;
  for (const item of picked) {
    const el = $('rows').querySelector(`[data-id="${CSS.escape(item.id)}"]`);
    await openItem(item, el);
  }
});
$('sel-copy').addEventListener('click', () => copyToPc(items.filter((i) => selected.has(i.id))));
$('sel-reveal').addEventListener('click', async () => {
  const [id] = selected;
  const r = id && await api()?.pc_reveal(id);
  if (r && !r.ok) banner(r.error || '열지 못했습니다.', true);
});
$('sel-forget').addEventListener('click', async () => {
  const r = await api()?.pc_forget([...selected]);
  if (r && r.ok) { load(); banner(`${r.count}개를 목록에서 뺐습니다. 파일은 그 자리에 그대로 있습니다.`); }
  else banner((r && r.error) || '빼지 못했습니다.', true);
});
$('sel-trash').addEventListener('click', async () => {
  const picked = items.filter((i) => selected.has(i.id));
  if (!picked.length) return;
  const what = picked.length === 1 ? `«${picked[0].name}»` : `${picked.length}개`;
  if (!(await api()?.ask({ title: '이 PC 에서 지우기', danger: true, ok: '휴지통으로',
    body: `${what} 을(를) 이 PC 의 휴지통으로 옮깁니다. 드라이브의 원본은 그대로입니다.` }))) return;
  const r = await api()?.pc_trash(picked.map((i) => i.id));
  load();
  if (!r || !r.ok) banner((r && r.error) || '지우지 못했습니다.', true);
  else if (r.errors?.length) banner(`${r.removed}개를 휴지통으로 옮겼습니다 · 못 옮긴 것: ${r.errors.slice(0, 2).join(' / ')}`, true);
  else banner(`${r.removed}개를 휴지통으로 옮겼습니다.`);
});

// 열기 ---------------------------------------------------------------------
async function openItem(item, el) {
  if (isFolder(item)) {
    path.push({ id: item.mimeType === SHORTCUT ? item.shortcutDetails.targetId : item.id, name: item.name });
    load();
    return;
  }
  if (inPc()) {
    const r = await api()?.pc_open(item.id);
    if (r && r.ok) banner(`«${item.name}» 을(를) 열었습니다. 이 PC 의 파일이라 고쳐도 드라이브에는 올라가지 않습니다.`);
    else { banner((r && r.error) || '열지 못했습니다.', true); load(); }
    return;
  }
  el?.classList.add('busy');
  banner(`«${item.name}» 을(를) 받아 여는 중…`);
  const r = await api()?.drive_open(item.id);
  el?.classList.remove('busy');
  if (r && r.ok) banner(`«${item.name}» 을(를) 열었습니다. 고쳐서 저장하면 드라이브에 다시 올라갑니다.`);
  else {
    banner((r && r.error) || '열지 못했습니다.', true);
    if (r && r.auth) showReconnect(true);
  }
}

// 컴퓨터로 복사 --------------------------------------------------------------
let copying = false;
async function copyToPc(picked) {
  if (!picked.length) return;
  const r = await api()?.drive_copy(picked.map((i) => ({ id: i.id, name: i.name, mimeType: i.mimeType, shortcutDetails: i.shortcutDetails })));
  if (!r || !r.ok) { banner((r && r.error) || '복사하지 못했습니다.', true); return; }
  if (!r.started) return;                       // 폴더 고르기를 취소했다
  copying = true;
  banner(`«${r.dest}» 에 복사하는 중…`);
}
async function watchCopy() {
  if (!copying) return;
  const c = await api()?.drive_copy_state();
  if (!c) return;
  if (c.running) {
    banner(`복사하는 중 ${c.done}/${c.total || '?'}${c.current ? ` — ${c.current}` : ''}`);
    return;
  }
  copying = false;
  const res = c.result || {};
  if (res.auth) showReconnect(true);
  const extra = (res.truncated ? ' (한 번에 500개까지라 일부만)' : '') + (res.errors?.length ? ` · 못 받은 것 ${res.errors.length}개: ${res.errors.slice(0, 2).join(' / ')}` : '');
  if (res.copied) refreshPcCount();
  banner(`${res.copied || 0}개를 «${c.dest}» 에 복사했습니다. 수업이 끝나도 남고, 다음 수업에도 왼쪽 «${PC_NAME}»에서 바로 열 수 있습니다.${extra}`,
    !!res.errors?.length && !res.copied, res.copied ? { label: '폴더 열기', run: () => api()?.drive_reveal() } : null);
}

// 열어 둔 파일 — 목록의 줄에 표시 + 아래 칸에 [다시 열기]·[이 PC 에 저장] -----------------
function stateText(f) {
  if (f.state === 'failed') return `${ST.failed} — ${f.message}`;
  if (f.state === 'synced' && f.uploaded_at) return `올림 ${timeText(f.uploaded_at)}`;
  return ST[f.state] || '';
}
function renderOpened() {
  for (const el of $('rows').children) {
    const f = openedOf(el.dataset.id);
    const pill = el.querySelector('.opened');
    pill.hidden = !f;
    if (!f) continue;
    const edited = f.exported && f.upload_id === el.dataset.id;
    pill.className = `opened st-${f.state}`;
    pill.textContent = edited ? `교실에서 고친 파일 · ${stateText(f)}` : `열림 · ${stateText(f)}`;
    pill.title = f.exported && !edited
      ? '구글 문서는 원본을 덮지 않고 같은 폴더에 «(교실에서 고침)» 파일로 올립니다.' : '이 수업에서 연 파일';
  }
}
function renderFiles() {
  $('files').hidden = files.length === 0 || inPc();
  const key = JSON.stringify(files);
  if ($('file-list').dataset.key === key) return;
  $('file-list').dataset.key = key;
  $('file-list').replaceChildren(...files.map((f) => {
    const li = document.createElement('li');
    const a = document.createElement('span');
    a.className = 'fname';
    a.textContent = f.name;
    a.title = f.name;
    const b = document.createElement('span');
    b.className = `st-${f.state}`;
    b.textContent = stateText(f);
    const again = document.createElement('button');
    again.type = 'button';
    again.className = 'mini';
    again.textContent = '다시 열기';
    again.addEventListener('click', () => api()?.drive_open(f.source_id));
    const keep = document.createElement('button');
    keep.type = 'button';
    keep.className = 'mini';
    keep.textContent = '이 PC 에 저장';
    keep.title = '교실에서 고친 지금 내용 그대로 이 PC 의 폴더에 남깁니다(수업이 끝나도 지우지 않음).';
    keep.addEventListener('click', async () => {
      const r = await api()?.drive_keep(f.key);
      if (r && r.ok && r.saved) {
        refreshPcCount();
        banner(`«${f.name}» 을(를) 이 PC 에 남겼습니다: ${r.saved} — 다음 수업에도 왼쪽 «${PC_NAME}»에서 열 수 있습니다.`, false, { label: '폴더 열기', run: () => api()?.drive_reveal() });
      }
      else if (r && !r.ok) banner(r.error || '저장하지 못했습니다.', true);
    });
    li.append(a, b, again, keep);
    return li;
  }));
}

// 왼쪽: 내 드라이브 · 공유 문서함 · 이 수업 폴더 · 공유 드라이브 ---------------------
function navButton(label, icon, onClick, id) {
  const b = document.createElement('button');
  b.type = 'button';
  b.dataset.id = id;
  b.innerHTML = svg(icon);
  const s = document.createElement('span');
  s.textContent = label;
  b.append(s);
  b.addEventListener('click', onClick);
  return b;
}
function goRoot(id, name, drive = null) {
  path = [{ id, name }];
  driveId = drive;
  load();
}
window.go = (id, name, reset) => {           // 독에서 폴더를 눌렀을 때(Python 이 부른다)
  if (reset || !path.length) goRoot(id, name);
  else { path.push({ id, name }); load(); }
};

let pcCount = null;
function setPcCount(n) {
  pcCount = n;
  const c = $('pcnav').querySelector('.count');
  if (c) c.textContent = n ? String(n) : '';
  $('re-pc').hidden = !n;
}
async function refreshPcCount() {
  const r = await api()?.pc_count();
  if (r && r.ok) setPcCount(r.count);
}

async function loadSide() {
  const pcButton = navButton(PC_NAME, ICON.pc, () => { showReconnect(false); goRoot(PC, PC_NAME); }, PC);
  const count = document.createElement('span');
  count.className = 'count';
  pcButton.append(count);
  $('pcnav').replaceChildren(pcButton);
  refreshPcCount();
  $('places').replaceChildren(
    navButton('내 드라이브', ICON.home, () => goRoot('root', '내 드라이브'), 'root'),
    navButton('공유 문서함', ICON.people, () => goRoot('shared', '공유 문서함'), 'shared'),
  );
  const r = await api()?.drive_shared_drives();
  const drives = (r && r.ok && r.drives) || [];
  $('drives-cap').hidden = drives.length === 0;
  $('drives').replaceChildren(...drives.map((d) => navButton(d.name, ICON.drives, () => goRoot(d.id, d.name, d.id), d.id)));
}

function renderPresets(session) {
  const folders = (session?.items || []).filter((i) => i.kind === 'drive' && i.folder);
  $('presets-cap').hidden = folders.length === 0;
  const key = JSON.stringify(folders.map((f) => f.name));
  if ($('presets').dataset.key === key) return;
  $('presets').dataset.key = key;
  $('presets').replaceChildren(...folders.map((f) => {
    const index = session.items.indexOf(f);
    return navButton(f.name, ICON.up, () => api()?.open_item(index), `preset-${index}`);
  }));
}

// 드라이브 다시 연결 -------------------------------------------------------
let wantReconnect = false;
function showReconnect(on) {
  wantReconnect = on;
  $('reconnect').hidden = !on;
}
$('re-make').addEventListener('click', async () => {
  $('re-make').disabled = true;
  const r = await api()?.drive_reconnect();
  $('re-make').disabled = false;
  if (r && !r.ok) $('re-left').textContent = r.error || 'QR 을 만들지 못했습니다.';
});
$('re-cancel').addEventListener('click', () => { api()?.drive_reconnect_cancel(); showReconnect(false); });
$('re-pc').addEventListener('click', () => { showReconnect(false); goRoot(PC, PC_NAME); });   // 연결이 끝나도 이 PC 의 파일은 연다

function renderState(s) {
  const session = s.session;
  if (!session) return;
  $('who').textContent = session.teacher ? `${session.teacher} 선생님의 드라이브` : '드라이브';
  renderPresets(session);
  const drive = session.drive || {};
  files = session.files || [];
  renderFiles();
  renderOpened();

  // 연결: 끝났으면 다시 연결 화면, 10분 안쪽이면 알림 줄
  const link = s.drive_link;
  $('re-title').textContent = drive.connected ? '드라이브 연결 이어 가기' : '드라이브 연결이 끝났습니다';
  if (!drive.connected && !inPc()) showReconnect(true);       // «이 PC» 는 드라이브 연결 없이 본다
  else if (wantReconnect && !link) showReconnect(false);
  $('re-qr').hidden = !link;
  $('re-cancel').hidden = !link && !drive.connected;
  $('re-make').hidden = !!link;
  if (link) {
    if ($('re-qr').dataset.qr !== link.qr) { $('re-qr').dataset.qr = link.qr; $('re-qr').innerHTML = link.qr; }
    $('re-left').textContent = `휴대폰 카메라로 찍으세요 · ${Math.max(0, link.left)}초 뒤 사라짐`;
  } else if (!$('re-left').textContent.startsWith('QR')) {
    $('re-left').textContent = '';
  }
  if (drive.connected && drive.left < 600 && $('banner').hidden && !copying && !inPc()) {
    banner(`드라이브 연결이 ${Math.max(0, Math.floor(drive.left / 60))}분 남았습니다. 고친 파일은 저장해 두세요.`, false,
      { label: '지금 다시 연결', run: () => { showReconnect(true); $('re-make').click(); } });
  }
}

// 단추 --------------------------------------------------------------------
$('up').addEventListener('click', () => { if (path.length > 1) { path.pop(); load(); } });
$('refresh').addEventListener('click', load);
$('upload').addEventListener('click', async () => {
  const here = path[path.length - 1];
  if (here.id === 'shared') { banner('공유 문서함에는 올릴 수 없습니다. 폴더를 열고 올려 주세요.', true); return; }
  banner('올릴 파일을 고르세요…');
  const r = await api()?.drive_upload(here.id);
  if (r && r.ok) { banner(r.count ? `${r.count}개를 «${here.name}» 에 올렸습니다.` : ''); if (r.count) load(); }
  else banner((r && r.error) || '올리지 못했습니다.', true);
});
$('mkdir').addEventListener('click', () => {
  if (path[path.length - 1].id === 'shared') { banner('공유 문서함에는 폴더를 만들 수 없습니다.', true); return; }
  $('folder-name').value = '';
  $('folder-dialog').hidden = false;           // <dialog> 가 아니라 보통 겹창 — 전자칠판 터치(2026-10-14)
  $('folder-name').focus();
});
$('folder-cancel').addEventListener('click', () => { $('folder-dialog').hidden = true; });
$('folder-ok').addEventListener('click', async () => {
  const here = path[path.length - 1];
  const r = await api()?.drive_mkdir(here.id, $('folder-name').value);
  $('folder-dialog').hidden = true;
  if (r && r.ok) load(); else banner((r && r.error) || '만들지 못했습니다.', true);
});
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a' && !(e.target instanceof HTMLInputElement)) {
    e.preventDefault();
    items.forEach((i) => selected.add(i.id));
    renderSelection();
  } else if (e.key === 'Escape' && selected.size) {
    selected.clear();
    renderSelection();
  }
});

async function tick() {
  try {
    const s = await api()?.state();
    if (s) renderState(s);
    await watchCopy();
  } catch { /* 다음 바퀴 */ }
}

window.addEventListener('pywebviewready', async () => {
  const start = await api()?.drive_start();
  if (start && start.folder) path = [{ id: start.folder, name: start.name || '폴더' }];
  load();
  loadSide();
  tick();
  setInterval(tick, 1000);
});
