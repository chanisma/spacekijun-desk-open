import unittest
from unittest.mock import patch, MagicMock
from core import startup


class StartupTests(unittest.TestCase):
    def test_frozen_command_uses_actual_executable_and_quotes_spaces(self):
        with patch.object(startup.sys, 'frozen', True, create=True), \
             patch.object(startup.sys, 'executable', 'C:/Example Folder/Desk.exe'):
            self.assertEqual(startup.command(), '"C:\\Example Folder\\Desk.exe" --autostart')

    def test_enabling_and_disabling_touch_only_this_users_named_value(self):
        with patch.object(startup, 'command', return_value='"C:\\Desk.exe" --autostart'), \
             patch.object(startup.winreg, 'CreateKeyEx') as create, \
             patch.object(startup.winreg, 'SetValueEx') as write:
            startup.set_enabled(True)
            create.assert_called_once_with(startup.winreg.HKEY_CURRENT_USER, startup.RUN_KEY, 0, startup.winreg.KEY_SET_VALUE)
            self.assertEqual(write.call_args.args[1], 'SpacekijunDesk')
        with patch.object(startup.winreg, 'OpenKey'), patch.object(startup.winreg, 'DeleteValue') as delete:
            startup.set_enabled(False)
            self.assertEqual(delete.call_args.args[1], 'SpacekijunDesk')

    def test_missing_value_is_disabled_and_opt_out_is_preserved(self):
        with patch.object(startup.winreg, 'OpenKey', side_effect=FileNotFoundError):
            self.assertFalse(startup.enabled())
            startup.set_enabled(False)
        with patch.object(startup, 'registered_command', return_value=None), patch.object(startup, 'set_enabled') as save:
            startup.refresh_registration()
            save.assert_not_called()

    def test_new_version_refreshes_existing_registration(self):
        with patch.object(startup, 'registered_command', return_value='old.exe'), \
             patch.object(startup, 'command', return_value='new.exe'), \
             patch.object(startup, 'set_enabled') as save:
            startup.refresh_registration()
            save.assert_called_once_with(True)

    def test_student_edition_starts_with_windows_unless_turned_off(self):
        """학생판 기본 = 자동 실행 (2026-10-16). 끈 것·학교가 건 것·소스 실행·교사판은 그대로."""
        def run(choice, student=True, frozen=True, managed=False):
            with patch.object(startup.edition, 'STUDENT', student), \
                 patch.object(startup.sys, 'frozen', frozen, create=True), \
                 patch.object(startup, 'managed', return_value=managed), \
                 patch.object(startup, 'set_enabled') as save:
                return startup.ensure_default(choice), save.call_args_list
        self.assertEqual(run(None), (True, [((True,),)]))
        for case in ({'choice': False}, {'choice': True}, {'choice': None, 'managed': True},
                     {'choice': None, 'frozen': False}, {'choice': None, 'student': False}):
            self.assertEqual(run(**case), (False, []), case)
