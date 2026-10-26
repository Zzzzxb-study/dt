"""Interactive first-run initialization, without a built-in account/password."""
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / '.deps')]
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth.models import User
from django.core.management import call_command

if __name__ == '__main__':
    call_command('migrate', verbosity=0)
    call_command('import_bank')
    if not User.objects.filter(is_superuser=True, is_active=True).exists():
        print('\n首次使用，请在本机创建管理员账号。密码输入不会显示。\n')
        call_command('createsuperuser')
    print('\n练习应用：http://127.0.0.1:8000\n保持此窗口开启；按 Ctrl+C 停止。\n')
    threading.Timer(1, lambda: webbrowser.open('http://127.0.0.1:8000')).start()
    from waitress import serve
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from config.wsgi import application
    serve(StaticFilesHandler(application), host='127.0.0.1', port=8000, threads=4)
