"""
담임 역할별 메뉴 정본 — 학교가 내려받은 `학교업무분장 메뉴목록` 을 옮겨 둔 것.

## 왜 이게 필요한가

메뉴 지식을 나이스 화면에서 긁어 모으면 늘 반쪽이다.

  · 계정에 열려 있는 탭만 보인다
  · 폴더인지 화면인지 눌러 봐야 안다 — 못 누른 폴더는 **화면인 척** 색인에 남는다
  · 화면 안쪽 탭(`동아리활동관리` 안의 `부서배정`)은 화면을 열어야 보인다

그래서 "출결관리 해야 해" 라고 하면 폴더 이름 `출결관리` 가 진짜 화면 `과목별출결관리` 를
밀어내고, 그것도 들어갈 수 없는 부서장 탭 쪽이 뽑혔다 (2026-09-11 사용자 보고).

업무분장 메뉴목록에는 세 담임 역할이 각각 어떤 메뉴를 쓰는지, 화면 안쪽 탭까지 한 줄씩
적혀 있다. 긁지 않아도 되고, 빠진 데가 없다. 이걸 정본으로 삼는다.

## 긁는 것과 어떻게 나눠 쓰나

    긁기(`neis_menu`)  →  이 **계정에 실제로 있는 탭**이 무엇인지   (학교·발령마다 다르다)
    정본(여기)         →  그 탭 안에 **어떤 화면과 안쪽 탭**이 있는지 (역할이 같으면 같다)
    화면 수집(`neis_glossary`) → 화면 **안에 무슨 글자**가 있는지

2026-09-11 에 맞춰 봤더니 정본의 교과담임 44개·동아리담임 2개가 긁어 온 것과 정확히 같았다.

## 갱신

메뉴가 바뀌면 업무포털에서 목록을 다시 내려받아

    python scripts/build-menu-roles.py "....xlsx"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROLES_FILE = 'neis-menu-roles.json'
_cache: list[dict] | None = None


def _resource_dir() -> Path:
    bundled = getattr(sys, '_MEIPASS', None)
    if bundled:
        return Path(bundled) / 'resources'
    return Path(__file__).resolve().parents[1] / 'resources'


def rows() -> list[dict]:
    """정본 전체. 파일이 없으면 빈 목록 — 긁어 온 색인만으로 돈다."""
    global _cache
    if _cache is None:
        try:
            data = json.loads((_resource_dir() / ROLES_FILE).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = []
        _cache = [r for r in data if r.get('name') and r.get('tabs')]
    return _cache


def _chain(row: dict) -> list[str]:
    """메뉴 검색 결과와 맞출 경로 조각. 2단계 폴더 이름이 화면과 같으면 한 칸이다."""
    group, name = row.get('group') or '', row['name']
    return [group, name] if group and group != name else [name]


def screens(tabs) -> list[dict]:
    """이 계정이 들어갈 수 있는 화면 목록. `neis_menu.screens` 와 같은 모양이다.

    `tabs` 는 나이스 창에서 실제로 본 탭 이름들. 정본에는 세 역할이 다 있지만 발령받지
    않은 역할의 탭은 계정에 없다 — 있지도 않은 메뉴로 데려가면 안 된다.
    """
    allowed = {t for t in (tabs or ())}
    out = []
    for row in rows():
        for tab in row['tabs']:
            if tab not in allowed:
                continue
            out.append({'tab': tab, 'group': row.get('section') or '',
                        'name': row['name'], 'chain': _chain(row)})
    return out


def inner_tabs(name: str, tabs=None) -> tuple[str, ...]:
    """화면 안쪽 탭 이름. `tabs` 를 주면 그 역할이 쓸 수 있는 것만 돌려준다.

    안쪽 탭에도 역할이 따로 붙는다. `동아리활동관리` 한 화면 안에서 `동아리활동 출결관리`·
    `이수시간기준등록` 은 동아리담임 것이고 `부서배정` 은 학급담임 것이다.
    """
    allowed = {t for t in tabs} if tabs else None
    out: list[str] = []
    for row in rows():
        if row['name'] != name:
            continue
        for spot in row.get('inner') or []:
            if allowed is not None and not (set(spot.get('tabs') or ()) & allowed):
                continue
            if spot['name'] not in out:
                out.append(spot['name'])
    return tuple(out)


def covers(tab: str) -> bool:
    """이 탭의 화면 목록을 정본이 통째로 알고 있는가.

    알고 있으면 긁을 필요가 없다. 긁어 봐야 폴더와 화면을 구별하지 못해 `출결관리` 같은
    **폴더 이름이 화면인 척** 섞여 들어올 뿐이다.
    """
    return any(tab in row['tabs'] for row in rows())


def tabs_of(name: str) -> tuple[str, ...]:
    """이 화면이 어느 담임 탭에 있는지. 없으면 빈 값."""
    out: list[str] = []
    for row in rows():
        if row['name'] == name:
            out.extend(t for t in row['tabs'] if t not in out)
    return tuple(out)


def elsewhere(name: str, tabs) -> tuple[str, ...]:
    """이 계정에는 없지만 **다른 담임 역할에는 있는** 탭. 왜 못 가는지 설명할 때 쓴다."""
    have = {t for t in (tabs or ())}
    return tuple(t for t in tabs_of(name) if t not in have)


def find(name: str, tabs) -> dict | None:
    for item in screens(tabs):
        if item['name'] == name:
            return item
    return None
