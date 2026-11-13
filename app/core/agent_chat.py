"""대화 보기 (2026-11-06 요청, 테스트 판) — 에이전트 터미널의 글자 화면 대신 대화를 말풍선으로.

«지금 cmd 화면으로 클로드 코드가 활용되고 있는데 최신 UI 들의 디자인과 거리가 있어서 어렵게 느끼는 사용자들이 있을 수 있음».
터미널(Claude Code)은 그대로 돌고, 이 모듈은 그 대화 기록(`~/.claude/projects/<폴더>/<id>.jsonl`)을 읽어
창이 그릴 항목으로 바꾼다. 입력·멈추기·선택지 고르기는 지금처럼 터미널로 보낸다 — 대화 보기는 **읽기 전용 그림**이다.

항목 (rev 는 바뀔 때마다 오른다 — 창은 since 뒤의 것만 받아 같은 i 를 갈아 끼운다):
  · user     {text, images?, queued?}  내가 보낸 말 — queued 는 에이전트가 일하는 중에 보내 하던 일 사이에 읽힌 말
  · text     {text}                    에이전트의 답 (마크다운)
  · tool     {name, label, detail, status: run|ok|err, result, images?}   도구 한 번 — 결과가 오면 status·result 가 붙는다
  · note     {text}                    /clear 같은 명령, 멈춤, 대화 줄이기
images 는 사진 열쇠 목록 — 사진 자체는 무거워 항목에 싣지 않고, 창이 Reader.image() 로 하나씩 받는다
(«b:<줄 자리>:<n>» 기록 줄 속 n 번째 사진 · «f:<경로>» 도구 결과에 나온 그림 파일 — 스크린샷을 파일로 남긴 것).
Claude Code 만 (Codex 는 기록 꼴이 달라 터미널로만 본다). 하위 에이전트(isSidechain)·생각(thinking)·시스템 안내는 뺀다.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
from pathlib import Path

from core.agent_usage import transcript_path

KEEP = 600            # 대화 하나에서 들고 있을 항목 수 (오래된 것부터 버린다)
FIRST = 200           # 처음 붙을 때 보낼 항목 수
TEXT_LIMIT = 20000
RESULT_LIMIT = 700
DETAIL_LIMIT = 160
CACHE_LIMIT = 30
IMAGES_PER_ITEM = 6
IMAGE_FILE_LIMIT = 20 * 1024 * 1024
IMAGE_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp',
               '.bmp': 'image/bmp'}
_IMAGE_PATH = re.compile(r'(?<![\w/\\])([A-Za-z]:[\\/][^\s"\'<>|*?`]*?\.(?:png|jpe?g|gif|webp|bmp))(?!\w)', re.I)
QUEUED_HEAD = 'The user sent a new message while you were working:'

TOOL_LABELS = {
    'Read': '파일 읽기', 'Write': '파일 만들기', 'Edit': '파일 고치기', 'MultiEdit': '파일 고치기',
    'NotebookEdit': '노트북 고치기', 'Bash': '명령 실행', 'PowerShell': '명령 실행', 'Grep': '내용 찾기',
    'Glob': '파일 찾기', 'WebFetch': '웹 페이지 읽기', 'WebSearch': '웹 검색', 'Agent': '도우미 에이전트',
    'Task': '도우미 에이전트', 'TodoWrite': '할 일 목록', 'Skill': '스킬 쓰기', 'ToolSearch': '도구 불러오기',
    'AskUserQuestion': '질문', 'ExitPlanMode': '계획 보여 주기', 'EnterPlanMode': '계획 세우기',
}
_TAG = re.compile(r'<(command-name|command-message|command-args|local-command-stdout|local-command-stderr)>(.*?)</\1>', re.S)
_SKIP_USER = ('<system-reminder>', 'Caveat:', '<local-command-', '<bash-', '<task-notification>', '<user-memory-input>')


def _cut(text: str, limit: int) -> str:
    text = str(text or '')
    return text if len(text) <= limit else text[:limit].rstrip() + ' …'


def _short_path(value) -> str:
    text = str(value or '')
    return Path(text).name or text


def tool_view(name: str, data: dict) -> tuple[str, str]:
    """도구 이름·입력 → (보일 이름, 한 줄 설명)."""
    data = data if isinstance(data, dict) else {}
    if name.startswith('mcp__'):
        parts = name.split('__')
        server = parts[1].replace('plugin_', '').replace('claude_ai_', '') if len(parts) > 1 else 'MCP'
        return f'{server} · {parts[-1]}', _cut(next((str(v) for v in data.values() if isinstance(v, str)), ''), DETAIL_LIMIT)
    label = TOOL_LABELS.get(name, name)
    if name in ('Read', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit'):
        detail = _short_path(data.get('file_path') or data.get('notebook_path'))
    elif name in ('Bash', 'PowerShell'):
        detail = data.get('description') or data.get('command') or ''
    elif name in ('Grep', 'Glob'):
        detail = data.get('pattern') or ''
    elif name == 'WebFetch':
        detail = data.get('url') or ''
    elif name == 'WebSearch':
        detail = data.get('query') or ''
    elif name in ('Agent', 'Task'):
        detail = data.get('description') or ''
    elif name == 'Skill':
        detail = data.get('skill') or ''
    elif name == 'TodoWrite':
        todos = data.get('todos') if isinstance(data.get('todos'), list) else []
        done = sum(1 for t in todos if isinstance(t, dict) and t.get('status') == 'completed')
        detail = f'{done}/{len(todos)} 끝남' if todos else ''
    elif name == 'AskUserQuestion':
        questions = data.get('questions') if isinstance(data.get('questions'), list) else []
        detail = questions[0].get('question', '') if questions and isinstance(questions[0], dict) else ''
    else:
        detail = next((str(v) for v in data.values() if isinstance(v, str)), '')
    return label, _cut(' '.join(str(detail).split()), DETAIL_LIMIT)


def _image_blocks(content):
    """기록 줄의 content 속 사진 블록을 차례대로 (도구 결과 안에 든 것까지) — 열쇠의 n 은 이 차례다."""
    for block in content if isinstance(content, list) else ():
        if not isinstance(block, dict):
            continue
        if block.get('type') == 'image':
            yield block
        elif block.get('type') == 'tool_result':
            yield from _image_blocks(block.get('content'))


def _image_files(text: str) -> list[str]:
    """도구 결과 글에 나온 그림 파일 (있는 것만) — 예) «스크린샷을 C:\…\page.png 에 저장했습니다»."""
    found = []
    for match in _IMAGE_PATH.finditer(text or ''):
        path = match.group(1).rstrip('.,);:]')
        if path not in found and os.path.isfile(path):
            found.append(path)
        if len(found) >= IMAGES_PER_ITEM:
            break
    return found


def _queued_text(text: str):
    """옛 꼴 — 도구 결과 옆 글 블록에 «일하는 중에 보낸 말»이 실려 온다."""
    text = text.lstrip()
    if text.startswith('<system-reminder>'):
        text = text[len('<system-reminder>'):].lstrip()
    if not text.startswith(QUEUED_HEAD):
        return None
    body = text[len(QUEUED_HEAD):].split('\n\nThis is how Claude Code surfaces', 1)[0]
    return body.replace('</system-reminder>', '').strip() or None


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    parts.append(str(block.get('text') or ''))
                elif block.get('type') == 'image':
                    parts.append('[사진]')
        return '\n'.join(parts)
    return ''


def _user_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'text':
                parts.append(str(block.get('text') or ''))
            elif block.get('type') == 'image':
                parts.append('[사진]')
        return '\n'.join(p for p in parts if p)
    return ''


class _Chat:
    def __init__(self):
        self.offset = 0
        self.items: list[dict] = []
        self.base = 0                      # items[0] 의 번호 (앞을 버리면 오른다)
        self.rev = 0
        self.tools: dict[str, int] = {}    # tool_use id → 항목 번호
        self.files: set[str] = set()       # 창이 받아 갈 수 있는 그림 파일 (이 대화에 나온 것만)

    def _add(self, item: dict) -> int:
        self.rev += 1
        item['i'] = self.base + len(self.items)
        item['rev'] = self.rev
        self.items.append(item)
        if len(self.items) > KEEP:
            drop = len(self.items) - KEEP
            self.items = self.items[drop:]
            self.base += drop
        return item['i']

    def _touch(self, index: int, **changes):
        at = index - self.base
        if 0 <= at < len(self.items):
            self.rev += 1
            self.items[at].update(changes, rev=self.rev)

    def feed(self, line: str, at: int = 0):
        try:
            row = json.loads(line)
        except ValueError:
            return
        if not isinstance(row, dict) or row.get('isSidechain'):
            return
        if row.get('type') == 'attachment':
            # 에이전트가 일하는 중에 보낸 말 — Claude Code 가 하던 일 사이에 끼워 읽힌다 (작업 알림 같은 다른 끼움은 뺀다)
            extra = row.get('attachment') if isinstance(row.get('attachment'), dict) else {}
            if extra.get('type') == 'queued_command' and extra.get('commandMode', 'prompt') == 'prompt':
                text = _user_text(extra.get('prompt')).strip()
                if text and not text.startswith(_SKIP_USER):
                    self._add({'k': 'user', 'text': _cut(text, TEXT_LIMIT), 'queued': True})
            return
        if row.get('type') not in ('user', 'assistant'):
            return
        message = row.get('message')
        if not isinstance(message, dict):
            return
        content = message.get('content')
        if row['type'] == 'assistant':
            for block in content if isinstance(content, list) else ():
                if not isinstance(block, dict):
                    continue
                kind = block.get('type')
                if kind == 'text' and str(block.get('text') or '').strip():
                    text = str(block['text']).strip()
                    if text != 'No response requested.':
                        self._add({'k': 'text', 'text': _cut(text, TEXT_LIMIT)})
                elif kind == 'tool_use':
                    name = str(block.get('name') or '')
                    label, detail = tool_view(name, block.get('input'))
                    self.tools[str(block.get('id') or '')] = self._add(
                        {'k': 'tool', 'name': name, 'label': label, 'detail': detail, 'status': 'run', 'result': ''})
            return
        # 사람 쪽 줄 — 도구 결과, 내가 보낸 말, 명령
        if row.get('isCompactSummary'):
            self._add({'k': 'note', 'text': '앞의 대화를 요약해 줄였습니다'})
            return
        if isinstance(content, list) and any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
            seen = 0                                    # 이 줄에서 앞 결과들이 가진 사진 수 — 열쇠의 n
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    count = sum(1 for _ in _image_blocks([block]))
                    first, seen = seen, seen + count
                    index = self.tools.pop(str(block.get('tool_use_id') or ''), None)
                    if index is None:
                        continue
                    result = _result_text(block.get('content')).strip()
                    changes = {'status': 'err' if block.get('is_error') else 'ok', 'result': _cut(result, RESULT_LIMIT)}
                    images = [f'b:{at}:{n}' for n in range(first, first + min(count, IMAGES_PER_ITEM))]
                    if not images:                      # 사진 대신 파일로 남긴 스크린샷
                        files = _image_files(result)
                        self.files.update(files)
                        images = ['f:' + path for path in files]
                    if images:
                        changes['images'] = images
                    self._touch(index, **changes)
                elif isinstance(block, dict) and block.get('type') == 'text':
                    queued = _queued_text(str(block.get('text') or ''))
                    if queued:
                        self._add({'k': 'user', 'text': _cut(queued, TEXT_LIMIT), 'queued': True})
            return
        if row.get('isMeta'):
            return
        text = _user_text(content).strip()
        if not text:
            return
        tags = dict((m.group(1), m.group(2).strip()) for m in _TAG.finditer(text))
        if 'command-name' in tags:
            command = tags['command-name']
            args = tags.get('command-args', '')
            self._add({'k': 'note', 'text': f'{command} {args}'.strip()})
            return
        if text.startswith(_SKIP_USER):
            return
        if text.startswith('[Request interrupted'):
            self._add({'k': 'note', 'text': '멈췄습니다'})
            # 결과 없이 끝난 도구는 멈춘 것으로
            for index in self.tools.values():
                self._touch(index, status='err', result='멈춤')
            self.tools.clear()
            return
        images = [f'b:{at}:{n}' for n, _ in zip(range(IMAGES_PER_ITEM), _image_blocks(content))]
        if images:                                      # 사진은 그림으로 — 글 속 자리표는 뺀다
            text = re.sub(r'\[(사진|Image #\d+)\]\s*', '', text).strip()
        item = {'k': 'user', 'text': _cut(text, TEXT_LIMIT)}
        if images:
            item['images'] = images
        self._add(item)

    def since(self, rev: int) -> list[dict]:
        if rev <= 0:
            return self.items[-FIRST:]
        return [item for item in self.items if item['rev'] > rev]


class Reader:
    """대화 id 마다 읽어 둔 곳과 항목을 들고 있다 — 새로 붙은 줄만 읽는다."""

    def __init__(self):
        self._lock = threading.Lock()
        self._chats: dict[str, _Chat] = {}

    def read(self, conversation: str, since: int = 0) -> dict:
        path = transcript_path(conversation)
        if not path:
            return {'conversation': conversation or '', 'items': [], 'rev': 0, 'reset': since > 0, 'empty': True}
        with self._lock:
            chat = self._chats.get(conversation)
            if chat is None:
                if len(self._chats) >= CACHE_LIMIT:
                    self._chats.pop(next(iter(self._chats)))
                chat = self._chats[conversation] = _Chat()
            try:
                with open(path, 'rb') as handle:
                    handle.seek(chat.offset)
                    data = handle.read()
            except OSError:
                data = b''
            end = data.rfind(b'\n')            # 쓰는 중인 마지막 줄은 다음에
            if end >= 0:
                at = chat.offset
                chat.offset += end + 1
                for raw in data[:end].split(b'\n'):
                    if raw.strip():
                        chat.feed(raw.decode('utf-8', 'replace'), at)
                    at += len(raw) + 1
            reset = since > chat.rev            # 데스크를 다시 켰거나 다른 대화로 바뀌었다 — 처음부터
            items = chat.since(0 if reset else since)
            return {'conversation': conversation, 'items': items, 'rev': chat.rev, 'reset': reset or since <= 0,
                    'empty': not chat.items}

    def image(self, conversation: str, key: str):
        """사진 하나 → {type, data(base64)}. 이 대화에서 읽어 준 열쇠만 (파일은 이 대화에 나온 그림 파일만)."""
        path = transcript_path(conversation)
        with self._lock:
            chat = self._chats.get(conversation)
        if not path or chat is None:
            return None
        if key.startswith('f:'):
            file = key[2:]
            kind = IMAGE_TYPES.get(Path(file).suffix.lower())
            if file not in chat.files or not kind:
                return None
            try:
                if os.path.getsize(file) > IMAGE_FILE_LIMIT:
                    return None
                with open(file, 'rb') as handle:
                    return {'type': kind, 'data': base64.b64encode(handle.read()).decode('ascii')}
            except OSError:
                return None                     # 작업 뒤 지운 스크린샷
        match = re.fullmatch(r'b:(\d+):(\d+)', key)
        if not match or int(match.group(1)) >= chat.offset:
            return None
        try:
            with open(path, 'rb') as handle:
                handle.seek(int(match.group(1)))
                row = json.loads(handle.readline().decode('utf-8', 'replace'))
        except (OSError, ValueError):
            return None
        message = row.get('message') if isinstance(row, dict) else None
        for n, block in enumerate(_image_blocks(message.get('content') if isinstance(message, dict) else None)):
            if n == int(match.group(2)):
                source = block.get('source') if isinstance(block.get('source'), dict) else {}
                if source.get('type') == 'base64' and isinstance(source.get('data'), str):
                    return {'type': str(source.get('media_type') or 'image/png'), 'data': source['data']}
                return None
        return None
