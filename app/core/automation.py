"""자동화 업무 폴더 — 업무용 스킬을 **한 폴더**에 설치해 두고, 에이전트를 거기서 연다 (2026-10-22 요청).

왜 폴더 하나인가
  · Claude Code 는 작업 폴더의 `.claude/skills`, Codex 는 `.agents/skills` 를 읽는다. 에이전트 터미널은 고른 폴더를 작업 위치로
    열므로, 스킬이 있는 폴더 = 에이전트를 여는 폴더가 된다. 스킬을 더해도 폴더는 늘지 않고 목록만 는다.
  · 사용자 전체(`~/.claude/skills`)에 깔면 모든 프로젝트에서 스킬 설명이 불려 나오고 사용자가 이미 쓰는 스킬과 섞인다 — 쓰지 않는다.

어디에 두나
  · 실제 폴더는 사용자 홈 아래(`~/자동화 업무`)다. 바탕화면은 OneDrive·서버로 동기화되는 PC 가 있어 업무 산출물(학생 정보가
    들어갈 수 있다)이 클라우드로 올라간다 → 바탕화면에는 **바로가기**만 둔다.
  · 스킬 정본은 실행 파일에 실린 `resources/skills/<이름>` 이다 (scripts/sync-desk-skills.py 가 `.claude/skills` 에서 맞춘다).
    데스크가 새 판으로 바뀌면 스킬도 새 판이 된다.

설치는 복사다 (양쪽 에이전트 폴더 모두). 우리가 깐 것은 `.spacekijun-skill.json` 에 내용 해시를 적어 두어, 새 판이면 덮어쓰고
**사용자가 직접 만든 같은 이름의 스킬(표시가 없는 것)은 건드리지 않는다.**
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from core import agent

FOLDER_NAME = '자동화 업무'
RC_NAME = '자동화 업무'                       # Claude Code 원격 제어(휴대폰·웹) 세션 이름
MANAGED = '.spacekijun-skill.json'
TARGETS = ('.claude/skills', '.agents/skills')   # Claude Code · Codex
SKIP_PARTS = {'__pycache__', '.omc', 'node_modules'}
KEEP_ON_UPDATE = ('node_modules',)               # 스킬 폴더에서 `npm install` 로 받은 것 — 새 판으로 바꿀 때 지우지 않는다 (에듀파인)
CREATE_NO_WINDOW = 0x08000000
RETIRED = ('kakaotalk',)                        # 걷어낸 스킬 — 우리가 깐 것이 남아 있으면 깔 때 뺀다 (2026-11-08: 카카오톡, 정책 위반 소지)

AGENTS_TEXT = """# 자동화 업무

이 폴더는 스페이스기전 데스크가 관리하는 **업무 자동화 작업 폴더**입니다. 업무용 스킬이 `.claude/skills` 와 `.agents/skills` 에 설치되어 있습니다.

