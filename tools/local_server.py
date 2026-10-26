"""Windows/跨平台本地预览；正式部署使用容器。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / '.deps')]
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from waitress import serve
from config.wsgi import application
from django.contrib.staticfiles.handlers import StaticFilesHandler

if __name__ == '__main__':
    serve(StaticFilesHandler(application), host='127.0.0.1', port=8000, threads=4)
