"""이세계 사회인 (2026-10-19 요청) — 학생판 독의 게임을 이 PC 안에서 내주는 작은 웹 서버.

무엇을 어디서 내주나
  게임(약 5MB)   실행 파일 안 games/isekai3d/ — 학생판과 함께 자동 업데이트로 바뀐다.
                 isekai3d 저장소에서 deploy/isekai3d/sync.py 로 빌드해 app/games/isekai3d/ 에 넣는다.
  캐릭터(약 500MB) Intune 앱 «스페이스기전 학생 · 이세계 사회인 캐릭터»가 깐 폴더 (deploy/intune-isekai3d/).
                 학생판을 업데이트해도 다시 받지 않는다. 없으면 게임은 도형 캐릭터로 돈다.
  게임은 `/models/index.json` 으로 캐릭터 목록을 받는다 (isekai3d 의 src/view3d/vrm.ts).

캐릭터 팩의 형식 (2026-10-25 요청 — 학생판과 팩이 따로 업데이트되니 판이 어긋나도 돌게)
  형식 1  2026-10-20 팩: Program Files\Spacekijun Isekai3D\models, 표식 ModelsDir. 캐릭터 한 명 = 옷까지 입은 파일.
  형식 2  기본 몸(@base) + 옷만 든 파일 + 직업복. 팩 폴더(pack)에 pack.json {format, version} 이 들어 있다.
          Intune 이 깐 것 = HKLM PackDir, 구글 드라이브에서 받아 학생이 직접 깐 것 = HKCU PackDir(%LOCALAPPDATA%).
  게임이 읽는 형식은 games/isekai3d/build.json 의 modelsFormat (deploy/isekai3d/sync.py 가 isekai3d package.json 에서 적는다).
  같은 형식의 팩 가운데 가장 새 판을 내주고, 맞는 팩이 없으면 빈 목록 — 게임은 도형 캐릭터로 돌고
  `/models/pack.json` 을 보고 새 팩을 받으라고 알린다(받는 곳 = 스페이스기전 system_settings 의 구글 드라이브 링크).

스페이스기전 다리 (2026-10-19, 질문 시스템 — isekai3d docs/ref-game/08-knowledge.md §6)
  게임은 학생 세션을 모른다. POST /api/isekai3d/<일> 을 이 서버가 받아 **학생 세션 헤더를 붙여**
  정해진 RPC·엣지 함수로만 넘긴다(BRIDGE). 토큰은 게임에 주지 않는다.
  🚨 다른 웹사이트가 이 PC 의 학생 브라우저에서 localhost 로 POST 해 학생의 질문·지식을 쓰지 못하게:
     Origin 이 이 서버 주소와 같을 때만, JSON 만, CORS 머리는 내지 않는다(사전 요청 OPTIONS 는 거절).

🚨 주소(포트)를 바꾸면 안 된다 — 게임 저장(localStorage)이 주소에 묶여 있어 이전 저장이 안 보인다.
   pywebview 로컬 서버(42001)·Playwright 통로(9333·9334)·구글 로그인(8912)과 겹치지 않는 자리다.
VRoid 샘플(`-sample_`)은 자체 라이선스가 수정·재배포를 막아 목록에도 넣지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 42110
HELLO = '/__isekai3d'          # 같은 자리에 다른 프로그램이 떠 있는지 가린다
GAME_DIR = Path(__file__).resolve().parents[1] / 'games' / 'isekai3d'
PACK_KEY = r'SOFTWARE\SpacekijunIsekai3D'          # 캐릭터 팩이 남기는 표식 (형식 1: ModelsDir·Version, 형식 2: PackDir·Version)
DEFAULT_MODELS = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Spacekijun Isekai3D' / 'models'
PACK_INFO = 'pack.json'            # 형식 2 팩 폴더 안의 표식 {format, version, files}
LINK_KEY = 'isekai3d_model_download'          # 스페이스기전 system_settings — 관리자가 바꾸는 구글 드라이브 링크
DRIVE_HOSTS = {'drive.google.com', 'docs.google.com'}
# 캐릭터 파일 이름: <female|male>-<단계>-<이름>[@옷].vrm — 이 밖의 이름은 내주지 않는다
# 게임이 부르는 일 → 스페이스기전의 RPC(이름, 받는 인자) 또는 엣지 함수. 이 밖은 넘기지 않는다.
BRIDGE = {
    'status': ('rpc', 'isekai3d_status', ('p_context_key',)),
    'knowledge/get': ('rpc', 'isekai3d_knowledge_get', ()),
    'knowledge/save': ('rpc', 'isekai3d_knowledge_save', ('p_version', 'p_knowledge')),
    'memory': ('rpc', 'isekai3d_memory_set', ('p_enabled',)),
    'question/take': ('rpc', 'isekai3d_question_take', ('p_context_key',)),
    'question/answer': ('rpc', 'isekai3d_question_answer', ('p_id', 'p_choice', 'p_text')),
    'question/fill': ('fn', 'isekai3d-question', None),
    # 오락기 동전 = 하루 플레이 분량 (2026-10-20) — 첫 동전 무료, 그다음은 다마고찌·아카데미 코인, 하루 3번까지
    'play/status': ('rpc', 'isekai3d_play_status', ()),
    'play/insert': ('rpc', 'isekai3d_play_insert', ()),
    'play/use': ('rpc', 'isekai3d_play_use', ('p_used',)),
    # 저장 칸 3개를 학생 계정에도 (2026-10-20) — 게임은 이 PC에 먼저 저장하고 뒤에서 올린다
    'save/list': ('rpc', 'isekai3d_save_list', ()),
    'save/get': ('rpc', 'isekai3d_save_get', ('p_slot',)),
    'save/put': ('rpc', 'isekai3d_save_put', ('p_slot', 'p_state', 'p_summary', 'p_saved_at', 'p_base_version')),
    'save/delete': ('rpc', 'isekai3d_save_delete', ('p_slot',)),
    # 직장 에피소드 (2026-10-25) — 장면 받기(하루 2개), 결정 남기기, 다음 장면 미리 쓰기(엣지 함수, 시간이 걸린다)
    'episode/take': ('rpc', 'isekai3d_episode_take', ('p_game_key', 'p_career')),
    'episode/answer': ('rpc', 'isekai3d_episode_answer', ('p_scene_id', 'p_choice', 'p_text')),
    'episode/fill': ('fn', 'isekai3d-episode', None),
    # 주식 앱 (2026-10-26) — 실제 시세 읽기만(보유·주문은 게임 저장에). 체결 값 = 주문 뒤 처음 마감한 종가(서버가 판정)
    'stocks/market': ('rpc', 'isekai3d_stock_market', ()),
    'stocks/history': ('rpc', 'isekai3d_stock_history', ('p_asset', 'p_days')),
    'stocks/closes': ('rpc', 'isekai3d_stock_closes', ('p_asks',)),
    # 시험용 — 관리자 계정만 서버가 받아 준다(만든 질문 모두). 게임의 🛠 단추도 관리자에게만 보인다.
    'dev/questions': ('rpc', 'isekai3d_dev_questions', ('p_limit',)),
}
MAX_BODY = 80_000          # 지식 64KB + 여유
MAX_SAVE_BODY = 600_000    # 저장 올리기만 — 게임 저장 512KB 상한 + 여유
MODEL = re.compile(r'^(female|male)-(toddler|child|teen|adult|elder)-[a-z0-9_]+(@[a-z]+)?\.vrm$')


def _send(request: urllib.request.Request, timeout: float):
    """스페이스기전으로 보내기 (시험에서 갈아 끼운다)."""
    return urllib.request.urlopen(request, timeout=timeout)


def game_format(game: Path) -> int:
    """이 판의 게임이 읽는 캐릭터 팩 형식. 적혀 있지 않은 옛 빌드는 1."""
    try:
        return int(json.loads((game / 'build.json').read_text(encoding='utf-8')).get('modelsFormat', 1))
    except (OSError, ValueError, TypeError, AttributeError):
        return 1


def _registry(hive_name: str, name: str) -> str | None:
    try:
        import winreg
        with winreg.OpenKey(getattr(winreg, hive_name), PACK_KEY) as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except (OSError, ImportError):
        return None


def _version_key(version: str) -> tuple[int, ...]:
    """판 번호(yyyy.M.d.HHmm)를 숫자로 — 글자로 견주면 9월이 10월보다 뒤가 된다."""
    return tuple(int(n) for n in re.findall(r'\d+', version or ''))


def read_pack(folder: Path, where: str, legacy_version: str | None = None) -> dict | None:
    """팩 폴더 하나: pack.json 이 있으면 거기 적힌 형식·판, 없으면 형식 1(2026-10-20 팩)."""
    if not folder.is_dir():
        return None
    info = folder / PACK_INFO
    if info.is_file():
        try:
            data = json.loads(info.read_text(encoding='utf-8'))
            return {'dir': folder, 'format': int(data['format']), 'version': str(data.get('version') or ''), 'where': where}
        except (OSError, ValueError, KeyError, TypeError):
            return None
    return {'dir': folder, 'format': 1, 'version': legacy_version or '', 'where': where}


def installed_packs() -> list[dict]:
    """이 PC 에 깔린 캐릭터 팩들: Intune(기기), 학생이 직접 깐 것(사용자), 형식 1 폴더."""
    found: list[dict] = []
    for hive, where in (('HKEY_LOCAL_MACHINE', 'machine'), ('HKEY_CURRENT_USER', 'user')):
        folder = _registry(hive, 'PackDir')
        if folder:
            found.append(read_pack(Path(folder), where))
    legacy = _registry('HKEY_LOCAL_MACHINE', 'ModelsDir')
    found.append(read_pack(Path(legacy) if legacy else DEFAULT_MODELS, 'machine', _registry('HKEY_LOCAL_MACHINE', 'Version')))
    seen, packs = set(), []
    for pack in found:
        if pack and str(pack['dir']).lower() not in seen:
            seen.add(str(pack['dir']).lower())
            packs.append(pack)
    return packs


def choose_pack(packs: list[dict], want: int) -> dict | None:
    """게임이 읽는 형식의 팩 가운데 가장 새 판(같으면 Intune 이 깐 것)."""
    fits = [p for p in packs if p['format'] == want]
    return max(fits, key=lambda p: (_version_key(p['version']), p['where'] == 'machine')) if fits else None


def active_pack(want: int) -> dict | None:
    """게임에 내줄 팩. 개발 PC 는 SPACEKIJUN_ISEKAI3D_MODELS, 맞는 팩이 없으면 isekai3d 저장소의 models."""
    override = os.environ.get('SPACEKIJUN_ISEKAI3D_MODELS')
    if override:
        return {'dir': Path(override), 'format': want, 'version': 'dev', 'where': 'dev'}
    pack = choose_pack(installed_packs(), want)
    if pack:
        return pack
    dev = Path(os.environ.get('SPACEKIJUN_ISEKAI3D') or Path.home() / 'orca' / 'projects' / 'isekai3d') / 'models'
    return {'dir': dev, 'format': want, 'version': 'dev', 'where': 'dev'} if dev.is_dir() else None


def drive_link(value) -> dict | None:
    """관리자가 넣은 값 → 받는 곳. https 구글 드라이브만(스페이스기전 src/lib/gameModelDownload.ts 와 같은 규칙)."""
    if not isinstance(value, dict) or not isinstance(value.get('url'), str):
        return None
    from urllib.parse import urlparse
    url = value['url'].strip()
    parts = urlparse(url)
    if parts.scheme != 'https' or parts.hostname not in DRIVE_HOSTS:
        return None
    note = value.get('note')
    return {'url': url, 'note': note[:200] if isinstance(note, str) else ''}


_link = {'at': 0.0, 'value': None}


def download_link() -> dict | None:
    """새 캐릭터 팩 설치 파일의 구글 드라이브 링크 (로그인 없이 읽는 공개 설정, 10분 동안 기억 — 못 읽으면 1분)."""
    import time
    now = time.monotonic()
    if _link['at'] and now < _link['at']:
        return _link['value']
    value, keep = None, 60
    try:
        from core import notify
        cfg = notify.config()
        key = cfg['anon_key']
        url = f"{cfg['url'].rstrip('/')}/rest/v1/system_settings?setting_key=eq.{LINK_KEY}&select=setting_value"
        request = urllib.request.Request(url, headers={'apikey': key, 'Authorization': f'Bearer {key}'})
        with _send(request, 8) as r:
            rows = json.loads(r.read() or b'[]')
        value, keep = drive_link(rows[0].get('setting_value') if rows else None), 600
    except Exception:
        pass
    _link.update(at=now + keep, value=value)
    return value


def model_files(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    return sorted(f.name for f in folder.iterdir() if MODEL.match(f.name) and '-sample_' not in f.name and f.is_file())


class _Handler(SimpleHTTPRequestHandler):
    game: Path = GAME_DIR
    models: Path | None = None          # 정해 준 캐릭터 폴더(시험) — 없으면 깔린 팩에서 고른다
    # 학생판의 스페이스기전 로그인(브라우저 구글 로그인)을 시작하는 일 — 게임이 로그인 안 된 것을 보면 부른다 (2026-10-20)
    signin = None
    # Windows 레지스트리가 .js 를 text/plain 으로 알려 주는 PC 가 있다 — 모듈 스크립트가 안 돈다
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
        '.wasm': 'application/wasm', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
        '.vrm': 'application/octet-stream',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.game), **kwargs)

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == HELLO:
            return self._text('isekai3d', 'text/plain')
        if path == '/models/index.json':
            pack = self.pack()
            return self._text(json.dumps(model_files(pack['dir']) if pack else []), 'application/json')
        if path == '/models/pack.json':
            return self._text(json.dumps(self.pack_status(), ensure_ascii=False), 'application/json')
        super().do_GET()

    def pack(self) -> dict | None:
        want = game_format(self.game)
        if self.models is not None:
            return {'dir': self.models, 'format': want, 'version': 'given', 'where': 'given'}
        return active_pack(want)

    def pack_status(self) -> dict:
        """게임이 보는 팩 상태: 읽는 형식, 내주는 팩, 깔린 팩들, 새 팩 받는 곳."""
        def brief(p):
            return {'format': p['format'], 'version': p['version'], 'where': p['where'], 'files': len(model_files(p['dir']))}
        pack = self.pack()
        installed = [] if self.models is not None else installed_packs()
        return {'want': game_format(self.game), 'active': brief(pack) if pack else None,
                'installed': [brief(p) for p in installed], 'download': download_link()}

    def do_POST(self):
        path = self.path.split('?', 1)[0]
        work = BRIDGE.get(path[len('/api/isekai3d/'):]) if path.startswith('/api/isekai3d/') else None
        if path == '/api/isekai3d/auth/start':
            work = 'signin'
        if path == '/api/isekai3d/pack/download':
            work = 'download'
        if not work:
            return self._json({'error': '없는 일이에요.'}, 404)
        if self.headers.get('Origin') != f'http://127.0.0.1:{self.server.server_address[1]}':
            return self._json({'error': '이 게임 창에서만 부를 수 있어요.'}, 403)
        if not (self.headers.get('Content-Type') or '').startswith('application/json'):
            return self._json({'error': 'JSON 만 받아요.'}, 415)
        size = int(self.headers.get('Content-Length') or 0)
        if size > (MAX_SAVE_BODY if path.endswith('/save/put') else MAX_BODY):
            return self._json({'error': '요청이 너무 커요.'}, 413)
        try:
            body = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._json({'error': '요청 형식을 확인해 주세요.'}, 400)
        if work == 'signin':
            # 이 게임은 다른 스페이스기전 앱처럼 로그인해야 한다 — 학생판의 로그인을 연다(토큰은 게임에 주지 않는다).
            start = type(self).signin
            if not start:
                return self._json({'error': '여기서는 로그인할 수 없어요.'}, 503)
            try:
                return self._json({'message': start()})
            except Exception as exc:
                return self._json({'error': str(exc) or '로그인을 시작하지 못했어요.'}, 409)
        if work == 'download':
            # 새 캐릭터 팩 설치 파일 — 게임 창이 아니라 학생의 브라우저에서 구글 드라이브를 연다
            link = download_link()
            if not link:
                return self._json({'error': '아직 받을 수 있는 링크가 없어요. 스페이스기전에 연결되면 다시 해 주세요.'}, 503)
            type(self).opener(link['url'])
            return self._json({'message': '브라우저에서 3D 캐릭터 팩 설치 파일을 받는 화면을 열었어요.'})
        status, answer = self.bridge(work, body)
        self._json(answer, status)

    @staticmethod
    def opener(url: str) -> None:
        import webbrowser
        webbrowser.open(url, new=2)

    def do_OPTIONS(self):
        self.send_error(405)          # 다른 출처의 사전 요청은 받지 않는다

    @staticmethod
    def bridge(work, body: dict) -> tuple[int, object]:
        """학생 세션으로 스페이스기전에 넘긴다. 로그인 안 했으면 401 (게임은 미리 써 둔 카드로)."""
        from core import notify, supa_auth
        kind, name, params = work
        try:
            headers = {**supa_auth.auth_headers(), 'Content-Type': 'application/json'}
        except Exception:
            return 401, {'error': '스페이스기전 로그인이 필요해요.', 'code': 'SIGNED_OUT'}
        base = notify.config()['url'].rstrip('/')
        if kind == 'rpc':
            url, data = f'{base}/rest/v1/rpc/{name}', {p: body.get(p) for p in params}
        else:
            url, data = f'{base}/functions/v1/{name}', body
        request = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers, method='POST')
        try:
            with _send(request, 100 if kind == 'fn' else 15) as r:
                return r.status, json.loads(r.read() or b'null')
        except urllib.error.HTTPError as e:
            try:
                answer = json.loads(e.read() or b'{}')
            except ValueError:
                answer = {}
            return e.code, {'error': answer.get('error') or answer.get('message') or '스페이스기전이 거절했어요.', 'code': answer.get('code')}
        except OSError:
            return 503, {'error': '스페이스기전에 닿지 못했어요.', 'code': 'OFFLINE'}

    def _json(self, value, status: int = 200):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def list_directory(self, path):
        self.send_error(404)          # 폴더 목록은 보여 주지 않는다

    def translate_path(self, path):
        clean = path.split('?', 1)[0].split('#', 1)[0]
        if clean.startswith('/models/'):
            name = urllib.request.url2pathname(clean[len('/models/'):])
            # 목록에 드는 이름만 — 폴더 밖으로 나가는 경로는 없는 파일이 된다
            ok = MODEL.match(name) and '-sample_' not in name
            pack = self.pack()
            folder = pack['dir'] if pack else DEFAULT_MODELS
            return str(folder / name) if ok and pack else str(folder / '__none__')
        return super().translate_path(path)

    def end_headers(self):
        # 게임 파일은 새 판에서 바뀐다(이름에 해시가 든 것도 있지만 index.html 은 같다).
        # 캐릭터 목록은 언제나 새로(깔린 팩이 바뀐다). 캐릭터 파일도 쓸 때마다 확인한다 — 바뀌지 않았으면
        # 304 로 내려받지 않는다(2026-10-20: 하루 동안 그냥 쓰게 했더니 다시 만든 서아·태오가 옛 파일과 섞여
        # 불러오지 못했고, 캐릭터 폴더 없이 켠 날의 빈 목록이 하루 동안 남았다).
        path = self.path.split('?', 1)[0]
        self.send_header('Cache-Control', 'no-store' if path == '/models/index.json' else 'no-cache')
        super().end_headers()

    def _text(self, text: str, kind: str):
        body = text.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', f'{kind}; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Server:
    """처음 게임을 열 때 띄우고, 프로그램을 끝낼 때 내린다."""

    def __init__(self, port: int = PORT, game: Path | None = None, models: Path | None = None, signin=None):
        self.port = port
        self.game = game or GAME_DIR
        self.models = models
        self.signin = signin              # 게임의 «스페이스기전 로그인» 단추가 부르는 일 (학생판의 _auth)
        self._server: ThreadingHTTPServer | None = None
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.port}/'

    def start(self) -> str:
        with self._lock:
            if self._server:
                return self.url
            if not (self.game / 'index.html').is_file():
                raise RuntimeError('이세계 사회인 게임 파일이 이 판에 들어 있지 않습니다.')
            handler = type('Isekai3DHandler', (_Handler,), {'game': self.game, 'models': self.models,
                                                          'signin': staticmethod(self.signin) if self.signin else None})
            try:
                self._server = ThreadingHTTPServer(('127.0.0.1', self.port), handler)
            except OSError:
                raise RuntimeError(f'{self.port}번 포트를 다른 프로그램이 쓰고 있어 이세계 사회인을 열 수 없습니다.') from None
            threading.Thread(target=self._server.serve_forever, name='isekai3d-server', daemon=True).start()
            return self.url

    def stop(self) -> None:
        with self._lock:
            server, self._server = self._server, None
        if server:
            server.shutdown()
            server.server_close()
