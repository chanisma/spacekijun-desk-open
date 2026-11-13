"""예약 업무 (2026-11-07 요청) — cron 식·쉬운 선택·놓친 예약·칸에 넣기·결과 읽기·알림, 로그인 확인, 데스크 연결.

진짜 에이전트·서버는 쓰지 않는다 — 칸은 가짜(넣은 말에 대화 기록 줄을 써 준다), 시계도 가짜."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명·설정 파일에는 절대 닿지 않는다
import json
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core import agent_cron
from core.agent_cron import Cron, Scheduler, clean_when, describe, next_due, read_turn


class CronTests(unittest.TestCase):
    def test_weekdays_skip_weekend(self):
        friday = datetime(2026, 11, 6, 9, 0)                       # 금요일 9시 → 다음 평일 8시는 월요일
        self.assertEqual(Cron('0 8 * * 1-5').next_after(friday), datetime(2026, 11, 9, 8, 0))

    def test_steps_ranges_lists(self):
        at = datetime(2026, 11, 7, 10, 7)
        self.assertEqual(Cron('*/15 * * * *').next_after(at), datetime(2026, 11, 7, 10, 15))
        self.assertEqual(Cron('5,35 9-10 * * *').next_after(at), datetime(2026, 11, 7, 10, 35))
        self.assertEqual(Cron('0 9 1 * *').next_after(at), datetime(2026, 12, 1, 9, 0))
        self.assertEqual(Cron('0 0 * * 7').next_after(at), datetime(2026, 11, 8, 0, 0))   # 7 = 일요일

    def test_day_and_weekday_is_or(self):
        # 표준 cron — 일과 요일을 둘 다 정하면 둘 중 하나만 맞아도 (13일 또는 금요일)
        self.assertEqual(Cron('0 9 13 * 5').next_after(datetime(2026, 11, 7, 12, 0)), datetime(2026, 11, 13, 9, 0))
        self.assertEqual(Cron('0 9 20 * 1').next_after(datetime(2026, 11, 7, 12, 0)), datetime(2026, 11, 9, 9, 0))

    def test_strictly_after_and_never(self):
        self.assertEqual(Cron('30 8 * * *').next_after(datetime(2026, 11, 7, 8, 30)), datetime(2026, 11, 8, 8, 30))
        self.assertIsNone(Cron('0 0 30 2 *').next_after(datetime(2026, 1, 1)))

    def test_bad_expressions(self):
        for expr in ('0 8 * *', '60 8 * * *', '0 24 * * *', 'a b c d e', '0 8 * * 1-9', '*/0 * * * *'):
            with self.assertRaises(ValueError, msg=expr):
                Cron(expr)


class WhenTests(unittest.TestCase):
    def test_easy_choices(self):
        at = datetime(2026, 11, 7, 12, 0)                          # 토요일 낮
        self.assertEqual(next_due(clean_when({'kind': 'daily', 'time': '8:05'}), at), datetime(2026, 11, 8, 8, 5))
        self.assertEqual(next_due(clean_when({'kind': 'weekdays', 'time': '07:30'}), at), datetime(2026, 11, 9, 7, 30))
        weekly = clean_when({'kind': 'weekly', 'time': '16:00', 'days': [3, 3, 0]})
        self.assertEqual(weekly['days'], [0, 3])
        self.assertEqual(next_due(weekly, at), datetime(2026, 11, 8, 16, 0))
        # 3시간마다 = 0·3·6·9·12·… 시 (cron */3) — 12:00 다음은 12:10
        self.assertEqual(next_due(clean_when({'kind': 'interval', 'hours': 3, 'minute': 10}), at), datetime(2026, 11, 7, 12, 10))
        once = clean_when({'kind': 'once', 'date': '2026-11-07', 'time': '13:00'})
        self.assertEqual(next_due(once, at), datetime(2026, 11, 7, 13, 0))
        self.assertIsNone(next_due(once, datetime(2026, 11, 7, 13, 0)))

    def test_describe(self):
        self.assertEqual(describe(clean_when({'kind': 'weekly', 'time': '09:00', 'days': [1, 3]})), '매주 월수 09:00')
        self.assertEqual(describe(clean_when({'kind': 'cron', 'expr': ' 0  8 * * 1-5 '})), 'cron 0 8 * * 1-5')

    def test_rejects(self):
        for when in (None, {'kind': 'hourly'}, {'kind': 'daily', 'time': '25:00'}, {'kind': 'weekly', 'time': '09:00', 'days': []},
                     {'kind': 'interval', 'hours': 0}, {'kind': 'interval', 'hours': True}, {'kind': 'once', 'time': '09:00'}):
            with self.assertRaises(ValueError, msg=when):
                clean_when(when)

    def test_preview(self):
        rows = agent_cron.preview({'kind': 'weekdays', 'time': '08:00'}, now=datetime(2026, 11, 6, 9, 0))
        self.assertEqual(rows, ['2026-11-09 08:00', '2026-11-10 08:00', '2026-11-11 08:00'])


def rows_text(*rows):
    return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)


class ReadTurnTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.path = Path(room.name) / 'c.jsonl'

    def test_result_is_text_after_last_tool(self):
        earlier = rows_text({'type': 'user', 'message': {'content': '전에 한 말 [예약 업무 «x»] #a'}})
        self.path.write_text(earlier + rows_text(
            {'type': 'user', 'message': {'content': [{'type': 'text', 'text': '[예약 업무 «x»] #b\n할 일'}]}},
            {'type': 'assistant', 'message': {'stop_reason': 'tool_use', 'content': [{'type': 'text', 'text': '찾아볼게요'},
                                                                                     {'type': 'tool_use', 'id': 't1'}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 't1', 'content': 'ok'}]}},
            {'type': 'assistant', 'message': {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '정리: 두 건'}]}},
            {'type': 'system', 'subtype': 'turn_duration'}), encoding='utf-8')
        offset = len(earlier.encode('utf-8'))
        turn = read_turn(self.path, offset, '[예약 업무 «x»] #b')
        self.assertEqual(turn, {'seen': True, 'done': True, 'stopped': False, 'result': '정리: 두 건'})
        self.assertFalse(read_turn(self.path, offset, '[예약 업무 «x»] #a')['seen'])     # offset 앞의 말은 보지 않는다

    def test_not_done_while_tools_run_and_interrupt(self):
        self.path.write_text(rows_text(
            {'type': 'user', 'message': {'content': 'M 할 일'}},
            {'type': 'assistant', 'message': {'stop_reason': 'tool_use', 'content': [{'type': 'tool_use', 'id': 't1'}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 't1', 'content': 'ok'}]}}),
            encoding='utf-8')
        self.assertFalse(read_turn(self.path, 0, 'M')['done'])
        with open(self.path, 'a', encoding='utf-8') as handle:
            handle.write(rows_text({'type': 'user', 'message': {'content': [{'type': 'text', 'text': '[Request interrupted by user]'}]}}))
        self.assertTrue(read_turn(self.path, 0, 'M')['stopped'])

    def test_queued_message_counts_as_seen(self):
        self.path.write_text(rows_text(
            {'type': 'attachment', 'attachment': {'type': 'queued_command', 'prompt': 'M 할 일'}},
            {'type': 'assistant', 'message': {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '끝'}]}}),
            encoding='utf-8')
        self.assertEqual(read_turn(self.path, 0, 'M')['result'], '끝')


class FakeSession:
    """넣은 말에 대해 일하는 척하고 대화 기록 줄을 쓴다. state 로 working·choice 를 흉내 낸다."""
    tool = 'claude'

    def __init__(self, name, path: Path, reply='결과 글', tool_turns=0):
        self.name, self.title, self.folder, self.path, self.reply = name, '', 'C:/work', path, reply
        self.closed, self.drafting, self.state, self.submitted, self.tool_turns = False, 0, 'idle', [], tool_turns
        self.path.write_text('', encoding='utf-8')

    def agent_running(self):
        return not self.closed

    def quiet_for(self):
        return 10

    def asking(self):
        return self.state == 'waiting-for-user-choice'

    def current_conversation(self):
        return 'conv'

    def submit(self, text):
        self.submitted.append(text)
        rows = [{'type': 'user', 'message': {'content': text}}]
        rows += [{'type': 'assistant', 'message': {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': self.reply}]}},
                 {'type': 'system', 'subtype': 'turn_duration'}]
        with open(self.path, 'a', encoding='utf-8') as handle:
            handle.write(rows_text(*rows))


class Clock:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at


LOGGED_IN = {'tool': 'claude', 'installed': True, 'logged_in': True, 'detail': ''}


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.room = Path(room.name)
        self.clock = Clock(datetime(2026, 11, 9, 7, 0))
        self.sessions, self.delivered, self.opened = {}, [], []
        for target, value in ((agent_cron, 'DONE_QUIET'), (agent_cron, 'IDLE_QUIET')):
            patcher = patch.object(target, value, 0)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (('transcript_path', lambda conversation: self.room / 'conv.jsonl'),
                            ('auth_status', lambda tool, fresh=False: LOGGED_IN)):
            patcher = patch.object(agent_cron, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        sleep = patch('core.agent_cron.time.sleep', lambda seconds: None)
        sleep.start()
        self.addCleanup(sleep.stop)
        self.cron = Scheduler(self.room, find=self.sessions.get, open=self.open, restart=lambda s: s,
                              status=lambda s: s.state if not s.closed else 'ended', deliver=self.deliver, clock=self.clock)

    def open(self, target):
        session = FakeSession(target['name'], self.room / 'conv.jsonl', reply='새 칸에서 한 결과')
        self.sessions[target['name']] = session
        self.opened.append(target)
        return session

    def deliver(self, row, agent_name, result, run):
        self.delivered.append((row['title'], agent_name, result, dict(run)))

    def add(self, when, name='claude-1', title='아침 공문'):
        self.clock.at, made = self.clock.at, None
        made = self.cron.add({'title': title, 'prompt': '오늘 공문 정리', 'when': clean_when(when), 'on': True,
                              'target': {'name': name, 'tool': 'claude', 'folder': str(self.room), 'skip': False, 'title': ''}})
        return made

    def settle(self):
        deadline = time.monotonic() + 5
        while self.cron._running and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.cron._running)

    def test_runs_when_due_into_open_pane(self):
        session = self.sessions['claude-1'] = FakeSession('claude-1', self.room / 'conv.jsonl')
        row = self.add({'kind': 'daily', 'time': '08:00'})
        self.assertEqual(self.cron.tick(), [])                     # 아직 7시
        self.clock.at = datetime(2026, 11, 9, 8, 0, 20)
        self.assertEqual(self.cron.tick(), [row['id']])
        self.settle()
        self.assertEqual(len(session.submitted), 1)
        self.assertIn('[예약 업무 «아침 공문»]', session.submitted[0])
        self.assertIn('오늘 공문 정리', session.submitted[0])
        title, agent_name, result, run = self.delivered[-1]
        self.assertEqual((title, agent_name, result, run['status'], run['late']), ('아침 공문', 'claude-1', '결과 글', 'done', False))
        self.assertEqual(self.cron.list()[0]['last']['status'], 'done')
        self.assertEqual(self.cron.list()[0]['next'], '2026-11-10T08:00:00')
        self.assertEqual(self.cron.runs()[0]['result'], '결과 글')
        self.assertEqual(self.cron.tick(), [])                     # 같은 시각을 두 번 돌리지 않는다

    def test_missed_runs_once_late(self):
        self.sessions['claude-1'] = FakeSession('claude-1', self.room / 'conv.jsonl')
        row = self.add({'kind': 'daily', 'time': '08:00'})
        self.clock.at = datetime(2026, 11, 12, 9, 30)              # PC 가 사흘 꺼져 있었다 — 08:00 를 세 번 놓쳤다
        self.assertEqual(self.cron.tick(), [row['id']])
        self.settle()
        self.assertEqual(self.cron.tick(), [])
        self.assertEqual(len(self.delivered), 1)
        self.assertTrue(self.delivered[0][3]['late'])
        self.assertEqual(self.cron.list()[0]['next'], '2026-11-13T08:00:00')

    def test_opens_pane_when_missing_and_once_turns_off(self):
        row = self.add({'kind': 'once', 'date': '2026-11-09', 'time': '07:30'})
        self.clock.at = datetime(2026, 11, 9, 7, 30)
        self.cron.tick()
        self.settle()
        self.assertEqual([t['name'] for t in self.opened], ['claude-1'])
        self.assertEqual(self.delivered[-1][2], '새 칸에서 한 결과')
        listed = self.cron.list()[0]
        self.assertFalse(listed['on'])
        self.assertEqual(listed['next'], '')
        with self.assertRaises(ValueError):                         # 지난 한 번짜리는 다시 켤 수 없다
            self.cron.set_on(row['id'], True)

    def test_waits_while_working_and_tells_phone_about_choice(self):
        session = self.sessions['claude-1'] = FakeSession('claude-1', self.room / 'conv.jsonl')
        session.state = 'waiting-for-user-choice'
        self.add({'kind': 'daily', 'time': '08:00'})
        self.clock.at = datetime(2026, 11, 9, 8, 0)
        calls = {'n': 0}

        def status(s):
            calls['n'] += 1
            if calls['n'] > 3:
                s.state = 'idle'                                    # 사람이 골랐다
            return s.state
        self.cron.status = status
        self.cron.tick()
        self.settle()
        statuses = [run['status'] for *_, run in self.delivered]
        self.assertEqual(statuses, ['choice', 'done'])
        self.assertEqual(len(session.submitted), 1)

    def test_busy_too_long_is_skipped(self):
        session = self.sessions['claude-1'] = FakeSession('claude-1', self.room / 'conv.jsonl')
        session.state = 'working'
        self.add({'kind': 'daily', 'time': '08:00'})
        self.clock.at = datetime(2026, 11, 9, 8, 0)
        with patch.object(agent_cron, 'BUSY_WAIT', 0):
            self.cron.tick()
            self.settle()
        self.assertEqual(session.submitted, [])
        self.assertEqual(self.delivered[-1][3]['status'], 'busy')

    def test_login_needed(self):
        session = self.sessions['claude-1'] = FakeSession('claude-1', self.room / 'conv.jsonl')
        self.add({'kind': 'daily', 'time': '08:00'})
        self.clock.at = datetime(2026, 11, 9, 8, 0)
        with patch.object(agent_cron, 'auth_status', lambda tool, fresh=False: {**LOGGED_IN, 'logged_in': False}):
            self.cron.tick()
            self.settle()
        self.assertEqual(session.submitted, [])
        self.assertEqual(self.delivered[-1][3]['status'], 'login')

    def test_turning_on_again_does_not_replay_missed(self):
        self.sessions['claude-1'] = FakeSession('claude-1', self.room / 'conv.jsonl')
        row = self.add({'kind': 'daily', 'time': '08:00'})
        self.cron.set_on(row['id'], False)
        self.clock.at = datetime(2026, 11, 11, 12, 0)
        self.assertEqual(self.cron.tick(), [])                     # 꺼 둔 동안
        self.cron.set_on(row['id'], True)
        self.assertEqual(self.cron.tick(), [])                     # 꺼 둔 동안의 시각은 놓친 것으로 치지 않는다

    def test_edit_limits_and_remove(self):
        row = self.add({'kind': 'daily', 'time': '08:00'})
        edited = self.cron.edit(row['id'], {**{k: row[k] for k in ('title', 'prompt', 'target', 'on')},
                                            'when': clean_when({'kind': 'weekdays', 'time': '09:00'})})
        self.assertEqual(edited['when']['kind'], 'weekdays')
        with patch.object(agent_cron, 'LIMIT', 1), self.assertRaises(ValueError):
            self.add({'kind': 'daily', 'time': '10:00'}, title='둘째')
        with self.assertRaises(ValueError):
            agent_cron.clean_schedule({'title': 't', 'prompt': 'p', 'when': {'kind': 'daily', 'time': '08:00'}},
                                      {'name': 'codex-1', 'tool': 'codex', 'folder': 'x', 'skip': False, 'title': ''})
        self.cron.remove(row['id'])
        self.assertEqual(self.cron.list(), [])


class RelayTests(unittest.TestCase):
    """에이전트가 대화로 예약을 다룬다 — 만들기·고치기·켜기는 승인, 끄기·지우기는 묻지 않음."""
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.clock = Clock(datetime(2026, 11, 9, 7, 0))
        self.cron = Scheduler(Path(room.name), *([None] * 5), clock=self.clock)
        self.answer, self.asked, self.pendings = True, [], []
        targets = {'claude-1': {'name': 'claude-1', 'tool': 'claude', 'folder': 'C:/w', 'skip': True, 'title': '비서'}}

        def target_of(name):
            if name not in targets:
                raise ValueError(f'no open agent named {name!r}')
            return targets[name]

        def approve(agent, proposal):
            self.asked.append((agent, proposal))
            return self.answer
        self.relay = agent_cron.Relay(self.cron, target_of, approve, pending=lambda agent, row: self.pendings.append(row['id']))

    def job(self, **extra):
        return {'title': '아침 공문', 'prompt': '오늘 마감 공문 정리', 'when': {'kind': 'weekdays', 'time': '08:00'}, 'agent': 'claude-1', **extra}

    def test_approved_job_is_on_and_marked(self):
        text = self.relay.save('비서', self.job())
        self.assertTrue(text.startswith('created '), text)
        row = self.cron.store.load()[0]
        self.assertTrue(row['on'])
        self.assertFalse(row['pending'])
        self.assertEqual(row['by'], '비서')
        agent, proposal = self.asked[0]
        self.assertEqual((agent, proposal['target'], proposal['describe'], proposal['skip'], proposal['edit']),
                         ('비서', '비서', '평일 08:00', True, False))
        self.assertEqual(proposal['next'][0], '2026-11-09 08:00')
        self.assertIn('	on	아침 공문	평일 08:00 [0 8 * * 1-5]	claude-1', self.relay.list_text())

    def test_no_answer_saves_pending_and_never_runs(self):
        self.answer = None
        text = self.relay.save('비서', self.job())
        self.assertIn('WAITING FOR APPROVAL', text)
        row = self.cron.store.load()[0]
        self.assertEqual((row['on'], row['pending']), (False, True))
        self.assertEqual(self.pendings, [row['id']])
        self.assertIn('pending-approval', self.relay.list_text())
        self.clock.at = datetime(2026, 11, 9, 8, 0)
        self.assertEqual(self.cron.tick(), [])
        with self.assertRaises(agent_cron.RelayError):
            self.relay.run(row['id'])
        self.cron.set_on(row['id'], True)                          # 사람이 예약 탭에서 켰다 = 승인
        self.assertFalse(self.cron.store.load()[0]['pending'])

    def test_refused_saves_nothing(self):
        self.answer = False
        self.assertTrue(self.relay.save('비서', self.job()).startswith('refused'))
        self.assertEqual(self.cron.store.load(), [])

    def test_cron_shorthand_partial_edit_and_errors(self):
        created = self.relay.save('비서', self.job(cron='30 7 * * 1-5', when=None))
        job_id = created.split()[1].rstrip(':')
        self.relay.save('비서', {'id': job_id, 'when': {'kind': 'daily', 'time': '09:00'}})
        edited = next(r for r in self.cron.store.load() if r['id'] == job_id)
        self.assertEqual((edited['prompt'], edited['when']['kind']), ('오늘 마감 공문 정리', 'daily'))
        self.assertTrue(self.asked[-1][1]['edit'])
        self.assertEqual(self.asked[-1][1]['before']['describe'], 'cron 30 7 * * 1-5')
        for bad in (self.job(agent='codex-9'), self.job(when={'kind': 'daily', 'time': '99:00'}), self.job(title=''),
                    self.job(when={'kind': 'once', 'date': '2026-01-01', 'time': '08:00'})):
            with self.assertRaises(agent_cron.RelayError, msg=bad) as caught:
                self.relay.save('비서', bad)
            self.assertEqual(caught.exception.code, 400)
        with self.assertRaises(agent_cron.RelayError):
            self.relay.save('비서', {'id': 'nope', 'title': 'x'})

    def test_off_and_delete_without_asking_on_asks(self):
        job_id = self.relay.save('비서', self.job()).split()[1].rstrip(':')
        asked = len(self.asked)
        self.assertIn('turned off', self.relay.set_on('비서', job_id, False))
        self.assertEqual(len(self.asked), asked)
        self.answer = None
        self.assertIn('not turned on', self.relay.set_on('비서', job_id, True))
        self.assertTrue(self.asked[-1][1]['turn_on'])
        self.answer = True
        self.assertIn('turned on', self.relay.set_on('비서', job_id, True))
        self.assertIn('deleted', self.relay.remove(job_id))
        self.assertEqual(len(self.asked), asked + 2)


class AuthTests(unittest.TestCase):
    def setUp(self):
        agent_cron.forget_auth()
        self.addCleanup(agent_cron.forget_auth)

    def probe(self, tool, stdout, code=0):
        done = subprocess.CompletedProcess([], code, stdout, '')
        with patch.object(agent_cron.agent, 'find', lambda name: 'C:/bin/' + name), \
             patch.object(agent_cron.subprocess, 'run', lambda *a, **k: done):
            return agent_cron.auth_status(tool, fresh=True)

    def test_claude_json(self):
        self.assertTrue(self.probe('claude', json.dumps({'loggedIn': True, 'email': 'a@b'}))['logged_in'])
        self.assertFalse(self.probe('claude', json.dumps({'loggedIn': False}), 1)['logged_in'])
        self.assertIsNone(self.probe('claude', 'error: unknown command auth')['logged_in'])     # 옛 판 — 막지 않는다

    def test_codex_text(self):
        self.assertTrue(self.probe('codex', 'Logged in using ChatGPT')['logged_in'])
        self.assertFalse(self.probe('codex', 'Not logged in', 1)['logged_in'])

    def test_not_installed(self):
        with patch.object(agent_cron.agent, 'find', lambda name: None):
            self.assertFalse(agent_cron.auth_status('claude', fresh=True)['installed'])

    def test_login_command(self):
        with patch.object(agent_cron.agent, 'find', lambda name: 'C:/bin/' + name):
            self.assertEqual(agent_cron.login_command('claude'), ['C:/bin/claude', 'auth', 'login', '--claudeai'])
            self.assertEqual(agent_cron.login_command('codex'), ['C:/bin/codex', 'login'])


class DesktopCronTests(unittest.TestCase):
    def setUp(self):
        import desktop
        self.desktop = desktop
        self.api = desktop.DesktopAPI()

    def test_student_edition_has_login_but_no_cron(self):
        with patch.object(self.desktop.edition, 'STUDENT', True):
            for action in ('term_cron_list', 'term_cron_save', 'term_cron_run', 'term_cron_preview'):
                self.assertIn('교직원판에서만', self.api.call(action, {})['error'], action)
            with patch.object(agent_cron, 'auth_status', lambda tool, fresh=False: dict(LOGGED_IN)):
                answer = self.api.call('term_auth', {'tool': 'claude'})
        self.assertTrue(answer['ok'], answer)
        self.assertTrue(answer['data']['logged_in'])
        self.assertFalse(answer['data']['login_open'])

    def test_deliver_sends_push_and_phone(self):
        sent, posted = [], []
        row = {'id': 's1', 'title': '아침', 'prompt': '할 일'}
        with patch('core.notify.send', lambda *a, **k: sent.append((a, k))), \
             patch.object(self.api, '_cron_phone_post', lambda *a: posted.append(a)):
            self.api._cron_deliver(row, 'claude-1', '정리 결과 ' * 50, {'id': 'r1', 'status': 'done', 'late': True})
            self.api._cron_deliver(row, 'claude-1', '골라 주세요', {'id': 'r2', 'status': 'choice', 'late': False})
        self.assertEqual(sent[0][0][0], '⏰ 예약 «아침» 완료 · 늦게 실행')
        self.assertLessEqual(len(sent[0][0][1]), agent_cron.SUMMARY_LIMIT)
        self.assertEqual(sent[0][1]['ntype'], 'desk_agent')
        self.assertEqual(sent[0][1]['meta']['kind'], 'cron')
        self.assertEqual(len(posted), 1)                            # «선택 필요»는 알림만, 휴대폰 대화에는 결과만
        self.assertEqual(sent[1][0][0], '⏰ 예약 «아침» 선택 필요')

    def test_approval_plumbing(self):
        self.assertIsNone(self.api._cron_ask('claude-1', {'title': 't'}))     # 창이 없으면 «답 없음» → 승인 대기
        self.assertIn('이미 끝난', self.api.call('term_cron_answer', {'request': 'x', 'allow': True})['error'])
        waiting = {'event': threading.Event(), 'answer': None}
        self.api._cron_asks['r1'] = waiting
        self.assertTrue(self.api.call('term_cron_answer', {'request': 'r1', 'allow': True})['ok'])
        self.assertTrue(waiting['event'].is_set() and waiting['answer'] is True)
        self.api._cron_asks['r2'] = second = {'event': threading.Event(), 'answer': None}
        self.api._cron_ask_cancel()                                            # 창을 닫으면 답 없음
        self.assertTrue(second['event'].is_set() and second['answer'] is None)
        with patch.object(self.api, '_cron_find', lambda name: None):
            with self.assertRaises(ValueError):
                self.api._cron_relay_target('claude-1')

    def test_save_needs_open_claude_pane(self):
        with patch.object(self.api, '_cron_scheduler', lambda: Scheduler(Path(tempfile.mkdtemp()), *([None] * 5))), \
             patch.object(self.api, '_cron_find', lambda name: None):
            answer = self.api.call('term_cron_save', {'title': 't', 'prompt': 'p', 'agent': 'claude-9',
                                                      'when': {'kind': 'daily', 'time': '08:00'}})
        self.assertFalse(answer['ok'])
        self.assertIn('에이전트를 골라', answer['error'])


if __name__ == '__main__':
    unittest.main()
