"""
에듀파인 문서 목록 위에 «바로보기» 단추를 얹는다 (2026-11-12 요청).

에듀파인에서 공문 내용을 보려면 제목을 눌러 뷰어 프로그램(WXSClient)이 뜨기를 기다려야 한다.
SPACEKIJUN DB(`official_doc`)에는 서버 PC 가 모은 본문과 AI 1차 판정이 이미 있다. 그래서
목록에서 DB 에 있는 문서 옆에 단추를 붙이고, 누르면 그 자리에서 오버레이로 보여 준다.
나이스 도우미처럼 화면을 옮기지는 않는다 — 보기만 한다. 에듀파인에 아무것도 쓰지 않는다.

## 짝

- 화면 쪽은 `web/klef-overlay.js` (Shadow DOM, 목록 프레임에서 돈다).
- 문서번호 = 목록 체크박스 `input[name=docinfo]` 값의 17번째 칸(«학교명-13628») = `official_doc.doc_no`.
  (klef-portal SKILL 5-10 · klef-cli.js `rows()` 와 같은 읽기)

## 왜 이렇게 만들었나

**표(ticket)를 주고 나중에 물어본다** — `neis_overlay` 와 같은 까닭이다. 페이지가 부르는 함수는
Playwright 스레드 위에서 돈다. 거기서 Supabase 응답을 기다리면 나이스 도우미까지 멈춘다.
`__deskKlefDocs` 는 캐시에 다 있으면 바로 답하고, 없으면 일꾼 스레드에 맡기고 표만 돌려준다.

**읽기 권한은 DB 가 정한다.** 데스크에 로그인한 계정의 토큰으로 PostgREST 를 부르므로 RLS 가
그대로 걸린다 — 관리자는 모든 공문, 교사는 결재권자가 본인인 공문만 보인다
(spacekijun `20261108110000_official_doc_owner_read.sql`). 못 보는 문서에는 단추가 붙지 않는다.

**토큰은 페이지에 넘기지 않는다.** 에듀파인 페이지의 스크립트가 읽을 수 있는 곳에 열쇠를 두지 않고,
데스크가 대신 받아 그 문서의 내용만 건넨다.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

SCRIPT_NAME = 'klef-overlay.js'
HOST = 'klef.jbe.go.kr'
CACHE_SECONDS = 300          # 같은 문서를 5분 안에 다시 물으면 DB 에 가지 않는다
MISS_SECONDS = 120           # «DB 에 없음»은 더 짧게 — 서버 PC 가 곧 모을 수 있다
BATCH = 25                   # 한 번에 묻는 문서번호 수 (주소 길이 — 한글 번호라 길다)
MAX_ITEMS = 200              # 한 쪽에서 받는 최대 행 수 (에듀파인 쪽당 최대 100)
TICKET_SECONDS = 120
_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
# 바로보기에서 데스크의 스페이스기전 창으로 열 수 있는 주소 — 업무노트 한 장(할 일 지정 가능)·구매 신청 페이지만
SPACE_PAGE = re.compile(rf'/work/o/work/{_UUID}(\?task={_UUID})?|/purchase-requests/{_UUID}(\?tab=(order|mine|manage))?')

DOC_FIELDS = ('id,doc_no,title,sender,registered_at,approver_name,drafter_name,approval_type,'
              'process_status,body,body_status,attachments,meta,'
              'official_doc_triage(nature,needs_action,deadline,confidence,question,result,model,created_at),'
              'official_doc_decision(decision,nature,reason,assignee_names,created_at,work_id,task_id)')


def _web_dir() -> Path:
    bundled = getattr(sys, '_MEIPASS', None)
    if bundled:
        return Path(bundled) / 'web'
    return Path(__file__).resolve().parents[1] / 'web'


def source_path() -> Path:
    return _web_dir() / SCRIPT_NAME


def script() -> str:
    return source_path().read_text(encoding='utf-8')


def _clean_items(items) -> list[dict]:
    """페이지가 보낸 행 목록을 믿지 않고 다듬는다 — 문자열·길이만 남긴다."""
    out, seen = [], set()
    for item in (items if isinstance(items, list) else [])[:MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        no = str(item.get('no') or '').strip()[:80]
        title = str(item.get('title') or '').strip()[:300]
        key = no or ('t:' + title if title else '')
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({'no': no, 'title': title, 'key': key})
    return out


def shape(row: dict) -> dict:
    """DB 한 행 → 오버레이가 그리는 모양. 판정·결정은 가장 최근 것 하나만."""
    triages = sorted(row.get('official_doc_triage') or [], key=lambda t: t.get('created_at') or '', reverse=True)
    decisions = sorted(row.get('official_doc_decision') or [], key=lambda d: d.get('created_at') or '', reverse=True)
    triage, decision = (triages[0] if triages else None), (decisions[0] if decisions else None)
    result = (triage or {}).get('result') or {}
    meta = row.get('meta') or {}
    return {
        'doc_no': row.get('doc_no') or '',
        'title': row.get('title') or '',
        'sender': row.get('sender') or meta.get('발신기관') or '',
        'registered_at': row.get('registered_at') or '',
        'approver': row.get('approver_name') or '',
        'drafter': row.get('drafter_name') or '',
        'status': row.get('process_status') or '',
        'body': row.get('body') or '',
        'body_status': row.get('body_status') or 'none',
        'attachments': [a.get('name') if isinstance(a, dict) else str(a) for a in (row.get('attachments') or [])][:30],
        'meta': {k: meta.get(k) for k in ('시행', '접수', '붙임', '관련', '수신', '경유', 'similar') if meta.get(k)},
        'triage': None if not triage else {
            'nature': triage.get('nature') or result.get('nature') or '',
            'needs_action': triage.get('needs_action'),
            'deadline': triage.get('deadline') or result.get('deadline') or '',
            'confidence': triage.get('confidence'),
            'question': triage.get('question') or result.get('question') or '',
            'model': triage.get('model') or '',
            'at': triage.get('created_at') or '',
            'summary': result.get('summary') or '',
            'obligation': result.get('obligation') or '',
            'obligation_why': result.get('obligation_why') or '',
            'deadlines': result.get('deadlines') or [],
            'target': result.get('target') or '',
            'survey_respondent': result.get('survey_respondent') or '',
            'work_candidates': [{'name': w.get('name', ''), 'why': w.get('why', '')}
                                for w in (result.get('work_candidates') or []) if isinstance(w, dict)][:5],
            'assignees': [{'name': a.get('name', ''), 'why': a.get('why', '')}
                          for a in (result.get('assignees') or []) if isinstance(a, dict)][:5],
            'uncertain': [u for u in (result.get('uncertain') or []) if isinstance(u, dict)][:5],
            'parent': [p for p in (result.get('parent') or []) if isinstance(p, dict)][:5],
        },
        'pages': [],                 # 이 공문과 이어진 업무노트 페이지 — _attach_pages 가 채운다
        'decision': None if not decision else {
            'decision': decision.get('decision') or '',
            'nature': decision.get('nature') or '',
            'reason': decision.get('reason') or '',
            'assignees': decision.get('assignee_names') or [],
            'at': decision.get('created_at') or '',
        },
    }


class DocLookup:
    """문서번호 → DB 분석 결과. 캐시·표·일꾼 스레드만 쥔다 (Playwright 를 부르지 않는다)."""

    def __init__(self, fetch=None, log=print):
        self._fetch = fetch or self._fetch_rest
        self._log = log
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict | None]] = {}   # key → (받은 때, 문서 또는 None)
        self._tickets: dict[str, dict] = {}

    # ── 페이지가 부르는 두 함수 ───────────────────────────────
    def ask(self, items) -> dict:
        """행 목록을 받는다. 캐시로 다 답할 수 있으면 `{docs}`, 아니면 `{ticket}`."""
        rows = _clean_items(items)
        if not rows:
            return {'docs': {}}
        now = time.time()
        with self._lock:
            missing = [r for r in rows if not self._fresh(r['key'], now)]
            if not missing:
                return {'docs': self._answer(rows)}
            ticket = uuid.uuid4().hex
            self._tickets[ticket] = {'at': now, 'done': False, 'rows': rows}
            self._sweep(now)
        threading.Thread(target=self._work, args=(ticket, missing), name='klef-doc-lookup', daemon=True).start()
        return {'ticket': ticket}

    def poll(self, ticket) -> dict:
        with self._lock:
            job = self._tickets.get(str(ticket or ''))
            if not job:
                return {'error': '요청이 만료됐습니다.'}
            if not job['done']:
                return {'pending': True}
            self._tickets.pop(str(ticket), None)
            if job.get('error'):
                return {'error': job['error']}
            return {'docs': self._answer(job['rows'])}

    # ── 안쪽 ───────────────────────────────────────────────
    def _fresh(self, key, now) -> bool:
        hit = self._cache.get(key)
        if not hit:
            return False
        return now - hit[0] < (CACHE_SECONDS if hit[1] else MISS_SECONDS)

    def _answer(self, rows) -> dict:
        out = {}
        for r in rows:
            hit = self._cache.get(r['key'])
            if hit and hit[1]:
                out[r['key']] = hit[1]
        return out

    def _sweep(self, now):
        for name in [n for n, j in self._tickets.items() if now - j['at'] > TICKET_SECONDS]:
            self._tickets.pop(name, None)

    def _work(self, ticket, rows):
        error = ''
        try:
            found = self._fetch(rows)
            now = time.time()
            with self._lock:
                for r in rows:
                    self._cache[r['key']] = (now, found.get(r['key']))
        except Exception as exc:
            error = _friendly(exc)
            self._log('에듀파인 바로보기 — 분석 결과를 받지 못했습니다:', exc)
        with self._lock:
            job = self._tickets.get(ticket)
            if job:
                job['done'], job['error'] = True, error

    def _fetch_rest(self, rows) -> dict:
        """문서번호로 묻고, 번호가 없는 행은 제목이 **하나만** 맞을 때만 쓴다."""
        found: dict[str, dict] = {}
        raws: dict[str, dict] = {}
        numbers = [r for r in rows if r['no']]
        for start in range(0, len(numbers), BATCH):
            chunk = numbers[start:start + BATCH]
            for row in _rest('doc_no', [r['no'] for r in chunk]):
                for r in chunk:
                    if r['no'] == row.get('doc_no'):
                        found[r['key']] = shape(row)
                        raws[r['key']] = row
        titled = [r for r in rows if not r['no'] and r['title']]
        for start in range(0, len(titled), BATCH):
            chunk = titled[start:start + BATCH]
            hits: dict[str, list] = {}
            for row in _rest('title', [r['title'] for r in chunk]):
                hits.setdefault(row.get('title') or '', []).append(row)
            for r in chunk:
                same = hits.get(r['title']) or []
                if len(same) == 1:
                    found[r['key']] = shape(same[0])
                    raws[r['key']] = same[0]
        try:
            _attach_pages(found, raws)
        except Exception as exc:          # 업무노트 연결은 덤이다 — 못 받아도 분석 결과는 보인다
            self._log('에듀파인 바로보기 — 업무노트 연결을 받지 못했습니다:', exc)
        return found


# ── 품의목록 ↔ SPACEKIJUN 구매 신청 품의 차수 (2026-11-12 요청) ─────────────────────
# 에듀파인 학교회계 › 품의목록(Nexacro, FADMANGECLI001M01 · dsMain)의 행을 품의 차수(purchase_order_batches)에 잇는다.
# 이음은 차수의 edufine_no(= 품의번호 sclCnsulNo) → 없으면 edufine_title(= 품의 제목 sj, 하나만 맞을 때).
# 이음이 없는 품의는 사람이 «구매 신청과 연결»로 한 번 고른다(담당자 토큰 PATCH, 정책 manager_all — 담당자만 보이고 고친다).
# spacekijun 20261112140000_purchase_order_edufine.sql
BATCH_FIELDS = ('id,page_id,title,status,status_updated_at,edufine_title,edufine_no,edufine_linked_at,'
                'purchase_request_pages(title),purchase_order_lines(name,unit_price,qty)')
BATCH_STATUS = {'draft': '작성 중', 'submitted': '품의 완료', 'purchased': '구매 완료'}
CNSUL_NO = re.compile(r'[0-9A-Za-z]{1,40}')


def batch_shape(row: dict) -> dict:
    lines = row.get('purchase_order_lines') or []
    total = sum((l.get('unit_price') or 0) * (l.get('qty') or 0) for l in lines
                if isinstance(l.get('unit_price'), (int, float)) and isinstance(l.get('qty'), (int, float)))
    page_id = str(row.get('page_id') or '')
    return {
        'id': row.get('id') or '', 'title': row.get('title') or '', 'status': row.get('status') or '',
        'status_label': BATCH_STATUS.get(row.get('status') or '', row.get('status') or ''),
        'page_title': (row.get('purchase_request_pages') or {}).get('title') or '',
        'total': int(total) if float(total).is_integer() else total,
        'lines': [l.get('name') or '' for l in lines][:6], 'line_count': len(lines),
        'edufine_title': row.get('edufine_title') or '', 'edufine_no': row.get('edufine_no') or '',
        'at': row.get('status_updated_at') or '',
        'route': f'/purchase-requests/{page_id}?tab=order' if re.fullmatch(_UUID, page_id) else '',
    }


def cnsul_lookup(items) -> dict:
    """품의목록 행들 → {행 key: [이어진 차수…]}. key = 품의번호(없으면 't:'+제목)."""
    rows = _clean_items(items)
    found: dict[str, list] = {}
    numbers = [r for r in rows if r['no'] and CNSUL_NO.fullmatch(r['no'])]
    for start in range(0, len(numbers), BATCH):
        chunk = numbers[start:start + BATCH]
        for row in _get('purchase_order_batches', {'select': BATCH_FIELDS, 'edufine_no': _in([r['no'] for r in chunk])}):
            for r in chunk:
                if r['no'] == row.get('edufine_no'):
                    found.setdefault(r['key'], []).append(batch_shape(row))
    titled = [r for r in rows if r['key'] not in found and r['title']]
    for start in range(0, len(titled), BATCH):
        chunk = titled[start:start + BATCH]
        hits: dict[str, list] = {}
        for row in _get('purchase_order_batches', {'select': BATCH_FIELDS, 'edufine_title': _in([r['title'] for r in chunk])}):
            hits.setdefault(row.get('edufine_title') or '', []).append(row)
        for r in chunk:
            for row in hits.get(r['title']) or []:
                if not row.get('edufine_no') or row.get('edufine_no') == r['no']:   # 다른 품의번호로 이은 차수는 아니다
                    found.setdefault(r['key'], []).append(batch_shape(row))
    return found


def list_batches() -> list[dict]:
    """«구매 신청과 연결» 창에 보일 차수 — 내가 담당자인 페이지의 차수(RLS), 최근 것부터."""
    rows = _get('purchase_order_batches', {'select': BATCH_FIELDS, 'order': 'status_updated_at.desc.nullslast,created_at.desc', 'limit': '300'})
    return [batch_shape(r) for r in rows]


def link_batch(payload) -> dict:
    """차수 하나에 에듀파인 품의(제목·품의번호)를 잇거나(unlink=true 면) 끊는다. 담당자만 고쳐진다(RLS)."""
    payload = payload if isinstance(payload, dict) else {}
    batch_id = str(payload.get('batch_id') or '')
    if not re.fullmatch(_UUID, batch_id):
        raise ValueError('품의 차수를 고르지 않았습니다.')
    if payload.get('unlink'):
        body = {'edufine_title': None, 'edufine_no': None, 'edufine_linked_at': None}
    else:
        title = str(payload.get('title') or '').strip()[:300]
        no = str(payload.get('no') or '').strip()
        if not title or not CNSUL_NO.fullmatch(no):
            raise ValueError('품의 제목·품의번호를 읽지 못했습니다.')
        body = {'edufine_title': title, 'edufine_no': no,
                'edufine_linked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    from . import notify, supa_auth
    cfg = notify.config()
    url = cfg['url'].rstrip('/') + '/rest/v1/purchase_order_batches?' + urllib.parse.urlencode(
        {'id': f'eq.{batch_id}', 'select': BATCH_FIELDS})
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), method='PATCH', headers={
        **supa_auth.auth_headers(), 'Accept': 'application/json', 'Content-Type': 'application/json',
        'Prefer': 'return=representation'})
    with urllib.request.urlopen(req, timeout=20) as response:
        rows = json.loads(response.read().decode('utf-8'))
    if not rows:
        raise PermissionError('이 차수를 고칠 권한이 없습니다 (구매 신청 페이지 담당자만).')
    return batch_shape(rows[0])


class Jobs:
    """페이지가 맡기는 일(품의 찾기·차수 목록·연결) — DocLookup 처럼 표를 주고 일꾼 스레드에서 한다."""

    KINDS = {'cnsul': cnsul_lookup, 'batches': lambda _payload=None: list_batches(), 'link': link_batch}

    def __init__(self, log=print, kinds=None):
        self._log = log
        self._kinds = kinds or self.KINDS
        self._lock = threading.Lock()
        self._tickets: dict[str, dict] = {}

    def ask(self, kind='', payload=None) -> dict:
        work = self._kinds.get(str(kind or ''))
        if not work:
            return {'error': '모르는 일입니다.'}
        ticket = uuid.uuid4().hex
        with self._lock:
            now = time.time()
            for name in [n for n, j in self._tickets.items() if now - j['at'] > TICKET_SECONDS]:
                self._tickets.pop(name, None)
            self._tickets[ticket] = {'at': now, 'done': False}
        threading.Thread(target=self._run, args=(ticket, work, payload), name='klef-job', daemon=True).start()
        return {'ticket': ticket}

    def poll(self, ticket='') -> dict:
        with self._lock:
            job = self._tickets.get(str(ticket or ''))
            if not job:
                return {'error': '요청이 만료됐습니다.'}
            if not job['done']:
                return {'pending': True}
            self._tickets.pop(str(ticket), None)
            return {'error': job['error']} if job.get('error') else {'result': job.get('result')}

    def _run(self, ticket, work, payload):
        result, error = None, ''
        try:
            result = work(payload)
        except (ValueError, PermissionError) as exc:
            error = str(exc)
        except Exception as exc:
            error = _friendly(exc)
            self._log('에듀파인 바로보기 — 품의 연결 작업 실패:', exc)
        with self._lock:
            job = self._tickets.get(ticket)
            if job:
                job.update(done=True, result=result, error=error)


def _attach_pages(found: dict, raws: dict) -> None:
    """공문마다 이어진 업무노트 페이지를 붙인다 (2026-11-12 요청 — 에듀파인에서 SPACEKIJUN 페이지를 바로 연다).

    이음은 두 군데에 남는다(spacekijun officialDocService·officialDocDecision):
      · 판단함의 **가장 최근** 결정 `official_doc_decision.work_id / task_id`
      · 업무·할 일의 `meta.fromOfficialDoc.doc_no` (판단함 밖에서 공문으로 만든 것)
    할 일은 따로 쪽이 없어서 그 할 일이 든 업무 쪽(`/work/o/work/<업무>?task=<할 일>`)으로 연다. 읽기 권한은 RLS 그대로.
    """
    if not found:
        return
    by_no = {doc['doc_no']: key for key, doc in found.items() if doc.get('doc_no')}
    want_work: dict[str, set] = {}       # 업무 id → 문서 key 들
    want_task: dict[str, set] = {}
    for key, row in raws.items():
        decisions = sorted(row.get('official_doc_decision') or [], key=lambda d: d.get('created_at') or '', reverse=True)
        latest = decisions[0] if decisions else {}
        if latest.get('task_id'):
            want_task.setdefault(latest['task_id'], set()).add(key)
        elif latest.get('work_id'):
            want_work.setdefault(latest['work_id'], set()).add(key)
    tasks: dict[str, dict] = {}
    works: dict[str, dict] = {}
    numbers = list(by_no)
    for start in range(0, len(numbers), BATCH):
        chunk = numbers[start:start + BATCH]
        for item in _get('task', {'select': 'id,title,event_id,meta->fromOfficialDoc', 'meta->fromOfficialDoc->>doc_no': _in(chunk)}):
            no = ((item.get('fromOfficialDoc') or {}).get('doc_no') or '')
            if no in by_no:
                want_task.setdefault(item['id'], set()).add(by_no[no])
                tasks[item['id']] = item
        for item in _get('work', {'select': 'id,name,meta->fromOfficialDoc', 'meta->fromOfficialDoc->>doc_no': _in(chunk)}):
            no = ((item.get('fromOfficialDoc') or {}).get('doc_no') or '')
            if no in by_no:
                want_work.setdefault(item['id'], set()).add(by_no[no])
                works[item['id']] = item
    missing = [i for i in want_task if i not in tasks]
    for start in range(0, len(missing), BATCH):
        for item in _get('task', {'select': 'id,title,event_id', 'id': _in(missing[start:start + BATCH])}):
            tasks[item['id']] = item
    parents = {t.get('event_id') for t in tasks.values() if t.get('event_id')} | set(want_work)
    missing = [i for i in parents if i not in works]
    for start in range(0, len(missing), BATCH):
        for item in _get('work', {'select': 'id,name', 'id': _in(missing[start:start + BATCH])}):
            works[item['id']] = item
    for task_id, keys in want_task.items():
        task = tasks.get(task_id)
        if not task or not task.get('event_id'):
            continue                                   # 못 보는 할 일(RLS)·업무 없는 할 일
        work = works.get(task['event_id']) or {}
        page = {'route': f"/work/o/work/{task['event_id']}?task={task_id}", 'kind': '할 일',
                'title': task.get('title') or '할 일', 'parent': work.get('name') or ''}
        for key in keys:
            found[key]['pages'].append(page)
    for work_id, keys in want_work.items():
        work = works.get(work_id)
        if not work:
            continue
        page = {'route': f'/work/o/work/{work_id}', 'kind': '업무', 'title': work.get('name') or '업무', 'parent': ''}
        for key in keys:
            pages = found[key]['pages']
            if not any(p['route'].startswith(page['route']) for p in pages):   # 그 업무의 할 일 쪽이 이미 있으면 겹치지 않게
                pages.append(page)
    for doc in found.values():
        doc['pages'] = [p for p in doc['pages'] if SPACE_PAGE.fullmatch(p['route'])][:12]


def _in(values) -> str:
    return 'in.(' + ','.join(_quote(v) for v in values) + ')'


def _get(table: str, params: dict) -> list[dict]:
    from . import notify, supa_auth
    cfg = notify.config()
    req = urllib.request.Request(cfg['url'].rstrip('/') + f'/rest/v1/{table}?' + urllib.parse.urlencode(params),
                                 headers={**supa_auth.auth_headers(), 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        rows = json.loads(response.read().decode('utf-8'))
    return rows if isinstance(rows, list) else []


def _quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _rest(column: str, values: list[str]) -> list[dict]:
    from . import notify, supa_auth
    cfg = notify.config()
    query = urllib.parse.urlencode({
        'select': DOC_FIELDS,
        column: 'in.(' + ','.join(_quote(v) for v in values) + ')',
        'limit': str(len(values) * 3),
    })
    req = urllib.request.Request(cfg['url'].rstrip('/') + '/rest/v1/official_doc?' + query,
                                 headers={**supa_auth.auth_headers(), 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode('utf-8'))


def _friendly(exc) -> str:
    name = type(exc).__name__
    if name == 'AuthError':
        return 'SPACEKIJUN 에 로그인하면 분석 결과를 볼 수 있습니다 (데스크 설정).'
    if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403):
        return 'SPACEKIJUN 로그인이 만료됐습니다. 데스크 설정에서 다시 로그인해 주세요.'
    return '분석 결과를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.'


# ── 창에 심기 ────────────────────────────────────────────────
def is_klef(url: str) -> bool:
    try:
        return urllib.parse.urlsplit(url or '').hostname == HOST
    except ValueError:
        return False


def install(page, lookup: DocLookup, opener=None, jobs: 'Jobs | None' = None) -> None:
    """에듀파인 탭 하나에 심는다. 이후 그 탭의 모든 문서·프레임(목록 iframe 포함)에 붙는다.

    🚨 `neis_overlay.install` 과 같이 **이 탭에만** 심는다 — 창(context) 전체에 심으면
    다른 업무시스템 탭까지 붙잡는다(2026-09-15). 스크립트도 스스로 주소를 확인한다.
    """
    source = script()
    for name, handler in {
        '__deskKlefDocs': lambda items=None: lookup.ask(items),
        '__deskKlefPoll': lambda ticket='': lookup.poll(ticket),
        # 연결된 SPACEKIJUN 페이지를 데스크의 스페이스기전 창에 연다 — 주소 모양은 데스크가 다시 확인한다
        '__deskKlefOpen': (lambda route='': opener(route)) if opener else (lambda route='': {'ok': False}),
        # 품의목록 ↔ 구매 신청 (품의 찾기·차수 목록·연결) — 표를 주고 나중에 묻는다
        '__deskKlefJob': (lambda kind='', payload=None: jobs.ask(kind, payload)) if jobs else (lambda kind='', payload=None: {'error': '준비되지 않았습니다.'}),
        '__deskKlefJobPoll': (lambda ticket='': jobs.poll(ticket)) if jobs else (lambda ticket='': {'error': '준비되지 않았습니다.'}),
    }.items():
        try:
            page.expose_function(name, handler)
        except Exception:
            pass                      # 이미 심어 둔 탭
    page.add_init_script(source)
    for frame in page.frames:         # 이미 떠 있는 목록 iframe 에도
        try:
            frame.evaluate(source)
        except Exception:
            pass
