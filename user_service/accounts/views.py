from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuthAccount
from .serializers import (
    InternalAccountCreateSerializer,
    LoginOTPRequestSerializer,
    LoginSerializer,
    ResetPasswordOTPRequestSerializer,
    ResetPasswordVerifySerializer,
)


class InternalTokenPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        token = request.headers.get("X-Internal-Token")
        return bool(token and token == settings.INTERNAL_SERVICE_TOKEN)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LoginOTPRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class ResetPasswordOTPRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class ResetPasswordVerifyView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class InternalAccountCreateView(APIView):
    permission_classes = [InternalTokenPermission]

    def post(self, request):
        serializer = InternalAccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(
            {
                "id": account.id,
                "nik": account.nik,
                "email": account.email,
                "peran": account.peran,
                "is_active": account.is_active,
            },
            status=status.HTTP_201_CREATED,
        )


class InternalAccountByNikView(APIView):
    permission_classes = [InternalTokenPermission]

    def get(self, request, nik):
        account = get_object_or_404(AuthAccount, nik=nik)
        return Response(
            {
                "id": account.id,
                "nik": account.nik,
                "email": account.email,
                "peran": account.peran,
                "is_active": account.is_active,
                "rt": account.rt_snapshot,
                "rw": account.rw_snapshot,
            }
        )


class InternalAccountActivationView(APIView):
    permission_classes = [InternalTokenPermission]

    def patch(self, request, account_id, action):
        account = get_object_or_404(AuthAccount, id=account_id)
        if action == "activate":
            account.is_active = True
        elif action == "deactivate":
            account.is_active = False
        else:
            return Response({"detail": "Action tidak valid."}, status=status.HTTP_400_BAD_REQUEST)

        account.save(update_fields=["is_active", "updated_at"])
        return Response({"id": account.id, "is_active": account.is_active})

