"""이 프로그램이 다른 프로그램을 띄울 때 쓰는 공통 손질 (에이전트 터미널·자동 업데이트).

🚨 한 파일 실행 파일(PyInstaller onefile)은 두 가지를 자식에게 물려준다.
  · DLL 찾는 자리(SetDllDirectory)를 압축 푼 임시 폴더로 바꿔 둔다 — 자식이 엉뚱한 DLL 을 읽는다.
  · `_PYI_*`·`_MEI*` 환경 값 — 자식이 **또 다른 PyInstaller 실행 파일**이면(새 판의 데스크) 제가
    부모의 자식인 줄 알고 우리 임시 폴더를 쓰려다 죽는다. PyInstaller 6 의 약속대로
    `PYINSTALLER_RESET_ENVIRONMENT=1` 을 넣고 그 값들을 뺀다.
"""
from __future__ import annotations

import contextlib
import ctypes
import os
import subprocess
import threading

NEW_CONSOLE = 0x00000010
DETACHED = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
_lock = threading.Lock()


def clean_env(path: str | None = None) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('_MEI', '_PYI'))}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    if path is not None:
        env['PATH'] = path
    return env


@contextlib.contextmanager
def plain_dll_directory():
    """그동안 DLL 찾는 자리를 Windows 기본으로 돌려 둔다 — 그 사이에 띄운 자식은 압축 푼 임시 폴더를 물려받지 않는다."""
    kernel32 = ctypes.WinDLL('kernel32')
    saved = ctypes.create_unicode_buffer(1024)
    had = kernel32.GetDllDirectoryW(1024, saved)
    with _lock:
        if had:
            kernel32.SetDllDirectoryW(None)
        try:
            yield
        finally:
            if had:
                kernel32.SetDllDirectoryW(saved.value)


def spawn(args: list[str], cwd: str, flags: int = 0, path: str | None = None) -> subprocess.Popen:
    with plain_dll_directory():
        return subprocess.Popen(args, cwd=cwd, env=clean_env(path), close_fds=True, creationflags=flags)
