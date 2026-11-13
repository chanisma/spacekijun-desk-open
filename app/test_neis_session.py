"""NEIS 세션 — 요청을 넣는 쪽과 화면을 누르는 쪽 사이의 규약. 브라우저 없이 돈다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명 파일에는 절대 닿지 않는다
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.neis_session import Session

INDEX = {'version': 2, 'at': time.time(), 'present': ['교과담임', '동아리담임'], 'tabs': {
    '교과담임': {'groups': [{'group': '학적', 'screens': ['출결관리']},
                            {'group': '교육과정', 'screens': ['시간표관리']}]},
    '동아리담임': {'groups': [{'group': '학생생활', 'screens': ['동아리활동관리']}]},
}}


class QueueContractTests(unittest.TestCase):
    def setUp(self):
        self.session = Session('teacher')

    def test_work_is_refused_until_the_window_is_open(self):
        with self.assertRaises(ValueError):
            self.session.enqueue('assist', {'text': '출결'})

    def test_unknown_ticket_is_reported_not_guessed(self):
        self.assertEqual(self.session.result('job-없음'), {'state': 'unknown'})

    def test_tickets_are_distinct_per_request(self):
        self.session.open.set()
        self.assertNotEqual(self.session.enqueue('assist', {'text': 'a'}),
                            self.session.enqueue('assist', {'text': 'b'}))

    def test_finished_tickets_are_trimmed_but_live_ones_survive(self):
        """창을 오래 켜 두면 표가 쌓인다. 끝난 것만 버려야 한다."""
        self.session.open.set()
        live = self.session.enqueue('assist', {'text': 'keep'})
        for index in range(80):
            ticket = self.session.enqueue('assist', {'text': str(index)})
            self.session._tickets[ticket]['done'].set()
        self.assertNotEqual(self.session.result(live)['state'], 'unknown')
        self.assertLessEqual(len(self.session._tickets), 81)


class PumpTests(unittest.TestCase):
    def setUp(self):
        self.session = Session('teacher')
        self.page = MagicMock()
        self.stop = threading.Event()
        self.page.is_closed.side_effect = lambda: self.stop.is_set()

    def start(self, run_job, progress=None):
        patcher = patch.object(Session, 'run_job', side_effect=run_job)
        patcher.start()
        self.addCleanup(patcher.stop)
        worker = threading.Thread(target=self.session.pump,
                                  args=(self.page, progress, self.stop.is_set), daemon=True)
        worker.start()
        self.addCleanup(lambda: (self.stop.set(), worker.join(timeout=3)))
        self.assertTrue(self.session.open.wait(2))
        return worker

    def wait_for(self, check, limit=60):
        for _ in range(limit):
            value = check()
            if value:
                return value
            time.sleep(0.05)
        return None

    def test_idle_loop_polls_the_page_at_the_shared_interval(self):
        self.start(lambda *_: {'ok': True})
        self.wait_for(lambda: self.page.wait_for_timeout.called)
        self.page.wait_for_timeout.assert_called_with(200)

    def test_a_request_is_answered_and_progress_is_visible_while_running(self):
        hold = threading.Event()

        def slow(_page, _job, say):
            say('메뉴 목록을 수집하는 중')
            hold.wait(3)
            return {'ok': True, 'reply': '열었습니다'}

        self.start(slow)
        ticket = self.session.enqueue('assist', {'text': '출결'})
        pending = self.wait_for(lambda: self.session.result(ticket)
                                if self.session.result(ticket)['progress'] else None)
        self.assertEqual(pending['state'], 'pending')
        self.assertEqual(pending['progress'], ['메뉴 목록을 수집하는 중'])
        hold.set()
        answer = self.wait_for(lambda: self.session.result(ticket)
                               if self.session.result(ticket)['state'] != 'pending' else None)
        self.assertEqual(answer['state'], 'done')
        self.assertEqual(answer['data']['reply'], '열었습니다')

    def test_progress_also_reaches_the_activity_log(self):
        seen = []
        self.start(lambda _p, _j, say: (say('출결관리 진입'), {'ok': True})[1], progress=seen.append)
        ticket = self.session.enqueue('assist', {'text': '출결'})
        self.wait_for(lambda: self.session.result(ticket)['state'] == 'done')
        self.assertEqual(seen, ['출결관리 진입'])

    def test_failure_becomes_a_plain_message(self):
        self.start(MagicMock(side_effect=RuntimeError('메뉴를 찾지 못했습니다')))
        with self.assertRaises(RuntimeError) as caught:
            self.session.submit('assist', {'text': '없는 업무'}, timeout=3)
        self.assertIn('메뉴를 찾지 못했습니다', str(caught.exception))

    def test_closing_the_window_releases_everything_that_was_waiting(self):
        """창이 닫히면 기다리던 요청은 즉시 실패해야 한다 — 무한정 매달리면 안 된다."""
        self.start(lambda *_: (self.stop.set(), {'ok': True})[1])
        self.session.submit('assist', {'text': '출결'}, timeout=3)
        self.wait_for(lambda: not self.session.open.is_set())
        with self.assertRaises(ValueError):
            self.session.enqueue('assist', {'text': '출결'})

    def test_slow_work_times_out_instead_of_hanging_the_caller(self):
        self.start(lambda *_: time.sleep(2) or {'ok': True})
        with self.assertRaises(RuntimeError):
            self.session.submit('assist', {'text': '출결'}, timeout=0.3)


class RunJobTests(unittest.TestCase):
    def setUp(self):
        self.session = Session('teacher')
        self.page = MagicMock()
        self.said = []

    def do(self, kind, payload):
        return self.session.run_job(self.page, {'kind': kind, 'payload': payload}, self.said.append)

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            self.do('삭제', {})

    def test_blank_text_is_refused_before_touching_the_browser(self):
        with self.assertRaises(ValueError):
            self.do('assist', {'text': '   '})
        self.page.evaluate.assert_not_called()

    def test_menu_job_reports_how_many_screens_it_found(self):
        with patch('core.neis_menu.build', return_value=INDEX),              patch('core.neis_roles.rows', return_value=[]):
            self.assertEqual(self.do('menu', {}), {'screens': 3})

    def test_pick_job_selects_the_named_class(self):
        row = {'text': '1학년 7(인공지능 기초)', 'grade': '1', 'room': '7', 'subject': '인공지능 기초'}
        with patch('core.neis_actions.click_row', return_value={'picked': row, 'rows': [row]}):
            answer = self.do('pick', {'row': row['text']})
        self.assertTrue(answer['ok'])
        self.assertIn('1학년 7(인공지능 기초)', answer['reply'])

    def test_unfindable_screen_comes_back_with_candidates(self):
        plan = {'screen': None, 'tab': None, 'group': None, 'subject': '', 'grade': '', 'room': '',
                'reply': '어떤 화면인지 찾지 못했습니다.', 'candidates': ['출결관리'], 'source': 'none'}
        with patch('core.neis_menu.load', return_value=INDEX), \
             patch('core.neis_assist.interpret', return_value=plan):
            answer = self.do('assist', {'text': '뭔가'})
        self.assertFalse(answer['ok'])
        self.assertEqual(answer['options'], ['출결관리'])
        self.assertEqual(answer['option_kind'], 'screen')

    def plan(self, **extra):
        return {'screen': '출결관리', 'tab': '교과담임', 'group': '학적', 'subject': '인공지능 기초',
                'grade': '', 'room': '', 'date': '', 'reply': '', 'candidates': [],
                'source': 'model', 'chain': ['출결관리'], **extra}

    def open_ok(self, screen):
        """메뉴 검색으로 그 화면이 열린 상황."""
        return patch('core.neis_nav.open_by_search', return_value=screen)

    def test_navigation_goes_through_menu_search(self):
        """메가메뉴를 단계별로 누르지 않는다 — 검색이 계정 차이에 강하다."""
        done = {'searched': True, 'picked': None, 'matches': [], 'rows': [],
                'dated': {'set': [], 'failed': [], 'boxes': 0}}
        with patch('core.neis_menu.load', return_value=INDEX),              patch('core.neis_assist.interpret', return_value=self.plan()),              self.open_ok('출결관리') as opened,              patch('core.neis_nav.auth_required', return_value=False),              patch('core.neis_actions.finish', return_value=done):
            answer = self.do('assist', {'text': '출결'})
        self.assertTrue(answer['ok'])
        self.assertEqual(opened.call_args.args[1], '출결관리')
        self.assertEqual(opened.call_args.args[2], '교과담임 > 학적 > 출결관리')

    def test_a_screen_only_a_department_head_has_is_refused(self):
        """부서장 메뉴는 그 부서장에게만 열린다. 데려가려 하면 안 된다."""
        plan = self.plan(tab='부서장(나이스부)', group='학적')
        with patch('core.neis_menu.load', return_value=INDEX),              patch('core.neis_assist.interpret', return_value=plan),              patch('core.neis_nav.open_by_search') as opened:
            answer = self.do('assist', {'text': '출결'})
        opened.assert_not_called()
        self.assertFalse(answer['ok'])
        self.assertIn('부서장(나이스부)', answer['reply'])

    def test_a_screen_that_did_not_open_is_reported(self):
        with patch('core.neis_menu.load', return_value=INDEX),              patch('core.neis_assist.interpret', return_value=self.plan()),              self.open_ok('다른화면'):
            answer = self.do('assist', {'text': '출결'})
        self.assertFalse(answer['ok'])
        self.assertIn('다른화면', answer['reply'])

    def test_an_inner_tab_named_in_the_request_is_opened(self):
        """`동아리활동관리` 한 화면 안에 부서만들기·부서배정 …이 들어 있다."""
        done = {'searched': True, 'picked': None, 'matches': [], 'rows': [],
                'dated': {'set': [], 'failed': [], 'boxes': 0}}
        plan = self.plan(screen='동아리활동관리', tab='동아리담임', group='학생생활',
                         chain=['창의적체험활동', '동아리활동관리'])
        with patch('core.neis_menu.load', return_value=INDEX), \
             patch('core.neis_assist.interpret', return_value=plan), \
             patch('core.neis_nav.open_by_search', return_value='동아리활동관리'), \
             patch('core.neis_nav.auth_required', return_value=False), \
             patch('core.neis_glossary.inner_tabs', return_value=('부서만들기', '부서배정')), \
             patch('core.neis_actions.click_tab', return_value={'clicked': True, 'why': ''}) as tab, \
             patch('core.neis_actions.finish', return_value=done):
            answer = self.do('assist', {'text': '동아리 부서배정 해야 해'})
        tab.assert_called_once()
        self.assertEqual(tab.call_args.args[1], '부서배정')
        self.assertEqual(answer['inner_tab'], '부서배정')
        self.assertIn('부서배정 탭을 열었습니다', answer['reply'])

    def test_an_inner_tab_the_account_cannot_use_is_reported(self):
        done = {'searched': True, 'picked': None, 'matches': [], 'rows': [],
                'dated': {'set': [], 'failed': [], 'boxes': 0}}
        plan = self.plan(screen='동아리활동관리', tab='동아리담임', group='학생생활',
                         chain=['창의적체험활동', '동아리활동관리'])
        with patch('core.neis_menu.load', return_value=INDEX), \
             patch('core.neis_assist.interpret', return_value=plan), \
             patch('core.neis_nav.open_by_search', return_value='동아리활동관리'), \
             patch('core.neis_nav.auth_required', return_value=False), \
             patch('core.neis_glossary.inner_tabs', return_value=('부서만들기',)), \
             patch('core.neis_actions.click_tab',
                   return_value={'clicked': False, 'why': '이 계정에서는 쓸 수 없는 탭입니다'}), \
             patch('core.neis_actions.finish', return_value=done):
            answer = self.do('assist', {'text': '부서만들기 해야 해'})
        self.assertEqual(answer['inner_tab'], '')
        self.assertIn('열지 못했습니다', answer['reply'])

    def test_no_inner_tab_is_touched_when_none_was_named(self):
        done = {'searched': True, 'picked': None, 'matches': [], 'rows': [],
                'dated': {'set': [], 'failed': [], 'boxes': 0}}
        with patch('core.neis_menu.load', return_value=INDEX), \
             patch('core.neis_assist.interpret', return_value=self.plan()), \
             patch('core.neis_nav.open_by_search', return_value='출결관리'), \
             patch('core.neis_nav.auth_required', return_value=False), \
             patch('core.neis_glossary.inner_tabs', return_value=('가', '나')), \
             patch('core.neis_actions.click_tab') as tab, \
             patch('core.neis_actions.finish', return_value=done):
            self.do('assist', {'text': '출결'})
        tab.assert_not_called()

    def test_a_screen_needing_second_factor_auth_says_so(self):
        """세특 화면처럼 2차 인증을 요구하는 곳이 있다. 대신 인증할 수는 없다."""
        with patch('core.neis_menu.load', return_value=INDEX),              patch('core.neis_assist.interpret', return_value=self.plan()),              self.open_ok('출결관리'),              patch('core.neis_nav.auth_required', return_value=True),              patch('core.neis_actions.finish') as finish:
            answer = self.do('assist', {'text': '출결'})
        finish.assert_not_called()          # 인증 전에는 조회도 하지 않는다
        self.assertTrue(answer['ok'])
        self.assertIn('2차 인증', answer['reply'])

    def test_a_stale_index_is_rebuilt_before_interpreting(self):
        with patch('core.neis_menu.load', return_value=None), \
             patch('core.neis_menu.build', return_value=INDEX) as build, \
             patch('core.neis_assist.interpret', return_value=self.plan()), \
             patch('core.neis_nav.open_by_search', return_value='출결관리'),              patch('core.neis_nav.auth_required', return_value=False), \
             patch('core.neis_actions.finish',
                   return_value={'searched': True, 'picked': None, 'matches': [], 'rows': [],
                               'dated': {'set': [], 'failed': [], 'boxes': 0}}):
            self.do('assist', {'text': '출결'})
        build.assert_called_once()
        self.assertIn('메뉴 목록을 수집하는 중', self.said)

    def test_a_fresh_index_is_reused(self):
        with patch('core.neis_menu.load', return_value=INDEX), \
             patch('core.neis_menu.build') as build, \
             patch('core.neis_assist.interpret', return_value=self.plan()), \
             patch('core.neis_nav.open_by_search', return_value='출결관리'),              patch('core.neis_nav.auth_required', return_value=False), \
             patch('core.neis_actions.finish',
                   return_value={'searched': True, 'picked': None, 'matches': [], 'rows': [],
                               'dated': {'set': [], 'failed': [], 'boxes': 0}}):
            self.do('assist', {'text': '출결'})
        build.assert_not_called()


if __name__ == '__main__':
    unittest.main()


class MissingRoleNoteTests(unittest.TestCase):
    """교과담임 계정에서 학급담임 메뉴를 말하면, 열기 전에 그렇다고 말해 준다.

    2026-09-11 사용자 보고: 담임 출결을 찾았더니 들어갈 수도 없는 메뉴 이름을 답으로 냈다.
    """

    def setUp(self):
        self.session = Session('teacher')

    def note(self, text):
        return self.session._missing_role_note(text, INDEX)

    def test_a_homeroom_only_screen_is_pointed_out(self):
        note = self.note('행동특성및종합의견 써야 해')
        self.assertIn('행동특성및종합의견', note)
        self.assertIn('학급담임', note)

    def test_an_inner_tab_says_which_screen_holds_it(self):
        note = self.note('일일출결관리 해야 해')
        self.assertIn('출결관리 화면 안에 있는 탭', note)
        self.assertIn('학급담임', note)

    def test_nothing_is_said_for_screens_this_account_has(self):
        self.assertEqual(self.note('인공지능 기초 과목 출결을 해야해'), '')
        self.assertEqual(self.note('동아리활동 출결관리'), '')


class DateAndMissingClassTests(unittest.TestCase):
    """일자를 말하면 일자 칸까지 맞춘다. 못 찾았을 때는 무엇이 없었는지 정확히 말한다."""

    def setUp(self):
        self.session = Session('teacher')
        self.page = MagicMock()

    def plan(self, **extra):
        return {'screen': '과목별출결관리', 'tab': '교과담임', 'group': '학적',
                'subject': '인공지능 기초', 'grade': '', 'room': '', 'date': '',
                'reply': '', 'candidates': [], 'source': 'model',
                'chain': ['출결관리', '과목별출결관리'], **extra}

    def run_with(self, plan, done):
        job = {'kind': 'assist', 'payload': {'text': '출결'}}
        with patch('core.neis_menu.load', return_value=INDEX), \
             patch('core.neis_assist.interpret', return_value=plan), \
             patch('core.neis_nav.open_by_search', return_value='과목별출결관리'), \
             patch('core.neis_nav.auth_required', return_value=False), \
             patch('core.neis_glossary.inner_tabs', return_value=()), \
             patch('core.neis_actions.finish', return_value=done) as finish:
            return self.session.run_job(self.page, job, lambda m: None), finish

    def test_the_date_is_handed_to_the_screen_in_neis_shape(self):
        done = {'searched': True, 'picked': None, 'matches': [], 'rows': [],
                'dated': {'set': [{'value': '2026.09.10.(목)'}], 'failed': [], 'boxes': 1}}
        answer, finish = self.run_with(self.plan(date='2026-09-10'), done)
        self.assertEqual(finish.call_args.args[4], '2026.09.10.')
        self.assertIn('일자는 2026.09.10.(목) 로 맞췄습니다', answer['reply'])
        self.assertEqual(answer['dated'], '2026.09.10.(목)')

    def test_a_screen_without_a_date_field_says_so(self):
        done = {'searched': True, 'picked': None, 'matches': [], 'rows': [],
                'dated': {'set': [], 'failed': [], 'boxes': 0}}
        answer, _ = self.run_with(self.plan(date='2026-09-10'), done)
        self.assertIn('일자 칸이 없어', answer['reply'])

    def test_nothing_is_said_about_dates_when_none_was_spoken(self):
        done = {'searched': True, 'picked': None, 'matches': [], 'rows': [],
                'dated': {'set': [], 'failed': [], 'boxes': 1}}
        answer, _ = self.run_with(self.plan(), done)
        self.assertNotIn('일자', answer['reply'])

    def test_a_missing_class_names_the_grade_and_room_that_were_asked(self):
        """과목은 있는데 그 반이 없을 때 '과목이 없다' 고 하면 오해한다."""
        rows = [{'text': '1학년 5(인공지능 기초)'}, {'text': '1학년 9(인공지능 기초)'}]
        done = {'searched': True, 'picked': None, 'matches': [], 'rows': rows,
                'dated': {'set': [], 'failed': [], 'boxes': 1}}
        answer, _ = self.run_with(self.plan(grade='1', room='7'), done)
        self.assertIn('1학년 7반 인공지능 기초 수업은 그날 목록에 없습니다', answer['reply'])
        # 그날 있던 수업은 눌러 고를 수 있게 그대로 돌려준다.
        self.assertEqual(answer['options'], ['1학년 5(인공지능 기초)', '1학년 9(인공지능 기초)'])


class HandsOffTests(unittest.TestCase):
    """학생별 출결 입력과 저장은 하지 않는다. 그 선을 답장에 분명히 긋는다."""

    def setUp(self):
        self.session = Session('teacher')
        self.page = MagicMock()

    def reply_for(self, text):
        plan = {'screen': '과목별출결관리', 'tab': '교과담임', 'group': '학적',
                'subject': '인공지능 기초', 'grade': '1', 'room': '7', 'date': '2026-09-11',
                'reply': '', 'candidates': [], 'source': 'model',
                'chain': ['출결관리', '과목별출결관리']}
        row = {'text': '1학년 7(인공지능 기초)'}
        done = {'searched': True, 'picked': row, 'matches': [row], 'rows': [row],
                'dated': {'set': [{'value': '2026.09.11.(금)'}], 'failed': [], 'boxes': 1}}
        with patch('core.neis_menu.load', return_value=INDEX), \
             patch('core.neis_assist.interpret', return_value=plan), \
             patch('core.neis_nav.open_by_search', return_value='과목별출결관리'), \
             patch('core.neis_nav.auth_required', return_value=False), \
             patch('core.neis_glossary.inner_tabs', return_value=()), \
             patch('core.neis_actions.finish', return_value=done):
            answer = self.session.run_job(
                self.page, {'kind': 'assist', 'payload': {'text': text}}, lambda m: None)
        return answer['reply']

    def test_asking_to_mark_a_student_absent_gets_an_honest_boundary(self):
        reply = self.reply_for('9월 11일 인공지능 기초 1학년 7반 임하준 학생이 결석했어')
        self.assertIn('일자는 2026.09.11.(금) 로 맞췄습니다', reply)
        self.assertIn('1학년 7(인공지능 기초) 을 선택했습니다', reply)
        self.assertIn('학생별 출결 입력과 저장은 하지 않습니다', reply)

    def test_merely_opening_a_screen_says_nothing_extra(self):
        self.assertNotIn('저장은 하지 않습니다', self.reply_for('인공지능 기초 1학년 7반 출결 보자'))
