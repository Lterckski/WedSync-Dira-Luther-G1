from django.urls import path

from . import views

app_name = "adminpanel"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:user_id>/", views.user_edit, name="user_edit"),
    path("users/<int:user_id>/toggle-active/", views.user_toggle_active, name="user_toggle_active"),
    path("users/<int:user_id>/password/", views.user_set_password, name="user_set_password"),
]
