"""카카오톡 기능 폐기 (2026-11-08) — 옛 테스트 판(1.3.66~1.3.70)이 남긴 계정·로그인·도구·스킬을 켤 때 치운다."""
from test_sandbox import use_sandbox
use_sandbox()
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop
from core import automation, secretstore


class RetireTests(unittest.TestCase):
    def setUp(self):
        room = tempfile.TemporaryDirectory()
        self.addCleanup(room.cleanup)
        self.room = Path(room.name)
        self.config, self.local, self.work = self.room / 'config', self.room / 'local', self.room / 'work'
        env = patch.dict(os.environ, {'AGENT_MESSENGER_CONFIG_DIR': str(self.config), 'LOCALAPPDATA': str(self.local)})
        env.start()
        self.addCleanup(env.stop)
        self.api = desktop.DesktopAPI()
        self.api._automation_folder = lambda: self.work
        self.addCleanup(secretstore.clear)                            # 다른 시험이 빈 저장소를 기대한다

    def test_leftovers_are_removed_and_other_logins_kept(self):
        secretstore.save({'riro_id': 'me', 'riro_password': 'pw', 'kakao_id': 'a@b.kr', 'kakao_password': 'x'})
        self.config.mkdir()
        (self.config / 'kakaotalk-credentials.json').write_text('{}', encoding='utf-8')
        (self.config / 'kakaotalk-sync-state-1.json').write_text('{}', encoding='utf-8')
        (self.config / 'slack-credentials.json').write_text('{}', encoding='utf-8')     # 다른 메신저 것은 그대로
        (self.local / 'KakaoTalkSkill' / 'cli').mkdir(parents=True)
        for target in automation.TARGETS:
            skill = self.work.joinpath(*target.split('/')) / 'kakaotalk'
            skill.mkdir(parents=True)
            (skill / automation.MANAGED).write_text(json.dumps({'name': 'kakaotalk', 'digest': 'old'}), encoding='utf-8')
        logs = []
        self.api._log = lambda *parts: logs.append(' '.join(map(str, parts)))
        self.api._retire_kakao()
        self.assertEqual(secretstore.load(), {'riro_id': 'me', 'riro_password': 'pw'})
        self.assertEqual(sorted(path.name for path in self.config.iterdir()), ['slack-credentials.json'])
        self.assertFalse((self.local / 'KakaoTalkSkill').exists())
        self.assertFalse((self.work / '.claude' / 'skills' / 'kakaotalk').exists())
        self.assertIn('SM-T870', logs[0])
        logs.clear()
        self.api._retire_kakao()                                      # 두 번째부터는 할 일이 없다 — 알리지 않는다
        self.assertEqual(logs, [])

    def test_settings_and_actions_have_no_kakao(self):
        self.assertFalse(any(name.startswith('kakao') for name in self.api._handlers()))


if __name__ == '__main__':
    unittest.main()
