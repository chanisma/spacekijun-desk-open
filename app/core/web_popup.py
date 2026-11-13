"""페이지가 스스로 여는 새 창을 **프로그램 안으로** 돌린다.

pywebview 는 새 창 요청을 기본으로 바깥 브라우저에 넘긴다
(`OPEN_EXTERNAL_LINKS_IN_BROWSER`). 업무포털의 `나이스`·`K-에듀파인` 링크가 그 길로
나가는데, 바깥은 프로필이 달라 **로그인이 끊긴 채** 뜬다 (2026-09-15 사용자 보고).

내려받기도 여기서 받는다. pywebview 는 기본값(`ALLOW_DOWNLOADS = False`)으로 **모든
내려받기를 소리 없이 취소한다** — 스페이스기전에서 첨부·내보내기를 눌러도 아무 일이
없었다 (2026-10-11 사용자 보고).

데스크 본체와 나이스 전용 실행 파일이 함께 쓴다. 그래서 `desktop` 이 아니라 여기에 둔다 —
작은 실행 파일이 데스크 살림 전체를 끌어안지 않도록.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading

from . import downloads as down

INSIDE = ('http://', 'https://')


def wants_window(args, uri: str) -> bool:
    """페이지가 **돌려받은 창에 글을 써 넣거나 다룰** 새 창인가.

    출력 창이 그렇다: `window.open('', …)` 로 빈 창을 받아 문서를 써 넣고 인쇄한다
    (스페이스기전 급식지도·자습 감독 명단, 과목 선택 확인표 …). `blob:` 주소(성적 분석·전자서명
    출력)와 크기를 준 작은 창(별까지 쌓기 미니 창)도 돌려받은 창을 쓴다.

    🚨 이런 요청을 데스크 창으로 돌리면 `window.open` 이 **null** 을 돌려받아 사이트가
    "팝업이 차단되어 출력 창을 열지 못했습니다" 를 띄운다 (2026-10-12 사용자 보고). 그래서 이것들은
    WebView2 가 **제 팝업 창**으로 열게 둔다 — 같은 프로필이라 로그인도 이어지고 인쇄도 된다.
    """
    if not uri.startswith(INSIDE):
        return True                     # '' · about:blank · blob: · data:
    try:
        features = args.WindowFeatures
        return features.HasSize is True or features.HasPosition is True
    except Exception:
        return False


def install(open_popup, log=lambda *parts: None) -> None:
    """새 창 요청을 가로채 `open_popup(주소)` 로 넘긴다. 프로그램마다 한 번 부른다.

    🚨 **창을 하나라도 만들기 전에 불러야 한다.** pywebview 는 창이 뜰 때
    `self.on_new_window_request` 를 **묶인 메서드**로 등록한다. 그 뒤에 갈아 끼우면 이미
    뜬 창은 옛 손을 그대로 쥐고 있어 바깥 브라우저로 내보낸다. 늦게 부르면 아무 일도
    일어나지 않는다 (2026-09-15: 패키지 검증에서 이 순서를 틀려 한 번 걸렸다).
    """
    from webview.platforms import edgechromium

    def on_new_window_request(browser, sender, args):
        try:
            uri = str(args.get_Uri())
        except Exception:
            uri = ''
        if wants_window(args, uri):
            # 손대지 않으면 WebView2 가 제 팝업 창을 연다 (바깥 브라우저가 아니다) —
            # `window.open` 이 그 창을 돌려받아 문서를 써 넣고 인쇄할 수 있다.
            return
        args.set_Handled(True)          # 무슨 일이 있어도 바깥으로 내보내지 않는다
        # 이 자리는 WebView2 이벤트 처리 중이다. 창 만드는 일은 넘긴다.
        threading.Thread(target=open_popup, args=(uri,),
                         daemon=True, name='desk-popup').start()

    edgechromium.EdgeChrome.on_new_window_request = on_new_window_request
    edgechromium.EdgeChrome.on_download_starting = _download_handler(log)
    ready = getattr(edgechromium.EdgeChrome, 'on_webview_ready', None)
    if ready is not None and not getattr(ready, 'desk_downloads', False):
        edgechromium.EdgeChrome.on_webview_ready = _with_repeat_downloads(ready)


def _with_repeat_downloads(ready):
    """한 화면에서 **두 번째 내려받기부터** 막히지 않게 한다.

    Chromium 은 한 페이지가 잇따라 내려받으면 '여러 파일 자동 다운로드' 허락을 묻는다.
    pywebview 는 그 물음을 받지 않아 받기가 **소리 없이 멈춘다**. 스페이스기전은 파일을
    먼저 가져온 뒤(`await`) 내려받게 해서 클릭 직후라는 표시가 사라지기 쉽다 — 첨부를
    두 번째 누르면 아무 일이 없던 이유다 (2026-10-11 실측). 그 허락 하나만 내준다.
    """
    def on_webview_ready(browser, sender, args):
        ready(browser, sender, args)
        if not args.IsSuccess:
            return
        try:
            from Microsoft.Web.WebView2.Core import CoreWebView2PermissionKind, CoreWebView2PermissionState
        except Exception:
            return

        def asked(_sender, request):
            if request.PermissionKind == CoreWebView2PermissionKind.MultipleAutomaticDownloads:
                request.State = CoreWebView2PermissionState.Allow
        sender.CoreWebView2.PermissionRequested += asked
    on_webview_ready.desk_downloads = True
    return on_webview_ready


def _download_handler(log):
    """내려받기를 **다운로드 폴더에 제 이름으로** 바로 놓는다. 묻는 창은 띄우지 않는다.

    Edge 가 평소 받는 것과 같은 자리·같은 이름 규칙이다. 진행 표시는
    WebView2 가 제 것을 오른쪽 위에 띄운다.

    `window.open(파일 주소)` 로 받는 경우(스페이스기전 첨부 대부분)는 그 일만 하려고 뜬
    빈 창이 남는다. 받기가 끝나면 그 창은 닫는다 — 끝나기 전에 닫으면 받기도 끊긴다.
    """
    def on_download_starting(browser, sender, args):
        operation = args.DownloadOperation
        try:
            spot = down.spot_for(os.path.basename(str(args.ResultFilePath)))
            args.ResultFilePath = str(spot)
        except Exception as exc:
            spot = Path(str(args.ResultFilePath))
            log('다운로드 폴더를 정하지 못해 기본 자리에 받습니다:', exc)
        uri = str(operation.Uri)
        left_blank = _only_for_download(sender, uri)
        log(f'내려받는 중: {spot.name}')

        def changed(_sender, _args):
            state = str(operation.State)
            if state == 'InProgress':
                return
            if state == 'Completed':
                log(f'내려받았습니다: {spot}')
            else:
                log(f'내려받지 못했습니다: {spot.name} ({operation.InterruptReason})')
            if left_blank:
                threading.Thread(target=browser.pywebview_window.destroy,
                                 daemon=True, name='desk-download-close').start()
        operation.StateChanged += changed
    return on_download_starting


def _only_for_download(core, uri: str) -> bool:
    """이 창이 **받기만 하려고 뜬 창**인가. 보여 줄 화면이 하나도 없으면 그렇다."""
    try:
        source = str(core.Source)
    except Exception:
        return False
    return source in ('', 'about:blank') or source == uri
