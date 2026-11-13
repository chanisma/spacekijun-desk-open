"""전북교육연수포털(jbstudy) 자동 로그인 (2026-10-29 요청, 교사만).

진짜 브라우저(Edge, 창 없이)에 실제 화면을 본뜬 가짜 페이지를 띄워 `portal.login_jbstudy` 를 돌린다 — 사이트에는
나가지 않는다(주소를 가로챈다). 본뜬 것: 불러올 때마다 바뀌는 칸 이름, `doLogin()` 의 ajax, 틀리면 alert,
로그인 여부를 알리는 전역 `isLogin`, 아래쪽에 비밀번호 칸 없이 같은 이름으로 하나 더 있는 loginForm."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명·설정 파일에는 절대 닿지 않는다
import secrets
import unittest
from unittest.mock import MagicMock, patch

import desktop
from core import edition, portal
from desktop import DesktopAPI


def login_page(signed_in: bool) -> str:
    user, pw = 'f' + secrets.token_hex(3), 'g' + secrets.token_hex(3)        # 실제 화면처럼 매번 다른 칸 이름
    return f"""<!doctype html><html><head><meta charset="utf-8"><script>var isLogin = {'true' if signed_in else 'false'};
var doLogin = function() {{
  var param = {{userId: document.getElementById('{user}').value, userPw: document.getElementById('{pw}').value}};
  fetch('/system/loginProcess.do', {{method: 'POST', body: JSON.stringify(param)}}).then(r => r.text()).then(data => {{
    if (data == 'false') {{ alert('아이디 또는 비밀번호를 잘못 입력했습니다.\\n입력하신 내용을 다시 확인해주세요.'); return; }}
    if (data == 'failCntOver') {{ alert('로그인 시도 실패 횟수 제한 상태입니다.'); return; }}
    document.location.href = '/main.do';
  }});
}};</script></head><body>
<header><a href="/system/login/login.do">로그인</a></header>
<form name="loginForm" method="post" action="system/loginProcess.do" autocomplete="off">
  <input type="text" id="{user}" name="{user}" placeholder="6~20자의 영문, 숫자만 가능">
  <div class="pass_box"><input type="password" id="{pw}" name="{pw}">
  <button type="button" class="btn_pass on"><span>비밀번호 보기</span></button></div>
  <button type="button" onclick="location.href='javascript:doLogin();'">로그인</button>
