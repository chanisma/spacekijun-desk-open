"""교실판 — 수업용 Edge 프로필(구글 로그인)을 이 PC 에 암호화해 보관한다 (2026-10-14 사용자 결정 «A+»).

수업이 끝날 때 프로필 폴더를 묶어(zip) AES-256-GCM 으로 잠가 profiles/<ref>.bin 에 둔다. 열쇠는 이 PC 에 없다 —
서버(classroom_profile_key)가 쥐고 있다가, 같은 선생님이 이 PC 에서 QR 로 승인할 때만 handoff.profile 로 넘긴다.
그래서 다음 수업엔 구글(클래스룸·슬라이드·폼)이 로그인된 채 열리고, 학생이 PC 를 만져도 남은 것은 암호문뿐이다.

· 캐시·모델·확장 내려받기 같은 큰 것은 빼고 묶는다(로그인에 필요한 쿠키·저장소만 남는다).
· 열쇠가 맞지 않으면(선생님이 지웠다·서버에서 새로 만들었다) 보관 파일을 지우고 빈 프로필로 시작한다.
· 60일 넘게 안 쓴 보관 파일은 켤 때 지운다(그 사이 열쇠는 서버에 있어도 파일이 없으면 다시 로그인).
· Edge 는 쿠키를 다시 이 Windows 사용자의 DPAPI 로 잠근다 — 다른 PC·다른 사용자로 옮긴 보관 파일은 풀려도 로그인되지 않는다.
"""
from __future__ import annotations

import base64
import io
import os
import re
import time
import zipfile

from .classroom_link import DATA_DIR

PROFILES_DIR = os.path.join(DATA_DIR, 'profiles')
MAGIC = b'SKV1'
MAX_PLAIN = 200 * 1024 * 1024      # 이보다 크면 보관하지 않는다(무언가 잘못 쌓였다)
KEEP_DAYS = 60
REF = re.compile(r'^[A-Za-z0-9_-]{16,64}$')

# 프로필 안에서 빼는 것 — 다시 받으면 되는 캐시·모델·업데이트 조각. 경로의 어느 마디든 이 이름이면 뺀다.
SKIP_DIRS = {
    'Cache', 'Code Cache', 'GPUCache', 'DawnCache', 'DawnGraphiteCache', 'DawnWebGPUCache', 'GraphiteDawnCache',
    'GrShaderCache', 'ShaderCache', 'CacheStorage', 'ScriptCache', 'component_crx_cache', 'extensions_crx_cache',
    'Crashpad', 'BrowserMetrics', 'optimization_guide_model_store', 'EdgeLanguageDetectionModel',
    'OnDeviceHeadSuggestModel', 'Safe Browsing', 'Subresource Filter', 'WidevineCdm', 'hyphen-data', 'ZxcvbnData',
    'MEIPreload', 'SmartScreen', 'Trust Protection Lists', 'FirstPartySetsPreloaded', 'OriginTrials',
    'PKIMetadata', 'CertificateRevocation', 'SSLErrorAssistant', 'FileTypePolicies', 'TpcdMetadata',
    'MaskedDomainListPreloaded', 'Edge Shopping', 'EdgeCoupons', 'EdgeHubAppUsage', 'Nurturing', 'Ad Blocking',
    'AutoLaunchProtocolsComponent', 'Speech Recognition', 'screen_ai', 'Floc', 'blob_storage',
}
SKIP_FILES = {'lockfile', 'LOCK', 'SingletonLock', 'SingletonCookie', 'SingletonSocket'}


class VaultError(RuntimeError):
    pass


def _key(key_b64: str) -> bytes:
    try:
        key = base64.b64decode(key_b64, validate=True)
    except Exception:
        raise VaultError('보관 열쇠가 올바르지 않습니다.') from None
    if len(key) != 32:
        raise VaultError('보관 열쇠가 올바르지 않습니다.')
    return key


def blob_path(ref: str) -> str:
    if not REF.match(ref or ''):
        raise VaultError('보관 이름이 올바르지 않습니다.')
    return os.path.join(PROFILES_DIR, ref + '.bin')


