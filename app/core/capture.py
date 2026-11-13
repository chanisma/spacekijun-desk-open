"""캡처 — Windows 화면 캡처로 자른 그림을 '캡처 보관함' 폴더에 파일로 모은다.

영역 고르기는 **Windows 자신의 캡처 화면**(`ms-screenclip:`, Win+Shift+S 와 같은 것)에
맡긴다. 사각형·자유형·창·전체 화면을 그대로 쓸 수 있고, 배율이 다른 모니터가 섞여도
Windows 가 알아서 맞춘다. 캡처가 끝나면 그림이 클립보드에 오므로, 클립보드가 바뀌기를
기다렸다가 그림이면 PNG 파일로 저장한다.

보관함의 그림은 **평범한 파일**이다. 끌어다 다른 프로그램에 놓거나(desktop.py 가 Windows
파일 끌기로 넘긴다) 두 번 눌러 기본 프로그램으로 열 수 있다.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from datetime import datetime
import io
import os
from pathlib import Path
import threading
import time

WAIT = 120                # 영역을 고르기를 기다리는 시간 (초). 그동안 그림이 안 오면 취소로 본다
CLOSE_GRACE = 1.5         # 캡처 화면이 닫힌 뒤 그림이 클립보드에 오기를 기다리는 시간 (초)
OVERLAY_TITLES = ('캡처 도구 오버레이', 'Snipping Tool Overlay')
THUMB = 360               # 썸네일 긴 변 (px)
IMAGES = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')
MAX_NAME = 120            # 파일 이름 길이 상한 (확장자 빼고)
BAD_CHARS = set('\\/:*?"<>|') | {chr(code) for code in range(32)}
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{n}' for n in range(1, 10)), *(f'LPT{n}' for n in range(1, 10))}

_thumbs: dict[tuple[str, int], tuple[int, int, str]] = {}   # (이름, 수정 시각) → (가로, 세로, 썸네일)
_thumb_lock = threading.Lock()


def _clipboard_sequence() -> int:
    return ctypes.windll.user32.GetClipboardSequenceNumber()


def _clipboard_image():
    """클립보드의 그림. 다른 프로그램이 클립보드를 잡고 있으면 잠깐 뒤 다시 본다."""
    from PIL import Image, ImageGrab
    for _ in range(6):
        try:
            data = ImageGrab.grabclipboard()
        except OSError:
            time.sleep(0.15)
            continue
        return data if isinstance(data, Image.Image) else None
    return None


def overlay_open() -> bool:
    """Windows 캡처 화면(영역 고르는 어두운 화면)이 떠 있나.

    캡처 도구 프로세스는 닫혀도 남아 있어 프로세스로는 알 수 없다. 대신 그 화면의 창
    ('캡처 도구 오버레이' / 'Snipping Tool Overlay')이 있는지 본다 — 고르거나 Esc 로
    닫으면 창이 사라진다 (2026-10-11 Windows 11 확인)."""
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if any(word in title.value for word in OVERLAY_TITLES):
            cloaked = wintypes.INT()
            dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
            if not cloaked.value:
                found.append(hwnd)
                return False
        return True
    user32.EnumWindows(visit, 0)
    return bool(found)


def wait_closed(timeout: float = 2.0, overlay=overlay_open) -> None:
    """캡처 화면이 다 닫힐 때까지 잠깐 기다린다 (그림이 닫히기 직전에 오기도 한다)."""
    deadline = time.monotonic() + timeout
    while overlay() and time.monotonic() < deadline:
        time.sleep(0.1)
    time.sleep(0.25)                     # 앞 창이 포커스를 되찾는 것까지 지나가게


def snip(folder: Path, cancelled: threading.Event, wait: float = WAIT,
         launch=lambda: os.startfile('ms-screenclip:'), overlay=overlay_open) -> Path | None:
    """Windows 캡처 화면을 띄우고, 자른 그림을 파일로 저장해 돌려준다. 취소하면 None.

    캡처 화면이 닫혔는데 그림이 오지 않으면(Esc) 곧바로 취소로 본다. 캡처 화면을 알아보지
    못하는 Windows 에서는 `wait` 초까지 기다린다."""
    seen = _clipboard_sequence()
    launch()
    started = time.monotonic()
    deadline = started + wait
    showed = False                       # 캡처 화면이 한 번이라도 떴나
    closed_at = None                     # 캡처 화면이 닫힌 시각 — 그림이 조금 늦게 올 수 있다
    while time.monotonic() < deadline and not cancelled.is_set():
        time.sleep(0.25)
        now = _clipboard_sequence()
        if now != seen:
            seen = now                   # 글자를 복사한 것일 수도 있다 — 그림일 때만 받는다
            image = _clipboard_image()
            if image is not None:
                return save(folder, image)
        if overlay():
            showed, closed_at = True, None
        elif showed:
            closed_at = closed_at or time.monotonic()
            if time.monotonic() - closed_at > CLOSE_GRACE:
                return None
    return None


def save(folder: Path, image) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y-%m-%d %H.%M.%S')
    path = folder / f'캡처 {stamp}.png'
    number = 2
    while path.exists():
        path = folder / f'캡처 {stamp} ({number}).png'
        number += 1
    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGBA')
    image.save(path, 'PNG')
    return path


def _thumbnail(path: Path, stamp: int) -> tuple[int, int, str]:
    key = (path.name, stamp)
    with _thumb_lock:
        if key in _thumbs:
            return _thumbs[key]
    from PIL import Image
    with Image.open(path) as image:
        width, height = image.size
        image.thumbnail((THUMB, THUMB))
        canvas = image.convert('RGBA')
        flat = Image.new('RGB', canvas.size, (255, 255, 255))
        flat.paste(canvas, mask=canvas.getchannel('A'))
        buffer = io.BytesIO()
        flat.save(buffer, 'JPEG', quality=82)
    value = (width, height, 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode())
    with _thumb_lock:
        _thumbs[key] = value
    return value


def items(folder: Path) -> list[dict]:
    """보관함의 그림들. 새것이 먼저."""
    if not folder.is_dir():
        return []
    found = []
    for path in folder.iterdir():
        if path.suffix.lower() not in IMAGES or not path.is_file():
            continue
        stat = path.stat()
        try:
            width, height, thumb = _thumbnail(path, stat.st_mtime_ns)
        except (OSError, ValueError):
            continue                     # 깨진 파일은 건너뛴다
        found.append({'name': path.name, 'size': stat.st_size, 'width': width, 'height': height,
                      'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
                      'stamp': stat.st_mtime_ns, 'thumb': thumb})
    return sorted(found, key=lambda item: item['stamp'], reverse=True)


def signature(folder: Path) -> str:
    """폴더가 바뀌었는지 보는 짧은 표식 — 보관함 창이 자주 묻는다."""
    if not folder.is_dir():
        return ''
    parts = sorted(f'{path.name}:{path.stat().st_mtime_ns}' for path in folder.iterdir()
                   if path.suffix.lower() in IMAGES and path.is_file())
    return str(hash(tuple(parts)))


def resolve(folder: Path, name) -> Path:
    """화면이 보낸 이름을 보관함 안의 파일로. 폴더 밖이나 그림이 아닌 것은 받지 않는다."""
    if not isinstance(name, str) or not name or Path(name).name != name or name in ('.', '..'):
        raise ValueError('파일 이름이 올바르지 않습니다.')
    path = folder / name
    if path.suffix.lower() not in IMAGES or not path.is_file():
        raise LookupError(f'‘{name}’ 파일을 찾을 수 없습니다. 이미 지웠거나 옮겼을 수 있습니다.')
    return path


def rename(folder: Path, name, new_stem) -> Path:
    """이름만 바꾼다. 확장자는 그대로 두고, 같은 이름이 있으면 막는다."""
    path = resolve(folder, name)
    if not isinstance(new_stem, str):
        raise ValueError('새 이름이 올바르지 않습니다.')
    stem = new_stem.strip().rstrip('. ')
    if stem.lower().endswith(path.suffix.lower()):
        stem = stem[:-len(path.suffix)].rstrip('. ')   # 확장자까지 적었으면 떼어 낸다
    if not stem:
        raise ValueError('새 이름을 입력해 주세요.')
    if len(stem) > MAX_NAME:
        raise ValueError(f'이름은 {MAX_NAME}자까지 쓸 수 있습니다.')
    if any(char in BAD_CHARS for char in stem):
        raise ValueError('이름에 \\ / : * ? " < > | 는 쓸 수 없습니다.')
    if stem.split('.')[0].upper() in RESERVED:
        raise ValueError('Windows 가 예약한 이름이라 쓸 수 없습니다.')
    target = folder / (stem + path.suffix)
    if target.name == path.name:        # 🚨 Path 끼리 == 은 Windows 에서 대소문자를 무시한다
        return path
    # 대소문자만 바꾸는 것은 같은 파일이다 (Windows 는 대소문자를 가리지 않는다)
    if target.exists() and target.name.lower() != path.name.lower():
        raise FileExistsError(f'‘{target.name}’ 파일이 이미 있습니다. 다른 이름을 써 주세요.')
    path.rename(target)
    return target


class _FileOp(ctypes.Structure):
    _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT),
                ('pFrom', wintypes.LPCWSTR), ('pTo', wintypes.LPCWSTR),
                ('fFlags', wintypes.WORD), ('fAnyOperationsAborted', wintypes.BOOL),
                ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', wintypes.LPCWSTR)]


def recycle(paths: list[Path]) -> None:
    """휴지통으로 보낸다 — 잘못 지워도 되살릴 수 있게."""
    if not paths:
        return
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 4, 0x10, 0x40, 0x400
    # 여러 파일을 \0 으로 잇고 \0\0 으로 끝낸다. 문자열 안에 \0 이 있어 버퍼로 넘긴다
    names = ctypes.create_unicode_buffer('\0'.join(str(path) for path in paths) + '\0\0')
    operation = _FileOp(None, FO_DELETE, ctypes.cast(names, wintypes.LPCWSTR), None,
                        FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI, False, None, None)
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result or operation.fAnyOperationsAborted:
        raise OSError('파일을 휴지통으로 옮기지 못했습니다. 다른 프로그램이 열고 있는지 확인해 주세요.')
