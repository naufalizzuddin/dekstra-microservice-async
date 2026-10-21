import uuid

from django.db import migrations, models


def populate_public_tokens(apps, schema_editor):
    BerkasPermohonan = apps.get_model("surat", "BerkasPermohonan")
    for attachment in BerkasPermohonan.objects.filter(public_token__isnull=True).iterator():
        attachment.public_token = uuid.uuid4()
        attachment.save(update_fields=["public_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("surat", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="berkaspermohonan",
            name="public_token",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(
            populate_public_tokens,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="berkaspermohonan",
            name="public_token",
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
