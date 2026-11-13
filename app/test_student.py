"""학생판 — 교사만 쓰는 기능이 막히는지, 학생 기능은 되는지, 저장 폴더가 따로인지 (2026-10-12 요청)."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명 파일에는 절대 닿지 않는다
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import desktop
from desktop import DesktopAPI

HERE = Path(__file__).parent
TEACHER_ONLY = [('portal', {'target': 'neis'}), ('portal', {'target': 'eduptl'}), ('portal', {'target': 'klef'}),
                ('inbox', {}), ('roster', {}), ('sync_roster', {}), ('alias', {}),
                ('save_credentials', {}), ('credential_settings', {}), ('save_riro', {}), ('save_aiep', {}),
                ('prepare_cm', {}), ('check_cm', {}), ('coolmsg_account', {}), ('options', {}),
                ('open_page', {'page': 'settings'}), ('sticky_list', {}), ('sticky_create', {}), ('state', {})]


class StudentEditionTest(unittest.TestCase):
    def setUp(self):
        for name, value in (('STUDENT', True), ('EDITION', 'student')):
            patcher = patch.object(desktop.edition, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.api = DesktopAPI()

    def test_teacher_only_features_are_refused_even_if_called(self):
        for action, payload in TEACHER_ONLY:
            answer = self.api.call(action, payload)
            self.assertFalse(answer['ok'], action)
            self.assertIn('학생용', answer['error'], action)

    def test_every_allowed_action_exists(self):
        # 🚨 부르지 않고 이름만 본다. 예전에는 하나씩 불러 보다가 진짜 클립보드 기록을 지우고 탐색기를
        #    여는 일이 있었다 (2026-10-12) — 시험은 사용자 자료에 닿으면 안 된다.
        missing = desktop.STUDENT_ACTIONS - set(self.api._handlers())
        self.assertEqual(missing, set())

    def test_student_features_work(self):
        self.assertEqual(self.api.call('dock_state')['data']['edition'], 'student')
        self.assertIn('/academy', desktop.SPACE_ROUTES)
        self.assertIn('/tamagotchi', desktop.SPACE_ROUTES)
        self.assertIn('/star-tower', desktop.SPACE_ROUTES)
        self.assertIn('/planner', desktop.SPACE_ROUTES)
        with patch('webbrowser.open', return_value=True) as browser:
            self.assertTrue(self.api.call('open_classroom')['ok'])
        browser.assert_called_once_with(desktop.CLASSROOM_URL, new=2)
        with patch('desktop.supa_auth.whoami', return_value='student@school'), \
             patch('desktop.startup.enabled', return_value=False):
            data = self.api.call('settings_panel')['data']
        self.assertEqual(data['user'], 'student@school')
        self.assertIn('choices', data['hotkey'])
        self.assertEqual(data['edition'], 'student')
        self.assertIn('version', data['update'])
        for teacher_only in ('cert', 'watch', 'coolmsg'):          # 교사판 칸은 학생판에 오지 않는다
            self.assertNotIn(teacher_only, data)

    def test_student_accounts_are_saved_encrypted_and_forgotten(self):
        self.assertTrue(self.api.call('student_account_save',
                                      {'target': 'riro', 'id': 'kijun2601', 'password': 'pw-1'})['ok'])
        self.assertEqual(self.api._student_account('riro'), ('kijun2601', 'pw-1'))
        with patch('desktop.supa_auth.whoami', return_value=None),              patch('desktop.startup.enabled', return_value=False),              patch('desktop.startup.managed', return_value=False):
            accounts = self.api.call('settings_panel')['data']['accounts']
        self.assertEqual(accounts['riro'], {'label': '리로스쿨', 'id': 'kijun2601', 'saved': True})
        self.assertFalse(accounts['aiep']['saved'])
        self.assertNotIn('pw-1', json.dumps(accounts))         # 비밀번호는 화면으로 돌려주지 않는다
        self.assertTrue(self.api.call('student_account_forget', {'target': 'riro'})['ok'])
        self.assertEqual(self.api._student_account('riro'), ('', ''))
        self.assertFalse(self.api.call('student_account_save', {'target': 'neis', 'id': 'a', 'password': 'b'})['ok'])

    def test_riro_without_account_just_opens_the_site(self):
        with patch.object(self.api, '_open_service_window') as opened,              patch('threading.Thread') as thread:
            answer = self.api.call('open_riro')
        self.assertTrue(answer['ok'])
        opened.assert_called_once_with('riro')
        thread.assert_not_called()

    def test_aiep_with_account_signs_in_inside_the_program(self):
        self.api.call('student_account_save', {'target': 'aiep', 'id': 'stu01@ai.jbedu.kr', 'password': 'pw'})
        window = MagicMock()
        with patch.object(self.api, '_open_service_window', return_value=window) as opened,              patch('core.web_signin.drive', return_value='signed-in') as drive:
            answer = self.api.call('open_aiep')
            for worker in [t for t in __import__('threading').enumerate() if t.name == 'desk-signin-aiep']:
                worker.join(5)
        self.assertTrue(answer['ok'], answer)
        opened.assert_called_once_with('aiep', 'https://ai.jbedu.kr')
        self.assertEqual(drive.call_args.args[1:4], ('aiep', 'stu01@ai.jbedu.kr', 'pw'))
        self.assertNotIn('aiep', self.api._portals)            # 끝나면 독의 '진행 중' 표시가 꺼진다
        self.api.call('student_account_forget', {'target': 'aiep'})

    def test_turning_startup_off_is_remembered(self):
        """학생판은 자동 실행이 기본이라, 끈 것을 기억해야 다음에 켤 때 다시 켜지 않는다."""
        with patch('desktop.startup.managed', return_value=False), patch('desktop.startup.set_enabled') as change:
            self.assertTrue(self.api.call('startup', {'enabled': False})['ok'])
        change.assert_called_once_with(False)
        self.assertIs(self.api._read_preferences()['startup'], False)

    def test_startup_switch_is_locked_when_the_school_manages_it(self):
        with patch('desktop.startup.managed', return_value=True),              patch('desktop.startup.set_enabled') as change:
            answer = self.api.call('startup', {'enabled': False})
        self.assertFalse(answer['ok'])
        change.assert_not_called()

    def test_no_coolmessenger_watching_after_login(self):
        with patch('desktop.supa_auth.whoami', return_value='student@school'), \
             patch.object(self.api._watcher, 'start') as start:
            self.api._reconcile_watch()
        start.assert_not_called()


class StudentDataFolderTest(unittest.TestCase):
    def test_student_edition_uses_its_own_folder_and_startup_name(self):
        script = ("import json, sys; sys.path.insert(0, r'%s');"
                  "from core import edition, secretstore, supa_auth, watcher, startup;"
                  "print(json.dumps([edition.DATA_DIR, secretstore.DATA_DIR, supa_auth.DATA_DIR, watcher.DATA_DIR,"
                  " startup.VALUE_NAME, edition.MUTEX]))") % HERE
        env = {**os.environ, 'SPACEKIJUN_EDITION': 'student'}
        out = json.loads(subprocess.run([sys.executable, '-c', script], env=env, capture_output=True,
                                        text=True, check=True).stdout)
        self.assertTrue(all(path.endswith('SpacekijunStudent') for path in out[:4]), out)
        self.assertEqual(out[4], 'SpacekijunStudent')
        self.assertNotEqual(out[5], 'Local\\SpacekijunDeskWeb')
        env.pop('SPACEKIJUN_EDITION')
        teacher = json.loads(subprocess.run([sys.executable, '-c', script], env=env, capture_output=True,
                                            text=True, check=True).stdout)
        self.assertTrue(teacher[0].endswith('SpacekijunDesk'))   # 교사판은 예전 폴더 그대로


class StudentDockItemsTest(unittest.TestCase):
    def test_student_icons_are_the_requested_ones_and_nothing_teacher_only(self):
        text = (HERE / 'web' / 'dock-items.js').read_text(encoding='utf-8')
        student = text[text.index('const STUDENT_GROUPS'):text.index('window.DOCK_SETS')]
        for wanted in ("'space'", "'classroom'", "'seaton'", "'riro'", "'/tamagotchi'", "'/star-tower'", "'/planner'",
                       "'today'", "'week'", "'capture'", "'captures'", "'clips'", "'settings'", "'isekai3d'"):
            self.assertIn(wanted, student)
        # 별빛 아카데미는 다마고찌 바로 위 (2026-10-22 요청)
        self.assertLess(student.index("route: '/academy'"), student.index("route: '/tamagotchi'"))
        self.assertNotIn("'/academy'", text[:text.index('const STUDENT_GROUPS')])   # 교사판 독에는 없다
        self.assertIn("'aiep'", student)                       # 전북 AIEP 는 학생도 쓴다 (2026-10-12 요청)
        for teacher_only in ("'neis'", "'eduptl'", "'klef'", "'inbox'", "'notes'", "'tasks'",
                             "'notices'", "'notifications'", "'desk'", "action: 'portal'"):
            self.assertNotIn(teacher_only, student, teacher_only)


if __name__ == '__main__':
    unittest.main()
