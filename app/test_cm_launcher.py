import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core import cm_launcher as launcher


class LauncherTests(unittest.TestCase):
    def test_ready_client_is_not_restarted(self):
        with patch.object(launcher, '_process', return_value=MagicMock()), \
             patch.object(launcher, '_ready', return_value=True), \
             patch.object(launcher.cm, 'main_window', return_value=123), \
             patch.object(launcher, '_launch') as launch:
            self.assertFalse(launcher.prepare()['needs_restart'])
            launch.assert_not_called()

    def test_existing_client_requires_confirmation(self):
        process=MagicMock()
        with patch.object(launcher, '_process', return_value=process), \
             patch.object(launcher, '_ready', return_value=False), \
             patch.object(launcher, '_listening', return_value=False), \
             patch.object(launcher, '_executable', return_value=Path('C:/CoolMessenger.exe')), \
             patch.object(launcher, '_launch') as launch:
            self.assertTrue(launcher.prepare()['needs_restart'])
            process.terminate.assert_not_called()
            launch.assert_not_called()

    def test_confirmed_restart_waits_then_launches(self):
        process=MagicMock();process.children.return_value=[]
        with patch.object(launcher, '_process', return_value=process), \
             patch.object(launcher, '_ready', side_effect=[False,True]), \
             patch.object(launcher, '_listening', return_value=False), \
             patch.object(launcher, '_executable', return_value=Path('C:/CoolMessenger.exe')), \
             patch.object(launcher, '_launch') as launch:
            self.assertFalse(launcher.prepare(restart=True)['needs_restart'])
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=5)
            launch.assert_called_once()

    def test_port_conflict_does_not_stop_existing_client(self):
        process=MagicMock()
        with patch.object(launcher, '_process', return_value=process), \
             patch.object(launcher, '_ready', return_value=False), \
             patch.object(launcher, '_listening', return_value=True):
            with self.assertRaises(RuntimeError): launcher.prepare(restart=True)
            process.terminate.assert_not_called()

    def test_missing_client_launches_without_bat(self):
        with patch.object(launcher, '_process', side_effect=[None, MagicMock()]), \
             patch.object(launcher, '_ready', side_effect=[False,True]), \
             patch.object(launcher, '_listening', return_value=False), \
             patch.object(launcher, '_executable', return_value=Path('C:/CoolMessenger.exe')), \
             patch.object(launcher, '_launch') as launch:
            self.assertFalse(launcher.prepare()['needs_restart'])
            launch.assert_called_once()
