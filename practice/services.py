import random
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import CATEGORIES, KINDS, MODES, Item, Mistake, Question, Session


@transaction.atomic
def start_session(user, categories, kinds, mode, count, minutes, subcategory=''):
    categories = sorted(set(categories))
    if not categories or not set(categories) <= dict(CATEGORIES).keys():
        raise ValueError('请至少选择一个有效板块')
    if mode not in dict(MODES) or not 1 <= count <= 300 or not 1 <= minutes <= 240:
        raise ValueError('练习设置无效：题量 1—300，时长 1—240 分钟')
    if not set(kinds) <= dict(KINDS).keys() or subcategory not in ('', 'underwriting', 'claims'):
        raise ValueError('题型或子分类无效')
    questions = Question.objects.filter(enabled=True, category__in=categories)
    if kinds:
        questions = questions.filter(kind__in=kinds)
    if subcategory:
        questions = questions.filter(~Q(category='auto') | Q(subcategory=subcategory))
    if mode == 'exam':
        questions = questions.exclude(kind='short')
    if mode == 'mistakes':
        questions = questions.filter(mistake__user=user, mistake__active=True)
    pool = list(questions)
    if not pool:
        raise ValueError('所选范围没有可用题目，请调整板块或题型')
    if mode == 'sequential':
        done = set(Item.objects.filter(session__user=user, session__mode='sequential', answered_at__isnull=False).values_list('question_id', flat=True))
        remaining = [q for q in pool if q.pk not in done]
        pool = remaining or pool
    else:
        random.SystemRandom().shuffle(pool)
    session = Session.objects.create(user=user, mode=mode, categories=categories, requested_count=count, deadline=timezone.now() + timedelta(minutes=minutes) if mode == 'exam' else None)
    Item.objects.bulk_create([Item(session=session, question=q, position=n, snapshot=q.snapshot()) for n, q in enumerate(pool[:count], 1)])
    return session


def _mark_wrong(user, item):
    mistake, created = Mistake.objects.select_for_update().get_or_create(user=user, question_id=item.question_id)
    restored = not created and not mistake.active
    if not created:
        mistake.errors += 1
    mistake.active = True
    mistake.removed_at = None
    mistake.last_wrong_at = timezone.now()
    mistake.save()
    return restored


def _close(session):
    if session.finished_at:
        return session
    items = list(session.items.all())
    session.restored_mistakes = 0
    # Consistent question lock order also covers two exams for the same user.
    for item in sorted(items, key=lambda item: item.question_id):
        if session.mode == 'exam':
            item.correct = bool(item.answered_at and set(item.selected) == set(item.snapshot['answer']))
            item.save(update_fields=['correct'])
            if not item.correct:
                session.restored_mistakes += _mark_wrong(session.user, item)
    answered = [i for i in items if i.correct is not None]
    session.score = round(sum(i.correct for i in answered) / len(items) * 100, 1) if items else 0
    session.finished_at = timezone.now()
    session.save(update_fields=['score', 'finished_at'])
    return session


def answer_item(user, item_id, selected, text_answer='', mastered=None):
    # All writes for one session acquire the same parent lock (PostgreSQL).
    item_ref = get_object_or_404(Item, pk=item_id, session__user=user)
    expired = False
    with transaction.atomic():
        session = get_object_or_404(Session.objects.select_for_update(), pk=item_ref.session_id, user=user)
        item = Item.objects.get(pk=item_id)
        if session.mode == 'exam' and not session.finished_at and timezone.now() >= session.deadline:
            _close(session)
            expired = True
        elif session.finished_at:
            raise ValueError('本次练习已结束')
        elif item.answered_at and session.mode != 'exam':
            return item
        else:
            selected = sorted(set(selected))
            snap = item.snapshot
            if snap['kind'] == 'short':
                if mastered not in (True, False):
                    raise ValueError('请标记掌握或未掌握')
                correct = mastered
            else:
                allowed = {'T', 'F'} if snap['kind'] == 'boolean' else set(snap['options'])
                if not selected or not set(selected) <= allowed or (snap['kind'] != 'multiple' and len(selected) != 1):
                    raise ValueError('请选择有效答案')
                correct = set(selected) == set(snap['answer'])
            item.selected = selected
            item.text_answer = text_answer[:10000]
            item.answered_at = timezone.now()
            item.correct = None if session.mode == 'exam' else correct
            item.save()
            if session.mode != 'exam' and not correct:
                item.restored_mistake = _mark_wrong(user, item)
    if expired:
        raise ValueError('模拟已到时，已自动交卷')
    return item


@transaction.atomic
def finish_session(user, session_id):
    session = get_object_or_404(Session.objects.select_for_update(), pk=session_id, user=user)
    return _close(session)
