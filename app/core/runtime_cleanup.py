"""Release this application's Playwright driver before the onefile loader cleans up."""
from pathlib import Path

import playwright
import psutil


def stop_owned_drivers():
    # Both ancestry and the exact executable path must match. Never stop another
    # desk instance, a user's Node server, or a normally launched browser.
    driver = (Path(playwright.__file__).parent / 'driver' / 'node.exe').resolve()
    owned = []
    for process in psutil.Process().children(recursive=True):
        try:
            if Path(process.exe()).resolve() == driver:
                process.terminate()
                owned.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    _, remaining = psutil.wait_procs(owned, timeout=3)
    for process in remaining:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(remaining, timeout=2)
