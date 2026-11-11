"""Django 应用注册信息。"""

from django.apps import AppConfig


class DatabaseManagerConfig(AppConfig):
    """声明业务应用名称和默认主键类型。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "database_manager"
    verbose_name = "数据库实例管理"
