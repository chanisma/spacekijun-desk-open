"""켰는데 화면이 뜨지 않을 때 남기는 기록 (2026-10-19 — 독이 안 뜨고 트레이를 누르면 먹통이던 PC).

화면(WebView2)이 끝내 뜨지 않으면 프로그램은 살아 있어도 아무것도 보이지 않는다. 그때 어디서 멈췄는지
(모든 스레드의 위치), 활동 기록, WebView2 버전, 디버그 포트를 잡은 프로세스, 남아 있는 같은 프로그램을
`<자료 폴더>/startup-hang.log` 에 적는다. 다음에 같은 일이 생기면 이 파일 하나로 원인을 좁힌다.
개인정보는 넣지 않는다 (활동 기록은 원래 화면에 보이는 문장이다).
"""
from __future__ import annotations

import faulthandler
import os
import sys
from datetime import datetime
from pathlib import Path

WEBVIEW2_CLIENT = r'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'


def webview2_version() -> str:
    """설치된 WebView2 런타임 판 (컴퓨터·사용자 설치 어느 쪽이든). 없으면 '없음'."""
    try:
        import winreg
    except ImportError:
        return '알 수 없음'
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\WOW6432Node\\' + WEBVIEW2_CLIENT),
                      (winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\' + WEBVIEW2_CLIENT),
                      (winreg.HKEY_CURRENT_USER, 'Software\\' + WEBVIEW2_CLIENT)):
        try:
            with winreg.OpenKey(root, key) as opened:
                value = winreg.QueryValueEx(opened, 'pv')[0]
                if value and value != '0.0.0.0':
                    return str(value)
        except OSError:
            continue
    return '없음'


def port_owners(port: int) -> list[str]:
    try:
        import psutil
        found = []
        for conn in psutil.net_connections(kind='tcp'):
            if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                try:
                    found.append(f'{conn.pid} {psutil.Process(conn.pid).name()}')
                except (psutil.Error, TypeError):
                    found.append(str(conn.pid))
        return found
    except Exception as exc:                       # 권한이 없으면 못 볼 수 있다
        return [f'확인 못 함: {exc}']


def same_programs() -> list[str]:
    try:
        import psutil
        names = {'spacekijundesk.exe', 'spacekijunstudent.exe', 'msedgewebview2.exe'}
        rows = []
        for proc in psutil.process_iter(['pid', 'name', 'create_time', 'ppid']):
            if (proc.info['name'] or '').lower() in names:
                started = datetime.fromtimestamp(proc.info['create_time']).strftime('%m-%d %H:%M:%S')
                rows.append(f"{proc.info['pid']} {proc.info['name']} (부모 {proc.info['ppid']}, {started})")
        return rows
    except Exception as exc:
        return [f'확인 못 함: {exc}']


def write_hang_report(path: Path, title: str, version: str, waited: int, logs: list[dict],
                      debug_port: int | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as out:
        out.write(f'{title} {version} — 켠 뒤 {waited}초 동안 화면이 뜨지 않았습니다\n')
        out.write(f'때: {datetime.now():%Y-%m-%d %H:%M:%S}\n')
        out.write(f'Windows: {sys.getwindowsversion().major}.{sys.getwindowsversion().minor} '
                  f'build {sys.getwindowsversion().build}\n' if hasattr(sys, 'getwindowsversion') else '')
        out.write(f'WebView2 런타임: {webview2_version()}\n')
        out.write(f'실행 파일: {sys.executable}\n인자: {sys.argv[1:]}\n')
        if debug_port:
            out.write(f'디버그 포트 {debug_port} 을 잡은 프로세스: {port_owners(debug_port) or "없음"}\n')
        out.write('같은 프로그램·WebView2 프로세스:\n')
        for row in same_programs():
            out.write(f'  {row}\n')
        out.write('\n활동 기록 (최근 40줄):\n')
        for item in logs[-40:]:
            out.write(f"  {item.get('time', '')} {item.get('text', '')}\n")
        out.write('\n스레드 위치:\n')
        out.flush()
        faulthandler.dump_traceback(file=out, all_threads=True)
    return path


def hang_log_path(data_dir: str) -> Path:
    return Path(data_dir) / 'startup-hang.log'


def clear_old(data_dir: str) -> None:
    """화면이 제대로 떴으면 지난번 기록은 지운다 — 남아 있으면 지금도 그런 줄 안다."""
    try:
        os.remove(hang_log_path(data_dir))
    except OSError:
        pass
