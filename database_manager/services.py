"""可被 HTTP 接口、Celery 任务和测试复用的领域服务。"""

import socket
import time
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import (
    Cluster,
    DailyInstanceStatistics,
    DatabaseInstance,
    PasswordRotationLog,
)
from .security import generate_database_password


@dataclass(frozen=True)
class TcpProbeResult:
    """TCP 探测的结构化返回值，供 API 直接序列化。"""

    reachable: bool
    latency_ms: float
    error: str = ""


def probe_tcp_port(host: str, port: int, timeout: float | None = None) -> TcpProbeResult:
    """尝试建立一次短连接，判断目标 TCP 端口是否可达。"""
    # 未显式传超时时，使用配置值，避免请求无限等待。
    effective_timeout = (
        settings.TCP_PROBE_TIMEOUT_SECONDS if timeout is None else timeout
    )
    started_at = time.perf_counter()

    try:
        # 连接成功后立即由上下文管理器关闭 socket，不发送应用层协议数据。
        with socket.create_connection((host, port), timeout=effective_timeout):
            latency_ms = (time.perf_counter() - started_at) * 1000
            return TcpProbeResult(reachable=True, latency_ms=round(latency_ms, 3))
    except OSError as exc:
        # 超时、拒绝连接和 DNS 失败都按“不可达”处理，并保留简短原因。
        latency_ms = (time.perf_counter() - started_at) * 1000
        return TcpProbeResult(
            reachable=False,
            latency_ms=round(latency_ms, 3),
            error=str(exc),
        )


def probe_and_record_instance(instance: DatabaseInstance) -> TcpProbeResult:
    """执行 TCP 探测，并把最新结果写回实例。"""
    result = probe_tcp_port(instance.host, instance.port)

    # 只更新探测相关字段，避免覆盖同时发生的密码轮换结果。
    instance.probe_status = (
        DatabaseInstance.ProbeStatus.ONLINE
        if result.reachable
        else DatabaseInstance.ProbeStatus.OFFLINE
    )
    instance.last_probe_at = timezone.now()
    instance.save(update_fields=["probe_status", "last_probe_at", "updated_at"])
    return result


def rotate_instance_password(instance_id: int) -> PasswordRotationLog:
    """为单个实例生成新密码并原子化更新密文和版本号。"""
    with transaction.atomic():
        # 行锁防止 Beat 重试或人工任务导致同一实例并发轮换。
        instance = DatabaseInstance.objects.select_for_update().get(pk=instance_id)
        new_password = generate_database_password()

        # 模型方法只保存 Fernet 密文，明文不会写入任何字段或日志。
        instance.set_database_password(new_password)
        instance.save(
            update_fields=[
                "password_ciphertext",
                "password_version",
                "password_updated_at",
                "updated_at",
            ]
        )

        # 审计记录只包含版本和结果，避免把新密码泄露到日志系统。
        return PasswordRotationLog.objects.create(
            instance=instance,
            status=PasswordRotationLog.Status.SUCCESS,
            password_version=instance.password_version,
            message="密码已随机生成并加密保存",
        )


def collect_daily_instance_statistics(
    stat_date: date | None = None,
) -> list[DailyInstanceStatistics]:
    """按集群汇总实例数量，并以幂等方式写入每日统计表。"""
    # 未指定日期时使用项目时区下的今天。
    target_date = stat_date or timezone.localdate()

    # 数据库先完成聚合，减少把全部实例加载到 Python 的内存开销。
    count_map = {
        row["cluster_id"]: row["total"]
        for row in DatabaseInstance.objects.values("cluster_id").annotate(
            total=Count("id")
        )
    }

    statistics = []
    # 遍历所有集群，因此没有实例的集群也会得到数量为 0 的快照。
    for cluster in Cluster.objects.select_related("department").iterator():
        statistic, _ = DailyInstanceStatistics.objects.update_or_create(
            stat_date=target_date,
            department=cluster.department,
            cluster=cluster,
            defaults={"instance_count": count_map.get(cluster.id, 0)},
        )
        statistics.append(statistic)
    return statistics
