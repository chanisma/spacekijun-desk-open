"""에이전트 터미널 — 폴더 찾기·실행 줄·설정 (2026-10-13 요청). 터미널은 진짜로 띄우지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명·설정 파일에는 절대 닿지 않는다
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop
from core import active_folder, agent
from desktop import DesktopAPI


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.work = Path(self.room.name) / 'data'
        self.folder = Path(self.room.name) / '수업 자료'
        self.folder.mkdir()

    def test_each_tool_has_its_own_skip_flag(self):
        self.assertEqual(agent.TOOLS['claude']['skip'], '--dangerously-skip-permissions')
        self.assertEqual(agent.TOOLS['codex']['skip'], '--dangerously-bypass-approvals-and-sandbox')
        self.assertEqual(agent.launcher_text(r'C:\npm\claude.cmd', True, 'claude'),
                         '@echo off\r\ncall "C:\\npm\\claude.cmd" --dangerously-skip-permissions\r\n')
        self.assertNotIn('dangerously', agent.launcher_text(r'C:\npm\codex.cmd', False, 'codex'))
        self.assertIn('C:\\100%%\\codex.exe', agent.launcher_text(r'C:\100%\codex.exe', False, 'codex'))

    def test_windows_terminal_is_used_when_there_is_one(self):
        with patch('shutil.which', return_value=r'C:\Apps\wt.exe'):
            args, console = agent.terminal_args(str(self.folder), 'Claude Code · 수업 자료', ['cmd.exe', '/k', 'x.cmd'])
        self.assertEqual(args[:5], [r'C:\Apps\wt.exe', '-w', 'new', '-d', str(self.folder)])
        self.assertEqual(args[-3:], ['cmd.exe', '/k', 'x.cmd'])
        self.assertFalse(console)
        with patch('shutil.which', return_value=None):
            self.assertEqual(agent.terminal_args('C:\\a', 't', ['cmd.exe']), (['cmd.exe'], True))
        with patch('shutil.which', return_value=r'C:\Apps\wt.exe'):     # wt 는 ; 를 명령 구분으로 읽는다
            self.assertEqual(agent.terminal_args('C:\\a;b', 't', ['cmd.exe']), (['cmd.exe'], True))

    def test_launch_writes_the_launcher_and_opens_the_terminal_in_the_folder(self):
        with patch.object(agent, 'find', return_value=r'C:\npm\claude.cmd'), \
             patch('shutil.which', return_value=None), patch.object(agent, 'spawn') as spawn:
            message = agent.launch('claude', str(self.folder), True, self.work)
        script = self.work / 'agent' / 'claude.cmd'
        self.assertIn('--dangerously-skip-permissions', script.read_text(encoding='oem'))
        spawn.assert_called_once_with(['cmd.exe', '/k', str(script)], str(self.folder), True)
        self.assertIn('수업 자료', message)
        self.assertIn('권한 묻지 않기', message)

    def test_launch_refuses_without_the_tool_or_the_folder(self):
        with patch.object(agent, 'find', return_value=None), patch.object(agent, 'spawn') as spawn:
            with self.assertRaisesRegex(RuntimeError, '설치'):
                agent.launch('codex', str(self.folder), False, self.work)
        with patch.object(agent, 'find', return_value='codex.exe'), patch.object(agent, 'spawn'):
            with self.assertRaises(ValueError):
                agent.launch('codex', str(self.folder / '없음'), False, self.work)
        spawn.assert_not_called()

    def test_install_scripts(self):
        claude, codex = agent.install_text('claude'), agent.install_text('codex')
        self.assertIn(agent.CLAUDE_INSTALL, claude)
        self.assertNotIn('Invoke-Expression', claude)         # 공식 스크립트의 exit 가 창을 닫지 않게 따로 돌린다
        self.assertIn('-File $official', claude)
        self.assertIn('OpenAI.Codex', codex)
        self.assertIn('@openai/codex', codex)                 # winget 이 없으면 npm
        with patch.object(agent, 'spawn') as spawn, patch('shutil.which', return_value=None):
            agent.install('codex', self.work)
        script = self.work / 'agent' / 'install-codex.ps1'
        self.assertTrue(script.read_bytes().startswith(b'\xef\xbb\xbf'))   # PowerShell 5.1 한글
        self.assertIn('-File', spawn.call_args.args[0])
        with self.assertRaises(ValueError):
            agent.install('rm -rf', self.work)

    def test_codex_from_winget_is_found_without_the_codex_link(self):
        """winget 이 링크를 못 만들었거나 관리자로 깔았을 때 — 패키지 폴더·Program Files 링크에서 찾는다 (2026-10-19)."""
        local, programs = self.work / 'local', self.work / 'programs'
        package = local / 'Microsoft' / 'WinGet' / 'Packages' / 'OpenAI.Codex_Microsoft.Winget.Source_8wekyb3d8bbwe'
        package.mkdir(parents=True)
        for name in ('codex-command-runner.exe', 'codex-windows-sandbox-setup.exe'):
            (package / name).write_bytes(b'')
        env = {'LOCALAPPDATA': str(local), 'ProgramFiles': str(programs), 'ProgramW6432': '', 'ProgramFiles(x86)': ''}
        with patch.dict('os.environ', env), patch('shutil.which', return_value=None):
            self.assertIsNone(agent.find('codex'))                     # 도우미 실행 파일은 Codex 가 아니다
            (package / 'codex-x86_64-pc-windows-msvc.exe').write_bytes(b'')
            self.assertEqual(agent.find('codex'), str(package / 'codex-x86_64-pc-windows-msvc.exe'))
            self.assertIsNone(agent.find('claude'))                    # Claude Code 는 winget 자리를 보지 않는다
            script = agent.install_text('codex')
        self.assertIn(str(programs / 'WinGet' / 'Links' / 'codex.exe'), script)
        self.assertIn('codex-*-pc-windows-msvc.exe', script)
        (package / 'codex-x86_64-pc-windows-msvc.exe').unlink()
        link = programs / 'WinGet' / 'Links'
        link.mkdir(parents=True)
        (link / 'codex.exe').write_bytes(b'')
        with patch.dict('os.environ', env), patch('shutil.which', return_value=None):
            self.assertEqual(agent.find('codex'), str(link / 'codex.exe'))

    def test_winget_codex_before_the_daemon_fix_opens_without_the_daemon(self):
        """winget 판 0.157~0.161 은 백그라운드 서버 준비에서 멈춘다 (openai/codex #51721) — --no-daemon 으로 연다."""
        package = self.work / 'OpenAI.Codex_x'
        package.mkdir(parents=True)
        exe = package / 'codex-x86_64-pc-windows-msvc.exe'
        exe.write_bytes(b'')

        def manifest(version, entrypoint='codex-x86_64-pc-windows-msvc.exe'):
            (package / 'codex-package.json').write_text(json.dumps(
                {'layoutVersion': 1, 'version': version, 'target': 'x86_64-pc-windows-msvc', 'entrypoint': entrypoint}),
                encoding='utf-8')

        manifest('0.161.0')
        self.assertEqual(agent.launcher_text(str(exe), True, 'codex'),
                         f'@echo off\r\ncall "{exe}" --no-daemon --dangerously-bypass-approvals-and-sandbox\r\n')
        manifest('0.163.0')                                    # 고쳐진 판은 그대로
        self.assertNotIn('--no-daemon', agent.launcher_text(str(exe), False, 'codex'))
        manifest('0.161.0', 'bin/codex.exe')                  # winget 판이 아니면 그대로
        self.assertNotIn('--no-daemon', agent.launcher_text(str(exe), False, 'codex'))
        manifest('0.161.0')
        self.assertNotIn('--no-daemon', agent.launcher_text(str(exe), False, 'claude'))
        self.assertNotIn('--no-daemon', agent.launcher_text(r'C:\npm\codex.cmd', False, 'codex'))

    def test_search_path_includes_where_installers_put_agents(self):
        path = agent.search_path().lower()
        self.assertIn(str(Path.home() / '.local' / 'bin').lower(), path)
        self.assertIn('winget', path)

    def test_child_environment_drops_pyinstaller_values(self):
        with patch.dict(os.environ, {'_MEIPASS2': 'x', '_PYI_APPLICATION_HOME_DIR': 'y', 'KEEP': 'z'}):
            env = agent.clean_env()
        self.assertNotIn('_MEIPASS2', env)
        self.assertNotIn('_PYI_APPLICATION_HOME_DIR', env)
        self.assertEqual(env['KEEP'], 'z')


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.root = Path(self.room.name)
        (self.root / '보고서').mkdir()
        (self.root / '보고서' / '1학기 평가.hwp').write_text('x', encoding='utf-8')

    def test_usable_keeps_real_folders_and_drops_system_ones(self):
        file = self.root / '보고서' / '1학기 평가.hwp'
        self.assertEqual(active_folder.usable(str(file), roots=[]), str(self.root / '보고서'))
        self.assertIsNone(active_folder.usable(str(self.root / '없음'), roots=[]))
        self.assertIsNone(active_folder.usable('relative\\path', roots=[]))
        root = os.path.normcase(str(self.root))
        self.assertIsNone(active_folder.usable(str(self.root / '보고서'), roots=[root]))
        self.assertIsNone(active_folder.usable(os.environ.get('SystemRoot', r'C:\Windows')))

    def test_paths_in_window_titles_and_arguments(self):
        file = self.root / '보고서' / '1학기 평가.hwp'
        self.assertEqual(active_folder.paths_in_text(f'{file} - 한글'), [str(file)])
        self.assertEqual(active_folder.paths_in_text('제목 없음 - 메모장'), [])
        self.assertEqual(active_folder.paths_in_arguments(['Hwp.exe', str(file)]), [str(file)])
        self.assertEqual(active_folder.paths_in_arguments(['x.exe', f'/open:{file}', '--flag']), [f'{file}'])
        self.assertEqual(active_folder.paths_in_arguments([str(file)]), [])          # 첫 인자는 프로그램 자신

    def test_code_editors_folder_is_matched_by_the_window_title(self):
        project = self.root / 'my-app'
        other = self.root / 'notes'
        project.mkdir(); other.mkdir()
        storage = self.root / 'Code' / 'User' / 'globalStorage'
        storage.mkdir(parents=True)
        uri = lambda path: 'file:///' + str(path).replace('\\', '/').replace(' ', '%20')
        (storage / 'storage.json').write_text(json.dumps({
            'windowsState': {'lastActiveWindow': {'folder': uri(other)}, 'openedWindows': [{'folder': uri(project)}]},
            'backupWorkspaces': {'folders': [{'folderUri': uri(project)}]}}), encoding='utf-8')
        found = active_folder.code_folders(self.root / 'Code', 'main.py - my-app - Visual Studio Code')
        self.assertEqual([os.path.normcase(path) for path in found], [os.path.normcase(str(project))])
        both = active_folder.code_folders(self.root / 'Code', 'Welcome - Visual Studio Code')
        self.assertEqual(len(both), 2)                          # 못 맞추면 열린 것 전부 — 고르게 한다
        self.assertEqual(active_folder.code_folders(self.root / '없음', 'x'), [])

    def test_unique_drops_duplicates_and_missing(self):
        folder = str(self.root / '보고서')
        with patch.object(active_folder, '_system_roots', return_value=[]):
            self.assertEqual(active_folder.unique([folder, folder.upper(), str(self.root / '없음'), folder + '\\']),
                             [folder])

    def test_tracker_remembers_the_last_window_that_is_not_ours(self):
        tracker = active_folder.Tracker(own_pid=100)
        pids = {1: 200, 2: 100, 3: 300}
        classes = {1: 'CabinetWClass', 2: 'WinFormsWindow', 3: 'Shell_TrayWnd'}
        with patch.object(active_folder, 'window_pid', side_effect=pids.get), \
             patch.object(active_folder, 'window_class', side_effect=classes.get):
            tracker.see(1)
            tracker.see(2)            # 독·패널 — 이 프로그램
            tracker.see(3)            # 작업 표시줄
            tracker.see(0)
        self.assertEqual(tracker.last, 1)


class AgentActionTests(unittest.TestCase):
    """데스크 쪽 연결 — 설정 저장·자주 쓰는 폴더·바로 열기."""
    def setUp(self):
        self.api = DesktopAPI()
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.api._preferences_path = Path(self.room.name) / 'desktop-preferences.json'
        self.api._save_preferences(agent_embed=False)     # 바깥 터미널 경로 — 데스크 안 터미널은 test_agent_term
        self.folder = Path(self.room.name) / 'project'
        self.folder.mkdir()
        launch = patch.object(agent, 'launch', return_value='열었습니다')
        self.launch = launch.start()
        self.addCleanup(launch.stop)

    def active(self, folders):
        return patch.object(active_folder, 'folders_of', return_value={'app': 'x', 'title': 't', 'folders': folders})

    def test_settings_are_saved_and_checked(self):
        self.assertTrue(self.api.call('agent_settings', {'tool': 'codex', 'skip': True})['ok'])
        self.assertEqual(self.api._agent_choice(), ('codex', True))
        self.assertFalse(self.api.call('agent_settings', {'tool': 'bash'})['ok'])
        self.assertFalse(self.api.call('agent_settings', {'skip': 'yes'})['ok'])
        self.assertFalse(self.api.call('agent_settings', {})['ok'])
        self.assertEqual(self.api._read_preferences()['agent_tool'], 'codex')

    def test_favorites_are_added_once_and_removed(self):
        folder = str(self.folder)
        self.assertTrue(self.api.call('agent_favorite', {'folder': folder, 'on': True})['ok'])
        self.assertIn('이미', self.api.call('agent_favorite', {'folder': folder, 'on': True})['data'])
        self.assertEqual(self.api._agent_favorites(), [os.path.normpath(folder)])
        self.assertFalse(self.api.call('agent_favorite', {'folder': folder + '\\없음', 'on': True})['ok'])
        self.assertFalse(self.api.call('agent_favorite', {'folder': 'relative', 'on': True})['ok'])
        self.assertTrue(self.api.call('agent_favorite', {'folder': folder, 'on': False})['ok'])
        self.assertEqual(self.api._agent_favorites(), [])

    def test_run_only_opens_real_folders(self):
        self.assertTrue(self.api.call('agent_run', {'folder': str(self.folder)})['ok'])
        self.assertEqual(self.launch.call_args.args[:3], ('claude', os.path.normpath(str(self.folder)), False))
        for bad in (None, '', 'relative', str(self.folder / '없음'), 'C:\\x\x00'):
            self.assertFalse(self.api.call('agent_run', {'folder': bad})['ok'], bad)

    def test_quick_launch_only_when_exactly_one_folder(self):
        self.api._foreground = active_folder.Tracker(own_pid=1)
        self.api._foreground.last = 123
        tools = {name: {'label': info['label'], 'installed': True, 'path': '', 'skip_flag': info['skip']}
                 for name, info in agent.TOOLS.items()}
        # 처음에는 묻는다 — 곧 열릴 패널이 한 번만 '이 폴더에서 열까요?'를 싣는다 (2026-10-25)
        with self.active([str(self.folder)]), patch.object(agent, 'find', return_value='claude.exe'), \
             patch.object(agent, 'tools', return_value=tools), patch.object(active_folder, 'open_explorer_folders', return_value=[]):
            self.assertEqual(self.api.call('agent_quick')['data'], {'launched': False, 'ask': True})
            state = self.api.call('agent_state')['data']
            self.assertEqual(state['ask'], {'path': str(self.folder), 'name': 'project'})
            self.assertTrue(state['askOn'])
            self.assertIsNone(self.api.call('agent_state')['data']['ask'])          # 한 번만
        self.assertEqual(self.launch.call_count, 0)
        self.assertTrue(self.api.call('agent_settings', {'ask': False})['ok'])         # 앞으로 묻지 않기
        self.assertFalse(self.api.call('agent_settings', {'ask': 'no'})['ok'])
        with self.active([str(self.folder)]), patch.object(agent, 'find', return_value='claude.exe'):
            answer = self.api.call('agent_quick')['data']
        self.assertEqual(answer, {'launched': True, 'message': '열었습니다'})
        for folders in ([], [str(self.folder), str(self.folder)]):
            with self.active(folders), patch.object(agent, 'find', return_value='claude.exe'):
                self.assertEqual(self.api.call('agent_quick')['data'], {'launched': False})
        with self.active([str(self.folder)]), patch.object(agent, 'find', return_value=None):
            self.assertEqual(self.api.call('agent_quick')['data'], {'launched': False})   # 설치부터
        self.assertEqual(self.launch.call_count, 1)

    def test_state_lists_tools_active_folders_and_favorites(self):
        self.api.call('agent_favorite', {'folder': str(self.folder), 'on': True})
        tools = {name: {'label': info['label'], 'installed': False, 'path': '', 'skip_flag': info['skip']}
                 for name, info in agent.TOOLS.items()}
        with self.active([str(self.folder)]), patch.object(agent, 'tools', return_value=tools), \
             patch.object(active_folder, 'open_explorer_folders', return_value=[]):
            state = self.api.call('agent_state')['data']
        self.assertEqual(state['tool'], 'claude')
        self.assertFalse(state['skip'])
        self.assertEqual(state['active']['folders'], [str(self.folder)])
        self.assertEqual(state['favorites'][0]['name'], 'project')
        self.assertTrue(state['favorites'][0]['exists'])

    def test_install_only_known_tools(self):
        with patch.object(agent, 'install', return_value='설치 창') as install:
            self.assertTrue(self.api.call('agent_install', {'tool': 'claude'})['ok'])
            self.assertFalse(self.api.call('agent_install', {'tool': 'powershell'})['ok'])
        install.assert_called_once()

    def test_agent_panel_is_a_known_popover_and_allowed_for_students(self):
        self.assertIn('agent', desktop.POPOVER_KEYS)
        for action in ('agent_state', 'agent_quick', 'agent_run', 'agent_settings', 'agent_favorite',
                       'agent_pick', 'agent_install'):
            self.assertIn(action, desktop.STUDENT_ACTIONS)
        items = (Path(desktop.__file__).parent / 'web' / 'dock-items.js').read_text(encoding='utf-8')
        teacher = items[items.index('const TEACHER_GROUPS'):items.index('const STUDENT_GROUPS')]
        student = items[items.index('const STUDENT_GROUPS'):items.index('window.DOCK_SETS')]
        self.assertIn('AGENT', teacher)
        self.assertIn('AGENT', student)


if __name__ == '__main__':
    unittest.main()
