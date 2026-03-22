from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contents", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="content",
            name="blockchain",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
