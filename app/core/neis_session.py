"""
NEIS 대화형 이동의 알맹이 — 열려 있는 나이스 창 하나를 붙잡고 요청을 처리한다.

## 왜 별도 모듈인가

화면 조작은 **Playwright 를 만든 스레드에서만** 할 수 있다. 그래서 요청을 넣는 곳(데스크
화면, 나이스에 심은 패널)과 실제로 누르는 곳(로그인 워커 스레드)이 갈린다. 그 사이를 잇는
큐와 일감 처리를 여기 모아 둔다.

데스크의 `desktop.py` 는 이것을 감싸기만 하고, 점검 스크립트는 같은 것을 그대로 쓴다.
UI 다리에 업무 로직이 섞이면 브라우저 없이는 아무것도 확인할 수 없게 된다.

## 쓰는 법

    session = Session(account='teacher')
    session.pump(page, progress, should_stop)      # 로그인 워커 스레드에서 (창이 닫힐 때까지)

    ticket = session.enqueue('assist', {'text': '인공지능 기초 출결'})   # 다른 스레드/페이지에서
    session.result(ticket)                                              # 될 때까지 물어본다
    session.submit('assist', {'text': '...'})                           # 기다려서 한 번에

`enqueue`/`result` 는 큐와 사전만 만진다. 나이스 페이지가 부르는 함수도 이 둘이라,
화면 조작 스레드가 자기 자신을 기다리는 일이 없다.
"""
from __future__ import annotations

import queue
import re
import threading

from . import neis_actions, neis_assist, neis_menu, neis_nav

# 여기까지는 하지 않는다고 말해야 하는 말들. 학생 한 명의 출결을 찍어 저장하는 일은
# 되돌리기 어렵고 생활기록부에 남는다. 화면과 조건만 맞춰 주고 손은 사람이 댄다.
HANDS_OFF = re.compile(r'결석|지각|조퇴|결과|출석\s*처리|무단|입력해|처리해|저장|마감')

MAX_DEPTH = 4                 # 폴더를 따라 내려가는 최대 단계
TICKET_LIMIT = 40             # 창을 오래 켜 두면 표가 쌓인다
IDLE_POLL_MS = 200


