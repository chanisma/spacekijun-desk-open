"""별사이 목장 (학생판, 2026-11-06) — 독 위 띠의 자리, 수업 시간 판정, 스페이스기전 다리.

세계와 세계 사이의 틈에 굴러든 아기 동물을 독 위 작은 목장에서 키운다. 화면·게임 규칙은 `web/ranch.js`,
저장·코인 교환은 스페이스기전 RPC(`ranch_*`, spacekijun 마이그레이션 `…_byeolsai_ranch.sql`).

자리 (설계 docs/plans/2026-11-06-byeolsai-ranch.md §3, 2026-11-06 참고 게임 Tiny Pasture 의 화면 방식으로 개편)
  · 띠는 독이 있는 모니터의 아래쪽을 **가로로 길게** 쓴다 — 기본은 작업 영역 전체 너비. 바닥선은 독이 아래에 가로로
    붙어 있으면 독 판 바로 위, 그 밖이면 작업 영역 맨 아래(작업 표시줄 바로 위).
  · 사용자가 «화면»에서 너비·가로 위치·높이(바닥선에서 올리기)·크기(그림 1화소 = 실제 몇 픽셀)·항상 위를 바꾼다(`view`).
    크기 기본값은 참고 게임처럼 화면 해상도로 — 세로 1200 이하 2, 1600 이하 3, 그 위 4.
  · 창은 띠 위로 패널 자리(PANEL)를 더 가진다 — 상점·도감을 열 때만 그 자리가 클릭을 받는다(창 모양).

수업 시간 (§4) — 학생판 대시보드가 받아 둔 이번 학기 시간표(`dashboard.timetable`)와 교시 시각(`PERIODS`, 50분).
  수업 중에는 보기만. 시간표를 못 받았으면 평일 1~7교시를 모두 수업으로 본다(놀게 두는 쪽으로 틀리지 않게).
  코인 교환처럼 중요한 것은 서버가 같은 시간표로 다시 확인한다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
STRIP_ART = 52        # 띠 높이 = 그림 화소 52개 (어른 32 + 여유) — ranch.js 와 같다
STRIP = 104           # 크기 2 일 때의 띠 높이 (CSS px, 시험·옛 셈)
PANEL = 300           # 띠 위 패널 자리 (CSS px)
VIEW_DEFAULT = {'width': 1.0, 'x': 0.5, 'lift': 0, 'zoom': None, 'top': False, 'outline': True}
GAP = 2               # 독 판과 띠 사이
LESSON_MINUTES = 50
PERIODS = {1: '09:00', 2: '10:00', 3: '11:00', 4: '12:50', 5: '13:50', 6: '14:50', 7: '15:50'}
REGION_RECTS = 256    # 창 모양 사각형 상한 — 배경 윤곽·동물·조각·단추 (독은 8)

# 화면이 부르는 일 → 스페이스기전 RPC(이름, 받는 인자). 이 밖은 넘기지 않는다.
BRIDGE = {
    'read': ('ranch_read', ()),
    'save': ('ranch_save', ('p_version', 'p_state')),
    'sell': ('ranch_sell_shards', ('p_times',)),
    'gifts': ('ranch_study_gifts', ()),
}
MAX_STATE = 48_000    # 저장 하나의 크기 상한 (서버와 같다)


def default_zoom(screen_height: int) -> int:
    """그림 1화소 = 실제 몇 픽셀 — 참고 게임처럼 화면 세로 해상도로 (1080p 2 · 1440p 3 · 4K 4)."""
    return 2 if screen_height <= 1200 else 3 if screen_height <= 1600 else 4


def clean_view(value) -> dict:
    """«화면» 설정 — 틀린 칸은 기본값으로."""
    view = dict(VIEW_DEFAULT)
    if not isinstance(value, dict):
        return view
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if num(value.get('width')) and 0.2 <= value['width'] <= 1:
        view['width'] = float(value['width'])
    if num(value.get('x')) and 0 <= value['x'] <= 1:
        view['x'] = float(value['x'])
    if num(value.get('lift')) and 0 <= value['lift'] <= 600:
        view['lift'] = int(value['lift'])
    if isinstance(value.get('zoom'), int) and not isinstance(value.get('zoom'), bool) and 1 <= value['zoom'] <= 6:
        view['zoom'] = value['zoom']
    view['top'] = value.get('top') is True
    view['outline'] = value.get('outline') is not False         # 품질 색 테두리 (참고 게임의 show_animal_outline)
    return view


def place(anchor: str | None, shelf: tuple[int, int, int, int] | None, work: tuple[int, int, int, int],
          view: dict, scale: float, monitor_height: int | None = None) -> dict:
    """띠 창의 화면 자리 (실제 픽셀). shelf = 독 판의 화면 사각형 (왼, 위, 오른, 아래), work = 그 모니터의 작업 영역,
    view = «화면» 설정(clean_view), scale = CSS 1px 의 실제 픽셀. 돌려주는 것 {x, y, width, height, mode, zoom}
    — mode 'dock'(독 위) · 'desk'(작업 표시줄 위), zoom = 그림 1화소의 실제 픽셀."""
    view = clean_view(view)
    wl, wt, wr, wb = work
    zoom = view['zoom'] or default_zoom(monitor_height or (wb - wt))
    strip, panel = STRIP_ART * zoom, round(PANEL * scale)
    height = strip + panel
    width = max(200, round((wr - wl) * view['width']))
    x = round(wl + (wr - wl) * view['x'] - width / 2)
    x = max(wl, min(x, wr - width))
    docked = anchor == 'bottom' and shelf
    floor = (shelf[1] - round(GAP * scale)) if docked else wb
    y = max(wt, floor - round(view['lift'] * scale) - height)
    return {'x': x, 'y': y, 'width': width, 'height': height, 'mode': 'dock' if docked else 'desk', 'zoom': zoom}


def _minutes(text: str) -> int:
    hour, minute = text.split(':')
    return int(hour) * 60 + int(minute)


def lesson_now(cells: list | None, now: datetime | None = None) -> dict:
    """지금 수업 중인가 — {in_class, period, until(HH:MM), known}. cells = dashboard.timetable 의 칸들(없으면 None)."""
    now = (now or datetime.now(KST)).astimezone(KST)
    day, minute = now.isoweekday(), now.hour * 60 + now.minute
    known = isinstance(cells, list) and bool(cells)
    if known:
        periods = {c.get('period') for c in cells if isinstance(c, dict) and c.get('day') == day}
    else:
        periods = set(PERIODS) if day <= 5 else set()
    for period in sorted(p for p in periods if p in PERIODS):
        start = _minutes(PERIODS[period])
        if start <= minute < start + LESSON_MINUTES:
            end = start + LESSON_MINUTES
            return {'in_class': True, 'period': period, 'until': f'{end // 60:02d}:{end % 60:02d}', 'known': known}
    return {'in_class': False, 'period': None, 'until': None, 'known': known}


def clean_rects(rects, limit: int = REGION_RECTS) -> list[tuple[int, int, int, int]]:
    """화면이 알려 준 누를 자리(창 안 CSS px 사각형) — 형식이 틀리면 ValueError."""
    if not isinstance(rects, list) or len(rects) > limit:
        raise ValueError('목장 영역 형식이 올바르지 않습니다.')
    out = []
    for rect in rects:
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            raise ValueError('목장 영역 형식이 올바르지 않습니다.')
        try:
            x, y, w, h = (int(v) for v in rect)
        except (TypeError, ValueError):
            raise ValueError('목장 영역 형식이 올바르지 않습니다.') from None
        if w <= 0 or h <= 0 or not all(-100 <= v <= 9000 for v in (x, y, w, h)):
            raise ValueError('목장 영역 형식이 올바르지 않습니다.')
        out.append((x, y, w, h))
    return out


def _send(request: urllib.request.Request, timeout: float):
    """스페이스기전으로 보내기 (시험에서 갈아 끼운다)."""
    return urllib.request.urlopen(request, timeout=timeout)


def bridge(work: str, body: dict) -> object:
    """학생 세션으로 스페이스기전 RPC 를 부른다. 실패하면 RuntimeError(학생에게 보일 말)."""
    if work not in BRIDGE:
        raise ValueError('지원하지 않는 목장 요청입니다.')
    from core import notify, supa_auth
    name, params = BRIDGE[work]
    data = {p: body.get(p) for p in params}
    if work == 'save' and len(json.dumps(data.get('p_state'), ensure_ascii=False)) > MAX_STATE:
        raise ValueError('목장 저장이 너무 큽니다.')
    try:
        headers = {**supa_auth.auth_headers(), 'Content-Type': 'application/json'}
    except Exception:
        raise RuntimeError('스페이스기전 로그인이 필요해요.') from None
    url = notify.config()['url'].rstrip('/') + f'/rest/v1/rpc/{name}'
    request = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers, method='POST')
    try:
        with _send(request, 15) as response:
            return json.loads(response.read() or b'null')
    except urllib.error.HTTPError as exc:
        try:
            answer = json.loads(exc.read() or b'{}')
        except ValueError:
            answer = {}
        raise RuntimeError(answer.get('message') or answer.get('error') or '스페이스기전이 거절했어요.') from None
    except OSError:
        raise RuntimeError('스페이스기전에 닿지 못했어요.') from None
