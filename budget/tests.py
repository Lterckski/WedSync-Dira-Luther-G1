import datetime
from decimal import Decimal

from django.db import DataError, IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Role
from weddings.models import MemberRole, Wedding, WeddingMember
from weddings.tests import columns, constraints, make_user, make_wedding, message_texts, raw

from .models import BudgetCategory, Expense

TODAY = datetime.date.today()


class BudgetFixtureMixin:
    """A wedding with a couple, a coordinator, a catering category and one expense recorded by the couple."""

    @classmethod
    def setUpTestData(cls):
        cls.couple = make_user("ana@example.com", full_name="Ana Dela Cruz")
        cls.coordinator = make_user("carla@example.com", Role.COORDINATOR, "Carla Santos")
        cls.wedding = make_wedding(cls.couple)
        WeddingMember.objects.create(wedding=cls.wedding, user=cls.coordinator, member_role=MemberRole.COORDINATOR)
        cls.catering = BudgetCategory.objects.create(wedding=cls.wedding, name="Catering", allocated_amount=Decimal("50000.00"))
        cls.couple_expense = Expense.objects.create(
            category=cls.catering, recorded_by=cls.couple, description="Tasting", amount=Decimal("2000.00"),
            expense_date=TODAY,
        )

    def url(self, name, *args):
        return reverse(f"budget:{name}", args=[self.wedding.pk, *args])


class BudgetTablesMatchSpecTests(TestCase):
    """SDD 4.4 — Tables: budget_categories and expenses."""

    def numeric(self, table, column):
        return raw(
            "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s", [table, column],
        )[0]

    def test_budget_categories_columns(self):
        cols = columns("budget_categories")
        self.assertEqual(
            sorted(cols), sorted(["category_id", "wedding_id", "name", "allocated_amount", "is_active", "created_at"])
        )
        self.assertEqual(cols["category_id"][0], "integer")
        self.assertEqual(cols["wedding_id"][:1] + cols["wedding_id"][2:3], ("integer", "NO"))
        self.assertEqual(cols["name"][:3], ("character varying", 100, "NO"))
        self.assertEqual(cols["allocated_amount"][0], "numeric")
        self.assertEqual(self.numeric("budget_categories", "allocated_amount"), (12, 2))
        self.assertEqual(cols["is_active"][0], "boolean")
        self.assertEqual(cols["is_active"][3], "true")
        self.assertEqual(cols["created_at"][0], "timestamp without time zone")
        self.assertIsNotNone(cols["created_at"][3])

    def test_expenses_columns(self):
        cols = columns("expenses")
        self.assertEqual(
            sorted(cols),
            sorted(["expense_id", "category_id", "recorded_by", "description", "amount", "expense_date", "created_at"]),
        )
        self.assertEqual(cols["recorded_by"][:1] + cols["recorded_by"][2:3], ("integer", "NO"))
        self.assertEqual(cols["description"][:3], ("character varying", 255, "NO"))
        self.assertEqual(self.numeric("expenses", "amount"), (12, 2))
        self.assertEqual(cols["expense_date"][0], "date")
        self.assertIn("CURRENT_DATE", cols["expense_date"][3])
        self.assertEqual(cols["created_at"][0], "timestamp without time zone")

    def test_named_constraints(self):
        categories = constraints("budget_categories")
        self.assertEqual(categories["budget_categories_allocated_amount_check"], ("c", "CHECK ((allocated_amount >= (0)::numeric))"))
        self.assertEqual(categories["budget_categories_wedding_id_name_key"], ("u", "UNIQUE (wedding_id, name)"))
        self.assertEqual(constraints("expenses")["expenses_amount_check"], ("c", "CHECK ((amount > (0)::numeric))"))

    def test_foreign_keys_restrict_in_postgresql(self):
        expected = {
            ("budget_categories", "budget_categories_wedding_id_fkey"): "REFERENCES weddings(wedding_id) ON DELETE RESTRICT",
            ("expenses", "expenses_category_id_fkey"): "REFERENCES budget_categories(category_id) ON DELETE RESTRICT",
            ("expenses", "expenses_recorded_by_fkey"): "REFERENCES users(user_id) ON DELETE RESTRICT",
        }
        for (table, name), definition in expected.items():
            with self.subTest(constraint=name):
                self.assertIn(definition, constraints(table)[name][1])


