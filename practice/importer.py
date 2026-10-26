"""Conservative, source-preserving importer for the five competition PDFs.

Answer text is separated before option parsing. Uncertain questions remain in
the export, with reasons, but are excluded from practice.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

START = re.compile(r'^\s*(\d{1,3})[.．、]\s*(.*)')
ANSWER = re.compile(r'【(?:正确答案|标准答案|答案|判断结果|参考答案[^】]*)】|(?<![\u4e00-\u9fff])(?:\*\*)?(?:正确答案|标准答案|参考答案|答案|答)(?:\s*[：:]|\s*(?=正确|错误|对|错|√|×|[A-H]))')
EXPLANATION = re.compile(r'【(?:解析|答案解析)】|(?:解析|分析)\s*[：:]')
PAREN = re.compile(r'[（(]\s*([A-H](?:[\s、,，.．]*[A-H])*[.．]?|正确|错误|对|错|√|✓|×|✕)\s*[）)]')
OPTION = re.compile(r'(?<![A-Za-z0-9])([A-H])(?:[ \t]*([.．、:：])[ \t]*|(?<!\S[A-H])([ \t]+)|(?<!\S[A-H])(?=[\u4e00-\u9fff]))', re.M)

def _kind_heading(line):
    compact = re.sub(r'\s+', '', line)
    if '...' in compact or re.search(r'^\d+[.．、]', compact):
        return None
    if not re.match(r'^(?:第[一二三四]部分|[一二三四][、.．])?(?:单项选择|单选|多项选择|多选|判断|简答|问答)', compact):
        return None
    if re.search(r'单项选择|单选', compact): return 'single'
    if re.search(r'多项选择|多选', compact): return 'multiple'
    if '判断' in compact: return 'boolean'
    return 'short'

def _clean_line(line):
    return line.strip().replace('\u200b', '')

def _header(line):
    return bool(re.fullmatch(r'(?:第\s*\d+\s*页|[—－-]\s*\d+\s*[—－-])', line) or
                re.match(r'^15\s*周年非车险知识竞赛题库', line))

def _classification(source):
    if '非车' in source: return 'nonauto', ''
    if '健康' in source: return 'health', ''
    if '农险' in source: return 'agri', ''
    return 'auto', 'claims' if '理赔' in source else 'underwriting'

def _answer_values(text, kind):
    text = text.strip(' *\n\t。；;')
    if kind == 'boolean':
        match = re.match(r'[（(]?\s*(正确|错误|对|错|√|✓|×|✕)', text)
        if match: return ['T' if match[1] in ('正确', '对', '√', '✓') else 'F']
        return []
    match = re.match(r'[（(]?[ \t]*([A-H](?:[ \t、,，]*[A-H])*)', text)
    return sorted(set(re.findall('[A-H]', match[1]))) if match else []

def _question(raw_lines, source, kind, number, page):
    raw = '\n'.join(raw_lines).strip()
    body = START.sub(lambda m: m[2], raw, count=1)
    issues = []
    explanation = ''
    em = EXPLANATION.search(body)
    if em:
        explanation = body[em.end():].strip()
        body = body[:em.start()].rstrip()
    am = ANSWER.search(body)
    answer_text = ''
    if am:
        answer_text, body = body[am.end():].strip(), body[:am.start()].rstrip(' *\n')
        if kind != 'short' and '\n' in answer_text:
            answer_text, trailing = answer_text.split('\n', 1)
            explanation = '\n'.join(x for x in (trailing.strip(' *\n'), explanation) if x)
    category, subcategory = _classification(source)
    options = {}
    reference = ''
    answer = []
    if kind == 'short':
        if am:
            reference = answer_text.strip(' *\n')
            stem = body
        else:
            # Health PDF has no answer labels: the prompt's terminating full
            # stop/question mark is the visible boundary before the reference.
            boundary = re.search(r'[。？?](?:\n|$)', body) if category == 'health' else None
            if boundary and boundary.end() < len(body):
                stem, reference = body[:boundary.end()].strip(), body[boundary.end():].strip()
            else:
                stem = body
                issues.append('missing_reference')
        if not reference and 'missing_reference' not in issues: issues.append('missing_reference')
    else:
        masked = PAREN.sub(lambda m: ' ' * len(m[0]), body)
        # Literal grade lists such as “评级 B、C、D 类” are option
        # content, even though the letters resemble inline delimiters.
        masked = re.sub(r'[A-H](?:[、,，][A-H])+', lambda m: ' ' * len(m[0]), masked)
        candidates_options = list(OPTION.finditer(masked)) if kind != 'boolean' else []
        om = []
        first_a = [m for m in candidates_options if m[1] == 'A' and m.start() > 0]
        line_start_a = [m for m in first_a if not masked[masked.rfind('\n', 0, m.start())+1:m.start()].strip()]
        chosen_a = (line_start_a or first_a or [None])[0]
        expected = 'A'
        for candidate_index, marker in enumerate(candidates_options):
            if chosen_a is None or marker.start() < chosen_a.start(): continue
            if chosen_a[2] and marker[3]: continue
            at_line_start = not masked[masked.rfind('\n', 0, marker.start())+1:marker.start()].strip()
            if not at_line_start and candidate_index + 1 < len(candidates_options):
                next_marker = candidates_options[candidate_index + 1]
                if not masked[marker.end():next_marker.start()].strip(' \t\n、,，'):
                    continue
            if marker[1] >= expected or (om and marker[1] == om[-1][1] and at_line_start):
                om.append(marker)
                expected = chr(ord(marker[1]) + 1)
        # A real option run begins at A; incidental Latin letters in a stem
        # cannot move the stem boundary to an unrelated B/C/D abbreviation.
        first = next((i for i, m in enumerate(om) if m[1] == 'A'), None)
        om = om[first:] if first is not None else []
        stem = body[:om[0].start()].strip() if om else body.strip()
        for i, marker in enumerate(om):
            end = om[i+1].start() if i+1 < len(om) else len(body)
            key = marker[1]
            value = body[marker.end():end].strip()
            if key in options:
                issues.append('duplicate_option_label')
                options[key] += f'\n{key}（原文重复标签）{value}'
            else:
                options[key] = value
        embedded = list(PAREN.finditer(stem))
        candidates = [_answer_values(m[1], kind) for m in embedded]
        candidates = [v for v in candidates if v]
        if answer_text:
            answer = _answer_values(answer_text, kind)
            if any(v != answer for v in candidates): issues.append('conflicting_answer')
        elif len(candidates) == 1:
            answer = candidates[0]
        elif len(candidates) > 1:
            if all(v == candidates[0] for v in candidates): answer = candidates[0]
            else: issues.append('ambiguous_answer')
        # Remove the encoded standard answer while retaining the blank.
        stem = PAREN.sub('（ ）', stem)
        if not answer: issues.append('missing_answer')
        if kind == 'single' and len(answer) > 1: issues.append('multiple_answers_in_single')
        if kind != 'boolean':
            if len(options) < 2: issues.append('missing_options')
            if any(a not in options for a in answer): issues.append('answer_option_missing')
            if any(not v for v in options.values()): issues.append('empty_option')
    uid = hashlib.sha256(f'{source}|{kind}|{number}'.encode('utf-8')).hexdigest()
    return dict(uid=uid, category=category, subcategory=subcategory, kind=kind,
                source_file=source, source_number=str(number), source_page=page,
                stem=stem.strip(), options=options, answer=answer, reference=reference,
                explanation=explanation, raw_text=raw, issues=sorted(set(issues)), enabled=not issues)

def parse_pages(pages, source):
    """Parse extracted page strings; source_page is the physical PDF page."""
    records = []
    kind = None
    current = None
    buffer = []
    previous_number = None
    def flush():
        if current is not None:
            records.append(_question(buffer, source, kind, current[0], current[1]))
    entries = [(page, line) for page, text in enumerate(pages, 1) for line in text.splitlines()]
    for entry_index, (page, raw_line) in enumerate(entries):
            line = _clean_line(raw_line)
            if not line or _header(line): continue
            heading = _kind_heading(line)
            if heading:
                flush()
                kind, current, buffer, previous_number = heading, None, [], None
                continue
            if kind is None: continue
            match = START.match(line)
            is_start = bool(match)
            if match and current:
                # Nested numbered reference points are not question boundaries.
                candidate = int(match[1])
                likely_prompt = bool(re.search(r'[？?]|^(?:分别简述|简述|请|试述|对比|何为|根据|2020|特种车|机动车增值|投保人|车辆危险|商业车险)', match[2]))
                if kind == 'short':
                    future = []
                    for _, next_line in entries[entry_index+1:entry_index+20]:
                        if START.match(next_line): break
                        future.append(next_line)
                    labelled_reference = bool(ANSWER.search('\n'.join(future)))
                    is_start = candidate == int(current[0]) + 1 and (labelled_reference or likely_prompt or candidate >= 571)
                else:
                    # Objective explanations can include numbered prose. A new
                    # question must have options/answer material, not just be
                    # the next numbered sentence in an explanation.
                    is_start = candidate == previous_number + 1
                    if '健康' in source and kind == 'multiple' and candidate == 2 and int(current[0]) == 15:
                        is_start = True
                    if is_start and kind != 'boolean':
                        future = []
                        for _, next_line in entries[entry_index+1:entry_index+35]:
                            if START.match(next_line) or _kind_heading(next_line): break
                            future.append(next_line)
                        is_start = any(marker[1] == 'A' for marker in OPTION.finditer('\n'.join([line]+future)))
            if is_start:
                flush()
                current, buffer = (match[1], page), [line]
                if previous_number is None or int(match[1]) == previous_number + 1:
                    previous_number = int(match[1])
            elif current:
                buffer.append(line)
    flush()
    seen = set()
    for q in records:
        if q['uid'] in seen:
            q['issues'].append('duplicate_source_number')
            q['enabled'] = False
            q['printed_source_number'] = q['source_number']
            q['source_number'] += '#duplicate'
            q['uid'] = hashlib.sha256(f"{source}|{q['kind']}|{q['source_number']}".encode('utf-8')).hexdigest()
        seen.add(q['uid'])
    return records

def parse_pdf(path, root=None):
    from pypdf import PdfReader
    path = Path(path).resolve()
    source = path.relative_to(Path(root).resolve()).as_posix() if root else path.name
    return parse_pages([page.extract_text() or '' for page in PdfReader(path).pages], source)

def build_bank(root, output_dir):
    import pypdf
    root, output_dir = Path(root).resolve(), Path(output_dir)
    questions = []
    sources = []
    for path in sorted(root.rglob('*.pdf')):
        if any(part in {'.venv', '.deps', 'node_modules'} for part in path.parts): continue
        records = parse_pdf(path, root)
        questions.extend(records)
        from pypdf import PdfReader
        expected = {'health':200, 'agri':200, 'nonauto':300}.get(records[0]['category'], 600 if records[0]['subcategory'] == 'claims' else 210) if records else None
        sources.append(dict(source_file=path.relative_to(root).as_posix(), total=len(records),
                            enabled=sum(q['enabled'] for q in records),
                            kinds=dict(Counter(q['kind'] for q in records)),
                            pdf_pages=len(PdfReader(path).pages), declared_or_section_total=expected,
                            count_difference=len(records)-expected if expected is not None else None,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), parser_library=f'pypdf {pypdf.__version__}', total=len(questions),
                  enabled=sum(q['enabled'] for q in questions), sources=sources,
                  issue_counts=dict(Counter(i for q in questions for i in q['issues'])),
                  anomalies=[{k:q[k] for k in ('uid','source_file','kind','source_number','source_page','issues','stem')} for q in questions if q['issues']],
                  content_audit=dict(unique_ids=len({q['uid'] for q in questions}),
                      enabled_answer_leaks=sum(bool(ANSWER.search(q['stem']) or PAREN.search(q['stem']) or any(ANSWER.search(v) for v in q['options'].values())) for q in questions if q['enabled'] and q['kind'] != 'short'),
                      enabled_empty_stems=sum(not q['stem'].strip() for q in questions if q['enabled']),
                      source_checks=['完整提取5份PDF共304页，按题型标题、编号序列与正文边界核对。', '非车险检索健康险、健康保险、重疾险、重大疾病保险、医疗保险、疾病保险等专属题干词，未发现需改归健康险的题目；雇主责任险、团体意外险仍归非车险。', '核对无标点答案、嵌入括号答案、内嵌选项、无空格选项、分行选项及解析中的数字条目。']),
                  observations=['健康险原卷声明200题，但多选题第15与第16题之间额外印有一道编号2的独立题，实际201题；额外题保留原文并隔离，source_number加#duplicate防止覆盖。', '车险承保多选第25、26、28题的原文仅给出一个选项答案，按原卷多选分组保留，允许只勾选一个答案。', '健康险单选第86题答案C之后有E开头的说明段，按原文位置保留为答案后说明，未擅自改写为第五个选项。'],
                  limitations=['答案仅忠实转录源题库，未验证法规及业务口径的现行有效性。', '保留源文件分类，雇主责任险及团体意外险不因出现健康术语而改归健康险。'])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir/'questions.json').write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding='utf-8')
    (output_dir/'import-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 题库导入核验', '', f"共 {report['total']} 题，可练习 {report['enabled']} 题，隔离 {report['total']-report['enabled']} 题。", '', '| 来源 | 总题数 | 可用 | 题型 |', '| --- | ---: | ---: | --- |']
    for s in sources: lines.append(f"| {s['source_file']} | {s['total']} | {s['enabled']} | {s['kinds']} |")
    lines += ['', '## 异常明细', '']
    for q in report['anomalies']: lines.append(f"- {q['source_file']} / {q['kind']} / 第 {q['source_number']} 题 / PDF 第 {q['source_page']} 页：{', '.join(q['issues'])}；{q['stem'][:100]}")
    lines += ['', '## 内容核对与源卷特别情况', ''] + ['- '+x for x in report['content_audit']['source_checks'] + report['observations']]
    lines += ['', f"唯一题目ID：{report['content_audit']['unique_ids']}；可用客观题展示区标准答案残留：{report['content_audit']['enabled_answer_leaks']}；可用空题干：{report['content_audit']['enabled_empty_stems']}。"]
    lines += ['', '## 边界', ''] + ['- '+x for x in report['limitations']]
    (output_dir/'import-report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return report
