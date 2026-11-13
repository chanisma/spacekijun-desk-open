"""Windows logon startup for this user only — opt-in on the teacher desk, on by default for students."""
from pathlib import Path
import sys
import winreg

from . import edition

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = edition.APP_ID      # 판마다 따로 등록한다 — 교사용·학생용이 서로 지우지 않게


def command() -> str:
    executable = Path(sys.executable).resolve()
    if getattr(sys, 'frozen', False):
        result = f'"{executable}" --autostart'
    else:
        pythonw = executable.with_name('pythonw.exe')
        if pythonw.exists():
            executable = pythonw
        script = Path(__file__).resolve().parents[1] / ('student.py' if edition.STUDENT else 'packaged.py')
        result = f'"{executable}" "{script}" --autostart'
    if len(result) > 260:
        raise ValueError('실행 파일 경로가 너무 깁니다. 더 짧은 경로로 옮긴 뒤 자동 실행을 켜 주세요.')
    return result


def registered_command() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
            return value if kind == winreg.REG_SZ and isinstance(value, str) else None
    except FileNotFoundError:
        return None


def managed() -> bool:
    """학교가 PC 전체에 자동 실행을 걸어 두었는가 (Intune 배포 — deploy/intune/install.ps1).

    그 값은 HKLM 에 있어 학생이 끌 수 없다. 이때는 설정의 스위치를 켜진 채 잠근다.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
            return kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and bool(value)
    except OSError:
        return False


def enabled() -> bool:
    return bool(registered_command()) or managed()


def set_enabled(value: bool):
    if value:
        executable_command = command()
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, executable_command)
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass


def ensure_default(choice) -> bool:
    """학생판은 자동 실행이 기본 (2026-10-16 요청) — 고른 적 없으면(choice None) 실행 파일일 때 켜 두고 True.
    설정에서 끈 것(False)·켠 것, 학교가 PC 전체에 건 것(HKLM)은 그대로 둔다."""
    if not edition.STUDENT or choice is not None or managed() or not getattr(sys, 'frozen', False):
        return False
    set_enabled(True)
    return True


def refresh_registration():
    # A new version is often saved under another filename. Respect opt-out, but
    # update an existing opt-in to the actual EXE, never the extracted _MEI path.
    previous = registered_command()
    if previous and previous != command():
        set_enabled(True)
