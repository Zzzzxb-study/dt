import tempfile
from pathlib import Path
from django.conf import settings
from django.test import Client, SimpleTestCase, override_settings


class ProductionStaticTests(SimpleTestCase):
    def test_collected_css_served_behind_existing_proxy(self):
        root = Path(settings.BASE_DIR) / 'tmp'
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            Path(directory).resolve().relative_to(root.resolve())
            css = Path(directory) / 'practice/app.css'
            css.parent.mkdir()
            css.write_text('body { color: #2d3142; }', encoding='utf-8')
            with override_settings(DEBUG=False, STATIC_ROOT=directory, ALLOWED_HOSTS=['testserver']):
                response = Client().get('/static/practice/app.css', secure=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn('text/css', response['Content-Type'])
                self.assertEqual(b''.join(response.streaming_content), css.read_bytes())
