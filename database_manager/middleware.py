"""记录每个 HTTP 请求耗时的 Django 中间件。"""

import ipaddress
import logging
import time
from decimal import Decimal

from django.utils import timezone

from .models import RequestMetric


logger = logging.getLogger(__name__)


class RequestTimingMiddleware:
    """在请求前后计时，并尽力把耗时写入数据库。"""

    def __init__(self, get_response):
        # Django 启动时注入下一个中间件或最终视图。
        self.get_response = get_response

    def __call__(self, request):
        # 使用高精度单调时钟，避免系统时间调整导致负耗时。
        started_at = time.perf_counter()

        try:
            # 继续执行后续中间件和实际视图。
            response = self.get_response(request)
        except Exception:
            # 即使视图抛异常，也先记录一条 500 指标再让异常继续传播。
            self._record_metric(request, started_at, 500)
            raise

        # 正常响应使用业务声明的 HTTP 状态码。
        self._record_metric(request, started_at, response.status_code)

        # 同时把耗时放进响应头，便于前端和网关快速观察。
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        response["X-Request-Duration-Ms"] = f"{elapsed_ms:.3f}"
        return response

    def _record_metric(self, request, started_at: float, status_code: int) -> None:
        """完成计时并落库；监控故障不能影响正常业务响应。"""
        elapsed_ms = (time.perf_counter() - started_at) * 1000

        # REMOTE_ADDR 不容易被请求头伪造；格式不合法时保存为空。
        remote_addr = request.META.get("REMOTE_ADDR")
        try:
            ipaddress.ip_address(remote_addr) if remote_addr else None
        except ValueError:
            remote_addr = None

        # 认证用户记录稳定 ID；匿名请求保持空值。
        user_id = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            user_id = user.pk

        try:
            RequestMetric.objects.create(
                method=request.method[:10],
                path=request.get_full_path()[:500],
                status_code=status_code,
                duration_ms=Decimal(str(round(elapsed_ms, 3))),
                remote_addr=remote_addr,
                user_id=user_id,
            )
        except Exception:
            # 指标表不可用时只记录日志，绝不把观测逻辑变成业务单点故障。
            logger.exception("请求耗时指标写入失败")
