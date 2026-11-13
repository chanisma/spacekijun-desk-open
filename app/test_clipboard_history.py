"""클립보드 기록 — 쌓기·같은 것 올리기·고정·지우기·암호화 보관·지켜보기. 진짜 클립보드는 쓰지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명 파일에는 절대 닿지 않는다
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from core import clipboard_history as ch
import desktop
from desktop import DesktopAPI


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='spacekijun-clips-'))
        self.history = ch.History(self.folder)

    def test_text_files_and_images_are_kept_newest_first(self):
        self.history.add('text', '안녕하세요')
        self.history.add('files', [r'C:\자료\계획.hwpx', r'C:\자료\예산.xlsx'])
        self.history.add('image', Image.new('RGB', (40, 30), (10, 120, 200)))
        kinds = [row['kind'] for row in self.history.listing()]
        self.assertEqual(kinds, ['image', 'files', 'text'])
        image = self.history.listing()[0]
        self.assertTrue(image['thumb'].startswith('data:image/jpeg;base64,'))
        self.assertEqual((image['width'], image['height']), (40, 30))
        self.assertEqual(self.history.listing()[1]['files'], ['계획.hwpx', '예산.xlsx'])

    def test_copying_the_same_thing_again_moves_it_up_instead_of_duplicating(self):
        first = self.history.add('text', '같은 글')
        self.history.add('text', '다른 글')
        again = self.history.add('text', '같은 글')
        self.assertEqual(again['id'], first['id'])
        self.assertEqual([row['text'] for row in self.history.listing()], ['같은 글', '다른 글'])

    def test_history_is_stored_encrypted_and_survives_restart(self):
        self.history.add('text', '비밀 아닌 메모 1234')
        raw = (self.folder / ch.STORE).read_bytes()
        self.assertNotIn('메모 1234'.encode('utf-8'), raw)            # 파일에는 글이 그대로 남지 않는다
        self.assertEqual(ch.History(self.folder).listing()[0]['text'], '비밀 아닌 메모 1234')

    def test_pinned_items_survive_clear_and_trimming(self):
        keep = self.history.add('text', '고정')
        self.history.pin(keep['id'], True)
        with mock.patch.object(ch, 'MAX_ITEMS', 3):
            for number in range(6):
                self.history.add('text', f'글 {number}')
        texts = [row['text'] for row in self.history.listing()]
        self.assertIn('고정', texts)
        self.assertEqual(len(texts), 4)                                  # 고정 1 + 최근 3
        self.assertEqual(self.history.clear(), 3)
        self.assertEqual([row['text'] for row in self.history.listing()], ['고정'])

    def test_deleting_an_image_removes_its_file(self):
        item = self.history.add('image', Image.new('RGB', (8, 8)))
        path = self.history.image_path(item)
        self.assertTrue(path.exists())
        self.history.delete(item['id'])
        self.assertFalse(path.exists())
        with self.assertRaises(LookupError):
            self.history.get(item['id'])

    def test_search_finds_text_and_file_names(self):
        self.history.add('text', '교과협의회 회의록')
        self.history.add('files', [r'D:\보고서\협의회 결과.pdf'])
        self.history.add('text', '점심 메뉴')
        self.assertEqual(len(self.history.listing('협의회')), 2)
        self.assertEqual(self.history.listing('없는 말'), [])

    def test_version_changes_only_when_something_changes(self):
        before = self.history.version
        self.history.listing()
        self.assertEqual(self.history.version, before)
        self.history.add('text', 'x')
        self.assertGreater(self.history.version, before)


class RecorderTest(unittest.TestCase):
    def test_records_each_new_copy_and_skips_what_was_there_before(self):
        history = ch.History(Path(tempfile.mkdtemp(prefix='spacekijun-rec-')))
        numbers = iter([1, 1, 2, 2, 3, 3, 3, 3, 3, 3])
        contents = iter([('text', '처음 복사'), None])               # 두 번째는 '기록하지 말라' 표시 등
        with mock.patch.object(ch, 'POLL', 0.01), mock.patch.object(ch, 'SETTLE', 0.0), \
             mock.patch.object(ch, 'sequence', side_effect=lambda: next(numbers, 3)), \
             mock.patch.object(ch, 'read', side_effect=lambda: next(contents, None)):
            recorder = ch.Recorder(history)
            recorder.start()
            deadline = time.time() + 2
            while time.time() < deadline and not history.items:
                time.sleep(0.02)
            time.sleep(0.1)
            recorder.stop()
        self.assertEqual([row['text'] for row in history.listing()], ['처음 복사'])


class ClipsBridgeTest(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp(prefix='spacekijun-clipapi-'))
        patcher = mock.patch.object(desktop, 'CLIPS_DIR', folder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.api = DesktopAPI()
        self.api._preferences_path = folder / 'prefs.json'
        self.recorder = mock.patch('core.clipboard_history.Recorder.start')
        self.recorder.start()
        self.addCleanup(self.recorder.stop)

    def test_list_is_not_resent_when_nothing_changed(self):
        clips = self.api._clip_store()
        clips.add('text', '하나')
        first = self.api.call('clips_list', {'query': ''})['data']
        self.assertEqual([row['text'] for row in first['items']], ['하나'])
        same = self.api.call('clips_list', {'query': '', 'since': first['version'], 'query_was': '',
                                            'paused_was': first['paused']})['data']
        self.assertEqual(same, {'same': True})
        clips.add('text', '둘')
        again = self.api.call('clips_list', {'query': '', 'since': first['version'], 'query_was': '',
                                             'paused_was': first['paused']})['data']
        self.assertEqual(len(again['items']), 2)

    def test_pause_is_remembered(self):
        self.api._clip_store()
        with mock.patch.object(self.api._clip_recorder, 'stop') as stop:
            self.assertTrue(self.api.call('clips_pause', {'paused': True})['ok'])
        stop.assert_called_once()
        self.assertTrue(self.api._read_preferences()['clips_paused'])

    def test_copy_back_needs_the_dock(self):
        item = self.api._clip_store().add('text', '다시 쓰기')
        self.assertFalse(self.api.call('clips_copy', {'id': item['id']})['ok'])   # 독·패널 창이 없다
        self.assertFalse(self.api.call('clips_copy', {'id': 'nope'})['ok'])


if __name__ == '__main__':
    unittest.main()
