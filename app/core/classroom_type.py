"""휴대폰으로 구글 비밀번호 입력(2026-10-14 사용자 결정) — 교실 기기 쪽.

교실 화면에서 구글 웹에 로그인할 때 칠판에서 비밀번호를 치면 학생들에게 보일 수 있다. 그래서
  1. 이 기기가 일회용 키(P-256)를 만들고 공개키를 서버에 맡긴 뒤 QR(…/classroom/type/<표>#k=<공개키>)을 띄운다.
  2. 수업 중인 선생님이 휴대폰으로 찍어 비밀번호를 넣으면, 휴대폰이 그 공개키로 암호화해 보낸다(spacekijun typeCrypto.ts).
  3. 이 기기가 받아 풀고, 수업용 Edge 의 구글 로그인 칸에 넣고 [다음]을 누른다(UI Automation — 아래). 비밀번호는 저장하지 않는다.
서버는 암호문만 맡았다 넘긴다. 규칙: ECDH → HKDF-SHA256(salt = 표, info = INFO) → AES-256-GCM. 안드로이드판 TypeRelay.kt 와 같다.
"""
from __future__ import annotations

import base64
import re
import time

INFO = b'spacekijun-classroom-type-v1'
TYPE_URL = 'https://spacekijun.lovable.app/classroom/type/'


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


class TypeKey:
    """한 번 쓰고 버리는 키 — 이 기기 메모리에만 있다"""

    def __init__(self, private=None):
        from cryptography.hazmat.primitives.asymmetric import ec
        self._private = private or ec.generate_private_key(ec.SECP256R1())

    @classmethod
    def from_hex(cls, hex_value: str) -> 'TypeKey':
        from cryptography.hazmat.primitives.asymmetric import ec
        return cls(ec.derive_private_key(int(hex_value, 16), ec.SECP256R1()))

    @property
    def public(self) -> str:
        from cryptography.hazmat.primitives import serialization
        raw = self._private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        return b64url(raw)

    def open(self, code: str, payload: dict) -> str:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64url(payload['epk']))
        shared = self._private.exchange(ec.ECDH(), peer)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=code.encode('utf-8'), info=INFO).derive(shared)
        return AESGCM(key).decrypt(unb64url(payload['iv']), unb64url(payload['ct']), None).decode('utf-8')


def type_url(code: str, public: str) -> str:
    return f'{TYPE_URL}{code}#k={public}'


# ── 수업용 Edge 의 구글 로그인 칸에 넣기 — UI Automation ─────────────────────────────
# 디버깅 포트(CDP)를 쓰지 않는다: 구글은 --remote-debugging-port 로 띄운 Edge 의 로그인을 아예 막는다
# («로그인할 수 없음 — 브라우저 또는 앱이 안전하지 않을 수 있습니다», 2026-10-14 실제 확인 — 사람이 직접 눌러도 막힌다).
# 대신 Windows 접근성(UI Automation)으로 그 Edge 창 안의 칸에 값을 넣고 [다음] 버튼을 누른다. 키 입력·클립보드는 쓰지 않는다.
# UIA 는 Edge 의 **앞에 띄운 탭**만 보인다 — 구글 로그인 탭이 뒤에 있으면 찾지 못한다.

GOOGLE_LOGIN = 'https://accounts.google.com/'
NEXT_NAMES = re.compile(r'\s*(다음|Next)\s*')        # 이름은 바뀔 수 있다 — 0개·2개 이상이면 누르지 않는다


