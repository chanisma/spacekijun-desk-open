import time
import unittest
from unittest.mock import Mock, patch
from core import web_login as login


class WebLoginTests(unittest.TestCase):
    def setUp(self):
        self.log = Mock()
        self.bridge = login.WebLogin(self.log)
        self.window = Mock(uid='web-window')
        self.window.get_current_url.return_value = login.ORIGINS['space']
        self.session = {'access_token': 'test-web-token', 'refresh_token': 'test-web-refresh',
                        'user': {'id': 'my-user'}, 'expires_at': time.time() + 3600}

    def test_foreign_origin_never_gets_session_or_script(self):
        self.window.get_current_url.return_value = 'https://spacekijun.lovable.app.evil.test'
        with patch.object(login, 'issue_session') as issue:
            self.bridge.connect(self.window, 'space', 'my-user', 0)
        issue.assert_not_called()
        self.window.evaluate_js.assert_not_called()

    def test_own_existing_valid_web_session_is_preserved(self):
        self.window.evaluate_js.return_value = {'user': 'my-user', 'expires': time.time() + 3600}
        with patch.object(login, 'issue_session') as issue:
            self.bridge.connect(self.window, 'space', 'my-user', 0)
        issue.assert_not_called()
        self.window.load_url.assert_not_called()

    def test_switch_to_desktop_identity_does_not_put_tokens_in_url_or_logs(self):
        self.window.evaluate_js.side_effect = [{'user': 'old-user'}, True]
        with patch.object(login, 'issue_session', return_value=self.session), patch.object(login.supa_auth, 'load_session', return_value={'user_id': 'my-user'}):
            self.bridge.connect(self.window, 'space', 'my-user', 0)
        self.window.load_url.assert_called_once_with(login.ORIGINS['space'])
        self.assertNotIn('test-web-token', str(self.log.call_args_list))

    def test_after_login_the_requested_page_opens_not_the_home(self):
        """웹 로그인이 끝나 가던 때 데스크에서 고른 기능이 홈으로 열리던 것 (2026-10-14 사용자 보고)."""
        space = login.ORIGINS['space']
        for here, target, opened in ((space + '/planner', None, space + '/planner'),           # 보던 화면
                                     (space + '/tamagotchi', space + '/planner', space + '/planner'),  # 열려던 화면
                                     (space + '/auth', None, space),                            # 로그인 화면이면 첫 화면
                                     (space + '/auth', space + '/star-tower?mini=1#x', space + '/star-tower?mini=1')):
            self.window.reset_mock()
            self.window.get_current_url.return_value = here
            self.window.evaluate_js.side_effect = [{'user': 'my-user', 'expires': time.time() + 30}, True]
            with patch.object(login, 'issue_session', return_value=self.session), \
                    patch.object(login.supa_auth, 'load_session', return_value={'user_id': 'my-user'}):
                self.bridge.connect(self.window, 'space', 'my-user', 0, target)
            self.window.load_url.assert_called_once_with(opened)
        self.assertEqual(login.landing('space', 'https://spacekijun.lovable.app.evil.test/planner'), space)
        self.assertEqual(login.landing('space', space + '/LOGIN'), space)

    def test_logout_race_discards_new_session_without_installing(self):
        self.window.evaluate_js.return_value = {}
        def issue(*_):
            self.bridge.cancel()
            return self.session
        with patch.object(login, 'issue_session', side_effect=issue), patch.object(login, 'discard_session') as discard:
            self.bridge.connect(self.window, 'space', 'my-user', 0)
        discard.assert_called_once_with(self.session)
        self.assertEqual(self.window.evaluate_js.call_count, 1)

    def test_redirect_during_issuance_never_receives_tokens(self):
        self.window.get_current_url.side_effect = [login.ORIGINS['space'], 'https://accounts.google.com']
        self.window.evaluate_js.return_value = {}
        with patch.object(login, 'issue_session', return_value=self.session), patch.object(login.supa_auth, 'load_session', return_value={'user_id':'my-user'}), patch.object(login, 'discard_session') as discard:
            self.bridge.connect(self.window, 'space', 'my-user', 0)
        discard.assert_called_once()
        self.assertEqual(self.window.evaluate_js.call_count, 1)

    def test_logged_out_desktop_leaves_manual_website_login_available(self):
        with patch.object(login.supa_auth, 'load_session', return_value=None), patch.object(login, 'issue_session') as issue:
            self.bridge.start(self.window, 'space')
        issue.assert_not_called()
        self.window.evaluate_js.assert_not_called()
