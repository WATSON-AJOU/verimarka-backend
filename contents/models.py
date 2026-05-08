import uuid

from django.conf import settings
from django.db import models


def content_upload_to(instance, filename):
    return f"contents/{instance.owner_id}/{instance.public_id}/original/{filename}"


class Content(models.Model):
    CONTENT_TYPE_CHOICES = [
        ("image", "Image"),
        ("document", "Document"),
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
    content_type = models.CharField(
        max_length=20, choices=CONTENT_TYPE_CHOICES, default="image"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    original_file = models.FileField(upload_to=content_upload_to)
    original_storage_key = models.CharField(max_length=500, blank=True)
    original_filename = models.CharField(max_length=255)
    source_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
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
    document_metadata = models.JSONField(default=dict, blank=True)
    blockchain = models.JSONField(default=dict, blank=True)
    timing_ms = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["owner", "-created_at"], name="content_owner_created_idx"
            ),
            models.Index(
                fields=["owner", "source_sha256"], name="content_owner_sha_idx"
            ),
            models.Index(fields=["-updated_at"], name="content_updated_idx"),
            models.Index(
                fields=["decision", "-created_at"], name="content_decision_created_idx"
            ),
            models.Index(
                fields=["status", "-created_at"], name="content_status_created_idx"
            ),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.status})"


class VoteParticipationLog(models.Model):
    CHOICE_CHOICES = [
        ("yes", "Yes"),
        ("no", "No"),
    ]

    content = models.ForeignKey(
        Content,
        on_delete=models.CASCADE,
        related_name="vote_participations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vote_participations",
    )
    wallet_address = models.CharField(max_length=42)
    choice = models.CharField(max_length=10, choices=CHOICE_CHOICES)
    tx_hash = models.CharField(max_length=100, blank=True)
    token_id = models.PositiveBigIntegerField(null=True, blank=True)
    signed_deadline = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="vote_user_created_idx"),
            models.Index(
                fields=["content", "-created_at"], name="vote_content_created_idx"
            ),
            models.Index(fields=["token_id"], name="vote_token_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["content", "user"],
                name="uniq_vote_participation_content_user",
            )
        ]

    def __str__(self):
        return f"{self.content_id}:{self.user_id}:{self.choice}"
