from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contents", "0002_content_blockchain"),
    ]

    operations = [
        migrations.CreateModel(
            name="AIJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("job_type", models.CharField(choices=[("register", "Register"), ("verify", "Verify"), ("watermark", "Watermark")], max_length=20)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("success", "Success"), ("failure", "Failure")], default="queued", max_length=20)),
                ("celery_task_id", models.CharField(blank=True, max_length=255)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("error_code", models.CharField(blank=True, max_length=100)),
                ("error_message", models.TextField(blank=True)),
                ("retryable", models.BooleanField(default=False)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("content", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="ai_jobs", to="contents.content")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_jobs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
