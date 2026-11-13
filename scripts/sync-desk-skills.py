"""데스크(교사판)에 실어 보낼 업무 스킬을 `.claude/skills/<이름>` 에서 `app/resources/skills/<이름>` 으로 맞춘다.

    python scripts/sync-desk-skills.py            # 복사 (바뀐 것만)
    python scripts/sync-desk-skills.py --check    # 맞는지만 본다 (다르면 종료코드 1)

왜 복사본을 두나
  · 스킬의 정본은 `.claude/skills/<이름>` 이다 (스킬을 고치고 시험하는 곳). 데스크 실행 파일은 `resources/` 만 싣는다.
  · 그래서 실을 스킬을 DESK_SKILLS 에 적어 두고, 배포 전에 이 스크립트로 복사본을 맞춘다. `--check` 는 packaging_check 가 부른다.
  · install.ps1 은 싣지 않는다 — 데스크가 `자동화 업무` 폴더에 직접 설치한다 (core/automation.py).
  · 다른 저장소가 정본인 스킬(EXTERNAL — SPACEKIJUN MCP 사용법은 spacekijun 저장소, 에듀파인은 배포용 스킬 폴더
    `~/school-skills/edufine` — klef-portal 에서 개인정보를 뺀 판, 나이스는 `~/school-skills/neis`)은 그 저장소에서 가져온다.
    거기에는 데스크용 카드 정보(skill.json)가 없으므로 복사본의 skill.json 은 이 저장소 것으로 두고 맞추지 않는다.
    그 저장소가 없는 PC 에서는 건너뛴다(--check 도 실패로 치지 않는다 — 실린 복사본을 그대로 쓴다).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.claude' / 'skills'
TARGET = ROOT / 'app' / 'resources' / 'skills'

DESK_SKILLS = ['coolmessenger-send', 'edufine', 'neis', 'riroschool-sms', 'saenggibu-writer', 'spacekijun-mcp', 'work-files']   # 새 업무 스킬을 데스크에 싣으려면 여기에 이름을 더한다
SKIP_NAMES = {'install.ps1', '__pycache__', '.omc', 'node_modules'}   # node_modules 는 쓰는 PC 에서 npm install
SPACEKIJUN = Path(os.environ.get('SPACEKIJUN_REPO') or ROOT.parent / 'spacekijun')
EDUFINE = Path(os.environ.get('EDUFINE_SKILL_DIR') or Path.home() / 'school-skills' / 'edufine')
NEIS = Path(os.environ.get('NEIS_SKILL_DIR') or Path.home() / 'school-skills' / 'neis')
EXTERNAL = {'spacekijun-mcp': SPACEKIJUN / '.claude' / 'skills' / 'spacekijun-mcp', 'edufine': EDUFINE, 'neis': NEIS}
DESK_OWNED = {'skill.json'}                                     # 다른 저장소 스킬에서 이 저장소가 갖는 파일


def files(folder: Path) -> dict[str, str]:
    """{상대 경로: sha256} — 싣지 않는 파일은 뺀다."""
    found = {}
    for path in sorted(folder.rglob('*')):
        relative = path.relative_to(folder)
        if path.is_dir() or any(part in SKIP_NAMES or part.endswith('.pyc') for part in relative.parts):
            continue
        found[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='복사하지 않고 맞는지만 본다')
    check = parser.parse_args().check
    problems = 0
    for name in DESK_SKILLS:
        external = name in EXTERNAL
        source, target = EXTERNAL.get(name, SOURCE / name), TARGET / name
        if not (source / 'SKILL.md').is_file():
            if external and (target / 'SKILL.md').is_file():
                print(f'· {name}: 정본 저장소가 없어 건너뜁니다 ({source}) — 실린 복사본을 씁니다')
                continue
            print(f'✗ {name}: 정본이 없습니다 ({source})')
            problems += 1
            continue
        keep = DESK_OWNED if external else set()
        wanted = {k: v for k, v in files(source).items() if k not in keep}
        have = {k: v for k, v in (files(target) if target.is_dir() else {}).items() if k not in keep}
        if wanted == have:
            print(f'✓ {name}: 맞음 ({len(wanted)}개)')
            continue
        if check:
            print(f'✗ {name}: 복사본이 정본과 다릅니다 — python scripts/sync-desk-skills.py')
            problems += 1
            continue
        saved = {k: (target / k).read_bytes() for k in keep if (target / k).is_file()}
        if target.exists():
            shutil.rmtree(target)
        for relative, data in saved.items():
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            (target / relative).write_bytes(data)
        for relative in wanted:
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, destination)
        print(f'↻ {name}: 복사했습니다 ({len(wanted)}개)')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
