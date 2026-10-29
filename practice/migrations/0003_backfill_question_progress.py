from django.db import migrations
from django.db.models import Case, DateTimeField, F, When


def backfill(apps, schema_editor):
    Item = apps.get_model('practice', 'Item')
    Progress = apps.get_model('practice', 'QuestionProgress')
    alias = schema_editor.connection.alias
    rows = (Item.objects.using(alias).filter(correct__isnull=False)
            .annotate(learned_at=Case(When(session__mode='exam', then=F('session__finished_at')),
                                     default=F('answered_at'), output_field=DateTimeField()))
            .exclude(learned_at__isnull=True)
            .order_by('session__user_id', 'question_id', 'learned_at', 'pk')
            .values('session__user_id', 'question_id', 'session__mode', 'snapshot', 'correct', 'answered_at'))
    batch, current, key = [], None, None
    for row in rows.iterator(chunk_size=1000):
        row_key = (row['session__user_id'], row['question_id'])
        if key != row_key:
            if current:
                batch.append(current)
            if len(batch) >= 1000:
                Progress.objects.using(alias).bulk_create(batch)
                batch = []
            key = row_key
            current = Progress(user_id=key[0], question_id=key[1])
        current.attempts += 1
        current.correct_streak = (3 if row['snapshot'].get('kind') == 'short' else min(3, current.correct_streak + 1)) if row['correct'] else 0
        if row['session__mode'] == 'sequential' and row['answered_at']:
            current.sequential_done = True
    if current:
        batch.append(current)
    if batch:
        Progress.objects.using(alias).bulk_create(batch)


class Migration(migrations.Migration):
    dependencies = [('practice', '0002_alter_session_mode_questionprogress')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
