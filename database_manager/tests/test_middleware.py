"""请求耗时中间件测试。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from database_manager.models import RequestMetric
from database_manager.tests.constants import TEST_FERNET_KEY


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY)
class RequestTimingMiddlewareTests(TestCase):
    """验证请求会写入指标并返回耗时响应头。"""

    def setUp(self):
        # 使用会话登录，让请求经过真实的 AuthenticationMiddleware。
        self.user = get_user_model().objects.create_user(
            username="middleware-user",
            password="middleware-password-123",
        )
        self.client.force_login(self.user)

    def test_request_metric_and_response_header_are_created(self):
        response = self.client.get(reverse("department-list"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-Duration-Ms", response)
        metric = RequestMetric.objects.latest("created_at")
        self.assertEqual(metric.method, "GET")
        self.assertIn("/api/departments/", metric.path)
        self.assertEqual(metric.status_code, 200)
        self.assertEqual(metric.user_id, self.user.id)
        self.assertGreaterEqual(metric.duration_ms, 0)
