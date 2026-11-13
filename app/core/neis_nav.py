"""
NEIS(4세대) 메뉴 탐색 — 데스크의 NEIS 자동 로그인 창(Playwright Edge)을 그대로 조작한다.

`.claude/skills/neis-navigate/neis-nav.js` 에서 출발했지만, 2026-09-11 실측으로 스킬 문서와
다른 점이 여럿 드러나 여기서 바로잡았다. 아래는 전부 실제로 확인한 것이다.

메뉴 구조
  · 상단 탭을 누르면 **메가메뉴 전체가 한 번에 렌더된다**. 1단계는 열 제목, 2단계는 그 아래
    항목으로 *처음부터 모두 보인다*. 1단계를 눌러 펼칠 필요가 없다.
  · 항목 텍스트는 두 가지다.
        아직 펼치지 않은 항목   "출결관리 2단계"
        펼쳐서 하위가 생긴 항목 "출결관리 2단계 메뉴항목"
    즉 **누르기 전에는 폴더인지 화면인지 알 수 없다**. 눌러 보고 하위가 생기면 폴더다.
  · 3단계 이하는 상위를 눌러야 나타난다.

함정
  · 로그인 직후 공지 팝업이 여러 겹 뜬다. 안 닫으면 메뉴 클릭이 **조용히 무시된다**.
  · 닫기 버튼은 `button` 이 아니라 **`div.cl-text`** 다. 그리고 겹친 팝업은 **맨 위(last)부터**
    닫아야 한다. 아래 것을 먼저 누르면 위 팝업이 클릭을 가로채 실패하는데 오류도 안 난다.
  · 메가메뉴는 "다른 탭 → 대상 탭" 순으로 눌러야 열린다. 활성 탭 재클릭은 무시된다.
  · 로딩 판정은 `.ers_progress_content` 가 사라지는 것으로 한다.
  · 세션은 약 50분 뒤 자동 로그아웃된다.
"""
from __future__ import annotations

import re

TAB_SELECTOR = '.cl-navigationbar-text.cl-text'
# 메뉴는 두 군데에 있다 (2026-09-11 실측).
#   상단 메가메뉴  `.cl-navigationbar-listitem`  — 1단계(열 제목)와 2단계. 항목을 누르면 닫힌다.
#   왼쪽 사이드바  `.cl-sidenavigation-item`     — 2단계를 누른 뒤 그 아래 3단계가 여기 나온다.
MEGA_SELECTOR = '.cl-navigationbar-listitem div.cl-text:visible'
SIDE_SELECTOR = '.cl-sidenavigation-item div.cl-text:visible'
ITEM_SELECTOR = 'div.cl-text:visible'
SCOPES = {'mega': '.cl-navigationbar-listitem div.cl-text',
          'side': '.cl-sidenavigation-item div.cl-text',
          'any': 'div.cl-text'}
LOADING_SELECTOR = '.ers_progress_content'
DETOUR_TAB = '교육통계'
DETOUR_FALLBACK = '업무분장설정업무'

# "이름 N단계" 또는 "이름 N단계 메뉴항목"
ITEM_PATTERN = re.compile(r'^(.+?)\s+(\d)단계(\s+메뉴항목)?$')


class NavError(RuntimeError):
    pass


def _escape(name: str) -> str:
    return re.escape(name)


def _item_rx(name: str) -> re.Pattern:
    """항목 텍스트는 '이름 N단계' 또는 '이름 N단계 메뉴항목' 이다."""
    return re.compile(r'^' + _escape(name) + r'\s+\d단계(\s+메뉴항목)?$')


def wait_loading(page, timeout_ms: int = 45000) -> None:
    page.evaluate(
        """async (limit) => {
            const d = t => new Promise(r => setTimeout(r, t));
            const t0 = Date.now();
            await d(300);
            while (Date.now() - t0 < limit) {
                const busy = document.querySelector('SELECTOR');
                if (!busy || busy.offsetParent === null) return;
                await d(400);
            }
        }""".replace('SELECTOR', LOADING_SELECTOR),
        timeout_ms)


