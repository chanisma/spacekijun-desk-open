"""이세계 사회인 게임 파일을 학생판에 넣기 (2026-10-19 요청) — isekai3d 저장소를 빌드해 app/games/isekai3d/ 로 복사한다.

    python deploy/isekai3d/sync.py                 # isekai3d 저장소에서 npm run build 후 복사
    python deploy/isekai3d/sync.py --skip-build    # 이미 빌드한 dist/ 를 그대로 복사

isekai3d 저장소 자리: SPACEKIJUN_ISEKAI3D (없으면 C:\\Users\\<사용자>\\orca\\projects\\isekai3d).
게임 파일(약 5MB)만 넣는다 — 캐릭터(models/, 약 500MB)는 Intune 캐릭터 팩(deploy/intune-isekai3d/)으로 따로 깐다.
app/games/ 는 git 에 올리지 않는다 (빌드할 때마다 만든다). deploy/intune/build.ps1 이 실행 파일을 만들기 전에 부른다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'app' / 'games' / 'isekai3d'


def isekai3d_repo() -> Path:
    return Path(os.environ.get('SPACEKIJUN_ISEKAI3D') or Path.home() / 'orca' / 'projects' / 'isekai3d')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-build', action='store_true')
    args = ap.parse_args()
    repo = isekai3d_repo()
    if not (repo / 'package.json').is_file():
        raise SystemExit(f'isekai3d 저장소를 찾지 못했습니다: {repo}\nSPACEKIJUN_ISEKAI3D 에 자리를 넣어 주세요.')
    if not args.skip_build:
        subprocess.run('npm run build', cwd=repo, shell=True, check=True)
    dist = repo / 'dist'
    if not (dist / 'index.html').is_file():
        raise SystemExit(f'빌드된 게임이 없습니다: {dist}')
    if (dist / 'models').exists():
        raise SystemExit('dist/ 에 models/ 가 들어 있습니다 — 캐릭터는 실행 파일에 넣지 않습니다.')
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(dist, OUT)
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True).stdout.strip())
    # 이 게임이 읽는 캐릭터 팩 형식 (2026-10-25) — core/isekai3d_server.py 가 맞는 팩만 내준다
    fmt = json.loads((repo / 'package.json').read_text(encoding='utf-8')).get('modelsFormat', 1)
    (OUT / 'build.json').write_text(json.dumps({'commit': commit, 'dirty': dirty, 'modelsFormat': fmt}), encoding='utf-8')
    size = sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())
    print(f'이세계 사회인 {commit}{" (커밋 안 한 변경 포함)" if dirty else ""}, 캐릭터 팩 형식 {fmt} → {OUT} ({size / 2**20:.1f} MB)')


if __name__ == '__main__':
    main()
