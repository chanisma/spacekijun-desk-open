"""데스크 화면 파일이 WebView2 의 옛 사본으로 뜨지 않는지 (2026-10-08 사용자 보고)."""
import tempfile
import time
import unittest
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path

from core import web_cache


class NoStoreTest(unittest.TestCase):
    def test_local_files_are_sent_with_no_store(self):
        from webview.http import BottleServer
        web_cache.install()
        url, _, _ = BottleServer.start_server(
            [str(Path(__file__).parent / 'web' / 'index.html')], None)
        base = url.rsplit('/', 1)[0]
        for name in ('index.html', 'app.js', 'sticky.js'):
            for _ in range(20):
                try:
                    response = urllib.request.urlopen(f'{base}/{name}', timeout=5)
                    break
                except (urllib.error.URLError, ConnectionError):
                    time.sleep(0.1)
            self.assertIn('no-store', response.headers.get('Cache-Control', ''), name)


class PurgeTest(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.profile = Path(room.name)
        self.default = self.profile / 'EBWebView' / 'Default'
        (self.default / 'Cache' / 'Cache_Data').mkdir(parents=True)
        (self.default / 'Cache' / 'Cache_Data' / 'old').write_text('옛 화면')
        (self.default / 'Cookies').write_text('로그인')

    def test_purges_once_and_keeps_login(self):
        self.assertTrue(web_cache.purge_stale(self.profile))
        self.assertFalse((self.default / 'Cache').exists())
        self.assertTrue((self.default / 'Cookies').exists())
        (self.default / 'Cache').mkdir()            # 새 정책으로 다시 쌓인 캐시는 두고 본다
        self.assertTrue(web_cache.purge_stale(self.profile))
        self.assertTrue((self.default / 'Cache').exists())

    def test_locked_cache_is_retried_next_time(self):
        with unittest.mock.patch('core.web_cache.shutil.rmtree',
                                 side_effect=lambda path, onerror: onerror(None, str(path), None)):
            self.assertFalse(web_cache.purge_stale(self.profile))
        self.assertFalse((self.profile / 'web-cache-policy').exists())


if __name__ == '__main__':
    unittest.main()
