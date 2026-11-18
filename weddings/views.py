from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, RestrictedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import role_required
from accounts.models import Role

from .decorators import wedding_member_required
from .forms import JoinWeddingForm, WeddingCreateForm, WeddingUpdateForm
from .models import CODE_JOIN_ROLES, MemberRole, WeddingMember, couple_membership

COUPLE_ONLY = (MemberRole.COUPLE,)


def render_confirm(request, membership, **context):
    """The shared confirmation page every delete/remove/leave goes through before its POST."""
    context.setdefault("cancel_url", reverse("weddings:detail", args=[membership.wedding_id]))
    return render(request, "weddings/confirm.html", {"wedding": membership.wedding, **context})


@role_required(Role.COUPLE)
@require_http_methods(["GET", "POST"])
def wedding_create(request):
    existing = couple_membership(request.user)
    if existing:
        messages.error(request, "You already have a wedding. A couple account can plan one wedding only.")
        return redirect("weddings:detail", wedding_id=existing.wedding_id)

    form = WeddingCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if form.is_valid():
            wedding = form.save_for(request.user)
            messages.success(
                request,
                f"{wedding.title} is ready. Share the event code {wedding.event_code} with your partner and coordinator.",
            )
            return redirect("weddings:detail", wedding_id=wedding.pk)
        messages.error(request, "Your wedding wasn't created yet. Fix the highlighted fields and try again.")
    return render(request, "weddings/wedding_create.html", {"form": form})


@role_required(*CODE_JOIN_ROLES)
@require_http_methods(["GET", "POST"])
def wedding_join(request):
    form = JoinWeddingForm(request.POST if request.method == "POST" else None, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            try:
                membership = form.save()
            except IntegrityError:
                # Someone joined in the same instant; the database constraints decided.
                messages.error(request, "You couldn't join this wedding. Refresh the page and check your weddings.")
                return redirect("dashboards:home")
            messages.success(request, f"You joined {membership.wedding.title}.")
            return redirect("weddings:detail", wedding_id=membership.wedding_id)
        messages.error(request, "You didn't join a wedding yet. Check the event code and try again.")
    return render(request, "weddings/wedding_join.html", {"form": form})


@wedding_member_required()
def wedding_detail(request, membership):
    wedding = membership.wedding
    return render(request, "weddings/wedding_detail.html", {
        "wedding": wedding,
        "membership": membership,
        "is_couple": membership.member_role == MemberRole.COUPLE,
        "members": wedding.members.select_related("user"),
    })


@wedding_member_required(member_roles=COUPLE_ONLY)
@require_http_methods(["GET", "POST"])
def wedding_edit(request, membership):
    wedding = membership.wedding
    form = WeddingUpdateForm(request.POST if request.method == "POST" else None, instance=wedding)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Wedding details saved.")
            return redirect("weddings:detail", wedding_id=wedding.pk)
        messages.error(request, "Your changes weren't saved. Fix the highlighted fields and try again.")
    return render(request, "weddings/wedding_edit.html", {"wedding": wedding, "form": form})


@wedding_member_required(member_roles=COUPLE_ONLY)
@require_http_methods(["GET", "POST"])
def wedding_delete(request, membership):
    wedding = membership.wedding
    if request.method == "POST":
        title = wedding.title
        try:
            with transaction.atomic():
                wedding.delete()
        except (RestrictedError, ProtectedError, IntegrityError):
            # budget_categories → weddings is ON DELETE RESTRICT.
            messages.error(
                request,
                f"{title} still has budget categories, so it can't be deleted. "
                "Change its status to Cancelled instead — its budget history stays.",
            )
            return redirect("weddings:detail", wedding_id=wedding.pk)
        messages.success(request, f"{title} was deleted.")
        return redirect("dashboards:home")
    return render_confirm(
        request, membership,
        page_title=f"Delete {wedding.title}",
        heading=f"Delete {wedding.title}?",
        message="This removes the wedding and its member list for everyone. It can't be undone. "
                "If the wedding is off but you want to keep its records, change its status to Cancelled instead.",
        confirm_label="Delete wedding",
        pending_label="Deleting…",
    )


@wedding_member_required(member_roles=COUPLE_ONLY)
@require_POST
def event_code_regenerate(request, membership):
    code = membership.wedding.regenerate_event_code()
    messages.success(request, f"New event code: {code}. The old code no longer works.")
    return redirect("weddings:detail", wedding_id=membership.wedding_id)


@wedding_member_required(member_roles=COUPLE_ONLY)
@require_http_methods(["GET", "POST"])
def member_remove(request, membership, member_id):
    # Only coordinators can be removed; anything else (or another wedding's member) is a 404.
    target = get_object_or_404(
        WeddingMember.objects.select_related("user"),
        pk=member_id, wedding_id=membership.wedding_id, member_role=MemberRole.COORDINATOR,
    )
    name = target.user.full_name
    if request.method == "POST":
        target.delete()
        messages.success(request, f"{name} was removed from {membership.wedding.title}.")
        return redirect("weddings:detail", wedding_id=membership.wedding_id)
    return render_confirm(
        request, membership,
        page_title=f"Remove {name}",
        heading=f"Remove {name}?",
        message=f"{name} will lose access to {membership.wedding.title}. "
                "They can join again only with your current event code.",
        confirm_label="Remove coordinator",
        pending_label="Removing…",
    )


@wedding_member_required(member_roles=(MemberRole.COORDINATOR,))
@require_http_methods(["GET", "POST"])
def wedding_leave(request, membership):
    title = membership.wedding.title
    if request.method == "POST":
        membership.delete()
        messages.success(request, f"You left {title}.")
        return redirect("dashboards:home")
    return render_confirm(
        request, membership,
        page_title=f"Leave {title}",
        heading=f"Leave {title}?",
        message="You'll lose access to this wedding. To come back, you'll need the couple's current event code.",
        confirm_label="Leave wedding",
        pending_label="Leaving…",
    )
