import uuid

from django.conf import settings
from django.db import models


def content_upload_to(instance, filename):
    return f"contents/{instance.owner_id}/{instance.public_id}/original/{filename}"


class Content(models.Model):
    CONTENT_TYPE_CHOICES = [
        ("image", "Image"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("allow", "Allow"),
        ("review", "Review"),
        ("block", "Block"),
        ("failed", "Failed"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contents",
    )
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default="image")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    original_file = models.FileField(upload_to=content_upload_to)
    original_storage_key = models.CharField(max_length=500, blank=True)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    file_size = models.PositiveBigIntegerField(default=0)

    decision = models.CharField(max_length=20, blank=True)
    reason = models.TextField(blank=True)
    next_action = models.CharField(max_length=30, blank=True)

    top_cosine = models.FloatField(null=True, blank=True)
    top_phash_dist = models.IntegerField(null=True, blank=True)
    top_match = models.JSONField(default=dict, blank=True)
    candidates = models.JSONField(default=list, blank=True)
    watermark = models.JSONField(default=dict, blank=True)
    timing_ms = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.status})"
