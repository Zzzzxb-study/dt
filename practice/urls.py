from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'), path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'), path('password/', views.password_view, name='password'),
    path('start/', views.start, name='start'), path('sessions/<uuid:pk>/', views.session_view, name='session'),
    path('items/<int:pk>/answer/', views.answer, name='answer'), path('sessions/<uuid:pk>/finish/', views.finish, name='finish'),
    path('sessions/<uuid:pk>/result/', views.result, name='result'), path('history/', views.history, name='history'),
    path('mistakes/', views.mistakes, name='mistakes'), path('mistakes/<int:pk>/remove/', views.remove_mistake, name='remove_mistake'),
    path('accounts/', views.accounts, name='accounts'), path('accounts/<int:pk>/action/', views.account_action, name='account_action'),
    path('accounts/batch/', views.batch_accounts, name='batch_accounts'),
]
