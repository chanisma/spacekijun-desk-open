// 구글 수업 도구 — 클래스룸 · 슬라이드 · 설문지를 «구글 로그인 없이»(2026-10-14 요청), 원래 구글 화면과 최대한 같게(같은 날 요청).
// QR 승인 때 휴대폰이 넘긴 토큰으로 기기가 구글 API 를 직접 부른다(드라이브와 같은 방식). 구글 웹 화면은 쓰지 않는다.
// Windows 교실판(classroom-gtools.html)과 전자칠판판(android board.html)이 함께 쓴다 — 앱과는 host 로만 말한다:
//   host.call(이름, ...인자) → Promise
//       google_api(method, url, body)  허용한 구글 API 주소만(core/google_tools.py · GoogleApi.kt) → {ok, data} | {ok:false, reason, error}
//       qr_svg(text) · drive_open(fileId) · open_web(url, title)
//   host.close() · host.fullscreen(on)
// 아래 줄(← 수업 화면 · 도구 바꾸기 · 뒤로·새로고침)은 칠판에서 손이 닿게 아래에 둔다. 나머지는 원래 구글 화면처럼.
// 🚨 옛 WebView(칠판)에서도 돌게 — ?. · ?? · replaceChildren 을 쓰지 않는다.
(function () {
  'use strict';
  var CLASSROOM = 'https://classroom.googleapis.com/v1';
  var FORMS = 'https://forms.googleapis.com/v1';
  var SLIDES = 'https://slides.googleapis.com/v1';
  var DRIVE = 'https://www.googleapis.com/drive/v3';
  var PPTX = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
  var TABS = [['classroom', '클래스룸', 'icons/google/classroom.png'], ['slides', '슬라이드', 'icons/google/slides.png'],
    ['forms', '설문지', 'icons/google/forms.png']];
  // 클래스룸 수업 색(원래 클래스룸의 테마 색들)
  var THEMES = ['#1967d2', '#1e8e3e', '#e37400', '#129eaf', '#d93025', '#9334e6', '#4285f4', '#0b8043', '#c26401', '#7b1fa2'];
  // 구글 차트 색(설문지 요약)
  var CHART = ['#4285f4', '#db4437', '#f4b400', '#0f9d58', '#ab47bc', '#00acc1', '#ff7043', '#9e9d24', '#5c6bc0', '#f06292'];

  var ICONS = {
    assignment: 'M19 3h-4.18C14.4 1.84 13.3 1 12 1s-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z',
    book: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z',
    question: 'M11 18h2v-2h-2v2zm1-16C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-14c-2.21 0-4 1.79-4 4h2c0-1.1.9-2 2-2s2 .9 2 2c0 2-3 1.75-3 5h2c0-2.25 3-2.5 3-5 0-2.21-1.79-4-4-4z',
    folder: 'M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z',
    play: 'M8 5v14l11-7z',
    link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
    search: 'M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
    left: 'M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z',
    right: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
    close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
    expand: 'M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z',
    send: 'M2.01 21 23 12 2.01 3 2 10l15 2-15 2z',
    file: 'M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
    video: 'M10 16.5l6-4.5-6-4.5v9zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z',
    people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
    stream: 'M4 6h16v2H4zm0 5h16v2H4zm0 5h16v2H4z',
  };

  var host = null;
  var root = null;
  var parts = {};
  var current = { tab: 'classroom', back: null, timer: 0, token: 0 };
  var present = null;
  var profiles = {};

  // ── 작은 도구 ─────────────────────────────────────────────
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function fill(node, children) {
    while (node.firstChild) node.removeChild(node.firstChild);
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }
  function append(node, children) {
    children.forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }
  function button(text, cls, onClick) {
    var b = el('button', cls || 'gt-btn', text);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }
  function icon(name, cls) {
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'gi' + (cls ? ' ' + cls : ''));
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS(ns, 'path');
    path.setAttribute('d', ICONS[name] || ICONS.file);
    svg.appendChild(path);
    return svg;
  }
  function iconButton(name, label, onClick, cls) {
    var b = button('', 'gt-ib' + (cls ? ' ' + cls : ''), onClick);
    b.setAttribute('aria-label', label);
    b.title = label;
    b.appendChild(icon(name));
    return b;
  }
  function enc(v) { return encodeURIComponent(v); }
  function when(iso, prefix) {
    if (!iso) return '';
    var d = new Date(iso);
    var now = new Date();
    var text = d.toDateString() === now.toDateString()
      ? d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('ko-KR', d.getFullYear() === now.getFullYear() ? { month: 'long', day: 'numeric' } : { year: 'numeric', month: 'long', day: 'numeric' });
    return (prefix || '') + text;
  }
  function hash(text) {
    var h = 0;
    for (var i = 0; i < String(text).length; i++) h = (h * 31 + String(text).charCodeAt(i)) >>> 0;
    return h;
  }
  function themeOf(course) { return THEMES[hash(course.id || course.name) % THEMES.length]; }
  function photo(url) { return url ? (url.indexOf('//') === 0 ? 'https:' + url : url) : ''; }
  function avatar(profile, size) {
    var name = (profile && profile.name && (profile.name.fullName || profile.name.givenName)) || '';
    var box = el('span', 'gt-avatar');
    box.style.width = box.style.height = (size || 40) + 'px';
    box.style.fontSize = Math.round((size || 40) * 0.42) + 'px';
    var src = photo(profile && profile.photoUrl);
    var letter = function () {
      box.textContent = name ? name.charAt(0) : '?';
      box.style.background = THEMES[hash(name || '?') % THEMES.length];
    };
    if (src && src.indexOf('default-user') < 0) {
      var img = new Image();
      img.alt = '';
      img.referrerPolicy = 'no-referrer';
      img.onerror = function () { box.removeChild(img); letter(); };
      img.src = src;
      box.appendChild(img);
    } else {
      letter();
    }
    return box;
  }
  function fullName(profile) {
    return (profile && profile.name && (profile.name.fullName || profile.name.givenName)) || '';
  }

  function message(r) {
    if (!r) return '앱과 연결되지 않았습니다.';
    if (r.reason === 'disabled') {
      return '학교 Google Cloud 에서 ' + (r.api || '이') + ' API 가 꺼져 있습니다. 관리자에게 켜 달라고 부탁해 주세요.';
    }
    if (r.reason === 'scope') return 'QR 승인 때 이 기능의 구글 권한을 허용하지 않았습니다. 다음 승인 때 구글 창에서 모두 허용해 주세요.';
    if (r.reason === 'auth') return '구글 연결 시간이 끝났습니다. «내 드라이브»에서 QR 로 다시 연결해 주세요.';
    if (r.reason === 'notfound') return '찾지 못했습니다(지워졌거나 권한이 없습니다).';
    return r.error || '구글에서 불러오지 못했습니다.';
  }

  function g(method, url, body) {
    return Promise.resolve(host.call('google_api', method, url, body || null)).then(function (r) {
      if (!r || r.ok === false) {
        var e = new Error(message(r));
        e.info = r;
        throw e;
      }
      return r.data || {};
    });
  }
  /** 실패해도 빈 값 — 권한이 없는 부분(예: 새 범위를 아직 허용하지 않음)만 비우고 나머지는 보인다 */
  function soft(promise, fallback) {
    return promise.catch(function (e) { return { __error: e, value: fallback }; });
  }

  function toast(text, error) {
    var t = parts.toast;
    t.textContent = text;
    t.className = 'gt-toast' + (error ? ' error' : '');
    t.hidden = false;
    clearTimeout(t._timer);
    t._timer = setTimeout(function () { t.hidden = true; }, error ? 8000 : 4000);
  }

  function modal(build, cls) {
    var box = el('div', 'gt-modal');
    var sheet = el('div', 'gt-sheet' + (cls ? ' ' + cls : ''));
    var close = function () { if (box.parentNode) root.removeChild(box); };
    build(sheet, close);
    box.appendChild(sheet);
    box.addEventListener('click', function (e) { if (e.target === box) close(); });
    root.appendChild(box);
    return close;
  }
  function confirmBox(title, body, ok, color) {
    return new Promise(function (resolve) {
      modal(function (sheet, close) {
        sheet.appendChild(el('h3', null, title));
        sheet.appendChild(el('p', null, body));
        var row = el('div', 'gt-row');
        row.appendChild(button('취소', 'gt-text-btn', function () { close(); resolve(false); }));
        var okb = button(ok, 'gt-fill-btn', function () { close(); resolve(true); });
        if (color) okb.style.background = color;
        row.appendChild(okb);
        sheet.appendChild(row);
      });
    });
  }
  function qrInto(node, text) {
    Promise.resolve(host.call('qr_svg', text)).then(function (svg) { if (typeof svg === 'string') node.innerHTML = svg; });
  }
  function loading(text) {
    fill(parts.body, [el('div', 'gt-empty', text || '불러오는 중…')]);
  }
  function failed(e, retry) {
    var box = el('div', 'gt-empty error');
    box.appendChild(el('p', null, e.message || String(e)));
    if (retry) box.appendChild(button('다시 시도', 'gt-btn', retry));
    fill(parts.body, [box]);
  }
  /** 아래 줄 오른쪽 단추(뒤로·새로고침·웹으로) */
  function frame(actions, back) {
    current.back = back || null;
    fill(parts.actions, (back ? [button('← ' + back.label, 'gt-btn', back.go)] : []).concat(actions || []));
  }
  function stopTimer() {
    clearInterval(current.timer);
    current.timer = 0;
  }
  /** 원래 앱의 위 막대(로고 · 이름 · 가운데 탭 · 오른쪽) */
  function appBar(logo, title, crumbs, center, right, cls) {
    var bar = el('header', 'gt-appbar' + (cls ? ' ' + cls : ''));
    var left = el('div', 'gt-appbar-left');
    var img = el('img', 'gt-applogo');
    img.alt = '';
    img.src = logo;
    left.appendChild(img);
    left.appendChild(el('span', 'gt-appname', title));
    (crumbs || []).forEach(function (c) {
      left.appendChild(icon('right', 'gt-crumb-sep'));
      var t = el('span', 'gt-crumb');
      t.appendChild(el('strong', null, c[0]));
      if (c[1]) t.appendChild(el('small', null, c[1]));
      left.appendChild(t);
    });
    bar.appendChild(left);
    bar.appendChild(center || el('div', 'gt-appbar-center'));
    bar.appendChild(right || el('div', 'gt-appbar-right'));
    return bar;
  }
  function tabStrip(items, active, color, onPick) {
    var nav = el('nav', 'gt-appbar-center gt-gtabs');
    items.forEach(function (t) {
      var b = button(t[1], 'gt-gtab' + (t[0] === active ? ' on' : ''), function () { onPick(t[0]); });
      if (t[0] === active && color) { b.style.color = color; b.style.borderColor = color; }
      nav.appendChild(b);
    });
    return nav;
  }

  // ── 도구 바꾸기 ───────────────────────────────────────────
  function open(tab) {
    if (!root) return;
    closePresenter();
    stopTimer();
    current.token++;
    current.tab = tab || current.tab || 'classroom';
    Array.prototype.forEach.call(parts.tabs.children, function (b) {
      b.classList.toggle('on', b.getAttribute('data-tab') === current.tab);
    });
    root.setAttribute('data-app', current.tab);
    if (current.tab === 'slides') slidesHome('');
    else if (current.tab === 'forms') formsHome();
    else classroomHome();
  }

  // ══ 클래스룸 ═══════════════════════════════════════════════
  function me() {
    if (!profiles.me) profiles.me = soft(g('GET', CLASSROOM + '/userProfiles/me'), null).then(function (v) { return v && v.__error ? null : v; });
    return profiles.me;
  }

  function classroomHome() {
    var token = current.token;
    frame([button('새로고침', 'gt-btn', function () { current.token++; classroomHome(); })]);
    loading();
    Promise.all([g('GET', CLASSROOM + '/courses?teacherId=me&courseStates=ACTIVE&pageSize=60'), me()]).then(function (r) {
      if (token !== current.token) return;
      var courses = r[0].courses || [];
      var mine = r[1];
      var right = el('div', 'gt-appbar-right');
      if (mine) right.appendChild(avatar(mine, 36));
      var page = el('div', 'gt-cr-home');
      if (!courses.length) {
        page.appendChild(el('div', 'gt-empty', '선생님이 가르치는 수업이 없습니다.'));
      } else {
        var grid = el('div', 'gt-cr-cards');
        courses.forEach(function (c) { grid.appendChild(courseCard(c, mine)); });
        page.appendChild(grid);
      }
      fill(parts.body, [appBar('icons/google/classroom.png', '클래스룸', null, null, right), page]);
    }).catch(function (e) { if (token === current.token) failed(e, classroomHome); });
  }

  function banner(color, big) {
    var b = el('div', big ? 'gt-cr-banner' : 'gt-cr-card-head');
    b.style.backgroundColor = color;
    return b;
  }

  function courseCard(c, mine) {
    var color = themeOf(c);
    var card = el('article', 'gt-cr-card');
    var head = banner(color);
    var open1 = button('', 'gt-cr-card-title', function () { course(c, 'stream'); });
    open1.appendChild(el('strong', null, c.name || '수업'));
    if (c.section) open1.appendChild(el('span', null, c.section));
    head.appendChild(open1);
    if (c.room) head.appendChild(el('span', 'gt-cr-card-room', c.room));
    card.appendChild(head);
    var pic = avatar(mine, 72);
    pic.className += ' gt-cr-card-avatar';
    card.appendChild(pic);
    var body = el('div', 'gt-cr-card-body');
    body.addEventListener('click', function () { course(c, 'stream'); });
    card.appendChild(body);
    var foot = el('div', 'gt-cr-card-foot');
    foot.appendChild(iconButton('assignment', '수업 과제', function () { course(c, 'work'); }));
    foot.appendChild(iconButton('people', '사용자', function () { course(c, 'people'); }));
    if (c.teacherFolder && c.teacherFolder.alternateLink) {
      foot.appendChild(iconButton('folder', '클래스룸 드라이브 폴더', function () { host.call('open_web', c.teacherFolder.alternateLink, c.name); }));
    }
    card.appendChild(foot);
    return card;
  }

  /** 수업 하나 — 데이터는 한 번 받아 세 탭(스트림·수업·사용자)이 같이 쓴다 */
  function course(c, tab) {
    var token = ++current.token;
    var color = themeOf(c);
    var data = null;
    var reload = function () { course(c, active); };
    var active = tab || 'stream';
    var actions = [button('새로고침', 'gt-btn', reload)];
    if (c.alternateLink) actions.push(button('웹으로 열기', 'gt-btn', function () { host.call('open_web', c.alternateLink, c.name); }));
    frame(actions, { label: '수업 목록', go: function () { current.token++; classroomHome(); } });
    loading();
    var base = CLASSROOM + '/courses/' + enc(c.id);
    Promise.all([
      soft(g('GET', base + '/announcements?pageSize=30&orderBy=' + enc('updateTime desc')), {}),
      // 초안·예약 게시도 — 원래 클래스룸은 선생님에게 «초안»·«예약됨»으로 보여 준다(기본값은 게시된 것만)
      soft(g('GET', base + '/courseWork?pageSize=60&orderBy=' + enc('updateTime desc') + '&courseWorkStates=PUBLISHED&courseWorkStates=DRAFT'), {}),
      soft(g('GET', base + '/courseWorkMaterials?pageSize=60&orderBy=' + enc('updateTime desc') +
        '&courseWorkMaterialStates=PUBLISHED&courseWorkMaterialStates=DRAFT'), {}),
      soft(g('GET', base + '/topics?pageSize=60'), {}),
      soft(g('GET', base + '/teachers?pageSize=60'), {}),
      soft(g('GET', base + '/students?pageSize=300'), {}),
      me(),
    ]).then(function (r) {
      if (token !== current.token) return;
      // 🚨 클래스룸 목록 응답의 필드 이름은 들쭉날쭉하다 — 자료는 courseWorkMaterial, 주제는 topic(단수).
      //    복수로 읽어 자료·주제가 늘 비어 보였다(2026-10-14 사용자 보고). 두 이름을 다 본다.
      var val = function (x, key, other) { return x && x.__error ? [] : ((x && (x[key] || (other && x[other]))) || []); };
      data = {
        announcements: val(r[0], 'announcements'), work: val(r[1], 'courseWork'), materials: val(r[2], 'courseWorkMaterial', 'courseWorkMaterials'),
        topics: val(r[3], 'topic', 'topics'), teachers: val(r[4], 'teachers'), students: val(r[5], 'students'), me: r[6],
        // 못 불러온 부분 — 이름과 함께(감추지 않는다: 자료가 안 보이면 왜인지 알 수 있게)
        errors: r.slice(0, 6).map(function (x, i) { return x && x.__error ? { part: ['공지', '과제', '수업 자료', '주제', '교사', '학생'][i], error: x.__error } : null; })
          .filter(Boolean),
      };
      if (r[0] && r[0].__error && r[1] && r[1].__error) { failed(r[0].__error, reload); return; }
      data.people = {};
      data.teachers.concat(data.students).forEach(function (p) { data.people[p.userId] = p.profile; });
      if (data.me) data.people[data.me.id] = data.me;
      render();
    });

    function render() {
      if (token !== current.token) return;
      var right = el('div', 'gt-appbar-right');
      if (data.me) right.appendChild(avatar(data.me, 36));
      var bar = appBar('icons/google/classroom.png', '클래스룸', [[c.name || '수업', c.section || '']],
        tabStrip([['stream', '스트림'], ['work', '수업'], ['people', '사용자']], active, color, function (t) { active = t; render(); }), right);
      var page = el('div', 'gt-cr-page');
      if (active === 'work') classwork(page);
      else if (active === 'people') people(page);
      else stream(page);
      // 못 불러온 부분이 있으면 무엇을 왜 못 불러왔는지 한 줄로(권한이 없으면 다음 승인 때 허용하라고)
      var scoped = data.errors.filter(function (x) { return x.error.info && x.error.info.reason === 'scope'; }).map(function (x) { return x.part; });
      var other = data.errors.filter(function (x) { return !(x.error.info && x.error.info.reason === 'scope'); });
      if (scoped.length) {
        page.insertBefore(el('p', 'gt-note', scoped.join('·') + '을(를) 보려면 권한이 더 필요합니다. 다음 QR 승인 때 구글 창에서 모두 허용해 주세요.'), page.firstChild);
      }
      other.forEach(function (x) { page.insertBefore(el('p', 'gt-note', x.part + '을(를) 불러오지 못했습니다: ' + x.error.message), page.firstChild); });
      fill(parts.body, [bar, page]);
      parts.body.scrollTop = 0;
    }

    function stream(page) {
      var b = banner(color, true);
      b.appendChild(el('h2', null, c.name || '수업'));
      if (c.section) b.appendChild(el('p', null, c.section));
      page.appendChild(b);
      var cols = el('div', 'gt-cr-stream');
      var side = el('aside', 'gt-cr-side');
      if (c.enrollmentCode) {
        var codeCard = el('section', 'gt-cr-box');
        var head = el('div', 'gt-cr-box-head');
        head.appendChild(el('span', null, '수업 코드'));
        head.appendChild(iconButton('expand', '크게 보기', function () { showCode(c, color); }));
        codeCard.appendChild(head);
        var code = el('div', 'gt-cr-code', c.enrollmentCode);
        code.style.color = color;
        codeCard.appendChild(code);
        side.appendChild(codeCard);
      }
      var up = el('section', 'gt-cr-box');
      up.appendChild(el('div', 'gt-cr-box-head', '예정된 과제'));
      var now = Date.now();
      var soon = data.work.filter(function (w) {
        if (!w.dueDate || w.state === 'DRAFT') return false;
        var t = new Date(w.dueDate.year, w.dueDate.month - 1, w.dueDate.day, 23, 59).getTime();
        return t >= now && t - now < 7 * 864e5;
      });
      if (soon.length) {
        soon.slice(0, 4).forEach(function (w) {
          var row = button('', 'gt-cr-upcoming', function () { active = 'work'; render(); });
          row.appendChild(el('span', 'when', '기한: ' + dueText(w)));
          row.appendChild(el('strong', null, w.title));
          up.appendChild(row);
        });
      } else {
        up.appendChild(el('p', 'gt-cr-muted', '예정된 과제가 없습니다.'));
      }
      up.appendChild(button('모두 보기', 'gt-text-btn', function () { active = 'work'; render(); }));
      side.appendChild(up);
      cols.appendChild(side);

      var main = el('div', 'gt-cr-main');
      main.appendChild(composer());
      var items = [];
      data.announcements.forEach(function (a) { items.push({ kind: 'ann', at: a.updateTime || a.creationTime, item: a }); });
      data.work.forEach(function (w) { if (w.state !== 'DRAFT') items.push({ kind: 'work', at: w.creationTime || w.updateTime, item: w }); });
      data.materials.forEach(function (m) { if (m.state !== 'DRAFT') items.push({ kind: 'mat', at: m.creationTime || m.updateTime, item: m }); });
      items.sort(function (x, y) { return String(y.at).localeCompare(String(x.at)); });
      if (!items.length) {
        var empty = el('section', 'gt-cr-post gt-cr-empty');
        empty.appendChild(el('strong', null, '여기에서 수업과 소통하세요'));
        empty.appendChild(el('p', null, '공지를 올리면 학생들에게 바로 보입니다.'));
        main.appendChild(empty);
      }
      items.slice(0, 40).forEach(function (x) { main.appendChild(x.kind === 'ann' ? announcement(x.item) : postedLine(x.item, x.kind)); });
      cols.appendChild(main);
      page.appendChild(cols);
    }

    function composer() {
      var box = el('section', 'gt-cr-post gt-cr-compose');
      var closed = button('', 'gt-cr-compose-closed', function () { openIt(); });
      closed.appendChild(avatar(data.me, 40));
      closed.appendChild(el('span', null, '수업에 공지하기'));
      box.appendChild(closed);
      function openIt() {
        var area = el('div', 'gt-cr-compose-open');
        var label = el('label', 'gt-cr-field');
        label.appendChild(el('span', null, '수업에 공지할 내용 입력'));
        var text = el('textarea');
        text.rows = 4;
        label.appendChild(text);
        area.appendChild(label);
        var row = el('div', 'gt-row');
        row.appendChild(button('취소', 'gt-text-btn', function () { fill(box, [closed]); }));
        var post = button('게시', 'gt-fill-btn', function () {
          var value = text.value.trim();
          if (!value) { text.focus(); return; }
          confirmBox('공지를 게시할까요?', '«' + (c.name || '수업') + '» 학생들에게 바로 보이고 알림이 갑니다.', '게시', color).then(function (yes) {
            if (!yes) return;
            post.disabled = true;
            g('POST', CLASSROOM + '/courses/' + enc(c.id) + '/announcements', { text: value, state: 'PUBLISHED' }).then(function () {
              toast('공지를 게시했습니다.');
              reload();
            }).catch(function (e) { post.disabled = false; toast(e.message, true); });
          });
        });
        post.style.background = color;
        row.appendChild(post);
        area.appendChild(row);
        fill(box, [area]);
        setTimeout(function () { text.focus(); }, 30);
      }
      return box;
    }

    function announcement(a) {
      var post = el('article', 'gt-cr-post');
      var head = el('div', 'gt-cr-post-head');
      var who = data.people[a.creatorUserId];
      head.appendChild(avatar(who, 40));
      var names = el('div', 'gt-cr-post-who');
      names.appendChild(el('strong', null, fullName(who) || '선생님'));
      names.appendChild(el('span', null, when(a.updateTime || a.creationTime)));
      head.appendChild(names);
      post.appendChild(head);
      if (a.text) post.appendChild(el('p', 'gt-cr-post-text', a.text));
      var mats = attachments(a.materials);
      if (mats) post.appendChild(mats);
      return post;
    }

    function postedLine(w, kind) {
      var row = button('', 'gt-cr-post gt-cr-line', function () { active = 'work'; render(); });
      var circle = el('span', 'gt-cr-circle');
      circle.style.background = color;
      circle.appendChild(icon(kind === 'mat' ? 'book' : w.workType === 'SHORT_ANSWER_QUESTION' || w.workType === 'MULTIPLE_CHOICE_QUESTION' ? 'question' : 'assignment'));
      row.appendChild(circle);
      var text = el('div', 'gt-cr-line-text');
      var who = fullName(data.people[w.creatorUserId]) || '선생님';
      text.appendChild(el('strong', null, who + '님이 새 ' + (kind === 'mat' ? '자료' : '과제') + '를 게시했습니다: ' + (w.title || '')));
      text.appendChild(el('span', null, when(w.creationTime || w.updateTime)));
      row.appendChild(text);
      return row;
    }

    function classwork(page) {
      var wrap = el('div', 'gt-cr-work');
      var all = data.work.map(function (w) { return { kind: 'work', item: w }; })
        .concat(data.materials.map(function (m) { return { kind: 'mat', item: m }; }));
      if (!all.length) {
        wrap.appendChild(el('div', 'gt-empty', '이 수업에 게시한 과제나 자료가 없습니다.'));
        page.appendChild(wrap);
        return;
      }
      var topics = data.topics.slice().sort(function (a, b) { return String(b.updateTime).localeCompare(String(a.updateTime)); });
      var groups = [{ id: '', name: '' }].concat(topics.map(function (t) { return { id: t.topicId, name: t.name }; }));
      groups.forEach(function (gr) {
        var list = all.filter(function (x) { return (x.item.topicId || '') === gr.id; });
        if (!list.length) return;
        var sec = el('section', 'gt-cr-topic');
        if (gr.name) {
          var h = el('h3', null, gr.name);
          h.style.color = color;
          h.style.borderColor = color;
          sec.appendChild(h);
        }
        list.sort(function (a, b) { return String(b.item.updateTime).localeCompare(String(a.item.updateTime)); });
        list.forEach(function (x) { sec.appendChild(workRow(x.item, x.kind)); });
        wrap.appendChild(sec);
      });
      page.appendChild(wrap);
    }

    function workRow(w, kind) {
      var item = el('article', 'gt-cr-witem');
      var top = button('', 'gt-cr-wtop', function () { toggle(); });
      var draft = w.state === 'DRAFT';
      var circle = el('span', 'gt-cr-circle');
      circle.style.background = draft ? '#9aa0a6' : color;
      circle.appendChild(icon(kind === 'mat' ? 'book' : w.workType === 'SHORT_ANSWER_QUESTION' || w.workType === 'MULTIPLE_CHOICE_QUESTION' ? 'question' : 'assignment'));
      top.appendChild(circle);
      top.appendChild(el('strong', null, w.title || (kind === 'mat' ? '자료' : '과제')));
      top.appendChild(el('span', 'when', draft
        ? (w.scheduledTime ? when(w.scheduledTime, '예약됨: ') : '초안')
        : kind === 'mat' ? when(w.creationTime || w.updateTime, '게시일: ') : (w.dueDate ? '기한: ' + dueText(w) : '기한 없음')));
      item.appendChild(top);
      var detail = el('div', 'gt-cr-wdetail');
      detail.hidden = true;
      item.appendChild(detail);
      var loaded = false;
      function toggle() {
        item.classList.toggle('open');
        detail.hidden = !detail.hidden;
        if (loaded || detail.hidden) return;
        loaded = true;
        var left = el('div', 'gt-cr-wdesc');
        left.appendChild(el('span', 'gt-cr-muted', when(w.creationTime || w.updateTime, '게시일: ')));
        if (w.description) left.appendChild(el('p', null, w.description));
        var mats = attachments(w.materials);
        if (mats) left.appendChild(mats);
        detail.appendChild(left);
        if (kind === 'work') {
          var stats = el('div', 'gt-cr-wstats');
          var turned = el('div', 'gt-cr-stat');
          var assigned = el('div', 'gt-cr-stat');
          turned.appendChild(el('b', null, '–'));
          turned.appendChild(el('span', null, '제출함'));
          assigned.appendChild(el('b', null, '–'));
          assigned.appendChild(el('span', null, '할당됨'));
          stats.appendChild(turned);
          stats.appendChild(assigned);
          detail.appendChild(stats);
          g('GET', CLASSROOM + '/courses/' + enc(c.id) + '/courseWork/' + enc(w.id) + '/studentSubmissions?pageSize=300').then(function (s) {
            var subs = s.studentSubmissions || [];
            var done = subs.filter(function (x) { return x.state === 'TURNED_IN' || x.state === 'RETURNED'; }).length;
            turned.firstChild.textContent = String(done);
            assigned.firstChild.textContent = String(subs.length - done);
          }).catch(function (e) { stats.appendChild(el('span', 'gt-cr-muted', e.message)); });
        }
        if (w.alternateLink) detail.appendChild(button(kind === 'mat' ? '자료 보기' : '과제 보기', 'gt-text-btn', function () { host.call('open_web', w.alternateLink, w.title); }));
      }
      return item;
    }

    function people(page) {
      var wrap = el('div', 'gt-cr-people');
      var sec = function (title, list, count) {
        var s = el('section', 'gt-cr-psec');
        var h = el('div', 'gt-cr-phead');
        h.style.color = color;
        h.style.borderColor = color;
        h.appendChild(el('h3', null, title));
        if (count) h.appendChild(el('span', null, count));
        s.appendChild(h);
        if (!list.length) s.appendChild(el('p', 'gt-cr-muted', title === '학생' ? '아직 학생이 없습니다.' : '정보가 없습니다.'));
        list.forEach(function (p) {
          var row = el('div', 'gt-cr-person');
          row.appendChild(avatar(p.profile, 36));
          row.appendChild(el('span', null, fullName(p.profile) || p.userId));
          s.appendChild(row);
        });
        return s;
      };
      var students = data.students.slice().sort(function (a, b) { return fullName(a.profile).localeCompare(fullName(b.profile), 'ko'); });
      wrap.appendChild(sec('교사', data.teachers));
      wrap.appendChild(sec('학생', students, students.length ? '학생 ' + students.length + '명' : ''));
      page.appendChild(wrap);
    }
  }

  function dueText(w) {
    if (!w.dueDate) return '';
    var d = new Date(w.dueDate.year, w.dueDate.month - 1, w.dueDate.day);
    var text = d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });
    if (w.dueTime && w.dueTime.hours != null) {
      var t = new Date(Date.UTC(w.dueDate.year, w.dueDate.month - 1, w.dueDate.day, w.dueTime.hours || 0, w.dueTime.minutes || 0));
      text = t.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' }) + ' ' +
        t.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' });
    }
    return text;
  }

  function showCode(c, color) {
    modal(function (sheet, close) {
      sheet.className = 'gt-sheet gt-codebox';
      var top = el('div', 'gt-codebox-top');
      top.appendChild(el('span', null, c.name || '수업'));
      top.appendChild(iconButton('close', '닫기', close));
      sheet.appendChild(top);
      var code = el('div', 'gt-codebox-code', c.enrollmentCode);
      code.style.color = color;
      sheet.appendChild(code);
      var qr = el('div', 'gt-qr');
      sheet.appendChild(qr);
      qrInto(qr, 'https://classroom.google.com/c/' + c.id + '?cjc=' + c.enrollmentCode);
      sheet.appendChild(el('p', null, '학생: 클래스룸 → [+] → 수업 참여하기 → 이 코드를 입력하거나 QR 을 찍으세요.'));
    });
  }

  /** 첨부(원래 클래스룸의 테두리 카드: 아이콘 · 제목 · 종류) */
  function attachments(materials) {
    var row = el('div', 'gt-cr-attach');
    (materials || []).forEach(function (m) {
      var card;
      var file = m.driveFile && m.driveFile.driveFile;
      if (file) {
        card = attachCard('file', file.title || '드라이브 파일', 'Google Drive', function () {
          toast('«' + (file.title || '파일') + '» 을(를) 받는 중입니다…');
          Promise.resolve(host.call('drive_open', file.id)).then(function (r) { if (r && r.ok === false) toast(r.error || '열지 못했습니다.', true); });
        });
      } else if (m.youtubeVideo) {
        card = attachCard('video', m.youtubeVideo.title || 'YouTube', 'YouTube 동영상', function () { host.call('open_web', m.youtubeVideo.alternateLink, m.youtubeVideo.title || ''); });
      } else if (m.link) {
        card = attachCard('link', m.link.title || m.link.url, (m.link.url || '').replace(/^https?:\/\//, '').split('/')[0], function () { host.call('open_web', m.link.url, m.link.title || ''); });
      } else if (m.form) {
        card = attachCard('assignment', m.form.title || '설문지', 'Google 설문지', function () { host.call('open_web', m.form.formUrl, m.form.title || ''); });
      }
      if (card) row.appendChild(card);
    });
    return row.children.length ? row : null;
  }
  function attachCard(kind, title, sub, onClick) {
    var b = button('', 'gt-cr-attach-card', onClick);
    var ic = el('span', 'gt-cr-attach-ic ' + kind);
    ic.appendChild(icon(kind));
    b.appendChild(ic);
    var t = el('span', 'gt-cr-attach-text');
    t.appendChild(el('strong', null, title));
    t.appendChild(el('span', null, sub));
    b.appendChild(t);
    return b;
  }

  // ══ 슬라이드 ════════════════════════════════════════════════
  function slidesHome(term) {
    var token = ++current.token;
    frame([button('새로고침', 'gt-btn', function () { slidesHome(term); })]);
    var search = el('label', 'gt-gsearch');
    search.appendChild(icon('search'));
    var input = el('input');
    input.type = 'search';
    input.placeholder = '검색';
    input.value = term || '';
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') slidesHome(input.value.trim()); });
    search.appendChild(input);
    var center = el('div', 'gt-appbar-center');
    center.appendChild(search);
    var page = el('div', 'gt-sl-home');
    var head = el('div', 'gt-sl-head');
    head.appendChild(el('h3', null, term ? '«' + term + '» 검색 결과' : '최근 프레젠테이션'));
    page.appendChild(head);
    var grid = el('div', 'gt-sl-grid');
    page.appendChild(grid);
    fill(parts.body, [appBar('icons/google/slides.png', '프레젠테이션', null, center), page]);
    fill(grid, [el('div', 'gt-empty', '불러오는 중…')]);
    var q = "(mimeType='application/vnd.google-apps.presentation' or mimeType='" + PPTX + "') and trashed=false";
    if (term) q += " and name contains '" + term.replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
    g('GET', DRIVE + '/files?q=' + enc(q) + '&orderBy=' + enc('modifiedTime desc') + '&pageSize=60' +
      '&fields=' + enc('files(id,name,mimeType,modifiedTime,thumbnailLink,owners(displayName))') + '&supportsAllDrives=true&includeItemsFromAllDrives=true')
      .then(function (data) {
        if (token !== current.token) return;
        var files = data.files || [];
        if (!files.length) { fill(grid, [el('div', 'gt-empty', term ? '검색 결과가 없습니다.' : '드라이브에 프레젠테이션이 없습니다.')]); return; }
        fill(grid, files.map(function (f) {
          var card = button('', 'gt-sl-card', function () {
            if (f.mimeType === PPTX) {
              toast('«' + f.name + '» 을(를) 받아 PowerPoint 로 엽니다…');
              Promise.resolve(host.call('drive_open', f.id)).then(function (r) { if (r && r.ok === false) toast(r.error || '열지 못했습니다.', true); });
            } else {
              slidesEditor(f, term);
            }
          });
          var thumb = el('span', 'gt-sl-thumb');
          if (f.thumbnailLink) {
            var img = new Image();
            img.alt = '';
            img.referrerPolicy = 'no-referrer';
            img.onerror = function () { thumb.removeChild(img); };
            img.src = f.thumbnailLink;
            thumb.appendChild(img);
          }
          card.appendChild(thumb);
          var info = el('span', 'gt-sl-info');
          info.appendChild(el('strong', null, f.name));
          var meta = el('span', 'gt-sl-meta');
          var mini = el('img');
          mini.alt = '';
          mini.src = f.mimeType === PPTX ? 'icons/programs/powerpoint.png' : 'icons/google/slides.png';
          meta.appendChild(mini);
          meta.appendChild(el('span', null, when(f.modifiedTime) + ' 수정'));
          info.appendChild(meta);
          card.appendChild(info);
          return card;
        }));
      }).catch(function (e) { if (token === current.token) fill(grid, [el('div', 'gt-empty error', e.message)]); });
  }

  /** 원래 슬라이드 편집 화면처럼(보기만) — 왼쪽 필름 띠 · 가운데 큰 슬라이드 · 오른쪽 위 [슬라이드쇼] */
  function slidesEditor(file, term) {
    var token = ++current.token;
    frame([button('웹으로 열기', 'gt-btn', function () { host.call('open_web', 'https://docs.google.com/presentation/d/' + file.id + '/edit', file.name); })],
      { label: '프레젠테이션 목록', go: function () { slidesHome(term); } });
    loading('프레젠테이션을 여는 중…');
    g('GET', SLIDES + '/presentations/' + enc(file.id) + '?fields=' + enc('title,slides(objectId)')).then(function (p) {
      if (token !== current.token) return;
      var slides = p.slides || [];
      if (!slides.length) { fill(parts.body, [el('div', 'gt-empty', '슬라이드가 없습니다.')]); return; }
      var deck = { file: file, slides: slides, urls: {}, index: 0 };
      var right = el('div', 'gt-appbar-right');
      var show = button('', 'gt-sl-show', function () { startPresent(deck, deck.index); });
      show.appendChild(icon('play'));
      show.appendChild(el('span', null, '슬라이드쇼'));
      right.appendChild(show);
      var bar = appBar('icons/google/slides.png', p.title || file.name, null, null, right, 'gt-sl-bar');
      var layout = el('div', 'gt-sl-editor');
      var strip = el('nav', 'gt-sl-strip');
      var stage = el('div', 'gt-sl-stage');
      var big = el('img', 'gt-sl-big');
      big.alt = '';
      big.referrerPolicy = 'no-referrer';
      stage.appendChild(big);
      layout.appendChild(strip);
      layout.appendChild(stage);
      fill(parts.body, [bar, layout]);
      var thumbs = slides.map(function (s, i) {
        var b = button('', 'gt-sl-film', function () { pick(i); });
        b.appendChild(el('span', 'num', String(i + 1)));
        var frameEl = el('span', 'gt-sl-film-img');
        b.appendChild(frameEl);
        strip.appendChild(b);
        return { button: b, frame: frameEl };
      });
      // 필름 띠는 앞에서부터 차례로(한꺼번에 부르지 않는다)
      var next = 0;
      function loadNext() {
        if (token !== current.token || next >= slides.length) return;
        var i = next++;
        slideUrl(deck, i).then(function (u) {
          var im = new Image();
          im.alt = '';
          im.referrerPolicy = 'no-referrer';
          im.src = u;
          fill(thumbs[i].frame, [im]);
        }).catch(function () {}).then(loadNext);
      }
      loadNext();
      loadNext();
      function pick(i) {
        deck.index = i;
        thumbs.forEach(function (t, n) { t.button.classList.toggle('on', n === i); });
        big.classList.add('loading');
        slideUrl(deck, i).then(function (u) { if (deck.index === i) { big.src = u; big.classList.remove('loading'); } })
          .catch(function (e) { toast(e.message, true); });
      }
      pick(0);
    }).catch(function (e) {
      if (token !== current.token) return;
      var info = e.info || {};
      if (info.reason === 'disabled') {
        var box = el('div', 'gt-empty error');
        box.appendChild(el('p', null, message(info)));
        box.appendChild(button('PowerPoint 로 열기', 'gt-btn', function () { host.call('drive_open', file.id); }));
        fill(parts.body, [box]);
      } else {
        failed(e, function () { slidesEditor(file, term); });
      }
    });
  }

  function slideUrl(deck, i) {
    if (!deck.urls[i]) {
      deck.urls[i] = g('GET', SLIDES + '/presentations/' + enc(deck.file.id) + '/pages/' + enc(deck.slides[i].objectId) +
        '/thumbnail?thumbnailProperties.thumbnailSize=LARGE').then(function (r) { return r.contentUrl; });
      deck.urls[i].catch(function () { delete deck.urls[i]; });
    }
    return deck.urls[i];
  }

  function startPresent(deck, at) {
    present = deck;
    parts.presenter.hidden = false;
    host.fullscreen(true);
    showSlide(at || 0);
  }

  function showSlide(i) {
    var p = present;
    if (!p) return;
    i = Math.max(0, Math.min(p.slides.length - 1, i));
    p.index = i;
    parts.pCount.textContent = (i + 1) + ' / ' + p.slides.length;
    parts.pPrev.disabled = i === 0;
    parts.pNext.disabled = i === p.slides.length - 1;
    parts.pImg.classList.add('loading');
    slideUrl(p, i).then(function (url) {
      if (present !== p || p.index !== i) return;
      parts.pImg.src = url;
      parts.pImg.classList.remove('loading');
      [i + 1, i + 2].forEach(function (n) {
        if (n < p.slides.length) slideUrl(p, n).then(function (u) { var im = new Image(); im.src = u; }).catch(function () {});
      });
    }).catch(function (e) { if (present === p) toast(e.message, true); });
  }

  function closePresenter() {
    if (!present) return;
    present = null;
    parts.presenter.hidden = true;
    parts.pImg.removeAttribute('src');
    host.fullscreen(false);
  }

  // ══ 설문지 ═════════════════════════════════════════════════
  function formsHome() {
    var token = ++current.token;
    frame([button('새로고침', 'gt-btn', formsHome)]);
    loading();
    var q = "mimeType='application/vnd.google-apps.form' and trashed=false";
    g('GET', DRIVE + '/files?q=' + enc(q) + '&orderBy=' + enc('modifiedTime desc') + '&pageSize=60' +
      '&fields=' + enc('files(id,name,modifiedTime,thumbnailLink)') + '&supportsAllDrives=true&includeItemsFromAllDrives=true')
      .then(function (data) {
        if (token !== current.token) return;
        var files = data.files || [];
        var page = el('div', 'gt-sl-home gt-fm-home');
        page.appendChild(el('h3', 'gt-sl-head', '최근 설문지'));
        if (!files.length) page.appendChild(el('div', 'gt-empty', '드라이브에 설문지가 없습니다.'));
        var grid = el('div', 'gt-sl-grid');
        files.forEach(function (f) {
          var card = button('', 'gt-sl-card gt-fm-file', function () { formView(f, 'responses'); });
          var thumb = el('span', 'gt-sl-thumb gt-fm-thumb');
          if (f.thumbnailLink) {
            var img = new Image();
            img.alt = '';
            img.referrerPolicy = 'no-referrer';
            img.onerror = function () { thumb.removeChild(img); };
            img.src = f.thumbnailLink;
            thumb.appendChild(img);
          }
          card.appendChild(thumb);
          var info = el('span', 'gt-sl-info');
          info.appendChild(el('strong', null, f.name));
          var meta = el('span', 'gt-sl-meta');
          var mini = el('img');
          mini.alt = '';
          mini.src = 'icons/google/forms.png';
          meta.appendChild(mini);
          meta.appendChild(el('span', null, when(f.modifiedTime) + ' 수정'));
          info.appendChild(meta);
          card.appendChild(info);
          grid.appendChild(card);
        });
        page.appendChild(grid);
        fill(parts.body, [appBar('icons/google/forms.png', '설문지', null, null, null, 'gt-fm-bar'), page]);
      }).catch(function (e) { if (token === current.token) failed(e, formsHome); });
  }

  function answersOf(responses, questionId) {
    var out = [];
    responses.forEach(function (r) {
      var a = r.answers && r.answers[questionId];
      var list = a && a.textAnswers && a.textAnswers.answers;
      if (list) list.forEach(function (x) { if (x.value != null) out.push(String(x.value)); });
    });
    return out;
  }

  /** 원래 설문지처럼 — 보라 띠 · 가운데 [질문 | 응답] 탭 · 오른쪽 [보내기]. 응답은 15초마다 */
  function formView(f, tab) {
    var token = ++current.token;
    var active = tab || 'responses';
    var form = null;
    var responses = [];
    var editUrl = 'https://docs.google.com/forms/d/' + f.id + '/edit';
    frame([button('새로고침', 'gt-btn', function () { refresh(true); }), button('웹으로 열기', 'gt-btn', function () { host.call('open_web', editUrl, f.name); })],
      { label: '설문 목록', go: formsHome });
    loading();
    g('GET', FORMS + '/forms/' + enc(f.id)).then(function (data) {
      if (token !== current.token) return;
      form = data;
      render();
      refresh(false);
      stopTimer();
      current.timer = setInterval(function () { if (token === current.token) refresh(false); else stopTimer(); }, 15000);
    }).catch(function (e) { if (token === current.token) failed(e, function () { formView(f, active); }); });

    function readAll(pageToken, acc, rounds) {
      var url = FORMS + '/forms/' + enc(f.id) + '/responses?pageSize=5000' + (pageToken ? '&pageToken=' + enc(pageToken) : '');
      return g('GET', url).then(function (r) {
        acc = acc.concat(r.responses || []);
        return r.nextPageToken && rounds < 5 ? readAll(r.nextPageToken, acc, rounds + 1) : acc;
      });
    }
    function refresh(say) {
      if (!form) return;
      readAll(null, [], 0).then(function (list) {
        if (token !== current.token) return;
        var changed = list.length !== responses.length;
        responses = list;
        if (changed || say) render();
        if (say) toast('응답 ' + list.length + '개');
      }).catch(function (e) { if (token === current.token) toast(e.message, true); });
    }

    function render() {
      if (token !== current.token || !form) return;
      var scroll = parts.body.scrollTop;
      var right = el('div', 'gt-appbar-right');
      var send = button('보내기', 'gt-fm-send', sendBox);
      right.appendChild(send);
      var tabs = tabStrip([['questions', '질문'], ['responses', '응답 ' + responses.length]], active, '#673ab7', function (t) { active = t; render(); });
      var bar = appBar('icons/google/forms.png', (form.info && (form.info.documentTitle || form.info.title)) || f.name, null, tabs, right, 'gt-fm-bar');
      var page = el('div', 'gt-fm-page');
      var col = el('div', 'gt-fm-col');
      if (active === 'questions') questions(col);
      else summary(col);
      page.appendChild(col);
      fill(parts.body, [bar, page]);
      parts.body.scrollTop = scroll;
    }

    function sendBox() {
      modal(function (sheet, close) {
        sheet.className = 'gt-sheet gt-fm-sendbox';
        var top = el('div', 'gt-codebox-top');
        top.appendChild(el('h3', null, '설문지 보내기'));
        top.appendChild(iconButton('close', '닫기', close));
        sheet.appendChild(top);
        sheet.appendChild(el('p', null, '학생 휴대폰 카메라로 찍으면 응답 화면이 열립니다.'));
        var qr = el('div', 'gt-qr');
        sheet.appendChild(qr);
        if (form.responderUri) {
          qrInto(qr, form.responderUri);
          sheet.appendChild(el('div', 'gt-fm-link', form.responderUri));
        }
      });
    }

    function header() {
      var head = el('section', 'gt-fm-card gt-fm-titlecard');
      head.appendChild(el('h1', null, (form.info && form.info.title) || f.name));
      if (form.info && form.info.description) head.appendChild(el('p', null, form.info.description));
      return head;
    }

    function questions(col) {
      col.appendChild(header());
      (form.items || []).forEach(function (item) {
        var card = el('section', 'gt-fm-card');
        card.appendChild(el('h4', null, item.title || ''));
        if (item.description) card.appendChild(el('p', 'gt-fm-desc', item.description));
        var q = item.questionItem && item.questionItem.question;
        if (q && q.choiceQuestion) {
          var type = q.choiceQuestion.type;
          (q.choiceQuestion.options || []).forEach(function (o) {
            var row = el('div', 'gt-fm-option');
            row.appendChild(el('span', type === 'CHECKBOX' ? 'gt-fm-check' : type === 'DROP_DOWN' ? 'gt-fm-num' : 'gt-fm-radio'));
            row.appendChild(el('span', null, o.value || (o.isOther ? '기타…' : '')));
            card.appendChild(row);
          });
        } else if (q && q.scaleQuestion) {
          var scale = el('div', 'gt-fm-scale');
          if (q.scaleQuestion.lowLabel) scale.appendChild(el('span', 'label', q.scaleQuestion.lowLabel));
          for (var v = q.scaleQuestion.low || 1; v <= (q.scaleQuestion.high || 5); v++) {
            var cell = el('span', 'cell');
            cell.appendChild(el('span', null, String(v)));
            cell.appendChild(el('span', 'gt-fm-radio'));
            scale.appendChild(cell);
          }
          if (q.scaleQuestion.highLabel) scale.appendChild(el('span', 'label', q.scaleQuestion.highLabel));
          card.appendChild(scale);
        } else if (q && q.textQuestion) {
          card.appendChild(el('div', 'gt-fm-line', q.textQuestion.paragraph ? '장문형 텍스트' : '단답형 텍스트'));
        } else if (q) {
          card.appendChild(el('div', 'gt-fm-line', '응답'));
        } else if (item.textItem || item.pageBreakItem) {
          card.className += ' gt-fm-section';
        }
        col.appendChild(card);
      });
    }

    function summary(col) {
      var top = el('section', 'gt-fm-card gt-fm-count');
      var left = el('div');
      left.appendChild(el('h2', null, '응답 ' + responses.length + '개'));
      left.appendChild(el('span', 'gt-fm-live', '● 응답을 받는 중 · 15초마다 새로 고침'));
      top.appendChild(left);
      var qr = el('button', 'gt-fm-qr');
      qr.type = 'button';
      qr.title = '크게 보기';
      qr.addEventListener('click', sendBox);
      if (form.responderUri) qrInto(qr, form.responderUri);
      top.appendChild(qr);
      col.appendChild(top);
      if (!responses.length) {
        col.appendChild(el('section', 'gt-fm-card gt-fm-wait', '응답을 기다리는 중입니다. [보내기]의 QR 을 학생들이 찍게 하세요.'));
        return;
      }
      (form.items || []).forEach(function (item) {
        var q = item.questionItem && item.questionItem.question;
        if (!q) return;
        var card = el('section', 'gt-fm-card');
        card.appendChild(el('h4', null, item.title || '질문'));
        var answers = answersOf(responses, q.questionId);
        card.appendChild(el('span', 'gt-fm-n', '응답 ' + answers.length + '개'));
        if (q.choiceQuestion && q.choiceQuestion.type !== 'CHECKBOX') card.appendChild(pie(options(q), answers));
        else if (q.choiceQuestion) card.appendChild(hbars(options(q), answers, responses.length));
        else if (q.scaleQuestion) card.appendChild(vbars(options(q), answers));
        else card.appendChild(texts(answers));
        col.appendChild(card);
      });
    }
  }

  function options(q) {
    if (q.scaleQuestion) {
      var out = [];
      for (var v = q.scaleQuestion.low || 1; v <= (q.scaleQuestion.high || 5); v++) out.push(String(v));
      return out;
    }
    return (q.choiceQuestion.options || []).map(function (o) { return o.value || '기타'; });
  }
  function counted(opts, answers) {
    var counts = opts.map(function () { return 0; });
    var other = 0;
    answers.forEach(function (a) { var i = opts.indexOf(a); if (i >= 0) counts[i]++; else other++; });
    var labels = opts.slice();
    if (other) { labels.push('기타'); counts.push(other); }
    return { labels: labels, counts: counts };
  }

  /** 원형 차트(객관식 · 드롭다운) — 설문지 요약과 같은 모양 */
  function pie(opts, answers) {
    var data = counted(opts, answers);
    var total = data.counts.reduce(function (a, b) { return a + b; }, 0) || 1;
    var wrap = el('div', 'gt-fm-pie');
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '-1.05 -1.05 2.1 2.1');
    svg.setAttribute('class', 'gt-fm-piesvg');
    var angle = -Math.PI / 2;
    data.counts.forEach(function (n, i) {
      if (!n) return;
      var frac = n / total;
      var color = CHART[i % CHART.length];
      if (frac >= 0.9999) {
        var circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('r', '1');
        circle.setAttribute('fill', color);
        svg.appendChild(circle);
      } else {
        var a2 = angle + frac * 2 * Math.PI;
        var path = document.createElementNS(ns, 'path');
        path.setAttribute('d', 'M0 0 L' + Math.cos(angle) + ' ' + Math.sin(angle) + ' A1 1 0 ' + (frac > 0.5 ? 1 : 0) + ' 1 ' + Math.cos(a2) + ' ' + Math.sin(a2) + ' Z');
        path.setAttribute('fill', color);
        path.setAttribute('stroke', '#fff');
        path.setAttribute('stroke-width', '0.01');
        svg.appendChild(path);
        if (frac > 0.06) {
          var mid = (angle + a2) / 2;
          var t = document.createElementNS(ns, 'text');
          t.setAttribute('x', String(Math.cos(mid) * 0.62));
          t.setAttribute('y', String(Math.sin(mid) * 0.62 + 0.04));
          t.setAttribute('class', 'gt-fm-pielabel');
          t.textContent = (frac * 100).toFixed(1) + '%';
          svg.appendChild(t);
        }
        angle = a2;
      }
    });
    wrap.appendChild(svg);
    var legend = el('ul', 'gt-fm-legend');
    data.labels.forEach(function (label, i) {
      var li = el('li');
      var dot = el('span', 'dot');
      dot.style.background = CHART[i % CHART.length];
      li.appendChild(dot);
      li.appendChild(el('span', null, label));
      li.appendChild(el('b', null, String(data.counts[i])));
      legend.appendChild(li);
    });
    wrap.appendChild(legend);
    return wrap;
  }

  /** 가로 막대(체크박스) — 각 항목을 고른 사람 수 / 응답자 수 */
  function hbars(opts, answers, people) {
    var data = counted(opts, answers);
    var wrap = el('div', 'gt-fm-hbars');
    var max = Math.max.apply(null, data.counts.concat([1]));
    data.labels.forEach(function (label, i) {
      var row = el('div', 'gt-fm-hrow');
      row.appendChild(el('span', 'name', label));
      var track = el('span', 'track');
      var bar = el('span', 'bar');
      bar.style.width = (data.counts[i] / max * 100) + '%';
      track.appendChild(bar);
      row.appendChild(track);
      row.appendChild(el('span', 'num', data.counts[i] + ' (' + Math.round(data.counts[i] / Math.max(1, people) * 100) + '%)'));
      wrap.appendChild(row);
    });
    return wrap;
  }

  /** 세로 막대(선형 배율) */
  function vbars(opts, answers) {
    var data = counted(opts, answers);
    var wrap = el('div', 'gt-fm-vbars');
    var max = Math.max.apply(null, data.counts.concat([1]));
    data.labels.forEach(function (label, i) {
      var col = el('div', 'gt-fm-vcol');
      col.appendChild(el('span', 'num', String(data.counts[i])));
      var bar = el('span', 'bar');
      bar.style.height = Math.max(2, data.counts[i] / max * 100) + '%';
      col.appendChild(bar);
      col.appendChild(el('span', 'name', label));
      wrap.appendChild(col);
    });
    return wrap;
  }

  /** 글 답(단답·장문) — 회색 상자들 */
  function texts(answers) {
    var wrap = el('div', 'gt-fm-texts');
    if (!answers.length) { wrap.appendChild(el('p', 'gt-cr-muted', '아직 응답이 없습니다.')); return wrap; }
    answers.slice(-30).reverse().forEach(function (a) { wrap.appendChild(el('div', 'gt-fm-text', a)); });
    if (answers.length > 30) wrap.appendChild(el('span', 'gt-cr-muted', '최근 30개 · 모두 ' + answers.length + '개'));
    return wrap;
  }

  // ── 틀 만들기 ─────────────────────────────────────────────
  function mount(container, adapter) {
    host = adapter;
    root = container;
    root.className = 'gt';
    parts.body = el('main', 'gt-body');
    var bar = el('footer', 'gt-footer');
    bar.appendChild(button('← 수업 화면', 'gt-btn', function () { stopTimer(); closePresenter(); host.close(); }));
    parts.tabs = el('div', 'gt-tabs');
    TABS.forEach(function (t) {
      var b = button('', 'gt-tab', function () { open(t[0]); });
      var img = el('img');
      img.alt = '';
      img.src = t[2];
      b.appendChild(img);
      b.appendChild(el('span', null, t[1]));
      b.setAttribute('data-tab', t[0]);
      parts.tabs.appendChild(b);
    });
    bar.appendChild(parts.tabs);
    bar.appendChild(el('span', 'gt-spacer'));
    parts.actions = el('div', 'gt-actions');
    bar.appendChild(parts.actions);
    parts.toast = el('div', 'gt-toast');
    parts.toast.hidden = true;

    // 슬라이드쇼 — 원래 슬라이드처럼 검은 화면 · 왼쪽 아래 조작 막대. 화면 왼쪽 1/3 누르면 앞으로, 나머지는 다음으로
    parts.presenter = el('div', 'gt-present');
    parts.presenter.hidden = true;
    parts.pImg = el('img', 'gt-slide');
    parts.pImg.alt = '';
    parts.pImg.referrerPolicy = 'no-referrer';
    var stage = el('div', 'gt-stage');
    stage.appendChild(parts.pImg);
    stage.addEventListener('click', function (e) {
      if (!present) return;
      var rect = stage.getBoundingClientRect();
      showSlide(present.index + (e.clientX - rect.left < rect.width / 3 ? -1 : 1));
    });
    var pbar = el('div', 'gt-pbar');
    parts.pPrev = iconButton('left', '이전 슬라이드', function () { if (present) showSlide(present.index - 1); }, 'dark');
    parts.pCount = el('span', 'gt-pcount');
    parts.pNext = iconButton('right', '다음 슬라이드', function () { if (present) showSlide(present.index + 1); }, 'dark');
    pbar.appendChild(parts.pPrev);
    pbar.appendChild(parts.pCount);
    pbar.appendChild(parts.pNext);
    var end = button('슬라이드쇼 종료', 'gt-pend', closePresenter);
    pbar.appendChild(end);
    parts.presenter.appendChild(stage);
    parts.presenter.appendChild(pbar);
    var startX = null;
    stage.addEventListener('touchstart', function (e) { startX = e.touches[0].clientX; }, { passive: true });
    stage.addEventListener('touchend', function (e) {
      if (startX == null || !present) return;
      var dx = e.changedTouches[0].clientX - startX;
      startX = null;
      if (Math.abs(dx) > 60) { e.preventDefault(); showSlide(present.index + (dx < 0 ? 1 : -1)); }
    });
    document.addEventListener('keydown', function (e) {
      if (!present) return;
      if (['ArrowRight', 'PageDown', ' ', 'Enter'].indexOf(e.key) >= 0) { e.preventDefault(); showSlide(present.index + 1); }
      else if (['ArrowLeft', 'PageUp', 'Backspace'].indexOf(e.key) >= 0) { e.preventDefault(); showSlide(present.index - 1); }
      else if (e.key === 'Escape') closePresenter();
    });

    fill(root, [parts.body, bar, parts.presenter, parts.toast]);
  }

  /** 뒤로(안드로이드 뒤로 단추) — 처리했으면 true */
  function back() {
    var modalEl = root && root.querySelector('.gt-modal');
    if (modalEl) { root.removeChild(modalEl); return true; }
    if (present) { closePresenter(); return true; }
    if (current.back) { current.back.go(); return true; }
    return false;
  }

  /** 수업이 끝났다 — 보던 것을 비운다 */
  function reset() {
    stopTimer();
    closePresenter();
    current.token++;
    profiles = {};
    if (parts.body) fill(parts.body, []);
  }

  window.GTools = { mount: mount, open: open, back: back, reset: reset };
})();
