"""데스크 자동 업데이트 (교사판, 2026-10-13 요청 — 묻지 않고 적용).

  1. 확인: 켠 지 조금 뒤와 6시간마다 Supabase Storage 의 `desk-releases/teacher/latest.json` 을 읽는다.
     목록은 **Ed25519 로 서명**되어 있고(배포 PC 에만 있는 키, deploy/desk-update/publish.py),
     여기 박아 둔 공개 키로 확인되지 않으면 버린다. 저장소 계정이 털려도 남의 실행 파일은 깔리지 않는다.
  2. 받기: 지금보다 새 판이면 조각(part)들을 받아 이어 붙이고, 조각마다·전체의 SHA-256 을 목록과 맞춘다.
     `<자료 폴더>/update/` 에 두고 pending.json 에 적는다.
  3. 바꾸기: 다음에 켤 때, 또는 켜져 있는 동안 사용자가 20분 넘게 손을 놓고 하던 일이 없을 때
     (desktop.py `_update_*`). **받아 둔 새 실행 파일을 '설치 모드'로 띄우고 옛것은 그냥 끝난다**
     (`start_install`). 새것(설치 모드, `install_main`)은 옛것의 두 프로세스가 다 끝나기를 기다렸다가
     제 몸을 원래 자리에 덮어쓰고, 그 자리의 새 판을 `--after-update` 로 띄운 뒤 끝난다. 자리가 같으니
     Windows 자동 실행 등록도 그대로다. 덮어쓰지 못하면 옛것을 그대로 다시 띄운다.
     🚨 돌고 있는 옛것이 제 실행 파일을 비키고(이름 바꾸기) 새것을 놓으면 안 된다. 한 파일 실행 파일은
        모듈을 **그 경로의 파일에서** 그때그때 읽으므로, 바꾼 뒤 옛것이 무엇이든 불러오면 새 파일을 옛
        자리표로 읽다 'Error -3 while decompressing data' 로 죽고 오류 창을 남긴다 (2026-10-13 확인).
  · 학생판(2026-10-16 요청)은 `desk-releases/student/` 를 본다. Intune 이 Program Files 에 깔아 학생이 쓸 수
    없으면 새 판을 **이 사용자의 사본**(`<자료 폴더>/app/`, `user_copy`)에 놓고, Program Files 의 것은 켤 때
    그 사본이 더 새 판이면 그쪽을 띄우고 끝난다 (`handoff`, student.py). Intune 이 더 새 판을 깔면 사본을 치운다.
  · 소스에서 돌릴 때(python app/main.py)는 바꿀 실행 파일이 없으니 쓰지 않는다.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.request
from pathlib import Path

from core import child, ed25519, edition

SUPABASE = 'https://your-project-ref.supabase.co'
BUCKET = 'desk-releases'
# 배포 PC 의 서명 키와 짝인 공개 키 (deploy/desk-update/publish.py --key 가 보여 준다)
PUBLIC_KEY = bytes.fromhex('2446b283914417bacf07dfa2a26447f3e9979a80d0ca28b8396e32b9762c529a')
FIRST_CHECK = 90           # 켜고 이만큼(초) 뒤 처음 확인 — 켜는 동안의 일과 겹치지 않게
EVERY = 6 * 3600           # 그다음 확인 간격
RETRY = 30 * 60            # 실패하면 이만큼 뒤 다시
RETRY_SOON = 30            # 켠 직후의 실패는 이만큼 뒤 다시 — 부팅 직후엔 인터넷이 아직 안 붙었을 수 있다
SOON_TRIES = 6             # 그렇게 몇 번까지 (그다음은 RETRY)
MAX_SIZE = 400 * 1024 * 1024
VERSION = re.compile(r'^\d{1,4}(\.\d{1,4}){1,3}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')


class UpdateError(Exception):
    pass


def use(student: bool, test: bool = False) -> None:
    """어느 판의 새 판을 다룰지 — 기본은 지금 도는 판. 올리는 쪽(publish.py --student · --test)이 바꾼다.
    test — 관리자만 받는 테스트 판(2026-10-30 요청): `desk-releases/teacher-test/`, 학생판은 `student-test/`(2026-11-04 요청).
    관리자 계정이고 «테스트 판 받기»를 켰을 때만 이 통로도 본다(Checker channels) — 둘 중 더 새 판을 받는다."""
    global APP, CHANNEL, TEST_CHANNEL, PUBLIC_URL, PART
    APP = 'SpacekijunStudent' if student else 'SpacekijunDesk'
    TEST_CHANNEL = ('student' if student else 'teacher') + '-test'
    CHANNEL = TEST_CHANNEL if test else ('student' if student else 'teacher')
    PUBLIC_URL = channel_url(CHANNEL)
    PART = re.compile(rf'^{APP}\.exe\.part\d{{1,3}}$')



def channel_url(channel: str) -> str:
    return f'{SUPABASE}/storage/v1/object/public/{BUCKET}/{channel}'


use(edition.STUDENT)


def version_tuple(value: str) -> tuple:
    if not isinstance(value, str) or not VERSION.match(value):
        raise UpdateError(f'판 번호 형식이 올바르지 않습니다: {value!r}')
    return tuple(int(piece) for piece in value.split('.'))


def newer(candidate: str, current: str) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def canonical(manifest: dict) -> bytes:
    """서명하는 바이트 — 키 순서·공백에 흔들리지 않게."""
    return json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def check_manifest(document, public_key: bytes = None) -> dict:
    """latest.json 을 믿을 수 있으면 그 안의 목록을 돌려준다. 아니면 UpdateError."""
    key = PUBLIC_KEY if public_key is None else public_key
    if not isinstance(document, dict) or not isinstance(document.get('manifest'), dict) \
            or not isinstance(document.get('signature'), str) or not re.fullmatch(r'[0-9a-f]{128}', document['signature']):
        raise UpdateError('업데이트 목록 형식이 올바르지 않습니다.')
    manifest = document['manifest']
    if not ed25519.verify(key, canonical(manifest), bytes.fromhex(document['signature'])):
        raise UpdateError('업데이트 목록의 서명이 맞지 않습니다.')
    if manifest.get('app') != APP:
        raise UpdateError('다른 프로그램의 업데이트 목록입니다.')
    version_tuple(manifest.get('version'))
    size, digest, parts = manifest.get('size'), manifest.get('sha256'), manifest.get('parts')
    if not isinstance(size, int) or not 0 < size <= MAX_SIZE or not isinstance(digest, str) or not HEX64.match(digest) \
            or not isinstance(parts, list) or not 0 < len(parts) <= 64:
        raise UpdateError('업데이트 목록 내용이 올바르지 않습니다.')
    total = 0
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get('name'), str) or not PART.match(part['name']) \
                or not isinstance(part.get('size'), int) or part['size'] <= 0 \
                or not isinstance(part.get('sha256'), str) or not HEX64.match(part['sha256']):
            raise UpdateError('업데이트 조각 정보가 올바르지 않습니다.')
        total += part['size']
    if total != size:
        raise UpdateError('업데이트 조각 크기가 맞지 않습니다.')
    return manifest


def fetch_bytes(url: str, timeout: float = 60) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': f'{APP}-updater', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(MAX_SIZE + 1)


def latest(fetch=fetch_bytes, channel: str | None = None) -> dict:
    raw = fetch(f'{channel_url(channel) if channel else PUBLIC_URL}/latest.json?t={int(time.time())}')
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise UpdateError('업데이트 목록을 읽지 못했습니다.') from None
    return check_manifest(document)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def download(manifest: dict, folder: Path, fetch=fetch_bytes, channel: str | None = None) -> dict:
    """조각을 받아 이어 붙이고 확인한 뒤 pending.json 에 적는다. 돌려주는 것은 그 내용."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    version = manifest['version']
    target = folder / f'{APP}-{version}.exe'
    if not (target.is_file() and target.stat().st_size == manifest['size'] and _sha256(target) == manifest['sha256']):
        temporary = target.with_suffix('.download')
        whole = hashlib.sha256()
        try:
            with open(temporary, 'wb') as handle:
                for part in manifest['parts']:
                    data = fetch(f'{channel_url(channel) if channel else PUBLIC_URL}/{version}/{part["name"]}', timeout=300)
                    if len(data) != part['size'] or hashlib.sha256(data).hexdigest() != part['sha256']:
                        raise UpdateError(f'{part["name"]} 조각이 목록과 다릅니다.')
                    handle.write(data)
                    whole.update(data)
            if whole.hexdigest() != manifest['sha256']:
                raise UpdateError('이어 붙인 실행 파일이 목록과 다릅니다.')
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
    record = {'version': version, 'path': str(target), 'sha256': manifest['sha256'], 'size': manifest['size']}
    (folder / 'pending.json').write_text(json.dumps(record), encoding='utf-8')
    return record