def fill_step(ui, doc, email: str, password: str) -> str:
    """구글 로그인 화면 한 단계 → 'password'(넣고 [다음]) · 'password_manual'(넣었지만 [다음]을 못 찾음)
    · 'chooser' · 'email' · 'wait' · 'none'. 구글 로그인은 이메일 → 비밀번호 두 화면이다(계정 고르기가 끼기도)."""
    if not ui.url(doc).startswith(GOOGLE_LOGIN):
        return 'none'                                    # 다른 사이트에는 절대 넣지 않는다
    box = ui.password(doc)
    if box is not None:
        ui.set_value(box, password)
        button = ui.next_button(doc)
        if button is None:
            return 'password_manual'
        ui.invoke(button)
        return 'password'
    account = ui.account(doc, email) if email else None
    if account is not None:
        ui.invoke(account)
        return 'chooser'
    box = ui.identifier(doc)
    if box is not None and (email or ui.value(box)):
        if not ui.value(box):
            ui.set_value(box, email)
        button = ui.next_button(doc)
        if button is None:
            return 'wait'                                # 선생님이 [다음]을 누르면 비밀번호 화면에서 이어 넣는다
        ui.invoke(button)
        return 'email'
    return 'none'


class EdgeUia:
    """수업용 Edge 창(그 프로세스 것만)의 접근성 트리. pywebview 가 이미 쓰는 pythonnet 으로 .NET UIAutomationClient 를 부른다."""

    def __init__(self):
        import clr
        import System
        from System.Reflection import Assembly
        for name in ('UIAutomationTypes', 'UIAutomationClient'):
            Assembly.Load(name + ', Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35')
            clr.AddReference(name)
        from System.Windows import Automation
        self.S, self.A = System, Automation
        self.E = Automation.AutomationElement

    def _is(self, prop, value):
        return self.A.PropertyCondition(prop, value)

    def _all(self, root, cond):
        return list(root.FindAll(self.A.TreeScope.Descendants, cond))

    def _type(self, control):
        return self._is(self.E.ControlTypeProperty, control)

    def documents(self, pids) -> list:
        """그 Edge 창들의 앞 탭 문서"""
        docs = []
        for pid in pids:
            for win in self.E.RootElement.FindAll(self.A.TreeScope.Children, self._is(self.E.ProcessIdProperty, self.S.Int32(pid))):
                found = []
                for _ in range(8):                        # 처음 물으면 Edge 가 접근성을 켜느라 잠깐 걸린다
                    found = self._all(win, self._type(self.A.ControlType.Document))
                    if found:
                        break
                    time.sleep(0.25)
                docs += found
        return docs

    def google_docs(self, pids) -> list:
        """그 Edge 창들에서 앞에 띄운 구글 로그인 문서"""
        return [d for d in self.documents(pids) if self.url(d).startswith(GOOGLE_LOGIN)]

    def url(self, doc) -> str:
        ok, pattern = doc.TryGetCurrentPattern(self.A.ValuePattern.Pattern, None)
        return str(pattern.Current.Value or '') if ok else ''

    def _visible(self, items):
        return [e for e in items if not e.Current.IsOffscreen]

    def password(self, doc):
        # 구글 화면에는 숨은 비밀번호 칸(hiddenPassword)이 먼저 있다 — 보이는 것만
        cond = self.A.AndCondition(self._type(self.A.ControlType.Edit), self._is(self.E.IsPasswordProperty, self.S.Boolean(True)))
        found = self._visible(self._all(doc, cond))
        return found[0] if found else None

    def identifier(self, doc):
        # 이메일 칸 = <input type=text id=identifierId> — UIA 의 AutomationId 가 HTML id 다
        found = self._visible(self._all(doc, self._is(self.E.AutomationIdProperty, 'identifierId')))
        return found[0] if found else None

    def account(self, doc, email: str):
        email = email.casefold()
        kinds = (self.A.ControlType.Hyperlink, self.A.ControlType.Button, self.A.ControlType.ListItem)
        cond = self.A.OrCondition(*[self._type(k) for k in kinds])
        found = [e for e in self._visible(self._all(doc, cond)) if email in (e.Current.Name or '').casefold()]
        return found[0] if len(found) == 1 else None

    def next_button(self, doc):
        found = [b for b in self._visible(self._all(doc, self._type(self.A.ControlType.Button)))
                 if NEXT_NAMES.fullmatch(b.Current.Name or '')]
        return found[0] if len(found) == 1 else None

    def account_emails(self, pids) -> list:
        """앞 탭(아무 구글 페이지)의 계정 단추 «Google 계정: 이름 (이메일)» 에서 이메일"""
        found = []
        kinds = (self.A.ControlType.Hyperlink, self.A.ControlType.Button)
        cond = self.A.OrCondition(*[self._type(k) for k in kinds])
        for doc in self.documents(pids):
            if not re.match(r'https://[a-z0-9.-]*\.google\.com/', self.url(doc)):
                continue
            for el in self._all(doc, cond):
                name = el.Current.Name or ''
                m = ACCOUNT_LABEL.search(name)
                if m:
                    found.append(m.group(1).lower())
                elif SIGN_IN_LABEL.fullmatch(name):
                    found.append('')                    # 오른쪽 위 [로그인] — 로그인 안 됨
        return found

    def value(self, el) -> str:
        ok, pattern = el.TryGetCurrentPattern(self.A.ValuePattern.Pattern, None)
        return str(pattern.Current.Value or '') if ok else ''

    def set_value(self, el, text: str):
        el.SetFocus()
        el.GetCurrentPattern(self.A.ValuePattern.Pattern).SetValue(text)

    def invoke(self, el):
        el.GetCurrentPattern(self.A.InvokePattern.Pattern).Invoke()


