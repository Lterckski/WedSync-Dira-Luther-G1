from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import ProtectedError, RestrictedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Role
from core.money import format_money
from weddings.decorators import wedding_member_required
from weddings.models import MemberRole, Wedding
from weddings.views import render_confirm

from .forms import CategoryForm, ExpenseForm
from .models import BudgetCategory, Expense
from .queries import categories_with_spending, category_spent, percent_used, with_budget_totals

PAGE_SIZE = 20

# Who can open the budget at all: couples and coordinators who are members of the wedding.
# Vendors and administrators get the 403 page, members or not.
budget_member_required = wedding_member_required(
    Role.COUPLE, Role.COORDINATOR, member_roles=(MemberRole.COUPLE, MemberRole.COORDINATOR)
)
# Editing, deactivating and deleting categories is the couple's decision.
couple_member_required = wedding_member_required(
    Role.COUPLE, Role.COORDINATOR, member_roles=(MemberRole.COUPLE,)
)


def is_couple(membership):
    return membership.member_role == MemberRole.COUPLE


def overview_url(wedding_id):
    return reverse("budget:overview", args=[wedding_id])


def get_category(membership, category_id):
    """A category of this wedding only; any other id is a 404."""
    return get_object_or_404(BudgetCategory, pk=category_id, wedding_id=membership.wedding_id)


def get_editable_expense(membership, expense_id):
    """
    An expense of this wedding (404 otherwise) that this member may change:
    the couple can change every expense, a coordinator only the ones they recorded.
    """
    expense = get_object_or_404(
        Expense.objects.select_related("category"), pk=expense_id, category__wedding_id=membership.wedding_id
    )
    if not is_couple(membership) and expense.recorded_by_id != membership.user_id:
        raise PermissionDenied
    return expense


def warn_if_over_budget(request, category, currency):
    over_by = category_spent(category) - category.allocated_amount
    if over_by > 0:
        messages.warning(request, f"{category.name} is now {format_money(over_by, currency)} over budget.")


@budget_member_required
def overview(request, membership):
    wedding = with_budget_totals(Wedding.objects.filter(pk=membership.wedding_id)).get()
    categories = list(categories_with_spending(wedding))
    for category in categories:
        category.percent_used = percent_used(category.spent, category.allocated_amount)
        category.is_over = category.spent > category.allocated_amount
        # The bar stops at full; the percentage next to it shows how far past 100% it went.
        if category.percent_used is None:
            category.bar_value = 100 if category.spent > 0 else 0
        else:
            category.bar_value = min(category.percent_used, 100)
    return render(request, "budget/overview.html", {
        "wedding": wedding,
        "is_couple": is_couple(membership),
        "active_categories": [c for c in categories if c.is_active],
        "inactive_categories": [c for c in categories if not c.is_active],
    })


@budget_member_required
@require_http_methods(["GET", "POST"])
def category_create(request, membership):
    wedding = membership.wedding
    form = CategoryForm(request.POST if request.method == "POST" else None, wedding=wedding)
    if request.method == "POST":
        if form.is_valid():
            category = form.save()
            messages.success(
                request, f"{category.name} added with {format_money(category.allocated_amount, wedding.base_currency)} allocated."
            )
            return redirect(overview_url(wedding.pk))
        messages.error(request, "The category wasn't added. Fix the highlighted fields and try again.")
    return render(request, "budget/category_form.html", {"wedding": wedding, "form": form})


@couple_member_required
@require_http_methods(["GET", "POST"])
def category_edit(request, membership, category_id):
    wedding = membership.wedding
    category = get_category(membership, category_id)
    form = CategoryForm(request.POST if request.method == "POST" else None, instance=category, wedding=wedding)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, f"Changes to {category.name} saved.")
            return redirect(overview_url(wedding.pk))
        messages.error(request, "Your changes weren't saved. Fix the highlighted fields and try again.")
    return render(request, "budget/category_form.html", {"wedding": wedding, "form": form, "category": category})


@couple_member_required
@require_POST
def category_toggle_active(request, membership, category_id):
    category = get_category(membership, category_id)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])
    if category.is_active:
        messages.success(request, f"{category.name} is active again. You can add expenses to it.")
    else:
        messages.success(
            request,
            f"{category.name} was deactivated. Its expenses still count in the totals, but new expenses can't be added to it.",
        )
    return redirect(overview_url(membership.wedding_id))


