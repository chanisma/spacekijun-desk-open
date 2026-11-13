"""Offline smoke check of the actual frozen binary; never starts account watchers."""
import json
from pathlib import Path
import threading
import time
import traceback


def _free_port() -> int:
    """비어 있는 포트 하나 — 고정 번호(9334)는 개발용으로 켜 둔 학생판(SPACEKIJUN_DEBUG_PORT=9334)의 WebView 와 겹쳐,
    점검이 남의 창(ranch·dock·popover)에 붙어 실패했다 (2026-11-07). 켜져 있는 데스크·학생판과 늘 따로 쓰게 그때그때 고른다."""
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


CHECK_PORT = _free_port()  # 데스크의 9333·개발용 학생판과 부딪히지 않는 확인용 통로


def check(report_path):
    report = {'ok': False, 'checks': []}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import webview
        import pystray
        from PIL import Image
        from core import cm_win32, portal, roster, secretstore, supa_auth, watcher
        from playwright.sync_api import sync_playwright
        report['checks'].append('Python services, tray and imaging imports')
        root = Path(__file__).parent
        public = json.loads((root / 'resources' / 'public-config.json').read_text(encoding='utf-8'))
        assert public['url'].startswith('https://') and public['anon_key']
        report['checks'].append('Bundled public configuration')

        # 도우미가 쓰는 지식과 패널은 번들에 들어가야 한다. onefile 에서 조용히 빠지기
        # 쉬운 자리라, 실제 실행 파일 안에서 읽어 보고 넘어간다.
        from core import neis_assist, neis_glossary, neis_menu, neis_overlay, neis_roles
        from core.neis_session import Session
        assert neis_overlay.script().find('__deskAsk') > 0, 'overlay panel script'
        from core import klef_overlay
        assert klef_overlay.script().find('__deskKlefDocs') > 0, 'edufine quick-view script'
        assert len(neis_roles.rows()) > 100, 'role menu list'
        assert neis_roles.tabs_of('과목별출결관리') == ('교과담임', '학급담임')
        assert '동아리활동 출결관리' in neis_glossary.inner_tabs('동아리활동관리')
        assert len(neis_glossary.captured()) > 40, 'captured screen text'
        assert len(neis_glossary.manual()) > 150, 'manual knowledge (scripts/build-neis-manual.py)'
        # 모델 키가 없는 PC 에서도 이름만으로 화면을 골라야 한다 (여기서 통신하면 안 된다).
        account = {'version': neis_menu.CACHE_VERSION, 'at': time.time(),
                   'present': ['교과담임'], 'tabs': {}}
        plan = neis_assist.interpret('과목별출결관리', account)
        assert plan['screen'] == '과목별출결관리' and plan['source'] == 'name', plan
        assert neis_assist.read_date('9월 11일 출결').endswith('-09-11')
        assert Session('packaging-check').state()['screens'] >= 0
        # 내려받은 파일이 갈 자리. 실행 파일 안에서도 다운로드 폴더를 찾아야 한다.
        from core import downloads as down
        assert down.folder().name and '/' not in down.safe_name('../evil.exe')
        report['checks'].append('NEIS assistant: overlay panel, role menu list, '
                                'captured screens and offline intent matching')
        # 자동화 업무 폴더에 깔 업무 스킬 (2026-10-22). resources/skills 는 scripts/sync-desk-skills.py 가 맞춘다.
        from core import automation
        shipped = {item['name']: item for item in automation.catalog()}
        assert 'coolmessenger-send' in shipped, 'bundled work skills (scripts/sync-desk-skills.py)'
        assert (shipped['coolmessenger-send']['path'] / 'send-message.ps1').is_file()
        assert (shipped['edufine']['path'] / 'scripts' / 'edufine.js').is_file(), 'K-에듀파인 skill (2026-10-26)'
        assert (shipped['neis']['path'] / 'knowledge' / 'catalog.json').is_file(), 'NEIS skill (2026-10-26)'
        assert not set(automation.RETIRED) & set(shipped), 'retired skills are not shipped (KakaoTalk, 2026-11-08)'
        # SPACEKIJUN 에이전트 연결 (2026-10-25) — 등록·인증 창 모듈과 그 사용법 스킬
        from core import spacekijun_mcp
        assert shipped['spacekijun-mcp']['mcp'] == 'spacekijun', 'SPACEKIJUN MCP skill'
        import tomllib
        entry = tomllib.loads(spacekijun_mcp.ENTRY_TEXT)['mcp_servers']['spacekijun']
        assert entry == {'url': spacekijun_mcp.URL, 'scopes': ['email', 'profile']}, entry   # openid 는 서버가 받지 않는다
        report['checks'].append('Automation folder: bundled work skills (incl. K-edufine, NEIS), SPACEKIJUN connection')
        # 독·패널·캡처·클립보드·단축키 (2026-10). 함수 안에서 늦게 불러 번들에서 빠지기 쉽다.
        import tempfile
        from core import capture, clipboard_history, dock_handle, hotkey
        web = Path(__file__).parent / 'web'
        for name in ('dock.html', 'dock.js', 'dock.css', 'dock-items.js', 'dock-tones.css', 'popover.html',
                     'popover.js', 'popover.css', 'captures.html', 'captures.js', 'sticky.html', 'sticky.js'):
            assert (web / name).is_file(), f'web/{name}'
        assert dock_handle.line_rect('bottom', (0, 0, 200, 77), 1) == (40, 78, 120, 6)
        assert 'off' in hotkey.CHOICES and hotkey.label(hotkey.DEFAULT)
        with tempfile.TemporaryDirectory() as folder:
            history = clipboard_history.History(Path(folder))
            history.add('text', '패키지 검증')
            assert clipboard_history.History(Path(folder)).listing()[0]['text'] == '패키지 검증'   # DPAPI 왕복
            assert capture.rename(Path(folder), *(lambda p: (p.name, '이름'))(
                capture.save(Path(folder), Image.new('RGB', (4, 4))))).name == '이름.png'
        report['checks'].append('Dock, panels, capture library, clipboard history (DPAPI) and hotkey modules')
        # 에이전트 터미널 (2026-10-13)
        from core import active_folder, agent
        assert '--dangerously-bypass-approvals-and-sandbox' in agent.launcher_text('C:\\a\\codex.cmd', True, 'codex')
        with tempfile.TemporaryDirectory() as folder:
            assert active_folder.usable(folder, roots=[]) and agent.search_path()
        report['checks'].append('Agent terminal (Claude Code, Codex): folder finder and launcher')
        # 데스크 안 에이전트 터미널 (2026-10-24) — 의사 콘솔(pywinpty)이 묶여 실제로 도는지, 화면 파일이 있는지
        from core import agent_term
        for name in ('agent-term.html', 'agent-term.js', 'agent-term.css', 'vendor/xterm/xterm.js', 'vendor/xterm/addon-fit.js'):
            assert (web / name).is_file(), f'web/{name}'
        with tempfile.TemporaryDirectory() as folder:
            assert agent_term.selftest(Path(folder)), 'pseudo console did not answer'
        report['checks'].append('In-desk agent terminal: ConPTY (pywinpty) round trip and xterm.js page bundled')
        # 에이전트끼리 보는 중계 (2026-10-25) — 이 PC 안에서만 열리고, 열쇠 없이는 답하지 않는지
        import urllib.error
        import urllib.request
        from core import agent_bridge
        with tempfile.TemporaryDirectory() as folder:
            bridge = agent_bridge.Bridge(agent_term.Manager(), Path(folder))
            try:
                assert bridge.start().startswith('http://127.0.0.1:') and bridge.guide.is_file()
                try:
                    urllib.request.urlopen(bridge.url + '/agents', timeout=5)
                    raise AssertionError('agent relay answered without a key')
                except urllib.error.HTTPError as error:
                    assert error.code == 401, error.code
            finally:
                bridge.stop()
        report['checks'].append('Agent relay: local-only HTTP, refuses requests without a key')
        # 에이전트의 화면 조작 (2026-10-25) — UI Automation(.NET)이 실행 파일 안에서 실리고 창을 읽는지 (입력은 보내지 않는다)
        import os as _os
        from core import computer_use
        computer_use.uia()
        with tempfile.TemporaryDirectory() as folder:
            computer = computer_use.Computer(_os.getpid(), Path(folder))
            assert all(row['pid'] != _os.getpid() for row in computer.apps())
        assert computer_use.parse_keys('ctrl+s') == [0x11, 0x53] and computer_use.blocked('1Password.exe', '')
        assert (web / 'computer-bar.html').is_file()
        report['checks'].append('Agent computer use: UI Automation (pythonnet) loads, window list, stop bar page bundled')
        # 다른 PC 와 메시지 (2026-10-27) — 모듈이 묶였고, 받은 글 머리에 다른 사람의 요청이라는 표시가 붙는지
        from core import agent_peer
        sample = {'id': 'x', 'body': 'b', 'sender': {'name': 'n', 'label': 'l', 'agent': 'a'}}
        assert '(from another PC)' in agent_peer.request_text(sample) and '/peer/reply/x' in agent_peer.request_text(sample)
        report['checks'].append('Agent messages to other PCs: module bundled, incoming requests are marked')
        # 예약 업무 · 로그인 안내 (2026-11-07) — 모듈이 묶였고 cron 식을 읽는지
        from core import agent_cron
        from datetime import datetime as _dt
        assert agent_cron.Cron('0 8 * * 1-5').next_after(_dt(2026, 11, 6, 9, 0)) == _dt(2026, 11, 9, 8, 0)
        report['checks'].append('Agent scheduled jobs: module bundled, cron expressions parse')
        # 메시지 · Realtime (2026-10-19) — 웹소켓 라이브러리가 묶였는지, 구독이 desk_message 만 보는지
        import websocket  # noqa: F401
        from core import desk_message, realtime
        assert realtime.join_message('t', '1')['payload']['config']['postgres_changes'][0]['filter'] == 'type=eq.desk_message'
        assert desk_message.TYPE == 'desk_message'
        # 메시지 사진 (2026-10-22) — 사진을 열어 확인하는 Pillow 가 묶였는지
        import base64 as _b64, io as _io
        from PIL import Image as _Image
        _png = _io.BytesIO()
        _Image.new('RGB', (3, 2)).save(_png, 'PNG')
        assert desk_message._checked_image({'data': _b64.b64encode(_png.getvalue()).decode()})[1:] == ('image/png', 3, 2)
        report['checks'].append('Messages: Realtime websocket (websocket-client), desk_message panel and photo check (Pillow) bundled')
        # 자동 업데이트 (2026-10-13) — 배포 스크립트가 이 판 번호를 보고 올린다
        from core import edition, ed25519, updater
        report['version'] = edition.DESK_VERSION
        updater.version_tuple(edition.DESK_VERSION)
        assert updater.PUBLIC_KEY != bytes(32), 'update public key is not set'
        seed = bytes(range(32))
        signed = {'manifest': {'app': 'x'}, 'signature': ed25519.sign(seed, updater.canonical({'app': 'x'})).hex()}
        try:
            updater.check_manifest(signed, ed25519.public_key(seed))
        except updater.UpdateError as exc:
            assert '다른 프로그램' in str(exc), exc      # 서명은 맞고, 다른 앱 목록이라 거절
        report['checks'].append(f'Self-update {edition.DESK_VERSION}: signed manifest check (Ed25519)')
        class CheckAPI:
            def call(self, action, payload=None):
                if action == 'dashboard':
                    return {'ok': True, 'data': {'name': '패키지 검증', 'updated_at': '2026-09-10T09:00:00+09:00', 'today': [], 'week': [], 'tasks': [], 'notices': [], 'notifications': [], 'errors': {}}}
                if action != 'state':
                    return {'ok': False, 'error': 'Self-test: actions disabled'}
                return {'ok': True, 'data': {'user': 'packaging@example.test', 'watching': False, 'summary': True,
                    'body': True, 'credentials': False, 'logs': []}}

        # 창을 만들기 전에 손을 걸어야 한다. pywebview 는 창이 뜰 때 새 창 처리기를
        # 묶인 메서드로 등록해 버려서, 나중에 갈아 끼우면 이미 뜬 창에는 듣지 않는다.
        import desktop
        api = desktop.DesktopAPI()
        desktop.install_web_hooks(api._open_popup, api._log)
        window = webview.create_window('SPACEKIJUN package verification', str(root / 'web' / 'index.html'),
                                       js_api=CheckAPI(), hidden=True, width=1180, height=820)
        def verify():
            try:
                deadline = time.monotonic() + 35
                while time.monotonic() < deadline:
                    if window.evaluate_js("document.getElementById('side-status')?.textContent") == '데스크 연결됨':
                        break
                    time.sleep(.25)
                else:
                    raise RuntimeError('WebView2 bridge did not become ready')
                assert window.evaluate_js("getComputedStyle(document.querySelector('.sidebar')).position") == 'fixed'
                assert window.evaluate_js("document.querySelectorAll('.nav').length") == 5   # 업무 홈·쪽지함·스티커 메모·명부·설정
                assert window.evaluate_js("document.fonts.check('14px Pretendard')")
                report['checks'].append('WebView2, HTML/CSS/fonts and JavaScript-Python bridge')
                # 업무시스템은 데스크 안 창에서 열리고, 나이스 도우미는 그 창에 CDP 로
                # 붙는다. 실행 파일로 묶은 뒤에도 붙는지가 관건이라 여기서 확인한다.
                # 실제 데스크가 떠 있어도 부딪히지 않게 포트만 옆으로 옮긴다.
                with sync_playwright() as playwright:
                    browser = playwright.chromium.connect_over_cdp(
                        f'http://127.0.0.1:{CHECK_PORT}')
                    try:
                        urls = [page.url for ctx in browser.contexts for page in ctx.pages]
                        assert any('index.html' in url for url in urls), urls
                        target = next(page for ctx in browser.contexts
                                      for page in ctx.pages if 'index.html' in page.url)
                        target.evaluate("() => { window.__cdpProof = 'reached'; }")
                        assert window.evaluate_js('window.__cdpProof') == 'reached'
                    finally:
                        browser.close()
                report['checks'].append('Bundled Playwright attaches to the desk window over CDP '
                                        '(127.0.0.1 only), so the NEIS helper works inside the app')
                # Hidden self-test windows intentionally skip automatic dashboard polling.
                window.evaluate_js("document.getElementById('refresh-dashboard').click()")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and window.evaluate_js("document.getElementById('dashboard-grid').hidden"):
                    time.sleep(.1)
                assert not window.evaluate_js("document.getElementById('dashboard-grid').hidden")
                assert window.evaluate_js("document.querySelectorAll('.dashboard-card').length") == 5
                report['checks'].append('Bundled desktop dashboard, five sections with offline fixture')
                window.evaluate_js("document.getElementById('open-guide').click()")
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if window.evaluate_js("document.getElementById('guide-frame').contentDocument?.querySelector('h1')?.textContent") == '화면으로 익히는 업무 데스크':
                        break
                    time.sleep(.2)
                else:
                    raise RuntimeError('Bundled React walkthrough did not render')
                assert window.evaluate_js("document.getElementById('guide-frame').contentDocument.querySelectorAll('nav button').length") == 10
                window.evaluate_js("document.getElementById('guide-frame').contentDocument.querySelector('button[aria-label=\"안내 닫기\"]').click()")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and window.evaluate_js("document.getElementById('guide-dialog').open"):
                    time.sleep(.1)
                assert not window.evaluate_js("document.getElementById('guide-dialog').open")
                report['checks'].append('Bundled 10-step React walkthrough, render and close')
                # Exercise the real in-app window lifecycle against a local page,
                # so this runtime check remains offline and cannot access accounts.
                original_url = desktop.SPACEKIJUN_URL
                original_seaton = desktop.SEATON_URL
                try:
                    desktop.SPACEKIJUN_URL = str(root / 'web' / 'index.html')
                    assert api.call('open_space')['ok']
                    embedded = api._space_window
                    assert embedded.evaluate_js('typeof window.pywebview.api.call') == 'undefined'
                    assert api.call('open_space')['ok']
                    assert api._space_window is embedded
                    desktop.SEATON_URL = str(root / 'web' / 'index.html')
                    # 업무시스템 창도 같은 살림이다. 바깥에 나가지 않도록 주소만 로컬로
                    # 바꿔 두고, 안에서 열리는지와 두 번 열리지 않는지를 본다.
                    from unittest.mock import patch
                    with patch.dict(desktop.DesktopAPI.HOME_URL,
                                    {'riro': str(root / 'web' / 'index.html')}):
                        made = api._open_service_window('riro')
                        assert made.evaluate_js('typeof window.pywebview.api.call') == 'undefined'
                        assert api._open_service_window('riro') is made
                    report['checks'].append('Riro and AIEP open as desk windows, one per service, '
                                            'with no Python API exposed to them')
                    # 페이지가 스스로 여는 창도 안에서 열려야 한다. 바깥 브라우저는 프로필이
                    # 달라 로그인이 끊긴다. 로컬 주소로 열어 통신 없이 확인한다.
                    before = len(api._popups)
                    window.evaluate_js("window.open(location.href, '_blank')")
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline and len(api._popups) == before:
                        time.sleep(.2)
                    assert len(api._popups) == before + 1, 'page-opened window stayed outside'
                    report['checks'].append('Windows a page opens itself stay inside the desk, '
                                            'so the signed-in session carries over')
                    assert api.call('open_seaton')['ok']
                    seaton = api._seaton_window
                    assert seaton.evaluate_js('typeof window.pywebview.api.call') == 'undefined'
                    assert api.call('open_seaton')['ok']
                    assert api._seaton_window is seaton
                    report['checks'].append('SPACEKIJUN and Seaton windows, reuse and isolated Python API')
                finally:
                    desktop.SPACEKIJUN_URL = original_url
                    desktop.SEATON_URL = original_seaton
                    api._close()
                report['ok'] = True
            except Exception:
                report['error'] = traceback.format_exc()
            finally:
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                window.destroy()
        # pywebview 가 이 값을 WebView2 에 그대로 넘겨 준다. 환경변수로는 되지 않는다.
        webview.settings['REMOTE_DEBUGGING_PORT'] = CHECK_PORT
        webview.start(verify, gui='edgechromium')
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