def pending(folder: Path, current: str) -> dict | None:
    """받아 둔 새 판 — 지금보다 새것이고 파일이 목록대로일 때만."""
    try:
        record = json.loads((Path(folder) / 'pending.json').read_text(encoding='utf-8'))
        path = Path(record['path'])
        if Path(folder) not in path.parents or not newer(record['version'], current):
            return None
        if not path.is_file() or path.stat().st_size != record['size'] or _sha256(path) != record['sha256']:
            return None
        return record
    except (OSError, ValueError, KeyError, TypeError, UpdateError):
        return None


def installable(exe: Path | None = None) -> bool:
    """이 실행 파일을 스스로 바꿀 수 있나 — 실행 파일로 돌고 있고 그 폴더에 쓸 수 있을 때."""
    if exe is None:
        if not getattr(sys, 'frozen', False):
            return False
        exe = Path(sys.executable)
    if exe.suffix.lower() != '.exe' or not exe.is_file():
        return False
    # 🚨 tempfile 로 시험하면 안 된다 — Windows 에서 ACL 로 막힌 폴더(Program Files)의 PermissionError 를
    #    '이름이 겹쳤다'로 보고 TMP_MAX(약 21억) 번 다시 해 프로그램이 멈춘다 (2026-10-16 학생판 시험에서 확인).
    probe = exe.parent / f'.{APP}-write-{os.getpid()}-{time.monotonic_ns()}.tmp'
    try:
        handle = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_TEMPORARY', 0))
    except OSError:
        return False
    os.close(handle)
    probe.unlink(missing_ok=True)
    return True


