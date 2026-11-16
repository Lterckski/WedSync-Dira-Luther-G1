from django.db import models


class TimestampField(models.DateTimeField):
    """
    A DateTimeField stored as PostgreSQL TIMESTAMP (without time zone).

    Django's default on PostgreSQL is TIMESTAMP WITH TIME ZONE; the SDD's data
    dictionary specifies plain TIMESTAMP, so every created_at / updated_at column
    uses this field. Times are stored in Asia/Manila (settings.TIME_ZONE).
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return "timestamp"
        return super().db_type(connection)
