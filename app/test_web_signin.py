"""학생판 자동 로그인(core/web_signin.py) — 가짜 창으로 순서를 따라가 본다. 네트워크·진짜 창은 쓰지 않는다."""
import threading
import unittest

from core import web_signin


class FakeWindow:
    """화면 상태를 차례로 돌려주는 창. 넣은 스크립트를 모아 둔다."""

    def __init__(self, states, url='https://kijun.riroschool.kr/user.php?action=signin'):
        self.states = list(states)
        self.url = url
        self.scripts = []

    def get_current_url(self):
        return self.url

    def evaluate_js(self, script):
        self.scripts.append(script)
        if '"pw"' in script:                       # 아이디·비밀번호를 넣는 스크립트
            return 'submitted'
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def drive(window, target='riro', **kw):
    clock = Clock()
    return web_signin.drive(window, target, 'kijun2601', 's3cret"pw', threading.Event(),
                            clock=clock, sleep=clock.sleep, **kw), window


class DriveTest(unittest.TestCase):
    def test_signs_in_once_and_stops(self):
        result, window = drive(FakeWindow(['wait', 'form', 'wait', 'signed-in']))
        self.assertEqual(result, 'signed-in')
        fills = [s for s in window.scripts if 's3cret' in s]
        self.assertEqual(len(fills), 1)
        self.assertIn('"s3cret\\"pw"', fills[0])           # JSON 으로 넣는다 — 따옴표가 스크립트를 깨지 않는다

    def test_wrong_password_is_never_retried(self):
        # 🚨 리로스쿨은 5번 틀리면 잠근다. 폼이 그대로면 다시 넣지 않고 멈춘다
        result, window = drive(FakeWindow(['form']))
        self.assertEqual(result, 'wrong')
        self.assertEqual(len([s for s in window.scripts if 's3cret' in s]), 1)

    def test_password_is_never_put_on_another_address(self):
        result, window = drive(FakeWindow(['form'], url='https://evil.example/login'), timeout=5)
        self.assertEqual(result, 'timeout')
        self.assertFalse([s for s in window.scripts if 's3cret' in s])

    def test_closed_window_stops_at_once(self):
        closed = threading.Event()
        closed.set()
        result = web_signin.drive(FakeWindow(['form']), 'riro', 'a', 'b', closed)
        self.assertEqual(result, 'closed')

    def test_stuck_window_gives_up(self):
        class Dead(FakeWindow):
            def evaluate_js(self, script):
                raise RuntimeError('alert open')
        result, _ = drive(Dead(['form']))
        self.assertEqual(result, 'stuck')


class ScriptTest(unittest.TestCase):
    def test_aiep_goes_through_the_student_button(self):
        script = web_signin.step_script('aiep')
        self.assertIn('"학생"', script)
        self.assertIn('.cl-button.student', script)
        self.assertIn('"ai-auth.jbedu.kr"', script)

    def test_aiep_id_drops_the_domain(self):
        self.assertEqual(web_signin.clean_id('aiep', ' stu01@ai.jbedu.kr '), 'stu01')
        self.assertEqual(web_signin.clean_id('riro', 'stu01@ai.jbedu.kr'), 'stu01@ai.jbedu.kr')

    def test_fill_scripts_check_the_address_first(self):
        for target in ('riro', 'aiep'):
            script = web_signin.fill_script(target, 'a', 'b')
            self.assertLess(script.index('location.hostname !== c.host'), script.index('put(id'))

    def test_riro_uses_the_student_teacher_tab(self):
        self.assertIn("getElementById('first')", web_signin.fill_script('riro', 'a', 'b'))


if __name__ == '__main__':
    unittest.main()
