"""학생판 자동 로그인 — Playwright 없이 **프로그램 안 창(WebView2)** 에서 로그인 폼을 채운다.

교사판은 Playwright 가 디버깅 통로로 붙어 로그인한다(`portal.login_riro`·`login_aiep`). 학생판은
실행 파일을 가볍게 하려고 Playwright 를 넣지 않고 디버깅 통로도 열지 않는다. 그래서 창에 직접
작은 스크립트를 넣어 사람이 하는 순서대로 누른다 (2026-10-12 요청).

    리로스쿨  로그인 화면 → 「학생 · 교사」 탭 → 아이디·비밀번호 → 로그인
    전북 AIEP  첫 화면 → 공지 닫기 → 「학생」 → (통합 인증) 아이디·비밀번호 → 로그인

🚨 **비밀번호는 한 번만 넣는다.** 리로스쿨은 5번 틀리면 계정을 잠근다. 넣은 뒤에도 폼이 그대로면
틀린 것으로 보고 멈춘다 — 창은 남겨 학생이 직접 고치게 한다.
🚨 **비밀번호는 정해 둔 주소에서만 넣는다.** 창이 다른 곳으로 넘어가 있으면 넣지 않는다.
"""
from __future__ import annotations

import json
import threading
import time
from urllib.parse import urlsplit

from . import portal

START_URL = {'riro': portal.RIRO_URL, 'aiep': portal.AIEP_HOME}
FORM_HOST = {'riro': urlsplit(portal.RIRO_URL).hostname, 'aiep': 'ai-auth.jbedu.kr'}
AIEP_ROLE = '학생'
TIMEOUT = 90.0          # 이만큼(초) 지나도 끝나지 않으면 손을 뗀다. 창은 그대로 둔다
POLL = 0.7              # 화면을 다시 보는 간격 (초)
WRONG_AFTER = 8.0       # 넣은 뒤 폼이 이만큼(초) 그대로면 아이디·비밀번호가 틀린 것으로 본다
EVAL_WAIT = 6.0         # 스크립트 하나가 이만큼(초) 안에 돌아오지 않으면 (알림창 등) 버린다
ROLE_TRIES = 3          # AIEP 첫 화면에서 「학생」 을 누르는 횟수 상한

_HELPERS = r"""
  const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const text = () => (document.body ? document.body.innerText : '').replace(/\s+/g, ' ');
  const press = el => {
    const r = el.getBoundingClientRect();
    for (const t of ['mousedown', 'mouseup', 'click'])
      el.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window,
        clientX: r.left + r.width / 2, clientY: r.top + r.height / 2}));
  };
  const put = (el, value) => {
    el.focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    el.blur();
  };
"""

# 화면이 어디까지 왔는지 본다. 자격증명은 들어 있지 않다. 돌려주는 값:
#   signed-in · form(아이디 칸이 보임) · moving(다음 화면으로 누름) · wait · away(엉뚱한 곳)
_STEP = {
    'riro': "(() => {" + _HELPERS + r"""
  if (location.hostname !== %(host)s) return 'away';
  const words = text();
  if (!/로그인이 필요합니다|접근 가능한 메뉴가 없습니다/.test(words) && /로그아웃/.test(words)) return 'signed-in';
  return vis(document.querySelector('#id')) && vis(document.querySelector('#pw')) ? 'form' : 'wait';
})()""",
    'aiep': "(() => {" + _HELPERS + r"""
  const host = location.hostname;
  if (host === %(host)s) {
    if (vis(document.querySelector('#id')) && vis(document.querySelector('#pw, #password'))) return 'form';
    const link = document.querySelector('a.certify-type-user');     // 「사용자 로그인」 고르는 화면
    if (vis(link)) { press(link); return 'moving'; }
    return 'wait';
  }
  if (host !== 'ai.jbedu.kr') return 'away';
  const words = text();
  const landing = words.includes('회원가입') && words.includes('아이디 찾기');
  if (!landing) return /로그아웃|마이페이지|내 정보/.test(words) ? 'signed-in' : 'wait';
  if (!%(press_role)s) return 'wait';
  const all = [...document.querySelectorAll('div,span,button,a')].filter(vis);
  const close = all.find(e => e.children.length === 0 && (e.textContent || '').trim() === '닫기');
  if (close) press(close);                                            // 공지 팝업 (없을 때도 있다)
  const compact = e => (e.textContent || '').replace(/\s+/g, '');
  const role = document.querySelector('.cl-button.student')
    || all.find(e => compact(e) === %(role)s && ![...e.children].some(c => compact(c) === %(role)s));
  if (!vis(role)) return 'wait';
  press(role);
  return 'moving';
})()""",
}

