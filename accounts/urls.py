from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import admin_views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('verify-otp/', views.VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', views.ResendOTPView.as_view(), name='resend-otp'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/', views.ResetPasswordView.as_view(), name='reset-password'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('admin/users/', admin_views.AdminUserListView.as_view(), name='admin-users'),
    path('admin/grant-plan/', admin_views.AdminGrantPlanView.as_view(), name='admin-grant-plan'),
    path('admin/revenue/', admin_views.AdminRevenueView.as_view(), name='admin-revenue'),
    path('me/', views.MeView.as_view(), name='me'),
]