import csv
import hashlib
import io
import math
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import AccountForm, StartForm
from .models import Audit, CATEGORIES, KINDS, Item, LoginAttempt, Mistake, Profile, Question, Session, QuestionProgress
from .services import answer_item, finish_session, start_session


def page(request, template, context=None):
    base = {'category_choices': CATEGORIES, 'kind_choices': KINDS, 'nav': ''}
    base.update(context or {})
    return render(request, f'practice/{template}.html', base)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '')[:150].strip()
        # Per account plus per connection-address limits; do not trust user-supplied forwarded headers.
        keys = [hashlib.sha256(f'{kind}:{value}'.encode()).hexdigest() for kind, value in [('account', username.lower()), ('ip', request.META.get('REMOTE_ADDR', 'unknown'))]]
        with transaction.atomic():
            attempts = [LoginAttempt.objects.select_for_update().get_or_create(key=k, defaults={'window_start': timezone.now()})[0] for k in keys]
            for attempt in attempts:
                if timezone.now() - attempt.window_start > timedelta(minutes=15):
                    attempt.failures = 0
                    attempt.window_start = timezone.now()
                    attempt.save()
            blocked = attempts[0].failures >= 5 or attempts[1].failures >= 40
            if blocked:
                error = '尝试次数过多，请在 15 分钟后重试，或联系管理员。'
            else:
                user = authenticate(request, username=username, password=request.POST.get('password', ''))
                if user:
                    attempts[0].delete()
                    login(request, user)
                    profile, _ = Profile.objects.get_or_create(user=user, defaults={'must_change_password': not user.is_superuser})
                    request.session['account_version'] = profile.session_version
                    return redirect('home')
                for attempt in attempts:
                    attempt.failures += 1
                    attempt.save()
                error = '账号或密码不正确，或账号已停用。'
    return page(request, 'login', {'error': error})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def password_view(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
            profile = Profile.objects.select_for_update().get(user=request.user)
            profile.must_change_password = False
            profile.session_version += 1
            profile.save()
        update_session_auth_hash(request, request.user)
        request.session['account_version'] = profile.session_version
        messages.success(request, '密码已修改，其他登录会话已退出。')
        return redirect('home')
    return page(request, 'password', {'form': form})


@login_required
def home(request):
    items = Item.objects.filter(session__user=request.user)
    completed = items.filter(correct__isnull=False)
    counts = {r['category']: r['count'] for r in Question.objects.filter(enabled=True).values('category').annotate(count=Count('pk'))}
    boards = [{'key': k, 'name': n, 'count': counts.get(k, 0), 'description': d, 'index': f'0{i}'} for i, ((k, n), d) in enumerate(zip(CATEGORIES, ['承保与理赔，系统练习', '财产、责任与工程等险种', '健康保障与业务实务', '农业风险与政策实务']), 1)]
    scope_data = list(Question.objects.filter(enabled=True).values('category', 'subcategory', 'kind').annotate(total=Count('pk')))
    progress = {(r['question__category'], r['question__subcategory'], r['question__kind']): r
                for r in QuestionProgress.objects.filter(user=request.user, question__enabled=True)
                .values('question__category', 'question__subcategory', 'question__kind')
                .annotate(done=Count('pk', filter=Q(sequential_done=True)), mastered=Count('pk', filter=Q(correct_streak__gte=3)))}
    for row in scope_data:
        state = progress.get((row['category'], row['subcategory'], row['kind']), {})
        row.update(done=state.get('done', 0), mastered=state.get('mastered', 0))
    selected = [r for r in scope_data if r['category'] == 'auto']
    initial = {k: sum(r[k] for r in selected) for k in ('total', 'done', 'mastered')}
    initial['remaining'] = initial['total'] - initial['done']
    recent = request.user.session_set.filter(finished_at__isnull=True).annotate(total_items=Count('items'), answered_items=Count('items', filter=Q(items__answered_at__isnull=False))).order_by('-created_at', '-pk')[:3]
    return page(request, 'home', {'nav': 'home', 'boards': boards, 'scope_data': scope_data, 'initial_progress': initial, 'resume': recent[0] if recent else None, 'practiced': items.filter(answered_at__isnull=False).values('question_id').distinct().count(), 'accuracy': round(completed.filter(correct=True).count() / completed.count() * 100) if completed.exists() else None, 'graded_count': completed.count(), 'wrong_count': Mistake.objects.filter(user=request.user, active=True).count(), 'recent': recent, 'total': sum(counts.values())})


@login_required
@require_POST
def start(request):
    form = StartForm(request.POST)
    if form.is_valid():
        try:
            session = start_session(request.user, **form.cleaned_data)
            if session.items.count() < session.requested_count:
                messages.info(request, f'所选范围实际可用 {session.items.count()} 题，本次已按实际题量创建。')
            return redirect('session', pk=session.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, '请至少选择一个板块，并检查题量、时长和题型。')
    return redirect('home')


@login_required
def session_view(request, pk):
    session = get_object_or_404(Session, pk=pk, user=request.user)
    if session.mode == 'exam' and not session.finished_at and timezone.now() >= session.deadline:
        session = finish_session(request.user, session.pk)
        messages.info(request, '模拟时间已结束，已自动交卷。')
        if getattr(session, 'restored_mistakes', 0):
            messages.info(request, f'{session.restored_mistakes} 道曾移除的错题再次答错，已重新加入错题本。')
    if session.finished_at:
        return redirect('result', pk=pk)
    items = list(session.items.values('pk', 'position', 'answered_at', 'correct'))
    try:
        position = int(request.GET.get('q', 0))
    except ValueError:
        position = 0
    if not 1 <= position <= len(items):
        current_row = next((i for i in items if not i['answered_at']), items[-1])
    else:
        current_row = items[position - 1]
    current = session.items.get(pk=current_row['pk'])
    snap = current.snapshot
    revealed = current.answered_at is not None and session.mode != 'exam'
    # Build a deliberately safe object: no answers/analysis in exam templates or JSON.
    question = {k: snap[k] for k in ['stem', 'kind', 'options', 'source_number', 'source_page', 'source_file', 'category', 'subcategory']}
    if snap['kind'] == 'boolean':
        question['options'] = {'T': '正确', 'F': '错误'}
    if revealed or snap['kind'] == 'short':
        question.update(answer=snap['answer'], reference=snap['reference'], explanation=snap['explanation'])
    nav_items = [{'position': i['position'], 'answered': i['answered_at'] is not None, 'correct': i['correct'] if session.mode != 'exam' else None} for i in items]
    answered = sum(i['answered_at'] is not None for i in items)
    context = {'nav': 'home', 'practice': session, 'current': current, 'question': question, 'revealed': revealed, 'kind_label': dict(KINDS)[snap['kind']], 'category_label': dict(CATEGORIES)[snap['category']], 'items': nav_items, 'total': len(items), 'answered': answered, 'previous': max(1, current.position - 1), 'next': min(len(items), current.position + 1), 'progress': round(answered / len(items) * 100), 'deadline': session.deadline.isoformat() if session.deadline else '', 'remaining_seconds': max(0, math.ceil((session.deadline - timezone.now()).total_seconds())) if session.deadline else 0}
    return page(request, 'session', context)


@login_required
@require_POST
def answer(request, pk):
    item = get_object_or_404(Item, pk=pk, session__user=request.user)
    try:
        saved = answer_item(request.user, pk, request.POST.getlist('selected'), request.POST.get('text_answer', ''), {'yes': True, 'no': False}.get(request.POST.get('mastered')))
        if getattr(saved, 'restored_mistake', False):
            messages.info(request, '这道题曾被移除；本次再次答错，已重新加入错题本。')
    except ValueError as exc:
        messages.error(request, str(exc))
    target = item.position + 1 if item.session.mode == 'exam' else item.position
    target = min(target, item.session.items.count())
    return redirect(reverse('session', args=[item.session_id]) + f'?q={target}')


@login_required
@require_POST
def finish(request, pk):
    session = finish_session(request.user, pk)
    if getattr(session, 'restored_mistakes', 0):
        messages.info(request, f'{session.restored_mistakes} 道曾移除的错题再次答错，已重新加入错题本。')
    return redirect('result', pk=pk)


@login_required
def result(request, pk):
    session = get_object_or_404(Session, pk=pk, user=request.user)
    if not session.finished_at:
        return redirect('session', pk=pk)
    items = list(session.items.all())
    for item in items:
        item.category_label = dict(CATEGORIES)[item.snapshot['category']]
        item.kind_label = dict(KINDS)[item.snapshot['kind']]
        item.answer_label = '、'.join({'T': '正确', 'F': '错误'}.get(a, a) for a in item.snapshot['answer'])
        item.selected_label = '、'.join({'T': '正确', 'F': '错误'}.get(a, a) for a in item.selected)
    return page(request, 'result', {'nav': 'history', 'practice': session, 'items': items, 'total': len(items), 'correct_count': sum(i.correct is True for i in items), 'wrong_count': sum(i.correct is False and i.answered_at is not None for i in items), 'unanswered': sum(i.answered_at is None for i in items)})


@login_required
def history(request):
    sessions = Session.objects.filter(user=request.user).annotate(total=Count('items'), answered=Count('items', filter=Q(items__answered_at__isnull=False))).order_by('-created_at', '-pk')
    return page(request, 'history', {'nav': 'history', 'page_obj': Paginator(sessions, 15).get_page(request.GET.get('page'))})


@login_required
def mistakes(request):
    qs = Mistake.objects.filter(user=request.user, active=True).select_related('question')
    category = request.GET.get('category', '')
    kind = request.GET.get('kind', '')
    if category in dict(CATEGORIES):
        qs = qs.filter(question__category=category)
    if kind in dict(KINDS):
        qs = qs.filter(question__kind=kind)
    return page(request, 'mistakes', {'nav': 'mistakes', 'page_obj': Paginator(qs, 12).get_page(request.GET.get('page')), 'category': category, 'kind': kind, 'wrong_count': qs.count()})


@login_required
@require_POST
def remove_mistake(request, pk):
    mistake = get_object_or_404(Mistake, pk=pk, user=request.user)
    mistake.active = False
    mistake.removed_at = timezone.now()
    mistake.save(update_fields=['active', 'removed_at'])
    messages.success(request, '已从错题本移除，历史记录仍保留；再次答错会重新加入。')
    return redirect('mistakes')


def require_admin(user):
    if not user.is_staff:
        raise PermissionDenied
    return True


@login_required
@user_passes_test(require_admin)
def accounts(request):
    form = AccountForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(**form.cleaned_data)
            Profile.objects.create(user=user)
            Audit.objects.create(actor=request.user, action='创建账号', target=user.username)
        messages.success(request, '账号已创建，首次登录需修改密码。')
        return redirect('accounts')
    users = User.objects.all().order_by('-date_joined')
    search = request.GET.get('search', '')[:150]
    if search:
        users = users.filter(Q(username__icontains=search) | Q(first_name__icontains=search))
    return page(request, 'accounts', {'nav': 'accounts', 'form': form, 'page_obj': Paginator(users, 20).get_page(request.GET.get('page')), 'search': search})


@login_required
@user_passes_test(require_admin)
@require_POST
def account_action(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk or (target.is_superuser and not request.user.is_superuser):
        messages.error(request, '不能在这里更改自己的账号或更高权限的管理员。')
        return redirect('accounts')
    action = request.POST.get('action')
    if action not in ('toggle', 'reset'):
        return HttpResponse('无效操作', status=400)
    try:
        if action == 'reset':
            validate_password(request.POST.get('password', ''), target)
        with transaction.atomic():
            target = User.objects.select_for_update().get(pk=pk)
            profile, _ = Profile.objects.select_for_update().get_or_create(user=target)
            if action == 'toggle':
                target.is_active = not target.is_active
            else:
                target.set_password(request.POST['password'])
                profile.must_change_password = True
            profile.session_version += 1
            target.save()
            profile.save()
            Audit.objects.create(actor=request.user, action='重置密码' if action == 'reset' else '切换账号状态', target=target.username)
        messages.success(request, '账号已更新，原有会话已撤销。')
    except ValidationError as exc:
        messages.error(request, '；'.join(exc.messages))
    return redirect('accounts')


@login_required
@user_passes_test(require_admin)
def batch_accounts(request):
    if request.method == 'GET':
        response = HttpResponse('\ufeffusername,first_name,password\n', content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="accounts-template.csv"'
        return response
    upload = request.FILES.get('file')
    errors, created = [], 0
    if not upload or upload.size > 1024 * 1024:
        messages.error(request, '请上传不超过 1 MiB 的 UTF-8 CSV 文件。')
        return redirect('accounts')
    try:
        reader = csv.DictReader(io.StringIO(upload.read().decode('utf-8-sig')))
        if reader.fieldnames != ['username', 'first_name', 'password']:
            raise ValueError('表头须为 username,first_name,password，请使用模板。')
        rows = list(reader)
        if len(rows) > 500:
            raise ValueError('每次最多导入 500 个账号。')
        for line, row in enumerate(rows, 2):
            form = AccountForm(row)
            if form.is_valid():
                with transaction.atomic():
                    user = User.objects.create_user(**form.cleaned_data)
                    Profile.objects.create(user=user)
                    Audit.objects.create(actor=request.user, action='批量创建账号', target=user.username)
                created += 1
            else:
                errors.append({'line': line, 'username': row.get('username', ''), 'error': '；'.join(str(m) for values in form.errors.values() for m in values)})
    except (UnicodeError, ValueError, csv.Error) as exc:
        errors.append({'line': '文件', 'username': '', 'error': str(exc)})
    return page(request, 'batch', {'nav': 'accounts', 'created': created, 'errors': errors})
