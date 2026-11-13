"""
쪽지 목록 — 받은 쪽지 + spacekijun 으로 보낸 답장을 한 줄기로 합친다.

받은 쪽지는 로컬 `.udb`(SQLite)에서, 답장은 spacekijun 의 `coolmsg_outbox` 에서 읽는다.
둘을 시간순으로 섞어 보여 주면 "무슨 쪽지가 왔고 내가 뭐라 답했는지"가 한 화면에 보인다.

읽기 전용이다. 앱을 건드리지 않으므로 사용 중에도 안전하다.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import shutil
import sqlite3
import tempfile
import urllib.error
import urllib.request

from . import notify, udb

UDB_GLOB = os.path.expandvars(r'%LOCALAPPDATA%\CoolMessenger\Memo\*.udb')
QUOTE_RE = re.compile(r'\s*\S{2,10}님이\s*보낸글\s*>>.*$', re.S)
DATE_RE = re.compile(r'(\d{4})/(\d{2})/(\d{2})\s+(\d{2}:\d{2}):(\d{2})')


def _norm_time(s: str) -> str:
    """'2026/09/10 11:00:24 (목)' → '09-10 11:00'. 정렬용으로도 쓴다."""
    m = DATE_RE.match(s or '')
    return f'{m.group(2)}-{m.group(3)} {m.group(4)}' if m else (s or '')[:16]


def _sort_key(s: str) -> str:
    m = DATE_RE.match(s or '')
    return ''.join(m.groups()) if m else '0'


def short_sender(s: str) -> str:
    s = (s or '').strip()
    if s.endswith(')') and '(' in s:
        head, _, last = s.rpartition('(')
        if head.split('(')[0] == last[:-1]:
            s = head
    return s


def received(limit=60, account: str | None = None) -> list[dict]:
    """
    받은 쪽지. **서버가 아니라 이 PC 의 `.udb` 파일에서만** 읽는다.

    ⚠️ 계정마다 파일이 따로 있다. 예전에는 "가장 큰 파일"을 골라서, 다른 계정으로 로그인해도
       남아 있던 옛 DB 를 읽는 문제가 있었다 → udb.pick() 이 활성 계정을 고른다.
    ⚠️ 삭제한 쪽지도 행으로 남으므로 DeletedDate IS NULL 이 필수다.
    """
    try:
        con, name, tmp = udb.open_readonly(account)
    except udb.UdbError:
        return []
    try:
        rows = con.execute(
            'SELECT MessageKey, ReceiveDate, Sender, Title, MessageText, IsUnRead '
            'FROM tbl_recv WHERE DeletedDate IS NULL '
            'ORDER BY MessageKey DESC LIMIT ?', (limit,)).fetchall()
    finally:
        udb.close_copy(con, tmp)

    out = []
    for key, when, sender, title, text, unread in rows:
        when = str(when or '')
        body = ' '.join(QUOTE_RE.sub('', (text or '').strip() or (title or '')).split())
        out.append({'kind': '받음', 'when': when, 'time': _norm_time(when),
                    'sort': _sort_key(when), 'who': short_sender(sender),
                    'body': body, 'status': '안읽음' if unread else '',
                    'key': key, 'account': name})
    return out


def replies(limit=40) -> list[dict]:
    """spacekijun 에서 쓴 답장. 로그인/설정이 없으면 조용히 빈 목록."""
    try:
        cfg = notify.config()
        headers = notify._auth_headers(cfg)
        req = urllib.request.Request(
            cfg['url'].rstrip('/') +
            f'/rest/v1/coolmsg_outbox?select=to_name,body,status,created_at,attempts'
            f'&order=created_at.desc&limit={limit}', headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read().decode('utf-8'))
    except Exception:
        return []

    label = {'pending': '대기', 'sending': '보내는 중', 'sent': '', 'failed': '실패'}
    out = []
    for r in rows:
        try:
            t = datetime.datetime.fromisoformat(r['created_at']).astimezone()
            when = t.strftime('%Y/%m/%d %H:%M:%S')
            shown = t.strftime('%m-%d %H:%M')
            sort = t.strftime('%Y%m%d%H%M%S')
        except Exception:
            when, shown, sort = r.get('created_at', ''), (r.get('created_at') or '')[:16], '0'
        out.append({'kind': '답장', 'when': when, 'time': shown, 'sort': sort,
                    'who': r.get('to_name', ''), 'body': ' '.join((r.get('body') or '').split()),
                    'status': label.get(r.get('status'), r.get('status', '')), 'key': None})
    return out


def timeline(limit=60, account: str | None = None) -> list[dict]:
    """받은 쪽지 + 답장을 시간 역순으로 합친다."""
    rows = received(limit, account) + replies(limit)
    rows.sort(key=lambda r: r['sort'], reverse=True)
    return rows[:limit]
