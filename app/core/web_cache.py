"""데스크 화면 파일(app/web)을 WebView2 가 **옛 사본으로** 띄우지 않게 한다.

무슨 일이 있었나 (2026-10-08)
  `app/web/index.html` 을 고쳐도 데스크에 옛 화면(스티커 메모 메뉴가 없는)이 떴다.
  pywebview 의 로컬 서버는 `Cache-Control: no-store` 를 `bottle.response` 에 걸지만,
  `bottle.static_file()` 은 **새 응답 객체**를 돌려줘서 그 헤더가 버려진다
  (pywebview 6.2.1). 헤더 없이 `Last-Modified` 만 받은 WebView2 는 '마지막 수정 후 지난
  시간의 10%' 동안 사본을 그냥 쓴다 — 3주 묵은 파일이면 이틀 넘게. 프로필이
  `webview-profile` 에 남아 있어 프로그램을 다시 켜도 그대로다.

고치는 방법
  1. `install()` — 로컬 파일 응답에 no-store 를 직접 단다. 이후로는 사본을 만들지 않는다.
  2. `purge_stale()` — 이미 '아직 신선하다'고 저장된 사본은 서버에 묻지도 않으니,
     HTTP 캐시 폴더를 **한 번** 비운다. 로그인(쿠키)·설정은 다른 폴더라 남는다.
"""
from __future__ import annotations

import shutil
from pathlib import Path

POLICY = '1'      # 캐시 정책이 바뀌면 올린다 — 다음 실행에서 한 번 더 비운다
NO_STORE = 'no-cache, no-store, must-revalidate'
_installed = False


def install() -> None:
    """pywebview 로컬 서버의 파일 응답에 no-store 를 붙인다. 창을 띄우기 전에 한 번."""
    global _installed
    if _installed:
        return
    from webview import http
    original = http.bottle.static_file

    def static_file(*args, **kwargs):
        response = original(*args, **kwargs)
        # 404 같은 HTTPError 도 HTTPResponse 라 같은 방법으로 단다
        response.set_header('Cache-Control', NO_STORE)
        response.set_header('Pragma', 'no-cache')
        response.set_header('Expires', '0')
        return response

    http.bottle.static_file = static_file
    _installed = True


def purge_stale(storage_path: Path, log=lambda *parts: None) -> bool:
    """옛 정책으로 쌓인 HTTP 캐시를 한 번 비운다. 비웠거나 이미 비운 상태면 True.

    WebView2 가 떠 있지 않을 때(창을 만들기 전) 불러야 한다. 다른 데스크가 떠 있어
    파일이 잠겨 있으면 표시를 남기지 않고 다음 실행에서 다시 해 본다."""
    marker = storage_path / 'web-cache-policy'
    try:
        if marker.read_text(encoding='utf-8').strip() == POLICY:
            return True
    except OSError:
        pass
    default = storage_path / 'EBWebView' / 'Default'
    failed = []
    for name in ('Cache', 'Code Cache'):
        folder = default / name
        if folder.exists():
            shutil.rmtree(folder, onerror=lambda _f, path, _e: failed.append(path))
    if failed:
        log('화면 캐시를 다 비우지 못했습니다 (다른 데스크가 실행 중일 수 있습니다). 다음 실행에서 다시 시도합니다.')
        return False
    try:
        storage_path.mkdir(parents=True, exist_ok=True)
        marker.write_text(POLICY, encoding='utf-8')
    except OSError:
        return False
    log('화면 캐시를 비웠습니다. 최신 데스크 화면을 불러옵니다.')
    return True
