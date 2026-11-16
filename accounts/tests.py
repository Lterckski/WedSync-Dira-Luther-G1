import os
from io import StringIO
from unittest import mock

from django.contrib.auth import SESSION_KEY
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import TestCase
from django.urls import reverse

from .models import Role, User

PASSWORD = "Vows-and-Rings-2027"


def make_user(email="ana@example.com", role=Role.COUPLE, password=PASSWORD, **extra):
    extra.setdefault("full_name", "Ana Dela Cruz")
    return User.objects.create_user(email=email, password=password, role=role, **extra)


def message_texts(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class UsersTableMatchesSddTests(TestCase):
    """SDD 4.4 — Table: users."""

    def columns(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
                FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position
                """
            )
            return {row[0]: row[1:] for row in cursor.fetchall()}

    def test_columns_types_and_nullability(self):
        columns = self.columns()
        self.assertEqual(
            list(columns),
            ["user_id", "email", "password_hash", "full_name", "phone", "role", "is_active", "created_at"],
        )
        self.assertEqual(columns["user_id"][:1], ("integer",))
        self.assertEqual(columns["email"][:3], ("character varying", 100, "NO"))
        self.assertEqual(columns["password_hash"][:3], ("character varying", 255, "NO"))
        self.assertEqual(columns["full_name"][:3], ("character varying", 100, "NO"))
        self.assertEqual(columns["phone"][:3], ("character varying", 20, "YES"))
        self.assertEqual(columns["role"][:3], ("character varying", 12, "NO"))
        self.assertEqual(columns["is_active"][0], "boolean")
        self.assertEqual(columns["is_active"][3], "true")
        self.assertEqual(columns["created_at"][0], "timestamp without time zone")
        self.assertIsNotNone(columns["created_at"][3])

    def test_email_is_unique_in_the_database(self):
        make_user()
        with self.assertRaises(IntegrityError):
            User.objects.bulk_create([User(email="ana@example.com", full_name="Copy", role=Role.COUPLE, password="x")])

    def test_role_check_constraint_rejects_unknown_roles(self):
        with self.assertRaises(IntegrityError):
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (email, password_hash, full_name, role) VALUES (%s, %s, %s, %s)",
                    ["x@example.com", "x", "X", "GUEST"],
                )

    def test_database_defaults_fill_is_active_and_created_at(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (%s, %s, %s, %s) "
                "RETURNING is_active, created_at",
                ["raw@example.com", "x", "Raw Insert", "VENDOR"],
            )
            is_active, created_at = cursor.fetchone()
        self.assertTrue(is_active)
        self.assertIsNotNone(created_at)


class RegistrationTests(TestCase):
    url = reverse("accounts:register")

    def valid_data(self, **overrides):
        data = {
            "full_name": "Ana Dela Cruz",
            "email": "ana@example.com",
            "phone": "0917 555 0123",
            "role": Role.COUPLE,
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return data

    def test_page_offers_only_public_roles(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for value in ("COUPLE", "COORDINATOR", "VENDOR"):
            self.assertContains(response, f'value="{value}"')
        self.assertNotContains(response, 'value="ADMIN"')

    def test_successful_registration_hashes_password_logs_in_and_redirects(self):
        response = self.client.post(self.url, self.valid_data())
        user = User.objects.get(email="ana@example.com")
        self.assertRedirects(response, reverse("dashboards:couple"))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(user.role, Role.COUPLE)
        self.assertEqual(str(user.pk), self.client.session[SESSION_KEY])
        self.assertTrue(any("Account created" in text for text in message_texts(response)))

    def test_each_public_role_lands_on_its_dashboard(self):
        for index, (role, url_name) in enumerate([
            (Role.COUPLE, "dashboards:couple"),
            (Role.COORDINATOR, "dashboards:coordinator"),
            (Role.VENDOR, "dashboards:vendor"),
        ]):
            self.client.logout()
            response = self.client.post(self.url, self.valid_data(email=f"user{index}@example.com", role=role))
            self.assertRedirects(response, reverse(url_name))

    def test_email_is_stored_lowercase_and_trimmed(self):
        self.client.post(self.url, self.valid_data(email="  Ana@Example.COM "))
        self.assertTrue(User.objects.filter(email="ana@example.com").exists())

    def test_blank_phone_is_stored_as_null(self):
        self.client.post(self.url, self.valid_data(phone="   "))
        self.assertIsNone(User.objects.get(email="ana@example.com").phone)

    def test_required_fields(self):
        response = self.client.post(self.url, {})
        form = response.context["form"]
        for field in ("full_name", "email", "role", "password1", "password2"):
            self.assertIn(field, form.errors)
        self.assertNotIn("phone", form.errors)
        self.assertEqual(User.objects.count(), 0)
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, "Your account wasn&#x27;t created yet")

    def test_invalid_email_format(self):
        response = self.client.post(self.url, self.valid_data(email="ana-at-example"))
        self.assertIn("Enter a valid email address", response.context["form"].errors["email"][0])

    def test_duplicate_email_is_rejected_case_insensitively(self):
        make_user(email="ana@example.com")
        response = self.client.post(self.url, self.valid_data(email="ANA@example.com"))
        self.assertIn("already exists", response.context["form"].errors["email"][0])
        self.assertEqual(User.objects.count(), 1)

    def test_password_confirmation_must_match(self):
        response = self.client.post(self.url, self.valid_data(password2=PASSWORD + "x"))
        self.assertIn("don't match", response.context["form"].errors["password2"][0])
        self.assertFalse(User.objects.exists())

    def test_weak_passwords_are_rejected(self):
        for weak in ("12345678", "password", "short1"):
            response = self.client.post(self.url, self.valid_data(password1=weak, password2=weak))
            self.assertIn("password1", response.context["form"].errors, weak)
        self.assertFalse(User.objects.exists())

    def test_cannot_register_as_administrator(self):
        response = self.client.post(self.url, self.valid_data(role="ADMIN"))
        self.assertIn("role", response.context["form"].errors)
        self.assertFalse(User.objects.exists())

    def test_invalid_phone(self):
        response = self.client.post(self.url, self.valid_data(phone="call me"))
        self.assertIn("phone", response.context["form"].errors)

    def test_logged_in_user_is_sent_to_dashboard(self):
        self.client.force_login(make_user())
        self.assertRedirects(self.client.get(self.url), reverse("dashboards:couple"))


class LoginLogoutTests(TestCase):
    login_url = reverse("accounts:login")
    logout_url = reverse("accounts:logout")

    def test_login_redirects_each_role_to_its_dashboard(self):
        for role, url_name in [
            (Role.COUPLE, "dashboards:couple"),
            (Role.COORDINATOR, "dashboards:coordinator"),
            (Role.VENDOR, "dashboards:vendor"),
            (Role.ADMIN, "adminpanel:overview"),
        ]:
            make_user(email=f"{role.lower()}@example.com", role=role)
            self.client.logout()
            response = self.client.post(self.login_url, {"username": f"{role.lower()}@example.com", "password": PASSWORD})
            self.assertRedirects(response, reverse(url_name))

    def test_login_email_is_case_insensitive(self):
        make_user()
        response = self.client.post(self.login_url, {"username": "ANA@Example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("dashboards:couple"))

    def test_invalid_credentials_show_an_error(self):
        make_user()
        response = self.client.post(self.login_url, {"username": "ana@example.com", "password": "wrong-password"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The email or password is incorrect")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_unknown_email_shows_the_same_error(self):
        response = self.client.post(self.login_url, {"username": "nobody@example.com", "password": PASSWORD})
        self.assertContains(response, "The email or password is incorrect")

    def test_deactivated_account_cannot_log_in(self):
        make_user(is_active=False)
        response = self.client.post(self.login_url, {"username": "ana@example.com", "password": PASSWORD})
        self.assertContains(response, "This account has been deactivated")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_safe_next_is_followed_and_external_next_is_ignored(self):
        make_user()
        response = self.client.post(
            self.login_url + "?next=/accounts/profile/",
            {"username": "ana@example.com", "password": PASSWORD, "next": "/accounts/profile/"},
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.client.logout()
        response = self.client.post(
            self.login_url, {"username": "ana@example.com", "password": PASSWORD, "next": "https://evil.example/"}
        )
        self.assertRedirects(response, reverse("dashboards:couple"))

    def test_logout_ends_the_session(self):
        self.client.force_login(make_user())
        response = self.client.post(self.logout_url)
        self.assertRedirects(response, self.login_url)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertRedirects(
            self.client.get(reverse("dashboards:couple")),
            f"{self.login_url}?next={reverse('dashboards:couple')}",
        )

    def test_messages_have_a_close_button_and_only_success_closes_itself(self):
        make_user()
        response = self.client.post(self.login_url, {"username": "ana@example.com", "password": PASSWORD}, follow=True)
        self.assertContains(response, 'data-alert-close')
        self.assertContains(response, 'aria-label="Dismiss message"')
        self.assertContains(response, 'data-autodismiss')
        self.client.logout()
        response = self.client.post(reverse("accounts:register"), {})
        self.assertContains(response, 'ws-alert--error')
        self.assertNotContains(response, 'data-autodismiss')

    def test_logout_requires_post(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(self.logout_url).status_code, 405)

    def test_deactivating_a_signed_in_user_ends_their_access(self):
        user = make_user()
        self.client.force_login(user)
        User.objects.filter(pk=user.pk).update(is_active=False)
        response = self.client.get(reverse("dashboards:couple"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(self.login_url))


class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_user(phone="0917 555 0123")
        self.other = make_user(email="marco@example.com", full_name="Marco Reyes")
        self.client.force_login(self.user)

    def test_profile_shows_only_the_signed_in_user(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "ana@example.com")
        self.assertContains(response, "0917 555 0123")
        self.assertNotContains(response, "marco@example.com")

    def test_profile_requires_login(self):
        self.client.logout()
        for name in ("accounts:profile", "accounts:profile_edit", "accounts:password_change"):
            url = reverse(name)
            self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_update_profile_details(self):
        response = self.client.post(reverse("accounts:profile_edit"), {
            "full_name": "Ana  Reyes ", "email": "Ana.Reyes@Example.com", "phone": "",
        })
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Ana Reyes")
        self.assertEqual(self.user.email, "ana.reyes@example.com")
        self.assertIsNone(self.user.phone)
        self.assertIn("Profile updated.", message_texts(response))

    def test_cannot_take_another_users_email(self):
        response = self.client.post(reverse("accounts:profile_edit"), {
            "full_name": "Ana Dela Cruz", "email": "MARCO@example.com", "phone": "",
        })
        self.assertIn("email", response.context["form"].errors)

    def test_role_and_status_cannot_be_changed_from_the_profile(self):
        self.client.post(reverse("accounts:profile_edit"), {
            "full_name": "Ana Dela Cruz", "email": "ana@example.com", "phone": "",
            "role": "ADMIN", "is_active": "false",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, Role.COUPLE)
        self.assertTrue(self.user.is_active)

    def test_change_password_keeps_the_session(self):
        new_password = "Seating-Chart-Table-9"
        response = self.client.post(reverse("accounts:password_change"), {
            "old_password": PASSWORD, "new_password1": new_password, "new_password2": new_password,
        })
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_change_password_needs_the_current_password(self):
        response = self.client.post(reverse("accounts:password_change"), {
            "old_password": "wrong", "new_password1": "Seating-Chart-Table-9", "new_password2": "Seating-Chart-Table-9",
        })
        self.assertIn("old_password", response.context["form"].errors)


class EnsureAdminCommandTests(TestCase):
    def test_creates_an_administrator_from_environment(self):
        env = {"ADMIN_EMAIL": "Admin@WedSync.test", "ADMIN_PASSWORD": "Run-of-Show-0900", "ADMIN_FULL_NAME": "Site Admin"}
        with mock.patch.dict(os.environ, env):
            call_command("ensure_admin", "--no-input", stdout=StringIO())
            call_command("ensure_admin", "--no-input", stdout=StringIO())  # idempotent
        admin = User.objects.get(email="admin@wedsync.test")
        self.assertEqual(admin.role, Role.ADMIN)
        self.assertTrue(admin.check_password("Run-of-Show-0900"))
        self.assertEqual(User.objects.count(), 1)

    def test_skips_quietly_without_variables(self):
        with mock.patch.dict(os.environ, {"ADMIN_EMAIL": "", "ADMIN_PASSWORD": ""}):
            call_command("ensure_admin", "--no-input", stdout=StringIO())
        self.assertFalse(User.objects.exists())
