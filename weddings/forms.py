import re

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.forms import StyledFormMixin
from accounts.models import Role

from .models import (
    EVENT_CODE_PATTERN,
    MemberRole,
    Wedding,
    WeddingMember,
    normalize_event_code,
)

WEDDING_ERRORS = {
    "title": {"required": "Enter a name for your wedding.", "max_length": "Use 150 characters or fewer."},
    "wedding_date": {"required": "Enter the wedding date.", "invalid": "Enter a real date, like 14 February 2027."},
    "venue": {"max_length": "Use 255 characters or fewer."},
    "base_currency": {"required": "Choose the currency for your budget.", "invalid_choice": "Choose one of the listed currencies."},
    "status": {"required": "Choose a status.", "invalid_choice": "Choose Planning, Completed or Cancelled."},
}


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class WeddingFieldsMixin:
    def clean_title(self):
        title = " ".join((self.cleaned_data.get("title") or "").split())
        if not title:
            raise ValidationError("Enter a name for your wedding.")
        return title

    def clean_venue(self):
        return " ".join((self.cleaned_data.get("venue") or "").split()) or None  # stored as NULL


class WeddingCreateForm(StyledFormMixin, WeddingFieldsMixin, forms.ModelForm):
    class Meta:
        model = Wedding
        fields = ["title", "wedding_date", "venue", "base_currency"]
        labels = {"title": "Wedding name", "wedding_date": "Wedding date", "venue": "Venue", "base_currency": "Budget currency"}
        help_texts = {
            "title": "Shown to everyone you invite, e.g. “Ana & Marco's Wedding”.",
            "base_currency": "Every amount in your budget uses this currency. It can't be changed later.",
        }
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Ana & Marco's Wedding"}),
            "wedding_date": DateInput(),
            "venue": forms.TextInput(attrs={"placeholder": "Church, garden or reception hall"}),
        }
        error_messages = WEDDING_ERRORS

    def save_for(self, couple):
        """Create the wedding and make `couple` its first COUPLE member, together or not at all."""
        with transaction.atomic():
            wedding = self.save()
            WeddingMember.objects.create(wedding=wedding, user=couple, member_role=MemberRole.COUPLE)
        return wedding


class WeddingUpdateForm(StyledFormMixin, WeddingFieldsMixin, forms.ModelForm):
    """base_currency isn't a field here: it is fixed once the wedding exists (BR-04)."""

    class Meta:
        model = Wedding
        fields = ["title", "wedding_date", "venue", "status"]
        labels = {"title": "Wedding name", "wedding_date": "Wedding date", "venue": "Venue", "status": "Status"}
        help_texts = {"status": "Cancelled weddings keep their budget history."}
        widgets = {"wedding_date": DateInput()}
        error_messages = WEDDING_ERRORS


class JoinWeddingForm(StyledFormMixin, forms.Form):
    event_code = forms.CharField(
        label="Event code",
        max_length=40,
        help_text="8 letters and numbers. Ask the couple for it.",
        widget=forms.TextInput(attrs={
            "placeholder": "K7M2Q9XA",
            "autocomplete": "off",
            "autocapitalize": "characters",
            "spellcheck": "false",
        }),
        error_messages={"required": "Enter the event code the couple shared with you."},
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.wedding = None

    def clean_event_code(self):
        code = normalize_event_code(self.cleaned_data.get("event_code"))
        if not re.fullmatch(EVENT_CODE_PATTERN, code):
            raise ValidationError("Event codes have 8 letters and numbers, like K7M2Q9XA. Check the code and try again.")
        self.wedding = Wedding.objects.filter(event_code=code).first()
        if self.wedding is None:
            raise ValidationError(
                "No wedding uses this code. Check it with the couple — the code changes if they make a new one."
            )
        return code

    def clean(self):
        cleaned = super().clean()
        if self.wedding is None:
            return cleaned
        if WeddingMember.objects.filter(wedding=self.wedding, user=self.user).exists():
            self.add_error("event_code", f"You're already a member of {self.wedding.title}.")
        elif self.user.role == Role.COUPLE and WeddingMember.objects.filter(
            user=self.user, member_role=MemberRole.COUPLE
        ).exists():
            self.add_error("event_code", "You already belong to a wedding. A couple account can be part of one wedding only.")
        return cleaned

    def save(self):
        return WeddingMember.objects.create(wedding=self.wedding, user=self.user, member_role=self.user.role)
