# 스페이스기전 교실 (교실판) — 다시 만들기: python -m PyInstaller --noconfirm --clean SpacekijunClassroom.spec
# 데스크(desktop.py)를 쓰지 않는 따로 된 창이다. Playwright·트레이·독이 없어 가볍다.
from pathlib import Path

root = Path(SPECPATH)
app = root / 'app'
web = app / 'web'
a = Analysis(
    [str(app / 'classroom.py')], pathex=[str(app)],
    binaries=[],
    datas=[(str(web / name), 'web') for name in ('classroom.html', 'classroom.css', 'classroom.js',
                                                 'classroom-dock.html', 'classroom-dock.css', 'classroom-dock.js',
                                                 'classroom-drive.html', 'classroom-drive.css', 'classroom-drive.js',
                                                 'classroom-toast.html', 'classroom-dialog.html', 'classroom-google.html',
                                                 'classroom-popup.css', 'classroom-popup.js',
                                                 'classroom-mini.html', 'classroom-mini.css', 'classroom-mini.js',
                                                 'classroom-gtools.html', 'classroom-gtools.js', 'gtools.js', 'gtools.css',
                                                 'classroom-type.html', 'classroom-type.js',
                                                 'fonts.css', 'dock-tones.css')]
          + [(str(web / 'fonts'), 'web/fonts'), (str(web / 'icons'), 'web/icons'), (str(app / 'resources'), 'resources')],
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium',
                   'core.classroom_link', 'core.classroom_setup', 'core.classroom_controller', 'core.classroom_drive',
                   'core.classroom_vault', 'core.classroom_icons', 'core.classroom_update', 'core.classroom_startup', 'classroom_check', 'cryptography.hazmat.primitives.ciphers.aead',
                   'core.web_login'],
    hookspath=[], runtime_hooks=[],
    excludes=['playwright', 'pystray', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'gi', 'matplotlib', 'numpy',
              'pandas', 'scipy', 'IPython', 'pytest'],
    noarchive=False,
)
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != 'dbghelp.dll']
# 별사이 목장 원화(*-source.png, 약 30MB)·미리보기 쪽·참고 게임 시험 파일(ranch/tinypasture*)은 싣지 않는다 (2026-11-11)
a.datas = [entry for entry in a.datas if not (Path(entry[0]).as_posix().startswith('web/ranch')
           and (entry[0].endswith('-source.png') or 'tinypasture' in entry[0]
                or Path(entry[0]).name in ('ranch-originals.html', 'ranch-environment.html')))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='SpacekijunClassroom', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(app / 'resources' / 'desk.ico'),
)
