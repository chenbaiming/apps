"""统一把数据库保护异常转换成易读的 HTTP 响应。"""

from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    """先尝试 DRF 默认处理，再补充受保护删除冲突。"""
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    if isinstance(exc, ProtectedError):
        # 409 表示资源当前状态与外键保护约束冲突。
        return Response(
            {
                "detail": "该资源仍被下级对象引用，不能删除。请先处理实例或集群。",
                "protected_objects": [
                    str(obj) for obj in list(exc.protected_objects)[:20]
                ],
            },
            status=status.HTTP_409_CONFLICT,
        )

    # 未识别的异常交回 Django，以便记录完整堆栈并返回 500。
    return None
