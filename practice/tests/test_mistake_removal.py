from django.contrib.auth.models import User
from django.test import TestCase
from practice.models import Item, Mistake, Profile, Question, QuestionProgress
from practice.services import answer_item, start_session


class PracticeMistakeRemovalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('removal-user')
        cls.other = User.objects.create_user('removal-other')
        Profile.objects.create(user=cls.user, must_change_password=False)
        cls.question = Question.objects.create(uid='removal', category='auto', kind='single', stem='错题重练示例', options={'A': '甲', 'B': '乙'}, answer=['A'], source_number='1')

    def setUp(self):
        self.mistake = Mistake.objects.create(user=self.user, question=self.question)
        self.practice = start_session(self.user, ['auto'], [], 'mistakes', 20, 60)
        self.item = self.practice.items.first()
        self.url = f'/mistakes/{self.mistake.pk}/remove/'
        self.page_url = f'/sessions/{self.practice.pk}/?q=1'
        self.client.force_login(self.user)
        session = self.client.session
        session['account_version'] = 1
        session.save()

    def test_remove_from_practice_returns_to_current_question_preserves_answer(self):
        answer_item(self.user, self.item.pk, ['A'])
        self.assertContains(self.client.get(self.page_url), '移出错题集')
        response = self.client.post(self.url, {'item': self.item.pk})
        self.assertRedirects(response, self.page_url)
        self.mistake.refresh_from_db()
        self.assertFalse(self.mistake.active)
        self.assertIsNotNone(self.mistake.removed_at)
        self.item.refresh_from_db()
        self.assertTrue(self.item.correct)
        self.assertEqual(QuestionProgress.objects.get(user=self.user).correct_streak, 1)
        page = self.client.get(self.page_url)
        self.assertContains(page, '已移出错题集')
        self.assertNotContains(page, 'name="item"')

    def test_unanswered_removal_does_not_answer_and_wrong_answer_restores(self):
        response = self.client.post(self.url, {'item': self.item.pk})
        self.assertRedirects(response, self.page_url)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.answered_at)
        self.assertFalse(QuestionProgress.objects.filter(user=self.user).exists())
        with self.assertRaisesMessage(ValueError, '没有可用题目'):
            start_session(self.user, ['auto'], [], 'mistakes', 20, 60)
        answer_item(self.user, self.item.pk, ['B'])
        self.mistake.refresh_from_db()
        self.assertTrue(self.mistake.active)
        self.assertContains(self.client.get(self.page_url), '移出错题集')

    def test_rejects_foreign_or_mismatched_items_before_removing(self):
        foreign = start_session(self.other, ['auto'], [], 'random', 1, 60).items.first()
        self.assertEqual(self.client.post(self.url, {'item': foreign.pk}).status_code, 404)
        second = Question.objects.create(uid='other-question', category='health', kind='boolean', stem='其他题目', answer=['T'], source_number='2')
        unrelated = start_session(self.user, ['health'], [], 'random', 1, 60).items.first()
        self.assertEqual(self.client.post(self.url, {'item': unrelated.pk}).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'item': 'bad'}).status_code, 404)
        self.mistake.refresh_from_db()
        self.assertTrue(self.mistake.active)

    def test_exam_has_no_mistake_status_and_rejects_exam_context(self):
        exam = start_session(self.user, ['auto'], [], 'exam', 1, 60)
        page = self.client.get(f'/sessions/{exam.pk}/')
        self.assertNotContains(page, '移出错题集')
        self.assertEqual(self.client.post(self.url, {'item': exam.items.first().pk}).status_code, 404)
        self.mistake.refresh_from_db()
        self.assertTrue(self.mistake.active)

    def test_existing_list_removal_and_repeated_practice_removal_still_work(self):
        self.assertRedirects(self.client.post(self.url), '/mistakes/')
        self.assertRedirects(self.client.post(self.url, {'item': self.item.pk}), self.page_url)
        self.assertEqual(Item.objects.filter(session=self.practice).count(), 1)
        self.assertEqual(Mistake.objects.filter(user=self.user).count(), 1)
