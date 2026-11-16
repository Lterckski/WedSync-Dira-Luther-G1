from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .models import Role

# Where each role lands after logging in.
DASHBOARD_URL_NAMES = {
    Role.COUPLE: "dashboards:couple",
    Role.COORDINATOR: "dashboards:coordinator",
    Role.VENDOR: "dashboards:vendor",
    Role.ADMIN: "adminpanel:overview",
}


def dashboard_url_for(user):
    return reverse(DASHBOARD_URL_NAMES[user.role])


def role_required(*roles):
    """
    Allow a view only for logged-in users whose role is in `roles`.

    Logged-out visitors are sent to the login page (with ?next=);
    logged-in users with another role get a 403 page, so typing another
    role's dashboard URL never shows its content. Responses are never cached,
    so the Back button can't reveal a page after logout.
    """
    allowed = {str(role) for role in roles}

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.role not in allowed:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return login_required(never_cache(wrapped))

    return decorator
