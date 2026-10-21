# Generated for development seed support.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="profilereadmodel",
            name="nip",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]
