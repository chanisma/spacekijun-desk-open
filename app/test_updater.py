"""자동 업데이트 — 서명 확인·조각 받기·실행 파일 바꾸기·되돌리기 (2026-10-13). 네트워크·진짜 실행 파일 없이."""
from test_sandbox import use_sandbox
use_sandbox()          # 진짜 자격증명·설정 파일에는 절대 닿지 않는다
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import desktop
from core import ed25519, edition, updater
from desktop import DesktopAPI

SEED = bytes(range(32))
KEY = ed25519.public_key(SEED)
EXE = Path('C:/Desk/SpacekijunDesk.exe')


def signed(manifest, seed=SEED):
    return {'manifest': manifest, 'signature': ed25519.sign(seed, updater.canonical(manifest)).hex()}


def release(version, data, part_size=7):
    pieces = [data[at:at + part_size] for at in range(0, len(data), part_size)]
    parts = [{'name': f'SpacekijunDesk.exe.part{index + 1}', 'size': len(piece),
              'sha256': hashlib.sha256(piece).hexdigest()} for index, piece in enumerate(pieces)]
    manifest = {'app': 'SpacekijunDesk', 'version': version, 'size': len(data),
                'sha256': hashlib.sha256(data).hexdigest(), 'parts': parts, 'published': '2026-10-13T00:00:00+00:00'}
    files = {f'{updater.PUBLIC_URL}/{version}/{part["name"]}': piece for part, piece in zip(parts, pieces)}
    return manifest, files


