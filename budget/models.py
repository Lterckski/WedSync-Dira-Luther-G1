"""
The budget and expense tracker (SDD F-03): the budget_categories and expenses tables.

    budget_categories(category_id PK, wedding_id FK ON DELETE RESTRICT, name,
                      allocated_amount NUMERIC(12,2) CHECK >= 0, is_active DEFAULT TRUE,
                      created_at DEFAULT CURRENT_TIMESTAMP, UNIQUE (wedding_id, name))

    expenses(expense_id PK, category_id FK ON DELETE RESTRICT, recorded_by FK ON DELETE RESTRICT,
             description, amount NUMERIC(12,2) CHECK > 0, expense_date DEFAULT CURRENT_DATE,
             created_at DEFAULT CURRENT_TIMESTAMP)

Money is always NUMERIC(12,2) (DecimalField), never a float.
"""
import datetime

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower, Now
from django.utils import timezone

from core.db_functions import CurrentDate
from core.fields import TimestampField
from weddings.models import Wedding

MONEY = {"max_digits": 12, "decimal_places": 2}


class BudgetCategory(models.Model):
    category_id = models.AutoField(primary_key=True)
    # BR-07 / RESTRICT: a wedding with budget categories can't be deleted.
    wedding = models.ForeignKey(Wedding, on_delete=models.RESTRICT, related_name="budget_categories")
    name = models.CharField(max_length=100)
    allocated_amount = models.DecimalField(**MONEY)
    is_active = models.BooleanField(default=True, db_default=True)
    created_at = TimestampField(default=timezone.now, db_default=Now(), editable=False)

    class Meta:
        db_table = "budget_categories"
        ordering = [Lower("name"), "category_id"]
        verbose_name_plural = "budget categories"
        constraints = [
            # BR-05
            models.CheckConstraint(
                condition=models.Q(allocated_amount__gte=0),
                name="budget_categories_allocated_amount_check",
            ),
            models.UniqueConstraint(fields=["wedding", "name"], name="budget_categories_wedding_id_name_key"),
            # "Catering" and "catering" are the same category.
            models.UniqueConstraint("wedding", Lower("name"), name="budget_categories_wedding_id_lower_name_key"),
        ]

    def __str__(self):
        return self.name


class Expense(models.Model):
    expense_id = models.AutoField(primary_key=True)
    # BR-07: a category with expenses can't be deleted, only deactivated.
    category = models.ForeignKey(BudgetCategory, on_delete=models.RESTRICT, related_name="expenses")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, db_column="recorded_by", related_name="recorded_expenses"
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(**MONEY)
    expense_date = models.DateField(default=datetime.date.today, db_default=CurrentDate())
    created_at = TimestampField(default=timezone.now, db_default=Now(), editable=False)

    class Meta:
        db_table = "expenses"
        ordering = ["-expense_date", "-created_at", "-expense_id"]
        constraints = [
            # BR-06
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="expenses_amount_check"),
        ]

    def __str__(self):
        return f"{self.description} ({self.amount})"
