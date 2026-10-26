import unittest
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '.deps'))
from practice.importer import parse_pages, parse_pdf

class ParserTests(unittest.TestCase):
    def parse(self, text):
        return parse_pages([text], '健康险.pdf')[0]

    def test_embedded_answer_and_explanation(self):
        q = self.parse('一、单选题\n1. 请选择（ B ）项目。\nA.甲 B.乙 C.丙 D.丁\n【解析】理由。')
        self.assertEqual(q['answer'], ['B'])
        self.assertNotIn('B', q['stem'])
        self.assertEqual(q['options'], dict(A='甲', B='乙', C='丙', D='丁'))
        self.assertEqual(q['explanation'], '理由。')

    def test_separate_answer(self):
        q = self.parse('一、单选题\n1. 选择什么？\nA.甲\nB.乙\n**答案：B**')
        self.assertEqual(q['answer'], ['B'])
        self.assertNotIn('答案', q['options']['B'])

    def test_boolean_and_page_metadata(self):
        records = parse_pages(['三、判断题\n1. 这是对的。（√）', '2. 这是错的。\n答案：错误'], '农险.pdf')
        self.assertEqual([q['answer'] for q in records], [['T'], ['F']])
        self.assertEqual(records[1]['source_page'], 2)

    def test_boolean_answer_without_colon_or_space(self):
        q = self.parse('三、判断题\n1. 这是错的。（）\n答案错误（×）\n【解析】理由。')
        self.assertEqual(q['answer'], ['F'])
        self.assertNotIn('错误', q['stem'])
        self.assertNotIn('答案', q['stem'])
        q = self.parse('三、判断题\n1. 这是对的。（）\n答案\n正确（√）')
        self.assertEqual(q['answer'], ['T'])
        self.assertNotIn('正确', q['stem'])

    def test_short_numbered_answer_not_new_question(self):
        records = parse_pages(['四、简答题\n1. 简述职责。\n答：\n1. 负责审核。\n2. 负责检查。\n2. 何为风险？\n答：损失的不确定性。'], '农险.pdf')
        self.assertEqual(len(records), 2)
        self.assertIn('负责检查', records[0]['reference'])

    def test_ambiguous_embedded_answer_disabled(self):
        q = self.parse('一、单选题\n1. （A）和（B）哪项正确？\nA.甲 B.乙')
        self.assertFalse(q['enabled'])
        self.assertIn('ambiguous_answer', q['issues'])

    def test_multiple_answer(self):
        q = self.parse('二、多选题\n1. 哪些正确（ A、C ）？\nA甲 B乙 C丙 D丁')
        self.assertEqual(q['answer'], ['A', 'C'])

    def test_no_answer_disabled_and_header_ignored(self):
        q = self.parse('一、单选题\n第 1 页\n1. 缺少答案\nA.甲 B.乙')
        self.assertFalse(q['enabled'])
        self.assertIn('missing_answer', q['issues'])

    def test_letter_names_in_stem_and_option_are_preserved(self):
        q = self.parse('一、单选题\n1. A、B两车相撞，近因是（B）。\nA.天气\nB.酒驾\nC.碰撞\nD. A 和B 均是')
        self.assertIn('A、B两车相撞', q['stem'])
        self.assertEqual(q['options']['D'], 'A 和B 均是')
        self.assertEqual(q['answer'], ['B'])

    def test_space_delimited_and_space_before_option_punctuation(self):
        q = self.parse('一、单选题\n1. 选谁（D）\nA 甲 B 乙\nC 丙 D 丁')
        self.assertEqual(q['options'], dict(A='甲', B='乙', C='丙', D='丁'))
        q = self.parse('一、单选题\n1. 选谁（B）\nA.甲 B 、乙 C 、丙 D 、丁')
        self.assertEqual(q['options']['B'], '乙')

    def test_option_letter_enumeration_is_part_of_option(self):
        q = self.parse('二、多选题\n1. 业务（ABC）\nA、甲\nB、过户车评级 B、C、D 类家用过户车业务\nC、丙\nD、丁')
        self.assertEqual(q['options']['B'], '过户车评级 B、C、D 类家用过户车业务')
        self.assertTrue(q['enabled'])

    def test_option_without_preceding_space(self):
        q = self.parse('一、单选题\n1. 选什么（B）\nA.甲 B.社保卡“一卡通”C.地方银行 D.丁')
        self.assertEqual(q['options']['B'], '社保卡“一卡通”')
        self.assertEqual(q['options']['C'], '地方银行')
        records = parse_pages(['一、单选题\n1. 前题（A）\nA.甲 B.乙\n2. 下题（）A.甲 B.乙\n【答案】B'], '健康险.pdf')
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]['answer'], ['B'])

    def test_unlabelled_commentary_after_answer_not_part_of_key(self):
        q = self.parse('一、单选题\n1. 选谁（）\nA.甲 B.乙 C.丙 D.丁\n答案：C\nE. GCS 的评估说明。')
        self.assertEqual(q['answer'], ['C'])
        self.assertIn('GCS', q['explanation'])

    def test_nested_objective_analysis_is_not_question(self):
        records = parse_pages(['一、单选题\n1. 问题（A）\nA.甲 B.乙\n【解析】\n2. 第二个知识点。\n2. 真实问题（B）\nA.甲 B.乙'], '健康险.pdf')
        self.assertEqual(len(records), 2)
        self.assertIn('第二个知识点', records[0]['explanation'])
        self.assertEqual(records[1]['answer'], ['B'])

    def test_duplicate_source_numbers_still_have_unique_stable_ids(self):
        text = '三、多选题\n1. 问（AB）\nA甲 B乙\n2. 问（AB）\nA甲 B乙\n'
        # Genuine health source has an extra #2 between #15 and #16.
        for number in range(3, 16): text += f'{number}. 问（AB）\nA甲 B乙\n'
        text += '2. 额外题（AB）\nA甲 B乙\n16. 后续题（AB）\nA甲 B乙'
        records = parse_pages([text], '健康险.pdf')
        self.assertEqual(len(records), 17)
        self.assertEqual(len({q['uid'] for q in records}), 17)
        duplicate = records[-2]
        self.assertFalse(duplicate['enabled'])
        self.assertEqual(duplicate['printed_source_number'], '2')
        self.assertEqual(duplicate['uid'], hashlib.sha256(f"健康险.pdf|multiple|{duplicate['source_number']}".encode()).hexdigest())

class ActualSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.records = json.loads((cls.root / 'data/questions.json').read_text(encoding='utf-8'))

    def test_actual_bank_counts_categories_and_unique_ids(self):
        from collections import Counter
        self.assertEqual(len(self.records), 1511)
        self.assertEqual(Counter(q['category'] for q in self.records), {'auto':810, 'nonauto':300, 'health':201, 'agri':200})
        self.assertEqual(len({q['uid'] for q in self.records}), 1511)
        self.assertEqual(sum(not q['enabled'] for q in self.records), 5)

    def test_no_standard_answers_leak_in_display(self):
        from practice.importer import ANSWER, PAREN
        for q in self.records:
            if not q['enabled'] or q['kind'] == 'short': continue
            self.assertIsNone(ANSWER.search(q['stem']), q['uid'])
            self.assertIsNone(PAREN.search(q['stem']), q['uid'])
            self.assertTrue(q['answer'], q['uid'])
            for option in q['options'].values():
                self.assertIsNone(ANSWER.search(option), q['uid'])

    def test_real_source_parse_matches_export_and_page_metadata(self):
        path = next(self.root.glob('*非车*.pdf'))
        parsed = parse_pdf(path, self.root)
        saved = [q for q in self.records if q['category'] == 'nonauto']
        self.assertEqual(parsed, saved)
        self.assertEqual(parsed[0]['source_page'], 1)
        self.assertEqual(parsed[-1]['source_page'], 69)
        self.assertIn('雇主责任险', parsed[1]['stem'])
        self.assertEqual(parsed[1]['category'], 'nonauto')

if __name__ == '__main__':
    unittest.main()