PROBE_MS = 8000          # 항목이 그려질 때까지 기다리는 시간. 무거운 화면 뒤에는 4초로 모자랐다.
DIALOG_SELECTOR = '.cl-dialog:visible'
# 모달에서 누를 단추. **안전한 것부터** 본다.
DISMISS_ORDER = ('취소', '아니오', '닫기', '확인')
# 2차 인증을 요구하는 창. 사람이 직접 해야 하므로 건드리지 않는다.
AUTH_PATTERN = re.compile(r'2차\s*인증|OTP|인증번호')


def auth_required(page) -> bool:
    """2차 인증 창이 떠 있는지. 떠 있으면 사람이 인증할 때까지 그 화면은 쓸 수 없다."""
    try:
        for text in page.evaluate(
                """() => Array.from(document.querySelectorAll('.cl-dialog'))
                       .filter(e => e.offsetParent !== null)
                       .map(e => (e.textContent || '').replace(/\s+/g, ' ').trim())""") or []:
            if AUTH_PATTERN.search(text):
                return True
    except Exception:
        pass
    return False


def close_auth_dialog(page) -> bool:
    """2차 인증 창을 닫는다. **그 화면을 포기해도 되는 경우에만** 쓴다.

    닫으면 화면까지 함께 닫힌다. 그러니 사용자가 그 화면을 쓰려고 기다리는 동안 대신
    닫으면 안 된다 — 인증은 사람이 해야 한다.

    반대로 **다른 화면으로 옮겨 갈 때는 닫아야 한다.** 이 창이 떠 있으면 뒤의 모든 클릭이
    막혀 그다음 요청이 통째로 실패한다 (2026-09-11 실측: 세특을 연 뒤 수행평가를 부탁하면
    "2차 인증 창이 떠 있습니다" 로 끝났다). 어차피 떠나는 화면이니 닫는 편이 맞다.
    """
    if not auth_required(page):
        return False
    for label in ('닫기', '취소'):
        button = (page.locator(DIALOG_SELECTOR + ' div.cl-text:visible, '
                               + DIALOG_SELECTOR + ' button:visible')
                  .filter(has_text=re.compile('^' + label + '$')).last)
        try:
            if button.count() == 0:
                continue
            button.click(timeout=6000)
        except Exception:
            continue
        page.wait_for_timeout(1200)
        return not auth_required(page)
    return False


def dismiss_dialogs(page) -> int:
    """모달 대화상자를 치운다.

    화면에 들어가기만 해도 `과목은(는) 필수 입력입니다.` 같은 알림이 뜨는 곳이 있다
    (2026-09-11 문항정보표관리에서 실측). 안 치우면 이후 클릭이 **전부** 막힌다.

    ★ 되묻는 창이면 **취소**를 누른다. 무엇을 묻는지 모르는 채로 확인을 누르면 지우거나
      마감해 버릴 수 있다. 취소가 없는 단순 알림일 때만 확인을 누른다.
    """
    closed = 0
    for _ in range(8):
        dialogs = page.locator(DIALOG_SELECTOR)
        try:
            if dialogs.count() == 0:
                break
            top = dialogs.last
            # 2차 인증 창은 사람이 해야 한다. 닫으면 화면까지 같이 닫힌다
            # (2026-09-11 과목별세부능력및특기사항에서 실측).
            if AUTH_PATTERN.search(' '.join((top.text_content() or '').split())):
                break
            for label in DISMISS_ORDER:
                button = (top.locator('div.cl-text:visible, button:visible')
                          .filter(has_text=re.compile('^' + label + '$')).first)
                if button.count() == 0:
                    continue
                button.click(timeout=5000)
                break
            else:
                break                      # 누를 만한 단추가 없다. 건드리지 않는다.
        except Exception:
            break
        page.wait_for_timeout(700)
        closed += 1
    return closed


def close_popups(page) -> int:
    """공지 팝업과 모달 알림을 전부 치운다. 개수는 매번 다르다 (관측: 3·5·8개)."""
    closed = dismiss_dialogs(page)
    for _ in range(20):
        buttons = (page.locator('div.cl-text:visible, button:visible')
                   .filter(has_text=re.compile(r'^닫기$')))
        try:
            if buttons.count() == 0:
                break
            buttons.last.click(timeout=5000)     # ★ 맨 위 팝업부터
        except Exception:
            break
        page.wait_for_timeout(700)
        closed += 1
    return closed


