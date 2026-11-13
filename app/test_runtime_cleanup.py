import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import playwright
from core.runtime_cleanup import stop_owned_drivers


class CleanupTests(unittest.TestCase):
    def test_only_owned_exact_driver_is_stopped_and_waited_for(self):
        driver, other = MagicMock(), MagicMock()
        driver.exe.return_value = str(Path(playwright.__file__).parent / 'driver' / 'node.exe')
        other.exe.return_value = 'C:/unrelated/node.exe'
        with patch('core.runtime_cleanup.psutil.Process') as current, \
             patch('core.runtime_cleanup.psutil.wait_procs', return_value=([], [])) as wait:
            current.return_value.children.return_value = [driver, other]
            stop_owned_drivers()
        driver.terminate.assert_called_once()
        other.terminate.assert_not_called()
        wait.assert_any_call([driver], timeout=3)

    def test_driver_still_running_is_killed_and_reaped(self):
        driver = MagicMock()
        driver.exe.return_value = str(Path(playwright.__file__).parent / 'driver' / 'node.exe')
        with patch('core.runtime_cleanup.psutil.Process') as current, \
             patch('core.runtime_cleanup.psutil.wait_procs', side_effect=[([], [driver]), ([driver], [])]) as wait:
            current.return_value.children.return_value = [driver]
            stop_owned_drivers()
        driver.kill.assert_called_once()
        wait.assert_any_call([driver], timeout=2)
