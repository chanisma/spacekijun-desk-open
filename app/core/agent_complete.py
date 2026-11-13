"""에이전트 터미널 입력칸의 자동 완성 (2026-11-08 요청) — «실제 터미널처럼 / 를 쓰면 쓸 수 있는 명령이 나오고, @ 로 파일을 고르게».

입력칸은 데스크 화면의 글상자라 에이전트(CLI)의 목록이 거기에는 뜨지 않는다. 그래서 같은 목록을 데스크가 만든다.
  · 빗금 명령 — 에이전트에 들어 있는 명령(아래 BUILTIN, 자주 쓰는 것만 한국어 설명과 함께) + 이 PC·이 폴더의 사용자 명령·스킬·플러그인.
      Claude Code: ~/.claude/commands/**.md · <폴더>/.claude/commands/**.md (하위 폴더는 «폴더:이름»)
                   ~/.claude/skills/*/SKILL.md · <폴더>/.claude/skills/*/SKILL.md (user-invocable: false 는 뺀다)
                   켜 둔 플러그인(settings.json enabledPlugins)의 commands/*.md · skills/*/SKILL.md → «플러그인:이름»
      Codex:       ~/.codex/prompts/*.md → «prompts:이름»
  · 파일 — 에이전트가 연 폴더 안의 파일·폴더를 이름 일부로 찾는다(무거운 폴더는 건너뛰고, 잠깐 기억해 둔다).

⚠️ 바뀔 수 있는 값 — BUILTIN 의 명령 이름(에이전트 판마다 늘고 준다), 사용자 명령·스킬·플러그인 자리와 파일 꼴.
   확인: Claude Code 2.1.319 · Codex 0.163.0 (2026-11-08).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

FILE_LIMIT = 8000          # 폴더 하나에서 훑는 가장 많은 파일 수
FILE_TTL = 20              # 파일 목록을 기억해 두는 시간 (초)
COMMAND_TTL = 15           # 명령 목록을 기억해 두는 시간 (초)
RESULTS = 40               # 한 번에 돌려주는 가장 많은 후보 수
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', '.mypy_cache', '.pytest_cache', '.next', '.cache',
             '.idea', '.vs', '$RECYCLE.BIN', 'System Volume Information'}

BUILTIN = {
    'claude': [
        ('clear', '새 대화 시작 (지난 대화는 /resume 으로 다시 열 수 있어요)'),
        ('resume', '지난 대화 이어 하기'),
        ('compact', '지금까지의 대화를 요약해 자리 만들기'),
        ('rewind', '앞의 한 지점으로 되돌리기'),
        ('model', '모델 바꾸기'),
        ('effort', '생각하는 정도 정하기'),
        ('plan', '계획 모드 — 먼저 계획만 세우기'),
        ('context', '대화가 얼마나 찼는지 보기'),
        ('usage', '사용량 보기'),
        ('status', '계정·모델·버전 보기'),
        ('init', '이 폴더 안내서(CLAUDE.md) 만들기'),
        ('memory', '기억해 둘 내용(CLAUDE.md) 고치기'),
        ('skills', '쓸 수 있는 스킬 목록'),
        ('mcp', '연결된 도구(MCP) 보기·관리'),
        ('agents', '서브에이전트 관리'),
        ('hooks', '훅 설정 보기'),
        ('permissions', '허락 규칙 보기·고치기'),
        ('add-dir', '작업 폴더 하나 더 열기'),
        ('btw', '하던 일을 끊지 않고 짧게 따로 묻기'),
        ('copy', 'Claude 의 마지막 답을 클립보드로 복사'),
        ('export', '대화를 파일이나 클립보드로 내보내기'),
        ('review', '바꾼 코드 검토 받기'),
        ('security-review', '바꾼 코드의 보안 점검'),
        ('config', '설정 열기'),
        ('theme', '색 테마 바꾸기'),
        ('doctor', '설치에 문제가 없는지 점검'),
        ('login', '다른 계정으로 로그인'),
        ('logout', '로그아웃'),
        ('feedback', '의견 보내기·버그 알리기'),
        ('help', '전체 명령 목록'),
        ('exit', '에이전트 끝내기'),
    ],
    'codex': [
        ('new', '새 대화 시작'),
        ('resume', '지난 대화 이어 하기'),
        ('compact', '지금까지의 대화를 요약해 자리 만들기'),
        ('model', '모델·생각하는 정도 바꾸기'),
        ('permissions', '묻지 않고 해도 되는 일의 범위 고르기'),
        ('status', '계정·모델·사용량'),
        ('init', '이 폴더 안내서(AGENTS.md) 만들기'),
        ('diff', '바뀐 파일 보기'),
        ('review', '바꾼 내용 검토 받기'),
        ('mention', '파일을 대화에 붙이기'),
        ('mcp', '연결된 도구(MCP) 보기'),
        ('logout', '로그아웃'),
        ('feedback', '의견 보내기'),
        ('quit', '에이전트 끝내기'),
    ],
}

_lock = threading.Lock()
_files: dict[str, tuple[float, list[tuple[str, bool]]]] = {}
_commands: dict[tuple, tuple[float, list[dict]]] = {}


# ── 빗금 명령 ───────────────────────────────────────────
def _front(path: Path) -> dict:
    """마크다운 머리말(--- … ---)의 단순한 «키: 값» 들."""
    try:
        with path.open(encoding='utf-8-sig', errors='replace') as handle:
            text = handle.read(6000)
    except OSError:
        return {}
    found = re.match(r'---\s*\n(.*?)\n---', text, re.S)
    data = {}
    for line in (found.group(1).splitlines() if found else []):
        pair = re.match(r'([A-Za-z][\w-]*)\s*:\s*(.*)$', line)
        if pair:
            data[pair.group(1).lower()] = pair.group(2).strip().strip('"\'')
    if 'description' not in data:                          # 머리말이 없으면 첫 글줄
        body = text[found.end():] if found else text
        line = next((row.strip().lstrip('#').strip() for row in body.splitlines() if row.strip()), '')
        data['description'] = line
    return data


def _short(text: str, limit: int = 120) -> str:
    text = re.sub(r'\s+', ' ', text or '').strip()
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _command_files(root: Path, prefix: str = '') -> list[dict]:
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob('*.md'))[:300]:
        parts = path.relative_to(root).with_suffix('').parts
        name = prefix + ':'.join(parts)
        rows.append({'name': name, 'desc': _short(_front(path).get('description', '')), 'kind': 'command'})
    return rows


def _skill_dirs(root: Path, prefix: str = '') -> list[dict]:
    rows = []
    if not root.is_dir():
        return rows
    for skill in sorted(root.iterdir())[:300]:
        card = skill / 'SKILL.md'
        if not card.is_file():
            continue
        front = _front(card)
        if front.get('user-invocable', '').lower() == 'false':
            continue
        rows.append({'name': prefix + (front.get('name') or skill.name), 'desc': _short(front.get('description', '')),
                     'kind': 'skill'})
    return rows


def _plugins(home: Path, folder: str) -> list[dict]:
    """켜 둔 플러그인의 명령·스킬 — 사용자 범위는 settings 의 enabledPlugins, 폴더 범위는 그 폴더에 깔린 것."""
    try:
        installed = json.loads((home / '.claude' / 'plugins' / 'installed_plugins.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    try:
        enabled = json.loads((home / '.claude' / 'settings.json').read_text(encoding='utf-8')).get('enabledPlugins') or {}
    except (OSError, ValueError, AttributeError):
        enabled = {}
    here = os.path.normcase(os.path.normpath(folder)) if folder else ''
    rows = []
    for key, entries in (installed.get('plugins') or {}).items():
        for entry in entries if isinstance(entries, list) else []:
            scope, project = entry.get('scope'), entry.get('projectPath') or ''
            if scope == 'user' and enabled.get(key) is not True:
                continue
            if scope != 'user' and (not here or os.path.normcase(os.path.normpath(project)) != here):
                continue
            base, plugin = Path(entry.get('installPath') or ''), key.split('@', 1)[0]
            rows += _command_files(base / 'commands', plugin + ':')
            rows += _skill_dirs(base / 'skills', plugin + ':')
            break
    return rows


def commands(tool: str, folder: str, home: Path | None = None) -> list[dict]:
    """[{name, desc, kind: builtin|command|skill}] — 이름이 겹치면 앞의 것(폴더 > 사용자 > 플러그인 > 기본)."""
    home = home or Path.home()
    key = (tool, folder, str(home))
    with _lock:
        cached = _commands.get(key)
        if cached and time.monotonic() - cached[0] < COMMAND_TTL:
            return cached[1]
    rows: list[dict] = []
    if tool == 'codex':
        rows += _command_files(home / '.codex' / 'prompts', 'prompts:')
    else:
        local = Path(folder) / '.claude' if folder else None
        if local:
            rows += _command_files(local / 'commands') + _skill_dirs(local / 'skills')
        rows += _command_files(home / '.claude' / 'commands') + _skill_dirs(home / '.claude' / 'skills')
        rows += _plugins(home, folder)
    rows += [{'name': name, 'desc': desc, 'kind': 'builtin'} for name, desc in BUILTIN.get(tool, BUILTIN['claude'])]
    seen, result = set(), []
    for row in rows:
        if row['name'] and row['name'] not in seen:
            seen.add(row['name'])
            result.append(row)
    with _lock:
        _commands[key] = (time.monotonic(), result)
    return result


# ── 파일 ───────────────────────────────────────────────
def _walk(folder: str) -> list[tuple[str, bool]]:
    rows: list[tuple[str, bool]] = []
    stack = ['']
    while stack and len(rows) < FILE_LIMIT:
        rel = stack.pop()
        try:
            entries = sorted(os.scandir(os.path.join(folder, rel)), key=lambda e: e.name.lower())
        except OSError:
            continue
        subdirs = []
        for entry in entries:
            path = f'{rel}/{entry.name}' if rel else entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if entry.name in SKIP_DIRS:
                    continue
                rows.append((path, True))
                subdirs.append(path)
            else:
                rows.append((path, False))
            if len(rows) >= FILE_LIMIT:
                break
        stack.extend(reversed(subdirs))                   # 얕은 것부터 — 앞쪽 폴더를 먼저 다 본다
    return rows


def _listing(folder: str) -> list[tuple[str, bool]]:
    key = os.path.normcase(os.path.normpath(folder))
    with _lock:
        cached = _files.get(key)
        if cached and time.monotonic() - cached[0] < FILE_TTL:
            return cached[1]
    rows = _walk(folder)
    with _lock:
        _files[key] = (time.monotonic(), rows)
    return rows


def _score(path: str, query: str) -> float | None:
    """작을수록 앞. 이름에 붙어 있으면 가장 앞, 경로에 붙어 있으면 다음, 글자가 차례로만 있으면 뒤."""
    low, name = path.lower(), path.rsplit('/', 1)[-1].lower()
    if not query:
        return path.count('/') * 10 + len(path) / 100
    if name.startswith(query):
        return 0 + len(path) / 1000
    if query in name:
        return 1 + len(path) / 1000
    if query in low:
        return 2 + len(path) / 1000
    at = -1
    for char in query:
        at = low.find(char, at + 1)
        if at < 0:
            return None
    return 3 + len(path) / 1000


def files(folder: str, query: str = '', limit: int = RESULTS) -> list[dict]:
    """폴더 안에서 query 와 맞는 파일·폴더 [{path, dir}] — path 는 폴더 기준 상대 경로(빗금 /)."""
    if not folder or not os.path.isdir(folder):
        return []
    query = query.replace('\\', '/').strip().lower()
    scored = []
    for path, is_dir in _listing(folder):
        score = _score(path, query)
        if score is not None:
            scored.append((score, path, is_dir))
    scored.sort()
    return [{'path': path + ('/' if is_dir else ''), 'dir': is_dir} for _score_, path, is_dir in scored[:limit]]
