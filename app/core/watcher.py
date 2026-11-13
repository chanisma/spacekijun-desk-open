"""
쿨메신저 새 쪽지 감시 + 답장 큐 처리 — watch-messages.py / outbox.py 의 통합 포팅.

GUI 에서 **스레드로** 돌린다. 창을 띄우지 않고 백그라운드에서 동작하며, 상태는 콜백으로 알린다.

받는 쪽
  `.udb`(SQLite)를 복사해 read-only 로 열고 `tbl_recv` 의 새 MessageKey 를 본다.
  앱을 전혀 건드리지 않으므로 사용자가 쓰는 중에도 안전하다.

보내는 쪽 (2026-10-18 부터 기본 꺼짐)
  spacekijun 의 `coolmsg_outbox` 를 훑어 pending 을 쿨메신저로 보낸다.
  일시적 실패는 몇 번 자동 재시도한다(앱 재시작 직전에 실패한 사례가 있었다).
  ⚠️ spacekijun 의 [답장]은 2026-09-22 부터 쿨메신저가 아니라 앱 알림(`direct_reply`)으로 간다 —
     이 큐에 쓰는 곳이 없는데 켜 둔 데스크마다 30초마다 서버에 물어 하루 2,880번씩 빈 결과를 받았다
     (게이트웨이 로그 실측: PC 3대 9,613건/일). 받는 쪽(로컬 `.udb`)은 서버에 묻지 않으므로 그대로 둔다.
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
import threading
import time
import traceback
import urllib.error
import urllib.request

from . import coolmsg, notify, summarize, udb
from . import edition

DATA_DIR = edition.DATA_DIR      # 판마다 따로 (core/edition.py)
STATE_PATH = os.path.join(DATA_DIR, 'watch-state.json')
UDB_GLOB = os.path.expandvars(r'%LOCALAPPDATA%\CoolMessenger\Memo\*.udb')

SUMMARY_MIN = 150            # 본문이 이보다 길면 Solar 로 요약한다
GROUP_ABOVE = 5              # 이보다 많으면 요약 알림 1건으로 묶는다
MAX_ATTEMPTS = 3
RETRY_AFTER_SEC = 300

# 답장에 딸려오는 인용부: '○○님이 보낸글 >> …'
QUOTE_RE = re.compile(r'\s*\S{2,10}님이\s*보낸글\s*>>.*$', re.S)


# ── 상태 ──────────────────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_state(st: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


# ── 수신 ──────────────────────────────────────────────────────
def _read_new(last_key: int, account: str | None = None) -> list[tuple]:
    """
    ⚠️ 계정마다 `.udb` 가 따로 있다. 잘못 고르면 **남의 쪽지를 읽어 알림으로 보낸다.**
       udb.pick() 이 활성 계정(가장 최근에 쓰인 DB)을 고른다.
    """
    try:
        con, _name, tmp = udb.open_readonly(account)
    except udb.UdbError:
        return []
    try:
        return con.execute(
            'SELECT MessageKey, ReceiveDate, Sender, Title, MessageText FROM tbl_recv '
            'WHERE MessageKey > ? AND DeletedDate IS NULL ORDER BY MessageKey',
            (last_key,)).fetchall()
    finally:
        udb.close_copy(con, tmp)


def recipient_count(reference: str | None, cc: str | None = None) -> int:
    """받는 사람 수 — `ReferenceList`·`CCList` 는 '|67|112|…|' 꼴의 사용자 번호 목록 (2026-11-05: 단체 쪽지인지 분석에 넘긴다)."""
    return sum(len([part for part in (value or '').split('|') if part.strip()]) for value in (reference, cc))


def recipient_counts(keys: list[int], account: str | None = None) -> dict[int, int]:
    """쪽지 번호 → 받는 사람 수. 읽지 못하면 빈 dict (분석은 수 없이 진행)."""
    if not keys:
        return {}
    try:
        con, _name, tmp = udb.open_readonly(account)
    except udb.UdbError:
        return {}
    try:
        marks = ','.join('?' * len(keys))
        rows = con.execute(f'SELECT MessageKey, ReferenceList, CCList FROM tbl_recv WHERE MessageKey IN ({marks})', list(keys)).fetchall()
    except Exception:
        return {}
    finally:
        udb.close_copy(con, tmp)
    return {key: recipient_count(reference, cc) for key, reference, cc in rows}


def message_by_key(key: int, account: str | None = None) -> dict | None:
    """받은 쪽지 하나 {key, when, sender, body, recipients} — 분석 기록을 에이전트에게 맡길 때(본문은 기록에 남기지 않으므로 다시 읽는다).
    ⚠️ MessageKey 는 계정마다 따로다 — 부르는 쪽에서 보낸 사람이 기록과 같은지 맞춰 본다."""
    try:
        con, _name, tmp = udb.open_readonly(account)
    except udb.UdbError:
        return None
    try:
        row = con.execute('SELECT ReceiveDate, Sender, Title, MessageText, ReferenceList, CCList FROM tbl_recv '
                          'WHERE MessageKey = ? AND DeletedDate IS NULL', (key,)).fetchone()
    finally:
        udb.close_copy(con, tmp)
    if not row:
        return None
    when, sender, title, text, reference, cc = row
    return {'key': key, 'when': when, 'sender': short_sender(sender), 'body': body_of(title, text),
            'recipients': recipient_count(reference, cc)}


def short_sender(s: str) -> str:
    """'정태오(정태오)' → '정태오',  '류태오(1-4)(류태오)' → '류태오(1-4)'."""
    s = (s or '').strip()
    if s.endswith(')') and '(' in s:
        head, _, last = s.rpartition('(')
        if head.split('(')[0] == last[:-1]:
            s = head
    return s


def body_of(title: str, text: str) -> str:
    """
    ⚠️ `Title` 은 쓰면 안 된다 — 발신자가 제목을 비우면 본문 앞부분이 **잘린 채** 제목에 들어간다.
       전문은 `MessageText` 에 있다.
    """
    raw = (text or '').strip() or (title or '')
    return ' '.join(QUOTE_RE.sub('', raw).split())


def _clip(s: str, n: int) -> str:
    return s[:n] + ('…' if len(s) > n else '')


def notice_body(title: str, text: str, use_summary: bool) -> str:
    full = body_of(title, text)
    if not use_summary or len(full) < SUMMARY_MIN:
        return _clip(full, 400)
    s = summarize.summarize(full)
    return f'{s}\n(요약 · 원문 {len(full)}자)' if s else _clip(full, 400)


def reset_baseline(account: str | None = None) -> int:
    """
    기준점을 지금 시점으로 옮긴다.

    ⚠️ `MessageKey` 는 **계정마다 따로** 매겨진다. 계정을 바꾸면 예전 기준점이
       엉뚱한 번호가 되어, 이미 읽은 쪽지가 무더기로 알림에 뜨거나(번호가 작아졌을 때)
       새 쪽지를 통째로 놓친다(번호가 커졌을 때). 계정을 바꿀 때 반드시 부른다.
    """
    st = load_state()
    rows = _read_new(-1, account)
    st['last_key'] = rows[-1][0] if rows else 0
    save_state(st)
    return st['last_key']


def check_inbox(st: dict, use_summary=True, show_body=True, log=print, on_message=None) -> dict:
    """on_message({key, when, sender, body, recipients}) — 새 쪽지마다 (메인 상주 에이전트의 분석, core/resident_tasks.py). 알림과 따로 돈다."""
    rows = _read_new(st['last_key'])
    if not rows:
        return st
    if on_message:
        counts = recipient_counts([row[0] for row in rows])
        for key, when, sender, title, text in rows:
            try:
                on_message({'key': key, 'when': when, 'sender': short_sender(sender), 'body': body_of(title, text),
                            'recipients': counts.get(key)})
            except Exception as exc:                 # 분석이 알림을 막지 않게
                log(f'쪽지 분석에 넘기지 못함: {exc}')
    log(f'새 쪽지 {len(rows)}건')
    if len(rows) <= GROUP_ABOVE:
        for key, when, sender, title, text in rows:
            who = short_sender(sender)
            notify.send(
                f'[쿨메신저] {who}',
                notice_body(title, text, use_summary) if show_body else '새 쪽지가 도착했습니다.',
                meta={'source': 'coolmessenger', 'sender': who,
                      'sender_plain': who.split('(')[0].strip() or who,
                      'message_key': key, 'received_at': when})
            log(f'  알림: {who}')
    else:
        names = []
        for _, _, sender, _, _ in rows:
            w = short_sender(sender)
            if w not in names:
                names.append(w)
        notify.send(f'[쿨메신저] 새 쪽지 {len(rows)}건', ', '.join(names[:8]),
                    meta={'source': 'coolmessenger'})
        log(f'  요약 알림 1건 ({len(rows)}건 묶음)')
    st['last_key'] = rows[-1][0]
    st['last_notified_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    save_state(st)
    return st


# ── 답장 큐 ───────────────────────────────────────────────────
def _outbox_req(method, path, body=None, extra=None):
    cfg = notify.config()
    headers = dict(notify._auth_headers(cfg))
    headers['Content-Type'] = 'application/json'
    headers.update(extra or {})
    req = urllib.request.Request(
        cfg['url'].rstrip('/') + '/rest/v1/' + path,
        data=json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None,
        headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode('utf-8')
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        raise notify.NotifyError('%s %s -> %s' % (
            e.code, e.reason, e.read().decode('utf-8', 'replace'))) from None


def _todo(limit=10) -> list[dict]:
    rows = _outbox_req('GET', f'coolmsg_outbox?status=in.(pending,failed)'
                              f'&attempts=lt.{MAX_ATTEMPTS}&order=created_at.asc&limit={limit}') or []
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    for r in rows:
        if r.get('status') == 'failed' and r.get('last_attempt_at'):
            try:
                if (now - datetime.datetime.fromisoformat(
                        r['last_attempt_at'])).total_seconds() < RETRY_AFTER_SEC:
                    continue
            except ValueError:
                pass
        out.append(r)
    return out


def _mark(row_id, **fields):
    _outbox_req('PATCH', f'coolmsg_outbox?id=eq.{row_id}', fields, {'Prefer': 'return=minimal'})


def check_outbox(log=print) -> int:
    rows = _todo()
    if not rows:
        return 0
    log(f'보낼 답장 {len(rows)}건')
    done = 0
    for r in rows:
        tries = r.get('attempts') or 0
        log(f"  → {r['to_name']}" + (f' (재시도 {tries + 1}회차)' if tries else ''))
        _mark(r['id'], status='sending', attempts=tries + 1, last_attempt_at='now()')
        try:
            sent = coolmsg.send([r['to_name']], r['title'], r['body'], log=lambda *_: None)
            _mark(r['id'], status='sent', sent_at='now()', error=None)
            log('    발송 완료 (도착: %s)' % (sent.get('scheduled') or '즉시'))
            done += 1
        except Exception as e:
            _mark(r['id'], status='failed', error=str(e)[:1000])
            left = MAX_ATTEMPTS - (tries + 1)
            log(f'    실패 — {str(e)[:120]}')
            log('    ' + (f'{RETRY_AFTER_SEC // 60}분 뒤 자동 재시도 ({left}회 남음)'
                          if left > 0 else '재시도 한도 도달 — 확인이 필요합니다'))
    return done


# ── 루프 ──────────────────────────────────────────────────────
class Watcher:
    """GUI 에서 시작·중지하는 감시 스레드."""

    def __init__(self, interval=30, use_summary=True, show_body=True,
                 do_outbox=False, log=print):
        self.interval = interval
        self.use_summary = use_summary
        self.show_body = show_body
        self.do_outbox = do_outbox
        self.log = log
        self.on_message = None        # 새 쪽지마다 부를 것 (데스크가 붙인다 — 메인 상주 에이전트의 분석)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        if self.running:
            return
        st = load_state()
        if st.get('last_key') is None:
            rows = _read_new(-1)
            st['last_key'] = rows[-1][0] if rows else 0
            save_state(st)
            self.log(f"기준점 설정: MessageKey={st['last_key']} (이후 도착분부터 알립니다)")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name='cm-watcher')
        self._thread.start()
        self.log(f'감시 시작 — {self.interval}초 간격')

    def stop(self):
        self._stop.set()
        self.log('감시 중지')

    def _run(self):
        while not self._stop.is_set():
            st = load_state()
            try:
                check_inbox(st, self.use_summary, self.show_body, self.log, self.on_message)
                self.last_error = None
            except Exception as e:
                self.last_error = str(e)
                self.log(f'수신 확인 오류: {e}')
                traceback.print_exc()
            if self.do_outbox:
                try:
                    check_outbox(self.log)
                except Exception as e:
                    self.last_error = str(e)
                    self.log(f'답장 큐 오류: {e}')
            self._stop.wait(self.interval)
