"""내려받은 파일을 놓을 자리. 진짜 다운로드 폴더에는 쓰지 않는다."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import downloads


class DownloadSpotTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='desk-download-test-'))

    def test_the_plain_case_keeps_the_name_the_server_gave(self):
        spot = downloads.spot_for('과목별출결_1학년7반.xlsx', self.folder)
        self.assertEqual(spot, self.folder / '과목별출결_1학년7반.xlsx')

    def test_a_name_already_there_steps_aside_like_a_browser(self):
        (self.folder / '자료.xlsx').write_text('먼저', encoding='utf-8')
        self.assertEqual(downloads.spot_for('자료.xlsx', self.folder).name, '자료 (2).xlsx')
        (self.folder / '자료 (2).xlsx').write_text('그다음', encoding='utf-8')
        self.assertEqual(downloads.spot_for('자료.xlsx', self.folder).name, '자료 (3).xlsx')

    def test_a_dangerous_name_cannot_walk_out_of_the_folder(self):
        """이름은 서버가 준 것이다. 그대로 믿고 붙이면 엉뚱한 자리에 쓸 수 있다."""
        for name in ('..\\..\\windows\\evil.exe', '../../etc/passwd', 'a:b*c?.txt'):
            spot = downloads.spot_for(name, self.folder)
            self.assertEqual(spot.parent, self.folder, name)

    def test_an_empty_name_still_gets_a_file(self):
        self.assertEqual(downloads.spot_for('', self.folder).name, '내려받은파일')
        self.assertEqual(downloads.spot_for('   ', self.folder).name, '내려받은파일')

    def test_the_folder_falls_back_when_windows_cannot_be_asked(self):
        with patch('winreg.OpenKey', side_effect=OSError('없음')):
            self.assertEqual(downloads.folder(), Path.home() / 'Downloads')


if __name__ == '__main__':
    unittest.main()
