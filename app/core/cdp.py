"""
CEF 원격 디버깅(CDP) 최소 클라이언트 — cdp.js 의 Python 포팅. **표준 라이브러리만** 쓴다.

왜 직접 만드나
  · 쿨메신저는 CEF 91 이라 Playwright 의 `connect_over_cdp` 가 실패한다
    ("Browser context management is not supported") — 브라우저 레벨 CDP 가 없어서
    **페이지 타깃 WebSocket 에 직접** 붙어야 한다.
  · `websocket-client` 같은 패키지를 넣으면 배포판 의존성이 늘어난다. 우리가 쓰는 건
    "텍스트 프레임 하나 보내고 하나 받기" 뿐이라 소켓으로 충분하다.

전제: 앱이 `--remote-debugging-port=9222` 로 떠 있어야 한다.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import urllib.request

PORT = int(os.environ.get('CM_CDP_PORT', '9222'))


class CdpError(RuntimeError):
    pass


def targets(port: int = PORT, timeout: float = 5) -> list[dict]:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        raise CdpError(
            '쿨메신저 답장 연동에 연결하지 못했습니다. 데스크의 연결 및 설정에서 '
            '‘쿨메신저 연결’을 눌러 주세요.') from e


def find_target(url_part: str, port: int = PORT) -> dict:
    pages = [t for t in targets(port) if t.get('type') == 'page']
    for t in pages:
        if url_part in (t.get('url', '') + t.get('title', '')):
            return t
    raise CdpError(f"CDP 타깃을 찾지 못했습니다 (검색어: '{url_part}'). "
                   f"열려 있는 페이지: {[t.get('url', '')[:60] for t in pages]}")


class Connection:
    """WebSocket 위의 아주 얇은 JSON-RPC. 한 번에 한 요청만 주고받는다."""

    def __init__(self, ws_url: str, timeout: float = 20.0):
        if not ws_url.startswith('ws://'):
            raise CdpError(f'지원하지 않는 주소: {ws_url}')
        rest = ws_url[len('ws://'):]
        hostport, _, path = rest.partition('/')
        host, _, port = hostport.partition(':')
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        self.sock.settimeout(timeout)
        self._handshake(host, port, '/' + path)
        self._id = 0

    def _handshake(self, host, port, path):
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f'GET {path} HTTP/1.1\r\n'
               f'Host: {host}:{port}\r\n'
               'Upgrade: websocket\r\n'
               'Connection: Upgrade\r\n'
               f'Sec-WebSocket-Key: {key}\r\n'
               'Sec-WebSocket-Version: 13\r\n\r\n')
        self.sock.sendall(req.encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CdpError('CDP 핸드셰이크 중 연결이 끊겼습니다.')
            buf += chunk
        if b'101' not in buf.split(b'\r\n', 1)[0]:
            raise CdpError('CDP 핸드셰이크 실패: ' + buf.split(b'\r\n', 1)[0].decode('latin1'))

    # ── 프레임 ────────────────────────────────────────────────
    def _send_text(self, text: str):
        payload = text.encode('utf-8')
        header = bytearray([0x81])                       # FIN + text
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < (1 << 16):
            header.append(0x80 | 126)
            header += struct.pack('>H', n)
        else:
            header.append(0x80 | 127)
            header += struct.pack('>Q', n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_exact(self, n: int) -> bytes:
        out = b''
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise CdpError('CDP 연결이 끊겼습니다.')
            out += chunk
        return out

    def _recv_text(self) -> str:
        while True:
            b0, b1 = self._recv_exact(2)
            opcode = b0 & 0x0F
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack('>H', self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack('>Q', self._recv_exact(8))[0]
            mask = self._recv_exact(4) if (b1 & 0x80) else None
            data = self._recv_exact(length)
            if mask:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if opcode == 0x8:                            # close
                raise CdpError('CDP 가 연결을 닫았습니다.')
            if opcode == 0x9:                            # ping → pong
                continue
            if opcode in (0x1, 0x0):
                return data.decode('utf-8', 'replace')

    # ── JSON-RPC ──────────────────────────────────────────────
    def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        want = self._id
        self._send_text(json.dumps({'id': want, 'method': method, 'params': params or {}}))
        for _ in range(50):                              # 이벤트가 섞여 오므로 id 로 골라낸다
            msg = json.loads(self._recv_text())
            if msg.get('id') == want:
                return msg
        raise CdpError(f'{method} 응답을 받지 못했습니다.')

    def evaluate(self, expression: str):
        r = self.send('Runtime.evaluate',
                      {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
        res = r.get('result', {})
        if 'exceptionDetails' in res:
            raise CdpError('JS 오류: %s' % res['exceptionDetails'].get('text'))
        return res.get('result', {}).get('value')

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def connect(url_part: str, port: int = PORT) -> Connection:
    return Connection(find_target(url_part, port)['webSocketDebuggerUrl'])
