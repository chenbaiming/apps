"""部门、集群、实例、统计和审计数据模型。"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Department(models.Model):
    """企业内部的组织单元，例如“基础架构部”。"""

    name = models.CharField("部门名称", max_length=100, unique=True)
    code = models.CharField("部门编码", max_length=50, unique=True)
    description = models.TextField("说明", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "部门"
        verbose_name_plural = "部门"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Cluster(models.Model):
    """某部门下的一组数据库实例。"""

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="clusters",
        verbose_name="所属部门",
    )
    name = models.CharField("集群名称", max_length=100)
    code = models.CharField("集群编码", max_length=50)
    description = models.TextField("说明", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["department_id", "code"]
        verbose_name = "集群"
        verbose_name_plural = "集群"
        constraints = [
            # 同一部门内集群名称和编码均不能重复。
            models.UniqueConstraint(
                fields=["department", "name"],
                name="uniq_cluster_name_per_department",
            ),
            models.UniqueConstraint(
                fields=["department", "code"],
                name="uniq_cluster_code_per_department",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.department.code}/{self.name}"


class DatabaseInstance(models.Model):
    """一个可连接并需要维护凭据的数据库实例。"""

    class Engine(models.TextChoices):
        MYSQL = "mysql", "MySQL"
        POSTGRESQL = "postgresql", "PostgreSQL"
        REDIS = "redis", "Redis"
        MONGODB = "mongodb", "MongoDB"
        OTHER = "other", "其他"

    class ProbeStatus(models.TextChoices):
        UNKNOWN = "unknown", "未探测"
        ONLINE = "online", "在线"
        OFFLINE = "offline", "离线"

    cluster = models.ForeignKey(
        Cluster,
        on_delete=models.PROTECT,
        related_name="instances",
        verbose_name="所属集群",
    )
    name = models.CharField("实例名称", max_length=100)
    instance_code = models.CharField("实例编码", max_length=100, unique=True)
    engine = models.CharField(
        "数据库类型",
        max_length=20,
        choices=Engine.choices,
        default=Engine.MYSQL,
    )
    host = models.CharField("主机名或 IP", max_length=255)
    port = models.PositiveIntegerField(
        "端口",
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
    )
    database_username = models.CharField("数据库账号", max_length=128)
    # 只允许加密后的凭据进入数据库，接口不会返回该字段。
    password_ciphertext = models.TextField("加密后的密码", blank=True)
    password_version = models.PositiveIntegerField("密码版本", default=1)
    password_updated_at = models.DateTimeField("密码更新时间", null=True, blank=True)
    rotation_enabled = models.BooleanField("启用自动轮换", default=True)
    probe_status = models.CharField(
        "探测状态",
        max_length=10,
        choices=ProbeStatus.choices,
        default=ProbeStatus.UNKNOWN,
    )
    last_probe_at = models.DateTimeField("最后探测时间", null=True, blank=True)
    description = models.TextField("说明", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["cluster_id", "name"]
        verbose_name = "数据库实例"
        verbose_name_plural = "数据库实例"
        constraints = [
            # 同一集群下实例名称不能重复。
            models.UniqueConstraint(
                fields=["cluster", "name"],
                name="uniq_instance_name_per_cluster",
            ),
        ]
        indexes = [
            # 统计任务会频繁按集群聚合，因此为外键建立索引。
            models.Index(fields=["cluster"], name="idx_instance_cluster"),
            models.Index(fields=["engine"], name="idx_instance_engine"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.host}:{self.port})"

    def set_database_password(self, raw_password: str) -> None:
        """加密密码并更新版本，不直接保存到数据库。"""
        # 延迟导入可避免模型模块与安全模块之间形成循环依赖。
        from .security import encrypt_secret

        self.password_ciphertext = encrypt_secret(raw_password)
        self.password_version += 1
        self.password_updated_at = timezone.now()

    def verify_database_password(self, candidate: str) -> bool:
        """解密当前密码后与候选值比较。"""
        from .security import decrypt_secret

        if not self.password_ciphertext:
            return False
        return decrypt_secret(self.password_ciphertext) == candidate


class PasswordRotationLog(models.Model):
    """记录密码轮换结果，但绝不记录明文或密文密码。"""

    class Status(models.TextChoices):
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    instance = models.ForeignKey(
        DatabaseInstance,
        on_delete=models.CASCADE,
        related_name="password_rotation_logs",
        verbose_name="实例",
    )
    status = models.CharField("状态", max_length=10, choices=Status.choices)
    password_version = models.PositiveIntegerField("密码版本")
    message = models.CharField("备注", max_length=500, blank=True)
    created_at = models.DateTimeField("发生时间", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "密码轮换记录"
        verbose_name_plural = "密码轮换记录"
        indexes = [
            models.Index(fields=["instance", "-created_at"], name="idx_rotation_instance_time"),
        ]


class DailyInstanceStatistics(models.Model):
    """按统计日期、部门和集群保存实例数量快照。"""

    stat_date = models.DateField("统计日期")
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="daily_statistics",
        verbose_name="部门",
    )
    cluster = models.ForeignKey(
        Cluster,
        on_delete=models.PROTECT,
        related_name="daily_statistics",
        verbose_name="集群",
    )
    instance_count = models.PositiveIntegerField("实例数量", default=0)
    generated_at = models.DateTimeField("生成时间", auto_now=True)

    class Meta:
        ordering = ["-stat_date", "department_id", "cluster_id"]
        verbose_name = "每日实例统计"
        verbose_name_plural = "每日实例统计"
        constraints = [
            # 同一日期、部门和集群仅保留一条可更新快照。
            models.UniqueConstraint(
                fields=["stat_date", "department", "cluster"],
                name="uniq_daily_stat_department_cluster",
            ),
        ]
        indexes = [
            models.Index(fields=["stat_date", "department"], name="idx_stat_date_department"),
        ]


class RequestMetric(models.Model):
    """保存每次 HTTP 请求的基础性能和响应信息。"""

    method = models.CharField("请求方法", max_length=10)
    path = models.CharField("请求路径", max_length=500)
    status_code = models.PositiveIntegerField("响应状态码")
    duration_ms = models.DecimalField("耗时（毫秒）", max_digits=12, decimal_places=3)
    remote_addr = models.GenericIPAddressField("客户端地址", null=True, blank=True)
    user_id = models.PositiveBigIntegerField("用户 ID", null=True, blank=True)
    created_at = models.DateTimeField("请求时间", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "请求耗时"
        verbose_name_plural = "请求耗时"
        indexes = [
            models.Index(fields=["-created_at"], name="idx_request_created"),
            models.Index(fields=["path", "-created_at"], name="idx_request_path_time"),
        ]
