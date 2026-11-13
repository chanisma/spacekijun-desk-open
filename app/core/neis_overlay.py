"""
NEIS 화면 위에 얹는 도우미 패널.

데스크의 별도 창(`web/assistant.html`)과 하는 일은 같다. 다른 점은 **나이스 화면 안에**
떠 있어서 눈을 옮기지 않아도 된다는 것뿐이다. 뒤쪽 로직(`neis_assist`·`neis_nav`)은 공유한다.
패널 자체는 `web/neis-overlay.js` 에 있다 — 이 모듈은 그 파일을 읽어 창에 심는다.

## 왜 이렇게 만들었나

**표(ticket)를 주고 나중에 물어본다.** 페이지가 부르는 함수는 화면 조작 스레드 위에서
실행된다. 거기서 결과를 기다리면 그 스레드가 자기 자신을 기다리다 멈춘다. 그래서
`__deskAsk` 는 일감을 큐에 넣고 표만 돌려주고, 패널이 `__deskPoll` 로 결과를 물어본다.
여기서 넘기는 함수는 큐와 사전만 만져야 한다 — Playwright 를 다시 부르면 안 된다.

**Shadow DOM 을 쓴다.** 나이스는 Cleopatra(`cl-*`) 프레임워크라 전역 스타일이 촘촘하다.
섀도 루트 안에 가둬야 서로 건드리지 않는다. 우리 스타일이 나이스를 망가뜨릴 일도 없다.

**주입은 CDP 로 한다.** `add_init_script` 는 페이지 스크립트보다 먼저 돌고 문서 CSP 를 타지
않는다. jbe.neis.go.kr 은 CSP 헤더가 없지만(2026-09-11 확인) 기대지 않는 편이 낫다.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_NAME = 'neis-overlay.js'


def _web_dir() -> Path:
    """`app/web` 의 위치. 배포 실행 파일에서는 번들 루트 아래에 풀린다."""
    bundled = getattr(sys, '_MEIPASS', None)
    if bundled:
        return Path(bundled) / 'web'
    return Path(__file__).resolve().parents[1] / 'web'


def source_path() -> Path:
    return _web_dir() / SCRIPT_NAME


def script() -> str:
    return source_path().read_text(encoding='utf-8')


def reload(page) -> str:
    """패널을 떼고 지금 파일 내용으로 다시 심는다. 개발 중 화면만 고칠 때 쓴다.

    로그인과 메뉴 색인은 그대로 두므로 인증서를 다시 넣지 않아도 된다.
    떼어낼 때 `__deskPanelStop` 을 불러야 한다 — 그냥 노드만 지우면 패널이 켜 둔 재부착
    타이머가 도로 붙여 놓는다.
    """
    source = script()
    page.evaluate("() => { if (window.__deskPanelStop) window.__deskPanelStop(); }")
    page.evaluate(source)
    return source


def install(page, enqueue, result, state=None) -> None:
    """열려 있는 NEIS 창에 패널을 심는다. 이후 이동하는 문서에도 자동으로 붙는다.

    `enqueue(kind, payload) -> ticket`, `result(ticket) -> dict`, `state() -> dict` 는
    큐와 사전만 만져야 한다.
    """
    source = script()
    bridge = {
        '__deskAsk': lambda text='': enqueue('assist', {'text': str(text or '')}),
        '__deskPick': lambda row='': enqueue('pick', {'row': str(row or '')}),
        '__deskPoll': lambda ticket='': result(str(ticket or '')),
        '__deskState': (lambda: state()) if state else (lambda: {}),
    }
    # 🚨 **이 탭에만** 심는다. 예전에는 창(context) 전체에 심었는데, 데스크가 업무시스템
    #    다섯 개를 한 창의 탭으로 열게 되면서 문제가 생겼다 (2026-09-15):
    #      · 업무포털·에듀파인·리로스쿨·AIEP 탭에도 나이스 도우미 패널이 붙는다
    #      · 심는 동안 **다른 탭까지 붙잡아** 다음 탭이 안 열린다
    for name, handler in bridge.items():
        try:
            page.expose_function(name, handler)
        except Exception:
            pass                      # 이미 심어 둔 탭이면 그대로 쓴다
    page.add_init_script(source)
    try:
        page.evaluate(source)         # 지금 보고 있는 문서에도 한 번 넣는다
    except Exception:
        pass
