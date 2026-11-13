"""클립보드 기록 — 컴퓨터에서 복사한 것(글·그림·파일)을 모아 두고 다시 꺼내 쓰게 한다.

· **지켜보기**: 클립보드 순번(GetClipboardSequenceNumber)이 바뀌면 그때 한 번 읽는다. 0.5초마다
  숫자 하나만 보므로 가볍다. 복사한 프로그램이 다 쓰기를 잠깐 기다렸다 읽는다.
· **무엇을**: 파일(탐색기에서 복사) → 글 → 그림 순으로 하나를 고른다. 엑셀·한글처럼 글과 그림을
  함께 올리는 프로그램은 글로 담는다 — 대부분 붙여 넣고 싶은 것은 글이다.
· **안 담는 것**: 비밀번호 관리자 등이 '기록하지 말라'고 표시한 것 (Windows 약속:
  `ExcludeClipboardContentFromMonitorProcessing`, `CanIncludeInClipboardHistory`=0).
· **보관**: 목록(글 포함)은 DPAPI 로 암호화해 이 PC·이 계정만 읽게 한다(secretstore 와 같은 방식).
  그림은 PNG 파일로 둔다.
· 같은 것을 다시 복사하면 새로 쌓지 않고 맨 위로 올린다.

🚨 Windows 함수는 이 모듈 전용 DLL 객체로 부른다 — `ctypes.windll.*` 에 argtypes 를 걸면
pywebview 까지 깨진다 (core/dock_handle.py 참고).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from . import capture, secretstore

POLL = 0.5                 # 클립보드 순번을 보는 간격 (초)
SETTLE = 0.2               # 순번이 바뀐 뒤 복사한 프로그램이 다 쓰기를 기다리는 시간 (초)
MAX_ITEMS = 300            # 고정하지 않은 것은 이만큼만 남긴다 (오래된 것부터 지운다)
MAX_TEXT = 200_000         # 글 한 건의 최대 길이 (글자)
PREVIEW = 500              # 목록에 보이는 글 길이
MAX_FILES = 200            # 한 번에 복사한 파일 목록 상한
STORE = 'history.dat'

CF_UNICODETEXT, CF_HDROP, CF_DIB, CF_DIBV5 = 13, 15, 8, 17

_user32 = ctypes.WinDLL('user32', use_last_error=True)
_kernel32 = ctypes.WinDLL('kernel32')
_shell32 = ctypes.WinDLL('shell32')
_user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.RegisterClipboardFormatW.restype = wintypes.UINT
_user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalSize.restype = ctypes.c_size_t
_kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
_shell32.DragQueryFileW.restype = wintypes.UINT
_shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]


def sequence() -> int:
    return _user32.GetClipboardSequenceNumber()


def _open_clipboard(tries: int = 10) -> bool:
    """다른 프로그램이 클립보드를 쥐고 있으면 잠깐씩 기다렸다 다시 연다."""
    for _ in range(tries):
        if _user32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def _excluded() -> bool:
    """복사한 프로그램이 '기록하지 말라'고 표시했나 (비밀번호 관리자 등)."""
    if _user32.IsClipboardFormatAvailable(_user32.RegisterClipboardFormatW(
            'ExcludeClipboardContentFromMonitorProcessing')):
        return True
    allow = _user32.RegisterClipboardFormatW('CanIncludeInClipboardHistory')
    if _user32.IsClipboardFormatAvailable(allow):
        handle = _user32.GetClipboardData(allow)
        pointer = _kernel32.GlobalLock(handle) if handle else None
        if pointer:
            try:
                return ctypes.c_uint32.from_address(pointer).value == 0
            finally:
                _kernel32.GlobalUnlock(handle)
    return False


def read() -> tuple[str, object] | None:
    """지금 클립보드의 것 — ('files', [경로…]) · ('text', 글) · ('image', PIL 그림) · None."""
    if not _open_clipboard():
        return None
    image = False
    try:
        if _excluded():
            return None
        if _user32.IsClipboardFormatAvailable(CF_HDROP):
            drop = _user32.GetClipboardData(CF_HDROP)
            count = _shell32.DragQueryFileW(drop, 0xFFFFFFFF, None, 0) if drop else 0
            files = []
            for index in range(min(count, MAX_FILES)):
                size = _shell32.DragQueryFileW(drop, index, None, 0) + 1
                buffer = ctypes.create_unicode_buffer(size)
                _shell32.DragQueryFileW(drop, index, buffer, size)
                files.append(buffer.value)
            if files:
                return 'files', files
        if _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            handle = _user32.GetClipboardData(CF_UNICODETEXT)
            pointer = _kernel32.GlobalLock(handle) if handle else None
            if pointer:
                try:
                    chars = _kernel32.GlobalSize(handle) // 2
                    text = ctypes.wstring_at(pointer, chars).split('\0', 1)[0]
                finally:
                    _kernel32.GlobalUnlock(handle)
                if text.strip():
                    return 'text', text[:MAX_TEXT]
        image = bool(_user32.IsClipboardFormatAvailable(CF_DIB) or _user32.IsClipboardFormatAvailable(CF_DIBV5))
    finally:
        _user32.CloseClipboard()
    if image:
        picture = capture._clipboard_image()   # 그림은 PIL 이 읽는다 (클립보드를 스스로 연다)
        if picture is not None:
            return 'image', picture
    return None


def _fingerprint(kind: str, data) -> str:
    digest = hashlib.sha1(kind.encode())
    if kind == 'text':
        digest.update(data.encode('utf-8', 'surrogatepass'))
    elif kind == 'files':
        digest.update('\n'.join(data).encode('utf-8', 'surrogatepass'))
    else:
        digest.update(f'{data.size}{data.mode}'.encode())
        digest.update(data.tobytes())
    return digest.hexdigest()


class History:
    """모아 둔 것들. 새것이 앞. 여러 스레드에서 부르므로 잠가서 다룬다."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self._lock = threading.RLock()
        self.version = 0                 # 바뀔 때마다 오른다 — 화면이 같은 목록을 다시 받지 않게
        self.items = self._load()

    # ── 보관 ──
    def _load(self) -> list[dict]:
        try:
            raw = secretstore.decrypt((self.folder / STORE).read_bytes())
            items = json.loads(raw.decode('utf-8'))
            return [item for item in items if isinstance(item, dict) and item.get('id')]
        except (OSError, ValueError, secretstore.SecretError):
            return []

    def _save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        data = secretstore.encrypt(json.dumps(self.items, ensure_ascii=False).encode('utf-8'))
        temporary = self.folder / (STORE + '.tmp')
        temporary.write_bytes(data)
        os.replace(temporary, self.folder / STORE)

    def _changed(self) -> None:
        self.version += 1
        self._save()

    # ── 쌓기 ──
    def add(self, kind: str, data) -> dict:
        fingerprint = _fingerprint(kind, data)
        now = datetime.now().isoformat(timespec='seconds')
        with self._lock:
            for index, item in enumerate(self.items):
                if item.get('hash') == fingerprint:          # 같은 것 — 맨 위로만
                    item['time'] = now
                    self.items.insert(0, self.items.pop(index))
                    self._changed()
                    return item
            item = {'id': uuid.uuid4().hex, 'kind': kind, 'hash': fingerprint, 'time': now, 'pinned': False}
            if kind == 'text':
                item['text'] = data
            elif kind == 'files':
                item['files'] = list(data)
            else:
                self.folder.mkdir(parents=True, exist_ok=True)
                name = f'clip-{item["id"]}.png'
                picture = data if data.mode in ('RGB', 'RGBA') else data.convert('RGBA')
                picture.save(self.folder / name, 'PNG')
                item.update(image=name, width=data.width, height=data.height)
            self.items.insert(0, item)
            self._trim()
            self._changed()
            return item

    def _trim(self) -> None:
        loose = [item for item in self.items if not item.get('pinned')]
        for item in loose[MAX_ITEMS:]:
            self._forget(item)

    def _forget(self, item: dict) -> None:
        self.items.remove(item)
        if item.get('image'):
            try:
                (self.folder / item['image']).unlink()
            except OSError:
                pass

    # ── 꺼내기 ──
    def get(self, item_id) -> dict:
        with self._lock:
            for item in self.items:
                if item['id'] == item_id:
                    return item
        raise LookupError('그 기록을 찾을 수 없습니다. 이미 지웠을 수 있습니다.')

    def image_path(self, item: dict) -> Path:
        return self.folder / item['image']

    def listing(self, query: str = '') -> list[dict]:
        """화면에 보낼 목록 — 글은 앞부분만, 그림은 썸네일로."""
        needle = (query or '').strip().lower()
        with self._lock:
            items = list(self.items)
        rows = []
        for item in items:
            kind = item['kind']
            if needle:
                haystack = item.get('text') or '\n'.join(item.get('files') or [])
                if kind == 'image' or needle not in haystack.lower():
                    continue
            row = {key: item.get(key) for key in ('id', 'kind', 'time', 'pinned')}
            if kind == 'text':
                text = item['text']
                row.update(text=text[:PREVIEW], length=len(text))
            elif kind == 'files':
                row.update(files=[Path(path).name for path in item['files'][:5]], count=len(item['files']),
                           folder=str(Path(item['files'][0]).parent) if item['files'] else '')
            else:
                path = self.image_path(item)
                try:
                    _, _, thumb = capture._thumbnail(path, path.stat().st_mtime_ns)
                except (OSError, ValueError):
                    continue                                    # 그림 파일이 없어졌다
                row.update(thumb=thumb, width=item.get('width'), height=item.get('height'))
            rows.append(row)
        return rows

    def pin(self, item_id, pinned: bool) -> None:
        with self._lock:
            self.get(item_id)['pinned'] = bool(pinned)
            self._changed()

    def delete(self, item_id) -> None:
        with self._lock:
            self._forget(self.get(item_id))
            self._changed()

    def clear(self) -> int:
        """고정하지 않은 것을 모두 지운다. 지운 수."""
        with self._lock:
            loose = [item for item in self.items if not item.get('pinned')]
            for item in loose:
                self._forget(item)
            self._changed()
            return len(loose)


class Recorder:
    """클립보드를 지켜보다 바뀌면 History 에 담는다."""

    def __init__(self, history: History, log=lambda *parts: None):
        self.history = history
        self._log = log
        self._stop = threading.Event()
        self._thread = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name='desk-clipboard')
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        seen = sequence()                 # 켜기 전에 있던 것은 담지 않는다
        failed = False
        while not self._stop.wait(POLL):
            now = sequence()
            if now == seen:
                continue
            seen = now
            self._stop.wait(SETTLE)
            try:
                found = read()
                if found:
                    self.history.add(*found)
                failed = False
            except Exception as exc:
                if not failed:            # 같은 오류를 계속 쌓지 않는다
                    self._log('클립보드를 기록하지 못했습니다:', exc)
                failed = True
