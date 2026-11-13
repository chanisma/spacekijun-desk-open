"""에이전트의 화면 조작 (2026-10-25 요청) — 키 읽기·막는 앱·민감한 칸, 중계의 허락 흐름, 데스크 연결.

진짜 마우스·키보드를 쓰는 시험은 여기서 하지 않는다 (사람이 쓰는 PC 를 건드린다):
    python scripts/check-live-computer-use.py
"""
from test_sandbox import use_sandbox
use_sandbox()
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import desktop
from core import agent, agent_bridge, agent_term, computer_use
from desktop import DesktopAPI


class PureTests(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(computer_use.parse_keys('Enter'), [0x0D])
        self.assertEqual(computer_use.parse_keys('ctrl+shift+s')[:2], [0x11, 0x10])
        self.assertEqual(computer_use.parse_keys('CmdOrCtrl+A')[0], 0x11)
        self.assertEqual(computer_use.parse_keys('alt+F4'), [0x12, 0x73])
        for bad in ('', 'ctrl+shift', 'ctrl+nothing', 'x' * 70, None, 3):
            with self.assertRaises(computer_use.ComputerError, msg=bad):
                computer_use.parse_keys(bad)
        with self.assertRaises(computer_use.ComputerError):
            computer_use.parse_keys('ctrl+a', allow_plain_modifier=False)
        self.assertEqual(computer_use.parse_keys('shift', allow_plain_modifier=False), [0x10])

    def test_blocked_apps(self):
        self.assertTrue(computer_use.blocked('1Password.exe', ''))
        self.assertTrue(computer_use.blocked('KeePass.exe', 'db'))
        self.assertTrue(computer_use.blocked('consent.exe', ''))
        self.assertFalse(computer_use.blocked('CoolMessenger.exe', '쿨메신저'))

    def test_sensitive_words(self):
        for text in ('Password', '비밀번호 입력', '인증번호', 'OTP code', 'PIN', 'one-time code', '주민등록번호'):
            self.assertTrue(computer_use.SENSITIVE.search(text), text)
        for text in ('Spinner', 'Pinned tabs', '메모', 'Note'):
            self.assertFalse(computer_use.SENSITIVE.search(text), text)

    def test_snapshot_line(self):
        info = {'role': 'Edit', 'name': '받는 사람', 'value': '김선생', 'enabled': True, 'offscreen': False,
                'focus': True, 'secret': False, 'box': (10, 20, 100, 24), 'actions': ['set-value']}
        self.assertEqual(computer_use.format_line(3, info, 1), '  [3] Edit "받는 사람" value="김선생" @(10,20 100x24) focused {set-value}')
        secret = {**info, 'name': 'Password', 'value': '[redacted]', 'secret': True, 'enabled': False, 'focus': False}
        line = computer_use.format_line(4, secret, 0)
        self.assertIn('[redacted]', line)
        self.assertIn('(sensitive)', line)
        self.assertIn('disabled', line)


class FakeComputer:
    """진짜 화면 대신 — 창 1001(메모장)·1002(데스크)·1003(막는 앱)."""
    def __init__(self):
        self.calls = []

    def apps(self):
        return [{'window': 1001, 'pid': 7, 'app': 'notepad.exe', 'title': '메모 - 메모장', 'minimized': False, 'size': (800, 600),
                 'blocked': False},
                {'window': 1003, 'pid': 9, 'app': 'KeePass.exe', 'title': 'db', 'minimized': True, 'size': (1, 1), 'blocked': True}]

    def window(self, value):
        if str(value) == '1002':
            raise computer_use.ComputerError('데스크의 창은 다룰 수 없습니다.', 403)
        if str(value) != '1001':
            raise computer_use.ComputerError('그 창이 없습니다.', 404)
        return {'window': 1001, 'pid': 7, 'app': 'notepad.exe', 'title': '메모 - 메모장'}

    def state(self, who, hwnd, limit=300):
        self.calls.append(('state', who, hwnd))
        return f'window {hwnd} "메모" — 2 elements\n[0] Window "메모"\n  [1] Document value="" {{set-value}}\n'

    def click(self, who, hwnd, payload):
        self.calls.append(('click', payload))
        return f'clicked element {payload.get("element")}'

    def type(self, who, hwnd, payload):
        self.calls.append(('type', payload))
        return f'typed {len(payload["text"])} characters'

    def keys(self, who, hwnd, payload):
        self.calls.append(('keys', payload))
        return f'pressed {payload["keys"]}'

    paste = type
    scroll = drag = set_value = action = click

    def screenshot(self, who, hwnd):
        return {'path': 'C:/shots/x.png', 'width': 800, 'height': 600, 'scale': 1.0}

    def settle(self):
        pass

    def forget(self, who=None):
        self.calls.append(('forget', who))


class BridgeComputerTests(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        folder = Path(self.room.name) / 'p'
        folder.mkdir()
        exe = Path(self.room.name) / 'fake.cmd'
        exe.write_text('@echo off\r\necho READY\r\n', encoding='ascii')
        for patcher in (patch.object(agent, 'find', return_value=str(exe)),
                        patch.object(agent_term.Session, 'agent_running', return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.manager = agent_term.Manager()
        self.addCleanup(self.manager.close_all)
        self.computer = FakeComputer()
        self.asked, self.answer = [], True
        self.bridge = agent_bridge.Bridge(self.manager, Path(self.room.name), computer=self.computer,
                                          approve=lambda session, info: self.asked.append(info['app']) or self.answer)
        self.addCleanup(self.bridge.stop)
        self.grant_changes = []
        self.bridge.on_grants = lambda: self.grant_changes.append(len(self.bridge.grants()))
        self.me = self.manager.open('claude', str(folder), False, Path(self.room.name), team=self.bridge)
        self.other = self.manager.open('codex', str(folder), False, Path(self.room.name), team=self.bridge)

    def call(self, path, body=None, me=None):
        data = json.dumps(body).encode('utf-8') if isinstance(body, dict) else body
        request = urllib.request.Request(self.bridge.url + path, data=data, method='POST' if data is not None else 'GET')
        request.add_header('X-Desk-Token', (me or self.me).env['DESK_AGENT_TOKEN'])
        request.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(request, timeout=10) as answer:
                return answer.status, answer.read().decode('utf-8')
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode('utf-8')

    def test_apps_need_no_approval_and_mark_blocked(self):
        code, text = self.call('/computer/apps')
        self.assertEqual(code, 200)
        self.assertIn('1001\tnotepad.exe\t메모 - 메모장\tasks the user first', text)
        self.assertIn('blocked, minimized', text)
        self.assertEqual(self.asked, [])

    def test_first_use_asks_once_then_remembers_per_agent_and_app(self):
        code, text = self.call('/computer/state?window=1001')
        self.assertEqual(code, 200, text)
        self.assertIn('[1] Document', text)
        self.call('/computer/click', {'window': 1001, 'element': 1})
        self.assertEqual(self.asked, ['notepad.exe'])                  # 한 번만 묻는다
        self.call('/computer/state?window=1001', me=self.other)
        self.assertEqual(self.asked, ['notepad.exe', 'notepad.exe'])   # 다른 에이전트는 따로 묻는다
        self.assertEqual({item['agent'] for item in self.bridge.grants()}, {'claude-1', 'codex-1'})
        self.assertEqual(self.grant_changes[:2], [1, 2])

    def test_actions_return_a_fresh_snapshot_and_are_logged(self):
        code, text = self.call('/computer/type', {'window': 1001, 'element': 1, 'text': '안녕하세요'})
        self.assertEqual(code, 200, text)
        self.assertTrue(text.startswith('ok: typed 5 characters'))
        self.assertIn('[1] Document', text)                           # 하고 나서 새 스냅숏
        code, text = self.call('/computer/key', {'window': 1001, 'keys': 'ctrl+s', 'snapshot': False, 'screenshot': True})
        self.assertNotIn('[1] Document', text)
        self.assertIn('screenshot: C:/shots/x.png', text)
        kinds = [(event['kind'], event['toName']) for event in self.manager.events()['events']]
        self.assertIn(('computer', 'notepad.exe'), kinds)
        self.assertTrue(any('typed 5' in event['text'] for event in self.manager.events()['events']))

    def test_refusal_is_remembered_for_a_while(self):
        self.answer = False
        self.assertEqual(self.call('/computer/state?window=1001')[0], 403)
        code, text = self.call('/computer/click', {'window': 1001, 'element': 1})
        self.assertEqual(code, 403)
        self.assertIn('do not ask again', text)
        self.assertEqual(self.asked, ['notepad.exe'])                  # 연달아 묻지 않는다
        self.assertFalse(any(call[0] == 'click' for call in self.computer.calls))

    def test_stop_revokes_everything(self):
        self.call('/computer/state?window=1001')
        self.assertEqual(self.bridge.revoke(), 1)
        self.assertEqual(self.bridge.grants(), [])
        self.assertIn(('forget', None), self.computer.calls)
        self.answer = False
        self.assertEqual(self.call('/computer/click', {'window': 1001, 'element': 1})[0], 403)   # 다시 묻고, 거절

    def test_desk_and_unknown_windows_and_bad_requests(self):
        self.assertEqual(self.call('/computer/state?window=1002')[0], 403)
        self.assertEqual(self.call('/computer/state?window=99')[0], 404)
        self.assertEqual(self.call('/computer/click', b'not json')[0], 400)
        self.assertEqual(self.call('/computer/fly', {'window': 1001})[0], 404)
        self.assertEqual(self.asked, [])                               # 창을 확인하기 전에는 묻지 않는다

    def test_always_allowed_apps_skip_the_question_until_stopped(self):
        rules = {'notepad.exe'}
        self.bridge.always = lambda info: info['app'].lower() in rules
        self.answer = False
        self.assertIn('1001\tnotepad.exe\t메모 - 메모장\tallowed', self.call('/computer/apps')[1])
        code, text = self.call('/computer/state?window=1001')
        self.assertEqual(code, 200, text)
        self.assertEqual(self.asked, [])                               # 묻지 않았다
        self.assertTrue(self.bridge.grants()[0]['always'])
        self.assertIn('항상 허락', [event['text'] for event in self.manager.events()['events']])
        self.bridge.revoke(halt=True)                                  # 멈추기 — 항상 허락도 쉰다
        self.assertTrue(self.bridge.halted)
        self.assertEqual(self.call('/computer/state?window=1001')[0], 403)
        self.assertEqual(self.asked, ['notepad.exe'])                  # 그동안은 묻는다 (그리고 거절)
        self.bridge.resume()
        self.assertEqual(self.call('/computer/state?window=1001')[0], 200)   # 거절 기억보다 항상 허락이 먼저
        self.assertEqual(self.asked, ['notepad.exe'])

    def test_a_broken_always_rule_falls_back_to_asking(self):
        self.bridge.always = lambda info: 1 / 0
        self.assertEqual(self.call('/computer/state?window=1001')[0], 200)
        self.assertEqual(self.asked, ['notepad.exe'])

    def test_without_computer_it_is_unavailable(self):
        self.bridge.computer = None
        self.assertEqual(self.call('/computer/apps')[0], 501)


class DesktopComputerTests(unittest.TestCase):
    def setUp(self):
        self.api = DesktopAPI()
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.api._preferences_path = Path(self.room.name) / 'desktop-preferences.json'

    def tearDown(self):
        if self.api._term_bridge:
            self.api._term_bridge.stop()

    def test_ask_without_the_window_refuses(self):
        self.assertFalse(self.api._term_computer_ask(None, {'app': 'x', 'title': 't'}))

    def test_answer_wakes_the_waiting_question(self):
        class Window:
            def __init__(self):
                self.scripts = []
            def run_js(self, script):
                self.scripts.append(script)
            show = restore = lambda self: None
        window = Window()
        self.api._term_window, self.api._term_ready = window, True
        session = type('S', (), {'id': 't1', 'title': '', 'name': 'claude-1'})()
        result = {}
        with patch.object(DesktopAPI, '_bring_front'):
            thread = threading.Thread(target=lambda: result.update(allow=self.api._term_computer_ask(session, {'app': 'notepad.exe', 'title': '메모'})))
            thread.start()
            for _ in range(50):
                if self.api._term_asks:
                    break
                time.sleep(0.02)
            request = next(iter(self.api._term_asks))
            self.assertIn('askComputer', window.scripts[0])
            self.assertTrue(self.api.call('term_computer_answer', {'request': request, 'allow': True})['ok'])
            thread.join(5)
        self.assertTrue(result['allow'])
        self.assertIn('askDone', window.scripts[-1])
        self.assertFalse(self.api.call('term_computer_answer', {'request': request, 'allow': True})['ok'])   # 끝난 질문
        self.assertFalse(self.api.call('term_computer_answer', {'request': 'x', 'allow': 'yes'})['ok'])

    def test_answer_can_allow_always_for_the_app_or_everything(self):
        self.api._term_manager()
        for always, expect in (('app', {'all': False, 'apps': ['notepad.exe']}), ('all', {'all': True, 'apps': ['notepad.exe']})):
            event = threading.Event()
            self.api._term_asks['r'] = waiting = {'event': event, 'allow': False, 'app': 'notepad.exe'}
            answer = self.api.call('term_computer_answer', {'request': 'r', 'allow': True, 'always': always})
            self.assertTrue(answer['ok'], answer)
            self.assertTrue(waiting['allow'] and event.is_set())
            self.assertEqual(self.api._term_always_rules(), expect)
        self.api._term_asks['r'] = {'event': threading.Event(), 'allow': False, 'app': 'mspaint.exe'}
        self.assertFalse(self.api.call('term_computer_answer', {'request': 'r', 'allow': True, 'always': 'forever'})['ok'])
        self.api.call('term_computer_answer', {'request': 'r', 'allow': False, 'always': 'app'})   # 거절이면 남기지 않는다
        self.assertEqual(self.api._term_always_rules()['apps'], ['notepad.exe'])

    def test_always_rules_are_edited_and_only_used_while_the_window_is_open(self):
        self.api._term_manager()
        self.assertIn('묻지 않고', self.api.call('term_computer_always', {'add': 'CoolMessenger.exe'})['data'])
        self.api.call('term_computer_always', {'add': 'coolmessenger.exe'})                     # 같은 앱은 한 번만
        self.assertEqual(self.api._term_always_rules(), {'all': False, 'apps': ['CoolMessenger.exe']})
        self.assertFalse(self.api.call('term_computer_always', {'add': 'KeePass.exe'})['ok'])    # 막아 둔 앱
        self.assertFalse(self.api.call('term_computer_always', {})['ok'])
        info = {'app': 'coolmessenger.exe', 'title': '쿨메신저'}
        self.assertFalse(self.api._term_computer_always_match(info))                            # 창이 닫혀 있다
        self.api._term_window, self.api._term_ready = object(), True
        self.assertTrue(self.api._term_computer_always_match(info))
        self.assertFalse(self.api._term_computer_always_match({'app': 'excel.exe', 'title': ''}))
        self.api.call('term_computer_always', {'all': True})
        self.assertTrue(self.api._term_computer_always_match({'app': 'excel.exe', 'title': ''}))
        self.api.call('term_computer_always', {'remove': 'COOLMESSENGER.EXE'})
        self.assertEqual(self.api._term_always_rules(), {'all': True, 'apps': []})
        self.api.call('term_computer_always', {'clear': True})
        self.assertEqual(self.api._term_always_rules(), {'all': False, 'apps': []})

    def test_stop_everything_halts_always_and_resume_restores_it(self):
        self.api._term_manager()
        self.api.call('term_computer_always', {'all': True})
        self.assertIn('다시 켜기', self.api.call('term_computer_stop')['data'])
        self.assertTrue(self.api.call('term_computer_list')['data']['halted'])
        self.api.call('term_computer_resume')
        self.assertFalse(self.api.call('term_computer_list')['data']['halted'])

    def test_options_list_open_apps_without_blocked_ones(self):
        self.api._term_manager()
        self.api._term_bridge.computer = FakeComputer()
        data = self.api.call('term_computer_options')['data']
        self.assertEqual(data['open'], [{'app': 'notepad.exe', 'title': '메모 - 메모장'}])
        self.assertEqual((data['all'], data['apps'], data['grants'], data['halted']), (False, [], [], False))

    def test_stop_and_list(self):
        self.api._term_manager()
        self.assertEqual(self.api.call('term_computer_list')['data'], {'grants': [], 'halted': False, 'all': False, 'apps': []})
        self.assertIn('없습니다', self.api.call('term_computer_stop')['data'])
        self.assertFalse(self.api.call('term_computer_stop', {'session': 3})['ok'])

    def test_actions_are_allowed_for_students_and_the_bar_page_exists(self):
        for action in ('term_computer_answer', 'term_computer_list', 'term_computer_stop',
                       'term_computer_options', 'term_computer_always', 'term_computer_resume'):
            self.assertIn(action, desktop.STUDENT_ACTIONS)
        self.assertTrue((Path(desktop.__file__).parent / 'web' / 'computer-bar.html').is_file())


if __name__ == '__main__':
    unittest.main()
