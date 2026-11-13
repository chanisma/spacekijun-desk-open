"""자동화 업무 폴더 — 스킬 설치·갱신·상태, 원격 제어 인자, 데스크 액션 (2026-10-22 요청). 터미널·바로가기는 진짜로 만들지 않는다."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명·설정 파일에는 절대 닿지 않는다
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop
from core import agent, automation
from desktop import DesktopAPI


def make_skill(root: Path, name: str = 'demo', body: str = '안내', meta: dict | None = None) -> Path:
    folder = Path(root) / name
    (folder / 'scripts').mkdir(parents=True, exist_ok=True)
    (folder / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: {name} 설명입니다.\n---\n# {name}\n{body}\n', encoding='utf-8')
    (folder / 'scripts' / 'run.ps1').write_text('Write-Host ok', encoding='utf-8')
    if meta is not None:
        (folder / 'skill.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    return folder


class Room(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.root = Path(self.room.name)
        self.source = self.root / 'source'
        self.workspace = self.root / '자동화 업무'
        self.source.mkdir()


class CatalogTests(Room):
    def test_catalog_reads_title_summary_and_needs(self):
        make_skill(self.source, 'send', meta={'title': '쪽지 보내기', 'summary': '쪽지를 씁니다.', 'sensitive': True,
                                              'needs': [{'program': 'node', 'label': 'Node 22'}, 'broken', {'label': 'x'}]})
        make_skill(self.source, 'plain')                                   # skill.json 이 없으면 SKILL.md 에서 읽는다
        (self.source / 'notes').mkdir()                                    # SKILL.md 가 없는 폴더는 스킬이 아니다
        found = {item['name']: item for item in automation.catalog(self.source)}
        self.assertEqual(sorted(found), ['plain', 'send'])
        self.assertEqual(found['send']['title'], '쪽지 보내기')
        self.assertEqual(found['send']['summary'], '쪽지를 씁니다.')
        self.assertTrue(found['send']['sensitive'])
        self.assertEqual([need['program'] for need in found['send']['needs']], ['node'])
        self.assertEqual(found['plain']['title'], 'plain')
        self.assertIn('plain 설명', found['plain']['summary'])

    def test_groups_are_read_and_their_actions_counted(self):
        """기능별 묶음 (2026-11-05) — 묶음 안의 일도 actions 에 들어가 개수·즐겨찾기가 그대로 돈다."""
        make_skill(self.source, 'mcp', meta={
            'actions': [{'label': '밖', 'prompt': '밖의 일'}],
            'groups': [{'label': '일정', 'summary': '일정을 다룹니다.', 'actions': [{'label': '보기', 'prompt': '일정 보기'}, {'label': 'x'}]},
                       {'summary': '이름 없는 묶음'}, 'broken'],
            'keep': ['references/memory', '../out', '/abs', 3]})
        skill = automation.catalog(self.source)[0]
        self.assertEqual(skill['groups'], [{'label': '일정', 'summary': '일정을 다룹니다.', 'actions': [{'label': '보기', 'prompt': '일정 보기'}]}])
        self.assertEqual([a['label'] for a in skill['actions']], ['밖', '보기'])
        self.assertEqual(skill['keep'], ['references/memory'])

    def test_shipped_skill_cards_are_well_formed(self):
        """실린 스킬 카드 — 즐겨찾기가 이름으로 가리키므로 한 스킬 안에서 일 이름이 겹치지 않는다."""
        for skill in automation.catalog():
            labels = [a['label'] for a in skill['actions']]
            self.assertEqual(len(labels), len(set(labels)), skill['name'])
        shipped = {skill['name']: skill for skill in automation.catalog()}
        self.assertGreaterEqual(len(shipped['spacekijun-mcp']['groups']), 15)
        self.assertEqual(shipped['saenggibu-writer']['keep'], ['references/memory'])
        memory = automation.resource_dir() / 'saenggibu-writer' / 'references' / 'memory'
        self.assertEqual(sorted(p.name for p in memory.iterdir()), ['INDEX.md', '인공지능기초.md'])   # 원작자의 과목 메모리는 싣지 않는다

    def test_long_summary_is_cut(self):
        make_skill(self.source, 'long', meta={'summary': '가' * 300})
        self.assertLessEqual(len(automation.catalog(self.source)[0]['summary']), 120)

    def test_digest_follows_content_and_ignores_our_marker_and_caches(self):
        folder = make_skill(self.source, 'a')
        first = automation.digest(folder)
        (folder / automation.MANAGED).write_text('{}', encoding='utf-8')
        (folder / '__pycache__').mkdir()
        (folder / '__pycache__' / 'x.pyc').write_bytes(b'1')
        self.assertEqual(automation.digest(folder), first)
        (folder / 'scripts' / 'run.ps1').write_text('Write-Host changed', encoding='utf-8')
        self.assertNotEqual(automation.digest(folder), first)

    def test_the_skills_we_ship_are_complete(self):
        shipped = {item['name']: item for item in automation.catalog()}
        self.assertIn('coolmessenger-send', shipped)
        skill = shipped['coolmessenger-send']
        self.assertTrue((skill['path'] / 'send-message.ps1').is_file())
        self.assertFalse((skill['path'] / 'install.ps1').exists(), '데스크가 직접 깐다 — install.ps1 은 싣지 않는다')
        self.assertIn('node', [need['program'] for need in skill['needs']])
        edufine = shipped['edufine']                                                       # 에듀파인 (2026-10-26)
        self.assertTrue((edufine['path'] / 'scripts' / 'edufine.js').is_file())
        self.assertTrue((edufine['path'] / 'scripts' / 'draft.ps1').is_file())
        self.assertFalse((edufine['path'] / 'node_modules').exists())
        self.assertTrue(edufine['sensitive'])
        self.assertIn('node', [need['program'] for need in edufine['needs']])
        neis = shipped['neis']                                                             # 나이스 조회 (2026-10-26)
        self.assertTrue((neis['path'] / 'scripts' / 'neis.js').is_file())
        self.assertTrue((neis['path'] / 'knowledge' / 'catalog.json').is_file())
        self.assertFalse((neis['path'] / 'node_modules').exists())
        self.assertTrue(neis['sensitive'])


class InstallTests(Room):
    def test_installs_into_both_agent_folders_and_writes_the_guides(self):
        make_skill(self.source, 'a')
        result = automation.install(self.workspace, self.source)
        self.assertEqual(result[0]['states'], {'.claude/skills': 'installed', '.agents/skills': 'installed'})
        for target in ('.claude', '.agents'):
            self.assertTrue((self.workspace / target / 'skills' / 'a' / 'SKILL.md').is_file())
            self.assertTrue((self.workspace / target / 'skills' / 'a' / 'scripts' / 'run.ps1').is_file())
            self.assertTrue((self.workspace / target / 'skills' / 'a' / automation.MANAGED).is_file())
        self.assertIn('보내기 전에 초안', (self.workspace / 'AGENTS.md').read_text(encoding='utf-8'))
        self.assertEqual((self.workspace / 'CLAUDE.md').read_text(encoding='utf-8'), '@AGENTS.md\n')

    def test_guides_are_not_overwritten(self):
        make_skill(self.source, 'a')
        self.workspace.mkdir()
        (self.workspace / 'AGENTS.md').write_text('내가 쓴 안내', encoding='utf-8')
        automation.install(self.workspace, self.source)
        self.assertEqual((self.workspace / 'AGENTS.md').read_text(encoding='utf-8'), '내가 쓴 안내')

    def test_again_is_current_and_a_changed_skill_is_updated(self):
        folder = make_skill(self.source, 'a')
        automation.install(self.workspace, self.source)
        self.assertEqual(set(automation.install(self.workspace, self.source)[0]['states'].values()), {'current'})
        (folder / 'scripts' / 'run.ps1').write_text('Write-Host v2', encoding='utf-8')
        (folder / 'scripts' / 'new.ps1').write_text('new', encoding='utf-8')
        self.assertEqual(set(automation.install(self.workspace, self.source)[0]['states'].values()), {'updated'})
        installed = self.workspace / '.claude' / 'skills' / 'a' / 'scripts'
        self.assertEqual((installed / 'run.ps1').read_text(encoding='utf-8'), 'Write-Host v2')
        self.assertTrue((installed / 'new.ps1').is_file())

    def test_a_skill_the_user_made_with_the_same_name_is_left_alone(self):
        make_skill(self.source, 'a')
        mine = make_skill(self.workspace / '.claude' / 'skills', 'a', body='내가 만든 것')
        result = automation.install(self.workspace, self.source)[0]['states']
        self.assertEqual(result['.claude/skills'], 'foreign')
        self.assertEqual(result['.agents/skills'], 'installed')
        self.assertIn('내가 만든 것', (mine / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('직접 만든', automation.summary(automation.install(self.workspace, self.source)))

    def test_retired_skill_we_installed_is_removed_but_the_users_own_stays(self):
        # 카카오톡 스킬 폐기 (2026-11-08) — 옛 판이 깐 것은 깔 때 빼고, 사용자가 만든 같은 이름은 그대로
        make_skill(self.source, 'kakaotalk')
        automation.install(self.workspace, self.source)
        mine = make_skill(self.workspace / '.agents' / 'skills', 'kakaotalk', body='내가 만든 것')
        (mine / automation.MANAGED).unlink()
        empty = self.workspace / 'none'
        empty.mkdir()
        automation.install(self.workspace, empty)
        self.assertFalse((self.workspace / '.claude' / 'skills' / 'kakaotalk').exists())
        self.assertIn('내가 만든 것', (mine / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertIn('kakaotalk', automation.RETIRED)
        self.assertNotIn('kakaotalk', {skill['name'] for skill in automation.catalog()})

    def test_status_tells_missing_outdated_current_and_foreign(self):
        folder = make_skill(self.source, 'a')
        self.assertEqual(automation.status(self.workspace, self.source)[0]['state'], 'missing')
        automation.install(self.workspace, self.source)
        self.assertEqual(automation.status(self.workspace, self.source)[0]['state'], 'current')
        (folder / 'scripts' / 'run.ps1').write_text('Write-Host v2', encoding='utf-8')
        self.assertEqual(automation.status(self.workspace, self.source)[0]['state'], 'outdated')
        (self.workspace / '.agents' / 'skills' / 'a' / automation.MANAGED).unlink()
        self.assertEqual(automation.status(self.workspace, self.source)[0]['state'], 'foreign')

    def test_summary_text(self):
        make_skill(self.source, 'a')
        self.assertEqual(automation.summary(automation.install(self.workspace, self.source)), '설치했습니다.')
        self.assertEqual(automation.summary(automation.install(self.workspace, self.source)), '이미 최신입니다.')
        (self.source / 'a' / 'SKILL.md').write_text('---\nname: a\n---\nv2\n', encoding='utf-8')
        self.assertIn('갱신', automation.summary(automation.install(self.workspace, self.source)))

    def test_workspace_must_be_an_absolute_path(self):
        with self.assertRaises(ValueError):
            automation.ensure_workspace(Path('상대/경로'))

    def test_requirements_only_report(self):
        make_skill(self.source, 'a', meta={'needs': [{'program': 'node', 'label': 'Node'},
                                                     {'program': 'python', 'label': 'Py', 'optional': True}]})
        with patch('shutil.which', side_effect=lambda name, path=None: r'C:\n\node.exe' if name == 'node' else None):
            needs = automation.requirements(automation.catalog(self.source)[0])
        self.assertEqual([(n['program'], n['found'], n['optional']) for n in needs],
                         [('node', True, False), ('python', False, True)])


    def test_update_keeps_the_dependencies_the_skill_downloaded(self):
        folder = make_skill(self.source, 'a')
        (folder / 'node_modules' / 'x').mkdir(parents=True)                               # 정본 쪽 것은 싣지 않는다
        (folder / 'node_modules' / 'x' / 'index.js').write_text('src', encoding='utf-8')
        automation.install(self.workspace, self.source)
        installed = self.workspace / '.claude' / 'skills' / 'a'
        self.assertFalse((installed / 'node_modules').exists())
        (installed / 'node_modules' / 'playwright').mkdir(parents=True)                  # 사용자가 npm install 로 받은 것
        (installed / 'node_modules' / 'playwright' / 'index.js').write_text('pw', encoding='utf-8')
        (folder / 'scripts' / 'run.ps1').write_text('Write-Host v2', encoding='utf-8')
        self.assertEqual(automation.install(self.workspace, self.source)[0]['states']['.claude/skills'], 'updated')
        self.assertEqual((installed / 'node_modules' / 'playwright' / 'index.js').read_text(encoding='utf-8'), 'pw')
        self.assertEqual((installed / 'scripts' / 'run.ps1').read_text(encoding='utf-8'), 'Write-Host v2')
        self.assertEqual(sorted(p.name for p in installed.parent.iterdir()), ['a'])        # 옆으로 옮긴 것이 남지 않는다
        (installed / 'node_modules' / 'playwright' / 'more.js').write_text('1', encoding='utf-8')
        self.assertEqual(automation.status(self.workspace, self.source)[0]['state'], 'current')   # 받은 것은 판 비교에 안 든다

    def test_update_keeps_what_the_user_built_up(self):
        """skill.json keep (2026-11-05) — 생기부 과목 메모리처럼 쓰면서 쌓은 하위 폴더는 새 판으로 바꿔도 남는다."""
        folder = make_skill(self.source, 'a', meta={'keep': ['references/memory']})
        (folder / 'references' / 'memory').mkdir(parents=True)
        (folder / 'references' / 'memory' / 'INDEX.md').write_text('shipped', encoding='utf-8')
        automation.install(self.workspace, self.source)
        installed = self.workspace / '.claude' / 'skills' / 'a'
        self.assertEqual((installed / 'references' / 'memory' / 'INDEX.md').read_text(encoding='utf-8'), 'shipped')
        (installed / 'references' / 'memory' / 'INDEX.md').write_text('mine', encoding='utf-8')
        (installed / 'references' / 'memory' / '정보.md').write_text('정보 지시', encoding='utf-8')
        (folder / 'SKILL.md').write_text('---\nname: a\n---\nv2', encoding='utf-8')
        self.assertEqual(automation.install(self.workspace, self.source)[0]['states']['.claude/skills'], 'updated')
        self.assertIn('v2', (installed / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertEqual((installed / 'references' / 'memory' / 'INDEX.md').read_text(encoding='utf-8'), 'mine')
        self.assertEqual((installed / 'references' / 'memory' / '정보.md').read_text(encoding='utf-8'), '정보 지시')
        self.assertEqual(sorted(p.name for p in installed.parent.iterdir()), ['a'])


class ShortcutTests(Room):
    def test_creates_one_shortcut_and_leaves_existing_ones(self):
        desktop_folder = self.root / 'Desktop'
        desktop_folder.mkdir()

        def fake_run(args, **kwargs):
            (desktop_folder / f'{automation.FOLDER_NAME}.lnk').write_text('lnk')

        with patch('subprocess.run', side_effect=fake_run) as run:
            self.assertTrue(automation.create_shortcut(self.workspace, desktop_folder))
            self.assertFalse(automation.create_shortcut(self.workspace, desktop_folder))      # 이미 있다
        self.assertEqual(run.call_count, 1)
        self.assertIn("'" + str(self.workspace) + "'", run.call_args.args[0][-1])

    def test_a_folder_with_that_name_on_the_desktop_is_respected(self):
        desktop_folder = self.root / 'Desktop'
        (desktop_folder / automation.FOLDER_NAME).mkdir(parents=True)
        with patch('subprocess.run') as run:
            self.assertFalse(automation.create_shortcut(self.workspace, desktop_folder))
        run.assert_not_called()

    def test_failure_is_quiet(self):
        desktop_folder = self.root / 'Desktop'
        desktop_folder.mkdir()
        with patch('subprocess.run', side_effect=OSError('x')):
            self.assertFalse(automation.create_shortcut(self.workspace, desktop_folder))
        self.assertFalse(automation.create_shortcut(self.workspace, None) if automation.desktop_dir() is None else False)


class RemoteTests(Room):
    def test_remote_control_is_added_only_for_claude_and_cleaned(self):
        self.assertEqual(agent.launcher_text(r'C:\n\claude.cmd', False, 'claude', '자동화 업무'),
                         '@echo off\r\ncall "C:\\n\\claude.cmd" --remote-control "자동화 업무"\r\n')
        self.assertEqual(agent.launcher_text(r'C:\n\claude.cmd', True, 'claude', '자동화 업무'),
                         '@echo off\r\ncall "C:\\n\\claude.cmd" --remote-control "자동화 업무" --dangerously-skip-permissions\r\n')
        self.assertNotIn('remote', agent.launcher_text(r'C:\n\codex.cmd', False, 'codex', '자동화 업무'))
        self.assertNotIn('remote', agent.launcher_text(r'C:\n\claude.cmd', False, 'claude'))
        evil = agent.launcher_text(r'C:\n\claude.cmd', False, 'claude', 'a" & calc & "%PATH%^')
        self.assertNotIn('calc &', evil)
        self.assertNotIn('%PATH%', evil)
        self.assertEqual(evil.count('"'), 4)

    def test_extra_arguments_for_codex(self):
        text = agent.launcher_text(r'C:\n\codex.cmd', False, 'codex', '', ('--sandbox', 'danger-full-access'))
        self.assertEqual(text, '@echo off\r\ncall "C:\\n\\codex.cmd" --sandbox danger-full-access\r\n')

    def test_old_claude_without_the_flag_is_detected(self):
        exe = self.root / 'claude.cmd'
        exe.write_text('@echo off', encoding='utf-8')
        agent._remote_cache.clear()

        class Done:
            def __init__(self, text): self.stdout, self.stderr = text, ''

        with patch('subprocess.run', return_value=Done('  --remote-control [name]  Start with Remote Control')) as run:
            self.assertTrue(agent.remote_supported(str(exe)))
            self.assertTrue(agent.remote_supported(str(exe)))             # 기억한다 — 다시 묻지 않는다
        self.assertEqual(run.call_count, 1)
        agent._remote_cache.clear()
        with patch('subprocess.run', return_value=Done('Usage: claude [options]')):
            self.assertFalse(agent.remote_supported(str(exe)))
        agent._remote_cache.clear()
        with patch('subprocess.run', side_effect=OSError('x')):
            self.assertFalse(agent.remote_supported(str(exe)))
            self.assertEqual(agent._remote_cache, {})                     # 못 알아낸 것은 기억하지 않는다
        self.assertFalse(agent.remote_supported(str(self.root / '없음.cmd')))

    def test_launch_connects_remote_control_only_when_supported(self):
        folder = self.root / 'work'
        folder.mkdir()
        data = self.root / 'data'
        for supported, name, shown in ((True, 'claude-auto.cmd', '원격 제어 연결'), (False, 'claude.cmd', '')):
            with patch.object(agent, 'find', return_value=r'C:\n\claude.cmd'), \
                 patch.object(agent, 'remote_supported', return_value=supported), \
                 patch('shutil.which', return_value=None), patch.object(agent, 'spawn'):
                message = agent.launch('claude', str(folder), False, data, '자동화 업무')
            script = (data / 'agent' / name).read_text(encoding='oem')
            self.assertEqual('--remote-control' in script, supported)
            self.assertEqual('원격 제어 연결' in message, bool(shown))

    def test_the_korean_name_reaches_the_program_through_cmd(self):
        """실행기를 진짜 cmd 로 돌려 한글 세션 이름이 깨지지 않고 인자 하나로 가는지 본다."""
        import subprocess
        fake = self.root / 'fake-claude.cmd'
        fake.write_text('@echo off\r\necho ARGS=%*\r\n', encoding='oem')
        script = self.root / 'run.cmd'
        script.write_text(agent.launcher_text(str(fake), True, 'claude', automation.RC_NAME), encoding='oem')
        done = subprocess.run(['cmd.exe', '/c', str(script)], capture_output=True, text=True, encoding='oem', timeout=30)
        self.assertIn('ARGS=--remote-control "자동화 업무" --dangerously-skip-permissions', done.stdout)

    def test_a_code_page_without_korean_falls_back_to_an_english_name(self):
        folder = self.root / 'work'
        folder.mkdir()
        real = str.encode

        def no_korean(text, encoding='utf-8', errors='strict'):
            if encoding == 'oem' and any(ord(ch) > 0x2FF for ch in text):
                raise UnicodeEncodeError('oem', text, 0, 1, 'no korean')
            return real(text, encoding, errors)

        with patch.object(agent, 'find', return_value=r'C:\n\claude.cmd'), patch.object(agent, 'remote_supported', return_value=True), \
             patch('shutil.which', return_value=None), patch.object(agent, 'spawn'), \
             patch.object(agent, 'launcher_text', wraps=agent.launcher_text) as text:
            with patch.object(Path, 'write_text'):                       # 파일은 쓰지 않는다 — 어떤 이름으로 만들었는지만 본다
                class Probe(str):
                    def encode(self, encoding='utf-8', errors='strict'):
                        return no_korean(str(self), encoding, errors)
                agent.launch('claude', str(folder), False, self.root / 'data', Probe(automation.RC_NAME))
        self.assertEqual(text.call_args.args[3], 'Desk')

    def test_launch_without_remote_still_uses_the_plain_launcher(self):
        folder = self.root / 'work'
        folder.mkdir()
        with patch.object(agent, 'find', return_value=r'C:\n\claude.cmd'), patch('shutil.which', return_value=None), \
             patch.object(agent, 'spawn'):
            agent.launch('claude', str(folder), False, self.root / 'data')
        self.assertTrue((self.root / 'data' / 'agent' / 'claude.cmd').is_file())
        self.assertFalse((self.root / 'data' / 'agent' / 'claude-auto.cmd').exists())


class DesktopTests(Room):
    def setUp(self):
        super().setUp()
        self.api = DesktopAPI()
        self.api._preferences_path = self.root / 'desktop-preferences.json'
        self.api._save_preferences(automation_folder=str(self.workspace), agent_embed=False)   # 바깥 터미널 경로를 본다
        make_skill(self.source, 'a', meta={'title': '시험 스킬'})
        for patcher in (patch.object(automation, 'resource_dir', return_value=self.source),
                        patch.object(automation, 'create_shortcut', return_value=True),
                        patch.object(agent, 'launch', return_value='열었습니다'),
                        patch.object(agent, 'find', return_value=r'C:\n\claude.cmd')):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.launch = agent.launch

    def test_open_installs_then_opens_claude_with_remote_control_by_default(self):
        self.assertTrue(self.api.call('automation_open')['ok'])
        self.assertTrue((self.workspace / '.claude' / 'skills' / 'a' / 'SKILL.md').is_file())
        self.assertTrue((self.workspace / '.agents' / 'skills' / 'a' / 'SKILL.md').is_file())
        args = self.launch.call_args.args
        self.assertEqual(args[:3], ('claude', str(self.workspace), False))
        self.assertEqual(args[4:], (automation.RC_NAME, ()))

    def test_remote_control_can_be_turned_off_and_stays_off(self):
        self.assertTrue(self.api.call('automation_settings', {'rc': False})['ok'])
        self.api.call('automation_open')
        self.assertEqual(self.launch.call_args.args[4], '')
        self.assertFalse(self.api.call('automation_settings', {'rc': 'no'})['ok'])
        self.assertFalse(self.api.call('automation_settings', {})['ok'])

    def test_codex_opens_without_the_sandbox_but_keeps_approvals(self):
        self.api.call('agent_settings', {'tool': 'codex'})
        self.api.call('automation_open')
        args = self.launch.call_args.args
        self.assertEqual(args[0], 'codex')
        self.assertEqual(args[4:], ('', ('--sandbox', 'danger-full-access')))
        self.api.call('agent_settings', {'skip': True})            # 권한 묻지 않기는 이미 샌드박스도 끈다 — 겹치지 않는다
        self.api.call('automation_open')
        self.assertEqual(self.launch.call_args.args[4:], ('', ()))

    def test_state_shows_folder_skills_and_which_agent_has_remote_control(self):
        state = self.api.call('automation_state')['data']
        self.assertEqual(state['folder'], str(self.workspace))
        self.assertFalse(state['exists'])
        self.assertTrue(state['rc'] and state['rcTool'])
        self.assertEqual(state['skills'][0]['state'], 'missing')
        self.assertEqual(state['skills'][0]['title'], '시험 스킬')
        self.api.call('automation_install')
        self.assertEqual(self.api.call('automation_state')['data']['skills'][0]['state'], 'current')
        self.api.call('agent_settings', {'tool': 'codex'})
        self.assertFalse(self.api.call('automation_state')['data']['rcTool'])

    def test_install_reports_what_happened(self):
        self.assertEqual(self.api.call('automation_install')['data'], '설치했습니다.')
        self.assertEqual(self.api.call('automation_install')['data'], '이미 최신입니다.')

    def test_a_skill_switched_off_is_removed_and_stays_off(self):
        """패널의 스킬 스위치 (2026-10-22): 끄면 빼고, 열거나 갱신해도 다시 깔지 않는다. 켜면 그것만 깐다."""
        make_skill(self.source, 'b', meta={'title': '둘째 스킬'})
        self.api.call('automation_install')
        self.assertTrue(self.api.call('automation_skill', {'name': 'a', 'on': False})['ok'])
        for target in ('.claude', '.agents'):
            self.assertFalse((self.workspace / target / 'skills' / 'a').exists())
            self.assertTrue((self.workspace / target / 'skills' / 'b').exists())
        self.api.call('automation_open')
        self.api.call('automation_install')
        self.assertFalse((self.workspace / '.claude' / 'skills' / 'a').exists())   # 꺼 둔 채로
        rows = {row['name']: row for row in self.api.call('automation_state')['data']['skills']}
        self.assertEqual((rows['a']['on'], rows['a']['state']), (False, 'missing'))
        self.assertEqual((rows['b']['on'], rows['b']['state']), (True, 'current'))
        self.assertIn('설치했습니다', self.api.call('automation_skill', {'name': 'a', 'on': True})['data'])
        self.assertTrue((self.workspace / '.agents' / 'skills' / 'a' / 'SKILL.md').is_file())
        self.assertTrue(self.api.call('automation_state')['data']['skills'][0]['on'])
        for bad in ({'name': 'zz', 'on': True}, {'name': 'a', 'on': 'yes'}, {'name': '../a', 'on': False}, {}):
            self.assertFalse(self.api.call('automation_skill', bad)['ok'], bad)

    def test_switching_off_leaves_a_skill_the_user_made_alone(self):
        own = self.workspace / '.claude' / 'skills' / 'a'
        own.mkdir(parents=True)
        (own / 'SKILL.md').write_text('내 스킬', encoding='utf-8')
        self.api.call('automation_skill', {'name': 'a', 'on': False})
        self.assertTrue((own / 'SKILL.md').is_file())
        self.assertIn('직접 만든', self.api.call('automation_skill', {'name': 'a', 'on': True})['data'])

    def test_default_folder_is_in_the_home_not_on_the_synced_desktop(self):
        self.api._save_preferences(automation_folder='상대/경로')
        self.assertEqual(self.api._automation_folder(), automation.default_workspace())
        self.assertEqual(automation.default_workspace(), Path.home() / automation.FOLDER_NAME)
        self.assertNotIn('Desktop', automation.default_workspace().parts)

    def test_students_cannot_use_it(self):
        for action in ('automation_state', 'automation_open', 'automation_install', 'automation_settings', 'automation_skill',
                       'automation_prepare'):
            self.assertNotIn(action, desktop.STUDENT_ACTIONS)
            self.assertIn(action, self.api._handlers())
        with patch.object(desktop.edition, 'STUDENT', True):
            self.assertFalse(self.api.call('automation_open')['ok'])
        self.launch.assert_not_called()


class FakeProcess:
    """설치 창 흉내 — 끝나는 때와 종료 코드를 시험이 정한다."""
    def __init__(self):
        import threading
        self.done, self.code = threading.Event(), None

    def finish(self, code):
        self.code = code
        self.done.set()

    def poll(self):
        return self.code if self.done.is_set() else None

    def wait(self):
        self.done.wait(5)
        return self.code


class ProgramTests(Room):
    """켜 둔 스킬이 쓰는데 없는 Node.js·Python 은 데스크가 깐다 (2026-10-22 요청)."""
    def test_missing_programs_follow_switched_on_skills_only(self):
        make_skill(self.source, 'a', meta={'needs': [{'program': 'python', 'optional': True}, {'program': 'node'}]})
        make_skill(self.source, 'b', meta={'needs': [{'program': 'git'}]})              # 데스크가 깔 줄 모르는 것은 빼고 알리기만
        with patch.object(automation, 'find_program', return_value=None):
            self.assertEqual(automation.missing_programs(self.workspace, source=self.source), ['node', 'python'])   # 늘 Node.js 먼저
            self.assertEqual(automation.missing_programs(self.workspace, skip={'a'}, source=self.source), [])
            needs = automation.status(self.workspace, self.source)[0]['needs']
            self.assertEqual([(n['program'], n['installable']) for n in needs], [('python', True), ('node', True)])
        with patch.object(automation, 'find_program', side_effect=lambda name: None if name == 'python' else 'x'):
            self.assertEqual(automation.missing_programs(self.workspace, source=self.source), ['python'])

    def test_the_store_placeholder_is_not_python(self):
        placeholder = r'C:\Users\t\AppData\Local\Microsoft\WindowsApps\python.exe'

        class Done:
            def __init__(self, code, out):
                self.returncode, self.stdout, self.stderr = code, out, ''
        store = 'Python was not found; run without arguments to install from the Microsoft Store'
        with patch('shutil.which', return_value=placeholder), patch('subprocess.run', return_value=Done(9009, store)):
            self.assertIsNone(automation.find_program('python'))
        with patch('shutil.which', return_value=placeholder), patch('subprocess.run', return_value=Done(0, 'Python 3.13.1')):
            self.assertEqual(automation.find_program('python'), placeholder)                # Python 설치 관리자면 진짜
        with patch('shutil.which', return_value=r'C:\Program Files\Python\python.exe'), patch('subprocess.run') as run:
            self.assertTrue(automation.find_program('python'))
        run.assert_not_called()                                                          # 보통 자리는 돌려 보지 않는다

    def test_python_installed_after_the_desk_started_is_found(self):
        """데스크가 뜰 때 PATH 에는 WindowsApps 자리표시자만, 새로 깐 Python 은 레지스트리 PATH 에만 있다 (2026-10-27 보고)."""
        store = self.root / 'Microsoft' / 'WindowsApps'
        real = self.root / 'Programs' / 'Python' / 'Python312'
        for folder in (store, real):
            folder.mkdir(parents=True)
            (folder / 'python.exe').write_bytes(b'')

        class Done:
            def __init__(self, code, out):
                self.returncode, self.stdout, self.stderr = code, out, ''
        with patch.dict(os.environ, {'PATH': str(store)}), patch.object(agent, '_registry_path', return_value=[str(real), str(store)]), \
                patch('subprocess.run', return_value=Done(9009, 'Python was not found')):
            self.assertEqual(Path(automation.find_program('python')).parent, real)
            path = agent.search_path().split(';')
            self.assertLess(path.index(str(real)), path.index(str(store)))                # 에이전트 터미널의 python 도 진짜가 먼저

    def test_a_node_that_dies_in_korean_folders_counts_as_missing(self):
        """Node 22.11 은 한글 폴더의 .js 를 읽다 죽는다(0xC0000005) — 자동화 업무 폴더에서는 없는 것과 같다 (2026-10-26)."""
        class Done:
            def __init__(self, code): self.returncode, self.stdout, self.stderr = code, b'', b''
        old = r'C:\Program Files\nodejs\node.exe'
        automation._node_checked.clear()
        self.addCleanup(automation._node_checked.clear)
        with patch('shutil.which', return_value=old), patch('subprocess.run', return_value=Done(3221225477)) as run:
            self.assertIsNone(automation.find_program('node'))
            self.assertIsNone(automation.find_program('node'))                           # 기억한다 — 다시 돌리지 않는다
        self.assertEqual(run.call_count, 1)
        probe = Path(run.call_args.args[0][1])
        self.assertIn(automation.KOREAN_PROBE, str(probe))                                # 한글 폴더에서 돌려 본다
        self.assertTrue(probe.is_file())
        automation._node_checked.clear()
        make_skill(self.source, 'a', meta={'needs': [{'program': 'node', 'label': 'Node.js 22 이상'}]})
        with patch('shutil.which', return_value=old), patch('subprocess.run', return_value=Done(-1073741819)):
            need = automation.requirements(automation.catalog(self.source)[0])[0]
        self.assertFalse(need['found'])
        self.assertTrue(need['installable'])                                              # 데스크가 새 판을 깐다
        self.assertIn('한글 폴더', need['label'])
        automation._node_checked.clear()
        with patch('shutil.which', return_value=old), patch('subprocess.run', return_value=Done(0)):
            self.assertEqual(automation.find_program('node'), old)
        automation._node_checked.clear()
        with patch('shutil.which', return_value=old), patch('subprocess.run', side_effect=OSError('x')):
            self.assertEqual(automation.find_program('node'), old)                        # 판단 못 하면 막지 않는다

    def test_node_installed_by_the_desk_comes_first(self):
        local = self.root / 'local'
        (local / 'Programs' / 'nodejs').mkdir(parents=True)
        with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}):
            self.assertFalse(agent.search_path().lower().startswith(str(local).lower()))  # 깔지 않았으면 그대로
            (local / 'Programs' / 'nodejs' / 'node.exe').write_bytes(b'')
            self.assertTrue(agent.search_path().lower().startswith(str(local / 'Programs' / 'nodejs').lower()))

    def test_install_script_needs_no_admin_and_checks_what_it_downloads(self):
        text = automation.prepare_text(['node', 'python'], then='곧 에이전트를 엽니다.')
        self.assertIn("'https://nodejs.org/dist/index.json'", text)
        self.assertIn('SHASUMS256.txt', text)                                             # Node.js zip 확인값
        self.assertIn("'Path', 'User'", text)                                             # 사용자 PATH 에만
        self.assertIn('--scope user', text)
        self.assertIn("'Python Software Foundation'", text)                              # 대체 설치 파일 서명
        self.assertIn('InstallAllUsers=0', text)
        self.assertNotIn('RunAs', text)
        self.assertNotIn('—', text)                                                       # 한국어 콘솔이 못 그린다
        self.assertLess(text.index('Node.js 설치'), text.index('Python 3 설치'))
        self.assertIn(automation.KOREAN_PROBE, text)                                      # 깐 Node 도 한글 폴더에서 돌려 본다
        self.assertIn('곧 에이전트를 엽니다.', text)
        for bad in ([], ['git'], ['node', 'rm -rf']):
            with self.assertRaises(ValueError):
                automation.prepare_text(bad)


class PrepareDesktopTests(Room):
    """필요한 프로그램이 없는 PC — DesktopTests 와 같은 데스크에서 (그 시험들을 물려받지 않게 따로 둔다)."""
    def setUp(self):
        super().setUp()
        self.api = DesktopAPI()
        self.api._preferences_path = self.root / 'desktop-preferences.json'
        self.api._save_preferences(automation_folder=str(self.workspace), agent_embed=False)   # 바깥 터미널 경로를 본다
        for patcher in (patch.object(automation, 'resource_dir', return_value=self.source),
                        patch.object(automation, 'create_shortcut', return_value=True),
                        patch.object(agent, 'launch', return_value='열었습니다'),
                        patch.object(agent, 'find', return_value=r'C:\n\claude.cmd')):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.launch = agent.launch
        make_skill(self.source, 'a', meta={'title': '시험 스킬', 'needs': [{'program': 'node', 'label': 'Node.js 22 이상'}]})
        self.processes = []

        def start(programs, work_dir, then=''):
            self.processes.append((FakeProcess(), programs, then))
            return self.processes[-1][0]
        for patcher in (patch.object(automation, 'find_program', return_value=None),
                        patch.object(automation, 'prepare', side_effect=start)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def wait_for_thread(self):
        import threading
        import time
        for _ in range(100):
            if not any(t.name == 'automation-prepare' for t in threading.enumerate()):
                return
            time.sleep(0.02)

    def test_open_installs_missing_programs_first_then_opens_the_agent(self):
        message = self.api.call('automation_open')['data']
        self.assertIn('Node.js', message)
        self.assertIn('에이전트를 엽니다', message)
        self.launch.assert_not_called()                                                  # 아직 — 새 PATH 를 못 본다
        self.assertEqual(self.processes[0][1], ['node'])
        self.assertEqual(self.api.call('automation_state')['data']['preparing'], ['Node.js'])
        self.assertIn('이미 열려', self.api.call('automation_open')['data'])                # 설치 창은 하나만
        self.assertEqual(len(self.processes), 1)
        self.processes[0][0].finish(0)
        self.wait_for_thread()
        self.launch.assert_called_once()
        self.assertEqual(self.api.call('automation_state')['data']['preparing'], [])

    def test_a_failed_install_does_not_open_the_agent(self):
        self.api.call('automation_open')
        self.processes[0][0].finish(1)
        self.wait_for_thread()
        self.launch.assert_not_called()

    def test_switching_a_skill_on_installs_its_programs_without_opening(self):
        self.api.call('automation_skill', {'name': 'a', 'on': False})
        self.assertEqual(self.processes, [])                                             # 끈 스킬 것은 깔지 않는다
        message = self.api.call('automation_skill', {'name': 'a', 'on': True})['data']
        self.assertIn('설치 창을 열었습니다', message)
        self.processes[0][0].finish(0)
        self.wait_for_thread()
        self.launch.assert_not_called()
        self.assertIn('설치 창', self.api.call('automation_prepare')['data'])           # 지금 설치 단추

    def test_nothing_to_install(self):
        with patch.object(automation, 'find_program', return_value='C:\\x.exe'):
            self.assertEqual(self.api.call('automation_prepare')['data'], '필요한 프로그램이 모두 있습니다.')
            self.api.call('automation_open')
        self.assertEqual(self.processes, [])
        self.launch.assert_called_once()

if __name__ == '__main__':
    unittest.main()
