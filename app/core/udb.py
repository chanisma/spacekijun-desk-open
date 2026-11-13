"""
쿨메신저 쪽지 DB(`.udb`) 고르기 — **계정을 잘못 고르면 남의 쪽지를 읽는다.**

`%LOCALAPPDATA%\\CoolMessenger\\Memo\\` 에는 **계정마다 파일이 하나씩** 쌓인다.
    권민결.udb        34.4 MB   (이 PC 에서 현재 로그인)
    인공지능실.udb     20.2 MB   (예전에 로그인했던 계정)

예전에는 "가장 큰 파일"을 골랐는데 그건 계정과 아무 상관이 없다.
다른 PC 에서 인공지능실로 로그인했는데도 예전에 남아 있던 `권민결.udb` 를 읽어
**옛 쪽지가 그대로 보이는** 문제가 있었다(2026-09-10 확인).

지금은 **가장 최근에 쓰인 파일**을 고른다. 로그인 중인 계정의 DB 에는 앱이 계속 기록하므로
`.udb` / `-wal` / `-shm` 중 가장 최신 시각이 곧 활성 세션이다.
레지스트리의 `UserID` 로 교차 확인하고, 어긋나면 숨기지 않고 알린다.
"""
from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import tempfile

from . import settings

MEMO_DIR = os.path.expandvars(r'%LOCALAPPDATA%\CoolMessenger\Memo')
UDB_GLOB = os.path.join(MEMO_DIR, '*.udb')
STALE_SEC = 6 * 60 * 60          # 이보다 오래 손대지 않았으면 "활성"으로 보지 않는다


class UdbError(RuntimeError):
    pass


def _touched(path: str) -> float:
    """본체와 WAL/SHM 중 가장 최근 시각. 활성 세션은 WAL 을 계속 건드린다."""
    times = [os.path.getmtime(path)]
    for ext in ('-wal', '-shm'):
        if os.path.exists(path + ext):
            times.append(os.path.getmtime(path + ext))
    return max(times)


def registry_user() -> str | None:
    """쿨메신저가 기억하는 계정명. 참고용이며 이것만 믿지는 않는다."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Jiransoft\CoolMsg50\Option\Mail') as k:
            v, _ = winreg.QueryValueEx(k, 'UserID')
            return (v or '').strip() or None
    except OSError:
        return None


def accounts() -> list[dict]:
    """이 PC 에 있는 계정별 DB 목록 (최근 사용 순)."""
    rows = []
    for p in glob.glob(UDB_GLOB):
        rows.append({'name': os.path.splitext(os.path.basename(p))[0],
                     'path': p, 'size': os.path.getsize(p), 'touched': _touched(p)})
    rows.sort(key=lambda r: r['touched'], reverse=True)
    return rows


def configured() -> str:
    """설정에서 사람이 지정한 계정. 빈 문자열이면 자동."""
    return (settings.get('coolmsg_account') or '').strip()


def pick(account: str | None = None) -> dict:
    """
    읽을 DB 를 고른다.
      1. 인자로 준 계정
      2. 설정에서 사람이 지정한 계정  ← 자동 감지가 틀릴 때 쓰는 확실한 수단
      3. 가장 최근에 쓰인 파일 (자동)

    지정한 계정의 DB 가 없으면 **다른 파일로 넘어가지 않고 오류**를 낸다.
    조용히 남의 쪽지를 읽는 것보다 멈추는 편이 낫다.
    """
    account = account or configured() or None
    rows = accounts()
    if not rows:
        raise UdbError(f'쿨메신저 쪽지 DB 를 찾지 못했습니다: {MEMO_DIR}\n'
                       '쿨메신저 설치·로그인 상태를 확인하세요.')
    if account:
        for r in rows:
            if r['name'] == account:
                return r
        raise UdbError(f"'{account}' 계정의 쪽지 DB 가 없습니다. "
                       f"이 PC 에 있는 계정: {', '.join(r['name'] for r in rows)}")
    return rows[0]


def status() -> dict:
    """어떤 계정을 읽고 있는지, 미심쩍은 점은 없는지."""
    rows = accounts()
    if not rows:
        return {'ok': False, 'why': '쪽지 DB 없음', 'accounts': []}
    import time
    fixed = configured()
    if fixed:
        chosen = next((r for r in rows if r['name'] == fixed), None)
        if chosen is None:
            return {'ok': False, 'account': fixed, 'source': '설정',
                    'why': f"설정한 계정 '{fixed}' 의 쪽지 DB 가 이 PC 에 없습니다.",
                    'warn': None, 'accounts': [r['name'] for r in rows]}
        return {'ok': True, 'account': chosen['name'], 'path': chosen['path'],
                'source': '설정에서 지정', 'registry': registry_user(), 'warn': None,
                'accounts': [r['name'] for r in rows]}
    chosen = rows[0]
    reg = registry_user()
    warn = None
    if len(rows) > 1:
        others = ', '.join(r['name'] for r in rows[1:])
        warn = (f'이 PC 에 다른 계정 DB 도 있습니다: {others}. '
                '엉뚱한 계정이 잡히면 설정에서 직접 지정하세요.')
    if reg and reg != chosen['name']:
        warn = (f"쿨메신저가 기억하는 계정은 '{reg}' 인데 최근 기록은 '{chosen['name']}' 입니다. "
                '계정을 바꿔 로그인했다면 쿨메신저를 한 번 켜 두고 다시 확인하세요.')
    if time.time() - chosen['touched'] > STALE_SEC:
        warn = (f"'{chosen['name']}' DB 가 오래 전({time.strftime('%m-%d %H:%M', time.localtime(chosen['touched']))})에 "
                '마지막으로 쓰였습니다. 지금 로그인한 계정이 맞는지 확인하세요.')
    return {'ok': True, 'account': chosen['name'], 'path': chosen['path'],
            'source': '자동 (최근 사용)', 'registry': reg, 'warn': warn,
            'accounts': [r['name'] for r in rows]}


def open_readonly(account: str | None = None):
    """
    원본을 건드리지 않도록 복사본을 연다 (WAL/SHM 동반).
    반환: (sqlite3.Connection, 계정명, 임시폴더) — 다 쓰면 close_copy() 로 정리한다.
    """
    row = pick(account)
    src = row['path']
    tmp = tempfile.mkdtemp(prefix='cmudb_')
    dst = os.path.join(tmp, 'm.udb')
    shutil.copy(src, dst)
    for ext in ('-wal', '-shm'):
        if os.path.exists(src + ext):
            shutil.copy(src + ext, dst + ext)
    return sqlite3.connect(f'file:{dst}?mode=ro', uri=True), row['name'], tmp


def close_copy(con, tmp):
    try:
        con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
