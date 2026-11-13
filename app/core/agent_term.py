"""데스크 안 에이전트 터미널 — Claude Code·Codex 를 데스크 창 안의 진짜 터미널(ConPTY)에서 돌린다 (2026-10-24 요청).

초보자가 cmd 창에서 명령어를 외우지 않아도 되게, 터미널 위에 단추(새 대화·모델·멈추기 …)와 입력칸·도움말을 붙인
창(web/agent-term.html)의 뒤쪽이다. 화면은 xterm.js, 여기서는 의사 콘솔(pywinpty)을 연다.

  · 한 창에 여러 에이전트를 띄운다 (2026-10-25 요청, Orca 처럼). 세션마다 이름(`claude-1`, `codex-2` …)이 있고,
    에이전트끼리는 데스크의 중계(core/agent_bridge.py)로 서로의 화면을 읽고 말을 건넨다 — 세션마다 따로 받는 열쇠로.
  · 실행기는 바깥 터미널과 같은 내용이다 (core/agent.py `write_launcher`) — `cmd /k 실행기.cmd`. 세션마다 제 이름의
    실행기를 써서 '다시 시작'이 다른 세션의 설정을 집어 오지 않는다. 에이전트가 살아 있는지는 cmd 아래 자식 프로세스로 본다.
  · 화면은 출력을 길게 기다려(long-poll) 받는다 — `read` 는 새 출력이 오거나 READ_WAIT 가 지나면 돌아온다.
    창을 다시 불러와도 이어 그리게 마지막 BACKLOG 글자를 남겨 둔다 (그보다 앞은 버린다).
  · 창을 닫으면 모든 세션의 프로세스를 통째로 끝낸다. Claude Code 대화는 저장되어 있어 `/resume` 으로 다시 연다.
  · 업데이트·PC 재시작으로 데스크가 꺼져도 다시 켜면 그대로 연다 (2026-10-27 요청, Orca 처럼). 열린 세션(칸)마다 도구·폴더·
    이름·권한·부모와 **대화 id** 를 `sessions.json` 에 적어 두고, 다시 켤 때 그 대화를 이어 연다 (Claude `--resume`,
    Codex `resume <id>`). Claude 는 `--session-id` 로 열고, '새 대화'(/clear)·`/resume` 으로 대화가 바뀌면 SessionStart
    훅이 새 id 를 세션마다의 파일에 적는다 (훅을 못 돌리는 PC 면 처음 id). 사람이 닫은 칸·'모두 끄기'만 목록에서 빠진다 —
    PC 가 꺼지며 프로세스가 먼저 죽어도 칸은 남아 있으니 지우지 않는다.
  · 에이전트가 자식 에이전트를 연다 (2026-10-27 요청) — 중계 `POST /spawn`. 자식은 진짜 새 칸이고 parent 에 부모 이름이 있다.
"""
from __future__ import annotations

import itertools
import json
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path

from core import agent, child

BACKLOG = 2_000_000       # 다시 그릴 때 보낼 출력의 상한 (글자)
READ_WAIT = 0.8           # 새 출력을 기다리는 가장 긴 시간 (초)
WRITE_LIMIT = 200_000     # 한 번에 받을 입력의 상한 (글자) — 긴 붙여넣기도 이 안이다
MESSAGE_LIMIT = 20_000    # 에이전트끼리 한 번에 건넬 말의 상한 (글자)
SESSION_LIMIT = 12        # 한꺼번에 열 수 있는 세션 수
CLOSE_WAIT = 3            # 세션을 끝낼 때 프로세스가 실제로 끝나기를 기다리는 시간 (초)
EVENT_KEEP = 500          # 창에 보일 에이전트 사이 대화 기록 수 — 데스크를 다시 켜도 남는다(events.jsonl)
ENTER_GAP = 0.15          # 말을 넣고 Enter 까지 쉬는 시간 (초) — 한꺼번에 보내면 Enter 까지 붙여넣기로 읽는다
COLS, ROWS = (20, 500), (5, 300)   # 받아 줄 터미널 크기 범위
PASTE_ON, PASTE_OFF = '\x1b[?2004h', '\x1b[?2004l'   # 에이전트가 붙여넣기 모드를 켜고 끄는 신호
ECHO_GAP = 0.5            # 사람이 친 글자·창 크기 바꾸기·포커스 뒤 이만큼(초) 안의 출력은 터미널을 다시 그린 것 — 일로 치지 않는다
ASKING = ('Esc to cancel', 'Enter to select')        # 에이전트가 허용 여부 같은 선택지를 띄워 둔 화면의 꼬리말 — Enter 가 답이 되어 버린다
_ESCAPE = re.compile(r'\x1b\[[0-9;?<=>]*[ -/]*[@-~]|\x1bO.|\x1b.')   # 방향키·붙여넣기 표시 같은 제어 열
# 출력에서 '일'이 아닌 것 — 창 제목(OSC)·커서 이동·색·공백. 이것만 있는 출력은 에이전트가 화면을 손본 것이지 일한 것이 아니다
_NOT_WORK = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?<=>]*[ -/]*[@-~]|\x1bO.|\x1b.|[\x00-\x20\x7f]')
_ids = itertools.count(1)
SAVE_EVERY = 15           # 대화 id 가 바뀌었나 보고 sessions.json 을 고쳐 쓰는 간격 (초) — 갑자기 꺼져도 이만큼만 늦다
# Claude Code SessionStart 훅 — 시작·/clear·/resume 마다 지금 대화 id 를 DESK_SESSION_FILE 에 적는다. 표준 출력은 대화에
# 들어가므로 아무것도 찍지 않는다. bash·cmd·PowerShell 어느 셸로 돌려도 같은 한 줄이 되게 powershell.exe -File 로 부른다.
HOOK_SCRIPT = """try {
    $in = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($env:DESK_SESSION_FILE -and $in.session_id) { [IO.File]::WriteAllText($env:DESK_SESSION_FILE, [string]$in.session_id) }
} catch {}
# 에이전트 기억 (2026-11-11, core/agent_memory.py) — 세션을 열 때마다 그때의 기억·프로필·배운 스킬을 맥락에 넣는다(얼린 사본).
# 표준 출력은 바이트 그대로(UTF-8) — PowerShell 문자열로 거치면 한글이 코드페이지로 깨진다.
try {
    if ($env:DESK_MEMORY_FILE -and (Test-Path -LiteralPath $env:DESK_MEMORY_FILE)) {
        $bytes = [IO.File]::ReadAllBytes($env:DESK_MEMORY_FILE)
        $out = [Console]::OpenStandardOutput(); $out.Write($bytes, 0, $bytes.Length); $out.Flush()
    }
} catch {}
exit 0
"""