def _pack(folder: str) -> bytes:
    buf = io.BytesIO()
    size = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if name in SKIP_FILES or name.endswith('.tmp'):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, folder)
                try:
                    with open(full, 'rb') as f:
                        data = f.read()
                except OSError:
                    continue                  # 잠긴 파일 — Edge 가 아직 쥐고 있다
                size += len(data)
                if size > MAX_PLAIN:
                    raise VaultError('브라우저 기록이 너무 커서 보관하지 않았습니다.')
                zf.writestr(rel.replace(os.sep, '/'), data)
    return buf.getvalue()


def save(folder: str, ref: str, key_b64: str) -> int:
    """프로필 폴더를 잠가 보관한다. 보관한 바이트 수를 돌려준다."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not os.path.isdir(folder):
        return 0
    path = blob_path(ref)
    plain = _pack(folder)
    nonce = os.urandom(12)
    sealed = MAGIC + nonce + AESGCM(_key(key_b64)).encrypt(nonce, plain, ref.encode('ascii'))
    os.makedirs(PROFILES_DIR, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(sealed)
    os.replace(tmp, path)
    return len(sealed)


def restore(ref: str, key_b64: str, dest: str) -> bool:
    """보관한 프로필을 dest 에 푼다. 보관이 없으면 False. 열쇠가 맞지 않으면 보관을 지우고 VaultError."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    path = blob_path(ref)
    if not os.path.exists(path):
        return False
    with open(path, 'rb') as f:
        sealed = f.read()
    try:
        if sealed[:4] != MAGIC:
            raise InvalidTag()
        plain = AESGCM(_key(key_b64)).decrypt(sealed[4:16], sealed[16:], ref.encode('ascii'))
    except InvalidTag:
        forget(ref)
        raise VaultError('보관한 구글 로그인을 열 수 없어 지웠습니다. 다시 로그인해 주세요.') from None
    root = os.path.realpath(dest)
    os.makedirs(root, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(plain)) as zf:
        for info in zf.infolist():
            target = os.path.realpath(os.path.join(root, info.filename))
            if not target.startswith(root + os.sep):
                continue                      # 폴더 밖으로 나가는 이름은 버린다
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, 'wb') as out:
                out.write(src.read())
    os.utime(path)                            # 쓴 날 — 60일 정리 기준
    return True


def forget(ref: str):
    try:
        os.remove(blob_path(ref))
    except (OSError, VaultError):
        pass


def sweep(now: float | None = None):
    """켤 때 — 60일 넘게 안 쓴 보관과 쓰다 만 조각을 지운다."""
    if not os.path.isdir(PROFILES_DIR):
        return
    limit = (now or time.time()) - KEEP_DAYS * 86400
    for name in os.listdir(PROFILES_DIR):
        path = os.path.join(PROFILES_DIR, name)
        try:
            if name.endswith('.tmp') or os.path.getmtime(path) < limit:
                os.remove(path)
        except OSError:
            pass


# ── 프로필에 구글 로그인이 들어 있나 (2026-10-14 — «지우기는 뜨는데 로그인은 안 돼 있음» 진단·표시용) ──────────────
# Edge 의 쿠키 DB(Default/Network/Cookies)에서 이름·호스트·만료만 본다 — 값(암호화됨)은 읽지 않는다.
# Edge 가 떠 있는 동안에는 파일을 독점으로 잠가 읽을 수 없다(None) — Edge 를 띄우기 전·닫은 뒤에만.
GOOGLE_LOGIN_COOKIES = ('SID', '__Secure-1PSID', '__Secure-3PSID')
CHROME_EPOCH = 11644473600          # 1601-01-01 → 1970-01-01 (초)


def google_login_in(profile_dir: str, now: float | None = None) -> bool | None:
    import sqlite3
    path = os.path.join(profile_dir, 'Default', 'Network', 'Cookies')
    if not os.path.exists(path):
        return False
    try:
        with open(path, 'rb') as f:
            data = f.read()
        con = sqlite3.connect(':memory:')
        try:
            con.deserialize(data)
            rows = con.execute(
                "select expires_utc, has_expires from cookies where host_key = '.google.com' and name in (%s)"
                % ','.join('?' * len(GOOGLE_LOGIN_COOKIES)), GOOGLE_LOGIN_COOKIES).fetchall()
        finally:
            con.close()
    except (OSError, sqlite3.Error):
        return None
    now = time.time() if now is None else now
    return any(not has or expires / 1e6 - CHROME_EPOCH > now for expires, has in rows)
