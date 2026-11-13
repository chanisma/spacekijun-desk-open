"""
spacekijun 알림(notification_events) 전송.

쿨메신저에서 받은 쪽지를 웹앱 알림함으로 밀어 준다. 알림에 [답장] 버튼이 붙으려면
`type='coolmessenger'` 과 `meta.sender_plain` 이 있어야 한다.

접근 권한
  · INSERT 는 `System can create notifications` 정책이 `WITH CHECK (true)` 라 anon 으로도 된다.
  · 다만 **사용자 세션이 있으면 그쪽을 쓴다** — resource_id 를 DB 에서 직접 읽을 수 있어
    다른 선생님이 써도 본인 알림함으로 간다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from . import edition

DATA_DIR = edition.DATA_DIR      # 판마다 따로 (core/edition.py)
CONFIG_PATH = os.path.join(DATA_DIR, 'spacekijun.json')

# 웹앱 번들에 들어 있는 **공개 값**이다. 배포판에 넣어도 무방하다(RLS 가 지킨다).
DEFAULT_URL = 'https://your-project-ref.supabase.co'
REPO_CLIENT = [
    r'C:\repository\spacekijun\src\integrations\supabase\client.ts',
    os.path.join(os.path.expanduser('~'), 'Documents', 'GitHub', 'spacekijun',
                 'src', 'integrations', 'supabase', 'client.ts'),
]


class NotifyError(RuntimeError):
    pass


def _from_repo():
    for p in REPO_CLIENT:
        if not os.path.exists(p):
            continue
        s = open(p, encoding='utf-8').read()
        u = re.search(r'SUPABASE_URL\s*=\s*"([^"]+)"', s)
        k = re.search(r'SUPABASE_PUBLISHABLE_KEY\s*=\s*"([^"]+)"', s)
        if u and k:
            return u.group(1), k.group(1)
    return None, None


def config() -> dict:
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        cfg = json.load(open(CONFIG_PATH, encoding='utf-8'))
    if not cfg.get('url') or not cfg.get('anon_key'):
        bundled = os.path.join(os.path.dirname(__file__), '..', 'resources', 'public-config.json')
        if os.path.exists(bundled):
            with open(bundled, encoding='utf-8') as source:
                public = json.load(source)
            cfg.setdefault('url', public['url'])
            cfg.setdefault('anon_key', public['anon_key'])
    if not cfg.get('url') or not cfg.get('anon_key'):
        u, k = _from_repo()
        cfg.setdefault('url', u or DEFAULT_URL)
        if k:
            cfg.setdefault('anon_key', k)
    if not cfg.get('anon_key'):
        raise NotifyError('spacekijun anon 키가 없습니다. 설정에서 입력하세요.')
    return cfg


def save_config(cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(cfg, open(CONFIG_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def _auth_headers(cfg):
    try:
        from . import supa_auth
        if supa_auth.load_session():
            return supa_auth.auth_headers()
    except Exception:
        pass
    return {'apikey': cfg['anon_key'], 'Authorization': 'Bearer ' + cfg['anon_key']}


def resource_id(cfg) -> str:
    from . import supa_auth
    if supa_auth.load_session():
        # Never reuse a target left by another account or an unfiltered lookup.
        rid = supa_auth.my_resource_id()
        if cfg.get('resource_id') != rid:
            cfg['resource_id'] = rid
            save_config(cfg)
        return rid
    if cfg.get('resource_id'):
        return cfg['resource_id']
    raise NotifyError('resource_id 를 알 수 없습니다. 설정에서 spacekijun 연동을 켜고 로그인하세요.')


def send(title: str, message: str, meta: dict | None = None, ntype='coolmessenger',
         priority='medium'):
    cfg = config()
    row = {'resource_id': resource_id(cfg), 'type': ntype, 'title': title,
           'message': message, 'priority': priority, 'is_read': False, 'meta': meta or {}}
    headers = dict(_auth_headers(cfg))
    headers['Content-Type'] = 'application/json'
    # ⚠️ return=representation 을 쓰면 INSERT 뒤 RETURNING 에 SELECT 정책이 걸려 42501 이 난다
    headers['Prefer'] = 'return=minimal'
    req = urllib.request.Request(
        cfg['url'].rstrip('/') + '/rest/v1/notification_events',
        data=json.dumps([row], ensure_ascii=False).encode('utf-8'),
        headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        raise NotifyError('%s %s -> %s' % (e.code, e.reason,
                                           e.read().decode('utf-8', 'replace'))) from None
