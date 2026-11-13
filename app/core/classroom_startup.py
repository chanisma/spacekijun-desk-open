"""교실판 Windows 자동 실행 (2026-10-14 요청).

교실 PC 는 켜면 곧바로 QR 이 떠 있어야 한다 — 그래서 **처음 실행(실행 파일)에서 저절로 켠다**.
기기 설정에서 끄면 classroom.json 의 `autostart: false` 로 기억해 다시 켜지 않는다.
학교가 PC 전체(HKLM Run)에 걸어 두었으면 그것을 따르고 설정의 스위치는 켜진 채 잠근다.

데스크의 core/startup.py 는 이름(edition.APP_ID)이 데스크로 정해져 있어 쓰지 않는다 — 교실판은 따로 등록해
한 PC 에 데스크·교실판이 같이 있어도 서로 지우지 않는다.
"""
from __future__ import annotations

import sys
import winreg
from pathlib import Path

from .classroom_link import load_settings, save_settings

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'SpacekijunClassroom'


def command() -> str:
    executable = Path(sys.executable).resolve()
    if getattr(sys, 'frozen', False):
        result = f'"{executable}" --autostart'
    else:
        pythonw = executable.with_name('pythonw.exe')
        if pythonw.exists():
            executable = pythonw
        script = Path(__file__).resolve().parents[1] / 'classroom.py'
        result = f'"{executable}" "{script}" --autostart'
    if len(result) > 260:
        raise ValueError('실행 파일 경로가 너무 깁니다. 더 짧은 경로로 옮긴 뒤 자동 실행을 켜 주세요.')
    return result


def registered_command() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
            return value if kind == winreg.REG_SZ and isinstance(value, str) else None
    except OSError:
        return None


def managed() -> bool:
    """학교가 PC 전체에 걸어 두었나(HKLM) — 사용자가 끌 수 없다"""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
            return kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and bool(value)
    except OSError:
        return False


def enabled() -> bool:
    return bool(registered_command()) or managed()


def set_enabled(value: bool, remember: bool = True):
    if value:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except OSError:
            pass
    if remember:
        settings = load_settings()
        settings['autostart'] = bool(value)
        save_settings(settings)


def ensure() -> None:
    """켤 때 — 처음이면 켜 두고(실행 파일일 때만), 켜 둔 것은 지금 실행 파일 자리로 고친다. 끈 것은 그대로."""
    if managed():
        return
    choice = load_settings().get('autostart')
    if choice is False:
        return
    if choice is None:
        if getattr(sys, 'frozen', False):
            set_enabled(True)                  # 교실 PC 기본 = 켬
        return
    current = registered_command()
    if current != command():
        set_enabled(True, remember=False)      # 실행 파일을 옮겼다 — 새 자리로
