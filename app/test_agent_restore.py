"""에이전트 터미널 — 다시 켜면 그 대화로 다시 열기 · 자식 에이전트 (2026-10-27 요청, Orca 처럼).

업데이트·PC 재시작으로 데스크가 꺼져도 열린 칸(도구·폴더·이름·권한·부모·대화 id)을 sessions.json 에서 되살린다.
에이전트가 중계 /spawn 으로 연 자식 에이전트는 진짜 새 칸이다. 에이전트 대신 짧은 명령 파일을 돌린다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명·설정 파일에는 절대 닿지 않는다
import json
import os
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import desktop
from core import agent, agent_bridge, agent_term
from desktop import DesktopAPI
from test_agent_term import read_until

UUID = '9a648346-2c0a-4a54-87a5-5cd43b735026'


class Room(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.root = Path(self.room.name)
        self.folder = self.root / 'project'
        (self.folder / 'part').mkdir(parents=True)
        self.work = self.root / 'data'
        self.store = self.work / 'agent' / 'sessions.json'
        exe = self.root / 'fake-agent.cmd'
        exe.write_text('@echo off\r\necho FAKE-AGENT\r\n', encoding='ascii')
        finder = patch.object(agent, 'find', return_value=str(exe))
        finder.start()
        self.addCleanup(finder.stop)

    def manager(self):
        manager = agent_term.Manager(self.store)
        self.addCleanup(manager.close_all)
        return manager

    def saved(self):
        return json.loads(self.store.read_text(encoding='utf-8'))


class LookupTests(Room):
    def test_claude_transcript_is_looked_up_by_id(self):
        projects = self.root / 'claude' / 'projects' / 'D--project'
        projects.mkdir(parents=True)
        (projects / f'{UUID}.jsonl').write_text('{}\n', encoding='utf-8')
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.root / 'claude')}):
            self.assertTrue(agent.claude_transcript(UUID))
            self.assertFalse(agent.claude_transcript(UUID.replace('9', '8')))
            self.assertFalse(agent.claude_transcript('*'))                      # 와일드카드로 아무 파일이나 잡지 않는다

    def test_codex_thread_is_the_latest_rollout_in_that_folder(self):
        day = time.strftime('%Y/%m/%d').split('/')
        sessions = self.root / 'codex' / 'sessions' / day[0] / day[1] / day[2]
        sessions.mkdir(parents=True)

        def rollout(name, cwd, age):
            path = sessions / f'rollout-{name}.jsonl'
            path.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': name, 'cwd': cwd}}) + '\n', encoding='utf-8')
            stamp = time.time() - age
            os.utime(path, (stamp, stamp))
        since = time.time() - 100
        rollout('old', str(self.folder), 500)                                     # 데스크가 열기 전
        rollout('mine', '\\\\?\\' + str(self.folder), 50)                         # Codex 는 \\?\ 를 붙인다
        rollout('newer', str(self.folder).upper(), 10)
        rollout('elsewhere', str(self.root), 1)
        with patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'codex')}):
            self.assertEqual(agent.codex_thread(str(self.folder), since), 'newer')
            self.assertEqual(agent.codex_thread(str(self.folder), since, exclude={'newer'}), 'mine')
            self.assertEqual(agent.codex_thread(str(self.folder / 'part'), since), '')

    def test_a_parent_claude_sessions_markers_are_not_inherited(self):
        """Claude Code 안에서 띄운 데스크면 그 표시를 물려받아 새 에이전트가 대화를 저장하지 않았다 (2026-10-27)."""
        with patch.dict(os.environ, {'CLAUDE_CODE_CHILD_SESSION': '1', 'CLAUDECODE': '1', 'CLAUDE_CONFIG_DIR': 'x'}):
            env = agent_term.session_env()
        self.assertNotIn('CLAUDE_CODE_CHILD_SESSION', env)
        self.assertNotIn('CLAUDECODE', env)
        self.assertEqual(env['CLAUDE_CONFIG_DIR'], 'x')                            # 사용자 설정은 그대로

    def test_the_hook_writes_the_session_id_it_is_given(self):
        settings = agent_term.claude_hooks(self.work)
        command = json.loads(settings.read_text(encoding='utf-8'))['hooks']['SessionStart'][0]['hooks'][0]['command']
        self.assertTrue(command.startswith('powershell.exe '))
        target = self.root / 'conversation.txt'
        done = subprocess.run(command, input=json.dumps({'session_id': UUID, 'source': 'clear'}), text=True, shell=True,
                              capture_output=True, timeout=60, env={**os.environ, 'DESK_SESSION_FILE': str(target)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), '')                                 # 훅의 출력은 대화에 들어간다 — 비어야 한다
        self.assertEqual(target.read_text(encoding='utf-8'), UUID)


class SaveTests(Room):
    def test_claude_opens_with_its_own_id_and_the_hook_follows_new_conversations(self):
        manager = self.manager()
        session = manager.open('claude', str(self.folder), True, self.work)
        script = session.script.read_text(encoding='oem')
        self.assertIn(f'--session-id {session.conversation}', script)
        self.assertIn('--settings "', script)
        self.assertEqual(session.env['DESK_SESSION_FILE'], str(session.conversation_file))
        row = self.saved()['sessions'][0]
        self.assertEqual((row['tool'], row['name'], row['skip'], row['conversation']),
                         ('claude', 'claude-1', True, session.conversation))
        Path(session.env['DESK_SESSION_FILE']).write_text(UUID, encoding='utf-8')   # '새 대화' 뒤 훅이 적는다
        manager.save()
        self.assertEqual(self.saved()['sessions'][0]['conversation'], UUID)

    def test_restart_resumes_the_conversation_instead_of_reusing_the_id(self):
        manager = self.manager()
        session = manager.open('claude', str(self.folder), False, self.work)
        Path(session.env['DESK_SESSION_FILE']).write_text(UUID, encoding='utf-8')
        with patch.object(agent, 'claude_transcript', return_value=True):
            fresh = manager.restart(session.id)
        self.assertIn(f'--resume {UUID}', fresh.script.read_text(encoding='oem'))
        self.assertNotIn('--session-id', fresh.script.read_text(encoding='oem'))
        with patch.object(agent, 'claude_transcript', return_value=False):        # 첫 메시지 전이라 대화가 없다 — 새로
            again = manager.restart(fresh.id)
        self.assertIn('--session-id', again.script.read_text(encoding='oem'))

    def test_phone_chat_room_follows_the_conversation(self):
        """휴대폰 채팅방 (2026-11-10) — 다시 켜서 그 대화를 이어 열면 같은 방, 이어 열지 못해 새 대화면 새 방."""
        manager = self.manager()
        session = manager.open('claude', str(self.folder), False, self.work)
        Path(session.env['DESK_SESSION_FILE']).write_text(UUID, encoding='utf-8')
        room = session.chat_thread()
        manager.save()
        row = self.saved()['sessions'][0]
        self.assertEqual((row['conversation'], row['thread']), (UUID, room))
        with patch.object(agent, 'claude_transcript', return_value=True):
            fresh = manager.restart(session.id)                                    # 칸 다시 시작 — 같은 대화
            back = manager.open('claude', str(self.folder), False, self.work, name='claude-7',
                                resume=row['conversation'], thread=row['thread'])  # 데스크를 다시 켬 — 이어 열기 성공
        self.assertEqual(fresh.chat_thread(), room)
        self.assertEqual(back.chat_thread(), room)
        with patch.object(agent, 'claude_transcript', return_value=False):         # 이어 열기 실패 — 새 대화라 새 방
            lost = manager.open('claude', str(self.folder), False, self.work, name='claude-8',
                                resume=row['conversation'], thread=row['thread'])
        self.assertNotEqual(lost.chat_thread(), room)
        self.assertNotEqual(manager.open('claude', str(self.folder), False, self.work, thread=room).chat_thread(), room)
        codex = manager.open('codex', str(self.folder), False, self.work)          # Codex — 대화 id 를 처음 알게 된 것은 같은 방
        first = codex.chat_thread()
        codex.conversation = UUID.replace('9', '7')
        self.assertEqual(codex.chat_thread(), first)
        codex.conversation = UUID.replace('9', '5')                                # 다른 대화로 바뀜 — 새 방
        self.assertNotEqual(codex.chat_thread(), first)

    def test_closing_a_tab_or_stopping_all_forgets_but_quitting_the_desk_keeps(self):
        manager = self.manager()
        first = manager.open('claude', str(self.folder), False, self.work)
        manager.open('codex', str(self.folder), False, self.work)
        manager.close(first.id)
        self.assertEqual([row['name'] for row in self.saved()['sessions']], ['codex-1'])
        manager.freeze()                                                           # 데스크를 끝낸다
        manager.close_all()
        self.assertEqual([row['name'] for row in self.saved()['sessions']], ['codex-1'])
        other = agent_term.Manager(self.store)
        self.assertEqual([row['name'] for row in other.saved()['sessions']], ['codex-1'])
        stopping = self.manager()
        stopping.open('claude', str(self.folder), False, self.work)
        stopping.close_all()                                                       # 사람이 '모두 끄기'
        self.assertEqual(self.saved()['sessions'], [])

    def test_a_tab_whose_process_died_stays_listed(self):
        """PC 가 꺼지며 에이전트가 먼저 죽어도 목록에서 빠지지 않는다 — 데스크도 곧 꺼진다."""
        manager = self.manager()
        session = manager.open('claude', str(self.folder), False, self.work)
        session.close()                                                            # 프로세스만 끝났다 (칸은 남았다)
        manager.save()
        self.assertEqual([row['name'] for row in self.saved()['sessions']], ['claude-1'])

    def test_restoring_keeps_name_title_parent_and_resumes(self):
        manager = self.manager()
        with patch.object(agent, 'claude_transcript', return_value=True):
            session = manager.open('claude', str(self.folder), False, self.work, name='claude-3', title='검토',
                                   parent='claude-1', resume=UUID)
            codex = manager.open('codex', str(self.folder), False, self.work, resume=UUID.replace('9', '7'))
        self.assertEqual((session.name, session.title, session.parent), ('claude-3', '검토', 'claude-1'))
        self.assertIn(f'--resume {UUID}', session.script.read_text(encoding='oem'))
        self.assertIn(f'resume {UUID.replace("9", "7")}', codex.script.read_text(encoding='oem'))
        self.assertEqual(manager.open('claude', str(self.folder), False, self.work, name='claude-3').name, 'claude-1')
        self.assertEqual(manager.open('claude', str(self.folder), False, self.work, name='a & calc').name, 'claude-2')
        bad = manager.open('codex', str(self.folder), False, self.work, resume='x & calc')
        self.assertNotIn('calc', bad.script.read_text(encoding='oem'))


class SpawnTests(Room):
    def setUp(self):
        super().setUp()
        self.terms = self.manager()
        self.bridge = agent_bridge.Bridge(self.terms, self.work)
        self.addCleanup(self.bridge.stop)
        self.typed = []
        self.bridge.spawner = lambda parent, tool, folder, title: self.terms.open(
            tool, folder, parent.skip, self.work, team=self.bridge, parent=parent.name, title=title)
        self.parent = self.terms.open('claude', str(self.folder), True, self.work, team=self.bridge)
        read_until(self.parent, 'FAKE-AGENT')
        for patcher in (patch.object(agent_term.Session, 'agent_running', return_value=True),
                        patch.object(agent_term.Session, 'submit', lambda s, text: self.typed.append((s.name, text))),
                        patch.object(agent_bridge, 'READY_WAIT', 5)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, path, body=None, session=None):
        data = json.dumps(body).encode('utf-8') if isinstance(body, dict) else body
        request = urllib.request.Request(self.bridge.url + path, data=data, method='POST' if data is not None else 'GET')
        request.add_header('X-Desk-Token', (session or self.parent).env['DESK_AGENT_TOKEN'])
        request.add_header('Content-Type', 'application/json' if isinstance(body, dict) else 'text/plain')
        try:
            with urllib.request.urlopen(request, timeout=20) as answer:
                return answer.status, answer.read().decode('utf-8')
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode('utf-8')

    def test_a_child_opens_in_its_own_tab_with_the_parents_permissions_and_gets_the_task(self):
        code, text = self.call('/spawn', {'task': '표를 검토해 줘', 'title': '검토', 'folder': 'part'})
        self.assertEqual(code, 200, text)
        child = self.terms.by_name('claude-2')
        self.assertEqual((child.parent, child.title, child.skip, child.folder), ('claude-1', '검토', True, str((self.folder / 'part').resolve())))
        self.assertIn('DESK_AGENT_TOKEN', child.env)                               # 부모에게 결과를 보낼 수 있다
        deadline = time.monotonic() + 15
        while not self.typed and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertEqual(self.typed[0][0], 'claude-2')
        self.assertTrue(self.typed[0][1].startswith('[에이전트 claude-1 의 메시지] 표를 검토해 줘'))
        self.assertIn('/send/claude-1', self.typed[0][1])
        self.assertIn('claude-1', self.call('/agents')[1].split('claude-2')[1].split('\n')[0])   # parent 칸
        self.assertEqual(self.terms.events()['events'][-1]['kind'], 'spawn')
        self.assertEqual(self.saved()['sessions'][1]['parent'], 'claude-1')

    def test_plain_text_body_is_the_task(self):
        code, text = self.call('/spawn', '그냥 글'.encode('utf-8'))
        self.assertEqual(code, 200, text)
        self.assertIn('claude-2', text)

    def test_children_stay_inside_the_parents_folder_and_are_limited(self):
        self.assertEqual(self.call('/spawn', {'folder': '..'})[0], 403)
        self.assertEqual(self.call('/spawn', {'folder': str(self.root)})[0], 403)
        self.assertEqual(self.call('/spawn', {'folder': 'none'})[0], 404)
        self.assertEqual(self.call('/spawn', {'tool': 'bash'})[0], 400)
        with patch.object(agent_bridge, 'CHILD_LIMIT', 1):
            self.assertEqual(self.call('/spawn', {})[0], 200)
            self.assertEqual(self.call('/spawn', {})[0], 429)
        child = self.terms.by_name('claude-2')
        with patch.object(agent_bridge, 'DEPTH_LIMIT', 1):
            self.assertEqual(self.call('/spawn', {}, session=child)[0], 403)        # 자식의 자식은 막는다

    def test_only_the_parent_closes_its_child(self):
        self.call('/spawn', {})
        stranger = self.terms.open('claude', str(self.folder), False, self.work, team=self.bridge)
        self.assertEqual(self.call('/close/claude-2', b'', session=stranger)[0], 403)
        self.assertEqual(self.call('/close/claude-9', b'')[0], 404)
        self.assertEqual(self.call('/close/claude-2', b'')[0], 200)
        self.assertIsNone(self.terms.by_name('claude-2'))

    def test_without_a_spawner_it_is_not_available(self):
        self.bridge.spawner = None
        self.assertEqual(self.call('/spawn', {})[0], 501)


class DesktopRestoreTests(Room):
    def setUp(self):
        super().setUp()
        self.api = DesktopAPI()
        self.api._preferences_path = self.root / 'desktop-preferences.json'
        for patcher in (patch.object(desktop.watcher, 'DATA_DIR', str(self.work)),
                        patch.object(DesktopAPI, '_term_show')):
            self.show = patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.api._terms:
            self.api._terms.close_all()
        if self.api._term_bridge:
            self.api._term_bridge.stop()

    def write(self, rows, window=True):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps({'version': 1, 'window': window, 'sessions': rows}), encoding='utf-8')

    def test_saved_agents_come_back_with_their_conversation_and_the_window(self):
        self.write([{'tool': 'claude', 'folder': str(self.folder), 'skip': True, 'name': 'claude-2', 'title': '작성',
                     'parent': '', 'conversation': UUID, 'remote': '', 'extra': [], 'team': True},
                    {'tool': 'codex', 'folder': str(self.folder / 'part'), 'skip': False, 'name': 'codex-1', 'title': '',
                     'parent': 'claude-2', 'conversation': '', 'remote': '', 'extra': ['--sandbox', 'a & calc'], 'team': True},
                    {'tool': 'claude', 'folder': str(self.root / 'gone'), 'name': 'claude-5'}])
        with patch.object(agent, 'claude_transcript', return_value=True):
            self.assertEqual(self.api._term_restore(), 2)
        rows = self.api.call('term_list')['data']['sessions']
        self.assertEqual([(row['agent'], row['title'], row['skip'], row['parent']) for row in rows],
                         [('claude-2', '작성', True, ''), ('codex-1', 'codex-1', False, 'claude-2')])
        first, second = self.api._terms.sessions()
        self.assertIn(f'--resume {UUID}', first.script.read_text(encoding='oem'))
        self.assertNotIn('calc', second.script.read_text(encoding='oem'))          # 명령으로 읽힐 인자는 버린다
        self.assertIn('--sandbox', second.script.read_text(encoding='oem'))
        self.show.assert_called_once_with(first.id)
        self.assertEqual(self.api._term_restore(), 0)                                # 이미 열려 있으면 다시 열지 않는다

    def test_window_stays_closed_if_it_was_closed_and_restore_can_be_turned_off(self):
        self.write([{'tool': 'claude', 'folder': str(self.folder), 'name': 'claude-1'}], window=False)
        self.api._save_preferences(agent_restore=False)
        self.assertEqual(self.api._term_restore(), 0)
        self.api._save_preferences(agent_restore=True)
        self.assertEqual(self.api._term_restore(), 1)
        self.show.assert_not_called()                                               # 창 없이 켜 둔다 (독에서 다시 연다)
        self.assertEqual(self.api._term_kept(), 1)

    def test_the_desk_quitting_keeps_the_list(self):
        self.api._term_open('claude', str(self.folder), False)
        self.api._close()
        self.assertEqual([row['name'] for row in self.saved()['sessions']], ['claude-1'])

    def test_a_child_spawned_through_the_desk_has_the_parents_mode(self):
        self.api._term_open('claude', str(self.folder), True)
        parent = self.api._terms.sessions()[0]
        child = self.api._term_spawn(parent, 'codex', str(self.folder), '도우미')
        self.assertEqual((child.parent, child.skip, child.title, child.remote), ('claude-1', True, '도우미', ''))
        self.assertIn('DESK_AGENT_TOKEN', child.env)
        self.api._term_child_close(child)
        self.assertEqual(len(self.api._terms.sessions()), 1)



class ResidentTests(Room):
    """상주 에이전트 (2026-10-30 요청) — 에이전트 터미널의 «상주» 단추, «모두 끄기»에도 남고, 데스크가 켜지면 자동으로 열리고, 꺼지면 되살린다."""
    def setUp(self):
        super().setUp()
        self.api = DesktopAPI()
        self.api._preferences_path = self.root / 'desktop-preferences.json'
        for patcher in (patch.object(desktop.watcher, 'DATA_DIR', str(self.work)), patch.object(DesktopAPI, '_term_show')):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.api._shutdown.set()
        if self.api._terms:
            self.api._terms.close_all()
        if self.api._term_bridge:
            self.api._term_bridge.stop()

    def test_manager_keeps_residents_and_one_main_through_stop_all(self):
        manager = self.manager()
        first = manager.open('claude', str(self.folder), False, self.work)
        second = manager.open('claude', str(self.folder), False, self.work)
        third = manager.open('claude', str(self.folder), False, self.work)
        manager.set_resident(first.id, True)
        manager.set_resident(second.id, True)                                       # 여럿 상주
        manager.set_main(first.id, True)
        manager.set_main(second.id, True)                                           # 메인은 하나
        self.assertEqual([(s.resident, s.main) for s in (first, second, third)], [(True, False), (True, True), (False, False)])
        self.assertTrue(self.saved()['sessions'][1]['main'])
        manager.close_all(keep_resident=True)                                       # 사람이 «모두 끄기»
        self.assertEqual([s.name for s in manager.sessions()], ['claude-1', 'claude-2'])
        self.assertTrue(manager.restart(second.id).main)                            # 다시 시작해도 메인
        manager.set_resident(second.id, False)
        self.assertIsNone(manager.main())                                            # 상주를 풀면 메인도
        manager.close_all()                                                          # 데스크를 끝낼 때는 모두
        self.assertEqual(manager.sessions(), [])

    def test_the_button_saves_it_and_the_desk_opens_it_on_start(self):
        self.api._term_open('claude', str(self.folder), True)
        session = self.api._terms.sessions()[0]
        self.assertIn('상주시킵니다', self.api.call('term_resident', {'id': session.id, 'on': True})['data'])
        [spec] = self.api._read_preferences()['agent_residents']
        self.assertEqual((spec['tool'], spec['folder'], spec['skip'], spec['name']), ('claude', str(self.folder), True, 'claude-1'))
        self.assertTrue(self.api.call('term_list')['data']['sessions'][0]['resident'])
        # 데스크를 끄고 다시 켠다 — sessions.json 이 없어도 설정만으로 연다
        self.api._terms.close_all()
        self.store.unlink()
        self.api._terms = None
        self.api._term_resident_ensure({})
        [again] = self.api._terms.sessions()
        self.assertEqual((again.name, again.resident, again.skip), ('claude-1', True, True))
        self.assertIn('DESK_AGENT_TOKEN', again.env)                                 # 휴대폰·다른 에이전트와 주고받을 수 있게

    def test_closing_the_window_with_stop_all_keeps_it_and_closing_it_turns_it_off(self):
        self.api._term_open('claude', str(self.folder), False)
        self.api._term_open('claude', str(self.folder), False)
        resident = self.api._terms.sessions()[0]
        self.api.call('term_resident', {'id': resident.id, 'on': True})
        self.api._terms.close_all(keep_resident=True)                               # 창 닫기 «모두 끄고 닫기»와 같은 길
        self.assertEqual([s.id for s in self.api._terms.sessions()], [resident.id])
        self.assertTrue(self.api.call('term_close', {'id': resident.id})['ok'])     # ✕ — 상주를 풀고 닫는다
        self.assertEqual(self.api._read_preferences()['agent_residents'], [])
        self.api._term_resident_ensure({})
        self.assertEqual(self.api._terms.sessions(), [])                             # 다시 열지 않는다

    def test_a_stopped_resident_is_brought_back(self):
        self.api._term_open('claude', str(self.folder), False)
        session = self.api._terms.sessions()[0]
        self.api.call('term_resident', {'id': session.id, 'on': True})
        session.close()                                                              # 프로세스가 죽었다
        self.api._term_resident_ensure({})
        fresh = self.api._terms.resident()
        self.assertIsNot(fresh, session)
        self.assertEqual((fresh.id, fresh.closed), (session.id, False))
        quiet = {}
        with patch.object(agent_term.Session, 'agent_running', return_value=False):  # 에이전트만 끝났다 — 바로 되살리지 않는다
            self.api._term_resident_ensure(quiet)
            self.assertIs(self.api._terms.resident(), fresh)
            quiet[fresh.id] -= desktop.RESIDENT_REVIVE + 1
            self.api._term_resident_ensure(quiet)
        self.assertIsNot(self.api._terms.resident(), fresh)

    def test_turning_it_off_keeps_the_agent_running(self):
        self.api._term_open('claude', str(self.folder), False)
        session = self.api._terms.sessions()[0]
        self.api.call('term_resident', {'id': session.id, 'on': True})
        self.assertIn('풀었습니다', self.api.call('term_resident', {'id': session.id, 'on': False})['data'])
        self.assertFalse(session.resident)
        self.assertFalse(session.closed)
        self.assertIn('term_resident', desktop.STUDENT_ACTIONS)

class KnowledgeAndMainTests(Room):
    """작업 폴더·지식 · 메인 상주 에이전트의 쪽지 분석 (2026-10-30 요청)."""
    def setUp(self):
        super().setUp()
        self.api = DesktopAPI()
        self.api._preferences_path = self.root / 'desktop-preferences.json'
        for patcher in (patch.object(desktop.watcher, 'DATA_DIR', str(self.work)), patch.object(DesktopAPI, '_term_show')):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.cleanup)
        self.repo = self.root / 'repo'
        self.repo.mkdir()

    def cleanup(self):
        self.api._shutdown.set()
        if self.api._terms:
            self.api._terms.close_all()
        if self.api._term_bridge:
            self.api._term_bridge.stop()

    def test_view_folders_reach_new_agents_with_a_knowledge_index(self):
        from core import knowledge
        self.api._save_preferences(agent_knowledge=[str(self.repo)])
        self.api._term_open('claude', str(self.folder), False)
        session = self.api._terms.sessions()[0]
        script = session.script.read_text(encoding='oem')
        self.assertIn(f'--add-dir "{self.repo}"', script)
        self.assertIn('--append-system-prompt', script)
        index = Path(session.env['DESK_KNOWLEDGE'])
        self.assertIn(str(knowledge.knowledge_file(self.work, str(self.repo))), index.read_text(encoding='utf-8'))
        self.assertTrue(knowledge.knowledge_file(self.work, str(self.repo)).exists())
        listed = self.api.call('term_knowledge')['data']['folders']
        self.assertEqual(listed[0]['folder'], str(self.repo))
        self.assertIn('뺐습니다', self.api.call('term_knowledge_remove', {'folder': str(self.repo)})['data'])
        self.assertFalse((self.work / 'agent' / 'knowledge.md').exists())
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.checked_folder(str(self.repo) + '%PATH%')

    def test_codex_gets_the_instruction_without_the_team_note(self):
        from core import agent_term
        args = agent_term.Manager._knowledge_args('codex', {'knowledge': {'folders': [str(self.repo)]}, 'team_args': ()})
        self.assertEqual(args[:2], ('--add-dir', f'"{self.repo}"'))
        self.assertIn('developer_instructions', args[-1])
        self.assertNotIn('developer_instructions', ' '.join(agent_term.Manager._knowledge_args(
            'codex', {'knowledge': {'folders': [str(self.repo)]}, 'team_args': ('-c', 'x')})))

    def test_main_is_saved_and_analysis_needs_a_main(self):
        self.api._term_open('claude', str(self.folder), False)
        self.api._term_open('claude', str(self.folder), False)
        first, second = self.api._terms.sessions()
        self.api.call('term_resident', {'id': first.id, 'on': True})
        self.api.call('term_resident', {'id': second.id, 'on': True})
        self.assertFalse(self.api.call('term_main_set', {'coolmsg': True})['ok'])  # 메인이 없다
        self.assertIn('메인', self.api.call('term_main', {'id': second.id, 'on': True})['data'])
        specs = self.api._read_preferences()['agent_residents']
        self.assertEqual([(spec['name'], spec['main']) for spec in specs], [('claude-1', False), ('claude-2', True)])
        self.assertTrue(self.api.call('term_main_set', {'coolmsg': True})['ok'])
        state = self.api.call('term_main_state')['data']
        self.assertEqual((state['main']['name'], state['tasks']['coolmsg']), ('claude-2', True))
        with patch.object(DesktopAPI, '_analyst') as analyst:
            self.api._coolmsg_received({'key': 1, 'sender': '김교사', 'body': '내일까지 제출'})
        analyst.return_value.offer.assert_called_once()
        # 데스크를 다시 켜면 상주 둘이 열리고 메인도 그대로
        self.api._terms.close_all()
        self.api._terms = None
        self.api._term_resident_ensure({})
        self.assertEqual(sorted((s.name, s.main) for s in self.api._terms.sessions()), [('claude-1', False), ('claude-2', True)])

    def test_the_first_single_resident_setting_is_carried_over(self):
        self.api._save_preferences(agent_resident={'on': True, 'tool': 'claude', 'folder': str(self.folder), 'name': 'claude-4'})
        self.assertEqual(self.api._main_spec()['name'], 'claude-4')


class SkillPanelTests(Room):
    """오른쪽 스킬 패널 · 기본 스킬(바탕화면 정리) · 즐겨찾기 (2026-10-30 요청)."""
    def setUp(self):
        super().setUp()
        self.api = DesktopAPI()
        self.api._preferences_path = self.root / 'desktop-preferences.json'
        self.home = self.root / 'home'
        self.api._save_preferences(automation_folder=str(self.root / '자동화 업무'))

    def test_general_skill_installs_for_both_agents_without_touching_users_own(self):
        from core import automation
        own = self.home / '.claude' / 'skills' / 'desktop-cleanup'
        own.mkdir(parents=True)
        (own / 'SKILL.md').write_text('사용자가 만든 것', encoding='utf-8')
        states = automation.install_general(self.home)[0]['states']
        self.assertEqual(states, {'.claude/skills': 'foreign', '.codex/skills': 'installed'})
        self.assertEqual((own / 'SKILL.md').read_text(encoding='utf-8'), '사용자가 만든 것')
        self.assertIn('지우지 않는다', (self.home / '.codex' / 'skills' / 'desktop-cleanup' / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertEqual(automation.install_general(self.home)[0]['states']['.codex/skills'], 'current')

    def test_panel_lists_skills_with_actions_and_keeps_favorites(self):
        from core import automation
        data = self.api.call('term_skills')['data']
        cleanup = next(skill for skill in data['general'] if skill['name'] == 'desktop-cleanup')
        self.assertEqual(cleanup['title'], '바탕화면 정리')
        self.assertTrue(cleanup['usable'])
        self.assertGreaterEqual(len(cleanup['actions']), 5)
        self.assertTrue(all(not skill['usable'] for skill in data['automation']))      # 자동화 업무에 아직 안 깔렸다
        self.assertTrue(all(skill['actions'] for skill in data['automation']))
        automation.install(Path(self.root / '자동화 업무'), only={'neis'})
        neis = next(skill for skill in self.api.call('term_skills')['data']['automation'] if skill['name'] == 'neis')
        self.assertTrue(neis['usable'])
        self.api._save_preferences(automation_off=['neis'])
        self.assertNotIn('neis', [skill['name'] for skill in self.api.call('term_skills')['data']['automation']])
        action = cleanup['actions'][0]
        favs = self.api.call('term_skill_favorite', {'skill': 'desktop-cleanup', **action, 'on': True})['data']
        self.assertEqual(favs, [{'skill': 'desktop-cleanup', **action}])
        self.api.call('term_skill_favorite', {'skill': 'desktop-cleanup', **action, 'on': True})
        self.assertEqual(len(self.api._skill_favorites()), 1)                          # 같은 것은 한 번
        self.assertEqual(self.api.call('term_skill_favorite', {'skill': 'desktop-cleanup', **action, 'on': False})['data'], [])
        self.assertFalse(self.api.call('term_skill_favorite', {'skill': 'x', 'label': '', 'prompt': 'p', 'on': True})['ok'])


class AnalystTests(Room):
    """쿨메신저 쪽지 분석 — Haiku 실행은 가짜로 바꾼다."""
    def setUp(self):
        super().setUp()
        from core import resident_tasks
        self.resident_tasks = resident_tasks
        self.sent, self.notes, self.calls = [], [], []
        self.reply = {'has_task': True, 'task': '수행평가 계획서 제출', 'deadline': '11월 3일', 'related': 'yes',
                      'related_why': '교무 업무분장에 평가 담당', 'ai': 'partly', 'ai_how': '양식 채우기는 에이전트가'}

        def run(args, **kwargs):
            self.calls.append((args, kwargs))
            outer = {'result': '분석:\n' + json.dumps(self.reply, ensure_ascii=False)}
            return subprocess.CompletedProcess(args, 0, json.dumps(outer), '')
        self.analyst = resident_tasks.Analyst(self.work, spec=lambda: {'folder': str(self.folder), 'name': 'claude-1'},
                                              folders=lambda: [str(self.folder)], enabled=lambda: True,
                                              send=lambda *args: self.sent.append(args),
                                              note=lambda text, data=None: self.notes.append((text, data)), run=run)

    def test_a_task_is_analysed_with_haiku_read_only_and_sent_as_a_notice(self):
        with patch.object(agent, 'find', return_value='C:/claude.exe'):
            entry = self.analyst.handle({'key': 7, 'sender': '김교사', 'when': '2026-10-30 09:00', 'body': '평가 계획서를 3일까지 제출해 주세요'})
        self.assertTrue(entry['notified'])
        args, kwargs = self.calls[0]
        self.assertEqual(args[args.index('--model') + 1], 'haiku')
        self.assertIn('mcp__spacekijun__read_data', args)
        self.assertNotIn('mcp__spacekijun__send_message', args)
        self.assertIn('Bash', args[args.index('--disallowedTools'):])
        self.assertIn('평가 계획서', kwargs['input'])
        self.assertEqual(kwargs['cwd'], str(self.folder))
        title, text, meta = self.sent[0]
        self.assertEqual(title, '수행평가 계획서 제출 · ~11월 3일')                   # 무엇을 · 언제까지
        self.assertEqual(text, '할 일: 수행평가 계획서 제출\n기한: 11월 3일\n근거: 교무 업무분장에 평가 담당\n'
                               'AI 조언: 양식 채우기는 에이전트가\n보낸 사람: 김교사')
        self.assertEqual((meta['kind'], meta['message_key']), ('coolmessenger_analysis', 7))
        log = self.analyst.recent()[0]
        self.assertNotIn('body', log)                                               # 본문은 남기지 않는다
        self.assertEqual(log['task'], '수행평가 계획서 제출')

    def test_personal_data_is_not_sent_anywhere(self):
        for body in ('3학년 2반 14번 학생 결석 확인', '학부모 연락처 010-1234-5678', '30214 김민수 보충', '박소이 학생 상담 기록 정리', '홍길동 학생 성적 확인 바랍니다'):
            entry = self.analyst.handle({'key': 1, 'sender': '교사', 'body': body})
            self.assertTrue(entry['skipped'].startswith('개인정보'), body)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.sent, [])

    def test_notice_has_only_what_is_needed(self):
        self.reply = {**self.reply, 'related': 'no'}                                # 내 일 아님 → 알림 없이 기록만
        with patch.object(agent, 'find', return_value='C:/claude.exe'):
            entry = self.analyst.handle({'key': 3, 'sender': '교사', 'body': '3학년 담임 선생님들은 진로 자료를 내 주세요'})
        self.assertNotIn('notified', entry)
        self.assertEqual(self.sent, [])
        self.assertIn('내 일 아님', self.notes[-1][0])
        self.reply = {**self.reply, 'related': 'unclear', 'deadline': '', 'ai': 'no', 'ai_how': '사람이', 'task': '가' * 200}
        with patch.object(agent, 'find', return_value='C:/claude.exe'):
            self.analyst.handle({'key': 4, 'sender': '교사', 'body': '자료를 내 주세요'})
        title, text, _ = self.sent[0]
        self.assertLessEqual(len(title), 60)                                         # 길면 잘라 …
        self.assertTrue(title.endswith('…'))
        self.assertNotIn('AI', text)                                                  # AI 도움이 없으면 그 줄을 뺀다
        self.assertNotIn('기한', text)                                                # 기한은 있을 때만
        self.assertIn('근거: 확인 필요', text)
        self.sent.clear()
        self.reply = {'has_task': True, 'related': 'audience', 'related_why': '출제 교사', 'ai': 'yes', 'ai_how': 'neis-exam-ratio 로 확인',
                      'tasks': [{'task': '원안 제출', 'deadline': '12/1(화)'}, {'task': '수행평가 입력', 'deadline': ''}]}
        with patch.object(agent, 'find', return_value='C:/claude.exe'):
            entry = self.analyst.handle({'key': 5, 'sender': '평가계', 'body': '원안 제출과 수행평가 입력 부탁드립니다'})
        title, text, _ = self.sent[0]
        self.assertEqual(title, '원안 제출 외 1건 · ~12/1(화)')                        # 여럿이면 나눠 쓴다
        self.assertEqual(text, '할 일 1: 원안 제출\n기한: 12/1(화)\n할 일 2: 수행평가 입력\n근거: 출제 교사\n'
                               'AI 조언: neis-exam-ratio 로 확인\n보낸 사람: 평가계')
        self.assertEqual(entry['task'], '원안 제출')                                   # 첫 할 일 = 터미널 목록의 칸

    def test_no_task_no_notice_and_bad_output_is_an_error(self):
        self.reply = {'has_task': False}
        with patch.object(agent, 'find', return_value='C:/claude.exe'):
            self.assertNotIn('notified', self.analyst.handle({'key': 2, 'sender': '교사', 'body': '수고하셨습니다'}))
        self.assertEqual(self.sent, [])
        with self.assertRaises(ValueError):
            self.resident_tasks.parse_reply(json.dumps({'result': '모르겠습니다'}))

    def test_an_analysis_can_be_handed_to_the_chosen_agent(self):
        with patch.object(agent, 'find', return_value='C:/claude.exe'):
            self.analyst.handle({'key': 7, 'sender': '김교사', 'when': '2026-10-30 09:00', 'body': '평가 계획서를 3일까지 제출해 주세요'})
        self.analyst.handle({'key': 8, 'sender': '교사', 'body': '학부모 연락처 010-1234-5678'})
        self.assertEqual([data for _, data in self.notes], [{'key': 7, 'handoff': True}, {'key': 8, 'handoff': False}])
        self.assertIsNone(self.analyst.find(8))                                     # 개인정보로 건너뛴 것은 맡기지 않는다
        row = self.analyst.find(7)
        text = self.resident_tasks.handoff({'sender': '김교사', 'when': '2026-10-30 09:00', 'body': '평가 계획서를 3일까지 제출해 주세요'}, row)
        self.assertIn('평가 계획서를 3일까지', text)
        self.assertIn('할 일: 수행평가 계획서 제출', text)
        self.assertIn('확인받은 뒤', text)
        with self.assertRaises(ValueError):                                        # 다시 읽은 원문에 개인정보가 보이면 넘기지 않는다
            self.resident_tasks.handoff({'sender': '김교사', 'body': '연락처 010-1234-5678'}, row)

    def test_clean_messages_pass_the_guard(self):
        from core import privacy_guard
        self.assertTrue(privacy_guard.is_safe('내일 3교시 회의실에서 교과협의회가 있습니다. 자료는 공유 폴더에 올려 주세요.'))
        self.assertEqual(privacy_guard.findings('주민번호 900101-1234567'), ['주민등록번호'])

    def test_guard_blocks_personal_data_not_work_topics(self):
        """«성적»«상담» 낱말만으로 막지 않는다 — 특정한 사람에게 붙을 때만 (2026-11-05, 성적처리 일정 쪽지가 막힘)."""
        from core import privacy_guard
        for clean in ('2차 정기시험 후 학기말 성적처리: 12월 18일 ~ 22일. 방학식 전에 학생들이 성적표를 받도록 하겠습니다.',
                      '정태오 선생님 성적처리 확인 부탁드립니다', '2학년 상담주간 운영 안내', '이번주 학생 건강검진 일정',
                      '학생회 성적우수 장학금 안내', '장애인식 개선 교육 안내'):
            self.assertTrue(privacy_guard.is_safe(clean), clean)
        for text, name in (('홍길동 학생 성적이 많이 떨어졌습니다', '성적'), ('김민수 85점, 박하준 92점', '성적'),
                           ('박소이 학생 상담 내용 공유', '상담'), ('최영희 선생님 병원 진료로 조퇴합니다', '건강'),
                           ('3학년 2반 5번 결석', '학년·반·번호'), ('김지은 학생 학폭 관련', '학교폭력·징계')):
            self.assertIn(name, privacy_guard.findings(text), text)


if __name__ == '__main__':
    unittest.main()
