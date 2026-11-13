"""교실판 ↔ 서버 — QR 을 띄우고, 교사의 승인을 기다리고, 수업을 연장·끝낸다.

서버는 SPACEKIJUN 의 DB 함수 `classroom_device_call`(PostgREST RPC, anon 키)이다(저장소 D:\\spacekijun,
20261110150000_classroom_device_rpc.sql · docs/features/classroom-link.md). 2026-11-10 까지는 Edge Function
`classroom-link` 를 불렀는데, QR 대기 중 2초마다 묻는 호출이 Edge Function 한도를 넘길 만큼 많아 DB 로 옮겼다
(교사 쪽 승인만 Edge Function 에 남는다). 이 기기는 **로그인하지 않는다.** 처음 켤 때 만든 임의 키(device key)를
DPAPI 로 이 PC 에 묶어 두고, 그 키로만 자기를 증명한다. 서버는 키의 sha256 만 안다.

흐름
  start  → QR 한 장(10분). 화면에 승인 주소를 QR 로 띄운다. 수업 중엔 purpose='drive' 로
           «드라이브 다시 연결» QR 도 만든다(구글 토큰 1시간이 끝났을 때).
  poll   → 교사가 휴대폰에서 승인하면 handoff(세팅·구글 토큰·스페이스기전 세션)를 **딱 한 번** 받는다.
           받은 handoff 는 메모리에만 둔다 — 디스크에 쓰지 않는다.
  extend → 수업 연장(승인 시각부터 최대 4시간)
  end    → 수업 끝. 서버가 이 기기에 준 스페이스기전 로그인을 끊는다.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import urllib.error
import urllib.request

from . import notify
from .secretstore import decrypt, encrypt

DATA_DIR = os.path.join(os.path.expandvars('%LOCALAPPDATA%'), 'SpacekijunClassroom')
KEY_PATH = os.path.join(DATA_DIR, 'device.key')
SETTINGS_PATH = os.path.join(DATA_DIR, 'classroom.json')
APPROVE_URL = 'https://spacekijun.lovable.app/classroom/link/'
PLATFORM = 'windows'

# 서버 오류 코드 → 교실 화면 문구
ERROR_TEXT = {
    'rate_limited': 'QR 을 너무 자주 새로 만들었습니다. 잠시 뒤 다시 시도합니다.',
    'invalid_device': '이 기기의 연결 키가 올바르지 않습니다. 프로그램을 다시 켜 주세요.',
    'network': '인터넷에 연결되지 않았습니다. 연결되면 QR 이 다시 나타납니다.',
}


class LinkError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(ERROR_TEXT.get(code, '서버와 연결하지 못했습니다. 잠시 뒤 다시 시도합니다.'))


def load_settings() -> dict:
    """이 기기의 설정 — 기기 이름, 관리자가 등록한 추가 프로그램.

    {"device_name": "2-3 교실", "programs": {"geogebra": {"label": "지오지브라", "path": "C:\\\\...\\\\GeoGebra.exe"}}}
    """
    try:
        with open(SETTINGS_PATH, encoding='utf-8') as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(value: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_PATH)


def device_name() -> str:
    name = str(load_settings().get('device_name') or '').strip()
    return (name or socket.gethostname() or '교실 PC')[:40]


def device_key() -> str:
    """이 PC 에 묶인 임의 키. 없거나 풀리지 않으면(다른 PC 에서 복사) 새로 만든다."""
    try:
        with open(KEY_PATH, 'rb') as f:
            key = decrypt(f.read()).decode('ascii')
        if 32 <= len(key) <= 128:
            return key
    except Exception:
        pass
    key = secrets.token_urlsafe(32)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KEY_PATH, 'wb') as f:
        f.write(encrypt(key.encode('ascii')))
    return key


def rpc_url() -> str:
    return notify.config()['url'].rstrip('/') + '/rest/v1/rpc/classroom_device_call'


class Client:
    """서버 호출. 테스트에서는 opener 를 바꿔 끼운다."""

    def __init__(self, key: str | None = None, url: str | None = None, opener=urllib.request.urlopen,
                 anon_key: str | None = None):
        self.key = key or device_key()
        self.url = url or rpc_url()
        self.anon_key = anon_key or notify.config()['anon_key']
        self.opener = opener

    def _call(self, action: str, **body) -> dict:
        data = json.dumps({'p_action': action, 'p_device_key': self.key, 'p_args': body}).encode('utf-8')
        req = urllib.request.Request(self.url, data=data, method='POST',
                                     headers={'Content-Type': 'application/json', 'apikey': self.anon_key,
                                              'Authorization': 'Bearer ' + self.anon_key})
        try:
            with self.opener(req, timeout=15) as res:
                result = json.loads(res.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            try:
                code = json.loads(e.read().decode('utf-8')).get('error') or 'server_error'
            except Exception:
                code = 'server_error'
            raise LinkError(code) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise LinkError('network') from None
        if not isinstance(result, dict):
            raise LinkError('server_error')
        if result.get('error'):                  # 알려진 오류는 200 에 {"error": 코드}로 온다
            raise LinkError(str(result['error']))
        return result

    def start(self, name: str, purpose: str = 'session') -> dict:
        """→ {'code', 'expires_at'}. purpose='drive' = 수업 중 «드라이브 다시 연결» QR"""
        return self._call('start', name=name[:40], platform=PLATFORM, purpose=purpose)

    def poll(self, code: str) -> dict:
        """→ {'status': pending|expired|approved|active|ended|cancelled|unknown, 'handoff'?, 'ends_at'?}"""
        return self._call('poll', code=code)

    def extend(self, code: str, minutes: int) -> dict:
        return self._call('extend', code=code, minutes=int(minutes))

    def end(self, code: str) -> dict:
        return self._call('end', code=code)

    # 휴대폰으로 구글 비밀번호 입력(core/classroom_type.py) — 암호문만 오간다
    def type_start(self, session_code: str, device_pub: str) -> dict:
        return self._call('type_start', code=session_code, device_pub=device_pub)

    def type_poll(self, code: str) -> dict:
        return self._call('type_poll', code=code)

    def type_cancel(self, code: str) -> dict:
        return self._call('type_cancel', code=code)

    def forget_profile(self, code: str) -> dict:
        """지금 수업 중인 선생님의 이 PC 구글 로그인 보관 열쇠를 서버에서 지운다(A+)"""
        return self._call('forget_profile', code=code)


def approve_url(code: str) -> str:
    return APPROVE_URL + code


def qr_svg(text: str) -> str:
    """QR 그림(SVG 문자열). 화면 크기에 맞춰 늘어나도록 viewBox 만 남긴다."""
    import segno
    qr = segno.make(text, error='m')
    return qr.svg_inline(scale=1, border=2, dark='#111', light='#fff', omitsize=True)
