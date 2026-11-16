from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User

DASHBOARDS = {
    Role.COUPLE: "dashboards:couple",
    Role.COORDINATOR: "dashboards:coordinator",
    Role.VENDOR: "dashboards:vendor",
    Role.ADMIN: "adminpanel:overview",
}


class RoleDashboardAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {
            role: User.objects.create_user(
                email=f"{role.lower()}@example.com", password="Vows-and-Rings-2027",
                full_name=f"{role.label} Person", role=role,
            )
            for role in Role
        }

    def test_logged_out_visitors_are_sent_to_login(self):
        for url_name in list(DASHBOARDS.values()) + ["dashboards:home"]:
            url = reverse(url_name)
            self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_dashboard_home_routes_each_role(self):
        for role, url_name in DASHBOARDS.items():
            self.client.force_login(self.users[role])
            self.assertRedirects(self.client.get(reverse("dashboards:home")), reverse(url_name))

    def test_each_role_opens_only_its_own_dashboard(self):
        for role, user in self.users.items():
            self.client.force_login(user)
            for other_role, url_name in DASHBOARDS.items():
                response = self.client.get(reverse(url_name))
                expected = 200 if other_role == role else 403
                self.assertEqual(response.status_code, expected, f"{role} -> {url_name}")
                if expected == 403:
                    self.assertContains(response, "This page belongs to another role", status_code=403)

    def test_dashboards_show_role_specific_content_and_navigation(self):
        expectations = {
            Role.COUPLE: ("Couple dashboard", "My wedding", "Seating planner"),
            Role.COORDINATOR: ("Coordinator dashboard", "Weddings", "Weddings you manage"),
            Role.VENDOR: ("Vendor dashboard", "Bookings", "Your bookings"),
            Role.ADMIN: ("Admin dashboard", "Users", "Newest accounts"),
        }
        for role, texts in expectations.items():
            self.client.force_login(self.users[role])
            response = self.client.get(reverse(DASHBOARDS[role]))
            for text in texts:
                self.assertContains(response, text)

    def test_vendor_dashboard_does_not_offer_couple_tools(self):
        self.client.force_login(self.users[Role.VENDOR])
        response = self.client.get(reverse("dashboards:vendor"))
        self.assertNotContains(response, "Seating planner")
        self.assertNotContains(response, reverse("adminpanel:user_list"))

    def test_protected_pages_are_not_cached(self):
        self.client.force_login(self.users[Role.COUPLE])
        response = self.client.get(reverse("dashboards:couple"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_django_admin_site_is_not_available(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)
