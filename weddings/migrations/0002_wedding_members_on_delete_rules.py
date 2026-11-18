# Sets the SDD's ON DELETE rules on wedding_members in PostgreSQL itself
# (Django's on_delete only runs in Python). See core/migration_ops.py.

from django.db import migrations

from core.migration_ops import set_on_delete


class Migration(migrations.Migration):

    dependencies = [
        ("weddings", "0001_initial"),
    ]

    operations = [
        set_on_delete("wedding_members", "wedding_id", "weddings", "wedding_id", "CASCADE"),
        set_on_delete("wedding_members", "user_id", "users", "user_id", "CASCADE"),
    ]
