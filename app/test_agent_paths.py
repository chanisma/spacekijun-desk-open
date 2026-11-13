"""파일·폴더 주소 누르면 열기 (2026-11-09 요청) — 있는 것만 고르고, 실행 파일은 열지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import agent_paths


class ResolveTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.root = Path(room.name)
        (self.root / '자동화 업무' / '성적').mkdir(parents=True)
        (self.root / '자동화 업무' / '성적' / '2학기 성적.xlsx').write_text('x', encoding='utf-8')
        (self.root / 'app' / 'web').mkdir(parents=True)
        (self.root / 'app' / 'web' / 'x.js').write_text('x', encoding='utf-8')
        (self.root / 'notes.txt').write_text('x', encoding='utf-8')

    def hit(self, text, folder=None):
        found = agent_paths.resolve(str(self.root) if folder is None else folder, text)
        return found and (found['text'], Path(found['path']).relative_to(self.root.resolve()).as_posix(), found['dir'])

    def test_absolute_with_spaces_cut_at_the_longest_existing(self):
        whole = str(self.root / '자동화 업무' / '성적' / '2학기 성적.xlsx')
        self.assertEqual(self.hit(whole + ' 에 저장했습니다.'), (whole, '자동화 업무/성적/2학기 성적.xlsx', False))
        folder = str(self.root / '자동화 업무')
        self.assertEqual(self.hit(folder + ' 폴더를 보세요')[2], True)

    def test_relative_trailing_marks_line_numbers_and_particles(self):
        self.assertEqual(self.hit('app/web/x.js:12:3')[0], 'app/web/x.js')
        self.assertEqual(self.hit('app\\web\\x.js).')[0], 'app\\web\\x.js')
        self.assertEqual(self.hit('notes.txt를')[0], 'notes.txt')
        self.assertEqual(self.hit('@notes.txt')[0], '@notes.txt')

    def test_missing_unc_and_no_folder(self):
        self.assertIsNone(self.hit('없는파일.txt'))
        self.assertIsNone(self.hit('\\\\server\\share\\a.txt'))
        self.assertIsNone(agent_paths.resolve('', 'notes.txt'))
        self.assertIsNone(self.hit(str(self.root / '자료없음')))       # 폴더 이름을 깎아 위 폴더를 고르지 않는다
        self.assertEqual(len(agent_paths.check(str(self.root), ['notes.txt'] * 100)), agent_paths.MAX_ITEMS)


class OpenTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.root = Path(room.name)

    def test_runnable_files_are_only_shown_in_explorer(self):
        for name, expected in (('run.bat', 'revealed'), ('setup.EXE', 'revealed'), ('표.xlsx', 'file'), ('보고서.pdf', 'file')):
            (self.root / name).write_text('x', encoding='utf-8')
            with patch('os.startfile', create=True) as start, patch('subprocess.Popen') as popen:
                self.assertEqual(agent_paths.open_path(str(self.root / name)), expected, name)
                self.assertEqual(start.called, expected == 'file')
                self.assertEqual(popen.called, expected == 'revealed')
        with patch('os.startfile', create=True) as start:
            self.assertEqual(agent_paths.open_path(str(self.root)), 'folder')
            start.assert_called_once()
        with patch('subprocess.Popen') as popen:
            self.assertEqual(agent_paths.open_path(str(self.root / '표.xlsx'), reveal=True), 'revealed')
        with self.assertRaises(ValueError):
            agent_paths.open_path('notes.txt')
        with self.assertRaises(ValueError):
            agent_paths.open_path(str(self.root / 'none.txt'))


class DesktopTests(unittest.TestCase):
    def test_actions_registered_for_both_editions(self):
        import desktop
        handlers = desktop.DesktopAPI()._handlers()
        for name in ('term_paths', 'term_path_open'):
            self.assertIn(name, handlers)
            self.assertIn(name, desktop.STUDENT_ACTIONS)


if __name__ == '__main__':
    unittest.main()
