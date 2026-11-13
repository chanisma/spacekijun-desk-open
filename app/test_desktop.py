"""Bridge contract checks with no real accounts, messages, or file writes."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명 파일에는 절대 닿지 않는다
import threading
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch
from core import portal, secretstore
import desktop
from desktop import DesktopAPI, SPACEKIJUN_URL


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.api = DesktopAPI()

    def test_unknown_actions_and_invalid_payload_are_rejected(self):
        self.assertFalse(self.api.call('__dict__')['ok'])
        self.assertFalse(self.api.call('state', 'invalid')['ok'])

    def test_login_failure_keeps_the_window_open(self):
        """로그인이 막혀도 창은 남긴다 — 그 자리에서 직접 로그인할 수 있어야 한다."""
        from core import portal
        edge, page = MagicMock(), MagicMock()

        def run_now(*args, **kwargs):
            worker = MagicMock()
            worker.start.side_effect = kwargs['target']
            return worker

        def stop(_seconds):
            self.api._shutdown.set()        # 한 바퀴 돌고 일꾼이 물러나도록

        with patch('desktop.secretstore.load',
                   return_value={'id': 'teacher', 'cert_password': 'test-only'}), \
             patch('desktop.threading.Thread', side_effect=run_now), \
             patch.object(self.api._shutdown, 'wait', side_effect=stop), \
             patch('playwright.sync_api.sync_playwright'), \
             patch.object(DesktopAPI, '_launch_edge', return_value=edge), \
             patch.object(DesktopAPI, '_new_window', return_value=page), \
             patch.object(DesktopAPI, '_attach_assist', return_value=None), \
             patch('core.portal.login_neis', side_effect=portal.LoginError('일치 항목 없음')):
            self.assertTrue(self.api.call('portal', {'target': 'neis'})['ok'])
        page.close.assert_not_called()          # 창을 닫지 않는다
        edge.browser.close.assert_called_once() # 연결만 끊는다
        edge.close.assert_not_called()          # 붙어서 얻은 창은 닫지 않는다
        self.assertTrue(any('자동 로그인 중단' in item['text'] for item in self.api._logs))

    def test_name_only_update_preserves_password_and_escapes_match(self):
        import re
        saved = {'id':'teacher', 'cert_password':'test-only', 'cert_match':None}
        with patch('desktop.secretstore.load', return_value=saved.copy()), patch('desktop.secretstore.save') as save:
            result = self.api.call('save_credentials', {'user':'teacher', 'password':'', 'cert_name':' 홍길동[1] '})
            self.assertTrue(result['ok'])
            values = save.call_args.args[0]
            self.assertEqual(values['cert_password'], 'test-only')
            self.assertEqual(values['cert_name'], '홍길동[1]')
            self.assertEqual(values['cert_match'], re.escape('홍길동[1]'))
        with patch('desktop.secretstore.load', return_value=values):
            settings = self.api.call('credential_settings')['data']
            self.assertEqual(settings, {'user':'teacher', 'cert_name':'홍길동[1]',
                                        'has_password':True, 'riro_id':'', 'has_riro':False,
                                        'aiep_id':'', 'has_aiep':False, 'jbstudy_id':'', 'has_jbstudy':False})
        with patch('desktop.secretstore.load', return_value=values), patch('desktop.secretstore.save') as save:
            self.api.call('save_credentials', {'user':'teacher', 'cert_name':''})
            self.assertIsNone(save.call_args.args[0]['cert_match'])

    def test_settings_panel_shows_teacher_connections_without_secrets(self):
        """교사판 '연결 및 설정' 독 패널 (2026-10-19) — 인증서·쪽지 알림·쿨메신저까지, 암호는 빼고."""
        saved = {'id': 'teacher', 'cert_password': 'cert-secret', 'cert_name': '홍길동',
                 'riro_id': 'riro-user', 'riro_password': 'riro-secret'}
        with patch('desktop.secretstore.load', return_value=saved),              patch('desktop.supa_auth.whoami', return_value='teacher@school'),              patch('desktop.startup.enabled', return_value=True),              patch('desktop.startup.managed', return_value=False),              patch('desktop.udb.status', return_value={'ok': True, 'account': 'kijun', 'accounts': ['kijun']}),              patch('desktop.udb.configured', return_value=''):
            data = self.api.call('settings_panel')['data']
        self.assertEqual(data['edition'], 'teacher')
        self.assertEqual(data['cert'], {'id': 'teacher', 'name': '홍길동', 'saved': True})
        self.assertEqual(data['accounts']['riro'], {'label': '리로스쿨', 'id': 'riro-user', 'saved': True})
        self.assertFalse(data['accounts']['aiep']['saved'])
        self.assertEqual(set(data['watch']), {'watching', 'error', 'summary', 'body'})
        self.assertEqual(data['coolmsg']['accounts'], ['kijun'])
        self.assertIn('version', data['update'])
        self.assertTrue(data['startup'])
        import json
        text = json.dumps(data, ensure_ascii=False)
        self.assertNotIn('cert-secret', text)                   # 암호는 화면으로 돌려주지 않는다
        self.assertNotIn('riro-secret', text)

    def test_teacher_dock_opens_settings_as_a_panel(self):
        items = (Path(desktop.WEB_DIR) / 'dock-items.js').read_text(encoding='utf-8')
        line = next(row for row in items.splitlines() if "id: 'settings', label: '연결 및 설정'" in row)
        self.assertIn("action: 'pop', key: 'settings'", line)
        self.assertIn('settings', desktop.POPOVER_KEYS)

    def test_state_does_not_load_or_expose_credentials(self):
        with patch('desktop.supa_auth.whoami', return_value=None), \
             patch('desktop.secretstore.has_credentials', return_value=True), \
             patch('desktop.secretstore.load') as load:
            data = self.api.call('state')['data']
        load.assert_not_called()
        self.assertTrue(data['credentials'])
        self.assertNotIn('password', str(data))

    def test_unknown_message_account_is_refused(self):
        with patch('desktop.udb.accounts', return_value=[{'name':'인공지능실'}]),              patch('desktop.settings.set') as save:
            result = self.api.call('coolmsg_account', {'account':'없는계정'})
            self.assertFalse(result['ok'])
            self.assertIn('인공지능실', result['error'])
            save.assert_not_called()

    def test_switching_message_account_moves_the_notification_baseline(self):
        """계정마다 쪽지 번호가 따로 매겨진다 — 기준점을 옮겨야 알림이 어긋나지 않는다."""
        with patch('desktop.udb.accounts', return_value=[{'name':'인공지능실'}, {'name':'권민결'}]),              patch('desktop.udb.configured', return_value=''),              patch('desktop.settings.set') as save,              patch('desktop.watcher.reset_baseline', return_value=1757) as baseline:
            self.assertTrue(self.api.call('coolmsg_account', {'account':'인공지능실'})['ok'])
            save.assert_called_once_with('coolmsg_account', '인공지능실')
            baseline.assert_called_once_with('인공지능실')

    def test_choosing_automatic_message_account_clears_the_setting(self):
        with patch('desktop.udb.configured', return_value='권민결'),              patch('desktop.settings.set') as save,              patch('desktop.watcher.reset_baseline', return_value=0):
            self.assertTrue(self.api.call('coolmsg_account', {'account':''})['ok'])
            save.assert_called_once_with('coolmsg_account', '')

    def test_save_validates_and_preserves_certificate_selection(self):
        with patch('desktop.secretstore.save') as save, \
             patch('desktop.secretstore.load', return_value={'cert_match': 'chosen'}):
            self.assertFalse(self.api.call('save_credentials', {'user': 'teacher'})['ok'])
            save.assert_not_called()
            result = self.api.call('save_credentials', {'user': ' teacher ', 'password': 'test-only'})
            self.assertTrue(result['ok'])
            save.assert_called_once_with({'id': 'teacher', 'cert_password': 'test-only', 'cert_match': 'chosen'})
            self.assertNotIn('test-only', str(result))
            self.assertNotIn('test-only', str(self.api._logs))

    def test_inbox_calls_existing_service_and_returns_failures(self):
        with patch('desktop.inbox.timeline', return_value=[{'body': '<script>example</script>'}]) as timeline:
            self.assertEqual(self.api.call('inbox')['data'][0]['body'], '<script>example</script>')
            timeline.assert_called_once_with(60)
        with patch('desktop.inbox.timeline', side_effect=RuntimeError('offline')):
            self.assertEqual(self.api.call('inbox')['error'], 'offline')

    def test_alias_and_portal_validation(self):
        with patch('desktop.roster.set_alias') as save:
            self.assertFalse(self.api.call('alias', {'source':' '})['ok'])
            save.assert_not_called()
            self.assertTrue(self.api.call('alias', {'source':'room', 'target':'teacher'})['ok'])
            save.assert_called_once_with('room', 'teacher')
        self.assertFalse(self.api.call('portal', {'target':'invalid'})['ok'])
        # 자격증명이 없어도 막지 않는다. 자동 로그인 대신 그 사이트를 그냥 연다.
        with patch('desktop.secretstore.has_credentials', return_value=False), \
             patch.object(self.api, '_open_plain', return_value='열었습니다') as plain:
            self.assertTrue(self.api.call('portal', {'target':'neis'})['ok'])
        plain.assert_called_once_with('neis')

    def test_auto_watch_follows_account_and_options_persist(self):
        with patch.object(self.api._watcher, 'start') as start, patch.object(self.api._watcher, 'stop') as stop:
            with patch('desktop.supa_auth.whoami', return_value=None):
                self.api._reconcile_watch()
                start.assert_not_called()
            with patch('desktop.supa_auth.whoami', return_value='teacher@example.test'):
                self.api._reconcile_watch()
            start.assert_called_once()
            with patch('desktop.supa_auth.whoami', return_value=None):
                self.api._reconcile_watch()
            stop.assert_called_once()
        with tempfile.TemporaryDirectory() as directory:
            self.api._preferences_path = Path(directory) / 'desktop-preferences.json'
            self.assertTrue(self.api.call('options', {'summary':False, 'body':False})['ok'])
            self.assertFalse(self.api._watcher.use_summary)
            self.assertFalse(self.api._watcher.show_body)
            self.assertIn('false', self.api._preferences_path.read_text())
            with patch('desktop.watcher.DATA_DIR', directory):
                restarted = DesktopAPI()
            self.assertFalse(restarted._watcher.use_summary)
            self.assertFalse(restarted._watcher.show_body)
        self.assertFalse(self.api.call('watch', {'enabled':False})['ok'])

    def test_auth_completion_reconciles_automatic_watch(self):
        with patch('desktop.supa_auth.login_async') as login, patch.object(self.api, '_reconcile_watch') as reconcile:
            self.assertTrue(self.api.call('auth')['ok'])
            self.assertFalse(self.api.call('auth')['ok'])
            login.call_args.args[0](None)
            self.assertFalse(self.api._auth_pending)
            reconcile.assert_called_once()

    def test_shutdown_does_not_restart_a_connected_watcher(self):
        with patch('desktop.supa_auth.whoami', return_value='teacher@example.test'), \
             patch.object(self.api._watcher, 'start') as start, \
             patch.object(self.api._watcher, 'stop') as stop:
            self.api._close()
            self.api._reconcile_watch()
            start.assert_not_called()
            stop.assert_called_once()

    def test_watcher_no_longer_polls_the_retired_reply_queue(self):
        # spacekijun 의 답장은 2026-09-22 부터 앱 알림 — 큐를 묻는 것은 빈 요청뿐이다
        self.assertFalse(self.api._watcher.do_outbox)
        stop = threading.Event()
        w = desktop.watcher.Watcher(log=lambda *_: None)
        w._stop = stop
        with patch('desktop.watcher.load_state', return_value={'last_key': 0}), \
             patch('desktop.watcher.check_inbox', side_effect=lambda *a, **k: stop.set()) as inbox, \
             patch('desktop.watcher.check_outbox') as outbox:
            w._run()
        inbox.assert_called_once()           # 받은 쪽지 감시(로컬 파일)는 그대로
        outbox.assert_not_called()

    def test_away_follows_input_idle_and_fails_open(self):
        with patch.object(DesktopAPI, '_idle_seconds', return_value=desktop.AWAY_AFTER - 1):
            self.assertFalse(self.api._away())
        with patch.object(DesktopAPI, '_idle_seconds', return_value=desktop.AWAY_AFTER):
            self.assertTrue(self.api._away())
            self.assertTrue(self.api.call('away')['data'])
            self.assertTrue(self.api.call('state')['data']['away'])
        with patch.object(DesktopAPI, '_idle_seconds', side_effect=OSError):
            self.assertFalse(self.api._away())   # 모르면 멈추지 않는다

    def test_dashboard_prefetch_rests_while_away(self):
        calls = []
        def fetch():
            calls.append(1)
            self.api._shutdown.set()
        waits = iter([False, False, True])
        with patch('desktop.supa_auth.whoami', return_value='teacher@example.test'), \
             patch.object(self.api._shutdown, 'wait', side_effect=lambda _t: next(waits)), \
             patch.object(self.api, '_dash_fetch', side_effect=fetch), \
             patch.object(self.api, '_away', side_effect=[True, False]):
            self.api._dash_prefetch_loop()
        self.assertEqual(len(calls), 1)      # 자리 비운 차례는 건너뛰고, 돌아온 차례에 받는다

    def test_space_opens_in_app_without_python_api_and_reuses_window(self):
        space = MagicMock()
        with patch('webview.create_window', return_value=space) as create:
            self.assertTrue(self.api.call('open_space')['ok'])
            self.assertEqual(create.call_args.args[1], SPACEKIJUN_URL)
            self.assertIsNone(create.call_args.kwargs['js_api'])
            self.assertTrue(self.api.call('open_space')['ok'])
            create.assert_called_once()
            space.show.assert_called_once()
            space.restore.assert_called_once()
            self.api._space_reload()
            space.run_js.assert_called_once_with('window.location.reload()')
            self.api._space_home()
            space.load_url.assert_called_once_with(SPACEKIJUN_URL)

    def test_closed_space_can_reopen_and_app_exit_closes_it(self):
        first, second = MagicMock(), MagicMock()
        first.events.closed.__iadd__.return_value = first.events.closed
        with patch('webview.create_window', side_effect=[first, second]):
            self.api.call('open_space')
            on_closed = first.events.closed.__iadd__.call_args.args[0]
            on_closed()
            self.assertIsNone(self.api._space_window)
            self.api.call('open_space')
            self.assertIs(self.api._space_window, second)
            with patch.object(self.api._watcher, 'stop'):
                self.api._close()
            second.destroy.assert_called_once()
            self.assertFalse(self.api.call('open_space')['ok'])


if __name__ == '__main__':
    unittest.main()


class NeisAssistWiringTests(unittest.TestCase):
    """자동 로그인으로 연 나이스 창에 도우미 패널이 얹혀야 한다.

    업무 홈에는 단추를 두지 않는다 — 나이스 창 안에서 바로 말을 건다.
    """

    def api(self):
        api = DesktopAPI.__new__(DesktopAPI)
        api._log = MagicMock()
        api._shutdown = threading.Event()
        return api

    def test_the_panel_is_installed_on_the_neis_tab(self):
        api = self.api()
        page = MagicMock()
        with patch('core.neis_overlay.install') as install:
            session = api._attach_assist(page, {'id': 'teacher'})
        install.assert_called_once()
        self.assertIs(install.call_args.args[0], page)
        self.assertIsNotNone(session)      # 창 지키는 쪽이 이 큐를 돌아가며 비운다

    def test_the_session_is_keyed_to_the_logged_in_account(self):
        api = self.api()
        with patch('core.neis_overlay.install'),              patch('core.neis_session.Session.__init__', return_value=None) as made:
            api._attach_assist(MagicMock(), {'id': 'teacher'})
        self.assertEqual(made.call_args.args[0], 'teacher')

    def test_a_tab_still_works_when_the_panel_cannot_be_installed(self):
        """패널을 못 심어도 탭은 그대로 쓸 수 있어야 한다."""
        api = self.api()
        with patch('core.neis_overlay.install', side_effect=RuntimeError('심기 실패')):
            session = api._attach_assist(MagicMock(), {})
        self.assertIsNone(session)
        self.assertIn('NEIS 도우미 패널을 심지 못했습니다:',
                      [c.args[0] for c in api._log.call_args_list])


class RiroSettingsTests(unittest.TestCase):
    """설정에 리로스쿨 계정을 저장하면 홈 버튼이 자동 로그인으로 바뀐다."""

    def setUp(self):
        self.api = DesktopAPI()
        self.addCleanup(self.api._close)

    def test_saving_keeps_the_certificate_entries_untouched(self):
        saved = {'id': 'teacher', 'cert_password': 'test-only', 'cert_match': None}
        with patch('desktop.secretstore.load', return_value=saved.copy()), \
             patch('desktop.secretstore.save') as save:
            self.assertTrue(self.api.call(
                'save_riro', {'riro_id': ' me ', 'riro_password': 'pw'})['ok'])
        values = save.call_args.args[0]
        self.assertEqual(values['riro_id'], 'me')          # 앞뒤 공백은 지운다
        self.assertEqual(values['riro_password'], 'pw')
        self.assertEqual(values['cert_password'], 'test-only')
        self.assertEqual(values['id'], 'teacher')

    def test_a_blank_password_keeps_the_stored_one(self):
        saved = {'riro_id': 'me', 'riro_password': 'pw'}
        with patch('desktop.secretstore.load', return_value=saved.copy()), \
             patch('desktop.secretstore.save') as save:
            self.api.call('save_riro', {'riro_id': 'me2', 'riro_password': ''})
        values = save.call_args.args[0]
        self.assertEqual(values['riro_id'], 'me2')
        self.assertEqual(values['riro_password'], 'pw')

    def test_an_empty_store_refuses_rather_than_saving_half(self):
        with patch('desktop.secretstore.load', side_effect=secretstore.SecretError('없음')), \
             patch('desktop.secretstore.save') as save:
            answer = self.api.call('save_riro', {'riro_id': 'me', 'riro_password': ''})
        self.assertFalse(answer['ok'])
        save.assert_not_called()

    def test_the_password_is_never_sent_back_to_the_screen(self):
        saved = {'riro_id': 'me', 'riro_password': 'pw'}
        with patch('desktop.secretstore.load', return_value=saved):
            settings = self.api.call('credential_settings')['data']
        self.assertEqual(settings['riro_id'], 'me')
        self.assertTrue(settings['has_riro'])
        self.assertNotIn('riro_password', settings)

    def test_the_home_button_opens_a_shortcut_until_an_account_is_saved(self):
        with patch('desktop.secretstore.load', return_value={}), \
             patch('desktop.secretstore.has_credentials', return_value=False), \
             patch.object(self.api, '_open_plain', return_value='열었습니다') as plain:
            self.assertTrue(self.api.call('open_riro', {})['ok'])
        plain.assert_called_once_with('riro')

    def test_the_home_button_signs_in_once_an_account_is_saved(self):
        with patch('desktop.secretstore.load',
                   return_value={'riro_id': 'me', 'riro_password': 'pw'}), \
             patch.object(self.api, '_open_plain') as plain, \
             patch('desktop.threading.Thread') as thread:
            self.assertTrue(self.api.call('open_riro', {})['ok'])
        plain.assert_not_called()
        thread.assert_called_once()          # 자동 로그인 일꾼이 떴다

    def test_riro_uses_the_id_and_password_not_the_certificate(self):
        page = MagicMock()
        cred = {'riro_id': 'me', 'riro_password': 'pw', 'cert_password': 'cert'}
        with patch('core.portal.login_riro') as riro, patch('core.portal.login_neis') as neis:
            DesktopAPI._sign_in('riro', page, cred, lambda m: None)
        neis.assert_not_called()
        self.assertEqual(riro.call_args.args[1:], ('me', 'pw'))

    def test_the_other_three_still_use_the_certificate(self):
        page = MagicMock()
        cred = {'id': 'teacher', 'cert_password': 'cert', 'cert_match': None}
        with patch('core.portal.login_klef') as klef:
            DesktopAPI._sign_in('klef', page, cred, lambda m: None)
        self.assertEqual(klef.call_args.args[1], 'cert')
        self.assertEqual(klef.call_args.kwargs['user_id'], 'teacher')


class AiepSettingsTests(unittest.TestCase):
    """AIEP 도 리로스쿨과 같은 규칙으로 다룬다."""

    def setUp(self):
        self.api = DesktopAPI()
        self.addCleanup(self.api._close)

    def test_saving_keeps_the_other_services_untouched(self):
        saved = {'cert_password': 'cert', 'riro_id': 'r', 'riro_password': 'rp'}
        with patch('desktop.secretstore.load', return_value=saved.copy()), \
             patch('desktop.secretstore.save') as save:
            self.assertTrue(self.api.call(
                'save_aiep', {'aiep_id': ' me ', 'aiep_password': 'pw'})['ok'])
        values = save.call_args.args[0]
        self.assertEqual(values['aiep_id'], 'me')
        self.assertEqual(values['cert_password'], 'cert')
        self.assertEqual(values['riro_password'], 'rp')

    def test_a_blank_password_keeps_the_stored_one(self):
        with patch('desktop.secretstore.load',
                   return_value={'aiep_id': 'me', 'aiep_password': 'pw'}), \
             patch('desktop.secretstore.save') as save:
            self.api.call('save_aiep', {'aiep_id': 'me2', 'aiep_password': ''})
        self.assertEqual(save.call_args.args[0]['aiep_password'], 'pw')

    def test_the_home_button_opens_a_shortcut_until_an_account_is_saved(self):
        with patch('desktop.secretstore.load', return_value={}), \
             patch('desktop.secretstore.has_credentials', return_value=False), \
             patch.object(self.api, '_open_plain', return_value='열었습니다') as plain:
            self.assertTrue(self.api.call('open_aiep', {})['ok'])
        plain.assert_called_once_with('aiep')

    def test_the_home_button_signs_in_once_an_account_is_saved(self):
        with patch('desktop.secretstore.load',
                   return_value={'aiep_id': 'me', 'aiep_password': 'pw'}), \
             patch.object(self.api, '_open_plain') as plain, \
             patch('desktop.threading.Thread') as thread:
            self.assertTrue(self.api.call('open_aiep', {})['ok'])
        plain.assert_not_called()
        thread.assert_called_once()

    def test_aiep_uses_its_own_id_and_password(self):
        cred = {'aiep_id': 'me', 'aiep_password': 'pw', 'riro_id': 'r', 'riro_password': 'rp'}
        with patch('core.portal.login_aiep') as aiep, patch('core.portal.login_riro') as riro:
            DesktopAPI._sign_in('aiep', MagicMock(), cred, lambda m: None)
        riro.assert_not_called()
        self.assertEqual(aiep.call_args.args[1:], ('me', 'pw'))


class DisconnectTests(unittest.TestCase):
    """설정의 연결 해제. 그 서비스 것만 지우고 나머지는 그대로 둔다."""

    def setUp(self):
        self.api = DesktopAPI()
        self.addCleanup(self.api._close)

    def test_clearing_the_certificate_leaves_the_other_services(self):
        saved = {'id': 'teacher', 'cert_password': 'cert', 'cert_match': None,
                 'cert_name': '홍길동', 'riro_id': 'r', 'riro_password': 'rp'}
        with patch('desktop.secretstore.load', return_value=saved.copy()), \
             patch('desktop.secretstore.save') as save, \
             patch('desktop.secretstore.clear') as wipe:
            self.assertTrue(self.api.call('disconnect', {'target': 'cert'})['ok'])
        values = save.call_args.args[0]
        self.assertEqual(values, {'riro_id': 'r', 'riro_password': 'rp'})
        wipe.assert_not_called()

    def test_clearing_a_password_login_also_forgets_the_browser(self):
        saved = {'cert_password': 'cert', 'aiep_id': 'me', 'aiep_password': 'pw'}
        with patch('desktop.secretstore.load', return_value=saved.copy()), \
             patch('desktop.secretstore.save') as save, \
             patch.object(DesktopAPI, '_forget_browser', return_value=True) as forget:
            answer = self.api.call('disconnect', {'target': 'aiep'})
        self.assertEqual(save.call_args.args[0], {'cert_password': 'cert'})
        forget.assert_called_once_with('aiep')
        self.assertIn('연결을 해제했습니다', answer['data'])

    def test_the_certificate_profiles_are_kept(self):
        """인증서 프로필에는 로컬 네트워크 허용이 들어 있다. 지우면 다시 물어본다."""
        saved = {'id': 'teacher', 'cert_password': 'cert'}
        with patch('desktop.secretstore.load', return_value=saved.copy()), \
             patch('desktop.secretstore.clear'), \
             patch.object(DesktopAPI, '_forget_browser') as forget:
            self.api.call('disconnect', {'target': 'cert'})
        forget.assert_not_called()

    def test_the_store_file_goes_when_nothing_is_left(self):
        with patch('desktop.secretstore.load', return_value={'riro_id': 'r', 'riro_password': 'p'}), \
             patch('desktop.secretstore.save') as save, \
             patch('desktop.secretstore.clear') as wipe, \
             patch.object(DesktopAPI, '_forget_browser', return_value=True):
            self.api.call('disconnect', {'target': 'riro'})
        wipe.assert_called_once()
        save.assert_not_called()

    def test_clearing_something_that_is_not_there_is_not_an_error(self):
        with patch('desktop.secretstore.load', return_value={'cert_password': 'c'}), \
             patch('desktop.secretstore.save') as save:
            answer = self.api.call('disconnect', {'target': 'riro'})
        self.assertTrue(answer['ok'])
        self.assertIn('이미 저장돼 있지 않습니다', answer['data'])
        save.assert_not_called()

    def test_an_unknown_target_is_refused(self):
        self.assertFalse(self.api.call('disconnect', {'target': 'everything'})['ok'])

    def test_a_browser_that_will_not_let_go_is_reported(self):
        saved = {'riro_id': 'r', 'riro_password': 'p', 'cert_password': 'c'}
        with patch('desktop.secretstore.load', return_value=saved.copy()), \
             patch('desktop.secretstore.save'), \
             patch.object(DesktopAPI, '_forget_browser', return_value=False):
            answer = self.api.call('disconnect', {'target': 'riro'})
        self.assertIn('지우지 못했습니다', answer['data'])
        self.assertIn('열린 창을 닫고', answer['data'])


class LinkFallbackTests(unittest.TestCase):
    """저장된 로그인 정보가 없으면 **다섯 곳 모두** 그냥 사이트를 연다.

    2026-09-14 요청. 예전에는 오류를 내거나, 파일만 있으면 자동 로그인을 시도했다.
    """

    SITES = {'neis': 'https://jbe.neis.go.kr',
             'eduptl': 'https://jbe.eduptl.kr',
             'klef': 'https://klef.jbe.go.kr',
             'riro': 'https://kijun.riroschool.kr',
             'aiep': 'https://ai.jbedu.kr'}

    def setUp(self):
        self.api = DesktopAPI()
        self.addCleanup(self.api._close)

    def open_with(self, stored, target):
        with patch('desktop.secretstore.load', return_value=dict(stored)), \
             patch.object(self.api, '_open_plain', return_value='열었습니다') as plain, \
             patch('desktop.threading.Thread') as thread:
            answer = self.api.call('portal', {'target': target})
        return answer, plain, thread

    def test_an_empty_store_opens_every_site_as_a_plain_link(self):
        for target, url in self.SITES.items():
            answer, plain, thread = self.open_with({}, target)
            self.assertTrue(answer['ok'], target)
            plain.assert_called_once_with(target)
            self.assertEqual(DesktopAPI.HOME_URL[target], url, target)
            thread.assert_not_called()

    def test_a_plain_link_opens_where_that_service_normally_lives(self):
        """자격증명이 없으면 자동 로그인 대신 사이트만 연다. **어디서 여는지는 그 서비스가
        평소 어디서 열리는지를 따른다** — 인증서 셋은 브라우저, 나머지는 데스크 안 창."""
        for target in ('neis', 'eduptl', 'klef'):
            with patch.object(self.api, '_open_service_window') as inside, \
                 patch.object(self.api, '_open_shortcut', return_value='열었습니다') as outside:
                self.api._open_plain(target)
            inside.assert_not_called()
            self.assertEqual(outside.call_args.args[0], self.SITES[target], target)
        for target in ('riro', 'aiep'):
            with patch.object(self.api, '_open_service_window') as inside, \
                 patch.object(self.api, '_open_shortcut') as outside:
                self.api._open_plain(target)
            inside.assert_called_once_with(target)
            outside.assert_not_called()

    def test_a_desk_window_that_cannot_open_falls_back_to_the_browser(self):
        with patch.object(self.api, '_open_service_window', side_effect=RuntimeError('창 없음')), \
             patch.object(self.api, '_open_shortcut', return_value='열었습니다') as outside:
            self.api._open_plain('riro')
        self.assertEqual(outside.call_args.args[0], self.SITES['riro'])

    def test_a_certificate_password_without_an_id_is_not_enough(self):
        """에듀파인은 아이디도 쓴다. 반쪽만 있으면 시도하다 실패할 뿐이다."""
        for stored in ({'cert_password': 'c'}, {'id': 'teacher'}):
            for target in ('neis', 'eduptl', 'klef'):
                _, plain, thread = self.open_with(stored, target)
                plain.assert_called_once()
                thread.assert_not_called()

    def test_saving_only_riro_does_not_make_neis_try_to_sign_in(self):
        """예전에는 자격증명 **파일이 있는지**만 봐서, 리로스쿨만 저장해도 나이스가 달려들었다."""
        stored = {'riro_id': 'me', 'riro_password': 'pw'}
        _, plain, thread = self.open_with(stored, 'neis')
        plain.assert_called_once_with('neis')
        thread.assert_not_called()
        # 리로스쿨은 갖춰졌으니 자동 로그인으로 간다.
        _, plain, thread = self.open_with(stored, 'riro')
        plain.assert_not_called()
        thread.assert_called_once()

    def test_a_full_certificate_set_signs_in(self):
        stored = {'id': 'teacher', 'cert_password': 'c'}
        for target in ('neis', 'eduptl', 'klef'):
            fresh = DesktopAPI()
            self.addCleanup(fresh._close)
            with patch('desktop.secretstore.load', return_value=dict(stored)), \
                 patch.object(fresh, '_open_plain') as plain, \
                 patch('desktop.threading.Thread') as thread:
                self.assertTrue(fresh.call('portal', {'target': target})['ok'])
            plain.assert_not_called()
            thread.assert_called_once()

    def test_every_service_shares_one_helper_worker(self):
        """창은 서비스마다 따로지만 Playwright 는 한 스레드에서만 만질 수 있다 — 일꾼은 하나다."""
        stored = {'id': 'teacher', 'cert_password': 'c'}
        with patch('desktop.secretstore.load', return_value=dict(stored)), \
             patch('desktop.threading.Thread') as thread:
            for target in ('neis', 'eduptl', 'klef'):
                self.assertTrue(self.api.call('portal', {'target': target})['ok'])
        thread.assert_called_once()                      # 일꾼은 한 번만 만든다
        queued = []
        while not self.api._browser_jobs.empty():
            queued.append(self.api._browser_jobs.get_nowait())
        self.assertEqual(queued, ['neis', 'eduptl', 'klef'])

    def test_the_same_service_twice_is_refused(self):
        stored = {'id': 'teacher', 'cert_password': 'c'}
        with patch('desktop.secretstore.load', return_value=dict(stored)),              patch('desktop.threading.Thread'):
            self.assertTrue(self.api.call('portal', {'target': 'neis'})['ok'])
            answer = self.api.call('portal', {'target': 'neis'})
        self.assertFalse(answer['ok'])
        self.assertIn('이미 열린 로그인 창', answer['error'])

    def test_the_activity_log_says_what_to_save(self):
        self.open_with({}, 'neis')
        self.assertTrue(any('인증서 정보가 없어 사이트만 엽니다' in item['text']
                            for item in self.api._logs))
        self.open_with({}, 'aiep')
        self.assertTrue(any('아이디와 비밀번호가 없어 사이트만 엽니다' in item['text']
                            for item in self.api._logs))


class BrowserLoopTests(unittest.TestCase):
    """창 지키는 루프.

    **두 갈래를 함께 쥔다.** 나이스·업무포털·에듀파인은 설치된 Edge 에서, 리로스쿨·AIEP 는
    데스크 안 창에서 연다 (2026-09-15 요청). 쉴 때는 어느 쪽도 건드리지 않는다 — 닫힘은
    브라우저가 알려 주게 하고(`page.on('close')`), 그동안에는 파이썬만 기다린다.
    """

    def api(self):
        api = DesktopAPI.__new__(DesktopAPI)
        api._log = MagicMock()
        api._lock = threading.RLock()
        api._shutdown = threading.Event()
        api._portals = set()
        api._portal_status = {}
        api._portal_workers = set()
        api._browser_jobs = __import__('queue').Queue()
        api._browser_worker = None
        api._neis_session = None
        api._service_windows = {}
        api._popups = []
        return api

    def stop_after(self, api, rounds):
        """쉬는 자리를 세다가 멈춘다. 일꾼은 데스크가 꺼질 때까지 살기 때문이다."""
        seen = {'n': 0}

        def tick(_seconds):
            seen['n'] += 1
            if seen['n'] >= rounds:
                api._shutdown.set()
        api._shutdown.wait = MagicMock(side_effect=tick)
        return seen

    def test_the_certificate_three_go_to_edge_and_the_rest_stay_inside(self):
        """어느 갈래로 가는지가 이 설계의 전부다."""
        api = self.api()
        for target in ('neis', 'eduptl', 'klef'):
            api._browser_jobs.put(target)
        for target in ('riro', 'aiep'):
            api._browser_jobs.put(target)
        edge, desk, page = MagicMock(), MagicMock(), MagicMock()
        self.stop_after(api, 6)
        with patch('playwright.sync_api.sync_playwright'), \
             patch('desktop.secretstore.load', return_value={'id': 'a', 'cert_password': 'b'}), \
             patch.object(DesktopAPI, '_launch_edge', return_value=edge) as launch, \
             patch.object(DesktopAPI, '_attach', return_value=desk) as attach, \
             patch.object(DesktopAPI, '_open_edge_window', return_value=page) as in_edge, \
             patch.object(DesktopAPI, '_open_tab', return_value=page) as inside, \
             patch.object(DesktopAPI, '_attach_assist', return_value=None):
            api._serve_browser()
        self.assertEqual([call.args[1] for call in in_edge.call_args_list],
                         ['neis', 'eduptl', 'klef'])
        self.assertEqual([call.args[1] for call in inside.call_args_list], ['riro', 'aiep'])
        launch.assert_called_once()        # 브라우저는 한 번만 띄운다
        attach.assert_called_once()

    def test_edge_is_not_launched_for_a_teacher_who_only_uses_riro(self):
        """리로스쿨만 쓰는 PC 에서 Edge 가 괜히 뜨면 안 된다."""
        api = self.api()
        api._browser_jobs.put('riro')
        self.stop_after(api, 2)
        with patch('playwright.sync_api.sync_playwright'), \
             patch('desktop.secretstore.load', return_value={'riro_id': 'me'}), \
             patch.object(DesktopAPI, '_launch_edge') as launch, \
             patch.object(DesktopAPI, '_attach', return_value=MagicMock()), \
             patch.object(DesktopAPI, '_open_tab', return_value=MagicMock()):
            api._serve_browser()
        launch.assert_not_called()

    def test_a_closed_window_is_noticed_without_asking_the_browser(self):
        """나이스만 계속 쥔다. 닫힘은 브라우저가 알려 준다 — 되묻지 않는다."""
        api = self.api()
        page, edge = MagicMock(), MagicMock()
        api._browser_jobs.put('neis')
        handlers = {}
        page.on.side_effect = lambda event, fn: handlers.setdefault(event, fn)
        rounds = {'n': 0}

        def tick(*_a, **_k):
            rounds['n'] += 1
            if 'close' in handlers and not getattr(tick, 'fired', False):
                tick.fired = True
                handlers['close'](page)
            elif getattr(tick, 'fired', False) and rounds['n'] >= 4:
                api._shutdown.set()
        api._shutdown.wait = MagicMock(side_effect=tick)

        with patch('playwright.sync_api.sync_playwright'), \
             patch('desktop.secretstore.load', return_value={'id': 'a', 'cert_password': 'b'}), \
             patch.object(DesktopAPI, '_launch_edge', return_value=edge), \
             patch.object(DesktopAPI, '_open_edge_window', return_value=page), \
             patch.object(DesktopAPI, '_attach_assist', return_value=None):
            api._serve_browser()
        page.on.assert_called_once()
        self.assertEqual(page.on.call_args.args[0], 'close')
        page.is_closed.assert_not_called()      # 되묻지 않는다
        self.assertEqual(api._portals, set())   # 닫힌 것을 알아챘다
        edge.browser.close.assert_called_once()  # 끝날 때 연결만 놓는다
        # 창 하나 닫혔다고 일꾼까지 끝내지 않는다. 다시 켜려면 새 스레드에서 Playwright 를
        # 또 켜야 하는데 그것이 실패한다 (2026-09-15 실측).
        self.assertGreaterEqual(rounds['n'], 4)

    def test_closing_edge_frees_its_three_and_leaves_the_desk_alone(self):
        """Edge 를 닫아도 일꾼은 산다. 그 셋만 놓아 주고 데스크 쪽은 그대로 둔다."""
        api = self.api()
        api._portals = {'neis', 'eduptl', 'riro'}
        edge = MagicMock()
        edge.cookies.side_effect = RuntimeError('닫힘')
        api._browser_jobs.put('neis')
        self.stop_after(api, 3)
        with patch('playwright.sync_api.sync_playwright'), \
             patch('desktop.secretstore.load', return_value={'id': 'a', 'cert_password': 'b'}), \
             patch.object(DesktopAPI, '_launch_edge', return_value=edge), \
             patch.object(DesktopAPI, '_open_edge_window', return_value=MagicMock()), \
             patch.object(DesktopAPI, '_attach_assist', return_value=None):
            api._serve_browser()
        self.assertEqual(api._portals, {'riro'})      # 데스크 쪽은 건드리지 않는다

    def test_a_signed_in_service_is_released_at_once(self):
        """로그인이 끝나면 손을 뗀다. 단추도 바로 풀린다 (2026-09-15 요청)."""
        api = self.api()
        edge, page = MagicMock(), MagicMock()
        api._browser_jobs.put('eduptl')
        self.stop_after(api, 2)
        with patch('playwright.sync_api.sync_playwright'), \
             patch('desktop.secretstore.load', return_value={'id': 'a', 'cert_password': 'b'}), \
             patch.object(DesktopAPI, '_launch_edge', return_value=edge), \
             patch.object(DesktopAPI, '_open_edge_window', return_value=page):
            api._serve_browser()
        page.on.assert_not_called()              # 따라다니지 않으니 알림도 안 받는다
        self.assertEqual(api._portals, set())    # 바로 풀어 준다

    def test_each_service_gets_its_own_edge_window(self):
        """탭으로 열면 서비스가 한 창에 뒤섞인다. 같은 프로필에서 창을 더 만드는 길은
        `window.open` 뿐이다 — 프로필 하나는 한 프로세스만 열 수 있다."""
        ctx = MagicMock()
        opener = MagicMock()
        opener.url = 'https://jbe.neis.go.kr/'    # 이미 쓰고 있는 창이라 비켜 준다
        fresh = MagicMock()
        ctx.pages = [opener]
        ctx.expect_page.return_value.__enter__.return_value.value = fresh
        got = DesktopAPI._new_window(ctx)
        ctx.new_page.assert_not_called()
        script = opener.evaluate.call_args.args[0]
        self.assertIn('window.open', script)
        self.assertIn('width=', script)          # 크기를 줘야 탭이 아니라 창이 된다
        self.assertIs(got, fresh)

    def test_the_blank_window_the_browser_opened_is_used_not_left_behind(self):
        """브라우저는 띄우면서 빈 창을 하나 준다. 그것을 두고 새 창을 만들면 누르지도 않은
        빈 창이 남는다 (2026-09-15 사용자 보고: 창이 셋 떴다)."""
        ctx = MagicMock()
        blank = MagicMock()
        blank.url = 'about:blank'
        ctx.pages = [blank]
        self.assertIs(DesktopAPI._new_window(ctx), blank)
        ctx.expect_page.assert_not_called()
        ctx.new_page.assert_not_called()

    def test_the_first_edge_window_is_made_when_there_is_none(self):
        ctx = MagicMock()
        ctx.pages = []
        DesktopAPI._new_window(ctx)
        ctx.new_page.assert_called_once()

    def test_edge_is_attached_without_playwright_download_defaults(self):
        """Playwright 기본값으로 붙으면 Edge 의 "파일 열기"·"폴더에 표시" 가 먹통이 된다
        (2026-10-12 보고). 평소처럼 띄운 Edge 에 no_defaults 로 붙는다."""
        pw, browser = MagicMock(), MagicMock()
        pw.chromium.connect_over_cdp.return_value = browser
        with tempfile.TemporaryDirectory() as data:
            Path(data, portal.SHARED_FOLDER).mkdir()
            Path(data, portal.SHARED_FOLDER, 'DevToolsActivePort').write_text('51234\n/devtools/browser/x')
            with patch.object(portal, 'DATA_DIR', data),                  patch('subprocess.Popen') as popen:
                self.assertIs(portal.open_shared_edge(pw), browser)
        pw.chromium.connect_over_cdp.assert_called_once_with('http://127.0.0.1:51234', no_defaults=True, timeout=10000)
        popen.assert_not_called()             # 이미 떠 있는 Edge 에 붙었다

    def test_edge_is_started_normally_when_none_is_running(self):
        pw, browser = MagicMock(), MagicMock()
        pw.chromium.connect_over_cdp.return_value = browser
        with tempfile.TemporaryDirectory() as data:
            profile = Path(data, portal.SHARED_FOLDER)

            def started(args, **_kw):
                profile.joinpath('DevToolsActivePort').write_text('51999\n/devtools/browser/y')
            with patch.object(portal, 'DATA_DIR', data),                  patch.object(portal, 'edge_exe', return_value='msedge.exe'),                  patch('subprocess.Popen', side_effect=started) as popen:
                self.assertIs(portal.open_shared_edge(pw), browser)
        args = popen.call_args.args[0]
        self.assertIn('--remote-debugging-port=0', args)
        self.assertIn(f'--user-data-dir={profile}', args)
        pw.chromium.connect_over_cdp.assert_called_once_with('http://127.0.0.1:51999', no_defaults=True, timeout=10000)

    def test_chrome_gets_its_own_profile(self):
        """Chrome 은 테스트 기능 (2026-10-23). 같은 방식으로 띄우되 프로필은 Edge 와 나눈다."""
        pw, browser = MagicMock(), MagicMock()
        pw.chromium.connect_over_cdp.return_value = browser
        with tempfile.TemporaryDirectory() as data:
            profile = Path(data, 'browser-chrome')

            def started(args, **_kw):
                profile.joinpath('DevToolsActivePort').write_text('52001\n/devtools/browser/z')
            with patch.object(portal, 'DATA_DIR', data), \
                 patch.object(portal, 'find_browser', return_value='chrome.exe'), \
                 patch('subprocess.Popen', side_effect=started) as popen:
                self.assertIs(portal.open_shared_edge(pw, browser='chrome'), browser)
        args = popen.call_args.args[0]
        self.assertEqual(args[0], 'chrome.exe')
        self.assertIn(f'--user-data-dir={profile}', args)

    def prefs_api(self):
        api = self.api()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        api._preferences_path = Path(folder.name) / 'desktop-preferences.json'
        return api

    def test_missing_chrome_falls_back_to_edge(self):
        api = self.prefs_api()
        api._save_preferences(cert_browser='chrome')
        with patch.object(portal, 'find_browser', return_value=None), \
             patch.object(portal, 'open_shared_edge') as opened:
            api._launch_edge(MagicMock())
        self.assertEqual(opened.call_args.kwargs['browser'], 'msedge')

    def test_browser_choice_is_saved_and_refuses_what_is_not_installed(self):
        api = self.prefs_api()
        with patch.object(portal, 'find_browser', return_value=None), self.assertRaises(ValueError):
            api._browser_choice({'browser': 'chrome'})
        with self.assertRaises(ValueError):
            api._browser_choice({'browser': 'firefox'})
        self.assertEqual(api._browser_choice_value(), 'msedge')
        with patch.object(portal, 'find_browser', return_value='chrome.exe'):
            api._browser_choice({'browser': 'chrome'})
        self.assertEqual(api._browser_choice_value(), 'chrome')

    def test_shutdown_lets_go_of_edge_without_closing_its_windows(self):
        """붙어서 얻은 창을 close() 하면 사용자의 Edge 창이 닫힌다. 브라우저 연결만 놓는다."""
        api = self.api()
        edge = MagicMock()
        api._browser_jobs.put('eduptl')
        api._shutdown.wait = MagicMock(side_effect=lambda *_: api._shutdown.set())
        with patch('playwright.sync_api.sync_playwright', return_value=MagicMock()),              patch.object(DesktopAPI, '_launch_edge', return_value=edge),              patch.object(DesktopAPI, '_open_edge_window', return_value=MagicMock()),              patch.object(secretstore, 'load', return_value={}):
            api._serve_browser()
        edge.browser.close.assert_called_once()
        edge.close.assert_not_called()

    def test_each_request_reads_the_store_again(self):
        """일꾼은 데스크가 꺼질 때까지 산다. 그 사이 설정에서 계정을 더 저장할 수 있으므로
        저장된 정보를 붙잡아 두면 방금 저장한 계정으로 열지 못한다."""
        api = self.api()
        ctx = MagicMock()
        api._browser_jobs.put('riro')
        api._browser_jobs.put('aiep')
        self.stop_after(api, 3)
        stores = [{'riro_id': 'me'}, {'riro_id': 'me', 'aiep_id': 'me'}]

        with patch('playwright.sync_api.sync_playwright'), \
             patch.object(DesktopAPI, '_attach', return_value=ctx), \
             patch('desktop.secretstore.load', side_effect=stores) as load, \
             patch.object(DesktopAPI, '_open_tab', return_value=MagicMock()) as open_tab:
            api._serve_browser()
        self.assertEqual(load.call_count, 2)
        self.assertEqual(open_tab.call_args_list[1].args[2], stores[1])

    def test_a_page_opening_a_window_stays_inside_the_desk(self):
        """업무포털의 `나이스` 링크는 `window.open(주소)` 다. 바깥 브라우저로 내보내면
        프로필이 달라 로그인이 끊긴다 (2026-09-15 사용자 보고)."""
        api = self.api()
        fresh = MagicMock()
        with patch('webview.create_window', return_value=fresh) as create:
            got = api._open_popup('https://jbe.neis.go.kr/some/page')
        self.assertIs(got, fresh)
        self.assertEqual(create.call_args.args[0], 'NEIS')      # 아는 곳은 이름으로 부른다
        self.assertEqual(create.call_args.args[1], 'https://jbe.neis.go.kr/some/page')
        self.assertIsNone(create.call_args.kwargs['js_api'])    # 데스크 API 는 주지 않는다
        self.assertEqual(api._popups, [fresh])

    def test_a_flood_of_windows_is_stopped(self):
        api = self.api()
        api._popups = [MagicMock() for _ in range(desktop.POPUP_LIMIT)]
        with patch('webview.create_window') as create:
            self.assertIsNone(api._open_popup('https://example.test/'))
        create.assert_not_called()

    def test_new_window_requests_never_reach_the_outside_browser(self):
        """가로채지 못하면 pywebview 가 바깥 브라우저를 띄운다. 무슨 일이 있어도 막는다."""
        import sys, types
        module = types.ModuleType('webview.platforms.edgechromium')

        class EdgeChrome:
            pass
        module.EdgeChrome = EdgeChrome
        api = self.api()
        opened = []
        with patch.dict(sys.modules, {'webview.platforms.edgechromium': module}):
            desktop.install_web_hooks(opened.append, api._log)
        args = MagicMock()
        args.get_Uri.return_value = 'https://jbe.neis.go.kr/'
        EdgeChrome.on_new_window_request(MagicMock(), MagicMock(), args)
        args.set_Handled.assert_called_once_with(True)
        deadline = time.time() + 5
        while time.time() < deadline and not opened:
            time.sleep(0.05)
        self.assertEqual(opened, ['https://jbe.neis.go.kr/'])

    def test_print_windows_are_left_to_webview2_so_window_open_returns_them(self):
        """출력 창(빈 창·blob·크기를 준 창)을 데스크 창으로 돌리면 `window.open` 이 null 을 받아
        '팝업이 차단되어 출력 창을 열지 못했습니다' 가 뜬다 (2026-10-12 사용자 보고)."""
        import sys, types
        module = types.ModuleType('webview.platforms.edgechromium')

        class EdgeChrome:
            pass
        module.EdgeChrome = EdgeChrome
        opened = []
        with patch.dict(sys.modules, {'webview.platforms.edgechromium': module}):
            desktop.install_web_hooks(opened.append, self.api()._log)
        for uri, sized in (('about:blank', False), ('', False), ('blob:https://spacekijun.lovable.app/1f2e', False),
                           ('https://spacekijun.lovable.app/star-tower?mini=1', True)):
            args = MagicMock()
            args.get_Uri.return_value = uri
            args.WindowFeatures.HasSize = sized
            args.WindowFeatures.HasPosition = False
            EdgeChrome.on_new_window_request(MagicMock(), MagicMock(), args)
            args.set_Handled.assert_not_called()
        time.sleep(0.2)
        self.assertEqual(opened, [])

    def hooked_edge(self):
        """가짜 WebView2 클래스에 데스크 손을 건다. 진짜 창은 띄우지 않는다."""
        import sys, types
        module = types.ModuleType('webview.platforms.edgechromium')
        calls = []

        class EdgeChrome:
            def on_webview_ready(self, sender, args):
                calls.append('pywebview')
        module.EdgeChrome = EdgeChrome
        with patch.dict(sys.modules, {'webview.platforms.edgechromium': module}):
            desktop.install_web_hooks(MagicMock(), self.api()._log)
        return EdgeChrome, calls

    class Event(list):
        """WebView2 이벤트 흉내 — `+=` 로 건 손을 모아 둔다."""
        def __iadd__(self, handler):
            self.append(handler)
            return self

    def download(self, source, uri='https://x.supabase.co/a.hwp', suggested=r'C:\Temp\a.hwp'):
        args = MagicMock()
        args.ResultFilePath = suggested
        args.DownloadOperation.Uri = uri
        args.DownloadOperation.StateChanged = self.Event()
        core = MagicMock()
        core.Source = source
        return args, core

    def test_downloads_land_in_the_download_folder_without_asking(self):
        """pywebview 기본값은 내려받기를 모두 취소한다 (2026-10-11 보고). 받아서 제 이름으로 둔다."""
        EdgeChrome, _ = self.hooked_edge()
        args, core = self.download('https://spacekijun.lovable.app/tasks')
        with tempfile.TemporaryDirectory() as folder, \
             patch('core.downloads.folder', return_value=Path(folder)):
            EdgeChrome.on_download_starting(MagicMock(), core, args)
            self.assertEqual(args.ResultFilePath, str(Path(folder) / 'a.hwp'))
        self.assertIsNot(args.Cancel, True)

    def test_a_window_opened_only_to_download_closes_when_done(self):
        """`window.open(파일 주소)` 로 뜬 빈 창은 받기가 끝나면 닫는다. 보던 화면은 남긴다."""
        EdgeChrome, _ = self.hooked_edge()
        for source, closes in (('about:blank', True),
                               ('https://x.supabase.co/a.hwp', True),
                               ('https://spacekijun.lovable.app/tasks', False)):
            browser = MagicMock()
            args, core = self.download(source)
            operation = args.DownloadOperation
            with tempfile.TemporaryDirectory() as folder, \
                 patch('core.downloads.folder', return_value=Path(folder)):
                EdgeChrome.on_download_starting(browser, core, args)
            [changed] = operation.StateChanged
            operation.State = 'InProgress'
            changed(None, None)
            browser.pywebview_window.destroy.assert_not_called()   # 끝나기 전에 닫으면 받기가 끊긴다
            operation.State = 'Completed'
            changed(None, None)
            deadline = time.time() + 2
            while closes and time.time() < deadline and not browser.pywebview_window.destroy.called:
                time.sleep(0.02)
            self.assertEqual(browser.pywebview_window.destroy.called, closes, source)

    def test_repeat_downloads_are_allowed_but_nothing_else(self):
        """두 번째 내려받기부터 묻는 허락만 내준다. 카메라·위치 같은 것은 건드리지 않는다."""
        import sys, types
        EdgeChrome, calls = self.hooked_edge()
        core_module = types.ModuleType('Microsoft.Web.WebView2.Core')
        core_module.CoreWebView2PermissionKind = types.SimpleNamespace(
            MultipleAutomaticDownloads='downloads', Camera='camera')
        core_module.CoreWebView2PermissionState = types.SimpleNamespace(Allow='allow')
        sender = MagicMock()
        sender.CoreWebView2.PermissionRequested = self.Event()
        parents = {name: types.ModuleType(name) for name in
                   ('Microsoft', 'Microsoft.Web', 'Microsoft.Web.WebView2')}
        with patch.dict(sys.modules, {**parents, 'Microsoft.Web.WebView2.Core': core_module}):
            EdgeChrome.on_webview_ready(MagicMock(), sender, MagicMock(IsSuccess=True))
        self.assertEqual(calls, ['pywebview'])
        [asked] = sender.CoreWebView2.PermissionRequested
        downloads = MagicMock(PermissionKind='downloads', State='default')
        camera = MagicMock(PermissionKind='camera', State='default')
        asked(None, downloads)
        asked(None, camera)
        self.assertEqual(downloads.State, 'allow')
        self.assertEqual(camera.State, 'default')

    def test_downloads_are_handed_back_to_the_browser_inside_the_desk(self):
        """데스크 안 창 쪽은 CDP 한 줄로 되돌아간다 (2026-09-15 실측)."""
        api = self.api()
        browser = MagicMock()
        api._free_downloads(browser)
        session = browser.new_browser_cdp_session.return_value
        session.send.assert_called_once_with('Browser.setDownloadBehavior',
                                             {'behavior': 'default'})

    def test_a_broken_download_reset_does_not_stop_the_desk(self):
        api = self.api()
        browser = MagicMock()
        browser.new_browser_cdp_session.side_effect = RuntimeError('끊김')
        api._free_downloads(browser)          # 던지지 않는다
        api._log.assert_called()

    def test_each_service_opens_as_a_desk_window(self):
        """리로스쿨·AIEP 는 **데스크 안 창**으로 열린다. 브라우저가 따로 뜨지 않는다."""
        api = self.api()
        fresh = MagicMock()
        with patch('webview.create_window', return_value=fresh) as create:
            got = api._open_service_window('riro')
        self.assertIs(got, fresh)
        self.assertEqual(create.call_args.args[0], DesktopAPI.LABEL['riro'])
        self.assertEqual(create.call_args.args[1], DesktopAPI.HOME_URL['riro'])

    def test_the_same_service_does_not_open_twice(self):
        """같은 서비스로 창이 겹치면 어느 것이 쓰던 창인지 알 수 없다. 앞으로 가져온다."""
        api = self.api()
        opened = MagicMock()
        api._service_windows = {'riro': opened}
        with patch('webview.create_window') as create:
            got = api._open_service_window('riro')
        self.assertIs(got, opened)
        create.assert_not_called()
        opened.show.assert_called_once()

    def test_no_new_window_opens_while_shutting_down(self):
        api = self.api()
        api._shutdown.set()
        with patch('webview.create_window') as create:
            with self.assertRaises(RuntimeError):
                api._open_service_window('riro')
        create.assert_not_called()

    def test_the_helper_only_reaches_pages_inside_the_desk(self):
        """도우미는 **127.0.0.1 로만** 붙는다. 바깥으로 나가는 통로가 아니다."""
        import inspect
        source = inspect.getsource(DesktopAPI._connect)
        self.assertIn('127.0.0.1', source)
        self.assertNotIn('0.0.0.0', source)

    def test_the_first_desk_window_opens_before_the_helper_connects(self):
        """창이 하나도 없으면 WebView2 가 디버깅 통로를 열지 않는다. 창이 먼저다."""
        api = self.api()
        order = []
        ctx = MagicMock()
        with patch.object(DesktopAPI, '_open_service_window',
                          side_effect=lambda t: order.append(('창', t))), \
             patch.object(DesktopAPI, '_connect',
                          side_effect=lambda pw: order.append(('연결',)) or ctx), \
             patch.object(DesktopAPI, '_free_downloads'):
            got = api._attach(MagicMock(), 'riro')
        self.assertIs(got, ctx)
        self.assertEqual(order, [('창', 'riro'), ('연결',)])

    def test_idle_waiting_never_touches_a_page(self):
        """쉬는 자리에서 페이지를 만지면, 화면이 바쁠 때 드라이버를 붙잡는다."""
        api = self.api()
        ctx = MagicMock()
        page = MagicMock()
        ctx.pages = [page]
        seen = self.stop_after(api, 3)

        api._browser_jobs.put('riro')
        with patch('playwright.sync_api.sync_playwright'), \
             patch.object(DesktopAPI, '_attach', return_value=ctx), \
             patch('desktop.secretstore.load', return_value={}), \
             patch.object(DesktopAPI, '_open_tab', return_value=None):
            api._serve_browser()
        page.wait_for_timeout.assert_not_called()
        page.is_closed.assert_not_called()
        self.assertGreaterEqual(seen['n'], 3)


class DockTests(unittest.TestCase):
    """독 — 아이콘 줄에서 기능 창을 여는 연결부. 진짜 창은 띄우지 않는다."""
    def setUp(self):
        self.api = DesktopAPI()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.api._preferences_path = Path(self.folder.name) / 'desktop-preferences.json'
        # 진짜 WinForms(.NET)를 불러오지 않는다 — 불러오면 뒤 시험의 가짜 모듈이 먹히지 않는다
        front = patch.object(DesktopAPI, '_bring_front')
        self.bring_front = front.start()
        self.addCleanup(front.stop)

    def test_dock_choice_is_remembered_without_dropping_other_options(self):
        self.assertTrue(self.api.call('options', {'summary': False, 'body': True})['ok'])
        with patch.object(self.api, '_show_dock') as show:
            self.api.set_dock(True)
        show.assert_called_once()
        saved = self.api._read_preferences()
        self.assertEqual(saved, {'summary': False, 'body': True, 'dock': True})
        # 알림 옵션을 다시 저장해도 독 설정은 남는다
        self.assertTrue(self.api.call('options', {'summary': True, 'body': True})['ok'])
        self.assertTrue(self.api._read_preferences()['dock'])
        with patch('desktop.watcher.DATA_DIR', self.folder.name):
            self.assertTrue(DesktopAPI().dock_enabled)

    def test_hiding_the_dock_hides_its_window(self):
        window = MagicMock()
        self.api._dock_window = window
        self.assertTrue(self.api.call('dock_hide')['ok'])
        window.hide.assert_called_once()
        self.assertFalse(self.api.dock_enabled)
        self.assertFalse(self.api._read_preferences()['dock'])

    def test_new_dock_window_goes_to_the_monitor_it_was_left_on(self):
        """새로 켜면 독 창이 주 모니터에 생긴다 — 기억한 자리(cx·cy)가 다른 모니터면 그 가운데로 먼저 보낸다."""
        upper, primary = [-644, -2160, 1916, -720], [0, 0, 2560, 1032]
        self.api._dock_layout = {'anchor': 'bottom', 'docked': True, 'cx': 900, 'cy': -820}
        user32 = MagicMock()
        with patch('desktop._user32', user32), patch('desktop.screen_of', return_value=primary), \
                patch('desktop.screen_at', return_value=upper) as at:
            self.api._dock_to_saved_screen(1234)
        at.assert_called_once_with(900, -820)
        user32.SetWindowPos.assert_called_once_with(1234, None, 636, -1440, 0, 0, 0x15)   # 창 크기를 모르면 0×0
        for here, there in ((upper, upper), (primary, None)):      # 이미 그 모니터 · 그 모니터를 뺐다
            user32.reset_mock()
            with patch('desktop._user32', user32), patch('desktop.screen_of', return_value=here), \
                    patch('desktop.screen_at', return_value=there):
                self.api._dock_to_saved_screen(1234)
            user32.SetWindowPos.assert_not_called()
        self.api._dock_layout = {'anchor': 'bottom', 'docked': True, 'cx': None, 'cy': None}
        with patch('desktop._user32', user32), patch('desktop.screen_at') as at:
            self.api._dock_to_saved_screen(1234)
        at.assert_not_called()

    def test_place_moves_the_dock_and_rejects_bad_sizes(self):
        window = MagicMock()
        self.api._dock_window = window
        self.assertTrue(self.api.call('dock_place', {'x': 100, 'y': 900, 'width': 880, 'height': 168})['ok'])
        window.resize.assert_called_once_with(880, 168)
        window.move.assert_called_once_with(100, 900)
        self.assertFalse(self.api.call('dock_place', {'x': 0, 'y': 0, 'width': 99999, 'height': 168})['ok'])
        self.assertFalse(self.api.call('dock_place', {'x': 'a'})['ok'])
        # 세로로 서면 창이 길어진다 — 세로 독 크기도 받아야 한다
        self.assertTrue(self.api.call('dock_place', {'x': 0, 'y': 40, 'width': 340, 'height': 886})['ok'])

    def test_text_size_setting_scales_the_dock_window_with_the_page(self):
        """Windows 텍스트 크기가 150% 면 WebView2 가 독을 1.5배로 그린다 — 창·패널도 같은 배수로 키워야
        잘리지 않는다 (2026-10-22 사용자 보고, 접근성 > 텍스트 크기를 바꿔 같은 증상을 확인)."""
        window, popover = MagicMock(), MagicMock()
        self.api._dock_window, self.api._popover_window = window, popover
        self.api._popover_ready = False
        with patch.object(self.api, '_log') as log:
            self.assertTrue(self.api.call('dock_place', {'x': 100, 'y': 600, 'width': 880, 'height': 168,
                                                         'ratio': 1.5})['ok'])   # 창 배율 1 (100%) × 텍스트 150%
        window.resize.assert_called_once_with(1320, 252)
        window.move.assert_called_once_with(150, 900)
        self.assertIn('텍스트 크기', log.call_args.args[0])
        self.assertEqual(self.api._dock_scales(), (1.5, 1.0, 1.5))
        self.assertTrue(self.api.call('dock_move', {'x': 200, 'y': 600, 'ratio': 1.5})['ok'])
        window.move.assert_called_with(300, 900)
        self.assertTrue(self.api.call('popover_open', {'key': 'notes', 'rect': [100, 200, 400, 500],
                                                       'caret': {'side': 'bottom', 'at': 60}, 'ratio': 1.5})['ok'])
        popover.resize.assert_called_once_with(600, 750)
        popover.move.assert_called_once_with(150, 300)
        # 손잡이 줄·누를 자리도 실제 픽셀은 같은 배율로 — 독 창 배율(dpi)만 쓰면 판보다 작게 잘린다
        self.assertTrue(self.api.call('dock_layout', {'anchor': 'bottom', 'docked': False, 'cx': 1000, 'cy': 700})['ok'])
        self.assertEqual(self.api._dock_layout['zoom'], 1.5)
        with patch('desktop.screen_at', return_value=None) as at:
            self.api._dock_to_saved_screen(1234)
        at.assert_called_once_with(1500.0, 1050.0)     # 기억한 자리를 화면 좌표로 바꿔 모니터를 찾는다
        # 이상한 값은 받지 않는다 — 배율을 모르면 창 배율 그대로
        self.api._dock_ratio = None
        self.api.call('dock_move', {'x': 10, 'y': 10, 'ratio': 'big'})
        self.assertEqual(self.api._dock_scales(), (1.0, 1.0, 1.0))

    def test_region_accepts_only_small_rect_lists(self):
        # 창이 아직 없으면 할 일이 없을 뿐 오류는 아니다
        self.assertTrue(self.api.call('dock_region', {'rects': [[0, 0, 300, 120]]})['ok'])
        self.assertTrue(self.api.call('dock_region', {'rects': None})['ok'])       # 창 전체
        for bad in ([], [[0, 0, 0, 10]], [[0, 0, 'a', 1]], [[0, 0, 10]], [[0, 0, 10, 10]] * 20,
                    [[0, 0, 10**6, 10]], 'all'):
            self.assertFalse(self.api.call('dock_region', {'rects': bad})['ok'], bad)

    def test_region_remembers_where_the_shelf_is(self):
        payload = {'rects': [[0, 0, 300, 120]], 'shelf': [70, 115, 1000, 77], 'anchor': 'left'}
        self.assertTrue(self.api.call('dock_region', payload)['ok'])
        self.assertEqual((self.api._dock_shelf, self.api._dock_anchor), ([70, 115, 1000, 77], 'left'))
        for bad in ({'shelf': [0, 0, 0, 10], 'anchor': 'left'}, {'shelf': [0, 0, 10, 10], 'anchor': 'up'},
                    {'shelf': 'x', 'anchor': 'top'}):
            self.assertFalse(self.api.call('dock_region', {'rects': None, **bad})['ok'], bad)

    def test_handle_line_sits_just_outside_the_screen_edge_side_of_the_shelf(self):
        from core.dock_handle import line_rect
        shelf = (100, 800, 1100, 877)          # 왼, 위, 오른, 아래
        self.assertEqual(line_rect('bottom', shelf, 1), (540, 878, 120, 6))    # 판 바로 아래
        self.assertEqual(line_rect('top', shelf, 1), (540, 793, 120, 6))       # 판 바로 위
        side = (0, 100, 77, 1000)
        self.assertEqual(line_rect('left', side, 1), (-7, 490, 6, 120))
        self.assertEqual(line_rect('right', side, 1), (78, 490, 6, 120))
        self.assertEqual(line_rect('bottom', shelf, 1.5), (510, 879, 180, 9))   # 배율 150%

    def test_handle_summons_the_dock_on_hover_once_per_visit(self):
        """마우스를 올려 잠깐 머무르면 독을 부른다 (2026-10-22 요청). 줄이 숨었다 커서 아래 다시 떠도
        나갔다 들어오기 전에는 또 부르지 않는다."""
        from core import dock_handle
        summon = MagicMock()
        handle = dock_handle.Handle(lambda work: None, summon)
        inside = [True]
        with patch.object(dock_handle, '_user32') as user32, \
             patch.object(handle, '_cursor_inside', side_effect=lambda: inside[0]):
            user32.DefWindowProcW.return_value = 0
            proc = lambda message: handle._wndproc(1, message, 0, 0)   # noqa: E731
            proc(dock_handle.WM_MOUSEMOVE)
            track = user32.TrackMouseEvent.call_args.args[0]._obj
            self.assertEqual((track.dwFlags, track.dwHoverTime),
                             (dock_handle.TME_LEAVE | dock_handle.TME_HOVER, dock_handle.HOVER_MS))
            summon.assert_not_called()                     # 스치기만 해서는 부르지 않는다
            proc(dock_handle.WM_MOUSEHOVER)
            self.assertEqual(summon.call_count, 1)
            proc(dock_handle.WM_MOUSELEAVE)                # 줄이 숨어서 — 커서는 그대로
            proc(dock_handle.WM_MOUSEMOVE)
            proc(dock_handle.WM_MOUSEHOVER)
            self.assertEqual(summon.call_count, 1)
            inside[0] = False
            proc(dock_handle.WM_MOUSELEAVE)                # 정말 나갔다가
            inside[0] = True
            proc(dock_handle.WM_MOUSEMOVE)
            proc(dock_handle.WM_MOUSEHOVER)                # 다시 들어와 머무르면 또 부른다
            self.assertEqual(summon.call_count, 2)
            # 나간 알림을 못 받았어도 주기 확인이 커서가 밖에 있는 것을 보고 다시 부를 수 있게 한다
            inside[0] = False
            handle.check()
            inside[0] = True
            proc(dock_handle.WM_MOUSEMOVE)
            proc(dock_handle.WM_MOUSEHOVER)
            self.assertEqual(summon.call_count, 3)
            proc(dock_handle.WM_LBUTTONDOWN)               # 눌러도 부른다
            self.assertEqual(summon.call_count, 4)

    def test_handle_is_always_shown_except_while_moving_or_hidden(self):
        """줄은 늘 보인다 (2026-10-11 요청). 끄는 중·독을 숨겼을 때만 감춘다."""
        import ctypes
        from core import dock_handle
        screen = ctypes.WinDLL('user32').GetDesktopWindow()     # 진짜로 보이는 창 핸들 하나
        self.api.dock_enabled = True
        self.api._dock_window, self.api._dock_hwnd = MagicMock(), screen
        self.api._dock_shelf, self.api._dock_anchor = [100, 800, 1000, 77], 'bottom'
        handle = MagicMock(hwnd=None)
        with patch.object(dock_handle, 'Handle', return_value=handle) as make:
            self.api._dock_handle_tick()
            handle.show.assert_called_once()
            self.api._dock_moving = True
            self.api._dock_handle_tick()
            handle.hide.assert_called_once()
            # 끌기가 끝나 판 자리가 오면 줄도 곧바로 다시 뜬다
            handle.reset_mock()
            self.api.call('dock_region', {'rects': [[0, 0, 300, 120]], 'shelf': [100, 800, 1000, 77],
                                          'anchor': 'bottom'})
            handle.show.assert_called_once()
        make.assert_called_once()                       # 줄 창은 한 번만 만든다
        self.api.dock_enabled = False
        handle.reset_mock()
        self.api._dock_handle_tick()
        handle.hide.assert_called_once()

    def test_shared_windows_functions_are_left_untouched(self):
        """pywebview 와 함께 쓰는 ctypes.windll 에 argtypes 를 걸면 창 옮기기가 깨진다
        (2026-10-11 사용자 보고 — SetWindowPos 에 None 을 넘기다 실패해 독이 움직이지 않았다)."""
        import ctypes
        from core import dock_handle  # noqa: F401 — 불러오기만 해도 걸던 것을 시험한다
        for name in ('SetWindowPos', 'SetWindowRgn', 'ShowWindow', 'GetWindowLongPtrW', 'SetWindowLongPtrW'):
            self.assertIsNone(getattr(ctypes.windll.user32, name).argtypes, name)
        for name in ('CreateRectRgn', 'CombineRgn', 'DeleteObject', 'CreateRoundRectRgn'):
            self.assertIsNone(getattr(ctypes.windll.gdi32, name).argtypes, name)

    def test_ui_thread_work_never_returns_a_value_or_raises(self):
        """Func[Type] 는 돌려준 값을 Type 으로 바꾸려다 앱을 멈춘다 (2026-10-11 사용자 보고)."""
        import sys, types
        sent = []
        system = types.ModuleType('System')
        system.Type = object
        system.Func = {object: lambda function: function}
        form = MagicMock()
        form.BeginInvoke.side_effect = sent.append
        logged = []
        with patch.dict(sys.modules, {'System': system}):
            desktop.on_ui(form, lambda: 3, logged.append)               # ShowWindow 처럼 숫자를 돌려준다
            desktop.on_ui(form, lambda: 1 / 0, lambda *parts: logged.append(parts))
        self.assertEqual([run() for run in sent], [None, None])
        self.assertEqual(len(logged), 1)                                 # 오류는 기록만

    def test_snap_preview_follows_the_dock_scale_and_hides_on_null(self):
        import ctypes
        from core import dock_handle
        self.api._dock_window, self.api._dock_hwnd = MagicMock(), ctypes.WinDLL('user32').GetDesktopWindow()
        ghost = MagicMock()
        with patch.object(dock_handle, 'Preview', return_value=ghost), \
             patch.object(DesktopAPI, '_dock_form', return_value=MagicMock()), \
             patch.object(desktop._user32, 'GetDpiForWindow', return_value=144):      # 150%
            self.assertTrue(self.api.call('dock_preview', {'rect': [0, 100, 77, 900], 'radius': 22})['ok'])
            ghost.show.assert_called_once_with((0, 150, 116, 1350), 33)
            self.assertTrue(self.api.call('dock_preview', {'rect': None})['ok'])
            ghost.hide.assert_called_once()
            for bad in ([0, 0, 0, 10], [0, 0, 'a', 10], [0, 0, 10], [10**7, 0, 10, 10]):
                self.assertFalse(self.api.call('dock_preview', {'rect': bad})['ok'], bad)

    def test_clicking_the_handle_brings_the_dock_back(self):
        self.api._dock_handle = MagicMock()
        with patch.object(self.api, 'dock_front') as front:
            self.api._handle_clicked()
        self.api._dock_handle.hide.assert_called_once()
        front.assert_called_once()

    def test_dock_is_not_always_on_top(self):
        """다른 창처럼 겹쳐야 한다 (2026-10-11 요청)."""
        with patch('webview.create_window') as create, patch('webview.screens', []):
            self.api._show_dock()
        self.assertFalse(create.call_args.kwargs.get('on_top', False))
        self.assertTrue(create.call_args.kwargs['transparent'])

    def test_dock_and_panel_windows_are_created_outside_the_lock(self):
        """create_window 는 UI 스레드를 기다린다 — 잠금을 쥔 채 부르면 켤 때 서로 기다려 멈췄다 (2026-10-19)."""
        free = []

        def probe():
            got = self.api._lock.acquire(timeout=1)
            if got:
                self.api._lock.release()           # RLock — 잡은 스레드가 놓는다
            free.append(got)

        def create(*_, **__):
            other = threading.Thread(target=probe)
            other.start()
            other.join()
            return MagicMock()
        with patch('webview.create_window', side_effect=create), patch('webview.screens', []):
            self.api._show_dock()
            self.api._popover_create((0, 0, 404, 504))
        self.assertEqual(free, [True, True])
        self.assertIsNotNone(self.api._dock_window)
        self.assertIsNotNone(self.api._popover_window)

    def test_saved_screen_move_does_not_wait_for_the_lock(self):
        """UI 스레드에서 돈다 — 다른 스레드가 잠금을 쥐고 있어도 끝나야 한다 (2026-10-19 켤 때 멈춤)."""
        self.api._dock_layout = {'anchor': 'bottom', 'docked': True, 'cx': 900, 'cy': -820}
        held, done = threading.Event(), threading.Event()

        def hold():
            with self.api._lock:
                held.set()
                done.wait(5)
        holder = threading.Thread(target=hold)
        holder.start()
        held.wait(5)
        try:
            ran = threading.Thread(target=self.api._dock_to_saved_screen, args=(1234,))
            with patch('desktop._user32', MagicMock()), patch('desktop.screen_of', return_value=None), \
                    patch('desktop.screen_at', return_value=[0, 0, 10, 10]):
                ran.start()
                ran.join(2)
            self.assertFalse(ran.is_alive())
        finally:
            done.set()
            holder.join()

    def test_window_created_after_shutdown_is_closed(self):
        made = MagicMock()

        def create(*_, **__):
            self.api._shutdown.set()               # 만드는 사이에 끝내기가 지나갔다
            return made
        with patch('webview.create_window', side_effect=create), patch('webview.screens', []):
            self.api._show_dock()
        self.assertIsNone(self.api._dock_window)
        made.destroy.assert_called_once()

    def test_drag_moves_only_the_position(self):
        window = MagicMock()
        self.api._dock_window = window
        self.assertTrue(self.api.call('dock_move', {'x': -1500, 'y': 300})['ok'])   # 왼쪽 모니터
        window.move.assert_called_once_with(-1500, 300)
        window.resize.assert_not_called()
        self.assertFalse(self.api.call('dock_move', {'x': 10**9, 'y': 0})['ok'])

    def test_layout_is_remembered_and_restored(self):
        layout = {'anchor': 'left', 'docked': True, 'cx': 170, 'cy': 480}
        self.assertTrue(self.api.call('dock_layout', layout)['ok'])
        layout = {**layout, 'zoom': 1.0}              # 그때의 CSS px → 화면 좌표 배수를 함께 기억한다
        self.assertEqual(self.api.call('dock_state')['data']['layout'], layout)
        self.assertEqual(self.api._read_preferences()['dock_layout'], layout)
        with patch('desktop.watcher.DATA_DIR', self.folder.name):
            self.assertEqual(DesktopAPI()._dock_layout, layout)
        for bad in ({'anchor': 'middle'}, {'anchor': 'top', 'cx': 'far'},
                    {'anchor': 'top', 'cx': True}, {'anchor': 'top', 'cy': 10**9}):
            self.assertFalse(self.api.call('dock_layout', bad)['ok'], bad)
        self.assertEqual(self.api._dock_layout, layout)       # 잘못된 값은 덮어쓰지 않는다

    def test_broken_saved_layout_falls_back_to_default(self):
        self.api._save_preferences(dock_layout={'anchor': 'sideways'})
        with patch('desktop.watcher.DATA_DIR', self.folder.name):
            self.assertIsNone(DesktopAPI()._dock_layout)

    def test_state_reports_open_windows_and_logins_in_progress(self):
        self.api._space_window = MagicMock()
        self.api._service_windows['riro'] = MagicMock()
        self.api._page_windows['inbox'] = MagicMock()
        self.api._portals.add('neis')
        state = self.api.call('dock_state')['data']
        self.assertEqual(state['running'], ['page:inbox', 'riro', 'space'])
        self.assertEqual(state['busy'], ['neis'])

    def test_open_page_reuses_its_window_and_only_allows_desk_pages(self):
        self.assertFalse(self.api.call('open_page', {'page': 'admin'})['ok'])
        class Hook(list):            # pywebview 이벤트처럼 `+=` 로 받는다
            def __iadd__(self, handler):
                self.append(handler)
                return self
        created = MagicMock()
        created.events.loaded, created.events.closed = Hook(), Hook()
        with patch('webview.create_window', return_value=created) as create:
            self.assertTrue(self.api.call('open_page', {'page': 'roster'})['ok'])
            self.assertTrue(self.api.call('open_page', {'page': 'roster'})['ok'])
        create.assert_called_once()
        self.assertTrue(create.call_args.kwargs['hidden'])
        created.show.assert_called_once()           # 두 번째는 있던 창을 앞으로
        # 화면이 뜨면 그 화면 하나만 보이게 고른 뒤에 창을 보인다
        created.events.loaded[0]()
        created.run_js.assert_called_once_with('window.deskSolo && window.deskSolo("roster")')
        # 독은 포커스를 안 가져가므로 새 창을 맨 앞으로 올려야 한다
        self.bring_front.assert_called_with(created)

    def test_dashboard_card_opens_alone_in_a_small_window(self):
        created = MagicMock()
        with patch('webview.create_window', return_value=created) as create:
            result = self.api.call('open_page', {'page': 'card:today'})
        self.assertTrue(result['ok'])
        self.assertIn('오늘 시간표', create.call_args.args[0])
        self.assertLess(create.call_args.kwargs['width'], 1000)
        self.assertIn('page:card:today', self.api.call('dock_state')['data']['running'])
        self.assertFalse(self.api.call('open_page', {'page': 'card:secret'})['ok'])

    def test_home_goes_to_the_main_desk_window(self):
        desk = MagicMock()
        self.api._desk_window = desk
        self.assertTrue(self.api.call('open_page', {'page': 'home'})['ok'])
        desk.show.assert_called_once()
        desk.run_js.assert_called_once()

    def test_closing_the_desk_closes_the_dock_and_page_windows(self):
        dock, page = MagicMock(), MagicMock()
        self.api._dock_window = dock
        self.api._page_windows['notes'] = page
        self.api._close()
        dock.destroy.assert_called_once()
        page.destroy.assert_called_once()


class _Hook(list):
    """pywebview 이벤트처럼 `+=` 로 손을 받는다."""
    def __iadd__(self, handler):
        self.append(handler)
        return self

    def is_set(self):                   # 아직 일어나지 않은 이벤트
        return False


def _fake_window():
    window = MagicMock()
    for name in ('loaded', 'shown', 'closed'):
        setattr(window.events, name, _Hook())
    return window


class PopoverAndCacheTests(unittest.TestCase):
    """독 위 패널·학교 정보 미리 받기·메모 링크 — 진짜 창·서버·브라우저는 쓰지 않는다."""
    def setUp(self):
        self.api = DesktopAPI()
        front = patch.object(DesktopAPI, '_bring_front')
        front.start()
        self.addCleanup(front.stop)

    def test_dashboard_is_served_from_the_prefetched_copy(self):
        with patch('desktop.supa_auth.whoami', return_value='teacher@school'), \
             patch('core.dashboard.snapshot', side_effect=[{'n': 1}, {'n': 2}, {'n': 3}]) as fetch:
            self.assertIsNone(self.api.call('dashboard_quick')['data'])       # 아직 받아 둔 것이 없다
            self.assertEqual(self.api.call('dashboard')['data'], {'n': 1})
            self.assertEqual(self.api.call('dashboard')['data'], {'n': 1})       # 1분 안 — 서버에 묻지 않는다
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(self.api.call('dashboard_quick')['data']['data'], {'n': 1})
            self.assertEqual(self.api.call('dashboard', {'force': True})['data'], {'n': 2})
            with patch('desktop.time.monotonic', return_value=time.monotonic() + desktop.DASHBOARD_FRESH + 5):
                self.assertEqual(self.api.call('dashboard')['data'], {'n': 3})   # 오래됐으면 새로
        # 계정이 바뀌면 받아 둔 것을 쓰지 않는다
        with patch('desktop.supa_auth.whoami', return_value='someone@else'):
            self.assertIsNone(self.api.call('dashboard_quick')['data'])

    def test_month_calendar_validates_and_caches_per_account(self):
        for bad in ({}, {'month': '2026-13'}, {'month': 'x'}, {'month': '1999-01'}):
            self.assertFalse(self.api.call('dashboard_month', bad)['ok'], bad)
        with patch('desktop.supa_auth.whoami', return_value='teacher@school'), \
             patch('core.dashboard.month', side_effect=[{'n': 1}, {'n': 2}, {'n': 3}]) as fetch:
            self.assertEqual(self.api.call('dashboard_month', {'month': '2026-10'})['data'], {'n': 1})
            self.assertEqual(self.api.call('dashboard_month', {'month': '2026-10'})['data'], {'n': 1})
            fetch.assert_called_once_with(2026, 10)
            self.assertEqual(self.api.call('dashboard_month', {'month': '2026-10', 'force': True})['data'], {'n': 2})
            with patch('desktop.supa_auth.whoami', return_value='someone@else'):
                self.assertEqual(self.api.call('dashboard_month', {'month': '2026-10'})['data'], {'n': 3})

    def test_popover_validates_and_reuses_one_window(self):
        payload = {'key': 'today', 'rect': [100, 300, 404, 504], 'caret': {'side': 'bottom', 'at': 200}}
        for bad in ({**payload, 'key': 'secret'}, {**payload, 'rect': [0, 0, 10, 10]},
                    {**payload, 'caret': {'side': 'middle', 'at': 1}}, {**payload, 'rect': 'x'}):
            self.assertFalse(self.api.call('popover_open', bad)['ok'], bad)
        window = _fake_window()
        with patch('webview.create_window', return_value=window) as create:
            self.assertTrue(self.api.call('popover_open', payload)['ok'])
            create.assert_called_once()
            self.assertTrue(create.call_args.kwargs['frameless'])
            # 다 불러오면 그 내용을 보인다
            with patch.object(self.api, '_dock_chrome'):
                window.events.loaded[0](window)
            window.run_js.assert_called_with('window.deskPopover && window.deskPopover.show('
                                             '{"key": "today", "caret": {"side": "bottom", "at": 200}})')
            window.show.assert_called_once()
            # 두 번째는 같은 창을 옮겨 다시 쓴다
            self.assertTrue(self.api.call('popover_open', {**payload, 'key': 'notes'})['ok'])
            create.assert_called_once()
            window.move.assert_called_with(100, 300)

    def test_prewarmed_popover_stays_hidden_until_asked(self):
        window = _fake_window()
        with patch('webview.create_window', return_value=window):
            self.api._popover_prewarm()
            with patch.object(self.api, '_dock_chrome'):
                window.events.loaded[0](window)
        window.hide.assert_called_once()
        window.show.assert_not_called()

    def test_closing_the_popover_tells_the_dock(self):
        self.api._popover_window, self.api._dock_window = MagicMock(), MagicMock()
        self.assertTrue(self.api.call('popover_close')['ok'])
        self.api._popover_window.hide.assert_called_once()
        self.api._dock_window.run_js.assert_called_once_with('window.deskDock && window.deskDock.popClosed()')

    def test_note_links_open_only_web_addresses(self):
        with patch('webbrowser.open', return_value=True) as browser:
            self.assertTrue(self.api.call('open_link', {'url': 'https://school.example/a?b=1'})['ok'])
            self.assertTrue(self.api.call('open_link', {'url': 'www.example.com'})['ok'])
            browser.assert_called_with('https://www.example.com', new=2)
            for bad in ('file:///C:/Windows/system32/calc.exe', 'javascript:alert(1)', 'C:/Windows/x.exe', '', 3,
                        'https://a b'):
                self.assertFalse(self.api.call('open_link', {'url': bad})['ok'], bad)

    def test_sticky_window_has_no_title_bar_and_resizes_within_limits(self):
        window = MagicMock()
        with patch('desktop.sticky.get', return_value={'id': 'n1', 'title': '메모'}), \
             patch('webview.create_window', return_value=window) as create:
            self.api._sticky_open({'id': 'n1'})
        self.assertTrue(create.call_args.kwargs['frameless'])
        self.assertFalse(create.call_args.kwargs['easy_drag'])          # 글을 고를 때 창이 끌려가지 않게
        self.assertTrue(self.api.call('sticky_resize', {'id': 'n1', 'width': 50, 'height': 9999})['ok'])
        window.resize.assert_called_once_with(220, 2000)
        self.assertFalse(self.api.call('sticky_resize', {'id': 'nope', 'width': 300, 'height': 300})['ok'])


class PanelRoutingTests(unittest.TestCase):
    """쪽지함·캡처 보관함도 독 위 패널로 (2026-10-12 요청)."""
    def setUp(self):
        self.api = DesktopAPI()

    def test_inbox_and_captures_are_panels(self):
        with patch('webview.create_window', return_value=_fake_window()):
            for key in ('inbox', 'captures'):
                payload = {'key': key, 'rect': [100, 100, 584, 584], 'caret': {'side': 'bottom', 'at': 200}}
                self.assertTrue(self.api.call('popover_open', payload)['ok'], key)

    def test_captures_open_above_the_dock_when_it_is_shown(self):
        dock = MagicMock()
        dock.evaluate_js.return_value = True
        self.api.dock_enabled, self.api._dock_window = True, dock
        with patch('webview.create_window') as create:
            self.assertTrue(self.api.call('captures')['ok'])
        create.assert_not_called()                                   # 패널로 열었다 — 창은 만들지 않는다
        dock.evaluate_js.assert_called_once()
        # 독이 패널을 못 열면(끄는 중 등) 예전처럼 제 창
        dock.evaluate_js.return_value = False
        with patch('webview.create_window', return_value=_fake_window()) as create:
            self.assertTrue(self.api.call('captures')['ok'])
        create.assert_called_once()


class DockIconSettingsTests(unittest.TestCase):
    """데스크 설정에서 독에 보일 아이콘을 고른다 (2026-10-12 요청)."""
    def setUp(self):
        self.api = DesktopAPI()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.api._preferences_path = Path(folder.name) / 'prefs.json'
        self.folder = folder.name

    def test_hidden_icons_are_saved_pushed_to_the_dock_and_restored(self):
        dock = MagicMock()
        self.api._dock_window = dock
        answer = self.api.call('dock_items_save', {'hidden': ['riro', 'seaton', 'riro'], 'total': 19})
        self.assertTrue(answer['ok'])
        dock.run_js.assert_called_once_with('window.deskDock && window.deskDock.setHidden(["riro", "seaton"])')
        self.assertEqual(self.api.call('dock_items')['data']['hidden'], ['riro', 'seaton'])
        self.assertEqual(self.api.call('dock_state')['data']['hidden'], ['riro', 'seaton'])
        with patch('desktop.watcher.DATA_DIR', self.folder):
            restarted = DesktopAPI()
        restarted._preferences_path = self.api._preferences_path
        self.assertEqual(DesktopAPI._valid_dock_hidden(restarted._read_preferences()['dock_hidden']),
                         ['riro', 'seaton'])

    def test_bad_lists_and_hiding_everything_are_refused(self):
        for bad in ('riro', ['Riro!'], [3], ['x'] * 100):
            self.assertFalse(self.api.call('dock_items_save', {'hidden': bad})['ok'], bad)
        self.assertFalse(self.api.call('dock_items_save', {'hidden': ['a', 'b'], 'total': 2})['ok'])
        self.assertEqual(self.api.call('dock_items')['data']['hidden'], [])

    def test_settings_icon_cannot_be_hidden_and_comes_back(self):
        """설정 아이콘을 숨기면 다시 켤 길이 없다 (2026-10-23 요청). 이미 숨겨 둔 PC 도 되살린다."""
        self.api.call('dock_items_save', {'hidden': ['riro', 'settings'], 'total': 19})
        self.assertEqual(self.api.call('dock_items')['data']['hidden'], ['riro'])
        # 예전 판이 저장한 값 — 다시 켤 때 설정만 빠진다
        Path(self.folder, 'desktop-preferences.json').write_text('{"dock_hidden": ["settings", "seaton"]}', encoding='utf-8')
        with patch('desktop.watcher.DATA_DIR', self.folder):
            restarted = DesktopAPI()
        self.assertEqual(restarted._dock_hidden, ['seaton'])


class DockHotkeyTests(unittest.TestCase):
    """가려진 독을 부르는 단축키 (2026-10-12 요청). 진짜 전역 단축키는 등록하지 않는다."""
    def setUp(self):
        self.api = DesktopAPI()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.api._preferences_path = Path(folder.name) / 'prefs.json'

    def test_choosing_a_combo_is_saved_and_conflicts_are_reported(self):
        with patch('core.hotkey.HotKey.use', return_value=True) as use:
            answer = self.api.call('dock_hotkey_save', {'combo': 'alt+q'})
        self.assertTrue(answer['ok'])
        use.assert_called_once_with('alt+q')
        self.assertEqual(self.api._read_preferences()['dock_hotkey'], 'alt+q')
        with patch('core.hotkey.HotKey.use', return_value=False):
            busy = self.api.call('dock_hotkey_save', {'combo': 'ctrl+alt+d'})
        self.assertFalse(busy['ok'])
        self.assertIn('다른 프로그램', busy['error'])
        self.assertFalse(self.api.call('dock_hotkey_save', {'combo': 'win+x'})['ok'])
        with patch('core.hotkey.HotKey.use', return_value=True):
            self.assertTrue(self.api.call('dock_hotkey_save', {'combo': 'off'})['ok'])

    def test_pressing_brings_the_dock_back_or_turns_it_on(self):
        with patch.object(self.api, 'set_dock') as turn_on, patch.object(self.api, 'dock_front') as front:
            self.api.dock_enabled = False
            self.api._hotkey_pressed()
            turn_on.assert_called_once_with(True)
            front.assert_not_called()
            self.api.dock_enabled, self.api._dock_window = True, MagicMock()
            self.api._hotkey_pressed()
            front.assert_called_once()
            self.api._dock_window.run_js.assert_called_once_with('window.deskDock && window.deskDock.nudge()')

    def test_open_panel_and_shown_memos_come_up_with_the_dock(self):
        """단축키·손잡이 줄로 독을 올리면 펼쳐 둔 패널·보이는 메모도 함께 (2026-10-29 요청)."""
        class Form:
            def __init__(self, visible=True, state='Normal', top=False):
                self.Visible, self.WindowState, self.TopMost, self.lifted = visible, state, top, 0

            def __setattr__(self, key, value):
                if key == 'TopMost' and value is True and 'lifted' in self.__dict__:
                    self.__dict__['lifted'] += 1
                super().__setattr__(key, value)
        dock, panel = MagicMock(), MagicMock()
        memos = {name: MagicMock() for name in ('shown', 'minimized', 'pinned', 'hidden')}
        forms = {id(panel): Form(), id(memos['shown']): Form(),
                 id(memos['minimized']): Form(state='Minimized'),
                 id(memos['pinned']): Form(top=True), id(memos['hidden']): Form(visible=False)}
        self.api.dock_enabled, self.api._dock_window = True, dock
        self.api._sticky_windows = dict(memos)
        self.api._popover_window, self.api._popover_ready, self.api._popover_request = panel, True, {'key': 'notes'}
        with patch.object(DesktopAPI, '_bring_front') as front, \
             patch.object(DesktopAPI, '_dock_form', side_effect=lambda w: forms.get(id(w))), \
             patch.object(desktop, 'on_ui', side_effect=lambda form, work, log=None: work()):
            self.api.dock_front()
            front.assert_called_once_with(dock)
            self.assertEqual(forms[id(panel)].lifted, 1)
            self.assertEqual(forms[id(memos['shown'])].lifted, 1)
            self.assertEqual([forms[id(memos[name])].lifted for name in ('minimized', 'pinned', 'hidden')], [0, 0, 0])
            self.assertTrue(forms[id(memos['pinned'])].TopMost)                       # '항상 위'는 그대로
            self.assertFalse(forms[id(memos['shown'])].TopMost)                       # 올렸다 내린다 — 항상 위로 남지 않게
            self.api._popover_request = None                                           # 닫힌 패널(숨겨 둔 창)은 올리지 않는다
            self.api.dock_front()
            self.assertEqual(forms[id(panel)].lifted, 1)

    def test_choices_list_offers_off(self):
        data = self.api.call('dock_hotkey')['data']
        self.assertEqual(data['combo'], 'ctrl+alt+d')
        self.assertIn('off', [choice['key'] for choice in data['choices']])


class DockOverlayLifetimeTests(unittest.TestCase):
    """독 손잡이·미리보기 창의 처리 함수 (2026-11-06 — 데스크가 하루 네 번 0xc0000005 로 튕김).
    객체를 버려도 창에 오는 메시지가 지워진 콜백을 부르지 않아야 한다. 되돌아가면 이 시험이 프로세스째 죽는다."""

    def test_window_outlives_its_object(self):
        import ctypes
        import gc
        from ctypes import wintypes
        from core import dock_handle
        preview = dock_handle.Preview(lambda work: work())
        hwnd = dock_handle._overlay_window(0x80, 'lifetime test', preview._proc)
        self.assertIn(preview._proc, dock_handle._kept_procs)
        del preview
        gc.collect()
        filler = [dock_handle._WNDPROC(lambda *a: 0) for _ in range(500)]   # 풀린 자리를 다른 것이 쓰게
        del filler
        gc.collect()
        user32 = ctypes.WinDLL('user32')
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        for message in (0x0, 0x0F, 0x1A):
            user32.SendMessageW(hwnd, message, 0, 0)
        dock_handle._destroy(hwnd)
        self.assertFalse(user32.IsWindow(wintypes.HWND(hwnd)))
