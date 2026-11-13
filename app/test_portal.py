"""Browser-based timing tests on local fixtures, without real credentials."""
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from playwright.sync_api import sync_playwright
from core import portal


class PortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel='msedge', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    def test_every_waiting_test_survives_a_page_with_no_body(self):
        """화면이 넘어가는 찰나에는 `document.body` 가 잠깐 없다. 그때 `.innerText` 를
        읽으면 판정식이 **예외로 끝나** 기다리기를 그만두고 로그인이 중단된다
        (2026-09-15 실측: 업무포털에서 `Cannot read properties of null` 로 멈췄다).
        예외 대신 거짓을 돌려줘야 다음 바퀴에 다시 본다."""
        names = [name for name in dir(portal)
                 if name.endswith(('_SIGNED_IN', '_READY')) and isinstance(getattr(portal, name), str)]
        self.assertGreaterEqual(len(names), 8, names)
        self.page.goto('about:blank')
        self.page.evaluate("() => document.documentElement.removeChild(document.body)")
        for name in names:
            with self.subTest(name):
                # 예외 없이 참거짓이 나와야 한다.
                self.assertIn(self.page.evaluate(f'({getattr(portal, name)})()'), (True, False))

    def test_certificate_name_selects_matching_row_only(self):
        import re
        self.page.set_content('''<table id="kc_cert_list"><tr><th>이름</th></tr>
          <tr onclick="window.picked='wrong'"><td>김교사</td></tr>
          <tr onclick="window.picked='right'"><td><div><span>홍길동(학교)[1]</span></div></td><td>2027</td></tr>
          <tr style="display:none"><td>홍길동(학교)[1]</td></tr></table>''')
        result = self.page.evaluate(portal._PICK_CERT, {'list':'#kc_cert_list', 'match':re.escape('홍길동(학교)[1]')})
        self.assertEqual(result['status'], 'selected')
        self.assertEqual(self.page.evaluate('window.picked'), 'right')

    def test_real_widget_delayed_rows_are_awaited_before_password(self):
        from pathlib import Path
        fixture = Path(__file__).parents[1] / 'scripts' / 'cert-widget-fixture.html'
        self.page.set_content(fixture.read_text(encoding='utf-8') + '<input name="certPassword"><button class="kc-btn-blue">확인</button>')
        self.page.evaluate('''() => {
            const body=document.querySelector('#kc_cert_list tbody');
            const rows=body.innerHTML; body.innerHTML='';
            window.clicked=false;
            document.querySelector('.kc-btn-blue').onclick=()=>window.clicked=true;
            setTimeout(()=>body.innerHTML=rows, 900);
        }''')
        started = time.perf_counter()
        with patch('core.portal.wait_overlay_gone', return_value=True):
            picked = portal.submit_cert(self.page, self.page, 'test-only', '홍길동')
        self.assertIn('홍길동', picked)
        self.assertGreaterEqual(time.perf_counter()-started, 1.5)
        self.assertTrue(self.page.evaluate('window.clicked'))
        self.assertEqual(self.page.locator('[name=certPassword]').input_value(), 'test-only')

    def test_empty_table_headers_are_not_certificate_candidates(self):
        self.page.set_content('<div id="kc_cert_list"><table><thead><tr><th><div>이름</div></th></tr></thead><tbody></tbody></table></div>')
        snapshot = self.page.evaluate(portal._PICK_CERT, {'list':'#kc_cert_list','probe':True})
        self.assertEqual(snapshot['total'], 0)

    def test_missing_or_duplicate_certificate_never_enters_password(self):
        for names, match in [(['홍길동', '김교사'], '없는이름'), (['홍길동 2026', '홍길동 2027'], '홍길동'), (['홍길동', '김교사'], None)]:
            with self.subTest(names=names, match=match):
                rows = ''.join(f'<tr onclick="window.clicked=true"><td><div>{name}</div></td></tr>' for name in names)
                self.page.set_content(f'<table id="kc_cert_list">{rows}</table><input name="certPassword">')
                self.page.evaluate('window.clicked=false')
                with self.assertRaises(portal.LoginError):
                    portal.submit_cert(self.page, self.page, 'test-only', match)
                self.assertEqual(self.page.locator('[name=certPassword]').input_value(), '')
                self.assertFalse(self.page.evaluate('window.clicked'))

    def test_nested_div_certificate_count_and_single_fallback(self):
        self.page.set_content('<div id="kc_cert_list"><div><div>홍길동 2027</div></div><div><div>김교사 2027</div></div></div>')
        self.assertEqual(self.page.evaluate(portal._PICK_CERT, {'list':'#kc_cert_list', 'match':'홍길동'})['status'], 'selected')
        self.page.set_content('<table id="kc_cert_list"><tr><td>홍길동</td><td>2027</td></tr></table>')
        self.assertEqual(self.page.evaluate(portal._PICK_CERT, {'list':'#kc_cert_list', 'match':None})['status'], 'selected')

    def test_security_install_link_does_not_block_login(self):
        self.page.set_content('<a>보안프로그램 설치 안내</a><button id="btnLgn">교육행정 전자서명 인증서 로그인</button>')
        started = time.perf_counter()
        self.page.wait_for_function(portal.EDUPTL_READY, timeout=2000)
        self.assertLess(time.perf_counter() - started, 1)
        self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<p id=loading>보안프로그램이 로딩중입니다</p>')")
        self.assertFalse(self.page.evaluate(portal.EDUPTL_READY))
        self.page.evaluate("setTimeout(()=>document.getElementById('loading').remove(), 300)")
        self.page.wait_for_function(portal.EDUPTL_READY, timeout=2000)

    def test_cached_sessions_skip_four_and_five_second_waits(self):
        fixtures = [
            (portal.login_neis, '<div class="cl-navigationbar-text cl-text">업무</div>', {}),
            (portal.login_eduptl, '<button>로그아웃</button> 업무바로가기', {}),
            (portal.login_klef, '테스트님 문서관리', {'user_id':'test-only'}),
        ]
        for login, html, kwargs in fixtures:
            with self.subTest(login=login.__name__):
                self.page.route('https://portal.test/**', lambda route, request, text=html: route.fulfill(body= '<meta charset=utf-8>'+text, content_type='text/html'))
                started = time.perf_counter()
                result = login(self.page, 'not-a-real-password', base_url='https://portal.test/', **kwargs)
                self.assertTrue(result['ok'])
                self.assertLess(time.perf_counter() - started, 2)
                self.page.unroute('https://portal.test/**')

    def test_neis_waits_for_visible_login_control(self):
        self.page.set_content('<button style="display:none">인증서 로그인</button>')
        self.assertFalse(self.page.evaluate(portal.NEIS_READY))
        self.page.evaluate("setTimeout(()=>document.querySelector('button').style.display='block',300)")
        self.page.wait_for_function(portal.NEIS_READY, timeout=2000)
        self.assertFalse(self.page.evaluate(portal.NEIS_SIGNED_IN))

    def test_eduptl_success_returns_without_nine_second_delay(self):
        html = '<meta charset=utf-8><button id="btnLgn">교육행정 전자서명 인증서 로그인</button>'
        self.page.route('https://portal.test/**', lambda route: route.fulfill(body=html, content_type='text/html'))
        def submit(*args):
            self.page.evaluate("document.body.innerHTML='<button>로그아웃</button> 업무바로가기'")
            return 'test-certificate'
        with patch.object(portal, 'find_cert_root', return_value=self.page), patch.object(portal, 'submit_cert', side_effect=submit):
            started = time.perf_counter()
            result = portal.login_eduptl(self.page, 'not-a-real-password', base_url='https://portal.test/')
            self.assertTrue(result['ok'])
            self.assertLess(time.perf_counter() - started, 2)

    def test_klef_types_id_and_uses_certificate_flow_only(self):
        html = f'<meta charset=utf-8><input id="{portal.KLEF_PREFIX}.edtUsid:input"><button id="{portal.KLEF_PREFIX}.btnLogin">Login</button>'
        self.page.route('https://portal.test/**', lambda route: route.fulfill(body=html, content_type='text/html'))
        def submit(*args):
            self.assertEqual(self.page.locator(portal.KLEF_ID).input_value(), 'test-id')
            self.page.evaluate("document.body.innerText='테스트님 문서관리'")
            return 'test-certificate'
        with patch.object(portal, 'find_cert_root', return_value=self.page), patch.object(portal, 'submit_cert', side_effect=submit):
            result = portal.login_klef(self.page, 'not-a-real-password', base_url='https://portal.test/', user_id='test-id')
            self.assertTrue(result['ok'])


