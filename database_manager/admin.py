"""Django 管理后台的模型展示、筛选和运维操作。"""

from django import forms
from django.contrib import admin, messages

from .models import (
    Cluster,
    DailyInstanceStatistics,
    DatabaseInstance,
    Department,
    PasswordRotationLog,
    RequestMetric,
)
from .tasks import rotate_database_instance_password


class DatabaseInstanceAdminForm(forms.ModelForm):
    """后台新增实例时收集初始密码，编辑时按需重置密码。"""

    initial_password = forms.CharField(
        label="初始密码/重置密码",
        required=False,
        min_length=12,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="新增实例时必填；编辑时留空表示保留现有密码。",
    )

    class Meta:
        model = DatabaseInstance
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 新建时必须有初始密码，编辑时允许留空保留原值。
        self.fields["initial_password"].required = not bool(self.instance.pk)

    def save(self, commit=True):
        # 先取得尚未写入数据库的实例，再加密表单中的明文密码。
        instance = super().save(commit=False)
        raw_password = self.cleaned_data.get("initial_password")
        if raw_password:
            instance.set_database_password(raw_password)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """部门数据维护界面。"""

    list_display = ["code", "name", "created_at", "updated_at"]
    search_fields = ["code", "name"]
    ordering = ["code"]


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    """集群数据维护界面。"""

    list_display = ["code", "name", "department", "created_at"]
    list_filter = ["department"]
    search_fields = ["code", "name", "department__name"]
    list_select_related = ["department"]


@admin.register(DatabaseInstance)
class DatabaseInstanceAdmin(admin.ModelAdmin):
    """实例维护界面；后台也不展示明文或密文密码。"""

    form = DatabaseInstanceAdminForm
    fields = [
        "cluster",
        "name",
        "instance_code",
        "engine",
        "host",
        "port",
        "database_username",
        "initial_password",
        "password_ciphertext",
        "password_version",
        "password_updated_at",
        "rotation_enabled",
        "probe_status",
        "last_probe_at",
        "description",
        "created_at",
        "updated_at",
    ]
    list_display = [
        "instance_code",
        "name",
        "engine",
        "host",
        "port",
        "probe_status",
        "password_version",
        "password_updated_at",
    ]
    list_filter = ["engine", "probe_status", "rotation_enabled", "cluster__department"]
    search_fields = ["instance_code", "name", "host", "database_username"]
    list_select_related = ["cluster", "cluster__department"]
    readonly_fields = [
        "password_ciphertext",
        "password_version",
        "password_updated_at",
        "probe_status",
        "last_probe_at",
        "created_at",
        "updated_at",
    ]
    actions = ["queue_password_rotation"]

    @admin.action(description="为选中实例异步轮换密码")
    def queue_password_rotation(self, request, queryset):
        """只负责投递 Celery 任务，避免后台请求被批量耗时阻塞。"""
        queued_count = 0
        failed_count = 0
        for instance_id in queryset.filter(rotation_enabled=True).values_list("id", flat=True):
            try:
                rotate_database_instance_password.delay(instance_id)
                queued_count += 1
            except Exception:
                # 队列不可用时继续尝试后续实例，并在后台展示失败数量。
                failed_count += 1
        self.message_user(
            request,
            f"已投递 {queued_count} 个密码轮换任务，失败 {failed_count} 个。",
            level=messages.WARNING if failed_count else messages.SUCCESS,
        )


@admin.register(PasswordRotationLog)
class PasswordRotationLogAdmin(admin.ModelAdmin):
    """只读查看密码轮换审计结果。"""

    list_display = ["instance", "status", "password_version", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["instance__name", "instance__instance_code"]
    list_select_related = ["instance"]
    readonly_fields = [
        "instance",
        "status",
        "password_version",
        "message",
        "created_at",
    ]

    def has_add_permission(self, request):
        # 审计记录只能由任务写入。
        return False

    def has_change_permission(self, request, obj=None):
        # 防止审计内容被后台人工篡改。
        return False


@admin.register(DailyInstanceStatistics)
class DailyInstanceStatisticsAdmin(admin.ModelAdmin):
    """只读查看每日统计快照。"""

    list_display = [
        "stat_date",
        "department",
        "cluster",
        "instance_count",
        "generated_at",
    ]
    list_filter = ["stat_date", "department"]
    search_fields = ["department__name", "cluster__name"]
    list_select_related = ["department", "cluster"]
    readonly_fields = [
        "stat_date",
        "department",
        "cluster",
        "instance_count",
        "generated_at",
    ]

    def has_add_permission(self, request):
        # 统计数据由 Celery 定时任务生成。
        return False

    def has_change_permission(self, request, obj=None):
        # 历史快照不应被后台手工修改。
        return False


@admin.register(RequestMetric)
class RequestMetricAdmin(admin.ModelAdmin):
    """只读查看请求耗时指标。"""

    list_display = [
        "created_at",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "user_id",
    ]
    list_filter = ["method", "status_code", "created_at"]
    search_fields = ["path"]
    readonly_fields = [
        "method",
        "path",
        "status_code",
        "duration_ms",
        "remote_addr",
        "user_id",
        "created_at",
    ]

    def has_add_permission(self, request):
        # 指标由中间件自动写入。
        return False

    def has_change_permission(self, request, obj=None):
        # 指标记录不可在后台修改。
        return False
