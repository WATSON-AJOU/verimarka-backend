from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    phone = models.CharField(max_length=20, blank=True, null=True)
    phone_verified = models.BooleanField(default=False)

    # 소셜용 : 어떤 provider로 가입했는지 기록
    provider = models.CharField(max_length=20, blank=True, null=True)
    # 소셜 유저 고유 id
    provider_sub = models.CharField(
        max_length=128, blank=True, null=True
    )  


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
