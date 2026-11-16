from django.urls import include, path

# Django's built-in admin site is deliberately not routed.
urlpatterns = [
    path("", include("core.urls")),
]
