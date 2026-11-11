"""业务 API 路由。"""

from django.urls import include, path


from rest_framework.routers import DefaultRouter

from .views import (
    ClusterViewSet,
    DailyInstanceStatisticsViewSet,
    DatabaseInstanceViewSet,
    DepartmentViewSet,
    PasswordRotationLogViewSet,
    RequestMetricViewSet,
)


router = DefaultRouter()

# ModelViewSet 自动生成 list/create/retrieve/update/partial_update/destroy 路由。
router.register("departments", DepartmentViewSet, basename="department")
router.register("clusters", ClusterViewSet, basename="cluster")
router.register("instances", DatabaseInstanceViewSet, basename="instance")

# 运维数据由任务自动产生，对外只开放读取接口。
router.register("daily-statistics", DailyInstanceStatisticsViewSet, basename="daily-statistics")
router.register("password-rotation-logs", PasswordRotationLogViewSet, basename="password-rotation-log")
router.register("request-metrics", RequestMetricViewSet, basename="request-metric")

urlpatterns = [
    # /api/ 本身提供可浏览的 API 根入口。
    path("", include(router.urls)),
]