## 지킬 것
- **쪽지·메일·문서처럼 다른 사람에게 가는 것은 보내기 전에 초안을 보여 주고 승인을 받는다.** 보낸 것은 회수할 수 없다.
- 학생·학부모·교직원의 개인정보를 외부 서비스에 보내거나 결과물에 남기지 않는다. 필요한 만큼만 보고 요약한다.
- 스킬 폴더의 파일은 데스크가 새 판으로 바꿀 때 덮어쓴다. 고치고 싶으면 사본을 만들어 다른 이름으로 둔다.
- 스킬의 `SKILL.md` 를 먼저 읽고 그 순서·주의를 따른다.
"""


# ── 스킬 목록 ─────────────────────────────────────────────────
def resource_dir(kind: str = 'skills') -> Path:
    """kind — 'skills'(자동화 업무 스킬) · 'general-skills'(어느 폴더에서나 쓰는 기본 스킬, 2026-10-30)."""
    bundled = getattr(sys, '_MEIPASS', None)
    if bundled:
        return Path(bundled) / 'resources' / kind
    return Path(__file__).resolve().parents[1] / 'resources' / kind


def _frontmatter(text: str) -> dict:
    found = {}
    match = re.match(r'---\s*\r?\n(.*?)\r?\n---', text, re.S)
    for line in (match.group(1).splitlines() if match else []):
        key, _, value = line.partition(':')
        if value and key.strip() in ('name', 'description'):
            found[key.strip()] = value.strip()
    return found


def digest(folder: Path) -> str:
    """폴더 내용의 해시 — 경로와 바이트만 본다(설치 표시·캐시는 뺀다)."""
    hasher = hashlib.sha256()
    for path in sorted(Path(folder).rglob('*')):
        relative = path.relative_to(folder)
        if path.is_dir() or path.name == MANAGED or any(p in SKIP_PARTS or p.endswith('.pyc') for p in relative.parts):
            continue
        hasher.update(relative.as_posix().encode('utf-8') + b'\0')
        hasher.update(path.read_bytes() + b'\0')
    return hasher.hexdigest()


def catalog(source: Path | None = None) -> list[dict]:
    """실려 있는 업무 스킬 목록. 이름순."""
    root = Path(source) if source else resource_dir()
    skills = []
    if not root.is_dir():
        return skills
    for folder in sorted(root.iterdir()):
        document = folder / 'SKILL.md'
        if not document.is_file():
            continue
        head = _frontmatter(document.read_text(encoding='utf-8', errors='replace'))
        try:
            meta = json.loads((folder / 'skill.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            meta = {}
        summary = meta.get('summary') or head.get('description', '')
        action = lambda a: {'label': str(a['label'])[:40], 'prompt': str(a['prompt'])[:600]}
        good = lambda items: [action(a) for a in items if isinstance(a, dict) and a.get('label') and a.get('prompt')] \
            if isinstance(items, list) else []
        # 기능별 묶음 (2026-11-05) — 스킬 패널이 스킬 안에서 묶음을 한 번 더 펼친다. 묶음 없는 스킬은 actions 만
        groups = [{'label': str(g['label'])[:40], 'summary': str(g.get('summary') or '')[:400], 'actions': good(g.get('actions'))}
                  for g in meta.get('groups', []) if isinstance(g, dict) and g.get('label')] \
            if isinstance(meta.get('groups'), list) else []
        skills.append({'name': folder.name, 'title': meta.get('title') or head.get('name') or folder.name,
                       'summary': summary if len(summary) <= 120 else summary[:117] + '…',
                       'needs': [n for n in meta.get('needs', []) if isinstance(n, dict) and n.get('program')],
                       'sensitive': meta.get('sensitive') is True,
                       'mcp': meta.get('mcp') if isinstance(meta.get('mcp'), str) else '',   # 쓰는 MCP 연결 (spacekijun)
                       # 할 수 있는 일 (2026-10-30) — 에이전트 터미널 오른쪽 «스킬» 패널에서 누르면 입력칸에 들어간다
                       # actions = 묶음 밖 + 묶음 안 전부 (개수·즐겨찾기는 이것으로)
                       'actions': good(meta.get('actions')) + [a for g in groups for a in g['actions']],
                       'groups': groups,
                       # 새 판으로 바꿀 때 지우지 않을 하위 폴더 (사용자가 쌓은 것 — 생기부 과목 메모리)
                       'keep': [k for k in meta.get('keep', []) if isinstance(k, str) and k and '..' not in k
                                and not k.startswith(('/', '\\'))] if isinstance(meta.get('keep'), list) else [],
                       'digest': digest(folder), 'path': folder})
    return skills


def _usable(place: str | None) -> bool:
    """찾은 실행 파일을 정말 쓸 수 있나. WindowsApps 의 python.exe 는 Microsoft Store 로 보내는 자리표시자일 수 있다
    ('Python was not found …', 종료 코드 9009) — 그 자리면 한 번 돌려 본다 (Python 설치 관리자면 진짜다)."""
    if not place:
        return False
    if 'windowsapps' not in place.lower():
        return True
    try:
        done = subprocess.run([place, '--version'], capture_output=True, text=True, timeout=10,
                              creationflags=CREATE_NO_WINDOW, env=agent.clean_env())
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and 'python' in (done.stdout + done.stderr).lower()


ACCESS_VIOLATION = 0xC0000005
KOREAN_PROBE = '스페이스기전-노드점검'
_node_checked: dict[tuple, bool] = {}


def node_reads_korean(place: str) -> bool:
    """이 Node 가 한글 폴더의 CommonJS 파일을 돌리나 (2026-10-26 실측).

    Node 22.11·22.12 는 경로에 한글이 든 `.js` 를 읽자마자 죽는다(0xC0000005, `.mjs` 는 된다). 22.23.4 는 된다.
    `자동화 업무` 폴더 이름이 한글이라 그 판이면 쿨메신저 `cdp.js`·에듀파인 스크립트가 한 줄도 못 돈다 → 없는 것으로 보고
    데스크가 새 판을 이 사용자에게 깐다. 판 번호로 자르지 않고 실제로 돌려 본다 — **죽는 것을 본 때만** False 다."""
    try:
        stamp = os.stat(place).st_mtime_ns
    except OSError:
        stamp = 0
    key = (str(place).lower(), stamp)
    if key in _node_checked:
        return _node_checked[key]
    try:
        folder = Path(tempfile.gettempdir()) / KOREAN_PROBE
        folder.mkdir(exist_ok=True)
        probe = folder / 'probe.js'
        probe.write_text("process.stdout.write('ok')", encoding='utf-8')
        done = subprocess.run([place, str(probe)], capture_output=True, timeout=20,
                              creationflags=CREATE_NO_WINDOW, env=agent.clean_env())
    except (OSError, subprocess.SubprocessError):
        return True                                     # 판단하지 못했다 — 막지 않는다 (기억하지도 않는다)
    works = (done.returncode & 0xFFFFFFFF) != ACCESS_VIOLATION
    _node_checked[key] = works
    return works


def find_program(program: str) -> str | None:
    """PATH 차례대로 쓸 수 있는 첫 것. 첫 자리가 Store 자리표시자라고 멈추지 않는다 — 데스크가 뜬 뒤 Python 을 깔면
    뜰 때의 PATH(WindowsApps 포함)가 앞서고 새로 깐 Python 은 레지스트리 PATH 에만 있다 (2026-10-27 '새로고침해도 그대로')."""
    for folder in agent.search_path().split(';'):
        place = shutil.which(str(program), path=folder)
        if not _usable(place):
            continue
        if program == 'node' and not node_reads_korean(place):
            return None
        return place
    return None


def requirements(skill: dict) -> list[dict]:
    """스킬이 쓰는 프로그램이 이 PC 에 있나. 없으면 데스크가 설치한다 (INSTALLERS 에 있는 것만)."""
    found = []
    for need in skill.get('needs', []):
        program = need['program']
        here = bool(find_program(program))
        label = need.get('label') or program
        if not here and program == 'node' and shutil.which('node', path=agent.search_path()):
            label += ' (지금 판은 한글 폴더에서 멈춤)'
        found.append({'program': program, 'label': label, 'optional': need.get('optional') is True,
                      'found': here, 'installable': program in INSTALLERS})
    return found


# ── 필요한 프로그램 설치 (2026-10-22 요청) ─────────────────────────
# 켜 둔 스킬이 쓰는데 없는 Node.js·Python 을 데스크가 깐다. 학교 PC 는 관리자 권한이 없는 경우가 많아 **이 사용자에게만** 깐다.
#   · Node.js — nodejs.org 의 공식 zip(22 이상 LTS)을 받아 SHASUMS256 으로 확인하고 %LOCALAPPDATA%\\Programs\\nodejs 에 푼다.
#     (winget 의 Node.js 는 컴퓨터 전체 설치라 관리자 권한을 묻는다.)
#   · Python — winget 의 사용자 설치(Python.Python.3.12 --scope user). winget 이 없거나 실패하면 python.org 설치 파일을
#     Python Software Foundation 서명을 확인하고 사용자 설치로 돌린다.
# 둘 다 사용자 PATH 에 넣는다 — 새로 여는 터미널(에이전트)부터 보인다.
INSTALLERS = {'node': 'Node.js', 'python': 'Python 3'}
PYTHON_FALLBACK = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'


def missing_programs(workspace: Path, skip=(), source: Path | None = None) -> list[str]:
    """켜 둔 스킬(사용자가 끄지 않았고 직접 만든 같은 이름이 아닌 것)이 쓰는데 이 PC 에 없는, 데스크가 깔 수 있는 프로그램."""
    wanted = []
    for row in status(workspace, source):
        if row['name'] in skip or row['state'] == 'foreign':
            continue
        for need in row['needs']:
            if not need['found'] and need['program'] in INSTALLERS and need['program'] not in wanted:
                wanted.append(need['program'])
    return [name for name in INSTALLERS if name in wanted]          # 늘 같은 차례 (Node.js → Python)


_NODE_STEPS = r"""
Step 'Node.js 설치 — nodejs.org 공식 파일, 이 사용자 폴더에 (관리자 권한 없이)' {
    $index = Invoke-RestMethod 'https://nodejs.org/dist/index.json'
    $pick = $index | Where-Object { $_.lts -and ($_.files -contains 'win-x64-zip') -and [int]($_.version.TrimStart('v').Split('.')[0]) -ge 22 } | Select-Object -First 1
    if (-not $pick) { throw 'Node.js 22 이상 LTS 판을 찾지 못했습니다.' }
    $name = "node-$($pick.version)-win-x64"
    $zip = Join-Path $env:TEMP "$name.zip"
    Write-Host "  받는 중: $name.zip"
    Invoke-WebRequest "https://nodejs.org/dist/$($pick.version)/$name.zip" -OutFile $zip -UseBasicParsing
    $sums = [Text.Encoding]::UTF8.GetString((Invoke-WebRequest "https://nodejs.org/dist/$($pick.version)/SHASUMS256.txt" -UseBasicParsing).RawContentStream.ToArray())
    $want = ($sums -split "`n" | Where-Object { $_ -match "\s$([regex]::Escape($name))\.zip\s*$" } | Select-Object -First 1) -replace '\s.*$', ''
    if (-not $want -or (Sha256 $zip) -ne $want.ToLower()) { Remove-Item $zip -Force; throw '받은 파일의 확인값(SHA-256)이 맞지 않습니다.' }
    Write-Host '  확인값(SHA-256) 맞음'
    $programs = Join-Path $Root 'Programs'
    $dest = Join-Path $programs 'nodejs'
    New-Item -ItemType Directory -Force -Path $programs | Out-Null
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, $programs)
    Rename-Item (Join-Path $programs $name) 'nodejs'
    Remove-Item $zip -Force
    AddUserPath $dest
}
"""

_PYTHON_STEPS = r"""
Step 'Python 3 설치 — 이 사용자에게 (관리자 권한 없이)' {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 -e --scope user --accept-source-agreements --accept-package-agreements --disable-interactivity
        Refresh
    }
    if (-not (RealPython)) {
        $setup = Join-Path $env:TEMP 'python-setup.exe'
        Write-Host "  받는 중: $PythonUrl"
        Invoke-WebRequest $PythonUrl -OutFile $setup -UseBasicParsing
        $sign = Get-AuthenticodeSignature $setup
        if ($sign.Status -ne 'Valid' -or $sign.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
            Remove-Item $setup -Force; throw '받은 설치 파일의 서명을 확인하지 못했습니다.'
        }
        $run = Start-Process $setup -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_test=0', 'Include_launcher=0' -Wait -PassThru
        Remove-Item $setup -Force
        if ($run.ExitCode -ne 0) { throw "Python 설치가 끝나지 않았습니다 (종료 코드 $($run.ExitCode))." }
        Refresh
    }
}
"""

_CHECKS = {
    # 판만 보지 않고 한글 폴더의 .js 를 돌려 본다 — 22.11 같은 판은 거기서 죽는다 (node_reads_korean)
    'node': r"""Check 'Node.js 22 이상 (한글 폴더에서 실행)' { $n = if ($SetPath) { 'node' } else { Join-Path $Root 'Programs\nodejs\node.exe' }; """
            r"""try { $v = & $n --version 2>$null; if ([int]("$v".TrimStart('v').Split('.')[0]) -lt 22) { return $false }; """
            rf"""$d = Join-Path $env:TEMP '{KOREAN_PROBE}'; New-Item -ItemType Directory -Force -Path $d | Out-Null; """
            r"""$p = Join-Path $d 'probe.js'; [IO.File]::WriteAllText($p, "process.stdout.write('ok')"); (& $n $p 2>$null) -eq 'ok' } catch { $false } }""",
    'python': r"Check 'Python 3' { [bool](RealPython) }",
}

_HEAD = r"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# 다른 PowerShell(7)에서 물려받은 모듈 경로면 Windows PowerShell 기본 명령이 안 불린다 — 기본 경로로
$env:PSModulePath = (Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\Modules') + ';' + (Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules') + ';' + (Join-Path $env:SystemRoot 'system32\WindowsPowerShell\v1.0\Modules')
$Host.UI.RawUI.WindowTitle = '자동화 업무 — 필요한 프로그램 설치'
$failed = @()
function Refresh { $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine') }
function AddUserPath($dir) {
    if ($SetPath) {
        $user = [Environment]::GetEnvironmentVariable('Path', 'User')
        if (-not (($user -split ';') -contains $dir)) { [Environment]::SetEnvironmentVariable('Path', ($dir + ';' + $user).TrimEnd(';'), 'User') }
        Refresh
    }
}
function Sha256($file) {
    $stream = [IO.File]::OpenRead($file)
    try { -join ([Security.Cryptography.SHA256]::Create().ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) } finally { $stream.Dispose() }
}
function RealPython {
    foreach ($c in @(Get-Command python -All -ErrorAction SilentlyContinue)) {
        try { $v = & $c.Source --version 2>&1; if ($LASTEXITCODE -eq 0 -and "$v" -match 'Python 3') { return $c.Source } } catch {}
    }
}
function Step($text, $work) {
    Write-Host ''
    Write-Host $text -ForegroundColor Cyan
    try { & $work } catch { Write-Host "  설치하지 못했습니다: $_" -ForegroundColor Red }
}
function Check($label, $test) {
    if (& $test) { Write-Host "  완료 — $label" -ForegroundColor Green } else { Write-Host "  실패 — $label" -ForegroundColor Red; $script:failed += $label }
}
"""


