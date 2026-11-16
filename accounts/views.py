from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .decorators import dashboard_url_for
from .forms import LoginForm, ProfileForm, RegistrationForm, StyledPasswordChangeForm


@never_cache
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect(dashboard_url_for(request.user))

    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(
                request,
                f"Account created. Welcome to WedSync, {user.get_short_name()} — "
                f"you're signed in as a {user.get_role_display()}.",
            )
            return redirect(dashboard_url_for(user))
        messages.error(request, "Your account wasn't created yet. Fix the highlighted fields and try again.")
    return render(request, "accounts/register.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Welcome back, {form.get_user().get_short_name()}.")
        return response

    def get_default_redirect_url(self):
        return dashboard_url_for(self.request.user)


class LogoutView(auth_views.LogoutView):
    """POST-only (Django 5). Ends the session and returns to the login page."""

    next_page = reverse_lazy("accounts:login")

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You've been logged out.")
        return response


@never_cache
@login_required
def profile(request):
    # Always the signed-in user's own record: there is no user id in the URL to tamper with.
    return render(request, "accounts/profile.html", {"profile_user": request.user})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def profile_edit(request):
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=request.user)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
        messages.error(request, "Your changes weren't saved. Fix the highlighted fields and try again.")
    return render(request, "accounts/profile_edit.html", {"form": form})


@method_decorator(never_cache, name="dispatch")
class PasswordChangeView(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:profile")
    success_message = "Password changed. You're still logged in on this device."

    def form_invalid(self, form):
        messages.error(self.request, "Your password wasn't changed. Fix the highlighted fields and try again.")
        return super().form_invalid(form)
