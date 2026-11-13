"""Native-only login handoff to the two fixed, trusted WebView origins.

Websites retain their own Google OAuth flows. Their independent session is
stored in the format used by the installed Supabase JS clients, then the page
reloads normally. No token is placed in a URL or exposed through the desk API.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import notify, supa_auth

ORIGINS = {'space': 'https://spacekijun.lovable.app', 'seaton': 'https://kijunseaton.netlify.app'}
AUTH_URL = 'https://your-project-ref.supabase.co'
STORAGE_KEY = 'sb-your-project-ref-auth-token'
OWNER_KEY = 'spacekijun-desktop-linked-user'


def origin(url):
    parsed = urllib.parse.urlsplit(url or '')
    return f'{parsed.scheme}://{parsed.netloc}'


def landing(site, url):
    """로그인을 넣은 뒤 다시 열 주소 — 열려던(보던) 화면 그대로. 다른 사이트이거나 로그인 화면이면 첫 화면.

    예전에는 늘 첫 화면을 열어, 웹 로그인이 끝나 가던 때(약 1시간마다)에 데스크에서 고른 기능
    (예: 플래너)이 스페이스기전 홈으로 열렸다 (2026-10-14 사용자 보고 — 가끔 한 번, 다시 누르면 제대로)."""
    parsed = urllib.parse.urlsplit(url or '')
    if origin(url) != ORIGINS[site] or parsed.path.lower().split('/')[1:2] in (['auth'], ['login']):
        return ORIGINS[site]
    return urllib.parse.urlunsplit(parsed._replace(fragment=''))


def issue_session(site, user_id):
    if site not in ORIGINS or notify.config()['url'].rstrip('/') != AUTH_URL:
        raise ValueError('통합 로그인 대상 설정을 확인해 주세요.')
    headers = supa_auth.auth_headers()
    if (supa_auth.load_session() or {}).get('user_id') != user_id:
        raise ValueError('로그인 계정이 변경되었습니다.')
    req = urllib.request.Request(AUTH_URL + '/functions/v1/desktop-session',
        data=json.dumps({'site': site}).encode(),
        headers={**headers, 'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            session = json.loads(response.read().decode())['session']
    except (OSError, ValueError, KeyError):
        raise RuntimeError('통합 로그인에 연결하지 못했습니다. 사이트의 Google 로그인으로 접속하거나 데스크에서 다시 열어 주세요.') from None
    if (session.get('user') or {}).get('id') != user_id or not session.get('access_token') or not session.get('refresh_token'):
        raise RuntimeError('웹 로그인 계정을 확인하지 못했습니다.')
    session.setdefault('expires_at', int(time.time()) + session.get('expires_in', 3600))
    return session


def inspect_script(site):
    return '''(() => {
      if (location.origin !== ORIGIN) return {foreign:true};
      try { const s = JSON.parse(localStorage.getItem(KEY) || 'null');
        return {user:s?.user?.id, expires:s?.expires_at};
      } catch { return {}; }
    })()'''.replace('ORIGIN', json.dumps(ORIGINS[site])).replace('KEY', json.dumps(STORAGE_KEY))


def discard_session(session):
    """Revoke an issued session that could not be handed off; never global logout."""
    req = urllib.request.Request(AUTH_URL + '/auth/v1/logout?scope=local', data=b'',
        headers={'apikey': notify.config()['anon_key'],
                 'Authorization': 'Bearer ' + session['access_token']}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except OSError:
        pass


def install_script(site, session):
    # Return only a boolean; pywebview must never serialize tokens back to UI/logs.
    values = json.dumps({'origin': ORIGINS[site], 'key': STORAGE_KEY,
                         'owner': OWNER_KEY, 'session': session}, ensure_ascii=True)
    return '''(() => {
      const p = PAYLOAD;
      if (location.origin !== p.origin) return false;
      if (p.origin === 'https://kijunseaton.netlify.app') localStorage.removeItem('auth-storage');
      localStorage.setItem(p.key, JSON.stringify(p.session));
      const claims = JSON.parse(atob(p.session.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      localStorage.setItem(p.owner, p.session.user.id + '|' + claims.session_id);
      localStorage.setItem('auth_login_timestamp', String(Date.now()));
      if (localStorage.getItem('spacekijun_personal_device_user') !== p.session.user.id)
        localStorage.removeItem('spacekijun_personal_device_user');
      return true;
    })()'''.replace('PAYLOAD', values)


def logout_script(site, user_id):
    values = json.dumps({'origin': ORIGINS[site], 'key': STORAGE_KEY, 'owner': OWNER_KEY,
                         'user': user_id, 'auth': AUTH_URL, 'anon': notify.config()['anon_key']})
    return '''(() => {
      const p = PAYLOAD;
      if (location.origin !== p.origin) return false;
      const s = JSON.parse(localStorage.getItem(p.key) || 'null');
      if (!s?.access_token || s?.user?.id !== p.user) return false;
      const claims = JSON.parse(atob(s.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      if (localStorage.getItem(p.owner) !== p.user + '|' + claims.session_id) return false;
      if (p.origin === 'https://kijunseaton.netlify.app') localStorage.removeItem('auth-storage');
      localStorage.removeItem(p.key);
      localStorage.removeItem(p.key + '-user');
      localStorage.removeItem(p.owner);
      localStorage.removeItem('auth_login_timestamp');
      localStorage.removeItem('spacekijun_personal_device_user');
      fetch(p.auth + '/auth/v1/logout?scope=local', {method:'POST', keepalive:true,
        headers:{apikey:p.anon, Authorization:'Bearer ' + s.access_token}}).catch(() => {});
      return true;
    })()'''.replace('PAYLOAD', values)


class WebLogin:
    def __init__(self, log):
        self.log = log
        self.lock = threading.RLock()
        self.issue_lock = threading.Lock()
        self.epoch = 0
        self.attempts = set()
        self.busy = set()

    def cancel(self):
        with self.lock:
            self.epoch += 1
            self.attempts.clear()

    def forget(self, window):
        with self.lock:
            self.attempts = {key for key in self.attempts if key[0] != window.uid}

    def start(self, window, site, force=False, target=None):
        """target: 데스크가 열려던 주소 (없으면 창이 지금 보는 주소). 로그인을 넣은 뒤 그 화면으로 다시 연다."""
        session = supa_auth.load_session() or {}
        uid = session.get('user_id')
        if not uid or site not in ORIGINS:
            return
        key = (window.uid, uid)
        with self.lock:
            if key in self.busy or (key in self.attempts and not force):
                return
            epoch = self.epoch
            self.busy.add(key)
        def work():
            try:
                self.connect(window, site, uid, epoch, target)
            except Exception:
                self.log('통합 로그인 연결을 완료하지 못했습니다. 사이트에서 직접 로그인하거나 바로가기를 다시 눌러 주세요.')
            finally:
                with self.lock:
                    self.busy.discard(key)
        threading.Thread(target=work, daemon=True, name=f'desk-web-login-{site}').start()

    def connect(self, window, site, uid, epoch, target=None):
        here = window.get_current_url()
        if origin(here) != ORIGINS[site]:
            return
        with self.lock:
            if self.epoch != epoch:
                return
            self.attempts.add((window.uid, uid))
        current = window.evaluate_js(inspect_script(site)) or {}
        if current.get('foreign'):
            return
        if current.get('user') == uid and (current.get('expires') or 0) > time.time() + 60:
            return
        # Supabase email-link issuance is per account: consume one link before
        # requesting the next when both shortcuts are opened together.
        with self.issue_lock:
            with self.lock:
                if self.epoch != epoch:
                    return
            session = issue_session(site, uid)
        installed = False
        try:
            with self.lock:
                if self.epoch != epoch or (supa_auth.load_session() or {}).get('user_id') != uid:
                    return
                if origin(window.get_current_url()) != ORIGINS[site]:
                    return
                installed = window.evaluate_js(install_script(site, session)) is True
                if installed:
                    window.load_url(landing(site, target or here))
            if installed:
                self.log(('스페이스기전' if site == 'space' else '기전시트온') + '에 데스크 계정으로 로그인했습니다.')
        finally:
            if not installed:
                discard_session(session)

    def logout(self, window, site, uid):
        if not uid or origin(window.get_current_url()) != ORIGINS[site]:
            return
        try:
            if window.evaluate_js(logout_script(site, uid)) is True:
                window.load_url(ORIGINS[site])
        except Exception:
            self.log('웹 창의 로그아웃 상태를 확인해 주세요.')
