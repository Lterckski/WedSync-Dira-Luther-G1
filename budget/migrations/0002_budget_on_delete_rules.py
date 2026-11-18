# Sets the SDD's ON DELETE rules on budget_categories and expenses in PostgreSQL itself
# (Django's on_delete only runs in Python). See core/migration_ops.py.

from django.db import migrations

from core.migration_ops import set_on_delete


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0001_initial"),
    ]

    operations = [
        set_on_delete("budget_categories", "wedding_id", "weddings", "wedding_id", "RESTRICT"),
        set_on_delete("expenses", "category_id", "budget_categories", "category_id", "RESTRICT"),
        set_on_delete("expenses", "recorded_by", "users", "user_id", "RESTRICT"),
    ]
