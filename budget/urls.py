from django.urls import path

from . import views

app_name = "budget"

# Included under weddings/<int:wedding_id>/budget/ (config/urls.py).
urlpatterns = [
    path("", views.overview, name="overview"),
    path("categories/new/", views.category_create, name="category_create"),
    path("categories/<int:category_id>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:category_id>/toggle-active/", views.category_toggle_active, name="category_toggle_active"),
    path("categories/<int:category_id>/delete/", views.category_delete, name="category_delete"),
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/new/", views.expense_create, name="expense_create"),
    path("expenses/<int:expense_id>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:expense_id>/delete/", views.expense_delete, name="expense_delete"),
]
