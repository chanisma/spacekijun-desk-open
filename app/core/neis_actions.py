"""
화면에 도착한 뒤의 마무리 — 조회를 누르고, 말한 과목·학급의 행을 골라 준다.

메뉴 진입까지만 해 주면 사용자는 결국 조건을 다시 고른다. "인공지능 기초 출결" 이라고 말했으면
과목까지 잡혀 있어야 쓸모가 있다. 다만 **저장·마감처럼 되돌리기 어려운 동작은 절대 하지 않는다**
— 조회와 선택까지만 한다.

과목별출결관리 기준 실측(2026-09-11): 조회를 누르면 왼쪽 그리드에 그날 수업이
`1학년 5(인공지능 기초)` 꼴로 뜬다. 그 행을 누르면 오른쪽에 학생 명부가 채워진다.
"""
from __future__ import annotations

import re

from . import neis_nav

# "1학년 5(인공지능 기초)" 처럼 학년·반(강의실)·과목이 한 셀에 들어 있다.
ROW_PATTERN = re.compile(r'^(\d+)학년\s*(\d+)\((.+)\)$')
SEARCH_LABELS = ('조회',)

# ── 일자 칸 ─────────────────────────────────────────────────
# 나이스 일자 칸은 `2026.09.11.(금)` 꼴로 보이는 콤보 입력이다(`role="combobox"`).
#
# 2026-09-11 실측으로 알아낸 것 — **값을 넣는 방법이 하나뿐이다.**
#   · `fill('2026.09.10.')` → DOM 값은 바뀌지만 Tab 을 누르면 원래 날짜로 되돌아간다.
#   · 점 없이 `20260910` 타이핑 → 글자는 들어가지만 조회를 누르면 되돌아간다.
#   · **점까지 한 글자씩 타이핑한 뒤 Enter** → `2026.09.10.(목)` 로 확정된다. 이것만 먹는다.
# 위젯이 자기 모델을 키 입력으로만 갱신하기 때문이다. 그래서 아래는 느리더라도 타이핑한다.
DATE_MARK = 'data-desk-date'
TYPE_DELAY_MS = 50
# 이미 날짜가 들어 있는 칸은 값 모양으로 알아본다 — `기간` 처럼 라벨이 '일자' 가 아닌 곳도 있다.
DATE_VALUE = re.compile(r'^\d{4}\.\d{2}\.\d{2}\.')