</form>
<form name="loginForm" id="loginForm" action="/system/login/login.do" method="POST"><input type="hidden" name="loginReferer"></form>
</body></html>"""


MAIN = """<!doctype html><html><head><meta charset="utf-8"><script>var isLogin = true;</script></head>
<body><header>권민결님 <a href="javascript:fn_logout()">로그아웃</a></header><main>나의 강의실</main></body></html>"""


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch(channel='msedge', headless=True)
        except Exception as exc:                       # Edge 가 없는 PC
            cls.pw.stop()
            raise unittest.SkipTest(f'Edge 를 띄우지 못했습니다: {exc}')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.posted, self.signed_in = [], False

        def serve(route):
            url = route.request.url
            if url.endswith('/system/loginProcess.do'):
                self.posted.append(route.request.post_data)
                ok = '"userId":"teacher01"' in route.request.post_data and '"userPw":"pa ss"' in route.request.post_data
                self.signed_in = self.signed_in or ok
                return route.fulfill(body='true' if ok else 'false', content_type='text/plain')
            if url.endswith('/main.do'):
                return route.fulfill(body=MAIN, content_type='text/html; charset=utf-8')
            return route.fulfill(body=login_page(self.signed_in), content_type='text/html; charset=utf-8')
        self.page.route('https://www.jbstudy.kr/**', serve)

    def test_fields_are_found_although_their_names_change(self):
        result = portal.login_jbstudy(self.page, ' teacher01 ', 'pa ss')
        self.assertTrue(result['ok'])
        self.assertEqual(result['user'], '권민결')
        self.assertTrue(self.page.url.endswith('/main.do'))
        self.assertEqual(len(self.posted), 1)

    def test_a_wrong_password_stops_after_one_try_and_says_what_the_site_said(self):
        with self.assertRaises(portal.LoginError) as caught:
            portal.login_jbstudy(self.page, 'teacher01', 'wrong')
        self.assertIn('아이디 또는 비밀번호를 잘못 입력했습니다', str(caught.exception))
        self.assertEqual(len(self.posted), 1)                                          # 다시 넣지 않는다 (잠김)

    def test_an_existing_session_is_used_as_is(self):
        self.signed_in = True
        self.assertTrue(portal.login_jbstudy(self.page, 'teacher01', 'pa ss')['ok'])
        self.assertEqual(self.posted, [])

    def test_missing_values_are_reported_before_opening(self):
        with self.assertRaises(portal.LoginError):
            portal.login_jbstudy(self.page, '', 'x')
        with self.assertRaises(portal.LoginError):
            portal.login_jbstudy(self.page, 'x', '  ')


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.api = DesktopAPI()
        self.addCleanup(self.api._close)

    def test_saving_keeps_the_other_services_untouched(self):
        saved = {'cert_password': 'cert', 'aiep_id': 'a', 'aiep_password': 'ap'}
        with patch('desktop.secretstore.load', return_value=saved.copy()), patch('desktop.secretstore.save') as save:
            self.assertTrue(self.api.call('save_jbstudy', {'jbstudy_id': ' me ', 'jbstudy_password': 'pw'})['ok'])
        values = save.call_args.args[0]
        self.assertEqual((values['jbstudy_id'], values['jbstudy_password']), ('me', 'pw'))
        self.assertEqual((values['cert_password'], values['aiep_password']), ('cert', 'ap'))

    def test_the_button_opens_the_site_until_an_account_is_saved_then_signs_in(self):
        with patch('desktop.secretstore.load', return_value={}), \
             patch.object(self.api, '_open_plain', return_value='열었습니다') as plain:
            self.assertTrue(self.api.call('open_jbstudy', {})['ok'])
        plain.assert_called_once_with('jbstudy')
        with patch('desktop.secretstore.load', return_value={'jbstudy_id': 'me', 'jbstudy_password': 'pw'}), \
             patch.object(self.api, '_open_plain') as plain, patch('desktop.threading.Thread') as thread:
            self.assertTrue(self.api.call('open_jbstudy', {})['ok'])
        plain.assert_not_called()
        thread.assert_called_once()

    def test_it_signs_in_with_its_own_account(self):
        cred = {'jbstudy_id': 'me', 'jbstudy_password': 'pw', 'riro_id': 'r', 'riro_password': 'rp'}
        with patch('core.portal.login_jbstudy') as jbstudy, patch('core.portal.login_riro') as riro:
            DesktopAPI._sign_in('jbstudy', MagicMock(), cred, lambda m: None)
        riro.assert_not_called()
        self.assertEqual(jbstudy.call_args.args[1:], ('me', 'pw'))

    def test_settings_panel_and_disconnect(self):
        with patch('desktop.secretstore.load', return_value={'jbstudy_id': 'me', 'jbstudy_password': 'pw'}):
            accounts = self.api.call('settings_panel')['data']['accounts']
            self.assertEqual(accounts['jbstudy'], {'label': '전북교육연수포털', 'id': 'me', 'saved': True})
            with patch('desktop.secretstore.clear') as clear, patch.object(DesktopAPI, '_forget_browser', return_value=True):
                self.assertIn('연결을 해제', self.api.call('disconnect', {'target': 'jbstudy'})['data'])
            clear.assert_called_once()

    def test_students_do_not_get_it(self):
        with patch.object(edition, 'STUDENT', True), patch.object(desktop.edition, 'STUDENT', True), \
             patch('desktop.secretstore.load', return_value={}):
            self.assertNotIn('jbstudy', self.api.call('settings_panel')['data']['accounts'])
            self.assertFalse(self.api.call('open_jbstudy', {})['ok'])
            self.assertFalse(self.api.call('student_account_save', {'target': 'jbstudy', 'id': 'a', 'password': 'b'})['ok'])
        self.assertNotIn('open_jbstudy', desktop.STUDENT_ACTIONS)

    def test_launchable_with_its_own_profile(self):
        with patch('core.portal.os.makedirs'), patch('core.portal.os.path.join', side_effect=lambda *p: '/'.join(p)):
            playwright = MagicMock()
            portal.launch(playwright, target='jbstudy')
        self.assertIn('browser-jbstudy-msedge', playwright.chromium.launch_persistent_context.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
