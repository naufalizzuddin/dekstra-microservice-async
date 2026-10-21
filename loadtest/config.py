import os


PASSWORD = os.getenv("SBLT_PASSWORD", "LoadTest!2026")
FIXED_OTP = os.getenv("SBLT_OTP", "246810")
RW_CODE = 99
RT_CODE = 99
KK_NUMBER = "9700000000000001"

ROLE_PREFIXES = {
    "citizen": "91",
    "rt": "92",
    "rw": "93",
    "admin": "94",
    "kades": "95",
    "registration": "96",
}

ENDPOINT_DEFINITIONS = {
    "E-01": {
        "method": "POST",
        "path": "/auth/login/",
        "function": "Login pengguna menggunakan OTP",
        "actor": "Semua pengguna",
        "authentication": "Tidak",
        "weight_percent": 10,
    },
    "E-02": {
        "method": "POST",
        "path": "/auth/register/",
        "function": "Pendaftaran akun baru",
        "actor": "Warga",
        "authentication": "Tidak",
        "weight_percent": 8,
    },
    "E-03": {
        "method": "GET",
        "path": "/pendaftaran-akun/list/",
        "function": "Melihat data pendaftaran akun baru",
        "actor": "Admin",
        "authentication": "Bearer Token",
        "weight_percent": 8,
    },
    "E-04": {
        "method": "POST",
        "path": "/verifikasi/pendaftaran-akun/{id}/",
        "function": "Memverifikasi pendaftaran akun",
        "actor": "Admin",
        "authentication": "Bearer Token",
        "weight_percent": 8,
    },
    "E-05": {
        "method": "GET",
        "path": "/pengajuan-surat/",
        "function": "Melihat daftar surat yang telah diajukan",
        "actor": "Warga",
        "authentication": "Bearer Token",
        "weight_percent": 14,
    },
    "E-06": {
        "method": "POST",
        "path": "/pengajuan-surat/",
        "function": "Mengajukan surat baru",
        "actor": "Warga",
        "authentication": "Bearer Token",
        "weight_percent": 14,
    },
    "E-07": {
        "method": "POST",
        "path": "/upload/berkas-surat/",
        "function": "Mengunggah berkas tambahan pengajuan surat",
        "actor": "Warga",
        "authentication": "Bearer Token",
        "weight_percent": 8,
    },
    "E-08": {
        "method": "POST",
        "path": "/riwayat-persetujuan/",
        "function": "Menyetujui atau menolak pengajuan surat",
        "actor": "RT, RW, Admin, Kepala Desa",
        "authentication": "Bearer Token",
        "weight_percent": 14,
    },
    "E-09": {
        "method": "GET",
        "path": "/notifikasi/",
        "function": "Melihat notifikasi yang masuk",
        "actor": "Semua pengguna",
        "authentication": "Bearer Token",
        "weight_percent": 8,
    },
    "E-10": {
        "method": "GET",
        "path": "/dashboard/",
        "function": "Melihat statistik pengajuan surat",
        "actor": "RT, RW, Admin, Kepala Desa",
        "authentication": "Bearer Token",
        "weight_percent": 8,
    },
}

ENDPOINT_CODES = {
    code: (details["method"], details["path"])
    for code, details in ENDPOINT_DEFINITIONS.items()
}


def test_nik(role, index):
    return f"{ROLE_PREFIXES[role]}{index:014d}"


def test_email(role, index):
    return f"loadtest-{role}-{index:04d}@example.invalid"


def registration_nik(index):
    return test_nik("registration", index)


def registration_email(index):
    return test_email("registration", index)


def approval_number(stage, index):
    return f"LT/{stage}/{index:06d}"


def completed_number(index):
    return f"LT/DONE/{index:06d}"
