"""작업 폴더(지식) — 에이전트가 함께 쓰는 저장소·폴더와, 폴더마다 쌓아 가는 지식 파일 (2026-10-30 요청).

에이전트 터미널에서 «에이전트끼리 보기» 외에 에이전트가 작업 폴더를 고른다. 새로 여는 에이전트는
  · 그 폴더들에 접근할 수 있고(Claude Code·Codex `--add-dir`),
  · 환경 값 DESK_KNOWLEDGE 로 **지식 목록 파일**(이 PC 의 `<자료>/agent/knowledge.md`)을 받는다 — 폴더마다 지식 파일 경로와 규칙.
지식 파일은 폴더 안이 아니라 데스크 자료 폴더(`<자료>/agent/knowledge/<폴더이름>-<해시>.md`)에 둔다 — 저장소를 더럽히지 않게.
에이전트는 그 폴더와 관련된 일을 하기 전에 읽고, 일하며 알게 된 오래갈 사실(구조·규칙·자주 쓰는 길)을 덧붙인다.
메인 상주 에이전트의 쪽지 분석(core/resident_tasks.py)도 이 지식을 읽는다.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path

LIMIT = 8                     # 작업 폴더 수
FILE_LIMIT = 200_000          # 지식 파일 하나를 분석에 넣을 때의 상한 (글자) — 넘으면 앞부분만 (에이전트가 정리해야 한다)
_UNSAFE = re.compile(r'[%"&|<>^\r\n]')          # 실행기(cmd 한 줄)에 들어가므로 이런 글자가 든 경로는 받지 않는다

INDEX_HEAD = """# 작업 폴더와 지식 (스페이스기전 데스크)

이 PC 의 사용자가 에이전트에게 함께 보게 한 폴더입니다. 각 폴더에는 그 폴더에 대한 **지식 파일**이 있습니다.

- 폴더와 관련된 일을 하기 전에 그 폴더의 지식 파일을 먼저 읽으세요.
- 일하면서 알게 된 **오래갈 사실**(폴더 구조·규칙·자주 쓰는 명령·주의할 점·담당 업무와의 관계)을 지식 파일 끝에
  `- YYYY-MM-DD: …` 한 줄로 덧붙이세요. 이미 있는 내용은 다시 쓰지 말고, 틀린 것은 고치세요.
- 학생·교직원 개인정보, 비밀번호·토큰은 지식 파일에 쓰지 마세요.
- 폴더 안의 파일은 사용자의 것입니다. 사용자가 시키지 않은 파일은 고치지 마세요.

"""
KNOWLEDGE_HEAD = """# {name} — 지식

폴더: {folder}

에이전트가 이 폴더에 대해 알게 된 것을 쌓는 파일입니다(스페이스기전 데스크). 사람이 고쳐도 됩니다.

## 알게 된 것
"""


class KnowledgeError(ValueError):
    pass


def checked_folder(value) -> str:
    if not isinstance(value, str) or not value or len(value) > 400:
        raise KnowledgeError('폴더 형식이 올바르지 않습니다.')
    if _UNSAFE.search(value):
        raise KnowledgeError('이 폴더 이름에는 쓸 수 없는 글자(% " & | < > ^)가 있습니다.')
    spot = Path(value)
    if not spot.is_absolute() or not spot.is_dir():
        raise KnowledgeError('폴더를 찾을 수 없습니다.')
    return os.path.normpath(str(spot))


def knowledge_file(work_dir: Path, folder: str) -> Path:
    digest = hashlib.sha1(os.path.normcase(folder).encode('utf-8')).hexdigest()[:8]
    name = re.sub(r'[^\w가-힣.-]+', '_', Path(folder).name or 'folder').strip('_') or 'folder'
    return Path(work_dir) / 'agent' / 'knowledge' / f'{name}-{digest}.md'


def ensure_file(work_dir: Path, folder: str) -> Path:
    path = knowledge_file(work_dir, folder)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(KNOWLEDGE_HEAD.format(name=Path(folder).name or folder, folder=folder), encoding='utf-8')
    return path


def entries(work_dir: Path, folders: list[str]) -> list[dict]:
    """[{folder, file, exists, size, updated}] — 화면과 분석이 쓴다. updated = 지식 파일을 고친 때(초, 없으면 0)."""
    rows = []
    for folder in folders:
        path = knowledge_file(work_dir, folder)
        stat = path.stat() if path.exists() else None
        rows.append({'folder': folder, 'name': Path(folder).name or folder, 'file': str(path),
                     'exists': os.path.isdir(folder), 'size': stat.st_size if stat else 0,
                     'updated': int(stat.st_mtime) if stat else 0})
    return rows


def write_index(work_dir: Path, folders: list[str]) -> Path | None:
    """지식 목록 파일을 쓴다(없으면 지운다) — 에이전트는 DESK_KNOWLEDGE 로 이것을 받는다."""
    index = Path(work_dir) / 'agent' / 'knowledge.md'
    live = [folder for folder in folders if os.path.isdir(folder)]
    if not live:
        index.unlink(missing_ok=True)
        return None
    lines = [INDEX_HEAD, f'(목록을 쓴 때: {time.strftime("%Y-%m-%d %H:%M")})\n']
    for folder in live:
        lines.append(f'- 폴더: {folder}\n  지식 파일: {ensure_file(work_dir, folder)}\n')
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text('\n'.join(lines), encoding='utf-8')
    return index


def launch_args(tool: str, folders: list[str]) -> tuple:
    """새로 여는 에이전트에 붙일 인자 — 폴더 접근(--add-dir)과, 지식 목록을 읽으라는 짧은 영어 지시(명령 줄에 들어간다)."""
    live = [folder for folder in folders if os.path.isdir(folder) and not _UNSAFE.search(folder)]
    if not live:
        return ()
    args: list[str] = []
    for folder in live:
        args += ['--add-dir', f'"{folder}"']
    note = ('Knowledge folders: the user lets you read the extra folders added to this session. The file named in env '
            'DESK_KNOWLEDGE lists them with one knowledge file each. Read the knowledge file before work related to a folder, '
            'and append durable learnings to it as one dated line. Never write personal data or secrets there.')
    if tool == 'claude':
        args += ['--append-system-prompt', f'"{note}"']
    return tuple(args)


def read_for_analysis(work_dir: Path, folders: list[str]) -> str:
    """분석에 넣을 지식 — 폴더마다 지식 파일 내용(앞부분)."""
    parts = []
    for row in entries(work_dir, folders):
        path = Path(row['file'])
        if path.exists():
            text = path.read_text(encoding='utf-8', errors='replace')[:FILE_LIMIT]
            parts.append(f'### 폴더 {row["folder"]}\n{text}')
    return '\n\n'.join(parts)
