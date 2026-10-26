"""Inspect extracted PDF content and the generated question bank."""
from pathlib import Path
import argparse
import json
import re
import sys

# Use the same pinned packages as manage.py, so PDF extraction and the
# exact-content regression checks do not depend on the host runtime.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.deps'))
from pypdf import PdfReader

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--match', default='')
    ap.add_argument('--tail', type=int, default=0)
    ap.add_argument('--bank', action='store_true')
    ap.add_argument('--page', type=int)
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--kind')
    ap.add_argument('--summary', action='store_true')
    ap.add_argument('--audit', action='store_true')
    args = ap.parse_args()
    root = Path(args.root)
    if args.audit:
        from collections import Counter
        records = json.loads((root / 'data/questions.json').read_text(encoding='utf-8'))
        print('OPTION COUNTS', Counter(len(q['options']) for q in records if q['kind'] in ('single','multiple')))
        print('ANSWER COUNTS', Counter((q['kind'], len(q['answer'])) for q in records))
        for q in records:
            reasons = []
            if len(q['stem']) < 6: reasons.append('short_stem')
            if q['kind'] != 'short' and len(q['stem']) > 1100: reasons.append('long_stem')
            if any(len(v) > 500 for v in q['options'].values()): reasons.append('long_option')
            if q['kind'] in ('single', 'multiple') and len(q['options']) not in (4,5): reasons.append('unusual_option_count')
            if q['kind'] == 'multiple' and len(q['answer']) < 2: reasons.append('single_key_in_multiple')
            if q['kind'] != 'short' and re.search(r'答案|解析|第\s*\d+\s*页|[—-]\s*\d+\s*[—-]', q['stem']): reasons.append('suspicious_stem')
            if q['category'] == 'nonauto' and re.search(r'健康险|健康保险|重疾险|重大疾病保险|医疗保险|疾病保险', q['stem']): reasons.append('possible_health_scope')
            if reasons:
                print(json.dumps(dict(reasons=reasons, **{k:q[k] for k in ('category','kind','source_number','source_page','stem','options','answer','issues')}), ensure_ascii=False))
        return
    if args.build:
        sys.path.insert(0, str(root.resolve()))
        from practice.importer import build_bank
        report = build_bank(root, root / 'data')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if args.bank:
        records = json.loads((root / 'data/questions.json').read_text(encoding='utf-8'))
        for q in records:
            if args.kind and args.kind != q['kind']: continue
            if not args.match or args.match in q['source_file'] or args.match in q['stem']:
                print(json.dumps({k:q[k] for k in ('source_file', 'kind', 'source_number','stem','options','answer','reference','explanation','issues')} if not args.summary else {k:q[k] for k in ('source_number','stem','issues')}, ensure_ascii=False))
        return
    for path in sorted(root.rglob('*.pdf')):
        if args.match and args.match not in str(path):
            continue
        reader = PdfReader(path)
        print('\nSOURCE', path, 'PAGES', len(reader.pages))
        texts = [p.extract_text() or '' for p in reader.pages]
        if args.page:
            print(texts[args.page - 1])
            continue
        text = '\n'.join(texts)
        if args.tail:
            print(text[-args.tail:])
        else:
            for index, page in enumerate(texts, 1):
                lines = page.splitlines()
                headings = [line for line in lines if re.search(r'单.*选|多.*选|判断|简答|问答', line) and len(line) < 65]
                starts = re.findall(r'^\s*(\d{1,3})[.．、]\s*(.*)', page, re.M)
                print('PAGE', index, 'HEADINGS', headings, 'STARTS', [n for n, _ in starts])
            print('FIRST', text[:1200])
            print('LAST', text[-3000:])

if __name__ == '__main__':
    main()
