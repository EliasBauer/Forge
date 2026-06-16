from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_view, name="auth-login"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("me/", views.current_user_view, name="auth-me"),
    path("users/", views.users_view, name="auth-users"),
]
