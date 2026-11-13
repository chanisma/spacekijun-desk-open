"""
Solar(Upstage) 요약 모듈 (표준 라이브러리만 사용).

쿨메신저 쪽지 본문이 길면 알림에 넣을 1~2줄 요약을 만든다.
실패하면 None 을 돌려주고, 호출부는 원문을 그대로 쓴다 — 요약 때문에 알림이 사라지면 안 된다.

API 키는 다음 순서로 찾는다:
  1. .secrets/upstage.key
  2. spacekijun 레포의 .env.local 의 SOLAR_API_KEY   ← 보통 이쪽
키를 복사해 두지 않고 원본 위치에서 읽는다(사본이 늘어나면 폐기가 어렵다).

spacekijun 은 `solar-proxy` 엣지 함수를 거치지만 그건 **유효한 사용자 JWT** 를 요구한다.
이 도구는 로그인 세션이 없으므로 Upstage API 를 직접 부른다. 요청 형태는 엣지 함수와 같다.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

KEY_PATH = os.path.join(os.path.expandvars('%LOCALAPPDATA%'),
                        'SpacekijunDesk', 'upstage.key')
ENV_CANDIDATES = [
    r'C:\repository\spacekijun\.env.local',
    os.path.join(os.path.expanduser('~'), 'Documents', 'GitHub', 'spacekijun', '.env.local'),
]

API_URL = 'https://api.upstage.ai/v1/chat/completions'
MODEL = 'solar-pro3'

SYSTEM_PROMPT = (
    '너는 교사가 받은 사내 쪽지를 한 줄로 요약한다.\n'
    '규칙:\n'
    '- 한국어 1~2문장, 100자 이내\n'
    '- 무엇을 · 언제까지 · 무엇을 해달라는지를 우선 남긴다\n'
    '- 날짜, 시각, 장소, 마감, 담당자 이름은 절대 지우지 않는다\n'
    '- 인사말과 상투적 표현은 버린다\n'
    '- 추측해서 덧붙이지 않는다. 원문에 없는 내용은 쓰지 않는다\n'
    '- 요약문만 출력한다. 머리말이나 따옴표를 붙이지 않는다'
)


def load_key():
    if os.path.exists(KEY_PATH):
        k = open(KEY_PATH, encoding='utf-8').read().strip()
        if k:
            return k
    for p in ENV_CANDIDATES:
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8', errors='replace'):
            m = re.match(r'\s*SOLAR_API_KEY\s*=\s*(.+)', line)
            if m:
                return m.group(1).strip().strip('"\'')
    return None


def _post(key, payload, timeout):
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def summarize(text, timeout=25):
    """실패하면 None. 호출부는 원문으로 넘어가야 한다."""
    key = load_key()
    if not key:
        return None
    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': text},
        ],
        'temperature': 0.2,
        'reasoning_effort': 'low',      # medium 은 2분을 넘긴 실측이 있다
    }
    for drop in ([], ['reasoning_effort'], ['reasoning_effort', 'temperature']):
        body = {k: v for k, v in payload.items() if k not in drop}
        try:
            data = _post(key, body, timeout)
            out = (data['choices'][0]['message']['content'] or '').strip()
            return ' '.join(out.split()) or None
        except urllib.error.HTTPError as e:
            if e.code != 400:
                return None                    # 인증·한도 등은 재시도해도 같다
            continue                           # 400 이면 선택 파라미터를 떼고 재시도
        except Exception:
            return None
    return None


if __name__ == '__main__':  # 수동 점검용
    key = load_key()
    print('키: %s' % ('찾음 (%s…)' % key[:6] if key else '없음'))
    if not key:
        sys.exit(1)
    sample = sys.argv[1] if len(sys.argv) > 1 else (
        '안녕하세요. 제8회 학교장배 학교스포츠클럽 마라톤 및 금연 캠페인 활동을 다음과 같이 '
        '실시합니다. 혹시 참여하실 분들은 오수아에게 말씀에 주세요 1. 일시 : 2026. 10. 24. '
        '토요일 (09시 30분 ~ 13시) 2. 장소 : 이동교 집합 3. 대상 : 학생 및 교직원 '
        '4. 참가자 기념티 증정 5. 간식 및 선물 제공 6. 점심식사 제공 : 선생님들')
    import time
    t0 = time.time()
    s = summarize(sample)
    print('요약(%.1f초): %s' % (time.time() - t0, s))
