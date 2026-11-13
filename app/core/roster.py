"""
조직도 명부 · 이름 별칭 — roster.ps1 의 Python 포팅.

**조직도 표시는 `(대화명)메모` 형식이고, 대화명이 실명이 아닐 수 있다.**
예) 황시우 선생님 → `(보건실)황시우` — 대화명은 '보건실', 실명은 메모에 있다.
"황시우에게 보내줘"를 그대로 트리에 넣으면 못 찾으므로, 명부를 떠 두고 실제 항목으로 바꾼다.

해석 순서: 별칭 → 대화명 완전일치 → 메모(실명) 완전일치 → 부분일치(유일할 때만)
부분일치가 여러 건이면 **고르지 않고 후보를 돌려준다** — 엉뚱한 사람에게 보내는 것보다 낫다.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from . import cm_win32 as cm
from . import edition

DATA_DIR = edition.DATA_DIR      # 판마다 따로 (core/edition.py)
ROSTER_PATH = os.path.join(DATA_DIR, 'roster.json')
ALIAS_PATH = os.path.join(DATA_DIR, 'aliases.json')

_ENTRY = re.compile(r'^\(([^)]*)\)(.*)$')


@dataclass
class Resolution:
    ok: bool
    text: str = ''
    why: str = ''
    candidates: tuple[str, ...] = ()


def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def sync() -> list[dict]:
    """조직도를 읽어 명부로 저장한다. 인사이동·대화명 변경 뒤에 다시 부르면 된다."""
    seen, rows = set(), []
    for it in cm.org_tree():
        m = _ENTRY.match(it['text'])
        if not m:
            continue
        if it['text'] in seen:
            continue
        seen.add(it['text'])
        rows.append({'text': it['text'],
                     'display': m.group(1).strip(),     # 대화명  '보건실'
                     'note': m.group(2).strip()})       # 메모(실명) '황시우'
    rows.sort(key=lambda r: r['text'])
    _save(ROSTER_PATH, rows)
    return rows


def roster() -> list[dict]:
    return _load(ROSTER_PATH, [])


def aliases() -> dict:
    return _load(ALIAS_PATH, {})


def set_alias(name: str, target: str):
    a = aliases()
    a[name] = target
    _save(ALIAS_PATH, a)


def remove_alias(name: str) -> bool:
    a = aliases()
    if name not in a:
        return False
    del a[name]
    _save(ALIAS_PATH, a)
    return True


def resolve(name: str) -> Resolution:
    rows = roster() or sync()
    if not rows:
        return Resolution(False, why='명부가 비어 있습니다. 조직도를 읽지 못했습니다.')

    q = name.strip()
    via = ''
    al = aliases()
    if q in al:
        via = f" (별칭 '{q}' → '{al[q]}')"
        q = al[q]

    hit = [r for r in rows if r['display'] == q]
    if len(hit) == 1:
        return Resolution(True, hit[0]['text'], '대화명 일치' + via)

    hit = [r for r in rows if r['note'] == q]
    if len(hit) == 1:
        return Resolution(True, hit[0]['text'], '메모(실명) 일치' + via)

    hit = [r for r in rows if q in r['text']]
    if len(hit) == 1:
        return Resolution(True, hit[0]['text'], '부분일치' + via)
    if len(hit) > 1:
        return Resolution(False, why=f"'{q}' 후보가 여러 명입니다. 별칭을 지정하세요.",
                          candidates=tuple(r['text'] for r in hit))
    return Resolution(False, why=f"'{q}' 를 조직도에서 찾지 못했습니다.")


def find_item(name: str):
    """해석된 이름으로 트리 항목(hItem)까지 돌려준다. 발송이 실제로 쓰는 진입점."""
    res = resolve(name)
    if not res.ok:
        detail = ('\n  후보: ' + ', '.join(res.candidates)) if res.candidates else ''
        raise cm.CmError(f"수신자 '{name}' 을 특정하지 못했습니다. {res.why}{detail}")
    tv = cm.org_tree_control()
    for it in cm.tree_items(tv['hwnd']):
        if it['text'] == res.text:
            return tv, it, res
    raise cm.CmError(f"명부에는 있으나 조직도에서 사라졌습니다: '{res.text}'. 명부를 다시 동기화하세요.")
