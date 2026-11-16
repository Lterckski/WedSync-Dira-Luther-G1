import re

from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.core.exceptions import ValidationError

from .models import PUBLIC_ROLES, Role, User, UserManager

PASSWORD_HELP = "Use at least 8 characters. Avoid common passwords, all-number passwords, and your name or email."

ROLE_DESCRIPTIONS = {
    Role.COUPLE: "Plan your wedding: budget, guests, vendors and the day-of timeline.",
    Role.COORDINATOR: "Run weddings for your clients and keep everyone on schedule.",
    Role.VENDOR: "See the events you're booked for, your contracts and your call times.",
}


class TelInput(forms.TextInput):
    input_type = "tel"


class StyledFormMixin:
    """Give every text-like widget the design system's ws-input class."""

    skip_widgets = (forms.RadioSelect, forms.CheckboxInput, forms.CheckboxSelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, self.skip_widgets):
                continue
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} ws-input".strip()


def clean_full_name_value(value):
    value = " ".join((value or "").split())
    if not value:
        raise ValidationError("Enter your full name.")
    return value


def clean_phone_value(value):
    value = (value or "").strip()
    if not value:
        return None  # stored as NULL, as in the SDD
    digits = sum(ch.isdigit() for ch in value)
    if not re.fullmatch(r"[0-9+()\-\s]+", value) or not 7 <= digits <= 15:
        raise ValidationError("Enter a phone number with 7 to 15 digits, like 0917 555 0123.")
    return value


def email_widget(**extra):
    attrs = {
        "autocomplete": "email",
        "spellcheck": "false",
        "autocapitalize": "none",
        "placeholder": "name@example.com",
    }
    attrs.update(extra)
    return forms.EmailInput(attrs=attrs)


EMAIL_ERRORS = {
    "required": "Enter your email address.",
    "invalid": "Enter a valid email address, like name@example.com.",
    "max_length": "Use an email address with 100 characters or fewer.",
}


class AccountFieldsMixin:
    """Shared cleaning for full_name / email / phone on any form that edits a user."""

    def clean_full_name(self):
        return clean_full_name_value(self.cleaned_data.get("full_name"))

    def clean_phone(self):
        return clean_phone_value(self.cleaned_data.get("phone"))

    def clean_email(self):
        email = UserManager.normalize_email_address(self.cleaned_data.get("email"))
        others = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise ValidationError(self.duplicate_email_message)
        return email

    duplicate_email_message = "An account with this email already exists."


class RegistrationForm(StyledFormMixin, AccountFieldsMixin, forms.ModelForm):
    duplicate_email_message = "An account with this email already exists. Log in instead, or use a different email."

    role = forms.ChoiceField(
        label="I'm joining as",
        choices=[(role.value, role.label) for role in PUBLIC_ROLES],
        widget=forms.RadioSelect,
        error_messages={
            "required": "Choose how you'll use WedSync.",
            "invalid_choice": "Choose Couple, Coordinator or Vendor.",
        },
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        help_text=PASSWORD_HELP,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Create a password."},
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Retype your password to confirm it."},
    )

    class Meta:
        model = User
        fields = ["full_name", "email", "phone", "role"]
        labels = {"full_name": "Full name", "email": "Email address", "phone": "Contact number"}
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Ana Dela Cruz"}),
            "email": email_widget(),
            "phone": TelInput(attrs={"autocomplete": "tel", "placeholder": "0917 555 0123"}),
        }
        error_messages = {
            "full_name": {"required": "Enter your full name.", "max_length": "Use 100 characters or fewer."},
            "email": EMAIL_ERRORS,
            "phone": {"max_length": "Use 20 characters or fewer."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].help_text = "Your coordinator and vendors use this to reach you."
        self.role_options = [
            {"value": value, "label": label, "description": ROLE_DESCRIPTIONS.get(value, "")}
            for value, label in self.fields["role"].choices
        ]

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords don't match. Retype the same password in both fields.")
        if password1:
            candidate = User(
                email=cleaned.get("email") or "",
                full_name=cleaned.get("full_name") or "",
            )
            try:
                password_validation.validate_password(password1, candidate)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(
        label="Email address",
        max_length=100,
        widget=email_widget(autofocus=True),
        error_messages=EMAIL_ERRORS,
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        error_messages={"required": "Enter your password."},
    )

    error_messages = {
        "invalid_login": "The email or password is incorrect. Check both and try again.",
        "inactive": "This account has been deactivated. Contact a WedSync administrator to restore it.",
    }

    def clean(self):
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if email is not None and password:
            self.user_cache = authenticate(self.request, username=email, password=password)
            if self.user_cache is None:
                # The default backend refuses inactive accounts without saying why.
                # Tell the owner (and only someone who knows the password) what happened.
                try:
                    user = User.objects.get_by_natural_key(email)
                except User.DoesNotExist:
                    user = None
                if user is not None and not user.is_active and user.check_password(password):
                    raise ValidationError(self.error_messages["inactive"], code="inactive")
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class ProfileForm(StyledFormMixin, AccountFieldsMixin, forms.ModelForm):
    duplicate_email_message = "Another account already uses this email. Use a different one."

    class Meta:
        model = User
        fields = ["full_name", "email", "phone"]
        labels = {"full_name": "Full name", "email": "Email address", "phone": "Contact number"}
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": email_widget(),
            "phone": TelInput(attrs={"autocomplete": "tel", "placeholder": "0917 555 0123"}),
        }
        error_messages = RegistrationForm.Meta.error_messages


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_incorrect": "Your current password is incorrect. Enter it again.",
        "password_mismatch": "The new passwords don't match. Retype the same password in both fields.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Current password"
        self.fields["old_password"].widget.attrs.pop("autofocus", None)
        self.fields["new_password1"].label = "New password"
        self.fields["new_password1"].help_text = PASSWORD_HELP
        self.fields["new_password2"].label = "Confirm new password"
        self.fields["old_password"].error_messages["required"] = "Enter your current password."
        self.fields["new_password1"].error_messages["required"] = "Create a new password."
        self.fields["new_password2"].error_messages["required"] = "Retype your new password to confirm it."


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    error_messages = {
        **SetPasswordForm.error_messages,
        "password_mismatch": "The passwords don't match. Retype the same password in both fields.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "New password"
        self.fields["new_password1"].help_text = PASSWORD_HELP
        self.fields["new_password2"].label = "Confirm new password"
        self.fields["new_password1"].error_messages["required"] = "Create a new password."
        self.fields["new_password2"].error_messages["required"] = "Retype the new password to confirm it."
