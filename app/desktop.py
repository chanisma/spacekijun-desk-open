"""Local HTML interface backed by the existing Python services."""
from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
import ctypes
import ctypes.wintypes
import json
import os
import re
import socket
import subprocess
import sys
import queue
import threading
import time

from core import cm_win32 as cm
from core import inbox, roster, secretstore, settings, sticky, supa_auth, udb, watcher, startup
from core import capture
from core import edition
from core import desk_message
from core import web_cache
# 페이지가 여는 새 창을 데스크 안으로 돌린다. 창을 만들기 전에 불러야 한다.
from core.web_popup import install as install_web_hooks

SPACEKIJUN_URL = 'https://spacekijun.lovable.app'
SEATON_URL = 'https://kijunseaton.netlify.app'
IDLE_WAIT = 0.25          # 할 일이 없을 때 쉬는 간격 (초). 브라우저는 건드리지 않는다
BEAT_EVERY = 2.0          # 창이 살아 있는지 확인하는 간격 (초)
KLEF_PUMP = 0.5           # 에듀파인 «바로보기»가 붙어 있을 때 페이지 부름을 받아 오는 간격 (초)
DEBUG_PORT = 9333         # 데스크 안 창에 Playwright 가 붙는 통로 (127.0.0.1 전용)
PUMP_URL = 'http://127.0.0.1/'   # 알림을 받아 오려고 한 번 묻는 자리. 받아 올 것이 거의 없다
POPUP_LIMIT = 12          # 페이지가 창을 끝없이 열어 화면을 덮는 것을 막는다
# 인증서를 쓰는 셋. 서로 링크로 오가고 인쇄·내려받기가 잦아 **설치된 Edge** 로 연다
# (2026-09-15 요청). 나머지(리로스쿨·AIEP·연수포털)는 데스크 안 창으로 연다.
EDGE_TARGETS = ('neis', 'eduptl', 'klef')
AIEP_URL = 'https://ai.jbedu.kr'
JBSTUDY_URL = 'https://www.jbstudy.kr'
STICKY_SIZE = (320, 340)  # 새 메모 창 크기 (Windows 스티커 메모와 비슷하게)
STICKY_LIMIT = 30         # 한꺼번에 띄울 수 있는 메모 창 수
WEB_DIR = Path(__file__).parent / 'web'
# 화면 파일(web/)을 내주는 pywebview 로컬 서버 자리 (2026-10-20). private_mode=False 이면 pywebview 는 늘
# 127.0.0.1:42001 을 쓰는데, 교사판·학생판이 한 PC 에서 함께 돌면 늦게 켠 쪽은 서버를 못 띄우고도 말없이
# **먼저 켠 쪽의 화면 파일**을 받아 쓴다 (학생판 독에 교사판 1.3.18 의 옛 아이콘 목록 — 이세계 사회인이 없던 일).
# 판마다 자리를 따로 두고, 이미 누가 잡고 있으면 그다음 빈 자리를 쓴다. 교사판은 예전 자리(42001) 그대로다
# — 자리(출처)가 바뀌면 그 창의 localStorage(패널의 마지막 보기)가 처음으로 돌아간다.
WEB_PORT = {'teacher': 42001, 'student': 42101}
DOCK_SIZE = (960, 200)    # 독 창의 첫 크기. 화면이 뜨면 dock.js 가 자리·방향에 맞춰 다시 잡는다
DOCK_ANCHORS = ('bottom', 'top', 'left', 'right')   # 독이 붙는 쪽. 좌우면 세로로 선다
DOCK_HANDLE_POLL = 0.5    # 손잡이 줄이 독을 따라가는지 다시 보는 간격 (초)
DOCK_ITEM_LIMIT = 64      # 숨길 수 있는 독 아이콘 id 수 상한
DOCK_ALWAYS = frozenset({'settings'})   # 숨길 수 없는 독 아이콘 — 교사판·학생판 모두 설정 (dock-items.js)
DOCK_REGION_RECTS = 8     # 독 창 모양을 이루는 사각형 수 상한 (판·말풍선·메뉴)
DOCK_REACH = 100_000      # 독 좌표로 받아 줄 범위 (여러 모니터를 이어도 이 안이다)
# 독에서 '제 창'으로 띄우는 데스크 화면들 (업무 홈은 데스크 본창이 맡는다)
DESK_PAGES = {'inbox': '쪽지함', 'notes': '스티커 메모', 'roster': '교직원 명부',
              'settings': '연결 및 설정'}
# 업무 홈 대시보드의 카드 하나만 담은 작은 창 ('card:today' 처럼 부른다)
DESK_CARDS = {'today': '오늘 시간표', 'week': '이번 주 일정', 'tasks': '나의 업무',
              'notices': '학교 공지', 'notifications': '최근 알림'}
DASHBOARD_FRESH = 60       # 학교 정보(대시보드)를 이만큼(초) 지나기 전에는 서버에 다시 묻지 않는다
DASHBOARD_PREFETCH = 120   # 미리 받아 두는 간격 (초) — 패널·업무 홈을 열자마자 보이게
# 키보드·마우스를 이만큼(초) 놓으면 «자리 비움» — 학교 정보 미리 받기·업무 홈 갱신·메모 동기화가 서버에
# 묻지 않고 쉰다. 데스크는 밤새·주말 내내 켜져 있어서, 이게 없으면 아무도 안 보는 화면이 서버 요청의
# 대부분을 만들었다 (2026-10-18 게이트웨이 로그 실측: 전체 요청의 88%, 새벽 3시에도 시간당 2,400건).
AWAY_AFTER = 10 * 60
MONTH_FRESH = 300          # 일정 패널의 달력 한 달치는 이만큼(초) 다시 묻지 않는다
# 독 아이콘을 누르면 독 위로 펼치는 정보 패널 (web/popover.html)
POPOVER_KEYS = ('today', 'week', 'tasks', 'notices', 'notifications', 'notes', 'inbox', 'captures', 'clips',
                'settings', 'agent', 'messages', 'automation')
CLASSROOM_URL = 'https://classroom.google.com'
SPACE_ROUTES = ('/', '/timetable', '/schedule', '/tasks', '/notifications', '/notices',
                '/classroom',                      # 교사판: 교실 세팅(교실 기기 QR 로 펼칠 반별 세팅)
                '/academy', '/tamagotchi', '/star-tower', '/planner')   # 학생판: 별빛 아카데미·다마고찌·별까지 쌓기·플래너
# 학생판 데스크 API 가 받는 일 — 이 밖(나이스·업무포털·에듀파인·인증서·쿨메신저·교직원 명부·알림 감시 등
# 교사만 쓰는 것)은 부르더라도 거절한다 (2026-10-12 요청). 화면에서 빼는 것만으로는 막았다고 할 수 없다.
STUDENT_ACTIONS = frozenset({
    'dashboard', 'dashboard_quick', 'dashboard_month', 'auth', 'startup', 'settings_panel', 'student_settings',
    'update_status', 'update_check', 'update_apply', 'update_test',      # update_test 는 관리자 계정만 켜진다 (2026-11-04)
    'open_space', 'open_seaton', 'open_riro', 'open_aiep', 'open_classroom', 'open_isekai3d',
    'student_account_save', 'student_account_forget',
    'dock_state', 'dock_place', 'dock_move', 'dock_layout', 'dock_region', 'dock_preview', 'dock_hide',
    'dock_items', 'dock_items_save', 'dock_hotkey', 'dock_hotkey_save',
    'popover_open', 'popover_close',
    'ranch_state', 'ranch_region', 'ranch_call', 'ranch_set', 'ranch_view',   # 별사이 목장 (2026-11-06)
    'msg_state', 'msg_directory', 'msg_send', 'msg_read', 'msg_image', 'msg_image_full', 'msg_image_open',
    'msg_request', 'msg_decide', 'msg_end',
    'capture', 'captures', 'capture_list', 'capture_open', 'capture_reveal', 'capture_folder',
    'capture_rename', 'capture_delete', 'capture_copy', 'capture_drag',
    'clips_list', 'clips_copy', 'clips_pin', 'clips_delete', 'clips_clear', 'clips_pause',
    'agent_state', 'agent_quick', 'agent_run', 'agent_settings', 'agent_favorite', 'agent_pick', 'agent_install',
    'term_info', 'term_list', 'term_read', 'term_write', 'term_resize', 'term_restart', 'term_reveal', 'term_new',
    'term_close', 'term_rename', 'term_events', 'term_events_clear', 'term_usage', 'term_chat', 'term_chat_image', 'term_output_open', 'term_team_set', 'term_window_close', 'term_show',
    'term_computer_answer', 'term_computer_list', 'term_computer_stop',
    'term_computer_options', 'term_computer_always', 'term_computer_resume',
    'term_peer_state', 'term_peer_set', 'term_peer_answer', 'term_own', 'term_own_send',          # 학생판에서는 '쓸 수 없음'만 답한다
    'term_external', 'term_snippets', 'term_snippets_save', 'term_link', 'term_paths', 'term_path_open', 'term_pick_files', 'term_complete', 'term_resident',
    'term_main', 'term_main_state', 'term_main_set', 'term_analysis_prompt',   # 메인의 할 일은 학생판에서 거절만 한다
    'term_requests', 'term_request_prompt', 'term_request_handed',           # 에이전트 작업 요청 (2026-11-11) — 학생판은 거절
    'term_memory', 'term_memory_remove', 'term_memory_skill', 'term_memory_skill_delete', 'term_memory_review',
    'term_memory_undo', 'term_memory_auto',                                  # 에이전트 기억 (2026-11-11, 헤르메스 방식)
    'term_knowledge', 'term_knowledge_add', 'term_knowledge_remove', 'term_knowledge_open', 'term_knowledge_reveal', 'term_skills', 'term_skill_favorite',
    'term_auth', 'term_login',    # 에이전트 로그인 안내 (2026-11-07)
    'term_cron_list', 'term_cron_save', 'term_cron_remove', 'term_cron_toggle', 'term_cron_run', 'term_cron_preview',
    'term_cron_runs', 'term_cron_answer'})            # 예약 업무는 교사판만 — 학생판에서는 처리 함수가 거절만 한다(_cron_scheduler)
AGENT_FAVORITES = 20      # 에이전트 터미널의 '자주 쓰는 폴더' 상한
RESIDENT_CHECK = 20       # 상주 에이전트를 확인하는 간격 (초)
MEMORY_CHECK = 60         # 밤 12시 지식 업데이트를 할 차례인지 보는 간격 (초)
SKILL_FAVORITES = 40      # 스킬 패널 즐겨찾기 상한
ROLE_TTL = 600            # 내 역할(관리자 여부)을 다시 묻는 간격 (초)
RESIDENT_REVIVE = 60      # 에이전트가 이만큼(초) 꺼져 있으면 되살린다 — 막 뜨는 중·잠깐의 /exit 에 서두르지 않게
AGENT_ASK_FRESH = 30      # 독을 누르고 이만큼(초) 안에 열린 패널만 '이 폴더에서 열까요?'를 묻는다
TERM_SIZE = (1120, 760)   # 데스크 안 에이전트 터미널 창의 첫 크기
CRON_ASK_WAIT = 180       # 에이전트가 만든 예약을 승인할지 묻고 기다리는 시간 (초) — 지나면 승인 대기로 저장
COMPUTER_ASK_WAIT = 120   # 에이전트가 앱을 다뤄도 되는지 사람에게 묻고 기다리는 시간 (초) — 지나면 거절
COMPUTER_BAR_SIZE = (460, 52)   # 화면 조작을 허락해 둔 동안 뜨는 '멈추기' 막대
COMPUTER_ALWAYS_LIMIT = 50      # '항상 허락'해 둘 수 있는 앱 수
PEER_ASK_WAIT = 120             # 다른 PC 에서 온 메시지를 넣어도 되는지 사람에게 묻고 기다리는 시간 (초) — 지나면 거절
PEER_TRUSTED_LIMIT = 100        # '이 사람은 항상' 허락해 둘 수 있는 사람 수
SNIPPET_LIMIT = 30        # 에이전트 터미널의 '자주 쓰는 말' 상한
SNIPPET_LENGTH = 4000     # 그 한 개의 글자 수 상한
UPDATE_FIRST = 5          # 켜고 새 판을 처음 확인하기까지 (초) — 켜자마자 확인하고 묻는다 (2026-10-26 요청)
CLIPS_DIR = Path(watcher.DATA_DIR) / 'clipboard'   # 클립보드 기록 (목록은 DPAPI 암호화, 그림은 PNG)
POPOVER_SIDES = ('top', 'bottom', 'left', 'right')
CAPTURE_DIR = Path(watcher.DATA_DIR) / 'captures'   # 캡처 보관함 — 평범한 폴더다
CAPTURE_PICK = 200        # 한 번에 끌거나 지울 수 있는 캡처 수
PAGE_TITLES = {**DESK_PAGES, **{f'card:{key}': title for key, title in DESK_CARDS.items()}}


# 🚨 이 파일이 부르는 Windows 함수는 **전용 DLL 객체**로 부른다. `ctypes.windll.*` 는 pywebview 와
#    함께 쓰는 객체라 거기에 argtypes 를 걸면 pywebview 의 창 옮기기까지 깨진다 (core/dock_handle.py).
_user32 = ctypes.WinDLL('user32')
_gdi32 = ctypes.WinDLL('gdi32')
_dwmapi = ctypes.WinDLL('dwmapi')


def on_ui(form, work, log=lambda *parts: None) -> None:
    """WinForms 창의 UI 스레드에서 `work` 를 돌린다 (기다리지 않는다).

    🚨 넘기는 함수는 **아무것도 돌려주면 안 된다.** `Func[Type]` 는 돌려준 값을 System.Type 으로
    바꾸려 하고, 못 바꾸면(예: `ShowWindow` 가 돌려준 숫자) .NET 예외 창을 띄우며 앱을 멈춘다
    (2026-10-11 사용자 보고 — 'value cannot be converted to Type'). UI 스레드에서 난 오류도
    같은 창을 띄우므로 여기서 받아 기록만 한다."""
    from System import Func, Type

    def run():
        try:
            work()
        except Exception as exc:
            log('화면 작업을 마치지 못했습니다:', exc)
    form.BeginInvoke(Func[Type](run))


DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE = 38, 1


class _MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_ulong), ('rcMonitor', ctypes.wintypes.RECT),
                ('rcWork', ctypes.wintypes.RECT), ('dwFlags', ctypes.c_ulong)]


def _work_area(monitor):
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    _user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MonitorInfo)]
    if not monitor or not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    work = info.rcWork
    return [work.left, work.top, work.right, work.bottom]


def screen_of(hwnd):
    """창이 놓인 모니터의 작업 영역 [왼, 위, 오른, 아래] (이 프로그램이 보는 화면 좌표). 모르면 None."""
    _user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    _user32.MonitorFromWindow.restype = ctypes.c_void_p
    return _work_area(_user32.MonitorFromWindow(hwnd, 0)) if hwnd else None     # 0: 없으면 없다


def screen_at(x, y):
    """그 점에 있는 모니터의 작업 영역 — 그 자리에 모니터가 없으면(뺐으면) None."""
    _user32.MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, ctypes.c_ulong]
    _user32.MonitorFromPoint.restype = ctypes.c_void_p
    return _work_area(_user32.MonitorFromPoint(ctypes.wintypes.POINT(int(x), int(y)), 0))


def clear_backdrop(hwnd) -> None:
    """창 뒤 시스템 배경(Mica)을 끈다. Windows 10 에는 없는 속성이라 실패해도 그냥 둔다."""
    none = ctypes.c_int(DWMSBT_NONE)
    _dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(none), ctypes.sizeof(none))


