"""다른 PC 의 에이전트와 메시지 (2026-10-27 요청) — 두 데스크(A·B)를 가짜 서버로 잇고 허락·결과·중계 길을 본다.

진짜 서버 규칙(교직원만·한도·만료)은 spacekijun `supabase/tests/desk_agent_peer.sql` 이 운영 DB 에서 본다.
여기 가짜 서버는 그 함수들의 모양만 흉내 낸다.
"""
from test_sandbox import use_sandbox
use_sandbox()
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

import desktop
from core import agent, agent_bridge, agent_peer, agent_term
from desktop import DesktopAPI


class FakeServer:
    """desk_agent_* 함수의 모양 — 보내기는 받는 PC 가 알린 에이전트에게만, 답은 받아 들인 것에만, is_reply 는 서버가 정한다."""
    def __init__(self):
        self.peers, self.messages, self.calls = {}, {}, []

    def rpc_for(self, rid, name):
        def call(fn, body):
            self.calls.append((rid, fn))
            return getattr(self, fn)(rid, name, body)
        return call

    def desk_agent_beat(self, rid, name, body):
        self.peers[(rid, body['p_device'])] = {'resource_id': rid, 'name': name, 'device': body['p_device'],
                                               'label': body['p_label'], 'agents': body['p_agents'],
                                               'cross': body.get('p_cross', True)}
        inbox = []
        for m in self.messages.values():
            if m['to'] == (rid, body['p_device']) and m['status'] == 'sent':
                original = self.messages.get(m['reply_to'])
                is_reply = bool(original and original['from'] == (rid, body['p_device']) and original['agent_from'] == m['agent_to'])
                from_phone = m['from'][0] == rid and m['from'][1].startswith('phone:') and not is_reply
                from_own_pc = m['from'][0] == rid and len(m['from'][1]) == 32 and m['from'][1] != body['p_device']
                inbox.append({'id': m['id'], 'body': m['body'], 'agent': m['agent_to'], 'reply_to': m['reply_to'], 'is_reply': is_reply,
                              'thread': m.get('thread'),
                              'from_phone': from_phone, 'from_own_pc': from_own_pc, 'sender': {'resource_id': m['from'][0], 'name': m['name_from'], 'label': m['label_from'],
                                         'device': m['from'][1], 'agent': m['agent_from']}})
        return {'me': f'{name} 선생님', 'inbox': inbox}

    def desk_agent_leave(self, rid, name, body):
        self.peers.pop((rid, body['p_device']), None)
        return {'ok': True}

    def desk_agent_directory(self, rid, name, body):
        return [{**peer, 'mine': peer['resource_id'] == rid} for key, peer in self.peers.items()
                if key != (rid, body['p_device']) and peer['agents'] and peer['cross']]

    def _add(self, rid, name, device, agent_from, to, agent_to, text, reply_to=None):
        mid = str(uuid.uuid4())
        self.messages[mid] = {'id': mid, 'from': (rid, device), 'name_from': name, 'label_from': self.peers[(rid, device)]['label'],
                              'agent_from': agent_from, 'to': to, 'agent_to': agent_to, 'body': text, 'reply_to': reply_to,
                              'status': 'sent', 'note': None}
        return mid

    def phone_send(self, rid, name, phone, to_device, agent_to, text, thread=None):
        """스페이스기전 모바일 «에이전트» 탭 — 내 휴대폰에서 내 PC 의 에이전트에게 (서버의 모바일 보내기 함수 모양).
        thread — 채팅방(그 칸의 대화) id. 보낼 때 그 방이 열려 있는지는 서버가 보지만, 그 사이 닫히면 데스크가 거른다."""
        mid = str(uuid.uuid4())
        self.messages[mid] = {'id': mid, 'from': (rid, 'phone:' + phone), 'name_from': name, 'label_from': '휴대폰',
                              'agent_from': 'phone', 'to': (rid, to_device), 'agent_to': agent_to, 'body': text,
                              'reply_to': None, 'status': 'sent', 'note': None, 'thread': thread}
        return mid

    def desk_agent_own_send(self, rid, name, body):
        """«내 다른 PC» 방 — 이 데스크 화면이 내 다른 PC 의 에이전트에게 (서버 20261112150000 모양, cross 는 보지 않는다)."""
        peer = self.peers.get((rid, body['p_to_device']))
        if body['p_device'] == body['p_to_device'] or not peer or not any(a['name'] == body['p_to_agent'] for a in peer['agents']):
            raise RuntimeError('그 PC 에 그 이름의 에이전트가 열려 있지 않습니다')
        mid = self._add(rid, name, body['p_device'], 'desk', (rid, body['p_to_device']), body['p_to_agent'], body['p_body'])
        self.messages[mid]['thread'] = body.get('p_thread')
        return {'id': mid, 'label': peer['label'], 'agent': body['p_to_agent']}

    def desk_agent_own_overview(self, rid, name, body):
        return {'pcs': [p for (r, d), p in self.peers.items() if r == rid and d != body['p_device']],
                'messages': [{'id': m['id'], 'body': m['body'], 'replies': [r['body'] for r in self.messages.values() if r['reply_to'] == m['id']]}
                             for m in self.messages.values() if m['from'] == (rid, body['p_device']) and m['agent_from'] == 'desk']}

    def desk_agent_send(self, rid, name, body):
        peer = self.peers.get((body['p_to_resource'], body['p_to_device']))
        if not peer or not any(a['name'] == body['p_to_agent'] for a in peer['agents']):
            raise RuntimeError('받는 PC 에 그 이름의 에이전트가 열려 있지 않습니다')
        if not peer['cross']:
            raise RuntimeError('받는 PC 가 «다른 PC» 메시지를 받지 않습니다')
        mid = self._add(rid, name, body['p_device'], body['p_agent'], (body['p_to_resource'], body['p_to_device']),
                        body['p_to_agent'], body['p_body'])
        return {'id': mid, 'to': peer['name'], 'label': peer['label'], 'agent': body['p_to_agent']}

    def desk_agent_reply(self, rid, name, body):
        original = self.messages[body['p_message']]
        if original['to'] != (rid, body['p_device']) or original['status'] != 'delivered':
            raise RuntimeError('받아 들인 메시지에만 답할 수 있습니다')
        mid = self._add(rid, name, body['p_device'], body['p_agent'], original['from'], original['agent_from'], body['p_body'],
                        reply_to=original['id'])
        return {'id': mid, 'to': original['name_from'], 'label': original['label_from'], 'agent': original['agent_from']}

    def desk_agent_ack(self, rid, name, body):
        m = self.messages[body['p_message']]
        if m['to'] == (rid, body['p_device']) and m['status'] == 'sent':
            m['status'], m['note'] = body['p_status'], body['p_note']
        return {'ok': True}

    def desk_agent_status(self, rid, name, body):
        return [{'id': m['id'], 'status': m['status'], 'note': m['note'],
                 'replies': [{'id': r['id']} for r in self.messages.values() if r['reply_to'] == m['id']]}
                for m in self.messages.values() if m['id'] in body['p_ids'] and m['from'] == (rid, body['p_device'])]


