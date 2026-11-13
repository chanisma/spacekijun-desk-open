"""
나이스를 **데스크 안 창**에서 열고 인증서로 자동 로그인한다. 별도 실행 파일의 알맹이다.

## 데스크 본체와 무엇이 다른가

본체는 Edge 를 따로 띄우고 Playwright 로 조종한다. 여기서는 프로그램 안 창(pywebview,
WebView2)에 나이스를 직접 띄우고 **`evaluate_js` 로만** 다룬다. 브라우저 창이 따로 뜨지
않아 프로그램 하나로 끝난다.

2026-09-15 실측: WebView2 에서도 인증서 프로그램(`127.0.0.1:8443`)에 닿는다. 로딩 덮개가
걷히고 인증서 목록이 그대로 보였다. 어제 찾은 "이 장치에서 다른 앱 및 서비스에 액세스"
관문을 WebView2 도 지나지만, 여기서도 통과한다.

## 못 하는 것

**나이스 도우미 패널은 없다.** 패널은 Playwright 가 심고, 말을 화면으로 옮기는 일도
Playwright 로 누른다. 여기서는 그 손이 없다. 도우미가 필요하면 데스크 본체를 쓴다.

## 쓰는 법

    python app/neis_desk.py

설정은 데스크 본체와 같은 자격증명 저장소를 읽는다. 아이디와 인증서 암호를 먼저
데스크에서 저장해 두어야 한다.
"""
from __future__ import annotations

import json
import time

from core import portal, secretstore

TITLE = '나이스 · 스페이스기전'
READY_WAIT = 40.0        # 로그인 화면이 뜨기를 기다리는 시간
WIDGET_WAIT = 30.0       # 인증서 창이 뜨기를 기다리는 시간
SIGNED_WAIT = 40.0       # 로그인이 끝나기를 기다리는 시간
STEP = 0.4

# 인증서 암호 칸에 값을 넣는다. 그냥 `value` 를 바꾸면 위젯이 알아채지 못하는 판이 있어
# 네이티브 setter 로 넣고 입력 이벤트를 함께 보낸다.
_FILL_PASSWORD = """(function (pw) {
  var el = document.querySelector('input[name="certPassword"]');
  if (!el) return 'no-box';
  var setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
  el.focus();
  setter.call(el, pw);
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  return el.value.length === pw.length ? 'filled' : 'short';
})"""

_BUSY = """() => {
  const el = document.querySelector('.isloading-overlay');
  return !!(el && el.getClientRects().length);
}"""

_WIDGET_OPEN = """() => {
  const pw = document.querySelector('input[name="certPassword"]');
  return !!(pw && pw.getClientRects().length);
}"""

# 창 프로그램이라 콘솔이 없다. 무슨 일이 있었는지는 화면 위 띠로 알린다.
_BANNER = """(function (text) {
  var id = 'spacekijun-notice';
  var box = document.getElementById(id);
  if (!box) {
    box = document.createElement('div');
    box.id = id;
    box.setAttribute('style', 'position:fixed;left:0;right:0;top:0;z-index:2147483647;'
      + 'background:#30374d;color:#fff;font:13px/1.7 system-ui,sans-serif;'
      + 'padding:10px 16px;white-space:pre-wrap');
    box.addEventListener('click', function () { box.remove(); });
    (document.body || document.documentElement).appendChild(box);
  }
  box.textContent = text + '   (눌러서 닫기)';
  return true;
})"""


class DeskLoginError(RuntimeError):
    pass


def _call(window, source: str, argument=None):
    """`portal` 의 자바스크립트 조각을 그대로 불러 쓴다. 규칙을 두 벌 두지 않으려는 것이다."""
    payload = json.dumps(argument, ensure_ascii=False) if argument is not None else ''
    return window.evaluate_js(f'({source})({payload})')


def _truth(window, source: str) -> bool:
    """`() => ...` 꼴 판정식을 **불러서** 참거짓을 받는다.

    `evaluate_js` 는 식을 평가할 뿐이라 함수를 그대로 주면 함수 자체가 돌아온다.
    괄호로 감싸 불러야 한다 (2026-09-15: 이걸 빠뜨려 40초를 기다리다 실패했다).
    """
    return bool(window.evaluate_js(f'({source})()'))


def _wait(window, source: str, seconds: float, want=True) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            if _truth(window, source) == want:
                return True
        except Exception:
            pass                        # 화면이 바뀌는 중이면 잠시 못 읽는다
        time.sleep(STEP)
    return False


