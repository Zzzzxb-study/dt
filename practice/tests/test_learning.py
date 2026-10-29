from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from unittest.mock import patch
from practice.models import Question, Profile, Item, Session, Mistake
from practice.services import start_session, answer_item, finish_session


class LearningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('progress-user')
        Profile.objects.create(user=cls.user, must_change_password=False)
        cls.other = User.objects.create_user('progress-other')
        Question.objects.bulk_create([
            Question(uid=f'auto-{n}', category='auto', subcategory='claims', kind='single',
                     stem=f'题目{n}', options={'A': '甲', 'B': '乙'}, answer=['A'], source_number=str(n))
            for n in range(701)
        ])

    def login(self):
        self.client.force_login(self.user)
        s = self.client.session
        s['account_version'] = 1
        s.save()

    def exercise(self, question, correct=True, mode='random'):
        s = Session.objects.create(user=self.user, mode=mode, categories=['auto'], requested_count=1)
        item = Item.objects.create(session=s, question=question, snapshot=question.snapshot(), position=1)
        answer_item(self.user, item.pk, ['A'] if correct else ['B'])
        return s

    def test_all_remaining_exceeds_300_and_never_silently_restarts(self):
        s = start_session(self.user, ['auto'], [], 'sequential', 0, 60)
        self.assertEqual(s.items.count(), 701)
        for item in s.items.all():
            answer_item(self.user, item.pk, ['A'])
        with self.assertRaisesMessage(ValueError, '本轮已全部练完'):
            start_session(self.user, ['auto'], [], 'sequential', 20, 60)
        self.assertEqual(start_session(self.other, ['auto'], [], 'sequential', 0, 60).items.count(), 701)

    def test_segmented_sweep_only_selects_remaining(self):
        s = start_session(self.user, ['auto'], [], 'sequential', 300, 60)
        # Answer using the public service so coverage follows actual submission.
        for item in s.items.all():
            answer_item(self.user, item.pk, ['A'])
        next_s = start_session(self.user, ['auto'], [], 'sequential', 0, 60)
        self.assertEqual(next_s.items.count(), 401)
        self.assertFalse(next_s.items.filter(question_id__in=s.items.values('question_id')).exists())

    def test_explicit_restart_is_scoped_and_preserves_history(self):
        q = Question.objects.first()
        health = Question.objects.create(uid='health', category='health', kind='boolean', stem='判断', answer=['T'], source_number='1')
        self.exercise(q, mode='sequential')
        hs = start_session(self.user, ['health'], [], 'sequential', 1, 60)
        answer_item(self.user, hs.items.first().pk, ['T'])
        before = Item.objects.filter(session__user=self.user).count()
        start_session(self.user, ['auto'], [], 'sequential', 1, 60, restart=True)
        with self.assertRaisesMessage(ValueError, '本轮已全部练完'):
            start_session(self.user, ['health'], [], 'sequential', 1, 60)
        self.assertEqual(Item.objects.filter(session__user=self.user).count(), before + 1)

    def test_review_prioritizes_unseen_and_updates_mastery_once_per_session(self):
        q = Question.objects.first()
        for _ in range(3):
            s = self.exercise(q)
        from practice.models import QuestionProgress
        p = QuestionProgress.objects.get(user=self.user, question=q)
        self.assertEqual(p.correct_streak, 3)
        answer_item(self.user, s.items.first().pk, ['A'])
        p.refresh_from_db()
        self.assertEqual(p.correct_streak, 3)
        review = start_session(self.user, ['auto'], [], 'review', 20, 60)
        self.assertFalse(review.items.filter(question=q).exists())
        self.exercise(q, correct=False)
        p.refresh_from_db()
        self.assertEqual(p.correct_streak, 0)
        self.assertTrue(Mistake.objects.get(user=self.user, question=q).active)

    def test_exam_limit_and_grading_remain_separate(self):
        for count in (0, 301):
            with self.assertRaises(ValueError):
                start_session(self.user, ['auto'], [], 'exam', count, 60)
        s = start_session(self.user, ['auto'], [], 'exam', 1, 60)
        item = s.items.first()
        answer_item(self.user, item.pk, ['A'])
        from practice.models import QuestionProgress
        self.assertFalse(QuestionProgress.objects.filter(user=self.user).exists())
        finish_session(self.user, s.pk)
        finish_session(self.user, s.pk)
        self.assertEqual(QuestionProgress.objects.get(user=self.user).attempts, 1)
        self.assertFalse(QuestionProgress.objects.get(user=self.user).sequential_done)

    def test_home_scope_progress_and_resume_first_unanswered(self):
        s = start_session(self.user, ['auto'], [], 'sequential', 20, 60)
        answer_item(self.user, s.items.first().pk, ['A'])
        self.login()
        r = self.client.get('/')
        self.assertContains(r, '累计通刷进度')
        self.assertContains(r, '全部未练题')
        self.assertContains(r, '巩固练习')
        self.assertContains(r, '继续上次练习')
        self.assertEqual(self.client.get(f'/sessions/{s.pk}/').context['current'].position, 2)

    def test_resume_banner_points_to_the_newest_unfinished_session(self):
        start_session(self.user, ['auto'], [], 'sequential', 20, 60)
        latest = start_session(self.user, ['auto'], [], 'review', 20, 60)
        self.login()
        self.assertEqual(self.client.get('/').context['resume'].pk, latest.pk)

    def test_post_all_remaining_and_restart_require_valid_mode(self):
        self.login()
        data = {'categories': ['auto'], 'mode': 'sequential', 'count': 0, 'minutes': 60}
        self.client.post('/start/', data)
        self.assertEqual(Session.objects.get(user=self.user).items.count(), 701)
        data.update(mode='exam', restart='on', count=20)
        self.client.post('/start/', data)
        self.assertEqual(Session.objects.filter(user=self.user).count(), 1)

    def test_weighted_review_prefers_wrong_then_normal_then_mastered(self):
        from practice.models import QuestionProgress
        qs = list(Question.objects.all()[:3])
        for q in qs:
            q.category = 'health'
            q.save()
        for q, streak in zip(qs, [3, 1, 0]):
            QuestionProgress.objects.create(user=self.user, question=q, attempts=3, correct_streak=streak)
        Mistake.objects.create(user=self.user, question=qs[2])
        with patch('practice.services.random.SystemRandom') as rng:
            rng.return_value.random.return_value = 0.5
            s = start_session(self.user, ['health'], [], 'review', 3, 60)
        self.assertEqual(list(s.items.values_list('question_id', flat=True)), [qs[2].pk, qs[1].pk, qs[0].pk])
        # Even mastered questions remain eligible in a normal mock exam.
        exam = start_session(self.user, ['health'], [], 'exam', 3, 60)
        self.assertEqual(set(exam.items.values_list('question_id', flat=True)), {q.pk for q in qs})

    def test_old_sessions_cannot_advance_a_restarted_round(self):
        from practice.models import QuestionProgress
        old = start_session(self.user, ['auto'], [], 'sequential', 2, 60)
        qid = old.items.first().question_id
        start_session(self.user, ['auto'], [], 'sequential', 1, 60, restart=True)
        answer_item(self.user, old.items.first().pk, ['A'])
        p = QuestionProgress.objects.get(user=self.user, question_id=qid)
        self.assertFalse(p.sequential_done)
        self.assertEqual(p.attempts, 1)

    def test_short_self_assessment_and_wrong_revoke_mastery(self):
        from practice.models import QuestionProgress
        q = Question.objects.create(uid='short', category='agri', kind='short', stem='简答', reference='要点', source_number='1')
        s = start_session(self.user, ['agri'], [], 'review', 1, 60)
        answer_item(self.user, s.items.first().pk, [], mastered=True)
        p = QuestionProgress.objects.get(user=self.user, question=q)
        self.assertEqual(p.correct_streak, 3)
        s2 = start_session(self.user, ['agri'], [], 'review', 1, 60)
        answer_item(self.user, s2.items.first().pk, [], mastered=False)
        p.refresh_from_db()
        self.assertEqual(p.correct_streak, 0)

    def test_scope_counts_exclude_other_users_disabled_and_unselected(self):
        from practice.models import QuestionProgress
        q = Question.objects.first()
        QuestionProgress.objects.create(user=self.other, question=q, sequential_done=True, correct_streak=3)
        self.login()
        r = self.client.get('/')
        self.assertEqual(r.context['initial_progress']['done'], 0)
        self.exercise(q, mode='sequential')
        r = self.client.get('/')
        self.assertEqual(r.context['initial_progress']['done'], 1)
        q.enabled = False
        q.save()
        r = self.client.get('/')
        self.assertEqual(r.context['initial_progress']['total'], 700)
        self.assertEqual(r.context['initial_progress']['done'], 0)

    def test_backfill_preserves_legacy_coverage_mastery_and_pending_exam(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from practice.models import QuestionProgress
        q = Question.objects.first()
        for mode in ['sequential', 'random', 'random']:
            self.exercise(q, mode=mode)
        pending = start_session(self.user, ['auto'], [], 'exam', 1, 60)
        answer_item(self.user, pending.items.first().pk, ['A'])
        QuestionProgress.objects.all().delete()
        import_module('practice.migrations.0003_backfill_question_progress').backfill(apps, connection.schema_editor())
        p = QuestionProgress.objects.get(user=self.user, question=q)
        self.assertTrue(p.sequential_done)
        self.assertEqual(p.correct_streak, 3)
        self.assertEqual(p.attempts, 3)
        self.assertEqual(QuestionProgress.objects.count(), 1)
