"""캡처 보관함 — 파일 다루기와 데스크 연결부. 진짜 캡처 화면·클립보드·휴지통은 쓰지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명 파일에는 절대 닿지 않는다
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from core import capture
import desktop
from desktop import DesktopAPI


def picture(path: Path, size=(40, 30), color=(200, 30, 30)):
    Image.new('RGB', size, color).save(path)
    return path


class CaptureFilesTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='spacekijun-captures-'))
        self.addCleanup(lambda: [p.unlink() for p in self.folder.iterdir()] and None)

    def test_save_never_overwrites(self):
        with mock.patch('core.capture.datetime') as clock:
            clock.now.return_value.strftime.return_value = '2026-10-11 21.00.00'
            first = capture.save(self.folder, Image.new('RGB', (10, 10)))
            second = capture.save(self.folder, Image.new('RGB', (10, 10)))
        self.assertEqual(first.name, '캡처 2026-10-11 21.00.00.png')
        self.assertEqual(second.name, '캡처 2026-10-11 21.00.00 (2).png')

    def test_items_are_newest_first_with_thumbnails(self):
        old = picture(self.folder / 'a.png')
        new = picture(self.folder / 'b.png', size=(800, 600))
        (self.folder / 'notes.txt').write_text('not a picture')
        import os
        os.utime(old, (1_000_000, 1_000_000))
        listed = capture.items(self.folder)
        self.assertEqual([item['name'] for item in listed], ['b.png', 'a.png'])
        self.assertEqual((listed[0]['width'], listed[0]['height']), (800, 600))
        self.assertTrue(listed[0]['thumb'].startswith('data:image/jpeg;base64,'))

    def test_resolve_stays_inside_the_folder(self):
        picture(self.folder / 'shot.png')
        self.assertEqual(capture.resolve(self.folder, 'shot.png'), self.folder / 'shot.png')
        for bad in ('../shot.png', 'C:\\Windows\\win.ini', '', None, 3, '..'):
            with self.assertRaises(ValueError, msg=bad):
                capture.resolve(self.folder, bad)
        with self.assertRaises(LookupError):
            capture.resolve(self.folder, 'missing.png')
        (self.folder / 'notes.txt').write_text('x')
        with self.assertRaises(LookupError):
            capture.resolve(self.folder, 'notes.txt')

    def test_rename_keeps_extension_and_refuses_clashes(self):
        picture(self.folder / 'one.png')
        picture(self.folder / 'two.png')
        self.assertEqual(capture.rename(self.folder, 'one.png', '  회의 자료 ').name, '회의 자료.png')
        self.assertEqual(capture.rename(self.folder, '회의 자료.png', '표지.png').name, '표지.png')
        with self.assertRaises(FileExistsError):
            capture.rename(self.folder, '표지.png', 'two')
        for bad in ('', '   ', 'a/b', 'what?', 'CON', '가' * 200):
            with self.assertRaises(ValueError, msg=bad):
                capture.rename(self.folder, '표지.png', bad)
        # 대소문자만 바꾸기는 된다
        self.assertEqual(capture.rename(self.folder, 'two.png', 'TWO').name, 'TWO.png')

    def test_signature_changes_when_files_change(self):
        empty = capture.signature(self.folder)
        picture(self.folder / 'a.png')
        filled = capture.signature(self.folder)
        self.assertNotEqual(empty, filled)
        self.assertEqual(filled, capture.signature(self.folder))


class SnipTest(unittest.TestCase):
    """Windows 캡처 화면 대신 가짜 클립보드·화면으로 기다리기를 시험한다."""
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='spacekijun-snip-'))
        self.sequence = [1]
        for name, fake in (('_clipboard_sequence', lambda: self.sequence[0]),
                           ('time', mock.Mock(monotonic=self.clock, sleep=self.tick))):
            patcher = mock.patch.object(capture, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.now = 0.0
        self.events = {}

    def clock(self):
        return self.now

    def tick(self, seconds):
        self.now += seconds
        for at, event in list(self.events.items()):
            if self.now >= at:
                event()
                del self.events[at]

    def test_saves_the_picture_that_arrives_on_the_clipboard(self):
        shot = Image.new('RGB', (64, 48), (0, 120, 255))
        self.events[1.0] = lambda: self.sequence.__setitem__(0, 2)
        with mock.patch.object(capture, '_clipboard_image', return_value=shot):
            path = capture.snip(self.folder, threading.Event(), launch=lambda: None, overlay=lambda: True)
        self.assertTrue(path.exists())
        with Image.open(path) as saved:
            self.assertEqual(saved.size, (64, 48))

    def test_text_on_the_clipboard_is_ignored(self):
        self.events[0.5] = lambda: self.sequence.__setitem__(0, 2)      # 글자를 복사했다
        with mock.patch.object(capture, '_clipboard_image', return_value=None):
            path = capture.snip(self.folder, threading.Event(), wait=3, launch=lambda: None,
                                overlay=lambda: True)
        self.assertIsNone(path)

    def test_closing_the_overlay_without_a_picture_cancels_quickly(self):
        shown = [True]
        self.events[2.0] = lambda: shown.__setitem__(0, False)            # Esc
        with mock.patch.object(capture, '_clipboard_image', return_value=None):
            path = capture.snip(self.folder, threading.Event(), wait=120, launch=lambda: None,
                                overlay=lambda: shown[0])
        self.assertIsNone(path)
        self.assertLess(self.now, 2.0 + capture.CLOSE_GRACE + 1)       # 2분을 다 기다리지 않는다


class CaptureBridgeTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='spacekijun-bridge-'))
        patcher = mock.patch.object(desktop, 'CAPTURE_DIR', self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.api = DesktopAPI()

    def test_list_skips_resending_an_unchanged_folder(self):
        picture(self.folder / 'a.png')
        first = self.api.call('capture_list', {})['data']
        self.assertEqual([item['name'] for item in first['items']], ['a.png'])
        self.assertEqual(self.api.call('capture_list', {'signature': first['signature']})['data'], {'same': True})
        # 막 찍은 캡처가 있으면 같아도 다시 보내고, 그것을 알려 준다
        self.api._capture_fresh = 'a.png'
        again = self.api.call('capture_list', {'signature': first['signature']})['data']
        self.assertEqual(again['fresh'], 'a.png')

    def test_rename_and_delete_go_through_the_folder_rules(self):
        picture(self.folder / 'a.png')
        picture(self.folder / 'b.png')
        self.assertEqual(self.api.call('capture_rename', {'name': 'a.png', 'to': '새 이름'})['data'],
                         {'name': '새 이름.png'})
        self.assertFalse(self.api.call('capture_rename', {'name': 'b.png', 'to': '새 이름'})['ok'])
        with mock.patch.object(capture, 'recycle') as recycle:
            self.assertTrue(self.api.call('capture_delete', {'names': ['새 이름.png', 'b.png']})['ok'])
        recycle.assert_called_once_with([self.folder / '새 이름.png', self.folder / 'b.png'])
        with mock.patch.object(capture, 'recycle') as recycle:
            self.assertFalse(self.api.call('capture_delete', {'names': ['../secret.png']})['ok'])
            self.assertFalse(self.api.call('capture_delete', {'names': []})['ok'])
            self.assertFalse(self.api.call('capture_delete', {'names': 'b.png'})['ok'])
        recycle.assert_not_called()

    def test_open_hands_the_file_to_windows(self):
        picture(self.folder / 'a.png')
        with mock.patch('desktop.os.startfile') as start:
            self.assertTrue(self.api.call('capture_open', {'name': 'a.png'})['ok'])
        start.assert_called_once_with(str(self.folder / 'a.png'))

    def test_drag_needs_the_library_window(self):
        picture(self.folder / 'a.png')
        self.assertFalse(self.api.call('capture_drag', {'names': ['a.png']})['ok'])

    def test_a_second_capture_request_reuses_the_waiting_worker(self):
        waiting = threading.Event()
        with mock.patch.object(capture, 'snip', side_effect=lambda *a, **k: waiting.wait(2) and None), \
             mock.patch('desktop.os.startfile') as start:
            self.assertTrue(self.api.call('capture')['ok'])
            self.assertTrue(self.api.call('capture')['ok'])
            start.assert_called_once_with('ms-screenclip:')    # 두 번째는 화면만 다시 띄운다
            waiting.set()


if __name__ == '__main__':
    unittest.main()