class Session:
    def __init__(self, account: str = 'default'):
        self.account = account or 'default'
        self.open = threading.Event()
        self._jobs: queue.Queue = queue.Queue()
        self._tickets: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._seq = 0

    # ── 요청 넣기 ────────────────────────────────────────────
    def enqueue(self, kind: str, payload: dict) -> str:
        """일감을 넣고 표만 돌려준다. 기다리지 않는다."""
        if not self.open.is_set():
            raise ValueError('NEIS 자동 로그인 창을 먼저 열어 주세요.')
        job = {'kind': kind, 'payload': payload or {}, 'done': threading.Event(),
               'result': None, 'error': None, 'progress': []}
        with self._lock:
            self._seq += 1
            ticket = f'job-{self._seq}'
            self._tickets[ticket] = job
            if len(self._tickets) > TICKET_LIMIT:
                for old, entry in list(self._tickets.items())[:TICKET_LIMIT // 2]:
                    if entry['done'].is_set():
                        self._tickets.pop(old, None)
        self._jobs.put(job)
        return ticket

    def result(self, ticket: str) -> dict:
        job = self._tickets.get(str(ticket))
        if not job:
            return {'state': 'unknown'}
        progress = list(job['progress'])
        if not job['done'].is_set():
            return {'state': 'pending', 'progress': progress}
        if job['error']:
            return {'state': 'error', 'error': job['error'], 'progress': progress}
        return {'state': 'done', 'data': job['result'], 'progress': progress}

    def submit(self, kind: str, payload: dict, timeout: float = 240):
        """넣고 끝날 때까지 기다린다. **화면 조작 스레드에서 부르면 안 된다.**"""
        ticket = self.enqueue(kind, payload)
        job = self._tickets[ticket]
        if not job['done'].wait(timeout):
            raise RuntimeError('NEIS 화면이 제때 응답하지 않았습니다. 창 상태를 확인해 주세요.')
        if job['error']:
            raise RuntimeError(job['error'])
        return job['result']

    # ── 처리 ────────────────────────────────────────────────
    def pump_once(self, page, progress=None, wait: float = 0.2) -> bool:
        """일감이 있으면 **하나만** 처리하고 돌아온다. 일감을 처리했으면 True.

        `pump` 은 창이 닫힐 때까지 붙잡고 있어서, 한 창에 여러 업무시스템을 탭으로 여는
        구조에서는 쓸 수 없다. 창을 지키는 쪽이 이것을 돌아가며 불러야 다른 탭도 연다.
        """
        self.open.set()
        # 일감이 없을 때는 **브라우저에 아무것도 묻지 않는다.** 여기가 창 지키기의 쉬는
        # 자리라 0.2초마다 도는데, 그때마다 `page.is_closed()` 를 부르면 화면이 바쁠 때
        # 드라이버를 붙잡아 프로그램이 멈춘 것처럼 보인다 (2026-09-15 사용자 보고).
        try:
            job = self._jobs.get(timeout=wait)
        except queue.Empty:
            return False
        if page.is_closed():
            job['error'] = 'NEIS 창이 닫혔습니다.'
            job['done'].set()
            return False

        def say(message, _job=job):
            _job['progress'].append(message)
            if progress:
                progress(message)

        try:
            job['result'] = self.run_job(page, job, say)
        except Exception as exc:
            job['error'] = str(exc) or '요청을 처리하지 못했습니다.'
        finally:
            job['done'].set()
        return True

    def close(self) -> None:
        """더 받지 않고, 기다리던 일감에는 창이 닫혔다고 알린다."""
        self.open.clear()
        while True:
            try:
                pending = self._jobs.get_nowait()
            except queue.Empty:
                return
            pending['error'] = 'NEIS 창이 닫혔습니다.'
            pending['done'].set()

    def pump(self, page, progress=None, should_stop=None) -> None:
        """창이 닫힐 때까지 일감을 처리한다. 로그인 워커 스레드에서 부른다."""
        stop = should_stop or (lambda: False)
        self.open.set()
        try:
            while not stop() and not page.is_closed():
                try:
                    job = self._jobs.get(timeout=0.3)
                except queue.Empty:
                    page.wait_for_timeout(IDLE_POLL_MS)
                    continue

                def say(message, _job=job):
                    """진행 상황은 이 일감과 활동 기록 양쪽에 남긴다 — 패널이 읽어 간다."""
                    _job['progress'].append(message)
                    if progress:
                        progress(message)

                try:
                    job['result'] = self.run_job(page, job, say)
                except Exception as exc:
                    job['error'] = str(exc) or '요청을 처리하지 못했습니다.'
                finally:
                    job['done'].set()
        finally:
            self.open.clear()
            while True:
                try:
                    pending = self._jobs.get_nowait()
                except queue.Empty:
                    break
                pending['error'] = 'NEIS 창이 닫혔습니다.'
                pending['done'].set()

    def run_job(self, page, job: dict, say) -> dict:
        kind, payload = job['kind'], job['payload']
        if kind == 'menu':
            index = neis_menu.build(page, self.account, progress=say)
            return {'screens': len(neis_menu.screens(index))}
        if kind == 'pick':
            done = neis_actions.click_row(page, str(payload.get('row', '')))
            return {'ok': True, 'reply': f"{done['picked']['text']} 을 선택했습니다.",
                    'options': [], 'option_kind': 'screen'}
        if kind == 'assist':
            return self._assist(page, str(payload.get('text', '')).strip(), say)
        raise ValueError('지원하지 않는 NEIS 요청입니다.')

    def _assist(self, page, text: str, say) -> dict:
        if not text:
            raise ValueError('무엇을 할지 말씀해 주세요.')

        index = neis_menu.load(self.account)
        if neis_menu.is_stale(index):
            say('메뉴 목록을 수집하는 중')
            index = neis_menu.build(page, self.account, progress=say)

        plan = neis_assist.interpret(text, index)
        # 말한 이름이 **다른 담임 역할**의 메뉴일 수 있다. 업무분장 메뉴목록을 보면 `출결관리`
        # 는 학급담임 것이고 `부서배정` 도 그렇다. 그냥 비슷한 화면으로 데려가면 왜 다른
        # 화면이 열렸는지 알 수 없으니 먼저 알려 준다.
        note = self._missing_role_note(text, index)
        if not plan['screen']:
            return {'ok': False, 'source': plan['source'],
                    'reply': (note + ' ' + plan['reply']).strip(),
                    'options': plan['candidates'], 'option_kind': 'screen'}

        # 이동은 **메뉴 검색**으로 한다. 메가메뉴를 단계별로 누르는 것보다 튼튼하고,
        # 계정마다 다른 메뉴 구성에도 그대로 통한다.
        place = {'tab': plan['tab'], 'group': plan['group'],
                 'chain': plan.get('chain') or [plan['screen']], 'name': plan['screen']}
        if plan['tab'] not in neis_menu.account_tabs(index):
            return {'ok': False, 'options': [], 'option_kind': 'screen',
                    'reply': f"{plan['screen']} 은(는) {plan['tab']} 메뉴에 있는데 이 계정에는 "
                             f"그 탭이 없습니다. 있는 탭: "
                             f"{', '.join(neis_menu.account_tabs(index)) or '없음'}."}
        # 앞서 연 화면이 2차 인증 창을 띄워 둔 채라면 뒤의 모든 클릭이 막힌다. 이제
        # 다른 화면으로 떠나는 참이니 그 창은 닫아도 된다.
        left_auth = neis_nav.auth_required(page) and neis_nav.close_auth_dialog(page)
        if left_auth:
            note = (note + ' 앞서 열어 둔 2차 인증 창은 닫았습니다.').strip()
        say(f"{plan['screen']} 찾는 중")
        opened = neis_nav.open_by_search(page, plan['screen'], neis_menu.full_path(place))
        if opened != plan['screen']:
            return {'ok': False, 'options': [], 'option_kind': 'screen',
                    'reply': f"{plan['screen']} 화면이 열리지 않았습니다. "
                             f"{('지금 열린 화면: ' + opened) if opened else ''}".strip()}
        chain = list(place['chain'])
        if neis_nav.auth_required(page):
            return {'ok': True, 'chain': chain, 'tab': plan['tab'], 'source': plan['source'],
                    'options': [], 'option_kind': 'screen', 'subject': plan['subject'],
                    'reply': f"{plan['screen']} 화면을 열었습니다. **2차 인증**을 요구하는 "
                             f"화면이라 인증을 마쳐야 내용이 보입니다."}

        # 화면 안쪽 하위 탭까지 말했으면 거기까지 눌러 준다 (예: 동아리활동관리 안의 부서배정).
        from . import neis_glossary
        inner = neis_assist.choose_inner_tab(text, neis_glossary.inner_tabs(plan['screen']))
        moved = neis_actions.click_tab(page, inner) if inner else {'clicked': False, 'why': ''}
        if inner and moved['clicked']:
            say(f'{inner} 탭으로')

        done = neis_actions.finish(page, plan['subject'], plan['grade'], plan['room'],
                                   neis_assist.screen_date(plan['date']), progress=say)
        reply = f"{note} {plan['tab']} · {' > '.join(chain)} 화면을 열었습니다.".strip()
        if inner:
            reply += (f" {inner} 탭을 열었습니다." if moved['clicked']
                      else f" {inner} 탭은 열지 못했습니다 ({moved['why']}).")
        # 날짜는 **무엇으로 알아들었는지 반드시 말한다.** "9월 11일" 이 몇 년도인지는 추측이라
        # 사용자가 눈으로 확인할 수 있어야 한다.
        dated = done['dated']
        if dated['set']:
            reply += f" 일자는 {dated['set'][0]['value']} 로 맞췄습니다."
        elif dated['failed']:
            reply += f" 일자는 바꾸지 못했습니다 ({dated['failed'][0]['why']})."
        elif dated.get('locked') and plan['date']:
            # 과목별출결현황처럼 학기가 통째로 박혀 있는 화면이 있다. 못 바꾼 것이 아니라
            # 바꿀 수 없는 화면이라는 것을 알려 준다.
            reply += (f" 이 화면은 기간이 고정되어 있어 {plan['date']} 로 좁히지 못했습니다."
                      ' 날짜별로 보려면 출결 입력 화면을 열어 주세요.')
        elif plan['date']:
            reply += f" 이 화면에는 일자 칸이 없어 {plan['date']} 는 반영하지 못했습니다."
        if done['picked']:
            reply += f" {done['picked']['text']} 을 선택했습니다."
        elif done['matches']:
            reply += f" 맞는 수업이 {len(done['matches'])}개라 선택하지 않았습니다."
        elif done['rows'] and (plan['subject'] or plan['grade'] or plan['room']):
            # 말한 조건을 그대로 되읽어 준다. 과목은 있는데 반이 없을 때 "과목이 없습니다"
            # 라고 하면 그날 수업이 아예 없는 줄 안다 (2026-09-11 실측).
            asked = ' '.join(part for part in (
                f"{plan['grade']}학년" if plan['grade'] else '',
                f"{plan['room']}반" if plan['room'] else '',
                plan['subject']) if part)
            reply += f" {asked} 수업은 그날 목록에 없습니다."
        # 설명서의 선행처리 — 화면이 비어 보이는 가장 흔한 이유라 한 문장만 덧붙인다
        before = neis_glossary.briefing(plan['screen'])
        if before:
            reply += f' ({before})'
        # 학생 이름과 출결 상태까지 말했는데 답장이 조용하면, 결석 처리까지 된 줄 안다.
        # 여기는 **일자와 수업 선택까지**가 끝이다. 그 선을 말로 분명히 긋는다.
        if HANDS_OFF.search(text):
            reply += ' 학생별 출결 입력과 저장은 하지 않습니다. 화면에서 직접 처리해 주세요.'
        # 고르지 못했으면 후보를 그대로 돌려준다 — 화면에서 눌러 고르게 하려는 것이다.
        waiting = [] if done['picked'] else [r['text'] for r in (done['matches'] or done['rows'])]
        return {'ok': True, 'reply': reply, 'chain': chain, 'tab': plan['tab'],
                'source': plan['source'], 'grade': plan['grade'], 'room': plan['room'],
                'subject': plan['subject'], 'date': plan['date'],
                'dated': dated['set'][0]['value'] if dated['set'] else '',
                'searched': done['searched'],
                'picked': done['picked'], 'rows': [r['text'] for r in done['rows']],
                'inner_tab': inner if inner and moved['clicked'] else '',
                'options': waiting, 'option_kind': 'row'}

    def _missing_role_note(self, text: str, index: dict | None) -> str:
        """말한 이름이 이 계정에 없는 담임 역할의 것이면 한 문장으로 알려 준다.

        화면 이름만이 아니라 **화면 안쪽 탭** 이름도 본다. 교과담임 계정에서 "일일출결관리"
        라고 하는 일이 잦은데, 그건 학급담임 화면 `출결관리` 안에 있다.
        """
        spot = neis_assist.out_of_reach(text, neis_menu.account_tabs(index))
        if not spot:
            return ''
        where = ('' if spot['screen'] == spot['said']
                 else f" {spot['screen']} 화면 안에 있는 탭이고,")
        return (f"{spot['said']} 은(는){where} {' · '.join(spot['tabs'])} 메뉴라 "
                f"이 계정에는 없습니다.")

    def state(self) -> dict:
        from . import summarize
        index = neis_menu.load(self.account)
        return {'open': self.open.is_set(),
                'screens': len(neis_menu.screens(index)) if index else 0,
                'stale': neis_menu.is_stale(index),
                # 모델을 쓸 수 있는 PC 인지. 키가 없으면 이름 맞춤만으로 돈다.
                'ai': bool(summarize.load_key())}
