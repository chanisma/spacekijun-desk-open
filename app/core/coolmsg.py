"""
쿨메신저 쪽지 발송 — send-message.ps1 의 Python 포팅.

    from core import coolmsg
    coolmsg.send(['황시우'], '제목', '본문')

지금까지 실측으로 알아낸 것이 전부 들어 있다. 요약하면:
  · 모달을 여는 버튼은 **Post** 로 눌러야 한다 (Send 는 대화상자가 닫힐 때까지 블록)
  · 예약전송·나에게보내기는 **오너드로우** 라 BM_GETCHECK 이 무의미하다 → 캡션으로 읽는다
  · 발송 성공 판정은 **tbl_send** 로 한다 (스크립트 출력은 믿을 수 없다)
  · 메인 창이 숨김·최소화면 조직도 클릭이 조용히 먹힌다 → 먼저 되살린다
"""
from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import tempfile
import time

from . import cdp
from . import cm_win32 as cm
from . import roster as R

UDB_GLOB = os.path.expandvars(r'%LOCALAPPDATA%\CoolMessenger\Memo\*.udb')

# 작성창 컨트롤 (실측)
ID_TITLE, ID_PICK, ID_CC = 4362, 1656, 1657
ID_SCHED, ID_SELF, ID_ATTACH, ID_SEND = 1660, 1661, 1449, 3249
# '사용자 선택' 대화상자
ID_SRC_TREE, ID_SEL_TREE, ID_ADD, ID_OK = 1400, 1401, 1636, 3007
# '열기'(파일) 대화상자
ID_FILE_NAME, ID_FILE_OPEN = 1148, 1


class SendError(RuntimeError):
    pass


def _wait_window(title_part: str, timeout=20, exclude=()) -> dict | None:
    end = time.time() + timeout
    while time.time() < end:
        for w in cm.windows():
            if title_part in w['title'] and w['hwnd'] not in exclude:
                return w
        time.sleep(0.5)
    return None


def last_sent() -> dict | None:
    """보낸함의 마지막 행. **발송 여부 판정의 유일한 근거**다."""
    files = glob.glob(UDB_GLOB)
    if not files:
        return None
    src = max(files, key=os.path.getsize)
    tmp = tempfile.mkdtemp(prefix='cmsend_')
    try:
        dst = os.path.join(tmp, 'm.udb')
        shutil.copy(src, dst)
        for ext in ('-wal', '-shm'):
            if os.path.exists(src + ext):
                shutil.copy(src + ext, dst + ext)
        con = sqlite3.connect(f'file:{dst}?mode=ro', uri=True)
        try:
            row = con.execute('SELECT MessageKey, SendDate, Receiver, Title, ScheduledDate '
                              'FROM tbl_send ORDER BY MessageKey DESC LIMIT 1').fetchone()
            return dict(zip(('key', 'sent', 'to', 'title', 'scheduled'), row)) if row else None
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def toggle_state(compose_hwnd, ctrl_id) -> str:
    """
    오너드로우 버튼(예약전송·나에게보내기)의 상태.
    ⚠️ BM_GETCHECK 은 항상 0 이라 쓸 수 없다. 캡션 접두어가 상태다.
       '선택 예약전송' = 켜짐 / '해제 예약전송' = 꺼짐
    """
    for c in cm.children(compose_hwnd):
        if c['id'] == ctrl_id:
            t = c['text']
            return 'ON' if t.startswith('선택') else 'OFF' if t.startswith('해제') else f'?({t})'
    return '?(없음)'


def _set_body(html: str):
    """본문은 CEF 편집기다. iframe(#editFrame) 안에 직접 넣고 결과를 되읽어 확인한다."""
    with cdp.connect('richtext') as c:
        js = ("(()=>{const f=document.getElementById('editFrame');"
              "if(!f||!f.contentDocument)return '(iframe 없음)';"
              "f.contentDocument.body.innerHTML=%s;"
              "return f.contentDocument.body.innerText.replace(/\\s+/g,' ').slice(0,80);})()"
              % _js_string(html))
        return c.evaluate(js)


def _js_string(s: str) -> str:
    import json as _j
    return _j.dumps(s, ensure_ascii=False)


