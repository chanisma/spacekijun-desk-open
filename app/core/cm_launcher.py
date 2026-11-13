"""Launch installed CoolMessenger with reply integration, without an external BAT."""
import ctypes
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import psutil
from . import cdp, cm_win32 as cm

_lock = threading.Lock()


def _process():
    pid = cm.pid()
    if pid:
        process = psutil.Process(pid)
        if process.name().lower() == 'coolmessenger.exe':
            return process
    # Also detect a client that is still starting, before its singleton window exists.
    for process in psutil.process_iter(['name']):
        if (process.info['name'] or '').lower() == 'coolmessenger.exe':
            return process
    return None


def _listening():
    try:
        with socket.create_connection(('127.0.0.1', cdp.PORT), timeout=.5):
            return True
    except OSError:
        return False


def _ready(process):
    if not process:
        return False
    try:
        owners = [process, *process.children(recursive=True)]
        if not any(conn.status == psutil.CONN_LISTEN and conn.laddr.port == cdp.PORT
                   for owner in owners for conn in owner.net_connections(kind='tcp')):
            return False
        cdp.targets(timeout=.7)
        return True
    except (OSError, psutil.Error, cdp.CdpError):
        return False


def _executable(process):
    candidates = [Path(process.exe())] if process else []
    for env in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
        root = os.environ.get(env)
        if root:
            candidates.extend([Path(root)/'CoolMessenger Gentoo'/'CoolMessenger.exe',
                               Path(root)/'CoolMessenger'/'CoolMessenger.exe'])
    for path in candidates:
        if path.name.lower() == 'coolmessenger.exe' and path.is_file():
            return path.resolve()
    raise RuntimeError('설치된 쿨메신저를 찾지 못했습니다. CoolMessenger Gentoo를 먼저 설치해 주세요.')


def _launch(path):
    env = os.environ.copy()
    frozen = getattr(sys, 'frozen', False)
    if frozen:
        # Do not make the installed external program load our bundled DLLs.
        bundle = str(Path(sys._MEIPASS).resolve()).lower()
        env['PATH'] = os.pathsep.join(p for p in env.get('PATH', '').split(os.pathsep)
                                     if not p.lower().startswith(bundle))
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        return subprocess.Popen([str(path), f'--remote-debugging-port={cdp.PORT}',
                                 '--remote-debugging-address=127.0.0.1'],
                                cwd=str(path.parent), env=env, shell=False,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        if frozen:
            ctypes.windll.kernel32.SetDllDirectoryW(str(sys._MEIPASS))


def prepare(restart=False):
    if not _lock.acquire(blocking=False):
        raise RuntimeError('쿨메신저 연결을 준비 중입니다. 잠시 기다려 주세요.')
    try:
        process = _process()
        if _ready(process):
            return {'needs_restart':False, 'message': '쿨메신저 연동 준비 완료.' +
                    (' 로그인 후 사용할 수 있습니다.' if not cm.main_window() else ' 알림·답장 연동을 사용할 수 있습니다.')}
        if _listening():
            raise RuntimeError('연동 포트를 다른 프로그램이 사용 중이거나 응답하지 않습니다. 해당 프로그램을 확인한 뒤 다시 연결해 주세요.')
        executable = _executable(process)
        if process and not restart:
            return {'needs_restart':True, 'message':'답장 연동을 위해 쿨메신저를 다시 실행해야 합니다. 작성 중인 쪽지와 첨부 내용을 먼저 저장해 주세요.'}
        if process:
            # Called only after the in-app restart confirmation. Never kill by image name.
            children = process.children(recursive=True)
            process.terminate()
            process.wait(timeout=5)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(children, timeout=3)
        _launch(executable)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if _ready(_process()):
                return {'needs_restart':False, 'message':'쿨메신저를 연동 모드로 실행했습니다. 로그인 창이 보이면 로그인해 주세요.'}
            time.sleep(.4)
        return {'needs_restart':False, 'message':'쿨메신저를 실행했습니다. 로그인한 뒤 ‘상태 확인’을 눌러 주세요.'}
    finally:
        _lock.release()
