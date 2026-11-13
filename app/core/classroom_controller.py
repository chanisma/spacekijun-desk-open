"""교실판의 흐름 — QR → 승인 → 수업(독) → 정리 → 다시 QR. 창(UI)과 떨어져 있어 시험할 수 있다.

단계(phase)
  qr        QR 을 띄우고 4초마다 승인을 묻는다. QR 은 10분마다 새로 만든다(서버가 정한다).
  sleep     쉬는 중 — 서버를 부르지 않는다. 평일 07~18시 밖(밤·주말)에 QR 을 10분 띄웠는데 아무도 연결하지 않으면.
            이 PC 를 누가 만지면(마우스·터치·키보드) 또는 평일 07시가 되면 다시 QR. 화면의 [연결 QR 띄우기]도 같다.
            (2026-11-10 — 교실 PC 가 밤새 2초마다 서버를 불러 Edge Function 한도를 넘길 뻔했다)
  offline   서버에 닿지 않는다 — 10초 뒤 다시.
  session   수업 중 — 독이 뜬다. 아무것도 저절로 열지 않는다(2026-10-13 사용자 결정).
            20초마다 서버에 물어 휴대폰에서 «수업 끝»을 눌렀는지 본다. 끝날 시각이 지나면 정리.
            연 드라이브 파일이 저장되면 2초 안팎에 되올린다.
            드라이브 토큰(1시간)이 끝나면 «드라이브 다시 연결» QR(purpose=drive)을 띄울 수 있다 —
            지금 수업 중인 선생님이 찍으면 토큰만 바뀌고 수업은 그대로다.
  ending    정리 중(창·프로그램 닫기 → 고친 파일 올리기 → 받은 파일·임시 프로필 지우기).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

from .classroom_link import LinkError, approve_url, qr_svg

POLL_QR = 4.0
SLEEP_CHECK = 2.0           # 쉬는 중 — 서버는 안 부르고, 깨울 때인지만 본다
AWAKE_OFF_HOURS = 10 * 60   # 쉬는 시간(평일 07~18시 밖)에 QR 을 이만큼 띄우고 아무도 연결하지 않으면 쉰다
WAKE_IDLE = 5.0             # 이 PC 의 마지막 입력이 이보다 가까우면 누가 만진 것 — 깨운다
POLL_SESSION = 20.0
RETRY_OFFLINE = 10.0
WARN_BEFORE = 5 * 60        # 끝나기 5분 전부터 독에 알린다


def school_hours(ts: float) -> bool:
    """평일 07~18시(이 PC 의 시각) — QR 을 쉬지 않고 띄워 두는 때"""
    t = datetime.fromtimestamp(ts)
    return t.weekday() < 5 and 7 <= t.hour < 18


def parse_time(value) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


# 수업이 끝날 때 구글 로그인을 어떻게 했나 — QR 화면 알림에 붙인다
END_LOGIN = {
    'saved': ' 구글 로그인을 이 PC 에 암호화해 보관했습니다.',
    'empty': ' 구글에 로그인되지 않은 채 끝나 보관할 로그인이 없었습니다.',
    'failed': ' 구글 로그인을 보관하지 못했습니다.',
    'off': ' 구글 로그인은 보관하지 않고 지웠습니다.',
}


class Controller:
    def __init__(self, client, name_fn, session_factory, clock=time.time, run_async=None, idle_fn=None):
        self.client = client
        self.idle_fn = idle_fn                      # 이 PC 의 마지막 입력 뒤 초(없으면 화면 단추로만 깨운다)
        self.name_fn = name_fn
        self.session_factory = session_factory      # handoff → Session
        self.clock = clock
        self.run_async = run_async or (lambda fn: threading.Thread(target=fn, daemon=True).start())
        self.lock = threading.RLock()
        self.phase = 'qr'
        self.code = None
        self.qr = ''
        self.expires_at = None
        self.ends_at = None
        self.error = ''
        self.notice = ''
        self.progress = ''
        self.session = None
        self.next_server_check = 0.0
        self.drive_link = None                      # 수업 중 드라이브 다시 연결 QR {code, qr, expires_at}
        self.next_drive_poll = 0.0
        self.awake_since = clock()

    # 바깥(창 루프)이 부른다 ----------------------------------------------------
    def step(self) -> float:
        """한 번 돌고, 다음까지 쉴 초를 돌려준다."""
        with self.lock:
            phase = self.phase
        try:
            if phase == 'sleep':
                return self._step_sleep()
            if phase in ('qr', 'offline'):
                if self._should_sleep():
                    self._sleep()
                    return SLEEP_CHECK
                return self._step_qr()
            if phase == 'session':
                return self._step_session()
            return 0.5
        except LinkError as e:
            with self.lock:
                self.error = str(e)
                if self.phase in ('qr', 'offline'):
                    self.phase = 'offline'
                    self.code = None
            return RETRY_OFFLINE

    # 쉬기 ----------------------------------------------------------------------
    def _should_sleep(self) -> bool:
        now = self.clock()
        if school_hours(now):
            return False
        if self._touched():
            self.awake_since = now               # 누가 쓰는 중 — 10분을 다시 센다
            return False
        return now - self.awake_since >= AWAKE_OFF_HOURS

    def _touched(self) -> bool:
        if not self.idle_fn:
            return False
        try:
            return self.idle_fn() < WAKE_IDLE
        except Exception:
            return False

    def _sleep(self):
        with self.lock:
            code, self.code = self.code, None
            self.phase = 'sleep'
            self.qr = ''
            self.expires_at = None
            self.error = ''
        if code:
            try:
                self.client.end(code)            # 떠 있던 QR 을 닫는다(찍어도 연결되지 않게)
            except LinkError:
                pass

    def _step_sleep(self) -> float:
        if self._touched() or school_hours(self.clock()):
            self.wake()
        return SLEEP_CHECK

    def wake(self):
        """쉬는 중이면 QR 을 다시 띄운다(다음 바퀴에 새 QR). 화면 단추·입력·평일 07시"""
        with self.lock:
            self.awake_since = self.clock()
            if self.phase == 'sleep':
                self.phase = 'qr'
                self.code = None

    def _new_qr(self):
        result = self.client.start(self.name_fn())
        with self.lock:
            self.code = result['code']
            self.expires_at = parse_time(result.get('expires_at')) or self.clock() + 180
            self.qr = qr_svg(approve_url(self.code))
            self.phase = 'qr'
            self.error = ''

    def _step_qr(self) -> float:
        if not self.code or (self.expires_at and self.clock() > self.expires_at - 5):
            self._new_qr()
            return POLL_QR
        result = self.client.poll(self.code)
        status = result.get('status')
        if status == 'approved' and isinstance(result.get('handoff'), dict):
            self._begin(result['handoff'], result.get('ends_at'))
            return 0.5
        if status in ('expired', 'cancelled', 'unknown', 'ended'):
            self.code = None
            if status == 'cancelled':
                self.notice = '휴대폰에서 연결을 거절했습니다.'
        return POLL_QR

    def _begin(self, handoff: dict, ends_at):
        session = self.session_factory(handoff)
        session.prepare()
        with self.lock:
            self.session = session
            self.ends_at = parse_time(ends_at)
            self.phase = 'session'
            self.notice = ''
            self.next_server_check = self.clock() + POLL_SESSION

    def _step_session(self) -> float:
        now = self.clock()
        if self.ends_at and now >= self.ends_at:
            self.finish('정해 둔 시간이 지나 수업을 정리했습니다.')
            return 0.5
        session = self.session
        if session:
            session.workspace.sync()
        self._step_drive_link(now)
        if now >= self.next_server_check:
            self.next_server_check = now + POLL_SESSION
            try:
                result = self.client.poll(self.code)
            except LinkError:
                return 1.0                       # 잠깐 끊긴 것 — 끝날 시각은 이 PC 가 지킨다
            if result.get('status') != 'active':
                self.finish('휴대폰에서 수업을 끝냈습니다.', tell_server=False)
                return 0.5
            ends = parse_time(result.get('ends_at'))
            if ends:
                self.ends_at = ends
        return 1.0

    # 드라이브 다시 연결 ---------------------------------------------------------
    def drive_reconnect(self):
        """수업 중 드라이브 QR 을 새로 만든다(독·탐색기의 «다시 연결»)."""
        with self.lock:
            if self.phase != 'session':
                return
        result = self.client.start(self.name_fn(), purpose='drive')
        with self.lock:
            self.drive_link = {'code': result['code'], 'qr': qr_svg(approve_url(result['code'])),
                               'expires_at': parse_time(result.get('expires_at')) or self.clock() + 180}
            self.next_drive_poll = 0.0

    def drive_reconnect_cancel(self):
        with self.lock:
            link, self.drive_link = self.drive_link, None
        if link:
            try:
                self.client.end(link['code'])
            except LinkError:
                pass

    def _step_drive_link(self, now: float):
        link = self.drive_link
        if not link or now < self.next_drive_poll:
            return
        self.next_drive_poll = now + POLL_QR
        if now > link['expires_at'] - 5:
            self.drive_link = None               # 3분이 지났다 — 화면에서 [다시 연결]을 또 누르면 된다
            return
        try:
            result = self.client.poll(link['code'])
        except LinkError:
            return
        status = result.get('status')
        handoff = result.get('handoff') if status == 'approved' else None
        if isinstance(handoff, dict):
            session = self.session
            same = session and (handoff.get('teacher') or {}).get('email') == session.email
            if same:
                session.update_google(handoff.get('google'))
                self.notice = '드라이브를 다시 연결했습니다.'
            else:
                self.notice = '수업 중인 선생님이 아니라 드라이브를 연결하지 않았습니다.'
            self.drive_link = None
            try:
                self.client.end(link['code'])     # 드라이브 QR 연결은 토큰만 받고 닫는다
            except LinkError:
                pass
        elif status in ('expired', 'cancelled', 'unknown', 'ended'):
            self.drive_link = None

    # 화면 단추 ----------------------------------------------------------------
    def extend(self, minutes: int = 10):
        with self.lock:
            if self.phase != 'session' or not self.code:
                return
            code = self.code
        result = self.client.extend(code, minutes)
        ends = parse_time(result.get('ends_at'))
        with self.lock:
            if result.get('status') == 'active' and ends:
                self.ends_at = ends

    def finish(self, notice: str = '수업을 정리했습니다.', tell_server: bool = True):
        with self.lock:
            if self.phase != 'session':
                return
            self.phase = 'ending'
            self.progress = '정리하는 중입니다.'
            session, code, link = self.session, self.code, self.drive_link
            self.drive_link = None
        for c in ([code] if tell_server and code else []) + ([link['code']] if link else []):
            try:
                self.client.end(c)
            except LinkError:
                pass                              # 서버는 끝날 시각에 스스로 로그인을 끊는다(cron)
        kept = 0
        copied = getattr(session, 'copied', 0) if session else 0
        places = getattr(session, 'copied_places', []) if session else []
        try:
            if session:
                kept = session.end(progress=lambda text: setattr(self, 'progress', text))
        finally:
            with self.lock:
                self.session = None
                self.code = None
                self.ends_at = None
                self.phase = 'qr'
                self.awake_since = self.clock()
                self.progress = ''
                self.notice = notice + END_LOGIN.get(getattr(session, 'end_login', None), '') +                     (f' 드라이브에 올리지 못한 파일 {kept}개는 다음에 연결하면 올립니다.' if kept else '') +                     (f' 이 PC 에 복사한 파일 {copied}개는 남아 있습니다({", ".join(places)}) — 다음 수업에 «내 드라이브» 창의 «이 PC 에 복사한 파일»에서 바로 열 수 있습니다.' if copied else '')

    def open_google(self) -> dict:
        with self.lock:
            session = self.session if self.phase == 'session' else None
        return session.open_google() if session else {'ok': False, 'error': '수업 중이 아닙니다.'}

    def open_google_app(self, key: str) -> dict:
        with self.lock:
            session = self.session if self.phase == 'session' else None
        return session.open_google_app(key) if session else {'ok': False, 'error': '수업 중이 아닙니다.'}

    def forget_google(self) -> dict:
        """이 PC 의 구글 로그인(지금 것·보관본)을 지운다"""
        with self.lock:
            session = self.session if self.phase == 'session' else None
        if not session:
            return {'ok': False, 'error': '수업 중이 아닙니다.'}
        # 서버 열쇠는 그대로 둔다 — 지운 뒤 다시 로그인하면 끝날 때 새로 보관한다(보관 끄기는 승인 화면에서)
        session.forget_google()
        self.notice = ('이 PC 의 구글 로그인을 지웠습니다. 다시 로그인하면 수업이 끝날 때 새로 보관합니다.' if session.profile
                       else '이 PC 의 구글 로그인을 지웠습니다.')
        return {'ok': True}

    def open_item(self, index: int) -> dict:
        with self.lock:
            session = self.session if self.phase == 'session' else None
        if not session or not (0 <= index < len(session.items)):
            return {'ok': False, 'error': '수업 중이 아닙니다.'}
        return session.open_item(index)

    def state(self) -> dict:
        with self.lock:
            now = self.clock()
            remaining = int(self.ends_at - now) if self.ends_at else None
            link = self.drive_link
            return {
                'phase': self.phase,
                'device': self.name_fn(),
                'qr': self.qr if self.phase == 'qr' else '',
                'qr_left': int(self.expires_at - now) if self.expires_at and self.phase == 'qr' else None,
                'error': self.error if self.phase == 'offline' else '',
                'notice': self.notice,
                'progress': self.progress,
                'remaining': remaining,
                'warn': remaining is not None and remaining <= WARN_BEFORE,
                'session': self.session.snapshot() if self.session else None,
                'drive_link': {'qr': link['qr'], 'left': int(link['expires_at'] - now)} if link else None,
            }