def user_copy() -> Path:
    """학생판 — 깔린 자리에 쓸 수 없을 때(Intune 의 Program Files) 새 판을 놓는 이 사용자의 사본."""
    return Path(edition.DATA_DIR) / 'app' / f'{APP}.exe'


def _same(a, b) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def target() -> Path | None:
    """새 판을 놓을 자리 — 이 실행 파일 자리에 쓸 수 있으면 그 자리, 학생판이 못 쓰는 곳에 깔렸으면 사용자 사본.
    소스에서 돌거나(바꿀 실행 파일이 없다) 교사판이 못 쓰는 곳에 있으면 None."""
    if installable():
        return Path(sys.executable)
    if edition.STUDENT and APP == 'SpacekijunStudent' and getattr(sys, 'frozen', False):
        return user_copy()
    return None


def _copy_record() -> Path:
    return user_copy().with_name('version.json')


def handoff(current: str) -> Path | None:
    """학생판 입구 — 사용자 사본이 이것보다 새 판이면 그 사본 (그쪽을 띄우고 이것은 끝낸다).
    Intune 이 같거나 더 새 판을 깔아 사본이 쓸모없어졌으면 사본을 치운다."""
    copy = user_copy()
    try:
        if _same(sys.executable, copy) or not copy.is_file():
            return None
        record = json.loads(_copy_record().read_text(encoding='utf-8'))
        if not newer(record['version'], current):
            for path in (copy, _copy_record()):
                path.unlink(missing_ok=True)
            return None
        if copy.stat().st_size != record['size'] or _sha256(copy) != record['sha256']:
            return None
        return copy
    except (OSError, ValueError, KeyError, TypeError, UpdateError):
        return None


INSTALL = '--install-update'     # 새 실행 파일을 설치 모드로: --install-update <놓을 자리> --wait <pid,…> [--fallback <옛것>] --then <인자…>