# 데스크를 Claude Code 안에서 띄웠으면(에이전트 터미널에서 다시 켜기 등) 그 세션의 표시가 환경에 남아 물려진다 —
# 그러면 새 에이전트는 자기를 그 세션의 자식으로 보고 **대화를 저장하지 않는다** ('Transcript saving is off — inherited
# CLAUDE_CODE_CHILD_SESSION', 2026-10-27 실측) → 다시 켤 때 이어 열 대화가 없다. 칸마다 독립된 세션이니 걷어 낸다.
SESSION_MARKERS = ('CLAUDECODE', 'CLAUDE_CODE_CHILD_SESSION', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_CODE_BRIDGE_SESSION_ID',
                   'CLAUDE_CODE_MESSAGING_SOCKET', 'CLAUDE_CODE_MESSAGING_TOKEN', 'CLAUDE_CODE_ENTRYPOINT',
                   'CLAUDE_CODE_SESSION_ATTENDED', 'CLAUDE_CODE_EXECPATH', 'CLAUDE_PID')


# Claude Code 상태 줄 — 받은 JSON(컨텍스트·비용·사용 한도)을 DESK_STATUS_FILE 에 적어 창의 «현황»이 읽는다(core/agent_usage.py).
# 사용자가 원래 쓰던 상태 줄 명령이 있으면 그것을 그대로 불러 그 줄을 보여 준다(__CHAIN__) — 없거나 빈 줄이면 짧은 줄 하나.
# ⚠️ [Console]::In 은 한글 경로를 깨뜨린다(2026-10-30 실측) — 표준 입력을 바이트로 읽어 UTF-8 로 푼다.
STATUS_SCRIPT = """$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8; $OutputEncoding = $utf8
$buffer = New-Object IO.MemoryStream
[Console]::OpenStandardInput().CopyTo($buffer)
$raw = $utf8.GetString($buffer.ToArray())
try { if ($env:DESK_STATUS_FILE) { [IO.File]::WriteAllText($env:DESK_STATUS_FILE, $raw, $utf8) } } catch {}
$chain = '__CHAIN__'
if ($chain) {
    try { $out = ($raw | & cmd.exe /d /s /c $chain 2>$null | Out-String).TrimEnd(); if ($out) { Write-Output $out; exit 0 } } catch {}
}
try {
    $in = $raw | ConvertFrom-Json
    $line = [string]$in.model.display_name
    if ($in.context_window.used_percentage -ne $null) { $line += ' | ctx ' + [math]::Round($in.context_window.used_percentage) + '%' }
    if ($in.rate_limits.five_hour.used_percentage -ne $null) { $line += ' | 5h ' + [math]::Round($in.rate_limits.five_hour.used_percentage) + '%' }
    Write-Output $line
} catch {}
exit 0
"""


def user_status_line() -> str:
    """사용자 설정(~/.claude/settings.json)의 상태 줄 명령 — 데스크의 상태 줄이 이어 부른다."""
    root = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude')
    try:
        line = json.loads((root / 'settings.json').read_text(encoding='utf-8-sig')).get('statusLine')
    except (OSError, ValueError, AttributeError):
        return ''
    command = line.get('command') if isinstance(line, dict) and line.get('type') == 'command' else ''
    return command if isinstance(command, str) and 'desk-status-line' not in command else ''


def session_env() -> dict:
    return {key: value for key, value in agent.clean_env().items() if key.upper() not in SESSION_MARKERS}


def claude_hooks(work_dir: Path) -> Path:
    """훅 스크립트와 그것을 부르는 설정 파일(`--settings`)을 쓰고 설정 파일 경로를 돌려준다."""
    folder = Path(work_dir) / 'agent'
    folder.mkdir(parents=True, exist_ok=True)
    script, settings = folder / 'session-hook.ps1', folder / 'claude-hooks.json'
    script.write_text(HOOK_SCRIPT, encoding='utf-8-sig')
    status = folder / 'desk-status-line.ps1'
    status.write_text(STATUS_SCRIPT.replace('__CHAIN__', user_status_line().replace("'", "''")), encoding='utf-8-sig')
    run = 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{}"'
    settings.write_text(json.dumps({'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': run.format(script)}]}]},
                                    'statusLine': {'type': 'command', 'command': run.format(status)}},
                                   ensure_ascii=False), encoding='utf-8')
    return settings


def status_file(work_dir: Path, name: str) -> Path:
    return Path(work_dir) / 'agent' / f'status-{name}.json'


