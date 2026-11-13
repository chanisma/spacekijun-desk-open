"""지금 보던 창의 폴더 — 독의 '에이전트 터미널'이 어느 폴더에서 열지 고를 때 쓴다 (2026-10-13 요청).

독을 누르는 순간의 앞 창은 독(또는 독 위 패널)일 수 있다. 그래서 `Tracker` 가 앞 창을 늘 지켜보다가
**이 프로그램이 아닌 마지막 앞 창**을 기억해 둔다. 그 창에서 폴더를 이렇게 찾는다.

  · 파일 탐색기   — 열린 탭마다 그 폴더 (Shell.Application). 탭이 여럿이면 여럿이 나온다
  · 바탕 화면     — 바탕 화면 폴더
  · VS Code 류    — 창 제목의 폴더 이름을 그 편집기가 열어 둔 폴더(storage.json)와 맞춘다
  · 터미널        — 그 창 아래 셸(cmd·PowerShell·bash)이 서 있는 폴더
  · 그 밖의 창    — 실행 인자의 파일·폴더 경로(한글·메모장처럼 파일을 두 번 눌러 연 경우),
                    창 제목에 적힌 전체 경로, 열려 있는 Office 문서의 폴더
찾은 폴더는 실제로 있는 것만 돌려준다. 아무것도 못 찾으면 빈 목록 — 화면이 고르게 한다.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import threading
from ctypes import wintypes
from pathlib import Path
from urllib.parse import unquote, urlparse

LIMIT = 8                  # 한 창에서 돌려주는 폴더 수 상한
POLL = 0.4                 # 앞 창을 다시 보는 간격 (초)
SHELLS = {'cmd.exe', 'powershell.exe', 'pwsh.exe', 'bash.exe', 'zsh.exe', 'fish.exe', 'nu.exe', 'wsl.exe',
          'claude.exe', 'codex.exe', 'node.exe', 'python.exe'}
TERMINALS = {'windowsterminal.exe', 'openconsole.exe', 'conhost.exe', 'wezterm-gui.exe', 'alacritty.exe',
             'mintty.exe', 'tabby.exe', 'hyper.exe'}
# 앞 창으로 치지 않는 것 — 작업 표시줄·시작 메뉴·Alt+Tab 처럼 잠깐 앞에 서는 껍데기
PASSING = {'Shell_TrayWnd', 'Shell_SecondaryTrayWnd', 'NotifyIconOverflowWindow', 'TopLevelWindowForOverflowXamlIsland',
           'Windows.UI.Core.CoreWindow', 'ForegroundStaging', 'MultitaskingViewFrame', 'XamlExplorerHostIslandWindow',
           'TaskListThumbnailWnd', 'Xaml_WindowedPopupClass', '#32768'}
DESKTOP = {'Progman', 'WorkerW'}
EXPLORER = {'CabinetWClass', 'ExploreWClass'}
# VS Code 와 그 갈래 — 실행 파일 이름 → %APPDATA% 아래 설정 폴더
CODE_FAMILY = {'code.exe': 'Code', 'code - insiders.exe': 'Code - Insiders', 'cursor.exe': 'Cursor',
               'windsurf.exe': 'Windsurf', 'vscodium.exe': 'VSCodium', 'trae.exe': 'Trae', 'kiro.exe': 'Kiro'}
OFFICE = {'winword.exe': ('Word.Application', 'ActiveDocument'), 'excel.exe': ('Excel.Application', 'ActiveWorkbook'),
          'powerpnt.exe': ('PowerPoint.Application', 'ActivePresentation')}
PATH_IN_TEXT = re.compile(r'[A-Za-z]:\\[^<>:"|?*\r\n]*')


# ── 앞 창 지켜보기 ────────────────────────────────────────────
class Tracker:
    """이 프로그램이 아닌 마지막 앞 창의 핸들을 기억한다."""

    def __init__(self, own_pid: int | None = None):
        self.own_pid = own_pid or os.getpid()
        self.last = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name='desk-foreground')
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.see(_user32.GetForegroundWindow())
            except Exception:
                pass
            self._stop.wait(POLL)

    def see(self, hwnd):
        if not hwnd:
            return
        if window_pid(hwnd) == self.own_pid or window_class(hwnd) in PASSING:
            return
        self.last = hwnd


# ── Win32 ────────────────────────────────────────────────────
# 🚨 전용 DLL 객체 — `ctypes.windll` 은 pywebview 와 같이 써서 argtypes 를 걸면 그쪽이 깨진다 (desktop.py)
_user32 = ctypes.WinDLL('user32', use_last_error=True)
_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_ntdll = ctypes.WinDLL('ntdll')
_shell32 = ctypes.WinDLL('shell32')
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.IsWindow.argtypes = [wintypes.HWND]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
_kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.Process32FirstW.argtypes = _kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                                             ctypes.POINTER(wintypes.ULONG)]
_shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
_shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]

QUERY_LIMITED, VM_READ = 0x1000, 0x0010


def window_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_class(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def window_title(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def _open(pid, rights=QUERY_LIMITED):
    return _kernel32.OpenProcess(rights, False, pid)


def process_image(pid) -> str:
    handle = _open(pid)
    if not handle:
        return ''
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(1024)
        return buffer.value if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else ''
    finally:
        _kernel32.CloseHandle(handle)


class _UnicodeString(ctypes.Structure):
    _fields_ = [('Length', wintypes.USHORT), ('MaximumLength', wintypes.USHORT), ('Buffer', ctypes.c_void_p)]


def process_command_line(pid) -> str:
    """ProcessCommandLineInformation (Windows 8.1+) — 남의 메모리를 읽지 않고 실행 줄을 받는다."""
    handle = _open(pid)
    if not handle:
        return ''
    try:
        size = wintypes.ULONG(0)
        _ntdll.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(size))
        if not size.value or size.value > 1 << 20:
            return ''
        buffer = ctypes.create_string_buffer(size.value)
        if _ntdll.NtQueryInformationProcess(handle, 60, buffer, size, ctypes.byref(size)) != 0:
            return ''
        text = _UnicodeString.from_buffer(buffer)
        return ctypes.wstring_at(text.Buffer, text.Length // 2) if text.Buffer else ''
    finally:
        _kernel32.CloseHandle(handle)


def process_cwd(pid) -> str:
    """셸이 서 있는 폴더 — PEB → ProcessParameters → CurrentDirectory (64비트 프로세스만)."""
    handle = _open(pid, QUERY_LIMITED | VM_READ)
    if not handle:
        return ''
    try:
        basic = (ctypes.c_void_p * 6)()       # PROCESS_BASIC_INFORMATION — [1] 이 PebBaseAddress
        if _ntdll.NtQueryInformationProcess(handle, 0, basic, ctypes.sizeof(basic), None) != 0 or not basic[1]:
            return ''

        def read(address, size):
            out = ctypes.create_string_buffer(size)
            done = ctypes.c_size_t()
            if not _kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address), out, size, ctypes.byref(done)):
                raise OSError('read')
            return out.raw

        params = int.from_bytes(read(basic[1] + 0x20, 8), 'little')
        raw = read(params + 0x38, 16)                         # CURDIR.DosPath (UNICODE_STRING)
        length, pointer = int.from_bytes(raw[0:2], 'little'), int.from_bytes(raw[8:16], 'little')
        if not pointer or not 0 < length <= 4096:
            return ''
        return read(pointer, length).decode('utf-16-le')
    except OSError:
        return ''
    finally:
        _kernel32.CloseHandle(handle)


class _ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260)]


def processes() -> list[tuple[int, int, str]]:
    """(pid, 부모 pid, 실행 파일 이름) 전부."""
    snap = _kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return []
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = []
        ok = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            found.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
            ok = _kernel32.Process32NextW(snap, ctypes.byref(entry))
        return found
    finally:
        _kernel32.CloseHandle(snap)


def split_command_line(line: str) -> list[str]:
    if not line:
        return []
    count = ctypes.c_int()
    argv = _shell32.CommandLineToArgvW(line, ctypes.byref(count))
    if not argv:
        return []
    try:
        return [argv[index] for index in range(count.value)]
    finally:
        _kernel32.LocalFree(argv)


# ── 폴더 고르기 (Win32 를 부르지 않는 셈 — 시험한다) ─────────────────
def _system_roots() -> list[str]:
    roots = [os.environ.get(name) for name in ('SystemRoot', 'ProgramFiles', 'ProgramFiles(x86)', 'ProgramData')]
    local = os.environ.get('LOCALAPPDATA')
    if local:
        roots += [str(Path(local) / 'Programs'), str(Path(local) / 'Microsoft'), str(Path(local) / 'Temp')]
    return [os.path.normcase(os.path.normpath(root)) for root in roots if root]


def usable(path: str, roots: list[str] | None = None) -> str | None:
    """실제로 있는 보통 폴더면 그 경로. 시스템·프로그램 폴더는 뺀다 — 거기서 에이전트를 돌릴 일은 없다."""
    if not path or not isinstance(path, str) or len(path) > 1024 or '\x00' in path:
        return None
    try:
        spot = Path(path)
        if not spot.is_absolute():
            return None
        if spot.is_file():
            spot = spot.parent
        if not spot.is_dir():
            return None
        resolved = os.path.normpath(str(spot))
    except (OSError, ValueError):
        return None
    folded = os.path.normcase(resolved)
    for root in (_system_roots() if roots is None else roots):
        if folded == root or folded.startswith(root.rstrip('\\') + '\\'):
            return None
    return resolved


def paths_in_text(text: str) -> list[str]:
    """창 제목 속 전체 경로 — 'C:\\작업\\보고서.hwp - 한글' 처럼. 있는 데까지 줄여 가며 찾는다."""
    found = []
    for match in PATH_IN_TEXT.finditer(text or ''):
        candidate = match.group(0).rstrip(' .-')
        while candidate and len(candidate) > 3:
            if os.path.exists(candidate):
                found.append(candidate)
                break
            cut = max(candidate.rfind(' - '), candidate.rfind(' — '), candidate.rfind(' '))
            if cut <= 2:
                break
            candidate = candidate[:cut].rstrip(' .-')
    return found


def paths_in_arguments(arguments: list[str]) -> list[str]:
    """실행 인자 가운데 절대 경로 (첫 인자 = 프로그램 자신은 뺀다). '/open:C:\\x' 같은 꼴도 본다."""
    found = []
    for argument in arguments[1:]:
        for piece in (argument, argument.split(':', 1)[-1] if argument.startswith(('/', '-')) else ''):
            if re.match(r'^[A-Za-z]:\\|^\\\\[^\\]', piece or '') and os.path.exists(piece):
                found.append(piece)
                break
    return found


def code_folders(app_dir: Path, title: str) -> list[str]:
    """VS Code 류가 열어 둔 폴더 가운데 창 제목에 이름이 보이는 것. 못 맞추면 열린 것 전부."""
    try:
        state = json.loads((app_dir / 'User' / 'globalStorage' / 'storage.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    uris = []
    windows = state.get('windowsState') or {}
    for entry in [windows.get('lastActiveWindow') or {}] + list(windows.get('openedWindows') or []):
        uris.append(entry.get('folder') if isinstance(entry, dict) else None)
    for entry in (state.get('backupWorkspaces') or {}).get('folders') or []:
        uris.append(entry.get('folderUri') if isinstance(entry, dict) else None)
    folders = []
    for uri in uris:
        if not isinstance(uri, str) or not uri.startswith('file:///'):
            continue
        path = unquote(urlparse(uri).path).lstrip('/').replace('/', '\\')
        if path and path not in folders:
            folders.append(path)
    pieces = {piece.strip().lower() for piece in re.split(r' [-—] ', title or '')}
    named = [path for path in folders if Path(path).name.lower() in pieces]
    return named or folders


def unique(paths, limit=LIMIT) -> list[str]:
    out, seen = [], set()
    for path in paths:
        good = usable(path)
        if good and os.path.normcase(good) not in seen:
            seen.add(os.path.normcase(good))
            out.append(good)
        if len(out) >= limit:
            break
    return out


# ── 창 → 폴더 ─────────────────────────────────────────────────
def explorer_windows() -> list[tuple[int, str]]:
    """열린 파일 탐색기 탭마다 (창 핸들, 폴더). 탭은 같은 창 핸들을 나눠 쓴다."""
    try:
        import clr  # noqa: F401  — pythonnet
        from System import Activator, Array, Int32, Object, Type
        from System.Reflection import BindingFlags
    except Exception:
        return []

    def get(target, name):
        return target.GetType().InvokeMember(name, BindingFlags.GetProperty, None, target, None)

    found = []
    try:
        shell = Activator.CreateInstance(Type.GetTypeFromProgID('Shell.Application'))
        windows = shell.GetType().InvokeMember('Windows', BindingFlags.InvokeMethod, None, shell, None)
        for index in range(int(get(windows, 'Count'))):
            try:
                window = windows.GetType().InvokeMember('Item', BindingFlags.InvokeMethod, None, windows,
                                                        Array[Object]([Int32(index)]))
                if window is None:
                    continue
                path = get(get(get(get(window, 'Document'), 'Folder'), 'Self'), 'Path')
                found.append((int(get(window, 'HWND')), str(path)))
            except Exception:
                continue                # 인터넷 익스플로러 창·특수 폴더(내 PC 등)는 건너뛴다
    except Exception:
        return found
    return found


def desktop_folder() -> str:
    try:
        import winreg
        key = r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as opened:
            return os.path.expandvars(winreg.QueryValueEx(opened, 'Desktop')[0])
    except OSError:
        return str(Path.home() / 'Desktop')


def office_folder(exe: str) -> list[str]:
    progid, member = OFFICE[exe]
    try:
        import clr  # noqa: F401
        from System.Reflection import BindingFlags
        from System.Runtime.InteropServices import Marshal
        app = Marshal.GetActiveObject(progid)
        document = app.GetType().InvokeMember(member, BindingFlags.GetProperty, None, app, None)
        path = str(document.GetType().InvokeMember('Path', BindingFlags.GetProperty, None, document, None))
        return [path] if re.match(r'^[A-Za-z]:\\|^\\\\', path) else []    # OneDrive 웹 주소는 뺀다
    except Exception:
        return []


def shell_folders(root_pid: int) -> list[str]:
    """터미널 창 아래(자손)의 셸들이 서 있는 폴더. 최근에 뜬 셸(큰 pid)부터."""
    table = processes()
    children = {}
    for pid, parent, name in table:
        children.setdefault(parent, []).append((pid, name))
    found, queue, seen = [], [root_pid], set()
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        for pid, name in children.get(current, []):
            queue.append(pid)
            if name.lower() in SHELLS:
                found.append(pid)
    return [process_cwd(pid) for pid in sorted(found, reverse=True)]


def folders_of(hwnd) -> dict:
    """창 하나에서 찾은 폴더들과 그 창의 이름 — {'app', 'title', 'folders'}."""
    if not hwnd or not _user32.IsWindow(hwnd):
        return {'app': '', 'title': '', 'folders': []}
    kind, title, pid = window_class(hwnd), window_title(hwnd), window_pid(hwnd)
    image = process_image(pid)
    exe = Path(image).name.lower() if image else ''
    app = Path(image).stem if image else kind
    found = []
    if kind in DESKTOP:
        return {'app': '바탕 화면', 'title': '', 'folders': unique([desktop_folder()])}
    if kind in EXPLORER:
        found += [path for handle, path in explorer_windows() if handle == int(hwnd)]
        app = '파일 탐색기'
    elif exe in CODE_FAMILY and os.environ.get('APPDATA'):
        found += code_folders(Path(os.environ['APPDATA']) / CODE_FAMILY[exe], title)
    elif exe in TERMINALS or kind == 'ConsoleWindowClass':
        found += shell_folders(pid)
        if exe in SHELLS or kind == 'ConsoleWindowClass':
            found.append(process_cwd(pid))
    if exe in OFFICE:
        found += office_folder(exe)
    found += paths_in_text(title)
    if kind not in EXPLORER:
        found += paths_in_arguments(split_command_line(process_command_line(pid)))
    return {'app': app, 'title': title, 'folders': unique(found)}


def open_explorer_folders(skip=()) -> list[str]:
    """열린 파일 탐색기 탭의 폴더 전부 (skip 에 든 것은 뺀다)."""
    skipped = {os.path.normcase(path) for path in skip}
    return [path for path in unique([path for _, path in explorer_windows()], limit=12)
            if os.path.normcase(path) not in skipped]
