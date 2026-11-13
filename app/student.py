"""스페이스기전 학생 — 학생판 입구 (SpacekijunStudent.exe · 스페이스기전-학생.bat).

학생이 쓰는 바로가기(스페이스기전·Google 클래스룸·기전시트온·리로스쿨)와 스페이스기전의 학생 기능
(다마고찌·별까지 쌓기·시간표·일정), 그리고 캡처·클립보드 도구만 담은 **독**이다. 교사만 쓰는 기능은
데스크 API 가 받지 않는다 (desktop.py `STUDENT_ACTIONS`).
"""
import os
import sys

# 🚨 어떤 모듈보다 먼저 판을 정한다 — 저장 폴더(%LOCALAPPDATA%/SpacekijunStudent)는 모듈을 불러올 때 정해진다
os.environ['SPACEKIJUN_EDITION'] = 'student'

import ctypes                     # noqa: E402
from pathlib import Path          # noqa: E402
import traceback                  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run():
    # 창만 있는 실행 파일에는 콘솔이 없다. 그래도 라이브러리가 쓸 수 있게 빈 곳으로 돌린다.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from student_check import check
        check(Path(sys.argv[2]))
        return

    from core import edition, updater
    # 받아 둔 새 판이 설치 모드로 떴다 — 옛것을 기다려 놓고 새 판을 띄운 뒤 끝난다 (잠금을 잡기 전에)
    if updater.INSTALL in sys.argv:
        updater.install_main(sys.argv[1:], Path(edition.DATA_DIR) / 'update')
        return
    # Intune 의 Program Files 판보다 새 판을 사용자 사본에 받아 두었으면 그쪽을 띄운다 (core/updater.py handoff).
    # 학교가 사용자 폴더의 실행 파일을 막았으면 띄우지 못하므로 이것으로 그대로 켠다.
    copy = updater.handoff(edition.VERSION) if getattr(sys, 'frozen', False) else None
    if copy is not None:
        try:
            updater.relaunch(copy, sys.argv[1:])
            return
        except OSError:
            pass
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, edition.MUTEX)
    if mutex and ctypes.get_last_error() == 183:
        if '--autostart' not in sys.argv:
            ctypes.windll.user32.MessageBoxW(
                None, '스페이스기전 학생이 이미 켜져 있습니다. 독이 가려져 있으면 Ctrl+Alt+D 를 누르거나 '
                '트레이 아이콘에서 ‘독 앞으로 가져오기’를 눌러 주세요.', edition.TITLE, 64)
        kernel.CloseHandle(mutex)
        return
    try:
        from desktop import main
        main()
    except Exception:
        log = Path(edition.DATA_DIR) / 'startup-error.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), encoding='utf-8')
        ctypes.windll.user32.MessageBoxW(
            None, f'프로그램을 실행하지 못했습니다. Microsoft Edge WebView2 Runtime 설치를 확인해 주세요.\n\n오류 기록: {log}',
            edition.TITLE, 16)
    finally:
        if mutex:
            kernel.CloseHandle(mutex)


if __name__ == '__main__':
    run()
