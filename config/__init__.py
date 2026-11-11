"""项目配置包。"""

# 确保 Django 启动时 Celery 应用也完成初始化，使 @shared_task 能被正确注册。
from .celery import app as celery_app

__all__ = ("celery_app",)
