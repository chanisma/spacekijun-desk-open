"""이세계 3D 로컬 서버 (2026-10-19 요청) — 게임·캐릭터 목록을 내주고, 목록 밖·폴더 밖 파일은 내주지 않는지."""
from test_sandbox import use_sandbox
use_sandbox()
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from core import isekai3d_server


class Isekai3DServerTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.game, self.models = root / 'game', root / 'models'
        (self.game / 'assets').mkdir(parents=True)
        (self.game / 'index.html').write_text('<!doctype html><title>이세계 3D</title>', encoding='utf-8')
        (self.game / 'assets' / 'index-abc.js').write_text('export {}', encoding='utf-8')
        self.models.mkdir()
        for name in ('female-adult-mina.vrm', 'female-adult-mina@sleep.vrm', 'female-adult-sample_a.vrm', 'notes.txt'):
            (self.models / name).write_bytes(b'glTF')
        (root / 'secret.txt').write_text('비밀', encoding='utf-8')
        self.server = isekai3d_server.Server(port=42199, game=self.game, models=self.models)
        self.addCleanup(self.server.stop)
        self.base = self.server.start().rstrip('/')

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.headers.get('Content-Type'), r.read()
        except urllib.error.HTTPError as e:
            return e.code, None, b''

    def test_game_and_its_scripts_as_modules(self):
        self.assertEqual(self.get('/')[0], 200)
        status, kind, _ = self.get('/assets/index-abc.js')
        self.assertEqual((status, kind), (200, 'text/javascript'))

    def test_characters_listed_without_the_vroid_samples(self):
        status, _, body = self.get('/models/index.json')
        self.assertEqual(json.loads(body), ['female-adult-mina.vrm', 'female-adult-mina@sleep.vrm'])
        self.assertEqual(self.get('/models/female-adult-mina%40sleep.vrm')[0], 200)
        self.assertEqual(self.get('/models/female-adult-sample_a.vrm')[0], 404)
        self.assertEqual(self.get('/models/notes.txt')[0], 404)

    def test_character_list_never_kept_and_files_checked_each_time(self):
        def cache(path):
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.headers.get('Cache-Control')
        self.assertEqual(cache('/models/index.json'), 'no-store')
        self.assertEqual(cache('/models/female-adult-mina.vrm?v=2'), 'no-cache')
        self.assertEqual(cache('/'), 'no-cache')

    def test_sign_in_starts_the_programs_login_only_from_the_game(self):
        calls = []
        self.server.stop()
        server = isekai3d_server.Server(port=42199, game=self.game, models=self.models, signin=lambda: calls.append(1) or '브라우저에서 로그인해 주세요.')
        self.addCleanup(server.stop)
        server.start()
        status, answer = self.post('/api/isekai3d/auth/start', b'{}')
        self.assertEqual((status, answer), (200, {'message': '브라우저에서 로그인해 주세요.'}))
        self.assertEqual(calls, [1])
        status, _ = self.post('/api/isekai3d/auth/start', b'{}', origin='http://evil.example')
        self.assertEqual(status, 403)
        self.assertEqual(calls, [1])

    def test_nothing_outside_the_folders(self):
        for path in ('/models/..%2Fsecret.txt', '/../secret.txt', '/models/../secret.txt', '/assets/'):
            self.assertEqual(self.get(path)[0], 404, path)

    def test_no_pack_means_no_characters(self):
        self.server.stop()
        bare = isekai3d_server.Server(port=42199, game=self.game, models=self.game / 'none')
        self.addCleanup(bare.stop)
        bare.start()
        self.assertEqual(json.loads(self.get('/models/index.json')[2]), [])

    # ---- 캐릭터 팩 형식 (2026-10-25) — 학생판과 팩이 따로 업데이트돼 판이 어긋나도 ----
    def pack_dir(self, name, fmt=None, version=''):
        folder = Path(self.models.parent) / name
        folder.mkdir()
        (folder / 'female-adult-mina.vrm').write_bytes(b'glTF')
        if fmt:
            (folder / 'pack.json').write_text(json.dumps({'format': fmt, 'version': version}), encoding='utf-8')
        return folder

    def registry(self, values):
        return patch('core.isekai3d_server._registry', side_effect=lambda hive, name: values.get((hive, name)))

    def test_the_newest_pack_of_the_format_the_game_reads(self):
        old = self.pack_dir('models-old')
        machine = self.pack_dir('pack-machine', 2, '2026.9.30.1200')
        user = self.pack_dir('pack-user', 2, '2026.10.25.900')
        values = {('HKEY_LOCAL_MACHINE', 'PackDir'): str(machine), ('HKEY_CURRENT_USER', 'PackDir'): str(user),
                  ('HKEY_LOCAL_MACHINE', 'ModelsDir'): str(old), ('HKEY_LOCAL_MACHINE', 'Version'): '2026.10.20.0727'}
        with self.registry(values):
            packs = isekai3d_server.installed_packs()
            self.assertEqual(sorted((p['where'], p['format']) for p in packs), [('machine', 1), ('machine', 2), ('user', 2)])
            # 10월 판이 9월 판보다 새 판 (글자로 견주면 거꾸로)
            self.assertEqual(isekai3d_server.choose_pack(packs, 2)['dir'], user)
            self.assertEqual(isekai3d_server.choose_pack(packs, 1)['dir'], old)
            self.assertIsNone(isekai3d_server.choose_pack(packs, 3))

    def test_a_game_that_reads_another_format_gets_no_characters_and_is_told_why(self):
        old = self.pack_dir('models-old')
        (self.game / 'build.json').write_text(json.dumps({'commit': 'abc', 'modelsFormat': 2}), encoding='utf-8')
        self.server.stop()
        server = isekai3d_server.Server(port=42199, game=self.game)
        self.addCleanup(server.stop)
        server.start()
        values = {('HKEY_LOCAL_MACHINE', 'ModelsDir'): str(old), ('HKEY_LOCAL_MACHINE', 'Version'): '2026.10.20.0727'}
        link = {'url': 'https://drive.google.com/file/d/x/view', 'note': ''}
        with self.registry(values), patch.dict('os.environ', {'SPACEKIJUN_ISEKAI3D': str(self.game / 'none')}), \
                patch('core.isekai3d_server.download_link', return_value=link):
            self.assertEqual(json.loads(self.get('/models/index.json')[2]), [])
            self.assertEqual(self.get('/models/female-adult-mina.vrm')[0], 404)
            status = json.loads(self.get('/models/pack.json')[2])
        self.assertEqual(status['want'], 2)
        self.assertIsNone(status['active'])
        self.assertEqual(status['installed'], [{'format': 1, 'version': '2026.10.20.0727', 'where': 'machine', 'files': 1}])
        self.assertEqual(status['download'], link)
        # 맞는 팩이 깔리면 그 팩을 내준다 (게임을 다시 열면)
        pack = self.pack_dir('pack', 2, '2026.10.25.1300')
        values[('HKEY_LOCAL_MACHINE', 'PackDir')] = str(pack)
        with self.registry(values), patch('core.isekai3d_server.download_link', return_value=None):
            self.assertEqual(json.loads(self.get('/models/index.json')[2]), ['female-adult-mina.vrm'])
            self.assertEqual(self.get('/models/female-adult-mina.vrm')[0], 200)

    def test_an_old_build_reads_the_first_format(self):
        self.assertEqual(isekai3d_server.game_format(self.game), 1)

    def test_only_https_drive_links(self):
        self.assertEqual(isekai3d_server.drive_link({'url': 'https://drive.google.com/file/d/x/view', 'note': '새 팩'}), {'url': 'https://drive.google.com/file/d/x/view', 'note': '새 팩'})
        for bad in ({'url': 'http://drive.google.com/x'}, {'url': 'https://evil.example/x.exe'}, {'url': 3}, None, 'x'):
            self.assertIsNone(isekai3d_server.drive_link(bad), bad)

    def test_download_opens_the_browser_only_from_the_game(self):
        opened = []
        link = {'url': 'https://drive.google.com/file/d/x/view', 'note': ''}
        with patch('core.isekai3d_server.download_link', return_value=link), patch.object(isekai3d_server._Handler, 'opener', staticmethod(opened.append)):
            self.assertEqual(self.post('/api/isekai3d/pack/download', origin='https://evil.example')[0], 403)
            status, _ = self.post('/api/isekai3d/pack/download')
        self.assertEqual((status, opened), (200, [link['url']]))
        with patch('core.isekai3d_server.download_link', return_value=None):
            self.assertEqual(self.post('/api/isekai3d/pack/download')[0], 503)

    # ---- 스페이스기전 다리 (2026-10-19) ----
    def post(self, path, body=b'{}', origin=None, kind='application/json'):
        headers = {'Content-Type': kind, 'Origin': origin or self.base}
        request = urllib.request.Request(self.base + path, body, headers, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def test_bridge_only_from_the_game_window(self):
        self.assertEqual(self.post('/api/isekai3d/status', origin='https://evil.example')[0], 403)
        self.assertEqual(self.post('/api/isekai3d/status', kind='text/plain')[0], 415)
        self.assertEqual(self.post('/api/isekai3d/admin')[0], 404)
        self.assertEqual(self.post('/api/isekai3d/status', body=b'[1]')[0], 400)

    def test_signed_out_says_so(self):
        with patch('core.supa_auth.auth_headers', side_effect=RuntimeError('no session')):
            status, answer = self.post('/api/isekai3d/status')
        self.assertEqual((status, answer['code']), (401, 'SIGNED_OUT'))

    def session(self, url, send):
        """학생 세션이 있는 척 + 스페이스기전으로 보내는 것을 가로챈다"""
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch('core.supa_auth.auth_headers', return_value={'apikey': 'anon', 'Authorization': 'Bearer t'}))
        stack.enter_context(patch('core.notify.config', return_value={'url': url, 'anon_key': 'anon'}))
        stack.enter_context(patch('core.isekai3d_server._send', side_effect=send))
        return stack

    def test_bridge_adds_the_session_and_passes_only_known_arguments(self):
        seen = {}

        class Reply:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"status": "card"}'

        def fake_open(request, timeout):
            seen.update(url=request.full_url, headers=dict(request.header_items()), body=json.loads(request.data), timeout=timeout)
            return Reply()

        with self.session('https://db.example/', fake_open):
            status, answer = self.post('/api/isekai3d/question/take', json.dumps({'p_context_key': 'explore', 'p_user': 'someone-else'}).encode())
        self.assertEqual((status, answer), (200, {'status': 'card'}))
        self.assertEqual(seen['url'], 'https://db.example/rest/v1/rpc/isekai3d_question_take')
        self.assertEqual(seen['body'], {'p_context_key': 'explore'})          # 남의 user id 같은 것은 안 넘긴다
        self.assertEqual(seen['headers']['Authorization'], 'Bearer t')
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/question/fill', json.dumps({'kind': 'explore'}).encode())
        self.assertEqual((seen['url'], seen['timeout']), ('https://db.example/functions/v1/isekai3d-question', 100))
        # 직장 에피소드 (2026-10-25): 받기·결정은 정해진 인자만, 미리 쓰기는 엣지 함수로 본문 그대로
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/episode/take', json.dumps({'p_game_key': 'abcd1234:1', 'p_career': 'tech', 'p_user': 'x'}).encode())
        self.assertEqual((seen['url'], seen['body']), ('https://db.example/rest/v1/rpc/isekai3d_episode_take', {'p_game_key': 'abcd1234:1', 'p_career': 'tech'}))
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/episode/answer', json.dumps({'p_scene_id': 's1', 'p_choice': None, 'p_text': '솔직하게 말한다'}).encode())
        self.assertEqual(seen['body'], {'p_scene_id': 's1', 'p_choice': None, 'p_text': '솔직하게 말한다'})
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/episode/fill', json.dumps({'gameKey': 'abcd1234:1', 'career': {'id': 'tech'}}).encode())
        self.assertEqual((seen['url'], seen['body']['gameKey'], seen['timeout']), ('https://db.example/functions/v1/isekai3d-episode', 'abcd1234:1', 100))
        # 주식 앱 (2026-10-26): 시세 읽기 셋 — 정해진 인자만
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/stocks/market', json.dumps({'p_user': 'x'}).encode())
        self.assertEqual((seen['url'], seen['body']), ('https://db.example/rest/v1/rpc/isekai3d_stock_market', {}))
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/stocks/history', json.dumps({'p_asset': 'kr:005930', 'p_days': 130, 'p_user': 'x'}).encode())
        self.assertEqual((seen['url'], seen['body']), ('https://db.example/rest/v1/rpc/isekai3d_stock_history', {'p_asset': 'kr:005930', 'p_days': 130}))
        asks = [{'key': 'o1', 'asset_id': 'us:AAPL', 'after': '2026-10-26T11:00:00Z'}]
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/stocks/closes', json.dumps({'p_asks': asks}).encode())
        self.assertEqual((seen['url'], seen['body']), ('https://db.example/rest/v1/rpc/isekai3d_stock_closes', {'p_asks': asks}))
        # 오락기 동전: 넣기는 인자가 없다 — 게임이 값을 보내도 넘기지 않는다
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/play/insert', json.dumps({'p_price': 0}).encode())
        self.assertEqual((seen['url'], seen['body']), ('https://db.example/rest/v1/rpc/isekai3d_play_insert', {}))
        with self.session('https://db.example', fake_open):
            self.post('/api/isekai3d/play/use', json.dumps({'p_used': 300}).encode())
        self.assertEqual(seen['body'], {'p_used': 300})
        # 저장 칸: 올리기는 큰 저장도 받고(600KB까지), 다른 일은 80KB까지
        big = {'p_slot': 2, 'p_state': {'blob': 'x' * 200_000}, 'p_summary': {}, 'p_saved_at': 1, 'p_base_version': None, 'p_user': 'x'}
        with self.session('https://db.example', fake_open):
            status, _ = self.post('/api/isekai3d/save/put', json.dumps(big).encode())
        self.assertEqual(status, 200)
        self.assertEqual(seen['url'], 'https://db.example/rest/v1/rpc/isekai3d_save_put')
        self.assertEqual(sorted(seen['body']), ['p_base_version', 'p_saved_at', 'p_slot', 'p_state', 'p_summary'])
        with self.session('https://db.example', fake_open):
            status, _ = self.post('/api/isekai3d/save/get', json.dumps({'p_slot': 1, 'pad': 'x' * 200_000}).encode())
        self.assertEqual(status, 413)

    def test_missing_game_is_said_plainly(self):
        with self.assertRaisesRegex(RuntimeError, '게임 파일'):
            isekai3d_server.Server(port=42198, game=self.game / 'none').start()


if __name__ == '__main__':
    unittest.main()
