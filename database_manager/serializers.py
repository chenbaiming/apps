"""REST API 的输入校验与响应序列化。"""

from rest_framework import serializers

from .models import (
    Cluster,
    DailyInstanceStatistics,
    DatabaseInstance,
    Department,
    PasswordRotationLog,
    RequestMetric,
)


class DepartmentSerializer(serializers.ModelSerializer):
    """部门 CRUD 序列化器，并附带集群数量。"""

    cluster_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "code",
            "description",
            "cluster_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ClusterSerializer(serializers.ModelSerializer):
    """集群 CRUD 序列化器，并附带部门名称和实例数量。"""

    department_name = serializers.CharField(
        source="department.name",
        read_only=True,
    )
    instance_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Cluster
        fields = [
            "id",
            "department",
            "department_name",
            "name",
            "code",
            "description",
            "instance_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class DatabaseInstanceSerializer(serializers.ModelSerializer):
    """实例 CRUD 序列化器；密码只允许写入，绝不回传。"""

    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=12,
        trim_whitespace=False,
        help_text="创建时必填；更新时填写才会重置密码。",
    )
    cluster_name = serializers.CharField(source="cluster.name", read_only=True)
    department_id = serializers.IntegerField(
        source="cluster.department_id",
        read_only=True,
    )
    department_name = serializers.CharField(
        source="cluster.department.name",
        read_only=True,
    )
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = DatabaseInstance
        fields = [
            "id",
            "cluster",
            "cluster_name",
            "department_id",
            "department_name",
            "name",
            "instance_code",
            "engine",
            "host",
            "port",
            "database_username",
            "password",
            "has_password",
            "password_version",
            "password_updated_at",
            "rotation_enabled",
            "probe_status",
            "last_probe_at",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "password_version",
            "password_updated_at",
            "probe_status",
            "last_probe_at",
            "created_at",
            "updated_at",
        ]

    def get_has_password(self, obj: DatabaseInstance) -> bool:
        """只告诉调用方是否已保存密码，不暴露密文或明文。"""
        return bool(obj.password_ciphertext)

    def validate(self, attrs):
        """创建实例时强制提供初始密码。"""
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "创建实例时必须提供初始密码"})
        return attrs

    def create(self, validated_data):
        """取出明文密码，加密后再持久化实例。"""
        raw_password = validated_data.pop("password")
        instance = DatabaseInstance(**validated_data)
        instance.set_database_password(raw_password)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        """未传密码时保留原凭据；传入时执行安全重置。"""
        raw_password = validated_data.pop("password", None)
        for field_name, value in validated_data.items():
            setattr(instance, field_name, value)
        if raw_password:
            instance.set_database_password(raw_password)
        instance.save()
        return instance


class TcpProbeResponseSerializer(serializers.Serializer):
    """TCP 探测接口的响应契约。"""

    instance_id = serializers.IntegerField()
    host = serializers.CharField()
    port = serializers.IntegerField()
    reachable = serializers.BooleanField()
    latency_ms = serializers.FloatField()
    error = serializers.CharField(allow_blank=True)
    probed_at = serializers.DateTimeField()


class DailyInstanceStatisticsSerializer(serializers.ModelSerializer):
    """只读的每日统计响应。"""

    department_name = serializers.CharField(source="department.name", read_only=True)
    cluster_name = serializers.CharField(source="cluster.name", read_only=True)

    class Meta:
        model = DailyInstanceStatistics
        fields = [
            "id",
            "stat_date",
            "department",
            "department_name",
            "cluster",
            "cluster_name",
            "instance_count",
            "generated_at",
        ]


class PasswordRotationLogSerializer(serializers.ModelSerializer):
    """只读的轮换审计记录，不包含任何密码字段。"""

    instance_name = serializers.CharField(source="instance.name", read_only=True)

    class Meta:
        model = PasswordRotationLog
        fields = [
            "id",
            "instance",
            "instance_name",
            "status",
            "password_version",
            "message",
            "created_at",
        ]


class RequestMetricSerializer(serializers.ModelSerializer):
    """只读的请求耗时记录。"""

    class Meta:
        model = RequestMetric
        fields = [
            "id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "remote_addr",
            "user_id",
            "created_at",
        ]
