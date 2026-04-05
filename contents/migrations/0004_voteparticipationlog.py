from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("contents", "0003_content_source_sha256"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="VoteParticipationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("wallet_address", models.CharField(max_length=42)),
                ("choice", models.CharField(choices=[("yes", "Yes"), ("no", "No")], max_length=10)),
                ("tx_hash", models.CharField(blank=True, max_length=100)),
                ("token_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("signed_deadline", models.BigIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("content", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vote_participations", to="contents.content")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vote_participations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(fields=("content", "user"), name="uniq_vote_participation_content_user"),
                ],
            },
        ),
    ]
