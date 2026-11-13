"""Shared desktop styles; uses only the standard Tk/ttk toolkit."""
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

BG = '#f6f7fb'
INK = '#1e293b'
MUTED = '#64748b'
ACCENT = '#4f46e5'
LINE = '#e2e8f0'


def apply_theme(root):
    root.configure(background=BG)
    families = set(tkfont.families(root))
    font = next((f for f in ('Pretendard', 'Pretendard Variable', '맑은 고딕') if f in families), '맑은 고딕')
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont'):
        tkfont.nametofont(name).configure(family=font, size=10)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=(font, 10), background=BG, foreground=INK)
    style.configure('TFrame', background=BG)
    style.configure('Hero.TFrame', background='#eef2ff')
    style.configure('HeroTitle.TLabel', background='#eef2ff', foreground='#312e81', font=(font, 26, 'bold'))
    style.configure('HeroCaption.TLabel', background='#eef2ff', foreground='#62668a')
    style.configure('Card.TFrame', background='white')
    style.configure('CardTitle.TLabel', background='white', font=(font, 13, 'bold'))
    style.configure('CardCaption.TLabel', background='white', foreground=MUTED)
    style.configure('TLabel', background=BG)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Title.TLabel', font=(font, 23, 'bold'))
    style.configure('Section.TLabel', font=(font, 14, 'bold'))
    style.configure('Brand.TLabel', font=(font, 11, 'bold'), foreground=ACCENT)
    style.configure('TButton', padding=(15, 9), background='white', bordercolor=LINE,
                    lightcolor='white', darkcolor='white', focusthickness=2, focuscolor=ACCENT)
    style.map('TButton', background=[('disabled', '#e9edf3'), ('pressed', '#e0e7ff'),
                                   ('active', '#eef2ff')],
              foreground=[('disabled', '#94a3b8')], bordercolor=[('focus', ACCENT)])
    style.configure('Accent.TButton', background=ACCENT, foreground='white',
                    bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    style.map('Accent.TButton', background=[('disabled', '#b9b6ee'), ('pressed', '#3730a3'),
                                          ('active', '#4338ca')], foreground=[('disabled', '#f6f7fb'), ('!disabled', 'white')])
    style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 0, 0, 12))
    style.layout('TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
    style.layout('TNotebook.Tab', [('Notebook.padding', {'sticky': 'nswe', 'children': [
        ('Notebook.focus', {'sticky': 'nswe', 'children': [('Notebook.label', {'sticky': 'nswe'})]})
    ]})])
    style.configure('TNotebook.Tab', padding=(24, 11), background=BG, foreground=MUTED,
                    borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', '#e0e7ff'), ('active', '#eef2ff')],
              foreground=[('selected', ACCENT), ('active', INK)])
    style.configure('TLabelframe', bordercolor=LINE, borderwidth=1, relief='solid')
    style.configure('TLabelframe.Label', font=(font, 10, 'bold'), foreground=ACCENT)
    style.configure('TEntry', fieldbackground='white', bordercolor=LINE, padding=7)
    style.map('TEntry', bordercolor=[('focus', ACCENT)])
    style.configure('TCheckbutton', padding=(0, 4))
    style.map('TCheckbutton', background=[('active', '#eef2ff')])
    style.configure('Treeview', background='white', fieldbackground='white', rowheight=36,
                    borderwidth=0, font=(font, 10))
    style.configure('Treeview.Heading', background='#eef1f7', foreground=INK,
                    font=(font, 10, 'bold'), padding=(10, 10), relief='flat')
    style.map('Treeview', background=[('selected', '#e0e7ff')], foreground=[('selected', '#312e81')])
    style.configure('Vertical.TScrollbar', background='#cbd5e1', troughcolor=BG, borderwidth=0,
                    arrowsize=12)
    root.option_add('*Text.background', 'white')
    root.option_add('*Text.foreground', INK)
    root.option_add('*Text.relief', 'flat')
    root.option_add('*Text.borderWidth', 0)
    root.option_add('*Text.highlightThickness', 1)
    root.option_add('*Text.highlightBackground', LINE)
    root.option_add('*Text.highlightColor', ACCENT)
    root.option_add('*Text.padX', 12)
    root.option_add('*Text.padY', 10)
    root.option_add('*Text.selectBackground', '#e0e7ff')


def page_heading(parent, title, description):
    block = ttk.Frame(parent)
    block.pack(fill='x', padx=8, pady=(6, 18))
    ttk.Label(block, text=title, style='Section.TLabel').pack(anchor='w')
    ttk.Label(block, text=description, style='Muted.TLabel').pack(anchor='w', pady=(5, 0))


def table(parent, columns, height):
    frame = ttk.Frame(parent)
    frame.pack(fill='both', expand=True, padx=8, pady=6)
    tree = ttk.Treeview(frame, columns=columns, show='headings', height=height)
    vertical = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
    horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    tree.grid(row=0, column=0, sticky='nsew')
    vertical.grid(row=0, column=1, sticky='ns')
    horizontal.grid(row=1, column=0, sticky='ew')
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return tree
