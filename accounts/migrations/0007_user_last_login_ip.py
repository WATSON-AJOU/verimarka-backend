from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_email_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="last_login_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
    ]
