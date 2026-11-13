"""스페이스기전 데스크(교사판) 새 판 올리기 — 켜져 있는 데스크들이 받아 스스로 바꾼다 (core/updater.py).

    python deploy/desk-update/publish.py --key        # 처음 한 번: 서명 키 만들기 (있으면 공개 키만 보인다)
    python deploy/desk-update/publish.py              # dist/SpacekijunDesk.exe 를 서명해 올린다
    python deploy/desk-update/publish.py --dry-run    # 올리지 않고 확인만
    python deploy/desk-update/publish.py --student    # 학생판: dist/SpacekijunStudent.exe → desk-releases/student/
    python deploy/desk-update/publish.py --test       # 테스트 판: 관리자 계정이 «테스트 판 받기»를 켠 데스크만 받는다
                                                      #   → desk-releases/teacher-test/ (2026-10-30). 정식 판보다 새 판이어야 한다
                                                      #   (STUDENT_VERSION, 같은 서명 키 — 2026-10-16)
    python deploy/desk-update/publish.py --student --test   # 학생판 테스트 판: 관리자 계정으로 로그인해 «테스트 판 받기»를 켠 학생판만
                                                      #   → desk-releases/student-test/ (2026-11-04). 학생판 정식 판보다 새 판이어야 한다

하는 일
  1. 실행 파일 자체 점검(--self-test)이 통과하고, 그 판 번호가 app/core/edition.py 의 DESK_VERSION 과 같은지
  2. 올라가 있는 판보다 새것인지 (같거나 옛것이면 멈춘다)
  3. 실행 파일을 조각(PART_SIZE)으로 나눠 SHA-256 을 적은 목록(manifest)을 만들고 **서명 키로 서명**
  4. 조각들 → 목록(latest.json) 순서로 Supabase Storage `desk-releases/teacher/` 에 올린다.
     올리기는 이 PC 데스크에 로그인한 계정으로 하며, 저장소 정책상 관리자(is_admin)만 된다.
  5. 공개 주소에서 다시 받아 데스크와 같은 코드로 서명·조각을 확인한다.

서명 키: .secrets/desk-update.key (DPAPI 로 암호화 — 이 PC 이 Windows 계정에서만 풀린다. 저장소에 올리지 않는다).
🚨 키를 잃으면 새 판을 올릴 수 없다. 그때는 새 키의 공개 키를 core/updater.py 에 넣은 판을 모든 PC 에 손으로 한 번 깔아야 한다.

다른 PC 에서도 올리기 (2026-10-30) — 키 파일은 복사해도 그 PC 에서 풀리지 않으니, 암호를 걸어 옮긴다.
    (키가 있는 PC)  python deploy/desk-update/publish.py --export-key E:\\desk-update.key.json
    (새 PC)        python deploy/desk-update/publish.py --import-key E:\\desk-update.key.json
  옮길 파일은 저장소 밖(USB 등)에만 쓴다. 가져온 뒤에는 지운다. 올리기 권한은 따로 — 새 PC 데스크에 관리자 계정으로 로그인.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app'))

from core import ed25519, edition, secretstore, supa_auth, updater   # noqa: E402

KEY_PATH = ROOT / '.secrets' / 'desk-update.key'
EXE = ROOT / 'dist' / 'SpacekijunDesk.exe'
STUDENT_EXE = ROOT / 'dist' / 'SpacekijunStudent.exe'
PART_SIZE = 20 * 1024 * 1024


def load_key(create: bool) -> bytes:
    if KEY_PATH.exists():
        return secretstore.decrypt(KEY_PATH.read_bytes())
    if not create:
        sys.exit('서명 키가 없습니다. 먼저  python deploy/desk-update/publish.py --key  로 만드세요.')
    seed = os.urandom(32)
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_bytes(secretstore.encrypt(seed))
    print(f'서명 키를 만들었습니다: {KEY_PATH}')
    return seed


KEY_FORMAT = 'spacekijun-desk-update-key/1'


def _passphrase_key(passphrase: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(passphrase.encode('utf-8'))


def seal_key(seed: bytes, passphrase: str) -> bytes:
    """서명 키를 암호로 잠근 옮길 파일 내용 (scrypt + AES-GCM)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(16), os.urandom(12)
    sealed = AESGCM(_passphrase_key(passphrase, salt)).encrypt(nonce, seed, KEY_FORMAT.encode())
    document = {'format': KEY_FORMAT, 'public': ed25519.public_key(seed).hex(),
                'salt': salt.hex(), 'nonce': nonce.hex(), 'sealed': sealed.hex()}
    return json.dumps(document, indent=1).encode('utf-8')


