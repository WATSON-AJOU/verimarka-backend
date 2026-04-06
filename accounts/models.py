from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from uuid import uuid4


class User(AbstractUser):
    AUTH_PROVIDER_CHOICES = [
        ("local", "Local"),
        ("google", "Google"),
        ("kakao", "Kakao"),
        ("apple", "Apple"),
    ]

    phone = models.CharField(max_length=20, blank=True, null=True, unique=True)
    phone_verified = models.BooleanField(default=False)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    nickname = models.CharField(max_length=30, unique=True)
    display_name = models.CharField(max_length=50, blank=True)
    profile_image = models.URLField(blank=True, null=True)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)

    auth_provider = models.CharField(
        max_length=20,
        choices=AUTH_PROVIDER_CHOICES,
        default="local",
    )
    is_profile_completed = models.BooleanField(default=False)

    terms_agreed_at = models.DateTimeField(null=True, blank=True)
    privacy_agreed_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.email or self.username

    def soft_delete(self):
        deleted_at = timezone.now()
        deleted_suffix = f"deleted_{self.pk}_{uuid4().hex[:8]}"

        self.is_active = False
        self.is_deleted = True
        self.deleted_at = deleted_at
        self.phone_verified = False
        self.phone_verified_at = None
        self.email_verified = False
        self.email_verified_at = None
        self.phone = None
        self.profile_image = None
        self.last_login_ip = None
        self.display_name = "탈퇴한 회원"
        self.email = ""
        self.username = deleted_suffix[:150]
        self.nickname = deleted_suffix[:30]
        self.auth_provider = "local"
        self.is_profile_completed = False
        self.set_unusable_password()
        self.save(
            update_fields=[
                "is_active",
                "is_deleted",
                "deleted_at",
                "phone_verified",
                "phone_verified_at",
                "email_verified",
                "email_verified_at",
                "phone",
                "profile_image",
                "last_login_ip",
                "display_name",
                "email",
                "username",
                "nickname",
                "auth_provider",
                "is_profile_completed",
                "password",
            ]
        )


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
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_sub"],
                name="uniq_provider_provider_sub",
            )
        ]

    def __str__(self):
        return f"{self.provider}:{self.user_id}"


class SmsVerification(models.Model):
    PURPOSE_CHOICES = [
        ("signup", "Signup"),
        ("profile_update", "Profile Update"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sms_verifications",
        null=True,
        blank=True,
    )
    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    send_count = models.PositiveIntegerField(default=0)
    fail_count = models.PositiveIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default="signup")

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"{self.phone} ({self.purpose})"
