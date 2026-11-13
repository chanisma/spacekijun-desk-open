"""
spacekijun(Supabase) 사용자 로그인 — 기기당 1회.

왜 이렇게 하나
  · 이 프로젝트 계정은 **전원 Google OAuth** 다 (비밀번호를 가진 계정이 0명). 그래서
    이메일+비밀번호 로그인은 쓸 수 없고 PKCE 흐름을 쓴다.
  · 배포판에 `service_role` 키를 넣으면 **RLS 가 통째로 무력화**된다. 프로그램이 학교 밖으로
    나가면 전교생 데이터가 열린다. 그래서 공유 비밀 없이 **사용자 본인 세션**으로만 접근한다.
    배포판에 들어가는 건 anon 키뿐이고, 그건 웹앱 번들에 이미 들어 있는 공개 값이다.

토큰 보관
  refresh_token 을 **DPAPI 로 암호화**해 둔다. 그 PC 의 그 사용자 계정에서만 풀린다.
  한 번 로그인하면 같은 기기에서는 다시 묻지 않는다(만료되면 자동 갱신).

사전 조건
  Supabase 대시보드 → Authentication → URL Configuration → Redirect URLs 에
  `http://localhost:8912/callback` 이 등록돼 있어야 한다.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from . import notify
from .secretstore import decrypt, encrypt
from . import edition

DATA_DIR = edition.DATA_DIR      # 판마다 따로 (core/edition.py)
SESSION_PATH = os.path.join(DATA_DIR, 'spacekijun.session')
REDIRECT_PORT = 8912
REDIRECT_URI = f'http://localhost:{REDIRECT_PORT}/callback'


class AuthError(RuntimeError):
    pass


# ── 세션 보관 ─────────────────────────────────────────────────
def save_session(sess: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SESSION_PATH, 'wb') as f:
        f.write(encrypt(json.dumps(sess, ensure_ascii=False).encode('utf-8')))


def load_session() -> dict | None:
    if not os.path.exists(SESSION_PATH):
        return None
    try:
        with open(SESSION_PATH, 'rb') as f:
            return json.loads(decrypt(f.read()).decode('utf-8'))
    except Exception:
        return None          # 다른 PC 에서 복사됐거나 손상 — 다시 로그인하면 된다


def logout():
    if os.path.exists(SESSION_PATH):
        os.remove(SESSION_PATH)


# ── Supabase auth ─────────────────────────────────────────────
def _post(path: str, body: dict) -> dict:
    cfg = notify.config()
    req = urllib.request.Request(
        cfg['url'].rstrip('/') + path,
        data=json.dumps(body).encode('utf-8'),
        headers={'apikey': cfg['anon_key'], 'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise AuthError('%s %s -> %s' % (e.code, e.reason,
                                         e.read().decode('utf-8', 'replace'))) from None


def _store(tok: dict) -> dict:
    user = tok.get('user') or {}
    sess = {'access_token': tok['access_token'],
            'refresh_token': tok['refresh_token'],
            'expires_at': time.time() + tok.get('expires_in', 3600) - 120,
            'email': user.get('email'), 'user_id': user.get('id')}
    save_session(sess)
    return sess


class _Handler(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path != '/callback':
            self.send_response(404); self.end_headers(); return
        _Handler.result.update({k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()})
        ok = 'code' in _Handler.result
        msg = ('로그인이 끝났습니다. 이 창을 닫으셔도 됩니다.' if ok else
               '로그인 실패: %s' % _Handler.result.get('error_description', '알 수 없음'))
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(('<html><meta charset="utf-8"><body style="font:16px sans-serif;'
                          'padding:40px"><h2>%s</h2></body></html>' % msg).encode('utf-8'))

    def log_message(self, *a):
        pass


def login(timeout_sec=300, log=print) -> dict:
    """브라우저로 구글 로그인. 성공하면 세션을 이 기기에 저장한다."""
    cfg = notify.config()
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip('=')
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    url = cfg['url'].rstrip('/') + '/auth/v1/authorize?' + urllib.parse.urlencode({
        'provider': 'google', 'redirect_to': REDIRECT_URI,
        'code_challenge': challenge, 'code_challenge_method': 's256'})

    _Handler.result = {}
    srv = http.server.HTTPServer(('127.0.0.1', REDIRECT_PORT), _Handler)
    srv.timeout = 1
    log('브라우저에서 구글 로그인해 주세요.')
    webbrowser.open(url)

    deadline = time.time() + timeout_sec
    while not _Handler.result and time.time() < deadline:
        srv.handle_request()
    srv.server_close()

    if 'code' not in _Handler.result:
        raise AuthError('로그인이 완료되지 않았습니다 (시간 초과 또는 취소).')
    sess = _store(_post('/auth/v1/token?grant_type=pkce',
                        {'auth_code': _Handler.result['code'], 'code_verifier': verifier}))
    log(f"로그인 완료: {sess.get('email')}")
    return sess


def login_async(on_done, log=print):
    """GUI 가 얼지 않게 스레드에서 로그인한다."""
    def work():
        try:
            on_done(login(log=log))
        except Exception as e:
            log(f'로그인 실패: {e}')
            on_done(None)
    threading.Thread(target=work, daemon=True).start()


def access_token() -> str:
    sess = load_session()
    if not sess:
        raise AuthError('spacekijun 로그인이 필요합니다 (설정 탭).')
    if time.time() < sess.get('expires_at', 0):
        return sess['access_token']
    return _store(_post('/auth/v1/token?grant_type=refresh_token',
                        {'refresh_token': sess['refresh_token']}))['access_token']


def auth_headers() -> dict:
    cfg = notify.config()
    return {'apikey': cfg['anon_key'], 'Authorization': 'Bearer ' + access_token()}


def my_resource_id() -> str:
    cfg = notify.config()
    headers = auth_headers()
    session = load_session()
    if not session or not session.get('user_id'):
        raise AuthError('로그인 계정을 확인할 수 없습니다. 다시 로그인해 주세요.')
    query = urllib.parse.urlencode({'select': 'resource_id',
                                   'user_id': 'eq.' + session['user_id'], 'limit': '2'})
    req = urllib.request.Request(
        cfg['url'].rstrip('/') + '/rest/v1/user_resource?' + query,
        headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        rows = json.loads(r.read().decode('utf-8'))
    if not rows:
        raise AuthError('이 계정에 연결된 resource 가 없습니다. 관리자에게 문의하세요.')
    if len(rows) != 1:
        raise AuthError('이 계정의 알림 수신 대상이 여러 개입니다. 관리자에게 연결 정보를 확인해 주세요.')
    return rows[0]['resource_id']


def my_role() -> str | None:
    """로그인한 계정의 역할(profiles.role — student·teacher·staff·admin). 모르면 None.
    관리자만 받는 테스트 판(core/updater.py teacher-test)을 고를 때 쓴다 — 서버의 role 은 트리거가 지킨다."""
    session = load_session()
    if not session or not session.get('user_id'):
        return None
    cfg = notify.config()
    query = urllib.parse.urlencode({'select': 'role', 'id': 'eq.' + session['user_id'], 'limit': '1'})
    req = urllib.request.Request(cfg['url'].rstrip('/') + '/rest/v1/profiles?' + query, headers=auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read().decode('utf-8'))
    except Exception:
        return None
    return rows[0].get('role') if rows else None


def whoami() -> str | None:
    sess = load_session()
    return sess.get('email') if sess else None
