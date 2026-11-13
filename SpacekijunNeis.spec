# Rebuild: python -m PyInstaller --noconfirm SpacekijunNeis.spec
#
# 나이스를 **프로그램 안 창**에서 열고 인증서로 자동 로그인하는 별도 실행 파일.
# 데스크 본체(SpacekijunDesk)와 달리 Edge 를 따로 띄우지 않고 Playwright 도 쓰지 않는다.
# 그래서 나이스 도우미 패널은 없다.
from pathlib import Path

root = Path(SPECPATH)
app = root / 'app'
a = Analysis(
    [str(app / 'neis_packaged.py')], pathex=[str(app)],
    binaries=[],
    datas=[(str(app / 'resources'), 'resources')],
    # 늦게 부르는 것들이라 분석이 놓칠 수 있다. 빠지면 창을 연 뒤에야 터진다.
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium',
                   'core.portal', 'core.secretstore', 'core.watcher', 'core.web_popup'],
    hookspath=[], runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'gi', 'matplotlib', 'numpy',
              'pandas', 'scipy', 'IPython', 'pytest', 'playwright'],
    noarchive=False,
)
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != 'dbghelp.dll']
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='SpacekijunNeis', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(app / 'resources' / 'desk.ico'),
)
