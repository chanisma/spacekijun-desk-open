"""
말한 내용을 NEIS 화면으로 옮긴다 — "인공지능 기초 과목 출결해야 해" → 과목별출결관리 + 과목명.

두 단계로 고른다.
  1. **이름 맞춤**: 사용자가 화면 이름을 거의 그대로 말했으면 모델을 부르지 않는다. 빠르고 틀릴
     일이 없다.
  2. **모델**: 그래도 못 고르면 Solar 에게 *색인에 있는 이름 중에서만* 고르게 한다. 목록에 없는
     이름을 지어내면 버린다 — 없는 메뉴로 데려가는 것이 못 찾는 것보다 나쁘다.

모델 호출은 `summarize.py` 와 같은 Upstage 엔드포인트를 표준 라이브러리로 쓴다.
키가 없으면 1번만으로 동작한다(기능이 아예 죽지는 않게).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import summarize

API_URL = summarize.API_URL
MODEL = summarize.MODEL

SYSTEM_PROMPT = (
    '너는 교사가 말한 업무를 NEIS 화면 하나로 연결한다.\n'
    '규칙:\n'
    '- screen 은 <화면목록> 에 **글자 그대로 있는 이름**만 쓴다. 목록에 없는 이름을 지어내지 않는다.\n'
    '- 말이 뭉뚱그려져 있어도 목록에서 가장 가까운 화면을 하나 고른다. 정말 관련된 화면이\n'
    '  하나도 없을 때만 screen 을 빈 문자열로 둔다.\n'
    '- subject·grade·room·date 는 screen 과 무관하게 **교사가 말한 그대로** 채운다.\n'
    '  subject 는 과목명, grade 는 학년 숫자, room 은 반 숫자다. 말하지 않았으면 빈 문자열.\n'
    '  date 는 YYYY-MM-DD 다. 연도를 말하지 않았으면 올해로 둔다. 날짜를 말하지 않았으면 빈 문자열.\n'
    '- reply 는 무엇을 하려는지 한국어 한 문장.\n'
    '- JSON 객체 하나만 출력한다. 설명·머리말·코드펜스를 붙이지 않는다.\n'
    '\n'
    '보기 — 목록에 "출결관리", "시간표관리", "수행평가" 가 있을 때\n'
    '  교사의 말: 인공지능 기초 과목 출결해야 해\n'
    '  {"screen":"출결관리","subject":"인공지능 기초","grade":"","room":"","date":"","reply":'
    '"인공지능 기초 과목의 출결을 처리합니다."}\n'
    '  교사의 말: 1학년 5반 시간표 좀 보자\n'
    '  {"screen":"시간표관리","subject":"","grade":"1","room":"5","date":"","reply":'
    '"1학년 5반 시간표를 엽니다."}'
)
SHORTLIST = 40
MIN_TAB_OVERLAP = 4      # 화면 안 탭을 고르려면 이만큼은 이어서 겹쳐야 한다
# 화면 이름을 그대로 말한 것이 언제나 가장 센 단서다. 안쪽 탭 이름은 길게 겹칠수록 세지만
# (`14 * 겹친 글자수`, 최대 180 남짓) 그래도 이름 일치를 넘지 못하게 400 으로 띄워 둔다.
# `과목별세부능력및특기사항` 은 그 자체로 화면이면서 `학기말성적조회` 안쪽 탭이기도 하다.
NAME_HIT = 400           # 화면 이름을 그대로 말했을 때
INNER_HIT = 390          # 안쪽 탭 이름을 통째로 말했을 때 — 이름 일치 바로 아래
INNER_WEIGHT = 14        # 안쪽 탭 이름이 일부만 겹칠 때, 이어서 겹친 글자 하나당
SURE_ENOUGH = 60         # 이만큼 강하게 걸렸는데 1·2등이 같으면 되묻는다
SURE_NAME = 6            # "그건 여기 없습니다" 라고 단언할 만큼 이어서 겹친 글자

# 사람들이 실제로 쓰는 말 → 화면 이름에 들어 있는 낱말
SYNONYMS = {
    '출결': ['출결'], '출석': ['출결'], '결석': ['출결'], '지각': ['출결'],
    '시간표': ['시간표'], '성적': ['성적'], '수행평가': ['수행평가'],
    '정기시험': ['정기시험'], '지필': ['정기시험'], '창체': ['창의적체험활동'],
    '생기부': ['학교생활기록부', '학생부'], '생활기록부': ['학교생활기록부', '학생부'],
    '세특': ['교과학습발달상황', '성적'], '봉사': ['봉사'], '독서': ['독서'],
    '상담': ['상담'], '전출': ['학적'], '전입': ['학적'],
}


class AssistError(RuntimeError):
    pass


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r'[\s,·/()]+', text or '') if t]


# ── 날짜 읽기 ────────────────────────────────────────────────
# "9월 11일 출결" 처럼 날짜를 말하는 일이 잦다. 화면에 일자 칸이 있으면 거기까지 맞춰 준다.
#
# 모델에게도 date 를 물어보지만 **여기서 먼저 읽는다.** 날짜는 규칙이 분명해서 정규식이 더
# 정확하고, 모델은 말하지 않은 연도를 지어내는 일이 있다. 모델 답은 여기서 못 읽었을 때만 쓴다.
RELATIVE_DAYS = {'그저께': -2, '그제': -2, '어제': -1, '작일': -1,
                 '오늘': 0, '금일': 0, '당일': 0,
                 '내일모레': 2, '모레': 2, '내일': 1, '익일': 1}
FULL_DATE = re.compile(r'(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})\s*일?')
MONTH_DAY = re.compile(r'(?<![\d학])(\d{1,2})\s*월\s*(\d{1,2})\s*일?')
SLASH_DAY = re.compile(r'(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])')
# `3일간`, `5일째`, `일자순` 같은 말에 걸리면 안 된다.
DAY_ONLY = re.compile(r'(?<!\d)(\d{1,2})\s*일(?![자정간째])')
ISO_DATE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')


def _iso(year: int, month: int, day: int) -> str:
    """달력에 있는 날이면 YYYY-MM-DD, 아니면 빈 문자열 (2월 30일 같은 것을 막는다)."""
    import datetime
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return ''


def read_date(utterance: str, today=None) -> str:
    """말 속의 날짜를 `YYYY-MM-DD` 로. 못 읽으면 빈 문자열.

    `9월 11일`, `2026-09-11`, `9/11`, `11일`, `어제` 를 읽는다. 연도를 말하지 않으면
    올해로 본다 — 교사가 말하는 날짜는 거의 언제나 이번 학기 안이다. 무엇으로 읽었는지는
    답장에 그대로 적어 사용자가 눈으로 확인할 수 있게 한다.
    """
    import datetime
    text = utterance or ''
    today = today or datetime.date.today()

    for word, shift in RELATIVE_DAYS.items():
        if word in text:
            return (today + datetime.timedelta(days=shift)).isoformat()

    match = FULL_DATE.search(text)
    if match:
        return _iso(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = MONTH_DAY.search(text)
    if match:
        return _iso(today.year, int(match.group(1)), int(match.group(2)))
    match = SLASH_DAY.search(text)
    if match:
        return _iso(today.year, int(match.group(1)), int(match.group(2)))
    match = DAY_ONLY.search(text)
    if match:
        return _iso(today.year, today.month, int(match.group(1)))
    return ''


def _valid_date(value: str) -> str:
    """모델이 준 날짜를 걸러 낸다. `YYYY-MM-DD` 이고 달력에 있는 날일 때만 받는다."""
    match = ISO_DATE.match((value or '').strip())
    if not match:
        return ''
    return _iso(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def screen_date(value: str) -> str:
    """`2026-09-11` → `2026.09.11.` — 나이스 일자 칸이 받는 꼴."""
    iso = _valid_date(value)
    return f'{iso[0:4]}.{iso[5:7]}.{iso[8:10]}.' if iso else ''


def match_by_name(utterance: str, screens: list[dict]) -> list[dict]:
    """이름·동의어·용도 설명이 겹치는 화면을 점수 순으로 돌려준다."""
    return [screen for _, screen in rank(utterance, screens)]


def rank(utterance: str, screens: list[dict]) -> list[tuple[int, dict]]:
    """점수를 붙여 돌려준다. 1·2등이 같은지 봐야 되물을지 정할 수 있다."""
    from . import neis_glossary
    words = _tokens(utterance)
    wanted: list[str] = []
    for word in words:
        for key, targets in SYNONYMS.items():
            if key in word:
                wanted.extend(targets)
    scored = []
    for screen in screens:
        name = screen['name']
        score = 0
        if name in utterance:
            score += NAME_HIT
        # 사전에 적어 둔 "교사가 실제로 쓰는 말" 은 이름 못지않게 강한 단서다.
        # 길수록 구체적이다 — `출석부` 가 `출석` 을 이겨야 출석부 출력 화면으로 간다.
        for slang in neis_glossary.words(name):
            if slang in utterance:
                score += 12 * len(slang)
        for hint in wanted:
            if hint in name:
                score += 10
        for word in words:
            if len(word) >= 2 and word in name:
                score += 3
        description = neis_glossary.describe(name)
        for word in words:
            if len(word) >= 2 and description and word in description:
                score += 1
        # 화면 안에 실제로 있는 글자. 하위 탭 이름("부서배정")처럼 메뉴에는 없는 말을
        # 받아 내려면 이게 필요하다. 다만 잡음이 섞이므로 가중치는 낮게 둔다.
        inside = neis_glossary.content_words(name)
        if inside:
            hits = sum(1 for word in words if len(word) >= 2 and any(word in v for v in inside))
            score += min(hits, 4) * 2
        # 화면 **안쪽 탭** 이름을 말하는 경우가 많다. `동아리활동 출결관리` 는 메뉴에 없고
        # `동아리활동관리` 화면 안에 있는 탭이다. 이걸 못 이으면 엉뚱한 탭의 비슷한 이름
        # (`출결관리`)으로 새어 나간다 — 2026-09-11 사용자 보고의 절반이 이것이었다.
        # 이름을 통째로 말하지는 않으므로 **이어서 겹치는 길이**로 재고, 화면 이름을 그대로
        # 말한 것(+100)과 맞먹게 준다. 겹침이 짧으면(3자 이하) 우연이므로 버린다.
        reach = inner_tab_hit(utterance, name)
        score += reach
        if score:
            scored.append((score, screen))
    scored.sort(key=lambda pair: (-pair[0], len(pair[1]['name'])))
    return scored


def inner_tab_hit(utterance: str, name: str) -> int:
    """말 속에 이 화면의 **안쪽 탭** 이름이 들어 있으면 그 무게를 돌려준다.

    `동아리활동 출결관리`, `부서배정`, `결시생 인정점` 처럼 메뉴에는 없고 화면을 열어야
    보이는 이름들이다. 괄호·띄어쓰기를 지우고 가장 길게 이어서 겹치는 만큼 점수를 준다.
    """
    from . import neis_glossary
    text = _plain(utterance)
    if not text:
        return 0
    best = 0
    for tab in neis_glossary.inner_tabs(name):
        plain = _plain(tab)
        reach = _overlap(text, plain)
        # 탭 이름의 절반도 안 겹치면 우연이다 (`관리` 두 글자로 걸리는 것을 막는다).
        if reach < MIN_TAB_OVERLAP or reach * 2 < len(plain):
            continue
        # 탭 이름을 통째로 말했으면 화면 이름을 말한 것이나 마찬가지다. 일부만 겹칠 때의
        # 눈금(`14 * 글자수`)으로 재면 `성취도-도수분포표` 를 정확히 말해도 `도수분포` 라는
        # 별칭이 붙은 다른 화면에 밀린다.
        best = max(best, INNER_HIT if reach == len(plain) else INNER_WEIGHT * reach)
    return best


def out_of_reach(utterance: str, tabs) -> dict | None:
    """말한 이름이 **이 계정에 없는 담임 역할**의 것이면 무엇인지 알려 준다.

    교과담임 계정에서 "일일출결관리" 라고 하는 일이 잦다. 그건 학급담임 화면 `출결관리`
    안쪽 탭이라 여기서는 열 수 없다. 그냥 비슷한 화면(`과목별출결관리`)으로 데려가면 왜
    다른 화면이 나왔는지 알 수 없으니, 열기 전에 한 문장으로 짚어 준다.

    화면 이름과 화면 안쪽 탭 이름을 모두 본다. 가장 길게 맞은 것을 고른다.
    돌려주는 것: {said, screen, tabs} — `screen` 은 그 이름이 든 화면, 없으면 이름 자체.
    """
    from . import neis_roles
    have = {t for t in (tabs or ())}
    text = _plain(utterance)
    if not text:
        return None

    def hit(name: str) -> int:
        plain = _plain(name)
        reach = _overlap(text, plain)
        return reach if reach >= MIN_TAB_OVERLAP and reach * 2 >= len(plain) else 0

    def worth_saying(name: str, reach: int) -> bool:
        """"이건 여기 없습니다" 라고 단언할 만큼 확실히 그 이름을 말했는가.

        "인공지능 기초 과목 출결" 에서 `과목출결` 넉 자가 겹친다고 학급담임의
        `반별과목출결현황` 을 들먹이면 안 된다. 이름을 통째로 말했거나, 여섯 자 넘게
        이어서 겹쳤을 때만 말한다.
        """
        return reach >= SURE_NAME or reach == len(_plain(name))

    best = None
    mine = 0            # 이 계정이 들어갈 수 있는 이름 중 가장 잘 맞은 정도
    for row in neis_roles.rows():
        reachable = bool(set(row['tabs']) & have)
        reach = hit(row['name'])
        if reachable:
            mine = max(mine, reach)
        elif reach and worth_saying(row['name'], reach) and (best is None or reach > best[0]):
            best = (reach, {'said': row['name'], 'screen': row['name'],
                            'tabs': tuple(row['tabs'])})
        for spot in row.get('inner') or []:
            spot_tabs = tuple(spot.get('tabs') or ())
            if not spot_tabs:
                continue
            reach = hit(spot['name'])
            if set(spot_tabs) & have:
                mine = max(mine, reach)
            elif (reach and worth_saying(spot['name'], reach)
                  and (best is None or reach > best[0])):
                best = (reach, {'said': spot['name'], 'screen': row['name'],
                                'tabs': spot_tabs})
    # 갈 수 있는 이름이 더 잘 맞으면 아무 말도 하지 않는다. "과목별출결관리" 라고 했는데
    # 학급담임의 "위탁·현장실습 과목별 출결관리" 를 들먹이면 헷갈리기만 한다.
    return best[1] if best and best[0] > mine else None


def _ask_model(utterance: str, outline: str, timeout: int = 30) -> dict | None:
    key = summarize.load_key()
    if not key:
        return None
    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': f'<화면목록>\n{outline}\n</화면목록>\n\n교사의 말: {utterance}'},
        ],
        'temperature': 0,
        'reasoning_effort': 'low',
    }
    for drop in ([], ['reasoning_effort'], ['reasoning_effort', 'temperature']):
        body = {k: v for k, v in payload.items() if k not in drop}
        request = urllib.request.Request(
            API_URL, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            content = (data['choices'][0]['message']['content'] or '').strip()
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                return None
            continue
        except Exception:
            return None
        match = re.search(r'\{.*\}', content, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except ValueError:
            return None
    return None


def choose_option(utterance: str, options: list[str]) -> str | None:
    """폴더를 눌렀더니 나온 하위 화면 중 하나를 고른다. 못 고르면 None (사용자에게 되묻는다)."""
    options = [o for o in options if o]
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    ranked = match_by_name(utterance, [{'name': o, 'tab': '', 'group': ''} for o in options])
    if ranked:
        return ranked[0]['name']
    answer = _ask_model(utterance, '\n'.join(options)) or {}
    name = (answer.get('screen') or '').strip()
    return name if name in options else None


def choose_inner_tab(utterance: str, tabs: tuple[str, ...]) -> str:
    """화면 안쪽 하위 탭 중 교사가 말한 것을 고른다.

    **말에 그 낱말이 실제로 있을 때만** 고른다. 추측해서 엉뚱한 탭을 누르면 화면이 바뀌어
    사용자가 헷갈린다. 여러 개가 걸리면 가장 긴 것 — 더 구체적인 쪽이다.

    탭 이름을 통째로 말하는 사람은 없다. `최소성취수준보장지도(추가학습)예외처리` 를
    "추가학습 예외처리" 라고 하고, `결시생 인정점 관리` 를 "결시생 인정점" 이라고 한다.
    그래서 **가장 길게 겹치는 조각**으로 고른다. 괄호·가운뎃점·띄어쓰기는 지우고 견준다.

    다만 겹치는 조각이 짧거나(3자 이하) 1·2등이 비슷하면 고르지 않는다 — 엉뚱한 탭을 눌러
    화면을 바꿔 놓는 것보다 그냥 두는 편이 낫다.
    """
    text = _plain(utterance)
    if not text:
        return ''
    scored = sorted(((_overlap(text, _plain(tab)), tab) for tab in tabs if tab),
                    key=lambda pair: -pair[0])
    if not scored or scored[0][0] < MIN_TAB_OVERLAP:
        return ''
    if len(scored) > 1 and scored[1][0] >= scored[0][0]:
        return ''                      # 비슷하게 걸린다. 고르지 않는다.
    return scored[0][1]


def _plain(value: str) -> str:
    return re.sub(r'[\s()·/,.\-]+', '', value or '')


def _overlap(text: str, name: str) -> int:
    """두 글자열이 이어서 겹치는 가장 긴 길이."""
    if not text or not name:
        return 0
    best = 0
    for start in range(len(name)):
        for end in range(len(name), start + best, -1):
            if name[start:end] in text:
                best = end - start
                break
    return best


def interpret(utterance: str, index: dict) -> dict:
    """말 한 마디를 {screen, tab, group, subject, grade, room, reply, source} 로 바꾼다.

    화면을 못 고르면 `screen` 이 None 이고 `candidates` 에 가까운 후보를 담아 돌려준다.
    """
    from . import neis_menu
    screens = neis_menu.screens(index)
    if not screens:
        raise AssistError('메뉴 목록이 비어 있습니다. NEIS 창에서 메뉴 수집을 먼저 해 주세요.')

    utterance = (utterance or '').strip()
    if not utterance:
        raise AssistError('무엇을 할지 말씀해 주세요.')
    said_date = read_date(utterance)

    def shape(picked, answer, source, ranked):
        return {'screen': picked['name'] if picked else None,
                'tab': picked['tab'] if picked else None,
                'group': picked['group'] if picked else None,
                # 색인이 알고 있는 메뉴 경로. 3단계 화면이면 두 칸짜리가 온다.
                'chain': list(picked.get('chain') or [picked['name']]) if picked else [],
                'subject': (answer.get('subject') or '').strip(),
                'grade': str(answer.get('grade') or '').strip(),
                'room': str(answer.get('room') or '').strip(),
                # 정규식으로 읽은 것이 먼저. 모델 답은 못 읽었을 때만 쓴다.
                'date': said_date or _valid_date(str(answer.get('date') or '')),
                'reply': (answer.get('reply') or '').strip()
                         or (f"{picked['name']} 화면으로 이동합니다." if picked
                             else '어떤 화면인지 찾지 못했습니다.'),
                'candidates': [s['name'] for s in ranked[:5]],
                'source': source}

    scored = rank(utterance, screens)
    ranked = [screen for _, screen in scored]

    # 같은 이름이 두 화면에 걸리는 자리가 있다. `성취도-도수분포표` 는 정기시험통계에도
    # 학기말성적통계에도 있다. 이럴 때 찍어서 열면 왜 그 화면이 나왔는지 알 수 없다 —
    # 묻고 나서 연다.
    tied = [s for score, s in scored if score == scored[0][0]] if scored else []
    if len(tied) > 1 and scored[0][0] >= SURE_ENOUGH:
        return {**shape(None, {}, 'ask', ranked),
                'reply': '어느 화면인가요? ' + ' / '.join(s['name'] for s in tied[:4]),
                'candidates': [s['name'] for s in tied[:4]]}

    # 화면 이름이나 그 화면 **안쪽 탭** 이름을 그대로 말한 경우는 모델을 부르지 않는다 —
    # 빠르고 틀릴 일이 없다.
    if ranked and (ranked[0]['name'] in utterance or inner_tab_hit(utterance, ranked[0]['name'])):
        return shape(ranked[0], {}, 'name', ranked)

    # 화면이 수백 개면 모델이 고르기 어렵다. 이름이 겹치는 것부터 추려서 보여 준다.
    shortlist = ranked[:SHORTLIST] or screens[:SHORTLIST * 2]
    answer = _ask_model(utterance, neis_menu.outline(shortlist))
    # 무엇이 결정했는지 남긴다. "AI 가 쓰이긴 하나" 를 화면에서 확인할 수 있어야 한다.
    #   model   모델이 고른 화면으로 갔다
    #   fallback 모델에 물었지만 쓸 만한 답이 없어 이름 맞춤으로 갔다
    #   offline  모델 키가 없어 물어보지도 못했다
    unavailable = not summarize.load_key()
    answer = answer or {}
    name = (answer.get('screen') or '').strip()
    picked = neis_menu.find(index, name) if name else None
    if picked:
        source = 'model'
    elif ranked:
        picked, source = ranked[0], ('offline' if unavailable else 'fallback')
    else:
        picked, source = None, ('offline' if unavailable else 'none')
    return shape(picked, answer, source, ranked)
