"""
The wedding workspace (SDD F-02): the weddings and wedding_members tables.

    weddings(wedding_id PK, title, event_code UNIQUE, wedding_date, venue NULL,
             base_currency CHAR(3) DEFAULT 'PHP', status CHECK DEFAULT 'PLANNING',
             created_at DEFAULT CURRENT_TIMESTAMP)

    wedding_members(wedding_member_id PK, wedding_id FK ON DELETE CASCADE,
                    user_id FK ON DELETE CASCADE, member_role CHECK,
                    joined_at DEFAULT CURRENT_TIMESTAMP, UNIQUE (wedding_id, user_id))

event_code is an addition to SDD 4.4: the code a partner or coordinator types
to join the wedding.
"""
import secrets

from django.conf import settings
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone

from accounts.models import Role
from core.fields import FixedCharField, TimestampField

# Event codes leave out the look-alikes 0/O and 1/I so they are easy to read aloud and type.
EVENT_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
EVENT_CODE_LENGTH = 8
EVENT_CODE_PATTERN = rf"^[{EVENT_CODE_ALPHABET}]{{{EVENT_CODE_LENGTH}}}$"

# ISO 4217 codes offered when a wedding is created. base_currency can't change afterwards (BR-04).
CURRENCY_CHOICES = [
    ("PHP", "PHP — Philippine peso"),
    ("USD", "USD — US dollar"),
    ("EUR", "EUR — Euro"),
    ("GBP", "GBP — British pound"),
    ("JPY", "JPY — Japanese yen"),
    ("KRW", "KRW — South Korean won"),
    ("SGD", "SGD — Singapore dollar"),
    ("HKD", "HKD — Hong Kong dollar"),
    ("AUD", "AUD — Australian dollar"),
    ("CAD", "CAD — Canadian dollar"),
    ("AED", "AED — UAE dirham"),
]


def normalize_event_code(value):
    """What people type → what is stored: spaces removed, uppercase."""
    return "".join((value or "").split()).upper()


def new_event_code():
    """A random event code that no wedding uses yet."""
    while True:
        code = "".join(secrets.choice(EVENT_CODE_ALPHABET) for _ in range(EVENT_CODE_LENGTH))
        if not Wedding.objects.filter(event_code=code).exists():
            return code


class WeddingStatus(models.TextChoices):
    PLANNING = "PLANNING", "Planning"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class MemberRole(models.TextChoices):
    COUPLE = "COUPLE", "Couple"
    COORDINATOR = "COORDINATOR", "Coordinator"
    VENDOR = "VENDOR", "Vendor"


# Roles that can join a wedding by typing its event code. Vendors join through contracts (F-04).
CODE_JOIN_ROLES = (Role.COUPLE, Role.COORDINATOR)


class WeddingQuerySet(models.QuerySet):
    def for_user(self, user):
        """Weddings the user is a member of."""
        return self.filter(members__user=user)


class Wedding(models.Model):
    wedding_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=150)
    event_code = models.CharField(
        max_length=EVENT_CODE_LENGTH,
        unique=True,
        editable=False,
        error_messages={"unique": "Another wedding already uses this event code."},
    )
    wedding_date = models.DateField()
    venue = models.CharField(max_length=255, null=True, blank=True)
    base_currency = FixedCharField(max_length=3, choices=CURRENCY_CHOICES, default="PHP", db_default="PHP")
    status = models.CharField(
        max_length=12,
        choices=WeddingStatus.choices,
        default=WeddingStatus.PLANNING,
        db_default=WeddingStatus.PLANNING,
    )
    created_at = TimestampField(default=timezone.now, db_default=Now(), editable=False)

    objects = WeddingQuerySet.as_manager()

    class Meta:
        db_table = "weddings"
        ordering = ["wedding_date", "wedding_id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=WeddingStatus.values),
                name="weddings_status_check",
            ),
            models.CheckConstraint(
                condition=models.Q(event_code__regex=EVENT_CODE_PATTERN),
                name="weddings_event_code_check",
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.event_code:
            self.event_code = new_event_code()
        super().save(*args, **kwargs)

    def regenerate_event_code(self):
        """Give the wedding a new code. The old one stops working at once."""
        self.event_code = new_event_code()
        self.save(update_fields=["event_code"])
        return self.event_code


def couple_membership(user):
    """The couple's own wedding membership (with its wedding), or None if they have no wedding yet."""
    return WeddingMember.objects.select_related("wedding").filter(user=user, member_role=MemberRole.COUPLE).first()


class WeddingMember(models.Model):
    wedding_member_id = models.AutoField(primary_key=True)
    wedding = models.ForeignKey(Wedding, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wedding_memberships")
    member_role = models.CharField(max_length=12, choices=MemberRole.choices)
    joined_at = TimestampField(default=timezone.now, db_default=Now(), editable=False)

    class Meta:
        db_table = "wedding_members"
        ordering = ["joined_at", "wedding_member_id"]
        constraints = [
            # BR-03: a person is a member of a wedding at most once.
            models.UniqueConstraint(fields=["wedding", "user"], name="wedding_members_wedding_id_user_id_key"),
            # A couple account plans one wedding.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(member_role=MemberRole.COUPLE),
                name="wedding_members_one_couple_wedding",
            ),
            models.CheckConstraint(
                condition=models.Q(member_role__in=MemberRole.values),
                name="wedding_members_member_role_check",
            ),
        ]

    def __str__(self):
        return f"{self.user} in {self.wedding} as {self.get_member_role_display()}"
