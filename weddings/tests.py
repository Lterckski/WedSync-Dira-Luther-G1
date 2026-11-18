import datetime

from django.contrib.messages import get_messages
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from accounts.models import Role, User

from .models import EVENT_CODE_PATTERN, MemberRole, Wedding, WeddingMember, new_event_code

PASSWORD = "Vows-and-Rings-2027"


def make_user(email, role=Role.COUPLE, full_name=None):
    return User.objects.create_user(
        email=email, password=PASSWORD, role=role, full_name=full_name or email.split("@")[0].title(),
    )


def make_wedding(couple, title="Ana & Marco's Wedding", **extra):
    extra.setdefault("wedding_date", datetime.date(2027, 2, 14))
    wedding = Wedding.objects.create(title=title, **extra)
    WeddingMember.objects.create(wedding=wedding, user=couple, member_role=MemberRole.COUPLE)
    return wedding


def message_texts(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


def raw(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall() if cursor.description else None


def columns(table):
    return {
        row[0]: row[1:]
        for row in raw(
            "SELECT column_name, data_type, character_maximum_length, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
            [table],
        )
    }


def constraints(table):
    """{constraint name: (type, definition)} as PostgreSQL stores them."""
    return {
        row[0]: (row[1], row[2])
        for row in raw(
            "SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = %s::regclass",
            [table],
        )
    }


class WeddingTablesMatchSpecTests(TestCase):
    """SDD 4.4 — Tables: weddings and wedding_members (event_code added)."""

    def test_weddings_columns(self):
        cols = columns("weddings")
        self.assertEqual(
            list(cols),
            ["wedding_id", "title", "event_code", "wedding_date", "venue", "base_currency", "status", "created_at"],
        )
        self.assertEqual(cols["wedding_id"][0], "integer")
        self.assertEqual(cols["title"][:3], ("character varying", 150, "NO"))
        self.assertEqual(cols["event_code"][:3], ("character varying", 8, "NO"))
        self.assertEqual(cols["wedding_date"][:1] + cols["wedding_date"][2:3], ("date", "NO"))
        self.assertEqual(cols["venue"][:3], ("character varying", 255, "YES"))
        self.assertEqual(cols["base_currency"][:3], ("character", 3, "NO"))
        self.assertIn("'PHP'", cols["base_currency"][3])
        self.assertEqual(cols["status"][:3], ("character varying", 12, "NO"))
        self.assertIn("'PLANNING'", cols["status"][3])
        self.assertEqual(cols["created_at"][0], "timestamp without time zone")
        self.assertIsNotNone(cols["created_at"][3])

    def test_wedding_members_columns(self):
        cols = columns("wedding_members")
        self.assertEqual(
            sorted(cols), sorted(["wedding_member_id", "wedding_id", "user_id", "member_role", "joined_at"])
        )
        self.assertEqual(cols["wedding_id"][0], "integer")
        self.assertEqual(cols["wedding_id"][2], "NO")
        self.assertEqual(cols["user_id"][2], "NO")
        self.assertEqual(cols["member_role"][:3], ("character varying", 12, "NO"))
        self.assertEqual(cols["joined_at"][0], "timestamp without time zone")
        self.assertIsNotNone(cols["joined_at"][3])

    def test_named_constraints_exist(self):
        weddings = constraints("weddings")
        self.assertIn("weddings_status_check", weddings)
        self.assertIn("weddings_event_code_check", weddings)
        self.assertTrue(any(kind == "u" and "(event_code)" in d for kind, d in weddings.values()))
        members = constraints("wedding_members")
        self.assertEqual(members["wedding_members_wedding_id_user_id_key"], ("u", "UNIQUE (wedding_id, user_id)"))
        self.assertIn("wedding_members_member_role_check", members)

    def test_foreign_keys_cascade_in_postgresql(self):
        members = constraints("wedding_members")
        self.assertIn("ON DELETE CASCADE", members["wedding_members_wedding_id_fkey"][1])
        self.assertIn("REFERENCES weddings(wedding_id)", members["wedding_members_wedding_id_fkey"][1])
        self.assertIn("ON DELETE CASCADE", members["wedding_members_user_id_fkey"][1])
        self.assertIn("REFERENCES users(user_id)", members["wedding_members_user_id_fkey"][1])


class WeddingConstraintTests(TestCase):
    """The database itself rejects bad rows, even when Django is bypassed."""

    @classmethod
    def setUpTestData(cls):
        cls.couple = make_user("ana@example.com")
        cls.wedding = make_wedding(cls.couple)

    def insert_wedding(self, code="ABCDEFGH", status="PLANNING"):
        raw(
            "INSERT INTO weddings (title, event_code, wedding_date, status) VALUES (%s, %s, %s, %s)",
            ["Raw", code, "2027-01-01", status],
        )

    def test_database_defaults(self):
        row = raw(
            "INSERT INTO weddings (title, event_code, wedding_date) VALUES ('Raw', 'RAWCODE2', '2027-01-01') "
            "RETURNING base_currency, status, created_at"
        )[0]
        self.assertEqual(row[:2], ("PHP", "PLANNING"))
        self.assertIsNotNone(row[2])

    def test_status_check(self):
        with self.assertRaises(IntegrityError):
            self.insert_wedding(status="POSTPONED")

    def test_event_code_unique(self):
        with self.assertRaises(IntegrityError):
            self.insert_wedding(code=self.wedding.event_code)

    def test_event_code_check_rejects_look_alikes_and_lowercase(self):
        for bad in ["ABCDEFG0", "ABCDEFGI", "abcdefgh", "ABC"]:
            with self.subTest(code=bad), self.assertRaises(IntegrityError), transaction.atomic():
                self.insert_wedding(code=bad)

    def test_member_role_check(self):
        coordinator = make_user("carla@example.com", Role.COORDINATOR)
        with self.assertRaises(IntegrityError):
            raw(
                "INSERT INTO wedding_members (wedding_id, user_id, member_role) VALUES (%s, %s, 'GUEST')",
                [self.wedding.pk, coordinator.pk],
            )

    def test_member_once_per_wedding(self):
        coordinator = make_user("carla@example.com", Role.COORDINATOR)
        WeddingMember.objects.create(wedding=self.wedding, user=coordinator, member_role=MemberRole.COORDINATOR)
        with self.assertRaises(IntegrityError):
            WeddingMember.objects.create(wedding=self.wedding, user=coordinator, member_role=MemberRole.COORDINATOR)

    def test_couple_account_has_one_wedding(self):
        other = Wedding.objects.create(title="Second", wedding_date=datetime.date(2027, 5, 1))
        with self.assertRaises(IntegrityError):
            WeddingMember.objects.create(wedding=other, user=self.couple, member_role=MemberRole.COUPLE)

    def test_deleting_a_wedding_in_sql_cascades_to_members(self):
        raw("DELETE FROM weddings WHERE wedding_id = %s", [self.wedding.pk])
        self.assertFalse(WeddingMember.objects.filter(wedding_id=self.wedding.pk).exists())

    def test_deleting_a_user_in_sql_cascades_to_memberships(self):
        raw("DELETE FROM users WHERE user_id = %s", [self.couple.pk])
        self.assertFalse(WeddingMember.objects.filter(user_id=self.couple.pk).exists())
        self.assertTrue(Wedding.objects.filter(pk=self.wedding.pk).exists())


class EventCodeTests(TestCase):
    def test_generated_codes_are_8_unambiguous_characters(self):
        for _ in range(50):
            code = new_event_code()
            self.assertRegex(code, EVENT_CODE_PATTERN)
            self.assertFalse(set(code) & set("0O1I"))

    def test_new_weddings_get_a_unique_code(self):
        couples = [make_user(f"c{i}@example.com") for i in range(5)]
        codes = {make_wedding(c, title=f"W{i}").event_code for i, c in enumerate(couples)}
        self.assertEqual(len(codes), 5)

    def test_regenerating_replaces_the_code(self):
        wedding = make_wedding(make_user("ana@example.com"))
        old = wedding.event_code
        new = wedding.regenerate_event_code()
        self.assertNotEqual(old, new)
        wedding.refresh_from_db()
        self.assertEqual(wedding.event_code, new)


class WeddingCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.couple = make_user("ana@example.com", full_name="Ana Dela Cruz")

    def setUp(self):
        self.client.force_login(self.couple)

    def test_full_crud_flow(self):
        # Create
        response = self.client.post(reverse("weddings:create"), {
            "title": "  Ana   & Marco  ", "wedding_date": "2027-02-14", "venue": "  ", "base_currency": "USD",
        })
        wedding = Wedding.objects.get()
        self.assertRedirects(response, reverse("weddings:detail", args=[wedding.pk]))
        self.assertEqual(wedding.title, "Ana & Marco")
        self.assertIsNone(wedding.venue)
        self.assertEqual(wedding.base_currency, "USD")
        self.assertEqual(wedding.status, "PLANNING")
        membership = WeddingMember.objects.get()
        self.assertEqual((membership.user, membership.member_role), (self.couple, "COUPLE"))
        self.assertIn(wedding.event_code, message_texts(response)[0])

        # Read
        response = self.client.get(reverse("weddings:detail", args=[wedding.pk]))
        self.assertContains(response, "Ana &amp; Marco")
        self.assertContains(response, wedding.event_code)
        self.assertContains(response, "Ana Dela Cruz")

        # Update (base_currency is ignored even if posted)
        response = self.client.post(reverse("weddings:edit", args=[wedding.pk]), {
            "title": "Ana & Marco's Wedding", "wedding_date": "2027-03-01", "venue": "Manila Cathedral",
            "status": "COMPLETED", "base_currency": "EUR",
        })
        self.assertRedirects(response, reverse("weddings:detail", args=[wedding.pk]))
        wedding.refresh_from_db()
        self.assertEqual(
            (wedding.title, wedding.wedding_date, wedding.venue, wedding.status, wedding.base_currency),
            ("Ana & Marco's Wedding", datetime.date(2027, 3, 1), "Manila Cathedral", "COMPLETED", "USD"),
        )

        # Delete: GET only asks, POST deletes
        response = self.client.get(reverse("weddings:delete", args=[wedding.pk]))
        self.assertContains(response, "Delete Ana &amp; Marco&#x27;s Wedding?")
        self.assertTrue(Wedding.objects.filter(pk=wedding.pk).exists())
        response = self.client.post(reverse("weddings:delete", args=[wedding.pk]))
        self.assertRedirects(response, reverse("dashboards:home"), fetch_redirect_response=False)
        self.assertFalse(Wedding.objects.exists())
        self.assertFalse(WeddingMember.objects.exists())

    def test_create_validation(self):
        response = self.client.post(reverse("weddings:create"), {
            "title": "   ", "wedding_date": "not-a-date", "venue": "x" * 256, "base_currency": "XYZ",
        })
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.errors["title"], ["Enter a name for your wedding."])
        self.assertEqual(form.errors["wedding_date"], ["Enter a real date, like 14 February 2027."])
        self.assertEqual(form.errors["venue"], ["Use 255 characters or fewer."])
        self.assertEqual(form.errors["base_currency"], ["Choose one of the listed currencies."])
        self.assertFalse(Wedding.objects.exists())

    def test_title_max_length(self):
        response = self.client.post(reverse("weddings:create"), {
            "title": "x" * 151, "wedding_date": "2027-02-14", "base_currency": "PHP",
        })
        self.assertEqual(response.context["form"].errors["title"], ["Use 150 characters or fewer."])

    def test_edit_rejects_an_unknown_status(self):
        wedding = make_wedding(self.couple)
        response = self.client.post(reverse("weddings:edit", args=[wedding.pk]), {
            "title": "X", "wedding_date": "2027-02-14", "status": "POSTPONED",
        })
        self.assertEqual(response.context["form"].errors["status"], ["Choose Planning, Completed or Cancelled."])

    def test_couple_cannot_create_a_second_wedding(self):
        wedding = make_wedding(self.couple)
        response = self.client.post(reverse("weddings:create"), {
            "title": "Second", "wedding_date": "2027-02-14", "base_currency": "PHP",
        })
        self.assertRedirects(response, reverse("weddings:detail", args=[wedding.pk]))
        self.assertIn("A couple account can plan one wedding only", message_texts(response)[0])
        self.assertEqual(Wedding.objects.count(), 1)

    def test_regenerate_code_is_post_only_and_old_code_stops_working(self):
        wedding = make_wedding(self.couple)
        old = wedding.event_code
        url = reverse("weddings:event_code_regenerate", args=[wedding.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        wedding.refresh_from_db()
        self.assertNotEqual(wedding.event_code, old)

        coordinator = make_user("carla@example.com", Role.COORDINATOR)
        self.client.force_login(coordinator)
        response = self.client.post(reverse("weddings:join"), {"event_code": old})
        self.assertIn("No wedding uses this code", response.context["form"].errors["event_code"][0])
        self.client.post(reverse("weddings:join"), {"event_code": wedding.event_code})
        self.assertTrue(WeddingMember.objects.filter(user=coordinator, wedding=wedding).exists())


class JoinWeddingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.couple = make_user("ana@example.com", full_name="Ana Dela Cruz")
        cls.partner = make_user("marco@example.com", full_name="Marco Reyes")
        cls.coordinator = make_user("carla@example.com", Role.COORDINATOR, "Carla Santos")
        cls.wedding = make_wedding(cls.couple)

    def join(self, user, code):
        self.client.force_login(user)
        return self.client.post(reverse("weddings:join"), {"event_code": code})

    def spaced_lowercase(self, code):
        return f"  {code[:4].lower()} {code[4:].lower()} "

    def test_partner_joins_with_any_case_and_spaces(self):
        response = self.join(self.partner, self.spaced_lowercase(self.wedding.event_code))
        self.assertRedirects(response, reverse("weddings:detail", args=[self.wedding.pk]))
        self.assertEqual(
            WeddingMember.objects.get(user=self.partner).member_role, MemberRole.COUPLE
        )

    def test_coordinator_joins_many_weddings(self):
        second = make_wedding(make_user("bea@example.com"), title="Bea & Leo")
        self.join(self.coordinator, self.wedding.event_code)
        self.join(self.coordinator, second.event_code)
        memberships = WeddingMember.objects.filter(user=self.coordinator)
        self.assertEqual(memberships.count(), 2)
        self.assertEqual({m.member_role for m in memberships}, {"COORDINATOR"})

    def test_joining_twice_is_rejected(self):
        self.join(self.coordinator, self.wedding.event_code)
        response = self.join(self.coordinator, self.wedding.event_code)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["event_code"], [f"You're already a member of {self.wedding.title}."]
        )
        self.assertEqual(WeddingMember.objects.filter(user=self.coordinator).count(), 1)

    def test_couple_already_in_a_wedding_cannot_join_another(self):
        other = make_wedding(make_user("bea@example.com"), title="Bea & Leo")
        response = self.join(self.couple, other.event_code)
        self.assertIn("one wedding only", response.context["form"].errors["event_code"][0])
        self.assertFalse(WeddingMember.objects.filter(wedding=other, user=self.couple).exists())

    def test_invalid_and_unknown_codes(self):
        cases = {
            "": "Enter the event code the couple shared with you.",
            "ABC": "Event codes have 8 letters and numbers",
            "ABCDEFG0": "Event codes have 8 letters and numbers",
            "ZZZZZZZZ": "No wedding uses this code",
        }
        for code, error in cases.items():
            with self.subTest(code=code):
                response = self.join(self.coordinator, code)
                self.assertEqual(response.status_code, 200)
                self.assertIn(error, response.context["form"].errors["event_code"][0])
        self.assertFalse(WeddingMember.objects.filter(user=self.coordinator).exists())

    def test_vendors_and_admins_cannot_join_with_a_code(self):
        for role in (Role.VENDOR, Role.ADMIN):
            user = make_user(f"{role.lower()}@example.com", role)
            with self.subTest(role=role):
                self.assertEqual(self.join(user, self.wedding.event_code).status_code, 403)
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse("weddings:join")).status_code, 403)
        self.assertEqual(WeddingMember.objects.count(), 1)


