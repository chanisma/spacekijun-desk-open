"""교실판 — 교사가 승인한 세팅을 독에 놓고, 누르면 연다. 수업이 끝나면 걷어 낸다.

2026-10-13 사용자 결정: «세팅된다» = 자동 실행이 아니라 **독(아이콘 줄)에 놓여 쉽게 열 수 있는 것**.
승인되어도 아무것도 저절로 열지 않는다.

세팅 항목 네 가지 (SPACEKIJUN `src/features/classroom-link/presetItems.ts` 와 같은 규칙):
  drive    드라이브 폴더 → 프로그램 안 탐색기를 그 폴더로 연다(classroom-drive.html).
           드라이브 파일 → 받아 열고, 저장하면 드라이브에 되올린다(core/classroom_drive.py).
           독에는 이와 별개로 «내 드라이브»가 늘 있다(드라이브를 연결했을 때).
  url      웹사이트. **이번 수업 전용 Edge 프로필**(빈 임시 폴더)로 연다 — 거기서 누가 로그인해도
           수업이 끝나면 프로필째 지운다.
  program  이름(허용 목록)으로만 실행한다. 서버는 실행 파일 경로를 모른다 — 교사 계정 하나가 털려도
           교실 PC 에서 아무 프로그램이나 돌리지 못하게. 목록 밖은 이 기기 관리자가 classroom.json 에
           등록한 것만.
  space    스페이스기전 화면 — 교실판 창이 직접 연다(classroom.py, 받은 세션을 심는다).

구글 웹(클래스룸·슬라이드·폼)은 독의 «구글»로 수업용 Edge 에서 선생님이 직접 로그인한다(이메일은 채워 둔다).
A+(2026-10-14): 그 Edge 프로필을 수업이 끝날 때 암호화해 이 PC 에 남기고(core/classroom_vault.py), 열쇠는 서버가
QR 승인 때만 넘긴다 — 같은 PC 의 다음 수업엔 로그인된 채. 승인 화면에서 끄면 보관하지 않는다.

🚨 이 파일의 PROGRAMS 키는 웹의 CLASSROOM_PROGRAMS 와 같아야 한다(spacekijun scripts/classroom-link-test).
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import threading
import time
import uuid

from . import classroom_icons as icons
from . import classroom_vault as vault
from .classroom_drive import FOLDER, DriveError, PcShelf, Workspace, has_unsent, send_unsent
from .classroom_link import DATA_DIR, load_settings

SESSIONS_DIR = os.path.join(DATA_DIR, 'sessions')
NO_WINDOW = 0x08000000
FULL_DRIVE = 'https://www.googleapis.com/auth/drive'

# 키 → (보여 줄 이름, 찾는 방법들). 방법: ('app', 'POWERPNT.EXE') = 레지스트리 App Paths,
# ('glob', 패턴) = 설치 폴더 검색, ('exe', 'notepad.exe') = Windows 기본 프로그램, ('uri', 'ms-…:') = 앱 주소
PROGRAMS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    'powerpoint': ('PowerPoint', [('app', 'POWERPNT.EXE')]),
    'word': ('Word', [('app', 'WINWORD.EXE')]),
    'excel': ('Excel', [('app', 'EXCEL.EXE')]),
    'hwp': ('한글', [('app', 'Hwp.exe'),
                    ('glob', r'%ProgramFiles(x86)%\HNC\Office*\HOffice*\Bin\Hwp.exe'),
                    ('glob', r'%ProgramFiles%\HNC\Office*\HOffice*\Bin\Hwp.exe'),
                    ('glob', r'%ProgramFiles(x86)%\Hnc\Office*\HOffice*\Bin\Hwp.exe')]),
    'whiteboard': ('Microsoft Whiteboard', [('uri', 'ms-whiteboard-cmd:')]),
    'notepad': ('메모장', [('exe', 'notepad.exe')]),
    'paint': ('그림판', [('exe', 'mspaint.exe')]),
    'calculator': ('계산기', [('exe', 'calc.exe')]),
    'snipping': ('캡처 도구', [('uri', 'ms-screenclip:')]),
    'osk': ('화상 키보드', [('exe', 'osk.exe')]),
}


# 구글 앱 — 독의 «구글» 창(classroom-google.html)과 세팅의 구글 앱 타일. 키는 웹 GOOGLE_APPS 와 같아야 한다
# (spacekijun scripts/classroom-link-test). 수업용 Edge(구글 로그인 보관 A+)에서 `authuser=선생님 이메일` 로 연다.
GOOGLE_APPS: dict[str, tuple[str, str]] = {
    'classroom': ('클래스룸', 'https://classroom.google.com/'),
    'drive': ('드라이브(웹)', 'https://drive.google.com/'),
    'docs': ('문서', 'https://docs.google.com/document/'),
    'sheets': ('시트', 'https://docs.google.com/spreadsheets/'),
    'slides': ('슬라이드', 'https://docs.google.com/presentation/'),
    'forms': ('설문지', 'https://docs.google.com/forms/'),
    'calendar': ('캘린더', 'https://calendar.google.com/'),
    'meet': ('Meet', 'https://meet.google.com/'),
    'gmail': ('Gmail', 'https://mail.google.com/'),
    'keep': ('Keep', 'https://keep.google.com/'),
    'sites': ('사이트', 'https://sites.google.com/'),
    'youtube': ('YouTube', 'https://www.youtube.com/'),
}


class SetupError(RuntimeError):
    pass


# ── 프로그램 찾기 ─────────────────────────────────────────────
def _app_path(exe: str) -> str | None:
    import winreg
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths' + '\\' + exe) as k:
                value = winreg.QueryValue(k, None)
        except OSError:
            continue
        value = os.path.expandvars(value.strip('"'))
        if os.path.isfile(value):
            return value
    return None


def resolve_program(key: str, settings: dict | None = None) -> tuple[str, list[str] | str] | None:
    """→ (이름, 명령 목록) 또는 (이름, 'uri:…'). 이 PC 에 없으면 None."""
    custom = ((settings if settings is not None else load_settings()).get('programs') or {}).get(key)
    if isinstance(custom, dict) and custom.get('path'):
        path = os.path.expandvars(str(custom['path']))
        return (str(custom.get('label') or key), [path]) if os.path.isfile(path) else None
    known = PROGRAMS.get(key)
    if not known:
        return None
    label, ways = known
    for how, what in ways:
        if how == 'app':
            path = _app_path(what)
            if path:
                return label, [path]
        elif how == 'glob':
            hits = sorted(glob.glob(os.path.expandvars(what)))
            if hits:
                return label, [hits[-1]]
        elif how == 'exe':
            path = shutil.which(what)
            if path:
                return label, [path]
        elif how == 'uri':
            return label, 'uri:' + what
    return None


def find_edge() -> str | None:
    path = _app_path('msedge.exe')
    if path:
        return path
    for base in ('%ProgramFiles(x86)%', '%ProgramFiles%'):
        candidate = os.path.expandvars(base + r'\Microsoft\Edge\Application\msedge.exe')
        if os.path.isfile(candidate):
            return candidate
    return None


# ── 한 번의 수업 ─────────────────────────────────────────────
class Session:
    """승인 한 건 = 수업 한 번. 연 것을 기억했다가 end() 에서 걷어 낸다.

    open_space(path, session) 은 교실판 창이 넘겨 준다(스페이스기전 화면을 프로그램 안 창으로).
    close_space() 는 그 창들을 닫는다.
    """

    def __init__(self, handoff: dict, *, open_space=None, close_space=None, settings: dict | None = None,
                 drive_opener=None, popen=subprocess.Popen, startfile=None, edge=None, clock=time.time):
        preset = handoff.get('preset') or {}
        self.teacher = handoff.get('teacher') or {}
        self.title = str(preset.get('title') or '')
        self.section = preset.get('section_name')
        self.items = [dict(item) for item in (preset.get('items') or []) if isinstance(item, dict)]
        self.status = [{'state': 'idle', 'message': ''} for _ in self.items]
        self._google = None
        self.google_expires = None
        self.google_scope = ''
        self.update_google(handoff.get('google'))
        self._space = handoff.get('space_session')
        profile = handoff.get('profile')
        self.profile = profile if isinstance(profile, dict) and vault.REF.match(str(profile.get('ref') or ''))             and profile.get('key') else None          # 구글 로그인 보관 열쇠(A+). None = 보관하지 않는다
        self.google_restored = False
        # 구글 로그인 상태(구글 창에 보인다) — restored(보관본에 로그인 있음) · restored_empty(보관본에 로그인 없음)
        # · none · cleared(지웠다) · phone(휴대폰으로 넣었다). 끝날 때 보관한 결과는 end_login(saved · empty · failed · off)
        self.login = 'none'
        self.end_login = None
        self.settings = settings if settings is not None else load_settings()
        self.dir = os.path.join(SESSIONS_DIR, uuid.uuid4().hex[:12])
        self.edge_profile = os.path.join(self.dir, 'edge-profile')
        self.popen = popen
        self.startfile = startfile or getattr(os, 'startfile', None)
        self.edge = edge if edge is not None else find_edge()
        self.open_space = open_space
        self.close_space = close_space
        self.clock = clock
        self.launched: list = []
        self.lock = threading.RLock()
        kw = {'startfile': self.startfile, 'clock': clock}
        if drive_opener:
            kw['opener'] = drive_opener
        self.workspace = Workspace(os.path.join(self.dir, 'drive'), self.google_token, **kw)
        self.shelf = PcShelf(self.email, startfile=self.startfile, clock=clock)   # 이 PC 에 복사해 둔 것(수업을 넘어 남는다)
        self.notice = ''
        self.icons: list[str | None] = [None] * len(self.items)   # 독 타일의 실제 아이콘(data URI 또는 web/ 안 경로)
        self.icons_version = 0
        self.copied = 0                    # «컴퓨터로 복사»·«이 PC 에 저장» 한 파일 수 — 수업이 끝나도 남는다
        self.copied_places: list[str] = []

    @property
    def space_session(self):
        return self._space

    @property
    def email(self) -> str:
        return str(self.teacher.get('email') or '')

    # 드라이브 연결 ------------------------------------------------------------
    def update_google(self, google):
        """승인·다시 연결 때 받은 구글 토큰으로 바꾼다."""
        if not isinstance(google, dict) or not google.get('access_token'):
            return
        with getattr(self, 'lock', threading.RLock()):
            self._google = google['access_token']
            self.google_expires = float(google.get('expires_at') or 0) or None
            self.google_scope = str(google.get('scope') or FULL_DRIVE)

    def google_token(self) -> str | None:
        if not self._google:
            return None
        if self.google_expires and time.time() >= self.google_expires - 30:
            return None
        return self._google

    def drive_state(self) -> dict:
        left = int(self.google_expires - time.time()) if self._google and self.google_expires else None
        connected = self.google_token() is not None
        return {'connected': connected, 'left': left if connected else 0, 'ever': self._google is not None,
                'full': FULL_DRIVE in self.google_scope.split()}

    def prepare(self):
        os.makedirs(self.dir, exist_ok=True)
        threading.Thread(target=self._load_icons, daemon=True, name='classroom-icons').start()
        # 이 PC 에 보관해 둔 구글 로그인(수업용 Edge 프로필)을 푼다
        if self.profile:
            try:
                self.google_restored = vault.restore(self.profile['ref'], self.profile['key'], self.edge_profile)
            except (vault.VaultError, OSError, ValueError) as e:
                self.notice = str(e)
            if self.google_restored:
                self.login = 'restored' if vault.google_login_in(self.edge_profile) is not False else 'restored_empty'
        # 지난 수업에 못 올린 파일이 있으면 지금 올린다
        if self.google_token() and has_unsent(self.email):
            try:
                n = send_unsent(self.workspace.drive(), self.email)
                if n:
                    self.notice = f'지난 수업에 못 올린 파일 {n}개를 드라이브 «교실에서 올리지 못한 파일» 폴더에 올렸습니다.'
            except (DriveError, OSError):
                pass
        # 지난 수업에 이 PC 에 복사해 둔 것 — 어디 있는지 찾지 않게 드라이브 창에 모아 보여 준다(2026-10-15)
        if not self.notice:
            n = self.shelf.count()
            if n:
                self.notice = f'지난 수업에 이 PC 에 복사해 둔 파일 {n}개가 있습니다. «내 드라이브» 창 왼쪽 «이 PC 에 복사한 파일»에서 열 수 있습니다.'

    def record_copy(self, dest: str, count: int, paths=()):
        with self.lock:
            self.copied += count
            if dest not in self.copied_places:
                self.copied_places.append(dest)
        try:
            self.shelf.add(paths, dest)
        except OSError:
            pass

    def _icon_for(self, item: dict) -> str | None:
        kind = item.get('kind')
        if kind == 'url' and item.get('app') in GOOGLE_APPS:
            return f"icons/google/{item['app']}.png"
        if kind == 'url':
            site = str(item.get('site') or '')                 # 추천 사이트 — 받아 넣어 둔 아이콘(web/icons/sites)
            web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web', 'icons', 'sites', site + '.png')
            if site.isalnum() and os.path.exists(web):
                return f'icons/sites/{site}.png'
            return icons.favicon(str(item.get('url') or ''))
        if kind == 'drive':
            return icons.drive_type_icon(str(item.get('mimeType') or 'application/octet-stream'))
        if kind == 'space':
            return 'icons/spacekijun.png'
        if kind == 'program':
            found = resolve_program(str(item.get('program') or ''), self.settings)
            if found and not isinstance(found[1], str):
                return icons.program_icon(found[1][0])
            key = str(item.get('program') or '')
            web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web', 'icons', 'programs', key + '.png')
            return f'icons/programs/{key}.png' if os.path.exists(web) else None
        return None

    def _load_icons(self):
        """독 타일의 실제 아이콘을 뒤에서 모은다(파비콘은 인터넷, 프로그램은 설치된 실행 파일)"""
        for index, item in enumerate(self.items):
            try:
                self.icons[index] = self._icon_for(item)
            except Exception:
                self.icons[index] = None
            self.icons_version += 1

    # 누르면 연다 --------------------------------------------------------------
    def open_item(self, index: int) -> dict:
        """→ {'ok': True} 또는 {'explore': 폴더 id, 'name': …}(탐색기로) 또는 {'ok': False, 'error': …}"""
        item = self.items[index]
        self._set(index, 'opening', '')
        try:
            handler = getattr(self, '_open_' + str(item.get('kind')), self._unknown)
            result = handler(index, item) or {'ok': True}
            self._set(index, 'opened', '')
            return result
        except (SetupError, DriveError) as e:
            self._set(index, 'failed', str(e))
            return {'ok': False, 'error': str(e)}
        except Exception:
            self._set(index, 'failed', '열지 못했습니다.')
            return {'ok': False, 'error': '열지 못했습니다.'}

    def _set(self, index, state, message):
        with self.lock:
            self.status[index] = {'state': state, 'message': message}

    def _unknown(self, index, item):
        raise SetupError('이 기기가 모르는 항목입니다. 교실 프로그램을 새 판으로 바꿔 주세요.')

    def _open_drive(self, index, item):
        if (item.get('mimeType') or '') == FOLDER:
            return {'explore': item['id'], 'name': item.get('name') or '폴더'}
        if not self.google_token():
            raise SetupError('드라이브가 연결되어 있지 않습니다. 드라이브 단추에서 QR 로 다시 연결해 주세요.')
        self.workspace.open(item['id'])
        return None

    def _open_url(self, index, item):
        url = str(item.get('url') or '')
        if not re.match(r'^https?://\S+$', url):
            raise SetupError('주소가 올바르지 않습니다.')
        self._edge_open(url)
        return None

    def _edge_open(self, url: str):
        if not self.edge:
            raise SetupError('Microsoft Edge 가 없어 열 수 없습니다.')
        os.makedirs(self.edge_profile, exist_ok=True)
        # 디버깅 포트(--remote-debugging-port)를 열지 않는다 — 열면 구글이 이 Edge 의 로그인을 막는다
        # («브라우저 또는 앱이 안전하지 않을 수 있습니다», 2026-10-14 실제 확인). 휴대폰 입력은 UI Automation 으로(classroom_type.py).
        # 같은 프로필로 다시 부르면 이미 뜬 창에 탭으로 붙는다.
        self.launched.append(self.popen([
            self.edge, '--user-data-dir=' + self.edge_profile, '--no-first-run', '--no-default-browser-check',
            '--disable-sync', '--hide-crash-restore-bubble', '--start-maximized', url]))

    def edge_pids(self, process_iter=None) -> list[int]:
        """수업용 Edge 의 브라우저 프로세스(창 주인) — 이 수업 프로필로 뜬 msedge.exe 중 보조 프로세스(--type=)가 아닌 것"""
        import psutil
        profile = os.path.normcase(os.path.abspath(self.edge_profile))
        pids = []
        for proc in (process_iter or psutil.process_iter)(['pid', 'name', 'cmdline']):
            try:
                if (proc.info.get('name') or '').lower() != 'msedge.exe':
                    continue
                cmd = proc.info.get('cmdline') or []
            except Exception:
                continue
            if any(a.startswith('--type=') for a in cmd):
                continue
            if any(profile == os.path.normcase(os.path.abspath(a.split('=', 1)[1])) for a in cmd if a.startswith('--user-data-dir=')):
                pids.append(proc.info['pid'])
        return pids

    def open_google(self, login: bool = False) -> dict:
        """독의 «구글» — 수업용 Edge 에서 구글 로그인(이메일을 채워 둔다). 보관된 로그인을 풀었으면 곧장 구글로
        (로그인 화면을 열면 로그인돼 있어도 로그인 화면처럼 보인다). login=True 는 늘 로그인 화면(휴대폰으로 입력)."""
        from urllib.parse import urlencode
        try:
            if self.google_restored and not login:
                self._edge_open('https://www.google.com/')
            elif self.email:
                self._edge_open('https://accounts.google.com/ServiceLogin?' +
                                urlencode({'Email': self.email, 'continue': 'https://www.google.com/'}))
            else:
                self._edge_open('https://www.google.com/')
            return {'ok': True}
        except SetupError as e:
            return {'ok': False, 'error': str(e)}

    def open_google_app(self, key: str) -> dict:
        """구글 앱 하나를 수업용 Edge 에서 — 선생님 계정으로(authuser)"""
        from urllib.parse import urlencode
        app = GOOGLE_APPS.get(str(key))
        if not app:
            return {'ok': False, 'error': '모르는 구글 앱입니다.'}
        url = app[1] + ('?' + urlencode({'authuser': self.email}) if self.email else '')
        try:
            self._edge_open(url)
            return {'ok': True}
        except SetupError as e:
            return {'ok': False, 'error': str(e)}

    def forget_google(self):
        """이 PC 에서 이 선생님의 구글 로그인을 지운다 — 수업용 Edge 를 닫고 지금 프로필·보관 파일을 지운다.

        보관은 끄지 않는다: 지운 뒤 다시 로그인하면 수업이 끝날 때 새로 보관한다. 1.5.4 까지는 «이번 수업도 남기지 않음»이라
        지우고 다시 로그인한 것이 사라졌다(2026-10-14 사용자 보고). 보관 자체를 끄는 것은 승인 화면의 «로그인 보관»."""
        close_edge(self.edge_profile, wait=5, graceful=False)
        remove_tree(self.edge_profile)
        if self.profile:
            vault.forget(self.profile['ref'])
        self.google_restored = False
        self.login = 'cleared'

    def mark_phone_login(self):
        self.login = 'phone'

    def signed_in_email(self) -> str | None:
        """수업용 Edge 앞 탭의 구글 계정 — 이메일 · ''(로그인 안 됨) · None(모름: 구글 페이지가 앞에 없다 등)"""
        from core import classroom_type
        try:
            return classroom_type.signed_in_email(self.edge_pids())
        except Exception:
            return None

    def _open_program(self, index, item):
        found = resolve_program(str(item.get('program') or ''), self.settings)
        if not found:
            raise SetupError('이 기기에 설치되어 있지 않거나 등록되지 않은 프로그램입니다.')
        label, command = found
        if isinstance(command, str):
            if not self.startfile:
                raise SetupError('이 기기에서 열 수 없습니다.')
            self.startfile(command[len('uri:'):])
        else:
            self.launched.append(self.popen(command))
        return None

    def _open_space(self, index, item):
        if not self.open_space:
            raise SetupError('이 기기에서 스페이스기전 화면을 열 수 없습니다.')
        if not self._space:
            raise SetupError('스페이스기전 로그인 없이 승인됐습니다.')
        self.open_space(str(item.get('path') or '/'), self._space)
        return None

    # 걷어 내기 ----------------------------------------------------------------
    def end(self, wait: float = 60.0, progress=None):
        """창·프로그램을 닫고(고친 문서는 프로그램이 저장할지 묻는다), 저장된 드라이브 파일을 올리고,
        받은 파일과 임시 Edge 프로필을 지운다. 못 올린 파일은 이 PC 의 unsent/ 에 남긴다."""
        say = progress or (lambda text: None)
        if self.close_space:
            try:
                self.close_space()
            except Exception:
                pass
        say('열린 창과 프로그램을 닫는 중입니다. 저장할지 묻는 창이 뜨면 골라 주세요.')
        close_processes(self.dir, self.launched, wait=wait)
        if self.profile and os.path.isdir(self.edge_profile):
            say('구글 로그인을 이 PC 에 암호화해 보관하는 중입니다.')
            has = vault.google_login_in(self.edge_profile)          # Edge 를 닫은 뒤라 읽힌다
            try:
                vault.save(self.edge_profile, self.profile['ref'], self.profile['key'])
                self.end_login = 'empty' if has is False else 'saved'
            except (vault.VaultError, OSError, ValueError):
                self.end_login = 'failed'                  # 못 남기면 다음 수업에 다시 로그인하면 된다
        elif not self.profile and os.path.isdir(self.edge_profile):
            self.end_login = 'off'
        say('고친 파일을 드라이브에 올리는 중입니다.')
        self.workspace.sync(final=True)
        kept = self.workspace.stash_unsent(self.email)
        with self.lock:
            self._google = None
            self._space = None
        remove_tree(self.dir)
        return kept

    def snapshot(self) -> dict:
        with self.lock:
            return {
                'teacher': str(self.teacher.get('name') or ''),
                'title': self.title, 'section': self.section,
                'items': [{'kind': item.get('kind'), 'folder': (item.get('mimeType') == FOLDER),
                           'program': item.get('program'), 'mime': item.get('mimeType'),
                           'app': item.get('app') if item.get('app') in GOOGLE_APPS else None,
                           'name': item.get('name') or item.get('url') or item.get('path') or item.get('program') or '',
                           **self.status[i]} for i, item in enumerate(self.items)],
                'drive': self.drive_state(),
                'files': self.workspace.snapshot(),
                'copied': self.copied, 'copied_places': list(self.copied_places),
                'icons_version': self.icons_version,
                # saved = 이 PC 에 지울 로그인이 있다(보관을 풀었거나 이번 수업에 수업용 Edge 를 띄웠다) — 처음 쓰는 기기엔 «지우기»를 안 띄운다
                'google': {'kept': self.profile is not None, 'restored': self.google_restored, 'email': self.email,
                           'login': self.login,
                           'saved': self.profile is not None and (self.google_restored or os.path.isdir(self.edge_profile)),
                           'apps': [{'key': k, 'label': v[0]} for k, v in GOOGLE_APPS.items()]},
                'notice': self.notice,
            }


def _taskkill(pid: int, force: bool):
    # 점잖게(WM_CLOSE)는 /T 없이 — /T 를 붙이면 자식 프로세스가 있는 프로그램(Edge 는 늘)에 «/F 로 강제 종료해야 합니다»로
    # 거절된다. 그래서 1.5.3 까지 수업용 Edge 는 늘 8초 뒤 강제로 죽었고, 디스크에 아직 안 쓴 쿠키(구글이 쓰는 내내 바꾸는
    # 로그인 쿠키)를 잃어 다음 수업에 로그인이 풀렸다(2026-10-14 사용자 보고·실제 재현). 강제는 자식까지(/T /F).
    args = ['taskkill', '/PID', str(pid)] + (['/T', '/F'] if force else [])
    try:
        subprocess.run(args, capture_output=True, timeout=10, creationflags=NO_WINDOW)
    except Exception:
        pass


def close_processes(session_dir: str, launched: list, wait: float = 60.0, process_iter=None):
    """이번 수업이 띄운 것을 닫는다.

    - 수업용 Edge: 먼저 점잖게 닫아(쿠키를 디스크에 쓰게 — 구글 로그인 보관 A+) 8초 뒤 남은 것만 강제로.
    - 우리가 띄운 프로그램, 받은 파일을 연 프로그램: **점잖게** 닫는다(WM_CLOSE) — 고친 문서가 있으면
      프로그램이 «저장할까요?»를 묻는다. 강제로 죽이지 않고, 다 닫힐 때까지(최대 wait 초) 기다린다.
    """
    import psutil
    session_dir = os.path.normcase(os.path.abspath(session_dir))
    edge_pids, other_pids = set(), set()
    for proc in (process_iter or psutil.process_iter)(['pid', 'name', 'cmdline']):
        try:
            cmd = ' '.join(proc.info.get('cmdline') or [])
        except Exception:
            continue
        if session_dir in os.path.normcase(cmd):
            (edge_pids if (proc.info.get('name') or '').lower() == 'msedge.exe' else other_pids).add(proc.info['pid'])
    for p in launched:
        pid = getattr(p, 'pid', None)
        if pid and pid not in edge_pids:
            other_pids.add(pid)
    _close_edge_pids(edge_pids)
    for pid in other_pids:
        _taskkill(pid, force=False)
    deadline = time.time() + wait
    while time.time() < deadline and any(psutil.pid_exists(pid) for pid in edge_pids | other_pids):
        time.sleep(0.5)


def _close_edge_pids(pids: set, wait: float = 8.0, graceful: bool = True):
    import psutil
    if graceful:
        for pid in pids:
            _taskkill(pid, force=False)
        deadline = time.time() + wait
        while time.time() < deadline and any(psutil.pid_exists(pid) for pid in pids):
            time.sleep(0.4)
    for pid in pids:
        if psutil.pid_exists(pid):
            _taskkill(pid, force=True)


def close_edge(profile_dir: str, wait: float = 8.0, graceful: bool = True, process_iter=None):
    """그 프로필로 뜬 Edge 만 닫는다"""
    import psutil
    target = os.path.normcase(os.path.abspath(profile_dir))
    pids = set()
    for proc in (process_iter or psutil.process_iter)(['pid', 'name', 'cmdline']):
        try:
            cmd = ' '.join(proc.info.get('cmdline') or [])
        except Exception:
            continue
        if (proc.info.get('name') or '').lower() == 'msedge.exe' and target in os.path.normcase(cmd):
            pids.add(proc.info['pid'])
    _close_edge_pids(pids, wait, graceful)


def remove_tree(path: str):
    shutil.rmtree(path, ignore_errors=True)


def sweep_leftovers():
    """켤 때 — 지난번에 지우지 못한 수업 폴더를 지운다.

    프로그램이 갑자기 꺼지면(강제 종료·정전) 수업 전용 Edge 가 임시 프로필을 쥔 채 남는다 — 거기엔 누가 로그인한
    상태가 있을 수 있다. 그 프로세스들을 먼저 닫고 지운다(2026-10-13 시험 중 실제로 남았다)."""
    vault.sweep()                     # 60일 넘게 안 쓴 구글 로그인 보관
    if not os.path.isdir(SESSIONS_DIR) or not os.listdir(SESSIONS_DIR):
        return
    try:
        close_processes(SESSIONS_DIR, [], wait=10)
    except Exception:
        pass
    for name in os.listdir(SESSIONS_DIR):
        remove_tree(os.path.join(SESSIONS_DIR, name))
