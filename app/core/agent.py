"""에이전트 터미널 — 고른 폴더에서 Claude Code·Codex 를 새 터미널 창으로 연다 (2026-10-13 요청).

  · 터미널은 Windows Terminal(wt.exe)이 있으면 그것, 없으면 보통 명령 창(cmd).
  · 에이전트는 cmd 안에서 돈다 (`cmd /k 실행기.cmd`). 에이전트를 끝내도 창이 남아 그 폴더에서 이어 쓴다.
    PowerShell 로 돌리면 npm 이 깐 `claude.ps1` 이 실행 정책에 막힐 수 있다 — cmd 는 `.cmd` 를 바로 쓴다.
  · 실행기(`<자료 폴더>/agent/<도구>.cmd`)에는 에이전트의 **전체 경로**를 적는다. 설치 직후라 새 터미널의
    PATH 가 아직 옛것이어도 찾는다.
  · '권한 묻지 않기'는 도구마다 플래그가 다르다 (FLAGS).
  · 설치되어 있지 않으면 설치 창을 띄운다 — Claude Code 는 Anthropic 공식 설치 스크립트(관리자 권한 없음),
    Codex 는 winget(없으면 npm). 설치가 끝나면 `find` 가 새 자리에서 찾는다.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from core import child

TOOLS = {
    'claude': {'label': 'Claude Code', 'skip': '--dangerously-skip-permissions'},
    'codex': {'label': 'Codex', 'skip': '--dangerously-bypass-approvals-and-sandbox'},
}
CLAUDE_INSTALL = 'https://claude.ai/install.ps1'
LAUNCHER_TRIES = 15        # 실행기 쓰기를 다시 해 볼 횟수 (0.2초 간격)


def _registry_path() -> list[str]:
    """레지스트리에 적힌 PATH (사용자·컴퓨터) — 이 프로그램이 뜬 뒤에 설치한 것도 보인다."""
    found = []
    try:
        import winreg
        for root, key in ((winreg.HKEY_CURRENT_USER, 'Environment'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')):
            try:
                with winreg.OpenKey(root, key) as opened:
                    found += os.path.expandvars(winreg.QueryValueEx(opened, 'Path')[0]).split(';')
            except OSError:
                continue
    except ImportError:
        pass
    return found


def search_path() -> str:
    home, appdata, local = Path.home(), os.environ.get('APPDATA', ''), os.environ.get('LOCALAPPDATA', '')
    known = [str(home / '.local' / 'bin')]
    first = []
    if appdata:
        known.append(str(Path(appdata) / 'npm'))
    if local:
        known.append(str(Path(local) / 'Microsoft' / 'WinGet' / 'Links'))
        # 데스크가 깐 Node.js 를 맨 앞에 — 컴퓨터 전체 PATH 의 옛 Node 는 한글 폴더에서 죽을 수 있어 그것 때문에 깐 것이다
        # (core/automation.py `node_reads_korean`). Windows 는 컴퓨터 PATH 를 사용자 PATH 앞에 두므로 여기서 앞세운다.
        mine = Path(local) / 'Programs' / 'nodejs'
        if (mine / 'node.exe').is_file():
            first.append(str(mine))
    parts = first + os.environ.get('PATH', '').split(';') + _registry_path() + known
    out, seen = [], set()
    for part in parts:
        part = part.strip().strip('"')
        if part and part.lower() not in seen:
            seen.add(part.lower())
            out.append(part)
    # WindowsApps 는 맨 뒤로 — 그 python.exe 는 Store 로 보내는 자리표시자일 수 있어, 데스크가 뜬 뒤 깐 Python(레지스트리 PATH)을
    # 가린다. 에이전트 터미널의 `python` 도 같은 PATH 를 쓴다.
    store = [p for p in out if p.lower().rstrip('\\').endswith('microsoft\\windowsapps')]
    return ';'.join([p for p in out if p not in store] + store)


# winget 의 Codex(OpenAI.Codex)는 압축을 푸는 portable 패키지다. 실행 파일 이름은
# `codex-x86_64-pc-windows-msvc.exe` 이고, `codex` 라는 이름은 winget 이 Links 폴더에 만드는 링크뿐이다.
# 링크를 만들 권한이 없는 PC(학교 PC 등)에서는 링크 대신 패키지 폴더를 PATH 에 넣어 `codex` 가 없고,
# 관리자로 깔았으면 링크가 Program Files 쪽에 생긴다 — winget 은 '이미 설치됨'인데 찾지 못했다 (2026-10-19 보고).
WINGET_CODEX = (('Links', 'codex.exe'), ('Packages', 'OpenAI.Codex_*', 'codex-*-pc-windows-msvc.exe'))


def winget_roots() -> list[Path]:
    roots = []
    if os.environ.get('LOCALAPPDATA'):
        roots.append(Path(os.environ['LOCALAPPDATA']) / 'Microsoft' / 'WinGet')      # 사용자 설치
    for name in ('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)'):
        root = Path(os.environ[name]) / 'WinGet' if os.environ.get(name) else None
        if root and root not in roots:
            roots.append(root)                                                         # 관리자(컴퓨터) 설치
    return roots


def _winget_codex() -> str | None:
    for root in winget_roots():
        for parts in WINGET_CODEX:
            for path in sorted(root.glob('/'.join(parts)), reverse=True):
                if path.is_file():
                    return str(path)
    return None


def find(tool: str) -> str | None:
    """설치된 에이전트의 전체 경로. 없으면 None."""
    if tool not in TOOLS:
        raise ValueError('지원하지 않는 에이전트입니다.')
    found = shutil.which(tool, path=search_path())
    if not found and tool == 'codex':
        found = _winget_codex()
    return found


def tools() -> dict:
    return {name: {'label': info['label'], 'installed': bool(path := find(name)), 'path': path or '',
                   'skip_flag': info['skip']} for name, info in TOOLS.items()}


# ── 실행기 · 설치 스크립트 ─────────────────────────────────────
# winget 판 Codex 0.157~0.161 은 켜자마자 백그라운드 서버(app-server daemon)를 준비하다가
# "the CLI package does not match this platform or executable" 로 멈춘다 (openai/codex #48366 · #51721,
# 2026-10-19 학교 PC 보고). 0.163.0 에서 고쳐졌지만 winget 카탈로그는 아직 0.161.0 이다 — 그 판들만
# 이슈의 우회법대로 서버 없이(--no-daemon) 연다.
CODEX_DAEMON_FIXED = (0, 163, 0)


def codex_needs_no_daemon(exe: str) -> bool:
    """winget 판(패키지 폴더에 codex-package.json, 실행 파일 이름이 entrypoint)이고 고쳐지기 전 판인가."""
    import json
    import re
    try:
        real = Path(os.path.realpath(exe))                   # Links\codex.exe 링크면 패키지의 실제 파일
        metadata = json.loads((real.parent / 'codex-package.json').read_text(encoding='utf-8'))
        if metadata.get('layoutVersion') != 1 or metadata.get('entrypoint', '').lower() != real.name.lower():
            return False
        version = tuple(int(part) for part in re.findall(r'\d+', str(metadata.get('version', '')))[:3])
        return len(version) == 3 and version < CODEX_DAEMON_FIXED
    except (OSError, ValueError, AttributeError):
        return False


def _cmd_text(text: str) -> str:
    """cmd 줄에 따옴표로 넣을 이름 — cmd 가 해석하는 글자와 제어 문자는 뺀다."""
    return ''.join(ch for ch in text if ch not in '"%^&|<>!' and ch >= ' ')[:40].strip()


def launcher_text(exe: str, skip: bool, tool: str, remote: str = '', extra: tuple = (), head: tuple = ()) -> str:
    """cmd 실행기 내용. 경로의 % 는 cmd 가 변수로 읽지 않게 겹친다.

    remote — Claude Code 원격 제어(휴대폰·웹에서 이 세션 이어 쓰기) 세션 이름. 비우면 켜지 않는다 (2026-10-22 요청).
    extra  — 그 밖에 붙일 인자 (자동화 업무 폴더의 Codex 가 샌드박스 없이 열리는 것 등).
    head   — 실행 파일 바로 뒤에 올 하위 명령 (Codex 의 `resume <id>` — 다른 인자보다 앞이어야 한다).
    """
    flag = ''.join(f' {part}' for part in head)
    flag += ' --no-daemon' if tool == 'codex' and codex_needs_no_daemon(exe) else ''
    flag += ''.join(f' {part}' for part in extra)
    if tool == 'claude' and _cmd_text(remote):
        flag += f' --remote-control "{_cmd_text(remote)}"'
    flag += f' {TOOLS[tool]["skip"]}' if skip else ''
    return '@echo off\r\ncall "{}"{}\r\n'.format(exe.replace('%', '%%'), flag)


_remote_cache: dict = {}


def remote_supported(exe: str) -> bool:
    """이 Claude Code 가 `--remote-control` 을 아나 — 옛 판은 모르는 인자에 터미널이 바로 꺼진다.
    `claude --help` 에 그 이름이 있는지 본다 (판이 바뀌기 전까지 기억한다)."""
    try:
        key = (exe, os.path.getmtime(exe))
    except OSError:
        return False
    if key not in _remote_cache:
        try:
            done = subprocess.run([exe, '--help'], capture_output=True, text=True, encoding='utf-8', errors='replace',
                                  timeout=20, env=clean_env(), creationflags=0x08000000)     # 창 없이
            _remote_cache[key] = '--remote-control' in (done.stdout or '') + (done.stderr or '')
        except (OSError, subprocess.SubprocessError):
            return False                                                                          # 못 알아내면 기억하지 않는다
    return _remote_cache[key]


def install_text(tool: str) -> str:
    """설치 창에서 돌릴 PowerShell. 끝나면 결과를 보이고 엔터를 기다린다."""
    label = TOOLS[tool]['label']
    if tool == 'claude':
        steps = f"""