SCREEN_TAB_SELECTOR = '.cl-tabfolder-item.type-M'
SCREEN_CLOSE_SELECTOR = '.cl-tabfolder-button'
SCREEN_LIMIT = 14        # 이만큼 쌓이면 닫는다 (상한은 20)
# 화면 오른쪽 아래의 '탭 아이템 전체 닫기'. 하나씩 닫는 것보다 훨씬 빠르다.
CLOSE_ALL_SELECTOR = '.btn-close-mdi[title*="전체 닫기"]:visible'


def open_screens(page) -> int:
    """지금 열어 둔 업무 화면 탭 수. 화면 아래쪽에 탭으로 쌓인다."""
    try:
        return page.locator(SCREEN_TAB_SELECTOR).count()
    except Exception:
        return 0


def close_screens(page, keep: int = 0) -> int:
    """열어 둔 업무 화면 탭을 오래된 것부터 닫는다.

    🚨 NEIS 는 화면을 아래쪽 탭으로 쌓아 두는데 **20개가 차면 더 열리지 않는다.** 그런데
    오류를 내지 않는다 — 메뉴를 눌러도 조용히 있던 화면에 머문다. 2026-09-11 에 이것 때문에
    수집 자료 여러 건이 엉뚱하게 같은 화면 내용으로 채워졌고, 화면 제목을 견주기 전까지
    알아채지 못했다.

    화면 오른쪽 아래에 **탭 아이템 전체 닫기** 단추가 있다. 하나씩 닫으면 20개에 20초가
    걸리므로 전부 닫을 때는 그 단추를 쓴다. 닫을 때 되묻는 창이 뜨면 `dismiss_dialogs` 가
    안전한 쪽을 고른다.
    """
    if keep <= 0:
        before = open_screens(page)
        button = page.locator(CLOSE_ALL_SELECTOR).first
        try:
            if before and button.count():
                button.click(timeout=8000)
                page.wait_for_timeout(800)
                dismiss_dialogs(page)
                if open_screens(page) == 0:
                    return before
        except Exception:
            pass                      # 단추가 없거나 막혔다. 아래에서 하나씩 닫는다.

    closed = 0
    for _ in range(30):
        buttons = page.locator(SCREEN_CLOSE_SELECTOR)
        try:
            before = buttons.count()
            if before <= keep:
                break
            buttons.last.click(timeout=5000)      # 가장 오래된 것부터
        except Exception:
            break
        page.wait_for_timeout(400)
        dismiss_dialogs(page)
        if open_screens(page) >= before:
            break                                  # 안 닫혔다. 더 눌러도 소용없다.
        closed += 1
    return closed


def active_screen(page) -> str:
    """지금 보고 있는 업무 화면 이름. 아래쪽 탭 중 선택된 것."""
    try:
        selected = page.locator(SCREEN_TAB_SELECTOR + '.cl-selected').first
        if selected.count() == 0:
            return ''
        return ' '.join((selected.text_content() or '').split())
    except Exception:
        return ''


# ── 메뉴 검색 ────────────────────────────────────────────────
# 왼쪽 아이콘 줄의 '메뉴 검색'. 찾은 결과마다 **전체 경로**가 붙어 나온다.
#   과목별출결관리
#   교과담임 > 학적 > 출결관리 > 과목별출결관리
# 메가메뉴를 한 단계씩 눌러 들어가는 것보다 훨씬 튼튼하다 — 경유 클릭도, 폴더 펼침도,
# 계정마다 다른 메뉴 구성을 미리 알 필요도 없다. 경로 첫 칸이 탭이라 어느 탭의 것인지도
# 바로 알 수 있다 (2026-09-11 실측).
SEARCH_BUTTON = '[class*="cl-button"][class*="search"]:visible'
SEARCH_ROW = '.menu-find-grp'                 # locator 용에는 :visible 을 덧붙인다


def open_search(page) -> None:
    """검색 패널을 연다. **아이콘은 토글이라** 이미 열려 있으면 누르지 않는다 —
    누르면 닫혀 버려서, 두 번째 검색부터 조용히 실패한다 (2026-09-11 실측)."""
    if search_open(page):
        return
    page.locator(SEARCH_BUTTON).first.click(timeout=15000)
    page.wait_for_timeout(900)


