from django.utils.functional import SimpleLazyObject

from accounts.models import Role
from weddings.models import Wedding, couple_membership


def budget_nav(request):
    """
    The wedding whose budget the navbar links to: a couple's own wedding, or for a
    coordinator the wedding they're looking at. Vendors and administrators never get
    a budget link. Looked up only when a template uses it.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or user.role not in (Role.COUPLE, Role.COORDINATOR):
        return {}

    def nav_wedding():
        if user.role == Role.COUPLE:
            membership = couple_membership(user)
            return membership.wedding if membership else None
        match = request.resolver_match
        wedding_id = match.kwargs.get("wedding_id") if match else None
        if wedding_id is None:
            return None
        return Wedding.objects.for_user(user).filter(pk=wedding_id).first()

    return {"budget_nav_wedding": SimpleLazyObject(nav_wedding)}