class BudgetConstraintTests(BudgetFixtureMixin, TestCase):
    """The database itself rejects bad rows, even when Django is bypassed."""

    def insert_category(self, name="Flowers", amount="100.00"):
        raw(
            "INSERT INTO budget_categories (wedding_id, name, allocated_amount) VALUES (%s, %s, %s) "
            "RETURNING is_active, created_at",
            [self.wedding.pk, name, amount],
        )

    def insert_expense(self, amount="100.00"):
        return raw(
            "INSERT INTO expenses (category_id, recorded_by, description, amount) VALUES (%s, %s, 'Raw', %s) "
            "RETURNING expense_date, created_at",
            [self.catering.pk, self.couple.pk, amount],
        )[0]

    def test_database_defaults(self):
        is_active, created_at = raw(
            "INSERT INTO budget_categories (wedding_id, name, allocated_amount) VALUES (%s, 'Flowers', 0) "
            "RETURNING is_active, created_at", [self.wedding.pk],
        )[0]
        self.assertTrue(is_active)
        self.assertIsNotNone(created_at)
        expense_date, created_at = self.insert_expense()
        self.assertEqual(expense_date, TODAY)
        self.assertIsNotNone(created_at)

    def test_allocated_amount_cannot_be_negative(self):
        self.insert_category(amount="0.00")  # zero is allowed (BR-05)
        with self.assertRaises(IntegrityError):
            self.insert_category(name="Cake", amount="-0.01")

    def test_expense_amount_must_be_positive(self):
        for amount in ("0.00", "-5.00"):
            with self.subTest(amount=amount), self.assertRaises(IntegrityError), transaction.atomic():
                self.insert_expense(amount)

    def test_numeric_12_2_limit(self):
        self.insert_expense("9999999999.99")
        with self.assertRaises(DataError):
            self.insert_expense("10000000000.00")

    def test_category_name_unique_per_wedding_regardless_of_case(self):
        for name in ("Catering", "CATERING"):
            with self.subTest(name=name), self.assertRaises(IntegrityError), transaction.atomic():
                self.insert_category(name=name)
        other = make_wedding(make_user("bea@example.com"), title="Bea & Leo")
        BudgetCategory.objects.create(wedding=other, name="Catering", allocated_amount=0)  # fine in another wedding

    def test_wedding_with_categories_cannot_be_deleted_in_sql(self):
        with self.assertRaises(IntegrityError):
            raw("DELETE FROM weddings WHERE wedding_id = %s", [self.wedding.pk])

    def test_category_with_expenses_cannot_be_deleted_in_sql(self):
        with self.assertRaises(IntegrityError):
            raw("DELETE FROM budget_categories WHERE category_id = %s", [self.catering.pk])

    def test_user_who_recorded_expenses_cannot_be_deleted_in_sql(self):
        with self.assertRaises(IntegrityError):
            raw("DELETE FROM users WHERE user_id = %s", [self.couple.pk])


