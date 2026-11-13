"""별사이 목장 (core/ranch.py) — 띠 자리, 수업 시간 판정, 창 모양, 스페이스기전 다리."""
from test_sandbox import use_sandbox
use_sandbox()
import io
import json
import unittest
import urllib.error
from datetime import datetime
from unittest import mock

from core import ranch


class PlaceTests(unittest.TestCase):
    """참고 게임 Tiny Pasture 의 화면 방식(2026-11-06) — 화면 아래를 가로로 길게, 너비·가로 위치·높이·크기를 «화면»에서."""
    WORK = (0, 0, 1920, 1032)            # 작업 표시줄 48px
    SHELF = (660, 900, 1260, 1000)

    def test_default_is_the_full_width_right_above_the_dock(self):
        spot = ranch.place('bottom', self.SHELF, self.WORK, {}, 1.0)
        self.assertEqual((spot['mode'], spot['x'], spot['width'], spot['zoom']), ('dock', 0, 1920, 2))
        self.assertEqual(spot['y'] + spot['height'], 900 - ranch.GAP)          # 독 판 바로 위
        self.assertEqual(spot['height'], ranch.STRIP_ART * 2 + ranch.PANEL)

    def test_other_docks_use_the_bottom_of_the_desktop(self):
        for anchor in ('left', 'right', 'top'):
            spot = ranch.place(anchor, (0, 300, 90, 800), self.WORK, {}, 1.0)
            self.assertEqual((spot['mode'], spot['x'], spot['width']), ('desk', 0, 1920), anchor)
            self.assertEqual(spot['y'] + spot['height'], 1032)               # 작업 표시줄 바로 위

    def test_width_position_lift_and_zoom_follow_the_view(self):
        spot = ranch.place('left', None, self.WORK, {'width': 0.5, 'x': 0.25, 'lift': 40, 'zoom': 3}, 1.0)
        self.assertEqual((spot['width'], spot['x'], spot['zoom']), (960, 0, 3))
        self.assertEqual(spot['y'] + spot['height'], 1032 - 40)
        self.assertEqual(spot['height'], ranch.STRIP_ART * 3 + ranch.PANEL)
        right = ranch.place('left', None, self.WORK, {'width': 0.5, 'x': 1.0}, 1.0)
        self.assertEqual(right['x'] + right['width'], 1920)                   # 화면 밖으로 나가지 않는다

    def test_zoom_default_follows_the_screen_resolution(self):
        self.assertEqual(ranch.place('left', None, (0, 0, 2560, 1392), {}, 1.0)['zoom'], 3)
        self.assertEqual(ranch.place('left', None, (0, 0, 3840, 2112), {}, 1.5)['zoom'], 4)

    def test_bad_view_values_fall_back(self):
        view = ranch.clean_view({'width': 9, 'x': -1, 'lift': 'a', 'zoom': True, 'top': 'yes'})
        self.assertEqual(view, ranch.VIEW_DEFAULT)
        self.assertEqual(ranch.clean_view({'top': True, 'zoom': 4})['zoom'], 4)


class LessonTests(unittest.TestCase):
    MON = [{'day': 1, 'period': 1}, {'day': 1, 'period': 2}, {'day': 1, 'period': 4}]

    def at(self, text):
        return datetime.fromisoformat(text + '+09:00')

    def test_in_class_only_during_a_lesson_on_the_timetable(self):
        self.assertTrue(ranch.lesson_now(self.MON, self.at('2026-11-09T09:10'))['in_class'])      # 월 1교시
        self.assertFalse(ranch.lesson_now(self.MON, self.at('2026-11-09T09:55'))['in_class'])     # 쉬는 시간
        self.assertFalse(ranch.lesson_now(self.MON, self.at('2026-11-09T11:10'))['in_class'])     # 3교시는 비어 있다
        self.assertFalse(ranch.lesson_now(self.MON, self.at('2026-11-10T09:10'))['in_class'])     # 화요일은 수업 없음
        now = ranch.lesson_now(self.MON, self.at('2026-11-09T12:55'))
        self.assertEqual((now['in_class'], now['period'], now['until']), (True, 4, '13:40'))

    def test_without_a_timetable_weekday_periods_count_as_class(self):
        self.assertTrue(ranch.lesson_now(None, self.at('2026-11-10T14:00'))['in_class'])          # 5교시
        self.assertFalse(ranch.lesson_now(None, self.at('2026-11-10T12:20'))['in_class'])         # 점심
        self.assertFalse(ranch.lesson_now([], self.at('2026-11-14T10:10'))['in_class'])           # 토요일
        self.assertFalse(ranch.lesson_now(None, self.at('2026-11-10T14:00'))['known'])


