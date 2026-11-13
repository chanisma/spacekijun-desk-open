"""
NEIS 메뉴 색인 — 로그인한 계정이 볼 수 있는 업무 화면 목록을 모아 캐시한다.

왜 필요한가
  "인공지능 기초 출결해야 해" 같은 말을 화면으로 옮기려면 **어떤 화면이 있는지** 알아야 한다.
  화면 목록은 학교·계정 권한마다 달라 코드에 적을 수 없다. 로그인한 계정에서 한 번 훑는다.

무엇을 모으나
  탭을 열면 1단계(열 제목)와 2단계 항목이 **한 번에** 보인다(`neis_nav` 주석 참고). 그래서
  탭마다 한 번만 열면 2단계까지는 공짜로 얻는다. 탭 7개에 30초 안팎.

  그런데 **교사가 실제로 쓰는 기능 이름은 3단계에 있는 경우가 많다.** 예를 들어 출결은
  2단계가 `출결관리` 라는 폴더일 뿐이고, 진짜 화면은 그 아래 `과목별출결관리` 와
  `교과시간별출석부출력` 이다. 2단계까지만 알면 모델이 고를 수 있는 이름이 두루뭉술해진다.
  그래서 담임이 쓰는 탭(`PRIORITY_TABS`)은 2단계를 하나씩 눌러 3단계까지 받아 둔다.
  나머지 탭(부서장·교육통계 등)은 2단계까지만 둔다 — 수집 시간을 그쪽에 쓸 이유가 없다.

  4단계 이하는 여기서 모으지 않는다. 그런 자리는 실제로 이동할 때 `neis_nav.goto` 가
  폴더임을 알아채고 그 자리에서 펼쳐 되묻는다.

캐시는 계정별로 `%LOCALAPPDATA%/SpacekijunDesk/neis-menu-<키>.json` 에 둔다.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from . import neis_nav, neis_roles
from . import edition

DATA_DIR = edition.DATA_DIR      # 판마다 따로 (core/edition.py)
CACHE_VERSION = 5
STALE_AFTER = 60 * 60 * 24 * 30      # 한 달

# 실제로 이동해도 되는 탭 — 일반 교사가 가진 담임 메뉴.
# 부서장 계열은 그 부서장에게만 열려 있어 여기 넣지 않는다. 지식을 쌓을 때만 참고한다.
#
# 🚨 색인에는 **이 탭들만** 담는다. 예전에는 부서장 탭도 2단계까지 담았는데, 2단계는 폴더인
#    경우가 많아 `출결관리` 같은 **폴더 이름이 화면인 척** 색인에 들어갔다. 그러면 "출결관리"
#    라고 말했을 때 진짜 화면(`과목별출결관리`)을 제치고 그 폴더가 뽑히고, 이동할 수 없는
#    탭이라 거절까지 했다 (2026-09-11 사용자 보고).
NAVIGABLE_TABS = ('교과담임', '학급담임', '동아리담임')
PRIORITY_TABS = NAVIGABLE_TABS


def cache_path(account: str) -> str:
    key = hashlib.sha256((account or 'default').encode('utf-8')).hexdigest()[:12]
    return os.path.join(DATA_DIR, f'neis-menu-{key}.json')


def load(account: str) -> dict | None:
    try:
        with open(cache_path(account), encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if data.get('version') == CACHE_VERSION else None


def save(account: str, data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = cache_path(account)
    with open(path + '.tmp', 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    os.replace(path + '.tmp', path)


def is_stale(index: dict | None) -> bool:
    return not index or (time.time() - (index.get('at') or 0)) > STALE_AFTER


def read_tab(page, tab_name: str) -> dict:
    """탭 하나를 열고 보이는 1·2단계 항목을 읽는다."""
    neis_nav.open_tab(page, tab_name)
    items = neis_nav.menu_items(page, 'mega')
    groups, current = [], None
    for item in items:
        if item['level'] == 0:
            continue
        if item['level'] == 1:
            current = {'group': item['name'], 'screens': []}
            groups.append(current)
        elif item['level'] == 2 and current is not None:
            current['screens'].append(item['name'])
    return {'groups': [g for g in groups if g['screens']]}


def deepen_tab(page, tab_name: str, entry: dict, progress=None) -> dict:
    """2단계 항목을 하나씩 눌러 3단계 이름을 받아 둔다.

    묶음(1단계)마다 탭을 한 번만 연다. 2단계를 누르면 메가메뉴는 닫히고 왼쪽 사이드바에
    그 묶음이 통째로 남으므로, 같은 묶음의 다음 항목은 사이드바에서 바로 누를 수 있다.

    하위 판정은 **누르기 전후의 차이**로 한다. 앞서 누른 형제의 하위가 아직 접히지 않고
    남아 있을 수 있어, 단순히 "지금 보이는 다음 단계"를 세면 남의 것까지 딸려 온다.
    """
    def say(message):
        if progress:
            progress(message)

    for group in entry.get('groups') or []:
        names = list(group.get('screens') or [])
        if not names:
            continue
        children: dict[str, list[str]] = {}
        opened = False
        for name in names:
            try:
                if not opened:
                    neis_nav.open_tab(page, tab_name)
                    opened = True
                before = {(i['name'], i['level']) for i in neis_nav.menu_items(page, 'any')}
                neis_nav.click_item(page, name)
                items = neis_nav.menu_items(page, 'any')
            except Exception as exc:
                say(f'{tab_name} · {name} 하위를 읽지 못했습니다: {exc}')
                opened = False           # 사이드바 상태를 믿을 수 없다. 탭부터 다시.
                continue
            me = next((i for i in items if i['name'] == name and i['folder']), None)
            if not me:
                children[name] = []      # 눌렀더니 화면이 열렸다 — 여기가 잎이다
                continue
            children[name] = [i['name'] for i in items
                              if i['level'] == me['level'] + 1
                              and (i['name'], i['level']) not in before]
        group['children'] = children
        found = sum(len(v) for v in children.values())
        say(f"{tab_name} · {group['group']}: 하위 화면 {found}개")
    return entry


def build(page, account: str, tab_names: list[str] | None = None,
          deep: tuple[str, ...] = PRIORITY_TABS, progress=None) -> dict:
    """탭들을 훑어 색인을 만들고 저장한다. `deep` 에 든 탭은 3단계까지 받는다."""
    def say(message):
        if progress:
            progress(message)

    neis_nav.close_popups(page)
    present = neis_nav.tabs(page)
    # 이동할 수 있는 탭만 담는다. 없는 탭(학급담임이 없는 계정 등)은 조용히 건너뛴다.
    names = tab_names or [t for t in present if t in NAVIGABLE_TABS]
    if not names:
        say('이동할 수 있는 담임 메뉴가 없습니다: ' + ', '.join(present))
    index = load(account) or {'version': CACHE_VERSION, 'tabs': {}}
    index['version'] = CACHE_VERSION
    index['tabs'] = dict(index.get('tabs') or {})
    for tab_name in names:
        try:
            entry = read_tab(page, tab_name)
        except Exception as exc:
            say(f'{tab_name} 메뉴 수집 실패: {exc}')
            continue
        say(f"{tab_name}: 2단계 {sum(len(g['screens']) for g in entry['groups'])}개")
        # 정본이 아는 탭은 3단계를 다시 눌러 볼 이유가 없다. 2단계를 하나씩 누르는 데
        # 탭마다 20~30초가 드는데, 얻는 것이 정본과 같다.
        if tab_name in (deep or ()) and not neis_roles.covers(tab_name):
            try:
                deepen_tab(page, tab_name, entry, progress=progress)
            except Exception as exc:
                say(f'{tab_name} 하위 수집 실패: {exc}')
        index['tabs'][tab_name] = entry
    index['present'] = present          # 이 계정 창에 실제로 있던 탭 전부
    index['at'] = int(time.time())
    save(account, index)
    return index


def account_tabs(index: dict | None) -> list[str]:
    """이 계정 나이스 창에 있는 담임 탭. 발령마다 다르므로 긁어 본 것만 믿는다."""
    index = index or {}
    seen = list(index.get('present') or index.get('tabs') or ())
    return [t for t in NAVIGABLE_TABS if t in seen]


def crawled(index: dict) -> list[dict]:
    """긁어 온 그대로. 하위가 있는 2단계는 폴더일 뿐이라 그 아래 화면 이름을 넣는다 —
    `출결관리` 가 아니라 `과목별출결관리` 로 고르게 하려는 것이다."""
    out = []
    for tab_name, entry in (index.get('tabs') or {}).items():
        for group in entry.get('groups') or []:
            children = group.get('children') or {}
            for name in group.get('screens') or []:
                kids = children.get(name) or []
                place = {'tab': tab_name, 'group': group['group']}
                if kids:
                    out.extend({**place, 'name': kid, 'chain': [name, kid]} for kid in kids)
                else:
                    out.append({**place, 'name': name, 'chain': [name]})
    return out


def screens(index: dict) -> list[dict]:
    """이 계정이 들어갈 수 있는 화면 목록 — {tab, group, name, chain}.

    **정본(`neis_roles`)이 먼저**다. 업무분장 메뉴목록에는 역할별로 어떤 화면이 있는지
    빠짐없이 적혀 있어, 긁다가 놓친 것도 폴더를 화면으로 잘못 본 것도 없다.
    긁어 온 것은 **이 계정에 어떤 탭이 있는지** 정하는 데 쓰고, 정본에 없는 화면만 보탠다
    (학교마다 더 열어 둔 메뉴가 있을 수 있다).
    """
    tabs = account_tabs(index)
    out = neis_roles.screens(tabs)
    known = {(i['tab'], i['name']) for i in out}
    for item in crawled(index):
        # 정본이 아는 탭에서 긁어 온 것은 버린다. 3단계를 못 받아 온 자리는 폴더 이름이
        # 화면인 척 남아 있어, 그걸 보태면 `출결관리` 가 `과목별출결관리` 를 밀어낸다.
        if neis_roles.covers(item['tab']):
            continue
        if (item['tab'], item['name']) not in known:
            out.append(item)
            known.add((item['tab'], item['name']))
    return out


def path_of(item: dict) -> str:
    """화면이 있는 자리 (잎 이름은 뺀다). 목록에 보여 줄 때 쓴다."""
    return ' > '.join([item['tab'], item['group']] + list(item.get('chain') or [])[:-1])


def full_path(item: dict) -> str:
    """메뉴 검색 결과와 같은 꼴의 전체 경로. 검색으로 이동할 때 이걸로 결과를 가려낸다.

        교과담임 > 학적 > 출결관리 > 과목별출결관리
    """
    return ' > '.join([item['tab'], item['group']] + list(item.get('chain') or [item['name']]))


def navigable(item: dict) -> bool:
    return item.get('tab') in NAVIGABLE_TABS


def outline(items: list[dict], limit: int = 400) -> str:
    """모델에게 보여 줄 화면 목록. 한 줄에 하나씩, 같은 줄은 한 번만.

    아는 화면에는 용도를 한 줄 붙인다 — 이름만으로는 `분할점수` 가 무엇인지 알 수 없다.
    """
    from . import neis_glossary
    lines = dict.fromkeys(f"{s['name']}   ({path_of(s)}){neis_glossary.label(s['name'])}"
                          for s in items)
    return '\n'.join(list(lines)[:limit])


def find(index: dict, name: str) -> dict | None:
    """화면 이름으로 위치를 찾는다.

    같은 화면이 교과담임과 부서장 탭 양쪽에 있는 일이 흔하다. **이동할 수 있는 탭을 먼저**
    고른다 — 부서장 메뉴는 그 부서장에게만 열려 있어 일반 교사는 들어갈 수 없다.
    """
    items = screens(index)
    ordered = [i for i in items if navigable(i)] + [i for i in items if not navigable(i)]
    for item in ordered:
        if item['name'] == name:
            return item
    for item in ordered:
        if name and name in item['name']:
            return item
    return None
