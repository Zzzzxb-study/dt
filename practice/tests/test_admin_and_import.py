import io
import json
import tempfile
from pathlib import Path
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from practice.models import Profile, Question


class AdminDataTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='Private!Example38', is_staff=True)
        Profile.objects.create(user=self.admin, must_change_password=False)
        self.client.force_login(self.admin)
        session = self.client.session
        session['account_version'] = 1
        session.save()

    def test_batch_partial_success_no_password_echo(self):
        csv = 'username,first_name,password\nnewperson,学员,Unique!Example578\nnewperson,重复,Unique!Example579\nweak,短密码,123\n'
        upload = SimpleUploadedFile('accounts.csv', csv.encode('utf-8'), content_type='text/csv')
        response = self.client.post('/accounts/batch/', {'file': upload})
        self.assertContains(response, '成功创建 <strong>1</strong>', html=False)
        self.assertContains(response, '失败 <strong>2</strong>', html=False)
        self.assertNotContains(response, 'Unique!Example578')
        self.assertTrue(User.objects.get(username='newperson').check_password('Unique!Example578'))
        self.assertFalse(User.objects.filter(username='weak').exists())

    def test_enabled_question_requires_valid_answer(self):
        q = Question(uid='invalid', category='auto', kind='single', stem='题干', options={'A': '甲', 'B': '乙'}, answer=['C'], source_number='1')
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_enabled_single_requires_exactly_one_answer(self):
        q = Question(uid='invalid', category='auto', kind='single', stem='题干', options={'A': '甲', 'B': '乙'}, answer=['A', 'B'], source_number='1')
        with self.assertRaises(ValidationError):
            q.full_clean()

    def test_import_preserves_edits_unless_explicit(self):
        q = Question.objects.create(uid='stable', category='auto', kind='single', stem='管理员修订题', options={'A': '甲', 'B': '乙'}, answer=['A'], source_number='1')
        data = [{'uid': 'stable', 'category': 'auto', 'kind': 'single', 'stem': '文件中的题', 'options': {'A': '甲', 'B': '乙'}, 'answer': ['B'], 'source_number': '1'}]
        root = Path(__file__).resolve().parents[2]
        (root / 'tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root / 'tmp') as tmp:
            Path(tmp).resolve().relative_to(root.resolve())
            path = Path(tmp) / 'questions.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            call_command('import_bank', file=str(path), stdout=io.StringIO())
            q.refresh_from_db()
            self.assertEqual(q.stem, '管理员修订题')
            call_command('import_bank', file=str(path), update=True, stdout=io.StringIO())
            q.refresh_from_db()
            self.assertEqual(q.stem, '文件中的题')
