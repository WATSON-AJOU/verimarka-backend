from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logs", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="verificationhistorylog",
            name="uploaded_preview_url",
            field=models.URLField(blank=True, max_length=2048, null=True),
        ),
    ]
