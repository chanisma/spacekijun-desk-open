"""교실판(classroom.py · core/classroom_*) — 가짜 서버·가짜 드라이브·가짜 실행으로 흐름을 따라가 본다.

    cd app && python -m unittest test_classroom
"""
import io
import json
import sys
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
from unittest import mock

from core import classroom_drive, classroom_icons, classroom_link, classroom_setup, classroom_vault
from datetime import datetime

from core.classroom_controller import AWAKE_OFF_HOURS, Controller, POLL_QR

CODE = 'c' * 24
DRIVE_CODE = 'd' * 24


class FakeClient:
    def __init__(self, polls, drive_polls=None):
        self.polls = list(polls)
        self.drive_polls = list(drive_polls or [{'status': 'pending'}])
        self.calls = []

    def start(self, name, purpose='session'):
        self.calls.append(('start', name, purpose))
        return {'code': DRIVE_CODE if purpose == 'drive' else CODE, 'expires_at': '2030-01-01T00:00:00+09:00'}

    def poll(self, code):
        self.calls.append(('poll', code))
        queue = self.drive_polls if code == DRIVE_CODE else self.polls
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def extend(self, code, minutes):
        self.calls.append(('extend', minutes))
        return {'status': 'active', 'ends_at': '2030-01-01T01:00:00+09:00'}

    def end(self, code):
        self.calls.append(('end', code))
        return {'status': 'ended'}


class FakeWorkspace:
    def __init__(self):
        self.synced = 0

    def sync(self, final=False):
        self.synced += 1


class FakeSession:
    def __init__(self, handoff):
        self.handoff = handoff
        self.items = handoff['preset']['items']
        self.email = handoff['teacher'].get('email', '')
        self.prepared = self.ended = False
        self.opened = []
        self.google = handoff.get('google')
        self.workspace = FakeWorkspace()

    def prepare(self):
        self.prepared = True

    def end(self, progress=None):
        self.ended = True
        return 0

    def open_item(self, index):
        self.opened.append(index)
        return {'ok': True}

    def update_google(self, google):
        self.google = google

    def snapshot(self):
        return {'teacher': '김교사', 'title': 'x', 'section': None, 'items': [], 'drive': {}, 'files': []}


HANDOFF = {'teacher': {'name': '김교사', 'email': 'kim@myschool.hs.kr'},
           'preset': {'title': '1-3 정보', 'items': [{'kind': 'url', 'url': 'https://a.b'}]}}
APPROVED = {'status': 'approved', 'handoff': HANDOFF, 'ends_at': '2030-01-01T00:50:00+09:00'}


def controller(polls, clock=lambda: 1000.0, drive_polls=None, idle_fn=None):
    sessions = []

    def factory(handoff):
        sessions.append(FakeSession(handoff))
        return sessions[-1]
    c = Controller(FakeClient(polls, drive_polls), lambda: '2-3 교실', factory, clock=clock, run_async=lambda fn: fn(),
                   idle_fn=idle_fn)
    return c, sessions


class ControllerTest(unittest.TestCase):
    def test_approval_shows_dock_without_opening_anything(self):
        c, sessions = controller([{'status': 'pending'}, APPROVED])
        self.assertEqual(c.step(), POLL_QR)                  # QR 만들기
        self.assertTrue(c.state()['qr'].startswith('<svg'))
        c.step()                                              # 대기
        self.assertEqual(c.phase, 'qr')
        c.step()                                              # 승인
        self.assertEqual(c.phase, 'session')
        self.assertTrue(sessions[0].prepared)
        self.assertEqual(sessions[0].opened, [])             # 저절로 열지 않는다(사용자 결정)
        self.assertEqual(c.open_item(0), {'ok': True})
        self.assertEqual(sessions[0].opened, [0])

    def test_saved_files_sync_during_session(self):
        c, sessions = controller([APPROVED])
        c.step(); c.step(); c.step()
        self.assertGreater(sessions[0].workspace.synced, 0)

    def test_time_up_ends_session_and_tells_server(self):
        now = [1000.0]
        c, sessions = controller([APPROVED], clock=lambda: now[0])
        c.step(); c.step()
        now[0] = c.ends_at + 1
        c.step()
        self.assertTrue(sessions[0].ended)
        self.assertIn(('end', CODE), c.client.calls)
        self.assertEqual(c.phase, 'qr')
        self.assertIsNone(c.state()['session'])              # 토큰을 쥔 세션을 놓았다

    def test_phone_stop_ends_without_server_call(self):
        now = [1000.0]
        c, sessions = controller([APPROVED, {'status': 'ended'}], clock=lambda: now[0])
        c.step(); c.step()
        now[0] += 25                                         # 서버 확인 주기
        c.step()
        self.assertTrue(sessions[0].ended)
        self.assertNotIn(('end', CODE), c.client.calls)
        self.assertIn('휴대폰', c.notice)

    def test_offline_then_recovers(self):
        c, _ = controller([{'status': 'pending'}])
        c.client.start = mock.Mock(side_effect=classroom_link.LinkError('network'))
        c.step()
        self.assertEqual(c.state()['phase'], 'offline')
        self.assertIn('인터넷', c.state()['error'])

    def test_sleeps_at_night_after_ten_minutes_and_wakes_on_touch(self):
        now = [datetime(2026, 11, 14, 22, 0).timestamp()]          # 토요일 밤
        idle = [600.0]
        c, _ = controller([{'status': 'pending'}], clock=lambda: now[0], idle_fn=lambda: idle[0])
        c.step(); c.step()
        self.assertEqual(c.phase, 'qr')
        now[0] += AWAKE_OFF_HOURS + 1
        c.step()
        self.assertEqual(c.phase, 'sleep')
        self.assertIn(('end', CODE), c.client.calls)             # 떠 있던 QR 을 닫는다
        self.assertEqual(c.state()['qr'], '')
        before = len(c.client.calls)
        for _ in range(5):
            c.step()
        self.assertEqual(len(c.client.calls), before)            # 쉬는 중에는 서버를 부르지 않는다
        idle[0] = 1.0                                            # 누가 화면을 만졌다
        c.step()
        self.assertEqual(c.phase, 'qr')
        c.step()
        self.assertEqual(c.client.calls[-1][0], 'start')         # 새 QR

    def test_touch_keeps_qr_awake_at_night(self):
        now = [datetime(2026, 11, 14, 22, 0).timestamp()]
        c, _ = controller([{'status': 'pending'}], clock=lambda: now[0], idle_fn=lambda: 1.0)
        c.step()
        now[0] += AWAKE_OFF_HOURS + 1
        c.step()
        self.assertEqual(c.phase, 'qr')

    def test_school_hours_never_sleep_and_morning_wakes(self):
        now = [datetime(2026, 11, 12, 9, 0).timestamp()]           # 목요일 아침
        c, _ = controller([{'status': 'pending'}], clock=lambda: now[0])
        c.step()
        now[0] += 5 * 3600
        c.step()
        self.assertEqual(c.phase, 'qr')
        now[0] = datetime(2026, 11, 12, 20, 0).timestamp()
        c.step()
        self.assertEqual(c.phase, 'sleep')
        now[0] = datetime(2026, 11, 13, 7, 0).timestamp()           # 금요일 07시
        c.step()
        self.assertEqual(c.phase, 'qr')

    def test_wake_button(self):
        now = [datetime(2026, 11, 15, 3, 0).timestamp()]            # 일요일 새벽
        c, _ = controller([{'status': 'pending'}], clock=lambda: now[0])
        now[0] += AWAKE_OFF_HOURS + 1
        c.step()
        self.assertEqual(c.phase, 'sleep')
        c.wake()
        self.assertEqual(c.phase, 'qr')
        c.step()
        self.assertEqual(c.phase, 'qr')                            # 10분을 다시 센다

    def test_extend_updates_end(self):
        c, _ = controller([APPROVED])
        c.step(); c.step()
        before = c.ends_at
        c.extend(10)
        self.assertGreater(c.ends_at, before)

    def test_drive_reconnect_by_same_teacher_swaps_token_only(self):
        google = {'access_token': 'new', 'expires_at': 9999999999}
        c, sessions = controller([APPROVED], drive_polls=[
            {'status': 'approved', 'handoff': {'teacher': {'email': 'kim@myschool.hs.kr'}, 'google': google}}])
        c.step(); c.step()
        c.drive_reconnect()
        self.assertIn(('start', '2-3 교실', 'drive'), c.client.calls)
        self.assertTrue(c.state()['drive_link']['qr'].startswith('<svg'))
        c.step()
        self.assertEqual(sessions[0].google, google)
        self.assertIn(('end', DRIVE_CODE), c.client.calls)    # 드라이브 QR 연결은 바로 닫는다
        self.assertNotIn(('end', CODE), c.client.calls)       # 수업은 그대로
        self.assertIsNone(c.state()['drive_link'])
        self.assertEqual(c.phase, 'session')

    def test_drive_reconnect_by_other_teacher_is_ignored(self):
        c, sessions = controller([APPROVED], drive_polls=[
            {'status': 'approved', 'handoff': {'teacher': {'email': 'lee@myschool.hs.kr'}, 'google': {'access_token': 'x'}}}])
        c.step(); c.step()
        c.drive_reconnect()
        c.step()
        self.assertIsNone(sessions[0].google)
        self.assertIn('수업 중인 선생님이 아니', c.notice)


