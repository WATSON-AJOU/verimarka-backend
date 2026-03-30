from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contents", "0002_content_blockchain"),
    ]

    operations = [
        migrations.AddField(
            model_name="content",
            name="source_sha256",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
    ]