class Session:
    def __init__(self, tool: str, folder: str, script: Path, cols: int = 120, rows: int = 32,
                 name: str = '', env: dict | None = None):
        from winpty import PtyProcess
        self.epoch = next(_ids)   # 다시 시작하면 id 는 같고 epoch 만 바뀐다 — 화면이 옛 세션의 cursor 를 들고 오면 처음부터
        self.id = f't{self.epoch}'
        self.tool, self.folder, self.script = tool, folder, script
        self.name = name or self.id                  # 에이전트끼리 부르는 이름 (영문·숫자 — 명령에 치기 쉽게)
        self.title = ''                              # 사용자가 붙인 이름 (비우면 이름을 보인다)
        self.remote_note = ''     # 마지막 이름 바꾸기에서 원격 제어 이름을 못 바꾼 이유 (rename)
        self.skip = False         # 권한 묻지 않기로 열었나 (Manager.open 이 적는다) — 창의 표시용
        self.env = dict(env or {})
        self.size = (_clamp(cols, COLS), _clamp(rows, ROWS))
        self.last_activity = time.monotonic()        # 에이전트가 마지막으로 **일한** 출력의 시각 (_append) — '일하는 중'의 기준
        self._echo_until = 0.0                       # 이 시각까지의 출력은 사람 입력·크기 바꾸기에 대한 다시 그리기
        self.paste_mode = False   # 에이전트가 붙여넣기 모드(bracketed paste)를 켰나
        self.remote = ''          # 원격 제어(휴대폰·웹)에 붙인 세션 이름의 앞부분 — 비우면 연결하지 않은 세션 (Manager.open 이 적는다)
        self.drafting = 0         # 입력칸에 치다 만 글자 수 (가늠) — 0 이 아니면 거기에 명령을 끼워 넣지 않는다
        self.parent = ''          # 이 에이전트를 연 에이전트의 이름 (/spawn) — 사람이 열었으면 ''
        self.resident = False     # 상주 에이전트 (2026-10-30) — '모두 끄기'에도 남고, 꺼지면 데스크가 되살린다. 여럿일 수 있다
        self.main = False         # 메인 상주 에이전트 — 하나. 사용자가 정한 할 일(쪽지 분석 …)을 맡는다 (core/resident_tasks.py)
        self.conversation = ''    # 이어 열 대화 id (Claude: 처음 --session-id, Codex: 찾은 rollout) — Manager 가 적고 고친다
        self.conversation_file = None   # Claude 훅이 지금 대화 id 를 적는 파일
        # 휴대폰 채팅방 id (2026-11-10 요청) — 이 칸의 '대화' 하나. 이름(claude-1)은 닫고 다시 열면 또 쓰이므로 방을 이름으로
        # 가르면 끝난 칸의 대화가 새 칸에 이어 붙는다. 대화가 바뀌면(/clear·/resume·이어 열기 실패) 새 방 — chat_thread.
        self.thread = str(uuid.uuid4())
        self._thread_conversation = ''   # 지금 방이 붙어 있는 대화 id ('' = 아직 모름, Codex 는 열고 나서 찾는다)
        self.started = time.time()
        self.launch = {}          # 다시 열 때 쓸 것 — work_dir · remote · extra · team (Manager.open 이 적는다)
        self._cond = threading.Condition()
        self._chunks: list[str] = []
        self._start = 0           # _chunks 의 첫 글자가 전체 출력에서 몇 번째인가
        self._end = 0             # 지금까지 나온 글자 수
        self._closed = False
        self._input = threading.Lock()   # 사람과 다른 에이전트의 입력이 한 줄 안에서 섞이지 않게
        self._pty = self._spawn(PtyProcess, script, folder)
        self._reader = threading.Thread(target=self._pump, name=f'agent-term-{self.id}', daemon=True)
        self._reader.start()

    def _spawn(self, PtyProcess, script: Path, folder: str):
        """의사 콘솔을 연다 — ConPTY 를 **골라서**, 안 되면 winpty 로.
        🚨 고르지 않고(backend=None) 맡기면, 창 없이 숨겨 띄운 프로세스(Start-Process -WindowStyle Hidden — Intune 포장
        스크립트의 자체 점검)에서 pywinpty 가 'HRESULT 0x80070003 경로를 찾을 수 없음'으로 panic 한다 (2026-10-25 확인).
        panic 은 Exception 이 아니라 BaseException 이라 그대로 두면 프로그램이 죽는다 — 여기서 RuntimeError 로 바꾼다."""
        from winpty import Backend
        failures = []
        for name, backend in (('ConPTY', Backend.ConPTY), ('winpty', Backend.WinPTY)):
            try:
                with child.plain_dll_directory():
                    return PtyProcess.spawn(['cmd.exe', '/k', str(script)], cwd=folder,
                                            env={**session_env(), **self.env},
                                            dimensions=(self.size[1], self.size[0]), backend=backend)
            except BaseException as exc:                     # pyo3 PanicException 도 받는다
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                failures.append(f'{name}: {exc}')
        raise RuntimeError('터미널을 열지 못했습니다 — ' + ' / '.join(failures))

    # ── 출력 ─────────────────────────────────────────────
    def _pump(self):
        while True:
            try:
                data = self._pty.read(65536)
            except Exception:             # EOF·끊긴 소켓 — 프로세스가 끝났다
                break
            if data:
                self._append(data)
            elif not self._pty.isalive():
                break
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _append(self, data: str):
        on, off = data.rfind(PASTE_ON), data.rfind(PASTE_OFF)
        if on != off:
            self.paste_mode = on > off
        now = time.monotonic()
        worked = now >= self._echo_until and bool(_NOT_WORK.sub('', data))
        with self._cond:
            if worked:
                self.last_activity = now
            self._chunks.append(data)
            self._end += len(data)
            size = self._end - self._start
            while size > BACKLOG and len(self._chunks) > 1:
                dropped = self._chunks.pop(0)
                self._start += len(dropped)
                size -= len(dropped)
            self._cond.notify_all()

    def read(self, cursor: int, wait: float = READ_WAIT, epoch=None) -> dict:
        """cursor 뒤에 나온 출력. 버린 데까지 밀렸거나 다른 세션(epoch)의 cursor 면 남은 처음부터 주고 reset 을 켠다."""
        if epoch is not None and epoch != self.epoch:
            cursor, wait = -1, 0
        with self._cond:
            if cursor >= self._end and not self._closed and wait > 0:
                self._cond.wait(timeout=max(0.0, min(wait, READ_WAIT)))
            reset = cursor < self._start or cursor > self._end
            begin = self._start if reset else cursor
            text, at = [], self._start
            for chunk in self._chunks:
                if at + len(chunk) > begin:
                    text.append(chunk[max(0, begin - at):])
                at += len(chunk)
            return {'data': ''.join(text), 'cursor': self._end, 'reset': reset, 'closed': self._closed, 'epoch': self.epoch}

    def quiet_for(self) -> float:
        """에이전트가 마지막으로 일한 출력에서 몇 초 지났나 — 일을 마치고 기다리는지 가늠한다 (2026-10-26 요청).
        모든 출력을 세면 쉬는 중에도 '일하는 중'으로 보였다 — 사람이 친 글자의 메아리, 창 크기·포커스가 바뀔 때 에이전트가
        화면을 다시 그리는 것, 커서·창 제목만 바꾸는 제어 문자. 그래서 제어 문자를 걷어 내고도 글자가 남고, 사람 입력·크기
        바꾸기 직후(ECHO_GAP)가 아닌 출력만 일로 친다. Enter 뒤의 출력은 에이전트의 대답이라 센다."""
        return time.monotonic() - self.last_activity

    # ── 입력 · 크기 ──────────────────────────────────────
    def write(self, data: str):
        if not isinstance(data, str) or len(data) > WRITE_LIMIT:
            raise ValueError('입력 형식이 올바르지 않습니다.')
        if self._closed:
            raise RuntimeError('터미널이 이미 끝났습니다. ‘다시 시작’을 눌러 주세요.')
        with self._input:
            self._pty.write(data)
            self._track_draft(data)
            if '\r' not in data and '\n' not in data:      # 글자·방향키·포커스 신호 — 곧 오는 출력은 메아리다
                self._echo_until = time.monotonic() + ECHO_GAP

    def _track_draft(self, data: str):
        """사람이 친 글자를 따라가 입력칸에 쓰다 만 것이 있는지 가늠한다. 모르겠으면 있다고 본다 (지우기는 한 글자씩만 센다)."""
        for ch in _ESCAPE.sub('', data):
            if ch in '\r\n\x03\x15':                 # Enter · Ctrl+C · Ctrl+U — 입력칸이 비었다
                self.drafting = 0
            elif ch in '\x7f\b':
                self.drafting = max(0, self.drafting - 1)
            elif ch >= ' ':
                self.drafting += 1

    def submit(self, text: str):
        """말 한 덩이를 넣고 Enter — 여러 줄이면 붙여넣기로 감싸 줄마다 보내지 않게 한다."""
        if self._closed:
            raise RuntimeError('이 에이전트의 터미널은 이미 끝났습니다.')
        body = text.replace('\r\n', '\n').replace('\n', '\r')
        with self._input:
            self._pty.write(f'\x1b[200~{body}\x1b[201~' if self.paste_mode else body)
            time.sleep(ENTER_GAP)
            self._pty.write('\r')
            self.drafting = 0

    def rename_remote(self, title: str) -> str:
        """휴대폰·웹 세션 목록의 이름을 `<앞부분> · <title>` 로 맞춘다 (`/rename`을 입력해 보낸다) — 2026-10-26 요청.
        돌려주는 것: '' 이면 보냈거나 보낼 일이 없는 세션, 아니면 **보내지 않은 이유** (화면에 보인다).
        입력칸에 치던 글자가 있거나 선택지를 띄워 둔 중이면 보내지 않는다 — Enter 가 엉뚱한 답이 된다.
        일하는 중에는 보낸다 — Claude Code 는 일하는 동안 넣은 `/rename` 도 받는다 (원격 제어는 Claude Code 에만 붙는다)."""
        if not self.remote or self._closed or not self.agent_running():
            return ''
        if self.drafting:
            return '입력하던 내용이 있어 원격 제어 이름은 그대로 뒀어요.'
        if self.asking():
            return '선택지를 기다리는 중이라 원격 제어 이름은 그대로 뒀어요.'
        name = ''.join(ch for ch in (title or self.name) if ch >= ' ' and ch != '\x7f').strip() or self.name
        self.submit(f'/rename {self.remote} · {name}')
        return ''

    def asking(self, span: int = 2000) -> bool:
        """출력 끝부분에 선택지 꼬리말(ASKING)이 보이나 — 창이 없어 화면 글로 볼 수 없을 때의 어림 (예약 업무·원격 이름)."""
        with self._cond:
            tail = ''.join(self._chunks[-16:])[-span:]
        return any(mark in tail for mark in ASKING)

    def resize(self, cols: int, rows: int):
        self.size = (_clamp(cols, COLS), _clamp(rows, ROWS))
        self._echo_until = time.monotonic() + ECHO_GAP              # 에이전트가 새 크기로 화면을 다시 그린다
        if not self._closed:
            self._pty.setwinsize(self.size[1], self.size[0])

    # ── 상태 · 끝내기 ────────────────────────────────────
    @property
    def closed(self) -> bool:
        return self._closed

    def agent_running(self) -> bool:
        """cmd 아래에 에이전트(자식 프로세스)가 아직 있나. 에이전트를 끝내면 cmd 만 남는다."""
        if self._closed:
            return False
        try:
            import psutil
            return bool(psutil.Process(self._pty.pid).children())
        except Exception:
            return True                     # 모르면 살아 있다고 본다 — '다시 시작' 안내를 함부로 띄우지 않게

    def close(self):
        """세션의 프로세스를 통째로 끝낸다 (cmd 와 그 아래 에이전트·node 까지)."""
        try:
            import psutil
            root = psutil.Process(self._pty.pid)
            family = root.children(recursive=True) + [root]
            for proc in family:
                try:
                    proc.kill()
                except psutil.Error:
                    pass
            psutil.wait_procs(family, timeout=CLOSE_WAIT)    # 폴더·실행기를 붙든 채 남지 않게 실제로 끝날 때까지
        except Exception:
            pass
        try:
            self._pty.terminate(force=True)
        except Exception:
            pass
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def info(self) -> dict:
        return {'id': self.id, 'tool': self.tool, 'label': agent.TOOLS[self.tool]['label'], 'folder': self.folder,
                'name': Path(self.folder).name or self.folder, 'agent': self.name, 'title': self.title or self.name,
                'closed': self._closed, 'skip': self.skip, 'team': 'DESK_AGENT_TOKEN' in self.env, 'parent': self.parent,
                'resident': self.resident, 'main': self.main}

    def current_conversation(self, taken=()) -> str:
        """지금 이어 열 대화 id. Claude 는 훅이 적은 것, Codex 는 이 폴더에서 연 뒤 쓴 rollout (다른 세션 것은 빼고)."""
        if self.tool == 'claude' and self.conversation_file:
            try:
                written = Path(self.conversation_file).read_text(encoding='utf-8').strip()
                if re.fullmatch(r'[0-9a-fA-F-]{36}', written):
                    self.conversation = written
            except OSError:
                pass
        elif self.tool == 'codex' and not self._closed:
            found = agent.codex_thread(self.folder, self.started, exclude=taken)
            if found:
                self.conversation = found
        return self.conversation

    def chat_thread(self) -> str:
        """휴대폰 채팅방 id. 대화 id 가 다른 대화로 바뀌면 새 방을 연다 — 에이전트가 앞 내용을 잊었으니 방도 나눈다.
        모르던 대화 id 를 처음 알게 된 것(Codex 가 연 뒤 rollout 을 찾음)은 같은 방이다.
        Claude 는 훅이 적은 파일을 읽고(가볍다), Codex 는 저장할 때 찾아 둔 값을 쓴다(폴더를 훑으므로 매번 하지 않는다)."""
        if self.tool == 'claude':
            self.current_conversation()
        return self._sync_thread()

    def _sync_thread(self) -> str:
        conversation = self.conversation
        if conversation and conversation != self._thread_conversation:
            if self._thread_conversation:
                self.thread = str(uuid.uuid4())
            self._thread_conversation = conversation
        return self.thread

    def keep_thread(self, thread: str, conversation: str):
        """다시 켤 때 — 저장해 둔 방을 이어 쓴다. 저장할 때의 대화를 그대로 이어 열었을 때만(이어 열기에 실패해 새 대화면 새 방)."""
        self._thread_conversation = self.conversation
        if (isinstance(thread, str) and re.fullmatch(r'[0-9a-f-]{36}', thread)
                and conversation and conversation == self.conversation):
            self.thread = thread

    def snapshot(self) -> dict:
        return {'tool': self.tool, 'folder': self.folder, 'skip': self.skip, 'name': self.name, 'title': self.title,
                'parent': self.parent, 'conversation': self.conversation, 'thread': self._sync_thread(),
                'remote': self.launch.get('remote', ''),
                'extra': list(self.launch.get('extra', ())), 'team': 'DESK_AGENT_TOKEN' in self.env, 'resident': self.resident,
                'main': self.main, 'knowledge': list(self.launch.get('knowledge', {}).get('folders', ()))}


