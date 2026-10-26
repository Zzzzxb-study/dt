import uuid
from django.conf import settings
from django.db import models

CATEGORIES = [('auto', '车险'), ('nonauto', '非车险'), ('health', '健康险'), ('agri', '农险')]
KINDS = [('single', '单选题'), ('multiple', '多选题'), ('boolean', '判断题'), ('short', '简答题')]
MODES = [('sequential', '顺序练习'), ('random', '随机练习'), ('exam', '模拟练习'), ('mistakes', '错题重练')]


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    must_change_password = models.BooleanField(default=True)
    session_version = models.PositiveIntegerField(default=1)


class Question(models.Model):
    uid = models.CharField(max_length=64, unique=True)
    category = models.CharField('板块', max_length=16, choices=CATEGORIES)
    subcategory = models.CharField('子分类', max_length=40, blank=True)
    kind = models.CharField('题型', max_length=16, choices=KINDS)
    stem = models.TextField('题干')
    options = models.JSONField('选项', default=dict, blank=True)
    answer = models.JSONField('标准答案', default=list, blank=True)
    reference = models.TextField('参考答案', blank=True)
    explanation = models.TextField('解析', blank=True)
    source_file = models.CharField('来源文件', max_length=255, blank=True)
    source_number = models.CharField('原题号', max_length=32)
    source_page = models.PositiveIntegerField('来源页码', default=1)
    raw_text = models.TextField('原始文本', blank=True)
    issues = models.JSONField('待复核项', default=list, blank=True)
    enabled = models.BooleanField('参与练习', default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['source_file', 'id']
        indexes = [models.Index(fields=['category', 'kind', 'enabled'])]
        verbose_name = '题目'
        verbose_name_plural = '题库维护'

    def __str__(self):
        return f'{self.get_category_display()} · {self.source_number} · {self.stem[:40]}'

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.enabled:
            return
        if self.kind == 'short':
            if not self.reference.strip():
                raise ValidationError({'reference': '启用简答题前请填写参考答案。'})
            return
        if not isinstance(self.answer, list) or not self.answer or any(not isinstance(a, str) for a in self.answer):
            raise ValidationError({'answer': '标准答案须为非空字符串数组，例如 ["A"]。'})
        allowed = {'T', 'F'} if self.kind == 'boolean' else set(self.options) if isinstance(self.options, dict) else set()
        if not set(self.answer) <= allowed or len(self.answer) != len(set(self.answer)):
            raise ValidationError({'answer': '标准答案必须属于题目选项，且不得重复。'})
        if self.kind in ('single', 'boolean') and len(self.answer) != 1:
            raise ValidationError({'answer': '单选题和判断题只能有一个标准答案。'})
        if self.kind != 'boolean' and (not isinstance(self.options, dict) or len(self.options) < 2 or any(not isinstance(v, str) or not v.strip() for v in self.options.values())):
            raise ValidationError({'options': '选择题至少需要两个非空文本选项。'})

    def snapshot(self):
        return {key: getattr(self, key) for key in ['uid', 'category', 'subcategory', 'kind', 'stem', 'options', 'answer', 'reference', 'explanation', 'source_file', 'source_number', 'source_page']}


class Session(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mode = models.CharField(max_length=16, choices=MODES)
    categories = models.JSONField(default=list)
    requested_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class Item(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    position = models.PositiveIntegerField()
    snapshot = models.JSONField()
    selected = models.JSONField(default=list)
    text_answer = models.TextField(blank=True)
    correct = models.BooleanField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['position']
        constraints = [models.UniqueConstraint(fields=['session', 'position'], name='unique_session_position'), models.UniqueConstraint(fields=['session', 'question'], name='unique_session_question')]


class Mistake(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    errors = models.PositiveIntegerField(default=1)
    last_wrong_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_wrong_at']
        constraints = [models.UniqueConstraint(fields=['user', 'question'], name='unique_personal_mistake')]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()


class Audit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64)
    target = models.CharField(max_length=150)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at']
        verbose_name = '管理操作'
        verbose_name_plural = '管理操作记录'