class BudgetPermissionTests(BudgetFixtureMixin, TestCase):
    """Every budget view as anonymous, non-member, couple, coordinator, vendor and admin; GET and POST."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.outsider = make_user("bea@example.com", full_name="Bea Lim")
        cls.vendor = make_user("vince@example.com", Role.VENDOR)
        cls.admin = make_user("admin@example.com", Role.ADMIN)
        cls.coordinator_expense = Expense.objects.create(
            category=cls.catering, recorded_by=cls.coordinator, description="Florist deposit",
            amount=Decimal("500.00"), expense_date=TODAY,
        )

    def all_urls(self):
        return {
            "overview": self.url("overview"),
            "category_create": self.url("category_create"),
            "category_edit": self.url("category_edit", self.catering.pk),
            "category_toggle_active": self.url("category_toggle_active", self.catering.pk),
            "category_delete": self.url("category_delete", self.catering.pk),
            "expense_list": self.url("expense_list"),
            "expense_create": self.url("expense_create"),
            "expense_edit": self.url("expense_edit", self.couple_expense.pk),
            "expense_delete": self.url("expense_delete", self.couple_expense.pk),
        }

    def assert_nothing_changed(self):
        self.catering.refresh_from_db()
        self.assertEqual((self.catering.name, self.catering.is_active), ("Catering", True))
        self.assertEqual(Expense.objects.count(), 2)
        self.assertEqual(BudgetCategory.objects.count(), 1)

    def test_anonymous_visitors_go_to_login(self):
        for name, url in self.all_urls().items():
            with self.subTest(view=name):
                self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")
                self.assertRedirects(self.client.post(url), f"{reverse('accounts:login')}?next={url}")
        self.assert_nothing_changed()

    def test_non_member_gets_404(self):
        self.client.force_login(self.outsider)
        for name, url in self.all_urls().items():
            with self.subTest(view=name):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, {"name": "X", "allocated_amount": "1"}).status_code, 404)
        self.assert_nothing_changed()

    def test_vendors_and_admins_get_403_even_as_members(self):
        # A vendor attached to the wedding (as contracts will do later) still can't see the budget.
        WeddingMember.objects.create(wedding=self.wedding, user=self.vendor, member_role=MemberRole.VENDOR)
        for user in (self.vendor, self.admin):
            self.client.force_login(user)
            for name, url in self.all_urls().items():
                with self.subTest(role=user.role, view=name):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertContains(response, "This page belongs to another role", status_code=403)
                    self.assertEqual(self.client.post(url, {"name": "X"}).status_code, 403)
        self.assert_nothing_changed()

    def test_couple_can_open_every_page(self):
        self.client.force_login(self.couple)
        for name, url in self.all_urls().items():
            if name == "category_toggle_active":
                continue  # POST-only
            with self.subTest(view=name):
                expected = 302 if name == "category_delete" else 200  # catering has expenses → redirected with a message
                self.assertEqual(self.client.get(url).status_code, expected)

    def test_coordinator_can_view_and_add_but_not_manage_categories(self):
        self.client.force_login(self.coordinator)
        for name in ("overview", "expense_list", "category_create", "expense_create"):
            with self.subTest(view=name):
                self.assertEqual(self.client.get(self.all_urls()[name]).status_code, 200)
        for name in ("category_edit", "category_toggle_active", "category_delete"):
            with self.subTest(view=name):
                self.assertEqual(self.client.get(self.all_urls()[name]).status_code, 403)
                response = self.client.post(self.all_urls()[name], {"name": "Hijacked", "allocated_amount": "1"})
                self.assertEqual(response.status_code, 403)
        self.assert_nothing_changed()

    def test_coordinator_cannot_edit_or_delete_someone_elses_expense(self):
        self.client.force_login(self.coordinator)
        edit = self.url("expense_edit", self.couple_expense.pk)
        delete = self.url("expense_delete", self.couple_expense.pk)
        self.assertEqual(self.client.get(edit).status_code, 403)
        self.assertEqual(self.client.post(edit, {
            "category": self.catering.pk, "description": "Changed", "amount": "1", "expense_date": TODAY.isoformat(),
        }).status_code, 403)
        self.assertEqual(self.client.get(delete).status_code, 403)
        self.assertEqual(self.client.post(delete).status_code, 403)
        self.couple_expense.refresh_from_db()
        self.assertEqual(self.couple_expense.description, "Tasting")

    def test_coordinator_edits_and_deletes_their_own_expense(self):
        self.client.force_login(self.coordinator)
        response = self.client.post(self.url("expense_edit", self.coordinator_expense.pk), {
            "category": self.catering.pk, "description": "Florist deposit (paid)", "amount": "600",
            "expense_date": TODAY.isoformat(),
        })
        self.assertRedirects(response, self.url("expense_list"))
        self.coordinator_expense.refresh_from_db()
        self.assertEqual(self.coordinator_expense.amount, Decimal("600.00"))
        self.client.post(self.url("expense_delete", self.coordinator_expense.pk))
        self.assertFalse(Expense.objects.filter(pk=self.coordinator_expense.pk).exists())

    def test_couple_edits_the_coordinators_expense(self):
        self.client.force_login(self.couple)
        response = self.client.post(self.url("expense_edit", self.coordinator_expense.pk), {
            "category": self.catering.pk, "description": "Florist", "amount": "700", "expense_date": TODAY.isoformat(),
        })
        self.assertRedirects(response, self.url("expense_list"))
        self.coordinator_expense.refresh_from_db()
        self.assertEqual(self.coordinator_expense.recorded_by, self.coordinator)  # recorder never changes

    def test_expense_list_shows_edit_links_only_where_allowed(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(self.url("expense_list"))
        self.assertContains(response, self.url("expense_edit", self.coordinator_expense.pk))
        self.assertNotContains(response, self.url("expense_edit", self.couple_expense.pk))
        self.client.force_login(self.couple)
        response = self.client.get(self.url("expense_list"))
        self.assertContains(response, self.url("expense_edit", self.coordinator_expense.pk))
        self.assertContains(response, self.url("expense_edit", self.couple_expense.pk))

    def test_overview_hides_category_management_from_coordinators(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(self.url("overview"))
        self.assertNotContains(response, self.url("category_edit", self.catering.pk))
        self.assertNotContains(response, self.url("category_delete", self.catering.pk))

    def test_ids_from_another_wedding_are_404(self):
        other = make_wedding(self.outsider, title="Bea & Leo")
        foreign_category = BudgetCategory.objects.create(wedding=other, name="Venue", allocated_amount=1)
        foreign_expense = Expense.objects.create(
            category=foreign_category, recorded_by=self.outsider, description="X", amount=1, expense_date=TODAY,
        )
        self.client.force_login(self.couple)
        for url in (
            self.url("category_edit", foreign_category.pk),
            self.url("category_toggle_active", foreign_category.pk),
            self.url("category_delete", foreign_category.pk),
            self.url("expense_edit", foreign_expense.pk),
            self.url("expense_delete", foreign_expense.pk),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(Expense.objects.filter(pk=foreign_expense.pk).exists())

    def test_get_cannot_change_anything(self):
        self.client.force_login(self.couple)
        self.assertEqual(self.client.get(self.url("category_toggle_active", self.catering.pk)).status_code, 405)
        self.client.get(self.url("expense_delete", self.couple_expense.pk))
        self.assert_nothing_changed()

    def test_budget_pages_are_not_cached(self):
        self.client.force_login(self.couple)
        self.assertIn("no-store", self.client.get(self.url("overview"))["Cache-Control"])


class CategoryValidationTests(BudgetFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.couple)

    def create(self, **data):
        data.setdefault("name", "Photography")
        data.setdefault("allocated_amount", "30000")
        return self.client.post(self.url("category_create"), data)

    def errors(self, response, field):
        return response.context["form"].errors.get(field)

    def test_name_rules(self):
        cases = {
            "": "Enter a category name.",
            "    ": "Enter a category name.",
            "x" * 101: "Use 100 characters or fewer.",
            "catering": "This wedding already has a category called Catering.",
            "  CATERING ": "This wedding already has a category called Catering.",
        }
        for name, error in cases.items():
            with self.subTest(name=name):
                response = self.create(name=name)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.errors(response, "name"), [error])
        self.assertEqual(BudgetCategory.objects.count(), 1)

    def test_name_is_trimmed(self):
        self.create(name="   Photo    and   Video  ")
        self.assertTrue(BudgetCategory.objects.filter(name="Photo and Video").exists())

    def test_allocated_amount_rules(self):
        cases = {
            "": "Enter how much you're setting aside for this category, or 0.",
            "-1": "The allocated amount can't be negative. Use 0 or more.",
            "10.555": "Use at most 2 decimal places, like 1500.50.",
            "10000000000": "Enter an amount up to 9,999,999,999.99.",
            "abc": "Enter an amount in numbers, like 12500 or 12,500.50.",
        }
        for amount, error in cases.items():
            with self.subTest(amount=amount):
                self.assertEqual(self.errors(self.create(allocated_amount=amount), "allocated_amount"), [error])
        self.assertEqual(BudgetCategory.objects.count(), 1)

    def test_valid_amounts_including_zero_commas_and_the_maximum(self):
        for name, amount, stored in (
            ("Zero", "0", "0.00"), ("Commas", "12,500.50", "12500.50"), ("Max", "9999999999.99", "9999999999.99"),
        ):
            with self.subTest(amount=amount):
                response = self.create(name=name, allocated_amount=amount)
                self.assertRedirects(response, self.url("overview"))
                self.assertEqual(BudgetCategory.objects.get(name=name).allocated_amount, Decimal(stored))

    def test_coordinator_can_create_a_category(self):
        self.client.force_login(self.coordinator)
        self.assertRedirects(self.create(), self.url("overview"))
        self.assertTrue(BudgetCategory.objects.filter(name="Photography", wedding=self.wedding).exists())

    def test_same_name_in_another_wedding_is_fine(self):
        other_couple = make_user("bea@example.com")
        other = make_wedding(other_couple, title="Bea & Leo")
        self.client.force_login(other_couple)
        response = self.client.post(
            reverse("budget:category_create", args=[other.pk]), {"name": "Catering", "allocated_amount": "1"}
        )
        self.assertRedirects(response, reverse("budget:overview", args=[other.pk]))

    def test_edit_keeps_its_own_name_and_rejects_another_categorys(self):
        BudgetCategory.objects.create(wedding=self.wedding, name="Venue", allocated_amount=1)
        url = self.url("category_edit", self.catering.pk)
        self.assertRedirects(self.client.post(url, {"name": "catering", "allocated_amount": "60000"}), self.url("overview"))
        self.catering.refresh_from_db()
        self.assertEqual((self.catering.name, self.catering.allocated_amount), ("catering", Decimal("60000.00")))
        response = self.client.post(url, {"name": "VENUE", "allocated_amount": "1"})
        self.assertEqual(self.errors(response, "name"), ["This wedding already has a category called Venue."])

    def test_deactivate_and_reactivate(self):
        url = self.url("category_toggle_active", self.catering.pk)
        response = self.client.post(url)
        self.assertRedirects(response, self.url("overview"))
        self.catering.refresh_from_db()
        self.assertFalse(self.catering.is_active)
        self.assertIn("was deactivated", message_texts(response)[0])
        self.client.post(url)
        self.catering.refresh_from_db()
        self.assertTrue(self.catering.is_active)

    def test_category_with_expenses_cannot_be_deleted(self):
        url = self.url("category_delete", self.catering.pk)
        for method in (self.client.get, self.client.post):
            response = method(url)
            self.assertRedirects(response, self.url("overview"))
            self.assertIn("Deactivate it instead", message_texts(response)[0])
        self.assertTrue(BudgetCategory.objects.filter(pk=self.catering.pk).exists())

    def test_empty_category_is_deleted_after_confirming(self):
        cake = BudgetCategory.objects.create(wedding=self.wedding, name="Cake", allocated_amount=Decimal("5000"))
        url = self.url("category_delete", cake.pk)
        self.assertContains(self.client.get(url), "Delete Cake?")
        self.assertTrue(BudgetCategory.objects.filter(pk=cake.pk).exists())
        self.assertRedirects(self.client.post(url), self.url("overview"))
        self.assertFalse(BudgetCategory.objects.filter(pk=cake.pk).exists())

    def test_wedding_with_categories_cannot_be_deleted(self):
        response = self.client.post(reverse("weddings:delete", args=[self.wedding.pk]))
        self.assertRedirects(response, reverse("weddings:detail", args=[self.wedding.pk]))
        self.assertIn("Change its status to Cancelled instead", message_texts(response)[0])
        self.assertTrue(Wedding.objects.filter(pk=self.wedding.pk).exists())


class ExpenseValidationTests(BudgetFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.couple)

    def create(self, **data):
        data.setdefault("category", self.catering.pk)
        data.setdefault("description", "Deposit")
        data.setdefault("amount", "1000")
        data.setdefault("expense_date", TODAY.isoformat())
        return self.client.post(self.url("expense_create"), data)

    def errors(self, response, field):
        return response.context["form"].errors.get(field)

    def test_description_rules(self):
        self.assertEqual(self.errors(self.create(description=""), "description"), ["Describe what the money was spent on."])
        self.assertEqual(self.errors(self.create(description="   "), "description"), ["Describe what the money was spent on."])
        self.assertEqual(self.errors(self.create(description="x" * 256), "description"), ["Use 255 characters or fewer."])
        self.create(description="   Final   payment  ")
        self.assertTrue(Expense.objects.filter(description="Final payment").exists())

    def test_amount_rules(self):
        cases = {
            "": "Enter the amount spent.",
            "0": "Enter an amount greater than 0.",
            "-50": "Enter an amount greater than 0.",
            "1.005": "Use at most 2 decimal places, like 1500.50.",
            "10000000000": "Enter an amount up to 9,999,999,999.99.",
        }
        for amount, error in cases.items():
            with self.subTest(amount=amount):
                self.assertEqual(self.errors(self.create(amount=amount), "amount"), [error])
        self.assertEqual(Expense.objects.count(), 1)

    def test_date_rules(self):
        tomorrow = (TODAY + datetime.timedelta(days=1)).isoformat()
        self.assertIn("can't be in the future", self.errors(self.create(expense_date=tomorrow), "expense_date")[0])
        self.assertEqual(self.errors(self.create(expense_date="2027-02-30"), "expense_date"), ["Enter a real date, like 14 February 2027."])
        self.assertEqual(self.errors(self.create(expense_date=""), "expense_date"), ["Enter the date of the expense."])
        self.assertRedirects(self.create(expense_date="2026-01-15"), self.url("expense_list"))

    def test_date_defaults_to_today(self):
        response = self.client.get(self.url("expense_create"))
        self.assertEqual(response.context["form"].initial["expense_date"], TODAY)
        self.assertContains(response, f'value="{TODAY.isoformat()}"')

    def test_recorded_by_is_the_signed_in_user(self):
        self.client.force_login(self.coordinator)
        self.create(description="Coordinator buy", recorded_by=self.couple.pk)
        self.assertEqual(Expense.objects.get(description="Coordinator buy").recorded_by, self.coordinator)

    def test_category_choices_are_this_weddings_active_categories(self):
        inactive = BudgetCategory.objects.create(wedding=self.wedding, name="Old", allocated_amount=1, is_active=False)
        other = make_wedding(make_user("bea@example.com"), title="Bea & Leo")
        foreign = BudgetCategory.objects.create(wedding=other, name="Theirs", allocated_amount=1)
        choices = list(self.client.get(self.url("expense_create")).context["form"].fields["category"].queryset)
        self.assertEqual(choices, [self.catering])
        for category in (inactive, foreign):
            with self.subTest(category=category.name):
                self.assertEqual(
                    self.errors(self.create(category=category.pk), "category"),
                    ["Choose one of this wedding's active categories."],
                )
        self.assertEqual(Expense.objects.count(), 1)

    def test_editing_keeps_an_inactive_current_category_but_cannot_switch_to_another(self):
        self.catering.is_active = False
        self.catering.save()
        old = BudgetCategory.objects.create(wedding=self.wedding, name="Old", allocated_amount=1, is_active=False)
        url = self.url("expense_edit", self.couple_expense.pk)
        choices = list(self.client.get(url).context["form"].fields["category"].queryset)
        self.assertEqual(choices, [self.catering])
        data = {"category": self.catering.pk, "description": "Tasting", "amount": "2500", "expense_date": TODAY.isoformat()}
        self.assertRedirects(self.client.post(url, data), self.url("expense_list"))
        response = self.client.post(url, {**data, "category": old.pk})
        self.assertEqual(self.errors(response, "category"), ["Choose one of this wedding's active categories."])

    def test_no_active_categories_shows_add_a_category_first(self):
        self.catering.is_active = False
        self.catering.save()
        response = self.client.get(self.url("expense_create"))
        self.assertContains(response, "Add a category first")

    def test_over_budget_expense_is_saved_with_a_warning(self):
        response = self.create(description="Balance", amount="50500")
        self.assertRedirects(response, self.url("expense_list"))
        self.assertEqual(Expense.objects.count(), 2)
        texts = message_texts(response)
        self.assertIn("Catering is now PHP 2,500.00 over budget.", texts)

    def test_within_budget_has_no_warning(self):
        texts = message_texts(self.create(amount="100"))
        self.assertFalse(any("over budget" in text for text in texts))


class BudgetOverviewTests(BudgetFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.couple)

    def test_totals_include_inactive_categories_and_count_over_budget(self):
        venue = BudgetCategory.objects.create(wedding=self.wedding, name="Venue", allocated_amount=Decimal("1000"))
        Expense.objects.create(category=venue, recorded_by=self.couple, description="X", amount=Decimal("1500"), expense_date=TODAY)
        BudgetCategory.objects.create(wedding=self.wedding, name="Old", allocated_amount=Decimal("500"), is_active=False)
        response = self.client.get(self.url("overview"))
        wedding = response.context["wedding"]
        self.assertEqual(wedding.budget_allocated, Decimal("51500.00"))
        self.assertEqual(wedding.budget_spent, Decimal("3500.00"))
        self.assertEqual(wedding.budget_remaining, Decimal("48000.00"))
        self.assertEqual(wedding.budget_over_count, 1)
        self.assertContains(response, "PHP 51,500.00")
        self.assertContains(response, "PHP 3,500.00")
        self.assertContains(response, "-PHP 500.00")
        self.assertContains(response, "Over budget")
        self.assertContains(response, "Inactive categories")
        self.assertEqual([c.name for c in response.context["inactive_categories"]], ["Old"])
        rows = {c.name: c for c in response.context["active_categories"]}
        self.assertEqual((rows["Venue"].percent_used, rows["Venue"].bar_value, rows["Venue"].is_over), (150, 100, True))
        self.assertEqual((rows["Catering"].percent_used, rows["Catering"].is_over), (4, False))

    def test_amounts_use_the_weddings_currency(self):
        Wedding.objects.filter(pk=self.wedding.pk).update(base_currency="USD")
        self.assertContains(self.client.get(self.url("overview")), "USD 50,000.00")

    def test_query_count_does_not_grow_with_categories(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.client.get(self.url("overview"))
            return len(queries)

        before = count()
        for i in range(5):
            category = BudgetCategory.objects.create(wedding=self.wedding, name=f"C{i}", allocated_amount=100)
            Expense.objects.create(category=category, recorded_by=self.couple, description="X", amount=1, expense_date=TODAY)
        self.assertEqual(count(), before)

    def test_expense_list_newest_first_filter_and_pagination(self):
        venue = BudgetCategory.objects.create(wedding=self.wedding, name="Venue", allocated_amount=1)
        for day in range(1, 26):
            Expense.objects.create(
                category=venue, recorded_by=self.couple, description=f"Venue {day}", amount=1,
                expense_date=datetime.date(2026, 1, day),
            )
        response = self.client.get(self.url("expense_list"))
        page = response.context["page"]
        self.assertEqual((page.paginator.count, len(page.object_list)), (26, 20))
        self.assertEqual(page.object_list[0], self.couple_expense)  # today's tasting is the newest
        self.assertEqual(page.object_list[1].description, "Venue 25")
        self.assertEqual(len(self.client.get(self.url("expense_list") + "?page=2").context["page"].object_list), 6)

        response = self.client.get(self.url("expense_list") + f"?category={self.catering.pk}")
        self.assertEqual(list(response.context["page"].object_list), [self.couple_expense])

        foreign = BudgetCategory.objects.create(
            wedding=make_wedding(make_user("bea@example.com"), title="B"), name="Theirs", allocated_amount=1
        )
        response = self.client.get(self.url("expense_list") + f"?category={foreign.pk}")
        self.assertIsNone(response.context["selected"])
        self.assertEqual(response.context["page"].paginator.count, 26)


class BudgetCrudFlowTests(TestCase):
    def test_create_read_update_delete(self):
        couple = make_user("ana@example.com", full_name="Ana Dela Cruz")
        wedding = make_wedding(couple)
        self.client.force_login(couple)

        def url(name, *args):
            return reverse(f"budget:{name}", args=[wedding.pk, *args])

        # Create a category and an expense
        self.assertRedirects(self.client.post(url("category_create"), {"name": "Venue", "allocated_amount": "80,000"}), url("overview"))
        venue = BudgetCategory.objects.get()
        self.assertRedirects(self.client.post(url("expense_create"), {
            "category": venue.pk, "description": "Reservation fee", "amount": "20000", "expense_date": TODAY.isoformat(),
        }), url("expense_list"))
        expense = Expense.objects.get()
        self.assertEqual((expense.recorded_by, expense.amount), (couple, Decimal("20000.00")))

        # Read
        response = self.client.get(url("overview"))
        self.assertContains(response, "PHP 80,000.00")
        self.assertContains(response, "PHP 60,000.00")
        self.assertContains(response, "25%")
        self.assertContains(self.client.get(url("expense_list")), "Reservation fee")

        # Update
        self.assertRedirects(self.client.post(url("category_edit", venue.pk), {"name": "Reception venue", "allocated_amount": "90000"}), url("overview"))
        self.assertRedirects(self.client.post(url("expense_edit", expense.pk), {
            "category": venue.pk, "description": "Reservation fee (paid)", "amount": "25000.50", "expense_date": TODAY.isoformat(),
        }), url("expense_list"))
        venue.refresh_from_db()
        expense.refresh_from_db()
        self.assertEqual((venue.name, venue.allocated_amount), ("Reception venue", Decimal("90000.00")))
        self.assertEqual((expense.description, expense.amount), ("Reservation fee (paid)", Decimal("25000.50")))

        # Delete (expense first; the category can only go once it's empty)
        self.assertContains(self.client.get(url("expense_delete", expense.pk)), "Delete this expense?")
        self.assertRedirects(self.client.post(url("expense_delete", expense.pk)), url("expense_list"))
        self.assertRedirects(self.client.post(url("category_delete", venue.pk)), url("overview"))
        self.assertFalse(Expense.objects.exists())
        self.assertFalse(BudgetCategory.objects.exists())


class BudgetDashboardAndNavigationTests(BudgetFixtureMixin, TestCase):
    def test_couple_dashboard_shows_budget_summary_and_links(self):
        self.client.force_login(self.couple)
        response = self.client.get(reverse("dashboards:couple"))
        self.assertContains(response, "PHP 50,000.00")
        self.assertContains(response, "PHP 48,000.00")
        for name in ("overview", "expense_create", "category_create"):
            self.assertContains(response, self.url(name))
        self.assertContains(response, ">Budget</a>")

    def test_coordinator_dashboard_shows_each_weddings_budget(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("dashboards:coordinator"))
        self.assertContains(response, "PHP 50,000.00")
        self.assertContains(response, "PHP 2,000.00")
        self.assertContains(response, self.url("overview"))

    def test_coordinator_sees_budget_nav_inside_a_wedding(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("weddings:detail", args=[self.wedding.pk]))
        self.assertContains(response, f'href="{self.url("overview")}"')

    def test_vendor_and_admin_have_no_budget_links(self):
        for role in (Role.VENDOR, Role.ADMIN):
            user = make_user(f"{role.lower()}@example.com", role)
            self.client.force_login(user)
            home = reverse("dashboards:vendor") if role == Role.VENDOR else reverse("adminpanel:overview")
            response = self.client.get(home)
            with self.subTest(role=role):
                self.assertNotContains(response, "/budget/")
                self.assertNotContains(response, ">Budget</a>")