def start_install(record: dict, exe: Path, then: list[str], pids: list[int], fallback: Path | None = None) -> None:
    """옛것 쪽 — 받아 둔 새 실행 파일을 설치 모드로 띄운다. 옛것은 이 뒤 **그냥 끝나면** 된다.
    제 실행 파일에는 손대지 않는다 (맨 위의 🚨). exe 는 새 판을 놓을 자리 — 학생판 사용자 사본이면 아직 없을 수
    있다. 그때 fallback 은 놓지 못했을 때 다시 띄울 옛것(지금 도는 실행 파일)."""
    source = Path(record['path'])
    if not source.is_file() or _sha256(source) != record['sha256']:
        raise UpdateError('받아 둔 새 판이 목록과 다릅니다.')
    args = [str(source), INSTALL, str(Path(exe)), '--wait', ','.join(str(pid) for pid in pids)]
    if fallback is not None:
        args += ['--fallback', str(Path(fallback))]
    child.spawn([*args, '--then', *then], str(source.parent), child.DETACHED)


def own_pids() -> list[int]:
    """이 프로그램의 두 프로세스 — 파이썬과 한 파일 실행 파일의 바깥 껍데기(부트로더). 둘 다 실행 파일을 잡는다."""
    return [os.getpid(), os.getppid()]


def install(source: Path, target: Path, tries: int = 60, delay: float = 1.0) -> None:
    """새것 쪽 — target 자리를 source 내용으로 바꾼다. target 을 잡고 있던 옛것이 놓을 때까지 다시 해 본다."""
    source, target = Path(source), Path(target)
    digest = _sha256(source)
    fresh = target.with_name(f'{target.stem}.new.exe')
    last = None
    for attempt in range(max(1, tries)):
        try:
            shutil.copyfile(source, fresh)
            if _sha256(fresh) != digest:
                raise OSError('복사한 내용이 다릅니다')
            os.replace(fresh, target)
            return
        except OSError as exc:
            last = exc
            if attempt + 1 < tries:
                time.sleep(delay)
    fresh.unlink(missing_ok=True)
    raise UpdateError(f'새 판을 놓지 못했습니다: {last}')


def install_main(argv: list[str], folder: Path) -> None:
    """설치 모드 진입점 (packaged.py). 옛것을 기다려 → 덮어쓰고 → 새 판을 띄운다.
    덮어쓰지 못하면 옛것을 그대로 다시 띄워, 사용자에게는 프로그램이 늘 돌아온다."""
    target = Path(argv[argv.index(INSTALL) + 1])
    then = argv[argv.index('--then') + 1:] if '--then' in argv else ['--autostart']
    head = argv[:argv.index('--then')] if '--then' in argv else argv
    fallback = Path(head[head.index('--fallback') + 1]) if '--fallback' in head else target
    copy = _same(target, user_copy())
    if '--wait' in argv:
        for pid in argv[argv.index('--wait') + 1].split(','):
            if pid.isdigit():
                wait_for(int(pid), 60)
    try:
        if target.suffix.lower() != '.exe' or not (target.is_file() or copy):
            raise UpdateError(f'바꿀 실행 파일이 없습니다: {target}')
        if copy:
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_record().unlink(missing_ok=True)          # 다 놓기 전에는 입구가 사본을 쓰지 않게
        install(Path(sys.executable), target)
        if copy:
            _copy_record().write_text(json.dumps({'version': edition.VERSION, 'size': target.stat().st_size,
                                                  'sha256': _sha256(target)}), encoding='utf-8')
        relaunch(target, then + ['--after-update'])
    except Exception as exc:
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
            (Path(folder) / 'install-error.log').write_text(f'{time.ctime()}\n{exc}\n', encoding='utf-8')
        except OSError:
            pass
        if fallback.is_file():
            relaunch(fallback, then)


def relaunch(exe: Path, args: list[str]) -> None:
    child.spawn([str(exe), *args], str(Path(exe).parent), child.DETACHED)


def wait_for(pid: int, timeout: float = 30) -> None:
    """프로세스가 끝나기를 기다린다 — 실행 파일과 한 번에 하나 잠금(뮤텍스)을 놓아야 새 판을 놓고 띄운다."""
    kernel32 = ctypes.WinDLL('kernel32')
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x00100000, False, int(pid))      # SYNCHRONIZE
    if handle:
        kernel32.WaitForSingleObject(handle, int(timeout * 1000))
        kernel32.CloseHandle(handle)