def open_key(data: bytes, passphrase: str) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    document = json.loads(data.decode('utf-8'))
    if document.get('format') != KEY_FORMAT:
        sys.exit('서명 키 옮길 파일이 아닙니다.')
    try:
        seed = AESGCM(_passphrase_key(passphrase, bytes.fromhex(document['salt']))).decrypt(
            bytes.fromhex(document['nonce']), bytes.fromhex(document['sealed']), KEY_FORMAT.encode())
    except InvalidTag:
        sys.exit('암호가 틀렸거나 파일이 손상됐습니다.')
    return seed


def ask_passphrase(confirm: bool) -> str:
    import getpass
    passphrase = getpass.getpass('옮길 파일 암호: ')
    if confirm:
        if len(passphrase) < 12:
            sys.exit('암호는 12자 이상으로 하세요.')
        if getpass.getpass('한 번 더: ') != passphrase:
            sys.exit('두 암호가 다릅니다.')
    return passphrase


def export_key(target: Path) -> None:
    target = target.resolve()
    if ROOT in target.parents:
        sys.exit('저장소 안에는 쓰지 않습니다. USB 등 저장소 밖 경로를 주세요.')
    if target.exists():
        sys.exit(f'이미 있는 파일입니다: {target}')
    seed = load_key(create=False)
    target.write_bytes(seal_key(seed, ask_passphrase(confirm=True)))
    print(f'내보냄: {target}\n새 PC 에서  --import-key  로 가져온 뒤 이 파일은 지우세요.')


def import_key(source: Path) -> None:
    seed = open_key(source.read_bytes(), ask_passphrase(confirm=False))
    if ed25519.public_key(seed) != updater.PUBLIC_KEY:
        sys.exit('core/updater.py 의 PUBLIC_KEY 와 짝이 아닌 키입니다. 가져오지 않았습니다.')
    if KEY_PATH.exists():
        if load_key(create=False) == seed:
            print('이 PC 에 이미 같은 키가 있습니다.')
            return
        sys.exit(f'이 PC 에 다른 키가 있습니다: {KEY_PATH}. 확인하고 직접 치운 뒤 다시 하세요.')
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_bytes(secretstore.encrypt(seed))
    print(f'가져옴: {KEY_PATH} (이 PC 이 Windows 계정에 묶어 저장)\n이제 옮길 파일을 지우세요: {source}')


def self_test(exe: Path) -> dict:
    report = Path(tempfile.gettempdir()) / f'spacekijun-desk-publish-{os.getpid()}.json'
    subprocess.run([str(exe), '--self-test', str(report)], check=False, timeout=300)
    try:
        return json.loads(report.read_text(encoding='utf-8'))
    finally:
        report.unlink(missing_ok=True)


def published() -> dict | None:
    try:
        return updater.latest()
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 404):
            return None                       # 아직 올린 판이 없다
        raise


