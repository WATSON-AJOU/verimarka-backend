from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contents", "0004_voteparticipationlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="content",
            name="document_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="content",
            name="content_type",
            field=models.CharField(
                choices=[("image", "Image"), ("document", "Document")],
                default="image",
                max_length=20,
            ),
        ),
    ]
