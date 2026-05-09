from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contents", "0006_content_content_owner_created_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="content",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("verified", "Verified"),
                    ("allow", "Allow"),
                    ("review", "Review"),
                    ("block", "Block"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
