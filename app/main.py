"""
스페이스기전 데스크 — 쿨메신저 · 업무시스템 도우미.

    python app/main.py

하나의 창에 지금까지 만든 기능을 모았다.
  · 바로가기   NEIS / 전북 업무포털 인증서 자동 로그인, 스페이스기전 열기
  · 쪽지       수신자·제목·본문을 넣어 쿨메신저로 보낸다
  · 명부       조직도를 떠 두고, 대화명이 실명과 다른 사람을 별칭으로 잇는다
  · 감시       새 쪽지를 spacekijun 알림으로, 거기서 쓴 답장을 쿨메신저로
  · 설정       자격증명(DPAPI), 요약 사용 여부

느린 작업(로그인·발송)은 **스레드**에서 돌린다. 창이 멈추면 사용자는 고장으로 받아들인다.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
import webbrowser
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import cm_win32 as cm          # noqa: E402
from core import inbox, roster, secretstore, settings, supa_auth, udb, watcher  # noqa: E402
from theme import ACCENT, BG, MUTED, apply_theme, page_heading, table  # noqa: E402

SPACEKIJUN_URL = 'https://spacekijun.lovable.app'
PAD = {'padx': 8, 'pady': 6}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('스페이스기전 데스크')
        self.geometry('1060x820')
        self.minsize(920, 740)
        self._log_q: queue.Queue[str] = queue.Queue()
        self.watcher = watcher.Watcher(log=self.log)

        apply_theme(self)
        header = ttk.Frame(self)
        header.pack(fill='x', padx=28, pady=(24, 18))
        ttk.Label(header, text='SPACEKIJUN  /  DESK', style='Brand.TLabel').pack(anchor='w')
        ttk.Label(header, text='스페이스기전 데스크', style='Title.TLabel').pack(anchor='w', pady=(5, 3))
        ttk.Label(header, text='학교 업무에 필요한 연결을 한곳에서.', style='Muted.TLabel').pack(anchor='w')

        # 기록은 아래에 고정하고 작업 영역에 나머지 공간을 배정한다.
        bottom = ttk.Frame(self)
        bottom.pack(side='bottom', fill='x', padx=28, pady=(10, 18))
        log_header = ttk.Frame(bottom)
        log_header.pack(fill='x', pady=(0, 7))
        ttk.Label(log_header, text='활동 기록', style='Brand.TLabel').pack(side='left')
        self.l_watch = ttk.Label(log_header, text='●  쪽지 감시 꺼짐', style='Muted.TLabel')
        self.l_watch.pack(side='right')
        self.logbox = tk.Text(bottom, height=3, wrap='word', state='disabled', font=('맑은 고딕', 9))
        self.logbox.pack(fill='x')

        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=20)
        self.nb = nb
        for name, build in (('바로가기', self._tab_links), ('쪽지', self._tab_inbox),
                            ('명부', self._tab_roster), ('설정', self._tab_settings)):
            f = ttk.Frame(nb)
            nb.add(f, text=name)
            if name == '설정':
                canvas = tk.Canvas(f, background=BG, highlightthickness=0)
                scroll = ttk.Scrollbar(f, orient='vertical', command=canvas.yview)
                scroll.pack(side='right', fill='y')
                canvas.pack(side='left', fill='both', expand=True)
                canvas.configure(yscrollcommand=scroll.set)
                content = ttk.Frame(canvas)
                window = canvas.create_window((0, 0), window=content, anchor='nw')
                content.bind('<Configure>', lambda e, c=canvas: c.configure(scrollregion=c.bbox('all')))
                canvas.bind('<Configure>', lambda e, c=canvas, w=window: c.itemconfigure(w, width=e.width))
                build(content)
                def scroll_settings(event):
                    if canvas.winfo_height() < content.winfo_reqheight():
                        canvas.yview_scroll(-int(event.delta / 120), 'units')
                def bind_scroll(widget):
                    widget.bind('<MouseWheel>', scroll_settings, add='+')
                    for child in widget.winfo_children():
                        bind_scroll(child)
                bind_scroll(f)
            else:
                build(f)

        nb.select(0)                     # 항상 «바로가기» 로 시작한다
        self.tray = self._make_tray()
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self.after(200, self._drain_log)
        self.log('준비됐습니다.')

    # ── 공통 ──────────────────────────────────────────────────
    def log(self, *parts):
        self._log_q.put(' '.join(str(p) for p in parts))

    def _drain_log(self):
        try:
            while True:
                line = self._log_q.get_nowait()
                self.logbox.configure(state='normal')
                self.logbox.insert('end', line + '\n')
                self.logbox.see('end')
                self.logbox.configure(state='disabled')
        except queue.Empty:
            pass
        self.after(200, self._drain_log)

    def _run_bg(self, fn, done=None):
        """느린 작업을 스레드로. 창이 얼지 않게 하려는 것."""
        def work():
            try:
                result = fn()
                if done:
                    self.after(0, lambda: done(result))
            except Exception as e:
                self.after(0, lambda error=e: self.log('오류:', error))
        threading.Thread(target=work, daemon=True).start()

    # ── 탭: 바로가기 ──────────────────────────────────────────
    def _tab_links(self, f):
        page_heading(f, '업무 바로가기', '자주 사용하는 업무시스템을 빠르게 여세요.')
        web = ttk.Frame(f, style='Hero.TFrame', padding=24)
        web.pack(fill='x', padx=8, pady=(0, 22))
        ttk.Label(web, text='우리 학교의 업무 공간', style='HeroCaption.TLabel').pack(anchor='w')
        ttk.Label(web, text='SPACEKIJUN', style='HeroTitle.TLabel').pack(anchor='w', pady=(6, 4))
        ttk.Label(web, text='평소 사용하던 브라우저에서 스페이스기전을 엽니다.',
                  style='HeroCaption.TLabel').pack(anchor='w')
        ttk.Button(web, text='스페이스기전 열기  ↗', style='Accent.TButton',
                   command=lambda: webbrowser.open(SPACEKIJUN_URL)).pack(anchor='w', pady=(18, 0))
        ttk.Label(f, text='인증서 자동 로그인', style='Brand.TLabel').pack(anchor='w', padx=8)
        cards = ttk.Frame(f)
        cards.pack(fill='x', padx=8, pady=(10, 12))
        cards.columnconfigure((0, 1), weight=1, uniform='links')
        for i, (title, desc, target) in enumerate((
                ('나이스 NEIS', '교육행정 업무시스템', 'neis'),
                ('전북 업무포털', '전자결재 및 학교 행정 업무', 'eduptl'))):
            card = ttk.Frame(cards, style='Card.TFrame', padding=20)
            card.grid(row=0, column=i, sticky='nsew', padx=(0, 8) if i == 0 else (8, 0))
            ttk.Label(card, text=title, style='CardTitle.TLabel').pack(anchor='w')
            ttk.Label(card, text=desc, style='CardCaption.TLabel').pack(anchor='w', pady=(5, 16))
            ttk.Button(card, text='로그인  →', command=lambda t=target: self._login(t)).pack(anchor='w')
        ttk.Label(f, text='처음 사용하시나요? 설정에서 인증서 암호를 저장하면 자동 로그인할 수 있습니다.',
                  style='Muted.TLabel').pack(anchor='w', padx=8, pady=(2, 0))

    def _login(self, which: str):
        if not secretstore.has_credentials():
            messagebox.showwarning('자격증명 필요', '설정 탭에서 인증서 암호를 먼저 저장하세요.')
            return
        self.log(f'{which} 로그인 시작 — 브라우저가 뜹니다')

        def work():
            from playwright.sync_api import sync_playwright
            from core import portal
            cred = secretstore.load()
            with sync_playwright() as pw:
                ctx = portal.launch(pw, target=which)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                fn = portal.login_neis if which == 'neis' else portal.login_eduptl
                r = fn(page, cred['cert_password'], cred.get('cert_match'))
                self.log(f"{which} 로그인: {'성공' if r.get('ok') else '실패'} {r.get('user') or ''}")
                self.log('창을 닫으면 세션이 끝납니다.')
                page.wait_for_event('close', timeout=0)   # 사용자가 닫을 때까지 유지
            return None
        self._run_bg(work)

    # ── 탭: 쪽지 (받은 쪽지 + spacekijun 답장) ────────────────
    def _tab_inbox(self, f):
        page_heading(f, '쪽지 모아보기', '쿨메신저에서 받은 쪽지와 스페이스기전 답장을 확인하세요.')
        top = ttk.Frame(f)
        top.pack(fill='x', **PAD)
        ttk.Button(top, text='새로고침', command=self._refresh_inbox).pack(side='left')
        self.l_inbox = ttk.Label(top, text='쪽지를 불러오는 중…', style='Muted.TLabel')
        self.l_inbox.pack(side='left', padx=10)

        cols = ('time', 'kind', 'who', 'status', 'body')
        self.msgs = table(f, cols, 7)
        for c, t, w in (('time', '시각', 100), ('kind', '구분', 56), ('who', '상대', 130),
                        ('status', '상태', 70), ('body', '내용', 420)):
            self.msgs.heading(c, text=t)
            self.msgs.column(c, width=w, anchor='w')
        self.msgs.tag_configure('reply', foreground=ACCENT)
        self.msgs.tag_configure('unread', foreground='#b02a37')
        self.msgs.bind('<<TreeviewSelect>>', self._show_message)

        ttk.Label(f, text='선택한 쪽지 전문').pack(anchor='w', padx=8, pady=(8, 0))
        self.t_detail = tk.Text(f, height=5, wrap='word', state='disabled',
                                font=('맑은 고딕', 10))
        self.t_detail.pack(fill='x', padx=8, pady=(2, 8))
        self._detail_hint('쪽지를 선택하면 여기에 전체 내용이 표시됩니다.')
        self._inbox_rows: list[dict] = []
        self.after(500, self._refresh_inbox)

    def _refresh_inbox(self):
        self.l_inbox.configure(text='쪽지를 불러오는 중…')
        def done(rows):
            self._inbox_rows = rows
            self.msgs.delete(*self.msgs.get_children())
            self._detail_hint('쪽지를 선택하면 여기에 전체 내용이 표시됩니다.' if rows
                              else '아직 표시할 쪽지가 없습니다. 쿨메신저 연결 상태를 확인한 뒤 새로고침하세요.')
            for i, r in enumerate(rows):
                tag = 'reply' if r['kind'] == '답장' else ('unread' if r['status'] == '안읽음' else '')
                self.msgs.insert('', 'end', iid=str(i), tags=(tag,),
                                 values=(r['time'], r['kind'], r['who'], r['status'],
                                         r['body'][:120]))
            got = sum(1 for r in rows if r['kind'] == '받음')
            self.l_inbox.configure(
                text=f'받음 {got}건 · 답장 {len(rows) - got}건'
                     + ('' if supa_auth.whoami() else '   (답장은 spacekijun 로그인 후 표시)'))
        self._run_bg(lambda: inbox.timeline(60), done=done)

    def _detail_hint(self, text):
        self.t_detail.configure(state='normal')
        self.t_detail.delete('1.0', 'end')
        self.t_detail.insert('1.0', text)
        self.t_detail.configure(state='disabled')

    def _show_message(self, _evt=None):
        sel = self.msgs.selection()
        if not sel:
            return
        r = self._inbox_rows[int(sel[0])]
        self.t_detail.configure(state='normal')
        self.t_detail.delete('1.0', 'end')
        self.t_detail.insert('1.0', f"[{r['kind']}] {r['who']}  {r['when']}\n\n{r['body']}")
        self.t_detail.configure(state='disabled')

    # ── 탭: 명부 ──────────────────────────────────────────────
    def _tab_roster(self, f):
        page_heading(f, '교직원 명부', '대화명을 검색하고, 실명과 다른 이름은 별칭으로 연결하세요.')
        top = ttk.Frame(f)
        top.pack(fill='x', **PAD)
        ttk.Button(top, text='조직도에서 새로 읽기', command=self._sync_roster).pack(side='left')
        self.e_find = ttk.Entry(top, width=24)
        self.e_find.pack(side='left', padx=8)
        self.e_find.bind('<Return>', lambda event: self._search_roster())
        ttk.Button(top, text='검색', command=self._search_roster).pack(side='left')
        aliases = ttk.Frame(f)
        aliases.pack(fill='x', **PAD)
        ttk.Label(aliases, text='대화명').pack(side='left', padx=(0, 8))
        self.e_alias_from = ttk.Entry(aliases, width=18)
        self.e_alias_from.pack(side='left')
        ttk.Label(aliases, text='→  실명').pack(side='left', padx=8)
        self.e_alias_to = ttk.Entry(aliases, width=18)
        self.e_alias_to.pack(side='left')
        ttk.Button(aliases, text='별칭 추가', command=self._add_alias).pack(side='left', padx=8)

        cols = ('display', 'note')
        self.tree = table(f, cols, 9)
        self.tree.heading('display', text='대화명')
        self.tree.heading('note', text='메모 (실명 등)')
        self.tree.column('display', width=200)
        self.l_roster = ttk.Label(f, text='', style='Muted.TLabel')
        self.l_roster.pack(anchor='w', **PAD)
        self.after(400, self._search_roster)

    def _fill_roster(self, rows):
        self.l_roster.configure(text=f'교직원 {len(rows)}명' if rows else '표시할 명부가 없습니다. 검색어를 바꾸거나 조직도에서 새로 읽어 주세요.')
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert('', 'end', values=(r['display'], r['note']))

    def _search_roster(self):
        q = self.e_find.get().strip()
        rows = [r for r in roster.roster() if not q or q in r['text']]
        self._fill_roster(rows)
        self.log(f'명부 {len(rows)}명' + (f" (검색: {q})" if q else ''))

    def _sync_roster(self):
        self.log('조직도를 읽는 중...')
        self._run_bg(roster.sync,
                     done=lambda rows: (self._fill_roster(rows), self.log(f'명부 {len(rows)}명 갱신')))

    def _add_alias(self):
        a, b = self.e_alias_from.get().strip(), self.e_alias_to.get().strip()
        if not a or not b:
            return
        roster.set_alias(a, b)
        res = roster.resolve(a)
        self.log(f"별칭 '{a}' → '{b}'  " + (f'확인: {res.text}' if res.ok else f'⚠ {res.why}'))

    # ── 탭: 설정 ──────────────────────────────────────────────
    def _tab_settings(self, f):
        page_heading(f, '연결 및 설정', '업무 계정과 쪽지 알림을 관리하세요.')
        box = ttk.LabelFrame(f, text='인증서 자동 로그인 · 이 PC에 암호화 저장', padding=10)
        box.pack(fill='x', **PAD)
        ttk.Label(box, text='업무포털 아이디').grid(row=0, column=0, sticky='w', **PAD)
        self.e_id = ttk.Entry(box, width=28)
        self.e_id.grid(row=0, column=1, sticky='w', **PAD)
        ttk.Label(box, text='인증서 암호').grid(row=1, column=0, sticky='w', **PAD)
        self.e_pw = ttk.Entry(box, width=28, show='•')
        self.e_pw.grid(row=1, column=1, sticky='w', **PAD)
        ttk.Button(box, text='저장', command=self._save_cred).grid(row=1, column=2, **PAD)
        try:
            cur = secretstore.load()
            self.e_id.insert(0, cur.get('id', ''))
            self.e_pw.insert(0, cur.get('cert_password', ''))
        except secretstore.SecretError:
            pass

        box2 = ttk.LabelFrame(f, text='쪽지 알림 · 답장 연동', padding=10)
        box2.pack(fill='x', **PAD)
        self.v_summary = tk.BooleanVar(value=True)
        self.v_body = tk.BooleanVar(value=True)
        ttk.Checkbutton(box2, text='긴 본문은 Solar 로 요약해서 알림',
                        variable=self.v_summary).grid(row=0, column=0, sticky='w', **PAD)
        ttk.Checkbutton(box2, text='알림에 본문 넣기 (끄면 발신자만)',
                        variable=self.v_body).grid(row=1, column=0, sticky='w', **PAD)
        self.b_watch = ttk.Button(box2, text='감시 시작', command=self._toggle_watch)
        self.b_watch.grid(row=0, column=1, rowspan=2, **PAD)

        boxs = ttk.LabelFrame(f, text='SPACEKIJUN 계정', padding=10)
        boxs.pack(fill='x', **PAD)
        self.l_auth = ttk.Label(boxs, text='')
        self.l_auth.grid(row=0, column=0, sticky='w', **PAD)
        self.b_auth = ttk.Button(boxs, text='로그인', command=self._toggle_auth)
        self.b_auth.grid(row=0, column=1, **PAD)
        ttk.Label(boxs, text='알림·답장에 쓰입니다. 로그인 정보는 이 PC 에만 암호화 보관됩니다.',
                  foreground=MUTED).grid(row=1, column=0, columnspan=2, sticky='w', **PAD)
        self._refresh_auth()

        box3 = ttk.LabelFrame(f, text='쿨메신저 연결', padding=10)
        box3.pack(fill='x', **PAD)
        ttk.Button(box3, text='상태 확인', command=self._check_cm).pack(side='left', **PAD)
        ttk.Label(box3, text='연결이 안 되면 쿨메신저-실행.bat로 실행해 주세요.',
                  foreground=MUTED).pack(side='left')

    # ── 쿨메신저 계정 ─────────────────────────────────────────
    AUTO = '자동 (최근 사용)'

    def _reload_accounts(self):
        names = [r['name'] for r in udb.accounts()]
        self.cb_account['values'] = [self.AUTO] + names
        cur = udb.configured()
        self.cb_account.set(cur if cur in names else self.AUTO)
        self._show_account_status()

    def _pick_account(self, _evt=None):
        v = self.cb_account.get()
        settings.set('coolmsg_account', '' if v == self.AUTO else v)
        self.log(f"쿨메신저 계정: {v}")
        self._show_account_status()
        self._refresh_inbox()

    def _show_account_status(self):
        st = udb.status()
        if not st.get('ok'):
            self.l_account.configure(text='⚠ ' + (st.get('why') or '쪽지 DB 를 찾지 못했습니다'),
                                     foreground='#b02a37')
            return
        msg = f"읽는 계정: {st['account']}  ({st['source']})"
        if st.get('registry'):
            msg += f"  · 쿨메신저 기억: {st['registry']}"
        if st.get('warn'):
            msg += '\n⚠ ' + st['warn']
        self.l_account.configure(text=msg,
                                 foreground='#b02a37' if st.get('warn') else '#666')

    def _refresh_auth(self):
        who = supa_auth.whoami()
        self.l_auth.configure(text=f'로그인됨: {who}' if who else '로그인 전')
        self.b_auth.configure(text='로그아웃' if who else '로그인')

    def _toggle_auth(self):
        if supa_auth.whoami():
            supa_auth.logout()
            self.log('spacekijun 로그아웃')
            self._refresh_auth()
            return
        self.log('브라우저에서 구글 로그인해 주세요...')
        supa_auth.login_async(
            lambda sess: self.after(0, lambda: (self._refresh_auth(), self._refresh_inbox())),
            log=self.log)

    def _save_cred(self):
        secretstore.save({'id': self.e_id.get().strip(),
                          'cert_password': self.e_pw.get(),
                          'cert_match': None})
        self.log('자격증명을 저장했습니다 (DPAPI, 이 PC 전용)')

    def _toggle_watch(self):
        if self.watcher.running:
            self.watcher.stop()
            self.b_watch.configure(text='감시 시작')
            self.l_watch.configure(text='●  쪽지 감시 꺼짐', foreground=MUTED)
        else:
            self.watcher.use_summary = self.v_summary.get()
            self.watcher.show_body = self.v_body.get()
            self.watcher.start()
            self.b_watch.configure(text='감시 중지')
            self.l_watch.configure(text='●  쪽지 감시 중', foreground=ACCENT)

    def _check_cm(self):
        def work():
            if not cm.pid():
                return '쿨메신저가 실행 중이 아닙니다.'
            m = cm.main_window()
            if not m:
                return '메인 창을 찾지 못했습니다 (로그인 확인).'
            try:
                n = len(cm.org_tree())
            except Exception as e:
                return f'조직도를 읽지 못했습니다: {e}'
            from core import cdp
            try:
                cdp.targets()
                port = 'CDP 정상'
            except Exception:
                port = 'CDP 없음 — 쿨메신저-실행.bat 로 다시 켜세요'
            return f'실행 중 · 조직도 {n}개 · {port}'
        self._run_bg(work, done=lambda msg: self.log('쿨메신저:', msg))

    # ── 트레이 상주 ───────────────────────────────────────────
    def _make_tray(self):
        """창을 닫아도 감시가 계속되도록 트레이에 남는다."""
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            self.log('pystray/Pillow 가 없어 트레이 없이 실행합니다')
            return None
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((6, 6, 58, 58), radius=14, fill=ACCENT)
        d.text((24, 20), 'S', fill='white')
        menu = pystray.Menu(
            pystray.MenuItem('열기', lambda *_: self.after(0, self._show_window), default=True),
            pystray.MenuItem('감시 시작/중지', lambda *_: self.after(0, self._toggle_watch)),
            pystray.MenuItem('종료', lambda *_: self.after(0, self._quit)))
        icon = pystray.Icon('spacekijun-desk', img, '스페이스기전 데스크', menu)
        threading.Thread(target=icon.run, daemon=True).start()
        return icon

    def _show_window(self):
        self.deiconify()
        self.lift()

    def _quit(self):
        if self.watcher.running:
            self.watcher.stop()
        if self.tray:
            self.tray.stop()
        self.destroy()

    def _on_close(self):
        """X 를 눌러도 종료하지 않는다 — 감시가 끊기면 알림이 멈추기 때문이다."""
        if self.tray:
            self.withdraw()
            self.log('트레이로 내려갔습니다. 감시는 계속됩니다 (종료는 트레이 메뉴에서).')
        else:
            self._quit()


if __name__ == '__main__':
    if '--classic' in sys.argv:
        App().mainloop()
    else:
        from desktop import main
        main()
