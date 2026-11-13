"""스페이스기전 교실(교실판) 새 판 올리기 — 켜져 있는 교실 프로그램들이 받아 스스로 바꾼다 (core/classroom_update.py).

    python deploy/classroom-update/publish.py              # dist/SpacekijunClassroom.exe 를 서명해 올린다
    python deploy/classroom-update/publish.py --dry-run    # 올리지 않고 확인만

데스크 올리기(deploy/desk-update/publish.py)와 같은 서명 키·같은 버킷(desk-releases)을 쓰고, 채널만 `classroom/` 이다.
그 스크립트의 도구(키 읽기·자체 점검·올리기)를 그대로 빌려 쓴다.

  1. 실행 파일 자체 점검(--self-test)이 통과하고, 그 판이 core/classroom_update.py 의 VERSION 과 같은지
  2. 올라가 있는 판보다 새것인지
  3. 조각으로 나눠 SHA-256 목록을 만들고 서명 → 조각들 → latest.json 순서로 올린다(관리자 계정 로그인 필요)
  4. 공개 주소에서 다시 받아 교실 프로그램과 같은 코드로 확인한다
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app'))

from core import classroom_update, ed25519, updater   # noqa: E402

classroom_update.configure()                     # updater 를 교실판 채널로 — published()·upload 경로가 여기를 따른다

_spec = importlib.util.spec_from_file_location('desk_publish', ROOT / 'deploy' / 'desk-update' / 'publish.py')
desk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(desk)

EXE = ROOT / 'dist' / 'SpacekijunClassroom.exe'
PART_SIZE = desk.PART_SIZE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--exe', type=Path, default=EXE)
    options = parser.parse_args()

    seed = desk.load_key(create=False)
    if ed25519.public_key(seed) != updater.PUBLIC_KEY:
        sys.exit('서명 키가 core/updater.py 의 PUBLIC_KEY 와 짝이 아닙니다.')

    version = classroom_update.VERSION
    print(f'== 스페이스기전 교실 {version} ==')
    report = desk.self_test(options.exe)
    if not report.get('ok'):
        sys.exit(f'실행 파일 자체 점검 실패:\n{report.get("error")}')
    if report.get('version') != version:
        sys.exit(f'실행 파일의 판({report.get("version")})이 classroom_update.VERSION({version})과 다릅니다. 다시 빌드하세요.')
    print(f'  자체 점검 {len(report["checks"])}개 통과')
    current = desk.published()
    if current and not updater.newer(version, current['version']):
        sys.exit(f'올라가 있는 판({current["version"]})보다 새 판이 아닙니다. classroom_update.VERSION 을 올리세요.')
    print(f'  올라가 있는 판: {current["version"] if current else "(없음)"}')

    data = options.exe.read_bytes()
    pieces = [data[at:at + PART_SIZE] for at in range(0, len(data), PART_SIZE)]
    parts = [{'name': f'SpacekijunClassroom.exe.part{index + 1}', 'size': len(piece),
              'sha256': hashlib.sha256(piece).hexdigest()} for index, piece in enumerate(pieces)]
    manifest = {'app': updater.APP, 'version': version, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'parts': parts, 'published': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    document = {'manifest': manifest, 'signature': ed25519.sign(seed, updater.canonical(manifest)).hex()}
    updater.check_manifest(document)
    print(f'  {len(data) / 1048576:.1f}MB → 조각 {len(parts)}개, 서명함')
    if options.dry_run:
        print('  (--dry-run: 올리지 않았습니다)')
        return

    for part, piece in zip(parts, pieces):
        desk.upload(f'{updater.CHANNEL}/{version}/{part["name"]}', piece, 'application/octet-stream', 'max-age=31536000')
        print(f'  올림 {part["name"]}')
    desk.upload(f'{updater.CHANNEL}/latest.json', json.dumps(document, ensure_ascii=False).encode('utf-8'),
                'application/json', 'max-age=60')
    print('  올림 latest.json')

    time.sleep(2)
    seen = updater.latest()
    if seen['version'] != version:
        sys.exit(f'공개 주소의 판이 아직 {seen["version"]} 입니다 (캐시). 잠시 뒤 다시 확인하세요.')
    with tempfile.TemporaryDirectory() as folder:
        record = updater.download(seen, Path(folder))
        assert Path(record['path']).read_bytes() == data
    print(f'완료 — 켜져 있는 교실 프로그램들이 30분 안에 {version} 을 받아, 수업이 없는 틈이나 다음에 켤 때 바꿉니다.')


if __name__ == '__main__':
    main()
