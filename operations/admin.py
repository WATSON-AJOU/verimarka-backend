from django.contrib import admin

from operations.models import (
    AdminActionLog,
    ModerationCase,
    Notification,
    PolicyVersion,
    ReportCase,
    RetentionRequest,
    UserPolicyConsent,
)


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    list_display = ("action", "target_type", "target_id", "actor", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("target_id", "reason", "request_id", "actor__email")
    readonly_fields = ("created_at",)


@admin.register(PolicyVersion)
class PolicyVersionAdmin(admin.ModelAdmin):
    list_display = ("policy_type", "version", "title", "is_active", "published_at")
    list_filter = ("policy_type", "is_active")
    search_fields = ("version", "title")


@admin.register(UserPolicyConsent)
class UserPolicyConsentAdmin(admin.ModelAdmin):
    list_display = ("user", "policy_version", "consented_at")
    search_fields = ("user__email", "policy_version__version")


@admin.register(ModerationCase)
class ModerationCaseAdmin(admin.ModelAdmin):
    list_display = ("content", "action", "actor", "status", "created_at")
    list_filter = ("action", "status")
    search_fields = ("content__original_filename", "reason", "actor__email")


@admin.register(ReportCase)
class ReportCaseAdmin(admin.ModelAdmin):
    list_display = ("title", "report_type", "status", "content", "created_at")
    list_filter = ("report_type", "status")
    search_fields = ("title", "description", "content__original_filename")


@admin.register(RetentionRequest)
class RetentionRequestAdmin(admin.ModelAdmin):
    list_display = ("request_type", "status", "target_type", "target_id", "created_at")
    list_filter = ("request_type", "status", "target_type")
    search_fields = ("target_id", "reason", "decision_note")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "channel", "status", "created_at")
    list_filter = ("channel", "status")
    search_fields = ("title", "message", "user__email")
