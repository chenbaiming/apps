"""Celery 异步任务：密码轮换调度与每日统计。"""

import logging

from celery import shared_task

from .models import DatabaseInstance, PasswordRotationLog
from .services import (
    collect_daily_instance_statistics as collect_daily_statistics_services,
    rotate_instance_password as rotate_password_service,
)


logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def dispatch_password_rotation(self):
    """每 12 小时扫描一次实例，并为每个实例投递独立任务。"""
    # 查询开启自动轮换的实例 ID，避免一次任务内部长时间串行处理。
    instance_ids = list(
        DatabaseInstance.objects.filter(rotation_enabled=True).values_list("id", flat=True)
    )

    try:
        # 每个实例单独入队，某个实例失败不会阻塞其他实例。
        for instance_id in instance_ids:
            rotate_database_instance_password.delay(instance_id)
    except Exception as exc:
        # 消息队列暂时不可用时，按指数退避重试整个分发动作。
        logger.exception("密码轮换任务分发失败")
        raise self.retry(exc=exc, countdown=min(60 * (2**self.request.retries), 3600))

    logger.info("已投递 %s 个数据库实例的密码轮换任务", len(instance_ids))
    return {"dispatched": len(instance_ids)}


@shared_task(bind=True, max_retries=3)
def rotate_database_instance_password(self, instance_id: int):
    """为单个实例执行可审计、可重试的密码轮换。"""
    try:
        # 真正的新密码生成、加密和数据库更新都由领域服务完成。
        rotation_log = rotate_password_service(instance_id)
        return {
            "instance_id": instance_id,
            "password_version": rotation_log.password_version,
            "status": rotation_log.status,
        }
    except DatabaseInstance.DoesNotExist:
        # 实例在任务排队期间被删除时无需重试，直接结束即可。
        logger.warning("实例 %s 已不存在，跳过密码轮换", instance_id)
        return {"instance_id": instance_id, "status": "skipped"}
    except Exception as exc:
        # 仅记录错误信息和实例 ID，禁止把密码或密文写入日志。
        logger.exception("实例 %s 密码轮换失败", instance_id)
        if DatabaseInstance.objects.filter(pk=instance_id).exists():
            current_version = (
                DatabaseInstance.objects.filter(pk=instance_id)
                .values_list("password_version", flat=True)
                .first()
                or 0
            )
            PasswordRotationLog.objects.create(
                instance_id=instance_id,
                status=PasswordRotationLog.Status.FAILED,
                password_version=current_version,
                message=f"轮换失败：{type(exc).__name__}",
            )

        # 使用指数退避重试，降低加密配置或数据库瞬时故障造成的影响。
        raise self.retry(exc=exc, countdown=min(60 * (2**self.request.retries), 3600))


@shared_task
def collect_daily_instance_statistics():
    """每天零点生成部门和集群维度的实例数量快照。"""
    statistics = collect_daily_statistics_services()
    logger.info("已生成 %s 条每日实例统计", len(statistics))
    return {"generated": len(statistics)}
