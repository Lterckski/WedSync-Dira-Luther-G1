from django import forms

from accounts.forms import RegistrationForm, StyledFormMixin, AccountFieldsMixin, TelInput, email_widget
from accounts.models import Role, User

ROLE_CHOICES = [(role.value, role.label) for role in Role]


class AdminUserCreateForm(RegistrationForm):
    """An administrator creates an account for someone: any role, administrators included."""

    duplicate_email_message = "An account with this email already exists."

    role = forms.ChoiceField(
        label="Role",
        choices=[("", "Choose a role")] + ROLE_CHOICES,
        error_messages={"required": "Choose a role for this account."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].widget.attrs["class"] = "ws-input"
        self.fields["phone"].help_text = ""
        self.fields["password1"].label = "Temporary password"
        self.fields["password1"].help_text = "Share it with the person privately. They can change it from their profile."


class AdminUserUpdateForm(StyledFormMixin, AccountFieldsMixin, forms.ModelForm):
    duplicate_email_message = "Another account already uses this email."

    class Meta:
        model = User
        fields = ["full_name", "email", "phone", "role", "is_active"]
        labels = {
            "full_name": "Full name",
            "email": "Email address",
            "phone": "Contact number",
            "role": "Role",
            "is_active": "Account is active",
        }
        widgets = {
            "email": email_widget(),
            "phone": TelInput(attrs={"placeholder": "0917 555 0123"}),
        }

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = ROLE_CHOICES
        self.fields["is_active"].help_text = "Deactivated accounts can't log in. Their records stay in the database."
        self.editing_self = acting_user is not None and acting_user.pk == self.instance.pk
        if self.editing_self:
            # An administrator can't lock themselves out.
            self.fields["role"].disabled = True
            self.fields["is_active"].disabled = True
            self.fields["role"].help_text = "You can't change your own role."