# 구글 페이지 오른쪽 위 계정 단추의 접근성 이름 — 한국어 «Google 계정: 이름 (이메일)», 영어 «Google Account: Name (email)».
# 이름은 바뀔 수 있다 — 못 찾으면 «모름»(None)으로 두고, «로그인 안 됨»이라고 단정하지 않는다.
SIGN_IN_LABEL = re.compile(r'\s*(로그인|Sign in)\s*', re.I)
ACCOUNT_LABEL = re.compile(r'Google\s*(?:계정|Account)\s*:.*\(([^()\s]+@[^()\s]+)\)', re.I)


def signed_in_email(pids, ui=None) -> str | None:
    """수업용 Edge 의 앞 탭이 구글 페이지면 → 계정 이메일 · ''(로그인 단추가 보임 = 로그인 안 됨). 모르면 None"""
    if not pids:
        return None
    found = (ui or EdgeUia()).account_emails(pids)
    emails = [e for e in found if e]
    return emails[0] if emails else ('' if found else None)


def login_page_open(pids, ui=None) -> bool:
    """수업용 Edge 에 구글 로그인 화면이 앞에 떠 있나"""
    if not pids:
        return False
    try:
        return bool((ui or EdgeUia()).google_docs(pids))
    except Exception:
        return False


STUCK_EMAIL = '구글 로그인이 이메일 단계에서 넘어가지 않습니다. 구글 로그인 창의 안내를 확인해 주세요.'
NOT_FOUND = '구글 로그인 화면을 찾지 못했습니다. 수업용 Edge 에서 구글 로그인 탭을 앞에 띄운 뒤 다시 시도해 주세요.'


def fill_in_edge(pids, email: str, password: str, timeout: float = 25.0, sleep=time.sleep, ui=None) -> str:
    """수업용 Edge 의 구글 로그인 화면에 넣는다 → 'ok' · 'manual'(넣었고 [다음]은 선생님이) · 오류 문구.
    비밀번호 화면까지 단계를 넘기며 기다린다."""
    if not pids:
        return '수업용 Edge 를 찾지 못했습니다. 구글 로그인 창을 다시 열어 주세요.'
    try:
        ui = ui or EdgeUia()
    except Exception:
        return '이 PC 에서 화면 자동 입력(UI Automation)을 쓸 수 없습니다.'
    deadline = time.time() + timeout
    emails = 0
    while time.time() < deadline:
        try:
            docs = ui.google_docs(pids)
            step = fill_step(ui, docs[0], email, password) if docs else 'none'
        except Exception:
            step = 'none'
        if step == 'password':
            return 'ok'
        if step == 'password_manual':
            return 'manual'
        emails = emails + 1 if step == 'email' else 0
        if emails >= 4:                                  # [다음]을 눌러도 이메일 화면 그대로 — 구글이 계정을 못 찾았다 등
            return STUCK_EMAIL
        sleep(2.0 if step in ('email', 'chooser') else 1.0)
    return NOT_FOUND
