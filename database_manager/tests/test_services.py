"""密码轮换、统计和 TCP 探测领域服务测试。"""

import socket
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings

from database_manager.models import (
    Cluster,
    DailyInstanceStatistics,
    DatabaseInstance,
    Department,
    PasswordRotationLog,
)
from database_manager.services import (
    collect_daily_instance_statistics,
    probe_tcp_port,
    rotate_instance_password,
)
from database_manager.tasks import dispatch_password_rotation
from database_manager.tests.constants import TEST_FERNET_KEY


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY)
class ServiceTests(TestCase):
    """验证服务的正确性和幂等行为。"""

    def setUp(self):
        self.department = Department.objects.create(name="研发部", code="RD")
        self.cluster = Cluster.objects.create(
            department=self.department,
            name="用户中心",
            code="USER",
        )
        self.empty_cluster = Cluster.objects.create(
            department=self.department,
            name="空集群",
            code="EMPTY",
        )
        self.instance = self._create_instance("USER-001", "user-db-01")

    def _create_instance(self, code, name):
        instance = DatabaseInstance(
            cluster=self.cluster,
            name=name,
            instance_code=code,
            engine=DatabaseInstance.Engine.POSTGRESQL,
            host="127.0.0.1",
            port=5432,
            database_username="app_user",
        )
        instance.set_database_password("Initial-Password-123!")
        instance.save()
        return instance

    def test_rotation_changes_ciphertext_and_records_audit(self):
        old_ciphertext = self.instance.password_ciphertext
        old_version = self.instance.password_version

        rotation_log = rotate_instance_password(self.instance.id)
        self.instance.refresh_from_db()

        self.assertNotEqual(self.instance.password_ciphertext, old_ciphertext)
        self.assertEqual(self.instance.password_version, old_version + 1)
        self.assertEqual(rotation_log.status, PasswordRotationLog.Status.SUCCESS)
        self.assertEqual(
            PasswordRotationLog.objects.filter(instance=self.instance).count(),
            1,
        )

    def test_dispatch_queues_one_task_per_enabled_instance(self):
        disabled_instance = self._create_instance("USER-002", "user-db-02")
        disabled_instance.rotation_enabled = False
        disabled_instance.save(update_fields=["rotation_enabled"])

        with patch(
            "database_manager.tasks.rotate_database_instance_password.delay"
        ) as delay:
            result = dispatch_password_rotation.run()

        self.assertEqual(result, {"dispatched": 1})
        delay.assert_called_once_with(self.instance.id)

    def test_daily_statistics_count_instances_and_are_idempotent(self):
        target_date = date(2026, 11, 10)
        self._create_instance("USER-002", "user-db-02")

        first_result = collect_daily_instance_statistics(target_date)
        second_result = collect_daily_instance_statistics(target_date)

        self.assertEqual(len(first_result), 2)
        self.assertEqual(len(second_result), 2)
        self.assertEqual(DailyInstanceStatistics.objects.count(), 2)
        user_stat = DailyInstanceStatistics.objects.get(cluster=self.cluster)
        empty_stat = DailyInstanceStatistics.objects.get(cluster=self.empty_cluster)
        self.assertEqual(user_stat.instance_count, 2)
        self.assertEqual(empty_stat.instance_count, 0)

    def test_tcp_probe_can_connect_to_a_listening_socket(self):
        # 监听本机随机空闲端口，避免依赖外部数据库服务。
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen(1)
        port = server_socket.getsockname()[1]
        try:
            result = probe_tcp_port("127.0.0.1", port, timeout=1)
        finally:
            server_socket.close()

        self.assertTrue(result.reachable)
        self.assertEqual(result.error, "")
        self.assertGreaterEqual(result.latency_ms, 0)
