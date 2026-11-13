"""학생판 실행 파일 자체 점검 — 계정·네트워크 없이, 창을 띄우지 않고 번들이 제대로 묶였는지 본다.

    SpacekijunStudent.exe --self-test <보고서.json>
"""
import json
from pathlib import Path
import tempfile
import sys
import traceback


def check(report_path: Path) -> None:
    report = {'ok': False, 'checks': []}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from core import edition
        assert edition.STUDENT and edition.DATA_DIR.endswith('SpacekijunStudent'), edition.DATA_DIR
        from core import secretstore, supa_auth, watcher
        assert secretstore.DATA_DIR == supa_auth.DATA_DIR == watcher.DATA_DIR == edition.DATA_DIR
        report['checks'].append('Student edition with its own data folder (accounts and history never mix with the teacher desk)')
        from core import updater
        report['version'] = edition.STUDENT_VERSION
        updater.version_tuple(edition.STUDENT_VERSION)
        assert (updater.APP, updater.CHANNEL) == ('SpacekijunStudent', 'student'), (updater.APP, updater.CHANNEL)
        assert updater.user_copy().parent == Path(edition.DATA_DIR) / 'app'
        report['checks'].append(f'Auto-update {edition.STUDENT_VERSION}: student channel, signed list, per-user copy when installed read-only')

        import webview                  # noqa: F401 — 번들에 들어 있는지
        import pystray                  # noqa: F401
        from PIL import Image
        from core import capture, clipboard_history, dock_handle, hotkey, web_signin
        assert '"학생"' in web_signin.step_script('aiep') and 'button.button_normal' in web_signin.fill_script('riro', 'a', 'b')
        root = Path(__file__).parent
        for name in ('dock.html', 'dock.js', 'dock.css', 'dock-items.js', 'dock-tones.css', 'popover.html',
                     'popover.js', 'popover.css', 'captures.js', 'fonts.css'):
            assert (root / 'web' / name).is_file(), f'web/{name}'
        items = (root / 'web' / 'dock-items.js').read_text(encoding='utf-8')
        for route in ("'/academy'", "'/tamagotchi'", "'/star-tower'", "'/planner'", "'open_classroom'", "'open_aiep'"):
            assert route in items, route
        assert dock_handle.line_rect('bottom', (0, 0, 200, 77), 1) == (40, 78, 120, 6)
        assert 'off' in hotkey.CHOICES
        with tempfile.TemporaryDirectory() as folder:
            history = clipboard_history.History(Path(folder))
            history.add('text', '학생판 점검')
            assert clipboard_history.History(Path(folder)).listing()[0]['text'] == '학생판 점검'
            assert capture.save(Path(folder), Image.new('RGB', (4, 4))).exists()
        report['checks'].append('Dock, panels, capture, clipboard history (DPAPI), hotkey and in-window sign-in (riro, AIEP) bundled')
        from core import active_folder, agent
        assert 'AGENT' in items[items.index('const STUDENT_GROUPS'):]
        assert '--dangerously-skip-permissions' in agent.launcher_text('C:\\a\\claude.cmd', True, 'claude')
        with tempfile.TemporaryDirectory() as folder:
            assert active_folder.usable(folder, roots=[]) and agent.search_path()
        report['checks'].append('Agent terminal (Claude Code, Codex): folder finder and launcher bundled')
        from core import agent_term       # 데스크 안 에이전트 터미널 (2026-10-24) — 의사 콘솔이 묶여 실제로 도는지
        with tempfile.TemporaryDirectory() as folder:
            assert agent_term.selftest(Path(folder)), 'pseudo console did not answer'
        report['checks'].append('In-desk agent terminal: ConPTY (pywinpty) round trip bundled')
        import os as _os
        from core import computer_use       # 에이전트의 화면 조작 (2026-10-25) — UI Automation 이 실리는지
        computer_use.uia()
        with tempfile.TemporaryDirectory() as folder:
            computer_use.Computer(_os.getpid(), Path(folder)).apps()
        report['checks'].append('Agent computer use: UI Automation (pythonnet) loads and lists windows')
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

        # 교사만 쓰는 기능은 데스크 API 가 거절해야 한다
        import desktop
        api = desktop.DesktopAPI()
        for action, payload in (('portal', {'target': 'neis'}), ('portal', {'target': 'eduptl'}),
                                ('inbox', {}), ('roster', {}), ('save_credentials', {}), ('prepare_cm', {}),
                                ('save_aiep', {}), ('open_page', {'page': 'settings'}), ('sticky_list', {})):
            answer = api.call(action, payload)
            assert not answer['ok'] and '학생용' in answer['error'], (action, answer)
        assert {'/academy', '/tamagotchi', '/star-tower', '/planner'} <= set(desktop.SPACE_ROUTES)
        # 이세계 사회인 (2026-10-19) — 게임 파일이 묶였는지, 열기가 학생판에서 허용되는지 (캐릭터 팩은 Intune 이 따로 깐다)
        from core import isekai3d_server
        assert (isekai3d_server.GAME_DIR / 'index.html').is_file(), isekai3d_server.GAME_DIR
        assert 'open_isekai3d' in desktop.STUDENT_ACTIONS and "'open_isekai3d'" in items
        report['checks'].append('Dwellers 3D game bundled and allowed (characters come from the Intune pack)')
        assert api.call('dock_state')['data']['edition'] == 'student'
        assert api.call('update_status')['ok']                # 자동 업데이트는 학생판도 받는다
        report['checks'].append('Teacher-only actions (NEIS, portals, certificates, CoolMessenger, roster, memos) are refused')
        # 시간표·일정 패널의 '한 주 시간표'·'일정 달력' — 달력 요청은 학생판에서도 받는다 (형식 검사까지 간다)
        answer = api.call('dashboard_month', {'month': 'bad'})
        assert not answer['ok'] and '학생용' not in answer['error'], answer
        popover = (root / 'web' / 'popover.js').read_text(encoding='utf-8')
        assert 'function weekTable' in popover and 'function monthCalendar' in popover
        report['checks'].append('Timetable panel week view and schedule panel month calendar available')
        # 별사이 목장 (2026-11-06) — 화면·그림이 실리고, 목장 요청은 학생판에서 받으며, 정해진 RPC 밖은 거절
        from core import ranch
        sprites = root / 'web' / 'ranch' / 'sprites'
        atlas = (sprites / 'atlas.js').read_text(encoding='utf-8')
        assert (root / 'web' / 'ranch.html').is_file() and 'RANCH_ATLAS' in atlas and (sprites / 'items.png').is_file(), 'ranch files'
        assert all((sprites / f'{name}.png').is_file() for name in ('rabbit_adult', 'rabbit_baby', 'fox_adult', 'char_scarfpigeon', 'visitor_clerk', 'bg_meadow')), 'ranch sprites'
        answer = api.call('ranch_state', {})
        assert answer['ok'] and 'in_class' in answer['data']['lesson'], answer
        answer = api.call('ranch_call', {'work': 'admin_coin_grant', 'body': {}})
        assert not answer['ok'], answer
        assert ranch.place('left', None, (0, 0, 1920, 1040), {}, 1.0)['mode'] == 'desk'
        report['checks'].append('Byeolsai ranch page, sprites and bridge (fixed RPCs only) bundled')
        try:
            import playwright           # noqa: F401
            report['checks'].append('note: playwright is bundled (not needed by the student edition)')
        except ImportError:
            report['checks'].append('Playwright left out of the student bundle')
        if getattr(sys, 'frozen', False):            # 교사판 자동화 업무 스킬은 학생판 실행 파일에 없다 (SpacekijunStudent.spec)
            assert (root / 'resources').is_dir() and not (root / 'resources' / 'skills').exists(), 'teacher skills bundled'
            report['checks'].append('Teacher work skills (resources/skills) left out of the student bundle')
        report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