class Desk:
    """데스크 하나 — 진짜 Manager·Bridge 에 가짜 서버로 이은 Link. 넣은 글은 typed 에 쌓인다."""
    def __init__(self, test, room, server, rid, name, device, label):
        self.manager = agent_term.Manager()
        test.addCleanup(self.manager.close_all)
        self.choice = set()
        self.bridge = agent_bridge.Bridge(self.manager, Path(room), choice=lambda s: s.name in self.choice)
        test.addCleanup(self.bridge.stop)
        self.on, self.trusted, self.answers, self.asked, self.phone, self.cross = True, set(), [], [], True, True

        def approve(message, target):
            self.asked.append((message['sender']['name'], target.name))
            return self.answers.pop(0) if self.answers else None
        self.link = agent_peer.Link(self.manager, server.rpc_for(rid, name), self.bridge.status, device, label,
                                    enabled=lambda: self.on, approve=approve, trusted=lambda r: r in self.trusted,
                                    phone=lambda: self.phone, cross=lambda: self.cross)
        self.bridge.peer = self.link
        folder = Path(room) / f'w-{label}'
        folder.mkdir()
        self.agent = self.manager.open('claude', str(folder), False, Path(room), team=self.bridge)
        self.typed = []

    def beat(self, wait_asks=True):
        self.link.beat_once()
        if wait_asks:
            for _ in range(100):                        # 묻는 스레드가 끝나기를
                if not self.link._asking:
                    break
                time.sleep(0.02)
            self.link.beat_once()                       # 허락 뒤 ack 보내기

    def call(self, path, body=None):
        data = body.encode('utf-8') if isinstance(body, str) else body
        request = urllib.request.Request(self.bridge.url + path, data=data, method='POST' if data is not None else 'GET')
        request.add_header('X-Desk-Token', self.agent.env['DESK_AGENT_TOKEN'])
        try:
            with urllib.request.urlopen(request, timeout=15) as answer:
                return answer.status, answer.read().decode('utf-8')
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode('utf-8')


