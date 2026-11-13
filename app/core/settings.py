"""
앱 설정 — 사람이 정한 값. 자동 감지가 틀릴 수 있는 것들을 여기서 못 박는다.

지금 담는 것
  coolmsg_account : 읽을 쿨메신저 계정(`.udb` 파일명). 빈 값이면 자동(최근 사용).
                    자동 감지는 "가장 최근에 쓰인 DB"인데, 한 PC 를 여러 계정이 쓰면
                    엉뚱한 계정을 고를 수 있다. 그때 사람이 직접 지정한다.
"""
from __future__ import annotations

import json
import os
from . import edition

DATA_DIR = edition.DATA_DIR      # 판마다 따로 (core/edition.py)
PATH = os.path.join(DATA_DIR, 'settings.json')

DEFAULTS = {
    'coolmsg_account': '',      # '' = 자동
}


def load() -> dict:
    values = dict(DEFAULTS)
    if os.path.exists(PATH):
        try:
            with open(PATH, encoding='utf-8') as f:
                values.update(json.load(f))
        except (OSError, ValueError):
            pass                # 손상돼도 기본값으로 계속 돈다
    return values


def save(values: dict):
    cur = load()
    cur.update(values)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(cur, f, ensure_ascii=False, indent=1)
    return cur


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def set(key: str, value):        # noqa: A001 - 설정 저장이라는 뜻이 분명하다
    return save({key: value})
