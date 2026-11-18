"""
Test runner that works through Supabase's Session pooler (Supavisor).

The pooler keeps its own idle connection open to the test database and reopens
it as soon as it is closed, so PostgreSQL refuses a plain DROP DATABASE
("is being accessed by other users"). This runner drops the test database with
DROP DATABASE ... WITH (FORCE) (PostgreSQL 13+), which ends those sessions and
drops it in one statement. Only Django's test_<name> databases are affected;
the real database is never dropped.
"""
from django.db import connections
from django.test.runner import DiscoverRunner


def force_drop(creation, test_database_name):
    if not test_database_name.startswith("test_"):
        raise ValueError(f"Refusing to drop {test_database_name!r}: not a test database.")
    with creation._nodb_cursor() as cursor:
        cursor.execute(
            "DROP DATABASE IF EXISTS %s WITH (FORCE)" % creation.connection.ops.quote_name(test_database_name)
        )


class PostgresTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        for alias in connections:
            creation = connections[alias].creation
            if connections[alias].vendor != "postgresql":
                continue
            # A test database left over from an earlier run is dropped here, because
            # Django's own clean-up uses a plain DROP DATABASE.
            if not self.keepdb:
                force_drop(creation, creation._get_test_db_name())
            creation._destroy_test_db = lambda name, verbosity, creation=creation: force_drop(creation, name)
        return super().setup_databases(**kwargs)
