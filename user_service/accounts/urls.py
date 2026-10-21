from django.urls import path

from .views import (
    InternalAccountActivationView,
    InternalAccountByNikView,
    InternalAccountCreateView,
    LoginOTPRequestView,
    LoginView,
    ResetPasswordOTPRequestView,
    ResetPasswordVerifyView,
)

urlpatterns = [
    path("auth/login/", LoginView.as_view()),
    path("auth/otp/request/login/", LoginOTPRequestView.as_view()),
    path("auth/otp/request/reset-password/", ResetPasswordOTPRequestView.as_view()),
    path("auth/otp/verify/reset-password/", ResetPasswordVerifyView.as_view()),
    path("internal/auth/accounts/", InternalAccountCreateView.as_view()),
    path("internal/auth/accounts/by-nik/<str:nik>/", InternalAccountByNikView.as_view()),
    path("internal/auth/accounts/<int:account_id>/<str:action>/", InternalAccountActivationView.as_view()),
]

