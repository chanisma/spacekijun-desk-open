"""SPACEKIJUN 에이전트 연결(MCP) — 자동화 업무 폴더의 에이전트에 SPACEKIJUN 서버를 등록하고 인증 창을 띄운다 (2026-10-25 요청).

서버는 SPACEKIJUN 엣지 함수 `mcp`(상태 없는 Streamable HTTP)이고, 인증은 Supabase OAuth 2.1 이다 — 에이전트가 동적 등록으로
제 클라이언트를 만들고, 선생님이 브라우저에서 **직접** SPACEKIJUN 에 로그인해 [승인]하면 그 사람 본인의 토큰을 받는다.
그래서 데스크는 로그인을 대신하지 않는다(CLAUDE.md «로그인은 자동화하지 않는다») — 등록하고, 인증 창을 열고, 상태를 보일 뿐이다.
쓸 수 있는 도구는 학교 관리자가 정한다(SPACEKIJUN Admin ▸ 에이전트(MCP)). 정본 = spacekijun 저장소 docs/features/mcp-agent.md.

어디에 등록하나
  · Claude Code — **자동화 업무 폴더의 로컬 범위**(`claude mcp add -s local`, ~/.claude.json 의 그 폴더 항목). 업무 스킬처럼
    그 폴더에서 연 에이전트만 SPACEKIJUN 도구를 본다. 사용자가 이미 다른 범위(사용자 전체 등)에 같은 주소로 넣어 두었으면 그것을 쓴다.
  · Codex — 폴더 범위가 없어 사용자 설정(`~/.codex/config.toml`)에 넣는다. `codex mcp add` 는 넣자마자 OAuth 를 시작하는데
    openid 범위를 달라고 한다 → 이 서버는 받지 않는다(HS256 프로젝트라 ID 토큰 불가). 그래서 표를 직접 더하고 `scopes` 를 적는다.
  · 같은 이름(spacekijun)이 다른 주소로 있으면 **사용자가 만든 것**이다 — 건드리지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

from core import agent, child

NAME = 'spacekijun'
URL = 'https://your-project-ref.supabase.co/functions/v1/mcp'
SCOPES = ('email', 'profile')                       # 서버가 알리는 범위 — openid 는 넣지 않는다
MANAGE_URL = 'https://spacekijun.lovable.app/oauth/consent'   # «연결된 에이전트» 목록 · [연결 해제]
CREATE_NO_WINDOW = 0x08000000
CHECK_TIMEOUT = 45                                   # `claude mcp get` 은 서버에 붙어 보고 답한다

# 상태: missing(등록 안 함) · auth(등록됨, 인증 필요) · ok(연결됨) · error(등록됐지만 붙지 못함) · foreign(같은 이름, 다른 주소)
STATES = ('missing', 'auth', 'ok', 'error', 'foreign')


class McpError(RuntimeError):
    pass


def _run(args: list[str], cwd: str, timeout: int = CHECK_TIMEOUT) -> subprocess.CompletedProcess:
    with child.plain_dll_directory():
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=timeout, env=agent.clean_env(), creationflags=CREATE_NO_WINDOW,
                              stdin=subprocess.DEVNULL)


# ── Claude Code ───────────────────────────────────────────────
def parse_claude_get(code: int, text: str) -> dict:
    """`claude mcp get spacekijun` 의 출력 → {state, scope}."""
    if code != 0 or not re.search(r'^\s*URL:', text, re.M):
        return {'state': 'missing', 'scope': ''}
    url = re.search(r'^\s*URL:\s*(\S+)', text, re.M).group(1)
    scope = (re.search(r'^\s*Scope:\s*(.+)$', text, re.M) or [None, ''])[1].strip()
    if url.rstrip('/') != URL:
        return {'state': 'foreign', 'scope': scope}
    status = (re.search(r'^\s*Status:\s*(.+)$', text, re.M) or [None, ''])[1]
    if re.search(r'needs auth', status, re.I):
        state = 'auth'
    elif re.search(r'connected', status, re.I):
        state = 'ok'
    else:
        state = 'error'
    return {'state': state, 'scope': scope}


def claude_status(exe: str, folder: Path) -> dict:
    done = _run([exe, 'mcp', 'get', NAME], str(folder))
    return parse_claude_get(done.returncode, (done.stdout or '') + (done.stderr or ''))


def claude_register(exe: str, folder: Path) -> str:
    """폴더 범위에 넣는다. 이미 있으면(같은 주소) 그대로. 돌려주는 것은 넣기 전 상태."""
    before = claude_status(exe, folder)['state']
    if before == 'foreign':
        raise McpError('같은 이름(spacekijun)으로 다른 주소의 서버가 이미 등록되어 있어 건드리지 않았습니다.')
    if before == 'missing':
        done = _run([exe, 'mcp', 'add', '--transport', 'http', '-s', 'local', NAME, URL], str(folder))
        if done.returncode != 0:
            raise McpError('Claude Code 에 등록하지 못했습니다: ' + (done.stderr or done.stdout or '').strip()[:200])
    return before


def claude_remove(exe: str, folder: Path) -> bool:
    """우리가 넣은 폴더 범위 등록과 인증 정보를 뺀다. 다른 범위(사용자가 넣은 것)는 두고, 뺀 것이 있으면 True."""
    found = claude_status(exe, folder)
    if found['state'] in ('missing', 'foreign') or not found['scope'].lower().startswith('local'):
        return False
    _run([exe, 'mcp', 'logout', NAME], str(folder))
    return _run([exe, 'mcp', 'remove', NAME, '-s', 'local'], str(folder)).returncode == 0


# ── Codex ─────────────────────────────────────────────────────
def codex_home() -> Path:
    saved = os.environ.get('CODEX_HOME')
    return Path(saved) if saved else Path.home() / '.codex'


def codex_entry(config: Path) -> dict | None:
    """config.toml 의 [mcp_servers.spacekijun] (없으면 None). 읽지 못하는 설정이면 McpError — 고쳐 쓰다 망가뜨리지 않는다."""
    if not config.is_file():
        return None
    try:
        data = tomllib.loads(config.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise McpError(f'Codex 설정 파일을 읽지 못해 건드리지 않았습니다 ({config}): {exc}')
    entry = (data.get('mcp_servers') or {}).get(NAME)
    return entry if isinstance(entry, dict) else None


ENTRY_TEXT = (f'\n# 스페이스기전 데스크가 더함 — SPACEKIJUN 에이전트 연결 (이 서버는 openid 범위를 받지 않는다)\n'
              f'[mcp_servers.{NAME}]\nurl = "{URL}"\nscopes = [{", ".join(json.dumps(s) for s in SCOPES)}]\n')


def codex_register(config: Path | None = None) -> bool:
    """사용자 설정 끝에 표를 더한다(다른 설정·주석은 그대로). 더했으면 True, 이미 있으면 False."""
    config = config or codex_home() / 'config.toml'
    entry = codex_entry(config)
    if entry is not None:
        if str(entry.get('url', '')).rstrip('/') != URL:
            raise McpError('Codex 설정에 같은 이름(spacekijun)으로 다른 서버가 있어 건드리지 않았습니다.')
        return False
    config.parent.mkdir(parents=True, exist_ok=True)
    text = config.read_text(encoding='utf-8') if config.is_file() else ''
    if text and not text.endswith('\n'):
        text += '\n'
    config.write_text(text + ENTRY_TEXT, encoding='utf-8')
    if codex_entry(config) is None:                  # 더한 뒤 다시 읽어 본다 — 못 읽으면 되돌린다
        config.write_text(text, encoding='utf-8')
        raise McpError('Codex 설정에 넣지 못했습니다.')
    return True


def parse_codex_list(text: str) -> str:
    """`codex mcp list --json` → 상태. auth_status 가 not_logged_in 이면 인증 필요."""
    try:
        rows = json.loads(text[text.index('['):])
    except (ValueError, json.JSONDecodeError):
        return 'error'
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get('name') == NAME:
            url = str((row.get('transport') or {}).get('url', '')).rstrip('/')
            if url != URL:
                return 'foreign'
            if not row.get('enabled', True):
                return 'error'
            return 'auth' if row.get('auth_status') in ('not_logged_in', 'unsupported', None) else 'ok'
    return 'missing'


def codex_status(exe: str) -> dict:
    done = _run([exe, 'mcp', 'list', '--json'], str(Path.home()))
    return {'state': parse_codex_list(done.stdout or ''), 'scope': 'user'}


def codex_remove(exe: str) -> bool:
    """우리 주소로 넣은 표만 뺀다(로그아웃 → 지우기)."""
    if codex_status(exe)['state'] in ('missing', 'foreign'):
        return False
    home = str(Path.home())
    _run([exe, 'mcp', 'logout', NAME], home)
    return _run([exe, 'mcp', 'remove', NAME], home).returncode == 0


# ── 공통 ──────────────────────────────────────────────────────
def status(tool: str, folder: Path) -> dict:
    """{tool, state, scope} — 에이전트가 없으면 state = 'none'."""
    exe = agent.find(tool)
    if not exe:
        return {'tool': tool, 'state': 'none', 'scope': ''}
    try:
        found = claude_status(exe, folder) if tool == 'claude' else codex_status(exe)
    except (OSError, subprocess.SubprocessError):
        found = {'state': 'error', 'scope': ''}
    return {'tool': tool, **found}


def register(tool: str, folder: Path) -> None:
    exe = agent.find(tool)
    if not exe:
        raise McpError(f'{agent.TOOLS[tool]["label"]} 가 설치되어 있지 않습니다.')
    if tool == 'claude':
        claude_register(exe, folder)
    else:
        codex_register()


def remove(tool: str, folder: Path) -> bool:
    exe = agent.find(tool)
    if not exe:
        return False
    return claude_remove(exe, folder) if tool == 'claude' else codex_remove(exe)


def login_text(tool: str, exe: str) -> str:
    """인증 창에서 돌릴 PowerShell — 에이전트의 `mcp login` 이 브라우저를 열고 승인을 기다린다.
    끝나면 성공은 잠깐 뒤 스스로 닫고(종료 코드 0), 실패는 창을 남긴다(1)."""
    label = agent.TOOLS[tool]['label']
    quoted = "'" + exe.replace("'", "''") + "'"
    scopes = f" --scopes {','.join(SCOPES)}" if tool == 'codex' else ''
    text = f"""$ErrorActionPreference = 'Continue'