def search_open(page) -> bool:
    """검색칸이 실제로 그려져 있는지. 아이콘의 `selected` 는 닫은 뒤에도 남아 믿을 수 없다."""
    try:
        return bool(page.evaluate(
            """() => Array.from(document.querySelectorAll('input:not([type=hidden])'))
                   .some(e => e.offsetParent !== null && e.getBoundingClientRect().x < 300)"""))
    except Exception:
        return False


def wait_overlay_gone(page, timeout_ms: int = 8000) -> None:
    """왼쪽 패널이 씌우는 덮개가 걷힐 때까지 기다린다.

    검색 패널이 뜨고 지는 동안 화면 전체를 덮는 `.cl-overlay` 가 잠시 깔린다. 그때 화면 안
    탭이나 조회 단추를 누르면 "subtree intercepts pointer events" 로 막힌다 (2026-09-11 실측).
    """
    try:
        page.evaluate(
            """async (limit) => {
                const d = t => new Promise(r => setTimeout(r, t));
                const t0 = Date.now();
                while (Date.now() - t0 < limit) {
                    const on = Array.from(document.querySelectorAll('.cl-overlay'))
                        .some(e => e.offsetParent !== null);
                    if (!on) return;
                    await d(250);
                }
            }""", timeout_ms)
    except Exception:
        pass


def search_menu(page, word: str, wait_ms: int = 2500, tries: int = 2) -> list[dict]:
    """메뉴를 검색해 [{name, tab, path}] 로 돌려준다.

    패널을 막 연 직후에는 결과가 비어 나오는 일이 있어 한 번 더 물어본다.
    """
    for attempt in range(tries):
        found = _search_once(page, word, wait_ms)
        if found or attempt == tries - 1:
            return found
        page.wait_for_timeout(1200)
    return []


def _search_once(page, word: str, wait_ms: int) -> list[dict]:
    open_search(page)
    # 패널이 그려지기 전에 입력하면 엉뚱한 칸에 들어간다. 검색칸이 생길 때까지 기다린다.
    for _ in range(20):
        if page.evaluate(
                """() => Array.from(document.querySelectorAll('input:not([type=hidden])'))
                       .some(e => e.offsetParent !== null && e.getBoundingClientRect().x < 300)"""):
            break
        page.wait_for_timeout(300)
    # 화면에도 입력칸이 있으므로 "첫 번째 input" 으로는 안 된다. 검색 패널은 화면 맨 왼쪽에
    # 있으니 보이는 입력칸 중 **가장 왼쪽** 것을 고른다.
    index = page.evaluate(
        """() => {
             const boxes = Array.from(document.querySelectorAll('input:not([type=hidden])'))
                 .map((e, i) => ({i, x: e.getBoundingClientRect().x, on: e.offsetParent !== null}))
                 .filter(b => b.on);
             if (!boxes.length) return -1;
             return boxes.sort((a, b) => a.x - b.x)[0].i;
           }""")
    if index < 0:
        raise NavError('메뉴 검색 입력칸을 찾지 못했습니다.')
    box = page.locator('input:not([type=hidden])').nth(index)
    box.click(timeout=10000)
    box.fill(word)
    box.press('Enter')
    page.wait_for_timeout(wait_ms)
    wait_loading(page)

    # `:visible` 은 Playwright 전용이라 브라우저 querySelectorAll 에는 넣을 수 없다.
    raw = page.evaluate(
        """(selector) => Array.from(document.querySelectorAll(selector))
              .filter(row => row.offsetParent !== null).map(row => {
              const link = row.querySelector('a');
              const path = Array.from(row.querySelectorAll('div.cl-text'))
                  .map(e => (e.textContent || '').replace(/\\s+/g, ' ').trim())
                  .find(t => t.includes(' > ')) || '';
              return {name: (link ? link.textContent : '').replace(/\\s+/g, ' ').trim(), path};
           })""", SEARCH_ROW) or []
    out, seen = [], set()
    for row in raw:
        path = row.get('path') or ''
        if not row.get('name') or ' > ' not in path or path in seen:
            continue
        seen.add(path)
        out.append({'name': row['name'], 'tab': path.split(' > ')[0].strip(), 'path': path})
    return out


