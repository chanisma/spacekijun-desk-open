"""전역 단축키 — 어느 프로그램을 쓰고 있든 눌리면 알린다 (독 불러오기, 2026-10-12 요청).

Windows `RegisterHotKey` 는 **등록한 스레드**의 메시지 고리로 WM_HOTKEY 를 보낸다. 그래서 단축키마다
전용 스레드를 하나 두고 그 안에서 등록·대기·해제한다. 다른 프로그램이 이미 같은 조합을 쓰면
등록이 실패하므로, 그 사실을 돌려주어 설정에서 다른 조합을 고르게 한다.

🚨 Windows 함수는 이 모듈 전용 DLL 객체로 부른다 (core/dock_handle.py 참고).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
HOTKEY_ID = 0x5D0C

# 고를 수 있는 조합 — 키 이름 → (보조키, 가상 키, 화면에 보일 이름)
CHOICES = {
    'ctrl+alt+d': (MOD_CONTROL | MOD_ALT, 0x44, 'Ctrl + Alt + D'),
    'ctrl+shift+space': (MOD_CONTROL | MOD_SHIFT, 0x20, 'Ctrl + Shift + Space'),
    'ctrl+alt+space': (MOD_CONTROL | MOD_ALT, 0x20, 'Ctrl + Alt + Space'),
    'alt+q': (MOD_ALT, 0x51, 'Alt + Q'),
    'off': None,
}
DEFAULT = 'ctrl+alt+d'

_user32 = ctypes.WinDLL('user32', use_last_error=True)
_kernel32 = ctypes.WinDLL('kernel32')
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def label(combo: str) -> str:
    choice = CHOICES.get(combo)
    return choice[2] if choice else '사용 안 함'


class HotKey:
    """단축키 하나. `use(조합)` 으로 바꾸고, 눌리면 `on_press()` 를 (따로 스레드에서) 부른다."""

    def __init__(self, on_press, log=lambda *parts: None):
        self._on_press = on_press
        self._log = log
        self._lock = threading.Lock()
        self._thread = None
        self._thread_id = None
        self.combo = 'off'
        self.active = False              # 지금 등록되어 있나

    def use(self, combo: str) -> bool:
        """조합을 바꾼다. 등록에 성공했으면 True ('off' 는 늘 True)."""
        if combo not in CHOICES:
            raise ValueError('지원하지 않는 단축키입니다.')
        with self._lock:
            self._stop()
            self.combo, self.active = combo, False
            if CHOICES[combo] is None:
                return True
            ready, result = threading.Event(), {}
            self._thread = threading.Thread(target=self._loop, args=(combo, ready, result), daemon=True,
                                            name='desk-hotkey')
            self._thread.start()
            ready.wait(3)
            self.active = bool(result.get('ok'))
            return self.active

    def stop(self) -> None:
        with self._lock:
            self._stop()
            self.active = False

    def _stop(self) -> None:
        if self._thread and self._thread.is_alive() and self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = self._thread_id = None

    def _loop(self, combo, ready, result) -> None:
        modifiers, key, _ = CHOICES[combo]
        self._thread_id = _kernel32.GetCurrentThreadId()
        result['ok'] = bool(_user32.RegisterHotKey(None, HOTKEY_ID, modifiers | MOD_NOREPEAT, key))
        ready.set()
        if not result['ok']:
            return                        # 다른 프로그램이 이미 쓰고 있다
        try:
            message = wintypes.MSG()
            while _user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                    # 메시지 고리를 막지 않게 따로 돌린다
                    threading.Thread(target=self._press, daemon=True, name='desk-hotkey-press').start()
        finally:
            _user32.UnregisterHotKey(None, HOTKEY_ID)

    def _press(self) -> None:
        try:
            self._on_press()
        except Exception as exc:
            self._log('단축키로 독을 부르지 못했습니다:', exc)
