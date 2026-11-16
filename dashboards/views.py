from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.decorators import dashboard_url_for, role_required
from accounts.models import Role

from .modules import ROLE_INTROS, ROLE_MODULES


@login_required
def home(request):
    """Send each user to the dashboard for their role."""
    return redirect(dashboard_url_for(request.user))


def _render_dashboard(request, role, template):
    return render(request, template, {
        "modules": ROLE_MODULES[role],
        "intro": ROLE_INTROS[role],
    })


@role_required(Role.COUPLE)
def couple(request):
    return _render_dashboard(request, Role.COUPLE, "dashboards/couple.html")


@role_required(Role.COORDINATOR)
def coordinator(request):
    return _render_dashboard(request, Role.COORDINATOR, "dashboards/coordinator.html")


@role_required(Role.VENDOR)
def vendor(request):
    return _render_dashboard(request, Role.VENDOR, "dashboards/vendor.html")
