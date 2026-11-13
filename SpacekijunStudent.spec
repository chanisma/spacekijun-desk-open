# 스페이스기전 학생 (학생판 독) — 다시 만들기: python -m PyInstaller --noconfirm --clean SpacekijunStudent.spec
# 교사판(SpacekijunDesk.spec)과 같은 코드에서, 입구만 student.py 로 바꿔 판을 'student' 로 정한다.
# 학생판은 Playwright(자동 로그인·나이스 도우미)를 쓰지 않으므로 넣지 않는다 — 실행 파일이 가볍다.
from pathlib import Path

root = Path(SPECPATH)
app = root / 'app'
a = Analysis(
    [str(app / 'student.py')], pathex=[str(app)],
    # 데스크 안 에이전트 터미널(core/agent_term.py)의 의사 콘솔 — pywinpty 는 DLL·exe 를 패키지 폴더에서 찾는다 (2026-10-24)
    binaries=[(str(path), 'winpty') for path in Path(__import__('winpty').__file__).parent.iterdir()
              if path.suffix.lower() in ('.dll', '.exe')],
    # 이세계 3D 게임(약 5MB, deploy/isekai3d/sync.py) — 캐릭터(약 500MB)는 넣지 않는다: Intune 캐릭터 팩이 따로 깐다
    datas=[(str(app / 'web'), 'web'), (str(app / 'resources'), 'resources'), (str(app / 'games' / 'isekai3d'), 'games/isekai3d')],
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium', 'pystray._win32',
                   'core.edition', 'core.capture', 'core.clipboard_history', 'core.dock_handle', 'core.hotkey',
                   'core.dashboard', 'core.web_login', 'core.web_signin', 'core.portal', 'core.agent', 'core.agent_term', 'core.agent_bridge', 'core.agent_memory', 'core.agent_cron', 'core.agent_complete', 'core.agent_paths', 'core.computer_use', 'winpty', 'winpty.ptyprocess', 'core.active_folder', 'core.isekai3d_server', 'core.ranch', 'student_check'],
    hookspath=[], runtime_hooks=[],
    excludes=['playwright', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'gi', 'matplotlib', 'numpy', 'pandas',
              'scipy', 'IPython', 'pytest'],
    noarchive=False,
)
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != 'dbghelp.dll']
# 교사판 자동화 업무 스킬(resources/skills — 쿨메신저 쪽지 보내기 등)은 학생판에 넣지 않는다 (2026-10-22 요청)
a.datas = [entry for entry in a.datas if Path(entry[0]).parts[:2] != ('resources', 'skills')]
# 별사이 목장 원화(*-source.png, 약 30MB)·미리보기 쪽·참고 게임 시험 파일(ranch/tinypasture*)은 싣지 않는다 (2026-11-11)
a.datas = [entry for entry in a.datas if not (Path(entry[0]).as_posix().startswith('web/ranch')
           and (entry[0].endswith('-source.png') or 'tinypasture' in entry[0]
                or Path(entry[0]).name in ('ranch-originals.html', 'ranch-environment.html')))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='SpacekijunStudent', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(app / 'resources' / 'desk.ico'),
)
