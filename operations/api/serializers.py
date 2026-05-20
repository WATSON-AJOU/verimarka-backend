from rest_framework import serializers

from operations.models import (
    AdminActionLog,
    ModerationCase,
    Notification,
    PolicyVersion,
    ReportCase,
    RetentionRequest,
)


class OperationPayloadSerializer(serializers.Serializer):
    def to_representation(self, instance):
        return dict(instance)


class AdminActionLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()

    class Meta:
        model = AdminActionLog
        fields = (
            "id",
            "actor_email",
            "action",
            "target_type",
            "target_id",
            "reason",
            "before",
            "after",
            "request_id",
            "ip_address",
            "created_at",
        )

    def get_actor_email(self, obj):
        if not obj.actor_id:
            return ""
        return obj.actor.email or obj.actor.username


class PolicyVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyVersion
        fields = (
            "id",
            "policy_type",
            "version",
            "title",
            "body",
            "is_active",
            "published_at",
            "created_at",
            "updated_at",
        )


class PolicyVersionCreateSerializer(serializers.Serializer):
    policy_type = serializers.ChoiceField(choices=("terms", "privacy"))
    version = serializers.CharField(max_length=40)
    title = serializers.CharField(max_length=120)
    body = serializers.CharField(required=False, allow_blank=True)
    publish = serializers.BooleanField(required=False, default=False)


class ModerationCaseSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()
    content_public_id = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = ModerationCase
        fields = (
            "id",
            "content_public_id",
            "file_name",
            "actor_email",
            "action",
            "status",
            "reason",
            "previous_status",
            "previous_decision",
            "next_status",
            "next_decision",
            "created_at",
            "resolved_at",
        )

    def get_actor_email(self, obj):
        if not obj.actor_id:
            return ""
        return obj.actor.email or obj.actor.username

    def get_content_public_id(self, obj):
        return str(obj.content.public_id)

    def get_file_name(self, obj):
        return obj.content.original_filename


class ModerationCaseCreateSerializer(serializers.Serializer):
    content_public_id = serializers.UUIDField()
    action = serializers.ChoiceField(
        choices=("approve", "reject", "needs_review", "hide", "restore", "reanalyze")
    )
    reason = serializers.CharField()


class ReportCaseSerializer(serializers.ModelSerializer):
    reporter_email = serializers.SerializerMethodField()
    assignee_email = serializers.SerializerMethodField()
    content_public_id = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = ReportCase
        fields = (
            "id",
            "reporter_email",
            "assignee_email",
            "content_public_id",
            "file_name",
            "report_type",
            "status",
            "title",
            "description",
            "evidence",
            "resolution",
            "created_at",
            "updated_at",
            "resolved_at",
        )

    def get_reporter_email(self, obj):
        if not obj.reporter_id:
            return ""
        return obj.reporter.email or obj.reporter.username

    def get_assignee_email(self, obj):
        if not obj.assignee_id:
            return ""
        return obj.assignee.email or obj.assignee.username

    def get_content_public_id(self, obj):
        return str(obj.content.public_id)

    def get_file_name(self, obj):
        return obj.content.original_filename


class ReportCaseCreateSerializer(serializers.Serializer):
    content_public_id = serializers.UUIDField()
    report_type = serializers.ChoiceField(
        choices=("copyright", "impersonation", "abuse", "other")
    )
    title = serializers.CharField(max_length=160)
    description = serializers.CharField()
    evidence = serializers.JSONField(required=False)


class ReportCaseUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=("open", "investigating", "resolved", "rejected"), required=False
    )
    resolution = serializers.CharField(required=False, allow_blank=True)
    assign_to_me = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("변경할 항목이 없습니다.")
        return attrs


class RetentionRequestSerializer(serializers.ModelSerializer):
    requester_email = serializers.SerializerMethodField()

    class Meta:
        model = RetentionRequest
        fields = (
            "id",
            "requester_email",
            "request_type",
            "status",
            "target_type",
            "target_id",
            "reason",
            "decision_note",
            "due_at",
            "completed_at",
            "created_at",
            "updated_at",
        )

    def get_requester_email(self, obj):
        if not obj.requester_id:
            return ""
        return obj.requester.email or obj.requester.username


class RetentionRequestCreateSerializer(serializers.Serializer):
    request_type = serializers.ChoiceField(
        choices=("delete_content", "anonymize_user", "purge_upload")
    )
    target_type = serializers.CharField(max_length=60)
    target_id = serializers.CharField(max_length=120)
    reason = serializers.CharField()
    due_at = serializers.DateTimeField(required=False)


class RetentionRequestUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=("approved", "completed", "rejected"), required=False
    )
    decision_note = serializers.CharField(required=False, allow_blank=True)


class NotificationSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "id",
            "user",
            "user_email",
            "channel",
            "status",
            "title",
            "message",
            "related_type",
            "related_id",
            "sent_at",
            "created_at",
        )

    def get_user_email(self, obj):
        return obj.user.email or obj.user.username


class NotificationCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    channel = serializers.ChoiceField(
        choices=("in_app", "email", "sms"), default="in_app"
    )
    title = serializers.CharField(max_length=160)
    message = serializers.CharField()
    related_type = serializers.CharField(
        required=False, allow_blank=True, max_length=60
    )
    related_id = serializers.CharField(required=False, allow_blank=True, max_length=120)