def prepare_text(programs: list[str], root: str = '$env:LOCALAPPDATA', set_path: bool = True, then: str = '') -> str:
    """없는 프로그램을 까는 PowerShell. 다 되면 종료 코드 0 으로 잠깐 뒤 스스로 닫히고, 하나라도 실패하면 창을 남긴다(1).
    root·set_path 는 시험용 — 실제로는 %LOCALAPPDATA% 와 사용자 PATH. 프로그램마다 따로 시도한다(하나가 실패해도 다음 것)."""
    if not programs or any(name not in INSTALLERS for name in programs):
        raise ValueError('설치할 수 없는 프로그램입니다.')
    labels = ', '.join(INSTALLERS[name] for name in programs)
    steps = ''.join(_NODE_STEPS if name == 'node' else _PYTHON_STEPS for name in programs)
    checks = '\n'.join(_CHECKS[name] for name in programs)
    done = '설치를 마쳤습니다.' + (f' {then}' if then else '')
    text = (_HEAD
            + f"$Root = {root}\n$SetPath = ${'true' if set_path else 'false'}\n$PythonUrl = '{PYTHON_FALLBACK}'\n"
            + f"Write-Host '자동화 업무 스킬에 필요한 프로그램을 설치합니다: {labels}' -ForegroundColor White\n"
            + steps
            + "Refresh\nWrite-Host ''\nWrite-Host '확인' -ForegroundColor Cyan\n" + checks + "\nWrite-Host ''\n"
            + "if ($failed.Count -eq 0) {\n"
            + f"    Write-Host '{done}' -ForegroundColor Green\n    Start-Sleep -Seconds 3\n    exit 0\n}}\n"
            + "Write-Host '설치하지 못한 것이 있습니다. 위의 메시지를 확인해 주세요. (학교 네트워크가 막았다면 직접 설치해 주세요)' -ForegroundColor Yellow\n"
            + "Read-Host '엔터를 누르면 이 창을 닫습니다'\nexit 1\n")
    return text.replace('—', '-')            # 한국어 콘솔(cp949)은 — 를 못 그려 ? 로 보인다


