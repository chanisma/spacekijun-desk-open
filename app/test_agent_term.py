"""데스크 안 에이전트 터미널 (2026-10-24 요청) — 의사 콘솔 세션, 여러 에이전트·중계(2026-10-25), 데스크 연결.

세션 시험은 진짜 의사 콘솔(pywinpty)에 에이전트 대신 짧은 명령 파일을 돌린다. 창은 띄우지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명·설정 파일에는 절대 닿지 않는다
import os
import tempfile
import threading
import time
import unittest
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import desktop
from core import agent, agent_bridge, agent_term
from desktop import DesktopAPI


def read_until(session, text, cursor=0, epoch=None, limit=10):
    seen, deadline = '', time.monotonic() + limit
    while text not in seen and time.monotonic() < deadline:
        result = session.read(cursor, 0.4, epoch)
        cursor, epoch = result['cursor'], result['epoch']
        seen += result['data']
    return seen, cursor


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.folder = Path(self.room.name) / '수업 자료'
        self.folder.mkdir()
        self.script = Path(self.room.name) / 'run.cmd'
        self.script.write_text('@echo off\r\necho READY\r\n', encoding='oem')

    def open(self):
        session = agent_term.Session('claude', str(self.folder), self.script, 90, 20)
        self.addCleanup(session.close)
        return session

    def test_output_and_input_round_trip_in_the_folder(self):
        session = self.open()
        seen, cursor = read_until(session, 'READY')
        self.assertIn('READY', seen)
        session.write('cd\r')
        seen, _ = read_until(session, '수업 자료', cursor)
        self.assertIn(str(self.folder), seen)            # cmd 는 고른 폴더에서 돈다
        self.assertFalse(session.agent_running())        # 명령 파일이 끝나 cmd 만 남았다

    def test_submit_types_then_enters_and_wraps_when_paste_mode_is_on(self):
        session = self.open()
        _, cursor = read_until(session, 'READY')
        session.submit('echo 한 줄')
        seen, cursor = read_until(session, '한 줄\r\n', cursor)
        self.assertIn('한 줄', seen)
        with patch.object(session._pty, 'write') as typed, patch.object(agent_term, 'ENTER_GAP', 0):
            session._append(agent_term.PASTE_ON)
            session.submit('첫 줄\n둘째 줄')
        self.assertEqual([call.args[0] for call in typed.call_args_list], ['\x1b[200~첫 줄\r둘째 줄\x1b[201~', '\r'])
        session._append('x' + agent_term.PASTE_OFF)
        self.assertFalse(session.paste_mode)

    def test_reading_again_from_zero_replays_and_other_epoch_resets(self):
        session = self.open()
        _, cursor = read_until(session, 'READY')
        again = session.read(0, 0)
        self.assertIn('READY', again['data'])
        self.assertFalse(again['reset'])
        stale = session.read(cursor, 0, epoch=session.epoch + 1000)     # 다시 시작하기 전 세션의 cursor
        self.assertTrue(stale['reset'])
        self.assertIn('READY', stale['data'])
        self.assertTrue(session.read(cursor + 10_000, 0)['reset'])      # 있을 수 없는 cursor

    def test_old_output_is_dropped_beyond_the_backlog(self):
        session = self.open()
        read_until(session, 'READY')
        with patch.object(agent_term, 'BACKLOG', 10):
            session._append('a' * 8)
            session._append('b' * 8)
        result = session.read(0, 0)
        self.assertTrue(result['reset'])
        self.assertEqual(result['data'], 'b' * 8)

    def test_close_ends_the_process_and_refuses_input(self):
        session = self.open()
        read_until(session, 'READY')
        session.close()
        self.assertTrue(session.read(0, 0.1)['closed'])
        with self.assertRaises(RuntimeError):
            session.write('x')
        with self.assertRaises(RuntimeError):
            session.submit('x')
        with self.assertRaises(ValueError):
            agent_term.Session.write(self.open(), 'x' * (agent_term.WRITE_LIMIT + 1))

    def test_size_is_clamped(self):
        session = self.open()
        session.resize(5000, 'many')
        self.assertEqual(session.size, (agent_term.COLS[1], agent_term.ROWS[0]))

    def test_spawn_picks_conpty_falls_back_to_winpty_and_turns_panics_into_errors(self):
        from winpty import Backend, PtyProcess

        class Panic(BaseException):                      # pyo3 의 PanicException 처럼 Exception 이 아니다
            pass
        real = PtyProcess.spawn
        tried = []

        def spawn(*args, backend=None, **kwargs):
            tried.append(backend)
            if backend == Backend.ConPTY:
                raise Panic('HRESULT(0x80070003)')
            return real(*args, backend=backend, **kwargs)
        with patch.object(PtyProcess, 'spawn', side_effect=spawn):
            session = self.open()
        self.assertEqual(tried, [Backend.ConPTY, Backend.WinPTY])
        self.assertIn('READY', read_until(session, 'READY')[0])
        with patch.object(PtyProcess, 'spawn', side_effect=Panic('boom')):
            with self.assertRaises(RuntimeError) as caught:
                self.open()
        self.assertIn('ConPTY: boom', str(caught.exception))

    def test_selftest(self):
        self.assertTrue(agent_term.selftest(Path(self.room.name)))


class FakeAgentRoom(unittest.TestCase):
    """에이전트 대신 짧은 명령 파일 — 실행기는 진짜로 쓴다."""
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.folder = Path(self.room.name) / 'project'
        self.folder.mkdir()
        self.work = Path(self.room.name) / 'data'
        self.manager = agent_term.Manager()
        self.addCleanup(self.manager.close_all)
        exe = Path(self.room.name) / 'fake-agent.cmd'
        exe.write_text('@echo off\r\necho FAKE-AGENT\r\n', encoding='ascii')
        finder = patch.object(agent, 'find', return_value=str(exe))
        finder.start()
        self.addCleanup(finder.stop)

    def open(self, tool='claude', skip=False, team=None, cron=None):
        return self.manager.open(tool, str(self.folder), skip, self.work, team=team, cron=cron)


class ManagerTests(FakeAgentRoom):
    def test_each_session_has_a_name_and_its_own_launcher(self):
        first, second, codex = self.open(skip=True), self.open(), self.open('codex')
        self.assertEqual((first.name, second.name, codex.name), ('claude-1', 'claude-2', 'codex-1'))
        self.assertEqual(first.script, self.work / 'agent' / 'term-claude-1.cmd')
        self.assertIn('--dangerously-skip-permissions', first.script.read_text(encoding='oem'))
        self.assertNotIn('--dangerously-skip-permissions', second.script.read_text(encoding='oem'))
        self.assertTrue(first.info()['skip'])
        self.assertFalse(first.info()['team'])
        self.assertIn('FAKE-AGENT', read_until(first, 'FAKE-AGENT')[0])
        self.assertIs(self.manager.get(first.id), first)
        self.assertIs(self.manager.by_name('CLAUDE-2'), second)
        with self.assertRaises(ValueError):
            self.manager.get('t-none')

    def test_remote_control_name_carries_the_agent_name(self):
        """휴대폰·웹 세션 목록에서 에이전트를 구분하게 "자동화 업무 · claude-1" (2026-10-26 요청)."""
        with patch.object(agent, 'remote_supported', return_value=True):
            first = self.manager.open('claude', str(self.folder), False, self.work, '자동화 업무')
            second = self.manager.open('claude', str(self.folder), False, self.work, '자동화 업무')
            plain = self.manager.open('claude', str(self.folder), False, self.work)
        self.assertIn('--remote-control "자동화 업무 · claude-1"', first.script.read_text(encoding='oem'))
        self.assertIn('--remote-control "자동화 업무 · claude-2"', second.script.read_text(encoding='oem'))
        self.assertNotIn('--remote-control', plain.script.read_text(encoding='oem'))

    def test_closed_numbers_are_used_again(self):
        """모두 닫고 다시 열면 claude-1 — 남은 에이전트가 있는 줄 알았다 (2026-10-25)."""
        first, second = self.open(), self.open()
        self.manager.close(first.id)
        self.assertEqual(self.open().name, 'claude-1')            # 빈 번호부터
        self.manager.rename(second.id, 'claude-3')                 # 붙인 이름과도 겹치지 않는다
        self.assertEqual(self.open().name, 'claude-4')
        self.assertEqual(len(self.manager.alive()), 3)
        self.manager.close_all()
        self.assertEqual((self.manager.alive(), self.open().name), ([], 'claude-1'))

    def test_rename_must_be_unique(self):
        first, second = self.open(), self.open()
        self.manager.rename(first.id, '작성 담당')
        self.assertIs(self.manager.by_name('작성 담당'), first)
        self.assertEqual(first.info()['title'], '작성 담당')
        with self.assertRaises(ValueError):
            self.manager.rename(second.id, '작성 담당')
        with self.assertRaises(ValueError):
            self.manager.rename(second.id, 'claude-1')
        with self.assertRaises(ValueError):
            self.manager.rename(second.id, 'x' * 31)
        self.manager.rename(first.id, '')
        self.assertEqual(first.info()['title'], 'claude-1')

    def test_restart_keeps_id_name_title_and_key_with_a_new_epoch(self):
        session = self.open('codex', skip=True)
        self.manager.rename(session.id, '검토')
        _, cursor = read_until(session, 'FAKE-AGENT')
        fresh = self.manager.restart(session.id)
        self.assertEqual((fresh.id, fresh.name, fresh.title, fresh.skip), (session.id, 'codex-1', '검토', True))
        self.assertNotEqual(fresh.epoch, session.epoch)
        self.assertTrue(session.closed)
        self.assertTrue(fresh.read(cursor, 0, epoch=session.epoch)['reset'])   # 옛 cursor 로 물어도 새 세션을 처음부터

    def test_session_limit_and_close(self):
        with patch.object(agent_term, 'SESSION_LIMIT', 1):
            first = self.open()
            with self.assertRaises(RuntimeError):
                self.open()
            self.manager.close(first.id)
            self.open()

    def test_events_are_kept_and_waited_for(self):
        first, second = self.open(), self.open()
        self.assertEqual(self.manager.events()['events'], [])
        self.manager.note('send', first, second, '안녕')
        events = self.manager.events(0)
        self.assertEqual(events['last'], 1)
        self.assertEqual(events['events'][0]['fromName'], 'claude-1')
        self.assertEqual(self.manager.events(1)['events'], [])
        started = time.monotonic()
        self.manager.events(1, wait=0.3)
        self.assertGreaterEqual(time.monotonic() - started, 0.25)

    def test_events_pile_up_across_restarts_until_cleared(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / 'sessions.json'
            manager = agent_term.Manager(store)
            manager.note('analysis', None, None, '김교사: 처리할 일 없음', data={'key': 3, 'handoff': True})
            manager.note('peer-in', None, None, '안녕', to_name='나', from_name='다른 PC')
            again = agent_term.Manager(store)                     # 데스크를 다시 켰다
            events = again.events(0)
            self.assertEqual([event['text'] for event in events['events']], ['김교사: 처리할 일 없음', '안녕'])
            self.assertEqual(events['events'][0]['data'], {'key': 3, 'handoff': True})
            self.assertTrue(events['events'][0]['day'])
            self.assertEqual(again.note('send', None, None, '다음')['id'], 3)   # 번호는 이어 간다
            again.clear_events()
            self.assertEqual(again.events(0)['events'], [])
            self.assertEqual(agent_term.Manager(store).events(0)['events'], [])


class RemoteRenameTests(unittest.TestCase):
    """휴대폰·웹 세션 이름을 에이전트 이름에 맞추되, 입력 중이면 건드리지 않는다 (2026-10-26 요청). 의사 콘솔은 쓰지 않는다."""
    def make(self, remote='자동화 업무'):
        session = agent_term.Session.__new__(agent_term.Session)
        session.remote, session.name, session.drafting, session._closed = remote, 'claude-1', 0, False
        session.paste_mode, session.last_activity, session._chunks = False, time.monotonic() - 10, []
        session._echo_until, session._start, session._end = 0.0, 0, 0
        session._cond, session._input, session._pty = threading.Condition(), threading.Lock(), unittest.mock.Mock()
        session.agent_running = lambda: True
        patcher = patch.object(agent_term, 'ENTER_GAP', 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        return session

    def sent(self, session):
        return [call.args[0] for call in session._pty.write.call_args_list]

    def test_idle_session_gets_the_new_name(self):
        session = self.make()
        self.assertEqual(session.rename_remote('검토 담당'), '')
        self.assertEqual(self.sent(session), ['/rename 자동화 업무 · 검토 담당', '\r'])
        session = self.make()
        session.rename_remote('')                                    # 이름을 비우면 원래 이름 (claude-1)
        self.assertEqual(self.sent(session)[0], '/rename 자동화 업무 · claude-1')

    def test_nothing_is_sent_while_something_is_being_typed(self):
        session = self.make()
        session.write('안녕')
        self.assertEqual(session.drafting, 2)
        self.assertIn('입력하던 내용', session.rename_remote('검토 담당'))
        self.assertEqual(self.sent(session), ['안녕'])               # 입력칸에 아무것도 끼워 넣지 않았다
        session.write('\x7f\x7f')                                    # 지워서 비웠다
        self.assertEqual(session.rename_remote('검토 담당'), '')
        session.write('x')
        session.write('\r')                                          # Enter 로 보냈다
        self.assertEqual(session.drafting, 0)

    def test_arrow_keys_and_paste_marks_do_not_count_but_pasted_text_does(self):
        session = self.make()
        session.write('\x1b[A\x1b[B\x1b[200~\x1b[201~')
        self.assertEqual(session.drafting, 0)
        session.write('\x1b[200~붙인 글\x1b[201~')
        self.assertEqual(session.drafting, 4)
        session.write('\x03')                                        # Ctrl+C 로 비웠다
        self.assertEqual(session.drafting, 0)

    def test_a_working_claude_still_gets_the_new_name(self):
        busy = self.make()
        busy.last_activity = time.monotonic()                        # 일하는 중이어도 Claude Code 는 /rename 을 받는다
        self.assertEqual(busy.rename_remote('검토 담당'), '')
        self.assertEqual(self.sent(busy), ['/rename 자동화 업무 · 검토 담당', '\r'])

    def test_only_real_output_counts_as_work(self):
        """쉬는 중에도 '일하는 중'으로 보이던 것 (2026-10-26) — 제어 문자·메아리·다시 그리기는 일이 아니다."""
        session = self.make()
        session._append('\x1b]0;✳ Claude Code\x07\x1b[?25l\x1b[3;5H\x1b[0m  \r\n')     # 창 제목·커서·색·공백만
        self.assertGreater(session.quiet_for(), 5)
        session.write('안')                                          # 사람이 친 글자 — 곧 오는 출력은 메아리
        session._append('> 안')
        self.assertGreater(session.quiet_for(), 5)
        session.write('\x1b[I')                                      # 창이 포커스를 받아 에이전트가 다시 그린다
        session._append('╭──────╮\r\n│ > 안 │')
        self.assertGreater(session.quiet_for(), 5)
        session._echo_until = 0.0
        session.write('\r')                                          # Enter 뒤의 출력은 대답이다
        session._append('✻ Thinking…')
        self.assertLess(session.quiet_for(), 1)

    def test_resizing_redraw_is_not_work(self):
        session = self.make()
        session.size, session._closed = (90, 20), True                # 의사 콘솔은 건드리지 않는다
        session.resize(120, 30)
        session._append('╭────────────╮\r\n│ > │')
        self.assertGreater(session.quiet_for(), 5)

    def test_asking_or_unconnected_sessions_are_left_alone(self):
        asking = self.make()
        asking._chunks.append('Do you want to proceed?\r\n Esc to cancel · Tab to amend')
        self.assertIn('선택지', asking.rename_remote('검토 담당'))
        plain = self.make(remote='')
        self.assertEqual(plain.rename_remote('검토 담당'), '')
        for session in (asking, plain):
            self.assertEqual(self.sent(session), [])

    def test_titles_cannot_smuggle_extra_keystrokes(self):
        session = self.make()
        session.rename_remote('검토\r\x03 담당')
        self.assertEqual(self.sent(session)[0], '/rename 자동화 업무 · 검토 담당')


class BridgeTests(FakeAgentRoom):
    def setUp(self):
        super().setUp()
        self.screens, self.choices = {}, set()
        self.bridge = agent_bridge.Bridge(self.manager, self.work, screen=lambda s, n: self.screens.get(s.id),
                                          choice=lambda s: s.id in self.choices)
        self.addCleanup(self.bridge.stop)
        self.me, self.peer = self.open(team=self.bridge), self.open('codex', team=self.bridge)
        for session in (self.me, self.peer):
            read_until(session, 'FAKE-AGENT')
        patcher = patch.object(agent_term.Session, 'agent_running', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, path, body=None, token=None, content_type='text/plain'):
        request = urllib.request.Request(self.bridge.url + path, data=body, method='POST' if body is not None else 'GET')
        request.add_header('X-Desk-Token', token if token is not None else self.me.env['DESK_AGENT_TOKEN'])
        request.add_header('Content-Type', content_type)
        try:
            with urllib.request.urlopen(request, timeout=10) as answer:
                return answer.status, answer.read().decode('utf-8')
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode('utf-8')

    def test_cron_relay_over_http(self):
        """예약 업무를 에이전트가 대화로 (2026-11-07) — 기본 대상은 부른 에이전트 자신, 만들기는 승인, 교사판 데스크만."""
        import json as _json
        from core import agent_cron
        status, text = self.call('/cron')
        self.assertEqual(status, 501)
        asked = []
        cron = agent_cron.Scheduler(self.work, *([None] * 5))
        self.bridge.cron = agent_cron.Relay(
            cron, target_of=lambda name: {'name': name, 'tool': 'claude', 'folder': str(self.folder), 'skip': False, 'title': ''},
            approve=lambda agent, proposal: asked.append((agent, proposal)) or True)
        body = _json.dumps({'title': '아침 공문', 'prompt': '공문 정리', 'cron': '0 8 * * 1-5'}, ensure_ascii=False).encode('utf-8')
        status, text = self.call('/cron', body, content_type='application/json')
        self.assertEqual(status, 200, text)
        self.assertTrue(text.startswith('created '), text)
        self.assertEqual(asked[0][0], 'claude-1')
        self.assertEqual(cron.store.load()[0]['target']['name'], 'claude-1')     # agent 를 빼면 부른 에이전트 자신
        job_id = cron.store.load()[0]['id']
        self.assertIn(job_id, self.call('/cron')[1])
        self.assertIn('공문 정리', self.call(f'/cron/{job_id}')[1])
        self.assertIn('평일 08:00', self.call('/cron/preview', _json.dumps({'when': {'kind': 'weekdays', 'time': '08:00'}}).encode(),
                                               content_type='application/json')[1])
        self.assertEqual(self.call(f'/cron/{job_id}/off', b'')[0], 200)
        self.assertFalse(cron.store.load()[0]['on'])
        self.assertEqual(self.call('/cron', b'{"title": ""}', content_type='application/json')[0], 400)
        self.assertEqual(self.call('/cron', b'not json', content_type='application/json')[0], 400)
        self.assertEqual(self.call('/cron/zzz/delete', b'')[0], 404)
        self.assertEqual(self.call(f'/cron/{job_id}/delete', b'')[0], 200)
        self.assertEqual(self.call('/cron', token='wrong')[0], 401)
        self.assertIn('/cron', agent_bridge.GUIDE)
        self.assertIn('Do NOT use Claude Code', agent_bridge.GUIDE)

    def test_team_off_agent_gets_a_cron_only_key(self):
        """서로 보기를 끈 칸에도 예약 업무만 (2026-11-08 — 끈 상태에서 Claude 가 자체 CronCreate 로 만들어 목록에 안 보였다)."""
        from core import agent_cron
        solo = self.open(cron=self.bridge)
        codex = self.open('codex', cron=self.bridge)
        read_until(solo, 'FAKE-AGENT')
        self.assertNotIn('DESK_AGENT_TOKEN', solo.env)
        self.assertFalse(solo.info()['team'])
        self.assertNotIn('DESK_CRON_TOKEN', codex.env)                    # 예약 대상은 Claude Code 만
        token = solo.env['DESK_CRON_TOKEN']
        self.assertIn('cron-guide.md', solo.script.read_text(encoding='oem'))
        guide = self.bridge.cron_guide.read_text(encoding='utf-8')
        self.assertIn('$DESK_CRON_URL/cron', guide)
        self.assertIn('Do NOT use Claude Code', guide)
        self.assertNotIn('DESK_AGENT_TOKEN', guide)
        for path in ('/agents', '/read/claude-1', '/peers'):
            self.assertEqual(self.call(path, token=token)[0], 403, path)
        self.assertEqual(self.call('/send/claude-1', b'hi', token=token)[0], 403)
        self.assertEqual(self.call('/agents')[0], 200)                       # 팀 열쇠는 그대로
        self.bridge.cron = agent_cron.Relay(
            agent_cron.Scheduler(self.work, *([None] * 5)),
            target_of=lambda name: {'name': name, 'tool': 'claude', 'folder': str(self.folder), 'skip': False, 'title': ''},
            approve=lambda agent, proposal: True)
        status, text = self.call('/cron', token=token)
        self.assertEqual(status, 200, text)

    def test_sessions_get_their_address_key_and_instructions(self):
        env = self.me.env
        self.assertEqual(env['DESK_AGENT_NAME'], 'claude-1')
        self.assertTrue(env['DESK_AGENTS_URL'].startswith('http://127.0.0.1:'))
        self.assertNotEqual(env['DESK_AGENT_TOKEN'], self.peer.env['DESK_AGENT_TOKEN'])
        self.assertTrue(self.me.info()['team'])
        self.assertIn('--append-system-prompt-file', self.me.script.read_text(encoding='oem'))
        self.assertIn('developer_instructions=', self.peer.script.read_text(encoding='oem'))
        self.assertIn('DESK_AGENTS_URL', self.bridge.guide.read_text(encoding='utf-8'))
        for bad in '"%^&|<>!\n':
            self.assertNotIn(bad, agent_bridge.CODEX_NOTE)            # 실행기 한 줄에 그대로 넣는다
        agent_bridge.CODEX_NOTE.encode('ascii')

    def test_wrong_key_is_refused(self):
        self.assertEqual(self.call('/agents', token='nope')[0], 401)
        self.assertEqual(self.call('/agents', token='')[0], 401)

    def test_agents_lists_everyone_and_marks_me(self):
        code, text = self.call('/agents')
        self.assertEqual(code, 200)
        self.assertIn('claude-1 (you)', text)
        self.assertIn('codex-1', text)

    def test_read_uses_the_window_screen_or_falls_back_to_output(self):
        self.screens[self.peer.id] = '첫 줄\n둘째 줄\n셋째 줄'
        code, text = self.call('/read/codex-1?lines=2')
        self.assertEqual(code, 200)
        self.assertIn('둘째 줄\n셋째 줄', text)
        self.assertNotIn('첫 줄', text)
        del self.screens[self.peer.id]
        self.assertIn('FAKE-AGENT', self.call('/read/codex-1')[1])     # 창이 없으면 출력에서
        self.assertEqual(self.call('/read/nobody')[0], 404)
        self.assertEqual(self.manager.events()['events'][-1]['kind'], 'read')

    def test_send_types_into_the_peer_with_the_sender_name(self):
        _, cursor = read_until(self.peer, 'FAKE-AGENT')
        code, text = self.call('/send/codex-1', 'echo 검토 부탁해요'.encode('utf-8'))
        self.assertEqual(code, 200, text)
        seen, _ = read_until(self.peer, '검토 부탁해요', cursor)
        self.assertIn('[에이전트 claude-1 의 메시지] echo 검토 부탁해요', seen)
        event = self.manager.events()['events'][-1]
        self.assertEqual((event['kind'], event['fromName'], event['toName'], event['text']),
                         ('send', 'claude-1', 'codex-1', 'echo 검토 부탁해요'))

    def test_send_reads_cp949_and_json(self):
        _, cursor = read_until(self.peer, 'FAKE-AGENT')
        self.assertEqual(self.call('/send/codex-1', '안녕 cp'.encode('cp949'))[0], 200)
        self.assertIn('안녕 cp', read_until(self.peer, '안녕 cp', cursor)[0])
        code, _ = self.call('/send/codex-1', '{"text": "제이슨"}'.encode('utf-8'), content_type='application/json')
        self.assertEqual(code, 200)
        self.assertEqual(self.manager.events()['events'][-1]['text'], '제이슨')

    def test_send_is_refused_while_the_peer_waits_on_a_choice(self):
        self.choices.add(self.peer.id)
        with patch.object(agent_term.Session, 'submit') as typed:
            code, text = self.call('/send/codex-1', b'yes')
        self.assertEqual(code, 409)
        self.assertIn('waiting-for-user-choice', text)
        typed.assert_not_called()                                     # 골라져 있던 답을 눌러 버리지 않는다

    def test_send_checks(self):
        self.assertEqual(self.call('/send/claude-1', b'me')[0], 400)   # 나에게
        self.assertEqual(self.call('/send/codex-1', b'   ')[0], 400)
        self.assertEqual(self.call('/send/nobody', b'x')[0], 404)
        self.assertEqual(self.call('/send/codex-1', b'x' * (agent_term.MESSAGE_LIMIT + 1))[0], 413)
        self.assertEqual(self.call('/nothing')[0], 404)

    def test_send_all_reaches_every_other_agent(self):
        with patch.object(agent_term.Session, 'submit') as typed:
            code, text = self.call('/send/all', '모두 안녕'.encode('utf-8'))
        self.assertEqual(code, 200, text)
        self.assertEqual(typed.call_count, 1)                         # 나 말고 하나
        self.assertIn('codex-1', text)

    def test_wait_returns_when_the_peer_is_quiet(self):
        self.peer.last_activity = time.monotonic() - 10
        code, text = self.call('/wait/codex-1?quiet=1&timeout=5')
        self.assertEqual(code, 200)
        self.assertIn('status: idle', text)
        self.peer.last_activity = time.monotonic() + 100               # 끝없이 일하는 중
        code, text = self.call('/wait/codex-1?quiet=1&timeout=1')
        self.assertIn('timeout', text)


class Hook:
    """pywebview 창의 events.* 흉내 — += 로 달고 fire 로 부른다 (closing 은 False 를 돌려주면 닫지 않는다)."""
    def __init__(self):
        self.items = []

    def __iadd__(self, func):
        self.items.append(func)
        return self

    def fire(self):
        return [func() for func in self.items]


class FakeWindow:
    def __init__(self, shown=True):
        self.events = type('Events', (), {})()
        for name in ('loaded', 'closing', 'closed'):
            setattr(self.events, name, Hook())
        self.shown, self.scripts, self.destroyed = shown, [], False

    def run_js(self, script):
        self.scripts.append(script)

    def evaluate_js(self, script):
        self.scripts.append(script)
        return self.shown

    def destroy(self):
        """진짜 창처럼 — 닫기 전에 closing 을 묻고, 막지 않으면 closed."""
        if False in self.events.closing.fire():
            return
        self.destroyed = True
        self.events.closed.fire()

    def show(self): pass
    def restore(self): pass


def settle(name):
    for _ in range(200):
        if not any(thread.name == name for thread in threading.enumerate()):
            return
        time.sleep(0.01)


class DesktopTermTests(unittest.TestCase):
    def setUp(self):
        self.api = DesktopAPI()
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.api._preferences_path = Path(self.room.name) / 'desktop-preferences.json'
        self.folder = Path(self.room.name) / 'project'
        self.folder.mkdir()

    def tearDown(self):
        if self.api._terms:
            self.api._terms.close_all()
        if self.api._term_bridge:
            self.api._term_bridge.stop()

    def fake_agent(self):
        exe = Path(self.room.name) / 'fake-agent.cmd'
        exe.write_text('@echo off\r\necho FAKE-AGENT\r\n', encoding='ascii')
        return patch.object(agent, 'find', return_value=str(exe))

    def test_embedded_is_the_default_and_can_be_turned_off(self):
        self.assertTrue(self.api._agent_embedded())
        with patch.object(DesktopAPI, '_term_open', return_value='안에서 열었습니다') as inside, \
             patch.object(agent, 'launch', return_value='밖에서 열었습니다') as outside:
            self.assertEqual(self.api.call('agent_run', {'folder': str(self.folder)})['data'], '안에서 열었습니다')
            self.assertIn('Windows Terminal', self.api.call('agent_settings', {'embed': False})['data'])
            self.assertEqual(self.api.call('agent_run', {'folder': str(self.folder)})['data'], '밖에서 열었습니다')
        self.assertEqual(inside.call_args.args[:3], ('claude', os.path.normpath(str(self.folder)), False))
        outside.assert_called_once()
        self.assertFalse(self.api.call('agent_settings', {'embed': 'yes'})['ok'])

    def test_falls_back_to_the_outside_terminal_without_pywinpty(self):
        with patch.object(DesktopAPI, '_term_open', side_effect=ImportError('winpty')), \
             patch.object(agent, 'launch', return_value='밖에서 열었습니다') as outside:
            self.assertEqual(self.api.call('agent_run', {'folder': str(self.folder)})['data'], '밖에서 열었습니다')
        outside.assert_called_once()

    def test_opening_adds_to_one_workspace_with_the_team_on(self):
        with self.fake_agent(), patch.object(desktop.watcher, 'DATA_DIR', self.room.name), \
             patch.object(DesktopAPI, '_term_show') as show:
            self.assertIn('claude-1', self.api._term_open('claude', str(self.folder), False))
            self.assertIn('claude-2', self.api._term_open('claude', str(self.folder), False))
            self.assertTrue(self.api.call('term_team_set', {'on': False})['ok'])
            self.api._term_open('codex', str(self.folder), False)
        self.assertEqual(show.call_count, 3)
        listed = self.api.call('term_list')['data']
        self.assertEqual([row['agent'] for row in listed['sessions']], ['claude-1', 'claude-2', 'codex-1'])
        self.assertEqual([row['team'] for row in listed['sessions']], [True, True, False])
        self.assertFalse(listed['team'])
        self.assertFalse(self.api.call('term_team_set', {'on': 'yes'})['ok'])

    def test_new_close_rename_and_events(self):
        with self.fake_agent(), patch.object(desktop.watcher, 'DATA_DIR', self.room.name), \
             patch.object(DesktopAPI, '_term_show'):
            self.assertTrue(self.api.call('term_new', {'tool': 'codex', 'folder': str(self.folder)})['ok'])
            self.assertFalse(self.api.call('term_new', {'tool': 'bash', 'folder': str(self.folder)})['ok'])
            self.assertFalse(self.api.call('term_new', {'tool': 'claude', 'folder': 'relative'})['ok'])
            self.assertFalse(self.api.call('term_new', {'tool': 'claude', 'folder': 'pick'})['ok'])   # 창이 없다
            with_tools = self.api.call('term_list', {'tools': True})['data']
        self.assertIn('claude', with_tools['tools'])
        sid = with_tools['sessions'][0]['id']
        renamed = self.api.call('term_rename', {'id': sid, 'title': '검토 담당'})['data']
        self.assertEqual(renamed['title'], '검토 담당')
        self.assertEqual(self.api.call('term_events', {'after': 0})['data'], {'events': [], 'last': 0})
        self.assertFalse(self.api.call('term_events', {'after': 'x'})['ok'])
        self.assertTrue(self.api.call('term_close', {'id': sid})['ok'])
        self.assertEqual(self.api.call('term_list')['data']['sessions'], [])

    def open_in_window(self, count=2):
        """창을 띄워(가짜) 에이전트를 count 개 연다 — 만든 창들을 돌려준다."""
        made = []

        def create_window(*args, **kwargs):
            made.append(FakeWindow())
            return made[-1]
        patches = [self.fake_agent(), patch.object(desktop.watcher, 'DATA_DIR', self.room.name),
                   patch('webview.create_window', side_effect=create_window),
                   patch.object(DesktopAPI, '_front_when_loaded'), patch.object(DesktopAPI, '_bring_front')]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        for _ in range(count):
            self.api._term_open('claude', str(self.folder), False)
            if made and not self.api._term_ready:
                made[-1].events.loaded.fire()
        return made

    def close_button(self, window):
        """창의 ✕ — 닫혔으면 True."""
        window.destroy()
        settle('agent-term-leave')
        settle('agent-term-close')
        return window.destroyed

    def test_automation_open_shows_the_running_automation_agent(self):
        """자동화 업무 폴더에서 연 에이전트가 켜져 있으면 «열기»가 새로 열지 않고 그것을 보인다 (2026-10-30 요청)."""
        from core import automation
        self.api._save_preferences(automation_folder=str(self.folder), agent_tool='claude')
        self.open_in_window(1)
        with patch.object(automation, 'install', return_value=[]),                 patch.object(automation, 'create_shortcut'),                 patch.object(self.api, '_automation_prepare', side_effect=AssertionError('새로 열면 안 된다')):
            message = self.api._automation_open({})
        self.assertIn('켜 둔 자동화 업무 에이전트', message)
        self.assertEqual(len(self.api._terms.sessions()), 1)
        self.api._save_preferences(agent_tool='codex')              # 다른 에이전트를 골랐으면 새로 연다
        self.assertIsNone(self.api._automation_session())

    def test_closing_asks_and_keeping_leaves_the_agents_running(self):
        """창을 닫을 때 모두 끌지 묻고, 켜 두면 다시 열었을 때 그대로 (2026-10-25 요청)."""
        first, = self.open_in_window(2)
        self.assertFalse(self.close_button(first))                    # 바로 닫지 않고 묻는다
        self.assertIn('askLeave', first.scripts[-1])
        self.assertTrue(self.api.call('term_window_close', {'keep': True})['ok'])
        settle('agent-term-close')
        self.assertTrue(first.destroyed)
        self.assertIsNone(self.api._term_window)
        self.assertEqual(len(self.api._terms.alive()), 2)             # 에이전트는 그대로
        self.assertEqual(self.api._term_kept(), 2)
        self.assertFalse(self.api.call('term_window_close', {'keep': 'yes'})['ok'])
        # 독 아이콘을 누르면 켜 둔 에이전트의 창부터 다시 연다 — 새 에이전트를 띄우지 않는다
        answer = self.api.call('agent_quick')['data']
        self.assertTrue(answer['launched'])
        self.assertIn('2개', answer['message'])
        self.assertEqual(len(self.api._terms.sessions()), 2)
        again = self.api._term_window
        again.events.loaded.fire()
        self.assertIn('attachAll', again.scripts[-1])
        self.assertEqual(self.api._term_kept(), 0)                    # 창이 열려 있으면 '켜 둔 것'이 아니다
        # 창이 열려 있어도(뒤에 가려져 있어도) 독 아이콘은 새로 열지 않고 그 창을 앞으로 (2026-10-30 요청)
        answer = self.api.call('agent_quick')['data']
        self.assertTrue(answer['launched'])
        self.assertIn('앞으로', answer['message'])
        self.assertEqual(len(self.api._terms.sessions()), 2)
        self.assertIs(self.api._term_window, again)
        # 이번엔 모두 끄고 닫는다 — 새로 열면 다시 claude-1
        self.assertFalse(self.close_button(again))
        self.api.call('term_window_close', {'keep': False})
        settle('agent-term-close')
        self.assertTrue(again.destroyed)
        self.assertEqual(self.api._terms.alive(), [])
        self.assertFalse(self.api.call('term_show')['ok'])
        self.open_in_window(1)
        self.assertEqual(self.api._terms.sessions()[0].name, 'claude-1')

    def test_closing_without_running_agents_or_a_working_page_does_not_get_stuck(self):
        first, = self.open_in_window(1)
        first.shown = None                                            # 화면이 묻지 못한다 — 예전처럼 모두 끄고 닫는다
        self.close_button(first)
        self.assertTrue(first.destroyed)
        self.assertEqual(self.api._terms.alive(), [])
        second, = self.open_in_window(1)
        self.api.call('term_close', {'id': self.api._terms.sessions()[0].id})
        self.assertTrue(self.close_button(second))                    # 켜진 에이전트가 없으면 묻지 않는다
        self.assertNotIn('askLeave', ''.join(second.scripts))

    def test_term_actions_need_a_known_session(self):
        for action in ('term_info', 'term_read', 'term_write', 'term_resize', 'term_restart', 'term_reveal', 'term_close'):
            answer = self.api.call(action, {'id': 'nope'})
            self.assertFalse(answer['ok'], action)

    def test_read_write_through_the_api(self):
        with self.fake_agent(), patch.object(desktop.watcher, 'DATA_DIR', self.room.name), \
             patch.object(DesktopAPI, '_term_show'):
            self.api._term_open('claude', str(self.folder), False)
        session = self.api._terms.sessions()[0]
        cursor, seen = 0, ''
        for _ in range(25):
            result = self.api.call('term_read', {'id': session.id, 'cursor': cursor})['data']
            cursor, seen = result['cursor'], seen + result['data']
            if 'FAKE-AGENT' in seen:
                break
        self.assertIn('FAKE-AGENT', seen)
        self.assertIn('running', result)
        self.assertTrue(self.api.call('term_write', {'id': session.id, 'data': 'echo 둘\r'})['ok'])
        self.assertFalse(self.api.call('term_write', {'id': session.id, 'data': 3})['ok'])
        self.assertFalse(self.api.call('term_read', {'id': session.id, 'cursor': -1})['ok'])
        self.assertTrue(self.api.call('term_resize', {'id': session.id, 'cols': 100, 'rows': 30})['ok'])
        info = self.api.call('term_info', {'id': session.id})['data']
        self.assertEqual((info['label'], info['name'], info['agent']), ('Claude Code', 'project', 'claude-1'))
        self.assertIn(info['state'], {'working', 'idle', 'waiting-for-user-choice', 'agent-exited', 'ended'})

    def test_snippets_are_checked_and_saved(self):
        self.assertIsNone(self.api.call('term_snippets')['data'])          # 고친 적 없으면 화면의 기본 목록
        items = [{'label': '요약', 'text': '요약해 줘'}, {'label': '', 'text': '이름 없는 말'}]
        self.assertTrue(self.api.call('term_snippets_save', {'items': items})['ok'])
        self.assertEqual(self.api.call('term_snippets')['data'][1]['label'], '이름 없는 말')
        self.assertFalse(self.api.call('term_snippets_save', {'items': [{'label': 'x', 'text': '  '}]})['ok'])
        self.assertFalse(self.api.call('term_snippets_save', {'items': [{'label': 'x', 'text': 'y' * 5000}]})['ok'])
        self.assertFalse(self.api.call('term_snippets_save', {'items': 'x'})['ok'])

    def test_term_actions_are_allowed_for_students(self):
        handlers = self.api._handlers()
        for action in [name for name in handlers if name.startswith('term_')]:
            self.assertIn(action, desktop.STUDENT_ACTIONS, action)

    def test_page_and_vendor_files_exist(self):
        web = Path(desktop.__file__).parent / 'web'
        for name in ('agent-term.html', 'agent-term.js', 'agent-term.css', 'vendor/xterm/xterm.js',
                     'vendor/xterm/xterm.css', 'vendor/xterm/addon-fit.js', 'vendor/xterm/LICENSE.md'):
            self.assertTrue((web / name).is_file(), name)


class UsageTests(unittest.TestCase):
    """현황 — 대화 기록에서 컨텍스트·결과물, 상태 줄 파일에서 크기·한도."""
    CONVERSATION = '11111111-2222-3333-4444-555555555555'

    def setUp(self):
        from core import agent_usage
        self.agent_usage = agent_usage
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'work'
        self.folder.mkdir()
        (self.root / 'projects' / 'D--work').mkdir(parents=True)
        self.transcript = self.root / 'projects' / 'D--work' / f'{self.CONVERSATION}.jsonl'
        patcher = patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def write(self, *rows):
        import json
        with self.transcript.open('a', encoding='utf-8') as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')

    def tool(self, use_id, name, path, msg='m1'):
        return {'type': 'assistant', 'timestamp': '2026-10-30T01:00:00Z', 'message': {
            'id': msg, 'model': 'claude-opus-5-5', 'usage': {'input_tokens': 10, 'cache_read_input_tokens': 50000,
                                                             'cache_creation_input_tokens': 2000, 'output_tokens': 300},
            'content': [{'type': 'tool_use', 'id': use_id, 'name': name, 'input': {'file_path': path}}]}}

    def result(self, use_id, text, error=False):
        return {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': use_id, 'content': text,
                                                          'is_error': error}]}}

    def test_outputs_context_and_status(self):
        made, fixed, failed = str(self.folder / '보고서.md'), str(self.folder / 'app.py'), str(self.folder / 'x.txt')
        Path(made).write_text('a', encoding='utf-8')
        self.write(self.tool('u1', 'Write', made), self.result('u1', 'File created successfully at: ' + made),
                   self.tool('u2', 'Edit', fixed, msg='m2'), self.result('u2', 'The file has been updated.'),
                   self.tool('u3', 'Write', failed, msg='m3'), self.result('u3', 'denied', error=True),
                   self.tool('u4', 'Edit', made, msg='m4'), self.result('u4', 'updated'))
        reader = self.agent_usage.Reader()
        data = reader.read(self.CONVERSATION)
        self.assertEqual([item['name'] for item in data['outputs']], ['보고서.md', 'app.py'])   # 최근 것부터, 실패는 빼고
        self.assertEqual((data['outputs'][0]['created'], data['outputs'][0]['count'], data['outputs'][0]['exists']), (True, 2, True))
        self.assertFalse(data['outputs'][1]['created'])
        self.assertEqual(data['context']['used'], 52010)
        self.assertTrue(data['context']['guessed'])
        self.assertEqual(data['output_tokens'], 1200)
        self.assertTrue(reader.has_output(self.CONVERSATION, made))
        self.assertFalse(reader.has_output(self.CONVERSATION, str(self.folder / 'other.txt')))
        status = self.root / 'status.json'
        import json
        status.write_text(json.dumps({'session_id': self.CONVERSATION, 'model': {'display_name': 'Opus 5.5'},
                                      'context_window': {'context_window_size': 1000000, 'used_percentage': 5.2},
                                      'cost': {'total_cost_usd': 1.5, 'total_lines_added': 3, 'total_lines_removed': 1},
                                      'rate_limits': {'five_hour': {'used_percentage': 40, 'resets_at': 1790000000}}}),
                          encoding='utf-8')
        data = reader.read(self.CONVERSATION, status)
        self.assertEqual((data['context']['size'], data['context']['percent'], data['context']['guessed']), (1000000, 5, False))
        self.assertEqual(data['limits'], [{'label': '5시간 한도', 'percent': 40, 'resets': 1790000000}])
        self.assertEqual((data['model'], data['cost']), ('Opus 5.5', 1.5))
        self.write(self.tool('u5', 'Write', str(self.folder / 'new.py'), msg='m5'))     # 결과가 아직 없으면 넣지 않는다
        self.assertEqual(len(reader.read(self.CONVERSATION)['outputs']), 2)
        self.write(self.result('u5', 'File created successfully'))                      # 새로 붙은 줄만 읽는다
        self.assertEqual(reader.read(self.CONVERSATION)['outputs'][0]['name'], 'new.py')

    def test_status_of_another_conversation_is_ignored(self):
        import json
        status = self.root / 'status.json'
        status.write_text(json.dumps({'session_id': 'old', 'context_window': {'context_window_size': 1000000}}), encoding='utf-8')
        self.assertFalse(self.agent_usage.Reader().read(self.CONVERSATION, status)['ready'])

    def test_status_line_chains_the_users_own_command(self):
        import json
        (self.root / 'settings.json').write_text(json.dumps({'statusLine': {'type': 'command', 'command': "C:/it's/line.cmd"}}),
                                                 encoding='utf-8')
        settings = json.loads(agent_term.claude_hooks(self.folder).read_text(encoding='utf-8'))
        self.assertIn('desk-status-line.ps1', settings['statusLine']['command'])
        self.assertIn('SessionStart', settings['hooks'])
        script = (self.folder / 'agent' / 'desk-status-line.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("$chain = 'C:/it''s/line.cmd'", script)


if __name__ == '__main__':
    unittest.main()


class ChatTests(UsageTests):
    """대화 보기 (2026-11-06) — 대화 기록을 말풍선 항목으로. 새로 붙은 줄만 읽고, 도구 결과는 같은 항목을 갈아 끼운다."""

    def test_outputs_context_and_status(self):            # 부모의 시험은 여기서 다시 돌리지 않는다
        pass

    def test_status_of_another_conversation_is_ignored(self):
        pass

    def test_status_line_chains_the_users_own_command(self):
        pass

    def test_items_and_updates(self):
        from core import agent_chat
        say = lambda text, **extra: {'type': 'user', 'message': {'content': text}, **extra}
        answer = lambda text: {'type': 'assistant', 'message': {'id': 'a', 'content': [
            {'type': 'thinking', 'thinking': '숨김'}, {'type': 'text', 'text': text}]}}
        self.write(say('반별 평균 정리해 줘'), say('<system-reminder>숨김</system-reminder>'), say('안내', isMeta=True),
                   say('<command-name>/clear</command-name><command-args></command-args>'),
                   answer('네, 볼게요.'), self.tool('u1', 'Read', str(self.folder / '성적.xlsx')),
                   {'type': 'assistant', 'isSidechain': True, 'message': {'content': [{'type': 'text', 'text': '도우미 속'}]}})
        reader = agent_chat.Reader()
        first = reader.read(self.CONVERSATION)
        self.assertEqual([(i['k'], i.get('text') or i.get('label')) for i in first['items']],
                         [('user', '반별 평균 정리해 줘'), ('note', '/clear'), ('text', '네, 볼게요.'), ('tool', '파일 읽기')])
        tool = first['items'][-1]
        self.assertEqual((tool['detail'], tool['status']), ('성적.xlsx', 'run'))
        self.write(self.result('u1', '28행'), answer('끝났습니다.'))
        later = reader.read(self.CONVERSATION, first['rev'])
        self.assertEqual([(i['i'], i['k'], i.get('status')) for i in later['items']],
                         [(tool['i'], 'tool', 'ok'), (tool['i'] + 1, 'text', None)])   # 같은 번호를 갈아 끼운다
        self.assertEqual(later['items'][0]['result'], '28행')
        self.assertFalse(later['reset'])
        self.assertTrue(reader.read(self.CONVERSATION, later['rev'] + 50)['reset'])       # 모르는 rev — 처음부터
        self.assertTrue(reader.read('22222222-2222-3333-4444-555555555555')['empty'])    # 아직 없는 대화

    def test_interrupted_tool_and_labels(self):
        from core import agent_chat
        self.write(self.tool('u1', 'Bash', ''), {'type': 'user', 'message': {'content': [
            {'type': 'text', 'text': '[Request interrupted by user]'}]}})
        items = agent_chat.Reader().read(self.CONVERSATION)['items']
        self.assertEqual((items[0]['status'], items[1]['text']), ('err', '멈췄습니다'))
        self.assertEqual(agent_chat.tool_view('mcp__spacekijun__list_contexts', {'p_query': '시험'}), ('spacekijun · list_contexts', '시험'))
        self.assertEqual(agent_chat.tool_view('Bash', {'command': 'dir', 'description': '파일 목록'}), ('명령 실행', '파일 목록'))

    def test_messages_sent_while_working(self):
        """일하는 중에 보낸 말 — 지금 꼴(attachment queued_command)과 옛 꼴(도구 결과 옆 글 블록) 모두. 작업 알림은 뺀다."""
        from core import agent_chat
        queued = lambda prompt, mode='prompt': {'type': 'attachment', 'attachment': {
            'type': 'queued_command', 'prompt': prompt, 'commandMode': mode}}
        old = {'type': 'user', 'message': {'content': [
            {'type': 'tool_result', 'tool_use_id': 'u1', 'content': 'ok'},
            {'type': 'text', 'text': 'The user sent a new message while you were working:\n인원도 넣어 줘\n\n'
                                     'This is how Claude Code surfaces messages the user sends mid-turn.'}]}}
        self.write(self.tool('u1', 'Bash', ''), queued('표도 만들어 줘'), queued('<task-notification>끝</task-notification>', 'task-notification'), old)
        items = agent_chat.Reader().read(self.CONVERSATION)['items']
        self.assertEqual([(i['k'], i.get('text'), i.get('queued')) for i in items[1:]],
                         [('user', '표도 만들어 줘', True), ('user', '인원도 넣어 줘', True)])
        self.assertEqual(items[0]['status'], 'ok')

    def test_images_are_keys_read_on_demand(self):
        """사진은 열쇠만 항목에 — 기록 줄 속 사진, 결과 글에 나온 그림 파일 (이 대화에 나온 것만 내준다)."""
        from core import agent_chat
        png = 'iVBORw0KGgo='
        shot = self.folder / '화면.png'
        shot.write_bytes(b'\x89PNG')
        self.write(self.tool('u1', 'mcp__playwright__browser_take_screenshot', ''), self.tool('u2', 'Bash', '', msg='m2'),
                   {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'u1', 'content': [
                       {'type': 'text', 'text': '찍었습니다'}, {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': png}}]}]}},
                   self.result('u2', f'저장: {shot}'),
                   {'type': 'user', 'message': {'content': [{'type': 'text', 'text': '[Image #1] 이거 봐 줘'},
                                                            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': 'AAA='}}]}})
        reader = agent_chat.Reader()
        items = reader.read(self.CONVERSATION)['items']
        first, second, mine = items[0]['images'], items[1]['images'], items[2]
        self.assertEqual(reader.image(self.CONVERSATION, first[0]), {'type': 'image/png', 'data': png})
        self.assertEqual(second, ['f:' + str(shot)])
        self.assertEqual(reader.image(self.CONVERSATION, second[0])['type'], 'image/png')
        self.assertEqual((mine['text'], reader.image(self.CONVERSATION, mine['images'][0])['type']), ('이거 봐 줘', 'image/jpeg'))
        self.assertIsNone(reader.image(self.CONVERSATION, 'f:' + str(self.folder / '다른.png')))   # 대화에 안 나온 파일
        self.assertIsNone(reader.image(self.CONVERSATION, 'b:0:0'))