class RegionTests(unittest.TestCase):
    def test_rects_are_checked(self):
        self.assertEqual(ranch.clean_rects([[1, 2, 3, 4], (5, 6, 7, 8)]), [(1, 2, 3, 4), (5, 6, 7, 8)])
        for bad in ('x', [[1, 2, 3]], [[1, 2, 0, 4]], [[1, 2, 'a', 4]], [[1, 2, 3, 99999]], [[0, 0, 1, 1]] * 257):
            with self.assertRaises(ValueError, msg=bad):
                ranch.clean_rects(bad)


class BridgeTests(unittest.TestCase):
    def test_only_known_calls_with_known_arguments_reach_the_server(self):
        sent = []

        def fake(request, timeout):
            sent.append((request.full_url, json.loads(request.data)))
            return io.BytesIO(b'{"conflict": false, "version": 2}')
        with mock.patch.object(ranch, '_send', fake), \
                mock.patch('core.supa_auth.auth_headers', return_value={'apikey': 'k', 'Authorization': 'Bearer t'}), \
                mock.patch('core.notify.config', return_value={'url': 'https://x.supabase.co/'}):
            got = ranch.bridge('save', {'p_version': 1, 'p_state': {'shards': 3}, 'p_owner': 'someone-else'})
            self.assertEqual(got, {'conflict': False, 'version': 2})
            self.assertEqual(sent[0], ('https://x.supabase.co/rest/v1/rpc/ranch_save', {'p_version': 1, 'p_state': {'shards': 3}}))
            with self.assertRaises(ValueError):
                ranch.bridge('admin_coin_grant', {})
            with self.assertRaises(ValueError):
                ranch.bridge('save', {'p_version': 1, 'p_state': {'x': 'a' * 60000}})

    def test_server_refusal_becomes_a_readable_error(self):
        def refuse(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 400, 'bad', {}, io.BytesIO('{"message": "수업 중에는 바꿀 수 없어요."}'.encode()))
        with mock.patch.object(ranch, '_send', refuse), \
                mock.patch('core.supa_auth.auth_headers', return_value={}), \
                mock.patch('core.notify.config', return_value={'url': 'https://x'}):
            with self.assertRaisesRegex(RuntimeError, '수업 중'):
                ranch.bridge('sell', {'p_times': 1})


if __name__ == '__main__':
    unittest.main()


class AdminOnlyTests(unittest.TestCase):
    """2026-11-11 요청: 학생판 정식 판의 목장은 관리자 계정만 — 역할을 모르면 뒤에서 묻고 그동안은 안 보인다."""

    def make(self, cached):
        import threading
        import time
        import desktop
        api = object.__new__(desktop.DesktopAPI)
        api._lock = threading.Lock()
        api._role_cache = (cached, time.monotonic()) if cached else None
        api._ranch_role_asking = False
        api._log = lambda *a: None
        api._dock_handle_tick = lambda: None
        return api, desktop

    def test_only_admin_students_see_it(self):
        for role, expected in (('admin', True), ('student', False), ('teacher', False)):
            api, desktop = self.make(role)
            with mock.patch.object(desktop.edition, 'STUDENT', True), mock.patch.dict('os.environ', {}, clear=False):
                desktop.os.environ.pop('SPACEKIJUN_RANCH', None)
                self.assertEqual(api._ranch_allowed(), expected, role)

    def test_unknown_role_asks_in_the_background_and_hides_meanwhile(self):
        api, desktop = self.make(None)
        asked = []
        api._is_admin = lambda: asked.append(1) or False
        with mock.patch.object(desktop.edition, 'STUDENT', True), \
                mock.patch.object(desktop.threading, 'Thread') as thread:
            desktop.os.environ.pop('SPACEKIJUN_RANCH', None)
            self.assertFalse(api._ranch_allowed())
            thread.assert_called_once()
            thread.call_args.kwargs['target']()
        self.assertEqual(asked, [1])
        self.assertFalse(api._ranch_role_asking)

    def test_teacher_desk_never(self):
        api, desktop = self.make('admin')
        with mock.patch.object(desktop.edition, 'STUDENT', False):
            desktop.os.environ.pop('SPACEKIJUN_RANCH', None)
            self.assertFalse(api._ranch_allowed())
