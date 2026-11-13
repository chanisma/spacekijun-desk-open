"""스페이스기전 교실 — 교실판 입구 (SpacekijunClassroom.exe · 스페이스기전-교실.bat).

교실 PC 에 QR 을 띄운다. 교사가 휴대폰으로 찍어 스페이스기전에서 승인하면, 화면 아래에 그 교사의 **독**이 뜬다
— 반별 세팅(드라이브 폴더·파일, 웹사이트, PC 프로그램, 스페이스기전 화면)과 «내 드라이브»가 아이콘으로 놓이고,
누르면 연다. 드라이브는 프로그램 안 탐색기에서 일반 폴더처럼 쓴다(열고 고쳐 저장하면 드라이브에 되올림).
수업이 끝나면(정해 둔 시간 · 독의 [수업 끝] · 휴대폰의 «수업 끝») 연 것을 닫고, 고친 파일을 올리고,
받은 파일과 로그인을 지운 뒤 다시 QR 로.

창 셋: QR 창(main) · 독(dock, 수업 중) · 드라이브 탐색기(drive, 누를 때). 셋 다 이 파일의 Api 만 부른다.
이 PC 는 아무 계정으로도 로그인하지 않는다. 서버와는 이 PC 에 묶인 기기 키로만 말한다(core/classroom_link.py).
저장 폴더는 %LOCALAPPDATA%/SpacekijunClassroom. 상세: app/CLASSROOM.md
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TITLE = '스페이스기전 교실'
MUTEX = 'Local\\SpacekijunClassroom'
WEB_DIR = Path(__file__).parent / 'web'
SETUP_URL = 'https://spacekijun.lovable.app/classroom'   # 세팅 만들기(웹 메뉴 [도구] → 교실 기기)
DOCK_HEIGHT = 112
DOCK_SLOT = 78               # 아이콘 한 칸 너비(이름 포함)
DOCK_EXTRA = 440             # 선생님 이름 · 남은 시간 · 수업 끝 자리 · 여백
MINI_SIZE = (340, 124)       # QR 창을 내렸을 때 오른쪽 아래 작은 위젯
GTOOLS_APPS = {'classroom': 'classroom', 'slides': 'slides', 'forms': 'forms'}   # 구글 앱 키 → 구글 수업 도구 탭


def work_area() -> tuple[int, int, int, int]:
    """주 화면의 작업 영역(작업 표시줄을 뺀 곳) — **논리 픽셀**(x, y, 너비, 높이).

    🚨 pywebview 는 프로세스를 DPI 인식으로 켜서 webview.screens 는 **물리 픽셀**을 주는데, create_window 의
    x·y·너비·높이는 논리 픽셀로 받아 화면 배율(예: 150%)을 곱한다. 화면 크기를 그대로 쓰면 배율이 큰 PC 에서
    독·작은 위젯·알림 창이 가운데가 아니라 오른쪽 아래(화면 밖)로 밀렸다(2026-10-14 사용자 보고). 그래서
    작업 영역을 물리 픽셀로 받아 배율로 나눈다.
    """
    user32 = ctypes.WinDLL('user32')
    try:
        scale = (user32.GetDpiForSystem() or 96) / 96
    except Exception:
        scale = 1.0

    class Rect(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
    rect = Rect()
    if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):      # SPI_GETWORKAREA — 주 화면
        rect.right, rect.bottom = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return (round(rect.left / scale), round(rect.top / scale),
            round((rect.right - rect.left) / scale), round((rect.bottom - rect.top) / scale))


def round_corners(window):
    """프레임 없는 독 창의 모서리를 Windows 11 처럼 둥글게(DWMWA_WINDOW_CORNER_PREFERENCE = 둥글게)."""
    try:
        from webview.platforms.winforms import BrowserView
        form = BrowserView.instances.get(window.uid)
        if form is None:
            return
        value = ctypes.c_int(2)
        ctypes.WinDLL('dwmapi').DwmSetWindowAttribute(
            ctypes.c_void_p(form.Handle.ToInt64()), 33, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def on_ui(window, work):
    """창의 UI 스레드에서 work 를 돌린다(기다리지 않는다). work 는 아무것도 돌려주면 안 된다(Func[Type])."""
    try:
        from System import Func, Type
        from webview.platforms.winforms import BrowserView
        form = BrowserView.instances.get(window.uid)
        if form is None:
            return

        def run():
            try:
                work(form)
            except Exception:
                pass
        form.BeginInvoke(Func[Type](run))
    except Exception:
        pass


def tool_window(window):
    """작업 표시줄·Alt+Tab 에서 뺀다(도구 창 스타일) — 작은 위젯용. WinForms ShowInTaskbar 는 핸들을 새로 만들어
    WebView2 가 죽으므로 같은 핸들에 Win32 스타일만 바꾸고, 작업 표시줄이 알아채도록 한 번 숨겼다 보인다."""
    def apply(form):
        user32 = ctypes.WinDLL('user32')
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        hwnd = ctypes.c_void_p(form.Handle.ToInt64())
        gwl_exstyle, ws_ex_toolwindow, ws_ex_appwindow = -20, 0x80, 0x40000
        style = user32.GetWindowLongPtrW(hwnd, gwl_exstyle)
        user32.SetWindowLongPtrW(hwnd, gwl_exstyle, (style | ws_ex_toolwindow) & ~ws_ex_appwindow)
        user32.ShowWindow(hwnd, 0)
        user32.ShowWindow(hwnd, 4)          # SW_SHOWNOACTIVATE
    on_ui(window, apply)


class Api:
    """교실판 화면(classroom*.html)만 부른다. 스페이스기전 창에는 넘기지 않는다."""

    def __init__(self, controller, link, windows):
        self._c = controller
        self._link = link
        self._w = windows
        self._copy = {'running': False}
        self._copy_lock = threading.Lock()

    # 공통 --------------------------------------------------------------------
    def state(self):
        return self._c.state()

    def settings(self):
        from core import classroom_startup
        from core import classroom_update
        updates = getattr(self._w, 'updates', None) or {}
        record = updates.get('record')
        return {'device_name': self._link.device_name(), 'settings_path': self._link.SETTINGS_PATH,
                'autostart': classroom_startup.enabled(), 'autostart_managed': classroom_startup.managed(),
                'version': classroom_update.VERSION, 'update_ready': record.get('version') if record else None,
                'can_update': updates.get('checker') is not None}

    def set_autostart(self, value):
        """기기 설정 — Windows 를 켜면 자동으로 실행"""
        from core import classroom_startup
        if classroom_startup.managed():
            return {'ok': False, 'error': '학교가 이 PC 에 자동 실행을 걸어 두어 끌 수 없습니다.'}
        try:
            classroom_startup.set_enabled(bool(value))
            return {'ok': True, 'autostart': classroom_startup.enabled()}
        except (OSError, ValueError) as e:
            return {'ok': False, 'error': str(e)}

    # 새 판 — 기기 설정에서 손으로(2026-10-14 요청). 뒤에서도 30분마다 확인한다 ------------------------------
    def check_update(self):
        """지금 확인하고, 새 판이 있으면 받아 둔다 → {ok, version(받아 둔 새 판) | None}"""
        updates = getattr(self._w, 'updates', None)
        if not updates or updates.get('checker') is None:
            return {'ok': False, 'error': '이 실행 방식(소스·쓸 수 없는 폴더)에서는 업데이트를 할 수 없습니다.'}
        try:
            record = updates['checker'].check_once()
        except Exception as e:
            return {'ok': False, 'error': f'새 판을 확인하지 못했습니다: {e}'}
        if record:
            updates['record'] = record
        current = updates.get('record')
        return {'ok': True, 'version': current.get('version') if current else None}

    def install_update(self):
        """받아 둔 새 판으로 지금 바꾼다 — 수업 중에는 하지 않는다(프로그램이 다시 켜진다)"""
        updates = getattr(self._w, 'updates', None)
        if not updates or not updates.get('record'):
            return {'ok': False, 'error': '받아 둔 새 판이 없습니다. [새 판 확인]을 먼저 눌러 주세요.'}
        if self._c.state()['phase'] not in ('qr', 'offline'):
            return {'ok': False, 'error': '수업 중에는 바꿀 수 없습니다. 수업이 끝난 뒤 눌러 주세요.'}
        install = getattr(self._w, 'install_update', None)
        if not install or not install():
            return {'ok': False, 'error': '새 판을 설치하지 못했습니다. 프로그램 폴더에 쓸 수 있는지 확인해 주세요.'}
        return {'ok': True}

    def quit_app(self):
        """기기 설정의 «프로그램 끝내기» — 이것 말고는 끝나지 않는다(창의 ✕ 는 내리기)"""
        quit_fn = getattr(self._w, 'quit', None)
        if quit_fn:
            threading.Thread(target=quit_fn, daemon=True).start()
        return {'ok': True}

    def restore_main(self):
        """작은 위젯의 [QR 크게 보기]"""
        self._c.wake()
        self._w.restore_main()

    def wake(self):
        """쉬는 중 화면의 [연결 QR 띄우기]"""
        self._c.wake()
        return {'ok': True}

    def setup_qr(self):
        """QR 화면 오른쪽의 작은 QR — 휴대폰으로 스페이스기전 «교실 기기»(세팅 만들기)를 연다"""
        return self._link.qr_svg(SETUP_URL)

    def save_name(self, name):
        name = str(name or '').strip()[:40]
        value = self._link.load_settings()
        value['device_name'] = name
        self._link.save_settings(value)
        self._c.code = None          # 새 이름으로 QR 을 다시 만든다
        return {'ok': True, 'device_name': self._link.device_name()}

    # 독 ----------------------------------------------------------------------
    def open_item(self, index):
        # 세팅의 클래스룸·슬라이드·설문지 타일은 구글 수업 도구로(로그인 없이) — 웹은 도구 안 [웹으로 열기]
        session = self._c.session
        items = getattr(session, 'items', None) or []
        if 0 <= int(index) < len(items):
            app = str(items[int(index)].get('app') or '')
            if items[int(index)].get('kind') == 'url' and app in GTOOLS_APPS:
                return self.open_gtools(GTOOLS_APPS[app])
        result = self._c.open_item(int(index))
        if result.get('explore'):
            self._w.show_drive(result['explore'], result.get('name'))
            return {'ok': True}
        return result

    def open_google(self):
        return self._c.open_google()

    def forget_google(self):
        return self._c.forget_google()

    def google_status(self):
        """구글 창을 열 때 — 수업용 Edge 앞 탭의 구글 계정(접근성으로 읽음). 못 읽으면 email None(«모름»)"""
        session = self._c.session
        if session is None:
            return {'ok': False}
        return {'ok': True, 'email': session.signed_in_email()}

    def item_icons(self):
        """독 타일의 실제 아이콘 — 상태(1초마다)에 싣기엔 커서 따로(icons_version 이 바뀔 때만 부른다)"""
        session = self._c.session
        return list(session.icons) if session else []

    # 휴대폰으로 구글 비밀번호 입력(2026-10-14) — 칠판에서 치지 않게(core/classroom_type.py) -----------------
    def open_type(self):
        if self._c.session is None:
            return {'ok': False, 'error': '수업 중이 아닙니다.'}
        self._w.close_popup('google')
        self._w.show_type()
        return {'ok': True}

    def type_start(self):
        """일회용 키를 만들어 서버에 맡기고 QR 을 돌려준다. 구글 로그인 창이 없으면 연다(이메일을 채운 로그인)"""
        from core import classroom_type as ct
        from core.classroom_link import LinkError
        session, code = self._c.session, self._c.code
        if session is None or not code:
            return {'ok': False, 'error': '수업 중이 아닙니다.'}
        key = ct.TypeKey()
        try:
            r = self._c.client.type_start(code, key.public)
        except LinkError as e:
            return {'ok': False, 'error': str(e)}
        self._type = {'code': r['code'], 'key': key}
        if not ct.login_page_open(session.edge_pids()):
            session.open_google(login=True)
        return {'ok': True, 'qr': self._link.qr_svg(ct.type_url(r['code'], key.public)), 'expires_at': r.get('expires_at')}

    def type_poll(self):
        """휴대폰에서 보냈으면 풀어서 구글 로그인 칸에 넣는다. 비밀번호는 남기지 않는다"""
        from core import classroom_type as ct
        from core.classroom_link import LinkError
        t, session = getattr(self, '_type', None), self._c.session
        if not t or session is None:
            return {'ok': False, 'status': 'none'}
        try:
            r = self._c.client.type_poll(t['code'])
        except LinkError:
            return {'ok': True, 'status': 'pending'}       # 잠깐 끊김 — 다시 묻는다
        status = r.get('status')
        if status == 'expired':
            self._type = None
            return {'ok': True, 'status': 'expired'}
        if status != 'sent':
            return {'ok': True, 'status': 'pending'}
        self._type = None
        try:
            password = t['key'].open(t['code'], r.get('payload') or {})
        except Exception:
            return {'ok': False, 'status': 'error', 'error': '받은 내용을 풀지 못했습니다. 다시 시도해 주세요.'}
        result = ct.fill_in_edge(session.edge_pids(), session.email, password)
        password = None
        if result != 'ok' and result != 'manual':
            return {'ok': False, 'status': 'error', 'error': result}
        session.mark_phone_login()
        if result == 'manual':
            return {'ok': True, 'status': 'filled', 'manual': True}
        return {'ok': True, 'status': 'filled'}

    def type_cancel(self):
        from core.classroom_link import LinkError
        t = getattr(self, '_type', None)
        self._type = None
        if t:
            try:
                self._c.client.type_cancel(t['code'])
            except LinkError:
                pass
        self._w.close_popup('type')
        return {'ok': True}

    def open_google_launcher(self):
        self._w.show_google()
        return {'ok': True}

    def open_google_app(self, key):
        result = self._c.open_google_app(str(key))
        if result.get('ok'):
            self._w.close_popup('google')
        return result

    # 따로 뜨는 작은 창 — 독(높이 112)에 그리면 잘려서(2026-10-14 사용자 보고) 알림·확인은 창으로 ----------
    def notify(self, text, error=False):
        self._w.notify(str(text or ''), bool(error))
        return {'ok': True}

    def ask(self, opts):
        """확인 창을 띄우고 고를 때까지 기다린다 → True/False"""
        return self._w.ask(opts if isinstance(opts, dict) else {})

    def answer(self, token, value):
        self._w.answer(str(token), bool(value))
        return {'ok': True}

    def popup(self, kind):
        return self._w.popup_content(str(kind))

    def close_popup(self, kind):
        self._w.close_popup(str(kind))
        return {'ok': True}

    def open_drive(self, folder_id=None, name=None):
        self._w.show_drive(folder_id or 'root', name or '내 드라이브')
        return {'ok': True}

    def extend(self, minutes=10):
        try:
            self._c.extend(int(minutes))
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def finish(self):
        threading.Thread(target=lambda: self._c.finish('수업을 정리했습니다.'), daemon=True).start()
        return {'ok': True}

    def drive_reconnect(self):
        try:
            self._c.drive_reconnect()
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def drive_reconnect_cancel(self):
        self._c.drive_reconnect_cancel()
        return {'ok': True}

    # 드라이브 탐색기 -----------------------------------------------------------
    # 구글 수업 도구(web/gtools.js) — 클래스룸·슬라이드 발표·설문지를 구글 로그인 없이(2026-10-14) ----------
    def open_gtools(self, tab='classroom'):
        if self._c.session is None:
            return {'ok': False, 'error': '수업 중이 아닙니다.'}
        self._w.show_gtools(str(tab or 'classroom'))
        self._w.close_popup('google')
        return {'ok': True}

    def close_gtools(self):
        self._w.close_gtools()
        return {'ok': True}

    def gtools_tab(self):
        return self._w.gtools_pending

    def gtools_fullscreen(self, on):
        self._w.gtools_fullscreen(bool(on))
        return {'ok': True}

    def google_api(self, method, url, body=None):
        """화면이 부르는 구글 API — 허용한 주소만, 토큰은 화면에 주지 않는다(core/google_tools.py)"""
        from core import google_tools
        session = self._c.session
        return google_tools.call(session.google_token() if session else None, method, url, body)

    def qr_svg(self, text):
        return self._link.qr_svg(str(text or ''))[:200000] if str(text or '').startswith('https://') else ''

    def open_web(self, url, title=None):
        """«웹으로 열기» — 수업용 Edge 로(구글 웹은 로그인이 필요할 수 있다)"""
        url = str(url or '')
        session = self._c.session
        if session is None or not url.startswith('https://'):
            return {'ok': False, 'error': '열 수 없는 주소입니다.'}
        try:
            session._edge_open(url)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e) or '열지 못했습니다.'}

    def _workspace(self):
        session = self._c.session
        if session is None:
            raise RuntimeError('수업 중이 아닙니다.')
        return session.workspace

    def _drive_call(self, fn):
        from core.classroom_drive import DriveError
        try:
            return {'ok': True, **fn()}
        except DriveError as e:
            return {'ok': False, 'error': str(e), 'auth': e.auth}
        except Exception as e:
            return {'ok': False, 'error': str(e) or '처리하지 못했습니다.'}

    def drive_start(self):
        """탐색기가 처음 뜰 때 — 어느 폴더로 열지"""
        return self._w.pending_drive

    def drive_list(self, folder_id='root', drive_id=None):
        return self._drive_call(lambda: {'items': self._workspace().drive().list(folder_id, drive_id)})

    def drive_shared_drives(self):
        return self._drive_call(lambda: {'drives': self._workspace().drive().shared_drives()})

    def drive_open(self, file_id):
        return self._drive_call(lambda: {'path': os.path.basename(self._workspace().open(file_id))})

    def drive_mkdir(self, parent, name):
        name = str(name or '').strip()[:120]
        if not name:
            return {'ok': False, 'error': '폴더 이름을 입력해 주세요.'}
        return self._drive_call(lambda: {'folder': self._workspace().drive().create_folder(name, parent)})

    def _pick_folder(self):
        """이 PC 에 남길 폴더를 고른다(그 선생님이 지난번에 고른 곳, 처음엔 바탕 화면)"""
        import webview
        window = self._w.drive
        if window is None:
            return None
        session = self._c.session
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        start = (session.shelf.last_dest() if session is not None else None) or (desktop if os.path.isdir(desktop) else '')
        picked = window.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
        return picked[0] if picked else None

    def drive_copy(self, items):
        """고른 파일·폴더를 이 PC 로 복사 — 다른 스레드에서 받고, 진행은 drive_copy_state 로"""
        items = [dict(id=str(i.get('id')), name=str(i.get('name') or ''), mimeType=str(i.get('mimeType') or ''),
                      shortcutDetails=i.get('shortcutDetails'))
                 for i in (items or []) if isinstance(i, dict) and i.get('id')][:200]
        if not items:
            return {'ok': False, 'error': '복사할 항목을 고르세요.'}
        with self._copy_lock:
            if self._copy.get('running'):
                return {'ok': False, 'error': '이미 복사하는 중입니다.'}
        dest = self._pick_folder()
        if not dest:
            return {'ok': True, 'started': False}
        try:
            workspace = self._workspace()
        except RuntimeError as e:
            return {'ok': False, 'error': str(e)}
        self._copy = {'running': True, 'done': 0, 'total': 0, 'current': '', 'dest': dest, 'result': None}

        def progress(done, total, name):
            self._copy.update(done=done, total=total, current=name)

        def run():
            from core.classroom_drive import DriveError
            try:
                result = workspace.copy_to_pc(items, dest, progress)
            except DriveError as e:
                result = {'copied': 0, 'errors': [str(e)], 'truncated': False, 'auth': e.auth}
            except OSError as e:
                result = {'copied': 0, 'errors': [str(e)], 'truncated': False}
            session = self._c.session
            if session is not None and result.get('copied'):
                session.record_copy(dest, result['copied'], result.get('paths') or ())
            self._copy.update(running=False, result=result)
        threading.Thread(target=run, daemon=True, name='classroom-copy').start()
        return {'ok': True, 'started': True, 'dest': dest}

    def drive_copy_state(self):
        return dict(self._copy)

    def drive_keep(self, key):
        """열어 둔 파일 하나를 이 PC 에 남긴다"""
        dest = self._pick_folder()
        if not dest:
            return {'ok': True, 'saved': None}

        def run():
            path = self._workspace().keep(str(key), dest)
            session = self._c.session
            if session is not None:
                session.record_copy(dest, 1, [path])
            self._copy = {'running': False, 'dest': dest, 'result': None}
            return {'saved': path}
        return self._drive_call(run)

    def drive_reveal(self):
        """방금 복사한 폴더를 탐색기로 연다(이 Api 가 고른 폴더만)"""
        dest = self._copy.get('dest')
        if dest and os.path.isdir(dest):
            os.startfile(dest)
        return {'ok': True}

    # 이 PC 에 복사한 파일(core/classroom_drive.py PcShelf) — 드라이브 연결 없이 -------------------------
    def _shelf(self):
        session = self._c.session
        if session is None:
            raise RuntimeError('수업 중이 아닙니다.')
        return session.shelf

    def pc_list(self, item_id='pc'):
        return self._drive_call(lambda: {'items': self._shelf().list(str(item_id or 'pc'))})

    def pc_count(self):
        return self._drive_call(lambda: {'count': self._shelf().count()})

    def pc_open(self, item_id):
        return self._drive_call(lambda: {'path': os.path.basename(self._shelf().open(str(item_id)))})

    def pc_reveal(self, item_id):
        """Windows 탐색기에서 그 자리를(그 파일을 고른 채로)"""
        def run():
            path = self._shelf().resolve(str(item_id))
            subprocess.Popen(['explorer', '/select,', path])
            return {}
        return self._drive_call(run)

    def pc_forget(self, ids):
        return self._drive_call(lambda: {'count': self._shelf().forget([str(i) for i in (ids or [])][:500])})

    def pc_trash(self, ids):
        return self._drive_call(lambda: self._shelf().trash([str(i) for i in (ids or [])][:500]))

    def drive_upload(self, parent):
        import webview
        window = self._w.drive
        if window is None:
            return {'ok': False, 'error': '탐색기가 닫혀 있습니다.'}
        paths = window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True) or []
        if not paths:
            return {'ok': True, 'count': 0}

        def run():
            drive = self._workspace().drive()
            for path in paths:
                drive.upload_new(path, parent)
            return {'count': len(paths)}
        return self._drive_call(run)


class Windows:
    """창 셋을 만들고 자리를 잡는다."""

    def __init__(self, main_window):
        self.main = main_window
        self.dock = None
        self.drive = None
        self.api = None
        self.pending_drive = {'folder': 'root', 'name': '내 드라이브'}
        self.gtools = None               # 구글 수업 도구 창
        self.gtools_pending = 'classroom'
        self.gtools_full = False
        self.updates = None              # {'record', 'checker'} — main 이 넣는다
        self.install_update = None
        self.lock = threading.RLock()
        self.popups = {}                 # 'toast' · 'dialog' · 'google' → 창
        self.toast = {'id': 0, 'text': '', 'error': False}
        self.dialog = None               # {token, opts, event, value}
        self.mini = None                 # QR 창을 내렸을 때 오른쪽 아래 작은 위젯
        self.lowered = False             # QR 창을 내려 두었다(위젯만 보인다)

    def arrange(self, state):
        import webview
        phase = state['phase']
        if phase in ('session', 'ending'):
            if self.dock is None and state.get('session'):
                count = len(state['session']['items']) + 2      # + 내 드라이브 · 구글
                ax, ay, aw, ah = work_area()
                width = min(max(560, DOCK_SLOT * count + DOCK_EXTRA), 1800, aw - 24)
                self.dock = webview.create_window(
                    TITLE, str(WEB_DIR / 'classroom-dock.html'), js_api=self.api,
                    width=width, height=DOCK_HEIGHT,
                    x=ax + (aw - width) // 2, y=ay + ah - DOCK_HEIGHT - 12,
                    frameless=True, easy_drag=False, resizable=False, background_color='#eef0f6')
                self.dock.events.shown += lambda w=self.dock: round_corners(w)
                self.close_mini()
                self.main.hide()
        elif self.dock is not None or self.drive is not None:
            for kind in list(self.popups):
                self.close_popup(kind)
            for window in (self.dock, self.drive, self.gtools):
                if window is not None:
                    try:
                        window.destroy()
                    except Exception:
                        pass
            self.dock = self.drive = self.gtools = None
            self.close_mini()
            self.lowered = False
            self.main.show()
            self.main.maximize()

    # 작은 위젯 — QR 창을 내리면(✕ · 작업 표시줄) 바탕화면 오른쪽 아래에 작게 남는다(2026-10-14 요청) -----------
    def show_mini(self):
        """항상 위가 아니다 — 바탕화면 위젯처럼 다른 창 아래에 깔린다. 작은 QR 로도 바로 연결된다."""
        import webview
        width, height = MINI_SIZE
        with self.lock:
            if self.mini is not None:
                self.mini.show()
                return
            ax, ay, aw, ah = work_area()
            self.mini = webview.create_window(
                TITLE, str(WEB_DIR / 'classroom-mini.html'), js_api=self.api, width=width, height=height,
                x=ax + aw - width - 16, y=ay + ah - height - 16,
                frameless=True, easy_drag=True, resizable=False, focus=False, background_color='#ffffff')
            mini = self.mini

            def shown(made=mini):
                round_corners(made)
                tool_window(made)

            def closed(made=mini):
                with self.lock:
                    if self.mini is made:
                        self.mini = None
            mini.events.shown += shown
            mini.events.closed += closed

    def lower(self):
        """QR 창이 내려졌다 — 위젯을 띄운다. 저절로 다시 띄우지는 않는다(위젯에 QR 이 있다, 2026-10-21 요청)"""
        self.lowered = True
        self.show_mini()

    def close_mini(self, *_):
        with self.lock:
            mini, self.mini = self.mini, None
        if mini is not None:
            try:
                mini.destroy()
            except Exception:
                pass

    def restore_main(self):
        self.lowered = False
        self.close_mini()
        self.main.restore()
        self.main.maximize()

    # 작은 창들 ---------------------------------------------------------------
    def _above_dock(self, width, height):
        """독 바로 위 가운데 자리(독이 없으면 화면 아래 가운데)"""
        ax, ay, aw, ah = work_area()
        dock = self.dock
        try:
            dx, dy, dw = dock.x, dock.y, dock.width          # pywebview 는 창 자리를 논리 픽셀로 준다
        except Exception:
            dx, dy, dw = ax, ay + ah - DOCK_HEIGHT - 12, aw
        x = max(ax + 8, min(dx + (dw - width) // 2, ax + aw - width - 8))
        return x, max(ay + 8, dy - height - 10)

    def _popup(self, kind, page, width, height, *, frameless=True, focus=True, title=TITLE, center=False):
        import webview
        with self.lock:
            window = self.popups.get(kind)
            if window is not None:
                window.evaluate_js('window.refresh && window.refresh()')
                window.show()
                return window
            if center:
                ax, ay, aw, ah = work_area()
                x, y = ax + (aw - width) // 2, ay + (ah - height) // 2
            else:
                x, y = self._above_dock(width, height)
            window = webview.create_window(title, str(WEB_DIR / page), js_api=self.api, width=width, height=height,
                                           x=x, y=y, frameless=frameless, easy_drag=False, resizable=False,
                                           on_top=True, focus=focus, background_color='#ffffff')
            if frameless:
                window.events.shown += lambda w=window: round_corners(w)

            def closed(made=window):
                with self.lock:
                    if self.popups.get(kind) is made:
                        del self.popups[kind]
            window.events.closed += closed
            self.popups[kind] = window
            return window

    def close_popup(self, kind):
        with self.lock:
            window = self.popups.pop(kind, None)
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass

    def popup_content(self, kind):
        if kind == 'toast':
            return dict(self.toast)
        if kind == 'dialog':
            d = self.dialog
            return {'token': d['token'], **d['opts']} if d else None
        return None

    def notify(self, text, error=False):
        """독 위에 알림 창 — 7초 뒤(오류는 12초) 저절로 닫힌다. 포커스는 가져가지 않는다."""
        if not text:
            return
        self.toast = {'id': self.toast['id'] + 1, 'text': text, 'error': error}
        made = self.toast['id']
        self._popup('toast', 'classroom-toast.html', 520, 116, focus=False)

        def hide():
            if self.toast['id'] == made:
                self.close_popup('toast')
        timer = threading.Timer(12 if error else 7, hide)
        timer.daemon = True
        timer.start()

    def ask(self, opts):
        """확인 창(화면 가운데) — 고를 때까지(최대 5분) 기다린다. 이미 떠 있으면 아니오."""
        import uuid
        with self.lock:
            if self.dialog is not None:
                return False
            self.dialog = {'token': uuid.uuid4().hex, 'event': threading.Event(), 'value': False,
                           'opts': {'title': str(opts.get('title') or '확인'), 'body': str(opts.get('body') or ''),
                                    'ok': str(opts.get('ok') or '확인'), 'cancel': str(opts.get('cancel') or '취소'),
                                    'danger': bool(opts.get('danger'))}}
            dialog = self.dialog
        self._popup('dialog', 'classroom-dialog.html', 480, 260, center=True)
        dialog['event'].wait(300)
        self.close_popup('dialog')
        with self.lock:
            self.dialog = None
        return dialog['value']

    def answer(self, token, value):
        d = self.dialog
        if d and d['token'] == token:
            d['value'] = value
            d['event'].set()

    def show_type(self):
        """휴대폰으로 구글 비밀번호 입력 — 화면 가운데 QR 창"""
        self._popup('type', 'classroom-type.html', 460, 640, center=True)

    def show_google(self):
        self._popup('google', 'classroom-google.html', 560, 580)

    def show_gtools(self, tab):
        """구글 수업 도구 창 — 크게(최대화). 이미 있으면 그 탭으로"""
        import webview
        with self.lock:
            self.gtools_pending = tab
            if self.gtools is not None:
                self.gtools.show()
                self.gtools.restore()
                self.gtools.maximize()
                self.gtools.evaluate_js(f'window.GTools && window.GTools.open({json.dumps(tab)})')
                return
            ax, ay, aw, ah = work_area()
            width, height = min(1280, aw - 40), min(820, ah - 40)
            self.gtools = webview.create_window(
                '구글 수업 도구 — ' + TITLE, str(WEB_DIR / 'classroom-gtools.html'), js_api=self.api,
                width=width, height=height, x=ax + (aw - width) // 2, y=ay + (ah - height) // 2,
                min_size=(720, 520), background_color='#f4f6fb')
            made = self.gtools
            made.events.shown += lambda: made.maximize()

            def closed(window=made):
                with self.lock:
                    if self.gtools is window:
                        self.gtools = None
                        self.gtools_full = False
            made.events.closed += closed

    def close_gtools(self):
        with self.lock:
            window, self.gtools = self.gtools, None
            self.gtools_full = False
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass

    def gtools_fullscreen(self, on):
        """슬라이드 발표 — 창을 화면 전체로(끝내면 되돌린다)"""
        window = self.gtools
        if window is None or self.gtools_full == on:
            return
        self.gtools_full = on
        try:
            window.toggle_fullscreen()
        except Exception:
            pass

    def show_drive(self, folder_id, name):
        import webview
        with self.lock:
            self.pending_drive = {'folder': folder_id, 'name': name}
            if self.drive is not None:
                self.drive.show()
                self.drive.restore()
                self.drive.evaluate_js(f'window.go && window.go({json.dumps(folder_id)}, {json.dumps(name)}, true)')
                return
            self.drive = webview.create_window(
                '드라이브 — ' + TITLE, str(WEB_DIR / 'classroom-drive.html'), js_api=self.api,
                width=1000, height=700, min_size=(560, 420), background_color='#f4f6fb')

            def closed(made=self.drive):
                with self.lock:
                    if self.drive is made:
                        self.drive = None
            self.drive.events.closed += closed


class SpaceWindows:
    """스페이스기전 화면 — 받은 세션을 창 저장소에 심고 연다. 수업이 끝나면 저장소를 비우고 닫는다."""

    def __init__(self):
        self.windows = []
        self.lock = threading.Lock()

    def open(self, path, session):
        import webview
        from core import web_login
        origin = web_login.ORIGINS['space']
        target = origin + (path if path.startswith('/') else '/')
        state = {'installed': False}
        window = webview.create_window('스페이스기전', target, js_api=None, width=1280, height=860,
                                       background_color='#f6f7fb', text_select=True, zoomable=True)

        def loaded():
            if state['installed'] or web_login.origin(window.get_current_url()) != origin:
                return
            state['installed'] = True
            if window.evaluate_js(web_login.install_script('space', session)) is True:
                window.load_url(target)
        window.events.loaded += loaded
        with self.lock:
            self.windows.append(window)

    def close(self):
        with self.lock:
            windows, self.windows = self.windows, []
        for window in windows:
            try:
                window.evaluate_js('try{localStorage.clear();sessionStorage.clear()}catch(e){};true')
            except Exception:
                pass
            try:
                window.destroy()
            except Exception:
                pass


def windows_shutting_down() -> bool:
    """Windows 가 꺼지거나 로그아웃하는 중인가(SM_SHUTTINGDOWN)"""
    try:
        return bool(ctypes.windll.user32.GetSystemMetrics(0x2000))
    except Exception:
        return False


def restart_after_crash(log) -> bool:
    """갑자기 죽었다 — 실행 파일이면 다시 켠다. 1분 안에 또 죽었으면 되풀이하지 않는다(무한 재시작 방지)."""
    import time
    if not getattr(sys, 'frozen', False):
        return False
    stamp = Path(log).with_name('last-crash.txt')
    try:
        if stamp.exists() and time.time() - float(stamp.read_text(encoding='utf-8') or 0) < 60:
            return False
        stamp.write_text(str(time.time()), encoding='utf-8')
        from core import child
        exe = Path(sys.executable)
        child.spawn([str(exe), '--autostart', '--wait-pid', str(os.getpid())], str(exe.parent), child.DETACHED)
        return True
    except Exception:
        return False


def main():
    import webview
    from core import classroom_link as link
    from core import classroom_setup as setup
    from core.classroom_controller import Controller
    from core import classroom_update

    setup.sweep_leftovers()
    try:
        from core import classroom_startup
        classroom_startup.ensure()          # 교실 PC 기본 = Windows 자동 실행(끈 것은 그대로)
    except Exception:
        pass
    spaces = SpaceWindows()
    controller = Controller(
        link.Client(), link.device_name,
        lambda handoff: setup.Session(handoff, open_space=spaces.open, close_space=spaces.close),
        idle_fn=classroom_update.idle_seconds)       # 밤·주말 쉬는 중 — 이 PC 를 만지면 다시 QR
    windows = Windows(None)
    api = Api(controller, link, windows)
    windows.api = api
    window = webview.create_window(TITLE, str(WEB_DIR / 'classroom.html'), js_api=api,
                                   width=1180, height=820, min_size=(360, 480), minimized=True,
                                   background_color='#f4f6fb', text_select=False)
    windows.main = window
    stopping = threading.Event()
    flags = {'closing': False, 'quit': False}

    def quit_app():
        """정말 끝낸다 — 수업 중이면 정리부터"""
        flags['quit'] = True
        if controller.state()['phase'] == 'session':
            controller.finish()
        stopping.set()
        windows.close_mini()
        window.destroy()
    windows.quit = quit_app
    # 자동 업데이트(데스크와 같은 서명 업데이트) — 받아 두기만 하고, 바꾸는 것은 아래 loop 가 «수업 중이 아니고 손 놓은 때»
    from core import classroom_update
    update = {'record': None, 'checker': None}
    update['checker'] = classroom_update.start_checker(lambda record: update.__setitem__('record', record),
                                                       classroom_update.log_to_file)
    windows.updates = update                 # 기기 설정의 [새 판 확인]·[지금 바꾸기](Api.check_update · install_update)

    def install_update():
        """받아 둔 새 판으로 지금 — 설치 모드를 띄우고 이 프로그램은 끝난다(새 판이 곧 다시 켜진다)"""
        record = update['record']
        if not record or not classroom_update.apply(record, classroom_update.log_to_file):
            return False
        flags['quit'] = True
        stopping.set()
        windows.close_mini()
        threading.Thread(target=window.destroy, daemon=True).start()
        return True
    windows.install_update = install_update

    def loop():
        # 켤 때는 내려 둔 채(2026-10-14 요청) — 작은 위젯만 오른쪽 아래에. 위젯·작업 표시줄로 열면 최대화된 QR 창
        windows.lower()
        shown = {'text': ''}
        while not stopping.is_set():
            delay = controller.step()
            try:
                state = controller.state()
                windows.arrange(state)
                # 수업 중 알림(드라이브 다시 연결·보관 로그인 문제 등)은 독 위 알림 창으로 — 같은 글은 한 번만
                session = state.get('session') or {}
                text = session.get('notice') or (state['notice'] if state['phase'] == 'session' else '')
                if text and text != shown['text']:
                    windows.notify(text)
                shown['text'] = text
                # 새 판: QR 화면(수업 없음)에서 2분 넘게 아무도 손대지 않을 때만 바꾼다 — 새 판이 곧 QR 로 다시 뜬다
                if update['record'] and state['phase'] in ('qr', 'offline', 'sleep') \
                        and classroom_update.idle_seconds() >= classroom_update.IDLE:
                    if classroom_update.apply(update['record'], classroom_update.log_to_file):
                        stopping.set()
                        windows.close_mini()
                        window.destroy()
                        return
                    update['record'] = None
            except Exception:
                pass
            stopping.wait(delay)

    def closing():
        # 항상 켜져 있게(2026-10-14 요청) — ✕ 는 끝내지 않고 내린다. 끝내기는 기기 설정의 «프로그램 끝내기»(quit_app).
        # 단 Windows 가 꺼지는 중이면 막지 않는다(막으면 «이 앱이 종료를 막고 있습니다»가 뜬다).
        if not flags['quit'] and not windows_shutting_down():
            threading.Thread(target=window.minimize, daemon=True).start()
            return False
        # 창을 닫아도 수업 자료·로그인을 남기지 않는다. 정리는 다른 스레드에서 — 여기(GUI 스레드)서
        # 스페이스기전 창의 evaluate_js 를 기다리면 서로를 기다려 멈춘다.
        if controller.state()['phase'] == 'session' and not flags['closing']:
            flags['closing'] = True

            def work():
                controller.finish()
                stopping.set()
                window.destroy()
            threading.Thread(target=work, daemon=True).start()
            return False
        stopping.set()
        threading.Thread(target=windows.close_mini, daemon=True).start()     # 위젯이 남으면 프로그램이 안 끝난다

    def minimized():
        # 수업 중에는 이 창이 숨고 독이 뜬다 — QR 화면을 내렸을 때만 작은 위젯
        if not flags['quit'] and controller.state()['phase'] in ('qr', 'offline'):
            windows.lower()

    def restored():
        # 켤 때 내려 둔 창은 «보통» 크기로 돌아온다 — 작업 표시줄로 열어도 최대화된 QR 로
        windows.close_mini()
        if windows.lowered:
            windows.lowered = False
            threading.Thread(target=window.maximize, daemon=True).start()

    window.events.closing += closing
    window.events.minimized += minimized
    window.events.restored += restored
    window.events.maximized += windows.close_mini
    webview.start(lambda: threading.Thread(target=loop, daemon=True).start(),
                  gui='edgechromium', private_mode=True,
                  icon=str(Path(__file__).parent / 'resources' / 'desk.ico'))
    stopping.set()


def run():
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from classroom_check import check
        check(Path(sys.argv[2]))
        return
    # 받아 둔 새 판이 설치 모드로 떴다 — 옛것이 끝나기를 기다려 제자리에 덮어쓰고 새 판을 띄운다(core/updater.py).
    # 잠금(뮤텍스)을 잡기 전에 한다: 옛것이 아직 잡고 있다.
    if '--install-update' in sys.argv:
        from core import classroom_update
        classroom_update.install_mode(sys.argv[1:])
        return
    # 죽은 옛것이 다시 켜 준 것이면 — 옛것이 한 번에 하나 잠금을 놓을 때까지 기다린다
    if '--wait-pid' in sys.argv:
        at = sys.argv.index('--wait-pid')
        if at + 1 < len(sys.argv) and sys.argv[at + 1].isdigit():
            from core import updater
            updater.wait_for(int(sys.argv[at + 1]), 30)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, MUTEX)
    if mutex and ctypes.get_last_error() == 183:
        if '--autostart' not in sys.argv:       # 자동 실행이 겹친 것이면 조용히 끝낸다
            ctypes.windll.user32.MessageBoxW(None, '스페이스기전 교실이 이미 켜져 있습니다.', TITLE, 64)
        kernel.CloseHandle(mutex)
        return
    try:
        from core import classroom_update
        # 받아 둔 새 판이 있으면 창을 띄우기 전에 바꾼다(설치 모드가 이것이 끝나기를 기다린다)
        if classroom_update.at_start(sys.argv[1:], classroom_update.log_to_file):
            return
        main()
    except Exception:
        from core.classroom_link import DATA_DIR
        log = Path(DATA_DIR) / 'startup-error.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding='utf-8')
        if restart_after_crash(log):          # 항상 켜져 있게 — 조용히 다시 켠다
            return
        ctypes.windll.user32.MessageBoxW(
            None, f'프로그램을 실행하지 못했습니다. Microsoft Edge WebView2 Runtime 설치를 확인해 주세요.\n\n오류 기록: {log}',
            TITLE, 16)
    finally:
        if mutex:
            kernel.CloseHandle(mutex)


if __name__ == '__main__':
    run()
