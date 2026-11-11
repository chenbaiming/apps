"""ASGI 部署入口，供异步服务器加载。"""

import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 创建标准 ASGI application 对象。
application = get_asgi_application()