def prepare(programs: list[str], work_dir: Path, then: str = ''):
    """설치 창을 띄운다(제 콘솔 — 끝나기를 기다릴 수 있게). 돌려주는 것은 그 프로세스."""
    from core import child
    work = Path(work_dir) / 'agent'
    work.mkdir(parents=True, exist_ok=True)
    script = work / 'prepare-programs.ps1'
    script.write_text(prepare_text(programs, then=then), encoding='utf-8-sig')   # PowerShell 5.1 은 BOM 이 있어야 한글을 읽는다
    return child.spawn(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                       str(Path.home()), child.NEW_CONSOLE, agent.search_path())


# ── 작업 폴더 ─────────────────────────────────────────────────
def default_workspace() -> Path:
    return Path.home() / FOLDER_NAME


def ensure_workspace(workspace: Path) -> None:
    """폴더와 에이전트 공통 안내(AGENTS.md, CLAUDE.md)를 만든다. 이미 있는 파일은 건드리지 않는다."""
    workspace = Path(workspace)
    if not workspace.is_absolute():
        raise ValueError('폴더 경로가 올바르지 않습니다.')
    workspace.mkdir(parents=True, exist_ok=True)
    for name, text in (('AGENTS.md', AGENTS_TEXT), ('CLAUDE.md', '@AGENTS.md\n')):      # Claude 는 @ 로 AGENTS.md 를 불러온다
        spot = workspace / name
        if not spot.exists():
            spot.write_text(text, encoding='utf-8')


