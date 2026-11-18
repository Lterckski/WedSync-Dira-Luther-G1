"""
Budget totals, calculated by PostgreSQL (Sum / Count with subqueries), never row by row in Python.
"""
from decimal import Decimal

from django.db.models import Count, DecimalField, F, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from .models import MONEY, BudgetCategory, Expense

MONEY_FIELD = DecimalField(**MONEY)
ZERO = Value(Decimal("0.00"), output_field=MONEY_FIELD)


def categories_with_spending(wedding):
    """The wedding's categories, each annotated with spent and remaining, in one query."""
    return BudgetCategory.objects.filter(wedding=wedding).annotate(
        spent=Coalesce(Sum("expenses__amount"), ZERO),
        remaining=F("allocated_amount") - F("spent"),
    )


def with_budget_totals(weddings):
    """
    Annotate a Wedding queryset with budget_allocated, budget_spent, budget_remaining
    and budget_over_count (categories where spent > allocated). One query however
    many weddings there are; inactive categories count too.
    """
    allocated = (
        BudgetCategory.objects.filter(wedding=OuterRef("pk"))
        .values("wedding").annotate(total=Sum("allocated_amount")).values("total")
    )
    spent = (
        Expense.objects.filter(category__wedding=OuterRef("pk"))
        .values("category__wedding").annotate(total=Sum("amount")).values("total")
    )
    category_spent = (
        Expense.objects.filter(category=OuterRef("pk"))
        .values("category").annotate(total=Sum("amount")).values("total")
    )
    over = (
        BudgetCategory.objects.filter(wedding=OuterRef("pk"))
        .annotate(spent=Coalesce(Subquery(category_spent, output_field=MONEY_FIELD), ZERO))
        .filter(spent__gt=F("allocated_amount"))
        .values("wedding").annotate(count=Count("category_id")).values("count")
    )
    return weddings.annotate(
        budget_allocated=Coalesce(Subquery(allocated, output_field=MONEY_FIELD), ZERO),
        budget_spent=Coalesce(Subquery(spent, output_field=MONEY_FIELD), ZERO),
        budget_over_count=Coalesce(Subquery(over, output_field=IntegerField()), 0),
    ).annotate(budget_remaining=F("budget_allocated") - F("budget_spent"))


def category_spent(category):
    """Total spent in one category (used for the over-budget warning after saving an expense)."""
    return category.expenses.aggregate(total=Coalesce(Sum("amount"), ZERO))["total"]


def percent_used(spent, allocated):
    """Whole-number percentage of the allocation spent; None when nothing was allocated."""
    if allocated > 0:
        return int((spent / allocated * 100).to_integral_value())
    return None
