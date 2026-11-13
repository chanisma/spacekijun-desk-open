"""SPACEKIJUN 에이전트 연결(MCP) — 출력 읽기, Codex 설정 더하기, 인증 창 스크립트, 데스크 액션 (2026-10-25 요청).
진짜 에이전트 설정(~/.claude.json, ~/.codex)에는 닿지 않고, 인증 창도 띄우지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명·설정 파일에는 절대 닿지 않는다
import subprocess
import tempfile
import threading
import time
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from core import agent, automation, spacekijun_mcp as mcp
from desktop import DesktopAPI
from test_automation import FakeProcess, make_skill

URL = mcp.URL


def claude_get(status: str, url: str = URL, scope: str = 'Local config (private to you in this project)') -> str:
    return (f'spacekijun:\n  Scope: {scope}\n  Status: {status}\n  Type: http\n  URL: {url}\n\n'
            'To remove this server, run: claude mcp remove spacekijun -s local\n')


class ParseTests(unittest.TestCase):
    def test_claude_get_states(self):
        self.assertEqual(mcp.parse_claude_get(0, claude_get('! Needs authentication'))['state'], 'auth')
        self.assertEqual(mcp.parse_claude_get(0, claude_get('✓ Connected'))['state'], 'ok')
        self.assertEqual(mcp.parse_claude_get(0, claude_get('✗ Failed to connect'))['state'], 'error')
        self.assertEqual(mcp.parse_claude_get(0, claude_get('✓ Connected', url='https://other.example/mcp'))['state'], 'foreign')
        self.assertEqual(mcp.parse_claude_get(1, 'No MCP server named "spacekijun". Run `claude mcp add` to add one.'),
                         {'state': 'missing', 'scope': ''})
        self.assertTrue(mcp.parse_claude_get(0, claude_get('✓ Connected'))['scope'].startswith('Local'))

    def test_codex_list_states(self):
        row = '{"name": "spacekijun", "enabled": true, "transport": {"type": "streamable_http", "url": "%s"}, "auth_status": "%s"}'
        self.assertEqual(mcp.parse_codex_list('[' + row % (URL, 'not_logged_in') + ']'), 'auth')
        self.assertEqual(mcp.parse_codex_list('WARNING: something\n[' + row % (URL, 'o_auth') + ']'), 'ok')
        self.assertEqual(mcp.parse_codex_list('[' + row % ('https://x.example/mcp', 'o_auth') + ']'), 'foreign')
        self.assertEqual(mcp.parse_codex_list('[]'), 'missing')
        self.assertEqual(mcp.parse_codex_list('not json'), 'error')


class CodexConfigTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.config = Path(room.name) / '.codex' / 'config.toml'

    def test_adds_the_table_with_scopes_and_keeps_the_rest(self):
        self.config.parent.mkdir()
        self.config.write_text('# 내 설정\nmodel = "gpt-5"\n[projects."d:\\\\work"]\ntrust_level = "trusted"', encoding='utf-8')
        self.assertTrue(mcp.codex_register(self.config))
        text = self.config.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('# 내 설정\nmodel = "gpt-5"\n'))
        data = tomllib.loads(text)
        self.assertEqual(data['model'], 'gpt-5')
        self.assertEqual(data['mcp_servers']['spacekijun'], {'url': URL, 'scopes': ['email', 'profile']})
        self.assertNotIn('openid', data['mcp_servers']['spacekijun']['scopes'])        # 이 서버는 openid 를 받지 않는다
        self.assertFalse(mcp.codex_register(self.config))                               # 두 번 더하지 않는다
        self.assertEqual(self.config.read_text(encoding='utf-8'), text)

    def test_creates_the_file_when_missing(self):
        self.assertTrue(mcp.codex_register(self.config))
        self.assertEqual(mcp.codex_entry(self.config)['url'], URL)

    def test_leaves_a_different_server_with_the_same_name_alone(self):
        self.config.parent.mkdir()
        self.config.write_text('[mcp_servers.spacekijun]\nurl = "https://mine.example/mcp"\n', encoding='utf-8')
        with self.assertRaises(mcp.McpError):
            mcp.codex_register(self.config)
        self.assertIn('mine.example', self.config.read_text(encoding='utf-8'))

    def test_does_not_touch_a_config_it_cannot_read(self):
        self.config.parent.mkdir()
        self.config.write_text('model = "unterminated\n', encoding='utf-8')
        with self.assertRaises(mcp.McpError):
            mcp.codex_register(self.config)
        self.assertEqual(self.config.read_text(encoding='utf-8'), 'model = "unterminated\n')


class ClaudeCommandTests(unittest.TestCase):
    """`claude mcp …` 를 흉내 — 어떤 명령을 어느 폴더에서 부르는가."""
    def setUp(self):
        self.calls, self.answers = [], []
        runner = patch.object(mcp, '_run', side_effect=self.fake)
        runner.start()
        self.addCleanup(runner.stop)
        self.folder = Path(tempfile.gettempdir()) / '자동화 업무'

    def fake(self, args, cwd, timeout=mcp.CHECK_TIMEOUT):
        self.calls.append((args[1:], cwd))
        code, out = self.answers.pop(0) if self.answers else (0, '')
        return subprocess.CompletedProcess(args, code, out, '')

    def test_register_adds_to_the_folder_scope_only_when_missing(self):
        self.answers = [(1, 'No MCP server named "spacekijun".'), (0, 'Added')]
        self.assertEqual(mcp.claude_register('claude', self.folder), 'missing')
        self.assertEqual(self.calls[1], (['mcp', 'add', '--transport', 'http', '-s', 'local', 'spacekijun', URL], str(self.folder)))
        self.calls.clear()
        self.answers = [(0, claude_get('! Needs authentication', scope='User config (available in all your projects)'))]
        self.assertEqual(mcp.claude_register('claude', self.folder), 'auth')                    # 이미 있으면 그대로
        self.assertEqual(len(self.calls), 1)

    def test_register_refuses_a_foreign_entry(self):
        self.answers = [(0, claude_get('✓ Connected', url='https://other.example/mcp'))]
        with self.assertRaises(mcp.McpError):
            mcp.claude_register('claude', self.folder)
        self.assertEqual(len(self.calls), 1)

    def test_remove_only_takes_out_the_folder_scope_entry(self):
        self.answers = [(0, claude_get('✓ Connected', scope='User config (available in all your projects)'))]
        self.assertFalse(mcp.claude_remove('claude', self.folder))                              # 사용자가 넣은 것
        self.calls.clear()
        self.answers = [(0, claude_get('✓ Connected')), (0, ''), (0, 'Removed')]
        self.assertTrue(mcp.claude_remove('claude', self.folder))
        self.assertEqual([c[0][:2] for c in self.calls], [['mcp', 'get'], ['mcp', 'logout'], ['mcp', 'remove']])


class LoginTextTests(unittest.TestCase):
    def test_codex_asks_only_for_the_supported_scopes(self):
        text = mcp.login_text('codex', r"C:\Users\o'neil\codex.exe")
        self.assertIn(r"& 'C:\Users\o''neil\codex.exe' mcp login spacekijun --scopes email,profile", text)
        self.assertNotIn('openid', text)
        self.assertNotIn('—', text)                                    # cp949 콘솔

    def test_claude_lets_the_teacher_sign_in_and_waits(self):
        text = mcp.login_text('claude', r'C:\n\claude.cmd')
        self.assertIn(r"& 'C:\n\claude.cmd' mcp login spacekijun", text)
        self.assertNotIn('--scopes', text)
        self.assertIn('직접 로그인', text)
        self.assertIn(mcp.MANAGE_URL, text)
        self.assertIn('exit 1', text)                                  # 실패하면 창을 남긴다


class DesktopTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.root = Path(room.name)
        self.workspace = self.root / '자동화 업무'
        source = self.root / 'source'
        source.mkdir()
        make_skill(source, 'spacekijun-mcp', meta={'title': 'SPACEKIJUN', 'mcp': 'spacekijun'})
        self.api = DesktopAPI()
        self.api._preferences_path = self.root / 'desktop-preferences.json'
        self.api._save_preferences(automation_folder=str(self.workspace), agent_embed=False)
        self.state = {'claude': 'missing', 'codex': 'missing'}
        self.processes, self.registered = [], []

        def login(tool, folder, work_dir):
            self.processes.append((FakeProcess(), tool, folder))
            return self.processes[-1][0]
        for patcher in (patch.object(automation, 'resource_dir', return_value=source),
                        patch.object(agent, 'find', return_value=r'C:\n\claude.cmd'),
                        patch.object(mcp, 'status', side_effect=lambda tool, folder: {'tool': tool, 'state': self.state[tool], 'scope': ''}),
                        patch.object(mcp, 'register', side_effect=lambda tool, folder: self.registered.append((tool, folder))),
                        patch.object(mcp, 'login', side_effect=login),
                        patch.object(mcp, 'remove', return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def wait_for_thread(self):
        for _ in range(100):
            if not any(t.name == 'spacekijun-login' for t in threading.enumerate()):
                return
            time.sleep(0.02)

    def test_connect_registers_then_opens_one_login_window_and_reports_progress(self):
        message = self.api.call('automation_mcp_connect')['data']
        self.assertIn('직접 로그인', message)
        self.assertEqual(self.registered, [('claude', self.workspace)])
        self.assertEqual(self.processes[0][1:], ('claude', self.workspace))
        self.assertTrue((self.workspace / 'AGENTS.md').is_file())                  # 폴더가 없어도 먼저 만든다
        self.assertEqual(self.api.call('automation_mcp_state')['data']['state'], 'authorizing')
        self.assertIn('이미 열려', self.api.call('automation_mcp_connect')['data'])    # 인증 창은 하나만
        self.assertEqual(len(self.processes), 1)
        self.state['claude'] = 'ok'
        self.processes[0][0].finish(0)
        self.wait_for_thread()
        found = self.api.call('automation_mcp_state')['data']
        self.assertEqual(found['state'], 'ok')
        self.assertEqual(found['manage'], mcp.MANAGE_URL)

    def test_already_connected_does_not_open_a_window(self):
        self.state['claude'] = 'ok'
        self.assertIn('이미', self.api.call('automation_mcp_connect')['data'])
        self.assertEqual(self.processes, [])

    def test_state_is_remembered_briefly_and_per_agent(self):
        self.assertEqual(self.api.call('automation_mcp_state')['data']['state'], 'missing')
        self.state['claude'] = 'auth'
        self.assertEqual(self.api.call('automation_mcp_state')['data']['state'], 'missing')            # 잠깐 기억
        self.assertEqual(self.api.call('automation_mcp_state', {'fresh': True})['data']['state'], 'auth')
        self.api.call('agent_settings', {'tool': 'codex'})
        self.assertEqual(self.api.call('automation_mcp_state')['data']['tool'], 'codex')

    def test_register_errors_come_back_as_plain_messages(self):
        with patch.object(mcp, 'register', side_effect=mcp.McpError('같은 이름이 있습니다')):
            result = self.api.call('automation_mcp_connect')
        self.assertFalse(result['ok'])
        self.assertIn('같은 이름', result['error'])
        self.assertEqual(self.processes, [])

    def test_disconnect_and_skill_card_marker(self):
        self.assertIn('뺐습니다', self.api.call('automation_mcp_disconnect')['data'])
        skills = self.api.call('automation_state')['data']['skills']
        self.assertEqual(skills[0]['mcp'], 'spacekijun')


if __name__ == '__main__':
    unittest.main()
