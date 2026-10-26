"""Validate production settings without printing generated credentials."""
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / '.deps')]
os.environ.update(APP_ENV='production', SECRET_KEY=secrets.token_urlsafe(64), ALLOWED_HOSTS='practice.example.com', CSRF_TRUSTED_ORIGINS='https://practice.example.com', POSTGRES_HOST='db', POSTGRES_PASSWORD=secrets.token_urlsafe(32), DJANGO_SETTINGS_MODULE='config.settings')
import django
django.setup()
from django.core.management import call_command
call_command('check', deploy=True, fail_level='WARNING')
