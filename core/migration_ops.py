"""
Migration helpers shared by the WedSync apps.

Django's on_delete runs in Python only: the foreign keys it creates in
PostgreSQL have no ON DELETE rule (NO ACTION). The SDD gives every foreign key
an explicit rule, so a migration replaces each constraint with one that has it.
Then a DELETE run outside Django (psql, the Supabase dashboard) behaves the same
as one run through the app.
"""
from django.db import migrations

RULES = {"CASCADE", "RESTRICT"}


def set_on_delete(table, column, ref_table, ref_column, rule):
    """
    Replace the foreign key on table.column with one named <table>_<column>_fkey
    that references ref_table(ref_column) with ON DELETE <rule>.

    If a later migration alters this field, Django recreates the constraint
    without the rule, so that migration has to call set_on_delete again.
    """
    if rule not in RULES:
        raise ValueError(f"ON DELETE rule must be one of {sorted(RULES)}.")
    name = f"{table}_{column}_fkey"

    def replace_with(on_delete_clause):
        return f"""
            DO $$
            DECLARE existing text;
            BEGIN
                FOR existing IN
                    SELECT con.conname
                    FROM pg_constraint con
                    JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
                    WHERE con.contype = 'f' AND con.conrelid = '{table}'::regclass AND att.attname = '{column}'
                LOOP
                    EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', existing);
                END LOOP;
            END $$;
            ALTER TABLE {table} ADD CONSTRAINT {name}
                FOREIGN KEY ({column}) REFERENCES {ref_table} ({ref_column}){on_delete_clause}
                DEFERRABLE INITIALLY DEFERRED;
        """

    return migrations.RunSQL(
        sql=replace_with(f" ON DELETE {rule}"),
        reverse_sql=replace_with(""),
    )
