"""에이전트 현황 — 지금 대화의 컨텍스트 크기·사용량·결과물 (2026-10-30 요청).

에이전트 터미널 오른쪽 패널의 «현황». Claude Code 만 (Codex 는 아직 읽지 못한다).

  · 컨텍스트·사용량 — Claude Code 상태 줄(statusLine)이 받는 JSON 을 데스크가 단 상태 줄 스크립트(core/agent_term.py
    STATUS_SCRIPT)가 `DESK_STATUS_FILE` 에 적는다: context_window(크기·쓴 비율), cost(비용·고친 줄), rate_limits(5시간·7일 한도).
    상태 줄이 아직 안 돌았으면(첫 메시지 전·옛 실행기) 대화 기록의 마지막 응답 usage 로 컨텍스트만 어림한다.
  · 결과물 — 대화 기록(`~/.claude/projects/<폴더>/<id>.jsonl`)에서 Write·Edit·MultiEdit·NotebookEdit 가 **성공한** 파일.
    명령(Bash)이나 스크립트가 만든 파일은 잡지 못한다. /clear 로 대화가 바뀌면 그 대화의 것부터 다시 센다.
  · 대화 기록은 수십 MB 가 될 수 있다 — 읽은 곳(offset)을 기억해 새로 붙은 줄만 읽는다.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

OUTPUT_TOOLS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')
OUTPUT_LIMIT = 200            # 보여 줄 결과물 수 (최근 것부터)
DEFAULT_WINDOW = 200_000      # 상태 줄이 크기를 알려 주기 전의 어림 (넘게 쓰고 있으면 1M)
CACHE_LIMIT = 40


def transcript_path(conversation: str) -> Path | None:
    if not conversation or not re.fullmatch(r'[0-9a-fA-F-]{36}', conversation):
        return None
    root = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'projects'
    try:
        return next(iter(root.glob(f'*/{conversation}.jsonl')), None)
    except OSError:
        return None


class _Transcript:
    """대화 기록 하나에서 읽어 둔 것."""

    def __init__(self):
        self.offset = 0
        self.model = ''
        self.context = 0                       # 마지막 응답이 본 입력(= 지금 컨텍스트) 토큰
        self.output_tokens = 0
        self.messages: set[str] = set()        # 응답 하나가 블록마다 여러 줄로 적힌다 — usage 를 한 번만 센다
        self.pending: dict[str, tuple] = {}    # tool_use id → (도구, 경로, 때)
        self.outputs: dict[str, dict] = {}     # normcase 경로 → 결과물

    def feed(self, line: str):
        try:
            row = json.loads(line)
        except ValueError:
            return
        if not isinstance(row, dict):
            return
        message = row.get('message')
        if not isinstance(message, dict):
            return
        content = message.get('content')
        if row.get('type') == 'assistant':
            usage = message.get('usage')
            if isinstance(usage, dict) and not row.get('isSidechain'):
                self.model = message.get('model') or self.model
                self.context = sum(int(usage.get(key) or 0) for key in
                                   ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
                if message.get('id') not in self.messages:
                    self.messages.add(message.get('id'))
                    self.output_tokens += int(usage.get('output_tokens') or 0)
            for block in content if isinstance(content, list) else ():
                if isinstance(block, dict) and block.get('type') == 'tool_use' and block.get('name') in OUTPUT_TOOLS:
                    tool_input = block.get('input') if isinstance(block.get('input'), dict) else {}
                    path = tool_input.get('file_path') or tool_input.get('notebook_path')
                    if isinstance(path, str) and path:
                        self.pending[block.get('id')] = (block['name'], path, row.get('timestamp') or '')
        elif row.get('type') == 'user':
            for block in content if isinstance(content, list) else ():
                if not isinstance(block, dict) or block.get('type') != 'tool_result':
                    continue
                found = self.pending.pop(block.get('tool_use_id'), None)
                if not found or block.get('is_error'):
                    continue
                tool, path, when = found
                text = json.dumps(block.get('content'), ensure_ascii=False)
                created = tool == 'Write' and 'created' in text
                key = os.path.normcase(os.path.normpath(path))
                item = self.outputs.pop(key, None) or {'path': path, 'created': False, 'count': 0}
                item['created'] = item['created'] or created
                item['count'] += 1
                item['time'] = when
                self.outputs[key] = item               # 다시 넣어 가장 최근 것이 끝에 오게


class Reader:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache: dict[str, _Transcript] = {}

    def _transcript(self, path: Path) -> _Transcript:
        key = str(path)
        with self._lock:
            state = self._cache.pop(key, None) or _Transcript()
            self._cache[key] = state
            while len(self._cache) > CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            try:
                size = path.stat().st_size
                if size < state.offset:                # 새로 쓰였다 — 처음부터
                    state = self._cache[key] = _Transcript()
                if size > state.offset:
                    with path.open('rb') as f:
                        f.seek(state.offset)
                        chunk = f.read()
                    end = chunk.rfind(b'\n') + 1       # 쓰는 중인 마지막 줄은 다음에
                    for line in chunk[:end].decode('utf-8', 'replace').splitlines():
                        if line.strip():
                            state.feed(line)
                    state.offset += end
            except OSError:
                pass
            return state

    @staticmethod
    def _status(status_file, conversation: str) -> dict:
        try:
            data = json.loads(Path(status_file).read_text(encoding='utf-8-sig'))
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(data, dict) or (conversation and data.get('session_id') not in (None, conversation)):
            return {}                                  # 옛 대화(/clear 전)의 것
        return data

    def read(self, conversation: str, status_file=None) -> dict:
        """{ready, model, context{used, size, percent, guessed}, cost, lines{added, removed}, limits[{label, percent, resets}],
        output_tokens, outputs[{path, name, folder, created, count, time, exists}]}"""
        path = transcript_path(conversation)
        state = self._transcript(path) if path else _Transcript()
        status = self._status(status_file, conversation) if status_file else {}
        window = status.get('context_window') if isinstance(status.get('context_window'), dict) else {}
        current = window.get('current_usage') if isinstance(window.get('current_usage'), dict) else {}
        used = (sum(int(current.get(key) or 0) for key in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
                if current else state.context)
        size = int(window.get('context_window_size') or 0)
        guessed = not size
        if not size:
            size = 1_000_000 if used > DEFAULT_WINDOW or '[1m]' in state.model else DEFAULT_WINDOW
        percent = window.get('used_percentage')
        percent = round(float(percent)) if isinstance(percent, (int, float)) else (round(used * 100 / size) if size else 0)
        cost = status.get('cost') if isinstance(status.get('cost'), dict) else {}
        model = status.get('model') if isinstance(status.get('model'), dict) else {}
        limits = []
        rates = status.get('rate_limits') if isinstance(status.get('rate_limits'), dict) else {}
        for key, label in (('five_hour', '5시간 한도'), ('seven_day', '7일 한도')):
            rate = rates.get(key)
            if isinstance(rate, dict) and isinstance(rate.get('used_percentage'), (int, float)):
                limits.append({'label': label, 'percent': round(rate['used_percentage']), 'resets': rate.get('resets_at') or ''})
        outputs = []
        for item in reversed(list(state.outputs.values())[-OUTPUT_LIMIT:]):
            file = Path(item['path'])
            outputs.append({'path': item['path'], 'name': file.name, 'folder': str(file.parent), 'created': item['created'],
                            'count': item['count'], 'time': item.get('time') or '', 'exists': file.exists()})
        return {'ready': bool(path or status), 'model': model.get('display_name') or state.model,
                'context': {'used': used, 'size': size, 'percent': max(0, min(100, percent)), 'guessed': guessed},
                'cost': cost.get('total_cost_usd'), 'lines': {'added': cost.get('total_lines_added'),
                                                              'removed': cost.get('total_lines_removed')},
                'limits': limits, 'output_tokens': state.output_tokens, 'outputs': outputs, 'checked': time.strftime('%H:%M:%S')}

    def has_output(self, conversation: str, path: str) -> bool:
        """화면이 열어 달라는 파일이 정말 이 대화의 결과물인가 (아무 경로나 열지 않게)."""
        transcript = transcript_path(conversation)
        if not transcript or not isinstance(path, str):
            return False
        return os.path.normcase(os.path.normpath(path)) in self._transcript(transcript).outputs
