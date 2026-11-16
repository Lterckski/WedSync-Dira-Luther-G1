import getpass
import os

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Role, User, UserManager


class Command(BaseCommand):
    help = (
        "Create the first WedSync administrator. Reads ADMIN_EMAIL, ADMIN_PASSWORD and "
        "ADMIN_FULL_NAME from the environment (for Render's build step), or asks for them. "
        "Does nothing if that account already exists."
    )

    def add_arguments(self, parser):
        parser.add_argument("--no-input", action="store_true", help="Never prompt; skip quietly if variables are missing.")

    def handle(self, *args, **options):
        no_input = options["no_input"]
        email = UserManager.normalize_email_address(os.environ.get("ADMIN_EMAIL", ""))
        password = os.environ.get("ADMIN_PASSWORD", "")
        full_name = " ".join(os.environ.get("ADMIN_FULL_NAME", "").split()) or "WedSync Administrator"

        if not email or not password:
            if no_input:
                self.stdout.write("ensure_admin: ADMIN_EMAIL / ADMIN_PASSWORD not set — skipped.")
                return
            email = email or UserManager.normalize_email_address(input("Admin email: "))
            full_name = " ".join(input(f"Full name [{full_name}]: ").split()) or full_name
            password = password or getpass.getpass("Password: ")
            if password != getpass.getpass("Confirm password: "):
                raise CommandError("Passwords don't match.")

        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            if existing.role != Role.ADMIN:
                self.stdout.write(self.style.WARNING(
                    f"ensure_admin: {email} already exists as {existing.get_role_display()}; left unchanged."
                ))
            else:
                self.stdout.write(f"ensure_admin: administrator {email} already exists.")
            return

        candidate = User(email=email, full_name=full_name)
        try:
            password_validation.validate_password(password, candidate)
        except ValidationError as error:
            raise CommandError("Admin password rejected: " + " ".join(error.messages))

        User.objects.create_admin(email=email, password=password, full_name=full_name)
        self.stdout.write(self.style.SUCCESS(f"ensure_admin: created administrator {email}."))
