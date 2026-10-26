import tempfile
import unittest
from pathlib import Path
from tools.prepare_cloud import prepare_environment


class CloudPreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        (self.root / 'tmp').mkdir(exist_ok=True)

    def test_writes_private_environment_for_verified_network(self):
        with tempfile.TemporaryDirectory(dir=self.root / 'tmp') as directory:
            root = Path(directory)
            root.resolve().relative_to(self.root.resolve())
            prepare_environment(root, 'actual-network')
            fields = dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines())
            self.assertEqual(fields['DOMAIN'], 'dt.riskai93.cn')
            self.assertEqual(fields['CADDY_NETWORK'], 'actual-network')
            self.assertEqual(len(fields['SECRET_KEY']), 64)
            self.assertNotEqual(fields['SECRET_KEY'], fields['POSTGRES_PASSWORD'])

    def test_never_overwrites_existing_environment(self):
        with tempfile.TemporaryDirectory(dir=self.root / 'tmp') as directory:
            root = Path(directory)
            root.resolve().relative_to(self.root.resolve())
            (root / '.env').write_text('existing-settings')
            with self.assertRaises(FileExistsError):
                prepare_environment(root, 'actual-network')
            self.assertEqual((root / '.env').read_text(), 'existing-settings')

    def test_rejects_invalid_network_name(self):
        with tempfile.TemporaryDirectory(dir=self.root / 'tmp') as directory:
            root = Path(directory)
            root.resolve().relative_to(self.root.resolve())
            with self.assertRaises(ValueError):
                prepare_environment(root, 'name\nINJECT=value')
            self.assertFalse((root / '.env').exists())
