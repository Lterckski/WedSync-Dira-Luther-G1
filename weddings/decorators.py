from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache

from accounts.decorators import role_required

from .models import WeddingMember


def wedding_member_required(*user_roles, member_roles=None):
    """
    Allow a view only for members of the wedding in the URL (<wedding_id>).

    Built on accounts' role_required: logged-out visitors go to the login page,
    and users whose account role isn't in `user_roles` get the 403 page.
    Someone who isn't a member of the wedding gets a 404, so a wedding id never
    reveals that the wedding exists. A member whose member_role isn't in
    `member_roles` gets a 403. The view receives the membership (with its
    wedding) instead of the raw id.
    """
    allowed_member_roles = {str(role) for role in member_roles} if member_roles else None

    def decorator(view):
        @wraps(view)
        def wrapped(request, wedding_id, *args, **kwargs):
            membership = get_object_or_404(
                WeddingMember.objects.select_related("wedding"), wedding_id=wedding_id, user=request.user
            )
            if allowed_member_roles is not None and membership.member_role not in allowed_member_roles:
                raise PermissionDenied
            return view(request, membership, *args, **kwargs)

        if user_roles:
            return role_required(*user_roles)(wrapped)
        return login_required(never_cache(wrapped))

    return decorator