def open_by_search(page, name: str, path: str = '') -> str:
    """검색으로 화면을 연다. 열린 화면 이름을 돌려준다.

    `path` 를 주면 그 경로의 결과만 누른다 — 같은 이름이 여러 탭에 있기 때문이다.
    """
    # 앞 화면이 남긴 알림 창이 있으면 검색 아이콘부터 못 누른다. 먼저 치운다.
    dismiss_dialogs(page)
    wait_overlay_gone(page)
    # 2차 인증 창이 떠 있으면 그 뒤의 모든 클릭이 막힌다. 먼저 알려야 한다.
    if auth_required(page):
        raise NavError('2차 인증 창이 떠 있습니다. 인증을 마치거나 그 창을 닫은 뒤 다시 시도해 주세요.')
    results = search_menu(page, name)
    if not results:
        raise NavError(f"'{name}' 을 메뉴 검색에서 찾지 못했습니다.")
    wanted = next((r for r in results if r['path'] == path), None) if path else None
    wanted = wanted or next((r for r in results if r['name'] == name), None) or results[0]
    row = page.locator(SEARCH_ROW + ':visible').filter(has_text=wanted['path']).first
    try:
        row.locator('a').first.click(timeout=15000)
    except Exception as exc:
        raise NavError(f"'{name}' 검색 결과를 누르지 못했습니다: "
                       f"{str(exc).splitlines()[0]}") from None
    page.wait_for_timeout(2000)
    wait_loading(page)
    page.wait_for_timeout(1500)
    dismiss_dialogs(page)       # 진입만 해도 뜨는 알림을 치우고
    wait_overlay_gone(page)     # 덮개가 걷힌 뒤에 돌려준다
    return active_screen(page)


def opened_screen(page) -> dict:
    """방금 연 화면의 상태. 2차 인증 대기 중인지도 함께 알려 준다."""
    return {'screen': active_screen(page), 'auth': auth_required(page)}


def tabs(page) -> list[str]:
    """상단 탭 이름 목록. 텍스트의 '0단계 메뉴항목' 꼬리표는 떼고 돌려준다."""
    out = []
    for raw in page.locator(TAB_SELECTOR).all_text_contents():
        match = ITEM_PATTERN.match(raw.strip())
        name = match.group(1) if match else raw.strip()
        if name:
            out.append(name)
    return out


def menu_items(page, where: str = 'any') -> list[dict]:
    """지금 보이는 메뉴 항목을 [{name, level, folder}] 로 읽는다.

    `where` 로 범위를 고른다 — 'mega'(상단 메가메뉴), 'side'(왼쪽 사이드바), 'any'(둘 다).
    색인을 만들 때는 'mega' 만 본다. 화면을 열면 사이드바에도 같은 꼴의 항목이 생기는데
    그것까지 주우면 색인이 엉뚱한 묶음으로 섞인다.

    `folder` 는 '메뉴항목' 꼬리표가 붙었는지 — 즉 **펼쳐진 폴더**인지다. 꼬리표가 없다고
    화면(잎)이라는 보장은 없다. 눌러 봐야 안다.
    """
    raw = page.evaluate(
        """(selector) => Array.from(document.querySelectorAll(selector))
              .filter(e => e.offsetParent !== null)
              .map(e => (e.textContent || '').trim())""",
        SCOPES.get(where, SCOPES['any'])) or []
    out, seen = [], set()
    for text in raw:
        match = ITEM_PATTERN.match(text)
        if not match:
            continue
        name, level = match.group(1), int(match.group(2))
        if (name, level) in seen:
            continue
        seen.add((name, level))
        out.append({'name': name, 'level': level, 'folder': bool(match.group(3))})
    return out


def open_tab(page, tab_name: str) -> None:
    """상단 탭을 열어 메가메뉴를 띄운다. 활성 탭 재클릭은 무시되므로 다른 탭을 경유한다."""
    close_popups(page)
    available = tabs(page)
    if tab_name not in available:
        raise NavError(f"'{tab_name}' 탭이 없습니다. 사용 가능한 탭: {', '.join(available)}")
    detour = DETOUR_FALLBACK if DETOUR_TAB in tab_name else DETOUR_TAB
    if detour not in available:
        detour = next((t for t in available if t != tab_name), None)
    if detour:
        page.locator(TAB_SELECTOR, has_text=detour).first.click(timeout=20000)
        page.wait_for_timeout(2000)
    page.locator(TAB_SELECTOR, has_text=tab_name).first.click(timeout=20000)
    page.wait_for_timeout(2500)


