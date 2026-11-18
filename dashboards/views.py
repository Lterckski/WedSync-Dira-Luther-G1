from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import redirect, render

from accounts.decorators import dashboard_url_for, role_required
from accounts.models import Role
from budget.queries import with_budget_totals
from weddings.forms import JoinWeddingForm
from weddings.models import MemberRole, Wedding, WeddingMember, couple_membership

from .modules import AVAILABLE_FEATURES, ROLE_INTROS, ROLE_MODULES


@login_required
def home(request):
    """Send each user to the dashboard for their role."""
    return redirect(dashboard_url_for(request.user))


def _render_dashboard(request, role, template, **context):
    return render(request, template, {
        "modules": ROLE_MODULES[role],
        "intro": ROLE_INTROS[role],
        "available_features": AVAILABLE_FEATURES[role],
        **context,
    })


@role_required(Role.COUPLE)
def couple(request):
    membership = couple_membership(request.user)
    wedding = None
    if membership:
        wedding = with_budget_totals(Wedding.objects.filter(pk=membership.wedding_id)).get()
    return _render_dashboard(
        request, Role.COUPLE, "dashboards/couple.html",
        wedding=wedding,
        join_form=None if membership else JoinWeddingForm(user=request.user),
    )


@role_required(Role.COORDINATOR)
def coordinator(request):
    # Each wedding with its budget totals and couple members in two queries, however many weddings there are.
    weddings = with_budget_totals(Wedding.objects.for_user(request.user)).prefetch_related(
        Prefetch(
            "members",
            queryset=WeddingMember.objects.filter(member_role=MemberRole.COUPLE).select_related("user"),
            to_attr="couple_members",
        )
    )
    return _render_dashboard(
        request, Role.COORDINATOR, "dashboards/coordinator.html",
        weddings=weddings,
        join_form=JoinWeddingForm(user=request.user),
    )


@role_required(Role.VENDOR)
def vendor(request):
    return _render_dashboard(request, Role.VENDOR, "dashboards/vendor.html")
