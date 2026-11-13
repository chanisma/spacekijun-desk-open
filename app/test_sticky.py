from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명 파일에는 절대 닿지 않는다
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import sticky

BOARD, ME = 'board-1', 'resource-1'


class StickyTest(unittest.TestCase):
    def setUp(self):
        sticky.forget()
        patcher = mock.patch.object(sticky, 'board', return_value=(BOARD, ME))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_title_is_first_non_empty_line(self):
        self.assertEqual(sticky._title('\n  장보기  \n우유'), '장보기')
        self.assertEqual(sticky._title('   '), '메모')
        self.assertEqual(len(sticky._title('가' * 200)), 60)
        # 메모 서식 표시는 제목에 남기지 않는다
        self.assertEqual(sticky._title('# 이번 주 할 일\n- 채점'), '이번 주 할 일')
        self.assertEqual(sticky._title('- 우유 사기'), '우유 사기')
        self.assertEqual(sticky._title('#해시태그'), '#해시태그')        # 띄어쓰기 없는 #는 제목 표시가 아니다

    def test_rejects_unknown_color_and_huge_content(self):
        with self.assertRaises(ValueError):
            sticky._clean({'color': 'red; drop table'})
        with self.assertRaises(ValueError):
            sticky._clean({'content': 'x' * (sticky.MAX_CONTENT + 1)})
        with self.assertRaises(ValueError):
            sticky._clean({'content': 3})

    def test_update_is_limited_to_my_sticky_board(self):
        with mock.patch.object(sticky, '_request', return_value=[{'id': 'n1'}]) as request:
            sticky.update({'id': 'n1', 'content': '오늘 할 일'})
        method, table, params = request.call_args.args[:3]
        self.assertEqual((method, table), ('PATCH', 'collab_notes'))
        self.assertEqual(params['board_id'], 'eq.' + BOARD)
        body = request.call_args.kwargs['body']
        self.assertEqual(body['title'], '오늘 할 일')
        self.assertNotIn('board_id', body)

    def test_update_of_missing_note_reports_deleted(self):
        with mock.patch.object(sticky, '_request', return_value=[]):
            with self.assertRaises(LookupError):
                sticky.update({'id': 'gone', 'content': 'a'})

    def test_create_writes_into_sticky_board_as_me(self):
        with mock.patch.object(sticky, '_request', return_value=[{'id': 'n1', 'content': ''}]) as request:
            sticky.create({})
        body = request.call_args.kwargs['body']
        self.assertEqual((body['board_id'], body['author_id']), (BOARD, ME))
        self.assertEqual(body['color'], sticky.COLORS[0])

    def test_delete_requires_id(self):
        with self.assertRaises(ValueError):
            sticky.delete({})


class StickyBoardTest(unittest.TestCase):
    def setUp(self):
        sticky.forget()
        for name, value in (('load_session', {'user_id': 'u1'}), ('my_resource_id', ME)):
            patcher = mock.patch.object(sticky.supa_auth, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_board_is_created_private_once(self):
        calls = []

        def fake(method, table, params=None, body=None, prefer=None):
            calls.append((method, body))
            return [] if method == 'GET' else [{'id': BOARD}]
        with mock.patch.object(sticky, '_request', side_effect=fake):
            self.assertEqual(sticky.board(), (BOARD, ME))
            self.assertEqual(sticky.board(), (BOARD, ME))     # 두 번째는 저장해 둔 값
        posted = [body for method, body in calls if method == 'POST']
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0]['visibility'], 'private')
        self.assertEqual(posted[0]['meta'], {'kind': sticky.KIND})

    def test_board_created_elsewhere_is_reused_after_conflict(self):
        gets = iter([[], [{'id': 'other-pc'}]])

        def fake(method, table, params=None, body=None, prefer=None):
            if method == 'POST':
                raise sticky._Conflict()
            return next(gets)
        with mock.patch.object(sticky, '_request', side_effect=fake):
            self.assertEqual(sticky.board(), ('other-pc', ME))


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args):
        for handler in self.handlers:
            handler(*args)


def _window():
    window = mock.MagicMock()
    window.events.loaded, window.events.moved = _Event(), _Event()
    window.events.resized, window.events.closed = _Event(), _Event()
    return window


