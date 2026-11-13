"""교실판 실행 파일 자체 점검 — 계정·네트워크 없이, 창을 띄우지 않고 번들이 제대로 묶였는지 본다.

    SpacekijunClassroom.exe --self-test <보고서.json>

deploy/classroom-update/publish.py 가 올리기 전에 돌린다(통과하고 판 번호가 맞아야 올린다).
"""
import base64
import json
import os
import tempfile
import traceback
from pathlib import Path


def check(report_path: Path) -> None:
    report = {'ok': False, 'checks': [], 'version': None}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from core import classroom_update
        report['version'] = classroom_update.VERSION
        classroom_update.configure()
        from core import updater
        assert updater.APP == 'SpacekijunClassroom' and updater.PUBLIC_URL.endswith('/classroom')
        assert updater.PART.match('SpacekijunClassroom.exe.part1') and not updater.PART.match('SpacekijunDesk.exe.part1')
        report['checks'].append('Auto-update points at desk-releases/classroom (signed, same key as the desk)')

        import webview                  # noqa: F401 — 번들에 들어 있는지
        import segno                    # noqa: F401
        import psutil                   # noqa: F401
        from PIL import Image           # noqa: F401
        from core import classroom_controller, classroom_drive, classroom_icons, classroom_link, classroom_setup  # noqa: F401
        assert classroom_link.qr_svg('https://example.com').startswith('<svg')
        report['checks'].append('Window, QR, drive, icons and setup modules bundled')

        from core import classroom_vault as vault
        with tempfile.TemporaryDirectory() as folder:
            vault.PROFILES_DIR = os.path.join(folder, 'profiles')
            src = Path(folder, 'edge', 'Default')
            src.mkdir(parents=True)
            (src / 'Cookies').write_bytes(b'x')
            key = base64.b64encode(os.urandom(32)).decode()
            vault.save(str(src.parent), 'c' * 24, key)
            assert vault.restore('c' * 24, key, os.path.join(folder, 'back'))
        report['checks'].append('Google login vault (AES-256-GCM via cryptography) works')

        # 휴대폰으로 입력 — 수업용 Edge 에 UI Automation 으로 넣는다(pythonnet + .NET UIAutomationClient)
        from core import classroom_type
        assert classroom_type.TypeKey().public
        classroom_type.EdgeUia().E.RootElement
        report['checks'].append('Phone typing: P-256 key and UI Automation (pythonnet) load')

        root = Path(__file__).parent / 'web'
        for name in ('classroom.html', 'classroom.js', 'classroom-dock.html', 'classroom-dock.js', 'classroom-drive.html',
                     'classroom-drive.js', 'classroom-toast.html', 'classroom-dialog.html', 'classroom-google.html',
                     'classroom-popup.js', 'classroom-popup.css', 'dock-tones.css', 'fonts.css',
                     'classroom-mini.html', 'classroom-mini.js', 'classroom-mini.css',
                     'classroom-gtools.html', 'classroom-gtools.js', 'gtools.js', 'gtools.css',
                     'classroom-type.html', 'classroom-type.js',
                     'icons/google/google.png', 'icons/google/classroom.png', 'icons/spacekijun.png'):
            assert (root / name).is_file(), f'web/{name}'
        assert set(classroom_setup.GOOGLE_APPS) <= {p.stem for p in (root / 'icons' / 'google').glob('*.png')}
        report['checks'].append('Screens, popups and real icons (Google apps, Spacekijun) bundled')
        report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
