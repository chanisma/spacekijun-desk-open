"""
자격증명 보관 — Windows DPAPI 로 **사용자·기기에 묶어** 암호화한다.

지금까지는 `.secrets/klef.credentials.json` 에 인증서 암호가 **평문**으로 있었다.
개인 PC 에서 혼자 쓸 때는 그럭저럭이지만, 다른 선생님들께 배포할 프로그램에는 맞지 않는다.

DPAPI 는 그 PC 의 그 사용자 계정으로만 복호화된다 — 파일만 복사해 가면 풀지 못한다.
별도 암호를 사람이 기억할 필요가 없다는 점이 이 방식의 장점이다.

  from core import secretstore as ss
  ss.save({'id': 'spacekijun', 'cert_password': '...'})
  ss.load()['cert_password']
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
from . import edition

DATA_DIR = edition.DATA_DIR      # 판마다 따로 (core/edition.py)
STORE_PATH = os.path.join(DATA_DIR, 'credentials.dat')

# 기존 평문 파일 — 처음 한 번만 읽어 옮겨 온다
LEGACY_JSON = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '.secrets', 'klef.credentials.json'))


class SecretError(RuntimeError):
    pass


class _BLOB(ctypes.Structure):
    _fields_ = [('cbData', wt.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _take(b: _BLOB) -> bytes:
    out = ctypes.string_at(b.pbData, b.cbData)
    ctypes.windll.kernel32.LocalFree(b.pbData)
    return out


def encrypt(data: bytes) -> bytes:
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(_blob(data)), None, None, None, None, 0, ctypes.byref(out)):
        raise SecretError('DPAPI 암호화 실패')
    return _take(out)


def decrypt(data: bytes) -> bytes:
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(_blob(data)), None, None, None, None, 0, ctypes.byref(out)):
        raise SecretError('저장된 자격증명을 풀지 못했습니다. '
                          '다른 PC/계정에서 복사된 파일이거나 손상됐습니다 — 다시 저장하세요.')
    return _take(out)


def save(values: dict) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STORE_PATH, 'wb') as f:
        f.write(encrypt(json.dumps(values, ensure_ascii=False).encode('utf-8')))
    return STORE_PATH


def load() -> dict:
    if os.path.exists(STORE_PATH):
        with open(STORE_PATH, 'rb') as f:
            return json.loads(decrypt(f.read()).decode('utf-8'))
    # 평문 파일이 남아 있으면 한 번 옮겨 온다 (원본은 사용자가 직접 지우도록 둔다)
    if os.path.exists(LEGACY_JSON):
        with open(LEGACY_JSON, encoding='utf-8') as f:
            old = json.load(f)
        values = {'id': old.get('id', ''), 'cert_password': old.get('certPassword', ''),
                  'cert_match': old.get('certMatch')}
        save(values)
        return values
    raise SecretError('저장된 자격증명이 없습니다. 설정에서 아이디와 인증서 암호를 입력하세요.')


def has_credentials() -> bool:
    return os.path.exists(STORE_PATH) or os.path.exists(LEGACY_JSON)


def clear():
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)