class LinkClientTest(unittest.TestCase):
    def test_sends_device_key_and_maps_errors(self):
        sent = []

        def opener(req, timeout):
            sent.append(json.loads(req.data))
            headers.append(dict(req.header_items()))
            return io.BytesIO(b'{"error":"rate_limited"}')      # DB RPC 는 알려진 오류를 200 에 담는다
        headers = []
        client = classroom_link.Client(key='k' * 43, url='https://x/rest/v1/rpc/classroom_device_call', opener=opener,
                                       anon_key='anon')
        with self.assertRaises(classroom_link.LinkError) as ctx:
            client.start('2-3 교실')
        self.assertEqual(ctx.exception.code, 'rate_limited')
        self.assertEqual(sent[0], {'p_action': 'start', 'p_device_key': 'k' * 43,
                                   'p_args': {'name': '2-3 교실', 'platform': 'windows', 'purpose': 'session'}})
        self.assertEqual(headers[0].get('Apikey'), 'anon')

        def http_error(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 404, 'x', {}, io.BytesIO(b'{"message":"no"}'))
        client.opener = http_error
        with self.assertRaises(classroom_link.LinkError) as ctx:
            client.poll(CODE)
        self.assertEqual(ctx.exception.code, 'server_error')

    def test_rpc_url_is_postgrest(self):
        self.assertTrue(classroom_link.rpc_url().endswith('/rest/v1/rpc/classroom_device_call'))

    def test_qr_is_svg_of_approve_url(self):
        svg = classroom_link.qr_svg(classroom_link.approve_url('c' * 24))
        self.assertTrue(svg.startswith('<svg') and 'viewBox' in svg)


