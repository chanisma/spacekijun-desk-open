"""스티커 메모 — SPACEKIJUN 협업노트(collab_notes)에 저장한다.

사람마다 `meta.kind = 'desk_sticky'` 인 private 보드 하나를 두고 메모를 그 안에 쌓는다.
웹의 협업노트에서도 '내 스티커 메모' 보드로 같은 메모가 보인다.

다른 사용자에게 보이지 않는 것은 **DB 가 지킨다** (spacekijun 마이그레이션
`20261008130000_desk_sticky_notes.sql`): 보드는 항상 private, 멤버 초대 불가,
교직원 전체 보드 열람 예외에서도 빠진다. 여기서는 사용자 본인 세션(RLS)으로만 접근한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import notify, supa_auth

KIND = 'desk_sticky'
BOARD_TITLE = '내 스티커 메모'
COLORS = ('#fff176', '#f48fb1', '#90caf9', '#a5d6a7', '#ce93d8', '#ffcc80', '#ffffff')
MAX_CONTENT = 20000
NOTE_FIELDS = 'id,title,content,color,updated_at,created_at'

_lock = threading.Lock()
_board_cache: dict[str, tuple[str, str]] = {}     # user_id → (board_id, resource_id)


def _request(method: str, path: str, params: dict | None = None, body=None, prefer: str | None = None):
    url = notify.config()['url'].rstrip('/') + '/rest/v1/' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    headers = {**supa_auth.auth_headers(), 'Content-Type': 'application/json'}
    if prefer:
        headers['Prefer'] = prefer
    req = urllib.request.Request(url, headers=headers, method=method,
                                 data=None if body is None else json.dumps(body).encode('utf-8'))
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            raise _Conflict() from None
        raise RuntimeError(f'메모 저장소 요청 실패 ({exc.code}). 계정 연결을 확인해 주세요.') from None
    except (OSError, ValueError):
        raise RuntimeError('서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.') from None


class _Conflict(Exception):
    pass


def _find_board(resource_id: str):
    rows = _request('GET', 'collab_boards', {'select': 'id', 'created_by': 'eq.' + resource_id,
                                             'meta->>kind': 'eq.' + KIND, 'limit': '1'})
    return rows[0]['id'] if rows else None


def board() -> tuple[str, str]:
    """(보드 id, 내 resource id). 처음이면 개인 보드를 만든다."""
    session = supa_auth.load_session() or {}
    user_id = session.get('user_id')
    if not user_id:
        raise RuntimeError('설정에서 SPACEKIJUN 계정을 연결해 주세요.')
    with _lock:
        if user_id in _board_cache:
            return _board_cache[user_id]
        resource_id = supa_auth.my_resource_id()
        board_id = _find_board(resource_id)
        if not board_id:
            try:
                rows = _request('POST', 'collab_boards', body={
                    'title': BOARD_TITLE, 'description': '스페이스기전 데스크의 개인 메모입니다. 나만 볼 수 있습니다.',
                    'color': 'yellow', 'created_by': resource_id, 'visibility': 'private',
                    'meta': {'kind': KIND}}, prefer='return=representation')
                board_id = rows[0]['id']
            except _Conflict:            # 다른 PC 의 데스크가 먼저 만들었다
                board_id = _find_board(resource_id)
            if not board_id:
                raise RuntimeError('개인 메모 보드를 준비하지 못했습니다.')
        _board_cache.clear()
        _board_cache[user_id] = (board_id, resource_id)
        return board_id, resource_id


def forget():
    """로그아웃하면 다른 계정의 보드를 쓰지 않게 비운다."""
    with _lock:
        _board_cache.clear()


def _title(content: str) -> str:
    """첫 줄을 제목으로. 메모 서식 표시(`# 제목`, `- 목록`)는 떼어 낸다 — 제목에 #가 붙지 않게."""
    first = next((line.strip() for line in content.splitlines() if line.strip()), '')
    first = re.sub(r'^(?:#{1,3}|[-*•])\s+', '', first).strip()
    return (first[:60] or '메모')


def _clean(payload: dict) -> dict:
    patch = {}
    if 'content' in payload:
        content = payload['content']
        if not isinstance(content, str):
            raise ValueError('메모 내용 형식이 올바르지 않습니다.')
        if len(content) > MAX_CONTENT:
            raise ValueError(f'메모는 {MAX_CONTENT:,}자까지 쓸 수 있습니다.')
        patch['content'] = content
        patch['title'] = _title(content)
    if 'color' in payload:
        if payload['color'] not in COLORS:
            raise ValueError('지원하지 않는 색입니다.')
        patch['color'] = payload['color']
    return patch


def _note_id(payload: dict) -> str:
    note_id = payload.get('id')
    if not isinstance(note_id, str) or not note_id or len(note_id) > 64:
        raise ValueError('메모를 찾을 수 없습니다.')
    return note_id


def notes() -> list[dict]:
    board_id, _ = board()
    return _request('GET', 'collab_notes', {'select': NOTE_FIELDS, 'board_id': 'eq.' + board_id,
                                            'is_archived': 'eq.false', 'order': 'updated_at.desc'})


def get(payload: dict) -> dict:
    board_id, _ = board()
    rows = _request('GET', 'collab_notes', {'select': NOTE_FIELDS, 'id': 'eq.' + _note_id(payload),
                                            'board_id': 'eq.' + board_id})
    if not rows:
        raise LookupError('메모가 삭제되었습니다.')
    return rows[0]


def create(payload: dict) -> dict:
    board_id, resource_id = board()
    fields = {'content': '', 'color': COLORS[0], **_clean({'content': payload.get('content', ''),
                                                          'color': payload.get('color', COLORS[0])})}
    rows = _request('POST', 'collab_notes', body={**fields, 'board_id': board_id,
                                                  'author_id': resource_id, 'meta': {'source': 'desk'}},
                    prefer='return=representation')
    note = rows[0]
    return {key: note.get(key) for key in NOTE_FIELDS.split(',')}


def update(payload: dict) -> dict:
    board_id, _ = board()
    patch = _clean(payload)
    if not patch:
        raise ValueError('바꿀 내용이 없습니다.')
    patch['updated_at'] = datetime.now(timezone.utc).isoformat()
    # board_id 조건을 같이 건다 — 스티커 보드 밖의 협업노트는 여기서 고치지 않는다
    rows = _request('PATCH', 'collab_notes', {'id': 'eq.' + _note_id(payload), 'board_id': 'eq.' + board_id,
                                              'select': NOTE_FIELDS},
                    body=patch, prefer='return=representation')
    if not rows:
        raise LookupError('메모가 삭제되었습니다.')
    return rows[0]


def delete(payload: dict) -> str:
    board_id, _ = board()
    _request('DELETE', 'collab_notes', {'id': 'eq.' + _note_id(payload), 'board_id': 'eq.' + board_id})
    return '메모를 삭제했습니다.'
