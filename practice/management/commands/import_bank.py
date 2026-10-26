import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from practice.models import Question


class Command(BaseCommand):
    help = '导入已校验 JSON 题库；默认保留管理员已有修改'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(settings.BASE_DIR / 'data/questions.json'))
        parser.add_argument('--update', action='store_true', help='明确覆盖已有题目内容，历史练习快照不受影响')
        parser.add_argument('--parse-pdfs', action='store_true', help='先重新解析项目下的 PDF')

    def handle(self, *args, **options):
        if options['parse_pdfs']:
            from practice.importer import build_bank
            build_bank(settings.BASE_DIR, settings.BASE_DIR / 'data')
        path = Path(options['file'])
        if not path.is_file():
            raise CommandError('题库文件不存在，请先执行 --parse-pdfs')
        records = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(records, list):
            raise CommandError('题库应为 JSON 数组')
        fields = {f.name for f in Question._meta.fields} - {'id', 'updated_at', 'uid'}
        created, updated = 0, 0
        with transaction.atomic():
            for record in records:
                defaults = {k: v for k, v in record.items() if k in fields}
                if options['update']:
                    _, new = Question.objects.update_or_create(uid=record['uid'], defaults=defaults)
                    updated += not new
                else:
                    _, new = Question.objects.get_or_create(uid=record['uid'], defaults=defaults)
                created += new
        self.stdout.write(self.style.SUCCESS(f'题库共 {len(records)} 题；新增 {created}，覆盖 {updated}；当前启用 {Question.objects.filter(enabled=True).count()} 题。'))
