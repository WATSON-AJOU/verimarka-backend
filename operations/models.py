from django.conf import settings
from django.db import models


class AdminActionLog(models.Model):
    ACTION_CHOICES = [
        ("user_update", "User Update"),
        ("content_moderation", "Content Moderation"),
        ("report_update", "Report Update"),
        ("retention_update", "Retention Update"),
        ("notification_create", "Notification Create"),
        ("job_retry", "Job Retry"),
        ("job_cancel", "Job Cancel"),
        ("policy_publish", "Policy Publish"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_action_logs",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    target_type = models.CharField(max_length=60)
    target_id = models.CharField(max_length=120)
    reason = models.TextField(blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=80, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["action", "-created_at"], name="oplog_action_created_idx"
            ),
            models.Index(fields=["target_type", "target_id"], name="oplog_target_idx"),
            models.Index(
                fields=["actor", "-created_at"], name="oplog_actor_created_idx"
            ),
        ]

    def __str__(self):
        return f"{self.action}:{self.target_type}:{self.target_id}"


class PolicyVersion(models.Model):
    POLICY_CHOICES = [
        ("terms", "Terms"),
        ("privacy", "Privacy"),
    ]

    policy_type = models.CharField(max_length=20, choices=POLICY_CHOICES)
    version = models.CharField(max_length=40)
    title = models.CharField(max_length=120)
    body = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["policy_type", "-published_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["policy_type", "version"],
                name="uniq_policy_type_version",
            )
        ]

    def __str__(self):
        return f"{self.policy_type}:{self.version}"


class UserPolicyConsent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="policy_consents",
    )
    policy_version = models.ForeignKey(
        PolicyVersion,
        on_delete=models.CASCADE,
        related_name="user_consents",
    )
    consented_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-consented_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "policy_version"],
                name="uniq_user_policy_consent",
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.policy_version_id}"


class ModerationCase(models.Model):
    ACTION_CHOICES = [
        ("approve", "Approve"),
        ("reject", "Reject"),
        ("needs_review", "Needs Review"),
        ("hide", "Hide"),
        ("restore", "Restore"),
        ("reanalyze", "Reanalyze"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("resolved", "Resolved"),
    ]

    content = models.ForeignKey(
        "contents.Content",
        on_delete=models.CASCADE,
        related_name="moderation_cases",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_cases",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="resolved")
    reason = models.TextField()
    previous_status = models.CharField(max_length=20, blank=True)
    previous_decision = models.CharField(max_length=20, blank=True)
    next_status = models.CharField(max_length=20, blank=True)
    next_decision = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["content", "-created_at"], name="modcase_content_created_idx"
            ),
            models.Index(
                fields=["action", "-created_at"], name="modcase_action_created_idx"
            ),
        ]

    def __str__(self):
        return f"{self.content_id}:{self.action}"


class ReportCase(models.Model):
    REPORT_TYPE_CHOICES = [
        ("copyright", "Copyright"),
        ("impersonation", "Impersonation"),
        ("abuse", "Abuse"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("investigating", "Investigating"),
        ("resolved", "Resolved"),
        ("rejected", "Rejected"),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_reports",
    )
    content = models.ForeignKey(
        "contents.Content",
        on_delete=models.CASCADE,
        related_name="report_cases",
    )
    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="open")
    title = models.CharField(max_length=160)
    description = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_reports",
    )
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "-created_at"], name="report_status_created_idx"
            ),
            models.Index(
                fields=["content", "-created_at"], name="report_content_created_idx"
            ),
        ]

    def __str__(self):
        return f"{self.report_type}:{self.content_id}:{self.status}"


class RetentionRequest(models.Model):
    REQUEST_TYPE_CHOICES = [
        ("delete_content", "Delete Content"),
        ("anonymize_user", "Anonymize User"),
        ("purge_upload", "Purge Upload"),
    ]
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("approved", "Approved"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
    ]

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retention_requests",
    )
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPE_CHOICES)
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="requested"
    )
    target_type = models.CharField(max_length=60)
    target_id = models.CharField(max_length=120)
    reason = models.TextField()
    decision_note = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "-created_at"], name="retention_status_created_idx"
            ),
            models.Index(
                fields=["target_type", "target_id"], name="retention_target_idx"
            ),
        ]

    def __str__(self):
        return f"{self.request_type}:{self.target_type}:{self.target_id}"


class Notification(models.Model):
    CHANNEL_CHOICES = [
        ("in_app", "In App"),
        ("email", "Email"),
        ("sms", "SMS"),
    ]
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="in_app")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    title = models.CharField(max_length=160)
    message = models.TextField()
    related_type = models.CharField(max_length=60, blank=True)
    related_id = models.CharField(max_length=120, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "-created_at"], name="notice_user_created_idx"
            ),
            models.Index(
                fields=["status", "-created_at"], name="notice_status_created_idx"
            ),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.channel}:{self.status}"