def _leftovers(exe: Path, folder: Path | None) -> list[Path]:
    """folder 를 주지 않으면 실행 파일 곁의 것만 (켤 때마다 — 받아 둔 새 판은 남긴다)."""
    exe = Path(exe)
    found = list(exe.parent.glob(f'{exe.stem}.old*.exe')) + list(exe.parent.glob(f'{exe.stem}.new.exe'))
    if folder is not None and Path(folder).is_dir():
        folder = Path(folder)
        found += list(folder.glob(f'{APP}-*.exe')) + list(folder.glob('*.download')) + [folder / 'pending.json']
    return [path for path in found if path.exists()]


def sweep(exe: Path, folder: Path | None, tries: int = 1, delay: float = 2.0) -> bool:
    """업데이트가 남긴 것(받아 둔 새 판·옛 방식의 .old.exe·pending.json)을 지운다. 다 지웠으면 True.

    🚨 설치 모드로 돈 새 실행 파일(받아 둔 것)은 새 판을 띄운 직후에도 한 파일 실행 파일의 **바깥
    껍데기(부트로더)**가 임시 폴더를 치우느라 잠깐 더 남아 파일을 잡고 있다 (2026-10-13 확인).
    그래서 몇 번 다시 해 본다."""
    for attempt in range(max(1, tries)):
        left = False
        for path in _leftovers(exe, folder):
            try:
                path.unlink()
            except OSError:
                left = True
        if not left:
            return True
        if attempt + 1 < tries:
            time.sleep(delay)
    return False


def finish(exe: Path, folder: Path) -> None:
    """새 판이 뜬 뒤 — 남은 것을 뒤에서 놓일 때까지 몇 번 지워 본다."""
    Path(folder, 'pending.json').unlink(missing_ok=True)       # 이건 바로 — 다시 설치하지 않게
    threading.Thread(target=sweep, args=(exe, folder, 30, 2.0), daemon=True, name='desk-update-sweep').start()


class Checker:
    """뒤에서 새 판을 확인하고 받아 둔다. 받아 두면 on_ready(record) — 언제 바꿀지는 부른 쪽이 정한다."""

    def __init__(self, current: str, folder: Path, on_ready, log, fetch=fetch_bytes, first: float = FIRST_CHECK,
                 channels=None):
        self.current, self.folder, self.on_ready, self.log, self.fetch = current, Path(folder), on_ready, log, fetch
        self.channels = channels or (lambda: [CHANNEL])   # 볼 통로들 — 관리자는 테스트 판 통로도 (desktop.py)
        self.first = first             # 켜고 처음 확인까지(초) — 데스크·학생판은 켜자마자 묻도록 짧게 (2026-10-26)
        self._stop = threading.Event()
        self._thread = None
        self._busy = threading.Lock()   # 뒤의 정기 확인과 손으로 누른 확인이 같은 파일을 함께 받지 않게

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name='desk-updater')
            self._thread.start()

    def stop(self):
        self._stop.set()

    def check_once(self) -> dict | None:
        with self._busy:
            return self._check()

    def _check(self) -> dict | None:
        record = pending(self.folder, self.current)
        if record is None:
            best, best_channel = None, None
            for channel in self.channels():
                try:
                    manifest = latest(self.fetch, channel)
                except Exception as exc:
                    if channel == CHANNEL:
                        raise                     # 정식 통로를 못 보면 실패다
                    self.log(f'테스트 판 통로를 보지 못했습니다 ({channel}):', exc)
                    continue
                if newer(manifest['version'], self.current) and (best is None or newer(manifest['version'], best['version'])):
                    best, best_channel = manifest, channel
            if best is None:
                return None
            label = '테스트 판' if best_channel != CHANNEL else '새 판'
            self.log(f'{label} {best["version"]} 을 받는 중입니다.')
            record = download(best, self.folder, self.fetch, best_channel)
            self.log(f'{label} {best["version"]} 을 받아 두었습니다.')
        self.on_ready(record)
        return record

    def _run(self):
        if self._stop.wait(self.first):
            return
        failed = 0
        while True:
            wait = EVERY
            try:
                if self.check_once():
                    return                    # 받아 두었다 — 바꾸는 것은 데스크가
                failed = SOON_TRIES           # 한 번 닿았으면 그다음 실패는 보통 간격으로
            except Exception as exc:
                self.log('업데이트를 확인하지 못했습니다:', exc)
                failed += 1
                wait = RETRY_SOON if failed <= SOON_TRIES else RETRY
            if self._stop.wait(wait):
                return