def sign_in(window, cred: dict, progress=lambda message: None) -> dict:
    """열려 있는 창에서 인증서 로그인을 끝낸다. 실패하면 창은 그대로 두고 알린다."""
    password = cred.get('cert_password') or ''
    if not password:
        raise DeskLoginError('설정에서 아이디와 인증서 암호를 먼저 저장해 주세요.')

    progress('나이스 화면 불러오는 중')
    if not _wait(window, portal.NEIS_READY, READY_WAIT):
        raise DeskLoginError('나이스 로그인 화면이 준비되지 않았습니다. 창을 확인해 주세요.')
    if _truth(window, portal.NEIS_SIGNED_IN):
        progress('이미 로그인되어 있습니다')
        return {'ok': True, 'already': True}

    progress('보안프로그램 준비 확인 중')
    if not _wait(window, _BUSY, READY_WAIT, want=False):
        raise DeskLoginError(portal.BUSY_HINT.format('나이스', READY_WAIT))

    progress('인증서 창 여는 중')
    for attempt in range(2):
        if not _call(window, portal._DOM_CLICK, {'selector': None, 'text': '인증서 로그인'}):
            raise DeskLoginError('[인증서 로그인] 버튼을 찾지 못했습니다.')
        if _wait(window, _WIDGET_OPEN, WIDGET_WAIT):
            break
        if attempt == 0:
            progress('인증서 창이 아직 안 떠 다시 눌러 봅니다')
    else:
        raise DeskLoginError(portal.CERT_HINT.format('나이스'))

    progress('인증서 고르는 중')
    picked = _pick(window, cred.get('cert_match'))

    progress('암호 넣는 중')
    filled = _call(window, _FILL_PASSWORD, password)
    if filled != 'filled':
        raise DeskLoginError('인증서 암호 칸에 넣지 못했습니다. 창에서 직접 입력해 주세요.')
    if not _call(window, portal._CLICK_OK, portal.KC['ok']):
        raise DeskLoginError('[확인] 단추를 누르지 못했습니다. 창에서 직접 눌러 주세요.')

    progress('인증서 확인 및 로그인 중')
    if not _wait(window, portal.NEIS_SIGNED_IN, SIGNED_WAIT):
        raise DeskLoginError('로그인이 끝나지 않았습니다. 창을 확인해 주세요.')
    return {'ok': True, 'picked': picked}


def _pick(window, cert_match) -> str:
    """인증서 목록이 다 찰 때까지 기다렸다가 고른다. 조건에 맞는 것이 하나일 때만 고른다."""
    end = time.time() + 15
    signature = None
    steady = None
    while time.time() < end:
        snapshot = _call(window, portal._PICK_CERT,
                         {'list': portal.KC['list'], 'probe': True}) or {}
        if snapshot.get('total'):
            if snapshot.get('signature') != signature:
                signature, steady = snapshot.get('signature'), time.time()
            elif steady is not None and time.time() - steady >= 0.6:
                break
        time.sleep(0.2)
    else:
        raise DeskLoginError('인증서 목록을 불러오지 못했습니다. 창에서 확인해 주세요.')

    got = _call(window, portal._PICK_CERT,
                {'list': portal.KC['list'], 'match': cert_match}) or {}
    if got.get('status') == 'ambiguous':
        raise DeskLoginError('조건에 맞는 인증서가 여러 개입니다. '
                             '설정의 인증서 사용자 이름을 더 자세히 적어 주세요.')
    if got.get('status') != 'selected':
        raise DeskLoginError('조건에 맞는 인증서를 찾지 못했습니다. '
                             '설정의 인증서 사용자 이름을 확인해 주세요.')
    return got.get('text', '')


def run() -> int:
    """창을 띄우고 자동 로그인한 뒤, 창은 사용자에게 넘긴다."""
    import webview
    from pathlib import Path
    from core import watcher

    def say(message):
        print(f'  {time.strftime("%H:%M:%S")}  {message}', flush=True)

    popups = []

    def open_popup(url):
        """나이스가 스스로 여는 창도 **이 프로그램 안에서** 연다.

        pywebview 기본값은 바깥 브라우저다. 거기는 프로필이 달라 로그인이 끊긴다.
        """
        if len(popups) >= 12:
            say('새 창이 너무 많아 더 열지 않습니다.')
            return
        host = url.split('//', 1)[-1].split('/', 1)[0]
        popups.append(webview.create_window(host or '새 창', url, js_api=None,
                                            width=1400, height=900, text_select=True))
        say(f'{host} 창을 열었습니다.')

    try:
        cred = secretstore.load()
    except secretstore.SecretError as exc:
        print(exc, flush=True)
        print('데스크 설정에서 아이디와 인증서 암호를 먼저 저장해 주세요.', flush=True)
        return 1

    # 창을 만들기 전에 걸어야 한다. pywebview 는 창이 뜰 때 처리기를 묶어 버린다.
    from core import web_popup
    web_popup.install(open_popup, say)
    window = webview.create_window(TITLE, portal.NEIS_URL, width=1500, height=950)

    def work(win):
        def show(message):
            """콘솔이 없는 실행 파일에서도 보이도록 제목에 단계를 적는다."""
            say(message)
            try:
                win.set_title(f'{TITLE} · {message}')
            except Exception:
                pass

        try:
            result = sign_in(win, cred, show)
            done = '로그인 완료' + (' (이미 열려 있던 세션)' if result.get('already') else '')
            say(done)
            if result.get('picked'):
                say(f"인증서: {result['picked']}")
            try:
                win.set_title(TITLE)
            except Exception:
                pass
        except Exception as exc:
            # 실패해도 창은 닫지 않는다. 그 자리에서 직접 로그인할 수 있어야 한다.
            say('자동 로그인 중단')
            print(str(exc), flush=True)
            try:
                win.set_title(f'{TITLE} · 자동 로그인 중단')
                _call(win, _BANNER, f'자동 로그인을 끝내지 못했습니다.\n{exc}')
            except Exception:
                pass

    webview.start(work, window, gui='edgechromium', private_mode=False,
                  storage_path=str(Path(watcher.DATA_DIR) / 'neis-webview-profile'))
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