Write-Host 'Anthropic 공식 설치 스크립트로 설치합니다 ({CLAUDE_INSTALL})' -ForegroundColor Cyan
# irm | iex 로 돌리지 않는다 — 공식 스크립트는 실패하면 `exit 1` 이라 이 창째 닫혀 오류를 못 보고, StrictMode·Stop 도 이 창에 남는다.
# 파일로 받아 따로 돌리고 종료 코드를 본다 (2026-10-27 검토).
$official = Join-Path $env:TEMP 'claude-install.ps1'
try {{
    Invoke-WebRequest '{CLAUDE_INSTALL}' -OutFile $official -UseBasicParsing -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $official
    if ($LASTEXITCODE -ne 0) {{ Write-Host "설치하지 못했습니다 (종료 코드 $LASTEXITCODE). 위의 빨간 메시지를 확인해 주세요." -ForegroundColor Red }}
}} catch {{ Write-Host "설치 스크립트를 받지 못했습니다: $_" -ForegroundColor Red }}
Remove-Item $official -Force -ErrorAction SilentlyContinue
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {{
    Write-Host ''
    Write-Host '참고: Git for Windows 가 없습니다. Claude Code 가 요구하면  winget install --id Git.Git -e  로 설치하세요.' -ForegroundColor Yellow
}}"""
    else:
        steps = """
