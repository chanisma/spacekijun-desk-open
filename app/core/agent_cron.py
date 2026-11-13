"""예약 업무 (cron) — 정한 시각에 정한 에이전트에게 정한 일을 시키고, 결과를 휴대폰으로 보낸다 (2026-11-07 요청).

  · 데스크가 켜져 있으면 돈다 — 작업 공간 창이 닫혀 있어도 된다(에이전트는 창 없이 돈다). PC 가 꺼져 있어 놓친 예약은
    켜진 뒤 **한 번만** 돌리고 «늦게 실행» 으로 알린다 (그사이 여러 번 놓쳤어도 한 번).
  · 예약마다 대상 에이전트(이름 — `claude-1` 등)를 정한다. 그 칸이 열려 있으면 그 칸의 입력칸에 넣고(대화가 이어진다),
    없거나 꺼져 있으면 같은 도구·폴더·권한 모드로 새 칸을 연다. 칸이 일하는 중·입력하던 글이 있으면 끝날 때까지 기다린다.
    선택지(권한 묻기 등)가 떠 있으면 휴대폰에 «선택이 필요합니다» 를 한 번 알리고 기다린다 — 권한 모드는 바꾸지 않는다.
  · Claude Code 만 (2026-11-07 결정) — 끝났는지·결과 글은 대화 기록(jsonl)에서 읽는다: 보낸 말 뒤의 `system/turn_duration`
    줄이 한 번의 응답이 끝났다는 표시, 결과는 마지막 도구 결과 뒤의 답 글.
  · 결과는 두 곳으로 (desktop.py 가 붙인다): 스페이스기전 알림(notification_events type 'desk_agent' — 휴대폰 푸시) 과
    휴대폰 «에이전트» 탭의 대화 묶음(서버 `desk_agent_cron_post` — 거기서 답하면 그 에이전트에게 이어서 시킨다).
  · 예약 목록은 이 PC 에만: `<자료>/agent/schedules.json`. 실행 기록: `<자료>/agent/schedule-runs.jsonl`(최근 RUN_KEEP 줄).
    결과 글에는 학생 정보가 섞일 수 있다 — 기록은 이 PC 의 사용자 폴더에만 남는다.

⚠️ 바뀔 수 있는 값 — Claude Code 대화 기록의 줄 꼴(`system`/`turn_duration`, `message.stop_reason`), 로그인 확인 명령
   (`claude auth status` 의 JSON `loggedIn`, `codex login status` 의 «Logged in»/«Not logged in»). 확인: Claude Code 2.1.319 ·
   Codex 0.167.0 (2026-11-07).
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from core import agent
from core.agent_usage import transcript_path

LIMIT = 30                 # 예약 수 상한
TITLE_LIMIT = 40
PROMPT_LIMIT = 4000
CHECK_EVERY = 20           # 예약 시각을 보는 간격 (초)
LATE_AFTER = 180           # 예약 시각에서 이만큼(초) 넘게 지나서 돌리면 «늦게 실행»
READY_WAIT = 180           # 새로 연 칸이 입력을 받을 수 있게 되기를 기다리는 시간 (초)
BUSY_WAIT = 30 * 60        # 칸이 일하는 중이면 끝나기를 기다리는 시간 (초) — 지나면 이번 실행은 실패
RUN_LIMIT = 2 * 60 * 60    # 넣은 뒤 결과를 기다리는 가장 긴 시간 (초)
DONE_QUIET = 4             # 응답이 끝났다는 줄을 본 뒤 이만큼(초) 조용하면 끝 — 이어 쓰는 글을 놓치지 않게
IDLE_QUIET = 3             # 이만큼(초) 출력이 없으면 입력을 받을 수 있다고 본다
RESULT_LIMIT = 7000        # 휴대폰 대화에 실을 결과 글 (서버 한도 8000)
SUMMARY_LIMIT = 180        # 푸시 알림에 실을 요약
RUN_KEEP = 300             # 실행 기록 줄 수
AUTH_TTL = 300             # 로그인 상태를 기억하는 시간 (초)
HEAD = '[예약 업무 «{title}»]'
TAIL = ('\n\n(이 글은 데스크의 예약 업무가 정해 둔 시각에 보낸 것입니다. 사용자가 자리에 없을 수 있어요 — 끝나면 무엇을 했는지와 '
        '결과를 마지막에 짧게 정리해 주세요. 그 정리가 사용자의 휴대폰으로 갑니다. 지우기·보내기·제출처럼 되돌리기 어려운 일은 '
        '하지 말고 확인이 필요하다고 적어 주세요.)')
DAY_NAMES = '일월화수목금토'
KINDS = ('once', 'daily', 'weekdays', 'weekly', 'interval', 'cron')


# ── cron 식 ─────────────────────────────────────────────
# 분 시 일 월 요일 — 숫자 · * · a-b · a,b · */n · a-b/n. 요일 0·7 = 일요일. 일과 요일을 둘 다 정하면 둘 중 하나만 맞아도 (표준 cron).
FIELDS = (('분', 0, 59), ('시', 0, 23), ('일', 1, 31), ('월', 1, 12), ('요일', 0, 7))


def _field(text: str, name: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in text.split(','):
        match = re.fullmatch(r'(\*|\d+(?:-\d+)?)(?:/(\d+))?', part.strip())
        if not match:
            raise ValueError(f'cron 식의 «{name}» 칸을 읽지 못했습니다: {part!r}')
        span, step = match.group(1), int(match.group(2) or 1)
        if span == '*':
            start, end = low, high
        elif '-' in span:
            start, end = (int(n) for n in span.split('-'))
        else:
            start = end = int(span)
            if match.group(2):                       # 5/15 = 5 부터 끝까지 15 칸마다
                end = high
        if step < 1 or not (low <= start <= end <= high):
            raise ValueError(f'cron 식의 «{name}» 칸은 {low}~{high} 사이여야 합니다: {part!r}')
        values.update(range(start, end + 1, step))
    return values


class Cron:
    def __init__(self, expr: str):
        parts = str(expr or '').split()
        if len(parts) != 5:
            raise ValueError('cron 식은 «분 시 일 월 요일» 다섯 칸입니다 — 예: 0 8 * * 1-5 (평일 8시)')
        self.expr = ' '.join(parts)
        sets = [_field(part, *spec) for part, spec in zip(parts, FIELDS)]
        self.minutes, self.hours, self.days, self.months, dow = sets
        self.dows = {d % 7 for d in dow}
        self.any_day, self.any_dow = parts[2] == '*', parts[4] == '*'

    def _day_ok(self, day: datetime) -> bool:
        if day.month not in self.months:
            return False
        dom, dow = day.day in self.days, (day.weekday() + 1) % 7     # 파이썬 월=0 → cron 일=0
        dow_ok = dow in self.dows
        if self.any_day and self.any_dow:
            return True
        if self.any_day:
            return dow_ok
        if self.any_dow:
            return dom
        return dom or dow_ok

    def next_after(self, moment: datetime) -> datetime | None:
        """moment 보다 뒤(분 단위)의 첫 시각. 5년 안에 없으면 None (2월 30일 같은 식)."""
        start = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        day = start.replace(hour=0, minute=0)
        hours, minutes = sorted(self.hours), sorted(self.minutes)
        for _ in range(366 * 5):
            if self._day_ok(day):
                for hour in hours:
                    for minute in minutes:
                        at = day.replace(hour=hour, minute=minute)
                        if at >= start:
                            return at
            day += timedelta(days=1)
        return None


# ── 쉬운 선택 ↔ cron ─────────────────────────────────────
def _hhmm(value) -> tuple[int, int]:
    match = re.fullmatch(r'([01]?\d|2[0-3]):([0-5]\d)', str(value or '').strip())
    if not match:
        raise ValueError('시각은 «08:30» 처럼 써 주세요.')
    return int(match.group(1)), int(match.group(2))


def clean_when(when) -> dict:
    """화면이 보낸 일정 → 고른 칸만 남긴 일정. 틀리면 ValueError (사람이 읽는 글)."""
    if not isinstance(when, dict) or when.get('kind') not in KINDS:
        raise ValueError('언제 할지 골라 주세요.')
    kind = when['kind']
    if kind == 'cron':
        return {'kind': kind, 'expr': Cron(when.get('expr')).expr}
    if kind == 'interval':
        hours = when.get('hours')
        if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 12:
            raise ValueError('«몇 시간마다» 는 1~12 시간입니다.')
        minute = when.get('minute', 0)
        if not isinstance(minute, int) or isinstance(minute, bool) or not 0 <= minute <= 59:
            raise ValueError('분은 0~59 입니다.')
        return {'kind': kind, 'hours': hours, 'minute': minute}
    hour, minute = _hhmm(when.get('time'))
    row = {'kind': kind, 'time': f'{hour:02d}:{minute:02d}'}
    if kind == 'once':
        try:
            date = datetime.strptime(str(when.get('date') or ''), '%Y-%m-%d')
        except ValueError:
            raise ValueError('날짜를 골라 주세요.') from None
        row['date'] = date.strftime('%Y-%m-%d')
    elif kind == 'weekly':
        days = when.get('days')
        if not isinstance(days, list) or not days or not all(isinstance(d, int) and 0 <= d <= 6 for d in days):
            raise ValueError('요일을 하나 이상 골라 주세요.')
        row['days'] = sorted(set(days))
    return row


def cron_of(when: dict) -> Cron | None:
    """한 번(once)이 아니면 cron 식으로."""
    kind = when['kind']
    if kind == 'once':
        return None
    if kind == 'cron':
        return Cron(when['expr'])
    if kind == 'interval':
        return Cron(f"{when['minute']} */{when['hours']} * * *")
    hour, minute = _hhmm(when['time'])
    dow = {'daily': '*', 'weekdays': '1-5', 'weekly': ','.join(str(d) for d in when.get('days', []))}[kind]
    return Cron(f'{minute} {hour} * * {dow}')


def next_due(when: dict, after: datetime) -> datetime | None:
    if when['kind'] == 'once':
        at = datetime.strptime(f"{when['date']} {when['time']}", '%Y-%m-%d %H:%M')
        return at if at > after else None
    return cron_of(when).next_after(after)


def describe(when: dict) -> str:
    kind = when['kind']
    if kind == 'once':
        return f"{when['date']} {when['time']} 한 번"
    if kind == 'daily':
        return f"매일 {when['time']}"
    if kind == 'weekdays':
        return f"평일 {when['time']}"
    if kind == 'weekly':
        return f"매주 {''.join(DAY_NAMES[d] for d in when['days'])} {when['time']}"
    if kind == 'interval':
        return f"{when['hours']}시간마다 (0시부터, {when['minute']:02d}분)"
    return f"cron {when['expr']}"


def preview(when, count: int = 3, now: datetime | None = None) -> list[str]:
    """다음 실행 시각 count 개 — 화면이 «고급» 을 고칠 때 미리 보인다."""
    when = clean_when(when)
    at, rows = now or datetime.now(), []
    for _ in range(count):
        at = next_due(when, at)
        if at is None:
            break
        rows.append(at.strftime('%Y-%m-%d %H:%M'))
    return rows


# ── 로그인 상태 ──────────────────────────────────────────
_auth_cache: dict[str, tuple[float, dict]] = {}
_auth_lock = threading.Lock()


def _auth_probe(tool: str) -> dict:
    exe = agent.find(tool)
    if not exe:
        return {'tool': tool, 'installed': False, 'logged_in': None, 'detail': ''}
    args = [exe, 'auth', 'status'] if tool == 'claude' else [exe, 'login', 'status']
    try:
        done = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=25,
                              env=agent.clean_env(), creationflags=0x08000000, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return {'tool': tool, 'installed': True, 'logged_in': None, 'detail': ''}
    text = (done.stdout or '') + '\n' + (done.stderr or '')
    if tool == 'claude':
        try:
            data = json.loads(done.stdout or '')
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get('loggedIn'), bool):
            detail = data.get('email') or data.get('authMethod') or ''
            return {'tool': tool, 'installed': True, 'logged_in': data['loggedIn'], 'detail': str(detail)}
        return {'tool': tool, 'installed': True, 'logged_in': None, 'detail': ''}      # 옛 판 — 모르면 막지 않는다
    if re.search(r'not logged in', text, re.I):
        return {'tool': tool, 'installed': True, 'logged_in': False, 'detail': ''}
    if re.search(r'logged in', text, re.I):
        found = re.search(r'logged in using (.+)', text, re.I)
        return {'tool': tool, 'installed': True, 'logged_in': True, 'detail': found.group(1).strip() if found else ''}
    return {'tool': tool, 'installed': True, 'logged_in': None, 'detail': ''}


def auth_status(tool: str, fresh: bool = False) -> dict:
    """{tool, installed, logged_in(True/False/None=모름), detail(계정)}. AUTH_TTL 동안 기억한다."""
    if tool not in agent.TOOLS:
        raise ValueError('지원하지 않는 에이전트입니다.')
    with _auth_lock:
        cached = _auth_cache.get(tool)
        if cached and not fresh and time.monotonic() - cached[0] < AUTH_TTL:
            return cached[1]
    result = _auth_probe(tool)
    with _auth_lock:
        if result['logged_in'] is not None or tool not in _auth_cache:
            _auth_cache[tool] = (time.monotonic(), result)
    return result


def forget_auth(tool: str | None = None):
    with _auth_lock:
        if tool:
            _auth_cache.pop(tool, None)
        else:
            _auth_cache.clear()


def login_command(tool: str) -> list[str]:
    exe = agent.find(tool)
    if not exe:
        raise RuntimeError(f'{agent.TOOLS[tool]["label"]} 가 이 PC 에 설치되어 있지 않습니다.')
    return [exe, 'auth', 'login', '--claudeai'] if tool == 'claude' else [exe, 'login']


# ── 대화 기록에서 결과 읽기 ──────────────────────────────
def _texts(content) -> list[str]:
    if isinstance(content, str):
        return [content]
    return [str(b.get('text') or '') for b in content if isinstance(b, dict) and b.get('type') == 'text'] \
        if isinstance(content, list) else []


def read_turn(path: Path | None, offset: int, marker: str) -> dict:
    """offset 뒤에서 marker 가 든 사람 줄을 찾고 그 뒤의 응답을 본다 →
    {seen: 보낸 말이 기록에 올랐나, done: 응답이 끝났나, stopped: 멈췄나, result: 마지막 답 글}."""
    state = {'seen': False, 'done': False, 'stopped': False, 'result': ''}
    if not path:
        return state
    try:
        with open(path, 'rb') as handle:
            handle.seek(offset)
            data = handle.read()
    except OSError:
        return state
    end = data.rfind(b'\n')
    texts: list[str] = []
    for raw in data[:end].split(b'\n') if end >= 0 else ():
        try:
            row = json.loads(raw.decode('utf-8', 'replace'))
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get('isSidechain'):
            continue
        kind, message = row.get('type'), row.get('message') if isinstance(row.get('message'), dict) else {}
        if not state['seen']:
            if kind == 'user' and any(marker in text for text in _texts(message.get('content'))):
                state['seen'] = True
            elif kind == 'attachment' and marker in json.dumps(row.get('attachment'), ensure_ascii=False):
                state['seen'] = True                                  # 일하는 중에 끼워 읽힌 말 (queued_command)
            continue
        if kind == 'assistant':
            texts.extend(t.strip() for t in _texts(message.get('content')) if t.strip())
            if message.get('stop_reason') == 'end_turn':
                state['done'] = True
        elif kind == 'user':
            content = message.get('content')
            if isinstance(content, list) and any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
                texts = []                                            # 도구를 또 썼다 — 결과는 그 뒤의 글
                state['done'] = False
            elif any(t.startswith('[Request interrupted') for t in _texts(content)):
                state['stopped'] = state['done'] = True
        elif kind == 'system' and row.get('subtype') == 'turn_duration':
            state['done'] = True
    state['result'] = '\n\n'.join(t for t in texts if t != 'No response requested.')
    return state


def summary(text: str, limit: int = SUMMARY_LIMIT) -> str:
    flat = re.sub(r'[#*`>|]+', '', re.sub(r'\s+', ' ', text or '')).strip()
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + '…'


# ── 예약 목록 ────────────────────────────────────────────
def _iso(moment: datetime | None) -> str:
    return moment.strftime('%Y-%m-%dT%H:%M:%S') if moment else ''


def _parse(value) -> datetime | None:
    try:
        return datetime.strptime(str(value), '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return None


class Store:
    def __init__(self, work_dir: Path):
        folder = Path(work_dir) / 'agent'
        self.path, self.runs_path = folder / 'schedules.json', folder / 'schedule-runs.jsonl'
        self._lock = threading.RLock()

    def load(self) -> list[dict]:
        with self._lock:
            try:
                rows = json.loads(self.path.read_text(encoding='utf-8')).get('schedules')
            except (OSError, ValueError, AttributeError):
                return []
            return [row for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str)
                    and isinstance(row.get('when'), dict)] if isinstance(rows, list) else []

    def save(self, rows: list[dict]):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'version': 1, 'schedules': rows}, ensure_ascii=False, indent=1), encoding='utf-8')
            temp.replace(self.path)

    def update(self, schedule_id: str, **changes) -> dict | None:
        with self._lock:
            rows = self.load()
            for row in rows:
                if row['id'] == schedule_id:
                    row.update(changes)
                    self.save(rows)
                    return row
            return None

    def record(self, entry: dict):
        with self._lock:
            self.runs_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                lines = self.runs_path.read_text(encoding='utf-8').splitlines()
            except OSError:
                lines = []
            lines = [line for line in lines if line.strip()][-(RUN_KEEP - 1):] + [json.dumps(entry, ensure_ascii=False)]
            self.runs_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def runs(self, schedule_id: str | None = None, limit: int = 20) -> list[dict]:
        with self._lock:
            try:
                lines = self.runs_path.read_text(encoding='utf-8').splitlines()
            except OSError:
                return []
        rows = []
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and (schedule_id is None or row.get('schedule') == schedule_id):
                rows.append(row)
                if len(rows) >= limit:
                    break
        return rows


def clean_schedule(payload: dict, target: dict) -> dict:
    """화면이 보낸 예약 → 저장할 칸. target = 데스크가 고른 칸에서 만든 {name, tool, folder, skip, title}."""
    title = str(payload.get('title') or '').strip()
    prompt = str(payload.get('prompt') or '').strip()
    if not title:
        raise ValueError('예약 이름을 써 주세요.')
    if len(title) > TITLE_LIMIT:
        raise ValueError(f'예약 이름은 {TITLE_LIMIT}자까지입니다.')
    if not prompt:
        raise ValueError('에이전트에게 시킬 일을 써 주세요.')
    if len(prompt) > PROMPT_LIMIT:
        raise ValueError(f'시킬 일은 {PROMPT_LIMIT}자까지입니다.')
    if target.get('tool') != 'claude':
        raise ValueError('예약 업무는 지금은 Claude Code 에이전트에게만 맡길 수 있습니다.')
    return {'title': title, 'prompt': prompt, 'when': clean_when(payload.get('when')), 'target': target,
            'on': payload.get('on') is not False}


# ── 돌리기 ───────────────────────────────────────────────
class Scheduler:
    """데스크가 하나 들고 있다. 붙이는 것(desktop.py):
    find(name) -> Session | None          — 그 이름의 칸 (닫혔어도)
    open(target) -> Session               — 칸이 없으면 새로 연다 (target = 저장된 대상)
    restart(session) -> Session           — 끝난 칸을 다시 켠다
    status(session) -> str                — working · idle · waiting-for-user-choice · agent-exited · ended
    deliver(schedule, session, result, run) — 알림·휴대폰으로 보낸다 (실패해도 예외를 밖으로 내지 않는다)
    note(text, data)                      — 작업 공간 창의 대화 기록에 한 줄
    """

    def __init__(self, work_dir: Path, find, open, restart, status, deliver, note=lambda text, data=None: None,
                 log=lambda *parts: None, enabled=lambda: True, clock=datetime.now):
        self.store = Store(work_dir)
        self.find, self.open, self.restart, self.status = find, open, restart, status
        self.deliver, self.note, self.log, self.enabled, self.clock = deliver, note, log, enabled, clock
        self._lock = threading.Lock()
        self._running: dict[str, dict] = {}            # 예약 id → 지금 도는 실행 (화면 표시)
        self._targets: dict[str, threading.Lock] = {}  # 대상 이름 → 한 칸에 예약 둘이 겹치지 않게
        self._stop = threading.Event()
        self._thread = None

    # 목록 ─────────────────────────────────────────────
    def list(self) -> list[dict]:
        now, rows = self.clock(), []
        for row in self.store.load():
            try:
                when = clean_when(row['when'])
                upcoming = next_due(when, max(now, _parse(row.get('cursor')) or now)) if row.get('on') else None
                text = describe(when)
            except ValueError:
                upcoming, text = None, '일정을 읽지 못했습니다'
            with self._lock:
                running = self._running.get(row['id'])
            rows.append({**row, 'describe': text, 'next': _iso(upcoming), 'running': dict(running) if running else None})
        return rows

    def add(self, cleaned: dict) -> dict:
        rows = self.store.load()
        if len(rows) >= LIMIT:
            raise ValueError(f'예약은 {LIMIT}개까지입니다. 안 쓰는 예약을 지워 주세요.')
        row = {'id': uuid.uuid4().hex[:12], **cleaned, 'created': _iso(self.clock()), 'cursor': _iso(self.clock()), 'last': None}
        self._check_due(row)
        self.store.save(rows + [row])
        return row

    def edit(self, schedule_id: str, cleaned: dict) -> dict:
        rows = self.store.load()
        row = next((r for r in rows if r['id'] == schedule_id), None)
        if row is None:
            raise ValueError('그 예약을 찾지 못했습니다.')
        changed_when, was_on = cleaned['when'] != row.get('when'), row.get('on') is True
        row.update(cleaned)
        if changed_when or (cleaned['on'] and not was_on):
            row['cursor'] = _iso(self.clock())             # 일정을 바꾸면 지난 시각은 놓친 것으로 치지 않는다
        self._check_due(row)
        self.store.save(rows)
        return row

    def _check_due(self, row: dict):
        if row.get('on') and next_due(row['when'], self.clock()) is None:
            if row['when']['kind'] == 'once':
                raise ValueError('이미 지난 시각입니다 — 앞으로의 날짜·시각을 골라 주세요.')
            raise ValueError('이 일정은 앞으로 5년 안에 돌 날이 없습니다.')

    def set_on(self, schedule_id: str, on: bool) -> dict:
        """켜기는 사람이 한 것으로 본다 — 승인 대기(pending)도 함께 걷는다."""
        changes = {'on': on}
        if on:
            changes['cursor'] = _iso(self.clock())        # 꺼 둔 동안의 시각은 놓친 것으로 치지 않는다
            changes['pending'] = False
        row = self.store.update(schedule_id, **changes)
        if row is None:
            raise ValueError('그 예약을 찾지 못했습니다.')
        if on:
            try:
                self._check_due(row)
            except ValueError:
                self.store.update(schedule_id, on=False)
                raise
        return row

    def remove(self, schedule_id: str):
        rows = self.store.load()
        left = [row for row in rows if row['id'] != schedule_id]
        if len(left) == len(rows):
            raise ValueError('그 예약을 찾지 못했습니다.')
        self.store.save(left)

    def runs(self, schedule_id=None, limit=20):
        return self.store.runs(schedule_id, limit)

    # 시계 ─────────────────────────────────────────────
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name='agent-cron', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(CHECK_EVERY):
            try:
                self.tick()
            except Exception as exc:
                self.log('예약 업무를 확인하지 못했습니다:', exc)

    def tick(self) -> list[str]:
        """한 번 본다 — 시각이 된 예약을 돌린다(스레드). 돌린 예약 id 목록 (시험용)."""
        if not self.enabled():
            return []
        now, started = self.clock(), []
        for row in self.store.load():
            if not row.get('on'):
                continue
            with self._lock:
                if row['id'] in self._running:
                    continue
            try:
                when = clean_when(row['when'])
                due = next_due(when, _parse(row.get('cursor')) or now)
            except ValueError:
                continue
            if due is None or due > now:
                continue
            late = (now - due).total_seconds() > LATE_AFTER
            changes = {'cursor': _iso(now)}                    # 그사이 여러 번 놓쳤어도 한 번만
            if when['kind'] == 'once':
                changes['on'] = False
            self.store.update(row['id'], **changes)
            self.run_now(row['id'], due=due, late=late)
            started.append(row['id'])
        return started

    def run_now(self, schedule_id: str, due: datetime | None = None, late: bool = False, manual: bool = False) -> bool:
        row = next((r for r in self.store.load() if r['id'] == schedule_id), None)
        if row is None:
            raise ValueError('그 예약을 찾지 못했습니다.')
        run = {'id': uuid.uuid4().hex[:10], 'schedule': row['id'], 'title': row['title'], 'due': _iso(due or self.clock()),
               'started': _iso(self.clock()), 'late': late, 'manual': manual, 'step': '준비 중'}
        with self._lock:
            if row['id'] in self._running:
                return False
            self._running[row['id']] = run
        threading.Thread(target=self._run, args=(row, run), name=f'agent-cron-{row["id"]}', daemon=True).start()
        return True

    def busy(self, schedule_id: str) -> bool:
        with self._lock:
            return schedule_id in self._running

    def _step(self, run: dict, text: str):
        run['step'] = text

    def _run(self, row: dict, run: dict):
        target = row['target']
        lock = self._targets.setdefault(target['name'].lower(), threading.Lock())
        try:
            try:
                with lock:
                    status, result, agent_name = self._execute(row, run)
            except Exception as exc:                           # 남은 실패 — 기록과 알림은 남긴다
                status, result, agent_name = 'error', f'예약을 돌리지 못했습니다: {exc}', target['name']
            run.update(status=status, finished=_iso(self.clock()), agent=agent_name, result=result[:RESULT_LIMIT])
            self._step(run, '결과 보내는 중')
            self.store.update(row['id'], last={'at': run['finished'], 'status': status, 'late': run['late'],
                                               'summary': summary(result, 120)})
            self.store.record({key: value for key, value in run.items() if key != 'step'})
            try:                                               # 기록·표시가 실패해도 결과는 보낸다
                self.log(f'예약 «{row["title"]}» — {status}' + (' (늦게 실행)' if run['late'] else ''))
                self.note(f'⏰ 예약 «{row["title"]}» {STATUS_TEXT.get(status, status)}', {'schedule': row['id'], 'status': status})
            except Exception:
                pass
            try:
                self.deliver(row, agent_name, result, run)
            except Exception as exc:
                self.log('예약 결과를 보내지 못했습니다:', exc)
        finally:                                               # 보낸 뒤에 «도는 중»을 걷는다 — 화면이 결과보다 먼저 끝났다고 보이지 않게
            with self._lock:
                self._running.pop(row['id'], None)

    def _execute(self, row: dict, run: dict) -> tuple[str, str, str]:
        target = row['target']
        auth = auth_status(target['tool'])
        if not auth['installed']:
            return 'error', f'{agent.TOOLS[target["tool"]]["label"]} 가 이 PC 에 설치되어 있지 않습니다.', target['name']
        if auth['logged_in'] is False:
            return 'login', (f'{agent.TOOLS[target["tool"]]["label"]} 에 로그인되어 있지 않아 예약을 돌리지 못했습니다 — '
                             '데스크의 에이전트 터미널에서 로그인해 주세요.'), target['name']
        self._step(run, '에이전트 찾는 중')
        session = self.find(target['name'])
        if session is not None and session.tool != 'claude':
            return 'error', f'{target["name"]} 는 Claude Code 에이전트가 아닙니다 — 예약의 대상을 다시 골라 주세요.', target['name']
        fresh = False
        if session is None:
            self._step(run, '새 칸 여는 중')
            session, fresh = self.open(target), True
        elif session.closed or not session.agent_running():
            self._step(run, '꺼진 칸 다시 켜는 중')
            session, fresh = self.restart(session), True
        name = session.name
        ready = self._wait_ready(session, run, fresh, row)
        if ready:
            return ready[0], ready[1], name
        marker = HEAD.format(title=row['title']) + f' #{run["id"]}'
        conversation = session.current_conversation()
        path = transcript_path(conversation)
        offset = path.stat().st_size if path and path.exists() else 0
        self._step(run, '일 넣는 중')
        session.submit(f'{marker}\n{row["prompt"]}{TAIL}')
        run['agent'] = name
        return self._wait_result(session, run, row, marker, conversation, path, offset)

    def _wait_ready(self, session, run: dict, fresh: bool, row: dict):
        """입력을 받을 수 있을 때까지 — 실패면 (status, 글), 준비되면 None."""
        started, asked = time.monotonic(), False
        while True:
            if self._stop.is_set():
                return 'error', '데스크를 끄는 중이라 멈췄습니다.'
            if session.closed:
                return 'error', '에이전트의 터미널이 끝났습니다.'
            state = self.status(session)
            waited = time.monotonic() - started
            if state == 'idle' and session.agent_running() and session.quiet_for() >= IDLE_QUIET \
                    and not session.drafting and (not fresh or waited >= 3):
                return None
            if state == 'waiting-for-user-choice' and not asked:
                asked = True
                self._step(run, '선택 기다림')
                self._ask(row, session, run, '에이전트가 선택지를 띄워 두어 예약 업무를 넣지 못하고 기다립니다')
            elif state == 'working':
                self._step(run, '하던 일이 끝나기를 기다리는 중')
            elif session.drafting:
                self._step(run, '입력하던 글이 있어 기다리는 중')
            limit = READY_WAIT if fresh and state not in ('working', 'waiting-for-user-choice') else BUSY_WAIT
            if waited > limit:
                return 'busy', f'에이전트 {session.title or session.name} 가 {int(limit // 60)}분 동안 입력을 받을 수 없어 이번 예약은 건너뛰었습니다 ({state}).'
            time.sleep(1)

    def _ask(self, row, session, run, text):
        try:
            self.deliver(row, session.name, text, {**run, 'status': 'choice'})
        except Exception as exc:
            self.log('선택이 필요하다는 알림을 보내지 못했습니다:', exc)

    def _wait_result(self, session, run, row, marker, conversation, path, offset) -> tuple[str, str, str]:
        started, done_at, asked, name = time.monotonic(), None, False, session.name
        self._step(run, '일하는 중')
        while True:
            time.sleep(1.5)
            if self._stop.is_set():
                return 'error', '데스크를 끄는 중이라 결과를 받지 못했습니다.', name
            if path is None or session.current_conversation() != conversation:
                conversation = session.current_conversation()     # 처음 메시지라 기록 파일이 이제 생겼다
                fresh = transcript_path(conversation)
                if fresh != path:
                    path, offset = fresh, 0
            turn = read_turn(path, offset, marker)
            state = self.status(session)
            if state == 'waiting-for-user-choice':
                self._step(run, '선택 기다림')
                if not asked:
                    asked = True
                    self._ask(row, session, run, '예약 업무를 하던 에이전트가 선택(허락 등)을 기다립니다 — PC 에서 골라 주세요')
            elif turn['seen']:
                self._step(run, '일하는 중')
            if turn['stopped']:
                return 'stopped', turn['result'] or '에이전트가 일을 멈췄습니다.', name
            if turn['done'] and state != 'working' and state != 'waiting-for-user-choice':
                done_at = done_at or time.monotonic()
                if time.monotonic() - done_at >= DONE_QUIET:
                    return 'done', turn['result'] or '(에이전트가 글로 된 답을 남기지 않았습니다)', name
            else:
                done_at = None
            if session.closed or not session.agent_running():
                return 'error', turn['result'] or '에이전트가 결과를 내기 전에 꺼졌습니다.', name
            if time.monotonic() - started > RUN_LIMIT:
                return 'timeout', turn['result'] or f'{RUN_LIMIT // 3600}시간 안에 끝나지 않았습니다.', name


class RelayError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class Relay:
    """에이전트가 대화로 예약을 다룬다 (2026-11-07 요청) — 데스크 중계 `/cron/*`(core/agent_bridge.py)의 뒤쪽.

    사용자가 «평일 8시마다 공문 정리해 줘» 라고 하면 에이전트가 시킬 일·일정을 정리해 여기로 보낸다.
    만들기·고치기·켜기는 **데스크 창에서 사람이 승인**한다(approve). 창이 없거나 답이 없으면 꺼진 채 «승인 대기»로 저장하고
    알린다 — 예약 탭에서 켜면 확정. 끄기·지우기·지금 한 번(승인된 것만)은 묻지 않는다. 대상은 Claude Code 칸만, 기본은 그 에이전트 자신.
    붙이는 것: target_of(name) -> 대상 dict (없거나 Claude 가 아니면 ValueError),
             approve(agent_label, proposal) -> True(승인) · False(거절) · None(창 없음·시간 지남),
             pending(agent_label, row) — 승인 대기로 저장했을 때 알림."""

    def __init__(self, scheduler: Scheduler, target_of, approve, pending=lambda agent, row: None):
        self.cron, self.target_of, self.approve, self.on_pending = scheduler, target_of, approve, pending

    @staticmethod
    def _when(data: dict) -> dict:
        if isinstance(data.get('cron'), str) and not data.get('when'):
            return clean_when({'kind': 'cron', 'expr': data['cron']})
        return clean_when(data.get('when'))

    def _row(self, schedule_id) -> dict:
        row = next((r for r in self.cron.store.load() if r['id'] == schedule_id), None)
        if row is None:
            raise RelayError(404, f'no scheduled job {schedule_id!r} — GET /cron lists them')
        return row

    def _line(self, row: dict) -> str:
        try:
            when = clean_when(row['when'])
            text, expr = describe(when), (cron_of(when).expr if cron_of(when) else 'once')
        except ValueError:
            text, expr = '?', '?'
        state = 'pending-approval' if row.get('pending') else ('on' if row.get('on') else 'off')
        listed = next((r for r in self.cron.list() if r['id'] == row['id']), {})
        last = row.get('last') or {}
        return (f"{row['id']}\t{state}\t{row['title']}\t{text} [{expr}]\t{row['target']['name']}\t"
                f"{listed.get('next') or '-'}\t{last.get('status') or '-'}\t{row.get('by') or 'user'}")

    def list_text(self) -> str:
        rows = self.cron.store.load()
        head = 'id\tstate\ttitle\twhen [cron]\tagent\tnext\tlast\tcreated_by'
        return '\n'.join([head] + [self._line(row) for row in rows]) + '\n' + (
            '' if rows else '(no scheduled jobs yet)\n')

    def show_text(self, schedule_id) -> str:
        row = self._row(schedule_id)
        return self._line(row) + '\n\nprompt:\n' + row['prompt'] + '\n'

    def runs_text(self, schedule_id=None, limit: int = 5) -> str:
        if schedule_id:
            self._row(schedule_id)
        runs = self.cron.runs(schedule_id, max(1, min(limit, 20)))
        if not runs:
            return '(no runs yet)\n'
        return '\n\n'.join(f"[{run.get('finished') or run.get('started')}] {run.get('title')} — {run.get('status')}"
                           + (' (late)' if run.get('late') else '') + '\n' + (run.get('result') or '')[:1500]
                           for run in runs) + '\n'

    def preview_text(self, data: dict) -> str:
        try:
            when = self._when(data)
        except ValueError as error:
            raise RelayError(400, str(error)) from None
        return f"{describe(when)}\nnext: {', '.join(preview(when)) or '(never)'}\n"

    def _proposal(self, me: str, cleaned: dict, old: dict | None, turn_on: bool = False) -> dict:
        return {'by': me, 'edit': bool(old), 'turn_on': turn_on, 'title': cleaned['title'], 'prompt': cleaned['prompt'],
                'describe': describe(cleaned['when']), 'next': preview(cleaned['when']),
                'target': cleaned['target'].get('title') or cleaned['target']['name'], 'skip': bool(cleaned['target'].get('skip')),
                'before': ({'title': old['title'], 'prompt': old['prompt'], 'describe': describe(clean_when(old['when']))}
                           if old else None)}

    def save(self, me: str, data: dict) -> str:
        """새 예약 · 고치기({id?, title, prompt, when | cron, agent?}). 승인되면 켜고, 아니면 승인 대기·거절."""
        if not isinstance(data, dict):
            raise RelayError(400, 'send a JSON object')
        old = self._row(data['id']) if data.get('id') else None
        name = data.get('agent') or (old['target']['name'] if old else me)
        try:
            if old and name == old['target']['name']:
                try:
                    target = self.target_of(name)
                except ValueError:                             # 그 칸이 지금 닫혀 있다 — 저장된 대상 그대로(시각이 되면 새로 연다)
                    target = old['target']
            else:
                target = self.target_of(name)
            cleaned = clean_schedule({'title': data.get('title', old['title'] if old else ''),
                                      'prompt': data.get('prompt', old['prompt'] if old else ''),
                                      'when': self._when(data) if (data.get('when') or data.get('cron')) or not old
                                      else old['when'], 'on': True}, target)
            if next_due(cleaned['when'], self.cron.clock()) is None:
                raise ValueError('that schedule never runs again (a one-time job must be in the future)')
        except ValueError as error:
            raise RelayError(400, str(error)) from None
        answer = self.approve(me, self._proposal(me, cleaned, old))
        if answer is False:
            return 'refused: the user declined this scheduled job in the Desk window. Do not retry — ask the user what to change.\n'
        approved = answer is True
        cleaned.update(on=approved, pending=not approved, by=me)
        try:
            row = self.cron.edit(old['id'], cleaned) if old else self.cron.add(cleaned)
        except ValueError as error:
            raise RelayError(400, str(error)) from None
        if not approved:
            self.on_pending(me, row)
            return (f"saved as {row['id']} but WAITING FOR APPROVAL (the Desk window is closed or the user did not answer). "
                    "It will not run until the user turns it on in the Desk agent window, right panel 예약. Tell the user.\n")
        nxt = next((r.get('next') for r in self.cron.list() if r['id'] == row['id']), '')
        return f"{'updated' if old else 'created'} {row['id']}: {describe(row['when'])} → {row['target']['name']}, next run {nxt or '-'}\n"

    def set_on(self, me: str, schedule_id: str, on: bool) -> str:
        row = self._row(schedule_id)
        if not on:
            self.cron.set_on(schedule_id, False)
            return f'turned off {schedule_id}\n'
        if row.get('on'):
            return f'{schedule_id} is already on\n'
        cleaned = {key: row[key] for key in ('title', 'prompt', 'when', 'target')}
        answer = self.approve(me, self._proposal(me, cleaned, None, turn_on=True))
        if answer is not True:
            return ('not turned on: ' + ('the user declined.' if answer is False else
                    'the Desk window is closed or the user did not answer — the user can turn it on in 예약.') + '\n')
        try:
            self.cron.set_on(schedule_id, True)
        except ValueError as error:
            raise RelayError(400, str(error)) from None
        return f'turned on {schedule_id}\n'

    def run(self, schedule_id: str) -> str:
        row = self._row(schedule_id)
        if row.get('pending'):
            raise RelayError(409, 'this job is waiting for the user\'s approval — it cannot run yet')
        if not self.cron.run_now(schedule_id, manual=True):
            return f'{schedule_id} is already running\n'
        return f'started {schedule_id} once now (the result goes to the user\'s phone; GET /cron/runs?id={schedule_id} later)\n'

    def remove(self, schedule_id: str) -> str:
        self._row(schedule_id)
        if self.cron.busy(schedule_id):
            raise RelayError(409, 'this job is running right now — try again after it finishes')
        self.cron.remove(schedule_id)
        return f'deleted {schedule_id}\n'


STATUS_TEXT = {'done': '완료', 'stopped': '멈춤', 'error': '실패', 'login': '로그인 필요', 'busy': '건너뜀',
               'timeout': '시간 초과', 'choice': '선택 필요'}
