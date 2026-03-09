from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)
    phone_verified = models.BooleanField(default=False)


class SocialAccount(models.Model):
    PROVIDER_CHOICES = [
        ("google", "Google"),
        ("kakao", "Kakao"),
        ("apple", "Apple"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="social_accounts",
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_sub = models.CharField(max_length=128)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_sub"],
                name="uniq_provider_provider_sub",
            )
        ]


class SmsVerification(models.Model):
    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    send_count = models.PositiveIntegerField(default=0)
    fail_count = models.PositiveIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() >= self.expires_at
