"""部门、集群、实例及运维数据的 REST API 视图。"""

from django.db.models import Count
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Cluster,
    DailyInstanceStatistics,
    DatabaseInstance,
    Department,
    PasswordRotationLog,
    RequestMetric,
)
from .serializers import (
    ClusterSerializer,
    DailyInstanceStatisticsSerializer,
    DatabaseInstanceSerializer,
    DepartmentSerializer,
    PasswordRotationLogSerializer,
    RequestMetricSerializer,
    TcpProbeResponseSerializer,
)
from .services import probe_and_record_instance


class DepartmentViewSet(viewsets.ModelViewSet):
    """提供部门的列表、创建、详情、修改和删除。"""

    # annotate 一次查询得到集群数，避免列表页产生 N+1 查询。
    queryset = Department.objects.annotate(cluster_count=Count("clusters")).order_by("code")
    serializer_class = DepartmentSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["code", "name", "created_at"]


class ClusterViewSet(viewsets.ModelViewSet):
    """提供集群的完整 CRUD。"""

    queryset = Cluster.objects.select_related("department").annotate(
        instance_count=Count("instances")
    ).order_by("department_id", "code")
    serializer_class = ClusterSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code", "department__name", "department__code"]
    ordering_fields = ["code", "name", "created_at"]


class DatabaseInstanceViewSet(viewsets.ModelViewSet):
    """提供实例 CRUD，并支持查询过滤和端口探测。"""

    queryset = DatabaseInstance.objects.select_related(
        "cluster",
        "cluster__department",
    ).order_by("cluster_id", "name")
    serializer_class = DatabaseInstanceSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "name",
        "instance_code",
        "host",
        "database_username",
        "cluster__name",
        "cluster__department__name",
    ]
    ordering_fields = ["name", "created_at", "last_probe_at", "password_updated_at"]

    def get_queryset(self):
        """在基础查询上追加集群、部门和数据库类型过滤。"""
        queryset = super().get_queryset()
        cluster_id = self.request.query_params.get("cluster")
        department_id = self.request.query_params.get("department")
        engine = self.request.query_params.get("engine")
        probe_status = self.request.query_params.get("probe_status")

        if cluster_id:
            queryset = queryset.filter(cluster_id=cluster_id)
        if department_id:
            queryset = queryset.filter(cluster__department_id=department_id)
        if engine:
            queryset = queryset.filter(engine=engine)
        if probe_status:
            queryset = queryset.filter(probe_status=probe_status)
        return queryset

    @action(detail=True, methods=["post"], url_path="probe-port")
    def probe_port(self, request, pk=None):
        """同步探测实例的 TCP 端口，并返回本次延迟和结果。"""
        instance = self.get_object()

        # 连接超时由配置控制，默认 2 秒，适合在线 API 的响应时间。
        result = probe_and_record_instance(instance)
        payload = {
            "instance_id": instance.id,
            "host": instance.host,
            "port": instance.port,
            "reachable": result.reachable,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "probed_at": timezone.now(),
        }
        serializer = TcpProbeResponseSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DailyInstanceStatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    """提供每日统计的查询能力，统计由 Celery 生成。"""

    queryset = DailyInstanceStatistics.objects.select_related(
        "department",
        "cluster",
    ).order_by("-stat_date", "department_id", "cluster_id")
    serializer_class = DailyInstanceStatisticsSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["stat_date", "instance_count", "department"]

    def get_queryset(self):
        """允许按日期、部门和集群筛选历史快照。"""
        queryset = super().get_queryset()
        stat_date = self.request.query_params.get("date")
        department_id = self.request.query_params.get("department")
        cluster_id = self.request.query_params.get("cluster")
        if stat_date:
            queryset = queryset.filter(stat_date=stat_date)
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if cluster_id:
            queryset = queryset.filter(cluster_id=cluster_id)
        return queryset


class PasswordRotationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """提供密码轮换审计记录查询。"""

    queryset = PasswordRotationLog.objects.select_related("instance").order_by("-created_at")
    serializer_class = PasswordRotationLogSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "password_version"]


class RequestMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """提供请求耗时记录查询。"""

    queryset = RequestMetric.objects.order_by("-created_at")
    serializer_class = RequestMetricSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "duration_ms", "status_code"]