class FakeResponse(io.BytesIO):
    def __init__(self, body=b'', headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeDriveServer:
    """구글 드라이브 API 흉내 — 받은 요청을 모아 둔다."""

    def __init__(self, files, token='g-token'):
        self.files = files            # id → {name, mimeType, parents, body}
        self.token = token
        self.requests = []
        self.uploads = {}             # 올린 곳 → 내용
        self.made = 0

    def __call__(self, req, timeout=60):
        url, method = req.full_url, req.get_method()
        if req.headers.get('Authorization') != 'Bearer ' + self.token:
            raise urllib.error.HTTPError(url, 401, 'x', {}, io.BytesIO(b''))
        self.requests.append((method, url))
        if url.startswith('https://upload.local/'):              # 이어 올리기 두 번째 요청
            self.uploads[url] = req.data
            return FakeResponse(json.dumps({'id': url.rsplit('/', 1)[-1]}).encode())
        if '/upload/drive/v3/files' in url:
            body = json.loads(req.data or b'{}')
            if method == 'POST':
                self.made += 1
                target = f'new{self.made}'
                self.files[target] = {'name': body.get('name'), 'parents': body.get('parents')}
            else:
                target = url.split('/files/')[1].split('?')[0]
            return FakeResponse(b'', {'Location': f'https://upload.local/{target}'})
        if '/export?' in url:
            return FakeResponse(b'EXPORTED')
        if 'alt=media' in url:
            return FakeResponse(self.files[url.split('/files/')[1].split('?')[0]]['body'])
        if '/files?' in url and method == 'POST':
            body = json.loads(req.data)
            self.made += 1
            self.files[f'f{self.made}'] = body
            return FakeResponse(json.dumps({'id': f'f{self.made}', 'name': body['name']}).encode())
        if '/files?' in url:
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('q', [''])[0]
            kids = [{'id': i, **{k: v for k, v in f.items() if k != 'body'}} for i, f in self.files.items()
                    if f"'{(f.get('parents') or [''])[0]}' in parents" in q]
            return FakeResponse(json.dumps({'files': kids}).encode())
        file_id = url.split('/files/')[1].split('?')[0]
        meta = {k: v for k, v in self.files[file_id].items() if k != 'body'}
        return FakeResponse(json.dumps({'id': file_id, **meta}).encode())


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ('UNSENT_DIR', 'COPIES_DIR'):
            patcher = mock.patch.object(classroom_drive, name, os.path.join(self.tmp.name, name.lower()))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.now = [100.0]
        self.opened = []

    def workspace(self, server, token='g-token'):
        state = {'token': token}
        ws = classroom_drive.Workspace(os.path.join(self.tmp.name, 'drive'), lambda: state['token'], opener=server,
                                       startfile=self.opened.append, clock=lambda: self.now[0])
        return ws, state

    def edit(self, path, data):
        with open(path, 'wb') as f:
            f.write(data)
        st = os.stat(path)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))

    def test_regular_file_is_updated_in_place_after_save_settles(self):
        server = FakeDriveServer({'abcdefghij': {'name': '활동지.hwp', 'mimeType': 'application/x-hwp',
                                                 'parents': ['p1'], 'body': b'HWP'}})
        ws, _ = self.workspace(server)
        path = ws.open('abcdefghij')
        self.assertEqual(self.opened, [path])
        self.assertTrue(path.endswith('활동지.hwp'))
        self.edit(path, b'HWP-EDITED')
        self.assertEqual(ws.sync(), 0)                       # 방금 바뀜 — 저장이 끝나길 기다린다
        self.assertEqual(ws.snapshot()[0]['state'], 'pending')
        self.now[0] += 3
        self.assertEqual(ws.sync(), 1)
        self.assertEqual(server.uploads['https://upload.local/abcdefghij'], b'HWP-EDITED')
        self.assertEqual(ws.snapshot()[0]['state'], 'synced')
        self.assertEqual(ws.sync(), 0)                       # 다시 바뀌기 전엔 올리지 않는다

    def test_google_slides_edits_go_to_a_new_file_then_update_it(self):
        server = FakeDriveServer({'slides12345': {'name': '3단원', 'parents': ['p1'],
                                                  'mimeType': 'application/vnd.google-apps.presentation'}})
        ws, _ = self.workspace(server)
        path = ws.open('slides12345')
        self.assertTrue(path.endswith('3단원.pptx'))
        self.edit(path, b'PPTX-1')
        ws.sync(final=True)
        self.assertEqual(server.files['new1']['name'], '3단원 (교실에서 고침).pptx')   # 구글 슬라이드 원본은 덮지 않는다
        self.assertEqual(server.files['new1']['parents'], ['p1'])
        self.edit(path, b'PPTX-2')
        ws.sync(final=True)
        self.assertEqual(server.uploads['https://upload.local/new1'], b'PPTX-2')        # 그 뒤로는 새 파일을 갱신
        self.assertEqual(server.made, 1)

    def test_expired_token_keeps_file_for_next_time(self):
        server = FakeDriveServer({'abcdefghij': {'name': 'a.pptx', 'mimeType': 'x', 'parents': ['p1'], 'body': b'A'}})
        ws, state = self.workspace(server)
        path = ws.open('abcdefghij')
        self.edit(path, b'A2')
        state['token'] = None                                # 1시간이 지났다
        ws.sync(final=True)
        self.assertEqual(ws.snapshot()[0]['state'], 'failed')
        self.assertEqual(ws.stash_unsent('kim@myschool.hs.kr'), 1)
        self.assertTrue(classroom_drive.has_unsent('kim@myschool.hs.kr'))
        self.assertFalse(classroom_drive.has_unsent('lee@myschool.hs.kr'))
        sent = classroom_drive.send_unsent(classroom_drive.Drive('g-token', server), 'kim@myschool.hs.kr')
        self.assertEqual(sent, 1)
        self.assertFalse(classroom_drive.has_unsent('kim@myschool.hs.kr'))
        self.assertIn(b'A2', server.uploads.values())

    def test_copy_to_pc_folders_recursively_and_prefers_edited_copy(self):
        server = FakeDriveServer({
            'fold000001': {'name': '1-3 정보', 'mimeType': classroom_drive.FOLDER, 'parents': ['root']},
            'sub0000001': {'name': '활동 결과', 'mimeType': classroom_drive.FOLDER, 'parents': ['fold000001']},
            'file000001': {'name': 'a.hwp', 'mimeType': 'application/x-hwp', 'parents': ['fold000001'], 'body': b'A'},
            'file000002': {'name': 'b.pdf', 'mimeType': 'application/pdf', 'parents': ['sub0000001'], 'body': b'B'},
            'slides0001': {'name': '3단원', 'mimeType': 'application/vnd.google-apps.presentation', 'parents': ['root']},
        })
        ws, _ = self.workspace(server)
        opened = ws.open('file000001')
        self.edit(opened, b'A-EDITED')                       # 교실에서 고쳤지만 아직 안 올림
        dest = os.path.join(self.tmp.name, 'Desktop')
        os.makedirs(os.path.join(dest, '1-3 정보'))           # 같은 이름 폴더가 이미 있다
        seen = []
        result = ws.copy_to_pc([{'id': 'fold000001', 'name': '1-3 정보', 'mimeType': classroom_drive.FOLDER},
                                {'id': 'slides0001', 'name': '3단원', 'mimeType': 'application/vnd.google-apps.presentation'}],
                               dest, lambda done, total, name: seen.append((done, total)))
        top = os.path.join(dest, '1-3 정보 (2)')               # 있던 폴더를 덮지 않는다
        self.assertEqual(result, {'copied': 3, 'errors': [], 'truncated': False,
                                  'paths': [top, os.path.join(dest, '3단원.pptx')]})   # 고른 것의 자리만(«이 PC» 목록에)
        with open(os.path.join(top, 'a.hwp'), 'rb') as f:
            self.assertEqual(f.read(), b'A-EDITED')          # 드라이브본이 아니라 교실에서 고친 최신본
        with open(os.path.join(top, '활동 결과', 'b.pdf'), 'rb') as f:
            self.assertEqual(f.read(), b'B')
        self.assertTrue(os.path.exists(os.path.join(dest, '3단원.pptx')))   # 구글 슬라이드는 pptx 로
        self.assertEqual(seen[-1], (3, 3))

    def test_keep_opened_file_on_pc(self):
        server = FakeDriveServer({'abcdefghij': {'name': '활동지.hwp', 'mimeType': 'x', 'parents': ['p'], 'body': b'H'}})
        ws, _ = self.workspace(server)
        ws.open('abcdefghij')
        key = ws.snapshot()[0]['key']
        dest = os.path.join(self.tmp.name, 'keep')
        os.makedirs(dest)
        first, second = ws.keep(key, dest), ws.keep(key, dest)
        self.assertEqual(os.path.basename(first), '활동지.hwp')
        self.assertEqual(os.path.basename(second), '활동지 (2).hwp')
        with self.assertRaises(classroom_drive.DriveError):
            ws.keep('nope', dest)

    def test_pc_shelf_remembers_copies_per_teacher(self):
        dest = os.path.join(self.tmp.name, 'Desktop')
        os.makedirs(os.path.join(dest, '1-3 정보', '활동 결과'))
        for rel, body in (('a.hwp', b'A'), (os.path.join('1-3 정보', 'b.pdf'), b'B'),
                          (os.path.join('1-3 정보', '~$b.docx'), b'lock'), ('밖.txt', b'X')):
            with open(os.path.join(dest, rel), 'wb') as f:
                f.write(body)
        opened, trashed = [], []
        kim = classroom_drive.PcShelf('Kim@myschool.hs.kr', startfile=opened.append,
                                      recycle=lambda p: trashed.append(p) or os.remove(p), clock=lambda: self.now[0])
        kim.add([os.path.join(dest, '1-3 정보'), os.path.join(dest, 'a.hwp')], dest)
        self.assertEqual(kim.last_dest(), os.path.abspath(dest))
        # 다음 수업 — 같은 선생님(대소문자 무관)만 본다
        kim = classroom_drive.PcShelf('kim@myschool.hs.kr', startfile=opened.append,
                                      recycle=lambda p: trashed.append(p) or os.remove(p))
        self.assertEqual(classroom_drive.PcShelf('lee@myschool.hs.kr').list(), [])
        roots = kim.list()
        self.assertEqual([r['name'] for r in roots], ['a.hwp', '1-3 정보'])   # 최근 것이 앞
        folder = roots[1]
        self.assertEqual(folder['mimeType'], classroom_drive.FOLDER)
        inside = kim.list(folder['id'])
        self.assertEqual([r['name'] for r in inside], ['활동 결과', 'b.pdf'])   # 폴더 먼저 · 오피스 잠금 파일은 숨김
        kim.open(inside[1]['id'])
        self.assertEqual(opened, [os.path.join(dest, '1-3 정보', 'b.pdf')])
        with self.assertRaises(classroom_drive.DriveError):              # 기억한 것 밖으로는 못 나간다
            kim.resolve(folder['id'] + '/../밖.txt')
        with self.assertRaises(classroom_drive.DriveError):
            kim.resolve('pc:000000000000')
        with self.assertRaises(classroom_drive.DriveError):
            kim.open(folder['id'])                                       # 폴더는 화면에서 들어간다
        self.assertEqual(kim.trash([roots[0]['id']]), {'removed': 1, 'errors': []})
        self.assertEqual(trashed, [os.path.join(dest, 'a.hwp')])
        self.assertEqual([r['name'] for r in kim.list()], ['1-3 정보'])  # 지운 것은 목록에서도 빠진다
        self.assertEqual(kim.forget([folder['id']]), 1)
        self.assertEqual(kim.list(), [])
        self.assertTrue(os.path.isdir(os.path.join(dest, '1-3 정보')))    # 목록에서만 뺐다

    def test_snapshot_links_list_rows(self):
        server = FakeDriveServer({'slides12345': {'name': '3단원', 'parents': ['p1'],
                                                  'mimeType': 'application/vnd.google-apps.presentation'}})
        ws, _ = self.workspace(server)
        path = ws.open('slides12345')
        self.edit(path, b'X')
        ws.sync(final=True)
        snap = ws.snapshot()[0]
        self.assertEqual((snap['source_id'], snap['upload_id'], snap['exported']), ('slides12345', 'new1', True))
        self.assertEqual(ws.local_copy('new1'), path)        # 목록의 «(교실에서 고침)» 파일도 같은 로컬본

    def test_list_query_escapes_folder_id(self):
        server = FakeDriveServer({})
        classroom_drive.Drive('g-token', server).list("a'b")
        self.assertIn("%27a%5C%27b%27+in+parents", server.requests[-1][1])


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for name, value in (('SESSIONS_DIR', self.tmp.name),):
            patcher = mock.patch.object(classroom_setup, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ('UNSENT_DIR', 'COPIES_DIR'):
            patcher = mock.patch.object(classroom_drive, name, os.path.join(self.tmp.name, name.lower()))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def session(self, items, server=None, google=True, **kw):
        handoff = {'teacher': {'name': '김교사', 'email': 'kim@myschool.hs.kr'}, 'preset': {'title': 't', 'items': items}}
        if google:
            handoff['google'] = {'access_token': 'g-token', 'expires_at': time.time() + 3600,
                                 'scope': 'https://www.googleapis.com/auth/drive'}
        opened, popened = [], []
        s = classroom_setup.Session(handoff, settings={}, drive_opener=server or FakeDriveServer({}),
                                    popen=lambda cmd: popened.append(cmd) or mock.Mock(pid=None),
                                    startfile=opened.append, edge='C:/Edge/msedge.exe', **kw)
        s.prepare()
        return s, opened, popened

    def test_prepare_opens_nothing(self):
        s, opened, popened = self.session([{'kind': 'url', 'url': 'https://padlet.com/x'},
                                           {'kind': 'program', 'program': 'notepad'}])
        self.assertEqual((opened, popened), ([], []))
        self.assertTrue(s.drive_state()['connected'] and s.drive_state()['full'])

    def test_drive_folder_item_opens_explorer(self):
        s, opened, _ = self.session([{'kind': 'drive', 'id': 'folder12345', 'name': '1-3 정보',
                                      'mimeType': 'application/vnd.google-apps.folder'}])
        self.assertEqual(s.open_item(0), {'explore': 'folder12345', 'name': '1-3 정보'})
        self.assertEqual(opened, [])

    def test_drive_file_item_downloads_and_opens(self):
        server = FakeDriveServer({'abcdefghijk': {'name': 'a.pdf', 'mimeType': 'application/pdf', 'parents': ['p'],
                                                  'body': b'%PDF'}})
        s, opened, _ = self.session([{'kind': 'drive', 'id': 'abcdefghijk'}], server)
        self.assertEqual(s.open_item(0), {'ok': True})
        self.assertTrue(opened[0].startswith(s.dir))

    def test_copies_are_offered_next_class(self):
        s, _, _ = self.session([])
        self.assertEqual(s.notice, '')
        dest = os.path.join(self.tmp.name, 'Desktop')
        os.makedirs(dest)
        with open(os.path.join(dest, 'a.hwp'), 'wb') as f:
            f.write(b'A')
        s.record_copy(dest, 1, [os.path.join(dest, 'a.hwp')])
        s.end()
        s2, _, _ = self.session([])                       # 같은 선생님의 다음 수업
        self.assertIn('이 PC 에 복사해 둔 파일 1개', s2.notice)
        self.assertEqual([r['name'] for r in s2.shelf.list()], ['a.hwp'])

    def test_drive_file_without_token_asks_reconnect(self):
        s, _, _ = self.session([{'kind': 'drive', 'id': 'abcdefghijk'}], google=False)
        result = s.open_item(0)
        self.assertFalse(result['ok'])
        self.assertIn('다시 연결', result['error'])

    def test_url_opens_in_throwaway_edge_profile(self):
        s, _, popened = self.session([{'kind': 'url', 'url': 'https://padlet.com/x'}])
        s.open_item(0)
        self.assertIn('--user-data-dir=' + s.edge_profile, popened[0])
        self.assertEqual(popened[0][-1], 'https://padlet.com/x')

    def test_edge_has_no_debug_port(self):
        """디버깅 포트를 열면 구글이 그 Edge 의 로그인을 막는다(2026-10-14 1.5.0 에서 실제로 겪음)"""
        s, _, popened = self.session([])
        s._edge_open('https://accounts.google.com/')
        self.assertFalse(any('remote-debugging' in a for a in popened[0]))

    def test_edge_pids_only_this_profile_browser(self):
        s, _, _ = self.session([])
        prof = s.edge_profile
        procs = [
            mock.Mock(info={'pid': 10, 'name': 'msedge.exe', 'cmdline': ['msedge.exe', '--user-data-dir=' + prof, 'https://x']}),
            mock.Mock(info={'pid': 11, 'name': 'msedge.exe', 'cmdline': ['msedge.exe', '--type=renderer', '--user-data-dir=' + prof]}),
            mock.Mock(info={'pid': 12, 'name': 'msedge.exe', 'cmdline': ['msedge.exe', '--user-data-dir=' + prof + '-other']}),
            mock.Mock(info={'pid': 13, 'name': 'msedge.exe', 'cmdline': ['msedge.exe']}),
        ]
        self.assertEqual(s.edge_pids(process_iter=lambda attrs: procs), [10])

    def test_unknown_program_never_runs(self):
        s, opened, popened = self.session([{'kind': 'program', 'program': 'cmd'}])
        self.assertFalse(s.open_item(0)['ok'])
        self.assertEqual((opened, popened), ([], []))

    def test_end_closes_uploads_and_drops_tokens(self):
        calls = []
        s, _, _ = self.session([{'kind': 'space', 'path': '/timetable'}],
                               open_space=lambda path, sess: calls.append(path), close_space=lambda: calls.append('closed'))
        self.assertFalse(s.open_item(0)['ok'])                 # handoff 에 space_session 이 없다
        with mock.patch.object(classroom_setup, 'close_processes') as close:
            s.end()
        close.assert_called_once()
        self.assertIsNone(s.google_token())
        self.assertIn('closed', calls)
        self.assertFalse(os.path.exists(s.dir))

    def test_update_google_reconnects(self):
        s, _, _ = self.session([], google=False)
        self.assertFalse(s.drive_state()['connected'])
        s.update_google({'access_token': 'new', 'expires_at': time.time() + 3600, 'scope': 'https://www.googleapis.com/auth/drive'})
        self.assertEqual(s.google_token(), 'new')

    def test_sweep_closes_leftover_processes_first(self):
        leftover = os.path.join(self.tmp.name, 'old123')
        os.makedirs(os.path.join(leftover, 'edge-profile'))
        with mock.patch.object(classroom_setup, 'close_processes') as close:
            classroom_setup.sweep_leftovers()
        close.assert_called_once_with(self.tmp.name, [], wait=10)
        self.assertFalse(os.path.exists(leftover))

    def test_program_keys_match_web(self):
        web = 'D:/spacekijun/src/features/classroom-link/presetItems.ts'
        if not os.path.exists(web):
            self.skipTest('SPACEKIJUN 저장소 없음')
        with open(web, encoding='utf-8') as f:
            text = f.read()
        import re
        block = text.split('export const CLASSROOM_PROGRAMS', 1)[1].split('];', 1)[0]
        self.assertEqual(set(re.findall(r"key: '([a-z0-9_-]+)'", block)), set(classroom_setup.PROGRAMS))

    def test_safe_name(self):
        self.assertEqual(classroom_drive.safe_name('a/b:c?.pdf'), 'a_b_c_.pdf')
        self.assertEqual(classroom_drive.safe_name('', '.docx'), '파일.docx')


class VaultTest(unittest.TestCase):
    """구글 로그인 보관(A+) — 수업용 Edge 프로필을 잠가 남기고, 같은 열쇠로만 푼다"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(classroom_vault, 'PROFILES_DIR', os.path.join(self.tmp.name, 'profiles'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.key = __import__('base64').b64encode(os.urandom(32)).decode()
        self.ref = 'r' * 24

    def profile(self, root):
        for rel, data in (('Default/Network/Cookies', b'COOKIES'), ('Local State', b'{}'),
                          ('Default/Cache/Cache_Data/big', b'X' * 1000), ('Default/LOCK', b'')):
            path = os.path.join(root, *rel.split('/'))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
        return root

    def test_roundtrip_keeps_login_and_drops_cache(self):
        src = self.profile(os.path.join(self.tmp.name, 'edge'))
        classroom_vault.save(src, self.ref, self.key)
        with open(classroom_vault.blob_path(self.ref), 'rb') as f:
            self.assertNotIn(b'COOKIES', f.read())           # 암호문 — 평문이 보이지 않는다
        dest = os.path.join(self.tmp.name, 'restored')
        self.assertTrue(classroom_vault.restore(self.ref, self.key, dest))
        with open(os.path.join(dest, 'Default', 'Network', 'Cookies'), 'rb') as f:
            self.assertEqual(f.read(), b'COOKIES')
        self.assertFalse(os.path.exists(os.path.join(dest, 'Default', 'Cache')))   # 캐시는 빼고 묶었다
        self.assertFalse(os.path.exists(os.path.join(dest, 'Default', 'LOCK')))

    def test_wrong_key_deletes_blob(self):
        classroom_vault.save(self.profile(os.path.join(self.tmp.name, 'edge')), self.ref, self.key)
        other = __import__('base64').b64encode(os.urandom(32)).decode()
        with self.assertRaises(classroom_vault.VaultError):
            classroom_vault.restore(self.ref, other, os.path.join(self.tmp.name, 'x'))
        self.assertFalse(os.path.exists(classroom_vault.blob_path(self.ref)))
        self.assertFalse(classroom_vault.restore(self.ref, self.key, os.path.join(self.tmp.name, 'y')))

    def test_bad_ref_and_sweep(self):
        with self.assertRaises(classroom_vault.VaultError):
            classroom_vault.blob_path('../../evil')
        classroom_vault.save(self.profile(os.path.join(self.tmp.name, 'edge')), self.ref, self.key)
        classroom_vault.sweep(now=time.time() + 61 * 86400)
        self.assertFalse(os.path.exists(classroom_vault.blob_path(self.ref)))


class GoogleSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, name, value in ((classroom_setup, 'SESSIONS_DIR', os.path.join(self.tmp.name, 's')),
                                    (classroom_vault, 'PROFILES_DIR', os.path.join(self.tmp.name, 'p'))):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.profile = {'ref': 'q' * 24, 'key': __import__('base64').b64encode(os.urandom(32)).decode()}

    def session(self, profile=True):
        handoff = {'teacher': {'name': '김교사', 'email': 'kim@myschool.hs.kr'}, 'preset': {'title': 't', 'items': []}}
        if profile:
            handoff['profile'] = self.profile
        popened = []
        s = classroom_setup.Session(handoff, settings={}, drive_opener=FakeDriveServer({}),
                                    popen=lambda cmd: popened.append(cmd) or mock.Mock(pid=None),
                                    startfile=lambda p: None, edge='C:/Edge/msedge.exe')
        s.prepare()
        return s, popened

    def login(self, s, expires_in=3600 * 24 * 400):
        """Edge 쿠키 DB 흉내 — 구글 로그인 쿠키(SID) 한 줄. 값은 Edge 가 암호화하므로 이름·만료만 본다"""
        import sqlite3
        cookie = os.path.join(s.edge_profile, 'Default', 'Network', 'Cookies')
        os.makedirs(os.path.dirname(cookie), exist_ok=True)
        if os.path.exists(cookie):
            os.remove(cookie)
        con = sqlite3.connect(cookie)
        con.execute('create table cookies (host_key text, name text, encrypted_value blob, expires_utc integer, has_expires integer)')
        expires = int((time.time() + expires_in + classroom_vault.CHROME_EPOCH) * 1e6)
        con.execute("insert into cookies values ('.google.com', 'SID', x'00', ?, 1)", (expires,))
        con.commit()
        con.close()

    def test_login_is_kept_for_next_class_on_this_pc(self):
        s, popened = self.session()
        self.assertFalse(s.google_restored)
        self.assertEqual(s.open_google(), {'ok': True})
        self.assertIn('Email=kim%40myschool.hs.kr', popened[0][-1])        # 이메일을 채워 둔 로그인
        self.login(s)
        with mock.patch.object(classroom_setup, 'close_processes'):
            s.end()
        self.assertFalse(os.path.exists(s.dir))                         # 풀린 프로필은 지웠다
        nxt, opened = self.session()                                    # 같은 PC·같은 선생님의 다음 수업
        self.assertTrue(nxt.google_restored)
        self.assertEqual(s.end_login, 'saved')                          # 끝날 때 «보관했습니다»
        self.assertEqual(nxt.login, 'restored')                         # 구글 창에 «불러왔습니다»
        self.assertEqual(nxt.snapshot()['google']['login'], 'restored')
        nxt.open_google()                                               # 풀었으면 로그인 화면이 아니라 곧장 구글
        self.assertEqual(opened[-1][-1], 'https://www.google.com/')
        nxt.open_google(login=True)                                     # 휴대폰으로 입력은 로그인 화면이 필요하다
        self.assertIn('accounts.google.com/ServiceLogin', opened[-1][-1])

    def test_graceful_close_has_no_tree_flag(self):
        """taskkill /T 는 자식이 있으면 점잖은 종료를 거절한다 — Edge 가 늘 강제로 죽어 쿠키를 잃었다"""
        with mock.patch.object(classroom_setup.subprocess, 'run') as run:
            classroom_setup._taskkill(42, force=False)
            classroom_setup._taskkill(42, force=True)
        self.assertEqual(run.call_args_list[0].args[0], ['taskkill', '/PID', '42'])
        self.assertEqual(run.call_args_list[1].args[0], ['taskkill', '/PID', '42', '/T', '/F'])

    def test_forget_button_only_when_this_pc_has_a_login(self):
        s, _ = self.session()                                           # 처음 쓰는 기기 — 보관 모드여도 지울 게 없다
        self.assertFalse(s.snapshot()['google']['saved'])
        s.open_google()
        self.login(s)
        self.assertTrue(s.snapshot()['google']['saved'])                # 이번 수업에 로그인했다
        with mock.patch.object(classroom_setup, 'close_processes'):
            s.end()
        nxt, _ = self.session()
        self.assertTrue(nxt.snapshot()['google']['saved'])              # 보관을 풀었다
        with mock.patch.object(classroom_setup, 'close_edge'):
            nxt.forget_google()
        self.assertFalse(nxt.snapshot()['google']['saved'])

    def test_no_profile_means_nothing_kept(self):
        s, _ = self.session(profile=False)
        self.login(s)
        with mock.patch.object(classroom_setup, 'close_processes'):
            s.end()
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, 'p')) and os.listdir(os.path.join(self.tmp.name, 'p')))

    def test_forget_then_login_again_is_kept(self):
        """«지우기» 뒤 다시 로그인하면 끝날 때 보관한다 — 1.5.4 까지는 이번 수업을 남기지 않아 로그인이 사라졌다(2026-10-14 사용자 보고)"""
        s, _ = self.session()
        self.login(s)
        with mock.patch.object(classroom_setup, 'close_processes'):
            s.end()
        old = classroom_vault.blob_path(self.profile['ref'])
        s, _ = self.session()
        with mock.patch.object(classroom_setup, 'close_edge'):
            s.forget_google()
        self.assertFalse(os.path.exists(s.edge_profile))                # 지금 로그인도
        self.assertFalse(os.path.exists(old))                           # 보관본도 지웠다
        self.assertEqual(s.login, 'cleared')
        self.login(s)                                                   # 지운 뒤 다시 로그인
        with mock.patch.object(classroom_setup, 'close_processes'):
            s.end()
        self.assertEqual(s.end_login, 'saved')
        nxt, _ = self.session()
        self.assertEqual(nxt.login, 'restored')

    def test_end_without_login_says_so(self):
        s, _ = self.session()
        self.login(s, expires_in=-60)                                   # 만료된 쿠키만 — 로그인 안 된 채 끝
        with mock.patch.object(classroom_setup, 'close_processes'):
            s.end()
        self.assertEqual(s.end_login, 'empty')
        nxt, _ = self.session()
        self.assertEqual(nxt.login, 'restored_empty')                   # «보관본에 로그인이 없었습니다»

    def test_google_login_in_reads_names_only(self):
        s, _ = self.session()
        self.assertFalse(classroom_vault.google_login_in(s.edge_profile))   # 쿠키 DB 없음
        self.login(s)
        self.assertTrue(classroom_vault.google_login_in(s.edge_profile))
        with open(os.path.join(s.edge_profile, 'Default', 'Network', 'Cookies'), 'wb') as f:
            f.write(b'not a database')
        self.assertIsNone(classroom_vault.google_login_in(s.edge_profile))  # 못 읽으면 «모름»

    def test_controller_forget_keeps_server_key(self):
        c, sessions = controller([APPROVED])
        c.step(); c.step()
        sessions[0].forget_google = mock.Mock()
        sessions[0].profile = {'ref': 'r' * 20, 'key': 'k'}
        c.client.forget_profile = mock.Mock()
        self.assertEqual(c.forget_google(), {'ok': True})
        c.client.forget_profile.assert_not_called()                    # 서버 열쇠는 그대로 — 다시 로그인하면 보관
        sessions[0].forget_google.assert_called_once()
        self.assertIn('새로 보관', c.notice)


class IconTest(unittest.TestCase):
    """독의 실제 아이콘 — 설치된 실행 파일에서 뽑기 · 항목별 출처"""

    def test_extracts_png_from_windows_exe(self):
        import shutil
        exe = shutil.which('notepad.exe')
        if not exe:
            self.skipTest('notepad 없음')
        png = classroom_icons.exe_icon_png(exe, 64)
        self.assertTrue(png and png[1:4] == b"PNG")

    def test_item_icon_sources(self):
        s = classroom_setup.Session({'teacher': {}, 'preset': {'items': []}}, settings={}, edge='x')
        with mock.patch.object(classroom_icons, 'favicon', return_value='data:fav') as fav, \
                mock.patch.object(classroom_icons, 'drive_type_icon', return_value='data:drive') as drv:
            self.assertEqual(s._icon_for({'kind': 'url', 'url': 'https://classroom.google.com/', 'app': 'classroom'}),
                             'icons/google/classroom.png')
            self.assertEqual(s._icon_for({'kind': 'url', 'url': 'https://padlet.com/', 'site': 'padlet'}), 'icons/sites/padlet.png')
            self.assertEqual(s._icon_for({'kind': 'url', 'url': 'https://padlet.com/x'}), 'data:fav')
            fav.assert_called_once_with('https://padlet.com/x')
            self.assertEqual(s._icon_for({'kind': 'drive', 'id': 'x', 'mimeType': 'application/pdf'}), 'data:drive')
            drv.assert_called_once_with('application/pdf')
            self.assertEqual(s._icon_for({'kind': 'space', 'path': '/'}), 'icons/spacekijun.png')
            self.assertIsNone(s._icon_for({'kind': 'program', 'program': 'nope'}))

    def test_bundled_google_icons_exist(self):
        web = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'icons', 'google')
        for key in list(classroom_setup.GOOGLE_APPS) + ['google']:
            self.assertTrue(os.path.exists(os.path.join(web, key + '.png')), key)


class UpdateTest(unittest.TestCase):
    """교실판 자동 업데이트 — 데스크의 updater 를 교실판 채널로 바꿔 끼운다"""

    def setUp(self):
        from core import updater
        self.updater = updater
        self.saved = {k: getattr(updater, k) for k in ('APP', 'CHANNEL', 'PUBLIC_URL', 'PART')}
        self.addCleanup(lambda: [setattr(updater, k, v) for k, v in self.saved.items()])

    def signed(self, app, seed):
        from core import ed25519
        data = b'x' * 10
        import hashlib
        manifest = {'app': app, 'version': '1.2.0', 'size': 10, 'sha256': hashlib.sha256(data).hexdigest(),
                    'parts': [{'name': f'{app}.exe.part1', 'size': 10, 'sha256': hashlib.sha256(data).hexdigest()}]}
        return {'manifest': manifest, 'signature': ed25519.sign(seed, self.updater.canonical(manifest)).hex()}

    def test_points_updater_at_classroom_channel(self):
        from core import classroom_update, ed25519
        classroom_update.configure()
        self.assertTrue(self.updater.PUBLIC_URL.endswith('/desk-releases/classroom'))
        seed = os.urandom(32)
        key = ed25519.public_key(seed)
        self.assertEqual(self.updater.check_manifest(self.signed('SpacekijunClassroom', seed), key)['version'], '1.2.0')
        with self.assertRaises(self.updater.UpdateError):          # 데스크 목록은 교실판이 받지 않는다
            self.updater.check_manifest(self.signed('SpacekijunDesk', seed), key)

    def test_does_nothing_when_running_from_source(self):
        from core import classroom_update
        self.assertFalse(classroom_update.at_start([]))           # 실행 파일이 아니면 바꿀 것이 없다
        self.assertIsNone(classroom_update.start_checker(lambda r: None))


class StartupTest(unittest.TestCase):
    """교실판 Windows 자동 실행 — 처음엔 켜고, 끈 것은 그대로, 옮긴 실행 파일은 새 자리로"""

    def run_ensure(self, settings, registered=None, frozen=True, managed=False):
        from core import classroom_startup as st
        calls = []
        with mock.patch.object(st, 'load_settings', return_value=settings),                 mock.patch.object(st, 'managed', return_value=managed),                 mock.patch.object(st, 'registered_command', return_value=registered),                 mock.patch.object(st, 'command', return_value='"C:/new/SpacekijunClassroom.exe" --autostart'),                 mock.patch.object(st, 'set_enabled', side_effect=lambda v, remember=True: calls.append((v, remember))),                 mock.patch.object(st.sys, 'frozen', frozen, create=True):
            st.ensure()
        return calls

    def test_first_run_turns_on(self):
        self.assertEqual(self.run_ensure({}), [(True, True)])

    def test_source_run_does_not_register(self):
        self.assertEqual(self.run_ensure({}, frozen=False), [])

    def test_opt_out_is_respected(self):
        self.assertEqual(self.run_ensure({'autostart': False}), [])

    def test_moved_exe_is_re_registered(self):
        self.assertEqual(self.run_ensure({'autostart': True}, registered='"C:/old/x.exe" --autostart'), [(True, False)])
        self.assertEqual(self.run_ensure({'autostart': True}, registered='"C:/new/SpacekijunClassroom.exe" --autostart'), [])

    def test_school_managed_is_left_alone(self):
        self.assertEqual(self.run_ensure({}, managed=True), [])


class AlwaysOnTest(unittest.TestCase):
    """항상 켜져 있게 — ✕ 는 내리기, 갑자기 죽으면 다시 켜기(1분 안에 또 죽으면 멈춤)"""

    def test_restart_only_for_exe_and_not_in_a_loop(self):
        import classroom
        with tempfile.TemporaryDirectory() as folder:
            log = os.path.join(folder, 'startup-error.log')
            self.assertFalse(classroom.restart_after_crash(log))            # 소스에서 돌 때는 다시 켜지 않는다
            spawned = []
            fake_child = mock.Mock(DETACHED=8, spawn=lambda args, cwd, flags: spawned.append(args))
            with mock.patch.object(classroom.sys, 'frozen', True, create=True), \
                    mock.patch.dict(sys.modules, {'core.child': fake_child}), \
                    mock.patch('core.child', fake_child, create=True):
                self.assertTrue(classroom.restart_after_crash(log))
                self.assertIn('--wait-pid', spawned[0])                      # 새것은 옛것이 잠금을 놓기를 기다린다
                self.assertFalse(classroom.restart_after_crash(log))         # 1분 안에 또 → 되풀이하지 않는다

    def test_qr_screen_points_to_new_web_menu(self):
        web = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'classroom.html')
        with open(web, encoding='utf-8') as f:
            html = f.read()
        self.assertIn('교실 기기', html)
        self.assertNotIn('프로필 → 교실 기기 세팅', html)                    # 옛 자리(프로필)를 가리키지 않는다
        self.assertIn('id="quit-dialog"', html)


class MiniWidgetTest(unittest.TestCase):
    """QR 창을 내리면 바탕화면 오른쪽 아래에 작은 위젯(2026-10-14 요청)"""

    def _windows(self):
        import classroom
        made = []

        def create_window(title, url, **kw):
            window = mock.Mock(events=mock.Mock(shown=mock.MagicMock(), closed=mock.MagicMock()))
            made.append((url, kw, window))
            return window
        fake = mock.Mock(create_window=create_window)
        windows = classroom.Windows(mock.Mock())
        return classroom, windows, fake, made

    def test_shows_once_at_bottom_right_and_restores(self):
        classroom, windows, fake, made = self._windows()
        with mock.patch.dict(sys.modules, {'webview': fake}), \
                mock.patch.object(classroom, 'work_area', return_value=(0, 0, 1920, 1040)):
            windows.lowered = True
            windows.show_mini()
            windows.show_mini()                                   # 두 번 내려도 하나
        self.assertEqual(len(made), 1)
        url, kw, mini = made[0]
        self.assertTrue(url.endswith('classroom-mini.html'))
        width, height = classroom.MINI_SIZE
        self.assertEqual((kw['x'], kw['y']), (1920 - width - 16, 1040 - height - 16))   # 작업 표시줄 바로 위 오른쪽
        self.assertFalse(kw.get('on_top', False))                # 바탕화면 위젯 — 다른 창을 가리지 않는다
        self.assertFalse(kw['focus'])
        windows.restore_main()
        mini.destroy.assert_called_once()
        windows.main.restore.assert_called_once()
        windows.main.maximize.assert_called_once()
        self.assertFalse(windows.lowered)
        self.assertIsNone(windows.mini)

    def test_lowered_qr_never_comes_back_by_itself(self):
        """내려 둔 QR 창은 손 놓은 시간과 상관없이 저절로 다시 뜨지 않는다 (2026-10-21 요청 — 위젯에 QR 이 있다)"""
        classroom, windows, fake, made = self._windows()
        with mock.patch.dict(sys.modules, {'webview': fake}), \
                mock.patch.object(classroom, 'work_area', return_value=(0, 0, 1920, 1040)):
            windows.lower()
        self.assertTrue(windows.lowered)
        self.assertEqual(len(made), 1)                            # 위젯
        with open(classroom.__file__, encoding='utf-8') as f:
            source = f.read()
        self.assertNotIn('RESTORE_IDLE', source)
        self.assertEqual(source.count('restore_main()'), 1)       # 위젯의 [QR 크게 보기](Api.restore_main)에서만

    def test_wired_to_minimize_and_bundled(self):
        root = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(root, 'classroom.py'), encoding='utf-8') as f:
            src = f.read()
        self.assertIn('window.events.minimized += minimized', src)
        self.assertIn('window.events.restored += restored', src)
        self.assertIn('minimized=True', src)                     # 켤 때 내려 둔 채(위젯만)
        with open(os.path.join(root, '..', 'SpacekijunClassroom.spec'), encoding='utf-8') as f:
            spec = f.read()
        for name in ('classroom-mini.html', 'classroom-mini.css', 'classroom-mini.js'):
            self.assertIn(name, spec)


class ScalingTest(unittest.TestCase):
    """화면 배율 150% — 창 자리는 논리 픽셀로(pywebview 가 배율을 곱한다). 물리 픽셀을 그대로 쓰면 오른쪽 아래로 밀렸다"""

    def test_work_area_is_logical(self):
        import classroom

        class FakeUser32:
            def GetDpiForSystem(self):
                return 144                                  # 150%

            def SystemParametersInfoW(self, action, _, rect, __):
                r = rect._obj
                r.left, r.top, r.right, r.bottom = 0, 0, 2560, 1380      # 1440 - 작업 표시줄 60(물리)
                return 1

            def GetSystemMetrics(self, i):
                return 0
        with mock.patch.object(classroom.ctypes, 'WinDLL', return_value=FakeUser32()):
            self.assertEqual(classroom.work_area(), (0, 0, 1707, 920))

    def test_dock_is_centered_in_work_area(self):
        import classroom
        made = []
        fake = mock.Mock(create_window=lambda title, url, **kw: made.append(kw) or mock.Mock(events=mock.Mock(shown=mock.MagicMock())))
        windows = classroom.Windows(mock.Mock())
        state = {'phase': 'session', 'session': {'items': [{}] * 3}}
        with mock.patch.dict(sys.modules, {'webview': fake}), \
                mock.patch.object(classroom, 'work_area', return_value=(0, 0, 1707, 920)):
            windows.arrange(state)
        kw = made[0]
        self.assertLessEqual(abs(kw['x'] * 2 + kw['width'] - 1707), 1)      # 가운데(1px 반올림)
        self.assertEqual(kw['y'] + kw['height'], 920 - 12)                 # 작업 표시줄 바로 위


class GoogleToolsTest(unittest.TestCase):
    """구글 수업 도구의 API 다리 — 허용한 주소만, 쓰기는 클래스룸 공지 하나(core/google_tools.py)"""

    def test_allow_list(self):
        from core import google_tools as gt
        ok = [('GET', 'https://classroom.googleapis.com/v1/courses?teacherId=me'),
              ('GET', 'https://classroom.googleapis.com/v1/courses/123/courseWork/9/studentSubmissions?pageSize=300'),
              ('GET', 'https://forms.googleapis.com/v1/forms/abc/responses?pageSize=5000'),
              ('GET', 'https://classroom.googleapis.com/v1/userProfiles/me'),
              ('GET', 'https://slides.googleapis.com/v1/presentations/abc/pages/p1/thumbnail?thumbnailProperties.thumbnailSize=LARGE'),
              ('GET', "https://www.googleapis.com/drive/v3/files?q=mimeType%3D'x'"),
              ('POST', 'https://classroom.googleapis.com/v1/courses/123/announcements')]
        bad = [('DELETE', 'https://classroom.googleapis.com/v1/courses/123'),
               ('POST', 'https://classroom.googleapis.com/v1/courses/123/courseWork'),
               ('POST', 'https://www.googleapis.com/drive/v3/files?x=1'),
               ('GET', 'https://www.googleapis.com/drive/v3/files/abc?alt=media'),       # 내려받기는 드라이브 탐색기로만
               ('GET', 'https://evil.example/v1/courses'),
               ('GET', 'https://classroom.googleapis.com/v1/courses/../../x'),
               ('GET', 'https://gmail.googleapis.com/gmail/v1/users/me/messages')]
        for method, url in ok:
            self.assertTrue(gt.allowed(method, url), url)
        for method, url in bad:
            self.assertFalse(gt.allowed(method, url), url)

    def _http_error(self, code, text):
        import io
        import urllib.error
        return urllib.error.HTTPError('u', code, 'x', {}, io.BytesIO(text.encode()))

    def test_errors_become_reasons(self):
        from core import google_tools as gt
        url = 'https://classroom.googleapis.com/v1/courses?teacherId=me'
        cases = [(401, '', 'auth'), (403, '{"error":{"status":"PERMISSION_DENIED","details":[{"reason":"SERVICE_DISABLED"}]}}', 'disabled'),
                 (403, '{"error":{"details":[{"reason":"ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}', 'scope'), (404, '', 'notfound')]
        for code, text, reason in cases:
            def opener(req, timeout=0, code=code, text=text):
                raise self._http_error(code, text)
            r = gt.call('tok', 'GET', url, None, opener)
            self.assertEqual(r['reason'], reason, code)
            self.assertNotIn('tok', json.dumps(r))
        disabled = gt.explain(403, 'SERVICE_DISABLED', 'https://slides.googleapis.com/v1/presentations/x')
        self.assertEqual(disabled['api'], 'Google Slides')
        self.assertEqual(gt.call(None, 'GET', url)['reason'], 'auth')

    def test_post_sends_only_text_and_state(self):
        from core import google_tools as gt
        seen = {}

        class Res:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"id":"1"}'

        def opener(req, timeout=0):
            seen['body'] = json.loads(req.data)
            seen['auth'] = req.get_header('Authorization')
            return Res()
        r = gt.call('tok', 'POST', 'https://classroom.googleapis.com/v1/courses/1/announcements',
                    {'text': '내일 준비물', 'state': 'DRAFT', 'assigneeMode': 'INDIVIDUAL_STUDENTS'}, opener)
        self.assertTrue(r['ok'])
        self.assertEqual(seen['body'], {'text': '내일 준비물', 'state': 'PUBLISHED'})
        self.assertEqual(seen['auth'], 'Bearer tok')
        self.assertFalse(gt.call('tok', 'POST', 'https://classroom.googleapis.com/v1/courses/1/announcements', {'text': ' '})['ok'])

    def test_classroom_tiles_open_tools(self):
        import classroom
        session = mock.Mock(items=[{'kind': 'url', 'app': 'forms', 'url': 'https://docs.google.com/forms/'},
                                   {'kind': 'url', 'url': 'https://padlet.com/'}])
        controller = mock.Mock(session=session)
        controller.open_item.return_value = {'ok': True}
        windows = mock.Mock()
        api = classroom.Api(controller, mock.Mock(), windows)
        self.assertEqual(api.open_item(0), {'ok': True})
        windows.show_gtools.assert_called_once_with('forms')
        controller.open_item.assert_not_called()
        api.open_item(1)
        controller.open_item.assert_called_once_with(1)


class ManualUpdateTest(unittest.TestCase):
    """기기 설정의 [새 판 확인]·[지금 바꾸기](2026-10-14 요청)"""

    def _api(self, phase='qr', checker=None, record=None, install=True):
        import classroom
        controller = mock.Mock()
        controller.state.return_value = {'phase': phase}
        windows = mock.Mock()
        windows.updates = {'record': record, 'checker': checker}
        windows.install_update = mock.Mock(return_value=install)
        return classroom.Api(controller, mock.Mock(), windows), windows

    def test_check_downloads_and_reports_version(self):
        checker = mock.Mock()
        checker.check_once.return_value = {'version': '9.9.9'}
        api, windows = self._api(checker=checker)
        self.assertEqual(api.check_update(), {'ok': True, 'version': '9.9.9'})
        self.assertEqual(windows.updates['record'], {'version': '9.9.9'})

    def test_check_when_latest(self):
        checker = mock.Mock()
        checker.check_once.return_value = None
        api, _ = self._api(checker=checker)
        self.assertEqual(api.check_update(), {'ok': True, 'version': None})

    def test_no_checker_when_running_from_source(self):
        api, _ = self._api(checker=None)
        self.assertFalse(api.check_update()['ok'])

    def test_install_only_outside_class(self):
        api, windows = self._api(phase='session', record={'version': '9.9.9'})
        self.assertFalse(api.install_update()['ok'])
        windows.install_update.assert_not_called()
        api, windows = self._api(phase='qr', record={'version': '9.9.9'})
        self.assertTrue(api.install_update()['ok'])
        windows.install_update.assert_called_once()
        api, windows = self._api(phase='qr', record=None)
        self.assertFalse(api.install_update()['ok'])


class PhoneTypeTest(unittest.TestCase):
    """휴대폰으로 구글 비밀번호 입력 — 휴대폰(웹 typeCrypto.ts)이 봉한 것을 이 PC 가 풀고, 로그인 칸에 넣는다"""
    # spacekijun 의 sealForDevice 로 만든 표본(scripts/classroom-link-test 와 같은 규칙)
    VECTOR = {"priv": "7d1c3a5e9b2f4c6d8e0a1b3c5d7e9f0a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e",
              "pub": "BLzIUtRepqNBH2Prw3KSwbMS-un_DUq_WcuJjGbH_9igST43CYKnyRC-qCReCbX2_EBd-c_Gn5qqSK8HAX2SxcE",
              "code": "VectorCode_0123456789ab",
              "epk": "BIsxg7G8hIm1CoEUC1apS_z13nE-Dh2wuG3G24Vp4IwA_jMGqHPIhBmoSVk-GZGAJG0woXe1fCrEZVlt3wLIsa0",
              "iv": "rmsR6qwD7EyRMwGa", "ct": "Smt5pvsOkYMHL2zcMc6BT85f8RHxIXRmvfEE4qdZWDKKMdTi7AzRVrg"}

    def test_opens_what_the_phone_sealed(self):
        from core.classroom_type import TypeKey
        key = TypeKey.from_hex(self.VECTOR['priv'])
        self.assertEqual(key.public, self.VECTOR['pub'])
        self.assertEqual(key.open(self.VECTOR['code'], self.VECTOR), '교실 비밀번호 P@ss!')
        with self.assertRaises(Exception):
            key.open('other-code', self.VECTOR)            # 표가 다르면 풀리지 않는다

    class FakeUi:
        """구글 로그인 화면 흉내 — UIA 대신"""
        def __init__(self, url, password=False, identifier=None, account=False, buttons=1):
            self.u, self.has_pw, self.ident, self.has_account, self.buttons = url, password, identifier, account, buttons
            self.log = []
        def url(self, doc): return self.u
        def password(self, doc): return 'pw' if self.has_pw else None
        def identifier(self, doc): return 'id' if self.ident is not None else None
        def account(self, doc, email): return 'acct' if self.has_account else None
        def next_button(self, doc): return 'next' if self.buttons == 1 else None
        def value(self, el): return self.ident or ''
        def set_value(self, el, text): self.log.append(('set', el, text))
        def invoke(self, el): self.log.append(('invoke', el))

    def test_fill_step_password(self):
        from core.classroom_type import fill_step
        ui = self.FakeUi('https://accounts.google.com/v3/signin/challenge/pwd', password=True)
        self.assertEqual(fill_step(ui, 'doc', 't@myschool.hs.kr', 'P@ss'), 'password')
        self.assertEqual(ui.log, [('set', 'pw', 'P@ss'), ('invoke', 'next')])

    def test_fill_step_never_types_into_other_sites(self):
        from core.classroom_type import fill_step
        for url in ('https://padlet.com/login', 'https://accounts.google.com.evil.example/', 'http://accounts.google.com/'):
            ui = self.FakeUi(url, password=True)
            self.assertEqual(fill_step(ui, 'doc', 't@myschool.hs.kr', 'P@ss'), 'none')
            self.assertEqual(ui.log, [])

    def test_fill_step_next_button_ambiguous(self):
        """[다음] 후보가 0개·2개 이상이면 누르지 않는다 — 넣기만 하고 선생님이 누른다"""
        from core.classroom_type import fill_step
        ui = self.FakeUi('https://accounts.google.com/x', password=True, buttons=2)
        self.assertEqual(fill_step(ui, 'doc', '', 'P@ss'), 'password_manual')
        self.assertEqual(ui.log, [('set', 'pw', 'P@ss')])
        ui = self.FakeUi('https://accounts.google.com/x', identifier='', buttons=0)
        self.assertEqual(fill_step(ui, 'doc', 't@myschool.hs.kr', 'P@ss'), 'wait')

    def test_fill_step_email_then_chooser(self):
        from core.classroom_type import fill_step
        ui = self.FakeUi('https://accounts.google.com/v3/signin/identifier', identifier='')
        self.assertEqual(fill_step(ui, 'doc', 't@myschool.hs.kr', 'P@ss'), 'email')
        self.assertEqual(ui.log, [('set', 'id', 't@myschool.hs.kr'), ('invoke', 'next')])
        ui = self.FakeUi('https://accounts.google.com/v3/signin/identifier', identifier='t@myschool.hs.kr')   # 미리 채워 둔 이메일
        self.assertEqual(fill_step(ui, 'doc', 't@myschool.hs.kr', 'P@ss'), 'email')
        self.assertEqual(ui.log, [('invoke', 'next')])
        ui = self.FakeUi('https://accounts.google.com/accountchooser', account=True)
        self.assertEqual(fill_step(ui, 'doc', 't@myschool.hs.kr', 'P@ss'), 'chooser')

    def test_signed_in_email_from_account_button(self):
        """구글 페이지 계정 단추로 로그인 상태 — 이메일 · ''(로그인 단추) · None(모름)"""
        from core import classroom_type as ct
        ui = mock.Mock()
        for found, want in ((['kim@myschool.hs.kr'], 'kim@myschool.hs.kr'), ([''], ''), (['', 'kim@myschool.hs.kr'], 'kim@myschool.hs.kr'), ([], None)):
            ui.account_emails.return_value = found
            self.assertEqual(ct.signed_in_email([1], ui), want)
        self.assertIsNone(ct.signed_in_email([], ui))
        self.assertEqual(ct.ACCOUNT_LABEL.search('Google 계정: 김교사  (Kim@myschool.hs.kr)').group(1), 'Kim@myschool.hs.kr')
        self.assertEqual(ct.ACCOUNT_LABEL.search('Google Account: Kim (kim@myschool.hs.kr)').group(1), 'kim@myschool.hs.kr')
        self.assertTrue(ct.SIGN_IN_LABEL.fullmatch('로그인') and not ct.SIGN_IN_LABEL.fullmatch('로그인 없이 바로'))

    def test_phone_fill_marks_login(self):
        import classroom
        from core.classroom_type import TypeKey
        key = TypeKey.from_hex(self.VECTOR['priv'])
        controller = mock.Mock()
        controller.session = mock.Mock(email='t@myschool.hs.kr')
        controller.client.type_poll.return_value = {'status': 'sent', 'payload': {k: self.VECTOR[k] for k in ('epk', 'iv', 'ct')}}
        api = classroom.Api(controller, mock.Mock(), mock.Mock())
        api._type = {'code': self.VECTOR['code'], 'key': key}
        with mock.patch('core.classroom_type.fill_in_edge', return_value='manual'):
            self.assertEqual(api.type_poll(), {'ok': True, 'status': 'filled', 'manual': True})
        controller.session.mark_phone_login.assert_called_once()

    def test_fill_in_edge_walks_to_password(self):
        from core import classroom_type as ct
        ui = self.FakeUi('https://accounts.google.com/v3/signin/identifier', identifier='t@myschool.hs.kr')
        ui.google_docs = lambda pids: ['doc']
        orig_invoke = ui.invoke
        def invoke(el):
            orig_invoke(el)
            ui.has_pw = True                               # [다음] 뒤 비밀번호 화면
        ui.invoke = invoke
        self.assertEqual(ct.fill_in_edge([1], 't@myschool.hs.kr', 'P@ss', sleep=lambda s: None, ui=ui), 'ok')
        self.assertIn(('set', 'pw', 'P@ss'), ui.log)
        ui = self.FakeUi('https://accounts.google.com/x')
        ui.google_docs = lambda pids: []
        self.assertEqual(ct.fill_in_edge([1], 'a', 'b', timeout=0.05, sleep=lambda s: None, ui=ui), ct.NOT_FOUND)
        self.assertIn('수업용 Edge', ct.fill_in_edge([], 'a', 'b', ui=ui))
        ui = self.FakeUi('https://accounts.google.com/v3/signin/identifier', identifier='nobody@x')   # 계정 없음 — 계속 이메일 화면
        ui.google_docs = lambda pids: ['doc']
        self.assertEqual(ct.fill_in_edge([1], 'nobody@x', 'P@ss', sleep=lambda s: None, ui=ui), ct.STUCK_EMAIL)

    def test_poll_fills_and_forgets(self):
        import classroom
        from core.classroom_type import TypeKey
        key = TypeKey.from_hex(self.VECTOR['priv'])
        controller = mock.Mock()
        controller.session = mock.Mock(email='t@myschool.hs.kr')
        controller.session.edge_pids.return_value = [4321]
        controller.client.type_poll.return_value = {'status': 'sent', 'payload': {k: self.VECTOR[k] for k in ('epk', 'iv', 'ct')}}
        api = classroom.Api(controller, mock.Mock(), mock.Mock())
        api._type = {'code': self.VECTOR['code'], 'key': key}
        with mock.patch('core.classroom_type.fill_in_edge', return_value='ok') as fill:
            self.assertEqual(api.type_poll(), {'ok': True, 'status': 'filled'})
        fill.assert_called_once_with([4321], 't@myschool.hs.kr', '교실 비밀번호 P@ss!')
        self.assertIsNone(api._type)                         # 한 번 쓰고 버린다
        controller.client.type_poll.return_value = {'status': 'pending'}
        self.assertEqual(api.type_poll()['status'], 'none')

class WebFilesTest(unittest.TestCase):
    def test_classroom_scripts_parse(self):
        """화면 스크립트 문법 — 한 군데만 깨져도 독·탐색기가 빈 창으로 뜬다(2026-10-14 실제로 겪음)"""
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('node 없음')
        web = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
        for name in ('classroom.js', 'classroom-dock.js', 'classroom-drive.js', 'classroom-popup.js', 'classroom-mini.js', 'gtools.js', 'classroom-gtools.js', 'classroom-type.js'):
            done = subprocess.run([node, '--check', os.path.join(web, name)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f'{name}: {done.stderr}')

    def test_no_native_dialogs(self):
        """confirm·alert 는 쓰지 않는다 — 독(높이 112) 안에 그려져 잘렸다(2026-10-14). api.ask·api.notify 로"""
        import re
        web = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
        for name in ('classroom-dock.js', 'classroom-drive.js', 'classroom-popup.js'):
            with open(os.path.join(web, name), encoding='utf-8') as f:
                self.assertIsNone(re.search(r'(?<![.\w])(confirm|alert)\(', f.read()), name)

    def test_google_app_keys_match_web(self):
        web = 'D:/spacekijun/src/features/classroom-link/presetItems.ts'
        if not os.path.exists(web):
            self.skipTest('SPACEKIJUN 저장소 없음')
        import re
        with open(web, encoding='utf-8') as f:
            text = f.read()
        block = text.split('export const GOOGLE_APPS', 1)[1].split('];', 1)[0]
        self.assertEqual(set(re.findall(r"key: '([a-z]+)'", block)), set(classroom_setup.GOOGLE_APPS))


if __name__ == '__main__':
    unittest.main()
