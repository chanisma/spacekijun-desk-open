import unittest
from unittest.mock import patch
from core import dashboard


class DashboardTests(unittest.TestCase):
    def test_completed_task_overrides_pending_assignee_and_multiple_deadlines(self):
        tasks = [{'title': 'finished', 'status': 'completed', 'meta': {'assignees': [{'id': 'me', 'status': 'pending'}]}},
                 {'title': 'other', 'meta': {'assignees': [{'id': 'other'}]}},
                 {'title': 'repeat', 'due_date': '2026-01-01', 'meta': {'assignees': [{'id': 'me'}],
                   'deadlines': ['2026-09-18', '2026-09-10', '2026-09-01']}}]
        rows = dashboard.task_rows({'assigned_tasks': tasks}, 'me', '2026-09-10')
        self.assertEqual([r['title'] for r in rows], ['repeat'])
        self.assertEqual(rows[0]['date'], '2026-09-10')
        self.assertEqual(rows[0]['label'], '오늘 마감')

    def test_assignee_names_are_exact_across_storage_formats(self):
        for value in ('홍길동', [{'name': '홍길동'}], {'person': {'name': '홍길동'}}):
            self.assertTrue(dashboard.assigned(value, '홍길동'))
            self.assertFalse(dashboard.assigned(value, '홍길'))

    def test_snapshot_filters_identity_and_discards_account_change(self):
        queries = []
        class Reader:
            session = {'user_id': 'current-user'}
            def get(self, table, params=None, body=None):
                queries.append((table, params, body))
                if table == 'user_resource': return [{'resource_id': 'my-resource'}]
                if table == 'resource': return [{'id': 'my-resource', 'name': 'Sample', 'type': 'teacher'}]
                if table == 'profiles': return [{'name': 'Sample'}]
                if table == 'department_notice': raise RuntimeError('offline')
                return []
        with patch.object(dashboard, 'Reader', Reader), patch.object(dashboard.supa_auth, 'load_session', return_value={'user_id': 'current-user'}):
            data = dashboard.snapshot()
            self.assertIn('notices', data['errors'])
            self.assertNotIn('notifications', data['errors'])
        for table, params, body in queries:
            if table == 'user_resource': self.assertEqual(params['user_id'], 'eq.current-user')
            if table == 'notification_events': self.assertEqual(params['resource_id'], 'eq.my-resource')
            if table == 'rpc/get_my_tasks_jsonb': self.assertEqual(body['p_user_id'], 'current-user')
        with patch.object(dashboard, 'Reader', Reader), patch.object(dashboard.supa_auth, 'load_session', return_value={'user_id': 'another-user'}):
            with self.assertRaisesRegex(ValueError, '계정이 변경'):
                dashboard.snapshot()

    def test_student_without_link_is_found_by_school_code(self):
        """학생은 대부분 user_resource 연결이 없다 — 이메일 앞부분(학번 코드)으로 찾는다 (2026-10-19 학생판 시간표 빈 화면)."""
        queries = []
        class Reader:
            session = {'user_id': 'student-user'}
            def get(self, table, params=None, body=None):
                queries.append((table, params, body))
                if table == 'user_resource': return []
                if table == 'profiles': return [{'name': '학생', 'role': 'student', 'email': 's26001@school.kr'}]
                if table == 'resource': return [{'id': 'student-resource', 'name': '학생', 'type': 'student'}]
                if table == 'system_settings': return [{'setting_value': {'year': 2026, 'semester': 2}}]
                if table == 'student_timetable': return [{'day_of_week': 1, 'period': 1, 'subject': '국어', 'teacher_name': '김'}]
                return []
        with patch.object(dashboard, 'Reader', Reader), \
             patch.object(dashboard.supa_auth, 'load_session', return_value={'user_id': 'student-user'}):
            data = dashboard.snapshot()
        self.assertEqual(data['timetable_week'], [{'day': 1, 'period': 1, 'title': '국어', 'detail': '김'}])
        self.assertEqual(data['errors'], {})
        lookup = next(params for table, params, _ in queries if table == 'resource')
        self.assertEqual((lookup['type'], lookup['status'], lookup['meta->>id']), ('eq.student', 'eq.active', 'eq.s26001'))
        timetable = next(params for table, params, _ in queries if table == 'student_timetable')
        self.assertEqual(timetable['resource_id'], 'eq.student-resource')
        asked = {table for table, _, _ in queries}
        self.assertFalse(asked & {'rpc/get_my_tasks_jsonb', 'department_notice'})   # 학생에게는 묻지 않는다

    def test_unlinked_teacher_or_unknown_student_still_stops(self):
        for profile, resources, message in (([{'name': 't', 'role': 'teacher', 'email': 't@x'}], [], '교직원 정보'),
                                            ([{'name': 's', 'role': 'student', 'email': 's1@x'}], [], '학생 정보'),
                                            ([{'name': 's', 'role': 'student', 'email': 's1@x'}], [{'id': 'a'}, {'id': 'b'}], '학생 정보')):
            class Reader:
                session = {'user_id': 'u'}
                def get(self, table, params=None, body=None, profile=profile, resources=resources):
                    if table == 'user_resource': return []
                    if table == 'profiles': return profile
                    if table == 'resource': return resources
                    raise AssertionError('Must stop before personal queries')
            with patch.object(dashboard, 'Reader', Reader):
                with self.assertRaisesRegex(ValueError, message):
                    dashboard.snapshot()

    def test_ambiguous_resource_mapping_stops_before_personal_queries(self):
        class Reader:
            session = {'user_id': 'current-user'}
            def get(self, table, params=None, body=None):
                if table != 'user_resource': raise AssertionError('Must stop before personal queries')
                return [{'resource_id': 'one'}, {'resource_id': 'two'}]
        with patch.object(dashboard, 'Reader', Reader):
            with self.assertRaises(ValueError): dashboard.snapshot()

    def test_week_timetable_keeps_every_day_and_today_uses_it(self):
        class Reader:
            session = {'user_id': 'u'}
            def get(self, table, params=None, body=None):
                if table == 'system_settings': return [{'setting_value': {'year': 2026, 'semester': 2}}]
                if table == 'teacher_timetable':
                    assert 'day_of_week' not in params          # 한 주 전체를 한 번에
                    return [{'day_of_week': 1, 'period': 2, 'subject_name': '정보', 'grade': 1, 'class_label': '3'},
                            {'day_of_week': 3, 'period': 1, 'subject_name': '수학', 'grade': 2, 'class_label': '1'},
                            {'day_of_week': 3, 'period': 9, 'subject_name': '범위 밖', 'grade': 2, 'class_label': '1'}]
                return []
        cells = dashboard.timetable(Reader(), {'id': 'r', 'type': 'teacher'})
        self.assertEqual(cells, [{'day': 1, 'period': 2, 'title': '정보', 'detail': '1-3'},
                                 {'day': 3, 'period': 1, 'title': '수학', 'detail': '2-1'}])
        wednesday = dashboard.datetime(2026, 10, 14, tzinfo=dashboard.KST)
        self.assertEqual(dashboard.today_lessons(cells, wednesday, False),
                         [{'title': '수학 2-1', 'time': '09:00', 'label': '1교시', 'detail': '수업'}])

    def test_month_spreads_multi_day_events_and_marks_closed_days(self):
        queries = []
        class Reader:
            session = {'user_id': 'u'}
            def get(self, table, params=None, body=None):
                queries.append((table, params))
                if table == 'user_resource': return [{'resource_id': 'r'}]
                if table == 'resource': return [{'id': 'r', 'name': '홍길동', 'type': 'teacher'}]
                if table == 'profiles': return [{'name': '홍길동'}]
                if table == 'meeting': return [
                    # 사흘 일정 — 끝이 다음 날 00:00 정각이면 그날은 빼고
                    {'kind': 'schedule', 'starts_at': '2026-10-21T00:00:00+09:00', 'ends_at': '2026-10-24T00:00:00+09:00',
                     'meta': {'title': '수학여행', 'date_only': True}},
                    {'kind': 'schedule', 'starts_at': '2026-10-09T00:00:00+09:00', 'ends_at': '2026-10-09T23:59:59+09:00',
                     'meta': {'title': '한글날', 'date_only': True, 'sbtr_dd_sc_nm': '공휴일'}},
                    {'kind': 'schedule', 'starts_at': '2026-10-10T00:00:00+09:00', 'ends_at': '2026-10-10T23:59:59+09:00',
                     'meta': {'title': '토요휴업일', 'date_only': True, 'sbtr_dd_sc_nm': '휴업일'}},
                    {'kind': 'meeting', 'starts_at': '2026-10-14T06:30:00Z', 'ends_at': '2026-10-14T07:30:00Z',
                     'meta': {'title': '교과협의회', 'assignee': [{'name': '홍길동'}]}},
                    {'kind': 'duty', 'starts_at': '2026-10-15T06:30:00Z', 'ends_at': '2026-10-15T07:30:00Z',
                     'meta': {'title': '남의 당번', 'assignee': '다른 사람'}}]
                return []
        with patch.object(dashboard, 'Reader', Reader), patch.object(dashboard.supa_auth, 'load_session', return_value={'user_id': 'u'}):
            data = dashboard.month(2026, 10)
        self.assertEqual(data['start'], '2026-09-27')                    # 일요일부터
        meeting = next(params for table, params in queries if table == 'meeting')
        self.assertIn(('starts_at', 'lt.2026-11-08T00:00:00+09:00'), meeting)
        self.assertEqual([d for d, rows in data['days'].items() if rows[0]['title'] == '수학여행'],
                         ['2026-10-21', '2026-10-22', '2026-10-23'])
        self.assertEqual(data['days']['2026-10-14'], [{'title': '교과협의회', 'time': '15:30', 'label': '일정', 'kind': 'mine'}])
        self.assertNotIn('2026-10-15', data['days'])
        self.assertNotIn('2026-10-10', data['days'])                     # 매주 토요휴업일은 감춘다
        self.assertEqual(data['closed'], ['2026-10-09'])
