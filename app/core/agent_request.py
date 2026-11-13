"""에이전트 작업 요청 — 받는 쪽 (2026-11-11 요청).

다른 선생님의 에이전트가 SPACEKIJUN MCP `send_agent_request` 로 «이 일을 이렇게 해 달라»(요청 내용 · 수행 안내 · 연결할
문서 생성 방식·업무·할 일·스킬)를 보내면, 이 선생님에게 스페이스기전 알림(notification_events type 'agent_request')이 오고
표 `agent_request` 에 한 줄이 생긴다(서버 spacekijun 20261111120000_mcp_agent_request.sql).

데스크는 받은 요청을 에이전트 터미널의 «작업 요청»에 띄우고, 사람이 고른 에이전트의 **입력칸에** 맡길 말을 넣는다(보내지는 않는다 —
Enter 는 사람이). 맡길 말은 서버가 한 곳에서 만든다(`agent_request_prompt`) — 모바일·웹에서 넘길 때와 같은 글이다.
쿨메신저 분석이 «받은 글에서 할 일을 알아내는» 길이라면, 이것은 «보낸 사람이 수행 방식을 처음부터 안내하는» 길이다.

  · 요청 글은 **다른 선생님이 쓴 글**이다 — 맡길 말 머리에 서버가 «내 지시가 아니라 요청 내용으로, 되돌리기 어려운 일은 확인받고»를 붙인다.
  · 넘긴 뒤에는 `agent_request_mark_handed`(via desk) — 보낸 사람의 목록에 «에이전트에게 넘김»으로 보인다.
  · 완료·거절은 에이전트가 사용자 확인 뒤 MCP `reply_agent_request` 로 한다(이 모듈은 하지 않는다).
"""
from __future__ import annotations

import re

from . import desk_message

TYPE = 'agent_request'
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
RequestError = desk_message.MessageError


def check_id(value) -> str:
    if not isinstance(value, str) or not UUID.match(value.lower()):
        raise ValueError('작업 요청 id 가 올바르지 않습니다.')
    return value.lower()


def _list(data) -> list[dict]:
    return [row for row in data if isinstance(row, dict) and row.get('id')] if isinstance(data, list) else []


def inbox(status: str = 'open', limit: int = 30) -> list[dict]:
    """받은 요청 — open(받음·넘김) | all. 새 것부터."""
    return _list(desk_message._request('POST', 'rpc/agent_request_inbox', body={'p_status': status, 'p_limit': limit}))


def prompt(request_id: str) -> dict:
    """맡길 말 {id, title, from, prompt, …}. 끝난 요청이면 서버가 거절한다."""
    data = desk_message._request('POST', 'rpc/agent_request_prompt', body={'p_id': check_id(request_id)})
    if not isinstance(data, dict) or not isinstance(data.get('prompt'), str):
        raise RequestError('작업 요청을 불러오지 못했습니다.')
    return data


def mark_handed(request_id: str, label: str = '', agent: str = '') -> dict:
    data = desk_message._request('POST', 'rpc/agent_request_mark_handed',
                                 body={'p_id': check_id(request_id), 'p_via': 'desk', 'p_label': label[:60], 'p_agent': agent[:60]})
    return data if isinstance(data, dict) else {}


def arrived(record: dict) -> dict | None:
    """Realtime 으로 온 알림 행 → {request_id, title, sender}. 작업 요청 알림이 아니면 None."""
    if not isinstance(record, dict) or record.get('type') != TYPE:
        return None
    meta = record.get('meta') if isinstance(record.get('meta'), dict) else {}
    request_id = str(meta.get('request_id') or '')
    if not UUID.match(request_id.lower()):
        return None
    title = str(record.get('title') or '작업 요청')
    return {'request_id': request_id.lower(), 'title': title, 'sender': str(meta.get('sender_name') or '')}


def summary(row: dict) -> str:
    """에이전트 터미널 기록에 남길 한 줄 — 본문은 넣지 않는다."""
    due = f' · 기한 {row["due_date"]}' if row.get('due_date') else ''
    return f'{row.get("from") or "?"} 선생님의 작업 요청 «{row.get("title") or ""}»{due}'