class StickyWindowTest(unittest.TestCase):
    def setUp(self):
        import desktop
        self.api = desktop.DesktopAPI()
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.api._sticky_path = Path(room.name) / 'sticky-windows.json'
        self.api._sticky_layout = {}
        patcher = mock.patch.object(sticky, 'get', side_effect=lambda p: {'id': p['id'], 'title': '장보기'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_open_reuses_window_and_remembers_place(self):
        window = _window()
        with mock.patch('webview.create_window', return_value=window) as create:
            self.assertTrue(self.api.call('sticky_open', {'id': 'n1'})['ok'])
            self.assertTrue(self.api.call('sticky_open', {'id': 'n1'})['ok'])
        create.assert_called_once()
        self.assertIs(create.call_args.kwargs['js_api'], self.api)   # 로컬 화면이라 API 를 준다
        window.events.moved.fire(40, 50)
        window.events.resized.fire(300, 280)
        window.events.loaded.fire()
        window.run_js.assert_called_once()
        self.assertIn('"n1"', window.run_js.call_args.args[0])
        window.events.closed.fire()                  # 사용자가 닫음 → 다음 실행엔 안 띄운다
        saved = json.loads(self.api._sticky_path.read_text(encoding='utf-8'))
        self.assertEqual(saved['n1'], {'x': 40, 'y': 50, 'w': 300, 'h': 280})
        self.assertNotIn('n1', self.api._sticky_windows)

    def test_app_exit_keeps_open_notes_for_next_launch(self):
        with mock.patch('webview.create_window', return_value=_window()):
            self.api.call('sticky_open', {'id': 'n1'})
        self.api._close()
        saved = json.loads(self.api._sticky_path.read_text(encoding='utf-8'))
        self.assertTrue(saved['n1']['open'])

    def test_delete_closes_window_and_forgets_place(self):
        window = _window()
        with mock.patch('webview.create_window', return_value=window), \
             mock.patch.object(sticky, 'delete', return_value='메모를 삭제했습니다.'):
            self.api.call('sticky_open', {'id': 'n1'})
            self.assertTrue(self.api.call('sticky_delete', {'id': 'n1'})['ok'])
        window.destroy.assert_called_once()
        self.assertNotIn('n1', self.api._sticky_layout)

    def test_delete_asks_outside_the_page_and_cancel_keeps_note(self):
        window = _window()
        with mock.patch('webview.create_window', return_value=window):
            self.api.call('sticky_open', {'id': 'n1'})
        with mock.patch.object(type(self.api), '_confirm', return_value=False) as confirm, \
             mock.patch.object(sticky, 'delete') as delete:
            result = self.api.call('sticky_delete', {'id': 'n1', 'ask': True})
        self.assertEqual(result['data']['deleted'], False)
        self.assertIs(confirm.call_args.args[0], window)     # 메모 창을 주인으로 띄운다
        delete.assert_not_called()
        window.destroy.assert_not_called()

    def test_pin_goes_through_window_thread_without_holding_lock(self):
        window = _window()
        with mock.patch('webview.create_window', return_value=window):
            self.api.call('sticky_open', {'id': 'n1'})

        def apply(made, on_top):
            # 잠금을 쥔 채 창 스레드로 넘기면 닫힘 처리와 서로 막힌다
            # (RLock 이라 같은 스레드에선 늘 잡힌다 — 다른 스레드에서 잡아 본다)
            import threading
            got = []

            def probe():
                if self.api._lock.acquire(blocking=False):
                    got.append(True)
                    self.api._lock.release()
            worker = threading.Thread(target=probe)
            worker.start()
            worker.join()
            self.assertEqual(got, [True])
        with mock.patch.object(type(self.api), '_set_on_top', side_effect=apply) as set_on_top:
            self.assertTrue(self.api.call('sticky_pin', {'id': 'n1', 'on_top': True})['ok'])
        set_on_top.assert_called_once_with(window, True)
        self.assertTrue(self.api._sticky_layout['n1']['top'])

    def test_pin_requires_boolean(self):
        self.assertFalse(self.api.call('sticky_pin', {'id': 'n1', 'on_top': 'yes'})['ok'])

    def test_logout_closes_notes_of_previous_account(self):
        window = _window()
        with mock.patch('webview.create_window', return_value=window):
            self.api.call('sticky_open', {'id': 'n1'})
        with mock.patch('desktop.supa_auth.logout'), mock.patch('desktop.supa_auth.load_session', return_value={}):
            self.assertTrue(self.api.call('auth', {'logout': True})['ok'])
        window.destroy.assert_called_once()
        self.assertEqual(self.api._sticky_layout, {})


if __name__ == '__main__':
    unittest.main()
