"""독 손잡이 — 독 판의 화면 끝 쪽 바로 바깥에 늘 떠 있는 작은 줄. 마우스를 올리면 독을 앞으로 부른다.

독은 항상 위가 아니다(2026-10-11 요청). 다른 창에 가려지면 다시 찾기 어려우므로, 독 자리에
아이폰 홈 막대 같은 줄을 **항상 위로** 둔다. 독이 보일 때는 판 바로 아래(또는 옆)의 손잡이로,
가려졌을 때는 그 자리를 알려 주는 표시로 쓰인다.

· 줄은 WebView·WinForms 없이 Win32 창 하나다 — 작고 가볍고, 건 스타일이 바뀌지 않는다.
  포커스를 가져가지 않는다.
· 누르지 않아도 된다 — 잠깐(HOVER_MS) 머무르면 부른다 (2026-10-22 요청). 줄이 독과 화면 끝 사이,
  작업 표시줄로 가는 길목에 있어 스치기만 해도 부르면 성가시다. 한 번 들어와 부르면 나갔다 다시 들어올
  때까지는 또 부르지 않는다 — 독이 앞으로 오면 줄이 커서 아래에 다시 뜨기 때문이다. 눌러도 부른다.
· 모든 좌표는 실제 픽셀이다. 부르는 쪽(desktop.py)이 독 창의 배율을 곱해 넘긴다.

🚨 Windows 함수는 **이 모듈 전용 DLL 객체**로 부른다. `ctypes.windll.user32` 는 프로세스가 함께
쓰는 객체라, 거기에 argtypes 를 걸면 pywebview 의 창 옮기기(`SetWindowPos` 에 None 을 넘긴다)
까지 깨진다 (2026-10-11 사용자 보고 — 독을 끌어도 창이 움직이지 않았다).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

LENGTH, THICK, GAP = 120, 6, 1       # 줄 길이·두께·판과의 틈 (논리 픽셀)
IDLE = (0x6B, 0x72, 0x80)            # 평소 줄 색
OPACITY = 0.85                       # 줄 불투명도 (만들 때 한 번만 정한다)
HOVER = (0x4F, 0x46, 0xE5)           # 가리켰을 때 — 데스크 강조색
HOVER_MS = 150                       # 이만큼 머무르면 독을 부른다 (스쳐 지나가는 것은 무시)
TITLE = '스페이스기전 독 손잡이'

GWL_EXSTYLE, GWLP_WNDPROC = -20, -4
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x8, 0x80, 0x08000000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4

_user32 = ctypes.WinDLL('user32')
_gdi32 = ctypes.WinDLL('gdi32')
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_uint]
_user32.SetWindowRgn.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
_gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
HWND_TOPMOST = wintypes.HWND(-1)


def line_rect(anchor: str, shelf: tuple[int, int, int, int], scale: float) -> tuple[int, int, int, int]:
    """줄의 자리 (x, y, 너비, 높이). shelf 는 독 판의 화면 사각형 (왼, 위, 오른, 아래).
    판의 화면 끝 쪽 바로 바깥 — 아래에 붙은 독이면 판 아래, 왼쪽에 붙은 독이면 판 왼쪽."""
    left, top, right, bottom = shelf
    length, thick, gap = round(LENGTH * scale), round(THICK * scale), round(GAP * scale)
    if anchor in ('left', 'right'):
        y = (top + bottom) // 2 - length // 2
        x = left - gap - thick if anchor == 'left' else right + gap
        return x, y, thick, length
    x = (left + right) // 2 - length // 2
    y = top - gap - thick if anchor == 'top' else bottom + gap
    return x, y, length, thick


class _PaintStruct(ctypes.Structure):
    _fields_ = [('hdc', wintypes.HDC), ('fErase', wintypes.BOOL), ('rcPaint', wintypes.RECT),
                ('fRestore', wintypes.BOOL), ('fIncUpdate', wintypes.BOOL), ('rgbReserved', ctypes.c_byte * 32)]


class _TrackMouse(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('hwndTrack', wintypes.HWND), ('dwHoverTime', wintypes.DWORD)]


_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class _WndClass(ctypes.Structure):
    _fields_ = [('style', wintypes.UINT), ('lpfnWndProc', _WNDPROC), ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int), ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HBRUSH),
                ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR)]


_kernel32 = ctypes.WinDLL('kernel32')
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_user32.DefWindowProcW.restype = _LRESULT
_user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WndClass)]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.BeginPaint.restype = wintypes.HDC
_user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(_PaintStruct)]
_user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(_PaintStruct)]
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
_user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
_user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
RDW_INVALIDATE, RDW_ERASE, RDW_UPDATENOW = 0x1, 0x4, 0x100


def _paint_now(hwnd):
    """지금 바로 그린다. 숨겼다 보이기를 잇달아 하면 Windows 가 그리기를 건너뛰어, 창은 '보임'인데
    화면에는 아무것도 없는 일이 생긴다 (2026-10-11 확인 — 끌던 독이 화면 끝을 잠깐 벗어났다
    돌아오면 미리보기가 안 보였다)."""
    _user32.RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_ERASE | RDW_UPDATENOW)
_user32.TrackMouseEvent.argtypes = [ctypes.POINTER(_TrackMouse)]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_user32.LoadCursorW.restype = wintypes.HANDLE
_user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
_user32.SetCursor.argtypes = [wintypes.HANDLE]
_user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
_gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
_gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x80000
WM_PAINT, WM_SETCURSOR, WM_MOUSEACTIVATE, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_MOUSEHOVER, WM_MOUSELEAVE = (
    0x0F, 0x20, 0x21, 0x200, 0x201, 0x2A1, 0x2A3)
MA_NOACTIVATE, TME_HOVER, TME_LEAVE, IDC_HAND, LWA_ALPHA = 3, 0x1, 0x2, 32649, 0x2
CLASS_NAME = 'SpacekijunDockHandle'


_class_proc = None
# 🚨 창에 건 처리 함수(ctypes 콜백)는 **프로세스가 끝날 때까지** 붙잡아 둔다. 콜백이 지워졌는데 창이 남아 있으면
# Windows 가 지워진 자리를 불러 데스크가 통째로 튕긴다(0xc0000005 · 이름 없는 모듈 — 2026-11-06 하루 네 번).
# 창을 부수는 일은 UI 스레드에 나중에 맡겨지므로, 객체가 먼저 사라져도 그 사이 오는 메시지를 받을 수 있어야 한다.
_kept_procs: list = []


def _overlay_window(ex_style: int, title: str, proc) -> int:
    """우리 처리 함수(proc)를 쓰는 테두리 없는 Win32 창을 만든다 (부른 스레드의 창이 된다)."""
    global _class_proc
    instance = _kernel32.GetModuleHandleW(None)
    if _class_proc is None:
        _class_proc = _WNDPROC(lambda h, m, w, l: _user32.DefWindowProcW(h, m, w, l))
        wc = _WndClass(0, _class_proc, 0, 0, instance, None, None, None, None, CLASS_NAME)
        _user32.RegisterClassW(ctypes.byref(wc))
    hwnd = _user32.CreateWindowExW(ex_style, CLASS_NAME, title, WS_POPUP, -32000, -32000, 10, 10,
                                   None, None, instance, None)
    if not hwnd:
        raise OSError(f'{title} 창을 만들지 못했습니다.')
    # 창마다 제 처리 함수로 — 같은 클래스의 다른 창과 섞이지 않게
    if not any(kept is proc for kept in _kept_procs):
        _kept_procs.append(proc)
    _user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(proc, ctypes.c_void_p).value)
    return hwnd


def _destroy(hwnd) -> None:
    """창을 부순다 — 먼저 처리 함수를 클래스의 것(늘 살아 있음)으로 되돌려, 부수는 동안 오는 메시지도 안전하게."""
    if not hwnd:
        return
    handle = wintypes.HWND(hwnd)
    if _class_proc is not None and _user32.IsWindow(handle):
        _user32.SetWindowLongPtrW(handle, GWLP_WNDPROC, ctypes.cast(_class_proc, ctypes.c_void_p).value)
    _user32.DestroyWindow(handle)


def _colorref(rgb):
    red, green, blue = rgb
    return red | (green << 8) | (blue << 16)


class Handle:
    """줄 창. **독 창의 UI 스레드에서** 만들고 다룬다 (`run` 이 그 스레드로 넘긴다 — 그 스레드의
    메시지 고리가 이 창의 메시지도 돌린다).

    🚨 WinForms 창으로 만들지 않는다. WinForms 는 속성을 바꿀 때 창을 부수고 새로 만들거나
    (가리킬 때 `Opacity` 를 바꾸면 그랬다) 제 스타일을 다시 덮어써, 손으로 건 '포커스 안 받기'·
    도구 창 스타일이 사라지고 코드는 옛 창을 붙잡고 있었다. 그래서 줄이 '보였다 안 보였다'
    했다 (2026-10-11 사용자 보고). Win32 창은 처음부터 끝까지 우리가 건 그대로 있다.
    그래도 다른 앱이 숨기거나 '항상 위'를 풀 수 있어 `check` 로 주기적으로 되돌린다."""

    def __init__(self, run, on_click):
        self._run = run                   # 일을 독 UI 스레드로 넘기는 함수 (desktop.on_ui)
        self._on_click = on_click         # 머무르거나 누르면 부른다
        self._armed = True                # 부르고 나면 커서가 줄을 벗어날 때까지 다시 부르지 않는다
        self.hwnd = None
        self._shown = None
        self._rect = None
        self._hover = False
        self._brushes = None
        self._proc = _WNDPROC(self._wndproc)    # 창이 사는 동안 붙잡아 둔다 (놓치면 튕긴다)

    def _wndproc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_PAINT:
                paint = _PaintStruct()
                hdc = _user32.BeginPaint(hwnd, ctypes.byref(paint))
                area = wintypes.RECT()
                _user32.GetClientRect(hwnd, ctypes.byref(area))
                _user32.FillRect(hdc, ctypes.byref(area), self._brushes[self._hover])
                _user32.EndPaint(hwnd, ctypes.byref(paint))
                return 0
            if message == WM_SETCURSOR:
                _user32.SetCursor(_user32.LoadCursorW(None, ctypes.c_void_p(IDC_HAND)))
                return 1
            if message == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE      # 눌러도 쓰던 창의 포커스를 뺏지 않는다
            if message == WM_MOUSEMOVE and not self._hover:
                self._hover = True
                track = _TrackMouse(ctypes.sizeof(_TrackMouse), TME_LEAVE | TME_HOVER, hwnd, HOVER_MS)
                _user32.TrackMouseEvent(ctypes.byref(track))
                _user32.InvalidateRect(hwnd, None, False)
            elif message == WM_MOUSEHOVER:
                self._summon()
                return 0
            elif message == WM_MOUSELEAVE:
                self._hover = False
                if not self._cursor_inside():   # 줄이 숨어서 온 것이면 커서는 아직 그 자리다
                    self._armed = True
                _user32.InvalidateRect(hwnd, None, False)
            elif message == WM_LBUTTONDOWN:
                self._armed = False
                self._on_click()
                return 0
        except Exception:
            pass                          # 창 메시지 처리 중 오류로 앱이 멈추지 않게
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _summon(self):
        if self._armed:
            self._armed = False
            self._on_click()

    def _cursor_inside(self) -> bool:
        if not self._rect:
            return False
        point = wintypes.POINT()
        if not _user32.GetCursorPos(ctypes.byref(point)):
            return False
        x, y, w, h = self._rect
        return x <= point.x < x + w and y <= point.y < y + h

    def _make(self):
        self._brushes = (_gdi32.CreateSolidBrush(_colorref(IDLE)), _gdi32.CreateSolidBrush(_colorref(HOVER)))
        ex = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED
        hwnd = _overlay_window(ex, TITLE, self._proc)
        _user32.SetLayeredWindowAttributes(hwnd, 0, round(255 * OPACITY), LWA_ALPHA)
        self.hwnd = hwnd

    def _place(self):
        x, y, w, h = self._rect
        hwnd = wintypes.HWND(self.hwnd)
        # 둥근 막대 — 두께만큼 둥글린다. 모양을 정하면 Windows 가 그 영역을 맡는다
        shape = _gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, min(w, h), min(w, h))
        _user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        if not _user32.SetWindowRgn(hwnd, shape, True):
            _gdi32.DeleteObject(shape)
        _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        _paint_now(hwnd)

    def show(self, rect: tuple[int, int, int, int]):
        if self._shown and rect == self._rect:
            return
        self._shown, self._rect = True, rect

        def work():
            if self.hwnd is None:
                self._make()
            self._place()
        self._run(work)

    def healthy(self) -> bool:
        """보여야 할 줄이 정말 보이고 '항상 위'인가."""
        if not self._shown or self.hwnd is None:
            return True
        hwnd = wintypes.HWND(self.hwnd)
        return bool(_user32.IsWindow(hwnd) and _user32.IsWindowVisible(hwnd)
                    and _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)

    def check(self):
        """주기적으로 부른다. 다른 앱이 줄을 숨기거나 '항상 위'를 풀었으면(전체 화면 게임 등)
        다시 건다. 창이 없어졌으면 새로 만든다.
        커서가 줄 밖에 있으면 다시 부를 수 있게 한다 — 줄이 숨는 동안 나가 '나갔다' 알림을 못 받았을 때."""
        if not (self._armed and not self._hover) and not self._cursor_inside():
            if self._hover and self.hwnd:
                _user32.InvalidateRect(wintypes.HWND(self.hwnd), None, False)   # 가리킨 색을 거둔다
            self._armed, self._hover = True, False
        if self.healthy():
            return

        def work():
            if not self._shown:
                return
            if self.hwnd is None or not _user32.IsWindow(wintypes.HWND(self.hwnd)):
                self.hwnd = None
                self._make()
            self._place()
        self._run(work)

    def hide(self):
        if self._shown is False:
            return
        self._shown = False
        if self.hwnd is None:
            return

        def work():
            _user32.ShowWindow(wintypes.HWND(self.hwnd), SW_HIDE)
        self._run(work)

    def close(self):
        hwnd, self.hwnd = self.hwnd, None
        brushes, self._brushes = self._brushes, None

        def work():
            _destroy(hwnd)
            for brush in brushes or ():
                _gdi32.DeleteObject(brush)
        self._run(work)


PREVIEW_TITLE = '스페이스기전 독 미리보기'
PREVIEW_FILL = (0x81, 0x8C, 0xF8)    # 밝은 강조색 — 어두운 화면에서도 보이게 반투명하게 깐다
PREVIEW_EDGE = (0xEE, 0xF2, 0xFF)    # 가장자리 선 — 거의 흰색
PREVIEW_ALPHA = 0.45
PREVIEW_BORDER = 3                   # 가장자리 선 두께 (실제 픽셀)
WS_EX_TRANSPARENT = 0x20


class Preview:
    """독을 끌어 화면 끝에 닿으면, 놓았을 때 독 판이 설 자리·방향·크기를 반투명하게 미리 보인다.

    클릭이 통과하고(WS_EX_TRANSPARENT) 포커스를 받지 않는다. 손잡이 줄처럼 Win32 창이며
    **독 창의 UI 스레드에서** 다룬다. 좌표는 실제 픽셀 (x, y, 너비, 높이)."""

    def __init__(self, run):
        self._run = run
        self.hwnd = None
        self._rect = None
        self._brushes = None
        self._proc = _WNDPROC(self._wndproc)

    def _wndproc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_PAINT:
                paint = _PaintStruct()
                hdc = _user32.BeginPaint(hwnd, ctypes.byref(paint))
                area = wintypes.RECT()
                _user32.GetClientRect(hwnd, ctypes.byref(area))
                fill, edge = self._brushes
                _user32.FillRect(hdc, ctypes.byref(area), edge)
                b = PREVIEW_BORDER
                inner = wintypes.RECT(area.left + b, area.top + b, area.right - b, area.bottom - b)
                _user32.FillRect(hdc, ctypes.byref(inner), fill)
                _user32.EndPaint(hwnd, ctypes.byref(paint))
                return 0
        except Exception:
            pass
        return _user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def show(self, rect: tuple[int, int, int, int], radius: int):
        if rect == self._rect:
            return
        self._rect = rect

        def work():
            if self.hwnd is None:
                self._brushes = (_gdi32.CreateSolidBrush(_colorref(PREVIEW_FILL)),
                                 _gdi32.CreateSolidBrush(_colorref(PREVIEW_EDGE)))
                ex = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_TRANSPARENT
                self.hwnd = _overlay_window(ex, PREVIEW_TITLE, self._proc)
                _user32.SetLayeredWindowAttributes(self.hwnd, 0, round(255 * PREVIEW_ALPHA), LWA_ALPHA)
            x, y, w, h = rect
            hwnd = wintypes.HWND(self.hwnd)
            corner = max(2, radius * 2)
            shape = _gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, corner, corner)
            _user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)
            if not _user32.SetWindowRgn(hwnd, shape, True):
                _gdi32.DeleteObject(shape)
            _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            _paint_now(hwnd)
        self._run(work)

    def hide(self):
        if self._rect is None:
            return
        self._rect = None
        if self.hwnd is None:
            return

        def work():
            _user32.ShowWindow(wintypes.HWND(self.hwnd), SW_HIDE)
        self._run(work)

    def close(self):
        hwnd, self.hwnd = self.hwnd, None
        brushes, self._brushes = self._brushes, None

        def work():
            _destroy(hwnd)
            for brush in brushes or ():
                _gdi32.DeleteObject(brush)
        self._run(work)