@couple_member_required
@require_http_methods(["GET", "POST"])
def category_delete(request, membership, category_id):
    category = get_category(membership, category_id)
    blocked_message = (
        f"{category.name} has expenses, so it can't be deleted. "
        "Deactivate it instead — its expenses stay in the totals."
    )
    # BR-07: checked before showing the confirmation, and again by the database (ON DELETE RESTRICT).
    if category.expenses.exists():
        messages.error(request, blocked_message)
        return redirect(overview_url(membership.wedding_id))
    if request.method == "POST":
        name = category.name
        try:
            category.delete()
        except (RestrictedError, ProtectedError):
            messages.error(request, blocked_message)
            return redirect(overview_url(membership.wedding_id))
        messages.success(request, f"{name} was deleted.")
        return redirect(overview_url(membership.wedding_id))
    return render_confirm(
        request, membership,
        page_title=f"Delete {category.name}",
        heading=f"Delete {category.name}?",
        message=f"{category.name} has no expenses. Deleting it removes the category and its "
                f"{format_money(category.allocated_amount, membership.wedding.base_currency)} allocation from the budget.",
        confirm_label="Delete category",
        pending_label="Deleting…",
        cancel_url=overview_url(membership.wedding_id),
    )


@budget_member_required
def expense_list(request, membership):
    wedding = membership.wedding
    categories = BudgetCategory.objects.filter(wedding=wedding)
    expenses = Expense.objects.filter(category__wedding=wedding).select_related("category", "recorded_by")

    selected = None
    category_param = request.GET.get("category", "")
    if category_param.isdigit():
        selected = categories.filter(pk=int(category_param)).first()
    if selected:
        expenses = expenses.filter(category=selected)

    page = Paginator(expenses, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "budget/expense_list.html", {
        "wedding": wedding,
        "is_couple": is_couple(membership),
        "categories": categories,
        "selected": selected,
        "page": page,
        "querystring": params.urlencode() if selected else "",
    })


@budget_member_required
@require_http_methods(["GET", "POST"])
def expense_create(request, membership):
    wedding = membership.wedding
    form = ExpenseForm(request.POST if request.method == "POST" else None, wedding=wedding)
    if request.method == "GET":
        preselect = request.GET.get("category", "")
        if preselect.isdigit() and form.fields["category"].queryset.filter(pk=int(preselect)).exists():
            form.initial["category"] = int(preselect)
    if request.method == "POST":
        if form.is_valid():
            form.instance.recorded_by = request.user
            expense = form.save()
            messages.success(
                request, f"Expense added: {expense.description}, {format_money(expense.amount, wedding.base_currency)}."
            )
            warn_if_over_budget(request, expense.category, wedding.base_currency)
            return redirect("budget:expense_list", wedding_id=wedding.pk)
        messages.error(request, "The expense wasn't added. Fix the highlighted fields and try again.")
    return render(request, "budget/expense_form.html", {
        "wedding": wedding,
        "form": form,
        "has_categories": form.fields["category"].queryset.exists(),
    })


@budget_member_required
@require_http_methods(["GET", "POST"])
def expense_edit(request, membership, expense_id):
    wedding = membership.wedding
    expense = get_editable_expense(membership, expense_id)
    form = ExpenseForm(request.POST if request.method == "POST" else None, instance=expense, wedding=wedding)
    if request.method == "POST":
        if form.is_valid():
            expense = form.save()
            messages.success(request, "Expense saved.")
            warn_if_over_budget(request, expense.category, wedding.base_currency)
            return redirect("budget:expense_list", wedding_id=wedding.pk)
        messages.error(request, "Your changes weren't saved. Fix the highlighted fields and try again.")
    return render(request, "budget/expense_form.html", {
        "wedding": wedding, "form": form, "expense": expense, "has_categories": True,
    })


@budget_member_required
@require_http_methods(["GET", "POST"])
def expense_delete(request, membership, expense_id):
    expense = get_editable_expense(membership, expense_id)
    list_url = reverse("budget:expense_list", args=[membership.wedding_id])
    amount = format_money(expense.amount, membership.wedding.base_currency)
    if request.method == "POST":
        expense.delete()
        messages.success(request, f"Expense deleted: {expense.description}, {amount}.")
        return redirect(list_url)
    return render_confirm(
        request, membership,
        page_title="Delete expense",
        heading="Delete this expense?",
        message=f"{expense.description} ({amount}, {expense.category.name}, {expense.expense_date:%d %B %Y}) "
                "will be removed from the budget. It can't be undone.",
        confirm_label="Delete expense",
        pending_label="Deleting…",
        cancel_url=list_url,
    )
