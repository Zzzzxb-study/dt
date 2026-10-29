from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import CATEGORIES, KINDS, MODES


class StartForm(forms.Form):
    categories = forms.MultipleChoiceField(choices=CATEGORIES)
    kinds = forms.MultipleChoiceField(choices=KINDS, required=False)
    mode = forms.ChoiceField(choices=MODES)
    count = forms.IntegerField(min_value=0, max_value=10000)
    restart = forms.BooleanField(required=False)
    minutes = forms.IntegerField(min_value=1, max_value=240, initial=60)
    subcategory = forms.ChoiceField(choices=[('', '全部'), ('underwriting', '车险承保'), ('claims', '车险理赔')], required=False)

    def clean(self):
        data = super().clean()
        mode, count = data.get('mode'), data.get('count')
        if mode == 'exam' and count is not None and not 1 <= count <= 300:
            self.add_error('count', '模拟练习每次为 1—300 题。')
        if mode != 'sequential' and count == 0:
            self.add_error('count', '全部未练题仅用于顺序练习。')
        if mode != 'sequential' and data.get('restart'):
            self.add_error('restart', '重新通刷仅用于顺序练习。')
        return data


class AccountForm(forms.Form):
    username = forms.CharField(label='账号', max_length=150)
    first_name = forms.CharField(label='姓名', max_length=150, required=False)
    password = forms.CharField(label='初始密码', widget=forms.PasswordInput)

    def clean_username(self):
        value = self.cleaned_data['username'].strip()
        User._meta.get_field('username').run_validators(value)
        if User.objects.filter(username=value).exists():
            raise forms.ValidationError('账号已存在')
        return value

    def clean(self):
        data = super().clean()
        if data.get('password'):
            validate_password(data['password'], User(username=data.get('username', ''), first_name=data.get('first_name', '')))
        return data
