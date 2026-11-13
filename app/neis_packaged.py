"""나이스 전용 실행 파일의 시작점.

창만 있는 프로그램이라 표준 출력이 없다. 없는 곳에 쓰다 터지지 않게 먼저 막아 둔다.
진행 상황은 창 제목에, 실패는 화면 위 띠에 적는다.
"""
import os
import sys
import traceback


def run() -> int:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    try:
        from neis_desk import run as start
        return start()
    except Exception:
        # 창도 못 띄운 상황이다. 남길 곳이 여기밖에 없다.
        spot = os.path.join(os.path.expandvars('%LOCALAPPDATA%'), 'SpacekijunDesk')
        os.makedirs(spot, exist_ok=True)
        with open(os.path.join(spot, 'neis-desk-error.txt'), 'w', encoding='utf-8') as note:
            note.write(traceback.format_exc())
        return 1


if __name__ == '__main__':
    raise SystemExit(run())
