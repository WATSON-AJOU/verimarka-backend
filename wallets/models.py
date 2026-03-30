from django.conf import settings
from django.db import models


class WalletLink(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet_link",
    )
    address = models.CharField(max_length=42, unique=True, db_index=True)
    chain_id = models.PositiveIntegerField(null=True, blank=True)
    wallet_type = models.CharField(max_length=50, blank=True, default="")
    verified_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id}:{self.address}"


class WalletConnectionChallenge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet_connection_challenges",
    )
    address = models.CharField(max_length=42, db_index=True)
    nonce = models.CharField(max_length=64)
    message = models.TextField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "address", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.address}:{self.nonce[:8]}"
