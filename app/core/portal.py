"""
전북교육청 인증서 자동 로그인 — cert-login.js 의 Playwright(Python) 포팅.

대상은 NEIS, 전북 업무포털(eduptl), K-에듀파인(klef), 리로스쿨(riro), 전북 AIEP(aiep)다.
앞의 셋은 **인증서**로 들어가고, 리로스쿨과 AIEP 는 **아이디·비밀번호**를 쓴다.
AIEP 에는 인증서(정부 통합로그인) 길도 있지만 여기서는 아이디 쪽을 쓴다.

브라우저는 **설치된 Edge**(`channel='msedge'`)를 쓴다. 배포판에 크로미움 405MB 를 넣지 않아도 된다.
프로필은 서비스별 전용 폴더에 고정한다 — 처음 한 번 인증서 프로그램 권한을 허용해 두면 계속 쓴다.

인증서는 브라우저가 아니라 **로컬 NPKI 저장소**에 있고 KSignCASE 에이전트가 읽는다.
그래서 새 프로필에서도 인증서 목록이 그대로 보인다.
"""
from __future__ import annotations

import os
import time
from . import edition

DATA_DIR = edition.DATA_DIR      # 판마다 따로 (core/edition.py)
CHANNEL = 'msedge'

# 창을 **내 Edge 처럼** 쓰기 위해 풀어 주는 것.
#
# Playwright 는 자동화용이라 기본으로 동기화와 확장을 꺼 버린다. 그러면 이 창에서 Edge 에
# 로그인해도 즐겨찾기·설정이 하나도 넘어오지 않는다. 두 가지만 풀면 사용자가 한 번 로그인해
# 두는 것으로 평소 쓰던 환경이 따라온다 (2026-09-15 요청).
#
# ⚠️ `--no-first-run` 은 **풀지 않는다.** 빼면 첫 실행 안내 화면이 떠서 자동화를 막는다.
# ⚠️ 평소 쓰는 브라우저 프로필을 그대로 쓰는 것은 다른 이야기다. Edge 는 프로필 하나를
#    한 번에 한 프로세스만 연다. 이미 켜져 있으면 새 창이 그쪽으로 넘어가 **자동화가 제어를
#    잃는다** (2026-09-14 에 두 번 겪었다). 그래서 프로필은 계속 우리 것을 쓴다.
KEEP_USER_SETTINGS = ['--disable-sync', '--disable-extensions']
# 데스크가 쓰는 공용 프로필. 이름은 예전 NEIS 프로필 그대로라 이미 허용해 둔
# 로컬 네트워크 권한과 로그인 기록을 그대로 물려받는다.
SHARED_FOLDER = 'browser-msedge'

# 인증서 사이트(나이스·업무포털·에듀파인)를 띄울 브라우저. 기본은 Edge.
# Chrome 은 **테스트 기능**이다 (2026-10-23 요청). 엔진이 같아 붙는 방식은 그대로 쓰고,
# 실행 파일과 프로필 폴더만 다르다. 프로필을 나누는 것은 Edge 에서 허용해 둔 로컬 네트워크
# 권한이 Chrome 으로 넘어가지 않기 때문이고, 두 브라우저가 한 폴더를 잡으면 부딪히기 때문이다.
BROWSERS = {
    'msedge': {'label': 'Edge', 'exe': ('Microsoft', 'Edge', 'Application', 'msedge.exe'),
               'folder': SHARED_FOLDER},
    'chrome': {'label': 'Chrome', 'exe': ('Google', 'Chrome', 'Application', 'chrome.exe'),
               'folder': 'browser-chrome'},
}
DEFAULT_BROWSER = 'msedge'

NEIS_URL = 'https://jbe.neis.go.kr'
EDUPTL_URL = 'https://jbe.eduptl.kr/bpm_lgn_lg00_001.do'
KLEF_URL = 'https://klef.jbe.go.kr/keris_ui/login.do'
# 리로스쿨은 학교마다 주소가 다르다. 인증서를 쓰지 않고 아이디·비밀번호만 받는다.
RIRO_URL = 'https://kijun.riroschool.kr/user.php?action=signin'
RIRO_ID = '#id'
RIRO_PW = '#pw'
# 🚨 `로그인` 이 들어간 단추가 네 개다. 세 개는 **숨어 있는** 재로그인·세션연장 팝업 것이고,
#    보이는 진짜 단추는 `button.button_normal` 하나뿐이다. `.first` 로 고르면 숨은 것을
#    집어 아무 일도 일어나지 않는다 (2026-09-14 사용자 보고: "로그인 버튼이 눌려지지 않음").
#    그래서 **보이는 것만** 추린다.
RIRO_LOGIN = 'button:visible'
# 전북 AIEP. 인증서(정부 통합로그인) 길도 있지만 여기서는 아이디·비밀번호 쪽을 쓴다.
#
# 🚨 **로그인 폼 주소로 바로 들어가면 안 된다.** 폼은 보이지만, 로그인을 누른 순간
#    `/idp/login/process/` 가 처리할 요청이 없어 무한 리디렉션에 빠진다
#    (2026-09-14 사용자 보고: "ai-auth.jbedu.kr 너무 여러 번 리디렉션되었습니다").
#    첫 화면에서 역할을 고르고 들어가야 통합 인증이 요청을 준비해 준다. 그래서 사람이
#    하는 순서를 그대로 따라간다: 첫 화면 → 공지 닫기 → 교사 → 사용자 로그인 → 폼.
AIEP_HOME = 'https://ai.jbedu.kr'
# 첫 화면의 역할 단추 — 학생·교원·관리자 중 우리가 쓰는 것. 글자가 바뀌어 왔다:
# 2026-09 '교사' → 2026-10 '교원(교직원)' (줄바꿈 포함). 띄어쓰기·줄바꿈은 빼고 앞에서부터 찾는다.
AIEP_ROLES = ('교원(교직원)', '교원', '교사')
AIEP_ROLE = AIEP_ROLES[0]
AIEP_FORM_LINK = 'a.certify-type-user'   # "사용자 로그인 — AIEP 아이디를 이용하여 로그인"
AIEP_ID = '#id'
# 🚨 로그인 폼이 **두 판**이다. 주소로 바로 들어갔을 때와 정상 경로로 왔을 때 칸 이름이
#    다르다 (`#password`/`button.login-btn` vs `#pw`/`#submitBtn`). 둘 다 받는다.
AIEP_PW = '#pw, #password'
AIEP_LOGIN = '#submitBtn, button.login-btn'
AIEP_SUFFIX = '@ai.jbedu.kr'     # 화면에 붙어 있는 꼬리. 아이디 칸에는 앞부분만 넣는다.
# 전북교육연수포털(배움누리터, jbstudy) — 아이디·비밀번호 (2026-10-29 요청, 교사만).
# 🚨 아이디·비밀번호 칸의 id·name 이 **불러올 때마다 바뀐다** (`ccTx0vX`·`yfkjarN` 같은 무작위 글자 — 2026-10-29
#    실측). 이름으로 찾지 말고, 로그인 폼(`form[name=loginForm]` 가운데 비밀번호 칸이 있는 것) 안의 글 칸·비밀번호 칸으로 찾는다.
#    로그인 단추는 `doLogin()` 을 부르고 ajax(`/system/loginProcess.do`)로 보낸 뒤 /main.do 로 옮긴다.
#    틀리면 alert("아이디 또는 비밀번호를 잘못 입력했습니다") — 그 글로 무엇이 틀렸는지 알린다.
#    로그인했는지는 화면이 심어 두는 전역 `isLogin` 으로 본다.
#    🚨 화면에 «회원 ID·비밀번호를 외부 업체에 제공해 연수를 대행하면 이용 제한» 경고가 있다 — 데스크는 **본인 PC 에서
#    본인 로그인만** 대신한다. 연수 수강(출석·진도)은 자동화하지 않는다.
JBSTUDY_HOME = 'https://www.jbstudy.kr'
JBSTUDY_URL = 'https://www.jbstudy.kr/system/login/login.do'
JBSTUDY_FORM = 'form[name="loginForm"]:has(input[type="password"])'
JBSTUDY_ID = f'{JBSTUDY_FORM} input[type="text"]'
JBSTUDY_PW = f'{JBSTUDY_FORM} input[type="password"]'
JBSTUDY_LOGIN = f'{JBSTUDY_FORM} button'
KLEF_PREFIX = 'mainframe.MainVFrameSet.LoginFrame.form.divLogin.form'
KLEF_ID = f'[id="{KLEF_PREFIX}.edtUsid:input"]'
KLEF_LOGIN = f'[id="{KLEF_PREFIX}.btnLogin"]'

