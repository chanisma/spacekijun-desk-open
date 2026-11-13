"""Windowed executable entry point, with an isolated packaged-runtime check."""
import ctypes
import os
from pathlib import Path
import sys
import traceback


def run():
    # Windowed builds have no console streams; libraries may still write to them.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    if len(sys.argv) == 3 and sys.argv[1] == '--shutdown-test':
        # Offline regression probe: leave a bundled driver running at exit.
        # The outer finally must reap it before the onefile parent removes _MEI.
        import json
        import subprocess
        import playwright
        driver = Path(playwright.__file__).parent / 'driver' / 'node.exe'
        child = subprocess.Popen([str(driver), '-e', 'setInterval(()=>{},1000)'],
                                 creationflags=subprocess.CREATE_NO_WINDOW,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Path(sys.argv[2]).write_text(json.dumps({'pid': child.pid,
            'runtime': str(Path(playwright.__file__).parent.parent)}), encoding='utf-8')
        return
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from packaging_check import check
        check(Path(sys.argv[2]))
        return
    # 받아 둔 새 판이 설치 모드로 떴다 — 옛것을 기다려 제자리에 덮어쓰고 새 판을 띄운 뒤 끝난다.
    # 잠금(뮤텍스)을 잡기 전에 한다: 옛것이 아직 잡고 있다 (core/updater.py install_main)
    if '--install-update' in sys.argv:
        from core import edition, updater
        updater.install_main(sys.argv[1:], Path(edition.DATA_DIR) / 'update')
        return

    # 실행 파일을 그냥 두 번 눌러 켜면 **독**으로 시작한다 (스페이스기전-독.bat 과 같다).
    # 데스크 본창은 독의 '데스크'·트레이 메뉴로 연다 — 다른 인자로 켜져도 본창은 숨긴 채 (desktop.py main).
    # 자동 실행(--autostart)은 기억한 대로.
    if getattr(sys, 'frozen', False) and len(sys.argv) == 1:
        sys.argv.append('--dock')
    # 새 판으로 막 바뀌었다 — 옛 판이 끝나 한 번에 하나 잠금을 놓을 때까지 기다린다 (core/updater.py)
    if '--after-update' in sys.argv:
        at = sys.argv.index('--after-update')
        if at + 1 < len(sys.argv) and sys.argv[at + 1].isdigit():
            from core import updater
            updater.wait_for(int(sys.argv[at + 1]))

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, 'Local\\SpacekijunDeskWeb')
    if mutex and ctypes.get_last_error() == 183:
        if '--dock' in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, '스페이스기전 데스크가 이미 실행 중입니다. 트레이 아이콘을 오른쪽 클릭해 ‘독 표시’를 켜 주세요.', '스페이스기전 독', 64)
        elif '--autostart' not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, '이미 실행 중입니다. 작업 표시줄 또는 트레이에서 스페이스기전 데스크를 열어 주세요.', '스페이스기전 데스크', 64)
        kernel.CloseHandle(mutex)
        return
    try:
        from desktop import main
        main()
    except Exception:
        log = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SpacekijunDesk' / 'startup-error.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding='utf-8')
        ctypes.windll.user32.MessageBoxW(None, f'프로그램을 실행하지 못했습니다. Microsoft Edge WebView2 Runtime 설치를 확인해 주세요.\n\n오류 기록: {log}', '스페이스기전 데스크', 16)
    finally:
        if mutex:
            kernel.CloseHandle(mutex)


if __name__ == '__main__':
    try:
        run()
    finally:
        # Daemon login threads may still be waiting on browser windows at exit.
        # The onefile parent must not remove _MEI while its node.exe is alive.
        from core.runtime_cleanup import stop_owned_drivers
        stop_owned_drivers()
