"""项目级 URL 路由表。"""

from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    # Django 管理后台用于初始化用户和执行基础运维。
    path("admin/", admin.site.urls),
    # DRF 登录页为基于浏览器的 API 调试提供会话登录能力。
    path("api-auth/", include("rest_framework.urls")),
    # 所有业务 API 统一挂在 /api/ 下。
    path("api/", include("database_manager.urls")),
]
