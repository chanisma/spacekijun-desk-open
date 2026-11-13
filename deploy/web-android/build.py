"""스페이스기전 웹앱 — 안드로이드 TWA 빌드.

    python deploy/web-android/build.py                                   # 서명된 APK → dist/SpacekijunWeb.apk
    python deploy/web-android/build.py --assetlinks D:/spacekijun/public/.well-known/assetlinks.json
    python deploy/web-android/build.py --publish         # 빌드하고 Storage 에 올린다(관리자 계정 로그인 필요)
    python deploy/web-android/build.py --publish-only    # 빌드 없이 dist/SpacekijunWeb.apk 를 확인해 올린다

올리는 곳 (2026-11-10): Supabase Storage `desk-releases/web-android/` — SpacekijunWeb-<판>.apk · SpacekijunWeb.apk(받기 주소) ·
latest.json. 교실판(`classroom-android/`, deploy/classroom-android/build.py)과 같은 모양이다. spacekijun 웹의 «PC 앱» 받기
페이지(src/lib/desktopApps.ts)가 latest.json 을 읽어 받기 단추를 보인다. 이 앱에는 자동 업데이트가 없다 — 사이트를
고치는 것은 앱을 다시 낼 필요가 없고(TWA), 앱 껍데기를 바꿨을 때만 versionCode 를 올려 다시 올린다.

빌드 도구는 교실판과 같은 %LOCALAPPDATA%/SpacekijunAndroidBuild(JDK 17 · Android SDK · Gradle).
판 번호는 android-web/app/build.gradle.kts 의 versionCode·versionName.

서명 키: .secrets/web-android.jks, 암호는 .secrets/web-android.pass(DPAPI). 없으면 처음 빌드할 때 만든다.
🚨 키를 잃으면 깔린 앱을 새 판으로 덮어쓸 수 없고, 사이트의 assetlinks.json 지문도 바꿔야 한다.
assetlinks.json 은 이 키의 인증서 SHA-256 — 사이트(`/.well-known/assetlinks.json`)에 있어야 주소창 없이 뜬다.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'app'))

from core import secretstore   # noqa: E402

ANDROID = ROOT / 'android-web'
TOOLS = Path(os.path.expandvars('%LOCALAPPDATA%')) / 'SpacekijunAndroidBuild'
KEYSTORE = ROOT / '.secrets' / 'web-android.jks'
PASSWORD = ROOT / '.secrets' / 'web-android.pass'
APK_OUT = ANDROID / 'app' / 'build' / 'outputs' / 'apk' / 'release' / 'app-release.apk'
DIST = ROOT / 'dist' / 'SpacekijunWeb.apk'
PACKAGE = 'kr.hs.kijun.spacekijun'
CHANNEL = 'web-android'
PUBLIC = 'https://your-project-ref.supabase.co/storage/v1/object/public/desk-releases/' + CHANNEL


def env() -> dict:
    e = dict(os.environ)
    e['JAVA_HOME'] = str(TOOLS / 'jdk')
    e['PATH'] = str(TOOLS / 'jdk' / 'bin') + os.pathsep + e['PATH']
    e['ANDROID_HOME'] = str(TOOLS / 'sdk')
    return e


def version() -> tuple[int, str]:
    text = (ANDROID / 'app' / 'build.gradle.kts').read_text(encoding='utf-8')
    code = int(re.search(r'versionCode\s*=\s*(\d+)', text).group(1))
    name = re.search(r'versionName\s*=\s*"([0-9.]+)"', text).group(1)
    return code, name


def password(create: bool) -> str:
    if PASSWORD.exists():
        return secretstore.decrypt(PASSWORD.read_bytes()).decode('ascii')
    if not create:
        sys.exit('서명 키 암호가 없습니다(.secrets/web-android.pass).')
    value = secrets.token_urlsafe(24)
    PASSWORD.parent.mkdir(parents=True, exist_ok=True)
    PASSWORD.write_bytes(secretstore.encrypt(value.encode('ascii')))
    return value


def ensure_keystore() -> str:
    if KEYSTORE.exists():
        return password(create=False)
    value = password(create=True)
    keytool = TOOLS / 'jdk' / 'bin' / 'keytool.exe'
    subprocess.run([str(keytool), '-genkeypair', '-keystore', str(KEYSTORE), '-storetype', 'PKCS12', '-alias', 'spacekijun',
                    '-keyalg', 'RSA', '-keysize', '4096', '-validity', '36500', '-storepass', value, '-keypass', value,
                    '-dname', 'CN=Spacekijun Web, O=Kijun High School, C=KR'], check=True, capture_output=True)
    print(f'  서명 키를 만들었습니다: {KEYSTORE.relative_to(ROOT)} (잃지 않게 따로 보관하세요)')
    return value


def build(value: str):
    e = env()
    e['WEB_KEYSTORE'] = str(KEYSTORE)
    e['WEB_KEYSTORE_PASSWORD'] = value
    done = subprocess.run([str(ANDROID / 'gradlew.bat'), '--no-daemon', '-q', 'assembleRelease'],
                          cwd=ANDROID, env=e, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if done.returncode != 0:
        sys.exit('빌드 실패:\n' + (done.stdout + done.stderr)[-4000:])


def verify(apk: Path) -> str:
    """서명 확인 → 인증서 SHA-256"""
    tools = sorted((TOOLS / 'sdk' / 'build-tools').iterdir())[-1]
    done = subprocess.run([str(tools / 'apksigner.bat'), 'verify', '--print-certs', str(apk)],
                          env=env(), capture_output=True, text=True, encoding='utf-8', errors='replace')
    if done.returncode != 0:
        sys.exit('APK 서명 확인 실패:\n' + done.stdout + done.stderr)
    found = re.search(r'certificate SHA-256 digest: ([0-9a-f]{64})', done.stdout)
    if not found:
        sys.exit('APK 인증서 지문을 읽지 못했습니다:\n' + done.stdout)
    return found.group(1)


def assetlinks(cert: str) -> str:
    fingerprint = ':'.join(cert[i:i + 2] for i in range(0, 64, 2)).upper()
    return json.dumps([{
        'relation': ['delegate_permission/common.handle_all_urls'],
        'target': {'namespace': 'android_app', 'package_name': PACKAGE, 'sha256_cert_fingerprints': [fingerprint]},
    }], indent=2) + '\n'


def apk_version(apk: Path) -> tuple[int, str]:
    """APK 안에 적힌 판 (aapt2) — --publish-only 가 dist 의 파일이 지금 판 번호로 빌드된 것인지 확인한다."""
    tools = sorted((TOOLS / 'sdk' / 'build-tools').iterdir())[-1]
    done = subprocess.run([str(tools / 'aapt2.exe'), 'dump', 'badging', str(apk)], env=env(),
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    found = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", done.stdout)
    if not found or found.group(1) != PACKAGE:
        sys.exit('APK 의 패키지·판을 읽지 못했습니다:\n' + done.stdout[:400] + done.stderr[:400])
    return int(found.group(2)), found.group(3)


def published() -> dict | None:
    try:
        with urllib.request.urlopen(f'{PUBLIC}/latest.json?t={datetime.now().timestamp()}', timeout=15) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception:
        return None


def publish(code: int, name: str, cert: str):
    """desk-releases/web-android/ 에 올린다 — 교실판과 같은 모양. 같은 판 번호로 다른 파일은 올리지 않는다."""
    data = DIST.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    current = published()
    if current and int(current.get('versionCode', 0)) > code:
        sys.exit(f'올라가 있는 판({current.get("version")}, {current.get("versionCode")})이 더 새 판입니다.')
    if current and int(current.get('versionCode', 0)) == code and current.get('sha256') != digest:
        sys.exit('같은 판 번호로 다른 파일이 이미 올라가 있습니다. versionCode 를 올리세요.')
    spec = importlib.util.spec_from_file_location('desk_publish', ROOT / 'deploy' / 'desk-update' / 'publish.py')
    desk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desk)
    file = f'SpacekijunWeb-{name}.apk'
    manifest = {'app': 'SpacekijunWebAndroid', 'version': name, 'versionCode': code, 'file': file, 'size': len(data),
                'sha256': digest, 'certificate': cert, 'published': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    kind = 'application/octet-stream'      # 버킷이 APK 형식(vnd.android.package-archive)을 받지 않는다 — 교실판과 같이
    desk.upload(f'{CHANNEL}/{file}', data, kind, 'max-age=31536000')
    print(f'  올림 {file}')
    desk.upload(f'{CHANNEL}/SpacekijunWeb.apk', data, kind, 'max-age=300')
    print('  올림 SpacekijunWeb.apk (받기 주소)')
    desk.upload(f'{CHANNEL}/latest.json', json.dumps(manifest, ensure_ascii=False).encode('utf-8'), 'application/json', 'max-age=60')
    print('  올림 latest.json')
    seen = published()
    if not seen or seen.get('sha256') != digest:
        sys.exit('공개 주소의 목록이 아직 옛것입니다(캐시). 잠시 뒤 다시 확인하세요.')
    with urllib.request.urlopen(f'{PUBLIC}/{file}', timeout=60) as res:
        if hashlib.sha256(res.read()).hexdigest() != digest:
            sys.exit('공개 주소에서 받은 APK 가 올린 것과 다릅니다.')
    print(f'완료 — {PUBLIC}/SpacekijunWeb.apk')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assetlinks', type=Path, help='assetlinks.json 을 이 경로에 쓴다(사이트 public/.well-known/)')
    parser.add_argument('--publish', action='store_true', help='빌드한 뒤 Storage desk-releases/web-android/ 에 올린다')
    parser.add_argument('--publish-only', action='store_true', help='빌드하지 않고 dist/SpacekijunWeb.apk 를 확인해 올린다')
    options = parser.parse_args()

    code, name = version()
    print(f'== 스페이스기전 웹앱(안드로이드) {name} ({code}) ==')
    if options.publish_only:
        if not DIST.exists():
            sys.exit(f'{DIST} 가 없습니다. 먼저 빌드하세요.')
        cert = verify(DIST)
        found = apk_version(DIST)
        if found != (code, name):
            sys.exit(f'{DIST.name} 은 {found} 판입니다 — build.gradle.kts({code}, {name})와 다릅니다. 다시 빌드하세요.')
        print(f'  서명 확인(인증서 {cert[:16]}…) · {DIST.stat().st_size / 1048576:.1f}MB')
        return publish(code, name, cert)
    value = ensure_keystore()
    build(value)
    cert = verify(APK_OUT)
    print(f'  서명 확인(인증서 {cert[:16]}…)')
    DIST.parent.mkdir(exist_ok=True)
    shutil.copyfile(APK_OUT, DIST)
    print(f'  {DIST.relative_to(ROOT)} ({DIST.stat().st_size / 1048576:.1f}MB)')
    links = assetlinks(cert)
    if options.assetlinks:
        options.assetlinks.parent.mkdir(parents=True, exist_ok=True)
        options.assetlinks.write_text(links, encoding='utf-8', newline='\n')
        print(f'  assetlinks.json → {options.assetlinks}')
    else:
        print('  사이트의 /.well-known/assetlinks.json:\n' + links)
    if options.publish:
        publish(code, name, cert)


if __name__ == '__main__':
    main()
