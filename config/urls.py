from django.urls import include, path

# Django's built-in admin site is deliberately not installed or routed.
# User management lives in the adminpanel app at /manage/.
urlpatterns = [
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("dashboard/", include("dashboards.urls")),
    path("manage/", include("adminpanel.urls")),
    path("weddings/", include("weddings.urls")),
    path("weddings/<int:wedding_id>/budget/", include("budget.urls")),
]

handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"
