"""시험이 **진짜 자격증명 저장소를 건드리지 못하게** 막는다.

2026-09-14 에 시험을 돌린 뒤 저장돼 있던 인증서 정보가 사라졌다. 어느 줄이 썼는지 끝내
집어내지 못했지만, 원인을 찾는 것과 별개로 **시험이 사용자 파일에 닿을 수 있다는 것 자체가
잘못**이다. 여기서 저장 경로를 임시 폴더로 돌려 둔다. 시험 모듈마다 `use_sandbox()` 를 부른다.

평문 레거시 파일 경로도 함께 돌린다. `secretstore.load` 는 저장 파일이 없으면 그 파일을
읽어 **옮겨 적기까지** 하기 때문이다.
"""
from __future__ import annotations

import atexit
import tempfile
from pathlib import Path

from core import secretstore

_started = False


def use_sandbox() -> Path:
    """자격증명 저장 경로를 임시 폴더로 돌린다. 여러 번 불러도 한 번만 바꾼다."""
    global _started
    if _started:
        return Path(secretstore.STORE_PATH).parent
    room = tempfile.mkdtemp(prefix='spacekijun-test-secrets-')
    secretstore.DATA_DIR = room
    secretstore.STORE_PATH = str(Path(room) / 'credentials.dat')
    secretstore.LEGACY_JSON = str(Path(room) / 'legacy-none.json')
    from core import automation                     # 기본 스킬(바탕화면 정리 …)을 진짜 ~/.claude/skills 에 깔지 않게
    automation.GENERAL_HOME = Path(room) / 'home'
    atexit.register(_cleanup, room)
    _started = True
    return Path(room)


def _cleanup(room: str) -> None:
    import shutil
    shutil.rmtree(room, ignore_errors=True)
