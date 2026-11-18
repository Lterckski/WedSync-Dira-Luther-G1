from django.urls import path

from . import views

app_name = "weddings"

urlpatterns = [
    path("new/", views.wedding_create, name="create"),
    path("join/", views.wedding_join, name="join"),
    path("<int:wedding_id>/", views.wedding_detail, name="detail"),
    path("<int:wedding_id>/edit/", views.wedding_edit, name="edit"),
    path("<int:wedding_id>/delete/", views.wedding_delete, name="delete"),
    path("<int:wedding_id>/event-code/", views.event_code_regenerate, name="event_code_regenerate"),
    path("<int:wedding_id>/leave/", views.wedding_leave, name="leave"),
    path("<int:wedding_id>/members/<int:member_id>/remove/", views.member_remove, name="member_remove"),
]
