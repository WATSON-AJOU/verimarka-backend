from django.conf import settings
from django.db import models


class VerificationHistoryLog(models.Model):
    OUTCOME_CHOICES = [
        ("verified", "Verified"),
        ("candidate", "Candidate"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_history_logs",
    )
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    uploaded_file_name = models.CharField(max_length=255)
    uploaded_file_size = models.PositiveBigIntegerField(default=0)
    uploaded_preview_url = models.URLField(blank=True, null=True)
    detect = models.JSONField(default=dict, blank=True)
    blockchain = models.JSONField(default=dict, blank=True)
    candidate = models.JSONField(default=dict, blank=True)
    summary = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}:{self.uploaded_file_name}:{self.outcome}"