if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host 'winget 으로 설치합니다 (OpenAI.Codex)' -ForegroundColor Cyan
    winget install --id OpenAI.Codex -e --accept-source-agreements --accept-package-agreements
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Host 'npm 으로 설치합니다 (@openai/codex)' -ForegroundColor Cyan
    npm install -g @openai/codex
} else {
    Write-Host 'winget 도 npm(Node.js)도 없어 설치하지 못했습니다. Microsoft Store 의 앱 설치 관리자를 먼저 설치해 주세요.' -ForegroundColor Red
}"""
    # winget 의 Codex 는 `codex` 이름 없이 깔릴 수 있다 — 데스크(find)와 같은 자리도 본다
    winget_check = ''
    if tool == 'codex':
        places = ', '.join("'" + str(root.joinpath(*parts)).replace("'", "''") + "'"
                           for root in winget_roots() for parts in WINGET_CODEX)
        winget_check = ('if (-not $found) {\n'
                        f'    $found = Get-ChildItem -Path {places} -ErrorAction SilentlyContinue | Select-Object -First 1\n'
                        '}\n')
    return f"""$ErrorActionPreference = 'Continue'
$Host.UI.RawUI.WindowTitle = '{label} 설치'
Write-Host '{label} 설치' -ForegroundColor White
Write-Host ''
{steps.strip()}
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + $env:USERPROFILE + '\\.local\\bin'
Write-Host ''
$found = Get-Command {tool} -ErrorAction SilentlyContinue
{winget_check}if ($found) {{
    Write-Host '설치를 마쳤습니다. 독의 에이전트 터미널에서 바로 쓸 수 있습니다.' -ForegroundColor Green
}} else {{
    Write-Host '설치를 확인하지 못했습니다. 위의 메시지를 확인해 주세요.' -ForegroundColor Yellow
}}
Read-Host '엔터를 누르면 이 창을 닫습니다'
"""


# ── 지난 대화 찾기 (2026-10-27 요청 — 업데이트·PC 재시작 뒤 에이전트 터미널을 그대로 다시 연다) ──
# Claude Code 는 대화를 `~/.claude/projects/<폴더>/<id>.jsonl` 에 남긴다 — `--resume <id>` 는 그 파일이 있어야 열린다
# (첫 메시지 전에는 파일이 없다). Codex 는 `~/.codex/sessions/YYYY/MM/DD/rollout-…-<id>.jsonl` 의 첫 줄(session_meta)에
# id 와 cwd 를 적는다 — 데스크가 연 뒤 그 폴더에서 생긴 것 가운데 가장 최근에 쓴 것이 그 세션의 대화다.
def claude_transcript(conversation: str) -> bool:
    if not conversation or not re.fullmatch(r'[0-9a-fA-F-]{36}', conversation):
        return False
    root = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'projects'
    try:
        return any(root.glob(f'*/{conversation}.jsonl'))
    except OSError:
        return False


def _same_folder(a: str, b: str) -> bool:
    clean = lambda path: os.path.normcase(os.path.normpath(str(path).removeprefix('\\\\?\\')))   # Codex 는 \\?\D:\… 로 적는다
    return clean(a) == clean(b)


def codex_thread(folder: str, since: float, exclude=()) -> str:
    """since(time.time()) 뒤에 folder 에서 쓴 Codex 대화 중 가장 최근 것의 id. 없으면 ''."""
    import datetime
    import json
    root = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'sessions'
    day, today, found = datetime.date.fromtimestamp(since), datetime.date.today(), []
    while day <= today:
        folder_of_day = root / f'{day:%Y}' / f'{day:%m}' / f'{day:%d}'
        try:
            for path in folder_of_day.glob('rollout-*.jsonl'):
                stamp = path.stat().st_mtime
                if stamp >= since - 5:
                    found.append((stamp, path))
        except OSError:
            pass
        day += datetime.timedelta(days=1)
    for _stamp, path in sorted(found, reverse=True):
        try:
            with open(path, encoding='utf-8') as opened:
                meta = json.loads(opened.readline()).get('payload') or {}
        except (OSError, ValueError, AttributeError):
            continue
        thread = str(meta.get('id') or meta.get('session_id') or '')
        if thread and thread not in exclude and _same_folder(meta.get('cwd') or '', folder):
            return thread
    return ''


# ── 터미널 띄우기 ─────────────────────────────────────────────
def terminal_args(folder: str, title: str, command: list[str]) -> tuple[list[str], bool]:
    """(실행할 인자, 새 콘솔이 필요한가). wt 는 ';' 를 명령 구분으로 읽으므로 그런 경로면 cmd 로 연다."""
    wt = shutil.which('wt.exe', path=search_path())
    if wt and not any(';' in part for part in [folder, title, *command]):
        return [wt, '-w', 'new', '-d', folder, '--title', title, *command], False
    return command, True


def clean_env() -> dict:
    """PyInstaller 가 넣은 값은 빼고, PATH 는 레지스트리 것까지 합친다 (core/child.py)."""
    return child.clean_env(search_path())


def spawn(args: list[str], cwd: str, new_console: bool) -> None:
    child.spawn(args, cwd, child.NEW_CONSOLE if new_console else 0, search_path())


def write_launcher(tool: str, folder: str, skip: bool, work_dir: Path, remote: str = '', extra: tuple = (),
                   script_name: str = '', head: tuple = ()) -> tuple[Path, str]:
    """`<자료 폴더>/agent/` 에 실행기를 쓰고 (그 경로, 실제로 붙인 원격 제어 이름)을 돌려준다 — 바깥 터미널(launch)과 데스크 안 터미널(agent_term)이 같이 쓴다."""
    exe = find(tool)
    if not exe:
        raise RuntimeError(f'{TOOLS[tool]["label"]} 가 설치되어 있지 않습니다.')
    if not os.path.isdir(folder):
        raise ValueError('폴더를 찾을 수 없습니다.')
    if remote and not (tool == 'claude' and remote_supported(exe)):
        remote = ''
    try:
        remote.encode('oem')                 # 실행기는 OEM 코드페이지로 쓴다 — 한글이 안 되는 PC 면 영문 이름으로
    except UnicodeEncodeError:
        remote = 'Desk'
    work = Path(work_dir) / 'agent'
    work.mkdir(parents=True, exist_ok=True)
    # 데스크 안 터미널은 세션마다 제 실행기(script_name)를 쓴다 — 다시 시작할 때 다른 세션의 설정을 집어 오지 않게
    script = work / (script_name or (f'{tool}-auto.cmd' if remote or extra else f'{tool}.cmd'))
    text = launcher_text(exe, skip, tool, remote, tuple(extra), tuple(head))
    text.encode('oem')                       # 한글이 안 되는 PC 면 여기서 UnicodeEncodeError — 다시 해 봐야 소용없다
    # 방금 끈 cmd(또는 백신 검사)가 실행기를 잠깐 쥐고 있으면 Errno 22·13 이 난다 — '다시 시작'이 실행기를 고쳐 쓰므로 잠깐 기다린다
    for attempt in range(LAUNCHER_TRIES):
        try:
            script.write_text(text, encoding='oem', errors='strict')
            break
        except OSError:
            if attempt == LAUNCHER_TRIES - 1:
                raise
            time.sleep(0.2)
    return script, remote


def launch(tool: str, folder: str, skip: bool, work_dir: Path, remote: str = '', extra: tuple = ()) -> str:
    """folder 에서 에이전트를 새 터미널로 연다. 돌려주는 것은 화면에 보일 한 줄.

    remote 를 주면 Claude Code 를 원격 제어(휴대폰·웹)에 연결해 연다 — 이 판이 그 인자를 모르면 붙이지 않고 그냥 연다.
    (claude.ai 구독 로그인이 아니거나 조직이 막았으면 세션은 그대로 열리고 연결 실패 알림만 뜬다.)"""
    script, remote = write_launcher(tool, folder, skip, work_dir, remote, extra)
    name = Path(folder).name or folder
    args, new_console = terminal_args(folder, f'{TOOLS[tool]["label"]} · {name}', ['cmd.exe', '/k', str(script)])
    spawn(args, folder, new_console)
    mode = (' (권한 묻지 않기)' if skip else '') + (' (원격 제어 연결)' if remote else '')
    return f'{name} 에서 {TOOLS[tool]["label"]}{mode} 를 열었습니다.'


def install(tool: str, work_dir: Path) -> str:
    if tool not in TOOLS:
        raise ValueError('지원하지 않는 에이전트입니다.')
    work = Path(work_dir) / 'agent'
    work.mkdir(parents=True, exist_ok=True)
    script = work / f'install-{tool}.ps1'
    script.write_text(install_text(tool), encoding='utf-8-sig')     # PowerShell 5.1 은 BOM 이 있어야 한글을 읽는다
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)]
    args, new_console = terminal_args(str(Path.home()), f'{TOOLS[tool]["label"]} 설치', command)
    spawn(args, str(Path.home()), new_console)
    return f'{TOOLS[tool]["label"]} 설치 창을 열었습니다. 끝나면 여기서 바로 쓸 수 있습니다.'
