from django.test import TestCase, Client
from django.contrib.auth.models import User
from practice.models import Question, Profile, Mistake
from practice.services import start_session


class AccountAndPrivacyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('learner', password='Strong!Example938')
        Profile.objects.create(user=self.user, must_change_password=False)
        self.other = User.objects.create_user('other', password='Strong!Example939')
        Profile.objects.create(user=self.other, must_change_password=False)
        self.admin = User.objects.create_user('manager', password='Strong!Example940', is_staff=True)
        Profile.objects.create(user=self.admin, must_change_password=False)
        self.q = Question.objects.create(uid='private', category='auto', kind='single', stem='隐私验证题', options={'A': '选项甲', 'B': '选项乙'}, answer=['B'], explanation='专属解析不可提前显示', source_number='1')

    def login(self, user=None):
        self.client.force_login(user or self.user)
        session = self.client.session
        session['account_version'] = 1
        session.save()

    def test_registration_absent(self):
        self.assertEqual(self.client.get('/register/').status_code, 404)

    def test_requires_login(self):
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_exam_does_not_leak_answers(self):
        s = start_session(self.user, ['auto'], [], 'exam', 1, 60)
        self.login()
        r = self.client.get(f'/sessions/{s.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, '专属解析不可提前显示')
        self.assertNotContains(r, '正确答案')
        self.client.post(f'/items/{s.items.first().pk}/answer/', {'selected': 'A'})
        self.assertNotContains(self.client.get(f'/sessions/{s.pk}/'), '专属解析不可提前显示')

    def test_cannot_read_other_session(self):
        s = start_session(self.other, ['auto'], [], 'exam', 1, 60)
        self.login()
        self.assertEqual(self.client.get(f'/sessions/{s.pk}/').status_code, 404)
        self.assertEqual(self.client.post(f'/sessions/{s.pk}/finish/').status_code, 404)

    def test_cannot_remove_other_mistake(self):
        m = Mistake.objects.create(user=self.other, question=self.q)
        self.login()
        self.assertEqual(self.client.post(f'/mistakes/{m.pk}/remove/').status_code, 404)
        self.assertEqual(self.client.get(f'/mistakes/{m.pk}/remove/').status_code, 405)

    def test_regular_user_cannot_manage_accounts(self):
        self.login()
        self.assertEqual(self.client.get('/accounts/').status_code, 403)
        self.assertEqual(self.client.post('/accounts/', {'username': 'rogue', 'password': 'Unique!Example578'}).status_code, 403)

    def test_first_login_requires_password_change(self):
        Profile.objects.filter(user=self.user).update(must_change_password=True)
        self.login()
        self.assertRedirects(self.client.get('/'), '/password/', fetch_redirect_response=False)

    def test_suspension_revokes_session(self):
        self.login()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_version_change_revokes_session(self):
        self.login()
        Profile.objects.filter(user=self.user).update(session_version=2)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_csrf_enforced(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.user)
        session = c.session
        session['account_version'] = 1
        session.save()
        self.assertEqual(c.post('/start/', {}).status_code, 403)

    def test_admin_create_and_reset(self):
        self.login(self.admin)
        r = self.client.post('/accounts/', {'username': 'new-user', 'password': 'Unique!Example578', 'first_name': '新学员'})
        self.assertEqual(r.status_code, 302)
        created = User.objects.get(username='new-user')
        self.assertTrue(created.check_password('Unique!Example578'))
        self.assertTrue(created.profile.must_change_password)
        self.client.post(f'/accounts/{created.pk}/action/', {'action': 'reset', 'password': 'Unique!Changed578'})
        created.refresh_from_db()
        self.assertTrue(created.check_password('Unique!Changed578'))
        self.assertEqual(created.profile.session_version, 2)

    def test_dashboard_and_empty_pages(self):
        self.login()
        for url in ['/', '/mistakes/', '/history/']:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_dashboard_has_valid_underwriting_option(self):
        self.login()
        self.assertContains(self.client.get('/'), '<option value="underwriting">仅车险承保</option>', html=True)

    def test_login_throttle(self):
        for _ in range(5):
            self.client.post('/login/', {'username': self.user.username, 'password': 'incorrect'})
        response = self.client.post('/login/', {'username': self.user.username, 'password': 'Strong!Example938'})
        self.assertContains(response, '尝试次数过多')

    def test_admin_login_uses_shared_authentication(self):
        self.client.post('/admin/login/', {'username': self.admin.username, 'password': 'Strong!Example940'})
        self.assertEqual(self.client.session.get('account_version'), 1)
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_staff_can_maintain_questions(self):
        self.login(self.admin)
        self.assertEqual(self.client.get('/admin/practice/question/').status_code, 200)