$Host.UI.RawUI.WindowTitle = 'SPACEKIJUN 연결 — {label}'
Write-Host 'SPACEKIJUN 에이전트 연결 (MCP) — {label} 인증' -ForegroundColor White
Write-Host ''
Write-Host '1. 곧 브라우저가 열립니다. SPACEKIJUN 에 직접 로그인하세요 (이미 로그인되어 있으면 건너뜁니다).'
Write-Host '2. 연결 승인 화면에서 [승인]을 누르세요. 승인하면 이 창이 저절로 이어집니다.'
Write-Host '   연결은 선생님 본인의 권한으로만 동작하고, 쓸 수 있는 도구는 학교 관리자가 정합니다.'
Write-Host '   연결을 끊으려면: {MANAGE_URL}'
Write-Host ''
& {quoted} mcp login {NAME}{scopes}
$code = $LASTEXITCODE
Write-Host ''
if ($code -eq 0) {{
    Write-Host '인증을 마쳤습니다. 자동화 업무 폴더에서 에이전트를 열면 SPACEKIJUN 도구를 쓸 수 있습니다.' -ForegroundColor Green
    Start-Sleep -Seconds 3
    exit 0
}}
Write-Host '인증하지 못했습니다. 위의 메시지를 확인하고 데스크에서 다시 [인증하기]를 눌러 주세요.' -ForegroundColor Yellow
Read-Host '엔터를 누르면 이 창을 닫습니다'
exit 1
"""
    return text.replace('—', '-')            # 한국어 콘솔(cp949)은 — 를 못 그려 ? 로 보인다


def login(tool: str, folder: Path, work_dir: Path) -> subprocess.Popen:
    """인증 창을 띄운다(제 콘솔 — 브라우저 승인을 기다리는 대화형 터미널이어야 한다). Claude 는 폴더 범위라 그 폴더에서."""
    exe = agent.find(tool)
    if not exe:
        raise McpError(f'{agent.TOOLS[tool]["label"]} 가 설치되어 있지 않습니다.')
    work = Path(work_dir) / 'agent'
    work.mkdir(parents=True, exist_ok=True)
    script = work / f'spacekijun-login-{tool}.ps1'
    script.write_text(login_text(tool, exe), encoding='utf-8-sig')     # PowerShell 5.1 은 BOM 이 있어야 한글을 읽는다
    cwd = str(folder) if tool == 'claude' else str(Path.home())
    return child.spawn(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                       cwd, child.NEW_CONSOLE, agent.search_path())
