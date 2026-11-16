"""
The users table, exactly as defined in the SDD data dictionary (Section 4.4).

    users(user_id PK, email UNIQUE, password_hash, full_name, phone NULL,
          role CHECK, is_active DEFAULT TRUE, created_at DEFAULT CURRENT_TIMESTAMP)

Django's own login bookkeeping column (last_login) is removed so the table
matches the document column for column.
"""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone

from core.fields import TimestampField


class Role(models.TextChoices):
    COUPLE = "COUPLE", "Couple"
    COORDINATOR = "COORDINATOR", "Coordinator"
    VENDOR = "VENDOR", "Vendor"
    ADMIN = "ADMIN", "Administrator"


# Roles a person can choose when they register. Administrators are created
# by another administrator or by the ensure_admin command.
PUBLIC_ROLES = (Role.COUPLE, Role.COORDINATOR, Role.VENDOR)


class UserManager(BaseUserManager):
    use_in_migrations = True

    @staticmethod
    def normalize_email_address(email):
        return (email or "").strip().lower()

    def get_by_natural_key(self, email):
        # Log-in is case-insensitive: Ana@Example.com and ana@example.com are one account.
        return self.get(email__iexact=self.normalize_email_address(email))

    def _create_user(self, email, password, **extra_fields):
        email = self.normalize_email_address(email)
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.COUPLE)
        return self._create_user(email, password, **extra_fields)

    def create_admin(self, email, password, **extra_fields):
        extra_fields["role"] = Role.ADMIN
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser):
    user_id = models.AutoField(primary_key=True)
    email = models.EmailField(
        max_length=100,
        unique=True,
        error_messages={"unique": "An account with this email already exists."},
    )
    # Django stores a salted hash (PBKDF2 by default), never the plain password.
    password = models.CharField("password", max_length=255, db_column="password_hash")
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, null=True, blank=True)
    role = models.CharField(max_length=12, choices=Role.choices)
    is_active = models.BooleanField(default=True, db_default=True)
    created_at = TimestampField(default=timezone.now, db_default=Now(), editable=False)

    # Not part of the SDD's users table.
    last_login = None

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=Role.values),
                name="users_role_check",
            ),
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    def clean(self):
        super().clean()
        self.email = UserManager.normalize_email_address(self.email)
        if self.phone is not None:
            self.phone = self.phone.strip() or None

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.email

    @property
    def initials(self):
        parts = [p for p in self.full_name.split() if p[:1].isalpha()]
        if not parts:
            return self.email[:1].upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def is_couple(self):
        return self.role == Role.COUPLE

    @property
    def is_coordinator(self):
        return self.role == Role.COORDINATOR

    @property
    def is_vendor(self):
        return self.role == Role.VENDOR

    @property
    def is_admin(self):
        return self.role == Role.ADMIN
