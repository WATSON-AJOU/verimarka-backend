from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone = models.CharField(max_length=20, blank=True, null=True)
    phone_verified = models.BooleanField(default=False)

    # 소셜용 : 어떤 provider로 가입했는지 기록
    provider = models.CharField(max_length=20, blank=True, null=True)
    # 소셜 유저 고유 id
    provider_sub = models.CharField(
        max_length=128, blank=True, null=True
    )  
