"""에이전트의 화면 조작 (computer use) — 다른 앱의 창을 읽고 누르고 글자를 친다 (2026-10-25 요청, Orca 의 computer use 처럼).

에이전트는 중계(core/agent_bridge.py `/computer/*`)로 부르고, 앱마다 **사람이 허락한 뒤에만** 여기까지 온다.
Orca 의 Windows 판(runtime.ps1 — 라이선스 표시가 없어 코드는 가져오지 않았다)의 모양을 따랐다:
앱·창을 고르고 → 접근성 스냅숏(번호 매긴 요소) → 번호나 창 좌표로 click·type·paste·key·scroll·drag·set-value·action,
그리고 **하고 나면 새 스냅숏을 돌려준다** (에이전트가 결과를 따로 물으러 오지 않게). 같은 일을 Windows UI Automation —
.NET 의 System.Windows.Automation (pywebview 가 이미 쓰는 pythonnet 으로 부른다) — 과 user32 SendInput 으로 직접 한다.

  · 창은 hwnd 숫자로 가리킨다 (`apps` 가 알려 준다). 좌표는 **창 왼쪽 위 기준 실제 픽셀** — `screenshot` 그림의 픽셀과 같다.
    (그림을 줄였으면 scale 을 함께 알린다.) 화면 배율과 상관없게, 일하는 동안 이 스레드를 모니터별 DPI 인식으로 바꾼다.
  · 요소 번호는 그 에이전트가 그 창에서 읽은 마지막 스냅숏에서만 통한다.
  · 누르기는 요소의 동작(Invoke·Toggle·선택)을 먼저 쓰고, 안 되면 요소 가운데를 마우스로 누른다.

🚨 지키는 것
  · 이 프로그램(데스크)의 창과 막아 둔 앱(비밀번호 관리자·Windows 로그인·권한 확인 창)은 다루지 않는다
    — 에이전트가 허락 단추를 스스로 누르거나 비밀을 꺼내지 못하게.
  · 마우스로 누를 자리를 다른 창이 가리고 있으면 누르지 않는다 (가린 것이 데스크의 허락 창일 수도 있다).
  · 키보드 입력은 그 창이 실제로 맨 앞에 온 것을 확인한 뒤에만 보낸다.
  · 비밀번호·인증번호 같은 민감한 칸은 값을 가리고([redacted]) 글자를 넣지 않는다.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

STATE_LIMIT = (20, 800)        # 스냅숏이 늘어놓을 요소 수 범위
STATE_DEFAULT = 300
STATE_DEPTH = 40               # UI 트리를 내려갈 깊이
STATE_BUDGET = 8.0             # 스냅숏 한 번에 쓸 시간 (초) — 큰 앱에서 끝없이 걷지 않게
VALUE_LIMIT = 200              # 스냅숏에 보일 값·이름 길이
TEXT_LIMIT = 5000              # type·paste 한 번에 넣을 글자 수
TYPE_GAP = 0.004               # 글자 사이 쉬는 시간 (초)
SETTLE = 0.35                  # 하고 나서 새 스냅숏을 찍기 전에 기다리는 시간 (초) — 화면이 바뀌기를
SHOT_KEEP = 40                 # 남겨 둘 화면 사진 수
SHOT_EDGE = 1600               # 사진의 긴 변 상한 (픽셀) — 넘으면 줄이고 scale 을 알린다
FOREGROUND_WAIT = 1.5          # 창이 맨 앞에 오기를 기다리는 시간 (초)
FOCUS_SETTLE = 0.12            # 앞에 오거나 초점을 옮긴 뒤 글자를 치기 전에 쉬는 시간 (초)
# 다루지 않는 앱 — 프로세스 이름이나 창 제목에 이 조각이 있으면 (소문자로 견준다)
BLOCKED_APPS = ('1password', 'bitwarden', 'dashlane', 'lastpass', 'nordpass', 'proton pass', 'keepass', 'enpass',
                'consent.exe', 'credentialuibroker', 'logonui', 'lockapp')
# 민감한 칸 — 이름·자동화 id·종류·클래스에 이 말이 있으면 값을 가리고 입력하지 않는다
SENSITIVE = re.compile(r'password|passcode|passwd|secret|one-time code|verification code|otp|(^|[^a-z0-9])pin([^a-z0-9]|$)'
                       r'|비밀번호|암호|인증번호|인증 번호|보안코드|보안 코드|주민등록번호', re.IGNORECASE)

# 🚨 전용 DLL 객체로 부른다 — ctypes.windll 은 pywebview 와 함께 쓰므로 argtypes 를 걸면 그쪽이 깨진다 (desktop.py)
_user32 = ctypes.WinDLL('user32', use_last_error=True)
_gdi32 = ctypes.WinDLL('gdi32')
_kernel32 = ctypes.WinDLL('kernel32')
_dwmapi = ctypes.WinDLL('dwmapi')

ULONG_PTR = ctypes.c_size_t


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', ctypes.c_long), ('dy', ctypes.c_long), ('mouseData', wt.DWORD), ('dwFlags', wt.DWORD),
                ('time', wt.DWORD), ('dwExtraInfo', ULONG_PTR)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wt.WORD), ('wScan', wt.WORD), ('dwFlags', wt.DWORD), ('time', wt.DWORD), ('dwExtraInfo', ULONG_PTR)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wt.DWORD), ('wParamL', wt.WORD), ('wParamH', wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [('mi', _MOUSEINPUT), ('ki', _KEYBDINPUT), ('hi', _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [('type', wt.DWORD), ('u', _INPUTUNION)]


INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_EXTENDEDKEY = 0x2, 0x4, 0x1
MOUSE_FLAGS = {'left': (0x2, 0x4), 'right': (0x8, 0x10), 'middle': (0x20, 0x40)}
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x800, 0x1000
WHEEL_DELTA = 120
NOTCHES_PER_PAGE = 5           # scroll 의 pages 하나 = 바퀴 몇 칸

_user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
_user32.SendInput.restype = wt.UINT
_user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
_user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_user32.GetWindowTextLengthW.argtypes = [wt.HWND]
_user32.IsWindow.argtypes = [wt.HWND]
_user32.IsWindowVisible.argtypes = [wt.HWND]
_user32.IsIconic.argtypes = [wt.HWND]
_user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
_user32.GetWindow.restype = wt.HWND
_user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
_user32.GetAncestor.restype = wt.HWND
_user32.WindowFromPoint.argtypes = [wt.POINT]
_user32.WindowFromPoint.restype = wt.HWND
_user32.GetForegroundWindow.restype = wt.HWND
_user32.SetForegroundWindow.argtypes = [wt.HWND]
_user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
_user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
_user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
_user32.BringWindowToTop.argtypes = [wt.HWND]
_user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
_user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
_user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
_user32.GetWindowDC.argtypes = [wt.HWND]
_user32.GetWindowDC.restype = wt.HDC
_user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
_user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
_user32.VkKeyScanW.argtypes = [wt.WCHAR]
_user32.VkKeyScanW.restype = ctypes.c_short
_user32.OpenClipboard.argtypes = [wt.HWND]
_user32.GetClipboardData.argtypes = [wt.UINT]
_user32.GetClipboardData.restype = wt.HANDLE
_user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
_user32.SetClipboardData.restype = wt.HANDLE
_user32.IsClipboardFormatAvailable.argtypes = [wt.UINT]
_dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
_gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
_gdi32.CreateCompatibleDC.restype = wt.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
_gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
_gdi32.SelectObject.restype = wt.HGDIOBJ
_gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wt.HDC]
_gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
_kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_kernel32.OpenProcess.restype = wt.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
_kernel32.CloseHandle.argtypes = [wt.HANDLE]
_kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wt.HGLOBAL
_kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
_kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]

VK = {'enter': 0x0D, 'return': 0x0D, 'tab': 0x09, 'esc': 0x1B, 'escape': 0x1B, 'backspace': 0x08, 'delete': 0x2E, 'del': 0x2E,
      'insert': 0x2D, 'space': 0x20, 'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27, 'home': 0x24, 'end': 0x23,
      'pageup': 0x21, 'pagedown': 0x22, 'ctrl': 0x11, 'control': 0x11, 'cmdorctrl': 0x11, 'shift': 0x10, 'alt': 0x12,
      'win': 0x5B, 'menu': 0x5D, 'capslock': 0x14, 'hangul': 0x15, 'hanja': 0x19, **{f'f{n}': 0x6F + n for n in range(1, 13)}}
EXTENDED = {0x2E, 0x2D, 0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0x5B, 0x5D}
MODIFIER_KEYS = {0x11, 0x10, 0x12, 0x5B}
ACTIONS = ('invoke', 'toggle', 'select', 'expand', 'collapse', 'show')


class ComputerError(Exception):
    """에이전트에게 그대로 알릴 수 있는 잘못 (code 는 HTTP 상태)."""
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


# ── 화면 배율 ────────────────────────────────────────────
@contextmanager
def physical_pixels():
    """이 스레드를 모니터별 DPI 인식(V2)으로 — 좌표·그림이 배율과 상관없이 실제 픽셀이 되게."""
    try:
        set_context = _user32.SetThreadDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_void_p
        before = set_context(ctypes.c_void_p(-4))
    except AttributeError:
        before = None
    try:
        yield
    finally:
        if before:
            set_context(before)


# ── 창 ──────────────────────────────────────────────────
def window_pid(hwnd) -> int:
    pid = wt.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_title(hwnd) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def process_name(pid: int) -> str:
    handle = _kernel32.OpenProcess(0x1000, False, pid)         # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ''
    try:
        size = wt.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return Path(buffer.value).name
        return ''
    finally:
        _kernel32.CloseHandle(handle)


def window_rect(hwnd) -> tuple[int, int, int, int]:
    rect = wt.RECT()
    # DWM 이 그린 실제 테두리 (그림자 빼고) — 없으면 창 사각형
    if _dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def _cloaked(hwnd) -> bool:
    value = ctypes.c_int(0)
    _dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(value), ctypes.sizeof(value))   # DWMWA_CLOAKED
    return bool(value.value)


def top_windows() -> list[int]:
    """눈에 보이는 앱 창들 (도구 창·숨은 창·가려 둔 UWP 창은 뺀다). 앞에 있는 것부터."""
    found = []

    def visit(hwnd, _):
        if not _user32.IsWindowVisible(hwnd) or _user32.GetWindow(hwnd, 4) or _cloaked(hwnd):   # GW_OWNER
            return True
        if _user32.GetWindowLongW(hwnd, -20) & 0x80:                                    # WS_EX_TOOLWINDOW
            return True
        if _user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        found.append(int(hwnd))
        return True
    _user32.EnumWindows(WNDENUMPROC(visit), 0)
    return found


def blocked(app: str, title: str) -> bool:
    haystack = f'{app} {title}'.lower()
    return any(fragment in haystack for fragment in BLOCKED_APPS)


# ── 입력 ────────────────────────────────────────────────
def _send(inputs: list[_INPUT]):
    array = (_INPUT * len(inputs))(*inputs)
    sent = _user32.SendInput(len(inputs), array, ctypes.sizeof(_INPUT))
    if sent != len(inputs):
        raise ComputerError('입력을 보내지 못했습니다 (다른 프로그램이 막았거나 관리자 권한 창일 수 있습니다).', 409)


def _key(vk: int, up: bool = False) -> _INPUT:
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0)
    item = _INPUT(type=INPUT_KEYBOARD)
    item.u.ki = _KEYBDINPUT(vk, _user32.MapVirtualKeyW(vk, 0), flags, 0, 0)
    return item


def _unicode(unit: int, up: bool = False) -> _INPUT:
    item = _INPUT(type=INPUT_KEYBOARD)
    item.u.ki = _KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0), 0, 0)
    return item


def parse_keys(combo, allow_plain_modifier: bool = True) -> list[int]:
    """'ctrl+shift+s' · 'Enter' · 'alt+F4' · 'CmdOrCtrl+A' → 가상 키 목록 (수식 키가 앞)."""
    if not isinstance(combo, str) or not combo.strip() or len(combo) > 60:
        raise ComputerError('keys 는 "Enter", "ctrl+s", "alt+tab" 같은 글이어야 합니다.')
    keys = []
    for part in [part.strip().lower() for part in combo.replace(' ', '').split('+')]:
        if part in VK:
            keys.append(VK[part])
        elif len(part) == 1 and (part.isalnum() or part in '-=[];\',./`\\'):
            scan = _user32.VkKeyScanW(part)
            if scan == -1:
                raise ComputerError(f'모르는 키: {part}')
            keys.append(scan & 0xFF)
        else:
            raise ComputerError(f'모르는 키: {part} (쓸 수 있는 이름: {", ".join(sorted(VK))}, 글자·숫자 하나)')
    if len(keys) > 1 and all(key in MODIFIER_KEYS for key in keys):
        raise ComputerError('수식 키(ctrl·shift·alt) 뒤에 누를 키가 있어야 합니다.')
    if not allow_plain_modifier and any(key not in MODIFIER_KEYS for key in keys):
        raise ComputerError('modifiers 에는 ctrl·shift·alt·win 만 씁니다.')
    return keys


def press_keys(keys: list[int]):
    _send([_key(key) for key in keys] + [_key(key, up=True) for key in reversed(keys)])


def type_text(text: str):
    for char in text:
        if char == '\n':
            press_keys([0x0D])
        elif char == '\t':
            press_keys([0x09])
        elif char == '\r':
            continue
        else:
            units = char.encode('utf-16-le')
            codes = [int.from_bytes(units[i:i + 2], 'little') for i in range(0, len(units), 2)]
            _send([_unicode(code) for code in codes] + [_unicode(code, up=True) for code in codes])
        time.sleep(TYPE_GAP)


def _mouse(flags: int, data: int = 0) -> _INPUT:
    item = _INPUT(type=INPUT_MOUSE)
    item.u.mi = _MOUSEINPUT(0, 0, ctypes.c_ulong(data & 0xFFFFFFFF).value, flags, 0, 0)
    return item


def mouse_click(x: int, y: int, button: str = 'left', count: int = 1, modifiers: list[int] = ()):
    down, up = MOUSE_FLAGS[button]
    if not _user32.SetCursorPos(x, y):
        raise ComputerError('마우스를 옮기지 못했습니다.', 409)
    time.sleep(0.03)
    if modifiers:
        _send([_key(key) for key in modifiers])
    try:
        for index in range(count):
            _send([_mouse(down), _mouse(up)])
            if index + 1 < count:
                time.sleep(0.04)
    finally:
        if modifiers:
            _send([_key(key, up=True) for key in reversed(modifiers)])


def mouse_drag(start: tuple[int, int], end: tuple[int, int], steps: int = 12):
    _user32.SetCursorPos(*start)
    time.sleep(0.03)
    _send([_mouse(MOUSE_FLAGS['left'][0])])
    try:
        for step in range(1, steps + 1):
            _user32.SetCursorPos(round(start[0] + (end[0] - start[0]) * step / steps),
                                 round(start[1] + (end[1] - start[1]) * step / steps))
            time.sleep(0.02)
    finally:
        _send([_mouse(MOUSE_FLAGS['left'][1])])


def mouse_wheel(x: int, y: int, notches: int, horizontal: bool = False):
    _user32.SetCursorPos(x, y)
    time.sleep(0.03)
    _send([_mouse(MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, notches * WHEEL_DELTA)])


# ── 클립보드 (paste) ────────────────────────────────────
CF_UNICODETEXT = 13


def _open_clipboard():
    for _ in range(20):
        if _user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise ComputerError('클립보드를 열지 못했습니다 (다른 프로그램이 쓰는 중).', 409)


def clipboard_text() -> str | None:
    _open_clipboard()
    try:
        if not _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        handle = _user32.GetClipboardData(CF_UNICODETEXT)
        pointer = _kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()


def set_clipboard_text(text: str):
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = _kernel32.GlobalAlloc(0x0002, size)                  # GMEM_MOVEABLE
    pointer = _kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, size)
    _kernel32.GlobalUnlock(handle)
    _open_clipboard()
    try:
        _user32.EmptyClipboard()
        if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
            _kernel32.GlobalFree(handle)
            raise ComputerError('클립보드에 넣지 못했습니다.', 409)
    finally:
        _user32.CloseClipboard()


# ── UI Automation (.NET) ────────────────────────────────
_uia = None
_uia_lock = threading.Lock()


def uia():
    """System.Windows.Automation — 처음 부를 때 한 번 싣는다 (pythonnet)."""
    global _uia
    with _uia_lock:
        if _uia is None:
            import clr
            for name in ('UIAutomationClient', 'UIAutomationTypes'):
                clr.AddReference(f'{name}, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35')
            import System.Windows.Automation as automation
            _uia = automation
        return _uia


def _pattern(element, pattern):
    try:
        return element.GetCurrentPattern(pattern)
    except Exception:
        return None


def sensitive(element) -> bool:
    """비밀번호·인증번호 같은 칸인가 (Orca 와 같은 생각 — 이름·id·종류·클래스를 함께 본다)."""
    try:
        current = element.Current
        if current.IsPassword:
            return True
        haystack = ' '.join(str(part or '') for part in (current.LocalizedControlType, current.Name,
                                                          current.AutomationId, current.ClassName))
        return bool(SENSITIVE.search(haystack))
    except Exception:
        return False


def _clip(text: str, limit: int = VALUE_LIMIT) -> str:
    text = ' '.join(str(text or '').split())
    return text[:limit] + ('…' if len(text) > limit else '')


def _describe(element, origin) -> dict | None:
    a = uia()
    try:
        current = element.Current
        rect = current.BoundingRectangle
        info = {'role': str(current.ControlType.ProgrammaticName).replace('ControlType.', ''),
                'name': _clip(current.Name), 'enabled': bool(current.IsEnabled), 'offscreen': bool(current.IsOffscreen),
                'focus': bool(current.HasKeyboardFocus), 'secret': sensitive(element), 'actions': []}
        if not rect.IsEmpty and rect.Width > 0 and rect.Height > 0:
            info['box'] = (int(rect.X) - origin[0], int(rect.Y) - origin[1], int(rect.Width), int(rect.Height))
        value = _pattern(element, a.ValuePattern.Pattern)
        if value is not None:
            info['value'] = '[redacted]' if info['secret'] else _clip(value.Current.Value)
            if not value.Current.IsReadOnly:
                info['actions'].append('set-value')
        toggle = _pattern(element, a.TogglePattern.Pattern)
        if toggle is not None:
            info['checked'] = str(toggle.Current.ToggleState).lower()
            info['actions'].append('toggle')
        selection = _pattern(element, a.SelectionItemPattern.Pattern)
        if selection is not None:
            info['selected'] = bool(selection.Current.IsSelected)
            info['actions'].append('select')
        expand = _pattern(element, a.ExpandCollapsePattern.Pattern)
        if expand is not None:
            state = str(expand.Current.ExpandCollapseState).lower()
            info['expanded'] = state
            info['actions'].append('collapse' if state == 'expanded' else 'expand')
        if _pattern(element, a.ScrollPattern.Pattern) is not None:
            info['actions'].append('scroll')
        return info
    except Exception:
        return None


def format_line(index: int, info: dict, depth: int) -> str:
    parts = [f'{"  " * min(depth, 12)}[{index}] {info["role"]}']
    if info['name']:
        parts.append(f'"{info["name"]}"')
    if info.get('value') not in (None, ''):
        parts.append(f'value="{info["value"]}"')
    for key in ('checked', 'expanded'):
        if info.get(key):
            parts.append(f'{key}={info[key]}')
    if info.get('selected'):
        parts.append('selected')
    if info['secret']:
        parts.append('(sensitive)')
    if 'box' in info:
        x, y, w, h = info['box']
        parts.append(f'@({x},{y} {w}x{h})')
    if info['focus']:
        parts.append('focused')
    if not info['enabled']:
        parts.append('disabled')
    if info['offscreen']:
        parts.append('offscreen')
    if info['actions']:
        parts.append('{' + ','.join(info['actions']) + '}')
    return ' '.join(parts)


class Computer:
    """에이전트의 화면 조작. own_pid 의 창(데스크)과 막아 둔 앱은 다루지 않는다."""

    def __init__(self, own_pid: int, shots_dir: Path):
        self.own_pid = own_pid
        self.shots_dir = Path(shots_dir)
        self._snapshots: dict[tuple, list] = {}     # (누가, 창) → 마지막 스냅숏의 요소들
        self._lock = threading.RLock()              # 입력은 한 번에 하나 — 두 에이전트의 클릭·글자가 섞이지 않게

    # ── 창 고르기 ──────────────────────────────────────
    def apps(self) -> list[dict]:
        with physical_pixels():
            rows = []
            for hwnd in top_windows():
                pid = window_pid(hwnd)
                if pid == self.own_pid:
                    continue
                app, title = process_name(pid) or '?', window_title(hwnd)[:120]
                x, y, w, h = window_rect(hwnd)
                rows.append({'window': hwnd, 'pid': pid, 'app': app, 'title': title, 'minimized': bool(_user32.IsIconic(hwnd)),
                             'size': (w, h), 'blocked': blocked(app, title)})
            return rows

    def window(self, value) -> dict:
        """에이전트가 준 창 번호를 확인한다 — 있는 창이고, 데스크 것도 막아 둔 앱도 아니어야 한다."""
        try:
            hwnd = int(value)
        except (TypeError, ValueError):
            raise ComputerError('window 에는 /computer/apps 가 알려 준 창 번호를 주세요.') from None
        if hwnd <= 0 or not _user32.IsWindow(hwnd):
            raise ComputerError('그 창이 없습니다. /computer/apps 로 다시 보세요.', 404)
        root = int(_user32.GetAncestor(hwnd, 2) or hwnd)               # GA_ROOT
        pid = window_pid(root)
        if pid == self.own_pid:
            raise ComputerError('데스크의 창은 다룰 수 없습니다.', 403)
        app, title = process_name(pid) or '?', window_title(root)[:120]
        if blocked(app, title):
            raise ComputerError(f'{app} 은(는) 막아 둔 앱입니다 (비밀번호 관리자·로그인·권한 확인 창).', 403)
        return {'window': root, 'pid': pid, 'app': app, 'title': title}

    # ── 보기 ───────────────────────────────────────────
    def state(self, who: str, hwnd: int, limit: int = STATE_DEFAULT) -> str:
        a = uia()
        try:
            limit = max(STATE_LIMIT[0], min(STATE_LIMIT[1], int(limit)))
        except (TypeError, ValueError):
            limit = STATE_DEFAULT
        with physical_pixels():
            origin = window_rect(hwnd)[:2]
            try:
                from System import IntPtr
                root = a.AutomationElement.FromHandle(IntPtr(hwnd))
            except Exception as exc:
                raise ComputerError(f'창의 UI 를 읽지 못했습니다: {exc}', 409) from None
            walker = a.TreeWalker.ControlViewWalker
            elements, lines, deadline, cut = [], [], time.monotonic() + STATE_BUDGET, ''
            stack = [(root, 0)]
            while stack:
                if len(elements) >= limit:
                    cut = f'... truncated: first {limit} elements shown (ask with a bigger limit, up to {STATE_LIMIT[1]})'
                    break
                if time.monotonic() > deadline:
                    cut = '... truncated: the window has too many elements to read in time'
                    break
                element, depth = stack.pop()
                info = _describe(element, origin)
                if info is not None:
                    lines.append(format_line(len(elements), info, depth))
                    elements.append(element)
                if depth >= STATE_DEPTH:
                    continue
                children = []
                try:
                    child = walker.GetFirstChild(element)
                    while child is not None and len(children) < 400:
                        children.append(child)
                        child = walker.GetNextSibling(child)
                except Exception:
                    pass
                stack.extend((child, depth + 1) for child in reversed(children))
            x, y, w, h = window_rect(hwnd)
        with self._lock:
            self._snapshots[(who, hwnd)] = elements
        head = (f'window {hwnd} "{window_title(hwnd)[:120]}" — {w}x{h} px — {len(elements)} elements '
                '(coordinates are pixels from the window top-left; {actions} lists what action can do)')
        return '\n'.join([head, *lines] + ([cut] if cut else [])) + '\n'

    def element(self, who: str, hwnd: int, index):
        with self._lock:
            elements = self._snapshots.get((who, hwnd))
        if elements is None:
            raise ComputerError('먼저 /computer/state 로 이 창의 요소 번호를 읽으세요.', 409)
        try:
            return elements[int(index)]
        except (TypeError, ValueError, IndexError):
            raise ComputerError('그 번호의 요소가 없습니다. /computer/state 를 다시 읽으세요.', 404) from None

    def screenshot(self, who: str, hwnd: int) -> dict:
        """창 사진을 파일로 — {'path', 'width', 'height', 'scale'}. scale 이 1 보다 작으면 그림 좌표 ÷ scale = 창 좌표."""
        from PIL import Image
        with physical_pixels():
            x, y, w, h = window_rect(hwnd)
            if w <= 0 or h <= 0 or _user32.IsIconic(hwnd):
                raise ComputerError('최소화된 창은 찍을 수 없습니다. 먼저 창을 보이게 해 주세요.', 409)
            image = self._print_window(hwnd, w, h)
            if image is None:                                          # PrintWindow 를 못 하는 창 — 화면에서 그 자리를 찍는다
                from PIL import ImageGrab
                image = ImageGrab.grab((x, y, x + w, y + h), all_screens=True)
        scale = min(1.0, SHOT_EDGE / max(image.size))
        if scale < 1.0:
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS)
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        path = self.shots_dir / f'{who}-{time.strftime("%Y%m%d-%H%M%S")}-{hwnd}.png'
        image.save(path)
        for old in sorted(self.shots_dir.glob('*.png'), key=lambda p: p.stat().st_mtime)[:-SHOT_KEEP]:
            try:
                old.unlink()
            except OSError:
                pass
        return {'path': str(path), 'width': image.width, 'height': image.height, 'scale': round(scale, 4)}

    @staticmethod
    def _print_window(hwnd, w, h):
        from PIL import Image
        window_dc = _user32.GetWindowDC(hwnd)
        memory = _gdi32.CreateCompatibleDC(window_dc)
        bitmap = _gdi32.CreateCompatibleBitmap(window_dc, w, h)
        old = _gdi32.SelectObject(memory, bitmap)
        try:
            if not _user32.PrintWindow(hwnd, memory, 2):              # PW_RENDERFULLCONTENT
                return None
            header = (ctypes.c_uint32 * 10)(40, w, ctypes.c_uint32(-h & 0xFFFFFFFF).value, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
            buffer = ctypes.create_string_buffer(w * h * 4)
            if not _gdi32.GetDIBits(memory, bitmap, 0, h, buffer, header, 0):
                return None
            image = Image.frombuffer('RGBA', (w, h), buffer, 'raw', 'BGRA', 0, 1).convert('RGB')
            return image if image.getbbox() else None                 # 온통 검으면 못 찍은 것
        finally:
            _gdi32.SelectObject(memory, old)
            _gdi32.DeleteObject(bitmap)
            _gdi32.DeleteDC(memory)
            _user32.ReleaseDC(hwnd, window_dc)

    # ── 앞으로 · 가림 확인 ─────────────────────────────
    def bring_front(self, hwnd: int):
        """창을 맨 앞으로. Windows 는 앞 창이 아닌 프로그램이 다른 창을 올리지 못하게 막는다 — 지금 앞 창의 입력 큐에
        잠깐 붙어서 올린다. 그래도 안 되면 Alt 를 눌렀다 떼는 수(앞 창의 메뉴 막대가 켜질 수 있어 마지막에만)."""
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, 9)                                # SW_RESTORE
        if self._front(hwnd):
            return
        front = _user32.GetForegroundWindow()
        mine = _kernel32.GetCurrentThreadId()
        theirs = _user32.GetWindowThreadProcessId(front, None) if front else 0
        _user32.PeekMessageW(ctypes.byref(wt.MSG()), None, 0, 0, 0)    # 이 스레드에 메시지 큐가 있어야 붙을 수 있다
        attached = bool(theirs and theirs != mine and _user32.AttachThreadInput(mine, theirs, True))
        try:
            _user32.BringWindowToTop(hwnd)
            _user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                _user32.AttachThreadInput(mine, theirs, False)
        if self._wait_front(hwnd, FOREGROUND_WAIT / 2):
            return
        press_keys([0x12])
        _user32.SetForegroundWindow(hwnd)
        if self._wait_front(hwnd, FOREGROUND_WAIT):
            return
        raise ComputerError('그 창을 맨 앞으로 가져오지 못했습니다. 사람이 그 창을 한 번 눌러 준 뒤 다시 하세요.', 409)

    def _wait_front(self, hwnd: int, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._front(hwnd):
                time.sleep(FOCUS_SETTLE)                                # 앞에 왔어도 키보드 초점이 옮겨 가는 데 잠깐 걸린다
                return True
            time.sleep(0.03)
        return False

    @staticmethod
    def _front(hwnd: int) -> bool:
        front = _user32.GetForegroundWindow()
        return bool(front) and int(_user32.GetAncestor(front, 2) or front) == hwnd

    def _still_front(self, hwnd: int):
        if not self._front(hwnd):
            raise ComputerError('그 창이 맨 앞이 아니어서 입력을 보내지 않았습니다.', 409)

    def check_point(self, hwnd: int, x: int, y: int):
        hit = _user32.WindowFromPoint(wt.POINT(x, y))
        root = _user32.GetAncestor(hit, 2) if hit else None
        if not root or window_pid(root) != window_pid(hwnd):
            other = window_title(root)[:60] if root else '?'
            raise ComputerError(f'그 자리를 다른 창({other})이 가리고 있어 누르지 않았습니다.', 409)

    # ── 자리 ───────────────────────────────────────────
    def point(self, who: str, hwnd: int, payload: dict, prefix: str = '') -> tuple[int, int, object]:
        """{prefix}element 번호나 창 기준 {prefix}x·{prefix}y 로 화면 좌표를 구한다 (요소면 그 가운데)."""
        origin = window_rect(hwnd)[:2]
        if payload.get(f'{prefix}element') is not None:
            element = self.element(who, hwnd, payload[f'{prefix}element'])
            try:
                rect = element.Current.BoundingRectangle
            except Exception:
                raise ComputerError('그 요소가 사라졌습니다. /computer/state 를 다시 읽으세요.', 409) from None
            if rect.IsEmpty or rect.Width <= 0:
                raise ComputerError('그 요소는 화면에 보이지 않습니다 (offscreen). 스크롤하거나 action show 를 쓰세요.', 409)
            return int(rect.X + rect.Width / 2), int(rect.Y + rect.Height / 2), element
        try:
            x, y = int(payload[f'{prefix}x']), int(payload[f'{prefix}y'])
        except (KeyError, TypeError, ValueError):
            raise ComputerError(f'{prefix}element 번호나 {prefix}x·{prefix}y 좌표(창 왼쪽 위 기준 픽셀)를 주세요.') from None
        _, _, w, h = window_rect(hwnd)
        if not (0 <= x < w and 0 <= y < h):
            raise ComputerError(f'좌표가 창 밖입니다 (창 크기 {w}x{h}).')
        return origin[0] + x, origin[1] + y, None

    # ── 하기 ───────────────────────────────────────────
    def click(self, who: str, hwnd: int, payload: dict) -> str:
        button = payload.get('button') or 'left'
        if button not in MOUSE_FLAGS:
            raise ComputerError('button 은 left · right · middle 가운데 하나입니다.')
        try:
            count = max(1, min(3, int(payload.get('count') or 1)))
        except (TypeError, ValueError):
            raise ComputerError('count 는 1~3 입니다.') from None
        modifiers = parse_keys(payload['modifiers'], allow_plain_modifier=False) if payload.get('modifiers') else []
        with self._lock, physical_pixels():
            x, y, element = self.point(who, hwnd, payload)
            if element is not None and button == 'left' and count == 1 and not modifiers and not payload.get('mouse'):
                done = self._primary(element)
                if done:
                    return f'clicked element {payload["element"]} ({done})'
            self.bring_front(hwnd)
            self.check_point(hwnd, x, y)
            mouse_click(x, y, button, count, modifiers)
        return f'{button} click x{count} at window ({x - window_rect(hwnd)[0]},{y - window_rect(hwnd)[1]})'

    def _primary(self, element) -> str:
        """요소의 기본 동작 — 마우스를 쓰지 않아 다른 창에 가려져도 된다. 못 하면 빈 글."""
        a = uia()
        for name, pattern, act in (('invoke', a.InvokePattern.Pattern, lambda p: p.Invoke()),
                                   ('toggle', a.TogglePattern.Pattern, lambda p: p.Toggle()),
                                   ('select', a.SelectionItemPattern.Pattern, lambda p: p.Select())):
            found = _pattern(element, pattern)
            if found is not None:
                try:
                    act(found)
                    return name
                except Exception:
                    return ''                                           # 동작이 거절됐다 — 마우스로
        return ''

    def action(self, who: str, hwnd: int, payload: dict) -> str:
        """요소의 접근성 동작 — invoke · toggle · select · expand · collapse · show(화면에 보이게 스크롤)."""
        a = uia()
        name = payload.get('action')
        if name not in ACTIONS:
            raise ComputerError(f'action 은 {", ".join(ACTIONS)} 가운데 하나입니다.')
        table = {'invoke': (a.InvokePattern.Pattern, lambda p: p.Invoke()),
                 'toggle': (a.TogglePattern.Pattern, lambda p: p.Toggle()),
                 'select': (a.SelectionItemPattern.Pattern, lambda p: p.Select()),
                 'expand': (a.ExpandCollapsePattern.Pattern, lambda p: p.Expand()),
                 'collapse': (a.ExpandCollapsePattern.Pattern, lambda p: p.Collapse()),
                 'show': (a.ScrollItemPattern.Pattern, lambda p: p.ScrollIntoView())}
        with self._lock, physical_pixels():
            element = self.element(who, hwnd, payload.get('element'))
            pattern, act = table[name]
            found = _pattern(element, pattern)
            if found is None:
                raise ComputerError(f'그 요소는 {name} 을(를) 할 수 없습니다. 스냅숏의 {{…}} 에 있는 동작만 됩니다.', 409)
            try:
                act(found)
            except Exception as exc:
                raise ComputerError(f'{name} 을(를) 하지 못했습니다: {exc}', 409) from None
        return f'{name} element {payload.get("element")}'

    def _focus(self, who: str, hwnd: int, payload: dict):
        """글자를 넣을 자리 — element 를 주면 그 요소에 초점. 민감한 칸이면 거절."""
        a = uia()
        if payload.get('element') is not None:
            element = self.element(who, hwnd, payload['element'])
            self._refuse_secret(element)
            self.bring_front(hwnd)
            try:
                element.SetFocus()
            except Exception:
                x, y, _ = self.point(who, hwnd, payload)
                self.check_point(hwnd, x, y)
                mouse_click(x, y)
            # 초점이 실제로 그 요소에 올 때까지 — 오기 전에 친 글자는 사라진다 (2026-10-25 시험: 앞 글자 9개가 빠졌다)
            deadline = time.monotonic() + FOREGROUND_WAIT
            while time.monotonic() < deadline:
                try:
                    if element.Current.HasKeyboardFocus:
                        break
                except Exception:
                    break
                time.sleep(0.03)
            time.sleep(FOCUS_SETTLE)
        else:
            self.bring_front(hwnd)
        try:
            focused = a.AutomationElement.FocusedElement
        except Exception:
            focused = None
        if focused is not None:
            self._refuse_secret(focused)
        self._still_front(hwnd)

    def type(self, who: str, hwnd: int, payload: dict) -> str:
        text = self._text(payload.get('text'))
        with self._lock, physical_pixels():
            self._focus(who, hwnd, payload)
            type_text(text)
        return f'typed {len(text)} characters'

    def paste(self, who: str, hwnd: int, payload: dict) -> str:
        """클립보드로 붙여 넣는다 — 긴 글·한글 IME 가 끼어드는 앱에 낫다. 원래 클립보드 글은 되돌려 놓는다."""
        text = self._text(payload.get('text'))
        with self._lock, physical_pixels():
            self._focus(who, hwnd, payload)
            before = clipboard_text()
            set_clipboard_text(text)
            try:
                self._still_front(hwnd)
                press_keys(parse_keys('ctrl+v'))
                time.sleep(0.25)                                         # 앱이 클립보드를 읽을 틈
            finally:
                if before is not None:
                    set_clipboard_text(before)
        return f'pasted {len(text)} characters'

    def keys(self, who: str, hwnd: int, payload: dict) -> str:
        keys = parse_keys(payload.get('keys'))
        with self._lock, physical_pixels():
            self.bring_front(hwnd)
            self._still_front(hwnd)
            press_keys(keys)
        return f'pressed {payload.get("keys")}'

    def scroll(self, who: str, hwnd: int, payload: dict) -> str:
        direction = payload.get('direction') or 'down'
        if direction not in ('up', 'down', 'left', 'right'):
            raise ComputerError('direction 은 up · down · left · right 가운데 하나입니다.')
        try:
            pages = max(0.2, min(10.0, float(payload.get('pages') or 1)))
        except (TypeError, ValueError):
            raise ComputerError('pages 는 숫자입니다.') from None
        notches = max(1, round(pages * NOTCHES_PER_PAGE)) * (1 if direction in ('up', 'right') else -1)
        with self._lock, physical_pixels():
            if payload.get('element') is None and payload.get('x') is None:
                _, _, w, h = window_rect(hwnd)
                payload = {**payload, 'x': w // 2, 'y': h // 2}
            x, y, _ = self.point(who, hwnd, payload)
            self.bring_front(hwnd)
            self.check_point(hwnd, x, y)
            mouse_wheel(x, y, notches, horizontal=direction in ('left', 'right'))
        return f'scrolled {direction} {pages:g} page(s)'

    def drag(self, who: str, hwnd: int, payload: dict) -> str:
        with self._lock, physical_pixels():
            start = self.point(who, hwnd, payload, 'from_')[:2]
            end = self.point(who, hwnd, payload, 'to_')[:2]
            self.bring_front(hwnd)
            self.check_point(hwnd, *start)
            self.check_point(hwnd, *end)
            mouse_drag(start, end)
        return 'dragged'

    def set_value(self, who: str, hwnd: int, payload: dict) -> str:
        value = payload.get('value')
        if not isinstance(value, str) or len(value) > TEXT_LIMIT:
            raise ComputerError('value 에 넣을 글을 주세요.')
        a = uia()
        with self._lock, physical_pixels():
            element = self.element(who, hwnd, payload.get('element'))
            self._refuse_secret(element)
            pattern = _pattern(element, a.ValuePattern.Pattern)
            if pattern is None or pattern.Current.IsReadOnly:
                raise ComputerError('그 요소는 값을 바꿀 수 없습니다. click 으로 고른 뒤 type 을 쓰세요.', 409)
            pattern.SetValue(value)
        return f'set value of element {payload.get("element")}'

    @staticmethod
    def _text(text) -> str:
        if not isinstance(text, str) or not text:
            raise ComputerError('text 에 넣을 글자를 주세요.')
        if len(text) > TEXT_LIMIT:
            raise ComputerError(f'한 번에 {TEXT_LIMIT}자까지 넣습니다.', 413)
        return text

    @staticmethod
    def _refuse_secret(element):
        if sensitive(element):
            raise ComputerError('비밀번호·인증번호 같은 칸에는 글자를 넣지 않습니다. 사람에게 직접 넣어 달라고 하세요.', 403)

    def settle(self):
        time.sleep(SETTLE)

    def forget(self, who: str | None = None):
        """스냅숏 기억을 지운다 (에이전트를 닫거나 모두 멈출 때)."""
        with self._lock:
            for key in [key for key in self._snapshots if who is None or key[0] == who]:
                del self._snapshots[key]

    def clear_shots(self):
        for path in self.shots_dir.glob('*.png') if self.shots_dir.is_dir() else []:
            try:
                path.unlink()
            except OSError:
                pass
