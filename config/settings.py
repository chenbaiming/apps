"""Django 与 Celery 的集中配置。"""

import os
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from dotenv import load_dotenv


# 项目根目录用于拼接静态目录、SQLite 文件等路径。
BASE_DIR = Path(__file__).resolve().parent.parent

# 读取本地 .env；已存在的系统环境变量优先级更高，不会被文件覆盖。
load_dotenv(BASE_DIR / ".env", override=False)


def env_bool(name: str, default: bool = False) -> bool:
    """把环境变量安全地解析成布尔值。"""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


# 开发环境提供可运行的默认值；生产环境应通过环境变量覆盖。
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "dev-only-change-me-database-instance-manager-secret",
)
DEBUG = env_bool("DJANGO_DEBUG", default=True)

# 只允许配置过的主机访问，避免 Host 头攻击。
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
]


INSTALLED_APPS = [
    # Django 内置应用。
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # REST API 提供数据序列化、通用 CRUD 和权限控制。
    "rest_framework",
    # 本项目的业务领域应用。
    "database_manager",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # 放在最后，使计时范围覆盖随后执行的视图以及其余内层处理逻辑。
    "database_manager.middleware.RequestTimingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# 默认使用 SQLite 方便直接运行；生产环境可切换为 PostgreSQL 等数据库。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Fernet 负责加密数据库账号密码；密钥不进入数据库，也不应提交到 Git。
CREDENTIAL_ENCRYPTION_KEY = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")

# TCP 探测的超时时间必须在“及时反馈”和“容忍网络抖动”之间折中。
TCP_PROBE_TIMEOUT_SECONDS = float(os.getenv("TCP_PROBE_TIMEOUT_SECONDS", "2"))


# API 默认要求登录，避免实例凭据和探测能力被匿名调用。
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # 把外键保护删除等数据库异常转换成 HTTP 409 响应。
    "EXCEPTION_HANDLER": "database_manager.exceptions.api_exception_handler",
}


# Celery 通过 Redis 接收和保存任务结果。
CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Beat 定时计划集中在此处，便于审计和修改。
CELERY_BEAT_SCHEDULE = {
    "rotate-database-passwords-every-12-hours": {
        "task": "database_manager.tasks.dispatch_password_rotation",
        # 每小时的第 0 分钟，且小时只能是 0 点或 12 点。
        "schedule": crontab(minute=0, hour="*/12"),
    },
    "collect-daily-instance-statistics": {
        "task": "database_manager.tasks.collect_daily_instance_statistics",
        # 每天 00:00（按 Celery 配置的 Asia/Shanghai 时区）。
        "schedule": crontab(minute=0, hour=0),
    },
}


# 控制台日志便于本地运行；生产环境可替换为结构化日志后端。
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
}