class WeddingPermissionTests(TestCase):
    """Every wedding view as anonymous, non-member, couple, coordinator, vendor and admin."""

    @classmethod
    def setUpTestData(cls):
        cls.couple = make_user("ana@example.com", full_name="Ana Dela Cruz")
        cls.coordinator = make_user("carla@example.com", Role.COORDINATOR, "Carla Santos")
        cls.other_coordinator = make_user("dino@example.com", Role.COORDINATOR, "Dino Cruz")
        cls.outsider = make_user("bea@example.com", full_name="Bea Lim")
        cls.vendor = make_user("vince@example.com", Role.VENDOR)
        cls.admin = make_user("admin@example.com", Role.ADMIN)
        cls.wedding = make_wedding(cls.couple)
        cls.coordinator_member = WeddingMember.objects.create(
            wedding=cls.wedding, user=cls.coordinator, member_role=MemberRole.COORDINATOR
        )
        WeddingMember.objects.create(wedding=cls.wedding, user=cls.other_coordinator, member_role=MemberRole.COORDINATOR)

    def urls(self):
        pk = self.wedding.pk
        return {
            "detail": reverse("weddings:detail", args=[pk]),
            "edit": reverse("weddings:edit", args=[pk]),
            "delete": reverse("weddings:delete", args=[pk]),
            "regenerate": reverse("weddings:event_code_regenerate", args=[pk]),
            "remove": reverse("weddings:member_remove", args=[pk, self.coordinator_member.pk]),
            "leave": reverse("weddings:leave", args=[pk]),
        }

    def test_anonymous_visitors_go_to_login(self):
        for name, url in list(self.urls().items()) + [("create", reverse("weddings:create")), ("join", reverse("weddings:join"))]:
            with self.subTest(view=name):
                self.assertRedirects(self.client.post(url), f"{reverse('accounts:login')}?next={url}")

    def test_non_members_vendors_and_admins_get_404_for_wedding_pages(self):
        for user in (self.outsider, self.vendor, self.admin):
            self.client.force_login(user)
            for name, url in self.urls().items():
                with self.subTest(user=user.email, view=name):
                    self.assertEqual(self.client.get(url).status_code, 404)
                    self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(Wedding.objects.filter(pk=self.wedding.pk).exists())

    def test_unknown_wedding_is_404(self):
        self.client.force_login(self.couple)
        self.assertEqual(self.client.get(reverse("weddings:detail", args=[999999])).status_code, 404)

    def test_only_couples_can_create(self):
        for user in (self.coordinator, self.vendor, self.admin):
            self.client.force_login(user)
            with self.subTest(role=user.role):
                self.assertEqual(self.client.get(reverse("weddings:create")).status_code, 403)
                response = self.client.post(reverse("weddings:create"), {
                    "title": "X", "wedding_date": "2027-02-14", "base_currency": "PHP",
                })
                self.assertEqual(response.status_code, 403)
        self.assertEqual(Wedding.objects.count(), 1)

    def test_coordinator_can_view_but_not_manage(self):
        self.client.force_login(self.coordinator)
        urls = self.urls()
        response = self.client.get(urls["detail"])
        self.assertContains(response, "Ana Dela Cruz")
        self.assertNotContains(response, self.wedding.event_code)
        self.assertNotContains(response, urls["edit"])
        for name in ("edit", "delete", "regenerate", "remove"):
            with self.subTest(view=name):
                self.assertEqual(self.client.post(urls[name], {"title": "Hijacked"}).status_code, 403)
        self.wedding.refresh_from_db()
        self.assertNotEqual(self.wedding.title, "Hijacked")
        self.assertEqual(WeddingMember.objects.filter(wedding=self.wedding).count(), 3)

    def test_couple_cannot_leave_and_cannot_remove_the_couple(self):
        self.client.force_login(self.couple)
        self.assertEqual(self.client.post(self.urls()["leave"]).status_code, 403)
        couple_member = WeddingMember.objects.get(user=self.couple)
        url = reverse("weddings:member_remove", args=[self.wedding.pk, couple_member.pk])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_couple_cannot_remove_a_member_of_another_wedding(self):
        other = make_wedding(self.outsider, title="Bea & Leo")
        foreign = WeddingMember.objects.create(wedding=other, user=self.coordinator, member_role=MemberRole.COORDINATOR)
        self.client.force_login(self.couple)
        url = reverse("weddings:member_remove", args=[self.wedding.pk, foreign.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(WeddingMember.objects.filter(pk=foreign.pk).exists())

    def test_couple_removes_a_coordinator_after_confirming(self):
        self.client.force_login(self.couple)
        url = self.urls()["remove"]
        self.assertContains(self.client.get(url), "Remove Carla Santos?")
        self.assertTrue(WeddingMember.objects.filter(pk=self.coordinator_member.pk).exists())
        response = self.client.post(url)
        self.assertRedirects(response, self.urls()["detail"])
        self.assertFalse(WeddingMember.objects.filter(pk=self.coordinator_member.pk).exists())
        self.client.force_login(self.coordinator)
        self.assertEqual(self.client.get(self.urls()["detail"]).status_code, 404)

    def test_coordinator_leaves_after_confirming(self):
        self.client.force_login(self.coordinator)
        url = self.urls()["leave"]
        self.assertContains(self.client.get(url), "Leave Ana &amp; Marco&#x27;s Wedding?")
        response = self.client.post(url)
        self.assertRedirects(response, reverse("dashboards:home"), fetch_redirect_response=False)
        self.assertFalse(WeddingMember.objects.filter(user=self.coordinator).exists())

    def test_wedding_pages_are_not_cached(self):
        self.client.force_login(self.couple)
        self.assertIn("no-store", self.client.get(self.urls()["detail"])["Cache-Control"])


class WeddingDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.couple = make_user("ana@example.com", full_name="Ana Dela Cruz")
        cls.partner = make_user("marco@example.com", full_name="Marco Reyes")
        cls.coordinator = make_user("carla@example.com", Role.COORDINATOR)

    def test_couple_without_a_wedding_sees_create_and_join(self):
        self.client.force_login(self.couple)
        response = self.client.get(reverse("dashboards:couple"))
        self.assertContains(response, "Create your wedding")
        self.assertContains(response, "Join with an event code")
        self.assertContains(response, reverse("weddings:create"))

    def test_couple_with_a_wedding_sees_its_card_and_code(self):
        wedding = make_wedding(self.couple, venue="Manila Cathedral")
        self.client.force_login(self.couple)
        response = self.client.get(reverse("dashboards:couple"))
        self.assertContains(response, escape(wedding.title))
        self.assertContains(response, "Manila Cathedral")
        self.assertContains(response, wedding.event_code)
        self.assertContains(response, "data-copy=")
        self.assertContains(response, reverse("weddings:detail", args=[wedding.pk]))
        self.assertNotContains(response, "Join with an event code")

    def test_coordinator_sees_join_form_and_weddings_with_couple_names(self):
        wedding = make_wedding(self.couple)
        WeddingMember.objects.create(wedding=wedding, user=self.partner, member_role=MemberRole.COUPLE)
        WeddingMember.objects.create(wedding=wedding, user=self.coordinator, member_role=MemberRole.COORDINATOR)
        make_wedding(make_user("bea@example.com"), title="Not mine")
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("dashboards:coordinator"))
        self.assertContains(response, "Join a wedding")
        self.assertContains(response, "Ana Dela Cruz &amp; Marco Reyes")
        self.assertContains(response, reverse("weddings:detail", args=[wedding.pk]))
        self.assertNotContains(response, "Not mine")

    def test_vendor_dashboard_is_unchanged(self):
        self.client.force_login(make_user("vince@example.com", Role.VENDOR))
        response = self.client.get(reverse("dashboards:vendor"))
        self.assertNotContains(response, "Join a wedding")
        self.assertNotContains(response, reverse("weddings:join"))