KC = {
    'list': '#kc_cert_list',
    'password': 'input[name="certPassword"]',
    'ok': 'button.kc-btn-blue',
}

CERT_HINT = ('{} 인증서 위젯이 뜨지 않았습니다.\n'
             '  1) 화면에 "이 장치에서 다른 앱 및 서비스에 액세스" 물음이 떴다면 **허용**을 누르세요.\n'
             '     인증서 프로그램이 컴퓨터 안에 있어서, 웹 페이지가 거기에 접속해야 합니다.\n'
             '  2) 인증서 프로그램(KSignCASE)이 설치돼 실행 중인지 확인하세요.')

# ── 로딩 덮개 ────────────────────────────────────────────────
# 세 시스템 모두 준비가 끝날 때까지 투명한 덮개(`.isloading-overlay`)를 깔아 둔다.
#
# 🚨 이 덮개는 **인증서 프로그램과 이야기가 끝나야** 걷힌다. 그 통신은 브라우저에서
#    `https://127.0.0.1:8443` 으로 나가는데, Edge 가 최근 버전부터 이것을 "이 장치에서 다른
#    앱 및 서비스에 액세스" 권한으로 막는다. 막히면 덮개가 **영영 걷히지 않는다.**
#
#    2026-09-14 실측(승인 이력 없는 새 프로필, 같은 페이지):
#        권한 막힘  → 45초 동안 45초 내내 덮여 있음 (끝까지 안 걷힘)
#        권한 허용  → 45초 중 0.5초만 덮여 있음
#
#    예전에는 15초만 기다린 뒤 **결과를 보지 않고 그냥 눌렀다.** 덮개 아래로 들어간 클릭은
#    조용히 사라지고, 40초 뒤에 "위젯이 뜨지 않았습니다" 라는 엉뚱한 말만 남았다. 느린 PC 에서
#    "멈춘다" 던 증상이 이것이다. 이제는 기다린 결과를 보고, 안 걷히면 이유를 짚어 준다.
OVERLAY_WAIT = 45.0      # 허용돼 있으면 0.5초면 걷힌다. 길게 잡아도 손해가 없다.
CERT_WAIT = 20.0         # 위젯이 뜨기를 기다리는 시간 (한 번에)
BUSY_HINT = (
    '{} 화면이 준비되지 않았습니다. 로딩 표시가 {:.0f}초 동안 걷히지 않았습니다.\n'
    '  대개 **인증서 프로그램에 접속하지 못해서**입니다. 확인할 것:\n'
    '  1) 브라우저에 "이 장치에서 다른 앱 및 서비스에 액세스" 물음이 떠 있으면 허용하세요.\n'
    '     한 번 거절하면 다시 묻지 않고 막아 버립니다. 그때는 사이트 권한에서 되돌려야 합니다.\n'
    '  2) 인증서 프로그램(KSignCASE)이 설치돼 실행 중인지 확인하세요.\n'
    '  3) 학교 전체에 배포한다면 Edge 정책 LoopbackNetworkAllowedForUrls 에 이 주소를 넣으면\n'
    '     물음 자체가 사라집니다.')


class LoginError(RuntimeError):
    pass


def find_browser(kind: str = DEFAULT_BROWSER):
    """설치된 브라우저 실행 파일. 없으면 None. Playwright 의 `channel` 이 찾는 자리와 같다."""
    parts = BROWSERS[kind]['exe']
    for base in (os.environ.get('PROGRAMFILES(X86)'), os.environ.get('PROGRAMFILES'),
                 os.environ.get('LOCALAPPDATA')):
        if base:
            spot = os.path.join(base, *parts)
            if os.path.exists(spot):
                return spot
    return None


def edge_exe() -> str:
    """설치된 Edge 실행 파일."""
    spot = find_browser('msedge')
    if not spot:
        raise RuntimeError('Microsoft Edge 를 찾지 못했습니다.')
    return spot


def _active_port(profile_dir):
    """Edge 가 열어 둔 디버깅 포트. `--remote-debugging-port=0` 이면 Edge 가 고른 번호를
    프로필의 `DevToolsActivePort` 첫 줄에 적는다. 없으면 None."""
    try:
        with open(os.path.join(profile_dir, 'DevToolsActivePort'), encoding='utf-8') as source:
            return int(source.readline().strip())
    except (OSError, ValueError):
        return None