class SignatureTests(unittest.TestCase):
    def test_rfc8032_vectors(self):
        secret = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
        self.assertEqual(ed25519.public_key(secret).hex(),
                         'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
        signature = ed25519.sign(secret, b'')
        self.assertEqual(signature.hex(), 'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f'
                                          'b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
        self.assertTrue(ed25519.verify(ed25519.public_key(secret), b'', signature))
        self.assertFalse(ed25519.verify(ed25519.public_key(secret), b'x', signature))
        second = bytes.fromhex('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb')
        self.assertEqual(ed25519.sign(second, b'\x72').hex(),
                         '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da'
                         '085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00')

    def test_manifest_must_be_signed_by_our_key_and_well_formed(self):
        manifest, _ = release('1.3.1', b'new desk exe bytes')
        self.assertEqual(updater.check_manifest(signed(manifest), KEY)['version'], '1.3.1')
        with self.assertRaisesRegex(updater.UpdateError, '서명'):
            updater.check_manifest(signed(manifest, bytes(32)), KEY)            # 다른 키
        tampered = signed(manifest)
        tampered['manifest'] = {**manifest, 'sha256': '0' * 64}
        with self.assertRaisesRegex(updater.UpdateError, '서명'):
            updater.check_manifest(tampered, KEY)
        for bad in ({**manifest, 'app': 'Other'}, {**manifest, 'version': '1.3.x'},
                    {**manifest, 'size': manifest['size'] + 1},
                    {**manifest, 'parts': [{**manifest['parts'][0], 'name': '..\\evil.exe'}] + manifest['parts'][1:]}):
            with self.assertRaises(updater.UpdateError):
                updater.check_manifest(signed(bad), KEY)
        with self.assertRaises(updater.UpdateError):
            updater.check_manifest({'manifest': manifest}, KEY)

    def test_versions_compare_as_numbers(self):
        self.assertTrue(updater.newer('1.10.0', '1.9.9'))
        self.assertFalse(updater.newer('1.3.0', '1.3.0'))
        self.assertFalse(updater.newer('1.2.9', '1.3.0'))
        with self.assertRaises(updater.UpdateError):
            updater.newer('latest', '1.0')

    def test_the_shipped_public_key_is_set(self):
        self.assertNotEqual(updater.PUBLIC_KEY, bytes(32))
        self.assertEqual(len(updater.PUBLIC_KEY), 32)


class DownloadAndSwapTests(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.root = Path(self.room.name)
        self.folder = self.root / 'update'
        self.data = b'MZ new desk build ' * 5
        self.manifest, self.files = release('1.3.1', self.data)

    def fetch(self, url, timeout=60):
        return self.files[url]

    def test_download_joins_checks_and_records(self):
        record = updater.download(self.manifest, self.folder, self.fetch)
        self.assertEqual(Path(record['path']).read_bytes(), self.data)
        self.assertEqual(updater.pending(self.folder, '1.3.0')['version'], '1.3.1')
        self.assertIsNone(updater.pending(self.folder, '1.3.1'))           # 이미 그 판이다
        Path(record['path']).write_bytes(b'tampered')
        self.assertIsNone(updater.pending(self.folder, '1.3.0'))           # 받아 둔 파일이 바뀌었다

    def test_a_bad_part_is_refused_and_nothing_is_left(self):
        first = next(iter(self.files))
        self.files[first] = b'X' * len(self.files[first])
        with self.assertRaisesRegex(updater.UpdateError, '조각'):
            updater.download(self.manifest, self.folder, self.fetch)
        self.assertEqual(list(self.folder.iterdir()), [])
        self.assertIsNone(updater.pending(self.folder, '1.3.0'))

    def test_the_old_build_only_starts_the_new_one_in_install_mode(self):
        exe = self.root / 'app' / 'SpacekijunDesk.exe'
        exe.parent.mkdir()
        exe.write_bytes(b'old build')
        record = updater.download(self.manifest, self.folder, self.fetch)
        with patch.object(updater.child, 'spawn') as spawn:
            updater.start_install(record, exe, ['--dock'], [11, 22])
        args = spawn.call_args.args[0]
        self.assertEqual(args, [record['path'], '--install-update', str(exe), '--wait', '11,22', '--then', '--dock'])
        self.assertEqual(exe.read_bytes(), b'old build')            # 🚨 옛것은 제 실행 파일에 손대지 않는다
        Path(record['path']).write_bytes(b'tampered')
        with patch.object(updater.child, 'spawn') as spawn, self.assertRaises(updater.UpdateError):
            updater.start_install(record, exe, [], [1])
        spawn.assert_not_called()

    def test_install_mode_waits_overwrites_and_starts_the_new_build(self):
        target = self.root / 'SpacekijunDesk.exe'
        target.write_bytes(b'old build')
        source = self.root / 'update' / 'SpacekijunDesk-1.3.1.exe'
        source.parent.mkdir()
        source.write_bytes(self.data)
        argv = ['--install-update', str(target), '--wait', '11,22', '--then', '--dock']
        with patch.object(updater, 'wait_for') as wait, patch.object(updater, 'relaunch') as relaunch, \
             patch.object(updater.sys, 'executable', str(source)):
            updater.install_main(argv, self.folder)
        self.assertEqual([call.args[0] for call in wait.call_args_list], [11, 22])
        self.assertEqual(target.read_bytes(), self.data)
        relaunch.assert_called_once_with(target, ['--dock', '--after-update'])

    def test_install_mode_retries_while_the_old_exe_is_held_then_gives_the_old_one_back(self):
        target = self.root / 'SpacekijunDesk.exe'
        target.write_bytes(b'old build')
        source = self.root / 'new.exe'
        source.write_bytes(self.data)
        real_replace, calls = os.replace, []

        def held_twice(src, dst):
            calls.append(dst)
            if len(calls) <= 2:
                raise PermissionError('옛것의 부트로더가 아직 잡고 있다')
            return real_replace(src, dst)
        with patch('os.replace', side_effect=held_twice):
            updater.install(source, target, tries=5, delay=0)
        self.assertEqual(target.read_bytes(), self.data)
        target.write_bytes(b'old build')
        with patch('os.replace', side_effect=PermissionError('잠김')), \
             patch.object(updater, 'relaunch') as relaunch, patch.object(updater, 'install',
                                                                       side_effect=updater.UpdateError('잠김')):
            updater.install_main(['--install-update', str(target), '--then', '--autostart'], self.folder)
        relaunch.assert_called_once_with(target, ['--autostart'])     # 옛것을 그대로 다시 띄운다
        self.assertIn('잠김', (self.folder / 'install-error.log').read_text(encoding='utf-8'))
        self.assertFalse((self.root / 'SpacekijunDesk.new.exe').exists())

    def test_finish_and_sweep_clean_up_with_retries(self):
        exe = self.root / 'SpacekijunDesk.exe'
        exe.write_bytes(b'new')
        (self.root / 'SpacekijunDesk.old.exe').write_bytes(b'old')     # 예전 방식이 남긴 것
        record = updater.download(self.manifest, self.folder, self.fetch)
        with patch('threading.Thread') as thread:
            updater.finish(exe, self.folder)
        self.assertFalse((self.folder / 'pending.json').exists())    # 다시 설치하지 않게 바로
        self.assertIs(thread.call_args.kwargs['target'], updater.sweep)
        self.assertTrue(updater.sweep(exe, None))                    # 켤 때 — 받아 둔 것은 남긴다
        self.assertTrue(Path(record['path']).exists())
        real_unlink, calls = Path.unlink, []

        def held_once(path, *args, **kwargs):
            calls.append(path.name)
            if len(calls) == 1:
                raise PermissionError('설치 모드 껍데기가 아직 잡고 있다')
            return real_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', held_once):
            self.assertTrue(updater.sweep(exe, self.folder, tries=3, delay=0))
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ['SpacekijunDesk.exe', 'update'])
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_installable_needs_a_writable_exe(self):
        exe = self.root / 'SpacekijunDesk.exe'
        exe.write_bytes(b'x')
        self.assertTrue(updater.installable(exe))
        self.assertFalse(updater.installable(self.root / 'missing.exe'))
        self.assertFalse(updater.installable())                   # 소스에서 돌 때는 쓰지 않는다
        # Program Files 처럼 ACL 로 막힌 폴더 — 한 번에 False (tempfile 은 여기서 TMP_MAX 번 다시 해 멈췄다)
        with patch.object(updater.os, 'open', side_effect=PermissionError('막힘')) as probe:
            self.assertFalse(updater.installable(exe))
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ['SpacekijunDesk.exe'])   # 시험 파일을 남기지 않는다

    def test_checker_downloads_once_and_hands_it_over(self):
        document = signed(self.manifest)
        files = {**self.files}

        def fetch(url, timeout=60):
            return json.dumps(document).encode() if 'latest.json' in url else files[url]
        ready = []
        with patch.object(updater, 'PUBLIC_KEY', KEY):
            checker = updater.Checker('1.3.0', self.folder, ready.append, lambda *a: None, fetch)
            self.assertEqual(checker.check_once()['version'], '1.3.1')
            files.clear()                                         # 두 번째는 받아 둔 것을 쓴다
            checker.check_once()
            self.assertEqual(len(ready), 2)
            self.assertIsNone(updater.Checker('1.3.1', self.root / 'other', ready.append,
                                              lambda *a: None, fetch).check_once())




class TestChannelTests(unittest.TestCase):
    """관리자만 받는 테스트 판 (2026-10-30 요청) — 정식·테스트 통로 중 더 새 판을, 테스트 통로가 없어도 정식은 그대로."""
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.folder = Path(self.room.name) / 'update'
        self.files = {}
        patcher = patch.object(updater, 'PUBLIC_KEY', KEY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def publish(self, channel, version):
        data = f'MZ {channel} {version} '.encode() * 4
        manifest, files = release(version, data)
        base = updater.channel_url(channel)
        self.files.update({url.replace(updater.PUBLIC_URL, base): piece for url, piece in files.items()})
        self.files[f'{base}/latest.json'] = json.dumps(signed(manifest)).encode()
        return data

    def fetch(self, url, timeout=60):
        url = url.split('?')[0]
        if url not in self.files:
            raise OSError('404')
        return self.files[url]

    def check(self, channels):
        got = []
        checker = updater.Checker('1.3.40', self.folder, got.append, lambda *a: None, fetch=self.fetch, channels=lambda: channels)
        checker.check_once()
        return got

    def test_the_newer_of_stable_and_test_is_taken(self):
        self.publish('teacher', '1.3.41')
        test_data = self.publish('teacher-test', '1.3.42')
        [record] = self.check(['teacher', 'teacher-test'])
        self.assertEqual(record['version'], '1.3.42')
        self.assertEqual(Path(record['path']).read_bytes(), test_data)

    def test_only_stable_without_the_test_channel_and_a_missing_test_channel_is_fine(self):
        self.publish('teacher', '1.3.41')
        self.publish('teacher-test', '1.3.42')
        self.assertEqual(self.check(['teacher'])[0]['version'], '1.3.41')
        (self.folder / 'pending.json').unlink()
        del self.files[f'{updater.channel_url("teacher-test")}/latest.json']
        self.assertEqual(self.check(['teacher', 'teacher-test'])[0]['version'], '1.3.41')


class TestChannelDeskTests(unittest.TestCase):
    def setUp(self):
        self.api = DesktopAPI()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.api._preferences_path = Path(folder.name) / 'prefs.json'

    def test_only_admins_can_turn_it_on_and_then_both_channels_are_checked(self):
        with patch('core.supa_auth.my_role', return_value='teacher'):
            self.assertFalse(self.api.call('update_test', {'on': True})['ok'])
            self.assertEqual(self.api._update_channels(), ['teacher'])
            self.assertFalse(self.api._update_status()['admin'])
        self.api._role_cache = None
        with patch('core.supa_auth.my_role', return_value='admin'):
            self.assertTrue(self.api.call('update_test', {'on': True})['ok'])
            self.assertEqual(self.api._update_channels(), ['teacher', 'teacher-test'])
            self.assertTrue(self.api._update_status()['test'])

    def test_the_student_edition_has_its_own_test_channel_for_admins(self):
        """학생판도 관리자 계정이면 테스트 판을 받는다 (2026-11-04 요청) — 통로는 student-test, 학생 계정은 못 켠다."""
        updater.use(True)
        self.addCleanup(updater.use, False)
        self.assertEqual(updater.TEST_CHANNEL, 'student-test')
        with patch.object(edition, 'STUDENT', True):
            with patch('core.supa_auth.my_role', return_value='student'):
                self.assertFalse(self.api.call('update_test', {'on': True})['ok'])
                self.assertEqual(self.api._update_channels(), ['student'])
                self.assertFalse(self.api._update_status()['admin'])
            self.api._role_cache = None
            with patch('core.supa_auth.my_role', return_value='admin'):
                self.assertTrue(self.api.call('update_test', {'on': True})['ok'])
                self.assertEqual(self.api._update_channels(), ['student', 'student-test'])
                self.assertTrue(self.api._update_status()['test'])
        updater.use(True, test=True)
        self.assertTrue(updater.PUBLIC_URL.endswith('/desk-releases/student-test'))
        self.assertTrue(updater.PART.match('SpacekijunStudent.exe.part1'))


class StudentCopyTests(unittest.TestCase):
    """학생판 자동 업데이트 (2026-10-16) — 채널, 사용자 사본에 놓기, 입구의 넘겨주기."""
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.root = Path(self.room.name)
        self.copy = self.root / 'data' / 'app' / 'SpacekijunStudent.exe'
        self.installed = self.root / 'Program Files' / 'SpacekijunStudent.exe'
        self.installed.parent.mkdir()
        self.installed.write_bytes(b'intune build')
        updater.use(True)
        self.addCleanup(updater.use, False)
        patcher = patch.object(updater, 'user_copy', return_value=self.copy)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_channel_and_part_names_follow_the_edition(self):
        self.assertTrue(updater.PUBLIC_URL.endswith('/desk-releases/student'))
        self.assertTrue(updater.PART.match('SpacekijunStudent.exe.part1'))
        self.assertFalse(updater.PART.match('SpacekijunDesk.exe.part1'))
        manifest, _ = release('1.0.6', b'student build')
        with self.assertRaisesRegex(updater.UpdateError, '다른 프로그램'):
            updater.check_manifest(signed(manifest), KEY)        # 교사판 목록은 학생판이 받지 않는다
        updater.use(False)
        self.assertTrue(updater.PUBLIC_URL.endswith('/desk-releases/teacher'))

    def test_install_mode_creates_the_copy_and_records_its_version(self):
        source = self.root / 'update' / 'SpacekijunStudent-1.0.6.exe'
        source.parent.mkdir()
        source.write_bytes(b'student 1.0.6')
        argv = ['--install-update', str(self.copy), '--wait', '1', '--fallback', str(self.installed), '--then', '--autostart']
        with patch.object(updater, 'wait_for'), patch.object(updater, 'relaunch') as relaunch,              patch.object(updater.sys, 'executable', str(source)), patch.object(updater.edition, 'VERSION', '1.0.6'):
            updater.install_main(argv, self.root / 'update')
        self.assertEqual(self.copy.read_bytes(), b'student 1.0.6')
        relaunch.assert_called_once_with(self.copy, ['--autostart', '--after-update'])
        self.assertEqual(json.loads(self.copy.with_name('version.json').read_text(encoding='utf-8'))['version'], '1.0.6')
        with patch.object(updater, 'install', side_effect=updater.UpdateError('막힘')),              patch.object(updater, 'relaunch') as relaunch, patch.object(updater, 'wait_for'):
            self.copy.unlink()
            updater.install_main(argv, self.root / 'update')
        relaunch.assert_called_once_with(self.installed, ['--autostart'])      # 못 놓으면 지금 것을 다시
        self.assertFalse(self.copy.with_name('version.json').exists())

    def test_start_install_passes_the_fallback_before_then(self):
        record = {'path': str(self.installed), 'sha256': hashlib.sha256(b'intune build').hexdigest()}
        with patch.object(updater.child, 'spawn') as spawn:
            updater.start_install(record, self.copy, ['--autostart'], [5], self.installed)
        self.assertEqual(spawn.call_args.args[0][3:], ['--wait', '5', '--fallback', str(self.installed),
                                                       '--then', '--autostart'])

    def test_handoff_runs_a_newer_copy_and_drops_a_stale_one(self):
        self.copy.parent.mkdir(parents=True)
        self.copy.write_bytes(b'student 1.0.7')
        mark = self.copy.with_name('version.json')

        def note(version, data=b'student 1.0.7'):
            mark.write_text(json.dumps({'version': version, 'size': len(data),
                                        'sha256': hashlib.sha256(data).hexdigest()}), encoding='utf-8')
        with patch.object(updater.sys, 'executable', str(self.installed)):
            self.assertIsNone(updater.handoff('1.0.6'))                         # 표식이 없다 (놓는 중)
            note('1.0.7')
            self.assertEqual(updater.handoff('1.0.6'), self.copy)
            with patch.object(updater.sys, 'executable', str(self.copy)):
                self.assertIsNone(updater.handoff('1.0.6'))                     # 사본 자신
            note('1.0.7', b'other bytes')
            self.assertIsNone(updater.handoff('1.0.6'))                         # 내용이 표식과 다르다
            self.assertTrue(self.copy.exists())
            note('1.0.7')
            self.assertIsNone(updater.handoff('1.0.7'))                         # Intune 이 같은 판을 깔았다
        self.assertFalse(self.copy.exists() or mark.exists())


class DeskUpdateTests(unittest.TestCase):
    def setUp(self):
        self.api = DesktopAPI()

    def test_source_runs_never_self_update(self):
        for student in (False, True):
            with patch.object(desktop.edition, 'STUDENT', student), patch.object(updater, 'Checker') as checker:
                self.api._start_updates()
                self.assertFalse(self.api._update_at_start([]))
            checker.assert_not_called()

    def test_student_installed_read_only_updates_into_its_own_copy(self):
        """학생판 (2026-10-16) — Intune 의 Program Files 에는 못 쓰니 사용자 사본에 놓고, 못 놓으면 지금 것을 다시 띄운다."""
        copy = Path('C:/Users/s/AppData/Local/SpacekijunStudent/app/SpacekijunStudent.exe')
        installed = 'C:/Program Files/Spacekijun Student/SpacekijunStudent.exe'
        record = {'version': '9.9.9'}
        updater.use(True)
        self.addCleanup(updater.use, False)
        with patch.object(desktop.edition, 'STUDENT', True), patch.object(updater.sys, 'frozen', True, create=True),              patch.object(updater.sys, 'executable', installed), patch.object(updater, 'installable', return_value=False),              patch.object(updater, 'user_copy', return_value=copy),              patch.object(updater, 'pending', return_value=record), patch.object(updater, 'start_install') as start, patch.object(DesktopAPI, '_ask_update', return_value=True):
            self.assertEqual(updater.target(), copy)
            self.assertTrue(self.api._update_at_start(['--autostart']))
        self.assertEqual(start.call_args.args[1], copy)
        self.assertEqual(start.call_args.args[4], Path(installed))
        with patch.object(desktop.edition, 'STUDENT', False), patch.object(updater.sys, 'frozen', True, create=True),              patch.object(updater, 'installable', return_value=False):
            self.assertIsNone(updater.target())                   # 교사판은 못 쓰는 곳이면 그대로

    def test_busy_work_blocks_an_update_while_running(self):
        with patch.object(DesktopAPI, '_dock_form', return_value=None):
            self.assertEqual(self.api._update_busy(), '')
            self.api._portals.add('neis')
            self.assertIn('로그인', self.api._update_busy())
            self.api._portals.clear()
            self.api._service_windows['riro'] = object()
            self.assertIn('창', self.api._update_busy())

    def test_apply_now_starts_the_installer_then_quits(self):
        quit_app = []
        self.api._update = {'version': '9.9.9', 'path': 'x', 'sha256': '0' * 64, 'size': 1}
        self.api._quit_for_update = lambda: quit_app.append(True)
        with patch.object(updater, 'start_install') as start, patch.object(updater, 'target', return_value=EXE):
            self.assertTrue(self.api._apply_update_now())
        self.assertEqual(start.call_args.args[2], ['--autostart'])
        self.assertEqual(start.call_args.args[3], updater.own_pids())
        self.assertEqual(quit_app, [True])

    def test_failed_install_start_keeps_running(self):
        quit_app = []
        self.api._update = {'version': '9.9.9'}
        self.api._quit_for_update = lambda: quit_app.append(True)
        with patch.object(updater, 'start_install', side_effect=updater.UpdateError('다름')):
            self.api._apply_update_now()
        self.assertEqual(quit_app, [])
        self.assertIsNone(self.api._update)

    def test_start_with_a_pending_update_hands_over_and_stops(self):
        record = {'version': '9.9.9'}
        with patch.object(updater, 'installable', return_value=True), \
             patch.object(updater, 'pending', return_value=record), \
             patch.object(updater, 'start_install') as start, patch.object(DesktopAPI, '_ask_update', return_value=True):
            self.assertTrue(self.api._update_at_start(['--dock']))
        self.assertEqual(start.call_args.args[2], ['--dock'])
        with patch.object(updater, 'installable', return_value=True), patch.object(updater, 'finish') as finish, \
             patch.object(updater, 'start_install') as start:
            self.assertFalse(self.api._update_at_start(['--autostart', '--after-update']))
        finish.assert_called_once()
        start.assert_not_called()

    def test_start_asks_first_and_no_keeps_this_version(self):
        """켤 때마다 묻는다 (2026-10-26 요청) — «아니요»면 지금 판으로 켜고, 켜 둔 동안 같은 판은 다시 묻지 않는다."""
        record = {'version': '9.9.9'}
        with patch.object(updater, 'installable', return_value=True), patch.object(updater, 'pending', return_value=record), \
             patch.object(updater, 'start_install') as start, patch.object(DesktopAPI, '_ask_update', return_value=False) as ask:
            self.assertFalse(self.api._update_at_start(['--autostart']))
        ask.assert_called_once_with('9.9.9')
        start.assert_not_called()
        with patch.object(desktop.threading, 'Thread') as thread:
            self.api._update_ready(record)
        thread.assert_not_called()

    def test_a_download_found_while_running_asks_once_and_yes_applies(self):
        record = {'version': '9.9.9', 'path': 'x', 'sha256': '0' * 64, 'size': 1}
        with patch.object(desktop.threading, 'Thread') as thread:
            self.api._update_ready(record)
            self.api._update_ready(record)                          # 6시간 뒤 같은 판 — 다시 묻지 않는다
        self.assertEqual(thread.call_count, 1)
        self.assertEqual(self.api._update, record)
        self.api._quit_for_update = lambda: None
        with patch.object(DesktopAPI, '_ask_update', return_value=True), \
             patch.object(DesktopAPI, '_apply_update_now') as apply:
            self.api._update_prompt(record)
        apply.assert_called_once_with(then=['--dock'])
        with patch.object(DesktopAPI, '_ask_update', return_value=False), \
             patch.object(DesktopAPI, '_apply_update_now') as apply:
            self.api._update_prompt(record)
        apply.assert_not_called()

    def test_a_manual_check_does_not_pop_a_question(self):
        record = {'version': '9.9.9'}
        with patch.object(desktop.threading, 'Thread') as thread:
            self.api._update_job = desktop.threading.current_thread()
            self.api._update_ready(record)
        thread.assert_not_called()
        self.assertEqual(self.api._update, record)

    def test_checks_right_after_start_and_retries_soon_while_offline(self):
        with patch.object(updater, 'installable', return_value=True), patch.object(updater, 'sweep'), \
             patch.object(updater.Checker, 'start'):
            self.api._start_updates()
        self.assertEqual(self.api._updater.first, desktop.UPDATE_FIRST)
        self.assertLessEqual(desktop.UPDATE_FIRST, 10)
        waits = []

        class Stop:
            def wait(self, seconds):
                waits.append(seconds)
                return len(waits) > updater.SOON_TRIES + 1
        checker = updater.Checker('1.0.0', Path('.'), lambda r: None, lambda *a: None, first=5)
        checker._stop = Stop()
        with patch.object(updater.Checker, 'check_once', side_effect=OSError('offline')):
            checker._run()
        self.assertEqual(waits[0], 5)
        self.assertEqual(waits[1:updater.SOON_TRIES + 1], [updater.RETRY_SOON] * updater.SOON_TRIES)
        self.assertEqual(waits[updater.SOON_TRIES + 1], updater.RETRY)

    def test_manual_check_downloads_in_the_background_and_reports(self):
        record = {'version': '9.9.9', 'path': 'x', 'sha256': '0' * 64, 'size': 1}
        self.assertFalse(self.api.call('update_check')['ok'])                 # 소스에서 돌 때는 못 한다
        self.assertFalse(self.api.call('update_status')['data']['available'])
        with patch.object(updater, 'installable', return_value=True),              patch.object(updater.Checker, 'check_once', return_value=None):
            self.assertTrue(self.api.call('update_check')['ok'])
            self.api._update_job.join(5)
            status = self.api.call('update_status')['data']
            self.assertEqual((status['checking'], status['ready']), (False, None))
            self.assertIn('최신', status['note'])
            # 다음 확인에서 새 판을 받으면 ready (진짜 Checker 는 on_ready 를 부른다) — 그다음 누르면 다시 받지 않는다
            def found():
                self.api._update = record
                return record
            with patch.object(updater.Checker, 'check_once', side_effect=found):
                self.api._update_check_run(self.api._updater)
            self.assertEqual(self.api.call('update_status')['data']['ready'], '9.9.9')
            self.api.call('update_check')
            self.assertFalse(self.api._update_job.is_alive())

    def test_manual_apply_waits_for_confirmation_when_busy_and_restarts_with_the_dock(self):
        self.assertFalse(self.api.call('update_apply')['ok'])                 # 받아 둔 판이 없다
        self.api._update = {'version': '9.9.9', 'path': 'x', 'sha256': '0' * 64, 'size': 1}
        self.api._quit_for_update = lambda: None
        self.api._portals.add('neis')
        with patch.object(desktop.threading, 'Timer') as timer:
            self.assertFalse(self.api.call('update_apply')['ok'])             # 하던 일이 있으면 한 번 더 묻는다
            timer.assert_not_called()
            self.assertTrue(self.api.call('update_apply', {'force': True})['ok'])
        self.assertEqual(timer.call_args.kwargs['kwargs'], {'then': ['--dock']})   # 새 판도 독만 (데스크 본창은 숨긴 채)
        with patch.object(updater, 'start_install') as start, patch.object(updater, 'target', return_value=EXE):
            self.api._apply_update_now(then=[])
        self.assertEqual(start.call_args.args[2], [])


if __name__ == '__main__':
    unittest.main()
