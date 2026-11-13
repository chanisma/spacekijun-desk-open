"""켰는데 화면이 안 뜰 때의 기록 · 먹통이 되지 않는 트레이 (2026-10-19)."""
from test_sandbox import use_sandbox
use_sandbox()
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop
from core import diagnostics
from desktop import DesktopAPI


class DiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='spacekijun-test-diag-'))
        self.addCleanup(lambda: __import__('shutil').rmtree(self.folder, ignore_errors=True))
        patcher = patch.object(desktop.watcher, 'DATA_DIR', str(self.folder))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.api = DesktopAPI()

    def test_report_has_versions_processes_logs_and_thread_stacks(self):
        path = diagnostics.write_hang_report(self.folder / 'startup-hang.log', '스페이스기전 데스크', '9.9.9', 45,
                                             [{'time': '10:00:00', 'text': '쪽지 감시 시작'}], debug_port=9)
        text = path.read_text(encoding='utf-8')
        for part in ('9.9.9', '45초', 'WebView2 런타임:', '디버그 포트 9', '쪽지 감시 시작', '스레드 위치:', 'test_report_has'):
            self.assertIn(part, text)

    def test_watch_writes_the_report_only_when_the_screen_never_came(self):
        with patch.object(self.api, '_tray_notify') as notify:
            self.api._watch_startup(0.2)
            deadline = time.time() + 5
            while not notify.called and time.time() < deadline:      # 기록을 쓴 뒤 트레이로 알린다
                time.sleep(0.05)
        self.assertTrue((self.folder / 'startup-hang.log').exists())
        notify.assert_called_once()
        self.assertIn('startup-hang.log', notify.call_args.args[0])
        # 다음에 화면이 제대로 뜨면 지난 기록을 지우고, 기다리던 감시는 아무것도 남기지 않는다
        fresh = DesktopAPI()
        fresh._ui_seen()
        self.assertFalse((self.folder / 'startup-hang.log').exists())
        with patch.object(fresh, '_tray_notify') as notify:
            fresh._watch_startup(0.1)
            time.sleep(0.4)
        notify.assert_not_called()
        self.assertFalse((self.folder / 'startup-hang.log').exists())

    def test_tray_actions_never_hold_the_tray_thread(self):
        release, done = threading.Event(), threading.Event()

        def stuck():                      # 화면 쪽이 멈춘 것처럼 오래 붙잡는 동작
            release.wait(5)
            done.set()
        started = time.monotonic()
        DesktopAPI._in_background(stuck)('icon', 'item')
        self.assertLess(time.monotonic() - started, 0.5)          # 트레이로 바로 돌아온다
        release.set()
        self.assertTrue(done.wait(2))

    def test_both_editions_wire_the_watch_and_background_tray(self):
        source = (Path(desktop.__file__)).read_text(encoding='utf-8')
        self.assertEqual(source.count('api._watch_startup('), 2)
        self.assertEqual(source.count("pystray.MenuItem('종료', api._in_background(quit_app))"), 2)
        self.assertEqual(source.count('api._exit_if_stuck()'), 2)


class WebPortTest(unittest.TestCase):
    """교사판·학생판이 한 PC 에서 함께 돌 때 서로의 화면 파일을 받지 않는다 (2026-10-20 — 학생판 독에 교사판 아이콘 목록)."""

    def test_each_edition_starts_its_own_page_server(self):
        source = Path(desktop.__file__).read_text(encoding='utf-8')
        self.assertIn("http_port=web_port(WEB_PORT['teacher'])", source)
        self.assertIn("http_port=web_port(WEB_PORT['student'])", source)
        self.assertNotEqual(desktop.WEB_PORT['teacher'], desktop.WEB_PORT['student'])
        self.assertEqual(desktop.WEB_PORT['teacher'], 42001)        # 교사판 창의 출처(localStorage)는 그대로

    def test_a_taken_port_is_skipped(self):
        import socket
        with socket.socket() as taken:
            taken.bind(('127.0.0.1', 0))
            taken.listen()
            busy = taken.getsockname()[1]
            port = desktop.web_port(busy, tries=3)
        self.assertNotEqual(port, busy)
        self.assertTrue(0 < port < 65536)


if __name__ == '__main__':
    unittest.main()
