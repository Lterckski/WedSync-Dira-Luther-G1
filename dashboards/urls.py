from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path("", views.home, name="home"),
    path("couple/", views.couple, name="couple"),
    path("coordinator/", views.coordinator, name="coordinator"),
    path("vendor/", views.vendor, name="vendor"),
]
