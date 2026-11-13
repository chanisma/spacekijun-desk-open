"""교실판 자동 업데이트 (2026-10-14 요청 — 데스크처럼).

데스크와 같은 core/updater.py 를 쓴다 — 서명된 목록(Ed25519, 같은 서명 키) · 조각 받기 · SHA-256 확인 · 설치 모드로
제자리 덮어쓰기. 다른 것은 «어디서 받나»뿐이라, updater 의 대상(앱 이름 · 채널 · 조각 이름)만 교실판으로 바꿔 끼운다.
updater.py 자체는 고치지 않는다(데스크와 함께 쓰는 코드).

  · 목록 = Supabase Storage `desk-releases/classroom/latest.json` (올리기 = deploy/classroom-update/publish.py)
  · 받기 = 켜고 90초 뒤 · 30분마다(CHECK_EVERY). 받아 두는 곳 = %LOCALAPPDATA%/SpacekijunClassroom/update
  · 바꾸기 = 켤 때 받아 둔 새 판이 있으면 바로 · 켜져 있으면 **수업 중이 아니고 QR 화면에서 2분 넘게 아무도 손대지 않을 때**
             (수업 중 화면이 꺼졌다 켜지면 안 된다)
  · 실행 파일이 쓸 수 없는 곳(예: Intune 이 깐 Program Files)에 있으면 바꾸지 않는다 — 교실 PC 에는 사용자 폴더에 둘 것.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from core import updater
from core.classroom_link import DATA_DIR

# 교실판 판 번호 — 새로 내보낼 때마다 올리고 deploy/classroom-update/publish.py 로 올린다.
VERSION = '1.5.9'
APP = 'SpacekijunClassroom'
CHANNEL = 'classroom'
FOLDER = Path(DATA_DIR) / 'update'
IDLE = 120                 # QR 화면에서 이만큼(초) 아무도 손대지 않으면 바꾼다
CHECK_EVERY = 30 * 60      # 새 판 확인 간격 — 데스크(6시간)보다 짧게: 고친 판이 교실에 빨리 닿게(2026-10-14)


def configure():
    """updater 를 교실판 대상으로 — 이 프로세스(교실판 실행 파일) 안에서만"""
    updater.APP = APP
    updater.CHANNEL = CHANNEL
    updater.PUBLIC_URL = f'{updater.SUPABASE}/storage/v1/object/public/{updater.BUCKET}/{CHANNEL}'
    updater.PART = re.compile(r'^SpacekijunClassroom\.exe\.part\d{1,3}$')
    updater.EVERY = CHECK_EVERY


def enabled() -> bool:
    return updater.installable()


def at_start(argv: list[str], log=print) -> bool:
    """켜자마자 — 막 바뀌었으면 남은 것을 치우고, 받아 둔 새 판이 있으면 설치 모드로 띄운다(True = 이 프로그램은 곧 끝낸다)."""
    configure()
    if not enabled():
        return False
    exe = Path(sys.executable)
    if '--after-update' in argv:
        updater.finish(exe, FOLDER)
        log(f'스페이스기전 교실 {VERSION} 로 업데이트했습니다.')
        return False
    updater.sweep(exe, None)
    record = updater.pending(FOLDER, VERSION)
    if record is None:
        return False
    try:
        updater.start_install(record, exe, [], updater.own_pids())
    except (OSError, updater.UpdateError) as exc:
        log('새 판을 설치하지 못했습니다:', exc)
        return False
    return True


def start_checker(on_ready, log=print):
    configure()
    if not enabled():
        return None
    checker = updater.Checker(VERSION, FOLDER, on_ready, log)
    checker.start()
    return checker


def apply(record: dict, log=print) -> bool:
    """지금 바꾼다 — 새 판(설치 모드)을 띄운다. True 면 부른 쪽이 프로그램을 끝내야 한다."""
    try:
        updater.start_install(record, Path(sys.executable), [], updater.own_pids())
        return True
    except (OSError, updater.UpdateError) as exc:
        log('새 판을 설치하지 못했습니다:', exc)
        return False


def install_mode(argv: list[str]):
    configure()
    updater.install_main(argv, FOLDER)


def idle_seconds() -> float:
    import ctypes

    class LastInput(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]
    info = LastInput(ctypes.sizeof(LastInput), 0)
    if not ctypes.WinDLL('user32').GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((ctypes.WinDLL('kernel32').GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def log_to_file(*parts):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, 'update.log'), 'a', encoding='utf-8') as f:
            f.write(' '.join(str(p) for p in parts) + '\n')
    except OSError:
        pass
