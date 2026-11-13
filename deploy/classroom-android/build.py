"""스페이스기전 교실 — 안드로이드(전자칠판)판 빌드·올리기.

    python deploy/classroom-android/build.py              # 시험 → 서명된 APK → dist/SpacekijunClassroom.apk
    python deploy/classroom-android/build.py --publish    # 위에 더해 자동 업데이트로 올린다(관리자 계정 로그인 필요)

빌드 도구는 %LOCALAPPDATA%/SpacekijunAndroidBuild 에 둔다(JDK 17 · Android SDK · Gradle — 처음 한 번 그 폴더의 setup.sh).
판 번호는 android/app/build.gradle.kts 의 versionCode·versionName — 새로 내보낼 때마다 둘 다 올린다.

서명 키: .secrets/classroom-android.jks, 암호는 .secrets/classroom-android.pass(DPAPI — 이 PC 이 Windows 계정에서만 풀린다).
없으면 처음 빌드할 때 만든다. 🚨 키를 잃으면 칠판에 깐 앱을 새 판으로 덮어쓸 수 없다(지우고 새로 깔아야 한다).
올리는 곳: Supabase Storage `desk-releases/classroom-android/` — SpacekijunClassroom-<판>.apk · latest.json ·
처음 깔 때 쓰는 고정 주소 SpacekijunClassroom.apk.
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

ANDROID = ROOT / 'android'
TOOLS = Path(os.path.expandvars('%LOCALAPPDATA%')) / 'SpacekijunAndroidBuild'
KEYSTORE = ROOT / '.secrets' / 'classroom-android.jks'
PASSWORD = ROOT / '.secrets' / 'classroom-android.pass'
APK_OUT = ANDROID / 'app' / 'build' / 'outputs' / 'apk' / 'release' / 'app-release.apk'
DIST = ROOT / 'dist' / 'SpacekijunClassroom.apk'
CHANNEL = 'classroom-android'
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
        sys.exit('서명 키 암호가 없습니다(.secrets/classroom-android.pass).')
    value = secrets.token_urlsafe(24)
    PASSWORD.parent.mkdir(parents=True, exist_ok=True)
    PASSWORD.write_bytes(secretstore.encrypt(value.encode('ascii')))
    return value


def ensure_keystore() -> str:
    if KEYSTORE.exists():
        return password(create=False)
    value = password(create=True)
    keytool = TOOLS / 'jdk' / 'bin' / 'keytool.exe'
    subprocess.run([str(keytool), '-genkeypair', '-keystore', str(KEYSTORE), '-storetype', 'PKCS12', '-alias', 'classroom',
                    '-keyalg', 'RSA', '-keysize', '4096', '-validity', '36500', '-storepass', value, '-keypass', value,
                    '-dname', 'CN=Spacekijun Classroom, O=Kijun High School, C=KR'], check=True, capture_output=True)
    print(f'  서명 키를 만들었습니다: {KEYSTORE.relative_to(ROOT)} (잃지 않게 따로 보관하세요)')
    return value


def build(value: str):
    e = env()
    e['CLASSROOM_KEYSTORE'] = str(KEYSTORE)
    e['CLASSROOM_KEYSTORE_PASSWORD'] = value
    gradlew = ANDROID / 'gradlew.bat'
    done = subprocess.run([str(gradlew), '--no-daemon', '-q', 'testDebugUnitTest', 'assembleRelease'],
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
    return found.group(1) if found else '?'


def published() -> dict | None:
    try:
        with urllib.request.urlopen(f'{PUBLIC}/latest.json?t={datetime.now().timestamp()}', timeout=15) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    options = parser.parse_args()

    code, name = version()
    print(f'== 스페이스기전 교실(안드로이드) {name} ({code}) ==')
    value = ensure_keystore()
    build(value)
    cert = verify(APK_OUT)
    print(f'  시험 통과 · 서명 확인(인증서 {cert[:16]}…)')
    DIST.parent.mkdir(exist_ok=True)
    shutil.copyfile(APK_OUT, DIST)
    data = DIST.read_bytes()
    print(f'  {DIST.relative_to(ROOT)} ({len(data) / 1048576:.1f}MB)')
    if not options.publish:
        return

    current = published()
    if current and int(current.get('versionCode', 0)) >= code:
        sys.exit(f'올라가 있는 판({current.get("version")}, {current.get("versionCode")})보다 새 판이 아닙니다. versionCode 를 올리세요.')
    spec = importlib.util.spec_from_file_location('desk_publish', ROOT / 'deploy' / 'desk-update' / 'publish.py')
    desk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desk)
    file = f'SpacekijunClassroom-{name}.apk'
    manifest = {'app': 'SpacekijunClassroomAndroid', 'version': name, 'versionCode': code, 'file': file, 'size': len(data),
                'sha256': hashlib.sha256(data).hexdigest(), 'certificate': cert,
                'published': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    desk.upload(f'{CHANNEL}/{file}', data, 'application/octet-stream', 'max-age=31536000')
    print(f'  올림 {file}')
    desk.upload(f'{CHANNEL}/SpacekijunClassroom.apk', data, 'application/octet-stream', 'max-age=300')
    print('  올림 SpacekijunClassroom.apk (처음 깔 때 쓰는 주소)')
    desk.upload(f'{CHANNEL}/latest.json', json.dumps(manifest, ensure_ascii=False).encode('utf-8'), 'application/json', 'max-age=60')
    print('  올림 latest.json')
    seen = published()
    if not seen or seen.get('versionCode') != code:
        sys.exit('공개 주소의 목록이 아직 옛것입니다(캐시). 잠시 뒤 다시 확인하세요.')
    with urllib.request.urlopen(f'{PUBLIC}/{file}', timeout=60) as res:
        if hashlib.sha256(res.read()).hexdigest() != manifest['sha256']:
            sys.exit('공개 주소에서 받은 APK 가 올린 것과 다릅니다.')
    print(f'완료 — 칠판의 교실 앱이 30분 안에 {name} 을 받아 QR 화면에 [새 판 설치]를 띄웁니다.')
    print(f'처음 깔 때: {PUBLIC}/SpacekijunClassroom.apk')


if __name__ == '__main__':
    main()
