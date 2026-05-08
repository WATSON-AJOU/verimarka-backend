from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logs", "0002_alter_verificationhistorylog_uploaded_preview_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="verificationhistorylog",
            name="uploaded_storage_key",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
