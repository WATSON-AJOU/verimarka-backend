from django.db import migrations, models


def backfill_completed_progress(apps, schema_editor):
    AIJob = apps.get_model("analysis", "AIJob")
    AIJob.objects.filter(status="success", progress=0).update(
        progress=100,
        progress_message="작업이 완료되었습니다.",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="aijob",
            name="progress",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="aijob",
            name="progress_message",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(backfill_completed_progress, migrations.RunPython.noop),
    ]
