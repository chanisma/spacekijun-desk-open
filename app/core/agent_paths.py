"""에이전트 터미널의 파일·폴더 주소를 눌러 열기 (2026-11-09 요청) — «Claude Code 처럼 화면에 나온 주소를 클릭해 바로 열게».

화면(web/agent-term.js)이 줄에서 주소 같은 글(후보)을 골라 보내면, 여기서 **실제로 있는 것만** 골라 돌려준다. 있는 것만 밑줄이 생긴다.
  · 절대 경로(C:\\…, ~\\…)는 빈칸이 든 이름이 많아 줄 끝까지를 후보로 받고, 빈칸 경계에서 잘라 가며 가장 긴 «있는 경로»를 찾는다.
  · 상대 경로(app/web/x.js, 성적.xlsx)는 그 에이전트의 작업 폴더 기준.
  · 뒤에 붙은 문장 부호·«:12:3»(줄:칸)·한국어 조사(«x.xlsx를»)는 떼어 보고 맞춘다.
  · 네트워크 경로(\\\\서버\\…)는 다루지 않는다 — 없는 서버를 확인하다 화면이 몇 초씩 멈춘다.

열기: 폴더는 탐색기로, 파일은 기본 프로그램으로. **실행되는 파일(.exe·.bat·.ps1·.lnk …)은 열지 않고 탐색기에서 골라 보여 준다**
— 에이전트가 쓴 글의 링크를 누르는 것만으로 프로그램이 돌면 안 된다.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

MAX_ITEMS = 40            # 한 번에 확인하는 후보 수
MAX_LENGTH = 400          # 후보 한 개의 가장 긴 길이
RUNNABLE = {'.exe', '.com', '.bat', '.cmd', '.ps1', '.psm1', '.psd1', '.ps1xml', '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh',
            '.msi', '.msp', '.mst', '.scr', '.pif', '.lnk', '.url', '.reg', '.hta', '.cpl', '.msc', '.jar', '.py', '.pyw',
            '.appref-ms', '.application', '.gadget', '.inf', '.scf', '.settingcontent-ms', '.library-ms', '.sct', '.xll',
            '.mjs', '.cjs', '.sh'}
TRAIL = '.,;:!?)]}>\'"`」』】〉》·…'
LINE_COL = re.compile(r'(?::\d+){1,2}$|\(\d+(?:,\d+)?\)$')
HANGUL_TAIL = re.compile(r'[가-힣]{1,4}$')


def _absolute(text: str, folder: str) -> Path | None:
    text = text.strip()
    if not text or text.startswith('\\\\') or text.startswith('//'):
        return None
    if text.startswith('~'):
        text = str(Path.home()) + text[1:]
    path = Path(text)
    if not path.is_absolute():
        if not folder or not os.path.isabs(folder):
            return None
        path = Path(folder) / text
    return path


def _variants(text: str):
    """뒤에 붙은 것을 떼어 본다 — 원래 글, 문장 부호, 줄:칸, 한국어 조사 (각각의 조합)."""
    seen = set()
    queue = [text]
    while queue:
        item = queue.pop(0)
        if not item or item in seen:
            continue
        seen.add(item)
        yield item
        queue.append(item.rstrip(TRAIL))
        queue.append(LINE_COL.sub('', item))
        tail = HANGUL_TAIL.search(item)
        if tail and re.search(r'\.[A-Za-z][A-Za-z0-9]{0,7}[가-힣]{1,4}$', item):   # «x.xlsx를» — 확장자 뒤의 조사만 (폴더 이름을 깎지 않게)
            for cut in range(1, len(tail.group()) + 1):
                queue.append(item[:-cut])


def resolve(folder: str, candidate: str) -> dict | None:
    """후보 글 → {text: 글 중 경로인 부분(앞에서부터), path: 절대 경로, dir} — 없으면 None."""
    if not isinstance(candidate, str) or not candidate or len(candidate) > MAX_LENGTH:
        return None
    lead = len(candidate) - len(candidate.lstrip('@'))                  # @경로 (Claude Code 의 파일 지정)
    body = candidate[lead:]
    ends = [match.start() for match in re.finditer(r'\s', body)] + [len(body)]
    for end in sorted(set(ends), reverse=True):                          # 긴 것부터 — 빈칸이 든 이름
        piece = body[:end].rstrip()
        for text in _variants(piece):
            path = _absolute(text, folder)
            if path is None:
                continue
            try:
                if path.exists():
                    return {'text': candidate[:lead] + text, 'path': str(path.resolve()), 'dir': path.is_dir()}
            except (OSError, ValueError):
                continue
    return None


def check(folder: str, items) -> list:
    if not isinstance(items, list):
        raise ValueError('확인할 주소 목록이 올바르지 않습니다.')
    return [resolve(folder, item) for item in items[:MAX_ITEMS]]


def open_path(path: str, reveal: bool = False) -> str:
    """연다. 돌려주는 것: 'folder' · 'file' · 'revealed'(탐색기에서 골라 보임)."""
    if not isinstance(path, str) or not os.path.isabs(path) or path.startswith('\\\\'):
        raise ValueError('열 수 없는 주소입니다.')
    target = Path(path)
    if not target.exists():
        raise ValueError('파일이나 폴더가 없습니다 — 옮기거나 지웠을 수 있어요.')
    if target.is_dir() and not reveal:
        os.startfile(str(target))
        return 'folder'
    if reveal or target.suffix.lower() in RUNNABLE:
        subprocess.Popen(['explorer.exe', '/select,', os.path.normpath(str(target))])
        return 'revealed'
    os.startfile(str(target))
    return 'file'
