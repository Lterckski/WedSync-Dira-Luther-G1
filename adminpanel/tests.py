from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User

PASSWORD = "Vows-and-Rings-2027"


class AdminPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_admin(email="admin@example.com", password=PASSWORD, full_name="Site Admin")
        cls.couple = User.objects.create_user(email="ana@example.com", password=PASSWORD, full_name="Ana Dela Cruz")
        cls.vendor = User.objects.create_user(
            email="lens@example.com", password=PASSWORD, full_name="Lens Studio", role=Role.VENDOR
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_non_admins_are_refused(self):
        self.client.force_login(self.couple)
        urls = [
            reverse("adminpanel:overview"),
            reverse("adminpanel:user_list"),
            reverse("adminpanel:user_create"),
            reverse("adminpanel:user_edit", args=[self.vendor.pk]),
            reverse("adminpanel:user_set_password", args=[self.vendor.pk]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        response = self.client.post(reverse("adminpanel:user_toggle_active", args=[self.vendor.pk]))
        self.assertEqual(response.status_code, 403)
        self.vendor.refresh_from_db()
        self.assertTrue(self.vendor.is_active)

    def test_overview_counts_accounts(self):
        response = self.client.get(reverse("adminpanel:overview"))
        counts = response.context["counts"]
        self.assertEqual((counts["total"], counts["couple"], counts["vendor"], counts["admin"]), (3, 1, 1, 1))

    def test_user_list_search_and_filters(self):
        response = self.client.get(reverse("adminpanel:user_list"), {"q": "lens"})
        self.assertEqual([u.pk for u in response.context["page"].object_list], [self.vendor.pk])
        response = self.client.get(reverse("adminpanel:user_list"), {"role": "COUPLE"})
        self.assertEqual([u.pk for u in response.context["page"].object_list], [self.couple.pk])
        response = self.client.get(reverse("adminpanel:user_list"), {"q": "nobody"})
        self.assertContains(response, "No users match these filters")

    def test_create_account_with_any_role(self):
        response = self.client.post(reverse("adminpanel:user_create"), {
            "full_name": "Mia Reyes", "email": "mia@example.com", "phone": "", "role": "COORDINATOR",
            "password1": PASSWORD, "password2": PASSWORD,
        })
        mia = User.objects.get(email="mia@example.com")
        self.assertRedirects(response, reverse("adminpanel:user_edit", args=[mia.pk]))
        self.assertEqual(mia.role, Role.COORDINATOR)
        self.assertTrue(mia.check_password(PASSWORD))

    def test_edit_role_and_status(self):
        response = self.client.post(reverse("adminpanel:user_edit", args=[self.vendor.pk]), {
            "full_name": "Lens Studio PH", "email": "lens@example.com", "phone": "", "role": "COORDINATOR",
        })
        self.assertRedirects(response, reverse("adminpanel:user_edit", args=[self.vendor.pk]))
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.role, Role.COORDINATOR)
        self.assertFalse(self.vendor.is_active)  # unchecked box = deactivated

    def test_toggle_active_is_post_only_and_reversible(self):
        url = reverse("adminpanel:user_toggle_active", args=[self.couple.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.couple.refresh_from_db()
        self.assertFalse(self.couple.is_active)
        self.client.post(url)
        self.couple.refresh_from_db()
        self.assertTrue(self.couple.is_active)

    def test_admin_cannot_lock_themselves_out(self):
        self.client.post(reverse("adminpanel:user_toggle_active", args=[self.admin.pk]))
        self.client.post(reverse("adminpanel:user_edit", args=[self.admin.pk]), {
            "full_name": "Site Admin", "email": "admin@example.com", "phone": "", "role": "COUPLE",
        })
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.role, Role.ADMIN)

    def test_set_a_new_password(self):
        new_password = "Reception-Hall-2027"
        response = self.client.post(reverse("adminpanel:user_set_password", args=[self.couple.pk]), {
            "new_password1": new_password, "new_password2": new_password,
        })
        self.assertRedirects(response, reverse("adminpanel:user_edit", args=[self.couple.pk]))
        self.couple.refresh_from_db()
        self.assertTrue(self.couple.check_password(new_password))

    def test_unknown_user_is_404(self):
        self.assertEqual(self.client.get(reverse("adminpanel:user_edit", args=[99999])).status_code, 404)
