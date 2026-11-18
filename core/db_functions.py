from django.db.models import DateField, Func


class CurrentDate(Func):
    """SQL CURRENT_DATE, for DATE columns whose database default is today (db_default=CurrentDate())."""

    template = "CURRENT_DATE"
    output_field = DateField()
