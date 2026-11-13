"""Realtime 새 메시지 (2026-10-19) — 진짜 서버에는 붙지 않는다. 가짜 웹소켓으로 프로토콜만 본다."""
from test_sandbox import use_sandbox
use_sandbox()
import json
import threading
import unittest
from unittest.mock import patch

from core import realtime

RECORD = {'id': 'n1', 'type': 'desk_message', 'title': '[메시지] 김선생 선생님', 'message': '안녕',
          'meta': {'sender_resource_id': 't1', 'sender_label': '김선생 선생님'}, 'is_read': False,
          'created_at': '2026-10-19T05:00:00.1+00:00'}


def change(record, topic=realtime.TOPIC):
    return {'topic': topic, 'event': 'postgres_changes', 'payload': {'data': {'type': 'INSERT', 'record': record}}}


class FakeSocket:
    """recv 는 넣어 둔 것을 차례로, 다 쓰면 time out 을 흉내 낸다 (리스너가 stop 될 때까지)."""
    def __init__(self, incoming, listener_ref):
        self.incoming, self.sent, self.ref = list(incoming), [], listener_ref
        self.closed = False

    def send(self, raw):
        self.sent.append(json.loads(raw))

    def settimeout(self, _):
        pass

    def recv(self):
        if self.incoming:
            return json.dumps(self.incoming.pop(0))
        self.ref['listener'].stop()
        raise TimeoutError()

    def close(self):
        self.closed = True


class RealtimeTest(unittest.TestCase):
    def setUp(self):
        for patcher in (patch('core.realtime.notify.config', return_value={'url': 'https://abc.supabase.co', 'anon_key': 'anon'}),
                        patch('core.realtime.supa_auth.access_token', return_value='token-1')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_only_desk_message_inserts_are_taken(self):
        self.assertEqual(realtime.record_of(change(RECORD)), RECORD)
        self.assertIsNone(realtime.record_of(change({**RECORD, 'type': 'coolmessenger'})))
        self.assertIsNone(realtime.record_of(change(RECORD, topic='realtime:other')))
        self.assertIsNone(realtime.record_of({'topic': realtime.TOPIC, 'event': 'phx_reply', 'payload': {}}))

    def test_socket_url_and_join_ask_for_rls_filtered_desk_messages(self):
        self.assertEqual(realtime.socket_url({'url': 'https://abc.supabase.co/', 'anon_key': 'k'}),
                         'wss://abc.supabase.co/realtime/v1/websocket?apikey=k&vsn=1.0.0')
        join = realtime.join_message('tok', '1')
        self.assertEqual(join['payload']['access_token'], 'tok')        # 사용자 토큰 — RLS 로 본인 것만 온다
        self.assertEqual(join['payload']['config']['postgres_changes'],
                         [{'event': 'INSERT', 'schema': 'public', 'table': 'notification_events', 'filter': 'type=eq.desk_message'},
                          {'event': 'INSERT', 'schema': 'public', 'table': 'notification_events', 'filter': 'type=eq.agent_request'}])

    def test_session_joins_and_hands_over_new_messages(self):
        got, ref = [], {}
        incoming = [{'topic': realtime.TOPIC, 'event': 'phx_reply', 'payload': {'status': 'ok', 'response': {}}},
                    change({**RECORD, 'type': 'coolmessenger'}), change(RECORD)]
        sockets = []

        def connect(url):
            sockets.append(FakeSocket(incoming, ref))
            return sockets[-1]
        listener = realtime.Listener(got.append, lambda: True, lambda *a: None, connect=connect)
        ref['listener'] = listener
        listener._session()
        self.assertEqual(got, [RECORD])
        self.assertEqual(sockets[0].sent[0]['event'], 'phx_join')
        self.assertTrue(listener.connected)
        self.assertTrue(sockets[0].closed)

    def test_refused_subscription_raises_so_it_reconnects_later(self):
        ref = {}
        incoming = [{'topic': realtime.TOPIC, 'event': 'system', 'payload': {'status': 'error', 'message': 'denied'}}]
        listener = realtime.Listener(lambda r: None, lambda: True, lambda *a: None,
                                     connect=lambda url: FakeSocket(incoming, ref))
        ref['listener'] = listener
        with self.assertRaisesRegex(RuntimeError, 'denied'):
            listener._session()

    def test_heartbeat_sends_a_fresh_token_when_it_changes(self):
        tokens = iter(['token-1', 'token-2'])
        socket = FakeSocket([], {})
        listener = realtime.Listener(lambda r: None, lambda: True, lambda *a: None, connect=lambda url: socket)

        def recv():
            if len(socket.sent) >= 3:               # 구독 · 심장 박동 · 새 토큰까지 보냈으면 끝
                listener.stop()
            raise TimeoutError()
        socket.recv = recv
        with patch('core.realtime.supa_auth.access_token', side_effect=lambda: next(tokens)), \
             patch('core.realtime.time.monotonic', side_effect=[0] + [30] * 10):
            listener._session()
        events = [m['event'] for m in socket.sent]
        self.assertEqual(events[:3], ['phx_join', 'heartbeat', 'access_token'])
        self.assertEqual(socket.sent[2]['payload'], {'access_token': 'token-2'})

    def test_does_not_connect_while_away_or_signed_out(self):
        connect = threading.Event()
        listener = realtime.Listener(lambda r: None, lambda: False, lambda *a: None,
                                     connect=lambda url: connect.set())
        listener.start()
        self.assertFalse(connect.wait(0.3))
        listener.stop()


if __name__ == '__main__':
    unittest.main()
