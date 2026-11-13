// 구글 수업 도구 창(Windows) — gtools.js 에 이 프로그램(pywebview api)을 이어 준다.
'use strict';

const api = () => window.pywebview && window.pywebview.api;

window.addEventListener('pywebviewready', async () => {
  window.GTools.mount(document.getElementById('gt-root'), {
    call: (name, ...args) => api()[name](...args),
    close: () => api().close_gtools(),
    fullscreen: (on) => api().gtools_fullscreen(!!on),
  });
  const tab = await api().gtools_tab();
  window.GTools.open(tab || 'classroom');
});