# 아이디·비밀번호를 넣고 로그인을 누른다. 주소를 다시 확인한 뒤에만 넣는다.
_FILL = {
    'riro': "((c) => {" + _HELPERS + r"""
  if (location.hostname !== c.host) return 'away';
  const tab = document.getElementById('first');                       // 「학생 · 교사」 (학부모 아님)
  if (tab && !tab.classList.contains('on')) tab.click();
  const id = document.querySelector('#id'), pw = document.querySelector('#pw');
  if (!vis(id) || !vis(pw)) return 'no-form';
  put(id, c.id); put(pw, c.pw);
  // `로그인` 단추가 여럿이다 — 숨은 재로그인·세션연장 팝업 것을 빼고 보이는 것만
  const button = [...document.querySelectorAll('button.button_normal, button')]
    .find(b => vis(b) && (b.textContent || '').trim() === '로그인');
  if (!button) return 'no-button';
  button.click();
  return 'submitted';
})(%(cred)s)""",
    'aiep': "((c) => {" + _HELPERS + r"""
  if (location.hostname !== c.host) return 'away';
  const id = document.querySelector('#id'), pw = document.querySelector('#pw, #password');
  if (!vis(id) || !vis(pw)) return 'no-form';
  put(id, c.id); put(pw, c.pw);
  const button = document.querySelector('#submitBtn, button.login-btn');
  if (!vis(button)) return 'no-button';
  button.click();                    // 폼 submit → 화면 스크립트가 숨은 email 칸을 채워 보낸다
  return 'submitted';
})(%(cred)s)""",
}


def step_script(target: str, press_role: bool = True) -> str:
    return _STEP[target] % {'host': json.dumps(FORM_HOST[target]), 'role': json.dumps(AIEP_ROLE, ensure_ascii=False),
                            'press_role': 'true' if press_role else 'false'}


def fill_script(target: str, user: str, password: str) -> str:
    return _FILL[target] % {'cred': json.dumps({'host': FORM_HOST[target], 'id': clean_id(target, user),
                                                'pw': password}, ensure_ascii=False)}


def clean_id(target: str, user: str) -> str:
    """AIEP 아이디 칸은 `@ai.jbedu.kr` 앞부분만 받는다. 전체 주소로 저장해 두었어도 꼬리를 뗀다."""
    name = (user or '').strip()
    if target == 'aiep' and name.lower().endswith(portal.AIEP_SUFFIX):
        name = name[:-len(portal.AIEP_SUFFIX)]
    return name


def _host(window) -> str:
    try:
        return urlsplit(window.get_current_url() or '').hostname or ''
    except Exception:
        return ''


def _evaluate(window, script: str, wait: float = EVAL_WAIT):
    """창에서 스크립트를 돌린다. 알림창이 떠 있으면 돌아오지 않으므로 기다리는 시간을 둔다."""
    box = {}

    def run():
        try:
            box['value'] = window.evaluate_js(script)
        except Exception as exc:
            box['error'] = exc
    worker = threading.Thread(target=run, daemon=True, name='desk-signin-eval')
    worker.start()
    worker.join(wait)
    if worker.is_alive():
        raise TimeoutError('창이 응답하지 않습니다 (알림창이 떠 있을 수 있습니다).')
    if 'error' in box:
        raise box['error']
    return box.get('value')


def drive(window, target: str, user: str, password: str, closed: threading.Event,
          progress=lambda message: None, timeout: float = TIMEOUT, poll: float = POLL,
          clock=time.monotonic, sleep=time.sleep) -> str:
    """창을 지켜보며 로그인까지 이끈다. 결과: signed-in · wrong · stuck · closed · timeout.

    `closed` 는 사용자가 창을 닫으면 켜진다. 무엇이 일어나도 창은 닫지 않는다.
    """
    if target not in _STEP:
        raise ValueError('자동 로그인을 지원하지 않는 서비스입니다.')
    end = clock() + timeout
    submitted_at = None
    form_since = None
    roles = 0
    stalls = 0
    while clock() < end:
        if closed.is_set():
            return 'closed'
        try:
            state = _evaluate(window, step_script(target, press_role=submitted_at is None and roles < ROLE_TRIES))
            stalls = 0
        except Exception:
            stalls += 1
            if stalls >= 3:
                return 'stuck'
            sleep(poll)
            continue
        if state == 'signed-in':
            return 'signed-in'
        if state == 'moving' and _host(window) != FORM_HOST[target]:
            roles += 1
            progress('로그인 화면으로 가는 중')
        if state == 'form':
            now = clock()
            if submitted_at is None:
                # 주소를 한 번 더 본다 — 폼 스크립트 안에서도 다시 본다
                if _host(window) != FORM_HOST[target]:
                    sleep(poll)
                    continue
                progress('아이디·비밀번호 넣는 중')
                try:
                    result = _evaluate(window, fill_script(target, user, password))
                except Exception:
                    return 'stuck'
                if result != 'submitted':
                    return 'stuck'
                submitted_at = now
                progress('로그인 중')
            else:
                form_since = form_since or now
                if now - form_since >= WRONG_AFTER:
                    return 'wrong'          # 🚨 다시 넣지 않는다 (리로스쿨 5회 잠금)
        else:
            form_since = None
        sleep(poll)
    return 'timeout'
