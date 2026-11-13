"""
쿨메신저(CoolMessenger Gentoo) Win32 조작 — native.ps1 의 ctypes 포팅.

PowerShell 판을 그대로 옮기되 세 가지가 나아진다.
  · 런타임이 하나로 줄어 배포판에 PowerShell 이 필요 없다
  · **콘솔 인코딩(cp949) 문제가 사라진다** — PS 출력을 파싱하다 여러 번 깨졌다
  · 예외로 실패를 알리므로 "조용히 무시"되는 경우가 줄어든다

⚠️ 쿨메신저는 **32비트 프로세스**다. 원격 메모리에 쓰는 구조체(TVITEM/LVITEM)는
   32비트 레이아웃(포인터 4바이트, 구조체 40바이트)으로 맞춰야 한다.
   64비트 파이썬에서 ctypes 기본 구조체를 그대로 쓰면 어긋난다.

⚠️ 커서를 뺏지 않는다. 모든 조작은 창 메시지로 하고, 실제 마우스는 움직이지 않는다.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# ── 메시지 상수 ───────────────────────────────────────────────
WM_CLOSE, WM_SETTEXT, WM_GETTEXT, WM_COMMAND, WM_NOTIFY = 0x0010, 0x000C, 0x000D, 0x0111, 0x004E
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x0201, 0x0202, 0x0203
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
BM_CLICK, BM_GETCHECK = 0x00F5, 0x00F0

TVM_FIRST = 0x1100
TVM_GETNEXTITEM = TVM_FIRST + 10
TVM_GETITEMW = TVM_FIRST + 62
TVM_SELECTITEM = TVM_FIRST + 11
TVM_GETITEMRECT = TVM_FIRST + 4
TVM_EXPAND = TVM_FIRST + 2
TVM_ENSUREVISIBLE = TVM_FIRST + 20
TVM_HITTEST = TVM_FIRST + 17
TVGN_ROOT, TVGN_NEXT, TVGN_CHILD, TVGN_FIRSTVISIBLE, TVGN_CARET = 0, 1, 4, 5, 9
TVIF_TEXT, TVIF_HANDLE = 0x0001, 0x0010
TVE_EXPAND = 0x0002

LVM_FIRST = 0x1000
LVM_GETITEMCOUNT = LVM_FIRST + 4
LVM_GETITEMTEXTW = LVM_FIRST + 115
LVM_SETITEMSTATE = LVM_FIRST + 43
LVM_GETSELECTEDCOUNT = LVM_FIRST + 50
LVIS_SELECTED = 0x0002

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT_RESERVE, MEM_RELEASE, PAGE_READWRITE = 0x3000, 0x8000, 4
SW_SHOW, SW_RESTORE = 5, 9

user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_ssize_t, ctypes.c_ssize_t]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_ssize_t, ctypes.c_ssize_t]
kernel32.VirtualAllocEx.restype = ctypes.c_void_p
kernel32.OpenProcess.restype = wt.HANDLE


class CmError(RuntimeError):
    pass


# ── 창 열거 ───────────────────────────────────────────────────
_EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _text(hwnd, getter, n=512):
    buf = ctypes.create_unicode_buffer(n)
    getter(hwnd, buf, n)
    return buf.value


def pid() -> int | None:
    """쿨메신저 프로세스 ID. 없으면 None."""
    found = []

    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if _text(hwnd, user32.GetClassNameW, 128) == 'CoolMsg50SingleInstance':
            found.append(p.value)
            return False
        return True

    user32.EnumWindows(_EnumProc(cb), 0)
    return found[0] if found else None


def windows(include_hidden: bool = False) -> list[dict]:
    """쿨메신저 프로세스의 최상위 창.
    include_hidden=True 면 **트레이로 숨긴 창**까지 본다 — 메인 창을 되살릴 때 필요하다."""
    target = pid()
    if not target:
        return []
    out = []

    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == target and (include_hidden or user32.IsWindowVisible(hwnd)):
            out.append({'hwnd': hwnd,
                        'cls': _text(hwnd, user32.GetClassNameW, 128),
                        'title': _text(hwnd, user32.GetWindowTextW)})
        return True

    user32.EnumWindows(_EnumProc(cb), 0)
    return out


def children(parent) -> list[dict]:
    """EnumChildWindows 는 **재귀**다 — 손자까지 전부 나온다."""
    out = []

    def cb(hwnd, _):
        out.append({'hwnd': hwnd,
                    'id': user32.GetDlgCtrlID(hwnd),
                    'cls': _text(hwnd, user32.GetClassNameW, 128),
                    'text': _text(hwnd, user32.GetWindowTextW),
                    'vis': bool(user32.IsWindowVisible(hwnd))})
        return True

    user32.EnumChildWindows(parent, _EnumProc(cb), 0)
    return out


def find_window(title_like: str = '', cls: str = '') -> dict | None:
    for w in windows():
        if title_like and title_like not in w['title']:
            continue
        if cls and w['cls'] != cls:
            continue
        return w
    return None


def find_control(title_like: str, cls: str) -> dict | None:
    for w in windows():
        if title_like and title_like not in w['title']:
            continue
        for c in children(w['hwnd']):
            if c['cls'] == cls and c['vis']:
                return c
    return None


def main_window() -> dict | None:
    """숨겨져 있어도 찾는다 — 트레이로 내려가면 보이는 창 목록에서 빠지기 때문이다."""
    for w in windows(include_hidden=True):
        if 'COOLMESSENGER' in w['title']:
            return w
    return None


def restore_main():
    """
    ★ 메인 창이 **최소화돼 있으면 조직도 더블클릭이 먹지 않는다** (2026-09-10 실측).
      좌표는 정상인데 쪽지창이 조용히 안 열린다. 복원만 해 두면 된다.
      SetForegroundWindow 는 쓰지 않는다 — 포커스를 뺏으면 사용자 작업을 방해한다.
    """
    m = main_window()
    if not m:
        return False
    changed = False
    if not user32.IsWindowVisible(m['hwnd']):
        user32.ShowWindow(m['hwnd'], SW_SHOW)
        changed = True
    if user32.IsIconic(m['hwnd']):
        changed = True
    user32.ShowWindow(m['hwnd'], SW_RESTORE)
    return changed


# ── 컨트롤 텍스트 ─────────────────────────────────────────────
def get_text(hwnd, n=1024) -> str:
    """
    ⚠️ 다른 프로세스의 Edit 은 GetWindowText 가 **빈 문자열**을 준다.
       반드시 WM_GETTEXT 로 읽어야 한다.
    """
    buf = ctypes.create_unicode_buffer(n)
    user32.SendMessageW(hwnd, WM_GETTEXT, n, ctypes.cast(buf, ctypes.c_void_p).value)
    return buf.value


def set_text(hwnd, s: str):
    buf = ctypes.create_unicode_buffer(s)
    return user32.SendMessageW(hwnd, WM_SETTEXT, 0, ctypes.cast(buf, ctypes.c_void_p).value)


def click(hwnd):
    """모달을 여는 버튼은 반드시 Post — Send 로 누르면 대화상자가 닫힐 때까지 블록된다."""
    user32.PostMessageW(hwnd, BM_CLICK, 0, 0)


def close_window(hwnd):
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


# ── 원격 메모리 ───────────────────────────────────────────────
class Remote:
    """대상 프로세스에 버퍼를 잡고 구조체를 주고받는다."""

    def __init__(self, size: int):
        p = pid()
        if not p:
            raise CmError('쿨메신저가 실행 중이 아닙니다.')
        self.size = size
        self.h = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, p)
        if not self.h:
            raise CmError('OpenProcess 실패 (권한 부족)')
        self.addr = kernel32.VirtualAllocEx(self.h, None, size, MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if not self.addr:
            kernel32.CloseHandle(self.h)
            raise CmError('VirtualAllocEx 실패')

    def write(self, data: bytes, offset: int = 0):
        n = ctypes.c_size_t()
        kernel32.WriteProcessMemory(self.h, ctypes.c_void_p(self.addr + offset),
                                    data, len(data), ctypes.byref(n))

    def read(self, size: int, offset: int = 0) -> bytes:
        buf = ctypes.create_string_buffer(size)
        n = ctypes.c_size_t()
        kernel32.ReadProcessMemory(self.h, ctypes.c_void_p(self.addr + offset),
                                   buf, size, ctypes.byref(n))
        return buf.raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        kernel32.VirtualFreeEx(self.h, ctypes.c_void_p(self.addr), 0, MEM_RELEASE)
        kernel32.CloseHandle(self.h)


# ── 트리(조직도) ──────────────────────────────────────────────
# 32비트 TVITEMW = mask, hItem, state, stateMask, pszText, cchTextMax,
#                  iImage, iSelectedImage, cChildren, lParam  → 40바이트
_TVITEM = struct.Struct('<10I')
_TEXT_BYTES = 1024


def tree_items(tree_hwnd, limit=2000) -> list[dict]:
    """트리 전체를 깊이 우선으로 읽는다. 접혀 있어도 읽힌다."""
    out = []
    with Remote(40 + _TEXT_BYTES) as rem:
        text_addr = rem.addr + 40

        def label(hitem):
            rem.write(_TVITEM.pack(TVIF_TEXT | TVIF_HANDLE, hitem, 0, 0,
                                   text_addr, _TEXT_BYTES // 2, 0, 0, 0, 0))
            user32.SendMessageW(tree_hwnd, TVM_GETITEMW, 0, rem.addr)
            raw = rem.read(_TEXT_BYTES, 40)
            s = raw.decode('utf-16-le', 'ignore')
            return s.split('\x00', 1)[0]

        stack = []
        h = user32.SendMessageW(tree_hwnd, TVM_GETNEXTITEM, TVGN_ROOT, 0)
        depth = 0
        while h and len(out) < limit:
            out.append({'hItem': h, 'text': label(h), 'depth': depth})
            child = user32.SendMessageW(tree_hwnd, TVM_GETNEXTITEM, TVGN_CHILD, h)
            if child:
                stack.append((h, depth))
                h, depth = child, depth + 1
                continue
            nxt = user32.SendMessageW(tree_hwnd, TVM_GETNEXTITEM, TVGN_NEXT, h)
            while not nxt and stack:
                up, depth = stack.pop()
                nxt = user32.SendMessageW(tree_hwnd, TVM_GETNEXTITEM, TVGN_NEXT, up)
            h = nxt
    return out


def org_tree_control() -> dict:
    """
    조직도 트리를 고른다.

    ⚠️ 메인 창에는 `SysTreeView32` 가 **여러 개**다 (실측: 3개).
       "첫 번째 보이는 것"을 쓰면 사용자가 좌측 패널 탭을 바꿨을 때 엉뚱한 트리를 잡는다.
       그래서 **내용으로 판별**한다 — 사람 항목은 `(이름)` 꼴이므로 그 개수가 가장 많은 트리다.
       (실측: 조직도 358개 / 접속자 목록 91개(숨김) / 빈 트리 0개)

    보이는 트리 중에 조직도로 볼 만한 게 없으면 **추측하지 않고 예외**를 던진다.
    """
    m = main_window()
    if not m:
        raise CmError('쿨메신저 메인 창이 없습니다 (로그인 상태를 확인하세요).')
    best, best_score = None, 0
    for c in children(m['hwnd']):
        if c['cls'] != 'SysTreeView32' or not c['vis']:
            continue
        try:
            probe = tree_items(c['hwnd'], limit=80)      # 판별용으로만 앞부분을 본다
        except CmError:
            continue
        score = sum(1 for i in probe if i['text'].startswith('('))
        if score > best_score:
            best, best_score = c, score
    if best is None or best_score < 5:
        raise CmError('조직도 트리를 찾지 못했습니다. '
                      '쿨메신저 좌측 패널을 «조직도» 탭으로 두고 다시 시도하세요.')
    return best


def org_tree(limit=2000) -> list[dict]:
    return tree_items(org_tree_control()['hwnd'], limit)


def _item_rect(tree_hwnd, hitem) -> tuple[int, int, int, int]:
    with Remote(16) as rem:
        rem.write(struct.pack('<I', hitem) + b'\x00' * 12)
        user32.SendMessageW(tree_hwnd, TVM_GETITEMRECT, 1, rem.addr)   # wParam=1: 텍스트 영역
        return struct.unpack('<4i', rem.read(16))


def _client_size(hwnd) -> tuple[int, int]:
    r = ctypes.create_string_buffer(16)
    user32.GetClientRect(hwnd, ctypes.byref(r))
    l, t, rr, b = struct.unpack('<4i', r.raw)
    return rr - l, b - t


def _hit_test(tree_hwnd, x: int, y: int) -> int:
    """그 좌표에 실제로 어떤 항목이 있는지 트리에게 되묻는다. 32비트 TVHITTESTINFO = 16바이트."""
    with Remote(16) as rem:
        rem.write(struct.pack('<iiII', x, y, 0, 0))
        user32.SendMessageW(tree_hwnd, TVM_HITTEST, 0, rem.addr)
        _, _, _, hitem = struct.unpack('<iiII', rem.read(16))
        return hitem


def select_tree_item(tree_hwnd, hitem, double_click=False):
    """
    항목을 선택하고, 필요하면 더블클릭까지 한다.

    좌표는 하드코딩이 아니라 `TVM_GETITEMRECT` 로 **매번 트리에게 물어본** 클라이언트 좌표다.
    그래도 환경에 따라 흔들릴 여지가 있다 — 들여쓰기 깊이, 이름 길이, 행 높이(DPI·글꼴),
    스크롤 위치가 모두 rect 를 바꾼다. 그래서 누르기 전에 두 가지를 확인한다.

      1. 좌표가 트리 클라이언트 영역 안인가 (음수 y·가로 스크롤 대비)
      2. **그 좌표에 있는 항목이 정말 목표 항목인가** (TVM_HITTEST 로 되묻는다)

    확인이 안 되면 **클릭하지 않고 예외를 던진다.** 엉뚱한 사람에게 쪽지가 가는 것보다 낫다.
    """
    import time
    user32.SendMessageW(tree_hwnd, TVM_ENSUREVISIBLE, 0, hitem)
    time.sleep(0.3)
    user32.SendMessageW(tree_hwnd, TVM_SELECTITEM, TVGN_FIRSTVISIBLE, hitem)
    time.sleep(0.4)
    user32.SendMessageW(tree_hwnd, TVM_SELECTITEM, TVGN_CARET, hitem)
    time.sleep(0.5)
    if not double_click:
        return None

    cw, ch = _client_size(tree_hwnd)
    xy = None
    for attempt in range(3):
        left, top, right, bottom = _item_rect(tree_hwnd, hitem)
        x = max(2, min((left + right) // 2, cw - 2))      # 가로 스크롤·긴 이름 대비 클램프
        y = (top + bottom) // 2
        if 0 <= y < ch and _hit_test(tree_hwnd, x, y) == hitem:
            xy = (x, y)
            break
        # 화면 밖이거나 다른 항목이 잡히면 다시 스크롤해서 재시도
        user32.SendMessageW(tree_hwnd, TVM_ENSUREVISIBLE, 0, hitem)
        user32.SendMessageW(tree_hwnd, TVM_SELECTITEM, TVGN_FIRSTVISIBLE, hitem)
        time.sleep(0.5)
    if xy is None:
        raise CmError('트리 항목의 화면 위치를 확정하지 못했습니다 '
                      '(스크롤/크기 문제). 클릭하지 않고 중단합니다.')

    x, y = xy
    lp = (y << 16) | (x & 0xFFFF)
    user32.PostMessageW(tree_hwnd, WM_LBUTTONDOWN, 1, lp)
    user32.PostMessageW(tree_hwnd, WM_LBUTTONUP, 0, lp)
    time.sleep(0.15)
    user32.PostMessageW(tree_hwnd, WM_LBUTTONDBLCLK, 1, lp)
    user32.PostMessageW(tree_hwnd, WM_LBUTTONUP, 0, lp)
    return xy


# ── 리스트뷰(메시지 관리함) ───────────────────────────────────
# 32비트 LVITEMW = mask, iItem, iSubItem, state, stateMask, pszText, cchTextMax, ... → 40바이트
_LVITEM = struct.Struct('<10I')


def list_rows(lv_hwnd, cols=5, limit=300) -> list[dict]:
    n = user32.SendMessageW(lv_hwnd, LVM_GETITEMCOUNT, 0, 0)
    rows = []
    with Remote(40 + _TEXT_BYTES) as rem:
        text_addr = rem.addr + 40
        for i in range(min(n, limit)):
            cells = []
            for c in range(cols):
                rem.write(_LVITEM.pack(0, i, c, 0, 0, text_addr, _TEXT_BYTES // 2, 0, 0, 0))
                user32.SendMessageW(lv_hwnd, LVM_GETITEMTEXTW, i, rem.addr)
                raw = rem.read(_TEXT_BYTES, 40)
                cells.append(raw.decode('utf-16-le', 'ignore').split('\x00', 1)[0])
            rows.append({'index': i, 'cells': cells})
    return rows


def set_list_selection(lv_hwnd, indexes: list[int]) -> int:
    """지정한 행만 선택하고 나머지는 해제한다 — 오삭제를 막으려고 명시적으로 다룬다."""
    with Remote(40) as rem:
        rem.write(_LVITEM.pack(0, 0, 0, 0, LVIS_SELECTED, 0, 0, 0, 0, 0))
        user32.SendMessageW(lv_hwnd, LVM_SETITEMSTATE, -1, rem.addr)      # 전체 해제
        rem.write(_LVITEM.pack(0, 0, 0, LVIS_SELECTED, LVIS_SELECTED, 0, 0, 0, 0, 0))
        for i in indexes:
            user32.SendMessageW(lv_hwnd, LVM_SETITEMSTATE, i, rem.addr)
    return user32.SendMessageW(lv_hwnd, LVM_GETSELECTEDCOUNT, 0, 0)


# ── 팝업 ──────────────────────────────────────────────────────
def close_ad_popups() -> int:
    """광고 팝업은 CEF 페이지를 얹은 #32770 이다. 안 닫으면 클릭이 조용히 먹힌다."""
    n = 0
    for w in windows():
        if w['cls'] != '#32770':
            continue
        t = w['title']
        if t == '' or 'COOLMESSENGER' in t or '로그인' in t:
            continue
        if any(c['id'] == 3195 for c in children(w['hwnd'])):     # 메시지 관리함은 건드리지 않는다
            continue
        close_window(w['hwnd'])
        n += 1
    return n
