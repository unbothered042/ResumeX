from django.urls import path
from . import views
from . import admin_views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('admin/users/', admin_views.AdminUserListView.as_view(), name='admin-users'),
    path('admin/grant-plan/', admin_views.AdminGrantPlanView.as_view(), name='admin-grant-plan'),
    path('me/', views.MeView.as_view(), name='me'),
]