def click_item(page, name: str, timeout_ms: int = 15000) -> None:
    """메뉴 항목 하나를 누른다. 메가메뉴를 먼저 보고, 없으면 사이드바에서 찾는다.

    2단계까지는 메가메뉴에 있고 3단계부터는 사이드바에만 있다. 같은 이름이 양쪽에 다 보일
    때도 있어(직전에 들어갔던 화면) 순서를 고정해 둔다.
    """
    pattern = _item_rx(name)
    trouble = ''
    for selector in (MEGA_SELECTOR, SIDE_SELECTOR, ITEM_SELECTOR):
        target = page.locator(selector).filter(has_text=pattern).first
        try:
            # 있는지 세어 보기만 하면 안 된다. 상위를 누른 직후 사이드바가 그려지는 데 시간이
            # 걸려, 그 순간 세면 0 이 나온다 (2026-09-11 분할점수관리에서 실측).
            target.wait_for(state='visible', timeout=PROBE_MS)
        except Exception:
            continue
        try:
            target.click(timeout=timeout_ms)
        except Exception as exc:
            trouble = str(exc).splitlines()[0]
            continue
        page.wait_for_timeout(2200)
        return
    raise NavError(f"'{name}' 메뉴를 누르지 못했습니다." + (f' {trouble}' if trouble else
                                                            ' 화면에서 찾지 못했습니다.'))


def goto(page, tab_name: str, chain: list[str], progress=None) -> dict:
    """탭 → 메뉴 항목들을 차례로 눌러 업무 화면까지 간다.

    마지막 항목을 눌렀는데 더 깊은 단계가 나타나면 그 자리는 폴더다. 그때는 오류 대신
    `{'leaf': False, 'children': [...]}` 로 알려 준다 — 호출부가 사용자에게 되물을 수 있게.
    """
    def say(message):
        if progress:
            progress(message)

    if not chain:
        raise NavError('이동할 메뉴 이름이 없습니다.')

    # 탭이 20개 차면 새 화면이 조용히 안 열린다. 그 전에 오래된 것부터 치운다.
    if open_screens(page) >= SCREEN_LIMIT:
        say(f'열어 둔 화면 {close_screens(page, keep=2)}개를 닫았습니다')

    say(f'{tab_name} 메뉴 여는 중')
    open_tab(page, tab_name)

    for position, name in enumerate(chain):
        click_item(page, name)
        say(f'{name} 진입')
        if position < len(chain) - 1:
            continue

        # 잎인지 폴더인지는 **누른 뒤에** 알 수 있다. 메가메뉴는 어느 쪽이든 닫히므로,
        # 판정은 왼쪽 사이드바를 본다.
        #   · 폴더였으면 사이드바에 이름이 '…N단계 메뉴항목' 으로 펼쳐지고 하위가 나타난다.
        #   · 잎이었으면 꼬리표 없이 남고 업무 화면이 열린다.
        # 탭을 다시 열고 들어왔으므로 펼쳐진 것은 이 항목 하나뿐이다. 따라서 바로 아래 단계에
        # 보이는 항목이 곧 이 항목의 하위다.
        wait_loading(page)
        page.wait_for_timeout(1500)
        items = menu_items(page, 'any')
        entry = next((i for i in items if i['name'] == name and i['folder']), None)
        if entry:
            children = [i['name'] for i in items
                        if i['level'] == entry['level'] + 1 and i['name'] != name]
            if children:
                return {'leaf': False, 'tab': tab_name, 'chain': chain, 'children': children}
        return {'leaf': True, 'tab': tab_name, 'chain': chain}

    wait_loading(page)
    return {'leaf': True, 'tab': tab_name, 'chain': chain}


def click_text(page, text: str, timeout_ms: int = 20000) -> None:
    """화면 안의 버튼을 누른다 (조회·저장 등)."""
    element = (page.locator('div.cl-text:visible, button:visible, .cl-button:visible')
               .filter(has_text=re.compile('^' + _escape(text) + '$')).first)
    element.click(timeout=timeout_ms)
    page.wait_for_timeout(1500)
    wait_loading(page)
    page.wait_for_timeout(1500)


def screen_text(page, limit: int = 4000) -> str:
    raw = page.evaluate('() => document.body.innerText') or ''
    return ' '.join(raw.split())[:limit]
