import random
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import CATEGORIES, KINDS, MODES, Item, Mistake, Question, Session, QuestionProgress


def question_scope(categories, kinds=(), subcategory=''):
    questions = Question.objects.filter(enabled=True, category__in=categories)
    if kinds:
        questions = questions.filter(kind__in=kinds)
    if subcategory:
        questions = questions.filter(~Q(category='auto') | Q(subcategory=subcategory))
    return questions


def _lock_user(user):
    # Serialize progress changes, restarts and submissions for the same learner.
    get_user_model().objects.select_for_update().get(pk=user.pk)


def _record_progress(user, item):
    progress, _ = QuestionProgress.objects.get_or_create(user=user, question_id=item.question_id)
    progress.attempts += 1
    progress.correct_streak = (3 if item.snapshot['kind'] == 'short' else min(3, progress.correct_streak + 1)) if item.correct else 0
    if item.session.mode == 'sequential' and (not progress.round_started_at or item.session.created_at >= progress.round_started_at):
        progress.sequential_done = True
    progress.save()


@transaction.atomic
def start_session(user, categories, kinds, mode, count, minutes, subcategory='', restart=False):
    categories = sorted(set(categories))
    if not categories or not set(categories) <= dict(CATEGORIES).keys():
        raise ValueError('请至少选择一个有效板块')
    if mode not in dict(MODES) or not 0 <= count <= 10000 or not 1 <= minutes <= 240:
        raise ValueError('练习设置无效：题量最多 10000，时长 1—240 分钟')
    if (mode == 'exam' and not 1 <= count <= 300) or (mode != 'sequential' and (count == 0 or restart)):
        raise ValueError('模拟练习为 1—300 题；全部未练题、重新通刷仅用于顺序练习')
    if not set(kinds) <= dict(KINDS).keys() or subcategory not in ('', 'underwriting', 'claims'):
        raise ValueError('题型或子分类无效')
    _lock_user(user)
    questions = question_scope(categories, kinds, subcategory)
    if mode == 'exam':
        questions = questions.exclude(kind='short')
    if mode == 'mistakes':
        questions = questions.filter(mistake__user=user, mistake__active=True)
    pool = list(questions)
    if not pool:
        raise ValueError('所选范围没有可用题目，请调整板块或题型')
    if mode == 'sequential':
        if restart:
            now = timezone.now()
            existing = set(QuestionProgress.objects.filter(user=user, question__in=questions).values_list('question_id', flat=True))
            QuestionProgress.objects.bulk_create([QuestionProgress(user=user, question=q, round_started_at=now) for q in pool if q.pk not in existing])
            QuestionProgress.objects.filter(user=user, question__in=questions).update(sequential_done=False, round_started_at=now)
        done = set(QuestionProgress.objects.filter(user=user, sequential_done=True).values_list('question_id', flat=True))
        pool = [q for q in pool if q.pk not in done]
        if not pool:
            raise ValueError('本轮已全部练完。可选择重新通刷，或切换到巩固练习、错题重练。')
    elif mode == 'review':
        states = {p.question_id: p for p in QuestionProgress.objects.filter(user=user, question__in=questions)}
        wrong = set(Mistake.objects.filter(user=user, active=True).values_list('question_id', flat=True))
        rng = random.SystemRandom()
        unseen, seen = [], []
        for q in pool:
            p = states.get(q.pk)
            if not p or not p.attempts:
                unseen.append(q)
            else:
                weight = 0.3 if p.correct_streak >= 3 else 6 if q.pk in wrong else 3
                seen.append((rng.random() ** (1 / weight), q))
        rng.shuffle(unseen)
        pool = unseen + [q for _, q in sorted(seen, key=lambda pair: pair[0], reverse=True)]
    else:
        random.SystemRandom().shuffle(pool)
    count = count or len(pool)
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
            _record_progress(session.user, item)
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
        _lock_user(user)
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
            if session.mode != 'exam':
                _record_progress(user, item)
    if expired:
        raise ValueError('模拟已到时，已自动交卷')
    return item


@transaction.atomic
def finish_session(user, session_id):
    _lock_user(user)
    session = get_object_or_404(Session.objects.select_for_update(), pk=session_id, user=user)
    return _close(session)
