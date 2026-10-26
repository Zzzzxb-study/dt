import tempfile
import unittest
from pathlib import Path
from tools.connect_domain import update_configuration


class DomainConnectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        (self.root / 'tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.root / 'tmp')
        self.directory = Path(self.temp.name)
        self.directory.resolve().relative_to(self.root.resolve())
        self.path = self.directory / 'Caddyfile'
        self.original = b'old.example.com {\n    reverse_proxy old-app:8000\n}\n'
        self.path.write_bytes(self.original)

    def tearDown(self):
        self.temp.cleanup()

    def test_adds_new_site_and_preserves_old_config_and_inode(self):
        inode = self.path.stat().st_ino
        reloads = []
        backup = update_configuration(self.path, lambda data: None, lambda: reloads.append(True))
        result = self.path.read_bytes()
        self.assertTrue(result.startswith(self.original))
        self.assertIn(b'dt.riskai93.cn {', result)
        self.assertIn(b'reverse_proxy cjpractice15-app:8000', result)
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(self.path.stat().st_ino, inode)
        self.assertEqual(reloads, [True])

    def test_validation_failure_does_not_write_or_reload(self):
        def invalid(data):
            raise RuntimeError('validation failed')
        with self.assertRaisesRegex(RuntimeError, 'validation failed'):
            update_configuration(self.path, invalid, lambda: self.fail('must not reload'))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(list(self.directory.glob('*.backup-*')))

    def test_reload_failure_restores_original_and_reloads_old_config(self):
        calls = []
        def reload_config():
            calls.append(self.path.read_bytes())
            if len(calls) == 1:
                raise RuntimeError('reload failed')
        with self.assertRaisesRegex(RuntimeError, 'reload failed'):
            update_configuration(self.path, lambda data: None, reload_config)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1], self.original)

    def test_concurrent_edit_is_not_overwritten(self):
        changed = b'changed.example.com {\n respond 200\n}\n'
        def edit_during_validation(data):
            self.path.write_bytes(changed)
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            update_configuration(self.path, edit_during_validation, lambda: self.fail('must not reload'))
        self.assertEqual(self.path.read_bytes(), changed)
