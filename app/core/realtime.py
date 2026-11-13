"""스페이스기전 Realtime — 새 메시지를 바로 받는다 (2026-10-19 요청, 데스크 메시지).

notification_events 는 이미 supabase_realtime 발행 목록에 있다(웹앱 알림함이 쓴다). 여기서 그 표의
INSERT 중 type = desk_message 만 구독한다. Realtime 은 RLS 를 지켜 **받는 사람 본인 것만** 보낸다
(학생은 current_student_code 규칙으로). DB 는 바꾸지 않았다.

  · Phoenix 웹소켓 프로토콜을 직접 쓴다 (websocket-client) — join · heartbeat(25초) · access_token(토큰 갱신).
  · 동시 연결 수가 요금제 한도에 걸리므로 **쓰는 동안만** 붙는다: active() 가 False(로그아웃·자리 비움)면
    끊고 기다린다. 끊긴 사이에 온 것은 desktop.py 의 2분 확인이 줍는다.
  · 끊기면 2 → 4 → … → 60초 간격으로 다시 붙는다.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse

from . import notify, supa_auth

TOPIC = 'realtime:desk-messages'
HEARTBEAT = 25
# 받는 알림 종류 — 데스크 메시지 · 에이전트 작업 요청(2026-11-11, core/agent_request.py). 필터는 하나에 한 값이라 종류마다 한 줄
TYPES = ('desk_message', 'agent_request')
TABLES = [{'event': 'INSERT', 'schema': 'public', 'table': 'notification_events', 'filter': f'type=eq.{kind}'} for kind in TYPES]
TABLE = TABLES[0]


def socket_url(cfg: dict) -> str:
    base = cfg['url'].rstrip('/').replace('https://', 'wss://', 1).replace('http://', 'ws://', 1)
    return f"{base}/realtime/v1/websocket?{urllib.parse.urlencode({'apikey': cfg['anon_key'], 'vsn': '1.0.0'})}"


def join_message(token: str, ref: str) -> dict:
    return {'topic': TOPIC, 'event': 'phx_join', 'ref': ref, 'join_ref': ref,
            'payload': {'config': {'broadcast': {'ack': False, 'self': False}, 'presence': {'key': ''},
                                   'postgres_changes': TABLES, 'private': False},
                        'access_token': token}}


def record_of(message: dict) -> dict | None:
    """postgres_changes 메시지에서 새로 들어온 행. 다른 것이면 None."""
    if message.get('topic') != TOPIC or message.get('event') != 'postgres_changes':
        return None
    data = (message.get('payload') or {}).get('data') or {}
    record = data.get('record')
    if data.get('type') != 'INSERT' or not isinstance(record, dict) or record.get('type') not in TYPES:
        return None
    return record


class Listener:
    """뒤에서 붙어 있다가 새 메시지가 오면 on_record(record). stop() 으로 끝낸다."""

    def __init__(self, on_record, active, log, connect=None):
        self.on_record, self.active, self.log = on_record, active, log
        self._connect = connect or self._websocket
        self._stop = threading.Event()
        self._thread = None
        self.connected = False

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name='desk-realtime')
            self._thread.start()

    def stop(self):
        self._stop.set()

    @staticmethod
    def _websocket(url):
        import websocket
        return websocket.create_connection(url, timeout=15, enable_multithread=True)

    def _run(self):
        delay = 2
        while not self._stop.is_set():
            if not self.active():
                self._stop.wait(5)                 # 쓰지 않는 동안은 연결을 잡지 않는다
                continue
            started = time.monotonic()
            try:
                self._session()
            except Exception as exc:               # 끊김·네트워크 — 조금 쉬고 다시
                if self.connected:
                    self.log('실시간 메시지 연결이 끊겼습니다:', exc)
            finally:
                self.connected = False
            if self._stop.is_set():
                break
            delay = 2 if time.monotonic() - started > 120 else min(delay * 2, 60)
            self._stop.wait(delay)

    def _session(self):
        token = supa_auth.access_token()
        ws = self._connect(socket_url(notify.config()))
        ref = 1
        try:
            ws.send(json.dumps(join_message(token, str(ref))))
            ws.settimeout(1)
            beat = time.monotonic()
            while not self._stop.is_set() and self.active():
                try:
                    raw = ws.recv()
                except Exception as exc:
                    if type(exc).__name__ not in ('WebSocketTimeoutException', 'TimeoutError', 'timeout'):
                        raise
                    raw = None
                if raw:
                    self._handle(json.loads(raw))
                if time.monotonic() - beat >= HEARTBEAT:
                    beat = time.monotonic()
                    ref += 1
                    ws.send(json.dumps({'topic': 'phoenix', 'event': 'heartbeat', 'payload': {}, 'ref': str(ref)}))
                    fresh = supa_auth.access_token()          # 한 시간마다 바뀐다 — 연결에 다시 넣는다
                    if fresh != token:
                        token = fresh
                        ref += 1
                        ws.send(json.dumps({'topic': TOPIC, 'event': 'access_token',
                                            'payload': {'access_token': token}, 'ref': str(ref)}))
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _handle(self, message):
        event, payload = message.get('event'), message.get('payload') or {}
        if message.get('topic') == TOPIC and event == 'phx_reply':
            if payload.get('status') == 'ok':
                if not self.connected:
                    self.connected = True
            else:
                raise RuntimeError(f'구독을 받지 않았습니다: {payload.get("response")}')
        elif message.get('topic') == TOPIC and event == 'system' and payload.get('status') == 'error':
            raise RuntimeError(payload.get('message') or 'Realtime 오류')
        elif message.get('topic') == TOPIC and event == 'phx_close':
            raise RuntimeError('서버가 연결을 닫았습니다')
        record = record_of(message)
        if record:
            self.on_record(record)
