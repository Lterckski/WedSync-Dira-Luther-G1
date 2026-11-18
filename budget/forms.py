import datetime
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from accounts.forms import StyledFormMixin
from weddings.forms import DateInput

from .models import BudgetCategory, Expense

MAX_AMOUNT = "9,999,999,999.99"


class MoneyField(forms.DecimalField):
    """A NUMERIC(12,2) amount. Accepts thousands separators, so "12,500.50" is fine."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("widget", forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}))
        super().__init__(**kwargs)
        self.error_messages.update({
            "invalid": "Enter an amount in numbers, like 12500 or 12,500.50.",
            "max_digits": f"Enter an amount up to {MAX_AMOUNT}.",
            "max_whole_digits": f"Enter an amount up to {MAX_AMOUNT}.",
            "max_decimal_places": "Use at most 2 decimal places, like 1500.50.",
        })

    def to_python(self, value):
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return super().to_python(value)


class CategoryForm(StyledFormMixin, forms.ModelForm):
    allocated_amount = MoneyField(
        label="Allocated amount",
        error_messages={"required": "Enter how much you're setting aside for this category, or 0."},
    )

    class Meta:
        model = BudgetCategory
        fields = ["name", "allocated_amount"]
        labels = {"name": "Category name"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "Catering, Venue, Photography…"})}
        error_messages = {
            "name": {"required": "Enter a category name.", "max_length": "Use 100 characters or fewer."},
        }

    def __init__(self, *args, wedding, **kwargs):
        super().__init__(*args, **kwargs)
        self.wedding = wedding
        self.fields["allocated_amount"].help_text = f"In {wedding.base_currency}. Use 0 if you haven't decided yet."

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        if not name:
            raise ValidationError("Enter a category name.")
        others = BudgetCategory.objects.filter(wedding=self.wedding, name__iexact=name)
        if self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise ValidationError(f"This wedding already has a category called {others.first().name}.")
        return name

    def clean_allocated_amount(self):
        amount = self.cleaned_data.get("allocated_amount")
        if amount is not None and amount < 0:
            raise ValidationError("The allocated amount can't be negative. Use 0 or more.")
        return amount

    def save(self, commit=True):
        self.instance.wedding = self.wedding
        return super().save(commit=commit)


class CategoryChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, category):
        return category.name if category.is_active else f"{category.name} (inactive)"


class ExpenseForm(StyledFormMixin, forms.ModelForm):
    category = CategoryChoiceField(
        queryset=BudgetCategory.objects.none(),
        label="Category",
        empty_label="Choose a category",
        error_messages={
            "required": "Choose the category this expense belongs to.",
            "invalid_choice": "Choose one of this wedding's active categories.",
        },
    )
    amount = MoneyField(label="Amount", error_messages={"required": "Enter the amount spent."})

    class Meta:
        model = Expense
        fields = ["category", "description", "amount", "expense_date"]
        labels = {"description": "Description", "expense_date": "Date"}
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "Deposit for the reception venue"}),
            "expense_date": DateInput(),
        }
        error_messages = {
            "description": {"required": "Describe what the money was spent on.", "max_length": "Use 255 characters or fewer."},
            "expense_date": {"required": "Enter the date of the expense.", "invalid": "Enter a real date, like 14 February 2027."},
        }

    def __init__(self, *args, wedding, **kwargs):
        super().__init__(*args, **kwargs)
        self.wedding = wedding
        # Only this wedding's active categories, plus the expense's own category when editing,
        # so a tampered category_id from another wedding or an inactive category is refused.
        allowed = Q(is_active=True)
        if self.instance.pk:
            allowed |= Q(pk=self.instance.category_id)
        self.fields["category"].queryset = BudgetCategory.objects.filter(allowed, wedding=wedding)
        self.fields["amount"].help_text = f"In {wedding.base_currency}."
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault("expense_date", datetime.date.today())

    def clean_description(self):
        description = " ".join((self.cleaned_data.get("description") or "").split())
        if not description:
            raise ValidationError("Describe what the money was spent on.")
        return description

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= Decimal("0"):
            raise ValidationError("Enter an amount greater than 0.")
        return amount

    def clean_expense_date(self):
        expense_date = self.cleaned_data.get("expense_date")
        if expense_date and expense_date > datetime.date.today():
            raise ValidationError("The date can't be in the future. Record expenses once they're paid or committed.")
        return expense_date
