"""Celery 应用入口与自动任务发现配置。"""

import os

from celery import Celery


# Django 启动时不总是经过 manage.py，因此这里再次指定默认配置模块。
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 创建 Celery 应用，名称通常与项目包保持一致。
app = Celery("config")

# 从 Django settings 中读取以 CELERY_ 为前缀的配置。
app.config_from_object("django.conf:settings", namespace="CELERY")

# 自动发现所有已注册 Django app 下的 tasks.py。
app.autodiscover_tasks()