def send(to: list[str], title: str, body: str = '', body_html: str = '',
         attachments: list[str] | None = None, dry_run: bool = False,
         log=print) -> dict:
    """
    쪽지를 보낸다. 성공하면 tbl_send 행을 돌려준다.
    dry_run 이면 작성만 하고 창을 남긴다(사람이 확인 후 보내도록).
    """
    attachments = attachments or []
    if not to:
        raise SendError('수신자가 없습니다.')
    for f in attachments:
        if not os.path.exists(f):
            raise SendError(f'첨부 파일 없음: {f}')
    cdp.targets()                       # CDP 가 죽어 있으면 여기서 명확히 실패한다

    # 0) 광고 팝업 정리 + 메인 창 되살리기
    cm.close_ad_popups()
    if cm.restore_main():
        log('메인 창이 숨김/최소화 상태라 되살렸습니다')
    if not cm.main_window():
        raise SendError('쿨메신저 메인 창을 찾지 못했습니다. 실행·로그인 상태를 확인하세요.')
    time.sleep(0.8)

    # 1) 수신자 이름 해석 (대화명이 실명이 아닐 수 있다)
    resolved = []
    for n in to:
        tv, item, res = R.find_item(n)
        if res.text != n:
            log(f"수신자 해석: '{n}' → '{res.text}'  ({res.why})")
        resolved.append((tv, item, res))

    # 2) 첫 수신자로 쪽지창 열기
    before = {w['hwnd'] for w in cm.windows() if '메시지 전송' in w['title']}
    tv, item, res = resolved[0]
    cm.select_tree_item(tv['hwnd'], item['hItem'], double_click=True)
    compose = _wait_window('메시지 전송', 20, before)
    if not compose:
        raise SendError(f"'{res.text}' 쪽지창이 열리지 않았습니다.")
    kids = cm.children(compose['hwnd'])
    log('쪽지창 열림 | 수신자: %s' % ', '.join(
        k['text'] for k in kids if k['vis'] and k['cls'].startswith('Afx') and k['text']))

    # 3) 추가 수신자 — [받는사람] → '사용자 선택'
    if len(resolved) > 1:
        cm.click(next(k['hwnd'] for k in kids if k['id'] == ID_PICK))   # 모달 → Post
        dlg = _wait_window('사용자 선택', 20)
        if not dlg:
            raise SendError("'사용자 선택' 창이 열리지 않았습니다.")
        dk = cm.children(dlg['hwnd'])
        src_tree = next(k['hwnd'] for k in dk if k['id'] == ID_SRC_TREE)
        add_btn = next(k['hwnd'] for k in dk if k['id'] == ID_ADD)
        ok_btn = next(k['hwnd'] for k in dk if k['id'] == ID_OK)
        for _, _, r in resolved[1:]:
            hit = next((i for i in cm.tree_items(src_tree) if i['text'] == r.text), None)
            if not hit:
                log(f"  '{r.text}' 을 사용자 선택 창에서 못 찾음 — 건너뜀")
                continue
            cm.select_tree_item(src_tree, hit['hItem'])
            cm.user32.SendMessageW(add_btn, cm.BM_CLICK, 0, 0)
            time.sleep(0.8)
            log(f'  추가: {r.text}')
        cm.click(ok_btn)
        time.sleep(3)
        kids = cm.children(compose['hwnd'])

    # 4) 제목
    title_edit = next(k['hwnd'] for k in kids if k['cls'] == 'Edit' and k['id'] == ID_TITLE)
    cm.set_text(title_edit, title)
    time.sleep(0.3)
    if cm.get_text(title_edit) != title:
        log('경고: 제목이 그대로 들어가지 않았습니다')

    # 5) 본문
    html = body_html or ('<p>' + '</p><p>'.join((body or '').split('\n')) + '</p>')
    log('본문 입력 → %s' % _set_body(html))

    # 6) 첨부 — [파일첨부] → '열기' 창 파일명에 **전체 경로**
    for f in attachments:
        full = os.path.abspath(f)
        cm.click(next(k['hwnd'] for k in cm.children(compose['hwnd']) if k['id'] == ID_ATTACH))
        fd = _wait_window('열기', 20)
        if not fd:
            log(f'  경고: 열기 창이 안 떠 첨부를 건너뜀 — {full}')
            continue
        fk = cm.children(fd['hwnd'])
        cm.set_text(next(k['hwnd'] for k in fk
                         if k['cls'] == 'Edit' and k['id'] == ID_FILE_NAME and k['vis']), full)
        time.sleep(0.5)
        cm.click(next(k['hwnd'] for k in fk if k['cls'] == 'Button' and k['id'] == ID_FILE_OPEN))
        time.sleep(3)
        name = os.path.basename(full)
        if any(name in k['text'] for k in cm.children(compose['hwnd'])):
            log(f'  첨부 확인: {name}')
        else:
            log(f'  경고: 첨부 칩을 확인하지 못했습니다 — {name}')

    # 7) 예약전송 상태 알림 (건드리지 않는다 — 토글하면 수신자가 지워질 때가 있다)
    sched = toggle_state(compose['hwnd'], ID_SCHED)
    dtp = next((k for k in cm.children(compose['hwnd'])
                if k['cls'] == 'SysDateTimePick32'), None)
    when = cm.get_text(dtp['hwnd']) if dtp else ''
    log(f'  예약전송={sched}  나에게보내기={toggle_state(compose["hwnd"], ID_SELF)}  예약시각={when!r}')
    if sched == 'ON':
        log(f'  ⚠️ 즉시 발송이 아니라 {when} 에 도착합니다')

    if dry_run:
        log('[DryRun] 작성만 완료 — 창을 남깁니다')
        return {'dry_run': True, 'compose': compose['hwnd'], 'scheduled': when if sched == 'ON' else None}

    # 8) 발송 + tbl_send 로 검증
    before_row = last_sent()
    before_key = before_row['key'] if before_row else -1
    cm.click(next(k['hwnd'] for k in cm.children(compose['hwnd']) if k['id'] == ID_SEND))
    log('보내기 클릭')
    for _ in range(20):
        time.sleep(1)
        row = last_sent()
        if row and row['key'] > before_key and title in (row['title'] or ''):
            log('발송 확인: key=%s  도착=%s' % (row['key'], row['scheduled'] or '즉시'))
            return row
    raise SendError('보내기를 눌렀지만 보낸함에 기록이 생기지 않았습니다 '
                    '(수신자 칩이 비었거나 앱이 응답하지 않았을 수 있습니다).')
