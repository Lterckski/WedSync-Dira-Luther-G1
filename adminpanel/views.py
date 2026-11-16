from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import role_required
from accounts.forms import StyledSetPasswordForm
from accounts.models import Role, User

from .forms import AdminUserCreateForm, AdminUserUpdateForm

PAGE_SIZE = 15


@role_required(Role.ADMIN)
def overview(request):
    counts = User.objects.aggregate(
        total=Count("user_id"),
        active=Count("user_id", filter=Q(is_active=True)),
        inactive=Count("user_id", filter=Q(is_active=False)),
        couple=Count("user_id", filter=Q(role=Role.COUPLE)),
        coordinator=Count("user_id", filter=Q(role=Role.COORDINATOR)),
        vendor=Count("user_id", filter=Q(role=Role.VENDOR)),
        admin=Count("user_id", filter=Q(role=Role.ADMIN)),
    )
    recent = User.objects.order_by("-created_at", "-user_id")[:5]
    return render(request, "adminpanel/overview.html", {"counts": counts, "recent": recent})


@role_required(Role.ADMIN)
def user_list(request):
    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    status = request.GET.get("status", "")

    users = User.objects.order_by("-created_at", "-user_id")
    if query:
        users = users.filter(Q(full_name__icontains=query) | Q(email__icontains=query))
    if role in Role.values:
        users = users.filter(role=role)
    else:
        role = ""
    if status == "active":
        users = users.filter(is_active=True)
    elif status == "inactive":
        users = users.filter(is_active=False)
    else:
        status = ""

    page = Paginator(users, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "adminpanel/user_list.html", {
        "page": page,
        "query": query,
        "role": role,
        "status": status,
        "roles": Role.choices,
        "filters_active": bool(query or role or status),
        "querystring": params.urlencode(),
    })


@role_required(Role.ADMIN)
@require_http_methods(["GET", "POST"])
def user_create(request):
    form = AdminUserCreateForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Account created for {user.full_name} ({user.get_role_display()}).")
            return redirect("adminpanel:user_edit", user_id=user.pk)
        messages.error(request, "The account wasn't created. Fix the highlighted fields and try again.")
    return render(request, "adminpanel/user_create.html", {"form": form})


@role_required(Role.ADMIN)
@require_http_methods(["GET", "POST"])
def user_edit(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    form = AdminUserUpdateForm(request.POST if request.method == "POST" else None, instance=member, acting_user=request.user)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, f"Changes to {member.full_name} saved.")
            return redirect("adminpanel:user_edit", user_id=member.pk)
        messages.error(request, "Changes weren't saved. Fix the highlighted fields and try again.")
    return render(request, "adminpanel/user_edit.html", {"member": member, "form": form})


@role_required(Role.ADMIN)
@require_POST
def user_toggle_active(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    if member.pk == request.user.pk:
        messages.error(request, "You can't deactivate your own account.")
    else:
        member.is_active = not member.is_active
        member.save(update_fields=["is_active"])
        if member.is_active:
            messages.success(request, f"{member.full_name} can log in again.")
        else:
            messages.success(request, f"{member.full_name} was deactivated and can no longer log in.")
    return redirect("adminpanel:user_edit", user_id=member.pk)


@role_required(Role.ADMIN)
@require_http_methods(["GET", "POST"])
def user_set_password(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    form = StyledSetPasswordForm(member, request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, f"New password set for {member.full_name}. Share it with them privately.")
            return redirect("adminpanel:user_edit", user_id=member.pk)
        messages.error(request, "The password wasn't changed. Fix the highlighted fields and try again.")
    return render(request, "adminpanel/user_set_password.html", {"member": member, "form": form})
