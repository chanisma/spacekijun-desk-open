"""Ed25519 서명·검증 — RFC 8032 6장의 참조 구현을 그대로 옮긴 것 (외부 라이브러리 없이).

데스크 자동 업데이트(core/updater.py)가 내려받을 판의 목록(latest.json)이 우리가 서명한 것인지 본다.
느리지만(검증 한 번에 수십 ms) 업데이트를 확인할 때 한 번만 쓴다. 정확성은 RFC 8032 7.1 의 시험
벡터로 확인한다 (test_updater.py).
"""
from __future__ import annotations

import hashlib

p = 2 ** 255 - 19
d = -121665 * pow(121666, p - 2, p) % p
q = 2 ** 252 + 27742317777372353535851937790883648493
_SQRT_M1 = pow(2, (p - 1) // 4, p)


def _sha512_modq(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), 'little') % q


def _add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C = 2 * P[3] * Q[3] * d % p
    D = 2 * P[2] * Q[2] % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % p, G * H % p, F * G % p, E * H % p)


def _mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q) -> bool:
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _recover_x(y: int, sign: int):
    if y >= p:
        return None
    x2 = (y * y - 1) * pow(d * y * y + 1, p - 2, p)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p != 0:
        x = x * _SQRT_M1 % p
    if (x * x - x2) % p != 0:
        return None
    if (x & 1) != sign:
        x = p - x
    return x


_GY = 4 * pow(5, p - 2, p) % p
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % p)


def _compress(P) -> bytes:
    zinv = pow(P[2], p - 2, p)
    x, y = P[0] * zinv % p, P[1] * zinv % p
    return int.to_bytes(y | ((x & 1) << 255), 32, 'little')


def _decompress(data: bytes):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % p)


def _expand(secret: bytes):
    if len(secret) != 32:
        raise ValueError('비밀 키는 32바이트입니다.')
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    return _compress(_mul(_expand(secret)[0], _G))


def sign(secret: bytes, message: bytes) -> bytes:
    a, prefix = _expand(secret)
    A = _compress(_mul(a, _G))
    r = _sha512_modq(prefix + message)
    R = _compress(_mul(r, _G))
    s = (r + _sha512_modq(R + A + message) * a) % q
    return R + int.to_bytes(s, 32, 'little')


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _decompress(public)
    R = _decompress(signature[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(signature[32:], 'little')
    if s >= q:
        return False
    h = _sha512_modq(signature[:32] + public + message)
    return _equal(_mul(s, _G), _add(R, _mul(h, A)))
