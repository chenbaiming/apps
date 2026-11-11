"""REST API、权限和端口探测接口测试。"""

import socket

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from database_manager.models import Cluster, DatabaseInstance, Department
from database_manager.tests.constants import TEST_FERNET_KEY


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY)
class DatabaseAPITests(APITestCase):
    """验证 CRUD、密码脱敏和受保护删除。"""

    def setUp(self):
        # 强制登录测试用户，等价于携带有效认证信息发起请求。
        self.user = get_user_model().objects.create_user(
            username="api-test",
            password="test-password-123",
        )
        self.client.force_authenticate(self.user)

    def test_department_cluster_and_instance_crud(self):
        department_response = self.client.post(
            reverse("department-list"),
            {"name": "平台部", "code": "PLATFORM", "description": "平台团队"},
            format="json",
        )
        self.assertEqual(department_response.status_code, status.HTTP_201_CREATED)

        cluster_response = self.client.post(
            reverse("cluster-list"),
            {
                "department": department_response.data["id"],
                "name": "支付集群",
                "code": "PAYMENT",
            },
            format="json",
        )
        self.assertEqual(cluster_response.status_code, status.HTTP_201_CREATED)

        raw_password = "Very-Secret-Password-123!"
        instance_response = self.client.post(
            reverse("instance-list"),
            {
                "cluster": cluster_response.data["id"],
                "name": "payment-mysql-01",
                "instance_code": "PAYMENT-MYSQL-01",
                "engine": "mysql",
                "host": "127.0.0.1",
                "port": 3306,
                "database_username": "payment_user",
                "password": raw_password,
            },
            format="json",
        )
        self.assertEqual(instance_response.status_code, status.HTTP_201_CREATED)

        # 响应中不能回传 password，也不能暴露底层的密文字段。
        self.assertNotIn("password", instance_response.data)
        self.assertNotIn("password_ciphertext", instance_response.data)
        self.assertTrue(instance_response.data["has_password"])
        instance = DatabaseInstance.objects.get(pk=instance_response.data["id"])
        self.assertTrue(instance.verify_database_password(raw_password))

        # 普通更新不传密码时应保留原凭据。
        old_ciphertext = instance.password_ciphertext
        update_response = self.client.patch(
            reverse("instance-detail", args=[instance.id]),
            {"description": "已更新说明"},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        instance.refresh_from_db()
        self.assertEqual(instance.password_ciphertext, old_ciphertext)

    def test_create_instance_requires_password(self):
        department = Department.objects.create(name="安全部", code="SEC")
        cluster = Cluster.objects.create(
            department=department,
            name="审计集群",
            code="AUDIT",
        )
        response = self.client.post(
            reverse("instance-list"),
            {
                "cluster": cluster.id,
                "name": "audit-db",
                "instance_code": "AUDIT-DB-01",
                "engine": "postgresql",
                "host": "127.0.0.1",
                "port": 5432,
                "database_username": "audit_user",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_probe_api_updates_instance_status(self):
        department = Department.objects.create(name="网络部", code="NET")
        cluster = Cluster.objects.create(
            department=department,
            name="探针集群",
            code="PROBE",
        )
        instance = DatabaseInstance(
            cluster=cluster,
            name="probe-target",
            instance_code="PROBE-001",
            engine=DatabaseInstance.Engine.REDIS,
            host="127.0.0.1",
            port=6379,
            database_username="probe_user",
        )
        instance.set_database_password("Probe-Password-123!")
        instance.save()

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(("127.0.0.1", 0))
        server_socket.listen(1)
        instance.port = server_socket.getsockname()[1]
        instance.save(update_fields=["port"])

        try:
            response = self.client.post(
                reverse("instance-probe-port", args=[instance.id]),
                format="json",
            )
        finally:
            server_socket.close()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["reachable"])
        instance.refresh_from_db()
        self.assertEqual(instance.probe_status, DatabaseInstance.ProbeStatus.ONLINE)

    def test_delete_department_in_use_returns_conflict(self):
        department = Department.objects.create(name="财务部", code="FIN")
        Cluster.objects.create(department=department, name="财务集群", code="FIN-DB")

        response = self.client.delete(reverse("department-detail", args=[department.id]))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Department.objects.filter(pk=department.id).exists())

    def test_api_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("department-list"))
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )
