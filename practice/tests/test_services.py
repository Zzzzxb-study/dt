from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from practice.models import Question, Session, Item, Mistake
from practice.services import start_session, answer_item, finish_session


class PracticeRulesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('learner', password='Random!Secure28')
        self.other = User.objects.create_user('other', password='Random!Secure29')
        self.q = Question.objects.create(uid='one', category='auto', kind='multiple', stem='选择正确项', options={'A': '甲', 'B': '乙', 'C': '丙'}, answer=['A', 'C'], source_number='1')
        self.q2 = Question.objects.create(uid='two', category='health', kind='boolean', stem='判断', answer=['T'], source_number='1')

    def test_filter_unique_and_actual_count(self):
        session = start_session(self.user, ['auto'], [], 'random', 50, 60)
        self.assertEqual(session.items.count(), 1)
        self.assertEqual(session.items.first().snapshot['uid'], 'one')

    def test_multiple_exact_and_snapshot(self):
        s = start_session(self.user, ['auto'], [], 'sequential', 20, 60)
        self.q.answer = ['B']
        self.q.save()
        item = s.items.first()
        answer_item(self.user, item.pk, ['C', 'A'])
        item.refresh_from_db()
        self.assertTrue(item.correct)

    def test_wrong_removed_and_wrong_again(self):
        s = start_session(self.user, ['auto'], [], 'random', 1, 60)
        item = s.items.first()
        answer_item(self.user, item.pk, ['A'])
        mistake = Mistake.objects.get(user=self.user, question=self.q)
        self.assertTrue(mistake.active)
        mistake.active = False
        mistake.save()
        s2 = start_session(self.user, ['auto'], [], 'random', 1, 60)
        answer_item(self.user, s2.items.first().pk, ['A'])
        mistake.refresh_from_db()
        self.assertTrue(mistake.active)
        self.assertEqual(mistake.errors, 2)

    def test_reopened_mistake_has_notice_flag(self):
        Mistake.objects.create(user=self.user, question=self.q, active=False)
        s = start_session(self.user, ['auto'], [], 'random', 1, 60)
        item = answer_item(self.user, s.items.first().pk, ['A'])
        self.assertTrue(item.restored_mistake)

    def test_correct_does_not_remove_mistake(self):
        Mistake.objects.create(user=self.user, question=self.q, active=True)
        s = start_session(self.user, ['auto'], [], 'random', 1, 60)
        answer_item(self.user, s.items.first().pk, ['A', 'C'])
        self.assertTrue(Mistake.objects.get(user=self.user, question=self.q).active)

    def test_cannot_answer_other_users_item(self):
        s = start_session(self.user, ['auto'], [], 'random', 1, 60)
        from django.http import Http404
        with self.assertRaises(Http404):
            answer_item(self.other, s.items.first().pk, ['A'])

    def test_exam_pending_grade_and_idempotence(self):
        s = start_session(self.user, ['auto', 'health'], [], 'exam', 50, 60)
        item = s.items.get(question=self.q)
        answer_item(self.user, item.pk, ['A', 'C'])
        item.refresh_from_db()
        self.assertIsNone(item.correct)
        self.assertFalse(Mistake.objects.exists())
        finish_session(self.user, s.pk)
        s.refresh_from_db()
        self.assertEqual(s.score, 50)
        self.assertEqual(Mistake.objects.count(), 1)
        finish_session(self.user, s.pk)
        self.assertEqual(Mistake.objects.get().errors, 1)

    def test_expired_exam_rejects_late_answer(self):
        s = start_session(self.user, ['auto'], [], 'exam', 1, 1)
        s.deadline = timezone.now() - timedelta(seconds=1)
        s.save()
        with self.assertRaisesMessage(ValueError, '已到时'):
            answer_item(self.user, s.items.first().pk, ['A', 'C'])
        s.refresh_from_db()
        self.assertIsNotNone(s.finished_at)
        self.assertEqual(s.score, 0)

    def test_short_only_practice(self):
        Question.objects.create(uid='short', category='agri', kind='short', stem='简述', reference='要点', source_number='1')
        with self.assertRaises(ValueError):
            start_session(self.user, ['agri'], [], 'exam', 1, 60)
        s = start_session(self.user, ['agri'], [], 'random', 1, 60)
        answer_item(self.user, s.items.first().pk, [], '未掌握', False)
        self.assertTrue(Mistake.objects.filter(user=self.user, active=True).exists())

    def test_answer_cannot_be_overwritten_in_practice(self):
        s = start_session(self.user, ['auto'], [], 'random', 1, 60)
        item = s.items.first()
        answer_item(self.user, item.pk, ['A'])
        answer_item(self.user, item.pk, ['A', 'C'])
        item.refresh_from_db()
        self.assertFalse(item.correct)
        self.assertEqual(Mistake.objects.get().errors, 1)

    def test_disabled_questions_not_selected(self):
        self.q.enabled = False
        self.q.save()
        with self.assertRaises(ValueError):
            start_session(self.user, ['auto'], [], 'random', 1, 60)

    def test_car_subcategory_does_not_filter_other_boards(self):
        self.q.subcategory = 'underwriting'
        self.q.save()
        s = start_session(self.user, ['auto', 'health'], [], 'random', 50, 60, 'underwriting')
        self.assertEqual(set(s.items.values_list('question__category', flat=True)), {'auto', 'health'})