def open_shared_edge(playwright, timeout: float = 30.0, browser: str = DEFAULT_BROWSER):
    """데스크가 쓰는 Edge 를 **평소처럼 띄우고** 붙는다. Browser 를 돌려준다.

    `browser='chrome'` 이면 Chrome 을 같은 방식으로 띄운다(테스트 기능). 설치돼 있지 않으면
    RuntimeError — 고르는 쪽(데스크)이 Edge 로 돌아갈지 정한다.

    🚨 `launch_persistent_context` 로 띄우거나, 붙을 때 기본값을 쓰면 Playwright 가
    `Browser.setDownloadBehavior` 를 보낸다. 그 뒤로는 기본값으로 되돌려도 Edge 의
    "파일 열기"·"폴더에 표시" 가 **아무 일도 하지 않는다** (2026-10-12 사용자 보고·실측:
    평소 Edge 는 되고, 붙은 Edge 는 안 됨). `no_defaults=True` 로 붙으면 그 명령을
    보내지 않아 내려받기가 Edge 것 그대로 남는다 — 실측으로 폴더가 열렸다.

    포트는 Edge 가 고르게 하고(`0`) 프로필의 `DevToolsActivePort` 에서 읽는다. 127.0.0.1 에만
    열린다. 데스크가 먼저 띄워 둔 Edge 가 아직 떠 있으면 새로 띄우지 않고 거기에 붙는다.
    """
    import subprocess
    if browser not in BROWSERS:
        raise ValueError(f'지원하지 않는 브라우저: {browser}')
    name = BROWSERS[browser]['label']
    exe = edge_exe() if browser == 'msedge' else find_browser(browser)
    if not exe:
        raise RuntimeError(f'{name} 를 찾지 못했습니다.')
    profile_dir = os.path.join(DATA_DIR, BROWSERS[browser]['folder'])
    os.makedirs(profile_dir, exist_ok=True)

    def attach(port):
        return playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}', no_defaults=True,
                                                    timeout=10000)

    def listening(port) -> bool:
        import socket
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                return True
        except OSError:
            return False

    port = _active_port(profile_dir)
    if port:
        try:
            return attach(port)              # 지난번에 띄운 Edge 가 아직 떠 있다
        except Exception as exc:
            # 🚨 Edge 가 떠 있는데 붙지 못했다. 붙어 있는 동안 `edge://downloads`(Ctrl+J)를
            #    한 번이라도 열었으면, 그 탭을 닫아도 다시 붙는 것이 멈춘다 (2026-10-12 실측).
            #    새로 띄우면 떠 있는 Edge 로 넘어가 포트가 생기지 않으므로, 기다리지 말고 바로 알린다.
            if listening(port):
                raise RuntimeError(f'열려 있는 {name} 에 다시 연결하지 못했습니다. 데스크가 띄운 '
                                   f'{name} 창을 모두 닫고 다시 눌러 주세요.') from exc
    try:
        os.remove(os.path.join(profile_dir, 'DevToolsActivePort'))
    except OSError:
        pass
    forget_last_session(profile_dir)
    subprocess.Popen(
        [exe, f'--user-data-dir={profile_dir}', '--remote-debugging-port=0',
         '--no-first-run', '--no-default-browser-check',
         '--disable-features=IsolateOrigins,site-per-process', '--start-maximized', 'about:blank'],
        # 데스크가 꺼져도 창은 사용자 것이라 남긴다.
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.time() + timeout
    last = None
    while time.time() < end:
        port = _active_port(profile_dir)
        if port:
            try:
                return attach(port)
            except Exception as exc:
                last = exc
        time.sleep(0.5)
    # 같은 프로필의 Edge 가 디버깅 포트 없이 떠 있으면 새 창이 그쪽으로 넘어가 포트가 안 생긴다.
    raise RuntimeError(f'{name} 에 연결하지 못했습니다. 데스크가 띄운 {name} 창을 모두 닫고 '
                       f'다시 눌러 주세요. ({last or "포트 없음"})')


def forget_last_session(profile_dir) -> None:
    """지난번에 열려 있던 창을 **다시 띄우지 않게** 한다. 띄우기 직전에 부른다.

    🚨 Edge 는 프로필에 남은 세션 기록을 보고 지난번 창을 되살린다. 그래서 나이스 하나를
    눌렀는데 며칠 전 에듀파인 창까지 함께 떠서 창이 셋이 됐다 (2026-09-15 사용자 보고:
    "이전에 틀어져 있던 내용이 같이 틀어지는 느낌"). 실측으로도 아무것도 하지 않고 띄우기만
    했는데 `klef.jbe.go.kr` 창이 먼저 떠 있었다.

    두 가지를 함께 한다. 설정만 고치면 동기화된 설정이 덮을 수 있고, 기록만 지우면 다음에
    또 쌓인다.

    브라우저가 떠 있는 동안에는 절대 부르지 말 것 — 그때는 Edge 가 이 파일들을 쥐고 있다.
    """
    import json
    import shutil
    default = os.path.join(profile_dir, 'Default')
    # 되살릴 기록 자체를 지운다. 최근 닫은 탭 목록이라 잃을 것이 없다.
    shutil.rmtree(os.path.join(default, 'Sessions'), ignore_errors=True)
    spot = os.path.join(default, 'Preferences')
    if not os.path.exists(spot):
        return                       # 아직 한 번도 안 띄운 프로필. 기본값이 새 탭이다
    try:
        with open(spot, encoding='utf-8') as source:
            prefs = json.load(source)
        session = prefs.setdefault('session', {})
        session['restore_on_startup'] = 5        # 5 = 새 탭 페이지
        session['startup_urls'] = []
        holder = prefs.setdefault('profile', {})
        holder['exit_type'] = 'Normal'           # 복구 물음표가 뜨지 않게
        holder['exited_cleanly'] = True
        fresh = spot + '.desk-tmp'
        with open(fresh, 'w', encoding='utf-8') as sink:
            json.dump(prefs, sink, ensure_ascii=False)
        os.replace(fresh, spot)
    except (OSError, ValueError):
        pass                         # 설정을 못 고쳐도 기록은 지웠다


def launch(playwright, headless=False, viewport=None, target='neis', profile=None,
           share=False):
    """설치된 Edge 를 고정 프로필로 띄운다.

    창은 **최대화**하고 뷰포트를 창 크기에 맞춘다. 예전에는 1680×1000 으로 고정했는데,
    NEIS 는 조회 조건·그리드·단추가 가로로 긴 화면이라 모니터가 더 큰데도 잘려 보였다
    (2026-09-11 사용자 보고). `viewport=(가로, 세로)` 를 주면 그 크기로 고정한다 — 크기를
    맞춰야 하는 점검용이다.

    `profile` 을 주면 프로필 폴더를 따로 쓴다. 개발 중 데스크를 켜 둔 채로 같은 서비스를
    또 띄우면 프로필 잠금이 충돌하기 때문이다. 이름은 폴더 이름으로 쓰므로 걸러 낸다.
    """
    if target not in ('neis', 'eduptl', 'klef', 'riro', 'aiep', 'jbstudy'):
        raise ValueError(f'지원하지 않는 자동 로그인 대상: {target}')
    # `share=True` 면 다섯 서비스가 **한 프로필**을 함께 쓴다. 데스크가 그렇게 부른다 —
    # 창 하나에 탭으로 열기 때문에 프로필도 하나여야 하고, 그래야 Edge 로그인을 한 번만
    # 해도 다섯 곳에 다 적용된다 (2026-09-15 요청).
    #
    # 점검 스크립트는 서비스별 프로필을 쓴다. 하나씩 따로 돌리고, 데스크가 켜져 있을 때
    # 같은 프로필을 잡으면 프로필 잠금이 부딪히기 때문이다.
    folder = (SHARED_FOLDER if share or target == 'neis'
              else f'browser-{target}-msedge')
    if profile:
        import re
        folder += '-' + (re.sub(r'[^A-Za-z0-9_-]', '', str(profile)) or 'alt')
    profile_dir = os.path.join(DATA_DIR, folder)
    os.makedirs(profile_dir, exist_ok=True)
    forget_last_session(profile_dir)
    # NEIS·업무포털·에듀파인 모두 가로로 긴 화면이라 뷰포트를 고정하면 잘린다.
    # `no_viewport` 는 "창 크기를 그대로 쓴다"는 뜻이고, 창은 최대화해서 띄운다.
    options = ({'no_viewport': True} if viewport is None
               else {'viewport': {'width': viewport[0], 'height': viewport[1]}})
    return playwright.chromium.launch_persistent_context(
        profile_dir,
        channel=CHANNEL,
        headless=headless,
        args=['--disable-features=IsolateOrigins,site-per-process', '--start-maximized'],
        # 이 창에서 Edge 에 로그인하면 즐겨찾기·설정·확장이 따라오게 한다.
        ignore_default_args=KEEP_USER_SETTINGS,
        **options)


# ── 공통 도우미 ───────────────────────────────────────────────
def wait_overlay_gone(ctx, timeout=40.0) -> bool:
    """
    ★ 두 시스템 모두 로딩 중 **투명 오버레이**를 깔아 둔다.
      이게 클릭을 가로채서 Playwright 의 click() 이 'intercepts pointer events' 로 버티다 죽는다.
    """
    end = time.time() + timeout
    while time.time() < end:
        busy = False
        for sel in ('.isloading-overlay', '.ers_progress_content'):
            try:
                if ctx.locator(sel).first.is_visible(timeout=500):
                    busy = True
                    break
            except Exception:
                pass
        if not busy:
            time.sleep(0.3)
            return True
        time.sleep(0.3)
    return False


_DOM_CLICK = """(a) => {
  const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  let el = a.selector ? document.querySelector(a.selector) : null;
  if (!el && a.text) {
    el = Array.from(document.querySelectorAll('div,span,button,a'))
      .find(e => e.children.length === 0 && (e.textContent||'').trim() === a.text && vis(e));
  }
  if (!el) return false;
  const r = el.getBoundingClientRect();
  for (const t of ['mousedown','mouseup','click'])
    el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window,
      clientX:r.left + r.width/2, clientY:r.top + r.height/2}));
  return true;
}"""


def dom_click(ctx, selector=None, text=None) -> bool:
    """
    오버레이를 통과하는 클릭. 걷히지 않는 오버레이가 있어서 DOM 에 직접 마우스 시퀀스를 쏜다.
    ⚠️ 단, **eduptl 의 `#btnLgn` 만은 이 방식으로 안 열린다** — 거기서는 실제 클릭을 쓴다.
    """
    return ctx.evaluate(_DOM_CLICK, {'selector': selector, 'text': text})


def wait_for(ctx, selector, timeout=60.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if ctx.locator(selector).count():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def require_ready(page, service: str, timeout: float = OVERLAY_WAIT) -> None:
    """로딩 덮개가 걷힐 때까지 기다린다. 안 걷히면 **이유를 짚어 멈춘다.**

    예전처럼 그냥 밀고 나가면 클릭이 덮개에 먹혀 사라지고, 한참 뒤에 엉뚱한 곳을 탓하게 된다.
    """
    if not wait_overlay_gone(page, timeout):
        raise LoginError(BUSY_HINT.format(service, timeout))


def open_cert_widget(page, service: str, press, progress=lambda message: None,
                     tries: int = 2):
    """[인증서 로그인] 을 눌러 인증서 위젯을 연다. 연 컨텍스트를 돌려준다.

    누르는 방법은 시스템마다 달라서(`press`) 밖에서 받는다 — 업무포털은 합성 클릭이 안 먹는다.

    한 번 더 눌러 보는 이유: 덮개가 막 걷힌 직후에는 앱이 아직 클릭을 받지 못하는 때가 있다.
    느린 PC 에서 특히 그렇다. 한 번의 헛클릭으로 로그인 전체를 포기할 이유가 없다.
    """
    for attempt in range(tries):
        require_ready(page, service)
        if not press():
            raise LoginError(f'[인증서 로그인] 버튼을 찾지 못했습니다 ({service}).')
        root = find_cert_root(page, timeout=CERT_WAIT)
        if root:
            return root
        if attempt + 1 < tries:
            progress('인증서 창이 아직 안 떠 다시 눌러 봅니다')
    raise LoginError(CERT_HINT.format(service))


def find_cert_root(page, timeout=40.0):
    """위젯이 있는 컨텍스트(page 또는 frame)를 찾는다. NEIS·eduptl 은 메인 문서에 뜬다."""
    end = time.time() + timeout
    while time.time() < end:
        for ctx in [page, *page.frames]:
            try:
                if ctx.locator(KC['list']).count():
                    if ctx.locator(KC['password']).first.is_visible(timeout=500):
                        return ctx
            except Exception:
                pass
        time.sleep(0.4)
    return None


_PICK_CERT = """(args) => {
  const list = document.querySelector(args.list);
  if (!list) return {status:'no-list'};
  const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
  let rows = Array.from(list.querySelectorAll('tr, li, [role="row"]'))
    .filter(el => visible(el) && (el.textContent||'').trim() &&
      !el.querySelector('th, [role="columnheader"]'));
  // Some widget versions use divs instead of table rows.
  if (!list.querySelector('table, tr, li, [role="row"]'))
    rows = Array.from(list.querySelectorAll('div')).filter(visible);
  rows = rows.filter(el => (el.textContent||'').trim());
  if (args.probe) return {total:rows.length, signature:rows.map(el => el.textContent).join('\u001f')};
  if (args.match) rows = rows.filter(el => new RegExp(args.match).test(el.textContent||''));
  else rows = rows.filter(el => (el.textContent||'').trim());
  // Count certificates, not nested copies of the same matching text.
  rows = rows.filter(el => !rows.some(other => other !== el && el.contains(other)));
  if (!rows.length) return {status:'no-row'};
  if (rows.length !== 1) return {status:'ambiguous', count:rows.length};
  const row = rows[0];
  const cand = Array.from(row.querySelectorAll('.kc-tableview-cell'))
    .find(el => !args.match || new RegExp(args.match).test(el.textContent||'')) || row;
  const r = cand.getBoundingClientRect();
  for (const t of ['mousedown','mouseup','click'])
    cand.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window,
      clientX:r.left + r.width/2, clientY:r.top + r.height/2}));
  return {status:'selected', text:cand.textContent.replace(/\\s+/g,' ').trim().slice(0,40)};
}"""

_CLICK_OK = """(sel) => {
  const btn = Array.from(document.querySelectorAll(sel))
    .find(b => (b.textContent||'').trim() === '확인');
  if (!btn) return false;
  const r = btn.getBoundingClientRect();
  for (const t of ['mousedown','mouseup','click'])
    btn.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window,
      clientX:r.left + r.width/2, clientY:r.top + r.height/2}));
  return true;
}"""


def submit_cert(page, root, cert_password: str, cert_match: str | None = None) -> str:
    """인증서 선택 → 암호 입력 → 확인."""
    # The password box appears before the local agent populates certificate rows.
    # Wait for a nonempty, stable list before matching or entering any password.
    deadline = time.monotonic() + 15
    signature, stable_since = None, None
    while time.monotonic() < deadline:
        snapshot = root.evaluate(_PICK_CERT, {'list': KC['list'], 'probe': True})
        if snapshot.get('total', 0):
            if snapshot['signature'] != signature:
                signature, stable_since = snapshot['signature'], time.monotonic()
            elif stable_since is not None and time.monotonic() - stable_since >= 0.6:
                break
        else:
            signature, stable_since = None, None
        page.wait_for_timeout(150)
    else:
        raise LoginError('인증서 창은 열렸지만 목록을 불러오지 못했습니다. 열린 창에서 저장매체와 인증서 목록을 확인해 주세요.')
    picked = root.evaluate(_PICK_CERT, {'list': KC['list'], 'match': cert_match})
    if picked['status'] == 'ambiguous':
        raise LoginError('선택 조건에 맞는 인증서가 여러 개입니다. 설정의 인증서 사용자 이름에 인증서를 구분할 수 있는 이름 전체 또는 문구를 입력해 주세요.')
    if picked['status'] != 'selected':
        raise LoginError('조건에 맞는 인증서를 찾지 못했습니다. 인증서 목록과 설정의 인증서 사용자 이름을 확인해 주세요.')
    page.wait_for_timeout(500)
    root.locator(KC['password']).fill(cert_password)
    page.wait_for_timeout(300)
    wait_overlay_gone(page, 10)
    wait_overlay_gone(root, 10)
    if not root.evaluate(_CLICK_OK, KC['ok']):
        root.locator(KC['ok']).filter(has_text='확인').first.click(force=True)
    return picked['text']


# ── NEIS ──────────────────────────────────────────────────────
def neis_state(page) -> dict:
    return page.evaluate("""() => {
        const tabs = Array.from(document.querySelectorAll('.cl-navigationbar-text.cl-text'))
          .map(d => Array.from(d.childNodes).filter(n => n.nodeType === 3)
            .map(n => n.textContent.trim()).join('')).filter(Boolean);
        const m = (document.body ? document.body.innerText : '').match(/([가-힣]+)\\(([a-zA-Z0-9_]+)\\)/);
        return { ok: tabs.length > 0, user: m ? `${m[1]}(${m[2]})` : null, tabs };
    }""")


def login_neis(page, cert_password: str, cert_match: str | None = None,
               base_url: str = NEIS_URL, progress=lambda message: None) -> dict:
    progress('NEIS 화면 불러오는 중')
    page.goto(base_url, wait_until='domcontentloaded')
    page.wait_for_function(NEIS_READY, timeout=30000, polling=150)
    if page.locator('.cl-navigationbar-text.cl-text').count():
        return neis_state(page)                     # 이미 로그인된 세션
    progress('보안프로그램 준비 확인 중')
    root = open_cert_widget(page, 'NEIS',
                            lambda: dom_click(page, text='인증서 로그인'), progress)
    picked = submit_cert(page, root, cert_password, cert_match)
    progress('인증서 확인 및 로그인 중')
    page.wait_for_function(NEIS_SIGNED_IN, timeout=30000, polling=150)
    return {**neis_state(page), 'picked': picked}


# ── 전북 업무포털 (eduptl) ────────────────────────────────────
def eduptl_state(page) -> dict:
    return page.evaluate("""() => {
        const t = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
        const login = /교육행정 전자서명 인증서 로그인/.test(t);
        const m = t.match(/([가-힣]{2,4})\\s+([a-zA-Z][a-zA-Z0-9_]{2,})\\s/);
        const timer = (t.match(/(\\d{1,2}:\\d{2})\\s*후에 로그아웃/) || [])[1] || null;
        return { ok: !login && /로그아웃|업무바로가기/.test(t),
                 user: m ? `${m[1]}(${m[2]})` : null, 세션잔여: timer, url: location.href };
    }""")


def login_eduptl(page, cert_password: str, cert_match: str | None = None,
                 base_url: str = EDUPTL_URL, progress=lambda message: None) -> dict:
    progress('업무포털 화면 불러오는 중')
    page.goto(base_url, wait_until='domcontentloaded')
    # A permanent "보안프로그램 설치" link is not a loading indicator.
    # Wait for the real login control and the active loading message together.
    progress('보안프로그램 준비 확인 중')
    page.wait_for_function(EDUPTL_READY, timeout=60000, polling=150)
    already = eduptl_state(page)
    if already['ok']:
        return already

    # ⚠️ 첫 진입에 "보안프로그램이 로딩중입니다" 오버레이가 뜬다.
    #    이때 누른 클릭은 **조용히 사라진다**. 문구가 없어질 때까지 기다린다.
    if not wait_for(page, '#btnLgn', 20):
        raise LoginError('[교육행정 전자서명 인증서 로그인] 버튼(#btnLgn)을 찾지 못했습니다.')
    progress('인증서 창 준비 중')

    def press():
        # ⚠️ domClick(DOM 이벤트 합성)으로는 위젯이 안 뜬다 — 실제 입력으로 눌러야 한다.
        page.click('#btnLgn')
        return True

    root = open_cert_widget(page, '업무포털(eduptl)', press, progress)
    picked = submit_cert(page, root, cert_password, cert_match)
    progress('인증서 확인 및 로그인 중')
    page.wait_for_function(EDUPTL_SIGNED_IN, timeout=30000, polling=150)
    return {**eduptl_state(page), 'picked': picked}


def klef_state(page) -> dict:
    return page.evaluate("""() => {
        const text = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
        return {ok: /님/.test(text) && /문서관리|결재/.test(text),
            user: (text.match(/([가-힣]{2,4})님/) || [])[1] || null,
            세션잔여: (text.match(/(\\d{1,2}:\\d{2})/) || [])[1] || null};
    }""")


def login_klef(page, cert_password: str, cert_match: str | None = None,
               base_url: str = KLEF_URL, progress=lambda message: None,
               user_id: str = '') -> dict:
    if not user_id.strip():
        raise LoginError('설정에서 에듀파인 로그인에 사용할 업무포털 아이디를 저장해 주세요.')
    progress('에듀파인 로그인 화면 불러오는 중')
    page.goto(base_url, wait_until='domcontentloaded')
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    try:
        page.wait_for_function(KLEF_READY, timeout=60000, polling=150)
    except PlaywrightTimeoutError:
        raise LoginError('에듀파인 로그인 화면이 준비되지 않았습니다. 열린 브라우저에서 보안프로그램 설치·실행 상태와 로컬 네트워크 접근 권한을 확인한 뒤 다시 시도해 주세요.') from None
    already = klef_state(page)
    if already['ok']:
        return already
    progress('아이디 입력 중')
    require_ready(page, 'K-에듀파인')
    page.locator(KLEF_ID).click(force=True)
    page.locator(KLEF_ID).fill('')
    # Nexacro needs real key events; a value assignment alone is ignored.
    page.locator(KLEF_ID).press_sequentially(user_id, delay=30)
    progress('인증서 창 준비 중')

    def press():
        if not dom_click(page, selector=KLEF_LOGIN):
            page.locator(KLEF_LOGIN).click(force=True)
        return True

    try:
        root = open_cert_widget(page, 'K-에듀파인', press, progress)
    except LoginError as exc:
        raise LoginError(f'{exc}\n업무포털 아이디도 확인해 주세요.') from None
    picked = submit_cert(page, root, cert_password, cert_match)
    progress('인증서 확인 및 로그인 중')
    page.wait_for_function(KLEF_SIGNED_IN, timeout=30000, polling=150)
    return {**klef_state(page), 'picked': picked}


# ── 리로스쿨 (riro) ───────────────────────────────────────────
# 앞의 셋과 달리 **인증서를 쓰지 않는다.** 학교 아이디(또는 통합 이메일)와 비밀번호뿐이라
# 인증서 위젯도, 로컬 프로그램과의 통신도 없다. 그래서 흐름이 훨씬 짧다.
def riro_state(page) -> dict:
    return page.evaluate("""() => {
        const text = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
        const needsLogin = /로그인이 필요합니다|접근 가능한 메뉴가 없습니다/.test(text);
        // 리로스쿨 머리글은 "권민결 교무부 로그아웃" 꼴이다. 이름 뒤에 `님` 이 붙지 않아
        // 부서와 로그아웃 사이에서 찾는다. 못 찾으면 이름 없이 둔다 — 틀린 이름보다 낫다.
        const near = text.match(/([가-힣]{2,4})\\s+[가-힣]+부\\s+로그아웃/);
        return {ok: !needsLogin && /로그아웃/.test(text),
                user: (near && near[1])
                      || [...text.matchAll(/([가-힣]{2,4})\\s*(?:선생님|님)/g)].map(m => m[1])
                         .filter(n => !['선생', '학생', '회원', '고객'].includes(n))[0] || null,
                url: location.href};
    }""")


def login_riro(page, user_id: str, password: str, base_url: str = RIRO_URL,
               progress=lambda message: None) -> dict:
    """리로스쿨 아이디 로그인. 인증서를 쓰지 않아 인증서 암호는 필요 없다."""
    if not (user_id or '').strip():
        raise LoginError('설정에서 리로스쿨 아이디를 저장해 주세요.')
    if not (password or '').strip():
        raise LoginError('설정에서 리로스쿨 비밀번호를 저장해 주세요.')
    progress('리로스쿨 화면 불러오는 중')
    page.goto(base_url, wait_until='domcontentloaded')
    page.wait_for_function(RIRO_READY, timeout=30000, polling=150)
    already = riro_state(page)
    if already['ok']:
        return already                              # 이미 로그인된 세션

    progress('아이디·비밀번호 입력 중')
    require_ready(page, '리로스쿨')
    page.locator(RIRO_ID).fill(user_id.strip())
    page.locator(RIRO_PW).fill(password)
    progress('로그인 중')
    page.locator(RIRO_LOGIN).filter(has_text='로그인').first.click(timeout=15000)
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    try:
        page.wait_for_function(RIRO_SIGNED_IN, timeout=30000, polling=150)
    except PlaywrightTimeoutError:
        # 아이디·비밀번호가 틀리면 화면에 그대로 머문다. 무엇이 틀렸는지 화면 글자로 알린다.
        text = page.evaluate("() => (document.body ? document.body.innerText : '').replace(/\\s+/g,' ').trim()")
        hint = next((line for line in ('비밀번호', '아이디', '잠금', '일치')
                     if line in text[:600]), '')
        raise LoginError('리로스쿨 로그인이 끝나지 않았습니다. '
                         f"{'아이디·비밀번호를 확인해 주세요.' if hint else '열린 창을 확인해 주세요.'}"
                         ) from None
    return riro_state(page)


# ── 전북교육연수포털 (jbstudy) ─────────────────────────────────
def jbstudy_state(page) -> dict:
    return page.evaluate("""() => {
        const text = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
        const near = text.match(/([가-힣]{2,5})\\s*님/);
        return {ok: window.isLogin === true, user: near ? near[1] : null, url: location.href};
    }""")


def login_jbstudy(page, user_id: str, password: str, base_url: str = JBSTUDY_URL,
                  progress=lambda message: None) -> dict:
    """전북교육연수포털 아이디 로그인. 틀리면 화면이 띄우는 알림 글을 받아 알린다 (한 번만 — 5번 틀리면 잠긴다)."""
    if not (user_id or '').strip():
        raise LoginError('설정에서 연수포털 아이디를 저장해 주세요.')
    if not (password or '').strip():
        raise LoginError('설정에서 연수포털 비밀번호를 저장해 주세요.')
    progress('연수포털 화면 불러오는 중')
    page.goto(base_url, wait_until='domcontentloaded')
    page.wait_for_function(JBSTUDY_READY, timeout=30000, polling=150)
    already = jbstudy_state(page)
    if already['ok']:
        return already                              # 이미 로그인된 세션
    alerts = []

    def caught(dialog):
        alerts.append(dialog.message)
        try:
            dialog.accept()
        except Exception:
            pass
    page.on('dialog', caught)
    try:
        progress('아이디·비밀번호 입력 중')
        page.locator(JBSTUDY_ID).first.fill(user_id.strip())
        page.locator(JBSTUDY_PW).first.fill(password)
        progress('로그인 중')
        page.locator(JBSTUDY_LOGIN).filter(has_text='로그인').first.click(timeout=15000)
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not alerts:
            try:
                page.wait_for_function(JBSTUDY_SIGNED_IN, timeout=1000, polling=150)
                break
            except PlaywrightTimeoutError:
                continue
        else:
            said = ' '.join(alerts).replace('\n', ' ').strip()
            raise LoginError('연수포털 로그인이 끝나지 않았습니다. '
                             + (f'화면 알림: {said}' if said else '열린 창을 확인해 주세요.'))
    finally:
        page.remove_listener('dialog', caught)
    return jbstudy_state(page)


# ── 전북 AIEP (aiep) ─────────────────────────────────────────
def aiep_state(page) -> dict:
    """로그인 여부는 **어디에 있는가**로 본다.

    인증 서버(`ai-auth`)를 벗어나 AIEP 쪽에 있고 암호 칸이 없어야 한다. 다만 그것만으로는
    모자라다 — 로그인이 안 돼도 첫 화면으로 되돌아오기 때문이다. 첫 화면에만 있는
    `회원가입`·`아이디 찾기` 가 보이면 아직 못 들어간 것으로 본다.
    """
    return page.evaluate("""() => {
        const host = location.hostname || '';
        const text = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ');
        const onForm = !!document.querySelector('#pw, #password');
        const onLanding = text.includes('회원가입') && text.includes('아이디 찾기');
        return {ok: !onForm && !onLanding
                    && host.endsWith('jbedu.kr') && !host.startsWith('ai-auth'),
                user: [...text.matchAll(/([가-힣]{2,4})\s*(?:선생님|님)/g)].map(m => m[1])
                    .filter(n => !['선생', '학생', '회원', '고객'].includes(n))[0] || null,
                url: location.href};
    }""")


_AIEP_PICK_ROLE = """(names) => {
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const compact = e => (e.textContent || '').replace(/\\s+/g, '');
  const all = [...document.querySelectorAll('div,span,button,a')].filter(vis);
  for (const name of names) {
    // 같은 글자를 품은 것 가운데 가장 안쪽 — 바깥 상자를 누르면 반응하지 않는 화면이 있다
    const el = all.find(e => compact(e) === name && ![...e.children].some(c => compact(c) === name));
    if (!el) continue;
    const r = el.getBoundingClientRect();
    for (const t of ['mousedown', 'mouseup', 'click'])
      el.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window,
        clientX: r.left + r.width / 2, clientY: r.top + r.height / 2}));
    return name;
  }
  return null;
}"""


def aiep_pick_role(page) -> str | None:
    """첫 화면에서 교원(교사) 단추를 누른다. 누른 단추의 글자, 못 찾으면 None."""
    return page.evaluate(_AIEP_PICK_ROLE, list(AIEP_ROLES))


def aiep_open_form(page, progress=lambda message: None, timeout: float = 40.0) -> bool:
    """첫 화면에서 사람이 하는 순서대로 눌러 로그인 폼까지 간다.

    폼 주소로 바로 가면 제출 뒤 무한 리디렉션에 빠진다(위 주석 참고). 공지 팝업은 때에 따라
    안 뜨므로 못 닫아도 넘어간다.
    """
    dom_click(page, text='닫기')                  # 공지 팝업. 없으면 그냥 False.
    page.wait_for_timeout(800)
    if not aiep_pick_role(page):
        raise LoginError('AIEP 첫 화면에서 교사용 로그인 단추(교원·교사)를 찾지 못했습니다. '
                         '화면이 바뀌었을 수 있습니다 — 열린 창에서 직접 로그인해 주세요.')
    progress('통합 인증으로 넘어가는 중')

    end = time.time() + timeout
    while time.time() < end:
        if page.locator(AIEP_PW).count():
            return True
        if page.locator(AIEP_FORM_LINK).count():
            progress('AIEP 아이디 로그인 고르는 중')
            page.locator(AIEP_FORM_LINK).first.click(timeout=10000)
            page.wait_for_timeout(1200)
        page.wait_for_timeout(600)
    return bool(page.locator(AIEP_PW).count())


def login_aiep(page, user_id: str, password: str, base_url: str = AIEP_HOME,
               progress=lambda message: None) -> dict:
    """전북 AIEP 아이디 로그인.

    아이디 칸은 `@ai.jbedu.kr` 앞부분만 받으므로, 사용자가 전체 주소를 저장해 두었어도
    꼬리를 떼고 넣는다.
    """
    if not (user_id or '').strip():
        raise LoginError('설정에서 AIEP 아이디를 저장해 주세요.')
    if not (password or '').strip():
        raise LoginError('설정에서 AIEP 비밀번호를 저장해 주세요.')
    name = user_id.strip()
    if name.lower().endswith(AIEP_SUFFIX):
        name = name[:-len(AIEP_SUFFIX)]

    progress('AIEP 화면 불러오는 중')
    page.goto(base_url, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    already = aiep_state(page)
    if already['ok']:
        return already                              # 이미 로그인된 세션

    if not aiep_open_form(page, progress):
        raise LoginError('AIEP 로그인 폼이 뜨지 않았습니다. 열린 창을 확인해 주세요.')

    progress('아이디·비밀번호 입력 중')
    # 🚨 `fill()` 로 넣으면 값은 들어가는데 **로그인이 붙지 않는다.** 폼에 숨은 `email` 칸이
    #    있고, 화면 스크립트가 키 입력을 듣고 그것을 채우기 때문이다. 값만 꽂으면 그 칸이
    #    빈 채로 넘어가 서버가 조용히 첫 화면으로 되돌려보낸다. 사람이 직접 치면 되는 것을
    #    2026-09-14 에 사용자가 확인해 주었다. 그래서 한 글자씩 친다.
    for spot, value in ((AIEP_ID, name), (AIEP_PW, password)):
        box = page.locator(spot).first
        box.click()
        box.fill('')
        box.press_sequentially(value, delay=40)
    page.locator(AIEP_ID).first.press('Tab')       # 칸을 떠날 때 숨은 값을 만드는 화면도 있다
    page.wait_for_timeout(500)
    progress('로그인 중')
    page.locator(AIEP_LOGIN).first.click(timeout=15000)
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    try:
        page.wait_for_function(AIEP_SIGNED_IN, timeout=30000, polling=150)
    except PlaywrightTimeoutError:
        raise LoginError(
            'AIEP 로그인이 끝나지 않았습니다.\n'
            '  1) 설정의 AIEP 아이디·비밀번호를 확인해 주세요. 아이디는 @ai.jbedu.kr 앞부분입니다.\n'
            '  2) 평소 **정부 통합로그인(인증서)** 으로 들어가신다면 이 아이디 로그인은 쓸 수\n'
            '     없습니다. 열린 창에서 직접 로그인해 주세요.') from None
    return aiep_state(page)


# These predicates run in the page, so navigation and asynchronous UI rendering
# do not require fixed sleeps. Keep success checks aligned with *_state above.
NEIS_SIGNED_IN = """() => Array.from(document.querySelectorAll('.cl-navigationbar-text.cl-text'))
    .some(el => el.getClientRects().length && el.textContent.trim())"""
NEIS_READY = """() => {
    const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    return Array.from(document.querySelectorAll('.cl-navigationbar-text.cl-text')).some(visible)
        || Array.from(document.querySelectorAll('div,span,button,a'))
            .some(el => el.children.length === 0 && el.textContent.trim() === '인증서 로그인' && visible(el));
}"""
EDUPTL_SIGNED_IN = """() => {
    const text = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
    return !/교육행정 전자서명 인증서 로그인/.test(text) && /로그아웃|업무바로가기/.test(text);
}"""
EDUPTL_READY = """() => {
    const text = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ');
    if (!/교육행정 전자서명 인증서 로그인/.test(text) && /로그아웃|업무바로가기/.test(text)) return true;
    const button = document.querySelector('#btnLgn');
    const loading = /보안프로그램(?:이|을)?\\s*(?:로딩|로드|확인)\\s*중|로딩\\s*중/.test(text);
    return !!button && button.getClientRects().length > 0
        && getComputedStyle(button).visibility !== 'hidden' && !button.disabled && !loading;
}"""
KLEF_SIGNED_IN = """() => {
    const text = document.body ? document.body.innerText : '';
    return /님/.test(text) && /문서관리|결재/.test(text);
}"""
KLEF_READY = """() => {
    const text = document.body ? document.body.innerText : '';
    const field = document.querySelector('[id$="edtUsid:input"]');
    return (/님/.test(text) && /문서관리|결재/.test(text))
        || (!!field && field.getClientRects().length > 0 && !field.disabled);
}"""
RIRO_SIGNED_IN = """() => {
    const text = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ');
    return !/로그인이 필요합니다|접근 가능한 메뉴가 없습니다/.test(text) && /로그아웃/.test(text);
}"""
RIRO_READY = """() => {
    const text = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ');
    if (!/로그인이 필요합니다|접근 가능한 메뉴가 없습니다/.test(text) && /로그아웃/.test(text)) return true;
    const id = document.querySelector('#id');
    const pw = document.querySelector('#pw');
    return !!(id && pw && id.getClientRects().length > 0 && !id.disabled);
}"""
JBSTUDY_SIGNED_IN = """() => window.isLogin === true"""
JBSTUDY_READY = """() => {
    if (window.isLogin === true) return true;
    const pw = document.querySelector('form[name="loginForm"] input[type="password"]');
    return !!(pw && pw.getClientRects().length > 0 && !pw.disabled);
}"""
# 🚨 "인증 서버를 벗어났다" 만으로는 부족하다. 로그인이 안 돼도 첫 화면으로 **되돌아오기**
#    때문이다 (2026-09-14 실측: 되돌아온 뒤 [교사] 를 누르면 다시 로그인을 요구했다).
#    첫 화면에만 있는 `회원가입`·`아이디 찾기` 가 보이면 아직 안 들어간 것으로 본다.
AIEP_SIGNED_IN = """() => {
    if (document.querySelector('#pw, #password')) return false;
    const host = location.hostname || '';
    if (!host.endsWith('jbedu.kr') || host.startsWith('ai-auth')) return false;
    const text = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ');
    return !(text.includes('회원가입') && text.includes('아이디 찾기'));
}"""
AIEP_READY = """() => {
    const text = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ');
    if (!document.querySelector('#password') && /로그아웃|마이페이지|내 정보/.test(text)) return true;
    const id = document.querySelector('#id');
    const pw = document.querySelector('#password');
    return !!(id && pw && id.getClientRects().length > 0 && !id.disabled);
}"""