def _clamp(value, bounds) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = bounds[0]
    return max(bounds[0], min(bounds[1], number))


def selftest(folder: Path) -> bool:
    """의사 콘솔을 실제로 열어 한 줄을 받아 본다 — 실행 파일에 pywinpty 의 DLL·exe 가 묶였는지 (packaging_check)."""
    script = Path(folder) / 'selftest.cmd'
    script.write_text('@echo off\r\necho AGENT-TERM-OK\r\nexit\r\n', encoding='ascii')
    session = Session('claude', str(folder), script, 80, 10)
    try:
        cursor, seen, deadline = 0, '', time.monotonic() + 10
        while 'AGENT-TERM-OK' not in seen and time.monotonic() < deadline:
            result = session.read(cursor, 0.5)
            cursor, seen = result['cursor'], seen + result['data']
        return 'AGENT-TERM-OK' in seen
    finally:
        session.close()


class Manager:
    """열린 세션들 (id → Session) 과 에이전트 사이 대화 기록. 데스크 API 가 하나 들고 있다.

    team 을 주면(에이전트끼리 보기) 세션마다 중계 주소·열쇠·이름을 환경 값으로 넣고, 에이전트에게 쓰는 법을 알린다
    (team 은 `env(name, token) -> dict`, `args(tool) -> tuple` 을 가진 것 — core/agent_bridge.py `Bridge`)."""

    def __init__(self, store: Path | None = None):
        """store — 열린 세션 목록을 적어 둘 파일 (sessions.json). 없으면 적지 않는다 (시험)."""
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}
        self._tokens: dict[str, str] = {}            # 열쇠 → 세션 id
        self._starting: set[str] = set()             # 이름을 골랐지만 아직 뜨는 중인 세션
        self._events: list[dict] = []
        self._event_seq = 0
        self._event_cond = threading.Condition(self._lock)
        self.store = Path(store) if store else None
        # 에이전트 대화 기록 — 창을 닫거나 데스크를 다시 켜도 쌓여 있게(2026-10-30 요청). 세션 목록 옆 events.jsonl
        self.event_path = self.store.with_name('events.jsonl') if self.store else None
        self._load_events()
        self.window_open = False                     # 데스크가 적는다 — 다시 켤 때 창까지 띄울지
        self._frozen = False                         # 데스크를 끝내는 중 — 마지막 목록을 그대로 둔다
        self._saved = None
        self._save_lock = threading.Lock()
        self._saver = None
        # 에이전트 기억 (2026-11-11) — 데스크가 붙인다. memory 는 `memory_env(token) -> dict` 를 가진 것(Bridge):
        # 모든 칸이 기억 열쇠를 받는다(서로 보기를 꺼도). on_save(rows) — 목록을 쓸 때마다 대화 id 를 기억 저장소에 적는다.
        self.memory = None
        self.on_save = None

    def open(self, tool: str, folder: str, skip: bool, work_dir: Path, remote: str = '', extra: tuple = (),
             cols: int = 120, rows: int = 32, team=None, name: str = '', title: str = '', parent: str = '',
             resume: str = '', knowledge: dict | None = None, cron=None, thread: str = '') -> Session:
        """새 칸. name·title·parent·resume 는 다시 켤 때(restore)와 자식 에이전트(/spawn)가 쓴다 — resume 은 이어 열 대화 id.
        thread — 다시 켤 때 저장해 둔 휴대폰 채팅방 id. resume 대화를 그대로 이어 열었을 때만 이어 쓴다(keep_thread).
        cron — 서로 보기(team)를 끈 칸에도 예약 업무만 쓸 열쇠를 준다 (중계 Bridge, 2026-11-08: 끈 상태에서 «예약 만들어 줘»가
        Claude Code 자체 CronCreate 로 가서 데스크 예약 목록에 안 보였다). Claude Code 칸만."""
        with self._lock:
            alive = [s for s in self._sessions.values() if not s.closed]
            if len(alive) >= SESSION_LIMIT:
                raise RuntimeError(f'에이전트는 {SESSION_LIMIT}개까지 함께 띄울 수 있습니다. 안 쓰는 에이전트를 닫아 주세요.')
            # 비어 있는 가장 작은 번호 — 모두 닫고 다시 열면 claude-1 부터 (2026-10-25: 닫았는데 claude-2 라 남은 줄 알았다)
            taken = {n.lower() for s in self._sessions.values() for n in (s.name, s.title)} | self._starting   # 붙인 이름과도 겹치지 않게
            if not (re.fullmatch(r'[A-Za-z0-9_-]{1,30}', name or '') and name.lower() not in taken):
                name = next(f'{tool}-{n}' for n in itertools.count(1) if f'{tool}-{n}' not in taken)
            self._starting.add(name)
        try:
            token = secrets.token_urlsafe(24)
            if team:
                env, team_args = team.env(name, token), team.args(tool)
            elif cron is not None and tool == 'claude':
                env, team_args = cron.cron_env(name, token), cron.cron_args(tool)
            else:
                env, team_args = {}, ()
            if self.memory is not None:
                env.update(self.memory.memory_env(token))
            launch = {'work_dir': Path(work_dir), 'remote': remote, 'extra': tuple(extra),
                      'team_args': team_args, 'memory': self.memory is not None,
                      # 작업 폴더 (2026-10-30) — {'folders': [...], 'index': 지식 목록 파일} (core/knowledge.py)
                      'knowledge': knowledge if knowledge and knowledge.get('folders') else {}}
            if launch['knowledge'].get('index'):
                env['DESK_KNOWLEDGE'] = launch['knowledge']['index']
            session_file = Path(work_dir) / 'agent' / f'conversation-{name}.txt'
            script, _remote, conversation = self._script(tool, folder, skip, name, launch, resume, session_file)
            if tool == 'claude':
                env['DESK_SESSION_FILE'] = str(session_file)
                env['DESK_STATUS_FILE'] = str(status_file(work_dir, name))
            session = Session(tool, folder, script, cols, rows, name=name, env=env)
            session.skip, session.parent, session.launch = skip, parent, launch
            session.title = title if isinstance(title, str) and len(title.strip()) <= 30 else ''
            session.conversation = conversation
            session.keep_thread(thread, resume)
            session.conversation_file = session_file if tool == 'claude' else None
            session.remote = remote if _remote else ''       # 실제로 붙인 세션만 (옛 판·한글 안 되는 PC 는 안 붙는다)
            with self._lock:
                self._sessions[session.id] = session
                if team or 'DESK_CRON_TOKEN' in env or 'DESK_MEMORY_TOKEN' in env:
                    self._tokens[token] = session.id
        finally:
            with self._lock:
                self._starting.discard(name)
        self.save()
        return session

    @staticmethod
    def _script(tool: str, folder: str, skip: bool, name: str, launch: dict, resume: str, session_file: Path):
        """실행기를 쓴다 → (경로, 붙인 원격 제어 이름, 이 실행기가 열 대화 id).
        Claude 는 대화 id 를 정해 연다(--session-id) — 이어 열 대화가 있으면 --resume. 대화 파일이 없으면(첫 메시지 전) 새로.
        Codex 는 `resume <id>` 를 앞에 둔다 (id 는 열고 나서 rollout 에서 찾는다)."""
        work_dir, head, first, conversation = launch['work_dir'], (), (), ''
        if tool == 'claude':
            if resume and agent.claude_transcript(resume):
                conversation, first = resume, ('--resume', resume)
            else:
                conversation = str(uuid.uuid4())
                first = ('--session-id', conversation)
            first += ('--settings', f'"{claude_hooks(work_dir)}"')
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.write_text(conversation, encoding='utf-8')     # 같은 이름의 옛 세션이 적은 id 를 집어 오지 않게
        elif tool == 'codex' and resume and re.fullmatch(r'[0-9a-fA-F-]{36}', resume):
            conversation, head = resume, ('resume', resume)
        remote = launch['remote']
        # 휴대폰·웹의 세션 목록에서 "자동화 업무 · claude-1" 처럼 어느 에이전트인지 구분되게 (2026-10-26 요청)
        script, attached = agent.write_launcher(tool, folder, skip, work_dir, f'{remote} · {name}' if remote else '',
                                                first + launch['extra'] + tuple(launch['team_args'])
                                                + Manager._knowledge_args(tool, launch),
                                                script_name=f'term-{name}.cmd', head=head)
        return script, attached, conversation

    # ── 다시 켤 때를 위한 목록 (sessions.json) ──────────────
    def snapshot(self) -> dict:
        with self._lock:
            sessions = list(self._sessions.values())
        rows, taken = [], set()
        for session in sessions:
            taken.add(session.current_conversation(taken))
            rows.append(session.snapshot())
        return {'version': 1, 'window': self.window_open, 'sessions': rows}

    def save(self):
        """목록을 고쳐 쓴다 (바뀐 때만). 끝내는 중(freeze 뒤)에는 쓰지 않는다 — 프로세스를 끄며 빈 목록을 적지 않게."""
        if self.store is None or self._frozen:
            return
        with self._save_lock:
            try:
                data = self.snapshot()
                if data == self._saved or self._frozen:
                    return
                self.store.parent.mkdir(parents=True, exist_ok=True)
                temp = self.store.with_suffix('.tmp')
                temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
                os.replace(temp, self.store)
                self._saved = data
                if self.on_save is not None:
                    self.on_save(data['sessions'])
            except Exception:
                pass                                  # 목록을 못 써도 터미널은 그대로 쓴다
        self._watch()

    def _watch(self):
        """대화 id 는 데스크 모르게 바뀐다(/clear) — 세션이 있는 동안 SAVE_EVERY 마다 다시 본다."""
        with self._lock:
            if self._saver is not None or not self._sessions or self._frozen:
                return

            def loop():
                while not self._frozen:
                    time.sleep(SAVE_EVERY)
                    with self._lock:
                        if not self._sessions:
                            self._saver = None
                            break
                    self.save()
            self._saver = threading.Thread(target=loop, name='agent-term-save', daemon=True)
            self._saver.start()

    def freeze(self):
        """데스크를 끝낸다 — 마지막으로 한 번 적고, 그 뒤로는 적지 않는다 (다시 켜면 이 목록대로 연다)."""
        self.save()
        self._frozen = True

    def saved(self) -> dict:
        """적어 둔 목록 (없거나 깨졌으면 빈 목록)."""
        try:
            data = json.loads(self.store.read_text(encoding='utf-8')) if self.store else {}
        except (OSError, ValueError):
            data = {}
        rows = data.get('sessions') if isinstance(data, dict) else None
        return {'window': bool(data.get('window')) if isinstance(data, dict) else False,
                'sessions': [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []}

    def get(self, session_id) -> Session:
        with self._lock:
            session = self._sessions.get(session_id) if isinstance(session_id, str) else None
        if session is None:
            raise ValueError('터미널 세션을 찾을 수 없습니다. 창을 닫고 다시 열어 주세요.')
        return session

    def sessions(self) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def by_token(self, token) -> Session | None:
        with self._lock:
            session_id = self._tokens.get(token) if isinstance(token, str) else None
            return self._sessions.get(session_id) if session_id else None

    def by_name(self, name) -> Session | None:
        """에이전트 이름이나 사용자가 붙인 이름으로 (대소문자 무시)."""
        if not isinstance(name, str) or not name.strip():
            return None
        wanted = name.strip().lower()
        with self._lock:
            for session in self._sessions.values():
                if wanted in (session.name.lower(), session.title.lower()):
                    return session
        return None

    def rename(self, session_id, title) -> Session:
        session = self.get(session_id)
        if not isinstance(title, str) or len(title.strip()) > 30:
            raise ValueError('이름은 30자까지입니다.')
        title = title.strip()
        other = self.by_name(title) if title else None
        if other is not None and other is not session:
            raise ValueError('같은 이름의 에이전트가 이미 있습니다.')
        session.title = title
        try:
            session.remote_note = session.rename_remote(title)    # 휴대폰·웹 쪽 이름도 — 보내지 못했으면 이유
        except Exception:                                         # 이름 바꾸기 자체는 이미 됐다
            session.remote_note = '원격 제어 이름은 바꾸지 못했어요.'
        self.save()
        return session

    def restart(self, session_id) -> Session:
        """같은 폴더·같은 이름·같은 열쇠로 새로 연다 (id 도 그대로 — 창은 이어서 쓴다). 하던 대화를 이어 연다."""
        old = self.get(session_id)
        conversation = old.current_conversation()
        old.close()
        script = old.script
        if old.launch:                    # 실행기를 다시 쓴다 — Claude 는 같은 --session-id 로 두 번 열 수 없다
            script, _remote, conversation = self._script(old.tool, old.folder, old.skip, old.name, old.launch,
                                                         conversation, old.conversation_file or Path(old.script).with_suffix('.txt'))
        fresh = Session(old.tool, old.folder, script, *old.size, name=old.name, env=old.env)
        fresh.id = old.id                 # epoch 는 새것 — 화면이 이것을 보고 처음부터 다시 그린다
        fresh.skip, fresh.title, fresh.remote, fresh.parent = old.skip, old.title, old.remote, old.parent
        fresh.resident, fresh.main = old.resident, old.main
        fresh.launch, fresh.conversation, fresh.conversation_file = old.launch, conversation, old.conversation_file
        fresh.thread, fresh._thread_conversation = old._sync_thread(), old._thread_conversation   # 같은 대화면 같은 방
        with self._lock:
            self._sessions[old.id] = fresh
        self.save()
        return fresh

    def close(self, session_id):
        with self._lock:
            session = self._sessions.pop(session_id, None)
            self._tokens = {token: sid for token, sid in self._tokens.items() if sid != session_id}
        if session:
            session.close()
            self.save()

    def alive(self) -> list[Session]:
        """아직 끝나지 않은 세션 — 창을 닫을 때 끌지 물을 것들."""
        with self._lock:
            return [session for session in self._sessions.values() if not session.closed]

    def close_all(self, keep_resident: bool = False):
        """모두 끝낸다. 사람이 '모두 끄기'를 골랐으면 목록도 비운다 — 데스크를 끝내는 중(freeze 뒤)이면 목록은 그대로.
        keep_resident — 사람이 고른 '모두 끄기'에서는 상주 에이전트를 남긴다(2026-10-30 요청). 데스크를 끝낼 때는 모두."""
        with self._lock:
            if keep_resident:
                sessions = [s for s in self._sessions.values() if not s.resident]
                self._sessions = {sid: s for sid, s in self._sessions.items() if s.resident}
                kept = set(self._sessions)
                self._tokens = {token: sid for token, sid in self._tokens.items() if sid in kept}
            else:
                sessions, self._sessions, self._tokens = list(self._sessions.values()), {}, {}
        for session in sessions:
            session.close()
        self.save()

    def resident(self) -> Session | None:
        with self._lock:
            return next((s for s in self._sessions.values() if s.resident), None)

    def residents(self) -> list[Session]:
        with self._lock:
            return [s for s in self._sessions.values() if s.resident]

    def main(self) -> Session | None:
        with self._lock:
            return next((s for s in self._sessions.values() if s.main), None)

    def set_resident(self, session_id, on: bool) -> Session:
        """상주로 · 풀기 (여럿 상주할 수 있다). 풀면 메인도 풀린다."""
        session = self.get(session_id)
        with self._lock:
            session.resident = bool(on)
            if not on:
                session.main = False
        self.save()
        return session

    def set_main(self, session_id, on: bool) -> Session:
        """메인 상주로(하나 — 다른 메인은 보통 상주로 남는다) · 풀기. 메인이면 상주이기도 하다."""
        session = self.get(session_id)
        with self._lock:
            if on:
                for other in self._sessions.values():
                    other.main = False
                session.resident = True
            session.main = bool(on)
        self.save()
        return session

    @staticmethod
    def _knowledge_args(tool: str, launch: dict) -> tuple:
        from core import knowledge as knowledge_mod
        folders = launch.get('knowledge', {}).get('folders') or []
        args = knowledge_mod.launch_args(tool, folders)
        if tool == 'codex' and not launch.get('team_args') and (args or launch.get('memory')):
            # Codex 는 지시를 developer_instructions 로 받는다(하나만 — 겹쳐 주면 마지막 것만 남는다).
            # 서로 보기를 켰으면 중계 안내(CODEX_NOTE)에 이미 들어 있다
            from core import agent_memory
            note = agent_memory.CODEX_NOTE if launch.get('memory') else ''
            if args:
                note += ('Knowledge folders: read the file named in env DESK_KNOWLEDGE before work related to the added folders, '
                         'and append durable learnings to the listed knowledge files. Never write personal data or secrets there.')
            args += ('-c', f'"developer_instructions=\'{note}\'"')
        return args

    def children(self, parent: Session) -> list[Session]:
        with self._lock:
            return [s for s in self._sessions.values() if s.parent and s.parent == parent.name and s is not parent]

    def depth(self, session: Session) -> int:
        """부모를 따라 올라간 수 (사람이 연 것은 0)."""
        seen, level = {session.name}, 0
        while session.parent and level < 10:
            session = self.by_name(session.parent)
            if session is None or session.name in seen:
                break
            seen.add(session.name)
            level += 1
        return level

    # ── 에이전트 사이 대화 기록 ─────────────────────────
    def note(self, kind: str, source: Session | None, target: Session | None, text: str = '', to_name: str = '',
             from_name: str = '', data: dict | None = None) -> dict:
        """창의 '에이전트 대화'에 보일 일 하나 (kind: send · read · wait · computer — computer 는 to_name 에 앱 이름,
        peer-out · peer-in — 다른 PC 와 오간 메시지, 상대는 to_name · from_name 에. data — 창이 쓸 덧붙임, analysis 의 {key, handoff})."""
        with self._event_cond:
            self._event_seq += 1
            event = {'id': self._event_seq, 'time': time.strftime('%H:%M:%S'), 'kind': kind,
                     'from': source.id if source else '',
                     'fromName': (source.title or source.name) if source else (from_name or '사람'),
                     'to': target.id if target else '', 'toName': (target.title or target.name) if target else to_name,
                     'text': text[:2000]}
            event['day'] = time.strftime('%Y-%m-%d')
            if data:
                event['data'] = data
            self._events.append(event)
            del self._events[:-EVENT_KEEP]
            self._keep_event(event)
            self._event_cond.notify_all()
            return event

    def _load_events(self):
        if not self.event_path:
            return
        try:
            lines = self.event_path.read_text(encoding='utf-8').splitlines()[-EVENT_KEEP:]
        except OSError:
            return
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and isinstance(event.get('id'), int):
                self._events.append(event)
        self._event_seq = max((event['id'] for event in self._events), default=0)

    def _keep_event(self, event: dict):
        """한 줄 덧붙이고, 두 배로 불면 최근 EVENT_KEEP 개만 다시 쓴다. 잠금(_event_cond) 안에서 부른다."""
        if not self.event_path:
            return
        try:
            self.event_path.parent.mkdir(parents=True, exist_ok=True)
            with self.event_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
            if self.event_path.stat().st_size > EVENT_KEEP * 2 * 400:
                self.event_path.write_text(''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in self._events),
                                           encoding='utf-8')
        except OSError:
            pass

    def clear_events(self):
        """«비우기» — 창의 목록과 쌓아 둔 기록을 함께 지운다. 번호는 이어 간다(열린 창이 놓치지 않게)."""
        with self._event_cond:
            self._events.clear()
            if self.event_path:
                try:
                    self.event_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def events(self, after: int = 0, wait: float = 0) -> dict:
        with self._event_cond:
            if wait > 0 and self._event_seq <= after:
                self._event_cond.wait(timeout=min(wait, READ_WAIT * 5))
            return {'events': [event for event in self._events if event['id'] > after], 'last': self._event_seq}
