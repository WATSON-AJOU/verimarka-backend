import uuid

from django.conf import settings
from django.db import models


class AIJob(models.Model):
    JOB_TYPE_CHOICES = [
        ("register", "Register"),
        ("verify", "Verify"),
        ("watermark", "Watermark"),
    ]

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("success", "Success"),
        ("failure", "Failure"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_jobs",
    )
    content = models.ForeignKey(
        "contents.Content",
        on_delete=models.CASCADE,
        related_name="ai_jobs",
        null=True,
        blank=True,
    )
    job_type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    celery_task_id = models.CharField(max_length=255, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    progress_message = models.CharField(max_length=100, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    retryable = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.job_type}:{self.public_id}:{self.status}"