class ProfileStartupTests(unittest.TestCase):
    """지난번 창을 되살리지 않게 프로필을 손본다. 브라우저를 띄우지 않는 시험이다.

    2026-09-15 사용자 보고: 나이스 하나를 눌렀는데 며칠 전 에듀파인 창까지 함께 떠서 창이
    셋이 됐다. 실측으로도 아무것도 하지 않고 띄우기만 했는데 지난 창이 먼저 떠 있었다.
    """

    def setUp(self):
        import tempfile
        self.profile = Path(tempfile.mkdtemp(prefix='desk-profile-test-'))
        self.default = self.profile / 'Default'
        self.default.mkdir()

    def test_the_record_of_last_time_is_thrown_away(self):
        sessions = self.default / 'Sessions'
        sessions.mkdir()
        (sessions / 'Session_1343').write_text('지난 창', encoding='utf-8')
        portal.forget_last_session(self.profile)
        self.assertFalse(sessions.exists())

    def test_startup_is_pinned_to_a_new_tab_and_the_rest_is_kept(self):
        import json
        mine = {'session': {'restore_on_startup': 1, 'startup_urls': ['https://old.test/']},
                'profile': {'exit_type': 'Crashed'},
                'bookmark_bar': {'show_on_all_tabs': True}}      # 사용자 설정은 건드리지 않는다
        (self.default / 'Preferences').write_text(json.dumps(mine), encoding='utf-8')
        portal.forget_last_session(self.profile)
        got = json.loads((self.default / 'Preferences').read_text(encoding='utf-8'))
        self.assertEqual(got['session']['restore_on_startup'], 5)
        self.assertEqual(got['session']['startup_urls'], [])
        self.assertEqual(got['profile']['exit_type'], 'Normal')
        self.assertTrue(got['bookmark_bar']['show_on_all_tabs'])

    def test_a_profile_never_used_and_a_broken_file_are_both_fine(self):
        portal.forget_last_session(self.profile)          # Preferences 가 없다
        (self.default / 'Preferences').write_text('{망가진', encoding='utf-8')
        portal.forget_last_session(self.profile)          # 던지지 않는다

    def test_launching_always_forgets_first(self):
        """띄운 뒤에 지우면 늦다. Edge 가 이미 그 기록을 읽은 뒤다."""
        order = []
        playwright = MagicMock()
        playwright.chromium.launch_persistent_context.side_effect = (
            lambda *a, **k: order.append('띄움'))
        with patch.object(portal, 'DATA_DIR', str(self.profile)), \
             patch.object(portal, 'forget_last_session',
                          side_effect=lambda spot: order.append('지움')):
            portal.launch(playwright, target='neis')
        self.assertEqual(order, ['지움', '띄움'])


if __name__ == '__main__':
    unittest.main()
