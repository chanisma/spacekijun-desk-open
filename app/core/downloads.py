"""내려받은 파일을 놓을 자리.

Playwright 가 브라우저에 붙어 있으면 내려받기를 가로채, 파일이 임시 폴더에
`d6b39ae4-…` 같은 GUID 이름으로 떨어진다. 그래서 잡아서 **다운로드 폴더에 제 이름으로**
옮겨 준다. 그 자리와 겹치지 않는 이름을 여기서 고른다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# 윈도우가 `다운로드` 폴더를 적어 두는 자리. 사용자가 옮겨 두었을 수 있어 여기서 읽는다.
SHELL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
DOWNLOADS_GUID = '{374DE290-123F-4565-9164-39C4925E467B}'
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def folder() -> Path:
    """이 PC 의 다운로드 폴더. 못 읽으면 집 아래 `Downloads` 로 본다."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_KEY) as key:
            spot = Path(os.path.expandvars(winreg.QueryValueEx(key, DOWNLOADS_GUID)[0]))
            if spot.is_dir():
                return spot
    except Exception:
        pass
    return Path.home() / 'Downloads'


def safe_name(name: str) -> str:
    """파일 이름으로 쓸 수 없는 글자를 걷어 낸다. 서버가 주는 이름을 그대로 믿지 않는다."""
    cleaned = UNSAFE.sub('_', (name or '').strip()).strip('. ')
    return cleaned or '내려받은파일'


def spot_for(name: str, where: Path | None = None) -> Path:
    """겹치지 않는 자리를 고른다. 브라우저처럼 `이름 (2).xlsx` 로 비켜 준다."""
    base = where or folder()
    base.mkdir(parents=True, exist_ok=True)
    clean = Path(safe_name(name))
    spot = base / clean
    for number in range(2, 1000):
        if not spot.exists():
            return spot
        spot = base / f'{clean.stem} ({number}){clean.suffix}'
    return base / f'{clean.stem} ({os.getpid()}){clean.suffix}'
