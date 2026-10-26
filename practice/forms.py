from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import CATEGORIES, KINDS, MODES


class StartForm(forms.Form):
    categories = forms.MultipleChoiceField(choices=CATEGORIES)
    kinds = forms.MultipleChoiceField(choices=KINDS, required=False)
    mode = forms.ChoiceField(choices=MODES)
    count = forms.IntegerField(min_value=1, max_value=300)
    minutes = forms.IntegerField(min_value=1, max_value=240, initial=60)
    subcategory = forms.ChoiceField(choices=[('', '全部'), ('underwriting', '车险承保'), ('claims', '车险理赔')], required=False)


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
