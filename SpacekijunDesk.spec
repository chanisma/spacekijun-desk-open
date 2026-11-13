# Rebuild: python -m PyInstaller --noconfirm SpacekijunDesk.spec
from pathlib import Path

root = Path(SPECPATH)
app = root / 'app'
a = Analysis(
    [str(app / 'packaged.py')], pathex=[str(app)],
    # 데스크 안 에이전트 터미널(core/agent_term.py)의 의사 콘솔 — pywinpty 는 DLL·exe 를 패키지 폴더에서 찾는다 (2026-10-24)
    binaries=[(str(path), 'winpty') for path in Path(__import__('winpty').__file__).parent.iterdir()
              if path.suffix.lower() in ('.dll', '.exe')],
    datas=[(str(app / 'web'), 'web'), (str(app / 'resources'), 'resources')],
    # NEIS 도우미 쪽은 함수 안에서 늦게 부르는 것이 많아 분석이 놓칠 수 있다. 빠지면
    # 나이스 창을 연 뒤에야 터지므로 이름을 적어 둔다.
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium', 'pystray._win32',
                   'core.neis_actions', 'core.neis_assist', 'core.neis_glossary',
                   'core.neis_menu', 'core.neis_nav', 'core.neis_overlay', 'core.klef_overlay',
                   'core.neis_roles', 'core.neis_session',
                   # 독·캡처·클립보드·단축키도 함수 안에서 부른다 (2026-10 추가)
                   'core.capture', 'core.clipboard_history', 'core.dock_handle', 'core.hotkey',
                   'core.dashboard', 'core.web_login', 'core.cdp', 'core.cm_launcher',
                   'core.agent', 'core.agent_term', 'core.agent_bridge', 'core.agent_peer', 'core.agent_request', 'core.agent_memory', 'core.agent_cron', 'core.agent_complete', 'core.agent_paths', 'core.knowledge', 'core.privacy_guard', 'core.resident_tasks', 'core.computer_use', 'winpty', 'winpty.ptyprocess', 'core.automation', 'core.spacekijun_mcp', 'core.active_folder', 'core.child', 'core.updater', 'core.ed25519'],
    hookspath=[], runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'gi', 'matplotlib', 'numpy', 'pandas', 'scipy', 'IPython', 'pytest'],
    noarchive=False,
)
# A machine-wide Oculus PATH entry can make dependency analysis pick up its
# private dbghelp.dll. Use Windows' system DLL instead of redistributing it.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != 'dbghelp.dll']
# 별사이 목장 원화(*-source.png, 약 30MB)·미리보기 쪽·참고 게임 시험 파일(ranch/tinypasture*)은 싣지 않는다 (2026-11-11)
a.datas = [entry for entry in a.datas if not (Path(entry[0]).as_posix().startswith('web/ranch')
           and (entry[0].endswith('-source.png') or 'tinypasture' in entry[0]
                or Path(entry[0]).name in ('ranch-originals.html', 'ranch-environment.html')))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='SpacekijunDesk', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(app / 'resources' / 'desk.ico'),
)