def _visible_texts(page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('div.cl-text'))
              .filter(e => e.offsetParent !== null)
              .map(e => (e.textContent || '').trim())
              .filter(Boolean)""") or []


MARK_DATES = """(mark) => {
  let found = 0, locked = 0;
  document.querySelectorAll('input').forEach(el => {
    el.removeAttribute(mark);
    if (el.offsetParent === null) return;
    const label = el.getAttribute('aria-label') || '';
    const looksLikeDate = /^\\d{4}\\.\\d{2}\\.\\d{2}\\./.test(el.value || '');
    if (!(label.indexOf('일자') >= 0 || looksLikeDate)) return;
    // 🚨 잠긴 칸은 세지 않는다. 과목별출결현황의 `기간` 처럼 학기가 통째로 박혀 있어
    //    누를 수 없는 칸이 있다. 누르러 가면 8초씩 기다리다 실패한다 (2026-09-15 실측).
    if (el.disabled || el.readOnly || el.closest('.cl-disabled')
        || getComputedStyle(el).pointerEvents === 'none') {
      locked += 1;
      return;
    }
    el.setAttribute(mark, String(found));
    found += 1;
  });
  return {found: found, locked: locked};
}"""


def date_boxes(page) -> tuple[list[dict], int]:
    """바꿀 수 있는 일자 칸들과, **잠겨 있어 건드릴 수 없는 칸의 수.**

    일자가 없는 화면이 훨씬 많고, 있어도 잠겨 있는 화면이 있다. 둘을 갈라 놓아야
    "일자 칸이 없다" 와 "이 화면은 기간이 고정이다" 를 다르게 말해 줄 수 있다.
    """
    try:
        got = page.evaluate(MARK_DATES, DATE_MARK) or {}
    except Exception:
        return [], 0
    count, locked = got.get('found', 0), got.get('locked', 0)
    out = []
    for index in range(count or 0):
        box = page.locator(f'input[{DATE_MARK}="{index}"]')
        try:
            out.append({'index': index,
                        'label': box.get_attribute('aria-label') or '일자',
                        'value': box.input_value()})
        except Exception:
            continue
    return out, locked


def set_date(page, value: str) -> dict:
    """일자 칸을 `2026.09.11.` 꼴 값으로 바꾼다.

    일자 칸이 없는 화면이면 조용히 넘어간다 — 그런 화면이 훨씬 많다. 칸이 여럿이면
    (`기간` 의 시작·종료) **모두 같은 날로** 맞춘다. "9월 11일" 은 그 하루를 뜻한다.

    넣은 뒤 값을 다시 읽어 확인한다. 위젯이 되돌려 놓는 경우가 있어서, 넣었다고 믿고
    조회하면 엉뚱한 날 자료를 보여 주게 된다.
    """
    if not value:
        return {'set': [], 'failed': [], 'boxes': 0, 'locked': 0}
    boxes, locked = date_boxes(page)
    if not boxes:
        return {'set': [], 'failed': [], 'boxes': 0, 'locked': locked}

    done, failed = [], []
    for box in boxes:
        handle = page.locator(f'input[{DATE_MARK}="{box["index"]}"]')
        try:
            handle.click(timeout=8000)
            page.keyboard.press('Control+A')
            page.keyboard.type(value, delay=TYPE_DELAY_MS)
            page.keyboard.press('Enter')
            page.wait_for_timeout(700)
            now = handle.input_value()
        except Exception as exc:
            failed.append({**box, 'why': str(exc).splitlines()[0]})
            continue
        if now.startswith(value):
            done.append({**box, 'value': now})
        else:
            failed.append({**box, 'why': f'{now!r} 로 되돌아갔습니다'})
    neis_nav.wait_loading(page)
    return {'set': done, 'failed': failed, 'boxes': len(boxes), 'locked': locked}


def search(page) -> bool:
    """조회 버튼이 있으면 누른다. 없으면 조용히 넘어간다."""
    for label in SEARCH_LABELS:
        button = (page.locator('div.cl-text:visible, button:visible')
                  .filter(has_text=re.compile('^' + label + '$')).first)
        try:
            if button.count() == 0:
                continue
            button.click(timeout=10000)
        except Exception:
            continue
        page.wait_for_timeout(1500)
        neis_nav.wait_loading(page)
        page.wait_for_timeout(1500)
        return True
    return False


def rows(page) -> list[dict]:
    """`N학년 M(과목명)` 꼴 행을 모은다."""
    out, seen = [], set()
    for text in _visible_texts(page):
        match = ROW_PATTERN.match(text)
        if not match or text in seen:
            continue
        seen.add(text)
        out.append({'text': text, 'grade': match.group(1),
                    'room': match.group(2), 'subject': match.group(3).strip()})
    return out


def pick_row(page, subject: str = '', grade: str = '', room: str = '') -> dict:
    """말한 과목·학년·반에 맞는 행을 고른다.

    후보가 여럿이면 고르지 않고 목록만 돌려준다 — 엉뚱한 반을 열어 두는 것보다 낫다.
    """
    found = rows(page)
    if not found:
        return {'picked': None, 'matches': [], 'rows': []}

    def fits(row):
        if subject and subject.replace(' ', '') not in row['subject'].replace(' ', ''):
            return False
        if grade and row['grade'] != str(grade):
            return False
        if room and row['room'] != str(room):
            return False
        return True

    matches = [row for row in found if fits(row)] if (subject or grade or room) else []
    if len(matches) != 1:
        return {'picked': None, 'matches': matches, 'rows': found}

    target = matches[0]
    cell = page.locator('div.cl-text:visible').filter(has_text=target['text']).first
    try:
        cell.click(timeout=10000)
    except Exception:
        return {'picked': None, 'matches': matches, 'rows': found}
    page.wait_for_timeout(1500)
    neis_nav.wait_loading(page)
    page.wait_for_timeout(1500)
    return {'picked': target, 'matches': matches, 'rows': found}


def click_row(page, text: str) -> dict:
    """되물은 뒤 사용자가 직접 고른 행을 누른다. 화면에 없는 행은 거절한다."""
    found = rows(page)
    target = next((row for row in found if row['text'] == text), None)
    if not target:
        raise RuntimeError(f"'{text}' 수업이 지금 화면에 없습니다. 다시 조회해 주세요.")
    page.locator('div.cl-text:visible').filter(has_text=target['text']).first.click(timeout=10000)
    page.wait_for_timeout(1500)
    neis_nav.wait_loading(page)
    page.wait_for_timeout(1500)
    return {'picked': target, 'rows': found}


def click_tab(page, label: str) -> dict:
    """화면 안쪽 하위 탭을 누른다.

    본문 맨 윗줄에 나란히 놓인 큰 단추다. `동아리활동관리` 의 부서만들기·부서배정처럼
    한 화면 안에서 일을 나눠 맡는다. 권한이 없으면 `cl-disabled` 로 회색이 되는데, 눌러도
    아무 일이 없으므로 미리 가려낸다.
    """
    neis_nav.wait_overlay_gone(page)      # 검색 패널 덮개가 남아 있으면 클릭이 막힌다
    button = (page.locator('.cl-button:visible, button:visible')
              .filter(has_text=re.compile('^' + re.escape(label) + '$')).first)
    try:
        if button.count() == 0:
            return {'clicked': False, 'why': '화면에서 찾지 못했습니다'}
        if 'cl-disabled' in (button.get_attribute('class') or ''):
            return {'clicked': False, 'why': '이 계정에서는 쓸 수 없는 탭입니다'}
        button.click(timeout=10000)
    except Exception as exc:
        return {'clicked': False, 'why': str(exc).splitlines()[0]}
    page.wait_for_timeout(1500)
    neis_nav.wait_loading(page)
    neis_nav.dismiss_dialogs(page)
    page.wait_for_timeout(1000)
    return {'clicked': True, 'why': ''}


def finish(page, subject: str = '', grade: str = '', room: str = '', date: str = '',
           progress=None) -> dict:
    """일자 맞추기 → 조회 → 행 선택까지. 되돌리기 어려운 동작은 하지 않는다."""
    def say(message):
        if progress:
            progress(message)

    neis_nav.wait_overlay_gone(page)
    # 화면에 들어가기만 해도 뜨는 알림이 있다. 안 치우면 조회 클릭이 막힌다.
    if neis_nav.dismiss_dialogs(page):
        say('알림 창을 닫았습니다')
    # 일자는 **조회보다 먼저** 맞춰야 한다. 조회를 누른 뒤 바꾸면 화면에 남은 자료는
    # 여전히 옛 날짜 것이다.
    dated = set_date(page, date)
    if dated['set']:
        say(f"일자를 {dated['set'][0]['value']} 로 맞췄습니다")
    elif dated['failed']:
        say(f"일자를 바꾸지 못했습니다 ({dated['failed'][0]['why']})")
    elif dated.get('locked'):
        say('이 화면은 기간이 고정되어 있어 일자를 바꾸지 않았습니다')
    searched = search(page)
    if searched:
        say('조회 완료')
    result = pick_row(page, subject, grade, room)
    if result['picked']:
        say(f"{result['picked']['text']} 선택")
    elif result['matches']:
        say(f"{len(result['matches'])}개가 맞아 고르지 않았습니다")
    return {'searched': searched, 'dated': dated, **result}