class PeerTests(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        exe = Path(self.room.name) / 'fake.cmd'
        exe.write_text('@echo off\r\necho READY\r\n', encoding='ascii')
        self.typed = []
        for patcher in (patch.object(agent, 'find', return_value=str(exe)),
                        patch.object(agent_term.Session, 'agent_running', return_value=True),
                        patch.object(agent_term.Session, 'submit', lambda s, text: self.typed.append((s.name, s.env.get('DESK_AGENT_TOKEN'), text)))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = FakeServer()
        self.a = Desk(self, self.room.name, self.server, 'ra', '김교사', 'a' * 32, 'A-PC')
        self.b = Desk(self, self.room.name, self.server, 'rb', '이교사', 'b' * 32, 'B-PC')

    def typed_to(self, desk):
        return [text for name, token, text in self.typed if token == desk.agent.env['DESK_AGENT_TOKEN']]

    def send_a_to_b(self, text='표를 검토해 주세요'):
        self.a.beat(); self.b.beat()
        code, peers = self.a.call('/peers')
        self.assertEqual(code, 200, peers)
        self.assertIn(f'bbbbbb/claude-1\t이교사\tB-PC\tclaude-1', peers)
        code, answer = self.a.call('/peer/send/bbbbbb/claude-1', text)
        self.assertEqual(code, 200, answer)
        return answer.split('id ')[1].split(' ')[0]

    def test_request_asks_per_person_then_result_comes_back_to_the_waiting_sender(self):
        self.b.answers = ['once']
        mid = self.send_a_to_b()
        self.b.beat()
        self.assertEqual(self.b.asked, [('김교사', 'claude-1')])
        [got] = self.typed_to(self.b)
        self.assertIn('(from another PC) — 김교사 선생님 · A-PC 의 claude-1', got)
        self.assertIn('표를 검토해 주세요', got)
        self.assertIn(f'/peer/reply/{mid}', got)
        self.assertEqual(self.server.messages[mid]['status'], 'delivered')

        result = {}
        waiter = threading.Thread(target=lambda: result.update(answer=self.a.call(f'/peer/wait/{mid}?timeout=20')))
        waiter.start()
        time.sleep(0.3)
        code, text = self.b.call(f'/peer/reply/{mid}', '2행 합계가 틀립니다')
        self.assertEqual(code, 200, text)
        for _ in range(50):                             # A 의 beat 가 결과를 가져가 기다리던 쪽에 준다
            self.a.beat()
            if not waiter.is_alive():
                break
            time.sleep(0.1)
        waiter.join(5)
        code, text = result['answer']
        self.assertEqual(code, 200, text)
        self.assertIn('result received', text)
        self.assertIn('2행 합계가 틀립니다', text)
        self.assertEqual(self.typed_to(self.a), [])     # 기다리던 결과는 입력칸에 넣지 않는다
        kinds = [event['kind'] for event in self.a.manager.events()['events']]
        self.assertEqual(kinds, ['peer-out', 'peer-in'])

        mid2 = self.send_a_to_b('하나 더')             # '이번만' — 이 창을 닫을 때까지 같은 사람은 묻지 않는다
        self.b.beat()
        self.assertEqual(len(self.b.asked), 1)
        self.assertEqual(self.server.messages[mid2]['status'], 'delivered')
        self.b.link.forget()                            # 창을 닫았다 — 다시 묻는다
        self.send_a_to_b('또 하나')
        self.b.beat()
        self.assertEqual(len(self.b.asked), 2)

    def test_result_while_not_waiting_is_typed_into_the_sender(self):
        self.b.trusted.add('ra')                        # '항상' 허락한 사람 — 묻지 않는다
        mid = self.send_a_to_b()
        self.b.beat()
        self.assertEqual(self.b.asked, [])
        self.assertEqual(self.b.call(f'/peer/reply/{mid}', '끝났습니다')[0], 200)
        self.a.beat()
        [got] = self.typed_to(self.a)
        self.assertIn('(result from another PC) — 이교사 선생님 · B-PC 의 claude-1', got)
        self.assertIn(f'보낸 메시지 {mid} 에 대한 답', got)
        code, text = self.a.call(f'/peer/wait/{mid}?timeout=2')   # 나중에 기다려도 받은 결과를 돌려준다
        self.assertIn('also typed into your input earlier', text)
        result_id = got.split('· id ')[1].split(']')[0]
        self.assertEqual(self.a.call(f'/peer/reply/{result_id}', '고마워요')[0], 200)   # 결과에 이어 답하기
        self.b.beat()
        self.assertEqual(self.b.asked, [])                         # 내가 보낸 결과에 대한 답 — 묻지 않는다
        self.assertIn('(result from another PC)', self.typed_to(self.b)[-1])

    def test_refusal_and_skip_mode_and_held_while_a_choice_is_open(self):
        mid = self.send_a_to_b()                        # 답 없음 = 거절
        self.b.beat()
        self.assertEqual(self.server.messages[mid]['status'], 'refused')
        self.assertEqual(self.typed_to(self.b), [])
        code, text = self.a.call(f'/peer/wait/{mid}?timeout=3')
        self.assertIn('status: refused', text)
        mid2 = self.send_a_to_b('다시')                  # 거절한 사람은 잠시 묻지 않고 거절
        self.b.beat()
        self.assertEqual(len(self.b.asked), 1)
        self.assertEqual(self.server.messages[mid2]['status'], 'refused')

        self.b.link._refused.clear()
        self.b.trusted.add('ra')
        self.b.agent.skip = True                        # 권한 묻지 않기 — '항상'이어도 묻는다
        self.b.answers = ['once']
        self.send_a_to_b('스킵 모드')
        self.b.beat()
        self.assertEqual(len(self.b.asked), 2)

        self.b.agent.skip = False
        self.b.choice.add('claude-1')                   # 선택지를 띄워 두었다 — 넣지 않고 들고 있는다
        mid3 = self.send_a_to_b('선택지')
        self.b.beat()
        self.assertEqual(self.server.messages[mid3]['status'], 'sent')
        before = len(self.typed_to(self.b))
        self.b.beat()
        self.assertEqual(len(self.typed_to(self.b)), before)
        self.b.choice.clear()
        self.b.beat()
        self.assertEqual(self.server.messages[mid3]['status'], 'delivered')
        self.assertIn('선택지', self.typed_to(self.b)[-1])

    def test_off_leaves_the_list_and_the_relay_refuses(self):
        self.a.beat(); self.b.beat()
        self.b.on = False
        self.b.beat()
        self.assertNotIn(('rb', 'b' * 32), self.server.peers)
        self.assertEqual(self.b.call('/peers')[0], 503)
        self.assertEqual(self.a.call('/peer/send/bbbbbb/claude-1', 'x')[0], 404)
        self.assertEqual(self.a.call('/peer/send/bbbbbb/claude-1', '   ')[0], 400)
        self.assertEqual(self.a.call('/peer/reply/nope', 'x')[0], 404)
        self.assertEqual(self.a.call('/read/claude-1')[0], 200)          # 이 PC 안의 읽기는 그대로
        self.assertEqual(self.a.call('/peer/read/bbbbbb/claude-1')[0], 404)   # 다른 PC 화면 읽기는 길이 없다
        self.a.bridge.peer = None
        self.assertEqual(self.a.call('/peers')[0], 501)

    def test_my_phone_is_delivered_without_asking_even_in_skip_mode_and_gets_the_reply(self):
        """스페이스기전 모바일에서 내가 보낸 것 — PC 앞에 없으니 묻지 않는다 (2026-10-29 요청)."""
        self.b.beat()
        self.b.agent.skip = True
        mid = self.server.phone_send('rb', '이교사', 'c' * 32, 'b' * 32, 'claude-1', '오늘 받은 공문 정리해 줘')
        self.b.beat()
        self.assertEqual(self.b.asked, [])
        self.assertEqual(self.server.messages[mid]['status'], 'delivered')
        [got] = self.typed_to(self.b)
        self.assertIn("(from the user's phone) — id " + mid, got)
        self.assertIn('오늘 받은 공문 정리해 줘', got)
        self.assertIn(f'/peer/reply/{mid}', got)
        event = self.b.manager.events()['events'][-1]
        self.assertEqual((event['kind'], event['fromName']), ('peer-in', '내 휴대폰'))
        code, text = self.b.call(f'/peer/reply/{mid}', '세 건 정리했습니다')
        self.assertEqual(code, 200, text)
        [reply] = [m for m in self.server.messages.values() if m['reply_to'] == mid]
        self.assertEqual((reply['to'], reply['agent_to']), (('rb', 'phone:' + 'c' * 32), 'phone'))   # 휴대폰으로 돌아간다

    def test_my_other_pc_room_is_delivered_without_asking_and_the_answer_stays_in_the_room(self):
        """«내 다른 PC» (2026-11-12 요청) — 같은 사람의 다른 PC 데스크 화면에서 보낸 것은 휴대폰처럼 묻지 않고,
        답은 보낸 PC 의 칸에 넣지 않고 그 화면의 방(overview)에 남는다. 다른 선생님 것과 섞이지 않는다."""
        home = Desk(self, self.room.name, self.server, 'rb', '이교사', 'c' * 32, 'B-집')
        home.beat(); self.b.beat()
        self.b.agent.skip = True
        self.b.cross = False                               # «다른 선생님»을 꺼도 내 PC 는 받는다
        sent = home.link.own_send('b' * 32, 'claude-1', '집에서 부탁', thread=self.b.agent.chat_thread())
        mid = sent['id']
        self.b.beat()
        self.assertEqual(self.b.asked, [])
        self.assertEqual(self.server.messages[mid]['status'], 'delivered')
        [got] = self.typed_to(self.b)
        self.assertIn("from the user's other PC «B-집»", got)
        self.assertIn(f'/peer/reply/{mid}', got)
        self.assertEqual(self.b.manager.events()['events'][-1]['fromName'], '내 다른 PC · B-집')
        code, text = self.b.call(f'/peer/reply/{mid}', '끝냈습니다')
        self.assertEqual(code, 200, text)
        before = len(self.typed)
        home.beat()
        self.assertEqual(len(self.typed), before)          # 집 PC 의 칸에는 넣지 않는다
        [reply] = [m for m in self.server.messages.values() if m['reply_to'] == mid]
        self.assertEqual(reply['status'], 'delivered')
        overview = home.link.own_overview()
        self.assertEqual(overview['news'], 1)
        self.assertEqual(overview['messages'][0]['replies'], ['끝냈습니다'])
        self.assertEqual([p['label'] for p in overview['pcs']], ['B-PC'])

    def test_my_other_pc_room_works_on_a_pc_with_no_agents_open(self):
        """에이전트를 하나도 열지 않은 PC 에서도 «내 다른 PC» 방이 연결된다 (2026-11-13 — «not connected to SPACEKIJUN yet» 이 계속 떴다).
        «내 기기»를 끄면 에이전트 없는 PC 는 목록에서 빠진다."""
        home = Desk(self, self.room.name, self.server, 'rb', '이교사', 'c' * 32, 'B-집')
        home.agent.close()
        self.b.beat()
        home.beat()
        self.assertTrue(home.link.active)
        self.assertEqual(self.server.peers[('rb', 'c' * 32)]['agents'], [])
        self.assertEqual([p['label'] for p in home.link.own_overview()['pcs']], ['B-PC'])
        mid = home.link.own_send('b' * 32, 'claude-1', '집에서 부탁', thread=self.b.agent.chat_thread())['id']
        self.b.beat()
        self.assertEqual(self.server.messages[mid]['status'], 'delivered')
        home.phone = False
        home.beat()
        self.assertFalse(home.link.active)
        self.assertNotIn(('rb', 'c' * 32), self.server.peers)

    def test_my_other_pc_is_refused_when_my_devices_are_off(self):
        home = Desk(self, self.room.name, self.server, 'rb', '이교사', 'c' * 32, 'B-집')
        home.beat(); self.b.beat()
        self.b.phone = False
        mid = home.link.own_send('b' * 32, 'claude-1', '집에서')['id']
        self.b.beat()
        self.assertEqual(self.server.messages[mid]['status'], 'refused')
        self.assertIn('내 기기', self.server.messages[mid]['note'])
        home.phone = False
        with self.assertRaises(agent_peer.PeerError):
            home.link.own_send('b' * 32, 'claude-1', '집에서')

    def test_phone_chat_room_is_the_conversation_not_the_name(self):
        """휴대폰 채팅방 (2026-11-10 요청) — 같은 이름으로 다시 연 칸·/clear 한 칸에 끝난 방의 메시지를 넣지 않는다."""
        self.b.beat()
        [listed] = self.server.peers[('rb', 'b' * 32)]['agents']
        room = listed['thread']
        self.assertEqual(room, self.b.agent.chat_thread())
        ok = self.server.phone_send('rb', '이교사', 'c' * 32, 'b' * 32, 'claude-1', '첫 방', thread=room)
        self.b.beat()
        self.assertEqual(self.server.messages[ok]['status'], 'delivered')
        # 칸을 닫고 같은 이름으로 새로 연다 — 이름은 claude-1 그대로, 방은 새것
        folder = self.b.agent.folder
        self.b.manager.close(self.b.agent.id)
        self.b.agent = self.b.manager.open('claude', folder, False, Path(self.room.name), team=self.b.bridge)
        self.assertEqual(self.b.agent.name, 'claude-1')
        self.assertNotEqual(self.b.agent.chat_thread(), room)
        old = self.server.phone_send('rb', '이교사', 'c' * 32, 'b' * 32, 'claude-1', '끝난 방에 보냄', thread=room)
        self.b.beat()
        self.assertEqual(self.server.messages[old]['status'], 'refused')
        self.assertIn('대화는 끝났습니다', self.server.messages[old]['note'])
        self.assertFalse(any('끝난 방에 보냄' in text for text in self.typed_to(self.b)))
        # /clear — 훅이 새 대화 id 를 적으면 방도 바뀐다
        fresh = self.b.agent.chat_thread()
        Path(self.b.agent.conversation_file).write_text(str(uuid.uuid4()), encoding='utf-8')
        self.assertNotEqual(self.b.agent.chat_thread(), fresh)
        cleared = self.server.phone_send('rb', '이교사', 'c' * 32, 'b' * 32, 'claude-1', '/clear 앞 방', thread=fresh)
        self.b.beat()
        self.assertEqual(self.server.messages[cleared]['status'], 'refused')
        # 방 없이 온 것(옛 휴대폰 화면)은 예전처럼 이름으로
        legacy = self.server.phone_send('rb', '이교사', 'c' * 32, 'b' * 32, 'claude-1', '옛 화면')
        self.b.beat()
        self.assertEqual(self.server.messages[legacy]['status'], 'delivered')

    def test_my_phone_is_refused_when_turned_off(self):
        self.b.beat()
        self.b.phone = False
        mid = self.server.phone_send('rb', '이교사', 'c' * 32, 'b' * 32, 'claude-1', '하나 더')
        self.b.beat()
        self.assertEqual(self.server.messages[mid]['status'], 'refused')
        self.assertIn('내 휴대폰에서 받기', self.server.messages[mid]['note'])
        self.assertEqual((self.b.asked, self.typed_to(self.b)), ([], []))

    def test_someone_elses_phone_is_not_treated_as_mine(self):
        """from_phone 은 보낸 이 = 받는 이일 때만 — 남의 휴대폰은 보통의 요청처럼 묻는다."""
        self.b.beat()
        mid = self.server.phone_send('ra', '김교사', 'd' * 32, 'b' * 32, 'claude-1', '남의 휴대폰')
        self.server.messages[mid]['to'] = ('rb', 'b' * 32)
        self.b.beat()
        self.assertEqual(self.b.asked, [('김교사', 'claude-1')])
        self.assertEqual(self.server.messages[mid]['status'], 'refused')

    def test_phone_only_pc_takes_my_phone_but_not_other_people(self):
        """«휴대폰»만 켜고 «다른 PC» 는 끈 PC (2026-10-30) — 내 휴대폰은 받고, 남의 목록·보내기·메시지는 막는다."""
        self.a.beat()
        self.b.cross = False
        self.b.beat()
        self.assertFalse(self.server.peers[('rb', 'b' * 32)]['cross'])                 # 서버에 알린다
        self.assertNotIn('bbbbbb', self.a.call('/peers')[1])                            # 남의 목록에 없다
        self.assertEqual(self.b.call('/peers')[0], 503)                                 # 이 PC 의 에이전트도 다른 PC 로는 못 보낸다
        mid = self.server.phone_send('rb', '이교사', 'c' * 32, 'b' * 32, 'claude-1', '휴대폰에서')
        with patch.object(agent_term.Session, 'submit', lambda s, text: self.b.typed.append((s.name, text))),              patch.object(agent_term.Session, 'agent_running', return_value=True):
            self.b.beat()
        self.assertEqual(self.server.messages[mid]['status'], 'delivered')
        # 옛 데스크처럼 서버가 막지 못한 남의 메시지가 와도 이 PC 가 거절한다
        self.b.cross = True
        self.b.beat()
        other = self.server.desk_agent_send('ra', '김교사', {'p_device': 'a' * 32, 'p_agent': 'claude-1', 'p_to_resource': 'rb',
                                                             'p_to_device': 'b' * 32, 'p_to_agent': 'claude-1', 'p_body': '안녕'})['id']
        self.b.cross = False
        self.b.beat()
        self.assertEqual(self.server.messages[other]['status'], 'refused')
        self.assertIn('다른 PC', self.server.messages[other]['note'])
        self.assertEqual(self.b.asked, [])                                              # 묻지도 않는다

    def test_agents_without_the_relay_are_not_listed(self):
        """에이전트끼리 보기를 끄고 연 에이전트는 받아도 답을 못 보낸다 — 목록에 알리지 않는다 (2026-10-30)."""
        lone = self.b.manager.open('codex', str(Path(self.room.name) / 'w-B-PC'), False, Path(self.room.name))
        self.b.beat()
        listed = [agent['name'] for agent in self.server.peers[('rb', 'b' * 32)]['agents']]
        self.assertIn('claude-1', listed)
        self.assertNotIn(lone.name, listed)

    def test_reply_only_by_the_agent_that_received_it(self):
        self.b.trusted.add('ra')
        mid = self.send_a_to_b()
        self.b.beat()
        other = self.b.manager.open('codex', str(Path(self.room.name) / 'w-B-PC'), False, Path(self.room.name), team=self.b.bridge)
        request = urllib.request.Request(self.b.bridge.url + f'/peer/reply/{mid}', data='가로채기'.encode(), method='POST')
        request.add_header('X-Desk-Token', other.env['DESK_AGENT_TOKEN'])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(caught.exception.code, 403)


class DesktopPeerTests(unittest.TestCase):
    def setUp(self):
        self.api = DesktopAPI()
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.api._preferences_path = Path(self.room.name) / 'desktop-preferences.json'

    def tearDown(self):
        if self.api._term_peer:
            self.api._term_peer.stop()
        if self.api._term_bridge:
            self.api._term_bridge.stop()

    def test_settings_and_trusted_people(self):
        state = self.api.call('term_peer_state')['data']
        self.assertTrue(state['available'])
        self.assertFalse(state['on'])
        self.assertIs(self.api._term_bridge.peer, self.api._term_peer)
        self.assertRegex(self.api._read_preferences()['agent_peer_device'], r'^[0-9a-f]{32}$')
        self.assertIn('알립니다', self.api.call('term_peer_set', {'on': True})['data'])
        self.assertFalse(self.api._term_peer_enabled())                  # 창이 닫혀 있다
        self.api._save_preferences(agent_peer_trusted=[{'id': 'r1', 'name': '김교사'}])
        self.assertIn('다시 처음에 묻습니다', self.api.call('term_peer_set', {'remove': 'r1'})['data'])
        self.assertEqual(self.api._term_peer_trusted(), [])
        self.assertFalse(self.api.call('term_peer_set', {})['ok'])
        self.assertFalse(self.api.call('term_peer_state')['data']['phone'])      # 휴대폰 — 따로 켜는 스위치, 정하지 않았으면 끔
        self.assertTrue(self.api.call('term_peer_set', {'phone': True})['ok'])
        self.assertIn('껐습니다', self.api.call('term_peer_set', {'phone': False})['data'])
        self.assertFalse(self.api._term_peer_phone())
        self.assertFalse(self.api._term_peer._safe(self.api._term_peer.phone))
        self.assertTrue(self.api.call('term_peer_set', {'phone': True})['ok'])
        self.assertTrue(self.api._term_peer_phone())

    def test_ask_answer_always_saves_the_person(self):
        class Window:
            def __init__(self):
                self.scripts = []
            def run_js(self, script):
                self.scripts.append(script)
            show = restore = lambda self: None
        window = Window()
        self.api._term_window, self.api._term_ready = window, True
        target = type('S', (), {'id': 't1', 'title': '', 'name': 'claude-1', 'skip': False})()
        message = {'id': 'm1', 'body': '안녕하세요', 'sender': {'resource_id': 'r9', 'name': '박교사', 'label': 'P', 'agent': 'codex-1'}}
        result = {}
        with patch.object(DesktopAPI, '_bring_front'):
            thread = threading.Thread(target=lambda: result.update(answer=self.api._term_peer_ask(message, target)))
            thread.start()
            for _ in range(50):
                if self.api._term_peer_asks:
                    break
                time.sleep(0.02)
            request = next(iter(self.api._term_peer_asks))
            self.assertIn('askPeer', window.scripts[0])
            self.assertFalse(self.api.call('term_peer_answer', {'request': request, 'answer': 'yes'})['ok'])
            self.assertTrue(self.api.call('term_peer_answer', {'request': request, 'answer': 'always'})['ok'])
            thread.join(5)
        self.assertEqual(result['answer'], 'always')
        self.assertEqual(self.api._term_peer_trusted(), [{'id': 'r9', 'name': '박교사'}])
        self.assertIn('askDone', window.scripts[-1])

    def test_student_edition_has_no_peer(self):
        with patch.object(desktop.edition, 'STUDENT', True):
            self.assertEqual(self.api.call('term_peer_state')['data'], {'available': False})   # 단추가 숨는다
            self.assertFalse(self.api.call('term_peer_set', {'on': True})['ok'])
            self.assertFalse(self.api.call('term_peer_answer', {'request': 'x', 'answer': 'once'})['ok'])
            self.api._term_manager()
            self.assertIsNone(self.api._term_peer)


if __name__ == '__main__':
    unittest.main()
