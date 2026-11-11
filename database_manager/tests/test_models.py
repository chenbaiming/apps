"""模型约束和凭据加密测试。"""

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.test.utils import override_settings

from database_manager.models import Cluster, DatabaseInstance, Department
from database_manager.security import decrypt_secret
from database_manager.tests.constants import TEST_FERNET_KEY


@override_settings(CREDENTIAL_ENCRYPTION_KEY=TEST_FERNET_KEY)
class CredentialModelTests(TestCase):
    """验证密码只以密文形式持久化。"""

    def setUp(self):
        # 准备部门与集群，供多个实例测试复用。
        self.department = Department.objects.create(name="基础架构部", code="INFRA")
        self.cluster = Cluster.objects.create(
            department=self.department,
            name="订单主库",
            code="ORDER",
        )

    def test_password_is_encrypted_at_rest_and_can_be_verified(self):
        instance = DatabaseInstance(
            cluster=self.cluster,
            name="order-mysql-01",
            instance_code="ORDER-MYSQL-01",
            engine=DatabaseInstance.Engine.MYSQL,
            host="127.0.0.1",
            port=3306,
            database_username="db_admin",
        )
        raw_password = "Initial-Password-123!"

        instance.set_database_password(raw_password)
        instance.save()
        instance.refresh_from_db()

        # 数据库字段不能出现明文，并且应该可以用同一密钥还原。
        self.assertNotEqual(instance.password_ciphertext, raw_password)
        self.assertNotIn(raw_password, instance.password_ciphertext)
        self.assertEqual(decrypt_secret(instance.password_ciphertext), raw_password)
        self.assertTrue(instance.verify_database_password(raw_password))
        self.assertFalse(instance.verify_database_password("wrong-password"))

    def test_instance_name_is_unique_inside_cluster(self):
        common_data = {
            "cluster": self.cluster,
            "name": "duplicate-name",
            "engine": DatabaseInstance.Engine.MYSQL,
            "host": "127.0.0.1",
            "port": 3306,
            "database_username": "db_admin",
        }
        DatabaseInstance.objects.create(
            instance_code="DUP-001",
            **common_data,
        )

        # 同一集群内的重名实例应触发数据库唯一约束。
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DatabaseInstance.objects.create(
                    instance_code="DUP-002",
                    **common_data,
                )
