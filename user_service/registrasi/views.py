from pathlib import Path

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PendaftaranAkun, WilayahRT, WilayahRW
from .serializers import (
    PendaftaranAkunDetailSerializer,
    PendaftaranAkunListSerializer,
    RegisterSerializer,
    VerifikasiPendaftaranSerializer,
    WilayahRTSerializer,
    WilayahRWSerializer,
)


def token_claim(request, key, default=None):
    if request.auth is None:
        return default
    value = request.auth.get(key, default)
    if key in {"user_id", "peran", "rt", "rw"} and isinstance(value, str) and value.isdigit():
        return int(value)
    return value


class IsAdminRole(permissions.BasePermission):
    message = "Hanya Admin yang dapat mengakses proses verifikasi pendaftaran."

    def has_permission(self, request, view):
        return token_claim(request, "peran") == 5


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class WilayahRWListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        queryset = WilayahRW.objects.all().order_by("kode_rw")
        return Response(WilayahRWSerializer(queryset, many=True).data)


class WilayahRTListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        rw = request.query_params.get("rw")
        if not rw:
            return Response({"rw": "Parameter rw wajib diisi"}, status=status.HTTP_400_BAD_REQUEST)
        queryset = WilayahRT.objects.filter(rw__kode_rw=rw).order_by("kode_rt")
        if not queryset.exists():
            return Response(
                {"rt": "RT tidak ditemukan"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(WilayahRTSerializer(queryset, many=True).data)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response({"id": obj.id, "nik": obj.nik}, status=status.HTTP_201_CREATED)


class PendaftaranAkunListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        queryset = PendaftaranAkun.objects.all().order_by("-created_at")
        status_filter = request.query_params.get("status")
        if status_filter is not None:
            try:
                queryset = queryset.filter(
                    status_verifikasi=int(status_filter)
                )
            except ValueError:
                pass
        else:
            queryset = queryset.filter(status_verifikasi=PendaftaranAkun.StatusVerifikasi.DITINJAU)
        nik_filter = request.query_params.get("nik")
        if nik_filter:
            queryset = queryset.filter(nik=nik_filter)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PendaftaranAkunListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class PendaftaranAkunDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request, id):
        obj = PendaftaranAkun.objects.select_related("rt__rw").get(id=id)
        return Response(PendaftaranAkunDetailSerializer(obj, context={"request": request}).data)


class PendaftaranAkunBerkasView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request, id, kind):
        obj = get_object_or_404(PendaftaranAkun, id=id)
        field = {"kk": obj.kk_file, "ktp": obj.ktp_file}.get(kind)
        if not field or not field.name or not field.storage.exists(field.name):
            return Response({"detail": "Berkas tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)

        return FileResponse(field.open("rb"), filename=Path(field.name).name)


class VerifikasiPendaftaranAkunView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def post(self, request, id):
        obj = PendaftaranAkun.objects.select_related("rt__rw").get(id=id)
        serializer = VerifikasiPendaftaranSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            instance=obj,
            actor_user_id=token_claim(request, "user_id"),
            actor_role=token_claim(request, "peran"),
        )
        message = "Pendaftaran berhasil disetujui" if serializer.validated_data["aksi"] == 1 else "Pendaftaran berhasil ditolak"
        return Response({"message": message})
