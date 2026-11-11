"""WSGI 部署入口，供 Gunicorn、uWSGI 等服务器加载。"""

import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 创建标准 WSGI application 对象。
application = get_wsgi_application()