def web_port(first: int, tries: int = 20) -> int:
    """first 부터 비어 있는 127.0.0.1 포트. 다 차 있으면 Windows 가 고른 빈 포트 — 남의 서버에는 붙지 않는다."""
    for port in [*range(first, first + tries), 0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                continue
            return probe.getsockname()[1]
    raise OSError('화면 파일을 내줄 빈 포트가 없습니다.')


class DesktopAPI:
    def __init__(self):
        self._lock = threading.RLock()
        self._logs = deque(maxlen=120)
        self._watcher = watcher.Watcher(log=self._log)
        self._watcher.on_message = self._coolmsg_received   # 메인 상주 에이전트의 쪽지 분석 (core/resident_tasks.py)
        self._resident_analyst = None
        self._cron = None               # 예약 업무 (core/agent_cron.py, 2026-11-07) — 교사판만
        self._logins: dict = {}         # 도구 → 로그인 창을 띄운 때 (로그인 안내 화면)
        self._role_cache = None        # (역할, 확인한 때) — 관리자 테스트 판
        self._ranch_role_asking = False   # 목장용 역할 확인이 뒤에서 도는 중
        self._auth_pending = False
        self._portals = set()
        self._portal_status = {}
        self._portal_workers = set()
        self._browser_jobs: queue.Queue = queue.Queue()
        self._browser_worker = None
        self._neis_session = None      # 도우미 큐. 나이스 창이 열려 있을 때만 있다
        self._klef_lookup = None       # 에듀파인 «바로보기» 조회 (core/klef_overlay.DocLookup)
        self._service_windows = {}     # 업무시스템별 데스크 안 창
        self._tray = None              # 학생판 알림(로그인 실패 등)을 띄울 트레이 아이콘
        self._popups = []              # 페이지가 스스로 연 창들 (업무포털 → 나이스 같은)
        self._shutdown = threading.Event()
        self._supervisor = None
        self._watch_requested = False
        self._space_window = None
        self._seaton_window = None
        self._isekai3d_window = None        # 이세계 사회인 (2026-10-19 요청) — 독의 게임 창과 그 로컬 서버
        self._isekai3d_server = None
        from core.web_login import WebLogin
        self._web_login = WebLogin(self._log)
        self._desk_window = None
        self._dock_window = None
        self._dock_creating = False    # 독 창을 만드는 중 — create_window 는 잠금 밖에서 부른다 (_show_dock)
        self._page_windows = {}        # 독에서 연 데스크 화면 → 그 창
        self._dock_hwnd = None         # 독 창 핸들 (독 UI 스레드에서 적어 둔다)
        self._theme_watched = False    # Windows 테마가 바뀌면 유리 창 배경을 다시 끈다 (_dock_chrome)
        self._dock_shelf = None        # 독 판 자리 — 창 안 좌표 [x, y, 너비, 높이] (논리 픽셀)
        self._dock_anchor = 'bottom'
        self._dock_handle = None       # 독이 가려졌을 때 띄우는 손잡이 줄 (core/dock_handle.py)
        # 별사이 목장 (학생판, 2026-11-06) — 독 위 띠 창 (core/ranch.py)
        self._ranch_window = None
        self._ranch_hwnd = None
        self._ranch_creating = False
        self._ranch_spot = None        # 마지막으로 놓은 (x, y, 너비, 높이) — 같으면 다시 옮기지 않는다
        self._ranch_mode = None        # 'dock'(독 위) · 'desk'(바탕화면 아래)
        self._ranch_ratio = None       # 목장 화면 CSS 1px 의 실제 픽셀 수
        self._ranch_length = 0         # 목장 길이 (CSS px) — 화면이 알려 준다
        self._ranch_rects = None       # 화면이 마지막으로 알려 준 누를 자리
        self._ranch_view = None        # «화면» 설정 (core/ranch.py clean_view) — 너비·가로 위치·높이·크기·항상 위
        self._ranch_zoom = 2           # 지금 그림 1화소의 실제 픽셀 (ranch.place)
        self._ranch_top = None         # 마지막으로 입힌 «항상 위»
        self.ranch_enabled = False
        self._dock_handle_job = None
        self._dock_moving = False      # 독을 끌거나 접었다 펴는 중
        self._automation_job = None     # 자동화 업무에 필요한 프로그램 설치 창 (프로세스, 이름들) — _automation_prepare
        self._automation_then_open = False
        self._mcp_job = None            # SPACEKIJUN 인증 창 (프로세스, 에이전트) — _automation_mcp_connect
        self._mcp_seen = {}             # 에이전트 → (시각, 상태) — `mcp get` 은 서버에 붙어 보느라 몇 초 걸린다
        self._dock_ratio = None        # 독 화면의 CSS 1px 이 실제 몇 픽셀인가 — dock.js 의 devicePixelRatio (_dock_scales)
        self._dock_preview = None      # 끌어 화면 끝에 닿았을 때 놓일 자리 미리보기 (core/dock_handle.py)
        self._popover_window = None    # 독 위로 펼치는 정보 패널 창 (한 번 만들어 두고 숨겼다 보인다)
        self._popover_request = None   # 패널 창이 화면을 다 불러오면 보일 내용
        self._popover_ready = False    # 패널 화면을 다 불러왔나
        self._popover_creating = False # 패널 창을 만드는 중 (_popover_create)
        self._dash_cache = None        # (받은 시각, 계정, 학교 정보) — 미리 받아 둔 대시보드
        self._month_cache = {}         # (계정, 'YYYY-MM') → (받은 시각, 달력) — 일정 패널의 달력
        self._clips = None             # 클립보드 기록 (core/clipboard_history.py) — 켤 때 연다
        self._hotkey = None            # 가려진 독을 부르는 전역 단축키 (core/hotkey.py)
        self._foreground = None        # 이 프로그램이 아닌 마지막 앞 창 (core/active_folder.py) — 에이전트 터미널
        self._agent_asking = None      # (폴더, 때) — 독을 눌러 '이 폴더에서 열까요?'를 물을 차례
        self._terms = None             # 데스크 안 에이전트 터미널 세션들 (core/agent_term.py) — 처음 열 때 만든다
        self._term_window = None       # 에이전트 작업 공간 창 (에이전트 여럿이 한 창에)
        self._term_leave = None        # 창을 닫을 때 고른 것 — 'keep'(켜 둔 채) · 'stop'(모두 끔) · None(아직 안 물음)
        self._term_ready = False       # 그 창이 화면을 다 불러왔나
        self._term_focus = None        # 창이 뜨면 앞에 둘 세션
        self._term_bridge = None       # 에이전트끼리 서로를 보는 중계 (core/agent_bridge.py)
        self._term_asks = {}           # 화면 조작 허락을 묻는 중 — 요청 id → {'event', 'allow'}
        self._term_peer = None         # 다른 PC 의 에이전트와 메시지 (core/agent_peer.py) — 교사판만
        self._cron_asks = {}           # 에이전트가 만든 예약을 승인할지 묻는 중 — 요청 id → {'event', 'answer'}
        self._term_peer_asks = {}      # 다른 PC 메시지를 넣을지 묻는 중 — 요청 id → {'event', 'answer', 'sender'}
        self._term_bar = None          # 화면 조작을 허락해 둔 동안 늘 위에 뜨는 '멈추기' 막대
        self._updater = None           # 새 판 확인·받기 (core/updater.py, 실행 파일로 돌 때만)
        self._update = None            # 받아 둔 새 판 — 바꿀지 묻는다
        self._quit_for_update = None   # 새 판을 띄운 뒤 이 프로그램을 끝내는 손 (main 이 넣는다)
        self._update_job = None        # 손으로 누른 업데이트 확인 (설정·트레이)
        self._update_asked = set()     # 이번에 켜 둔 동안 바꿀지 물은 판 — 같은 판은 한 번만 묻는다
        self._update_note = ''         # 그 결과 — 설정 화면에 보인다
        self._update_failed = False
        self._desk_tray = None         # 교사판 트레이 아이콘 — 손으로 누른 업데이트의 결과를 알린다
        self._clip_recorder = None
        self._dash_fetching = threading.Lock()   # 서버에는 한 번에 한 번만 묻는다
        self._dash_prefetcher = None
        # 데스크 메시지 (학생 ↔ 선생님, core/desk_message.py) — 안 읽은 수는 독 배지, 새로 온 것은 트레이 알림
        self._msg_unread = 0
        self._msg_seen = None          # (계정, 이미 알린 메시지 id 들)
        self._msg_directory = None     # (계정, 받은 때, 주소록)
        self._ui_ready = threading.Event()   # 화면(WebView2)이 실제로 그려졌다 — 안 되면 startup-hang.log
        self._realtime = None          # 새 메시지를 바로 받는 연결 (core/realtime.py)
        self._req_seen = None          # (계정, 이미 알린 작업 요청 id 들) — core/agent_request.py
        self._memory = None            # 에이전트 기억 저장소 (core/agent_memory.Store)
        self._memory_review = None     # 밤 12시 지식 업데이트 (core/agent_memory.Review)
        self._capture_window = None    # 캡처 보관함 창
        self._capture_job = None       # Windows 캡처 화면에서 그림을 기다리는 일꾼
        self._capture_fresh = None     # 막 찍은 캡처 — 보관함이 뜨면 골라 보여 준다
        self._sticky_windows = {}      # 메모 id → 메모 창
        self._sticky_path = Path(watcher.DATA_DIR) / 'sticky-windows.json'
        self._sticky_layout = self._read_sticky_layout()
        self._preferences_path = Path(watcher.DATA_DIR) / 'desktop-preferences.json'
        preferences = self._read_preferences()
        self._watcher.use_summary = bool(preferences.get('summary', True))
        self._watcher.show_body = bool(preferences.get('body', True))
        self.dock_enabled = bool(preferences.get('dock', False))
        self.ranch_enabled = bool(preferences.get('ranch', True))   # 보일지는 _ranch_allowed(학생판 관리자)가 정한다
        self._ranch_view = preferences.get('ranch_view')
        self._dock_layout = self._valid_dock_layout(preferences.get('dock_layout'))
        self._dock_hidden = self._valid_dock_hidden(preferences.get('dock_hidden')) or []
        self._log('데스크가 준비되었습니다.')

    def _reconcile_watch(self):
        if edition.STUDENT:
            return                      # 학생판은 쿨메신저 쪽지를 감시하지 않는다
        with self._lock:
            connected = bool(supa_auth.whoami()) and not self._shutdown.is_set()
            if connected and not self._watcher.running:
                self._watcher.start()
                self._watch_requested = True
            elif not connected and self._watch_requested:
                self._watcher.stop()
                self._watch_requested = False

    def _start_supervisor(self):
        if self._supervisor:
            return
        def supervise():
            while not self._shutdown.is_set():
                try:
                    self._reconcile_watch()
                except Exception as exc:
                    self._log('자동 감시 시작 실패 (10초 후 재시도):', exc)
                self._shutdown.wait(10)
        self._supervisor = threading.Thread(target=supervise, daemon=True, name='desk-auto-watch')
        self._supervisor.start()

    def _close(self):
        self._shutdown.set()
        if self._cron:
            self._cron.stop()
        if self._terms:
            self._terms.freeze()         # 켜 둔 에이전트 목록을 남긴다 — 다시 켜면 그 대화로 연다 (아래 close_all 이 지우지 않게)
        if self._clip_recorder:
            self._clip_recorder.stop()
        if self._hotkey:
            self._hotkey.stop()
        if self._foreground:
            self._foreground.stop()
        if self._updater:
            self._updater.stop()
        self._web_login.cancel()
        with self._lock:
            self._watcher.stop()
            self._watch_requested = False
            space_window = self._space_window
            seaton_window = self._seaton_window
            isekai3d_window = self._isekai3d_window
            self._space_window = None
            self._seaton_window = None
            self._isekai3d_window = None
            services = list(self._service_windows.values()) + list(self._popups)
            if self._ranch_window:
                services.append(self._ranch_window)
            self._ranch_window, self._ranch_hwnd = None, None
            # 메모 창은 '열려 있던 것'으로 기억해 둔다. 다음 실행에 다시 띄운다
            services += list(self._sticky_windows.values())
            services += list(self._page_windows.values())
            if self._term_window:
                services.append(self._term_window)
            self._term_window, self._term_ready = None, False
            if self._popover_window:
                services.append(self._popover_window)
            self._popover_window = None
            if self._capture_window:
                services.append(self._capture_window)
            self._capture_window = None
            if self._dock_window:
                services.append(self._dock_window)
            for overlay in (self._dock_handle, self._dock_preview):
                if overlay:
                    try:
                        overlay.close()
                    except Exception:
                        pass
            self._dock_handle = self._dock_preview = None
            self._dock_window = None
            self._page_windows.clear()
            self._sticky_windows.clear()
            self._save_sticky_layout()
            self._service_windows.clear()
            self._popups.clear()
        # 🚨 **창보다 일꾼을 먼저 보낸다.** 창을 먼저 부수면 붙어 있던 Playwright 가
        #    허공을 잡고 `TargetClosedError` 를 뱉는다. 일꾼은 `_shutdown` 을 보고 스스로
        #    연결을 끊고 나온다.
        with self._lock:
            workers = list(self._portal_workers)
        deadline = time.monotonic() + 2
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=max(0, deadline - time.monotonic()))
        if space_window:
            space_window.destroy()
        if seaton_window:
            seaton_window.destroy()
        if isekai3d_window:
            isekai3d_window.destroy()
        if self._isekai3d_server:
            self._isekai3d_server.stop()
        if self._terms:
            self._terms.close_all()       # 에이전트·node 까지 함께 끝낸다 (창이 닫히기 전에 — 고아 프로세스가 남지 않게)
        if self._term_bridge:
            self._term_bridge.stop()
        if self._term_peer:
            self._term_peer.stop()            # 목록에서는 30초 안에 저절로 빠진다
        for window in services:
            # 업무시스템 창도 데스크 것이다. 데스크를 끝내면 함께 닫는다.
            try:
                window.destroy()
            except Exception:
                pass

    def _log(self, *parts):
        with self._lock:
            self._logs.append({'time': datetime.now().strftime('%H:%M:%S'),
                               'text': ' '.join(map(str, parts))})

    def call(self, action, payload=None):
        """Explicit allowlist; never expose credentials or arbitrary Python access."""
        handlers = self._handlers()
        try:
            if action not in handlers:
                raise ValueError('지원하지 않는 작업입니다.')
            if edition.STUDENT and action not in STUDENT_ACTIONS:
                raise ValueError('학생용에서는 쓸 수 없는 기능입니다.')
            if payload is not None and not isinstance(payload, dict):
                raise ValueError('요청 형식이 올바르지 않습니다.')
            return {'ok': True, 'data': handlers[action](payload or {})}
        except Exception as exc:
            message = str(exc)
            self._log('오류:', message)
            return {'ok': False, 'error': message}

    def _handlers(self) -> dict:
        """화면이 부를 수 있는 일 전부 (이름 → 처리 함수). 학생판은 이 가운데 STUDENT_ACTIONS 만."""
        return {
            'dashboard': self._dashboard, 'dashboard_quick': self._dashboard_quick,
            'dashboard_month': self._dashboard_month, 'state': self._state,
            'update_status': self._update_status, 'update_check': self._update_check, 'update_test': self._update_test,
            'update_apply': self._update_apply,
            'clips_list': self._clips_list, 'clips_copy': self._clips_copy, 'clips_pin': self._clips_pin,
            'clips_delete': self._clips_delete, 'clips_clear': self._clips_clear, 'clips_pause': self._clips_pause, 'inbox': lambda p: inbox.timeline(60),
            'roster': lambda p: roster.roster(), 'sync_roster': self._sync_roster,
            'alias': self._alias, 'save_credentials': self._save_credentials,
            'credential_settings': self._credential_settings,
            'options': self._options, 'auth': self._auth, 'portal': self._portal,
            'open_space': self._open_space, 'check_cm': self._check_cm,
            'open_aiep': self._open_aiep,
            'open_jbstudy': self._open_jbstudy,
            'open_classroom': self._open_classroom,
            'settings_panel': self._settings_panel,
            'student_settings': self._settings_panel,   # 예전 이름 — 옛 화면 파일이 부른다 (1.0.7 까지)
            'student_account_save': self._student_account_save,
            'student_account_forget': self._student_account_forget,
            'open_seaton': self._open_seaton,
            'open_isekai3d': self._open_isekai3d,
            'open_riro': self._open_riro,
            'save_riro': self._save_riro,
            'save_aiep': self._save_aiep,
            'save_jbstudy': self._save_jbstudy,
            'disconnect': self._disconnect,
            'startup': self._startup,
            'coolmsg_account': self._coolmsg_account,
            'browser_choice': self._browser_choice,
            'prepare_cm': self._prepare_cm,
            'sticky_list': lambda p: sticky.notes(),
            'sticky_get': lambda p: sticky.get(p),
            'away': self._away,
            'sticky_create': self._sticky_create,
            'sticky_update': self._sticky_update,
            'sticky_delete': self._sticky_delete,
            'sticky_open': self._sticky_open,
            'sticky_close': self._sticky_close,
            'sticky_pin': self._sticky_pin,
            'show_notes': self._show_notes,
            'open_page': self._open_page,
            'dock_state': self._dock_state,
            'dock_place': self._dock_place,
            'dock_move': self._dock_move,
            'dock_layout': self._dock_save_layout,
            'dock_region': self._dock_region,
            'dock_preview': self._dock_preview_show,
            'ranch_state': self._ranch_state,
            'ranch_region': self._ranch_region,
            'ranch_call': self._ranch_call,
            'ranch_set': self._ranch_set,
            'ranch_view': self._ranch_set_view,
            'dock_items': self._dock_items,
            'dock_items_save': self._dock_items_save,
            'dock_hotkey': self._dock_hotkey,
            'dock_hotkey_save': self._dock_hotkey_save,
            'popover_open': self._popover_open,
            'popover_close': self._popover_close,
            'sticky_resize': self._sticky_resize,
            'open_link': self._open_link,
            'capture': self._capture_start,
            'captures': self._captures_show,
            'capture_list': self._capture_list,
            'capture_open': self._capture_open,
            'capture_reveal': self._capture_reveal,
            'capture_folder': self._capture_folder,
            'capture_rename': self._capture_rename,
            'capture_delete': self._capture_delete,
            'capture_copy': self._capture_copy,
            'capture_drag': self._capture_drag,
            'dock_hide': lambda p: self.set_dock(False),
            'agent_state': self._agent_state,
            'agent_quick': self._agent_quick,
            'agent_run': self._agent_run,
            'agent_settings': self._agent_settings,
            'agent_favorite': self._agent_favorite,
            'agent_pick': self._agent_pick,
            'agent_install': self._agent_install,
            'term_info': self._term_info,
            'term_list': self._term_list,
            'term_new': self._term_new,
            'term_close': self._term_close,
            'term_rename': self._term_rename,
            'term_window_close': self._term_window_close,
            'term_resident': self._term_resident,
            'term_skills': self._term_skills,
            'term_skill_favorite': self._term_skill_favorite,
            'term_main': self._term_main,
            'term_main_state': self._term_main_state,
            'term_main_set': self._term_main_set,
            'term_analysis_prompt': self._term_analysis_prompt,
            'term_requests': self._term_requests,
            'term_memory': self._term_memory,
            'term_memory_remove': self._term_memory_remove,
            'term_memory_skill': self._term_memory_skill,
            'term_memory_skill_delete': self._term_memory_skill_delete,
            'term_memory_review': self._term_memory_review,
            'term_memory_undo': self._term_memory_undo,
            'term_memory_auto': self._term_memory_auto,
            'term_request_prompt': self._term_request_prompt,
            'term_request_handed': self._term_request_handed,
            'term_knowledge': self._term_knowledge,
            'term_cron_list': self._term_cron_list,
            'term_cron_save': self._term_cron_save,
            'term_cron_remove': self._term_cron_remove,
            'term_cron_toggle': self._term_cron_toggle,
            'term_cron_run': self._term_cron_run,
            'term_cron_preview': self._term_cron_preview,
            'term_cron_runs': self._term_cron_runs,
            'term_cron_answer': self._term_cron_answer,
            'term_auth': self._term_auth,
            'term_login': self._term_login,
            'term_knowledge_add': self._term_knowledge_add,
            'term_knowledge_remove': self._term_knowledge_remove,
            'term_knowledge_open': self._term_knowledge_open,
            'term_knowledge_reveal': self._term_knowledge_reveal,
            'term_show': self._term_show_kept,
            'term_events': self._term_events,
            'term_events_clear': self._term_events_clear,
            'term_usage': self._term_usage,
            'term_chat': self._term_chat,
            'term_chat_image': self._term_chat_image,
            'term_output_open': self._term_output_open,
            'term_team_set': self._term_team_set,
            'term_computer_answer': self._term_computer_answer,
            'term_computer_list': self._term_computer_list,
            'term_computer_stop': self._term_computer_stop,
            'term_computer_options': self._term_computer_options,
            'term_computer_always': self._term_computer_always,
            'term_computer_resume': self._term_computer_resume,
            'term_peer_state': self._term_peer_state,
            'term_own': self._term_own, 'term_own_send': self._term_own_send,
            'term_peer_set': self._term_peer_set,
            'term_peer_answer': self._term_peer_answer,
            'term_read': self._term_read,
            'term_write': self._term_write,
            'term_resize': self._term_resize,
            'term_restart': self._term_restart,
            'term_reveal': self._term_reveal,
            'term_external': self._term_external,
            'term_snippets': self._term_snippets,
            'term_snippets_save': self._term_snippets_save,
            'term_link': self._open_link,
            'term_paths': self._term_paths,
            'term_path_open': self._term_path_open,
            'term_pick_files': self._term_pick_files,
            'term_complete': self._term_complete,
            'automation_state': self._automation_state,
            'automation_open': self._automation_open,
            'automation_install': self._automation_install,
            'automation_settings': self._automation_settings,
            'automation_skill': self._automation_skill,
            'automation_prepare': self._automation_prepare_now,
            'automation_mcp_state': self._automation_mcp_state,
            'automation_mcp_connect': self._automation_mcp_connect,
            'automation_mcp_disconnect': self._automation_mcp_disconnect,
            'automation_mcp_manage': self._automation_mcp_manage,
            'msg_state': self._msg_state,
            'msg_directory': self._msg_directory_get,
            'msg_send': self._msg_send,
            'msg_request': self._msg_request,
            'msg_decide': self._msg_decide,
            'msg_end': self._msg_end,
            'msg_read': self._msg_read,
            'msg_image': self._msg_image,
            'msg_image_open': self._msg_image_open,
            'msg_image_full': self._msg_image_full,
        }

    # ── 에이전트 터미널 ─────────────────────────────────────────
    # 지금 보던 창의 폴더(여럿이면 고른다)나 자주 쓰는 폴더에서 Claude Code·Codex 를 새 터미널로 연다
    # (2026-10-13 요청). 권한 묻지 않기(--dangerously-skip-permissions 등)는 설정으로 켠다. 설치되어
    # 있지 않으면 설치 창을 띄운다. 폴더 찾기는 core/active_folder.py, 띄우기는 core/agent.py.
    def _start_foreground(self):
        from core import active_folder
        with self._lock:
            if self._foreground is None:
                self._foreground = active_folder.Tracker()
        self._foreground.start()

    def _agent_choice(self) -> tuple[str, bool]:
        from core import agent
        preferences = self._read_preferences()
        tool = preferences.get('agent_tool')
        return (tool if tool in agent.TOOLS else 'claude'), preferences.get('agent_skip') is True

    def _agent_embedded(self) -> bool:
        """데스크 안 터미널로 여나 (정하지 않았으면 그렇다). 끄면 예전처럼 Windows Terminal·명령 창으로."""
        return self._read_preferences().get('agent_embed') is not False

    def _agent_open(self, tool: str, folder: str, skip: bool, remote: str = '', extra: tuple = ()) -> str:
        """설정대로 데스크 안 터미널이나 바깥 터미널로 연다. 돌려주는 것은 화면에 보일 한 줄."""
        from core import agent
        if not self._agent_embedded():
            return agent.launch(tool, folder, skip, Path(watcher.DATA_DIR), remote, extra)
        try:
            return self._term_open(tool, folder, skip, remote, extra)
        except ImportError as exc:      # pywinpty 가 없는 실행 환경 — 바깥 터미널로라도 연다
            self._log('데스크 안 터미널을 쓸 수 없어 바깥 터미널로 엽니다:', exc)
            return agent.launch(tool, folder, skip, Path(watcher.DATA_DIR), remote, extra)

    def _agent_favorites(self) -> list:
        favorites = self._read_preferences().get('agent_folders')
        if not isinstance(favorites, list):
            return []
        return [path for path in favorites if isinstance(path, str)][:AGENT_FAVORITES]

    @staticmethod
    def _agent_folder(value) -> str:
        """화면이 보낸 폴더 — 실제로 있는 절대 경로 폴더만."""
        if not isinstance(value, str) or not value or len(value) > 1024 or '\x00' in value:
            raise ValueError('폴더 형식이 올바르지 않습니다.')
        spot = Path(value)
        if not spot.is_absolute() or not spot.is_dir():
            raise ValueError('폴더를 찾을 수 없습니다. 옮기거나 지웠는지 확인해 주세요.')
        return os.path.normpath(str(spot))

    def _agent_active(self) -> dict:
        from core import active_folder
        hwnd = self._foreground.last if self._foreground else None
        try:
            return active_folder.folders_of(hwnd)
        except Exception as exc:
            self._log('지금 보던 창의 폴더를 찾지 못했습니다:', exc)
            return {'app': '', 'title': '', 'folders': []}

    def _agent_state(self, _):
        from core import active_folder, agent
        tool, skip = self._agent_choice()
        active = self._agent_active()
        favorites = self._agent_favorites()
        try:
            explorer = active_folder.open_explorer_folders(skip=active['folders'] + favorites)
        except Exception:
            explorer = []
        with self._lock:                         # 독을 왼쪽 클릭해 막 물어보기로 했으면 한 번만 싣는다
            asking, self._agent_asking = self._agent_asking, None
        ask = None
        if asking and time.monotonic() - asking[1] < AGENT_ASK_FRESH and os.path.isdir(asking[0]):
            ask = {'path': asking[0], 'name': Path(asking[0]).name or asking[0]}
        return {'tools': agent.tools(), 'tool': tool, 'skip': skip, 'embed': self._agent_embedded(),
                'askOn': self._read_preferences().get('agent_ask') is not False, 'ask': ask, 'active': active,
                'kept': self._term_kept(), 'rc': None if edition.STUDENT else self._automation_rc(),   # 원격 제어 — 교사판(자동화 업무)만
                'favorites': [{'path': path, 'name': Path(path).name or path, 'exists': os.path.isdir(path)}
                              for path in favorites],
                'explorer': explorer}

    def _agent_launch(self, folder: str) -> str:
        tool, skip = self._agent_choice()
        message = self._agent_open(tool, folder, skip)
        self._log(message)
        return message

    def _agent_quick(self, _):
        """독 아이콘을 눌렀다 — 지금 보던 창의 폴더가 **하나**면 그 폴더에서 열지 패널에서 묻는다 (2026-10-25 요청).
        '앞으로 묻지 않기'를 골랐으면 곧바로 연다. 폴더가 없거나 여럿이거나 설치 전이면 패널(설정·폴더 고르기)."""
        from core import agent
        tool, _skip = self._agent_choice()
        # 켜 둔 에이전트가 있다 — 새로 열지 않고 에이전트 터미널부터 (2026-10-25 창만 닫은 것, 2026-10-30 창이 열려 있어도·상주도).
        # 다른 폴더에서 새로 열려면 오른쪽 클릭(패널).
        if self._agent_embedded() and self._terms and self._terms.alive():
            return {'launched': True, 'message': self._term_show_kept()}
        folders = self._agent_active()['folders']
        with self._lock:
            self._agent_asking = None
        if len(folders) != 1 or not agent.find(tool):
            return {'launched': False}
        if self._read_preferences().get('agent_ask') is not False:
            with self._lock:
                self._agent_asking = (folders[0], time.monotonic())   # 곧 열릴 패널이 위에 묻는다 (_agent_state)
            return {'launched': False, 'ask': True}
        return {'launched': True, 'message': self._agent_launch(folders[0])}

    def _agent_run(self, payload):
        return self._agent_launch(self._agent_folder(payload.get('folder')))

    def _agent_settings(self, payload):
        from core import agent
        changes = {}
        if 'tool' in payload:
            if payload['tool'] not in agent.TOOLS:
                raise ValueError('지원하지 않는 에이전트입니다.')
            changes['agent_tool'] = payload['tool']
        if 'skip' in payload:
            if not isinstance(payload['skip'], bool):
                raise ValueError('설정 형식이 올바르지 않습니다.')
            changes['agent_skip'] = payload['skip']
        if 'embed' in payload:
            if not isinstance(payload['embed'], bool):
                raise ValueError('설정 형식이 올바르지 않습니다.')
            self._save_preferences(agent_embed=payload['embed'])
            if not changes:
                return '데스크 안 터미널로 엽니다.' if payload['embed'] else 'Windows Terminal(없으면 명령 창)로 엽니다.'
        if 'ask' in payload:
            if not isinstance(payload['ask'], bool):
                raise ValueError('설정 형식이 올바르지 않습니다.')
            self._save_preferences(agent_ask=payload['ask'])
            if not changes:
                return '독을 누르면 먼저 물어봅니다.' if payload['ask'] else '앞으로 묻지 않고 보던 폴더에서 바로 엽니다.'
        if not changes:
            raise ValueError('바꿀 설정이 없습니다.')
        self._save_preferences(**changes)
        tool, skip = self._agent_choice()
        label = agent.TOOLS[tool]['label']
        return f'{label} · 권한 묻지 않기 켬' if skip else f'{label} · 권한을 물어 가며 실행'

    def _agent_favorite(self, payload):
        """자주 쓰는 폴더에 넣거나 뺀다. 뺄 때는 지금 없는 폴더도 뺄 수 있다."""
        on = payload.get('on')
        if not isinstance(on, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        value = payload.get('folder')
        with self._lock:
            favorites = self._agent_favorites()
            if on:
                folder = self._agent_folder(value)
                if any(os.path.normcase(path) == os.path.normcase(folder) for path in favorites):
                    return '이미 자주 쓰는 폴더에 있습니다.'
                if len(favorites) >= AGENT_FAVORITES:
                    raise ValueError(f'자주 쓰는 폴더는 {AGENT_FAVORITES}개까지 둘 수 있습니다.')
                favorites.append(folder)
            else:
                if not isinstance(value, str):
                    raise ValueError('폴더 형식이 올바르지 않습니다.')
                favorites = [path for path in favorites if os.path.normcase(path) != os.path.normcase(value)]
            self._save_preferences(agent_folders=favorites)
        return '자주 쓰는 폴더에 넣었습니다.' if on else '자주 쓰는 폴더에서 뺐습니다.'

    def _agent_pick(self, _):
        """폴더 고르기 창 — 고른 폴더를 자주 쓰는 폴더에 넣는다."""
        import webview
        with self._lock:
            window = self._popover_window or self._dock_window
        if window is None:
            raise RuntimeError('독이 떠 있을 때 쓸 수 있습니다.')
        picked = window.create_file_dialog(webview.FileDialog.FOLDER)
        if not picked:
            return None
        folder = picked[0] if isinstance(picked, (list, tuple)) else picked
        return self._agent_favorite({'folder': folder, 'on': True})

    # ── 데스크 안 에이전트 터미널 (2026-10-24 요청) ─────────────────
    # 초보자도 쓰기 쉽게 — 진짜 터미널(xterm.js + ConPTY) 위에 새 대화·모델·멈추기 같은 단추와 입력칸·도움말을 붙인 창.
    # 한 창(작업 공간)에 여러 에이전트를 띄우고, 에이전트끼리 서로를 본다 (2026-10-25 요청, Orca 처럼 — core/agent_bridge.py).
    # 화면은 web/agent-term.html, 프로세스는 core/agent_term.py. 창을 닫을 때 켜진 에이전트가 있으면 모두 끌지 묻고,
    # 켜 두면 창 없이 계속 돌다가 다시 열면 그대로 보인다 (2026-10-25 요청). 데스크를 끝내면 모두 끝낸다.
    def _term_manager(self):
        from core import agent_bridge, agent_term, computer_use
        with self._lock:
            if self._terms is None:
                self._terms = agent_term.Manager(Path(watcher.DATA_DIR) / 'agent' / 'sessions.json')
                threading.Thread(target=self._install_general_skills, name='general-skills', daemon=True).start()
                computer = computer_use.Computer(os.getpid(), Path(watcher.DATA_DIR) / 'agent' / 'screens')
                self._term_bridge = agent_bridge.Bridge(self._terms, Path(watcher.DATA_DIR), screen=self._term_screen,
                                                        choice=self._term_choice, log=self._log,
                                                        computer=computer, approve=self._term_computer_ask,
                                                        always=self._term_computer_always_match)
                self._term_bridge.on_grants = self._term_bar_update
                # 에이전트 기억 (2026-11-11) — 모든 칸이 기억 열쇠·얼린 사본을 받고, 연 대화 id 를 기억 저장소에 적는다
                memory = self._memory_store()
                self._term_bridge.memory = memory
                self._terms.memory = self._term_bridge
                self._terms.on_save = memory.register
                self._term_bridge.spawner = self._term_spawn
                self._term_bridge.closer = self._term_child_close
                if not edition.STUDENT:                 # 다른 PC 와 메시지는 교직원끼리만 (서버도 막는다)
                    self._term_peer = self._term_peer_link()
                    self._term_bridge.peer = self._term_peer
                    self._term_bridge.cron = self._cron_relay()   # 예약 업무를 에이전트가 대화로 다룬다 (2026-11-07)
            return self._terms

    def _term_cron_key(self):
        """서로 보기를 끈 칸에도 예약 업무만 쓸 열쇠를 줄 중계 (교사판 — 2026-11-08). 서로 보기를 켠 칸은 team 열쇠에 이미 있다."""
        return None if edition.STUDENT else self._term_bridge

    def _term_team(self) -> bool:
        """에이전트끼리 보기 (정하지 않았으면 켬) — 새로 여는 에이전트부터 적용된다."""
        return self._read_preferences().get('agent_team') is not False

    def _term_open(self, tool: str, folder: str, skip: bool, remote: str = '', extra: tuple = ()) -> str:
        """작업 공간 창에 에이전트를 하나 더한다. 창이 없으면 만든다."""
        from core import agent
        if self._shutdown.is_set():
            raise RuntimeError('프로그램을 종료하는 중입니다.')
        terms = self._term_manager()
        session = terms.open(tool, folder, skip, Path(watcher.DATA_DIR), remote, tuple(extra),
                             team=self._term_bridge if self._term_team() else None, knowledge=self._knowledge_launch(),
                             cron=self._term_cron_key())
        try:
            self._term_show(session.id)
        except Exception:
            terms.close(session.id)
            raise
        mode = ' (권한 묻지 않기)' if skip else ''
        return f"{session.info()['name']} 에서 {agent.TOOLS[tool]['label']}{mode} 를 열었습니다 ({session.name})."

    # ── 상주 에이전트 · 메인 · 작업 폴더 (2026-10-30 요청) ─────────────
    # 에이전트 터미널 목록의 📌 로 에이전트를 상주시킨다(여럿). 그중 하나는 ★ **메인** — 사용자가 켠 할 일(쿨메신저 쪽지 분석 …)을
    # 맡는다(core/resident_tasks.py). 상주는 «모두 끄고 닫기»에도 남고, 데스크가 켜질 때 창 없이 하던 대화로 열리고, 꺼지면
    # RESIDENT_CHECK 마다 보고 되살린다. 풀기 = 📌 다시 · ✕ 로 닫기(화면이 먼저 묻는다).
    # 설정 agent_residents = [{tool, folder, skip, name, title, team, conversation, main}] — 다음에 같은 이름·대화로 연다.
    # 작업 폴더(agent_knowledge) — 새로 여는 에이전트가 함께 쓰는 작업 폴더와 폴더마다의 지식 파일(core/knowledge.py).
    def _resident_specs(self) -> list[dict]:
        prefs = self._read_preferences()
        specs = prefs.get('agent_residents')
        if not isinstance(specs, list):                        # 첫 판(하나만, agent_resident)에서 옮긴다
            old = prefs.get('agent_resident')
            specs = [{**old, 'main': True}] if isinstance(old, dict) and old.get('on') is True else []
        return [spec for spec in specs if isinstance(spec, dict) and isinstance(spec.get('tool'), str)
                and isinstance(spec.get('folder'), str) and spec['folder'] and isinstance(spec.get('name'), str)]

    def _save_resident_specs(self, specs: list[dict]):
        self._save_preferences(agent_residents=specs, agent_resident=None)

    def _main_spec(self) -> dict | None:
        return next((spec for spec in self._resident_specs() if spec.get('main') is True), None)

    def _spec_of(self, session, main: bool) -> dict:
        row = session.snapshot()
        return {**{key: row[key] for key in ('tool', 'folder', 'skip', 'name', 'title', 'team', 'conversation')}, 'main': main}

    def _term_resident(self, payload):
        """목록의 📌 — {id, on}. 여럿 상주할 수 있다. 풀면 그 에이전트는 켜 둔 채 보통 에이전트가 된다."""
        on = payload.get('on')
        if not isinstance(on, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        session = self._term_manager().set_resident(payload.get('id'), on)
        specs = [spec for spec in self._resident_specs() if spec['name'] != session.name]
        label = session.title or session.name
        if on:
            self._save_resident_specs(specs + [self._spec_of(session, session.main)])
            self._log(f'{label} 를 상주시킵니다.')
            return (f'{label} 를 상주시킵니다 — «모두 끄고 닫기»에도 남고, 데스크가 켜질 때 자동으로 하던 대화로 열립니다. '
                    '꺼지면 데스크가 되살립니다.')
        self._save_resident_specs(specs)
        self._log(f'{label} 의 상주를 풀었습니다.')
        return f'{label} 의 상주를 풀었습니다. 이제 다른 에이전트처럼 «모두 끄기»에 함께 꺼집니다.'

    def _term_main(self, payload):
        """상주 줄의 ★ — {id, on}. 메인은 하나 — 사용자가 켠 할 일을 맡는다."""
        on = payload.get('on')
        if not isinstance(on, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        session = self._term_manager().set_main(payload.get('id'), on)
        specs = [{**spec, 'main': False} for spec in self._resident_specs() if spec['name'] != session.name]
        self._save_resident_specs(specs + [self._spec_of(session, on)])
        label = session.title or session.name
        self._log(f'{label} 를 메인 상주 에이전트로 정했습니다.' if on else f'{label} 는 이제 메인이 아닙니다.')
        return (f'{label} 가 메인 상주 에이전트입니다 — 위쪽 «메인 에이전트»에서 맡길 일을 켭니다.' if on
                else f'{label} 는 이제 메인이 아닙니다(상주는 그대로).')

    def _resident_forget(self, name: str):
        self._save_resident_specs([spec for spec in self._resident_specs() if spec['name'] != name])

    def _term_resident_ensure(self, quiet_since: dict):
        """한 번 본다 — 상주마다: 없으면 열고, 끝났거나 에이전트가 RESIDENT_REVIVE 넘게 꺼져 있으면 하던 대화로 다시 켠다."""
        from core import agent
        specs = self._resident_specs()
        if not specs or self._shutdown.is_set():
            return
        terms = self._term_manager()
        changed = False
        for spec in specs:
            session = next((s for s in terms.sessions() if s.resident and s.name == spec['name']), None)
            if session is None:
                if spec['tool'] not in agent.TOOLS or not os.path.isdir(spec['folder']) or not agent.find(spec['tool']):
                    if spec['name'] not in quiet_since:
                        self._log('상주 에이전트를 열 수 없습니다 (폴더·프로그램이 없음):', spec.get('title') or spec['name'])
                    quiet_since[spec['name']] = 'missing'
                    continue
                quiet_since.pop(spec['name'], None)
                text = lambda key: spec.get(key) if isinstance(spec.get(key), str) else ''
                fresh = terms.open(spec['tool'], spec['folder'], spec.get('skip') is True, Path(watcher.DATA_DIR),
                                   team=self._term_bridge if spec.get('team') is not False else None,
                                   name=spec['name'], title=text('title'), resume=text('conversation'),
                                   knowledge=self._knowledge_launch(), cron=self._term_cron_key(), thread=text('thread'))
                fresh.resident, fresh.main = True, spec.get('main') is True
                terms.save()
                if (fresh.name != spec['name'] or fresh.conversation != spec.get('conversation')
                        or fresh.thread != spec.get('thread')):
                    spec.update(name=fresh.name, conversation=fresh.conversation, thread=fresh.thread)
                    changed = True
                self._log(f'상주 에이전트를 열었습니다 ({fresh.title or fresh.name}).')
                continue
            if not (session.closed or not session.agent_running()):
                quiet_since.pop(session.id, None)
                current = session.current_conversation()      # /clear 로 대화가 바뀌었으면 다음에 열 때 그 대화로
                if current and current != spec.get('conversation'):
                    spec['conversation'] = current
                    changed = True
                continue
            first = quiet_since.setdefault(session.id, time.monotonic())
            if session.closed or time.monotonic() - first >= RESIDENT_REVIVE:
                quiet_since.pop(session.id, None)
                terms.restart(session.id)
                self._log(f'상주 에이전트 {session.title or session.name} 가 꺼져 있어 하던 대화로 다시 켰습니다.')
        if changed:
            self._save_resident_specs(specs)

    def _term_resident_watch(self):
        def loop():
            quiet: dict = {}
            while not self._shutdown.wait(RESIDENT_CHECK):
                try:
                    self._term_resident_ensure(quiet)
                except Exception as exc:
                    self._log('상주 에이전트를 확인하지 못했습니다:', exc)
        try:
            self._term_resident_ensure({})
        except Exception as exc:
            self._log('상주 에이전트를 열지 못했습니다:', exc)
        threading.Thread(target=loop, name='agent-resident', daemon=True).start()

    # 작업 폴더 ────────────────────────────────────────────
    def _knowledge_folders(self) -> list[str]:
        folders = self._read_preferences().get('agent_knowledge')
        return [folder for folder in folders if isinstance(folder, str)] if isinstance(folders, list) else []

    def _knowledge_launch(self) -> dict | None:
        """새로 여는 에이전트에 줄 작업 폴더 — 지식 목록 파일을 새로 쓴다."""
        from core import knowledge
        folders = [folder for folder in self._knowledge_folders() if os.path.isdir(folder)]
        if not folders:
            return None
        index = knowledge.write_index(Path(watcher.DATA_DIR), folders)
        return {'folders': folders, 'index': str(index)} if index else None

    def _term_knowledge(self, _):
        from core import knowledge
        return {'folders': knowledge.entries(Path(watcher.DATA_DIR), self._knowledge_folders()), 'limit': knowledge.LIMIT}

    def _term_knowledge_add(self, payload):
        """«작업 폴더 더하기» — payload.folder(지금 에이전트가 열린 폴더)가 있으면 그것, 없으면 폴더 고르기 창(작업 공간 창 위에)."""
        import webview
        from core import knowledge
        folders = self._knowledge_folders()
        if len(folders) >= knowledge.LIMIT:
            raise ValueError(f'작업 폴더는 {knowledge.LIMIT}개까지입니다.')
        picked = (payload or {}).get('folder')
        if not picked:
            with self._lock:
                window = self._term_window
            if window is None:
                raise RuntimeError('작업 공간 창을 찾을 수 없습니다.')
            picked = window.create_file_dialog(webview.FileDialog.FOLDER)
            if not picked:
                return None
        folder = knowledge.checked_folder(picked[0] if isinstance(picked, (list, tuple)) else picked)
        if any(os.path.normcase(folder) == os.path.normcase(other) for other in folders):
            return f'{Path(folder).name} 는 이미 작업 폴더입니다.'
        self._save_preferences(agent_knowledge=folders + [folder])
        knowledge.ensure_file(Path(watcher.DATA_DIR), folder)
        knowledge.write_index(Path(watcher.DATA_DIR), folders + [folder])
        self._log(f'작업 폴더를 더했습니다: {folder}')
        return f'{Path(folder).name or folder} 를 작업 폴더로 더했습니다 — 새로 여는 에이전트부터 봅니다(열려 있는 것은 «다시 시작»).'

    def _term_knowledge_remove(self, payload):
        from core import knowledge
        folder = payload.get('folder')
        folders = self._knowledge_folders()
        if folder not in folders:
            raise ValueError('작업 폴더가 아닙니다.')
        left = [other for other in folders if other != folder]
        self._save_preferences(agent_knowledge=left)
        knowledge.write_index(Path(watcher.DATA_DIR), left)
        self._log(f'작업 폴더에서 뺐습니다: {folder}')
        return f'{Path(folder).name or folder} 를 작업 폴더에서 뺐습니다. 지식 파일은 남겨 둡니다.'

    def _term_knowledge_open(self, payload):
        """그 폴더의 지식 파일을 연다(기본 편집기)."""
        from core import knowledge
        folder = payload.get('folder')
        if folder not in self._knowledge_folders():
            raise ValueError('작업 폴더가 아닙니다.')
        path = knowledge.ensure_file(Path(watcher.DATA_DIR), folder)
        os.startfile(str(path))
        return None

    def _term_knowledge_reveal(self, payload):
        """작업 폴더 자체를 탐색기로 연다."""
        folder = payload.get('folder')
        if folder not in self._knowledge_folders():
            raise ValueError('작업 폴더가 아닙니다.')
        if not os.path.isdir(folder):
            raise ValueError('폴더를 찾을 수 없습니다. 옮기거나 지웠는지 확인해 주세요.')
        os.startfile(folder)
        return None

    # 메인 에이전트의 할 일 ───────────────────────────────
    def _main_tasks(self) -> dict:
        tasks = self._read_preferences().get('agent_main_tasks')
        return tasks if isinstance(tasks, dict) else {}

    def _coolmsg_analysis_on(self) -> bool:
        return not edition.STUDENT and self._main_tasks().get('coolmsg') is True and self._main_spec() is not None

    def _analyst(self):
        from core import notify, resident_tasks
        with self._lock:
            if self._resident_analyst is None:
                self._resident_analyst = resident_tasks.Analyst(
                    Path(watcher.DATA_DIR), spec=self._main_spec, folders=self._knowledge_folders,
                    enabled=self._coolmsg_analysis_on,
                    send=lambda title, text, meta: notify.send(title, text, meta=meta, ntype='desk_agent'),
                    note=self._analysis_note, log=self._log)
            return self._resident_analyst

    def _analysis_note(self, text: str, data: dict | None = None):
        if self._terms:
            self._terms.note('analysis', self._terms.main(), None, text, data=data)

    def _term_analysis_prompt(self, payload):
        """분석 기록 → 지금 고른 에이전트 (2026-10-30 요청) — 쪽지 원문을 다시 읽어 분석과 함께 맡길 말을 만든다(창이 입력칸에 넣는다)."""
        from core import resident_tasks
        if edition.STUDENT:
            raise ValueError('쪽지 분석은 교직원판에서만 씁니다.')
        key = payload.get('key')
        if not isinstance(key, int) or isinstance(key, bool):
            raise ValueError('쪽지 번호가 올바르지 않습니다.')
        row = self._analyst().find(key)
        if row is None:
            raise ValueError('그 쪽지의 분석 기록이 없습니다 — 건너뛰었거나 실패한 쪽지는 맡길 수 없습니다.')
        message = watcher.message_by_key(key)
        if message is None or (row.get('sender') and message['sender'] != row['sender']):
            raise ValueError('쿨메신저에서 그 쪽지를 찾지 못했습니다 — 지워졌거나 다른 계정의 쪽지입니다.')
        return {'text': resident_tasks.handoff(message, row)}

    # ── 에이전트 작업 요청 (2026-11-11) — 다른 선생님이 수행 방식까지 안내해 보낸 일을 내 에이전트에게 (core/agent_request.py) ──
    def _term_requests(self, _):
        """받은 작업 요청(열린 것) — 에이전트 터미널의 «작업 요청» 표시."""
        from core import agent_request
        if edition.STUDENT or not supa_auth.whoami():
            return {'available': False, 'requests': []}
        rows = agent_request.inbox('open')
        with self._lock:
            account = (supa_auth.load_session() or {}).get('user_id')
            seen = self._req_seen[1] if self._req_seen and self._req_seen[0] == account else set()
            self._req_seen = (account, seen | {row['id'] for row in rows})
        return {'available': True, 'requests': rows}

    def _term_request_prompt(self, payload):
        """맡길 말 — 서버가 만든 것 그대로(모바일·웹에서 넘길 때와 같다). 창이 고른 에이전트의 입력칸에 넣는다."""
        from core import agent_request
        if edition.STUDENT:
            raise ValueError('작업 요청은 교직원판에서만 씁니다.')
        data = agent_request.prompt(payload.get('id'))
        return {'id': data['id'], 'title': data.get('title') or '', 'from': data.get('from') or '', 'text': data['prompt']}

    def _term_request_handed(self, payload):
        """입력칸에 넣은 뒤 — 보낸 선생님 쪽 목록에 «에이전트에게 넘김»으로 보이게. 실패해도 넣은 것은 그대로다."""
        from core import agent_request
        if edition.STUDENT:
            raise ValueError('작업 요청은 교직원판에서만 씁니다.')
        agent = str(payload.get('agent') or '')[:60]
        agent_request.mark_handed(payload.get('id'), label=socket.gethostname()[:40], agent=agent)
        return {'ok': True}

    def _request_arrived(self, record: dict):
        """Realtime 으로 온 작업 요청 알림 — 트레이 알림과 에이전트 터미널 기록(맡기기 단추)."""
        from core import agent_request
        item = agent_request.arrived(record)
        if item is None or edition.STUDENT:
            return
        account = (supa_auth.load_session() or {}).get('user_id')
        with self._lock:
            seen = self._req_seen[1] if self._req_seen and self._req_seen[0] == account else set()
            if item['request_id'] in seen:
                return
            self._req_seen = (account, seen | {item['request_id']})
        sender = item['sender'] or '다른 선생님'
        self._msg_notify(f'작업 요청 · {sender}', item['title'])
        if self._terms:
            self._terms.note('request', None, None, f'{sender} 선생님 — {item["title"]}', from_name=sender,
                             data={'request': item['request_id']})

    def _req_check(self):
        """Realtime 이 끊긴 사이에 온 요청 — 2분마다(메시지 확인과 같은 주기·자리 비움 규칙). 처음 한 번은 알리지 않고 기억만."""
        from core import agent_request
        if edition.STUDENT:
            return
        account = (supa_auth.load_session() or {}).get('user_id')
        if not account:
            return
        rows = [row for row in agent_request.inbox('open') if row.get('status') == 'sent']
        with self._lock:
            first = not (self._req_seen and self._req_seen[0] == account)
            seen = set() if first else self._req_seen[1]
            fresh = [row for row in rows if row['id'] not in seen]
            self._req_seen = (account, seen | {row['id'] for row in rows})
        if first:
            if fresh:
                self._msg_notify('작업 요청', f'아직 맡기지 않은 작업 요청이 {len(fresh)}건 있습니다 — 에이전트 터미널의 «작업 요청»에서 봅니다.')
            return
        for row in fresh[:3]:
            self._msg_notify(f'작업 요청 · {row.get("from") or ""}', row.get('title') or '')
            if self._terms:
                self._terms.note('request', None, None, agent_request.summary(row), from_name=row.get('from') or '',
                                 data={'request': row['id']})

    def _coolmsg_received(self, message: dict):
        """쿨메신저 감시가 새 쪽지마다 부른다 — 메인 에이전트에 쪽지 분석을 켜 두었으면 대기열에."""
        if self._coolmsg_analysis_on():
            self._analyst().offer(message)

    def _term_main_state(self, _):
        session = self._terms.main() if self._terms else None
        spec = self._main_spec()
        state = self._term_status(session) if session is not None and self._term_bridge else None
        return {'available': not edition.STUDENT,
                'main': ({'name': session.name, 'title': session.title or session.name, 'state': state['state'] if state else '',
                          'folder': session.folder} if session else
                         {'name': spec['name'], 'title': spec.get('title') or spec['name'], 'state': 'ended', 'folder': spec['folder']}
                         if spec else None),
                'tasks': {'coolmsg': self._main_tasks().get('coolmsg') is True},
                'watching': bool(self._watcher.running), 'recent': self._analyst().recent() if not edition.STUDENT else [],
                'knowledge': len(self._knowledge_folders())}

    def _term_main_set(self, payload):
        if edition.STUDENT:
            raise ValueError('메인 에이전트의 할 일은 교직원판에서만 씁니다.')
        on = payload.get('coolmsg')
        if not isinstance(on, bool):
            raise ValueError('설정 형식이 올바르지 않습니다.')
        if on and self._main_spec() is None:
            raise ValueError('먼저 메인 상주 에이전트를 정해 주세요 — 목록에서 📌 로 상주시킨 뒤 ★.')
        self._save_preferences(agent_main_tasks={**self._main_tasks(), 'coolmsg': on})
        self._log('메인 에이전트: 쿨메신저 쪽지 분석을 ' + ('켰습니다.' if on else '껐습니다.'))
        return ('새 쿨메신저 쪽지를 Haiku 로 분석합니다 — 처리할 일이 있으면 스페이스기전 알림으로 보냅니다. 개인정보가 보이는 쪽지는 '
                '분석하지 않습니다.' + ('' if self._watcher.running else ' (지금은 쪽지 감시가 꺼져 있습니다 — 연결 및 설정에서 켜 주세요)')
                if on else '쿨메신저 쪽지 분석을 껐습니다.')

    # ── 예약 업무 (2026-11-07 요청) ──────────────────────────
    # 정한 시각에 정한 에이전트(Claude Code 칸)에게 정한 일을 시키고 결과를 스페이스기전 알림(휴대폰 푸시)과 휴대폰 «에이전트» 탭
    # 대화로 보낸다. 데스크가 켜져 있으면 돈다(창은 닫혀 있어도 됨), 놓친 예약은 켜진 뒤 한 번. 목록은 오른쪽 패널 «예약».
    # 본체는 core/agent_cron.py, 휴대폰 대화는 서버 desk_agent_cron_post (spacekijun 20261107090000_desk_agent_cron.sql). 교사판만.
    CRON_STUDENT = '예약 업무는 교직원판에서만 씁니다.'

    def _cron_scheduler(self):
        from core import agent_cron
        if edition.STUDENT:
            raise ValueError(self.CRON_STUDENT)
        with self._lock:
            if self._cron is None:
                self._cron = agent_cron.Scheduler(
                    Path(watcher.DATA_DIR), find=self._cron_find, open=self._cron_open, restart=self._cron_restart,
                    status=self._cron_status, deliver=self._cron_deliver, note=self._cron_note, log=self._log,
                    enabled=lambda: not self._shutdown.is_set())
            return self._cron

    # 에이전트가 대화로 만드는 예약 (2026-11-07 요청) — 중계 /cron/* (core/agent_bridge.py) → agent_cron.Relay.
    # 만들기·고치기·켜기는 작업 공간 창에 승인 카드를 띄워 사람이 정한다(CRON_ASK_WAIT 안에 답이 없거나 창이 없으면 승인 대기로 저장).
    def _cron_relay(self):
        from core import agent_cron
        return agent_cron.Relay(self._cron_scheduler(), target_of=self._cron_relay_target, approve=self._cron_ask,
                                pending=self._cron_pending)

    def _cron_relay_target(self, name: str) -> dict:
        session = self._cron_find(name) if isinstance(name, str) and name else None
        if session is None or session.closed:
            raise ValueError(f'no open agent named {name!r} — GET /agents lists them')
        if session.tool != 'claude':
            raise ValueError(f'{name} is not a Claude Code agent — scheduled jobs run on Claude Code agents only')
        return {'name': session.name, 'tool': session.tool, 'folder': session.folder, 'skip': session.skip, 'title': session.title}

    def _cron_ask(self, agent_label: str, proposal: dict):
        """중계 스레드에서 — 사람이 답할 때까지 기다린다. True 승인 · False 거절 · None 창 없음·시간 지남."""
        import uuid
        with self._lock:
            window = self._term_window if self._term_ready else None
        if window is None:
            return None
        request = uuid.uuid4().hex
        waiting = {'event': threading.Event(), 'answer': None}
        with self._lock:
            self._cron_asks[request] = waiting
        try:
            window.run_js('window.deskTerm && window.deskTerm.askCron(%s)' % json.dumps({'id': request, 'agent': agent_label, **proposal}))
            window.show()
            window.restore()
            self._bring_front(window)
            waiting['event'].wait(CRON_ASK_WAIT)
            return waiting['answer']
        finally:
            with self._lock:
                self._cron_asks.pop(request, None)
            try:
                window.run_js('window.deskTerm && window.deskTerm.askDone(%s)' % json.dumps(request))
            except Exception:
                pass

    def _term_cron_answer(self, payload):
        request, allow = payload.get('request'), payload.get('allow')
        if not isinstance(request, str) or not isinstance(allow, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        with self._lock:
            waiting = self._cron_asks.get(request)
        if waiting is None:
            raise ValueError('이미 끝난 질문입니다.')
        waiting['answer'] = allow
        waiting['event'].set()
        return '예약을 승인했습니다.' if allow else '거절했습니다 — 에이전트에게 알립니다.'

    def _cron_ask_cancel(self):
        """창을 닫는다 — 묻던 것은 «답 없음»(승인 대기로 저장)."""
        with self._lock:
            pending = list(self._cron_asks.values())
        for waiting in pending:
            waiting['event'].set()

    def _cron_pending(self, agent_label: str, row: dict):
        from core import agent_cron, notify
        self._cron_note(f'⏳ {agent_label} 가 만든 예약 «{row["title"]}» — 승인 대기 (예약 탭에서 켜면 확정)')
        try:
            notify.send(f'⏰ 예약 «{row["title"]}» 승인 대기', f'{agent_label} 가 {agent_cron.describe(row["when"])} 예약을 만들었습니다. '
                        '데스크 에이전트 터미널의 «예약»에서 켜야 돕니다.',
                        meta={'source': 'desk_agent', 'kind': 'cron_pending', 'schedule': row['id']}, ntype='desk_agent')
        except Exception as exc:
            self._log('예약 승인 대기 알림을 보내지 못했습니다:', exc)

    def _cron_find(self, name: str):
        wanted = name.lower()
        return next((s for s in self._term_manager().sessions() if s.name.lower() == wanted), None)

    def _cron_open(self, target: dict):
        """대상 칸이 없다 — 같은 도구·폴더·권한 모드·이름으로 새로 연다. 창이 열려 있으면 화면이 목록을 다시 받을 때 칸이 생긴다."""
        from core import agent
        if self._shutdown.is_set():
            raise RuntimeError('프로그램을 종료하는 중입니다.')
        if not os.path.isdir(target['folder']):
            raise RuntimeError(f'대상 에이전트의 폴더를 찾을 수 없습니다: {target["folder"]}')
        if not agent.find(target['tool']):
            raise RuntimeError(f'{agent.TOOLS[target["tool"]]["label"]} 가 이 PC 에 설치되어 있지 않습니다.')
        session = self._term_manager().open(target['tool'], target['folder'], target.get('skip') is True, Path(watcher.DATA_DIR),
                                            team=self._term_bridge if self._term_team() else None, name=target['name'],
                                            title=target.get('title') or '', knowledge=self._knowledge_launch(), cron=self._term_cron_key())
        self._log(f'예약 업무를 위해 에이전트 {session.title or session.name} 를 열었습니다 ({target["folder"]}).')
        return session

    def _cron_restart(self, session):
        fresh = self._term_manager().restart(session.id)
        self._log(f'예약 업무를 위해 꺼져 있던 {fresh.title or fresh.name} 를 다시 켰습니다.')
        return fresh

    def _cron_status(self, session) -> str:
        state = self._term_bridge.status(session) if self._term_bridge else 'idle'
        # 창이 없으면 화면 글로 선택지를 볼 수 없다 — 출력 끝부분의 꼬리말로 어림한다
        if state == 'idle' and self._term_choice(session) is None and session.asking():
            return 'waiting-for-user-choice'
        return state

    def _cron_note(self, text: str, data: dict | None = None):
        if self._terms:
            self._terms.note('cron', None, None, text, to_name='예약', data=data)

    def _cron_deliver(self, row: dict, agent_name: str, result: str, run: dict):
        """결과 → 스페이스기전 알림(푸시) + 휴대폰 «에이전트» 탭 대화. «선택 필요»는 알림만."""
        from core import agent_cron, notify
        status = run.get('status') or ''
        late = ' · 늦게 실행' if run.get('late') else ''
        title = f'⏰ 예약 «{row["title"]}» {agent_cron.STATUS_TEXT.get(status, status)}{late}'
        meta = {'source': 'desk_agent', 'kind': 'cron', 'schedule': row['id'], 'run': run.get('id'), 'status': status,
                'agent': agent_name, 'late': bool(run.get('late'))}
        try:
            notify.send(title, agent_cron.summary(result) or title, meta=meta, ntype='desk_agent')
        except Exception as exc:
            self._log('예약 결과 알림을 보내지 못했습니다:', exc)
        if status == 'choice':
            return
        try:
            self._cron_phone_post(row, agent_name, result, run)
        except Exception as exc:
            self._log('휴대폰 «에이전트» 탭에 예약 결과를 올리지 못했습니다:', exc)

    def _agent_peer_device(self) -> str:
        """이 PC 의 무작위 표시(32자 hex) — 다른 PC·휴대폰과 주고받을 때 서버가 이 PC 를 이것으로 안다."""
        import secrets
        device = self._read_preferences().get('agent_peer_device')
        if not (isinstance(device, str) and re.fullmatch(r'[0-9a-f]{32}', device)):
            device = secrets.token_hex(16)
            self._save_preferences(agent_peer_device=device)
        return device

    def _cron_phone_post(self, row: dict, agent_name: str, result: str, run: dict):
        from core import agent_cron, desk_message, supa_auth
        if supa_auth.load_session() is None:
            return
        body = {
            'p_device': self._agent_peer_device(), 'p_label': (os.environ.get('COMPUTERNAME') or socket.gethostname())[:40],
            'p_agent': agent_name, 'p_title': row['title'][:agent_cron.TITLE_LIMIT], 'p_prompt': row['prompt'][:2000],
            'p_result': (result or '(결과 없음)')[:agent_cron.RESULT_LIMIT], 'p_status': run.get('status') or 'done',
            'p_late': bool(run.get('late'))}
        # 휴대폰 채팅방 — 그 칸의 지금 대화 방에 붙인다(2026-11-10). 칸이 이미 닫혔으면 방 없이(이름으로만) 올린다.
        session = self._cron_find(agent_name)
        if session is not None and not session.closed:
            body['p_thread'] = session.chat_thread()
        desk_message._request('POST', 'rpc/desk_agent_cron_post', body=body)

    def _cron_target(self, name) -> dict:
        session = self._cron_find(name) if isinstance(name, str) and name else None
        if session is None:
            raise ValueError('예약을 맡길 에이전트를 골라 주세요 — 열려 있는 Claude Code 에이전트 가운데서 고릅니다.')
        return {'name': session.name, 'tool': session.tool, 'folder': session.folder, 'skip': session.skip,
                'title': session.title}

    def _term_cron_list(self, _):
        from core import agent_cron, supa_auth
        cron = self._cron_scheduler()
        agents = [{'name': s.name, 'title': s.title or s.name, 'tool': s.tool, 'folder': s.folder, 'skip': s.skip,
                   'team': 'DESK_AGENT_TOKEN' in s.env, 'closed': s.closed}
                  for s in self._term_manager().sessions() if s.tool == 'claude']
        return {'schedules': cron.list(), 'agents': agents, 'auth': agent_cron.auth_status('claude'), 'limit': agent_cron.LIMIT,
                'phone': self._term_peer_phone(), 'linked': supa_auth.load_session() is not None,
                'status_text': agent_cron.STATUS_TEXT}

    def _term_cron_save(self, payload):
        """새 예약 · 고치기({id, title, prompt, when, agent, on}). 고칠 때 대상 칸이 지금 없으면 저장된 대상을 그대로 둔다."""
        from core import agent_cron
        cron = self._cron_scheduler()
        schedule_id = payload.get('id')
        old = next((row for row in cron.store.load() if row['id'] == schedule_id), None) if schedule_id else None
        if schedule_id and old is None:
            raise ValueError('그 예약을 찾지 못했습니다.')
        name = payload.get('agent')
        if old and name == old['target']['name'] and self._cron_find(name) is None:
            target = old['target']
        else:
            target = self._cron_target(name)
        cleaned = agent_cron.clean_schedule(payload, target)
        cleaned['pending'] = False                  # 사람이 패널에서 저장했다 — 승인한 것
        row = cron.edit(schedule_id, cleaned) if old else cron.add(cleaned)
        self._log(f'예약 업무 «{row["title"]}» 를 {"고쳤습니다" if old else "만들었습니다"} — {agent_cron.describe(row["when"])}.')
        return f'«{row["title"]}» — {agent_cron.describe(row["when"])}, {target.get("title") or target["name"]} 에게 맡깁니다.'

    def _term_cron_remove(self, payload):
        cron = self._cron_scheduler()
        if cron.busy(payload.get('id')):
            raise ValueError('지금 도는 중인 예약입니다 — 끝난 뒤에 지워 주세요.')
        cron.remove(payload.get('id'))
        return '예약을 지웠습니다.'

    def _term_cron_toggle(self, payload):
        on = payload.get('on')
        if not isinstance(on, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        row = self._cron_scheduler().set_on(payload.get('id'), on)
        return f'«{row["title"]}» 를 {"켰습니다" if on else "껐습니다"}.'

    def _term_cron_run(self, payload):
        """«지금 한 번» — 시각과 상관없이 돌린다(정해 둔 다음 시각은 그대로)."""
        if not self._cron_scheduler().run_now(payload.get('id'), manual=True):
            raise ValueError('이미 도는 중입니다.')
        return '지금 한 번 돌립니다 — 끝나면 휴대폰으로 결과를 보냅니다.'

    def _term_cron_preview(self, payload):
        from core import agent_cron
        if edition.STUDENT:
            raise ValueError(self.CRON_STUDENT)
        when = agent_cron.clean_when(payload.get('when'))
        return {'describe': agent_cron.describe(when), 'next': agent_cron.preview(when)}

    def _term_cron_runs(self, payload):
        limit = payload.get('limit', 20)
        return self._cron_scheduler().runs(payload.get('id'), max(1, min(int(limit) if isinstance(limit, int) else 20, 50)))

    # ── 에이전트 로그인 안내 (2026-11-07 요청) ─────────────────
    # Claude Code·Codex 가 로그인되어 있지 않으면 칸 위에 «로그인이 필요합니다» 화면을 덮는다(web/agent-term.js `paintLogin`).
    # [로그인하기] 는 보이는 콘솔 창에서 `claude auth login` / `codex login` 을 돌린다 — 브라우저가 열리고, 코드를 붙여 넣으라고
    # 하면 그 창에서 한다. 화면은 몇 초마다 term_auth 로 다시 보고, 로그인되면 그 칸을 다시 켠다.
    def _term_auth(self, payload):
        from core import agent, agent_cron
        tool = payload.get('tool') or 'claude'
        if tool not in agent.TOOLS:
            raise ValueError('지원하지 않는 에이전트입니다.')
        state = dict(agent_cron.auth_status(tool, fresh=payload.get('fresh') is True))
        started = self._logins.get(tool)
        if state['logged_in'] and started:
            self._logins.pop(tool, None)
            started = None
        state['login_open'] = bool(started and time.monotonic() - started < 15 * 60)
        state['label'] = agent.TOOLS[tool]['label']
        return state

    def _term_login(self, payload):
        from core import agent, agent_cron
        tool = payload.get('tool')
        if tool not in agent.TOOLS:
            raise ValueError('지원하지 않는 에이전트입니다.')
        command = agent_cron.login_command(tool)
        # cmd /k — 로그인이 끝나도 창이 남아 결과(실패 문구 포함)를 읽을 수 있다. 설명은 데스크 화면이 한다
        agent.spawn(['cmd.exe', '/k', *command], str(Path.home()), True)
        agent_cron.forget_auth(tool)
        self._logins[tool] = time.monotonic()
        self._log(f'{agent.TOOLS[tool]["label"]} 로그인 창을 열었습니다.')
        return f'{agent.TOOLS[tool]["label"]} 로그인 창을 열었습니다 — 브라우저에서 로그인을 마치면 여기가 저절로 이어집니다.'

    # ── 스킬 패널 (2026-10-30 요청) ──────────────────────────
    # 에이전트 터미널 오른쪽 패널 — 스킬을 폴더처럼 펼치면 «할 수 있는 일»이 나오고, 누르면 입력칸에 들어간다. ☆ 즐겨찾기.
    # 기본 스킬(바탕화면 정리 …)은 어느 폴더에서나 — 처음 터미널을 열 때 사용자 범위에 깐다(core/automation.py install_general).
    # 자동화 업무 스킬은 그 폴더에 깔려 있고 켜 둔 것만 보인다(그 폴더에서 연 에이전트가 쓴다).
    def _install_general_skills(self):
        from core import automation
        try:
            done = automation.install_general()
            changed = [row['title'] for row in done if any(state in ('installed', 'updated') for state in row['states'].values())]
            if changed:
                self._log('기본 스킬을 깔았습니다:', ', '.join(changed))
        except Exception as exc:
            self._log('기본 스킬을 깔지 못했습니다:', exc)

    def _skill_favorites(self) -> list[dict]:
        saved = self._read_preferences().get('agent_skill_favorites')
        return [item for item in saved if isinstance(item, dict) and isinstance(item.get('skill'), str)
                and isinstance(item.get('label'), str) and isinstance(item.get('prompt'), str)] if isinstance(saved, list) else []

    def _term_skills(self, _):
        from core import automation
        shape = lambda skill, scope, usable=True: {
            'name': skill['name'], 'title': skill['title'], 'summary': skill['summary'], 'scope': scope, 'usable': usable,
            'actions': skill.get('actions', []), 'groups': skill.get('groups', [])}
        general = [shape(skill, 'general') for skill in automation.general_catalog()]
        folder = self._automation_folder()
        off = self._automation_off()
        states = {row['name']: row['state'] for row in automation.status(folder)}
        work = [shape(skill, 'automation', states.get(skill['name']) in ('current', 'outdated'))
                for skill in automation.catalog() if skill['name'] not in off]
        return {'general': general, 'automation': work, 'favorites': self._skill_favorites(),
                'automation_folder': str(folder), 'automation_ready': folder.is_dir()}

    def _term_skill_favorite(self, payload):
        """☆ — {skill, label, prompt, on}. 즐겨찾기는 SKILL_FAVORITES 개까지, 같은 것은 한 번."""
        skill, label, prompt, on = payload.get('skill'), payload.get('label'), payload.get('prompt'), payload.get('on')
        if not all(isinstance(value, str) and value for value in (skill, label, prompt)) or not isinstance(on, bool) \
                or len(label) > 40 or len(prompt) > 600:
            raise ValueError('요청 형식이 올바르지 않습니다.')
        items = [item for item in self._skill_favorites() if not (item['skill'] == skill and item['label'] == label)]
        if on:
            if len(items) >= SKILL_FAVORITES:
                raise ValueError(f'즐겨찾기는 {SKILL_FAVORITES}개까지입니다. 안 쓰는 것을 빼 주세요.')
            items.append({'skill': skill, 'label': label, 'prompt': prompt})
        self._save_preferences(agent_skill_favorites=items)
        return items

    def _term_spawn(self, parent, tool: str, folder: str, title: str):
        """에이전트가 연 자식 에이전트 (중계 /spawn) — 부모와 같은 권한 모드, 서로 보기 켜고, 원격 제어는 붙이지 않는다.
        창이 열려 있으면 화면이 목록을 다시 받을 때(pollList) 칸이 생긴다 — 사람이 보던 칸을 빼앗지 않게 앞에 두지 않는다."""
        from core import agent
        if self._shutdown.is_set():
            raise RuntimeError('프로그램을 종료하는 중입니다.')
        if not agent.find(tool):
            raise RuntimeError(f'{agent.TOOLS[tool]["label"]} is not installed on this PC')
        extra = tuple(parent.launch.get('extra', ())) if tool == parent.tool else ()
        child = self._term_manager().open(tool, folder, parent.skip, Path(watcher.DATA_DIR), '', extra,
                                          team=self._term_bridge, parent=parent.name, title=title,
                                          knowledge=self._knowledge_launch())
        self._log(f'{parent.title or parent.name} 가 자식 에이전트 {child.name} 를 열었습니다 ({folder}).')
        return child

    def _term_child_close(self, session):
        self._terms.close(session.id)
        if self._term_bridge:
            self._term_bridge.revoke(session.id)

    def _start_term_restore(self):
        """지난번에 켜 둔 에이전트들을 다시 연다 (업데이트·PC 재시작 뒤 — 2026-10-27 요청). 화면이 뜬 뒤에."""
        def run():
            self._ui_ready.wait(90)
            if self._shutdown.is_set():
                return
            try:
                self._term_restore()
            except Exception as exc:
                self._log('지난 에이전트들을 다시 열지 못했습니다:', exc)
            self._term_resident_watch()             # 상주 에이전트 — 없으면 열고, 꺼지면 되살린다
            if not edition.STUDENT:
                try:
                    self._cron_scheduler().start()  # 예약 업무 — 놓친 예약은 여기서 한 번 돈다
                except Exception as exc:
                    self._log('예약 업무를 켜지 못했습니다:', exc)
            # 밤 12시 지식 업데이트 — 데스크가 꺼져 자정을 놓쳤으면 여기서(켜진 뒤) 한 번 한다
            threading.Thread(target=self._memory_loop, name='agent-memory-review', daemon=True).start()
        threading.Thread(target=run, name='agent-term-restore', daemon=True).start()

    # ── 에이전트 기억 (2026-11-11 요청 — 헤르메스 방식, core/agent_memory.py) ──────────
    # 기억(MEMORY.md)·사용자 프로필(USER.md)·배운 스킬을 데스크가 들고, 칸을 열 때 얼린 사본을 넣는다(Claude 는 SessionStart 훅).
    # 에이전트는 중계의 /memory · /skills · /history 로 바로 고치고, 밤 12시에 데스크가 그날 대화를 읽어 정리한다.
    def _memory_store(self):
        from core import agent_memory
        with self._lock:
            fresh = self._memory is None
            if fresh:
                self._memory = agent_memory.Store(Path(watcher.DATA_DIR) / 'agent' / 'memory', log=self._log)
            store = self._memory
        if fresh:
            try:
                store.write_snapshot()
                threading.Thread(target=store.sync_skills, name='agent-memory-skills', daemon=True).start()
            except Exception as exc:
                self._log('에이전트 기억을 준비하지 못했습니다:', exc)
        return store

    def _memory_reviewer(self):
        from core import agent, agent_memory, agent_term
        store = self._memory_store()
        with self._lock:
            if self._memory_review is None:
                self._memory_review = agent_memory.Review(store, find=lambda: agent.find('claude'),
                                                          env=agent_term.session_env, log=self._log)
            return self._memory_review

    def _memory_auto(self) -> bool:
        return self._read_preferences().get('agent_memory_review') is not False

    def _memory_loop(self):
        while not self._shutdown.is_set():
            try:
                if self._memory_auto() and self._memory_reviewer().due():
                    self._memory_run(manual=False)
            except Exception as exc:
                self._log('지식 업데이트 확인 실패:', exc)
            if self._shutdown.wait(MEMORY_CHECK):
                break

    def _memory_run(self, manual: bool) -> dict:
        entry = self._memory_reviewer().run(manual=manual)
        changed = [change for change in entry['changes'] if change.get('ok')]
        if entry['status'] == 'done' and changed:
            self._msg_notify('에이전트 지식 업데이트', entry['summary'][:200])
        if self._terms and (entry['status'] != 'idle' or manual):
            head = {'done': f'지식 업데이트 — {len(changed)}건 바꿈', 'idle': '지식 업데이트 — 바꿀 것 없음',
                    'failed': '지식 업데이트 실패'}.get(entry['status'], '지식 업데이트')
            self._terms.note('memory', None, None, f'{head}: {entry["summary"]}', from_name='지식 업데이트',
                             data={'review': entry['at']})
        self._log(f'지식 업데이트({entry["status"]}): {entry["summary"]}')
        return entry

    def _term_memory(self, _=None):
        """창의 «기억» — 기억·프로필 항목, 배운 스킬, 밤 정리 기록, 최근 바뀜."""
        from core import agent_memory
        store, review = self._memory_store(), self._memory_reviewer()
        state = review.state()
        return {'stores': {target: {'entries': store.entries(target), **store.usage(target)} for target in agent_memory.LIMITS},
                'skills': store.skills(), 'changes': store.changes(20), 'auto': self._memory_auto(),
                'review': {'last_run': state.get('last_run') if state.get('status') != 'baseline' else '',
                           'status': state.get('status') or '', 'running': review.running,
                           'history': (state.get('history') or [])[:10]},
                'undo': store.latest_backup()}

    def _term_memory_remove(self, payload):
        from core import agent_memory
        target, index = payload.get('target'), payload.get('index')
        if target not in agent_memory.LIMITS or not isinstance(index, int):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        try:
            self._memory_store().remove_entry(target, index)
        except agent_memory.MemoryError as error:
            raise ValueError(str(error)) from None
        return '항목을 지웠습니다. 새로 여는 에이전트부터 적용됩니다.'

    def _term_memory_skill(self, payload):
        from core import agent_memory
        try:
            return {'name': payload.get('name'), 'text': self._memory_store().skill(payload.get('name'))}
        except agent_memory.MemoryError as error:
            raise ValueError(str(error)) from None

    def _term_memory_skill_delete(self, payload):
        from core import agent_memory
        try:
            self._memory_store().skill_manage('delete', payload.get('name'), source='사람')
        except agent_memory.MemoryError as error:
            raise ValueError(str(error)) from None
        return f'배운 스킬 «{payload.get("name")}»을 지웠습니다.'

    def _term_memory_review(self, _=None):
        review = self._memory_reviewer()
        if review.running:
            raise ValueError('지식 업데이트가 이미 진행 중입니다.')

        def run():
            try:
                self._memory_run(manual=True)
            except Exception as exc:
                self._log('지식 업데이트 실패:', exc)
        threading.Thread(target=run, name='agent-memory-review-now', daemon=True).start()
        return '지식 업데이트를 시작했습니다 — 대화가 많으면 몇 분 걸립니다.'

    def _term_memory_undo(self, payload):
        from core import agent_memory
        store = self._memory_store()
        name = payload.get('name')
        if not name or name != store.latest_backup():
            raise ValueError('되돌릴 업데이트가 바뀌었습니다. 새로 고쳐 주세요.')
        if self._memory_reviewer().running:
            raise ValueError('지식 업데이트가 진행 중입니다. 끝난 뒤에 되돌려 주세요.')
        try:
            store.restore(name)
        except agent_memory.MemoryError as error:
            raise ValueError(str(error)) from None
        return '지난 지식 업데이트 앞의 모양으로 되돌렸습니다.'

    def _term_memory_auto(self, payload):
        on = payload.get('on')
        if not isinstance(on, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        self._save_preferences(agent_memory_review=on)
        return '매일 밤 12시에 지식을 업데이트합니다.' if on else '밤 12시 지식 업데이트를 껐습니다.'

    def _term_restore(self) -> int:
        from core import agent, agent_term
        if self._read_preferences().get('agent_restore') is False or not self._agent_embedded():
            return 0
        terms = self._term_manager()
        if terms.sessions():
            return 0
        saved = terms.saved()
        opened, missed = [], []
        for row in saved['sessions'][:agent_term.SESSION_LIMIT]:
            tool, folder = row.get('tool'), row.get('folder')
            label = row.get('title') or row.get('name') or tool
            if tool not in agent.TOOLS or not isinstance(folder, str) or not os.path.isdir(folder) or not agent.find(tool):
                missed.append(str(label))
                continue
            # 실행기에 그대로 들어가는 인자 — cmd 가 명령으로 읽을 글자가 든 것은 버린다 (손으로 고친 파일 대비)
            extra = tuple(part for part in row.get('extra') or () if isinstance(part, str) and not re.search(r'[&|<>^%"\r\n]', part))
            text = lambda key: row.get(key) if isinstance(row.get(key), str) else ''
            try:
                session = terms.open(tool, folder, row.get('skip') is True, Path(watcher.DATA_DIR), text('remote'), extra,
                                     team=self._term_bridge if row.get('team') is not False else None,
                                     name=text('name'), title=text('title'), parent=text('parent'),
                                     resume=text('conversation'), knowledge=self._knowledge_launch(), cron=self._term_cron_key(),
                                     thread=text('thread'))
                spec = next((item for item in self._resident_specs() if item['name'] == session.name), None)
                session.resident = row.get('resident') is True and spec is not None
                session.main = session.resident and spec.get('main') is True
                opened.append(session)
            except Exception as exc:
                missed.append(str(label))
                self._log(f'에이전트 {label} 를 다시 열지 못했습니다:', exc)
        if missed:
            self._log('다시 열지 못한 에이전트 (폴더·프로그램이 없음):', ', '.join(missed))
        if not opened:
            terms.save()                              # 열 것이 없었다 — 목록을 지금 상태(빈 것)로
            return 0
        self._log(f'지난번에 켜 둔 에이전트 {len(opened)}개를 그 대화로 다시 열었습니다.')
        if saved['window']:
            self._term_show(opened[0].id)
        return len(opened)

    def _term_show(self, focus: str):
        """작업 공간 창을 보이고 focus 세션을 앞에 둔다. 다 불러온 창이면 화면에 세션을 더하라고 알린다."""
        import webview
        with self._lock:
            window, ready = self._term_window, self._term_ready
            self._term_focus = focus
        created = window is None
        if created:
            # 🚨 create_window 는 잠금 밖에서 — UI 스레드를 기다리는 동안 잠금을 쥐면 서로 기다린다 (_show_dock 의 🚨)
            made = webview.create_window(
                '에이전트 터미널 · 스페이스기전 데스크', str(WEB_DIR / 'agent-term.html'), js_api=self,
                width=TERM_SIZE[0], height=TERM_SIZE[1], min_size=(720, 480), background_color='#16171d')
            with self._lock:
                if self._term_window is None:
                    self._term_window = window = made
                else:                                   # 그사이 다른 요청이 만들었다 — 그 창을 쓴다
                    window, ready, created = self._term_window, self._term_ready, False
            if not created:
                made.destroy()
        if not created:
            if not ready:                               # 아직 뜨는 중 — 곧 보이고, loaded 의 attachAll 이 함께 붙인다
                return
            window.run_js('window.deskTerm && window.deskTerm.add(%s)' % json.dumps(focus))
            window.show()
            window.restore()
            self._bring_front(window)
            return

        def loaded(made=window):
            with self._lock:
                self._term_ready = True
                focus_id = self._term_focus
            self._terms.window_open = True            # 다시 켤 때 창까지 띄운다
            self._terms.save()
            if self._term_peer:
                self._term_peer.poke()
            # 창을 다시 불러와도(F5) 모든 세션에 다시 붙는다 — 출력은 세션이 들고 있다
            ids = [session.id for session in self._terms.sessions()]
            made.run_js('window.deskTerm && window.deskTerm.attachAll(%s, %s)' % (json.dumps(ids), json.dumps(focus_id)))
            try:
                from webview.dom import DOMEventHandler
                made.dom.document.events.drop += DOMEventHandler(
                    lambda event, w=made: self._term_dropped(w, event), prevent_default=True)
            except Exception as exc:
                self._log('에이전트 터미널에 파일 끌어 놓기를 켜지 못했습니다:', exc)

        def closing(made=window):
            """창의 ✕ — 켜진 에이전트가 있으면 닫지 않고 화면에 묻는다 (답은 term_window_close).
            UI 스레드에서 곧바로 불리므로 여기서 기다리거나 화면에 물어 답을 받으면 안 된다."""
            if (self._term_leave or self._shutdown.is_set() or not self._term_ready
                    or not (self._terms and self._terms.alive())):
                return True

            def ask():
                try:
                    shown = made.evaluate_js('!!(window.deskTerm && window.deskTerm.askLeave && window.deskTerm.askLeave())')
                except Exception:
                    shown = False
                if shown is not True:               # 화면이 묻지 못한다 — 창이 닫히지 않는 일이 없게 예전처럼 모두 끄고 닫는다
                    self._term_window_close({'keep': False})
            threading.Thread(target=ask, name='agent-term-leave', daemon=True).start()
            return False

        def closed(made=window):
            with self._lock:
                if self._term_window is made:
                    self._term_window, self._term_ready = None, False
                keep, self._term_leave = self._term_leave == 'keep' and not self._shutdown.is_set(), None
            if self._terms:
                self._terms.window_open = False
            if self._terms and not keep:
                # '모두 끄기' — 다시 켤 목록도 빈다 (끝내는 중이면 그대로 둔다). 상주 에이전트는 남긴다(데스크를 끝낼 때만 끈다)
                self._terms.close_all(keep_resident=not self._shutdown.is_set())
                if self._terms.resident():
                    self._log('에이전트 터미널을 닫았습니다 — 상주 에이전트는 켜 둡니다.')
            elif keep:
                self._terms.save()
                self._log(f'에이전트 터미널 창을 닫았습니다 — 에이전트 {len(self._terms.alive())}개는 켜 둡니다.')
            if self._term_bridge:                       # 창과 함께 화면 조작 허락·사진도 걷는다
                self._term_bridge.revoke()
                if self._term_bridge.computer:
                    self._term_bridge.computer.clear_shots()
            self._term_computer_cancel()
            self._cron_ask_cancel()                     # 묻던 예약 승인은 «답 없음» — 승인 대기로 저장된다
            self._term_peer_cancel()                    # 다른 PC: 묻던 것은 거절, '이번만' 허락을 걷고 목록에서 빠진다
            if self._term_peer:
                self._term_peer.forget()
        window.events.loaded += loaded
        window.events.closing += closing
        window.events.closed += closed
        self._front_when_loaded(window)

    def _term_js(self, script: str):
        """작업 공간 창의 화면에 묻는다 — 창이 없거나 답하지 못하면 None (중계가 출력에서 대강 뽑는다)."""
        with self._lock:
            window = self._term_window if self._term_ready else None
        if window is None:
            return None
        try:
            return window.evaluate_js(script)
        except Exception:
            return None

    def _term_screen(self, session, lines: int):
        text = self._term_js('window.deskTerm ? window.deskTerm.screenOf(%s, %d) : null' % (json.dumps(session.id), lines))
        return text if isinstance(text, str) else None

    def _term_choice(self, session):
        answer = self._term_js('window.deskTerm ? window.deskTerm.choiceOf(%s) : null' % json.dumps(session.id))
        return answer if isinstance(answer, bool) else None

    # ── 에이전트의 화면 조작 (2026-10-25 요청, Orca 의 computer use 처럼) ──────────
    # 에이전트가 다른 앱 창을 읽고 누르고 글자를 친다 (core/computer_use.py, 중계 /computer/*). 에이전트가 처음 다루는 앱마다
    # 작업 공간 창에서 사람에게 묻고(허락·거절, 2분 안에 답이 없으면 거절), 허락해 둔 동안은 늘 위에 뜨는 '멈추기' 막대를 띄운다.
    def _term_computer_ask(self, session, info) -> bool:
        """중계의 스레드에서 부른다 — 사람이 답할 때까지 기다린다."""
        import uuid
        with self._lock:
            window = self._term_window if self._term_ready else None
        if window is None:
            return False
        request = uuid.uuid4().hex
        waiting = {'event': threading.Event(), 'allow': False, 'app': info['app']}
        with self._lock:
            self._term_asks[request] = waiting
        try:
            window.run_js('window.deskTerm && window.deskTerm.askComputer(%s)' % json.dumps(
                {'id': request, 'session': session.id, 'agent': session.title or session.name,
                 'app': info['app'], 'title': info['title']}))
            window.show()
            window.restore()
            self._bring_front(window)
            waiting['event'].wait(COMPUTER_ASK_WAIT)
            return waiting['allow']
        finally:
            with self._lock:
                self._term_asks.pop(request, None)
            try:
                window.run_js('window.deskTerm && window.deskTerm.askDone(%s)' % json.dumps(request))
            except Exception:
                pass

    def _term_computer_answer(self, payload):
        """always — 허락하면서 'app'(이 앱은 늘) · 'all'(모든 앱을 늘) 로 정해 둔다. 없으면 이번만(창을 닫을 때까지)."""
        request, allow, always = payload.get('request'), payload.get('allow'), payload.get('always')
        if not isinstance(request, str) or not isinstance(allow, bool) or always not in (None, 'app', 'all'):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        with self._lock:
            waiting = self._term_asks.get(request)
        if waiting is None:
            raise ValueError('이미 끝난 질문입니다.')
        if allow and always:
            self._term_computer_always({'all': True} if always == 'all' else {'add': waiting['app']})
        waiting['allow'] = allow
        waiting['event'].set()
        if not allow:
            return '거절했습니다.'
        scope = {'all': '모든 앱을 항상 허락합니다', 'app': f'{waiting["app"]} 은(는) 항상 허락합니다'}.get(always, '허락했습니다')
        return f'{scope}. 멈추려면 화면 위쪽의 ‘멈추기’를, 바꾸려면 ‘화면 조작’ 단추를 누르세요.'

    def _term_computer_cancel(self):
        with self._lock:
            pending = list(self._term_asks.values())
        for waiting in pending:
            waiting['event'].set()                    # 답 없이 끝낸다 = 거절

    def _term_computer_list(self, _):
        grants = self._term_bridge.grants() if self._term_bridge else []
        return {'grants': grants, 'halted': bool(self._term_bridge and self._term_bridge.halted), **self._term_always_rules()}

    # '항상 허락' (2026-10-26 요청) — 앱마다 또는 모든 앱을 데스크 설정에 남겨 다음에도 묻지 않는다.
    # 그래도 작업 공간 창이 열려 있을 때만 쓴다 (창을 닫으면 허락을 걷는 약속은 그대로). 막아 둔 앱은 늘 막는다.
    def _term_always_rules(self) -> dict:
        preferences = self._read_preferences()
        apps = preferences.get('computer_always_apps')
        apps = [app for app in apps if isinstance(app, str)] if isinstance(apps, list) else []
        return {'all': preferences.get('computer_always_all') is True, 'apps': apps}

    def _term_computer_always_match(self, info) -> bool:
        with self._lock:
            if not (self._term_window and self._term_ready):
                return False
        rules = self._term_always_rules()
        return rules['all'] or info['app'].lower() in {app.lower() for app in rules['apps']}

    def _term_computer_options(self, _):
        """화면 조작 설정 창 — 항상 허락 규칙 · 지금 허락 · 멈춤 · 지금 열린 앱(골라 더하기)."""
        self._term_manager()
        opened, seen = [], set()
        if self._term_bridge and self._term_bridge.computer:
            try:
                rows = self._term_bridge.computer.apps()
            except Exception:
                rows = []
            for row in rows:
                if row['blocked'] or row['app'] == '?' or row['app'].lower() in seen:
                    continue
                seen.add(row['app'].lower())
                opened.append({'app': row['app'], 'title': row['title']})
        return {**self._term_computer_list(None), 'open': opened, 'team': self._term_team()}

    def _term_computer_always(self, payload):
        """{'all': bool} · {'add': 앱} · {'remove': 앱} · {'clear': True} — 더 허락하는 쪽으로 바꾸면 멈춤도 푼다."""
        from core import computer_use
        rules = self._term_always_rules()
        apps, everything = rules['apps'], rules['all']
        if isinstance(payload.get('all'), bool):
            everything = payload['all']
            message = '모든 앱을 묻지 않고 허락합니다.' if everything else '모든 앱 항상 허락을 껐습니다.'
        elif isinstance(payload.get('add'), str) and payload['add'].strip():
            app = payload['add'].strip()[:120]
            if computer_use.blocked(app, ''):
                raise ValueError(f'{app} 은(는) 막아 둔 앱이라 허락할 수 없습니다.')
            if app.lower() not in {item.lower() for item in apps}:
                if len(apps) >= COMPUTER_ALWAYS_LIMIT:
                    raise ValueError(f'항상 허락은 {COMPUTER_ALWAYS_LIMIT}개까지 둘 수 있습니다.')
                apps = apps + [app]
            message = f'{app} 은(는) 이제 묻지 않고 허락합니다.'
        elif isinstance(payload.get('remove'), str):
            apps = [item for item in apps if item.lower() != payload['remove'].lower()]
            message = f'{payload["remove"]} 은(는) 다시 처음에 묻습니다.'
        elif payload.get('clear') is True:
            apps, everything = [], False
            message = '항상 허락을 모두 지웠습니다. 앱마다 처음에 묻습니다.'
        else:
            raise ValueError('요청 형식이 올바르지 않습니다.')
        self._save_preferences(computer_always_all=everything, computer_always_apps=apps)
        if self._term_bridge:
            if (everything and not rules['all']) or len(apps) > len(rules['apps']):
                self._term_bridge.resume()
            else:
                self._term_bar_update()
        return message

    def _term_computer_resume(self, _):
        if self._term_bridge:
            self._term_bridge.resume()
        return '항상 허락을 다시 씁니다.'

    def _term_computer_stop(self, payload):
        """화면 조작 허락을 거둔다 — session·app 을 주면 그것만, 아니면 모두 (멈추기)."""
        if not self._term_bridge:
            return '허락해 둔 앱이 없습니다.'
        session, app = payload.get('session'), payload.get('app')
        if (session is not None and not isinstance(session, str)) or (app is not None and not isinstance(app, str)):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        everything = session is None and app is None
        count = self._term_bridge.revoke(session, app, halt=everything)
        if everything:
            self._term_computer_cancel()              # 묻고 있던 것도 거절로 끝낸다
        rules = self._term_always_rules()
        if everything and (rules['all'] or rules['apps']):
            return f'화면 조작을 멈췄습니다 ({count}개 허락을 거뒀습니다). 항상 허락도 ‘다시 켜기’ 전까지 쉬고, 그동안은 묻습니다.'
        return f'화면 조작을 멈췄습니다 ({count}개 허락을 거뒀습니다).' if count else '허락해 둔 앱이 없습니다.'

    def _term_bar_update(self):
        """허락이 있으면 늘 위에 '멈추기' 막대를, 없으면 걷는다. 중계 스레드에서 부르므로 창 만들기는 따로 돌린다."""
        grants = self._term_bridge.grants() if self._term_bridge else []
        with self._lock:
            bar = self._term_bar
        if grants and bar is None and not self._shutdown.is_set():
            threading.Thread(target=self._term_bar_open, name='computer-bar', daemon=True).start()
        elif not grants and bar is not None:
            with self._lock:
                self._term_bar = None
            try:
                bar.destroy()
            except Exception:
                pass
        elif bar is not None:
            try:
                bar.run_js('window.deskBar && window.deskBar.refresh()')
            except Exception:
                pass
        with self._lock:
            window = self._term_window if self._term_ready else None
        if window is not None:
            try:
                window.run_js('window.deskTerm && window.deskTerm.grantsChanged()')
            except Exception:
                pass

    def _term_bar_open(self):
        import webview
        width, height = COMPUTER_BAR_SIZE
        screen_width = _user32.GetSystemMetrics(0) or 1280
        bar = webview.create_window('에이전트 화면 조작 · 멈추기', str(WEB_DIR / 'computer-bar.html'), js_api=self,
                                    width=width, height=height, x=max(0, (screen_width - width) // 2), y=8,
                                    frameless=True, easy_drag=True, on_top=True, focus=False, resizable=False,
                                    background_color='#7f1d1d')
        with self._lock:
            mine = self._term_bar is None
            if mine:
                self._term_bar = bar
        if not mine:                                                  # 그사이 다른 쪽이 띄웠다
            bar.destroy()
            return

        def closed(made=bar):
            with self._lock:
                if self._term_bar is made:
                    self._term_bar = None
        bar.events.closed += closed
        if not (self._term_bridge and self._term_bridge.grants()):  # 띄우는 사이 모두 멈췄다
            self._term_bar_update()

    # ── 다른 PC 의 에이전트와 메시지 (2026-10-27 요청, 1단계) ──────────
    # SPACEKIJUN 이 중계한다 (core/agent_peer.py, 서버 spacekijun 20261027120000_desk_agent_peer.sql). 교직원끼리만, 메시지·결과만.
    # 켜 두고(설정 agent_peer) 작업 공간 창이 열려 있고 로그인돼 있을 때만 이 PC 를 알린다. 새 요청은 보낸 사람마다 묻는다 —
    # 이번만(이 창을 닫을 때까지 그 사람) · 이 사람은 항상(설정 agent_peer_trusted) · 거절. 2분 안에 답이 없으면 거절.
    def _term_peer_link(self):
        from core import agent_peer, desk_message
        device = self._agent_peer_device()
        link = agent_peer.Link(self._terms, lambda name, body: desk_message._request('POST', f'rpc/{name}', body=body),
                               self._term_bridge.status, device, os.environ.get('COMPUTERNAME') or socket.gethostname(),
                               enabled=self._term_peer_enabled, approve=self._term_peer_ask,
                               trusted=lambda resource_id: resource_id in {item['id'] for item in self._term_peer_trusted()},
                               log=self._log, phone=self._term_peer_phone, cross=self._term_peer_on)
        link.start()
        return link

    def _term_peer_phone(self) -> bool:
        """내 휴대폰(스페이스기전 모바일 /m)과 주고받기 — 머리의 «휴대폰» 스위치 (2026-10-29 요청, 2026-10-30 «다른 PC» 와 따로).
        켜면 휴대폰에서 보낸 것을 묻지 않고 넣는다. 켜지 않았으면 꺼짐 — 켜면 이 PC 와 에이전트 이름이 서버에 알려진다."""
        return self._read_preferences().get('agent_peer_phone') is True

    def _term_peer_on(self) -> bool:
        return self._read_preferences().get('agent_peer') is True

    def _term_peer_enabled(self) -> bool:
        from core import supa_auth
        with self._lock:
            window_open = bool(self._term_window and self._term_ready)
        # «다른 PC» 나 «휴대폰» 하나만 켜도 서버에 알린다 — 무엇을 받을지는 agent_peer.Link 가 둘을 따로 본다
        return (window_open and (self._term_peer_on() or self._term_peer_phone())
                and supa_auth.load_session() is not None)

    def _term_peer_trusted(self) -> list[dict]:
        saved = self._read_preferences().get('agent_peer_trusted')
        return [item for item in saved if isinstance(item, dict) and isinstance(item.get('id'), str)
                and isinstance(item.get('name'), str)] if isinstance(saved, list) else []

    def _term_peer_ask(self, message, target):
        """agent_peer 의 스레드에서 부른다 — 사람이 답할 때까지 기다린다. 'once' · 'always' · None(거절)."""
        import uuid
        with self._lock:
            window = self._term_window if self._term_ready else None
        if window is None:
            return None
        request = uuid.uuid4().hex
        sender = message['sender']
        waiting = {'event': threading.Event(), 'answer': None, 'sender': {'id': sender['resource_id'], 'name': sender['name']}}
        with self._lock:
            self._term_peer_asks[request] = waiting
        try:
            window.run_js('window.deskTerm && window.deskTerm.askPeer(%s)' % json.dumps(
                {'id': request, 'session': target.id, 'target': target.title or target.name, 'skip': bool(getattr(target, 'skip', False)),
                 'name': sender['name'], 'label': sender['label'], 'agent': sender['agent'], 'body': message['body'][:4000],
                 'long': len(message['body']) > 4000}))
            window.show()
            window.restore()
            self._bring_front(window)
            waiting['event'].wait(PEER_ASK_WAIT)
            return waiting['answer']
        finally:
            with self._lock:
                self._term_peer_asks.pop(request, None)
            try:
                window.run_js('window.deskTerm && window.deskTerm.askDone(%s)' % json.dumps(request))
            except Exception:
                pass

    def _term_peer_answer(self, payload):
        if edition.STUDENT:
            raise ValueError('다른 PC 와 메시지는 교직원만 쓸 수 있습니다.')
        request, answer = payload.get('request'), payload.get('answer')
        if not isinstance(request, str) or answer not in ('once', 'always', 'deny'):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        with self._lock:
            waiting = self._term_peer_asks.get(request)
        if waiting is None:
            raise ValueError('이미 끝난 질문입니다.')
        name = waiting['sender']['name']
        if answer == 'always':
            trusted = [item for item in self._term_peer_trusted() if item['id'] != waiting['sender']['id']]
            self._save_preferences(agent_peer_trusted=(trusted + [waiting['sender']])[-PEER_TRUSTED_LIMIT:])
        waiting['answer'] = None if answer == 'deny' else answer
        waiting['event'].set()
        return {'once': f'{name} 선생님의 메시지를 넣었습니다. 이 창을 닫을 때까지는 다시 묻지 않습니다.',
                'always': f'{name} 선생님의 메시지는 앞으로 묻지 않고 넣습니다. ‘다른 PC’ 단추에서 뺄 수 있어요.',
                'deny': '거절했습니다. 보낸 쪽에 거절로 알립니다.'}[answer]

    def _term_peer_cancel(self):
        with self._lock:
            pending = list(self._term_peer_asks.values())
        for waiting in pending:
            waiting['event'].set()                    # 답 없이 끝낸다 = 거절

    def _term_peer_state(self, _):
        link = self._term_peer if self._term_peer or edition.STUDENT else (self._term_manager() and self._term_peer)
        if link is None:
            return {'available': False}
        return {'available': True, 'on': self._term_peer_on(), 'team': self._term_team(), 'phone': self._term_peer_phone(),
                'trusted': self._term_peer_trusted(), **link.state()}

    # ── 내 다른 PC (2026-11-12 요청) — 왼쪽 패널 «내 다른 PC» 방. 다른 선생님과의 연결(«다른 PC»)과 따로, «내 기기» 스위치를 따른다.
    def _term_own_link(self):
        if edition.STUDENT:
            raise ValueError('내 다른 PC 와 주고받기는 교직원만 쓸 수 있습니다.')
        link = self._term_peer or (self._term_manager() and self._term_peer)
        if link is None:
            raise ValueError('에이전트 터미널이 아직 준비되지 않았습니다.')
        return link

    def _term_own(self, _):
        """내 다른 PC·에이전트와 이 화면이 보낸 것·답. 꺼져 있거나 연결 전이면 그 까닭만."""
        from core import agent_peer
        link = self._term_own_link()
        if not self._term_peer_phone():
            return {'on': False, 'reason': '«내 기기»를 켜면 내 다른 PC 의 에이전트가 여기 보입니다.'}
        try:
            return {'on': True, **link.own_overview()}
        except agent_peer.PeerError as exc:
            return {'on': True, 'pcs': [], 'messages': [], 'reason': str(exc)}

    def _term_own_send(self, payload):
        from core import agent_peer
        link = self._term_own_link()
        try:
            return link.own_send(str(payload.get('device') or ''), str(payload.get('agent') or ''),
                                 str(payload.get('body') or ''), str(payload.get('thread') or ''))
        except agent_peer.PeerError as exc:
            raise ValueError(str(exc)) from None

    def _term_peer_set(self, payload):
        if edition.STUDENT:
            raise ValueError('다른 PC 와 메시지는 교직원만 쓸 수 있습니다.')
        if isinstance(payload.get('on'), bool):
            self._save_preferences(agent_peer=payload['on'])
            if self._term_peer:
                self._term_peer.poke()
            return ('이 PC 를 SPACEKIJUN 에 알립니다. 다른 선생님의 에이전트가 이 PC 의 에이전트에게 메시지를 보낼 수 있고, '
                    '넣기 전에 늘 먼저 묻습니다.' if payload['on'] else '다른 PC 와 메시지를 껐습니다. 이 PC 는 목록에서 빠집니다.')
        if isinstance(payload.get('phone'), bool):
            self._save_preferences(agent_peer_phone=payload['phone'])
            if self._term_peer:
                self._term_peer.poke()
            return ('내 휴대폰(스페이스기전 모바일 «에이전트» 탭)과 주고받습니다 — 휴대폰에서 보낸 것은 묻지 않고 에이전트에게 넣습니다.'
                    if payload['phone'] else '휴대폰과 주고받기를 껐습니다.')
        if isinstance(payload.get('remove'), str):
            trusted = self._term_peer_trusted()
            gone = [item for item in trusted if item['id'] == payload['remove']]
            self._save_preferences(agent_peer_trusted=[item for item in trusted if item['id'] != payload['remove']])
            return f'{gone[0]["name"]} 선생님의 메시지는 다시 처음에 묻습니다.' if gone else '목록에 없는 사람입니다.'
        raise ValueError('요청 형식이 올바르지 않습니다.')

    def _term_dropped(self, window, event):
        """끌어 놓은 파일의 전체 경로 — 화면(브라우저)은 경로를 모르므로 pywebview 가 알려 준 것을 넘긴다."""
        try:
            files = (event.get('dataTransfer') or {}).get('files') or []
            paths = [item.get('pywebviewFullPath') for item in files if isinstance(item, dict)]
            paths = [path for path in paths if isinstance(path, str) and path][:50]
            if paths:
                window.run_js('window.deskTerm && window.deskTerm.dropped(%s)' % json.dumps(paths))
        except Exception as exc:
            self._log('끌어 놓은 파일을 넣지 못했습니다:', exc)

    def _term_session(self, payload):
        return self._term_manager().get(payload.get('id'))

    def _term_status(self, session) -> dict:
        running = session.agent_running()
        return {**session.info(), 'running': running,
                'state': self._term_bridge.status(session) if self._term_bridge else ('working' if running else 'ended')}

    def _term_info(self, payload):
        return self._term_status(self._term_session(payload))

    def _term_list(self, payload):
        """작업 공간의 에이전트들과 상태. tools 를 달라면 설치된 에이전트도 (＋ 새 에이전트 고르기)."""
        terms = self._term_manager()
        answer = {'sessions': [self._term_status(session) for session in terms.sessions()], 'team': self._term_team()}
        if payload.get('tools'):
            from core import agent
            answer['tools'] = agent.tools()
            answer['tool'] = self._agent_choice()[0]
        return answer

    def _term_read(self, payload):
        """새 출력을 기다렸다 준다 (길게 기다리기 — core/agent_term.py READ_WAIT)."""
        session = self._term_session(payload)
        cursor = payload.get('cursor', 0)
        if not isinstance(cursor, int) or cursor < 0:
            raise ValueError('요청 형식이 올바르지 않습니다.')
        epoch = payload.get('epoch')
        result = session.read(cursor, epoch=epoch if isinstance(epoch, int) else None)
        result['running'] = session.agent_running()
        return result

    def _term_write(self, payload):
        self._term_session(payload).write(payload.get('data'))

    def _term_resize(self, payload):
        self._term_session(payload).resize(payload.get('cols'), payload.get('rows'))

    def _term_restart(self, payload):
        self._term_manager().restart(payload.get('id'))
        return '에이전트를 다시 시작했습니다.'

    def _term_close(self, payload):
        """작업 공간에서 에이전트 하나를 닫는다 (그 프로세스를 끝낸다). 상주 에이전트면 상주도 푼다(화면이 먼저 묻는다)."""
        session = self._term_session(payload)
        if session.resident:
            self._resident_forget(session.name)
            self._log(f'상주 에이전트 {session.title or session.name} 를 닫아 상주를 풀었습니다.')
        self._terms.close(session.id)
        if self._term_bridge:
            self._term_bridge.revoke(session.id)
        return f'{session.title or session.name} 를 닫았습니다.'

    def _term_window_close(self, payload):
        """창을 닫을 때 물은 것의 답 — keep 이면 에이전트를 켜 둔 채 창만 닫는다."""
        keep = payload.get('keep')
        if not isinstance(keep, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        with self._lock:
            window = self._term_window
            self._term_leave = 'keep' if keep else 'stop'
        if window is not None:
            threading.Thread(target=window.destroy, name='agent-term-close', daemon=True).start()

    def _term_kept(self) -> int:
        """창 없이 켜 둔 에이전트 수 (창이 열려 있으면 0)."""
        with self._lock:
            if self._term_window is not None or self._terms is None:
                return 0
        return len(self._terms.alive())

    def _term_show_kept(self, _=None) -> str:
        """켜 둔 에이전트들이 있는 창을 다시 연다. 창이 이미 열려 있으면 고른 에이전트 그대로 앞으로만 가져온다."""
        alive = self._terms.alive() if self._terms else []
        if not alive:
            raise RuntimeError('켜 둔 에이전트가 없습니다.')
        with self._lock:
            window, ready = self._term_window, self._term_ready
        if window is not None and ready:
            window.show()
            window.restore()
            self._bring_front(window)
            return f'에이전트 터미널을 앞으로 가져왔습니다 (에이전트 {len(alive)}개).'
        self._term_show(alive[-1].id)
        return f'켜 둔 에이전트 {len(alive)}개를 다시 보입니다.'

    def _term_rename(self, payload):
        session = self._term_manager().rename(payload.get('id'), payload.get('title'))
        return {**self._term_status(session), 'remoteNote': session.remote_note}

    def _term_events(self, payload):
        """에이전트 사이 대화 기록 — after 뒤의 것. wait 초까지 새 일을 기다린다."""
        after, wait = payload.get('after', 0), payload.get('wait', 0)
        if not isinstance(after, int) or not isinstance(wait, (int, float)):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        return self._term_manager().events(after, max(0, min(float(wait), 4.0)))

    # 현황 (2026-10-30 요청) — 고른 에이전트의 컨텍스트 크기·사용량·결과물(Claude 가 만들거나 고친 파일). core/agent_usage.py
    def _usage_reader(self):
        from core import agent_usage
        with self._lock:
            if getattr(self, '_agent_usage', None) is None:
                self._agent_usage = agent_usage.Reader()
            return self._agent_usage

    def _term_usage(self, payload):
        from core import agent_term
        session = self._term_session(payload)
        base = {'id': session.id, 'tool': session.tool, 'title': session.title or session.name, 'folder': session.folder}
        if session.tool != 'claude':
            return {**base, 'supported': False}
        conversation = session.current_conversation()
        return {**base, 'supported': True,
                **self._usage_reader().read(conversation, agent_term.status_file(Path(watcher.DATA_DIR), session.name))}

    # 대화 보기 (2026-11-06 요청, 테스트 판) — 터미널 글자 화면 대신 대화 기록을 말풍선으로. core/agent_chat.py
    def _chat_reader(self):
        from core import agent_chat
        with self._lock:
            if getattr(self, '_agent_chat', None) is None:
                self._agent_chat = agent_chat.Reader()
            return self._agent_chat

    def _term_chat(self, payload):
        session = self._term_session(payload)
        if session.tool != 'claude':
            return {'supported': False, 'items': [], 'rev': 0, 'reset': True, 'conversation': ''}
        reader = self._chat_reader()
        since = payload.get('since', 0)
        since = since if isinstance(since, int) and since > 0 else 0
        conversation = session.current_conversation()
        if payload.get('conversation') != conversation:
            since = 0                                   # /clear·지난 대화로 대화가 바뀌었다 — 처음부터
        return {'supported': True, **reader.read(conversation, since)}

    def _term_chat_image(self, payload):
        """대화 보기의 사진 하나 (스크린샷·붙여 넣은 사진·도구가 만든 그림) — 그 에이전트의 지금 대화에 나온 것만."""
        session = self._term_session(payload)
        if session.tool != 'claude':
            return {'ok': False}
        found = self._chat_reader().image(session.current_conversation(), str(payload.get('key') or ''))
        return {'ok': True, **found} if found else {'ok': False}

    def _term_output_open(self, payload):
        """결과물 열기 — 그 에이전트의 지금 대화가 만들거나 고친 파일만. reveal 이면 탐색기에서 그 파일을 고른 채로."""
        session = self._term_session(payload)
        path = payload.get('path')
        if session.tool != 'claude' or not self._usage_reader().has_output(session.current_conversation(), path):
            raise ValueError('이 에이전트의 결과물이 아닙니다.')
        if not os.path.exists(path):
            raise ValueError('파일이 없습니다 — 옮기거나 지웠을 수 있어요.')
        if payload.get('reveal'):
            subprocess.Popen(['explorer.exe', '/select,', os.path.normpath(path)])
        else:
            os.startfile(path)

    def _term_events_clear(self, _=None):
        self._term_manager().clear_events()
        return '에이전트 대화 기록을 비웠습니다.'

    def _term_team_set(self, payload):
        on = payload.get('on')
        if not isinstance(on, bool):
            raise ValueError('설정 형식이 올바르지 않습니다.')
        self._save_preferences(agent_team=on)
        return ('새로 여는 에이전트부터 서로를 볼 수 있습니다.' if on
                else '새로 여는 에이전트는 다른 에이전트를 볼 수 없습니다. (이미 연 에이전트는 다시 열어야 바뀝니다)')

    def _term_new(self, payload):
        """작업 공간의 ＋ — 고른 에이전트를 (같은 폴더 | 고른 폴더) 에서 하나 더 연다."""
        import webview
        from core import agent
        tool = payload.get('tool')
        if tool not in agent.TOOLS:
            raise ValueError('지원하지 않는 에이전트입니다.')
        if not agent.find(tool):
            raise RuntimeError(f'{agent.TOOLS[tool]["label"]} 가 설치되어 있지 않습니다. 독의 에이전트 터미널 패널에서 설치해 주세요.')
        folder = payload.get('folder')
        if folder == 'pick':
            with self._lock:
                window = self._term_window
            if window is None:
                raise RuntimeError('작업 공간 창을 찾을 수 없습니다.')
            start = payload.get('near') if isinstance(payload.get('near'), str) and os.path.isdir(payload['near']) else ''
            picked = window.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
            if not picked:
                return None
            folder = picked[0] if isinstance(picked, (list, tuple)) else picked
        folder = self._agent_folder(folder)
        _tool, skip = self._agent_choice()
        message = self._term_open(tool, folder, skip)
        self._log(message)
        return message

    # 화면에 나온 파일·폴더 주소를 눌러 열기 (2026-11-09 요청, core/agent_paths.py) — 있는 것만 밑줄, 실행 파일은 탐색기에서 골라 보임
    def _term_paths(self, payload):
        from core import agent_paths
        return agent_paths.check(self._term_session(payload).folder, payload.get('items'))

    def _term_path_open(self, payload):
        from core import agent_paths
        how = agent_paths.open_path(payload.get('path'), reveal=payload.get('reveal') is True)
        name = Path(payload['path']).name or payload['path']
        if how == 'revealed' and payload.get('reveal') is not True:
            return f'{name} 은(는) 실행되는 파일이라 열지 않고 탐색기에서 보여 줍니다.'
        return None

    def _term_reveal(self, payload):
        """작업 폴더를 탐색기로 연다."""
        folder = self._term_session(payload).folder
        if not os.path.isdir(folder):
            raise ValueError('폴더를 찾을 수 없습니다. 옮기거나 지웠는지 확인해 주세요.')
        os.startfile(folder)

    def _term_pick_files(self, payload):
        """파일 고르기 창 — 고른 파일들의 전체 경로 (입력칸에 넣는다)."""
        import webview
        session = self._term_session(payload)
        with self._lock:
            window = self._term_window
        if window is None:
            raise RuntimeError('작업 공간 창을 찾을 수 없습니다.')
        picked = window.create_file_dialog(webview.FileDialog.OPEN, directory=session.folder, allow_multiple=True)
        return [str(path) for path in picked or []][:50]

    def _term_complete(self, payload):
        """입력칸 자동 완성 (2026-11-08 요청) — kind 'commands'(빗금 명령) · 'files'(@ 파일, query 로 찾기). core/agent_complete.py"""
        from core import agent_complete
        session = self._term_session(payload)
        kind = payload.get('kind')
        if kind == 'commands':
            return agent_complete.commands(session.tool, session.folder)
        if kind == 'files':
            query = payload.get('query')
            return agent_complete.files(session.folder, query[:200] if isinstance(query, str) else '')
        raise ValueError('요청 형식이 올바르지 않습니다.')

    def _term_external(self, payload):
        """이 폴더를 바깥 터미널(Windows Terminal·명령 창)로도 연다 — 익숙한 사람용."""
        from core import agent
        session = self._term_session(payload)
        _tool, skip = self._agent_choice()
        message = agent.launch(session.tool, session.folder, skip, Path(watcher.DATA_DIR))
        self._log(message)
        return message

    def _term_snippets(self, _):
        """저장한 '자주 쓰는 말'. 한 번도 고친 적 없으면 None — 화면이 기본 목록을 쓴다."""
        saved = self._read_preferences().get('agent_snippets')
        if not isinstance(saved, list):
            return None
        return [{'label': item['label'], 'text': item['text']} for item in saved
                if isinstance(item, dict) and isinstance(item.get('label'), str) and isinstance(item.get('text'), str)]

    def _term_snippets_save(self, payload):
        items = payload.get('items')
        if not isinstance(items, list) or len(items) > SNIPPET_LIMIT:
            raise ValueError(f'자주 쓰는 말은 {SNIPPET_LIMIT}개까지 둘 수 있습니다.')
        clean = []
        for item in items:
            label = item.get('label') if isinstance(item, dict) else None
            text = item.get('text') if isinstance(item, dict) else None
            if not isinstance(label, str) or not isinstance(text, str) or not text.strip():
                raise ValueError('자주 쓰는 말의 형식이 올바르지 않습니다.')
            if len(text) > SNIPPET_LENGTH:
                raise ValueError(f'자주 쓰는 말 하나는 {SNIPPET_LENGTH}자까지입니다.')
            clean.append({'label': (label.strip() or text.strip())[:40], 'text': text})
        self._save_preferences(agent_snippets=clean)
        return '자주 쓰는 말을 저장했습니다.'

    # ── 자동화 업무 (교사판 전용) ───────────────────────────────
    # 업무용 스킬(쿨메신저 쪽지 보내기 등)을 **한 폴더**에 깔아 두고 그 폴더에서 에이전트를 연다 (2026-10-22 요청).
    # 스킬이 늘어도 폴더는 늘지 않는다. Claude Code 는 원격 제어(휴대폰·웹)에 자동으로 연결한다 — 설정으로 끌 수 있다.
    # Codex 는 쿨메신저 같은 **내 화면의 창**을 조작하려면 샌드박스 밖이어야 해서 샌드박스만 풀고 승인은 유지한다.
    # 학생판에서는 받지 않는다(STUDENT_ACTIONS 에 없음). 만들고 까는 일은 core/automation.py.
    def _automation_folder(self) -> Path:
        from core import automation
        saved = self._read_preferences().get('automation_folder')
        if isinstance(saved, str) and saved and Path(saved).is_absolute():
            return Path(saved)
        return automation.default_workspace()

    def _automation_off(self) -> set[str]:
        """패널에서 끈 스킬 — 열 때·갱신할 때 다시 깔지 않는다 (2026-10-22). 새로 실린 스킬은 켜진 채로 온다."""
        saved = self._read_preferences().get('automation_off')
        return {name for name in saved if isinstance(name, str)} if isinstance(saved, list) else set()

    def _automation_rc(self) -> bool:
        return self._read_preferences().get('automation_rc') is not False        # 정하지 않았으면 켬

    def _automation_state(self, _):
        from core import agent, automation
        tool, skip = self._agent_choice()
        folder = self._automation_folder()
        off = self._automation_off()
        with self._lock:
            job = self._automation_job
        preparing = job[1] if job and job[0].poll() is None else []
        return {'folder': str(folder), 'exists': folder.is_dir(), 'tool': tool, 'installed': bool(agent.find(tool)),
                'rc': self._automation_rc(), 'rcTool': tool == 'claude', 'skip': skip, 'preparing': preparing,
                'skills': [{**row, 'on': row['name'] not in off} for row in automation.status(folder)]}

    def _automation_install(self, _):
        from core import automation
        message = automation.summary(automation.install(self._automation_folder(), skip=self._automation_off()))
        self._log('자동화 업무 폴더:', message)
        return message

    def _automation_open(self, _):
        from core import automation
        folder = self._automation_folder()
        automation.install(folder, skip=self._automation_off())   # 열 때마다 최신 판으로 맞춘다 (바뀐 것만, 끈 스킬은 빼고)
        automation.create_shortcut(folder)               # 바탕화면 바로가기 — 실제 폴더는 동기화되는 바탕화면 밖에 둔다
        running = self._automation_session()
        if running:                                      # 이미 켜 둔 자동화 업무 에이전트 — 그 에이전트를 앞에 (2026-10-30 요청)
            self._term_show(running.id)
            return f'켜 둔 자동화 업무 에이전트({running.title or running.name})를 보입니다. 새로 열려면 에이전트 터미널의 «새 에이전트».'
        waiting = self._automation_prepare(then_open=True)
        if waiting:
            return waiting                               # 필요한 프로그램부터 — 다 깔리면 에이전트를 연다
        return self._automation_launch()

    def _automation_session(self):
        """켜 둔 에이전트 중 자동화 업무 폴더에서 지금 고른 에이전트(Claude Code·Codex)로 연 것 — 가장 나중 것. 바깥 터미널 설정이면 없음."""
        if not self._agent_embedded() or not self._terms:
            return None
        tool, _skip = self._agent_choice()
        folder = os.path.normcase(os.path.normpath(str(self._automation_folder())))
        found = [session for session in self._terms.alive()
                 if session.tool == tool and os.path.normcase(os.path.normpath(session.folder)) == folder]
        return found[-1] if found else None

    def _automation_launch(self):
        from core import automation
        tool, skip = self._agent_choice()
        folder = self._automation_folder()
        remote = automation.RC_NAME if tool == 'claude' and self._automation_rc() else ''
        extra = ('--sandbox', 'danger-full-access') if tool == 'codex' and not skip else ()
        message = self._agent_open(tool, str(folder), skip, remote, extra)
        self._log(message)
        return message

    def _automation_skill(self, payload):
        """스킬 하나를 켜거나(깔기) 끈다(빼기) — 패널의 스킬 목록 스위치. 끈 것은 기억해 다시 깔지 않는다."""
        from core import automation
        name, on = payload.get('name'), payload.get('on')
        titles = {skill['name']: skill['title'] for skill in automation.catalog()}
        if name not in titles or not isinstance(on, bool):
            raise ValueError('스킬 설정 형식이 올바르지 않습니다.')
        folder = self._automation_folder()
        off = self._automation_off()
        off.discard(name) if on else off.add(name)
        self._save_preferences(automation_off=sorted(off))
        if on:
            states = set(automation.install(folder, only={name})[0]['states'].values())
            if states == {'foreign'}:
                return f"‘{titles[name]}’ — 같은 이름으로 직접 만든 스킬이 있어 그대로 뒀습니다."
            kept = ' (직접 만든 같은 이름이 있는 곳은 그대로 뒀습니다)' if 'foreign' in states else ''
            waiting = self._automation_prepare(then_open=False)
            return f"‘{titles[name]}’ 설치했습니다{kept}." + (f' {waiting}' if waiting else '')
        automation.uninstall(folder, name)
        return f"‘{titles[name]}’ 뺐습니다. 다시 켜기 전에는 설치하지 않습니다."

    # 켜 둔 스킬이 쓰는데 없는 Node.js·Python 은 데스크가 깐다 (2026-10-22 요청, core/automation.py `prepare_text`).
    # 열기·스킬 켜기에서 저절로, 패널의 '지금 설치' 로도. 설치 창은 하나만 — 열기에서 시작했으면 다 깔린 뒤 에이전트를 연다
    # (새로 연 터미널이라야 새 PATH 가 보인다). 실패하면 창이 남아 이유를 보이고, 에이전트는 열지 않는다.
    def _automation_prepare(self, then_open: bool) -> str | None:
        from core import automation
        programs = automation.missing_programs(self._automation_folder(), skip=self._automation_off())
        if not programs:
            return None
        labels = [automation.INSTALLERS[name] for name in programs]
        with self._lock:
            job = self._automation_job
            if job and job[0].poll() is None:
                if then_open:
                    self._automation_then_open = True
                return f"{', '.join(job[1])} 설치 창이 이미 열려 있습니다." + (' 끝나면 에이전트를 엽니다.' if then_open else '')
            self._automation_then_open = then_open
        process = automation.prepare(programs, Path(watcher.DATA_DIR),
                                     then='곧 에이전트를 엽니다.' if then_open else '')
        with self._lock:
            self._automation_job = (process, labels)
        threading.Thread(target=self._automation_prepared, args=(process, labels), daemon=True,
                         name='automation-prepare').start()
        self._log('자동화 업무: 필요한 프로그램 설치 —', ', '.join(labels))
        return (f"{', '.join(labels)} 이(가) 없어 설치 창을 열었습니다."
                + (' 다 깔리면 에이전트를 엽니다.' if then_open else ' 이 사용자에게만 깔고 관리자 권한은 묻지 않습니다.'))

    def _automation_prepared(self, process, labels):
        code = process.wait()
        with self._lock:
            then_open, self._automation_then_open = self._automation_then_open, False
        if code != 0:
            self._log('자동화 업무: 설치하지 못했습니다 —', ', '.join(labels), f'(종료 코드 {code})')
            return
        self._log('자동화 업무: 설치를 마쳤습니다 —', ', '.join(labels))
        if then_open and not self._shutdown.is_set():
            try:
                self._automation_launch()
            except Exception as exc:
                self._log('자동화 업무: 에이전트를 열지 못했습니다:', exc)

    def _automation_prepare_now(self, _):
        return self._automation_prepare(then_open=False) or '필요한 프로그램이 모두 있습니다.'

    # SPACEKIJUN 에이전트 연결(MCP) — 자동화 업무 폴더의 에이전트에 서버를 등록하고 인증 창을 띄운다 (2026-10-25 요청).
    # 로그인·승인은 선생님이 브라우저에서 직접 한다(인증 창의 `mcp login` 이 기다린다). 등록·상태·인증 창은 core/spacekijun_mcp.py.
    # 상태는 패널이 따로 묻는다(몇 초 걸린다) — 잠깐 기억해 두고, 연결·해제·인증 창이 닫히면 잊는다.
    MCP_FRESH = 20

    def _automation_mcp_state(self, payload):
        from core import spacekijun_mcp
        tool, _ = self._agent_choice()
        with self._lock:
            job = self._mcp_job
            busy = bool(job and job[0].poll() is None and job[1] == tool)
            seen = self._mcp_seen.get(tool)
        if busy:
            return {'tool': tool, 'state': 'authorizing', 'scope': '', 'manage': spacekijun_mcp.MANAGE_URL}
        if not payload.get('fresh') and seen and time.monotonic() - seen[0] < self.MCP_FRESH:
            return seen[1]
        found = {**spacekijun_mcp.status(tool, self._automation_folder()), 'manage': spacekijun_mcp.MANAGE_URL}
        with self._lock:
            self._mcp_seen[tool] = (time.monotonic(), found)
        return found

    def _automation_mcp_connect(self, _):
        """등록(없으면) → 아직 연결되지 않았으면 인증 창. 인증 창은 하나만."""
        from core import agent, automation, spacekijun_mcp
        tool, _ = self._agent_choice()
        label = agent.TOOLS[tool]['label']
        folder = self._automation_folder()
        with self._lock:
            job = self._mcp_job
            if job and job[0].poll() is None:
                return 'SPACEKIJUN 인증 창이 이미 열려 있습니다. 브라우저에서 로그인하고 [승인]을 눌러 주세요.'
            self._mcp_seen.pop(tool, None)
        automation.ensure_workspace(folder)
        try:
            spacekijun_mcp.register(tool, folder)
        except spacekijun_mcp.McpError as exc:
            raise ValueError(str(exc)) from None
        if spacekijun_mcp.status(tool, folder)['state'] == 'ok':
            return f'{label} 는 이미 SPACEKIJUN 에 연결되어 있습니다.'
        process = spacekijun_mcp.login(tool, folder, Path(watcher.DATA_DIR))
        with self._lock:
            self._mcp_job = (process, tool)
        threading.Thread(target=self._automation_mcp_done, args=(process, tool), daemon=True,
                         name='spacekijun-login').start()
        self._log(f'SPACEKIJUN 연결: {label} 에 등록하고 인증 창을 열었습니다.')
        return f'{label} 에 SPACEKIJUN 을 등록하고 인증 창을 열었습니다. 브라우저에서 직접 로그인하고 [승인]을 눌러 주세요.'

    def _automation_mcp_done(self, process, tool):
        from core import agent
        code = process.wait()
        with self._lock:
            self._mcp_seen.pop(tool, None)
        self._log(f'SPACEKIJUN 연결: {agent.TOOLS[tool]["label"]} 인증 ' + ('완료' if code == 0 else f'못 함 (종료 코드 {code})'))

    def _automation_mcp_disconnect(self, _):
        from core import agent, spacekijun_mcp
        tool, _ = self._agent_choice()
        with self._lock:
            self._mcp_seen.pop(tool, None)
        removed = spacekijun_mcp.remove(tool, self._automation_folder())
        label = agent.TOOLS[tool]['label']
        if not removed:
            return f'{label} 에 데스크가 등록한 SPACEKIJUN 연결이 없습니다 (직접 등록한 것은 그대로 둡니다).'
        self._log(f'SPACEKIJUN 연결: {label} 에서 뺐습니다.')
        return f'{label} 에서 SPACEKIJUN 연결을 뺐습니다. 서버 쪽 승인까지 거두려면 SPACEKIJUN 웹의 «연결된 에이전트»에서 해제하세요.'

    def _automation_mcp_manage(self, _):
        from core import spacekijun_mcp
        return self._open_link({'url': spacekijun_mcp.MANAGE_URL})

    def _automation_settings(self, payload):
        rc = payload.get('rc')
        if not isinstance(rc, bool):
            raise ValueError('설정 형식이 올바르지 않습니다.')
        self._save_preferences(automation_rc=rc)
        return '원격 제어 자동 연결 켬' if rc else '원격 제어 자동 연결 끔'

    # ── 자동 업데이트 (교사판, 2026-10-16 부터 학생판도) ─────────────────
    # 켜자마자 새 판을 확인해 뒤에서 받아 두고, **바꿀지 묻는다** (2026-10-26 요청 — 그전에는 묻지 않고
    # 다음에 켤 때나 손을 놓은 틈에 바꿨다). «나중에»면 이번에는 그대로 쓰고, 다음에 켤 때 다시 묻는다.
    # 켜 둔 동안 정기 확인(6시간)에서 새 판을 받아도 같은 판은 한 번만 묻는다.
    def _update_folder(self) -> Path:
        return Path(watcher.DATA_DIR) / 'update'

    @staticmethod
    def _ask_update(version: str, busy: str = '') -> bool:
        """«새 판으로 바꿀까요?» — 맨 위에 뜨는 Windows 창. 예면 True. 화면 쪽 창이 없어도(켜는 중) 뜬다."""
        note = f'\n\n지금 {busy} — 업데이트하면 닫혀요.' if busy else ''
        message = (f'{edition.TITLE} 새 판 {version} 이 있습니다. (지금 {edition.VERSION})\n\n'
                   f'지금 업데이트할까요? 프로그램이 잠깐 닫혔다가 다시 켜집니다.{note}\n\n'
                   '«아니요»를 누르면 지금 판을 그대로 쓰고, 다음에 켤 때 다시 물어봐요.')
        # MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND | MB_TOPMOST
        return _user32.MessageBoxW(None, message, f'{edition.TITLE} 업데이트', 0x4 | 0x20 | 0x10000 | 0x40000) == 6

    def _update_at_start(self, argv: list) -> bool:
        """켜자마자 — 받아 둔 새 판이 있으면 바꾸고 새 판을 띄운다 (True 면 이 프로그램은 곧 끝낸다).
        새 판으로 막 바뀌어 켜진 것이면 옛 판·받아 둔 파일을 치운다."""
        from core import updater
        exe = updater.target()
        if exe is None:
            return False
        if '--after-update' in argv:
            updater.finish(exe, self._update_folder())
            self._log(f'{edition.TITLE} {edition.VERSION} 로 업데이트했습니다.')
            return False
        record = updater.pending(self._update_folder(), edition.VERSION)
        if record is None:
            return False
        if not self._ask_update(record['version']):
            with self._lock:
                self._update_asked.add(record['version'])     # 켜 둔 동안은 다시 묻지 않는다
            self._log(f'새 판 {record["version"]} 업데이트를 미뤘습니다.')
            return False
        try:
            updater.start_install(record, exe, list(argv), updater.own_pids(), self._update_fallback(exe))
        except (OSError, updater.UpdateError) as exc:
            self._log('새 판을 설치하지 못했습니다:', exc)
            return False
        return True

    @staticmethod
    def _update_fallback(exe: Path):
        """새 판을 학생판 사용자 사본에 놓을 때 — 놓지 못하면 다시 띄울 지금의 실행 파일."""
        return None if Path(exe) == Path(sys.executable) else Path(sys.executable)

    def _start_updates(self):
        from core import updater
        exe = updater.target()
        if exe is None:
            return
        updater.sweep(exe, None)                   # 지난번 업데이트가 실행 파일 곁에 남긴 것
        with self._lock:
            if self._updater is None:
                self._updater = updater.Checker(edition.VERSION, self._update_folder(),
                                                self._update_ready, self._log, first=UPDATE_FIRST,
                                                channels=self._update_channels)
        self._updater.start()

    # 손으로 하는 업데이트 (2026-10-14 요청) — 설정의 «프로그램 업데이트»와 트레이 메뉴.
    # 확인·받기는 정기 확인과 같은 Checker 로(서명·조각 확인 그대로), 바꾸기는 손을 놓기를 기다리지 않고 바로.
    # 테스트 판 (2026-10-30 요청) — 관리자 계정만 «테스트 판 받기»를 켤 수 있고, 켜면 정식 판 통로와 테스트 판 통로 중 더 새 판을 받는다.
    # 학생판도 같다 (2026-11-04 요청): 관리자 계정으로 로그인한 학생판은 student-test 통로도 본다.
    def _is_admin(self) -> bool:
        from core import supa_auth
        with self._lock:
            cached = self._role_cache
        if cached and time.monotonic() - cached[1] < ROLE_TTL:
            return cached[0] == 'admin'
        role = supa_auth.my_role()
        with self._lock:
            self._role_cache = (role, time.monotonic())
        return role == 'admin'

    def _update_channels(self) -> list[str]:
        from core import updater
        channels = [updater.CHANNEL]
        try:
            if self._read_preferences().get('update_test') is True and self._is_admin():
                channels.append(updater.TEST_CHANNEL)
        except Exception as exc:
            self._log('테스트 판 받기 여부를 확인하지 못했습니다:', exc)
        return channels

    def _update_test(self, payload):
        on = payload.get('on')
        if not isinstance(on, bool):
            raise ValueError('설정 형식이 올바르지 않습니다.')
        if on and not self._is_admin():
            raise ValueError('테스트 판은 관리자 계정만 받을 수 있습니다.')
        self._save_preferences(update_test=on)
        self._log('테스트 판 받기를 ' + ('켰습니다.' if on else '껐습니다.'))
        return ('테스트 판도 받습니다 — 새 테스트 판이 있으면 «업데이트 확인»으로 바로 받을 수 있어요.' if on
                else '테스트 판을 받지 않습니다. 다음 정식 판부터 정식 판만 받습니다.')

    def _update_status(self, _=None):
        from core import updater
        with self._lock:
            job, record = self._update_job, self._update
            note, failed = self._update_note, self._update_failed
        checking = bool(job and job.is_alive())
        available = updater.target() is not None
        admin = self._is_admin()
        return {'version': edition.VERSION, 'available': available, 'checking': checking,
                'admin': admin, 'test': admin and self._read_preferences().get('update_test') is True,
                'ready': record['version'] if record else None,
                'note': note if available else '실행 파일로 켰을 때만 업데이트할 수 있습니다 (지금은 소스로 실행 중이거나 쓸 수 없는 폴더).',
                'failed': failed, 'busy': self._update_busy(manual=True) if record else ''}

    def _update_check(self, _=None):
        """지금 새 판을 확인하고, 있으면 받아 둔다 (뒤에서). 결과는 update_status 로."""
        from core import updater
        if updater.target() is None:
            raise ValueError('실행 파일로 켰을 때만 업데이트할 수 있습니다.')
        with self._lock:
            if self._update_job and self._update_job.is_alive():
                return self._update_status()
            if self._update is not None:
                return self._update_status()
            if self._updater is None:
                self._updater = updater.Checker(edition.VERSION, self._update_folder(),
                                                self._update_ready, self._log, channels=self._update_channels)
            checker = self._updater
            self._update_note, self._update_failed = '새 판이 있는지 확인하고 있습니다…', False
            self._update_job = threading.Thread(target=self._update_check_run, args=(checker,), daemon=True,
                                                name='desk-update-manual')
            self._update_job.start()
        return self._update_status()

    def _update_check_run(self, checker):
        try:
            record = checker.check_once()
            note, failed = (f'새 판 {record["version"]} 을 받아 두었습니다.' if record
                            else f'지금 쓰는 {edition.VERSION} 이 최신 판입니다.'), False
        except Exception as exc:
            self._log('업데이트를 확인하지 못했습니다:', exc)
            note, failed = '업데이트를 확인하지 못했습니다. 인터넷 연결을 확인하고 다시 눌러 주세요.', True
        with self._lock:
            self._update_note, self._update_failed = note, failed
        self._tray_notify(note)

    def _update_apply(self, payload):
        """받아 둔 새 판으로 지금 바꾸고 다시 켠다. 하던 일이 있으면 force 일 때만."""
        with self._lock:
            record, quit_app = self._update, self._quit_for_update
        if record is None:
            raise ValueError('받아 둔 새 판이 없습니다. 먼저 «업데이트 확인»을 눌러 주세요.')
        if quit_app is None:
            raise ValueError('지금은 바꿀 수 없습니다. 프로그램을 다시 켜면 새 판으로 바뀝니다.')
        busy = self._update_busy(manual=True)
        if busy and not payload.get('force'):
            raise ValueError(f'{busy}. 닫고 다시 누르거나, 그대로 바꾸려면 한 번 더 확인해 주세요.')
        # 이 요청의 답을 화면에 돌려준 뒤 끝낸다
        threading.Timer(0.8, self._apply_update_now, kwargs={'then': ['--dock']}).start()   # 새 판도 독만
        return f'새 판 {record["version"]} 으로 바꾸고 다시 켭니다. 잠시만 기다려 주세요.'

    def _tray_notify(self, message):
        try:
            tray = self._desk_tray or self._tray
            if tray is not None:
                tray.notify(message, edition.TITLE)
        except Exception:
            pass

    def _tray_update(self):
        """트레이 메뉴 «업데이트 확인» / «지금 업데이트» — 받아 둔 판이 있으면 바꾸고, 없으면 확인한다."""
        result = self.call('update_apply' if self._update else 'update_check')
        if not result['ok']:
            self._tray_notify(result['error'])
        elif isinstance(result['data'], str):
            self._tray_notify(result['data'])

    def _update_ready(self, record):
        """새 판을 받아 두었다 — 정기 확인에서면 바꿀지 묻는다 (같은 판은 한 번만).
        설정·트레이에서 손으로 확인한 것이면 묻지 않는다 — 거기서 «지금 바꾸기»를 누른다."""
        with self._lock:
            self._update = record
            manual = threading.current_thread() is self._update_job
            ask = not manual and record['version'] not in self._update_asked
            if ask:
                self._update_asked.add(record['version'])
        if ask:
            threading.Thread(target=self._update_prompt, args=(record,), daemon=True, name='desk-update-ask').start()

    def _update_prompt(self, record):
        if not self._ask_update(record['version'], self._update_busy(manual=True)):
            self._log(f'새 판 {record["version"]} 업데이트를 미뤘습니다. 다음에 켤 때 다시 묻습니다.')
            return
        # 켠 직후면 화면 쪽(main)이 끝내는 손을 아직 넣지 않았을 수 있다 — 잠깐 기다린다
        for _ in range(60):
            with self._lock:
                if self._quit_for_update is not None:
                    break
            if self._shutdown.wait(1):
                return
        self._apply_update_now(then=['--dock'])           # 손으로 고른 것 — 새 판도 독만 (데스크 본창은 숨긴 채)

    @staticmethod
    def _idle_seconds() -> float:
        class LastInput(ctypes.Structure):
            _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]
        info = LastInput(ctypes.sizeof(LastInput), 0)
        if not _user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        return ((ctypes.WinDLL('kernel32').GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000

    def _away(self, _=None) -> bool:
        """자리를 비웠는가 — 서버에 묻는 정기 작업들이 이것 하나로 쉰다 (AWAY_AFTER)."""
        try:
            return self._idle_seconds() >= AWAY_AFTER
        except Exception:
            return False                           # 모르면 종전처럼 (갱신을 멈추는 쪽으로 틀리지 않는다)

    def _update_busy(self, manual: bool = False) -> str:
        """지금 바꾸면 안 되는 까닭 (없으면 ''). manual 이면 데스크 창은 보지 않는다 — 거기서 누른 것이다."""
        with self._lock:
            if self._portals or self._neis_session is not None:
                return '로그인·나이스 도우미가 돌고 있습니다'
            if self._service_windows or self._page_windows or self._popups or self._capture_window:
                return '열어 둔 창이 있습니다'
            if self._capture_job and self._capture_job.is_alive():
                return '캡처 중입니다'
            if self._isekai3d_window:
                return '게임(이세계 사회인)을 하고 있습니다'
            desk = self._desk_window
        if manual:
            return ''
        form = self._dock_form(desk)
        try:
            if form is not None and form.Visible:
                return '데스크 창이 열려 있습니다'
        except Exception:
            return '데스크 창을 확인하지 못했습니다'
        return ''

    def _apply_update_now(self, then=('--autostart',)) -> bool:
        """then = 새 판을 띄울 인자. 손을 놓은 틈에 바꿀 때는 숨겨 켜고(--autostart), 손으로 누르면 창을 보인다."""
        from core import updater
        with self._lock:
            record, quit_app = self._update, self._quit_for_update
        if record is None or quit_app is None:
            return False
        exe = updater.target()
        try:
            if exe is None:
                raise updater.UpdateError('새 판을 놓을 자리가 없습니다.')
            updater.start_install(record, exe, list(then), updater.own_pids(), self._update_fallback(exe))
        except (OSError, updater.UpdateError) as exc:
            self._log('새 판을 설치하지 못했습니다:', exc)
            with self._lock:
                self._update = None           # 다음에 켤 때 다시 해 본다
            return True
        self._log(f'새 판 {record["version"]} 으로 바꾸고 다시 켭니다.')
        quit_app()                            # 새 판(설치 모드)이 이것이 끝나기를 기다렸다가 바꾼다
        return True

    def _agent_install(self, payload):
        from core import agent
        tool = payload.get('tool')
        if tool not in agent.TOOLS:
            raise ValueError('지원하지 않는 에이전트입니다.')
        message = agent.install(tool, Path(watcher.DATA_DIR))
        self._log(message)
        return message

    # ── 클립보드 기록 ──────────────────────────────────────────
    # 컴퓨터에서 복사한 글·그림·파일을 모아 두고, 독 위 패널에서 눌러 다시 복사한다 (2026-10-12 요청).
    def _start_clips(self):
        from core import clipboard_history
        with self._lock:
            if self._clips is None:
                self._clips = clipboard_history.History(CLIPS_DIR)
                self._clip_recorder = clipboard_history.Recorder(self._clips, self._log)
            paused = bool(self._read_preferences().get('clips_paused'))
        if not paused:
            self._clip_recorder.start()

    def _clip_store(self):
        if self._clips is None:
            self._start_clips()
        return self._clips

    def _clips_list(self, payload):
        """기록 목록. 화면이 가진 것과 같으면(version) 다시 보내지 않는다."""
        clips = self._clip_store()
        query = payload.get('query') or ''
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError('찾을 말이 올바르지 않습니다.')
        paused = not self._clip_recorder.running
        if payload.get('since') == clips.version and payload.get('query_was') == query \
                and payload.get('paused_was') == paused:
            return {'same': True}
        return {'version': clips.version, 'paused': paused, 'items': clips.listing(query)}

    def _clips_copy(self, payload):
        """기록 하나를 다시 클립보드에 — 그다음 Ctrl+V 로 어디든 붙여 넣는다."""
        clips = self._clip_store()
        item = clips.get(payload.get('id'))
        kind = item['kind']
        path = clips.image_path(item) if kind == 'image' else None

        def work(_form):
            from System.Windows.Forms import Clipboard, DataObject, TextDataFormat
            data = DataObject()
            if kind == 'text':
                data.SetText(item['text'], TextDataFormat.UnicodeText)
            elif kind == 'files':
                data.SetFileDropList(self._file_list(item['files']))
            else:
                from System.Drawing import Bitmap
                source = Bitmap(str(path))              # 파일을 잡지 않게 복사본을 넘긴다
                data.SetImage(Bitmap(source))
                source.Dispose()
            Clipboard.SetDataObject(data, True)
        self._on_panel_ui(work)
        return '복사했습니다. Ctrl+V 로 붙여 넣으세요.'

    def _on_panel_ui(self, work):
        """독 위 패널(없으면 독) 창의 UI 스레드에서 — 클립보드는 그 스레드(STA)에서만 쓸 수 있다."""
        with self._lock:
            window = self._popover_window or self._dock_window
        form = self._dock_form(window)
        if form is None:
            raise RuntimeError('독이 떠 있을 때 쓸 수 있습니다.')
        on_ui(form, lambda: work(form), self._log)

    def _clips_pin(self, payload):
        self._clip_store().pin(payload.get('id'), bool(payload.get('pinned')))
        return None

    def _clips_delete(self, payload):
        self._clip_store().delete(payload.get('id'))
        return None

    def _clips_clear(self, _):
        count = self._clip_store().clear()
        self._log(f'클립보드 기록 {count}개를 지웠습니다.')
        return f'{count}개를 지웠습니다. 고정한 것은 남겨 두었습니다.'

    def _clips_pause(self, payload):
        paused = bool(payload.get('paused'))
        self._clip_store()
        self._save_preferences(clips_paused=paused)
        if paused:
            self._clip_recorder.stop()
        else:
            self._clip_recorder.start()
        return '클립보드 기록을 멈췄습니다.' if paused else '클립보드를 다시 기록합니다.'

    # ── 학교 정보(대시보드) 미리 받아 두기 ─────────────────────────
    # 예전에는 누를 때마다 서버에 다섯 가지를 물어 '학교 정보를 불러오고 있습니다'가 떴다
    # (2026-10-11 사용자 보고). 이제는 뒤에서 2분마다 받아 두고, 1분 안의 것은 바로 돌려준다.
    def _dash_cached(self):
        """지금 계정의 받아 둔 학교 정보 (받은 시각, 내용). 계정이 바뀌었으면 버린다."""
        cache, user = self._dash_cache, supa_auth.whoami()
        if not cache or not user or cache[1] != user:
            return None
        return cache[0], cache[2]

    def _dash_fetch(self):
        started = time.monotonic()
        with self._dash_fetching:
            cached = self._dash_cached()
            if cached and cached[0] >= started:      # 기다리는 사이 다른 쪽이 막 받아 왔다
                return cached[1]
            from core.dashboard import snapshot
            user = supa_auth.whoami()
            data = snapshot()
            self._dash_cache = (time.monotonic(), user, data)
            return data

    def _dashboard(self, payload):
        """학교 정보. 1분 안에 받아 둔 것이 있으면 서버에 묻지 않는다 (force 면 새로)."""
        cached = self._dash_cached()
        if cached and not payload.get('force') and time.monotonic() - cached[0] < DASHBOARD_FRESH:
            return cached[1]
        return self._dash_fetch()

    def _dashboard_quick(self, _):
        """받아 둔 학교 정보를 **기다리지 않고** — 오래됐어도. 없으면 None.
        패널은 이것부터 보이고, 그다음 `dashboard` 로 새것을 받아 바꿔 그린다."""
        cached = self._dash_cached()
        if not cached:
            return None
        return {'data': cached[1], 'age': round(time.monotonic() - cached[0])}

    def _dashboard_month(self, payload):
        """일정 패널의 달력 한 달 ('YYYY-MM'). 5분 안에 받은 달은 서버에 묻지 않는다 (force 면 새로)."""
        value = str(payload.get('month') or '')
        try:
            year, month = (int(part) for part in value.split('-'))
        except ValueError:
            raise ValueError('달 형식이 올바르지 않습니다.') from None
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError('달 형식이 올바르지 않습니다.')
        from core.dashboard import month as month_calendar
        key = (supa_auth.whoami(), f'{year:04d}-{month:02d}')
        cached = self._month_cache.get(key)
        if cached and key[0] and not payload.get('force') and time.monotonic() - cached[0] < MONTH_FRESH:
            return cached[1]
        data = month_calendar(year, month)
        if len(self._month_cache) > 24:            # 넘겨 본 달이 쌓이지 않게
            self._month_cache.clear()
        self._month_cache[key] = (time.monotonic(), data)
        return data

    def _start_dash_prefetch(self):
        with self._lock:
            if self._dash_prefetcher and self._dash_prefetcher.is_alive():
                return
            self._dash_prefetcher = threading.Thread(target=self._dash_prefetch_loop, daemon=True,
                                                     name='desk-dashboard-prefetch')
            self._dash_prefetcher.start()

    def _dash_prefetch_loop(self):
        wait = 3                                   # 켜자마자 한 번 — 처음 누를 때도 바로 보이게
        while not self._shutdown.wait(wait):
            wait = DASHBOARD_PREFETCH
            if not supa_auth.whoami() or self._away():
                continue                           # 돌아오면 다음 차례(최대 2분)에 받는다 — 패널은 열 때 직접 받는다
            try:
                self._dash_fetch()
            except Exception:
                pass                               # 다음 차례에 다시. 누르면 그때 오류를 보인다
            try:
                self._msg_check()                  # 새 메시지 — 같은 2분 주기·자리 비움 규칙
            except Exception:
                pass
            try:
                self._req_check()                  # 에이전트 작업 요청 — Realtime 이 놓친 것
            except Exception:
                pass

    # ── 데스크 메시지 (학생 ↔ 선생님, 2026-10-19) ─────────────────────────
    # 내용은 스페이스기전 알림으로 오간다 (core/desk_message.py). 보낸 사람·받을 수 있는 사람은 서버가 정한다.
    def _msg_check(self):
        """새로 온 메시지를 트레이로 알리고 독 배지를 맞춘다. 2분마다 (자리를 비우면 쉰다).
        Realtime(_start_realtime)이 붙어 있으면 이미 알린 것이다 — 알린 것은 id 로 기억해 두 번 알리지 않는다."""
        account = (supa_auth.load_session() or {}).get('user_id')
        if not account:
            with self._lock:
                self._msg_unread, self._msg_seen = 0, None
            return
        rows = desk_message.unread_after(None)
        with self._lock:
            first = not (self._msg_seen and self._msg_seen[0] == account)
            seen = set() if first else self._msg_seen[1]
            fresh = [row for row in rows if row['id'] not in seen]
            self._msg_seen = (account, seen | {row['id'] for row in rows})
            self._msg_unread = len(rows)
        if first and fresh:
            self._msg_notify('새 메시지', f'안 읽은 메시지가 {len(fresh)}건 있습니다. 독의 «메시지»를 눌러 보세요.'
                             if len(fresh) > 1 else f"{fresh[0]['from_label']}: {fresh[0]['body'][:80]}")
        else:
            for row in fresh[:3]:
                self._msg_notify(f"메시지 · {row['from_label']}", row['body'][:120])
        if fresh:
            self._msg_changed()

    def _start_realtime(self):
        """새 메시지를 바로 받는다 (core/realtime.py). 로그인해 있고 자리에 있을 때만 붙는다."""
        from core import realtime
        with self._lock:
            if self._realtime is not None:
                return
            self._realtime = realtime.Listener(self._msg_arrived,
                                               lambda: bool(supa_auth.whoami()) and not self._away(), self._log)
        self._realtime.start()

    def _msg_arrived(self, record):
        """Realtime 으로 온 새 메시지 — 알림·배지·열린 패널을 바로. 작업 요청 알림은 따로(_request_arrived)."""
        if record.get('type') == 'agent_request':
            self._request_arrived(record)
            return
        item = desk_message.shape(record)
        account = (supa_auth.load_session() or {}).get('user_id')
        with self._lock:
            seen = self._msg_seen[1] if self._msg_seen and self._msg_seen[0] == account else set()
            if not item['id'] or item['id'] in seen:
                return
            self._msg_seen = (account, seen | {item['id']})
            if not item['read']:
                self._msg_unread += 1
        self._msg_notify(f"메시지 · {item['from_label']}", item['body'][:120])
        self._msg_changed()

    def _msg_changed(self):
        """메시지 패널이 열려 있으면 다시 읽게 한다."""
        with self._lock:
            window = self._popover_window if self._popover_ready else None
        if window:
            try:
                window.run_js('window.deskMessages && window.deskMessages.changed()')
            except Exception:
                pass

    def _msg_notify(self, title, message):
        try:
            tray = self._desk_tray or self._tray
            if tray is not None:
                tray.notify(message, title)
        except Exception:
            pass

    def _msg_state(self, _):
        """메시지 패널 — 상대마다 묶은 대화 (받은 것·보낸 것 모두 서버 — 어느 PC 에서나 같다)."""
        if not supa_auth.whoami():
            raise ValueError('설정에서 스페이스기전 계정을 먼저 연결해 주세요.')
        inbox = desk_message.received()
        try:
            outbox = desk_message.sent()
        except desk_message.MessageError:
            outbox = []                            # 보낸 것을 못 읽어도 받은 메시지는 보인다
        threads = desk_message.conversations(inbox, outbox)
        with self._lock:
            self._msg_unread = sum(1 for item in inbox if not item['read'])
        try:
            session = desk_message.sessions()
        except desk_message.MessageError:
            session = {'role': '', 'sessions': None}   # 상태를 못 읽으면 화면이 막지 않는다 — 막는 것은 서버다
        return {'threads': threads, 'unread': self._msg_unread, **session}

    def _msg_directory_get(self, payload):
        """보낼 수 있는 사람 — 10분 동안은 받아 둔 것을 쓴다."""
        account = (supa_auth.load_session() or {}).get('user_id')
        if not account:
            raise ValueError('설정에서 스페이스기전 계정을 먼저 연결해 주세요.')
        with self._lock:
            cached = self._msg_directory
        if cached and cached[0] == account and time.monotonic() - cached[1] < 600 and not payload.get('force'):
            return cached[2]
        data = desk_message.directory()
        with self._lock:
            self._msg_directory = (account, time.monotonic(), data)
        return data

    def _msg_send(self, payload):
        # 사진은 보내면서 이 PC 의 캡처 보관함에도 남긴다 (core/desk_message.py — 지우는 것도 거기서)
        result = desk_message.send(payload.get('to'), payload.get('body'), str(payload.get('label') or '')[:80],
                                   payload.get('reply_to') if isinstance(payload.get('reply_to'), str) else None,
                                   payload.get('images'), CAPTURE_DIR)
        name = result.get('recipient_name') or '받는 사람'
        self._log(f'메시지를 보냈습니다: {name}')
        if result.get('recipient_linked') is False:
            return f'{name}에게 보냈습니다. 아직 스페이스기전에 로그인한 적이 없어, 로그인하면 볼 수 있습니다.'
        return f'{name}에게 보냈습니다.'

    # 학생이 처음 보낼 때 허락받기 (2026-10-31) — 막는 것은 서버 send_desk_message_v2 다
    def _msg_request(self, payload):
        result = desk_message.request_permission(payload.get('to'), payload.get('body'))
        name = result.get('recipient_name') or '선생님'
        self._log(f'메시지 허락을 요청했습니다: {name}')
        if result.get('recipient_linked') is False:
            return f'{name}께 요청했습니다. 아직 스페이스기전에 로그인한 적이 없어, 로그인하면 볼 수 있습니다.'
        return f'{name}께 요청했습니다. 허락하면 메시지를 보낼 수 있습니다.'

    def _msg_decide(self, payload):
        approve = payload.get('approve')
        desk_message.decide(payload.get('to'), approve)
        return '허락했습니다.' if approve else '거절했습니다.'

    def _msg_end(self, payload):
        desk_message.end_session(payload.get('to'))
        return '대화를 종료했습니다.'

    def _msg_image(self, payload):
        """대화에 보일 사진 — 이 PC 캡처 보관함의 것, 없으면 서버(7일)에서 받아 보관함에 남긴다."""
        return desk_message.image(CAPTURE_DIR, payload.get('id'), str(payload.get('label') or '')[:80])

    def _msg_image_full(self, payload):
        """패널에서 크게 볼 사진 — 캡처 보관함의 원본."""
        image_id = payload.get('id')
        if not isinstance(image_id, str) or not desk_message.UUID.match(image_id):
            raise ValueError('사진 id 가 올바르지 않습니다.')
        return desk_message.full_image(CAPTURE_DIR, image_id)

    def _msg_image_open(self, payload):
        """사진을 기본 프로그램(사진 앱)으로 크게 연다."""
        path = desk_message.local_path(CAPTURE_DIR, payload.get('id'))
        if not path:
            raise ValueError('이 PC 에 없는 사진입니다. 캡처 보관함에서 지웠을 수 있습니다.')
        os.startfile(path)
        return None

    def _msg_read(self, payload):
        ids = payload.get('ids')
        if not isinstance(ids, list):
            raise ValueError('읽음 표시 형식이 올바르지 않습니다.')
        desk_message.mark_read(ids)
        with self._lock:
            self._msg_unread = max(0, self._msg_unread - len(ids))
        return None

    # ── 켰는데 화면이 안 뜰 때 (2026-10-19 — 독이 안 뜨고 트레이가 먹통이던 PC) ─────────────
    def _ui_seen(self, *_):
        """독(또는 데스크 창)이 다 그려졌다 — 화면 엔진이 살아 있다."""
        if not self._ui_ready.is_set():
            self._ui_ready.set()
            from core import diagnostics
            diagnostics.clear_old(watcher.DATA_DIR)

    def _watch_startup(self, seconds=45, debug_port=None):
        """seconds 안에 화면이 뜨지 않으면 어디서 멈췄는지 startup-hang.log 에 남기고 트레이로 알린다."""
        def watch():
            if self._ui_ready.wait(seconds) or self._shutdown.is_set():
                return
            from core import diagnostics
            # 🚨 멈춘 원인이 잠금이면 여기서도 같이 멈춰 기록을 못 남긴다 (2026-10-19) — 잠깐만 기다린다
            locked = self._lock.acquire(timeout=2)
            try:
                logs = list(self._logs)
            except RuntimeError:                   # 잠금 없이 읽다 마침 기록이 늘었다
                logs = []
            finally:
                if locked:
                    self._lock.release()
            try:
                path = diagnostics.write_hang_report(diagnostics.hang_log_path(watcher.DATA_DIR), edition.TITLE,
                                                     edition.VERSION, seconds, logs, debug_port)
            except Exception as exc:
                self._log('멈춤 기록을 남기지 못했습니다:', exc)
                return
            self._log(f'화면이 {seconds}초 동안 뜨지 않아 기록을 남겼습니다: {path}')
            self._tray_notify(f'화면을 띄우지 못하고 있습니다. 트레이 메뉴 «종료» 뒤 다시 켜 주세요. 기록: {path}')
        threading.Thread(target=watch, daemon=True, name='desk-startup-watch').start()

    @staticmethod
    def _in_background(action):
        """트레이 메뉴 동작 — 트레이 스레드를 붙잡지 않게 따로 돌린다. 화면 쪽이 멈춰도 트레이는 산다."""
        def run(*_):
            threading.Thread(target=action, daemon=True, name='desk-tray-action').start()
        return run

    @staticmethod
    def _exit_if_stuck(seconds=15):
        """종료를 눌렀는데 화면 쪽이 응답하지 않아 끝나지 않으면 seconds 뒤 프로세스를 끝낸다.
        제대로 끝나면 이 타이머(데몬)는 프로세스와 함께 사라진다."""
        timer = threading.Timer(seconds, os._exit, args=(0,))
        timer.daemon = True
        timer.start()

    def _state(self, _):
        with self._lock:
            return {'user': supa_auth.whoami(), 'credentials': secretstore.has_credentials(),
                    'away': self._away(),
                    'startup': startup.enabled(),
                    'watching': self._watcher.running, 'watch_error': self._watcher.last_error,
                    'summary': self._watcher.use_summary, 'body': self._watcher.show_body,
                    'auth_pending': self._auth_pending, 'portals': sorted(self._portals),
                    'portal_status': dict(self._portal_status),
                    'coolmsg': self._coolmsg(),
                    'logs': list(self._logs)}

    def _coolmsg(self):
        """어느 계정의 쪽지를 읽고 있는지. 한 PC 를 여러 계정이 쓰면 여기서 갈린다."""
        try:
            info = udb.status()
        except Exception as exc:
            return {'ok': False, 'why': str(exc), 'accounts': [], 'fixed': ''}
        info['fixed'] = udb.configured()
        # 인증서 이름과 견주는 일은 화면 쪽에서 한다 — state 는 2초마다 도는데
        # 그때마다 암호화된 인증서 정보를 풀어 보는 것은 값싸지도, 안전하지도 않다.
        return info

    def _coolmsg_account(self, payload):
        name = str(payload.get('account', '')).strip()
        if name:
            known = [row['name'] for row in udb.accounts()]
            if name not in known:
                raise ValueError(f"'{name}' 계정의 쪽지 DB 가 이 PC 에 없습니다. "
                                 f"확인된 계정: {', '.join(known) or '없음'}")
        if name == udb.configured():
            return '이미 같은 계정으로 설정되어 있습니다.'
        settings.set('coolmsg_account', name)
        # 계정마다 쪽지 번호가 따로 매겨진다 — 기준점을 옮기지 않으면 알림이 어긋난다.
        key = watcher.reset_baseline(name or None)
        label = name or '자동 (최근 사용)'
        self._log(f'쪽지 계정: {label} (기준 번호 {key})')
        return (f'{label} 계정의 쪽지를 표시합니다. 알림은 지금 이후 도착분부터 보냅니다.')

    def _sync_roster(self, _):
        rows = roster.sync()
        self._log(f'명부 {len(rows)}명을 새로 읽었습니다.')
        return rows

    def _alias(self, payload):
        source, target = str(payload.get('source', '')).strip(), str(payload.get('target', '')).strip()
        if not source or not target:
            raise ValueError('대화명과 실명을 모두 입력해 주세요.')
        with self._lock:
            roster.set_alias(source, target)
        self._log(f'별칭 저장: {source} → {target}')
        return '별칭을 저장했습니다.'

    def _credential_settings(self, _):
        with self._lock:
            try:
                values = secretstore.load()
            except secretstore.SecretError:
                values = {}
            return {'user': values.get('id', ''), 'cert_name': values.get('cert_name', ''),
                    'has_password': bool(values.get('cert_password')),
                    # 리로스쿨은 인증서가 아니라 아이디·비밀번호다. 비밀번호는 돌려주지 않고
                    # 저장돼 있는지만 알린다.
                    'riro_id': values.get('riro_id', ''),
                    'has_riro': bool(values.get('riro_id') and values.get('riro_password')),
                    'aiep_id': values.get('aiep_id', ''),
                    'has_aiep': bool(values.get('aiep_id') and values.get('aiep_password')),
                    'jbstudy_id': values.get('jbstudy_id', ''),
                    'has_jbstudy': bool(values.get('jbstudy_id') and values.get('jbstudy_password'))}

    def _save_credentials(self, payload):
        user = str(payload.get('user', '')).strip()
        password = str(payload.get('password', ''))
        with self._lock:
            try:
                values = secretstore.load()
            except secretstore.SecretError:
                values = {}
            password = password or values.get('cert_password', '')
            if not user or not password:
                raise ValueError('업무포털 아이디와 인증서 암호를 모두 입력해 주세요.')
            values.update(id=user, cert_password=password)
            values.setdefault('cert_match', None)
            if 'cert_name' in payload:
                name = str(payload['cert_name']).strip()
                values['cert_name'] = name
                # All three login paths already share cert_match. Treat the UI input literally.
                values['cert_match'] = re.escape(name) if name else None
            secretstore.save(values)
        self._log('인증서 정보를 이 PC에 암호화하여 저장했습니다.')
        return '인증서 정보를 저장했습니다.'

    def _save_password_login(self, target, payload):
        """아이디·비밀번호로 들어가는 서비스의 계정을 저장한다.

        인증서 항목은 건드리지 않는다. 비밀번호 칸을 비우고 저장하면 **기존 비밀번호를
        그대로 둔다** — 아이디만 고칠 때 비밀번호를 다시 치게 만들 이유가 없다. 인증서
        쪽과 같은 규칙이다.
        """
        id_key, pw_key, label = self.BY_PASSWORD[target]
        user = str(payload.get(id_key, '')).strip()
        password = str(payload.get(pw_key, ''))
        with self._lock:
            values = self._credentials()
            password = password or values.get(pw_key, '')
            if not user or not password:
                raise ValueError(f'{label} 아이디와 비밀번호를 모두 입력해 주세요.')
            values[id_key] = user
            values[pw_key] = password
            secretstore.save(values)
        self._log(f'{label} 정보를 이 PC에 암호화하여 저장했습니다.')
        return f'{label} 정보를 저장했습니다. 홈의 {label} 버튼이 자동 로그인으로 바뀝니다.'

    # 연결 해제할 때 지울 것. 인증서 한 벌은 세 시스템이 함께 쓴다.
    DISCONNECT = {'cert': (('id', 'cert_password', 'cert_match', 'cert_name'),
                           '인증서', ()),
                  'riro': (('riro_id', 'riro_password'), '리로스쿨', ('riro',)),
                  'aiep': (('aiep_id', 'aiep_password'), '전북 AIEP', ('aiep',)),
                  'jbstudy': (('jbstudy_id', 'jbstudy_password'), '연수포털', ('jbstudy',))}

    def _disconnect(self, payload):
        """저장된 로그인 정보를 지운다. 그 서비스 것만 지우고 나머지는 그대로 둔다.

        아이디·비밀번호로 들어가는 곳은 **브라우저에 남은 로그인까지** 지운다. 정보만 지우고
        브라우저가 로그인된 채면 연결을 끊었다고 할 수 없다. 인증서 쪽 프로필은 건드리지
        않는다 — 거기에는 로컬 네트워크 접근 허용이 들어 있어서, 지우면 그 물음을 다시 받는다.
        """
        target = str(payload.get('target', ''))
        if target not in self.DISCONNECT:
            raise ValueError('어떤 연결을 해제할지 알 수 없습니다.')
        keys, label, profiles = self.DISCONNECT[target]
        with self._lock:
            values = self._credentials()
            if not any(values.get(key) for key in keys):
                return f'{label} 정보는 이미 저장돼 있지 않습니다.'
            for key in keys:
                values.pop(key, None)
            if values:
                secretstore.save(values)
            else:
                secretstore.clear()          # 남은 것이 없으면 파일째 없앤다
        left = [name for name in profiles if not self._forget_browser(name)]
        self._log(f'{label} 연결을 해제했습니다.')
        note = (f" 브라우저에 남은 로그인은 지우지 못했습니다 ({', '.join(left)}) — "
                f"열린 창을 닫고 다시 눌러 주세요." if left else '')
        return f'{label} 연결을 해제했습니다.{note}'

    @staticmethod
    def _forget_browser(target: str) -> bool:
        """그 서비스의 브라우저 프로필을 지운다. 창이 열려 있으면 못 지운다."""
        import shutil
        from core import portal
        folder = Path(portal.DATA_DIR) / f'browser-{target}-msedge'
        if not folder.exists():
            return True
        shutil.rmtree(folder, ignore_errors=True)
        return not folder.exists()

    def _save_riro(self, payload):
        return self._save_password_login('riro', payload)

    def _save_aiep(self, payload):
        return self._save_password_login('aiep', payload)

    def _save_jbstudy(self, payload):
        return self._save_password_login('jbstudy', payload)

    # ── 카카오톡 연결 폐기 (2026-11-08) ─────────────────────────
    # 1.3.66~1.3.70 테스트 판의 카카오톡 스킬·«연결 및 설정»의 카카오톡 연결은 비공식 프로토콜(태블릿 흉내)이라 카카오 정책
    # 위반 소지가 있어 걷어냈다. 그 판들이 이 PC 에 남긴 것을 켤 때 한 번 치운다 — 저장한 카카오 계정(DPAPI kakao_id·
    # kakao_password), CLI 의 로그인(~/.config/agent-messenger/kakaotalk-*.json), 받아 둔 CLI(%LOCALAPPDATA%\KakaoTalkSkill),
    # 자동화 업무 폴더에 데스크가 깐 스킬(표시가 있는 것만 — core/automation.py RETIRED). 휴대폰의 기기 연결(SM-T870)은 사람이 해제한다.
    KAKAO_KEYS = ('kakao_id', 'kakao_password')

    def _retire_kakao_safely(self):
        try:
            self._retire_kakao()
        except Exception as exc:
            self._log('카카오톡 기능의 흔적을 지우지 못했습니다:', exc)

    def _retire_kakao(self):
        import shutil
        from core import automation
        done = []
        with self._lock:
            values = self._credentials()
            if any(key in values for key in self.KAKAO_KEYS):
                for key in self.KAKAO_KEYS:
                    values.pop(key, None)
                if values:
                    secretstore.save(values)
                else:
                    secretstore.clear()
                done.append('저장한 카카오 계정')
        config = Path(os.environ.get('AGENT_MESSENGER_CONFIG_DIR') or Path.home() / '.config' / 'agent-messenger')
        tokens = [*config.glob('kakaotalk-credentials.json'), *config.glob('kakaotalk-sync-state-*.json')]
        for path in tokens:
            path.unlink(missing_ok=True)
        if tokens:
            done.append('카카오톡 로그인')
        cli = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'KakaoTalkSkill'
        if cli.is_dir():
            shutil.rmtree(cli, ignore_errors=True)
            done.append('카카오톡 도구')
        folder = self._automation_folder()
        if folder.is_dir() and automation.retire(folder):
            done.append('카카오톡 스킬')
        if done:
            self._log('카카오톡 기능을 걷어내 이 PC 에서 지웠습니다:', ', '.join(done),
                      '— 휴대폰 카카오톡 «설정 > 기기 연결 관리»에 SM-T870 이 있으면 해제해 주세요.')

    def _startup(self, payload):
        if not isinstance(payload.get('enabled'), bool):
            raise ValueError('자동 실행 설정 형식이 올바르지 않습니다.')
        if startup.managed():
            raise ValueError('학교에서 자동 실행을 관리하고 있어 여기서 바꿀 수 없습니다.')
        startup.set_enabled(payload['enabled'])
        self._save_preferences(startup=payload['enabled'])     # 학생판은 고른 적 없으면 켜 둔다 — 끈 것은 기억한다
        message = ('Windows 로그인 시 데스크를 자동으로 실행합니다.' if payload['enabled']
                   else 'Windows 자동 실행을 해제했습니다.')
        self._log(message)
        return message

    def _read_preferences(self) -> dict:
        try:
            preferences = json.loads(self._preferences_path.read_text(encoding='utf-8'))
            return preferences if isinstance(preferences, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_preferences(self, **changes) -> dict:
        """설정 파일의 다른 항목은 그대로 두고 바꾼 것만 덮어쓴다."""
        with self._lock:
            preferences = {**self._read_preferences(), **changes}
            self._preferences_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._preferences_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(preferences), encoding='utf-8')
            os.replace(temporary, self._preferences_path)
            return preferences

    def _options(self, payload):
        with self._lock:
            preferences = self._save_preferences(summary=bool(payload.get('summary', True)),
                                                 body=bool(payload.get('body', True)))
            self._watcher.use_summary = preferences['summary']
            self._watcher.show_body = preferences['body']
        self._log('쪽지 알림 옵션을 저장했습니다.')
        return '다음 쪽지부터 적용됩니다.'

    def _auth(self, payload):
        with self._lock:
            if self._auth_pending:
                raise ValueError('브라우저에서 진행 중인 로그인을 완료해 주세요.')
            if payload.get('logout'):
                self._watcher.stop()
                self._watch_requested = False
                uid = (supa_auth.load_session() or {}).get('user_id')
                self._web_login.cancel()
                supa_auth.logout()
                self._month_cache = {}
                sticky.forget()
                for window in list(self._sticky_windows.values()):
                    window.destroy()          # 다른 계정의 메모를 화면에 남기지 않는다
                self._sticky_layout = {}
                self._save_sticky_layout()
                for site, window in (('space', self._space_window), ('seaton', self._seaton_window)):
                    if window:
                        self._web_login.logout(window, site, uid)
                self._log('SPACEKIJUN에서 로그아웃했습니다.')
                return '로그아웃했습니다.'
            self._auth_pending = True
        def done(_session):
            with self._lock:
                self._auth_pending = False
            if _session:
                for site, window in (('space', self._space_window), ('seaton', self._seaton_window)):
                    if window:
                        self._web_login.start(window, site, force=True)
            try:
                self._reconcile_watch()
            except Exception as exc:
                self._log('자동 감시 시작 실패:', exc)
        try:
            supa_auth.login_async(done, log=self._log)
        except Exception:
            done(None)
            raise
        return '브라우저에서 구글 로그인을 완료해 주세요.'

    @staticmethod
    def _credentials():
        try:
            return secretstore.load()
        except secretstore.SecretError:
            return {}

    # 아이디·비밀번호로 들어가는 서비스. 값이 저장된 키 이름과 사람이 읽을 이름.
    BY_PASSWORD = {'riro': ('riro_id', 'riro_password', '리로스쿨'),
                   'aiep': ('aiep_id', 'aiep_password', 'AIEP'),
                   'jbstudy': ('jbstudy_id', 'jbstudy_password', '연수포털')}
    TEACHER_ONLY = frozenset({'jbstudy'})          # 학생판에는 없는 자동 로그인 (교원 연수)
    # 자동 로그인에 필요한 것이 없을 때 **대신 열어 줄 주소.** 자동 로그인은 덤이지
    # 조건이 아니다 — 설정이 비어 있다고 버튼이 못 쓰게 되면 안 된다 (2026-09-14 요청).
    HOME_URL = {'neis': 'https://jbe.neis.go.kr',
                'eduptl': 'https://jbe.eduptl.kr',
                'klef': 'https://klef.jbe.go.kr',
                'riro': 'https://kijun.riroschool.kr',
                'aiep': AIEP_URL,
                'jbstudy': JBSTUDY_URL}
    LABEL = {'neis': 'NEIS', 'eduptl': '전북 업무포털', 'klef': 'K-에듀파인',
             'riro': '리로스쿨', 'aiep': '전북 AIEP', 'jbstudy': '전북교육연수포털'}

    def _can_sign_in(self, target: str) -> bool:
        """이 업무시스템에 들어갈 자격증명이 **실제로** 갖춰져 있는가.

        저장 파일이 있는지가 아니라 **그 서비스에 필요한 값이 들어 있는지**를 본다.
        리로스쿨만 저장해 둔 PC 에서도 파일은 있으므로, 파일 존재만 보면 나이스가 자동
        로그인을 시도하다 실패한다 (2026-09-14 요청). 없으면 그냥 사이트를 연다.

        나이스·업무포털·에듀파인은 인증서 한 벌(아이디와 인증서 암호)을 함께 쓴다.
        인증서 사용자 이름은 여러 장일 때 골라내는 용도라 없어도 로그인은 된다.
        """
        values = self._credentials()
        spot = self.BY_PASSWORD.get(target)
        if spot:
            return bool(values.get(spot[0]) and values.get(spot[1]))
        return bool(values.get('id') and values.get('cert_password'))

    @staticmethod
    def _sign_in(target, page, cred, progress):
        """서비스마다 로그인에 필요한 것이 다르다. **리로스쿨만 인증서를 쓰지 않는다.**"""
        from core import portal
        spot = DesktopAPI.BY_PASSWORD.get(target)
        if spot:
            sign = {'riro': portal.login_riro, 'aiep': portal.login_aiep, 'jbstudy': portal.login_jbstudy}[target]
            return sign(page, cred.get(spot[0], ''), cred.get(spot[1], ''), progress=progress)
        login = {'neis': portal.login_neis, 'eduptl': portal.login_eduptl,
                 'klef': portal.login_klef}[target]
        extra = {'user_id': cred.get('id', '')} if target == 'klef' else {}
        return login(page, cred['cert_password'], cred.get('cert_match'),
                     progress=progress, **extra)

    def _open_riro(self, payload):
        """계정이 저장돼 있으면 자동 로그인, 없으면 그냥 사이트를 연다 (`_portal` 안에서)."""
        if edition.STUDENT:
            return self._student_service('riro')
        return self._portal({'target': 'riro'})

    def _portal(self, payload):
        """업무시스템 하나를 **데스크 안 창**으로 연다. 브라우저가 따로 뜨지 않는다.

        예전에는 Edge 를 따로 띄웠다. 프로필 하나를 한 프로세스만 열 수 있어서, 선생님이
        평소 Edge 를 켜 두면 새 창이 그쪽으로 넘어가 자동화가 제어를 잃었다. 안에서 열면
        그 제약이 사라진다 (2026-09-15 요청). 도우미는 CDP 로 붙어 그대로 쓴다.
        """
        target = payload.get('target')
        if target not in self.LABEL:
            raise ValueError('지원하지 않는 업무시스템입니다.')
        label = self.LABEL[target]
        # 저장된 것이 없으면 막지 않고 **그냥 그 사이트를 연다.** 무엇을 저장하면 자동으로
        # 되는지만 활동 기록에 남긴다.
        if not self._can_sign_in(target):
            spot = self.BY_PASSWORD.get(target)
            need = (f'{label} 아이디와 비밀번호' if spot else '인증서 정보')
            self._log(f'{label}: 저장된 {need}가 없어 사이트만 엽니다. '
                      f'설정에 저장하면 자동 로그인으로 바뀝니다.')
            return self._open_plain(target)
        with self._lock:
            if target in self._portals:
                raise ValueError('이미 열린 로그인 창을 확인해 주세요.')
            self._portals.add(target)
            self._portal_status[target] = '실행 준비 중'
            self._browser_jobs.put(target)
            running = self._browser_worker is not None and self._browser_worker.is_alive()
            if not running:
                worker = threading.Thread(target=self._serve_browser, daemon=True,
                                          name='desk-browser')
                self._browser_worker = worker
                self._portal_workers.add(worker)
            else:
                worker = None
        if worker:
            worker.start()
        return '자동 로그인 창을 여는 중입니다.'

    def _say_for(self, target, started):
        """그 서비스의 진행 상황을 상태와 활동 기록 양쪽에 남기는 함수를 만든다."""
        label = self.LABEL[target]

        def progress(message):
            with self._lock:
                self._portal_status[target] = message
            self._log(f'{label} · {message} ({time.perf_counter() - started:.1f}초)')
        return progress

    def _done_with(self, target):
        with self._lock:
            self._portals.discard(target)
            self._portal_status.pop(target, None)

    def _open_service_window(self, target, url=None):
        """업무시스템을 **데스크 안 창**으로 연다. 브라우저가 따로 뜨지 않는다.

        이미 열어 둔 창이 있으면 그것을 앞으로 가져온다 — 같은 서비스로 창이 겹치면
        어느 것이 쓰던 창인지 알 수 없다.
        """
        import webview
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            window = self._service_windows.get(target)
        if window:
            try:
                window.show()
                window.restore()
                self._bring_front(window)
                return window
            except Exception:
                pass                  # 사용자가 이미 닫은 창이다. 새로 연다.
        window = webview.create_window(self.LABEL[target], url or self.HOME_URL[target],
                                       # 바깥 웹 화면에는 데스크 API 를 절대 주지 않는다.
                                       js_api=None, width=1500, height=950,
                                       min_size=(900, 640), text_select=True, zoomable=True)
        with self._lock:
            self._service_windows[target] = window

        def gone(name=target, made=window):
            """사용자가 창을 닫으면 잊는다 — 죽은 창을 다시 앞으로 부르지 않도록."""
            with self._lock:
                if self._service_windows.get(name) is made:
                    self._service_windows.pop(name, None)
            self._done_with(name)
        window.events.closed += gone
        self._front_when_loaded(window)
        return window

    @classmethod
    def _popup_title(cls, url):
        """아는 업무시스템이면 그 이름으로, 아니면 주소로 부른다."""
        host = url.split('//', 1)[-1].split('/', 1)[0]
        for target, home in cls.HOME_URL.items():
            if host and host in home:
                return cls.LABEL[target]
        return host or '새 창'

    def _open_popup(self, url):
        """페이지가 **스스로 연 창**을 데스크 안에서 띄운다.

        업무포털의 `나이스`·`K-에듀파인` 링크가 이 길로 온다. 전부 `window.open(주소)` 다.
        예전에는 pywebview 기본값대로 바깥 브라우저로 나갔는데, 거기는 프로필이 달라
        **로그인이 끊겼다** (2026-09-15 사용자 보고). 데스크 안에서 열면 쿠키가 같아
        로그인된 채로 이어진다.
        """
        import webview
        title = self._popup_title(url)
        with self._lock:
            if self._shutdown.is_set():
                return None
            if len(self._popups) >= POPUP_LIMIT:
                self._log(f'새 창이 너무 많아 {title} 창을 열지 않았습니다.')
                return None
        # 바깥 웹 화면에는 데스크 API 를 절대 주지 않는다.
        window = webview.create_window(title, url, js_api=None, width=1400, height=900,
                                       min_size=(900, 640), text_select=True, zoomable=True)
        with self._lock:
            self._popups.append(window)

        def gone(made=window):
            with self._lock:
                if made in self._popups:
                    self._popups.remove(made)
        window.events.closed += gone
        self._log(f'{title} 창을 데스크 안에서 열었습니다.')
        return window

    def _open_plain(self, target):
        """자동 로그인 없이 그 사이트만 연다. 자격증명이 없을 때의 길이다.

        **어디서 여는지는 그 서비스가 평소 어디서 열리는지를 따른다.** 나이스·업무포털·
        에듀파인은 Edge 를 쓰므로 평소 쓰시는 브라우저로, 리로스쿨·AIEP 는 데스크 안 창으로
        연다. 아무것도 입력해 주지 않는다.
        """
        label = self.LABEL[target]
        if target in EDGE_TARGETS:
            return self._open_shortcut(self.HOME_URL[target], label)
        try:
            self._open_service_window(target)
        except Exception as exc:
            self._log(f'{label}을 데스크 안에서 열지 못해 브라우저로 엽니다:', exc)
            return self._open_shortcut(self.HOME_URL[target], label)
        self._log(f'{label}을 열었습니다.')
        return f'{label}을 열었습니다.'

    def _attach(self, pw, target):
        """데스크 안 창에 붙는다. 리로스쿨·AIEP 가 이 길로 간다.

        창이 하나도 없으면 WebView2 가 디버깅 통로를 열지 않는다. 그래서 먼저 창을 띄운다.
        """
        self._open_service_window(target)
        browser = self._connect(pw)
        self._free_downloads(browser)
        return browser

    def _launch_edge(self, pw):
        """설치된 Edge 를 고정 프로필로 띄운다. 나이스·업무포털·에듀파인이 이 길로 간다.

        이 셋은 서로 링크로 오간다 (업무포털 → 나이스·에듀파인). 진짜 브라우저라야 그
        링크도, 인쇄·내려받기 같은 창도 평소처럼 동작한다 (2026-09-15 요청).

        🚨 Playwright 가 띄우지 않고 **Edge 를 평소처럼 띄운 뒤 붙는다.** Playwright 가 띄우거나
        기본값으로 붙으면 Edge 의 "파일 열기"·"폴더에 표시" 가 먹통이 되고, 내려받은 파일도
        임시 폴더에 GUID 이름으로 떨어졌다 (2026-09-15·2026-10-12 사용자 보고). 자세한 것은
        `portal.open_shared_edge`.
        """
        from core import portal
        choice = self._browser_choice_value()
        if choice != portal.DEFAULT_BROWSER and not portal.find_browser(choice):
            # 테스트 기능 — 고른 브라우저가 없으면 막지 말고 Edge 로 연다
            self._log(f'{portal.BROWSERS[choice]["label"]} 를 찾지 못해 Edge 로 엽니다.')
            choice = portal.DEFAULT_BROWSER
        browser = portal.open_shared_edge(pw, browser=choice)
        return browser.contexts[0]

    def _browser_choice_value(self) -> str:
        """인증서 사이트를 띄울 브라우저 (`portal.BROWSERS` 의 키). 고른 적 없으면 Edge."""
        from core import portal
        choice = self._read_preferences().get('cert_browser')
        return choice if choice in portal.BROWSERS else portal.DEFAULT_BROWSER

    def _browser_choice(self, payload):
        """나이스·업무포털·에듀파인을 띄울 브라우저를 고른다. Chrome 은 테스트 기능 (2026-10-23 요청).

        이미 띄워 둔 브라우저에는 손대지 않는다 — 그 창을 닫고 다음에 새로 띄울 때부터 바뀐다.
        """
        from core import portal
        choice = payload.get('browser')
        if choice not in portal.BROWSERS:
            raise ValueError('지원하지 않는 브라우저입니다.')
        label = portal.BROWSERS[choice]['label']
        if not portal.find_browser(choice):
            raise ValueError(f'이 PC 에 {label} 가 설치돼 있지 않습니다.')
        self._save_preferences(cert_browser=choice)
        self._log(f'인증서 사이트 브라우저를 {label} 로 바꿨습니다.')
        return (f'나이스·업무포털·에듀파인을 {label} 로 엽니다. 이미 열린 창이 있으면 '
                '모두 닫은 뒤 다시 눌러 주세요.')

    @staticmethod
    def _new_window(context):
        """같은 프로필에서 창을 하나 준다.

        **브라우저가 처음 띄워 둔 빈 창이 있으면 그것을 쓴다.** 안 그러면 빈 창이 하나
        남아, 누르지도 않은 창이 떠 있게 된다 (2026-09-15 사용자 보고).

        빈 창이 없으면 새로 만든다. Edge 는 프로필 하나를 한 프로세스만 열 수 있어서,
        창을 더 만드는 길은 크기를 준 `window.open` 뿐이다 — 크기를 주지 않으면 탭으로
        열린다 (2026-09-15 실측).
        """
        for page in context.pages:
            try:
                if page.url in ('', 'about:blank'):
                    return page
            except Exception:
                continue
        opener = context.pages[0] if context.pages else None
        if opener is None:
            return context.new_page()
        with context.expect_page() as caught:
            opener.evaluate("() => window.open('about:blank', '', 'width=1500,height=950')")
        return caught.value

    def _open_edge_window(self, context, target, cred):
        """Edge 에 창을 하나 열어 로그인까지 한다. 막혀도 창은 남긴다."""
        started = time.perf_counter()
        progress = self._say_for(target, started)
        label = self.LABEL[target]
        progress('창 여는 중')
        page = self._new_window(context)
        page.goto(self.HOME_URL[target], wait_until='domcontentloaded')
        self._log(f'{label} 로그인을 시작합니다.')
        try:
            result = self._sign_in(target, page, cred, progress)
            progress('로그인 완료 · 창 열림' if result.get('ok') else '로그인 상태 확인 필요')
            self._log(f"{label} 로그인: {'성공' if result.get('ok') else '실패'}")
        except Exception as exc:
            self._log(f'{label} 자동 로그인 중단:', exc)
            progress('자동 로그인 중단 · 열린 창과 활동 기록 확인')
        return page

    def _free_downloads(self, browser):
        """내려받기를 **브라우저 본래 동작**으로 되돌린다.

        🚨 Playwright 는 붙는 순간 `Browser.setDownloadBehavior` 를 `allowAndName` 으로
        바꾼다. 그러면 데스크 안 **모든 창**의 내려받기가 Playwright 임시 폴더에 GUID
        이름으로 떨어지고, WebView2 의 내려받기 이벤트는 아예 오지 않는다. 선생님 눈에는
        "파일 이름이 `d6b39ae4-…` 이고 다운로드 폴더에 없다" 로 보인다 (2026-09-15 보고).

        2026-09-15 실측. 같은 파일을 세 번 받아 보았다.

            붙기 전            C:\\Users\\...\\Downloads\\출결자료.txt
            Playwright 가 붙은 뒤   (내려받기 이벤트 없음 — 몰래 가로챈다)
            이 함수를 부른 뒤       C:\\Users\\...\\Downloads\\출결자료.txt
        """
        try:
            session = browser.new_browser_cdp_session()
            session.send('Browser.setDownloadBehavior', {'behavior': 'default'})
        except Exception as exc:
            self._log('내려받기 설정을 되돌리지 못했습니다:', exc)

    @staticmethod
    def _connect(pw, tries: int = 20):
        """데스크 안 창들에 붙는다. 창이 하나라도 떠야 포트가 열리므로 조금 기다린다."""
        last = None
        for _ in range(tries):
            try:
                return pw.chromium.connect_over_cdp(f'http://127.0.0.1:{DEBUG_PORT}')
            except Exception as exc:
                last = exc
                time.sleep(0.5)
        raise RuntimeError(f'데스크 안 창에 연결하지 못했습니다: {last}')

    @staticmethod
    def _pump(browser, seconds: float = 0.3):
        """드라이버에 **한 번 들어갔다 나온다.** 그래야 브라우저가 보낸 알림이 전달된다.

        동기 API 는 우리가 부를 때만 알림을 처리한다. `browser.contexts` 는 그 자리에서
        읽는 값이라 드나들지 않아, 그냥 되풀이해 읽으면 **새 창이 생긴 것을 영영 모른다**
        (2026-09-15: 이걸 빠뜨려 30초를 세다 창을 못 찾았다).

        창(context)에 묻는 것이라 사용자가 보는 화면은 읽지도 고치지도 않는다.
        쿠키도 주소를 좁혀 물어 받아 오는 양을 줄인다.
        """
        try:
            browser.contexts[0].cookies(PUMP_URL)
        except Exception:
            pass
        if seconds:
            time.sleep(seconds)

    @staticmethod
    def _find_page(browser, host: str, seconds: float = 30.0):
        """그 주소를 띄운 창을 찾는다. 데스크 본체 화면과 섞이지 않게 주소로 가른다."""
        end = time.time() + seconds
        while True:
            for ctx in browser.contexts:
                for page in ctx.pages:
                    try:
                        if host in page.url:
                            return page
                    except Exception:
                        pass
            if time.time() >= end:
                return None
            DesktopAPI._pump(browser)         # 새 창 소식을 받아 온다

    def _open_tab(self, ctx, target, cred):
        """창을 열고 로그인한다. 연 페이지를 돌려준다.

        로그인이 막혀도 창은 남긴다 — 사용자가 그 자리에서 직접 로그인할 수 있어야 한다.
        """
        started = time.perf_counter()
        progress = self._say_for(target, started)
        label = self.LABEL[target]
        progress('창 여는 중')
        self._open_service_window(target)
        # 창이 늘 때마다 한 번 더 못을 박는다. 내려받기는 조용히 어긋나면 알아채기 어렵다.
        self._free_downloads(ctx)
        host = self.HOME_URL[target].split('//', 1)[-1].split('/', 1)[0]
        page = self._find_page(ctx, host)
        if page is None:
            progress('창을 찾지 못했습니다')
            self._log(f'{label}: 데스크 안 창을 찾지 못했습니다.')
            return None
        self._log(f'{label} 로그인을 시작합니다.')
        try:
            result = self._sign_in(target, page, cred, progress)
            progress('로그인 완료 · 창 열림' if result.get('ok') else '로그인 상태 확인 필요')
            self._log(f"{label} 로그인: {'성공' if result.get('ok') else '실패'}")
        except Exception as exc:
            self._log(f'{label} 자동 로그인 중단:', exc)
            progress('자동 로그인 중단 · 열린 창과 활동 기록 확인')
        return page

    def _serve_browser(self):
        """요청이 오는 대로 창을 연다. **두 갈래를 함께 쥔다.**

        나이스·업무포털·에듀파인은 설치된 Edge 에서 열고(`edge`), 리로스쿨·AIEP 는 데스크 안
        창에서 연다(`desk`). Playwright 는 자기를 만든 스레드에서만 만질 수 있어서, 두 갈래
        모두 이 스레드에서 돈다. 도우미 일감도 마찬가지라 `pump_once` 로 조금씩 나눈다.

        브라우저는 **필요할 때 처음 한 번만** 띄운다. 리로스쿨만 쓰는 선생님 PC 에서 Edge 가
        괜히 뜨지 않도록.
        """
        from playwright.sync_api import sync_playwright
        pages, session, cred = {}, None, {}
        edge = desk = None
        closed = set()              # 브라우저가 알려 준 "닫힌 창" 이름
        beat = 0.0                  # 창이 살아 있는지 마지막으로 본 때
        klef = []                   # «바로보기»를 심은 에듀파인 탭 (2026-11-12)
        klef_beat = 0.0
        try:
            with sync_playwright() as pw:
                try:
                    while not self._shutdown.is_set():
                        try:
                            target = self._browser_jobs.get_nowait()
                        except queue.Empty:
                            target = None
                        if target:
                            # 🚨 **일감마다 새로 읽는다.** 이 일꾼은 데스크가 꺼질 때까지
                            #    사는데, 그 사이에 설정에서 계정을 더 저장할 수 있다.
                            #    한 번만 읽어 두면 방금 저장한 계정으로 열지 못한다.
                            page = None
                            try:
                                cred = secretstore.load()
                                if target in EDGE_TARGETS:
                                    if edge is None:
                                        edge = self._launch_edge(pw)
                                    page = self._open_edge_window(edge, target, cred)
                                else:
                                    if desk is None:
                                        desk = self._attach(pw, target)
                                    page = self._open_tab(desk, target, cred)
                            except Exception as exc:
                                self._log(f'{self.LABEL[target]}을 열지 못했습니다:', exc)
                            if page is None:
                                # 못 열었다. 단추를 풀어 다시 눌러 볼 수 있게 한다.
                                self._done_with(target)
                                target = None
                        if target:
                            if target == 'neis':
                                # 나이스만 계속 쥔다 — 도우미 패널이 이 창에 붙어 있다.
                                pages['neis'] = page
                                page.on('close', lambda _p: closed.add('neis'))
                                session = self._attach_assist(page, cred)
                                self._neis_session = session
                            else:
                                if target == 'klef':
                                    self._attach_klef(page, klef)
                                # 🚨 로그인이 끝나면 **손을 뗀다.** 더 따라다니지 않고
                                #    사용자가 알아서 쓰게 둔다 (2026-09-15 요청). 단추도
                                #    바로 풀어 준다.
                                self._done_with(target)
                        for name in list(closed):
                            closed.discard(name)
                            pages.pop(name, None)
                            self._done_with(name)
                            if name == 'neis' and session:
                                session.close()
                                session = self._neis_session = None
                        # 쉬는 동안에는 **화면을 전혀 건드리지 않는다.** 순수 파이썬 대기다.
                        neis = pages.get('neis')
                        if session and neis:
                            session.pump_once(neis, self._log, wait=IDLE_WAIT)
                        else:
                            self._shutdown.wait(IDLE_WAIT)
                        # 가끔 한 번만 드나든다. 이때 창이 닫혔다는 알림도 받아 온다.
                        #
                        # 🚨 **데스크가 살아 있는 한 이 일꾼도 산다.** 브라우저가 닫혔다고
                        #    끝내면, 다음에 새 스레드에서 Playwright 를 다시 켜야 하는데
                        #    그것이 실패한다 ("signal only works in main thread",
                        #    2026-09-15 실측). 그래서 닫힌 쪽만 놓고 자리를 지킨다.
                        now = time.monotonic()
                        # 에듀파인 «바로보기» — 페이지가 데스크를 부르면 다음 드나들 때 받는다.
                        # 2초를 기다리게 하지 않으려고 탭이 있을 때만 조금 더 자주 드나든다.
                        if klef and edge is not None and now - klef_beat >= KLEF_PUMP:
                            klef_beat = now
                            self._still_there(edge)
                        if now - beat >= BEAT_EVERY:
                            beat = now
                            if edge is not None and not self._still_there(edge):
                                edge = self._edge_is_gone(pages, session)
                                session = self._neis_session
                                klef.clear()
                            elif edge is not None:
                                # 업무포털 링크로 연 에듀파인 탭에도 붙인다 (주소만 본다 — 화면은 건드리지 않는다)
                                try:
                                    klef[:] = [p for p in klef if not p.is_closed()]
                                    for other in list(edge.pages):
                                        if other not in klef and self._is_klef(other):
                                            self._attach_klef(other, klef)
                                except Exception as exc:   # 바로보기는 덤이다 — 창 지키기를 멈추지 않는다
                                    self._log('에듀파인 탭을 살피지 못했습니다:', exc)
                            if desk is not None:
                                try:
                                    if not desk.is_connected():
                                        break          # 데스크가 닫혔다
                                    self._pump(desk, 0)
                                except Exception:
                                    break              # 데스크가 닫혔다
                finally:
                    # 창은 사용자 것이라 닫지 않는다. 연결만 끊는다.
                    # Edge 는 창(context)이 아니라 **붙은 브라우저**를 놓는다 — 붙어서 얻은
                    # 창을 close() 하면 사용자의 Edge 창이 닫힌다.
                    for holder in (desk, edge.browser if edge is not None else None):
                        try:
                            if holder is not None:
                                holder.close()
                        except Exception:
                            pass
        except Exception as exc:
            self._log('자동 로그인 창을 유지하지 못했습니다:', exc)
        finally:
            self._neis_session = None
            if session:
                session.close()
            for name in list(pages):
                self._done_with(name)
            with self._lock:
                while True:
                    try:
                        self._done_with(self._browser_jobs.get_nowait())
                    except queue.Empty:
                        break
                self._browser_worker = None
                self._portal_workers.discard(threading.current_thread())

    def _still_there(self, context) -> bool:
        """Edge 창이 아직 살아 있는가. 한 번 드나들며 알림도 받아 온다.

        페이지가 아니라 창(context)에 묻는 것이라 사용자가 보는 화면을 읽지도 고치지도
        않는다. 동기 API 는 이렇게 들어갔다 나와야 `page.on('close')` 같은 알림이 온다.
        """
        try:
            context.cookies(PUMP_URL)
            return True
        except Exception:
            return False

    def _edge_is_gone(self, pages, session):
        """Edge 를 닫으면 그 안의 셋을 놓아 준다. 데스크는 그대로 둔다."""
        self._log('Edge 자동 로그인 창이 닫혔습니다.')
        for name in [name for name in pages if name in EDGE_TARGETS]:
            pages.pop(name, None)
        for name in EDGE_TARGETS:
            self._done_with(name)
        if session:
            session.close()
        self._neis_session = None
        return None

    @staticmethod
    def _is_klef(page) -> bool:
        from core import klef_overlay
        try:
            return klef_overlay.is_klef(page.url)
        except Exception:
            return False

    def _attach_klef(self, page, holder: list):
        """에듀파인 탭에 «바로보기»를 심는다 (2026-11-12 요청). 못 심어도 에듀파인은 그대로 쓴다.

        목록의 문서가 SPACEKIJUN DB(`official_doc`)에 있으면 제목 옆에 단추가 붙고, 누르면 뷰어를
        기다리지 않고 요약·판정·본문을 오버레이로 본다. 보기 전용. 업무포털 링크·새 창으로 뜬 에듀파인 탭은 창 확인(BEAT_EVERY) 때 찾아 붙인다.
        """
        from core import klef_overlay
        if page in holder:
            return
        if edition.STUDENT:
            return
        with self._lock:
            lookup = getattr(self, '_klef_lookup', None)
            if lookup is None:
                lookup = self._klef_lookup = klef_overlay.DocLookup(log=self._log)
            jobs = getattr(self, '_klef_jobs', None)
            if jobs is None:
                jobs = self._klef_jobs = klef_overlay.Jobs(log=self._log)
        try:
            klef_overlay.install(page, lookup, opener=self._klef_open, jobs=jobs)
        except Exception as exc:
            self._log('에듀파인 바로보기를 심지 못했습니다:', exc)
            return
        holder.append(page)
        self._log('에듀파인 바로보기를 붙였습니다 — 분석된 공문 제목 옆 «바로보기»를 누르면 바로 볼 수 있습니다.')

    def _attach_assist(self, page, cred):
        """나이스 창에 도우미 패널을 얹는다. 못 얹어도 창은 그대로 쓸 수 있어야 한다."""
        from core import neis_overlay
        from core.neis_session import Session
        session = Session(cred.get('id') or 'default')
        try:
            neis_overlay.install(page, session.enqueue, session.result, session.state)
            self._log('NEIS 도우미 패널을 심었습니다. 창 오른쪽 아래에서 말을 걸 수 있습니다.')
        except Exception as exc:
            self._log('NEIS 도우미 패널을 심지 못했습니다:', exc)
            return None
        return session

    def _open_shortcut(self, url, title):
        """마지막 수단이다. 데스크 안 창을 만들지 못했을 때만 바깥 브라우저로 넘긴다."""
        import webbrowser
        if not webbrowser.open(url, new=2):
            raise RuntimeError(f'{title}을 열지 못했습니다. 기본 브라우저 설정을 확인해 주세요.')
        self._log(f'{title}을 열었습니다.')
        return f'{title}을 열었습니다.'

    def _open_classroom(self, _):
        """Google 클래스룸 — 기본 브라우저로 연다. 구글은 프로그램 안 창(임베디드 웹뷰)에서의 로그인을
        막아서, 학생이 이미 구글에 로그인해 둔 브라우저가 가장 확실하다."""
        import webbrowser
        if not webbrowser.open(CLASSROOM_URL, new=2):
            raise RuntimeError('브라우저를 열지 못했습니다. 기본 브라우저 설정을 확인해 주세요.')
        return 'Google 클래스룸을 브라우저에서 열었습니다.'

    def _settings_panel(self, _):
        """독 위 설정 패널 — 계정·자동 로그인·독 아이콘·단축키·자동 실행·업데이트를 한 번에.

        학생판에서 시작했고, 교사판 '연결 및 설정'도 같은 패널로 연다 (2026-10-19 요청). 교사판은
        인증서·쪽지 알림·쿨메신저를 더 보인다. 비밀번호·인증서 암호는 돌려주지 않고 저장 여부만 알린다.
        """
        with self._lock:
            pending = self._auth_pending
        accounts = {}
        for target in ('riro', 'aiep') + (() if edition.STUDENT else ('jbstudy',)):
            user, password = self._student_account(target)
            accounts[target] = {'label': self.LABEL[target], 'id': user, 'saved': bool(user and password)}
        data = {'edition': edition.EDITION, 'user': supa_auth.whoami(), 'auth_pending': pending,
                'startup': startup.enabled(), 'startup_managed': startup.managed(), 'accounts': accounts,
                'hidden': list(self._dock_hidden), 'hotkey': self._dock_hotkey({}),
                'update': self._update_status()}
        if self._ranch_allowed():
            data['ranch'] = self.ranch_enabled          # 별사이 목장 보이기 (2026-11-06)
        if edition.STUDENT:
            return data
        values = self._credentials()
        with self._lock:
            watch = {'watching': self._watcher.running, 'error': self._watcher.last_error,
                     'summary': self._watcher.use_summary, 'body': self._watcher.show_body}
        from core import portal
        data.update(cert={'id': values.get('id', ''), 'name': values.get('cert_name', ''),
                          'saved': bool(values.get('id') and values.get('cert_password'))},
                    watch=watch, coolmsg=self._coolmsg(),
                    browser={'choice': self._browser_choice_value(),
                             'choices': [{'key': key, 'label': info['label'],
                                          'installed': bool(portal.find_browser(key))}
                                         for key, info in portal.BROWSERS.items()]})
        return data

    def _open_aiep(self, payload):
        """계정이 저장돼 있으면 자동 로그인, 없으면 그냥 사이트를 연다 (`_portal` 안에서)."""
        if edition.STUDENT:
            return self._student_service('aiep')
        return self._portal({'target': 'aiep'})

    def _open_jbstudy(self, payload):
        """전북교육연수포털 (2026-10-29 요청, 교사만) — 계정이 저장돼 있으면 자동 로그인, 없으면 그냥 연다.
        로그인까지만 한다. 연수 수강(출석·진도)은 자동화하지 않는다 (사이트 약관 — core/portal.py JBSTUDY_*)."""
        return self._portal({'target': 'jbstudy'})

    # ── 학생판 자동 로그인 (리로스쿨·AIEP) ───────────────────────
    # 학생판에는 Playwright 가 없다. 프로그램 안 창에 스크립트를 넣어 폼을 채운다 (core/web_signin.py).
    def _student_account(self, target):
        id_key, pw_key, _ = self.BY_PASSWORD[target]
        values = self._credentials()
        return values.get(id_key, ''), values.get(pw_key, '')

    def _student_service(self, target):
        """리로스쿨·AIEP 를 프로그램 안 창으로 연다. 계정을 저장해 두었으면 로그인까지 한다."""
        from core import web_signin
        label = self.LABEL[target]
        with self._lock:
            window = self._service_windows.get(target)
            busy = target in self._portals
        if window:
            # 이미 연 창은 앞으로만 가져온다 — 로그인을 다시 하지 않는다 (잠금 걱정)
            self._open_service_window(target)
            return f'{label} 창을 앞으로 가져왔습니다.' + (' 로그인하는 중입니다.' if busy else '')
        user, password = self._student_account(target)
        if not (user and password):
            self._open_service_window(target)
            return f'{label}을 열었습니다. 설정에 계정을 저장하면 다음부터 자동으로 로그인합니다.'
        window = self._open_service_window(target, web_signin.START_URL[target])
        closed = threading.Event()
        window.events.closed += closed.set
        with self._lock:
            self._portals.add(target)
            self._portal_status[target] = '로그인 준비 중'
        started = time.perf_counter()
        progress = self._say_for(target, started)

        def work():
            try:
                result = web_signin.drive(window, target, user, password, closed, progress=progress)
            except Exception as exc:
                result = 'stuck'
                self._log(f'{label} 자동 로그인 중단:', exc)
            self._log(f'{label} 자동 로그인: ' + {
                'signed-in': '완료',
                'wrong': '아이디·비밀번호가 맞지 않는 것 같습니다. 다시 넣지 않고 멈췄습니다 — 창에서 직접 확인해 주세요.',
                'closed': '창을 닫아 멈췄습니다.',
            }.get(result, '끝까지 마치지 못했습니다 — 열린 창에서 이어서 로그인해 주세요.'))
            if result == 'wrong':
                self._notify_student(f'{label} 로그인 실패',
                                     '저장한 아이디·비밀번호를 확인해 주세요. (설정 → 자동 로그인)')
            self._done_with(target)
        threading.Thread(target=work, daemon=True, name=f'desk-signin-{target}').start()
        return f'{label}에 로그인하는 중입니다.'

    def _notify_student(self, title, message):
        try:
            if self._tray is not None:
                self._tray.notify(message, title)
        except Exception:
            pass

    def _student_account_save(self, payload):
        target = payload.get('target')
        if target not in self.BY_PASSWORD or (edition.STUDENT and target in self.TEACHER_ONLY):
            raise ValueError('자동 로그인을 지원하지 않는 서비스입니다.')
        id_key, pw_key, label = self.BY_PASSWORD[target]
        self._save_password_login(target, {id_key: payload.get('id', ''), pw_key: payload.get('password', '')})
        return f'{self.LABEL[target]} 계정을 이 기기에 암호화해 저장했습니다. 독에서 누르면 자동으로 로그인합니다.'

    def _student_account_forget(self, payload):
        target = payload.get('target')
        if target not in self.BY_PASSWORD:
            raise ValueError('자동 로그인을 지원하지 않는 서비스입니다.')
        id_key, pw_key, _ = self.BY_PASSWORD[target]
        with self._lock:
            values = self._credentials()
            if not (values.get(id_key) or values.get(pw_key)):
                return f'{self.LABEL[target]} 계정은 저장돼 있지 않습니다.'
            values.pop(id_key, None)
            values.pop(pw_key, None)
            if values:
                secretstore.save(values)
            else:
                secretstore.clear()
        self._log(f'{self.LABEL[target]} 계정을 지웠습니다.')
        return f'{self.LABEL[target]} 계정을 지웠습니다. 이제 자동으로 로그인하지 않습니다.'

    def _open_space(self, payload):
        route = payload.get('route')
        if route is not None and route not in SPACE_ROUTES:
            raise ValueError('지원하지 않는 스페이스기전 화면입니다.')
        return self._show_space(route)

    def _klef_open(self, route):
        """에듀파인 «바로보기»가 연결된 SPACEKIJUN 페이지(업무노트·구매 신청)를 데스크의 스페이스기전 창에 연다.

        페이지가 부르는 함수라 Playwright 스레드 위에서 돈다 — 창을 만드느라 기다리지 않게 따로 띄운다.
        주소는 klef_overlay.SPACE_PAGE 모양(업무노트 한 장·구매 신청 페이지)만 받는다.
        """
        from core import klef_overlay
        route = str(route or '')
        if edition.STUDENT or not klef_overlay.SPACE_PAGE.fullmatch(route):
            return {'ok': False, 'error': '열 수 없는 주소입니다.'}

        def run():
            try:
                self._show_space(route)
            except Exception as exc:
                self._log('에듀파인 바로보기에서 SPACEKIJUN 을 열지 못했습니다:', exc)
        threading.Thread(target=run, name='klef-open-space', daemon=True).start()
        return {'ok': True}

    def _show_space(self, route=None):
        url = SPACEKIJUN_URL.rstrip('/') + route if route else SPACEKIJUN_URL
        import webview
        from webview.menu import Menu, MenuAction
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            if self._space_window:
                if route:
                    self._space_window.load_url(url)
                self._space_window.show()
                self._space_window.restore()
                self._bring_front(self._space_window)
                self._web_login.start(self._space_window, 'space', force=True, target=url)
                return '프로그램 안의 스페이스기전 창을 열었습니다.'
            space = webview.create_window(
                'SPACEKIJUN · 스페이스기전', url,
                # Remote web content must never receive the local Python API.
                js_api=None, width=1280, height=900, min_size=(860, 620),
                background_color='#f6f7fb', text_select=True, zoomable=True,
                menu=[Menu('스페이스기전', [
                    MenuAction('업무 홈으로 이동', lambda: self._space_home()),
                    MenuAction('새로고침', lambda: self._space_reload()),
                    MenuAction('데스크 설정 열기', lambda: self._show_desk()),
                ])])
            self._space_window = space
            first = [url]       # 처음 불러올 때만 열려던 화면 — 그 뒤로는 창이 보는 화면
            space.events.loaded += lambda: self._web_login.start(space, 'space', target=first.pop() if first else None)

            def closed():
                self._web_login.forget(space)
                with self._lock:
                    if self._space_window is space:
                        self._space_window = None
            space.events.closed += closed
            self._front_when_loaded(space)
        self._log('프로그램 안에서 스페이스기전을 열었습니다.')
        return '최신 배포된 스페이스기전을 불러옵니다.'

    def _open_seaton(self, _):
        import webview
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            if self._seaton_window:
                self._seaton_window.show()
                self._seaton_window.restore()
                self._bring_front(self._seaton_window)
                self._web_login.start(self._seaton_window, 'seaton', force=True)
                return '프로그램 안의 기전시트온 창을 열었습니다.'
            window = webview.create_window('기전시트온 · 자습 관리', SEATON_URL,
                js_api=None, width=1280, height=900, min_size=(860, 620),
                background_color='#f6f7fb', text_select=True, zoomable=True)
            self._seaton_window = window
            window.events.loaded += lambda: self._web_login.start(window, 'seaton')
            def closed():
                self._web_login.forget(window)
                with self._lock:
                    if self._seaton_window is window:
                        self._seaton_window = None
            window.events.closed += closed
            self._front_when_loaded(window)
        return '기전시트온을 열고 데스크 계정으로 연결합니다.'

    def _open_isekai3d(self, _):
        """이세계 사회인 (2026-10-19 요청) — 이 PC 의 로컬 서버(core/isekai3d_server.py)에서 게임을 연다.
        게임 창은 웹 내용이라 데스크 API 를 주지 않는다(js_api=None). 저장은 학생 프로필의 localStorage."""
        import webview
        from core import isekai3d_server
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            if self._isekai3d_window:
                self._isekai3d_window.show()
                self._isekai3d_window.restore()
                self._bring_front(self._isekai3d_window)
                return '열려 있는 이세계 사회인 창을 앞으로 가져왔습니다.'
            if not self._isekai3d_server:
                # 게임에서 로그인 안 된 것을 보면 이 프로그램의 스페이스기전 로그인(브라우저 구글 로그인)을 연다
                self._isekai3d_server = isekai3d_server.Server(signin=lambda: self._auth({}))
            url = self._isekai3d_server.start()
            window = webview.create_window('고등학생이었던 내가 이세계에서는 사회인?', url, js_api=None, width=1440, height=900,
                min_size=(1024, 700), background_color='#dfeee2', text_select=False)
            self._isekai3d_window = window
            def closed():
                with self._lock:
                    if self._isekai3d_window is window:
                        self._isekai3d_window = None
            window.events.closed += closed
            self._front_when_loaded(window)
        self._log('이세계 사회인을 열었습니다.')
        return '이세계 사회인을 엽니다.'

    def _space_home(self):
        if self._space_window:
            self._space_window.load_url(SPACEKIJUN_URL)

    def _space_reload(self):
        if self._space_window:
            self._space_window.run_js('window.location.reload()')

    def _show_desk(self):
        if self._desk_window:
            self._desk_window.show()
            self._desk_window.restore()
            self._bring_front(self._desk_window)

    # ── 독 ─────────────────────────────────────────────────────
    # 바탕화면 아래 가운데에 떠 있는 아이콘 줄(web/dock.html). 아이콘을 누르면 위의
    # 기존 작업(업무시스템·스페이스기전·데스크 화면)을 그대로 부른다.
    def set_dock(self, visible: bool):
        """독을 띄우거나 숨기고, 다음 실행에도 그대로 하도록 기억한다."""
        self.dock_enabled = bool(visible)
        self._save_preferences(dock=self.dock_enabled)
        if self.dock_enabled:
            self._show_dock()
            return '독을 표시합니다.'
        with self._lock:
            window = self._dock_window
        if window:
            window.hide()
        if self._dock_handle:
            self._dock_handle.hide()
        self._popover_close({})
        self._log('독을 숨겼습니다. 트레이 메뉴에서 다시 표시할 수 있습니다.')
        return '독을 숨겼습니다.'

    def dock_front(self):
        """다른 창에 가려진 독을 앞으로 (독은 항상 위가 아니다). 꺼져 있으면 켠다."""
        if not self.dock_enabled:
            return self.set_dock(True)
        with self._lock:
            window = self._dock_window
        if window is None:
            self._show_dock()
            return '독을 표시합니다.'
        window.show()
        self._bring_front(window)
        self._raise_dock_company()
        return '독을 앞으로 가져왔습니다.'

    def _raise_dock_company(self):
        """독과 함께 떠 있던 것들도 앞으로 (2026-10-29 요청) — 단축키·손잡이 줄로 독을 올리면 독만 올라와,
        펼쳐 둔 패널과 바탕화면의 스티커 메모가 다른 창 뒤에 남았다.
        · 패널 — 열려 있을 때만(닫힌 패널은 숨겨 둔 미리 만든 창이다). 독 다음에 올려 독보다 위에.
        · 메모 창 — 보이는 것만(내려 둔 것은 그대로). '항상 위' 메모는 이미 앞이라 건드리지 않는다
          (TopMost 를 껐다 켜면 그 설정이 풀린다).
        포커스는 독이 가져간다 — 여기서는 순서만 올리고 활성화하지 않는다."""
        with self._lock:
            stickies = list(self._sticky_windows.values())
            popover = self._popover_window if self._popover_request and self._popover_ready else None
        for window in stickies + ([popover] if popover else []):
            form = self._dock_form(window)
            if form is None:
                continue

            def lift(form=form, sticky=window is not popover):
                if not form.Visible or str(form.WindowState) == 'Minimized':
                    return
                if sticky and form.TopMost:
                    return
                form.TopMost = True
                form.TopMost = False
            on_ui(form, lift, self._log)

    def _show_dock(self):
        import webview
        with self._lock:
            if self._shutdown.is_set() or self._dock_creating:
                return
            if self._dock_window:
                self._dock_window.show()
                return
            self._dock_creating = True
        # 🚨 create_window 는 잠금 밖에서 부른다. 이 호출은 창이 UI 스레드에서 만들어질 때까지 기다리는데,
        #    그 UI 스레드가 잠금을 기다리면(예: 독 창 꾸미기) 서로 기다리다 화면이 영영 안 뜬다
        #    (2026-10-19 확인 — 독·데스크가 about:blank 로 숨은 채 멈추고 트레이도 먹통).
        try:
            width, height = DOCK_SIZE
            x = y = None
            if webview.screens:
                area = webview.screens[0]
                x = area.x + (area.width - width) // 2
                y = area.y + area.height - height - 48     # 작업 표시줄 높이쯤. dock.js 가 바로잡는다
            # 항상 위에 두지 않는다 — 다른 창처럼 겹치고, 누르면 앞으로 온다 (2026-10-11 요청)
            window = webview.create_window(
                '스페이스기전 독', str(WEB_DIR / 'dock.html'), js_api=self,
                width=width, height=height, x=x, y=y, frameless=True, easy_drag=False,
                transparent=True, shadow=False, resizable=False, min_size=(200, 100))
        finally:
            with self._lock:
                self._dock_creating = False
        with self._lock:
            late = self._shutdown.is_set()         # 만드는 사이에 끝내기가 지나갔다 (_close 가 못 본 창)
            if not late:
                self._dock_window = window
        if late:
            window.destroy()
            return

        def shown(made=window):
            self._dock_chrome(made)

        def closed(made=window):
            with self._lock:
                if self._dock_window is made:
                    self._dock_window = None
        window.events.shown += shown
        window.events.loaded += self._ui_seen
        window.events.closed += closed
        self._watch_dock_handle()

    @staticmethod
    def _dock_form(window):
        if window is None or 'webview.platforms.winforms' not in sys.modules:
            return None
        try:
            from webview.platforms.winforms import BrowserView
        except ImportError:
            return None
        return BrowserView.instances.get(window.uid)

    def _dock_chrome(self, window, keep_hwnd=True):
        """독 창을 바탕화면에 얹힌 모양으로 만든다.

        · **바깥 비우기** — pywebview 의 `transparent` 는 Windows 에서 창 바탕색(회색)을 그대로
          비춘다 (6.2.1 확인). 창 바탕을 검게 칠하고 DWM 프레임을 창 전체로 넓히면(유리) 검은
          자리가 비치고, 반투명한 판·그림자도 아래 화면과 섞여 보인다.
          🚨 `TransparencyKey`(색 뚫기)를 쓰면 안 된다. 보기에는 같지만 WebView2 가 그린 판까지
          뚫린 것으로 쳐서 **클릭이 전부 아래 창으로 빠진다** (2026-10-11 사용자 보고).
          🚨 pywebview 는 Windows 가 다크 모드면 창 배경을 Mica(DWMWA_SYSTEMBACKDROP_TYPE=2)로
          켠다 (테마가 바뀔 때마다 다시). 유리 창에서는 그 Mica 가 창 모양 전체에 짙은 회색으로
          비친다 (2026-10-12 사용자 보고). 그래서 배경을 끄고, 테마가 바뀌면 다시 끈다.
        · **누를 자리만 남기기** — 유리는 창 전체가 클릭을 받는다. dock.js 가 판·말풍선·메뉴
          자리를 알려 주면 창 모양(region)을 그만큼으로 줄여, 나머지는 아래 창이 받게 한다
          (`_dock_region`).
        · **작업 표시줄·Alt+Tab 에서 빼기** — 도구 창 스타일.
          🚨 WinForms `ShowInTaskbar = False` 를 쓰면 안 된다. 창 핸들을 새로 만들어서 이미
          붙은 WebView2 가 `E_ABORT` 로 죽고 독이 영영 안 보인다 (2026-10-11 확인).
          같은 핸들에 Win32 스타일만 바꾸고, 작업 표시줄이 알아채도록 한 번 숨겼다 보인다.
        `_set_on_top` 처럼 창의 UI 스레드에서 바꾼다.
        """
        form = self._dock_form(window)
        if form is None:
            return
        from System.Drawing import Color

        class Margins(ctypes.Structure):
            _fields_ = [('left', ctypes.c_int), ('right', ctypes.c_int),
                        ('top', ctypes.c_int), ('bottom', ctypes.c_int)]

        def apply():
            form.BackColor = Color.Black
            user32 = _user32
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            hwnd = ctypes.c_void_p(form.Handle.ToInt64())
            if keep_hwnd:
                self._dock_hwnd = form.Handle.ToInt64()
                self._dock_to_saved_screen(hwnd)
            glass = Margins(-1, -1, -1, -1)
            _dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(glass))
            clear_backdrop(hwnd)
            GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
            style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
            SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
            user32.ShowWindow(hwnd, SW_HIDE)
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        on_ui(form, apply, self._log)
        self._watch_theme()

    def _watch_theme(self):
        """Windows 테마가 바뀌면 pywebview 가 Mica 를 다시 켠다 — 독·패널 창에서 곧바로 다시 끈다.

        pywebview 의 처리와 어느 쪽이 먼저 돌지 정해져 있지 않아, 바로 한 번, 조금 뒤 한 번 끈다."""
        with self._lock:
            if self._theme_watched:
                return
            self._theme_watched = True
        try:
            from Microsoft.Win32 import SystemEvents
        except ImportError:
            return

        def clear():
            with self._lock:
                windows = (self._dock_window, self._popover_window)
            for window in windows:
                form = self._dock_form(window)
                if form is not None:
                    on_ui(form, lambda form=form: clear_backdrop(ctypes.c_void_p(form.Handle.ToInt64())),
                          self._log)

        def changed(*_):
            clear()
            later = threading.Timer(1.0, clear)
            later.daemon = True
            later.start()
        SystemEvents.UserPreferenceChanged += changed

    # ── 독 위 정보 패널 ─────────────────────────────────────────
    # 시간표·일정·업무·공지·알림·스티커 메모는 새 창 대신 독 위로 펼치는 패널로 보인다
    # (2026-10-11 요청). 패널 창은 하나를 만들어 두고 내용만 바꿔 가며 숨겼다 보인다 — 처음 한 번만
    # WebView2 를 띄우는 시간이 든다. 독과 같은 유리 창이고, 자리는 dock.js 가 아이콘 위로 셈한다.
    def _popover_open(self, payload):
        key, rect, caret = payload.get('key'), payload.get('rect'), payload.get('caret') or {}
        if key not in POPOVER_KEYS:
            raise ValueError('지원하지 않는 패널입니다.')
        try:
            x, y, w, h = (int(value) for value in rect)
            side, at = caret.get('side'), int(caret.get('at', 0))
        except (TypeError, ValueError, AttributeError):
            raise ValueError('패널 자리 형식이 올바르지 않습니다.') from None
        if side not in POPOVER_SIDES or not (200 <= w <= 1200 and 200 <= h <= 1200) \
                or not (-DOCK_REACH <= x <= DOCK_REACH and -DOCK_REACH <= y <= DOCK_REACH):
            raise ValueError('패널 자리 형식이 올바르지 않습니다.')
        request = {'key': key, 'caret': {'side': side, 'at': at}}
        # 자리는 독 화면의 CSS px — 패널 화면도 같은 배율로 그려지므로 창도 같은 배수로 (_dock_scales)
        self._dock_take_ratio(payload)
        zoom = self._dock_scales()[2]
        x, y, w, h = (round(value * zoom) for value in (x, y, w, h))
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            self._popover_request = request
            window, ready = self._popover_window, self._popover_ready
        if window is None:
            self._popover_create((x, y, w, h))   # 다 불러오면 loaded 가 보인다
            return None
        window.resize(w, h)
        window.move(x, y)
        if ready:
            self._popover_render(window)
            window.show()
            self._bring_front(window)
        return None                                # 아직 불러오는 중이면 loaded 가 보인다

    def _popover_prewarm(self):
        """패널 창을 미리 만들어 둔다 (화면 밖에, 다 불러오면 숨겨) — 처음 누를 때 기다리지 않게."""
        self._popover_create((-32000, -32000, 404, 504))

    def _popover_create(self, rect):
        import webview
        x, y, w, h = rect
        with self._lock:
            if self._popover_window is not None or self._popover_creating or self._shutdown.is_set():
                return
            self._popover_creating = True
        try:
            # 🚨 잠금 밖에서 — _show_dock 의 🚨 와 같다 (켤 때 독 꾸미기와 서로 기다려 멈췄다, 2026-10-19)
            window = webview.create_window(
                '스페이스기전 독 패널', str(WEB_DIR / 'popover.html'), js_api=self,
                width=w, height=h, x=x, y=y, frameless=True, easy_drag=False,
                transparent=True, shadow=False, resizable=False, min_size=(200, 200))
        finally:
            with self._lock:
                self._popover_creating = False
        with self._lock:
            late = self._shutdown.is_set()
            if not late:
                self._popover_window, self._popover_ready = window, False
        if late:
            window.destroy()
            return
        glassed = threading.Event()

        def shown(*_):
            # 🚨 shown 은 손을 걸기 전에 지나갈 수 있다 — loaded 에서도 한 번 더 확인한다
            if not glassed.is_set():
                glassed.set()
                self._dock_chrome(window, keep_hwnd=False)

        def loaded(made=window):
            shown()
            with self._lock:
                self._popover_ready = True
                request = self._popover_request
            if request:
                self._popover_render(made)
                made.show()
                self._bring_front(made)
            else:
                made.hide()                        # 미리 만든 창 — 부를 때까지 숨겨 둔다

        def closed(made=window):
            with self._lock:
                if self._popover_window is made:
                    self._popover_window, self._popover_ready = None, False
        window.events.shown += shown
        window.events.loaded += loaded
        window.events.closed += closed

    def _popover_render(self, window):
        with self._lock:
            request = self._popover_request
        if request:
            window.run_js('window.deskPopover && window.deskPopover.show(%s)' % json.dumps(request))

    def _popover_close(self, _):
        """패널을 숨기고, 독에게 알려 아이콘의 '열림' 표시를 지우게 한다."""
        with self._lock:
            window, dock = self._popover_window, self._dock_window
            self._popover_request = None
        if window:
            window.hide()
        if dock:
            dock.run_js('window.deskDock && window.deskDock.popClosed()')
        return None

    def _on_dock_ui(self, work):
        """독 창의 UI 스레드에서 돌린다 — 손잡이 줄(WinForms)도 그 스레드에 산다."""
        with self._lock:
            form = self._dock_form(self._dock_window)
        if form is None:
            return
        on_ui(form, work, self._log)

    def _watch_dock_handle(self):
        with self._lock:
            if self._dock_handle_job and self._dock_handle_job.is_alive():
                return
            self._dock_handle_job = threading.Thread(target=self._dock_handle_loop, daemon=True,
                                                     name='desk-dock-handle')
            self._dock_handle_job.start()

    def _dock_handle_loop(self):
        """손잡이 줄이 독을 따라가게 한다. 독 판이 옮겨 갈 때(`_dock_region`)도 바로 맞추지만,
        작업 표시줄·해상도가 바뀌거나 독이 숨겨지는 경우를 위해 가끔 다시 본다."""
        failed = False
        while not self._shutdown.wait(DOCK_HANDLE_POLL):
            try:
                self._dock_handle_tick()
                failed = False
            except Exception as exc:
                if not failed:                     # 같은 오류를 0.4초마다 쌓지 않는다
                    self._log('독 손잡이를 확인하지 못했습니다:', exc)
                failed = True

    def _handle_clicked(self):
        """손잡이 줄에 마우스를 올려 잠깐 머무르거나 눌렀다 (core/dock_handle.py) — 독을 앞으로."""
        if self._dock_handle:
            self._dock_handle.hide()
        self.dock_front()

    def _dock_handle_tick(self):
        """독 판의 화면 끝 쪽 바로 바깥에 손잡이 줄을 **늘** 띄워 둔다 (2026-10-11 요청).
        독을 끌거나 접었다 펴는 동안, 독을 숨겼을 때만 감춘다."""
        from core import dock_handle
        with self._lock:
            window, hwnd = self._dock_window, self._dock_hwnd
            shelf, anchor, moving = self._dock_shelf, self._dock_anchor, self._dock_moving
        handle = self._dock_handle
        if (not (self.dock_enabled and window and hwnd and shelf) or moving
                or not _user32.IsWindowVisible(ctypes.c_void_p(hwnd))):
            if handle:
                handle.hide()
            self._ranch_follow(None, None)          # 독이 숨거나 끌리는 동안 목장도 감춘다
            return
        rect = ctypes.wintypes.RECT()
        _user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
        scale = self._dock_scales()[0]
        x, y, w, h = shelf
        box = (rect.left + round(x * scale), rect.top + round(y * scale),
               rect.left + round((x + w) * scale), rect.top + round((y + h) * scale))
        self._ranch_follow(box, anchor)
        if handle is None:
            self._dock_handle = handle = dock_handle.Handle(self._on_dock_ui, self._handle_clicked)
        handle.show(dock_handle.line_rect(anchor, box, scale))
        handle.check()

    # ── 별사이 목장 (학생판, 2026-11-06) ──────────────────────────
    # 독 위 띠에서 아기 동물을 키운다 (core/ranch.py · web/ranch.html). 독처럼 유리 창이고, 독 창을 **소유자**로 두어
    # 독과 함께 앞뒤가 바뀐다(항상 위가 아님). 누를 자리(동물·조각·단추·열린 패널)만 창 모양으로 남겨 빈 곳은 아래 창이 받는다.
    # 자리는 독 손잡이 줄과 같은 박자(_dock_handle_tick)로 따라간다.
    # 2026-11-11 요청: 학생판 정식 판에서는 **관리자 계정만** 목장을 본다(아직 다듬는 중) — 나머지 학생은 목장 없이 같은 판.
    # 손잡이 박자에서 불리므로 역할을 기다리지 않는다 — 모르면(처음·만료) 뒤에서 묻고 그동안은 안 보인다.
    def _ranch_allowed(self) -> bool:
        if os.environ.get('SPACEKIJUN_RANCH') == '1':                     # 시험할 때
            return True
        if not edition.STUDENT:
            return False
        with self._lock:
            cached = self._role_cache
            asking = self._ranch_role_asking
        if cached and time.monotonic() - cached[1] < ROLE_TTL:
            return cached[0] == 'admin'
        if not asking:
            with self._lock:
                self._ranch_role_asking = True

            def ask():
                try:
                    if self._is_admin():
                        self._dock_handle_tick()
                except Exception as exc:
                    self._log('별사이 목장 — 계정 역할을 확인하지 못했습니다:', exc)
                finally:
                    with self._lock:
                        self._ranch_role_asking = False
            threading.Thread(target=ask, daemon=True, name='ranch-role').start()
        return bool(cached and cached[0] == 'admin')

    def _ranch_follow(self, box, anchor):
        """독 판(화면 사각형)을 따라 목장 창을 놓는다. box 가 None 이면 감춘다. 손잡이 박자에서 불린다."""
        allowed = self._ranch_allowed()
        with self._lock:
            enabled, window, hwnd = self.ranch_enabled and allowed, self._ranch_window, self._ranch_hwnd
            dock_hwnd, length = self._dock_hwnd, self._ranch_length
        if not allowed and window is None:
            return
        if box is None or not enabled:
            if window is not None and hwnd and _user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
                form = self._dock_form(window)

                def hide():
                    _user32.ShowWindow(ctypes.c_void_p(hwnd), 0)       # SW_HIDE
                if form is not None:
                    on_ui(form, hide, self._log)
                    self._ranch_spot = None
            return
        if window is None:
            self._ranch_create()
            return
        if not hwnd:
            return                                  # 아직 꾸미는 중 (_ranch_chrome)
        from core import ranch
        work = screen_of(ctypes.c_void_p(dock_hwnd)) or [box[0], box[1] - 600, box[2], box[3]]
        scale = self._ranch_ratio or self._dock_scales()[0]
        view = ranch.clean_view(self._ranch_view)
        spot = ranch.place(anchor, box, tuple(work), view, scale)
        key = (spot['x'], spot['y'], spot['width'], spot['height'])
        top = view['top']
        visible = bool(_user32.IsWindowVisible(ctypes.c_void_p(hwnd)))
        if key == self._ranch_spot and visible and top == self._ranch_top:
            return
        self._ranch_spot, self._ranch_mode, self._ranch_zoom, self._ranch_top = key, spot['mode'], spot['zoom'], top
        form = self._dock_form(window)
        if form is None:
            return

        def apply():
            SWP_NOZORDER, SWP_NOACTIVATE, SW_SHOWNOACTIVATE = 0x4, 0x10, 4
            _user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                             ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            # 항상 위(참고 게임의 «게임 창 고정») — 끄면 다시 독과 함께 앞뒤가 바뀐다(소유자 = 독)
            after = ctypes.c_void_p(-1 if top else -2)                       # HWND_TOPMOST · HWND_NOTOPMOST
            _user32.SetWindowPos(ctypes.c_void_p(hwnd), after, *key, SWP_NOACTIVATE)
            if not _user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
                _user32.ShowWindow(ctypes.c_void_p(hwnd), SW_SHOWNOACTIVATE)
        on_ui(form, apply, self._log)

    def _ranch_create(self):
        import webview
        with self._lock:
            if self._shutdown.is_set() or self._ranch_creating or self._ranch_window is not None:
                return
            self._ranch_creating = True
        try:
            from core import ranch
            window = webview.create_window(
                '별사이 목장', str(WEB_DIR / 'ranch.html'), js_api=self,
                width=900, height=ranch.STRIP + ranch.PANEL, x=-32000, y=-32000, frameless=True, easy_drag=False,
                transparent=True, shadow=False, resizable=False, focus=False, hidden=True)
        finally:
            with self._lock:
                self._ranch_creating = False
        with self._lock:
            late = self._shutdown.is_set()
            if not late:
                self._ranch_window, self._ranch_hwnd, self._ranch_spot = window, None, None
        if late:
            window.destroy()
            return

        def closed(made=window):
            with self._lock:
                if self._ranch_window is made:
                    self._ranch_window, self._ranch_hwnd, self._ranch_spot = None, None, None
        window.events.shown += lambda made=window: self._ranch_chrome(made)
        window.events.loaded += lambda made=window: self._ranch_chrome(made)
        window.events.closed += closed

    def _ranch_chrome(self, window):
        """독과 같은 유리 창 + 작업 표시줄에서 빼기 + 독 창을 소유자로 (독과 함께 앞뒤가 바뀐다)."""
        form = self._dock_form(window)
        with self._lock:
            dock_hwnd = self._dock_hwnd
        if form is None or not dock_hwnd:
            return
        from System.Drawing import Color

        class Margins(ctypes.Structure):
            _fields_ = [('left', ctypes.c_int), ('right', ctypes.c_int), ('top', ctypes.c_int), ('bottom', ctypes.c_int)]

        def apply():
            form.BackColor = Color.Black
            user32 = _user32
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            hwnd = ctypes.c_void_p(form.Handle.ToInt64())
            glass = Margins(-1, -1, -1, -1)
            _dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(glass))
            clear_backdrop(hwnd)
            GWL_EXSTYLE, GWLP_HWNDPARENT, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_NOACTIVATE = -20, -8, 0x80, 0x40000, 0x08000000
            style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, (style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW)
            user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, dock_hwnd)
            user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
            _gdi32.CreateRectRgn.restype = ctypes.c_void_p
            user32.SetWindowRgn(hwnd, ctypes.c_void_p(_gdi32.CreateRectRgn(0, 0, 0, 0)), True)   # 화면이 알려 줄 때까지 아무것도 받지 않는다
            with self._lock:
                if self._ranch_window is window:
                    self._ranch_hwnd, self._ranch_spot = form.Handle.ToInt64(), None
            self._ranch_apply_region()                # 꾸미기 전에 온 누를 자리
        on_ui(form, apply, self._log)

    def _ranch_region(self, payload):
        """목장 화면이 알려 준 누를 자리(창 안 CSS px 사각형들) · 배율 · 목장 길이."""
        from core import ranch
        rects = ranch.clean_rects(payload.get('rects'))
        ratio, length = payload.get('ratio'), payload.get('length')
        with self._lock:
            if isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and 0.5 <= ratio <= 5:
                self._ranch_ratio = float(ratio)
            if isinstance(length, int) and not isinstance(length, bool) and 0 <= length <= 9000:
                if length != self._ranch_length:
                    self._ranch_spot = None          # 길이가 바뀌었다 — 다음 박자에 다시 놓는다
                self._ranch_length = length
            # 기억해 둔다 — 창을 꾸미기 전에 온 자리는 꾸민 뒤에 입힌다(화면은 같은 자리를 다시 보내지 않는다, 2026-11-06 실측)
            self._ranch_rects = rects
        self._ranch_apply_region()
        return None

    def _ranch_apply_region(self):
        with self._lock:
            window, hwnd, scale, rects = self._ranch_window, self._ranch_hwnd, self._ranch_ratio or 1.0, self._ranch_rects
        form = self._dock_form(window)
        if form is None or not hwnd or rects is None:
            return

        def apply():
            _gdi32.CreateRectRgn.restype = ctypes.c_void_p
            _gdi32.CombineRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            _gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
            _user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
            shape = _gdi32.CreateRectRgn(0, 0, 0, 0)
            for x, y, w, h in rects:
                piece = _gdi32.CreateRectRgn(round(x * scale), round(y * scale), round((x + w) * scale), round((y + h) * scale))
                _gdi32.CombineRgn(shape, shape, piece, 2)          # RGN_OR
                _gdi32.DeleteObject(piece)
            if not _user32.SetWindowRgn(ctypes.c_void_p(hwnd), ctypes.c_void_p(shape), True):
                _gdi32.DeleteObject(ctypes.c_void_p(shape))
        on_ui(form, apply, self._log)

    def _ranch_state(self, _):
        """목장 화면이 처음과 가끔 묻는 것 — 수업 중인가, 놓인 자리(독 위·바탕화면 아래), 로그인."""
        from core import ranch
        cached = self._dash_cached()
        cells = (cached[1] or {}).get('timetable_week') if cached else None
        signed = bool(supa_auth.whoami())
        if signed and not cached:
            self._start_dash_prefetch()               # 시간표를 받아 두면 다음 물음부터 정확하다
        return {'lesson': ranch.lesson_now(cells), 'mode': self._ranch_mode or 'dock', 'signed_in': signed,
                'view': ranch.clean_view(self._ranch_view), 'zoom': self._ranch_zoom}

    def _ranch_set_view(self, payload):
        """«화면» — 너비(작업 영역의 몇 할)·가로 위치·높이(바닥선에서 올리기)·크기(그림 1화소 = 실제 몇 픽셀, 비우면 해상도대로)·항상 위."""
        from core import ranch
        view = ranch.clean_view(payload.get('view'))
        with self._lock:
            self._ranch_view, self._ranch_spot = view, None
        self._save_preferences(ranch_view=view)
        self._dock_handle_tick()
        return {'view': view, 'zoom': self._ranch_zoom}

    def _ranch_call(self, payload):
        """목장 저장·코인 교환·공부 선물 — 정해진 스페이스기전 RPC 로만 (core/ranch.py BRIDGE)."""
        from core import ranch
        work, body = payload.get('work'), payload.get('body') or {}
        if not isinstance(body, dict):
            raise ValueError('목장 요청 형식이 올바르지 않습니다.')
        return ranch.bridge(str(work), body)

    def _ranch_set(self, payload):
        """학생판 설정의 «별사이 목장 보이기»."""
        on = payload.get('on')
        if not isinstance(on, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        if on and not self._ranch_allowed():
            raise ValueError('별사이 목장은 지금 관리자 계정에서만 볼 수 있습니다.')
        with self._lock:
            self.ranch_enabled = on
            if not on:
                self._ranch_spot = None
        self._save_preferences(ranch=on)
        self._dock_handle_tick()
        return '별사이 목장을 보입니다.' if on else '별사이 목장을 숨겼습니다.'

    def _dock_preview_show(self, payload):
        """끄는 독이 화면 끝에 닿으면 놓였을 때의 판 자리를 반투명하게 보인다. rect 가 없으면 감춘다.

        rect 는 화면 좌표 [x, y, 너비, 높이] (논리 픽셀) — dock.js 가 놓일 방향·크기로 미리 계산한다."""
        self._dock_take_ratio(payload)
        rect = payload.get('rect')
        if rect is None:
            if self._dock_preview:
                self._dock_preview.hide()
            return
        try:
            x, y, w, h = (int(value) for value in rect)
            radius = int(payload.get('radius', 22))
        except (TypeError, ValueError):
            raise ValueError('독 미리보기 형식이 올바르지 않습니다.') from None
        if not (0 < w <= 8000 and 0 < h <= 8000 and 0 <= radius <= 200
                and -DOCK_REACH <= x <= DOCK_REACH and -DOCK_REACH <= y <= DOCK_REACH):
            raise ValueError('독 미리보기 형식이 올바르지 않습니다.')
        from core import dock_handle
        with self._lock:
            hwnd = self._dock_hwnd
        if not hwnd or self._dock_form(self._dock_window) is None:
            return
        # 독 화면과 같은 배율로 실제 픽셀로 바꾼다
        scale = self._dock_scales()[0]
        # 🚨 pywebview 는 부를 때마다 스레드를 따로 쓴다 — 끄는 동안 미리보기 요청이 겹치면 둘이 함께 만들고 하나를
        # 버렸고, 버린 것의 창은 처리 함수가 지워진 채 남아 다음 메시지에서 데스크가 튕겼다 (2026-11-06 0xc0000005)
        with self._lock:
            if self._dock_preview is None:
                self._dock_preview = dock_handle.Preview(self._on_dock_ui)
            preview = self._dock_preview
        preview.show((round(x * scale), round(y * scale), round(w * scale), round(h * scale)),
                                round(radius * scale))

    def _dock_take_ratio(self, payload):
        """dock.js 가 알려 준 devicePixelRatio 를 받아 둔다. 창 배율과 다르면 한 번 기록한다."""
        ratio = payload.get('ratio')
        if not (isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and 0.5 <= ratio <= 8):
            return
        with self._lock:
            changed, self._dock_ratio = self._dock_ratio != ratio, float(ratio)
        if changed:
            dpi, zoom = self._dock_scales()[1:]
            if abs(zoom - 1) > 0.01:
                self._log(f'독 화면 배율({ratio:g})이 창 배율({dpi:g})과 다릅니다 — '
                          f'Windows 텍스트 크기 설정 등. {zoom:.2f}배로 맞춥니다.')

    def _dock_scales(self):
        """(ratio, dpi, zoom) — ratio: 독 화면 CSS 1px 의 실제 픽셀 수, dpi: 창 배율(pywebview 가 곱하는 값),
        zoom = ratio / dpi: CSS px 를 pywebview 의 창 크기·자리 단위로 바꾸는 배수.

        보통은 둘이 같아 zoom 이 1 이다. WebView2 는 **Windows 텍스트 크기**(설정 > 접근성)까지 곱해 그리므로
        그 값이 100% 가 아니면 화면 속 독이 그만큼 커지는데, 창·누를 자리·손잡이 줄을 창 배율로만 셈하면
        독이 크게 그려지면서 가장자리가 잘렸다 (2026-10-22 사용자 보고, 학생판 — 150% PC).
        그래서 창 쪽 셈은 모두 dock.js 가 알려 준 ratio 로 한다."""
        with self._lock:
            hwnd, ratio = self._dock_hwnd, self._dock_ratio
        dpi = (_user32.GetDpiForWindow(ctypes.c_void_p(hwnd)) or 96) / 96 if hwnd else 1.0
        ratio = ratio or dpi
        return ratio, dpi, ratio / dpi

    def _dock_region(self, payload):
        """독 창 가운데 **누를 수 있는 자리**만 남긴다 (창 안 좌표, 논리 픽셀 사각형들).

        rects 가 없으면(null) 창 전체 — 끌거나 접었다 펴는 동안 잘리지 않게."""
        self._dock_take_ratio(payload)
        shelf, anchor = payload.get('shelf'), payload.get('anchor')
        if shelf is not None:
            try:
                shelf = [int(value) for value in shelf]
            except (TypeError, ValueError):
                raise ValueError('독 판 자리 형식이 올바르지 않습니다.') from None
            if len(shelf) != 4 or shelf[2] <= 0 or shelf[3] <= 0 or anchor not in DOCK_ANCHORS:
                raise ValueError('독 판 자리 형식이 올바르지 않습니다.')
            with self._lock:
                self._dock_shelf, self._dock_anchor = shelf, anchor
        rects = payload.get('rects')
        if rects is not None:
            if not isinstance(rects, list) or not 1 <= len(rects) <= DOCK_REGION_RECTS:
                raise ValueError('독 영역 형식이 올바르지 않습니다.')
            try:
                rects = [tuple(int(value) for value in rect) for rect in rects]
            except (TypeError, ValueError):
                raise ValueError('독 영역 형식이 올바르지 않습니다.') from None
            if any(len(rect) != 4 or rect[2] <= 0 or rect[3] <= 0
                   or not all(-4000 <= value <= 8000 for value in rect) for rect in rects):
                raise ValueError('독 영역 형식이 올바르지 않습니다.')
        with self._lock:
            self._dock_moving = rects is None      # 끄는 중·접었다 펴는 중 — 줄을 감춘다
            form = self._dock_form(self._dock_window)
        try:
            self._dock_handle_tick()               # 독이 새 자리에 놓이면 줄도 곧바로 따라간다
        except Exception as exc:
            self._log('독 손잡이를 옮기지 못했습니다:', exc)
        if form is None:
            return
        # 창 모양은 실제 픽셀이다 — 독 화면 배율(화면 배율 × 텍스트 크기)을 곱한다.
        # 🚨 배율은 **여기서** 센다. apply 는 UI 스레드에서 도는데 _dock_scales 는 self._lock 을 잡는다.
        #    _open_space 처럼 잠금을 쥔 채 create_window 로 UI 스레드를 기다리는 쪽과 맞물리면 서로 기다려
        #    데스크 전체가 멈춘다 (2026-10-23 사용자 보고 — 스페이스기전·시트온이 안 열림, py-spy 로 확인).
        scale = self._dock_scales()[0]

        def apply():
            user32, gdi32 = _user32, _gdi32
            hwnd = ctypes.c_void_p(form.Handle.ToInt64())
            if rects is None:
                user32.SetWindowRgn(hwnd, None, True)
                return
            gdi32.CreateRectRgn.restype = ctypes.c_void_p
            gdi32.CombineRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
            user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
            shape = gdi32.CreateRectRgn(0, 0, 0, 0)
            RGN_OR = 2
            for x, y, w, h in rects:
                piece = gdi32.CreateRectRgn(round(x * scale), round(y * scale),
                                            round((x + w) * scale), round((y + h) * scale))
                gdi32.CombineRgn(shape, shape, piece, RGN_OR)
                gdi32.DeleteObject(piece)
            if not user32.SetWindowRgn(hwnd, shape, True):   # 성공하면 Windows 가 shape 를 맡는다
                gdi32.DeleteObject(shape)
        on_ui(form, apply, self._log)

    @staticmethod
    def _dock_point(payload):
        try:
            x, y = int(payload['x']), int(payload['y'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('독 위치 형식이 올바르지 않습니다.') from None
        if not (-DOCK_REACH <= x <= DOCK_REACH and -DOCK_REACH <= y <= DOCK_REACH):
            raise ValueError('독 위치가 화면을 벗어났습니다.')
        return x, y

    @staticmethod
    def _bring_front(window):
        """독에서 연 창을 맨 앞으로 가져온다.

        독은 눌러도 포커스를 가져가지 않는다(`focus=False`). 그래서 이 프로그램은 '앞 창'이
        아니고, Windows 는 새 창을 **다른 창 뒤에** 띄운다 (2026-10-11 확인). 잠깐 '항상 위'로
        올렸다 내리면 포커스 제한과 상관없이 맨 앞에 선다. 창의 UI 스레드에서 바꾼다."""
        if 'webview.platforms.winforms' not in sys.modules:
            return                      # 화면(WinForms)이 아직 안 떴다 — 올릴 창도 없다
        try:
            from webview.platforms.winforms import BrowserView
        except ImportError:
            return
        form = BrowserView.instances.get(window.uid)
        if form is None:
            return

        def apply():
            form.TopMost = True
            form.TopMost = False
            form.Activate()
        on_ui(form, apply)

    def _front_when_loaded(self, window):
        """새 창이 처음 화면을 그리면 한 번만 맨 앞으로 올린다.

        🚨 `events.shown` 에 걸면 안 된다. 프로그램이 이미 돌고 있을 때 만든 창은
        `create_window` 가 돌아오기 전에 shown 이 지나가 버려 손이 불리지 않는다
        (2026-10-11 확인 — 캡처 보관함이 다른 창 뒤에 떴다). 그 뒤 화면 이동에서는
        다시 올리지 않는다 — 사용자가 다른 창으로 옮겨 간 사이 튀어나오지 않게.
        로컬 화면은 loaded 마저 손을 걸기 전에 지나갈 수 있어(백그라운드 스레드에서 만든
        캡처 보관함), 걸고 나서 이미 지나갔는지도 본다."""
        done = threading.Event()
        lock = threading.Lock()

        def first():
            with lock:
                if done.is_set():
                    return
                done.set()
            self._bring_front(window)
        window.events.loaded += first
        if window.events.loaded.is_set():
            first()

    def _dock_place(self, payload):
        """dock.js 가 화면 크기를 보고 고른 자리·크기로 옮긴다 (독 화면의 CSS px — _dock_scales 의 zoom 을 곱한다)."""
        self._dock_take_ratio(payload)
        x, y = self._dock_point(payload)
        try:
            width, height = int(payload['width']), int(payload['height'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('독 크기 형식이 올바르지 않습니다.') from None
        if not (100 <= width <= 4000 and 100 <= height <= 4000):
            raise ValueError('독 크기가 올바르지 않습니다.')
        with self._lock:
            window = self._dock_window
        if window:
            zoom = self._dock_scales()[2]
            window.resize(round(width * zoom), round(height * zoom))
            window.move(round(x * zoom), round(y * zoom))

    def _dock_move(self, payload):
        """끄는 동안 창만 따라 옮긴다. 크기는 그대로."""
        self._dock_take_ratio(payload)
        x, y = self._dock_point(payload)
        with self._lock:
            window = self._dock_window
        if window:
            zoom = self._dock_scales()[2]
            window.move(round(x * zoom), round(y * zoom))

    @staticmethod
    def _valid_dock_layout(layout):
        """저장된 독 자리 — {anchor: 붙는 쪽, docked: 끝에 붙었나, cx·cy: 창 가운데(독 화면 CSS px),
        zoom: 그때의 CSS px → 이 프로그램 화면 좌표 배수 (_dock_scales, 없으면 1)}."""
        if not isinstance(layout, dict) or layout.get('anchor') not in DOCK_ANCHORS:
            return None
        result = {'anchor': layout['anchor'], 'docked': bool(layout.get('docked', True))}
        for name in ('cx', 'cy'):
            value = layout.get(name)
            if value is None:
                result[name] = None
            elif isinstance(value, (int, float)) and not isinstance(value, bool) \
                    and -DOCK_REACH <= value <= DOCK_REACH:
                result[name] = int(value)
            else:
                return None
        zoom = layout.get('zoom', 1)
        if isinstance(zoom, (int, float)) and not isinstance(zoom, bool) and 0.25 <= zoom <= 4:
            result['zoom'] = float(zoom)
        return result

    def _dock_to_saved_screen(self, hwnd):
        """새로 띄운 독 창을 지난번에 둔 모니터로 먼저 옮긴다 (독 UI 스레드에서).

        독 창은 늘 주 모니터에 생긴다. dock.js 는 **창이 놓인 모니터** 안에서만 자리를 셈하므로, 다른
        모니터에 두었던 독은 그대로 두면 주 모니터 끝으로 끌려왔다 (2026-10-14 사용자 보고 — 새로
        켜면 처음 자리로 돌아간다). 그 모니터의 가운데로 먼저 보내 두면 dock.js 가 그 모니터 안에서
        기억한 자리(cx·cy)로 놓는다. 그 모니터를 뺐으면 옮기지 않는다 — 주 모니터에 놓인다.
        cx·cy 는 독 화면의 CSS px 라 저장할 때의 zoom 을 곱해 이 프로그램의 화면 좌표로 모니터를 찾는다
        (보통 zoom 은 1 — 2026-10-14 위 모니터 150% 에서 확인, zoom 은 2026-10-22 텍스트 크기 때문에 더함).

        🚨 UI 스레드에서 돈다 — self._lock 을 잡으면 안 된다. 잠금을 쥔 채 창을 만들며 UI 스레드를
           기다리는 쪽과 서로 기다려 켤 때 화면이 영영 안 떴다 (2026-10-19). _dock_layout 은 통째로
           바꿔 끼우기만 하므로(_dock_save_layout) 잠금 없이 한 번 읽어도 된다."""
        layout = self._dock_layout or {}
        if layout.get('cx') is None or layout.get('cy') is None:
            return
        zoom = layout.get('zoom', 1)
        target = screen_at(layout['cx'] * zoom, layout['cy'] * zoom)
        if not target or target == screen_of(hwnd):
            return
        rect = ctypes.wintypes.RECT()
        _user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        width, height = rect.right - rect.left, rect.bottom - rect.top
        x = (target[0] + target[2] - width) // 2
        y = (target[1] + target[3] - height) // 2
        SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x4, 0x10
        _user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 4 + [ctypes.c_uint]
        _user32.SetWindowPos(hwnd, None, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)

    @staticmethod
    def _valid_dock_hidden(value):
        """설정에서 숨긴 독 아이콘 id 들. 형식이 어긋나면 None.

        설정 아이콘(`DOCK_ALWAYS`)은 숨길 수 없다 — 숨기면 다시 켤 길이 없다 (2026-10-23 요청).
        이미 숨겨 둔 PC 도 저장된 값을 읽을 때 여기서 빠지므로 다시 보인다.
        """
        if not isinstance(value, list) or len(value) > DOCK_ITEM_LIMIT:
            return None
        if not all(isinstance(item, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', item) for item in value):
            return None
        return sorted(set(value) - DOCK_ALWAYS)

    def _dock_items(self, _):
        """데스크 설정의 '독 아이콘' — 지금 숨긴 아이콘들."""
        with self._lock:
            return {'hidden': list(self._dock_hidden), 'dock': self.dock_enabled}

    def _dock_items_save(self, payload):
        """보일 아이콘을 바꾼다. 독이 떠 있으면 곧바로 다시 그리게 알린다 (2026-10-12 요청)."""
        hidden = self._valid_dock_hidden(payload.get('hidden'))
        if hidden is None:
            raise ValueError('독 아이콘 설정 형식이 올바르지 않습니다.')
        total = payload.get('total')
        if isinstance(total, int) and len(hidden) >= total:
            raise ValueError('아이콘을 적어도 하나는 남겨 주세요.')
        with self._lock:
            self._dock_hidden = hidden
            self._save_preferences(dock_hidden=hidden)
            dock = self._dock_window
        if dock:
            dock.run_js('window.deskDock && window.deskDock.setHidden(%s)' % json.dumps(hidden))
        return '독에 바로 반영했습니다.' if dock else '저장했습니다. 독을 켜면 이대로 보입니다.'

    # ── 독 불러오기 단축키 ─────────────────────────────────────
    # 독은 항상 위가 아니라 다른 창에 가려진다. 어디서든 단축키(기본 Ctrl+Alt+D)를 누르면 앞으로
    # 오고, 꺼져 있었으면 켠다 (2026-10-12 요청). 조합은 설정의 '독 아이콘'에서 바꾼다.
    def _start_hotkey(self):
        from core import hotkey
        combo = self._read_preferences().get('dock_hotkey', hotkey.DEFAULT)
        if combo not in hotkey.CHOICES:
            combo = hotkey.DEFAULT
        with self._lock:
            if self._hotkey is None:
                self._hotkey = hotkey.HotKey(self._hotkey_pressed, self._log)
        if not self._hotkey.use(combo):
            self._log(f'독 단축키 {hotkey.label(combo)} 를 다른 프로그램이 쓰고 있습니다. '
                      '설정의 ‘독 아이콘’에서 다른 조합을 골라 주세요.')

    def _hotkey_pressed(self):
        if not self.dock_enabled:
            self.set_dock(True)
            return
        self.dock_front()
        with self._lock:
            dock = self._dock_window
        if dock:
            dock.run_js('window.deskDock && window.deskDock.nudge()')   # 여기 있다고 살짝 튄다

    def hotkey_label(self) -> str:
        from core import hotkey
        if not self._hotkey or not self._hotkey.active:
            return ''
        return hotkey.label(self._hotkey.combo)

    def _dock_hotkey(self, _):
        from core import hotkey
        current = self._hotkey.combo if self._hotkey else self._read_preferences().get('dock_hotkey', hotkey.DEFAULT)
        return {'combo': current, 'active': bool(self._hotkey and self._hotkey.active),
                'choices': [{'key': key, 'label': hotkey.label(key)} for key in hotkey.CHOICES]}

    def _dock_hotkey_save(self, payload):
        from core import hotkey
        combo = payload.get('combo')
        if combo not in hotkey.CHOICES:
            raise ValueError('지원하지 않는 단축키입니다.')
        with self._lock:
            if self._hotkey is None:
                self._hotkey = hotkey.HotKey(self._hotkey_pressed, self._log)
        ok = self._hotkey.use(combo)
        self._save_preferences(dock_hotkey=combo)
        if combo == 'off':
            return '독 단축키를 껐습니다.'
        if not ok:
            raise RuntimeError(f'{hotkey.label(combo)} 는 다른 프로그램이 쓰고 있습니다. 다른 조합을 골라 주세요.')
        return f'이제 {hotkey.label(combo)} 를 누르면 독이 앞으로 옵니다.'

    def _dock_save_layout(self, payload):
        layout = self._valid_dock_layout({**payload, 'zoom': self._dock_scales()[2]})
        if layout is None:
            raise ValueError('독 배치 형식이 올바르지 않습니다.')
        with self._lock:
            self._dock_layout = layout
            self._save_preferences(dock_layout=layout)

    def _dock_state(self, _):
        """독 아이콘 아래 '실행 중' 점과 '여는 중' 움직임에 쓴다. 자주 부르므로 가볍게."""
        with self._lock:
            running = set(self._service_windows) | {f'page:{page}' for page in self._page_windows}
            if self._space_window:
                running.add('space')
            if self._seaton_window:
                running.add('seaton')
            if self._isekai3d_window:
                running.add('isekai3d')
            if self._sticky_windows:
                running.add('page:notes')
            if self._capture_window:
                running.add('captures')
            return {'running': sorted(running), 'busy': sorted(self._portals),
                    'layout': self._dock_layout, 'hidden': self._dock_hidden, 'edition': edition.EDITION,
                    'badges': {'messages': self._msg_unread, 'update': bool(self._update)}}

    def _open_page(self, payload):
        """독에서 고른 데스크 기능 하나를 **제 창**으로 띄운다. 이미 떠 있으면 앞으로 가져온다."""
        page = payload.get('page')
        if page == 'home':
            self._show_desk()
            if self._desk_window:
                self._desk_window.run_js("window.deskNavigate && window.deskNavigate('home')")
            return '데스크를 열었습니다.'
        if page not in PAGE_TITLES:
            raise ValueError('지원하지 않는 데스크 화면입니다.')
        title = PAGE_TITLES[page]
        import webview
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            window = self._page_windows.get(page)
            if window:
                window.show()
                window.restore()
                self._bring_front(window)
                return f'{title} 창을 앞으로 가져왔습니다.'
            # 옆 메뉴 없이 그 화면 하나만 보인다 (app.js 의 deskSolo). 바뀌기 전 화면이
            # 비치지 않도록 숨겨 만들고, 화면을 고른 뒤에 보인다.
            card = page.startswith('card:')
            window = webview.create_window(
                f'{title} · 스페이스기전 데스크', str(WEB_DIR / 'index.html'),
                js_api=self, width=560 if card else 1000, height=720 if card else 780,
                min_size=(420, 420) if card else (720, 560),
                background_color='#f6f7fb', text_select=True, hidden=True)
            self._page_windows[page] = window

        def loaded(made=window):
            made.run_js('window.deskSolo && window.deskSolo(%s)' % json.dumps(page))
            made.show()
            self._bring_front(made)

        def closed(made=window):
            with self._lock:
                if self._page_windows.get(page) is made:
                    self._page_windows.pop(page, None)
        window.events.loaded += loaded
        window.events.closed += closed
        return f'{title} 창을 열었습니다.'

    # ── 스티커 메모 ─────────────────────────────────────────────
    # 메모 자체는 SPACEKIJUN 협업노트에 저장한다(core/sticky.py). 여기서는 창만 다룬다.
    # 창 위치·크기·'항상 위'·열려 있던 메모는 이 PC 에만 기억한다.
    def _read_sticky_layout(self) -> dict:
        try:
            data = json.loads(self._sticky_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}

    def _save_sticky_layout(self):
        try:
            self._sticky_path.parent.mkdir(parents=True, exist_ok=True)
            self._sticky_path.write_text(json.dumps(self._sticky_layout, ensure_ascii=False),
                                         encoding='utf-8')
        except OSError as exc:
            self._log('메모 창 위치 저장 실패:', exc)

    def _sticky_create(self, payload):
        note = sticky.create(payload)
        if payload.get('open', True):
            self._sticky_open({'id': note['id']})
        return note

    def _sticky_update(self, payload):
        note = sticky.update(payload)
        with self._lock:
            window = self._sticky_windows.get(note['id'])
        if window and 'content' in payload:
            window.set_title(note.get('title') or '메모')    # 작업 표시줄에 첫 줄이 보이게
        return note

    def _sticky_delete(self, payload):
        if payload.get('ask'):
            with self._lock:
                window = self._sticky_windows.get(payload.get('id'))
            if not self._confirm(window, '메모 삭제',
                                 '이 메모를 삭제할까요?\n'
                                 '스페이스기전 협업노트에서도 함께 삭제되며 되돌릴 수 없습니다.'):
                return {'deleted': False, 'message': '삭제를 취소했습니다.'}
        message = sticky.delete(payload)
        with self._lock:
            window = self._sticky_windows.pop(payload.get('id'), None)
            self._sticky_layout.pop(payload.get('id'), None)
            self._save_sticky_layout()
        if window:
            window.destroy()
        return {'deleted': True, 'message': message}

    @staticmethod
    def _confirm(window, title: str, message: str) -> bool:
        """창 **바깥**에 뜨는 Windows 확인 창. 확인을 누르면 True.

        `window.confirm()` 은 페이지 안에 그려져 작은 메모 창에서 잘린다 (2026-10-08).
        pywebview 의 `create_confirmation_dialog` 는 주인 창 없이 떠서 '항상 위' 메모
        뒤로 숨는다. 그래서 메모 창을 주인으로 삼아 그 창의 UI 스레드에서 띄운다
        (다른 스레드에서 창을 건드리면 먹통이 된다 — `_set_on_top` 참고)."""
        try:
            from webview.platforms.winforms import BrowserView, WinForms
            from System import Func, Type
        except ImportError:                       # 다른 GUI 백엔드
            return bool(window and window.create_confirmation_dialog(title, message))
        form = BrowserView.instances.get(window.uid) if window else None
        buttons, icon = WinForms.MessageBoxButtons.OKCancel, WinForms.MessageBoxIcon.Warning
        default = WinForms.MessageBoxDefaultButton.Button2     # 실수로 Enter 를 눌러도 지우지 않게
        if form is None:
            return WinForms.MessageBox.Show(message, title, buttons, icon, default) == WinForms.DialogResult.OK
        answer = []

        def ask():
            answer.append(WinForms.MessageBox.Show(form, message, title, buttons, icon, default))
        form.Invoke(Func[Type](ask))             # 답할 때까지 기다린다 (이 호출은 JS 연결 스레드)
        return bool(answer) and answer[0] == WinForms.DialogResult.OK

    def _sticky_close(self, payload):
        with self._lock:
            window = self._sticky_windows.get(payload.get('id'))
        if window:
            window.destroy()
        return '메모 창을 닫았습니다.'

    def _sticky_pin(self, payload):
        on_top = payload.get('on_top')
        if not isinstance(on_top, bool):
            raise ValueError('요청 형식이 올바르지 않습니다.')
        with self._lock:
            window = self._sticky_windows.get(payload.get('id'))
            if not window:
                raise ValueError('메모 창이 열려 있지 않습니다.')
            self._sticky_layout.setdefault(payload['id'], {})['top'] = on_top
            self._save_sticky_layout()
        # 잠금 밖에서 바꾼다 — 창 스레드가 닫힘 처리로 잠금을 기다리면 서로 막힌다
        self._set_on_top(window, on_top)
        return '항상 위에 표시합니다.' if on_top else '항상 위 표시를 껐습니다.'

    @staticmethod
    def _set_on_top(window, on_top: bool):
        """🚨 `window.on_top = …` 은 WinForms `TopMost` 를 **부른 스레드에서** 바로 바꾼다.
        화면 버튼(JS 연결 스레드)에서 그렇게 하면 창이 먹통이 된다 (2026-10-08 확인).
        그래서 창 자신의 UI 스레드로 넘겨 바꾼다."""
        try:
            from webview.platforms.winforms import BrowserView
            from System import Func, Type
        except ImportError:                       # 다른 GUI 백엔드 — pywebview 에 맡긴다
            window.on_top = on_top
            return
        form = BrowserView.instances.get(window.uid)
        if form is None:
            raise ValueError('메모 창이 열려 있지 않습니다.')

        def apply():
            form.TopMost = on_top
        form.BeginInvoke(Func[Type](apply))

    @staticmethod
    def _open_link(payload):
        """메모 속 웹 주소를 기본 브라우저로 연다. http·https 주소만 — 파일·프로그램은 열지 않는다."""
        url = payload.get('url')
        if not isinstance(url, str) or not url or len(url) > 2000:
            raise ValueError('열 수 없는 주소입니다.')
        if url.lower().startswith('www.'):
            url = 'https://' + url
        if not re.fullmatch(r'https?://[^\s<>"]+', url, re.IGNORECASE):
            raise ValueError('웹 주소(http·https)만 열 수 있습니다.')
        import webbrowser
        if not webbrowser.open(url, new=2):
            raise RuntimeError('브라우저를 열지 못했습니다. 기본 브라우저 설정을 확인해 주세요.')
        return None

    def _sticky_resize(self, payload):
        """제목 표시줄이 없는 메모 창의 크기를 바꾼다 (오른쪽 아래 손잡이)."""
        try:
            width, height = int(payload['width']), int(payload['height'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('메모 창 크기 형식이 올바르지 않습니다.') from None
        width, height = min(max(width, 220), 2000), min(max(height, 200), 2000)
        with self._lock:
            window = self._sticky_windows.get(payload.get('id'))
        if window is None:
            raise LookupError('메모 창이 열려 있지 않습니다.')
        window.resize(width, height)
        return None

    @staticmethod
    def _round_corners(window):
        """제목 표시줄 없는 창도 Windows 11 처럼 모서리를 둥글게 (그 전 Windows 에서는 아무 일도 없다)."""
        form = DesktopAPI._dock_form(window)
        if form is None:
            return

        def apply():
            DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, ctypes.c_int(2)
            _dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(form.Handle.ToInt64()), DWMWA_WINDOW_CORNER_PREFERENCE,
                                          ctypes.byref(DWMWCP_ROUND), ctypes.sizeof(DWMWCP_ROUND))
        on_ui(form, apply)

    def _sticky_open(self, payload):
        """메모 하나를 작은 창으로 띄운다. 이미 떠 있으면 앞으로 가져온다."""
        note = sticky.get(payload)            # 내 스티커 보드의 메모인지 먼저 확인한다
        note_id = note['id']
        import webview
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            if note_id in self._sticky_windows:
                window = self._sticky_windows[note_id]
                window.show()
                window.restore()
                return '메모 창을 앞으로 가져왔습니다.'
            if len(self._sticky_windows) >= STICKY_LIMIT:
                raise RuntimeError(f'메모 창은 {STICKY_LIMIT}개까지 띄울 수 있습니다. 안 쓰는 창을 닫아 주세요.')
            place = self._sticky_layout.setdefault(note_id, {})
            place['open'] = True
            on_top = bool(place.get('top'))
            window = webview.create_window(
                note.get('title') or '메모', str(Path(__file__).parent / 'web' / 'sticky.html'),
                js_api=self, width=int(place.get('w') or STICKY_SIZE[0]),
                height=int(place.get('h') or STICKY_SIZE[1]), x=place.get('x'), y=place.get('y'),
                min_size=(220, 200), on_top=on_top, background_color='#fff176', text_select=True,
                # 제목 표시줄을 없앤다 (2026-10-11 요청). 끌기는 메모 위쪽 막대(sticky.html 의
                # pywebview-drag-region), 닫기는 막대의 X, 크기는 오른쪽 아래 손잡이가 맡는다.
                frameless=True, easy_drag=False)
            self._sticky_windows[note_id] = window
            self._save_sticky_layout()

        def loaded(made=window):
            self._round_corners(made)
            made.run_js('window.deskSticky && window.deskSticky.open(%s, %s)'
                        % (json.dumps(note_id), json.dumps(on_top)))

        def moved(x, y):
            place.update(x=x, y=y)

        def resized(w, h):
            place.update(w=w, h=h)

        def closed(made=window):
            with self._lock:
                if self._sticky_windows.get(note_id) is made:
                    self._sticky_windows.pop(note_id, None)
                if not self._shutdown.is_set():
                    # 사용자가 직접 닫았다 — 다음 실행에는 다시 띄우지 않는다
                    place.pop('open', None)
                self._save_sticky_layout()

        window.events.loaded += loaded
        window.events.moved += moved
        window.events.resized += resized
        window.events.closed += closed
        return '메모 창을 열었습니다.'

    def _show_notes(self, _):
        self._show_desk()
        if self._desk_window:
            self._desk_window.run_js("window.deskNavigate && window.deskNavigate('notes')")
        return '메모 목록을 열었습니다.'

    def _sticky_restore(self):
        """지난번에 열어 두었던 메모 창을 다시 띄운다 (계정이 연결돼 있을 때만)."""
        if not supa_auth.whoami():
            return
        for note_id, place in list(self._sticky_layout.items()):
            if not place.get('open'):
                continue
            try:
                self._sticky_open({'id': note_id})
            except LookupError:               # 웹에서 지운 메모
                with self._lock:
                    self._sticky_layout.pop(note_id, None)
                    self._save_sticky_layout()
            except Exception as exc:
                self._log('메모 창을 다시 열지 못했습니다:', exc)
                return

    # ── 캡처 ───────────────────────────────────────────────────
    # 영역 고르기는 Windows 캡처 화면에 맡기고, 그림은 보관함 폴더에 파일로 쌓는다
    # (core/capture.py). 보관함 창(web/captures.html)에서 끌어 놓기·열기·이름 바꾸기·지우기.
    def _capture_start(self, _):
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            waiting = bool(self._capture_job and self._capture_job.is_alive())
            if not waiting:
                self._capture_job = threading.Thread(target=self._capture_wait, daemon=True,
                                                     name='desk-capture')
                self._capture_job.start()
        if waiting:
            os.startfile('ms-screenclip:')     # 이미 기다리는 중 — 캡처 화면만 다시 띄운다
        return '캡처할 영역을 골라 주세요.'

    def _capture_wait(self):
        try:
            path = capture.snip(CAPTURE_DIR, self._shutdown)
        except Exception as exc:
            self._log('캡처하지 못했습니다:', exc)
            return
        if path is None:
            self._log('캡처를 취소했습니다.')
            return
        self._log(f'캡처를 보관함에 담았습니다: {path.name}')
        # 캡처 화면이 닫히면 Windows 가 앞 창에 포커스를 돌려주며 그 창을 맨 위로 올린다.
        # 보관함을 그 뒤에 띄워야 가려지지 않는다 (2026-10-11 확인).
        capture.wait_closed()
        with self._lock:
            self._capture_fresh = path.name
        try:
            self._captures_show({})
        except Exception as exc:
            self._log('캡처 보관함을 열지 못했습니다:', exc)

    def _captures_show(self, _):
        """캡처 보관함을 보인다. 독이 떠 있으면 독의 캡처 보관함 아이콘 위 패널로, 아니면 제 창으로.
        막 찍은 캡처가 있으면 그것을 골라 보여 준다."""
        with self._lock:
            dock = self._dock_window if self.dock_enabled else None
        if dock is not None:
            try:
                # run_js 는 결과를 돌려준다는 보장이 없다 — 열었는지 알아야 하므로 evaluate_js
                if dock.evaluate_js('window.deskDock ? window.deskDock.openPop("captures") : false'):
                    return '캡처 보관함을 열었습니다.'
            except Exception:
                pass                                # 독이 답하지 못하면 제 창으로
        import webview
        with self._lock:
            if self._shutdown.is_set():
                raise RuntimeError('프로그램을 종료하는 중입니다.')
            window = self._capture_window
            created = window is None
            if created:
                window = webview.create_window(
                    '캡처 보관함 · 스페이스기전 데스크', str(WEB_DIR / 'captures.html'),
                    js_api=self, width=860, height=640, min_size=(480, 380),
                    background_color='#f6f7fb')
                self._capture_window = window
        if created:
            def closed(made=window):
                with self._lock:
                    if self._capture_window is made:
                        self._capture_window = None
            window.events.closed += closed
            self._front_when_loaded(window)
            return '캡처 보관함을 열었습니다.'
        window.show()
        window.restore()
        self._bring_front(window)
        window.run_js('window.deskCaptures && window.deskCaptures.reload()')
        return '캡처 보관함을 열었습니다.'

    def _capture_list(self, payload):
        """보관함 목록. 화면이 가진 것과 같으면(signature) 목록을 다시 보내지 않는다."""
        signature = capture.signature(CAPTURE_DIR)
        with self._lock:
            fresh, self._capture_fresh = self._capture_fresh, None
        if not fresh and payload.get('signature') == signature:
            return {'same': True}
        return {'signature': signature, 'fresh': fresh, 'folder': str(CAPTURE_DIR),
                'items': capture.items(CAPTURE_DIR)}

    @staticmethod
    def _capture_names(payload):
        names = payload.get('names')
        if not isinstance(names, list) or not names or len(names) > CAPTURE_PICK:
            raise ValueError('고른 캡처가 올바르지 않습니다.')
        return [capture.resolve(CAPTURE_DIR, name) for name in names]

    def _capture_open(self, payload):
        """기본 프로그램(사진 앱 등)으로 연다 — 파일을 두 번 누른 것과 같다."""
        path = capture.resolve(CAPTURE_DIR, payload.get('name'))
        os.startfile(str(path))
        return f'{path.name} 파일을 열었습니다.'

    def _capture_reveal(self, payload):
        path = capture.resolve(CAPTURE_DIR, payload.get('name'))
        subprocess.Popen(['explorer', f'/select,{path}'])
        return '파일 탐색기에서 보여 줍니다.'

    def _capture_folder(self, _):
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(CAPTURE_DIR))
        return '캡처 폴더를 열었습니다.'

    def _capture_rename(self, payload):
        path = capture.rename(CAPTURE_DIR, payload.get('name'), payload.get('to'))
        desk_message.renamed(payload.get('name'), path.name)     # 메시지 사진이면 대화가 새 이름을 따라간다
        self._log(f'캡처 이름을 바꿨습니다: {path.name}')
        return {'name': path.name}

    def _capture_delete(self, payload):
        paths = self._capture_names(payload)
        capture.recycle(paths)
        self._log(f'캡처 {len(paths)}개를 휴지통으로 옮겼습니다.')
        return f'{len(paths)}개를 휴지통으로 옮겼습니다. 휴지통에서 되살릴 수 있습니다.'

    def _on_capture_ui(self, work):
        """보관함을 보이는 창의 UI 스레드에서 돌린다. 클립보드·끌기는 그 스레드(STA)에서만 된다.
        독 위 패널이 캡처 보관함을 보이고 있으면 그 패널 창, 아니면 캡처 보관함 창."""
        with self._lock:
            request = self._popover_request or {}
            window = (self._popover_window if request.get('key') == 'captures' and self._popover_window
                      else self._capture_window)
        if window is None or 'webview.platforms.winforms' not in sys.modules:
            raise RuntimeError('캡처 보관함 창이 열려 있지 않습니다.')
        try:
            from webview.platforms.winforms import BrowserView
        except ImportError:
            raise RuntimeError('이 화면에서는 지원하지 않습니다.') from None
        form = BrowserView.instances.get(window.uid)
        if form is None:
            raise RuntimeError('캡처 보관함 창이 열려 있지 않습니다.')
        on_ui(form, lambda: work(form), self._log)

    @staticmethod
    def _file_list(paths):
        from System.Collections.Specialized import StringCollection
        files = StringCollection()
        for path in paths:
            files.Add(str(path))
        return files

    def _capture_copy(self, payload):
        """그림과 파일을 함께 클립보드에 — 그림판·한글에는 그림으로, 탐색기에는 파일로 붙는다."""
        paths = self._capture_names(payload)

        def work(_form):
            from System.Drawing import Bitmap
            from System.Windows.Forms import Clipboard, DataObject
            data = DataObject()
            data.SetFileDropList(self._file_list(paths))
            if len(paths) == 1:
                source = Bitmap(str(paths[0]))          # 파일을 잡지 않게 복사본을 넘긴다
                data.SetImage(Bitmap(source))
                source.Dispose()
            Clipboard.SetDataObject(data, True)
        self._on_capture_ui(work)
        return '복사했습니다. 원하는 곳에 붙여 넣으세요.' if len(paths) == 1 else f'{len(paths)}개를 복사했습니다.'

    def _capture_drag(self, payload):
        """Windows 파일 끌기를 시작한다 — 탐색기·메신저·메일에 파일을 놓듯이 놓을 수 있다.

        화면(JS)이 단추를 누른 채 움직이는 것을 보고 부른다. 단추를 누르고 있는 동안
        시작해야 하므로 기다리지 않고 바로 넘긴다. 복사로만 넘겨 보관함의 원본은 남는다."""
        paths = self._capture_names(payload)

        def work(form):
            from System.Windows.Forms import DataObject, DragDropEffects
            data = DataObject()
            data.SetFileDropList(self._file_list(paths))
            form.DoDragDrop(data, DragDropEffects.Copy)
        self._on_capture_ui(work)

    def _prepare_cm(self, payload):
        from core import cm_launcher
        restart = payload.get('restart', False)
        if not isinstance(restart, bool):
            raise ValueError('쿨메신저 연결 요청 형식이 올바르지 않습니다.')
        result = cm_launcher.prepare(restart=restart)
        self._log('쿨메신저:', result['message'])
        return result

    def _check_cm(self, _):
        if not cm.pid():
            message = '쿨메신저가 실행 중이 아닙니다. ‘쿨메신저 연결’을 눌러 주세요.'
        elif not cm.main_window():
            message = '쿨메신저 로그인 상태를 확인해 주세요.'
        else:
            count = len(cm.org_tree())
            from core import cdp
            try:
                cdp.targets()
                message = f'정상 연결 · 조직도 {count}개'
            except Exception:
                message = '쪽지 확인은 가능하지만 답장 연동 준비가 필요합니다. ‘쿨메신저 연결’을 눌러 주세요.'
        self._log('쿨메신저:', message)
        return message


def main():
    if edition.STUDENT:
        return main_student()
    import webview
    api = DesktopAPI()
    try:
        if api._update_at_start(sys.argv[1:]):
            return                     # 받아 둔 새 판으로 바꾸고 새 판을 띄웠다 — 이것은 끝낸다
    except Exception as exc:
        api._log('업데이트를 적용하지 못했습니다:', exc)
    install_web_hooks(api._open_popup, api._log)
    # 고친 화면 파일이 옛 사본에 가려지지 않게 한다 (core/web_cache.py 참고)
    web_cache.install()
    web_cache.purge_stale(Path(watcher.DATA_DIR) / 'webview-profile', api._log)
    try:
        startup.refresh_registration()
    except (OSError, ValueError) as exc:
        api._log('자동 실행 경로 갱신 실패:', exc)
    api._start_supervisor()
    api._start_term_restore()          # 지난번에 켜 둔 에이전트 터미널을 그 대화로 다시 연다 (화면이 뜬 뒤)
    api._start_dash_prefetch()         # 학교 정보를 미리 받아 둔다 — 패널·업무 홈이 바로 뜨게
    api._start_realtime()              # 새 메시지를 바로 (자리에 있을 때만 연결)
    try:
        api._start_clips()             # 복사한 것을 모아 둔다 (독의 클립보드 패널)
    except Exception as exc:
        api._log('클립보드 기록을 시작하지 못했습니다:', exc)
    try:
        api._start_hotkey()            # 가려진 독을 부르는 단축키 (기본 Ctrl+Alt+D)
    except Exception as exc:
        api._log('독 단축키를 켜지 못했습니다:', exc)
    try:
        api._start_foreground()        # 에이전트 터미널이 '지금 보던 창'을 알도록
    except Exception as exc:
        api._log('앞 창 지켜보기를 시작하지 못했습니다:', exc)
    try:
        api._start_updates()           # 새 판을 뒤에서 받아 둔다 (core/updater.py)
    except Exception as exc:
        api._log('자동 업데이트를 시작하지 못했습니다:', exc)
    threading.Thread(target=api._retire_kakao_safely, daemon=True, name='desk-kakao-retire').start()   # 걷어낸 카카오톡 기능의 흔적 (2026-11-08)
    # 켤 때는 **독만** 띄운다 — 데스크 본창은 독의 '데스크'·트레이의 '데스크 열기'로 연다 (2026-10-25 요청:
    # 손으로 업데이트한 뒤처럼 인자 없이 켜지면 본창이 떴다). 자동 실행(--autostart)은 독을 켜 둔 대로,
    # `--desk` 로 켜면 본창도 보인다 (개발·점검용).
    desk_launch = '--desk' in sys.argv
    dock_launch = not desk_launch and '--autostart' not in sys.argv
    if dock_launch and not api.dock_enabled:
        api.dock_enabled = True
        api._save_preferences(dock=True)
    window = webview.create_window('스페이스기전 데스크',
                                  str(WEB_DIR / 'index.html'),
                                  js_api=api, width=1180, height=820, min_size=(860, 620),
                                  background_color='#f6f7fb', text_select=True,
                                  hidden=not desk_launch)
    api._desk_window = window
    tray = None
    quitting = threading.Event()

    def quit_app(*_):
        quitting.set()
        api._exit_if_stuck()               # 화면 쪽이 멈춰 있어도 «종료»는 끝난다
        api._close()
        if tray:
            tray.stop()
        window.destroy()
    api._quit_for_update = quit_app

    def show(*_):
        window.show()
        window.restore()

    try:
        import pystray
        from PIL import Image
        with Image.open(Path(__file__).parent / 'resources' / 'desk.ico') as source:
            icon = source.convert('RGBA')
        tray = pystray.Icon('spacekijun-desk', icon, f'스페이스기전 데스크 {edition.DESK_VERSION}',
                           # 트레이 아이콘을 누르면 데스크가 아니라 **독(위젯)**이 앞으로 온다 (2026-10-13 요청).
                           # 꺼져 있었으면 켠다 — 단축키와 같다. 데스크 본창은 메뉴의 '데스크 열기'로.
                           # 메뉴 동작은 따로 돌린다 — 화면 쪽이 멈춰도 트레이가 먹통이 되지 않게 (2026-10-19)
                           pystray.Menu(pystray.MenuItem(lambda _: '독 보이기' + (f' ({api.hotkey_label()})' if api.hotkey_label() else ''),
                                                         api._in_background(api._hotkey_pressed), default=True),
                                        pystray.MenuItem('데스크 열기', api._in_background(show)),
                                        pystray.MenuItem('독 표시',
                                                         api._in_background(lambda: api.set_dock(not api.dock_enabled)),
                                                         checked=lambda _: api.dock_enabled),
                                        pystray.MenuItem('화면 캡처', api._in_background(lambda: api.call('capture'))),
                                        pystray.MenuItem('캡처 보관함', api._in_background(lambda: api.call('captures'))),
                                        pystray.Menu.SEPARATOR,
                                        pystray.MenuItem(lambda _: f'지금 업데이트 ({api._update["version"]})' if api._update
                                                         else '업데이트 확인', api._in_background(api._tray_update)),
                                        pystray.MenuItem('종료', api._in_background(quit_app))))
        api._desk_tray = tray
        threading.Thread(target=tray.run, daemon=True).start()
        if '--after-update' in sys.argv:
            def updated():
                try:
                    tray.notify(f'{edition.DESK_VERSION} 판으로 업데이트했습니다.', '스페이스기전 데스크')
                except Exception:
                    pass
            threading.Timer(4, updated).start()
    except ImportError:
        api._log('트레이 모듈이 없어 창을 닫으면 종료합니다.')

    def closing():
        if tray and not quitting.is_set():
            window.hide()
            api._log('트레이에서 계속 실행 중입니다. 완전히 끝내려면 트레이 메뉴에서 종료하세요.')
            return False
        api._close()

    window.events.closing += closing
    window.events.loaded += api._ui_seen           # 독을 꺼 둔 PC 는 데스크 창이 그려진 것으로 본다
    api._watch_startup(45, DEBUG_PORT)
    try:
        # 🚨 이 포트로 Playwright 가 **데스크 안 창**에 붙는다. 그래야 업무시스템을
        #    프로그램 안에서 열면서도 나이스 도우미를 쓸 수 있다 (2026-09-15 확인).
        #    127.0.0.1 에만 열리고, 프로그램이 꺼지면 함께 닫힌다.
        webview.settings['REMOTE_DEBUGGING_PORT'] = DEBUG_PORT
        def started():
            if tray is None:
                window.show()
            if api.dock_enabled:
                api._show_dock()
                api._popover_prewarm()     # 독 위 패널 창도 미리 — 처음 누를 때 기다리지 않게
            api._sticky_restore()         # 지난번에 열어 둔 메모 창을 다시 띄운다
        webview.start(started,
                      gui='edgechromium', private_mode=False, http_port=web_port(WEB_PORT['teacher']),
                      storage_path=str(Path(watcher.DATA_DIR) / 'webview-profile'),
                      icon=str(Path(__file__).parent / 'resources' / 'desk.ico'))
    finally:
        api._close()
        if tray:
            tray.stop()


def main_student():
    """학생판 — 데스크 본창 없이 **독이 곧 프로그램**이다. 교사판의 쪽지 감시·나이스 도우미 통로는 켜지 않는다."""
    import webview
    api = DesktopAPI()
    try:
        if api._update_at_start(sys.argv[1:]):
            return                     # 받아 둔 새 판으로 바꾸고 새 판을 띄웠다 — 이것은 끝낸다
    except Exception as exc:
        api._log('업데이트를 적용하지 못했습니다:', exc)
    install_web_hooks(api._open_popup, api._log)        # 스페이스기전·시트온이 연 창은 프로그램 안으로
    web_cache.install()
    web_cache.purge_stale(Path(watcher.DATA_DIR) / 'webview-profile', api._log)
    try:
        # 학생판은 Windows 자동 실행이 기본 (2026-10-16 요청) — 처음 켤 때 켜 두고, 설정에서 끈 것은 그대로
        if startup.ensure_default(api._read_preferences().get('startup')):
            api._save_preferences(startup=True)
        startup.refresh_registration()
    except (OSError, ValueError) as exc:
        api._log('자동 실행 경로 갱신 실패:', exc)
    api._start_dash_prefetch()                          # 시간표·일정 (학생 계정을 연결했을 때)
    api._start_realtime()                               # 새 메시지를 바로 (자리에 있을 때만 연결)
    for start, what in ((api._start_clips, '클립보드 기록'), (api._start_hotkey, '독 단축키'),
                        (api._start_foreground, '앞 창 지켜보기'), (api._start_updates, '자동 업데이트')):
        try:
            start()
        except Exception as exc:
            api._log(f'{what}을 시작하지 못했습니다:', exc)
    api.dock_enabled = True
    api._show_dock()                                    # 첫 창 — pywebview 는 창이 하나 있어야 시작한다
    tray = None
    quitting = threading.Event()

    def quit_app(*_):
        quitting.set()
        api._exit_if_stuck()                            # 화면 쪽이 멈춰 있어도 «종료»는 끝난다
        api._close()                                    # 독·패널·창을 모두 닫는다
        if tray:
            tray.stop()
    api._quit_for_update = quit_app

    try:
        import pystray
        from PIL import Image
        with Image.open(Path(__file__).parent / 'resources' / 'desk.ico') as source:
            icon = source.convert('RGBA')
        tray = pystray.Icon('spacekijun-student', icon, f'{edition.TITLE} {edition.VERSION}',
                            pystray.Menu(pystray.MenuItem(lambda _: '독 앞으로 가져오기' + (f' ({api.hotkey_label()})' if api.hotkey_label() else ''),
                                                          api._in_background(api.dock_front), default=True),
                                         pystray.MenuItem('화면 캡처', api._in_background(lambda: api.call('capture'))),
                                         pystray.Menu.SEPARATOR,
                                         pystray.MenuItem(lambda _: f'지금 업데이트 ({api._update["version"]})' if api._update
                                                          else '업데이트 확인', api._in_background(api._tray_update)),
                                         pystray.MenuItem('종료', api._in_background(quit_app))))
        threading.Thread(target=tray.run, daemon=True).start()
        api._tray = tray
    except ImportError:
        api._log('트레이 모듈이 없습니다.')
    # 원격 디버깅 통로는 개발할 때만 (학생 PC 에서는 열지 않는다)
    port = os.environ.get('SPACEKIJUN_DEBUG_PORT', '').strip()
    if port.isdigit():
        webview.settings['REMOTE_DEBUGGING_PORT'] = int(port)
    api._watch_startup(45)
    try:
        webview.start(lambda: api._popover_prewarm(),
                      gui='edgechromium', private_mode=False, http_port=web_port(WEB_PORT['student']),
                      storage_path=str(Path(watcher.DATA_DIR) / 'webview-profile'),
                      icon=str(Path(__file__).parent / 'resources' / 'desk.ico'))
    finally:
        api._close()
        if tray:
            tray.stop()


if __name__ == '__main__':
    main()
