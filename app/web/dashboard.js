'use strict';
let dashboardUser, dashboardGeneration = 0, dashboardBusy = false, dashboardUpdated = 0;
let dashboardName = '';
// Same time boundaries and wording as SPACEKIJUN TeacherDashboardBriefing.
function refreshGreeting() {
  const now = new Date(), hour = now.getHours();
  const greeting = hour < 11 ? '좋은 아침입니다' : hour < 17 ? '좋은 오후입니다' : '오늘도 수고 많으셨습니다';
  $('dashboard-greeting').textContent = `${greeting}, ${dashboardName ? dashboardName + ' 선생님' : '선생님'}.`;
  $('today').textContent = new Intl.DateTimeFormat('ko-KR', {year:'numeric',month:'long',day:'numeric',weekday:'long'}).format(now);
  $('today').dateTime = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}
refreshGreeting();
setInterval(refreshGreeting, 60000);
document.addEventListener('visibilitychange', () => {if (!document.hidden) refreshGreeting();});
const dashboardSections = ['today', 'week', 'tasks', 'notices', 'notifications'];
const shortDay = value => value ? `${Number(value.slice(5,7))}.${Number(value.slice(8,10))}` : '';
const dashEmpty = text => `<p class="dashboard-empty">${escapeHTML(text)}</p>`;
function dashboardReset() {
  dashboardGeneration++;
  dashboardBusy = false;
  dashboardUpdated = 0;
  $('dashboard-grid').hidden = true;
  $('dashboard-grid').removeAttribute('aria-busy');
  dashboardSections.forEach(key => {$(`dash-${key}`).replaceChildren();});
  $('dash-task-count').textContent = '';
  dashboardName = '';
  refreshGreeting();
  $('dashboard-message').hidden = false;
  $('dashboard-message').querySelector('p').textContent = state.user ? '학교 정보를 불러오고 있습니다…' : 'SPACEKIJUN 계정을 연결하면 일정과 업무를 표시합니다.';
  $('dashboard-message').querySelector('button').hidden = !!state.user;
  $('dashboard-sync').textContent = state.user ? '불러오는 중' : '계정 연결 필요';
  $('refresh-dashboard').disabled = !state.user;
}
function renderDashboard(data) {
  const esc = escapeHTML;
  const errors = data.errors || {};
  const row = (lead, title, detail, label='', style='') => `<div class="dashboard-row ${style}"><span class="dashboard-lead">${esc(lead)}</span><div class="dashboard-copy"><strong>${esc(title)}</strong>${detail ? `<p>${esc(detail)}</p>` : ''}</div>${label ? `<span class="dashboard-tag">${esc(label)}</span>` : ''}</div>`;
  const fill = (key, html, empty, error) => {$(`dash-${key}`).innerHTML = (error ? dashEmpty(error) : '') + (html || (!error ? dashEmpty(empty) : ''));};
  dashboardName = data.name || '';
  refreshGreeting();
  const todayRows = data.today || [];
  fill('today', todayRows.map(item => row(item.time || item.label, item.title, item.detail, item.time ? item.label : '')).join(''), '오늘 등록된 수업과 일정이 없습니다.', errors.timetable || errors.meetings);
  const weekRows = data.week || [];
  fill('week', weekRows.map(item => row(shortDay(item.date), item.title, item.time, item.label)).join(''), '이번 주 남은 일정과 업무 마감이 없습니다.', errors.meetings || errors.tasks);
  const tasks = data.tasks || [];
  $('dash-task-count').textContent = errors.tasks ? '' : String(tasks.length);
  fill('tasks', tasks.map(item => row(shortDay(item.date) || '—', item.title, item.detail, item.label, item.label === '기한 초과' ? 'overdue' : '')).join(''), '진행할 업무가 없습니다.', errors.tasks);
  fill('notices', (data.notices || []).map(item => `<details class="dashboard-notice"><summary><span class="dashboard-tag">${esc(item.department)}</span><strong>${esc(item.title)}</strong><small>${shortDay(item.start_date)}–${shortDay(item.end_date)}</small></summary><p>${esc(item.content)}</p></details>`).join(''), '현재 게시 중인 학교 공지가 없습니다.', errors.notices);
  fill('notifications', (data.notifications || []).map(item => row(item.is_read ? '확인' : '새 알림', item.title, item.message, shortDay(new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Seoul'}).format(new Date(item.created_at))), item.is_read ? '' : 'unread')).join(''), '도착한 알림이 없습니다.', errors.notifications);
  const updated = new Date(data.updated_at);
  $('dashboard-sync').textContent = `${Number.isNaN(updated.getTime()) ? '' : updated.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}) + ' 확인 · '}${Object.keys(errors).length ? '일부 조회 실패' : '1분마다 갱신'}`;
  $('dashboard-message').hidden = true;
  $('dashboard-grid').hidden = false;
}
async function loadDashboard() {
  if (!ready || !state.user || dashboardBusy) return;
  dashboardBusy = true;
  const generation = dashboardGeneration;
  $('refresh-dashboard').disabled = true;
  $('dashboard-grid').setAttribute('aria-busy', 'true');
  $('dashboard-sync').textContent = '불러오는 중…';
  try {
    // 데스크가 미리 받아 둔 것부터 바로 그린다 — '불러오고 있습니다'를 오래 보이지 않게
    try {
      const quick = await api('dashboard_quick');
      if (quick && generation === dashboardGeneration) renderDashboard(quick.data);
    } catch {/* 없으면 아래에서 받아 온다 */}
    const data = await api('dashboard');
    if (generation !== dashboardGeneration) return;
    if (!data || typeof data !== 'object') throw new Error('대시보드 데이터를 확인할 수 없습니다.');
    renderDashboard(data);
  } catch (error) {
    if (generation !== dashboardGeneration) return;
    // Hide stale personal data after an auth or network failure.
    $('dashboard-grid').hidden = true;
    dashboardSections.forEach(key => {$(`dash-${key}`).replaceChildren();});
    $('dashboard-message').hidden = false;
    $('dashboard-message').querySelector('p').textContent = error.message;
    $('dashboard-message').querySelector('button').hidden = false;
    $('dashboard-sync').textContent = '새로고침 필요';
  } finally {
    if (generation === dashboardGeneration) {
      dashboardBusy = false;
      dashboardUpdated = Date.now();
      $('refresh-dashboard').disabled = !state.user;
      $('dashboard-grid').removeAttribute('aria-busy');
    }
  }
}
$('refresh-dashboard').addEventListener('click', loadDashboard);
window.addEventListener('desk-state', () => {
  if (dashboardUser !== state.user) {
    dashboardUser = state.user;
    dashboardReset();
  }
  // 자리를 비우면(state.away — 데스크의 AWAY_AFTER) 쉰다. 창을 띄워 둔 채 퇴근하면 document.hidden 은
  // 거짓이라 밤새 1분마다 물었다(2026-10-18 로그: 새벽에도 같은 빈도). 돌아오면 다음 상태 확인(2초)에서
  // 1분이 지났으므로 곧바로 받는다.
  if (currentPage === 'home' && !document.hidden && !state.away && Date.now() - dashboardUpdated >= 60000) loadDashboard();
});
