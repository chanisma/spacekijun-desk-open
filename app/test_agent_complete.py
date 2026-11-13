"""입력칸 자동 완성 (2026-11-08 요청) — / 명령 목록과 @ 파일 찾기."""
from test_sandbox import use_sandbox
use_sandbox()
import json
import tempfile
import unittest
from pathlib import Path

from core import agent_complete


def write(path: Path, text: str = ''):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


class CommandTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.home, self.folder = Path(room.name) / 'home', Path(room.name) / 'work'
        self.folder.mkdir(parents=True)
        agent_complete._commands.clear()

    def names(self, tool='claude'):
        return {row['name']: row for row in agent_complete.commands(tool, str(self.folder), home=self.home)}

    def test_builtin_custom_skill_and_plugin(self):
        write(self.home / '.claude/commands/daily.md', '---\ndescription: 오늘 할 일 정리\n---\n본문')
        write(self.folder / '.claude/commands/neis/grade.md', '# 성적 확인\n본문')
        write(self.folder / '.claude/skills/riro/SKILL.md', '---\nname: riroschool-sms\ndescription: "리로스쿨 문자"\n---\n')
        write(self.home / '.claude/skills/hidden/SKILL.md', '---\nname: hidden\nuser-invocable: false\n---\n')
        plugin = self.home / 'plugins/sb'
        write(plugin / 'skills/supabase/SKILL.md', '---\nname: supabase\ndescription: DB\n---\n')
        write(plugin / 'commands/deploy.md', '---\ndescription: 배포\n---\n')
        off = self.home / 'plugins/off'
        write(off / 'commands/nope.md', 'x')
        write(self.home / '.claude/plugins/installed_plugins.json', json.dumps({'version': 2, 'plugins': {
            'supabase@market': [{'scope': 'user', 'installPath': str(plugin)}],
            'off@market': [{'scope': 'user', 'installPath': str(off)}],
            'local@market': [{'scope': 'project', 'projectPath': 'D:\\elsewhere', 'installPath': str(off)}]}}))
        write(self.home / '.claude/settings.json', json.dumps({'enabledPlugins': {'supabase@market': True}}))
        found = self.names()
        self.assertEqual(found['daily']['desc'], '오늘 할 일 정리')
        self.assertEqual(found['neis:grade']['desc'], '성적 확인')
        self.assertEqual(found['riroschool-sms']['kind'], 'skill')
        self.assertNotIn('hidden', found)
        self.assertIn('supabase:supabase', found)
        self.assertIn('supabase:deploy', found)
        self.assertFalse(any(name.startswith('off:') for name in found))
        self.assertEqual(found['clear']['kind'], 'builtin')

    def test_codex_prompts(self):
        write(self.home / '.codex/prompts/weekly.md', '주간 정리')
        found = self.names('codex')
        self.assertIn('prompts:weekly', found)
        self.assertIn('new', found)
        self.assertNotIn('clear', found)


class FileTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.folder = Path(room.name)
        for name in ('성적/2학기 성적.xlsx', '성적/1학기.xlsx', 'notes.txt', 'node_modules/x/index.js', '.git/HEAD', 'deep/a/b/report.md'):
            write(self.folder / name, 'x')
        agent_complete._files.clear()

    def paths(self, query):
        return [row['path'] for row in agent_complete.files(str(self.folder), query)]

    def test_name_match_first_and_heavy_dirs_skipped(self):
        self.assertEqual(self.paths('2학기')[0], '성적/2학기 성적.xlsx')
        self.assertIn('성적/', self.paths('성적'))
        self.assertEqual(self.paths('rep'), ['deep/a/b/report.md'])
        self.assertEqual(self.paths('index'), [])
        self.assertEqual(self.paths('HEAD'), [])

    def test_fuzzy_and_empty_query(self):
        self.assertIn('notes.txt', self.paths('nts'))
        self.assertEqual(set(self.paths('')[:3]), {'성적/', 'deep/', 'notes.txt'})   # 얕은 것부터
        self.assertEqual(agent_complete.files(str(self.folder / 'none'), 'x'), [])


class DesktopTests(unittest.TestCase):
    def test_action_is_registered_for_both_editions(self):
        import desktop
        self.assertIn('term_complete', desktop.DesktopAPI()._handlers())
        self.assertIn('term_complete', desktop.STUDENT_ACTIONS)


if __name__ == '__main__':
    unittest.main()