def _install_one(workspace: Path, skill: dict, target: str) -> str:
    destination = workspace.joinpath(*target.split('/')) / skill['name']
    mark = destination / MANAGED
    state = 'installed'
    kept = []
    if destination.exists():
        try:
            current = json.loads(mark.read_text(encoding='utf-8')).get('digest')
        except (OSError, ValueError, AttributeError):
            return 'foreign'                                        # 우리가 깐 것이 아니다 — 건드리지 않는다
        if current == skill['digest']:
            return 'current'
        # 받아 둔 의존성·사용자가 쌓은 것(skill.json keep)은 옆으로 옮겨 두었다가 되돌린다
        for name in (*KEEP_ON_UPDATE, *skill.get('keep', ())):
            if (destination / name).is_dir():
                aside = destination.parent / f'.{skill["name"]}.{name.replace("/", "~")}.keep'
                if aside.exists():
                    shutil.rmtree(aside)
                (destination / name).rename(aside)
                kept.append((name, aside))
        shutil.rmtree(destination)
        state = 'updated'
    shutil.copytree(skill['path'], destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.omc', 'node_modules'))
    for name, aside in kept:
        if (destination / name).exists():                            # 새 판에 실린 것보다 쌓아 둔 것이 먼저다
            shutil.rmtree(destination / name)
        (destination / name).parent.mkdir(parents=True, exist_ok=True)
        aside.rename(destination / name)
    mark.write_text(json.dumps({'name': skill['name'], 'digest': skill['digest']}, ensure_ascii=False), encoding='utf-8')
    return state


def install(workspace: Path, source: Path | None = None, skip=(), only=None) -> list[dict]:
    """업무 스킬을 양쪽 에이전트 폴더에 깐다(바뀐 것만). 돌려주는 것: [{name, title, states:{대상: 상태}}].
    skip — 사용자가 끈 스킬(깔지 않는다), only — 이 이름들만 (패널의 스킬 스위치, 2026-10-22)."""
    workspace = Path(workspace)
    ensure_workspace(workspace)
    retire(workspace)
    results = []
    for skill in catalog(source):
        if skill['name'] in skip or (only is not None and skill['name'] not in only):
            continue
        states = {target: _install_one(workspace, skill, target) for target in TARGETS}
        results.append({'name': skill['name'], 'title': skill['title'], 'states': states})
    return results


# ── 기본 스킬 (2026-10-30 요청) ──────────────────────────────
# 자동화 업무 폴더가 아니어도 쓰는 스킬(바탕화면 정리 …) — 사용자 범위에 깐다: Claude Code `~/.claude/skills`, Codex `~/.codex/skills`.
# 자동화 업무 스킬처럼 표시 파일(MANAGED)로 우리가 깐 것만 고친다 — 같은 이름의 사용자 스킬은 건드리지 않는다.
GENERAL_TARGETS = ('.claude/skills', '.codex/skills')
GENERAL_HOME: Path | None = None        # 깔 곳의 사용자 폴더 — 시험은 임시 폴더로 돌린다(test_sandbox), 없으면 Path.home()


def general_catalog() -> list[dict]:
    return catalog(resource_dir('general-skills'))


def install_general(home: Path | None = None) -> list[dict]:
    home = Path(home) if home else (GENERAL_HOME or Path.home())
    results = []
    for skill in general_catalog():
        states = {}
        for target in GENERAL_TARGETS:
            (home.joinpath(*target.split('/'))).mkdir(parents=True, exist_ok=True)
            states[target] = _install_one(home, skill, target)
        results.append({'name': skill['name'], 'title': skill['title'], 'states': states})
    return results


def uninstall(workspace: Path, name: str) -> int:
    """우리가 깐 스킬을 양쪽 에이전트 폴더에서 뺀다. 표시가 없는 것(사용자가 만든 같은 이름)은 그대로 둔다. 뺀 곳 수."""
    if not isinstance(name, str) or not name or Path(name).name != name or name in ('.', '..'):
        raise ValueError('스킬 이름이 올바르지 않습니다.')
    removed = 0
    for target in TARGETS:
        folder = Path(workspace).joinpath(*target.split('/')) / name
        if (folder / MANAGED).is_file():
            shutil.rmtree(folder)
            removed += 1
    return removed


def retire(workspace: Path) -> int:
    """걷어낸 스킬(RETIRED) 중 우리가 깐 것을 뺀다. 사용자가 만든 같은 이름은 그대로. 뺀 곳 수."""
    return sum(uninstall(workspace, name) for name in RETIRED)


def status(workspace: Path, source: Path | None = None) -> list[dict]:
    """스킬마다 설치 상태: missing(없음) · outdated(옛 판) · current(최신) · foreign(사용자가 만든 같은 이름)."""
    workspace = Path(workspace)
    rows = []
    for skill in catalog(source):
        seen = []
        for target in TARGETS:
            mark = workspace.joinpath(*target.split('/')) / skill['name'] / MANAGED
            folder = mark.parent
            if not folder.exists():
                seen.append('missing')
                continue
            try:
                seen.append('current' if json.loads(mark.read_text(encoding='utf-8')).get('digest') == skill['digest']
                            else 'outdated')
            except (OSError, ValueError, AttributeError):
                seen.append('foreign')
        state = next((s for s in ('foreign', 'missing', 'outdated') if s in seen), 'current')
        rows.append({'name': skill['name'], 'title': skill['title'], 'summary': skill['summary'], 'state': state,
                     'sensitive': skill['sensitive'], 'mcp': skill['mcp'], 'needs': requirements(skill)})
    return rows


def summary(results: list[dict]) -> str:
    """install() 결과를 화면에 보일 한 줄로."""
    counts = {'installed': 0, 'updated': 0, 'foreign': 0}
    for item in results:
        for state in item['states'].values():
            if state in counts:
                counts[state] += 1
    parts = []
    if counts['installed']:
        parts.append('설치')
    if counts['updated']:
        parts.append('최신 판으로 갱신')
    text = ' · '.join(parts) + '했습니다' if parts else '이미 최신입니다'
    if counts['foreign']:
        text += f' (직접 만든 같은 이름의 스킬 {counts["foreign"]}개는 그대로 뒀습니다)'
    return text + '.'


# ── 바탕화면 바로가기 ─────────────────────────────────────────
def desktop_dir() -> Path | None:
    """바탕화면 폴더 — 리디렉션(OneDrive·서버)돼 있어도 Windows 가 알려 주는 자리를 쓴다."""
    try:
        guid = uuid.UUID('{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}')            # FOLDERID_Desktop
        buffer = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(ctypes.create_string_buffer(guid.bytes_le, 16)), 0, None, ctypes.byref(buffer))
        if result == 0 and buffer.value:
            path = Path(buffer.value)
            ctypes.windll.ole32.CoTaskMemFree(buffer)
            if path.is_dir():
                return path
    except Exception:
        pass
    fallback = Path.home() / 'Desktop'
    return fallback if fallback.is_dir() else None


def create_shortcut(workspace: Path, desktop: Path | None = None) -> bool:
    """바탕화면에 `자동화 업무` 바로가기를 만든다. 이미 있거나 만들지 못하면 False (실패해도 기능은 계속된다)."""
    desktop = desktop or desktop_dir()
    if not desktop:
        return False
    link = Path(desktop) / f'{FOLDER_NAME}.lnk'
    if link.exists() or (Path(desktop) / FOLDER_NAME).exists():
        return False
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    script = ('$s=(New-Object -ComObject WScript.Shell).CreateShortcut(' + quote(link) + '); '
              '$s.TargetPath=' + quote(workspace) + '; $s.Save()')
    try:
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                       timeout=20, creationflags=CREATE_NO_WINDOW, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return False
    return link.exists()