def upload(path: str, data: bytes, content_type: str, cache: str) -> None:
    url = f'{updater.SUPABASE}/storage/v1/object/{updater.BUCKET}/{path}'
    headers = {**supa_auth.auth_headers(), 'Content-Type': content_type, 'x-upsert': 'true', 'Cache-Control': cache}
    request = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f'올리지 못했습니다 ({path}): {exc.code} {exc.read().decode("utf-8", "replace")}') from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', action='store_true', help='서명 키를 만들고(없으면) 공개 키를 보인다')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--student', action='store_true', help='학생판을 desk-releases/student/ 에 올린다')
    parser.add_argument('--test', action='store_true', help='관리자만 받는 테스트 판으로 desk-releases/teacher-test/ (--student 와 함께면 student-test/) 에 올린다')
    parser.add_argument('--export-key', type=Path, metavar='FILE', help='서명 키를 암호로 잠가 다른 PC 로 옮길 파일로 쓴다')
    parser.add_argument('--import-key', type=Path, metavar='FILE', help='--export-key 로 만든 파일에서 서명 키를 이 PC 에 들인다')
    options = parser.parse_args()

    if options.export_key:
        return export_key(options.export_key)
    if options.import_key:
        return import_key(options.import_key)

    seed = load_key(create=options.key)
    public = ed25519.public_key(seed)
    if options.key:
        print(f'공개 키: {public.hex()}')
        print('core/updater.py 의 PUBLIC_KEY 와 같아야 합니다.')
        return
    if public != updater.PUBLIC_KEY:
        sys.exit('서명 키가 core/updater.py 의 PUBLIC_KEY 와 짝이 아닙니다. 데스크들이 이 판을 믿지 않습니다.')

    updater.use(options.student, options.test)           # 판·조각 이름·올릴 자리 (teacher / teacher-test / student / student-test)
    options.exe = options.exe or (STUDENT_EXE if options.student else EXE)
    version = edition.STUDENT_VERSION if options.student else edition.DESK_VERSION
    name, field = ('스페이스기전 학생', 'STUDENT_VERSION') if options.student else ('스페이스기전 데스크', 'DESK_VERSION')
    print(f'== {name} {version} ({updater.CHANNEL}) ==')
    report = self_test(options.exe)
    if not report.get('ok'):
        sys.exit(f'실행 파일 자체 점검 실패:\n{report.get("error")}')
    if report.get('version') != version:
        sys.exit(f'실행 파일의 판({report.get("version")})이 edition.py 의 {field}({version})과 다릅니다. 다시 빌드하세요.')
    print(f'  자체 점검 {len(report["checks"])}개 통과')
    current = published()
    if current and not updater.newer(version, current['version']):
        sys.exit(f'올라가 있는 판({current["version"]})보다 새 판이 아닙니다. {field} 을 올리세요.')
    print(f'  올라가 있는 판: {current["version"] if current else "(없음)"}')
    if options.test:
        stable = updater.latest(channel='student' if options.student else 'teacher')
        if not updater.newer(version, stable['version']):
            sys.exit(f'정식 판({stable["version"]})보다 새 판이어야 관리자의 {name}이 받습니다. {field} 을 올리세요.')
        print(f'  정식 판: {stable["version"]} — 이 테스트 판은 관리자 계정의 {name}만 받습니다')

    data = options.exe.read_bytes()
    pieces = [data[at:at + PART_SIZE] for at in range(0, len(data), PART_SIZE)]
    parts = [{'name': f'{updater.APP}.exe.part{index + 1}', 'size': len(piece),
              'sha256': hashlib.sha256(piece).hexdigest()} for index, piece in enumerate(pieces)]
    manifest = {'app': updater.APP, 'version': version, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'parts': parts, 'published': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    document = {'manifest': manifest, 'signature': ed25519.sign(seed, updater.canonical(manifest)).hex()}
    updater.check_manifest(document)                     # 데스크와 같은 확인을 먼저 통과해야 한다
    print(f'  {len(data) / 1048576:.1f}MB → 조각 {len(parts)}개, 서명함')
    if options.dry_run:
        print('  (--dry-run: 올리지 않았습니다)')
        return

    for part, piece in zip(parts, pieces):
        upload(f'{updater.CHANNEL}/{version}/{part["name"]}', piece, 'application/octet-stream', 'max-age=31536000')
        print(f'  올림 {part["name"]}')
    upload(f'{updater.CHANNEL}/latest.json', json.dumps(document, ensure_ascii=False).encode('utf-8'),
           'application/json', 'max-age=60')
    print('  올림 latest.json')

    # 공개 주소에서 다시 받아 데스크와 똑같이 확인한다
    time.sleep(2)
    seen = updater.latest()
    if seen['version'] != version:
        sys.exit(f'공개 주소의 판이 아직 {seen["version"]} 입니다 (캐시). 잠시 뒤 다시 확인하세요.')
    with tempfile.TemporaryDirectory() as folder:
        record = updater.download(seen, Path(folder), channel=updater.CHANNEL)
        assert Path(record['path']).read_bytes() == data
    print(f'완료 — 켜져 있는 {name}이 6시간 안에 {version} 을 받아 바꿀지 묻고, 다음에 켤 때도 묻습니다 (1.3.34·1.0.33 까지의 판은 묻지 않고 바꿉니다).')


if __name__ == '__main__':
    main()
