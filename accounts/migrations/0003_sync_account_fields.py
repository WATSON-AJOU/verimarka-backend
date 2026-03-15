import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def populate_existing_users(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.all():
        updates = []

        if not user.nickname:
            base_nickname = (user.username or f"user_{user.pk}")[:30]
            nickname = base_nickname
            counter = 1
            while User.objects.exclude(pk=user.pk).filter(nickname=nickname).exists():
                suffix = f"_{counter}"
                nickname = f"{base_nickname[: 30 - len(suffix)]}{suffix}"
                counter += 1
            user.nickname = nickname
            updates.append("nickname")

        if not user.display_name:
            user.display_name = (user.username or user.email or "회원")[:50]
            updates.append("display_name")

        if user.phone_verified and not user.phone_verified_at:
            user.phone_verified_at = django.utils.timezone.now()
            updates.append("phone_verified_at")

        if updates:
            user.save(update_fields=updates)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_smsverification_remove_user_provider_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialaccount",
            name="last_login_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="smsverification",
            name="purpose",
            field=models.CharField(
                choices=[("signup", "Signup"), ("profile_update", "Profile Update")],
                default="signup",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="smsverification",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sms_verifications",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="auth_provider",
            field=models.CharField(
                choices=[
                    ("local", "Local"),
                    ("google", "Google"),
                    ("kakao", "Kakao"),
                    ("apple", "Apple"),
                ],
                default="local",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="display_name",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="user",
            name="is_profile_completed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="nickname",
            field=models.CharField(default="", max_length=30, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="user",
            name="phone_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="privacy_agreed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="profile_image",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="terms_agreed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(
            code=populate_existing_users,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
