"""데스크 메시지 (학생 ↔ 선생님, 2026-10-19) — 서버·진짜 계정에는 닿지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명 파일에는 절대 닿지 않는다
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop
from core import desk_message
from desktop import DesktopAPI

TEACHER = '11111111-1111-1111-1111-111111111111'
PHOTO = '33333333-3333-4333-8333-333333333333'
OTHER_PHOTO = '44444444-4444-4444-8444-444444444444'


def png_data():
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (3, 2), (200, 30, 30)).save(buffer, 'PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def gif_bytes():
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (3, 2)).save(buffer, 'GIF')
    return buffer.getvalue()
STUDENT = '22222222-2222-2222-2222-222222222222'


def row(id_, sender, label, body, time, read=False, quote=''):
    meta = {'sender_resource_id': sender, 'sender_label': label, 'sender_role': 'teacher'}
    if quote:
        meta['quote'] = quote
    return {'id': id_, 'title': '[메시지] ' + label, 'message': body, 'meta': meta, 'is_read': read, 'created_at': time}


class SentStoreMixin:
    def setUp(self):
        folder = tempfile.mkdtemp(prefix='spacekijun-test-messages-')
        self.addCleanup(lambda: __import__('shutil').rmtree(folder, ignore_errors=True))
        for patcher in (patch.object(desk_message, 'LEGACY_SENT_PATH', str(Path(folder) / 'sent.bin')),
                        patch.object(desk_message, 'IMAGE_INDEX', str(Path(folder) / 'images.json')),
                        patch('core.desk_message.supa_auth.load_session', return_value={'user_id': 'me-1'})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.folder = Path(folder)


class DeskMessageTest(SentStoreMixin, unittest.TestCase):
    def test_conversations_merge_received_and_sent_per_person(self):
        inbox = [desk_message.shape(row('n2', TEACHER, '김선생 선생님', '내일 와요', '2026-10-19T02:00:00+00:00')),
                 desk_message.shape(row('n1', TEACHER, '김선생 선생님', '질문 있어요?', '2026-10-19T01:00:00+00:00', read=True))]
        outbox = [{'id': 's1', 'to': TEACHER, 'to_label': '김선생 선생님', 'body': '네', 'time': '2026-10-19T01:30:00+00:00'},
                  {'id': 's2', 'to': STUDENT, 'to_label': '1학년 2반 3번 이학생', 'body': '안녕', 'time': '2026-10-19T00:10:00+00:00'}]
        threads = desk_message.conversations(inbox, outbox)
        self.assertEqual([t['id'] for t in threads], [TEACHER, STUDENT])           # 최근 대화가 위
        self.assertEqual([m['body'] for m in threads[0]['messages']], ['질문 있어요?', '네', '내일 와요'])
        self.assertEqual([m['mine'] for m in threads[0]['messages']], [False, True, False])
        self.assertEqual(threads[0]['unread'], 1)
        self.assertEqual(threads[1]['label'], '1학년 2반 3번 이학생')

    def test_send_checks_input_before_calling_the_server(self):
        with patch.object(desk_message, '_request') as request:
            for body, to in (('   ', TEACHER), ('가' * 1001, TEACHER), ('안녕', 'not-an-id')):
                with self.assertRaises(desk_message.MessageError):
                    desk_message.send(to, body)
            request.assert_not_called()

    def test_send_lets_the_server_pick_the_sender_and_keeps_nothing_on_this_pc(self):
        answer = {'notification_id': 'n-new', 'recipient_name': '김선생', 'recipient_linked': True}
        with patch.object(desk_message, '_request', return_value=answer) as request:
            desk_message.send(TEACHER, '  비밀 내용  ', '김선생 선생님')
        body = request.call_args.kwargs['body']
        self.assertEqual(body, {'p_recipient_resource_id': TEACHER, 'p_body': '비밀 내용',
                                'p_reply_to_notification_id': None, 'p_images': None})   # 보낸 사람은 서버가 정한다
        self.assertEqual(list(self.folder.iterdir()), [])                     # 이 PC 에는 남기지 않는다

    def test_sent_messages_come_from_the_server_so_every_pc_sees_them(self):
        rows = [{'id': 'n1', 'to': TEACHER, 'to_label': '김선생 선생님', 'body': '안녕하세요',
                 'time': '2026-10-21T01:00:00+00:00', 'read': True}]
        legacy = self.folder / 'sent.bin'
        legacy.write_bytes(b'old')
        with patch.object(desk_message, '_request', return_value=rows) as request:
            items = desk_message.sent()
        request.assert_called_once_with('POST', 'rpc/desk_message_sent', body={'p_limit': desk_message.SENT_KEEP})
        self.assertEqual(items, [{'id': 'n1', 'to': TEACHER, 'to_label': '김선생 선생님', 'body': '안녕하세요',
                                  'time': '2026-10-21T01:00:00+00:00', 'read': True, 'images': [],
                                  'photo_only': False, 'kind': ''}])
        self.assertFalse(legacy.exists())                                      # 예전 이 PC 사본은 지운다
        with patch.object(desk_message, '_request', return_value=None):
            with self.assertRaises(desk_message.MessageError):
                desk_message.sent()

    def test_photos_are_checked_sent_and_kept_in_the_capture_folder(self):
        """사진 (2026-10-22): 그림인지 열어 보고 보낸다. 보낸 사진은 캡처 보관함에 파일로 남긴다."""
        captures = self.folder / 'captures'
        answer = {'notification_id': 'n-new', 'recipient_name': '김선생', 'recipient_linked': True,
                  'images': [{'id': PHOTO, 'w': 3, 'h': 2}]}
        with patch.object(desk_message, '_request', return_value=answer) as request:
            desk_message.send(TEACHER, '', '김선생 선생님', images=[{'data': png_data()}], folder=captures)
        sent = request.call_args.kwargs['body']
        self.assertEqual(request.call_args.args[1], 'rpc/send_desk_message_v2')
        self.assertEqual(sent['p_body'], '')                                   # 사진만 보내도 된다
        self.assertEqual([(i['mime'], i['width'], i['height']) for i in sent['p_images']], [('image/png', 3, 2)])
        files = list(captures.iterdir())
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].name.startswith('메시지 사진 ') and files[0].name.endswith(' 김선생 선생님.png'))
        self.assertEqual(desk_message.local_path(captures, PHOTO), str(files[0]))
        # 다시 볼 때는 서버에 묻지 않는다
        with patch.object(desk_message, '_request') as request:
            shown = desk_message.image(captures, PHOTO)
        request.assert_not_called()
        self.assertTrue(shown['src'].startswith('data:image/jpeg;base64,'))
        full = desk_message.full_image(captures, PHOTO)                       # 크게 보기는 보관함의 원본 그대로
        self.assertEqual(base64.b64decode(full['src'].split(',', 1)[1]), files[0].read_bytes())
        self.assertTrue(full['src'].startswith('data:image/png;base64,'))
        # 캡처 보관함에서 이름을 바꿔도 따라간다
        moved = files[0].with_name('내 사진.png')
        files[0].rename(moved)
        desk_message.renamed(files[0].name, moved.name)
        self.assertEqual(desk_message.image(captures, PHOTO)['name'], '내 사진.png')
        # 보관함에서 지우면 다시 받아 오지 않는다
        moved.unlink()
        with patch.object(desk_message, '_request') as request:
            self.assertEqual(desk_message.image(captures, PHOTO), {'removed': True})
        request.assert_not_called()
        self.assertEqual(desk_message.full_image(captures, PHOTO), {'removed': True})

    def test_received_photo_is_fetched_once_and_kept_after_the_server_forgets_it(self):
        captures = self.folder / 'captures'
        row = {'id': PHOTO, 'mime': 'image/png', 'width': 3, 'height': 2, 'created_at': '2026-10-22T05:03:04+00:00',
               'data': png_data()}
        with patch.object(desk_message, '_request', return_value=row) as request:
            shown = desk_message.image(captures, PHOTO, '김선생 선생님')
        request.assert_called_once_with('POST', 'rpc/desk_message_image', body={'p_image_id': PHOTO})
        self.assertIn('김선생 선생님', shown['name'])
        with patch.object(desk_message, '_request', return_value=None):         # 7일이 지나 서버에서 지워져도
            self.assertIn('src', desk_message.image(captures, PHOTO))           # 본 사진은 남는다
            self.assertEqual(desk_message.image(captures, OTHER_PHOTO), {'expired': True})   # 안 본 것은 끝

    def test_bad_photos_are_refused_before_the_server(self):
        with patch.object(desk_message, '_request') as request:
            for images in ([{'data': base64.b64encode(b'not an image at all').decode()}],
                           [{'data': 'not base64 !!'}],
                           [{'data': png_data()}] * 5,
                           [{'data': base64.b64encode(gif_bytes()).decode()}],
                           'x'):
                with self.assertRaises(desk_message.MessageError):
                    desk_message.send(TEACHER, '안녕', images=images)
            with self.assertRaises(desk_message.MessageError):
                desk_message.image(self.folder, '../../etc')                    # id 모양이 아니면 받지 않는다
        request.assert_not_called()

    def test_photo_refs_from_the_notification_are_cleaned(self):
        record = row('n1', TEACHER, '김선생 선생님', '사진 1장', '2026-10-22T01:00:00+00:00')
        record['meta'].update({'images': [{'id': PHOTO, 'w': 3, 'h': 2}, {'id': '../x'}, 'junk'], 'photo_only': True})
        item = desk_message.shape(record)
        self.assertEqual(item['images'], [{'id': PHOTO, 'w': 3, 'h': 2}])
        self.assertTrue(item['photo_only'])
        self.assertEqual(item['body'], '사진 1장')                               # 트레이 알림·목록에 쓰는 글

    def test_limit_errors_returned_as_500_are_shown_as_written(self):
        """한 시간 한도(54000)·받는 사람 없음(P0002)은 PostgREST 가 500 으로 준다 — 그래도 글을 보인다."""
        import io
        import urllib.error
        for code, text in (('54000', '한 시간에 30건까지 보낼 수 있습니다'), ('P0002', '받는 사람을 찾을 수 없습니다')):
            error = urllib.error.HTTPError('u', 500, 'Server Error', {},
                                           io.BytesIO(json.dumps({'code': code, 'message': text}).encode()))
            with patch('core.desk_message.notify.config', return_value={'url': 'https://example.invalid'}),                  patch('core.desk_message.supa_auth.auth_headers', return_value={}),                  patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaisesRegex(desk_message.MessageError, text):
                    desk_message.send(TEACHER, '안녕')
        crash = urllib.error.HTTPError('u', 500, 'Server Error', {},
                                       io.BytesIO(json.dumps({'code': 'XX000', 'message': 'internal detail'}).encode()))
        with patch('core.desk_message.notify.config', return_value={'url': 'https://example.invalid'}),              patch('core.desk_message.supa_auth.auth_headers', return_value={}),              patch('urllib.request.urlopen', side_effect=crash):
            with self.assertRaisesRegex(desk_message.MessageError, '요청 실패 \(500\)'):   # 내부 오류 글은 숨긴다
                desk_message.send(TEACHER, '안녕')

    def test_server_errors_are_shown_as_written(self):
        import io
        import urllib.error
        error = urllib.error.HTTPError('u', 400, 'Bad Request', {},
                                       io.BytesIO(json.dumps({'message': '받는 사람을 찾을 수 없습니다'}).encode()))
        with patch('core.desk_message.notify.config', return_value={'url': 'https://example.invalid'}), \
             patch('core.desk_message.supa_auth.auth_headers', return_value={}), \
             patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaisesRegex(desk_message.MessageError, '받는 사람을 찾을 수 없습니다'):
                desk_message.send(TEACHER, '안녕')


class DeskMessageSessionTest(SentStoreMixin, unittest.TestCase):
    """처음 보낼 때 허락받기 (2026-10-31) — 서버 쪽 판정은 spacekijun supabase/tests/desk_message_session.sql."""

    def test_sessions_are_keyed_by_the_other_person(self):
        with patch.object(desk_message, '_request', return_value={'role': 'student', 'sessions': [
                {'peer': TEACHER, 'status': 'pending'}, {'status': 'active'}, 'bad']}):
            self.assertEqual(desk_message.sessions(), {'role': 'student', 'sessions': {TEACHER: 'pending'}})

    def test_request_needs_a_reason_and_a_real_teacher(self):
        with patch.object(desk_message, '_request') as request:
            for teacher, body in ((TEACHER, '   '), (TEACHER, 'x' * 1001), ('nope', '용건')):
                with self.assertRaises(desk_message.MessageError):
                    desk_message.request_permission(teacher, body)
            request.assert_not_called()

    def test_request_decide_and_end_call_the_server_functions(self):
        with patch.object(desk_message, '_request', return_value={}) as request:
            desk_message.request_permission(TEACHER, ' 질문 ')
            desk_message.decide(STUDENT, False)
            desk_message.end_session(STUDENT)
        self.assertEqual([call.args[1] for call in request.call_args_list],
                         ['rpc/desk_message_request', 'rpc/desk_message_decide', 'rpc/desk_message_end_session'])
        self.assertEqual(request.call_args_list[0].kwargs['body'], {'p_teacher_resource_id': TEACHER, 'p_body': '질문'})
        self.assertIs(request.call_args_list[1].kwargs['body']['p_approve'], False)

    def test_decide_refuses_anything_but_true_or_false(self):
        with patch.object(desk_message, '_request') as request, self.assertRaises(desk_message.MessageError):
            desk_message.decide(STUDENT, 'yes')
        request.assert_not_called()

    def test_kind_survives_only_when_known(self):
        record = row('n1', TEACHER, '김선생 선생님', '허락', '2026-10-31T01:00:00+00:00')
        self.assertEqual(desk_message.shape(record)['kind'], '')
        record['meta']['kind'] = 'session_event'
        self.assertEqual(desk_message.shape(record)['kind'], 'session_event')
        record['meta']['kind'] = '<b>'
        self.assertEqual(desk_message.shape(record)['kind'], '')

    def test_conversations_keep_kind_on_both_sides(self):
        inbox = [desk_message.shape({**row('n1', TEACHER, '김', '허락', '2026-10-31T02:00:00+00:00'),
                                     'meta': {'sender_resource_id': TEACHER, 'kind': 'session_event'}})]
        outbox = [{'id': 's1', 'to': TEACHER, 'to_label': '김', 'body': '용건', 'time': '2026-10-31T01:00:00+00:00',
                   'kind': 'session_request'}]
        self.assertEqual([m['kind'] for m in desk_message.conversations(inbox, outbox)[0]['messages']],
                         ['session_request', 'session_event'])


class DeskMessageBridgeTest(SentStoreMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.api = DesktopAPI()

    def test_both_editions_can_use_messages(self):
        for action in ('msg_state', 'msg_directory', 'msg_send', 'msg_read', 'msg_image', 'msg_image_full', 'msg_image_open',
                       'msg_request', 'msg_decide', 'msg_end'):
            self.assertIn(action, desktop.STUDENT_ACTIONS)
            self.assertIn(action, self.api._handlers())
        self.assertIn('messages', desktop.POPOVER_KEYS)
        items = (Path(desktop.WEB_DIR) / 'dock-items.js').read_text(encoding='utf-8')
        self.assertEqual(items.count('    MESSAGES,'), 2)                       # 교사판·학생판 독 모두

    def test_state_counts_unread_for_the_dock_badge(self):
        inbox = [desk_message.shape(row('n1', TEACHER, '김선생 선생님', '안녕', '2026-10-19T01:00:00+00:00'))]
        with patch('desktop.supa_auth.whoami', return_value='student@school'), \
             patch('core.desk_message.received', return_value=inbox),              patch('core.desk_message.sent', return_value=[]), \
             patch('core.desk_message.sessions', return_value={'role': 'student', 'sessions': {TEACHER: 'active'}}):
            data = self.api.call('msg_state')['data']
        self.assertEqual(data['unread'], 1)
        self.assertEqual((data['role'], data['sessions']), ('student', {TEACHER: 'active'}))
        with patch('desktop.supa_auth.whoami', return_value='student@school'), \
             patch('core.desk_message.received', return_value=inbox), patch('core.desk_message.sent', return_value=[]), \
             patch('core.desk_message.sessions', side_effect=desk_message.MessageError('없음')):
            self.assertIsNone(self.api.call('msg_state')['data']['sessions'])      # 서버가 아직 옛 판이어도 메시지는 보인다
        self.assertEqual(self.api.call('dock_state')['data']['badges']['messages'], 1)
        with patch('core.desk_message.mark_read') as mark:
            self.assertTrue(self.api.call('msg_read', {'ids': ['n1']})['ok'])
        mark.assert_called_once_with(['n1'])
        self.assertEqual(self.api.call('dock_state')['data']['badges']['messages'], 0)

    def test_new_messages_are_announced_once(self):
        first = [desk_message.shape(row('n1', TEACHER, '김선생 선생님', '첫 메시지', '2026-10-19T01:00:00+00:00'))]
        second = [desk_message.shape(row('n2', TEACHER, '김선생 선생님', '두 번째', '2026-10-19T02:00:00+00:00'))] + first
        with patch('desktop.supa_auth.load_session', return_value={'user_id': 'me-1'}), \
             patch.object(self.api, '_msg_notify') as notify:
            with patch('core.desk_message.unread_after', return_value=first):
                self.api._msg_check()
                self.api._msg_check()                                          # 같은 것은 다시 알리지 않는다
            with patch('core.desk_message.unread_after', return_value=second):
                self.api._msg_check()
        self.assertEqual([c.args[1] for c in notify.call_args_list], ['김선생 선생님: 첫 메시지', '두 번째'])
        self.assertEqual(self.api._msg_unread, 2)

    def test_realtime_and_polling_announce_each_message_once(self):
        """Realtime 으로 바로 알린 것은 2분 확인이 다시 알리지 않는다 (시각 표기가 달라 id 로 기억한다)."""
        record = row('n9', TEACHER, '김선생 선생님', '바로 온 메시지', '2026-10-19T05:00:00.123+00:00')
        with patch('desktop.supa_auth.load_session', return_value={'user_id': 'me-1'}), \
             patch.object(self.api, '_msg_notify') as notify, patch.object(self.api, '_msg_changed') as changed:
            with patch('core.desk_message.unread_after', return_value=[]):
                self.api._msg_check()                                          # 켤 때 — 안 읽은 것 없음
            self.api._msg_arrived(record)
            self.api._msg_arrived(record)                                      # 같은 것이 또 와도 한 번
            same = desk_message.shape({**record, 'created_at': '2026-10-19T14:00:00.123+09:00'})
            with patch('core.desk_message.unread_after', return_value=[same]):
                self.api._msg_check()
        self.assertEqual([c.args for c in notify.call_args_list], [('메시지 · 김선생 선생님', '바로 온 메시지')])
        self.assertEqual(changed.call_count, 1)
        self.assertEqual(self.api._msg_unread, 1)

    def test_settings_icon_shows_a_dot_when_an_update_is_ready(self):
        self.assertFalse(self.api.call('dock_state')['data']['badges']['update'])
        self.api._update = {'version': '9.9.9'}
        self.assertTrue(self.api.call('dock_state')['data']['badges']['update'])
        items = (Path(desktop.WEB_DIR) / 'dock-items.js').read_text(encoding='utf-8')
        self.assertEqual(items.count("key: 'settings', glyph: 'gear', tone: 'silver', badge: 'update'"), 2)   # 교사판·학생판

    def test_send_tells_when_the_recipient_never_signed_in(self):
        with patch('core.desk_message.send', return_value={'notification_id': 'x', 'recipient_name': '이학생',
                                                           'recipient_linked': False}) as send:
            message = self.api.call('msg_send', {'to': STUDENT, 'body': '안녕', 'label': '1학년 2반 3번 이학생'})['data']
        self.assertIn('로그인하면 볼 수 있습니다', message)
        send.assert_called_once_with(STUDENT, '안녕', '1학년 2반 3번 이학생', None, None, desktop.CAPTURE_DIR)


if __name__ == '__main__':
    unittest.main()
