"""개인정보가 든 글인가 — PC 밖(AI 분석)으로 보내기 **전에** 이 PC 에서 거른다 (2026-10-30 요청).

메인 상주 에이전트가 쿨메신저 쪽지를 분석할 때 «개인정보가 포함된 경우 분석하지 않음». 무엇에 걸렸는지 이름만 돌려주고 글은 남기지 않는다.

**막는 것은 «개인의 정보 자체»다 (2026-11-05 사용자 결정).** 첫 판은 «성적»«상담» 같은 낱말이 보이기만 해도 막아
«학기말 성적처리 일정» 같은 업무 안내까지 막았다(정태오 선생님 쪽지). 이제는

  1. 그 자체가 개인정보인 번호·학생 지칭 — 보이면 막는다
     주민등록번호 · 휴대폰·전화번호 · 이메일 · 계좌번호 · «N학년 N반 N번» · «N-N N번» · 학번(다섯 자리)+이름
  2. 민감한 주제(성적·건강·상담·장애·가정 형편·학교폭력·징계·출결 사유) — **특정한 사람에게 붙어 있을 때만** 막는다
     · 사람 지칭(«홍길동 학생», «김OO 선생님», 위 1의 학생 지칭)이 주제 낱말 가까이(WINDOW 글자) 있을 때
     · 성적은 이름 바로 뒤의 점수·등급·등수(«홍길동 85점», «김민수 2등급»)도 막는다
     · 성적·상담·학교폭력·출결 사유는 학생에게 붙을 때(교사 이름 + «성적처리»는 업무), 건강·장애·가정 형편·징계는 누구든
⚠️ 사람 이름은 흔한 성씨로 시작하는 세 글자로 어림한다 — 놓친 것·잘못 막은 것이 보이면 여기와 회귀(test_agent_restore.py)에 더한다.
"""
from __future__ import annotations

import re

PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ('주민등록번호', re.compile(r'(?<!\d)\d{6}\s*-\s*[1-8]\d{6}(?!\d)')),
    ('휴대폰 번호', re.compile(r'(?<!\d)01[016789][\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)')),
    ('전화번호', re.compile(r'(?<!\d)0(?:2|[3-6]\d|70)[\s.)-]+\d{3,4}[\s.-]+\d{4}(?!\d)')),
    ('이메일', re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')),
    ('계좌번호', re.compile(r'(?<!\d)\d{2,6}-\d{2,6}-\d{2,8}(?:-\d{1,4})?(?!\d)')),
    ('학년·반·번호', re.compile(r'[1-6]\s*학년\s*\d{1,2}\s*반\s*\d{1,2}\s*번')),
    ('반·번호', re.compile(r'(?<![\d-])[1-6]\s*-\s*\d{1,2}\s+\d{1,2}\s*번')),
    ('학번과 이름', re.compile(r'(?<!\d)[1-3]\d{4}\s*[가-힣]{2,4}(?![가-힣])')),
)

SURNAMES = ('김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경')
NOT_NAMES = ('이번주', '이번달', '이번에', '지난주', '지난달', '금요일', '우리반', '전학년', '전교생', '고학년', '신입생', '재학생',
             '편입생', '전입생', '전학생', '해당반', '한부모', '다문화', '모든반', '각학년')
NAME = rf'(?<![가-힣])(?!{"|".join(NOT_NAMES)})[{SURNAMES}][가-힣]{{2}}'
# 이름 뒤의 호칭 — 학생 쪽과 누구든 쪽. 뒤에 «들·회·부·증» 등이 붙으면 낱말(학생회·학생부)이라 사람이 아니다
STUDENT_REF = re.compile(NAME + r'\s*(?:학생|군|양|학부모|어머님|어머니|아버님|아버지|보호자)(?![들회부증수과])')
ANYONE_REF = re.compile(NAME + r'\s*(?:학생|군|양|학부모|어머님|어머니|아버님|아버지|보호자|선생님|선생|교사|샘|님|씨|부장|주무관|실무사)(?![들회부증수과])')
STUDENT_ID = re.compile('|'.join(p.pattern for name, p in PATTERNS if name in ('학년·반·번호', '반·번호', '학번과 이름')))
SCORE_AFTER_NAME = re.compile(NAME + r'(?:\s*(?:학생|군|양))?[\s:,(은는이가의]{0,4}\d{1,3}(?:\.\d+)?\s*(?:점(?![검수])|등급|등(?![교록]))')
WINDOW = 40

TOPICS: tuple[tuple[str, tuple[str, ...], bool], ...] = (     # (이름, 낱말, 학생에게 붙을 때만)
    ('성적', ('성적', '점수', '석차', '내신등급', '평균점'), True),
    ('건강', ('건강', '진단', '질병', '병원', '입원', '수술', '병명', '투약', '복약', '감염', '확진', '병가'), False),
    ('상담', ('상담', '심리', '우울', '자해', '자살'), True),
    ('장애', ('장애',), False),
    ('가정 형편', ('가정환경', '기초생활', '수급자', '한부모', '차상위', '저소득', '다문화가정'), False),
    ('학교폭력·징계', ('학교폭력', '학폭', '선도위원회'), True),
    ('학교폭력·징계', ('징계',), False),
    ('출결 사유', ('결석사유', '결석 사유', '조퇴 사유', '병결'), True),
)


def _person_spans(text: str, students_only: bool) -> list[tuple[int, int]]:
    refs = [STUDENT_REF if students_only else ANYONE_REF, STUDENT_ID]
    return [m.span() for ref in refs for m in ref.finditer(text)]


def _near(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(s - WINDOW <= end and start <= e + WINDOW for s, e in spans)


def findings(text: str) -> list[str]:
    """걸린 것의 이름 (없으면 빈 목록). 글은 돌려주지 않는다."""
    text = text or ''
    found = [name for name, pattern in PATTERNS if pattern.search(text)]
    spans = {flag: _person_spans(text, flag) for flag in (True, False)}
    for name, words, students_only in TOPICS:
        if name in found:
            continue
        for word in words:
            hit = any(_near(spans[students_only], m.start(), m.end()) for m in re.finditer(re.escape(word), text))
            if hit:
                found.append(name)
                break
    if '성적' not in found and SCORE_AFTER_NAME.search(text):
        found.append('성적')
    return found


def is_safe(text: str) -> bool:
    return not findings(text)
