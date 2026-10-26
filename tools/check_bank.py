"""Offline validation of enabled question contracts and bank metadata."""
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / '.deps')]
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from practice.models import Question

records = json.loads((ROOT / 'data/questions.json').read_text(encoding='utf-8'))
errors = []
fields = {f.name for f in Question._meta.fields} - {'id', 'updated_at'}
for record in records:
    if record['enabled']:
        question = Question(**{k: v for k, v in record.items() if k in fields})
        try:
            question.clean()
        except Exception as exc:
            errors.append({'uid': record['uid'], 'error': str(exc)})
print(json.dumps({'total': len(records), 'enabled': sum(q['enabled'] for q in records), 'enabled_by_category': dict(Counter(q['category'] for q in records if q['enabled'])), 'validation_errors': errors}, ensure_ascii=False, indent=2))
raise SystemExit(bool(errors))
