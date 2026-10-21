import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PASSWORD = "admin"
DEFAULT_ADMIN_NIK = "1234567890123456"
DEFAULT_ADMIN_EMAIL = "budi@example.com"
JSON_MARKER = "__SEED_JSON__"


class Peran:
    WARGA = 1
    RT = 2
    RW = 3
    KEPALA_DESA = 4
    ADMIN = 5


DATA_JENIS_SURAT = [
    ("A01", "Surat Keterangan Usaha"),
    ("A02", "Surat Keterangan Tempat Usaha"),
    ("A03", "Surat Keterangan Pengantar Barang"),
    ("A04", "Surat Keterangan Tidak Mampu (Sekolah)"),
    ("A05", "Permohonan Izin Keramaian"),
    ("A06", "Surat Pengantar SKCK"),
    ("A07", "Surat Keterangan Ahli Waris"),
    ("A08", "Surat Keterangan Lainnya"),
    ("B01", "Formulir Kartu Keluarga (Pengganti F-1.01)"),
    ("B02", "Formulir Pendaftaran Peristiwa Kependudukan (F-1.02)"),
    ("B03", "Formulir Permohonan KK Baru WNI (F-1.15)"),
    ("B04", "Formulir Permohonan Perubahan KK Baru WNI (F-1.16)"),
    ("B05", "Formulir Permohonan KTP (F-1.21)"),
    ("B06", "Surat Keterangan Domisili"),
    ("B07", "Surat Keterangan Kehilangan KK"),
    ("B08", "Surat Keterangan Pindah Penduduk"),
    ("B09", "Formulir Pendaftaran Perpindahan Penduduk (F-1.03)"),
    ("B10", "Surat Keterangan Kelahiran"),
    ("B11", "Surat Keterangan Kematian"),
]


TEMPLATE_MAPPING = {
    "A01": "A01 - Surat Keterangan Usaha.docx",
    "A02": "A02 - Surat Keterangan Tempat Usaha.docx",
    "A03": "A03 - Surat Keterangan Pengantar Barang.docx",
    "A04": "A04 - Surat Keterangan Tidak Mampu (Sekolah).docx",
    "A05": "A05 - Permohonan Izin Keramaian.docx",
    "A06": "A06 - Surat Pengantar SKCK.docx",
    "A07": "A07 - Surat Keterangan Ahli Waris.docx",
    "A08": "A08 - Surat Keterangan Lainnya.docx",
    "B01": "B01 - Formulir Kartu Keluarga (Pengganti F-1.01).xlsx",
    "B02": "B02 - Formulir Pendaftaran Peristiwa Kependudukan (F-1.02).xlsx",
    "B03": "B03 - Formulir Permohonan KK Baru WNI (F-1.15).xlsx",
    "B04": "B04 - Formulir Permohonan Perubahan KK Baru WNI (F-1.16).xlsx",
    "B05": "B05 - Formulir Permohonan KTP (F-1.21).xlsx",
    "B06": "B06 - Surat Keterangan Domisili.docx",
    "B07": "B07 - Surat Keterangan Kehilangan KK.docx",
    "B08": "B08 - Surat Keterangan Pindah Penduduk.docx",
    "B09": "B09 - Formulir Pendaftaran Perpindahan Penduduk (F-1.03).xlsx",
    "B10": "B10 - Surat Keterangan Kelahiran.docx",
    "B11": "B11 - Surat Keterangan Kematian.docx",
}


SEED_ACCOUNTS = [
    {
        "nama": "Budi Santoso",
        "email": "budi@example.com",
        "nik": "1234567890123456",
        "nomor_kk": "3201010101010001",
        "peran": Peran.ADMIN,
        "rt": 1,
        "rw": 1,
        "alamat": "Jl Mawar No. 1",
        "no_hp": "081234567890",
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "nama": "Andi Wijaya",
        "email": "rt1@example.com",
        "nik": "2234567890123456",
        "nomor_kk": "3201010101010002",
        "peran": Peran.RT,
        "rt": 1,
        "rw": 1,
        "alamat": "Jl Mawar No. 2",
        "no_hp": "081234567891",
    },
    {
        "nama": "Citra Putri",
        "email": "rt2@example.com",
        "nik": "2234567890123457",
        "nomor_kk": "3201010101010003",
        "peran": Peran.RT,
        "rt": 2,
        "rw": 2,
        "alamat": "Jl Melati No. 1",
        "no_hp": "081234567892",
    },
    {
        "nama": "Dewi Pratama",
        "email": "rw1@example.com",
        "nik": "3234567890123456",
        "nomor_kk": "3201010101010004",
        "peran": Peran.RW,
        "rt": 1,
        "rw": 1,
        "alamat": "Jl Mawar No. 3",
        "no_hp": "081234567893",
    },
    {
        "nama": "Eko Saputra",
        "email": "rw2@example.com",
        "nik": "3234567890123457",
        "nomor_kk": "3201010101010005",
        "peran": Peran.RW,
        "rt": 2,
        "rw": 2,
        "alamat": "Jl Melati No. 2",
        "no_hp": "081234567894",
    },
    {
        "nama": "Fajar Santoso",
        "email": "kades@example.com",
        "nik": "4234567890123456",
        "nomor_kk": "3201010101010006",
        "peran": Peran.KEPALA_DESA,
        "rt": 2,
        "rw": 2,
        "alamat": "Jl Melati No. 3",
        "no_hp": "081234567895",
        "nip": "198709102010011001",
    },
    {
        "nama": "Gilang Pratama",
        "email": "warga1@example.com",
        "nik": "5234567890123456",
        "nomor_kk": "3201010101010007",
        "peran": Peran.WARGA,
        "rt": 1,
        "rw": 1,
        "alamat": "Jl Mawar No. 4",
        "no_hp": "081234567896",
    },
    {
        "nama": "Hendra Wijaya",
        "email": "warga2@example.com",
        "nik": "5234567890123457",
        "nomor_kk": "3201010101010008",
        "peran": Peran.WARGA,
        "rt": 1,
        "rw": 1,
        "alamat": "Jl Mawar No. 5",
        "no_hp": "081234567897",
    },
    {
        "nama": "Indah Putri",
        "email": "warga3@example.com",
        "nik": "5234567890123458",
        "nomor_kk": "3201010101010009",
        "peran": Peran.WARGA,
        "rt": 1,
        "rw": 1,
        "alamat": "Jl Mawar No. 6",
        "no_hp": "081234567898",
    },
    {
        "nama": "Joko Saputra",
        "email": "warga4@example.com",
        "nik": "5234567890123459",
        "nomor_kk": "3201010101010010",
        "peran": Peran.WARGA,
        "rt": 2,
        "rw": 2,
        "alamat": "Jl Melati No. 4",
        "no_hp": "081234567899",
    },
    {
        "nama": "Lestari Santoso",
        "email": "warga5@example.com",
        "nik": "5234567890123460",
        "nomor_kk": "3201010101010011",
        "peran": Peran.WARGA,
        "rt": 2,
        "rw": 2,
        "alamat": "Jl Melati No. 5",
        "no_hp": "081234567880",
    },
]


def service_dir(service):
    service_root = os.getenv("SEED_SERVICE_ROOT")
    if service_root:
        return Path(service_root)
    if service in {"auth", "citizen", "registration", "user"}:
        return REPO_ROOT / "user_service"
    return REPO_ROOT / f"{service}_service"


def setup_django(service):
    os.chdir(service_dir(service))
    sys.path.insert(0, str(service_dir(service)))
    sys.path.insert(0, str(REPO_ROOT / "shared"))

    database_url = os.getenv(f"{service.upper()}_DATABASE_URL")
    if service in {"auth", "citizen", "registration", "user"} and not database_url:
        database_url = os.getenv("USER_DATABASE_URL")
    if service == "citizen" and not database_url:
        database_url = os.getenv("REGISTRATION_DATABASE_URL")
    if service == "reporting" and not database_url:
        database_url = os.getenv("DASHBOARD_DATABASE_URL")
    if database_url:
        os.environ["DATABASE_URL"] = database_url

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()


def role_label(role):
    return {
        Peran.WARGA: "Warga",
        Peran.RT: "RT",
        Peran.RW: "RW",
        Peran.KEPALA_DESA: "Kepala Desa",
        Peran.ADMIN: "Admin",
    }[role]


def ensure_django_admin_user():
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    username_field = user_model.USERNAME_FIELD
    user = user_model.objects.filter(**{username_field: DEFAULT_ADMIN_NIK}).first()

    # Service selain user_service masih memakai auth.User. Pertahankan migrasi
    # akun admin lama hanya untuk model yang benar-benar memiliki field username.
    legacy_user = None
    if username_field == "username":
        legacy_user = user_model.objects.filter(username="admin").first()

    if user is None and legacy_user is not None:
        user = legacy_user
        setattr(user, username_field, DEFAULT_ADMIN_NIK)
    elif user is None:
        user = user_model(**{username_field: DEFAULT_ADMIN_NIK})
    elif legacy_user is not None and legacy_user.pk != user.pk:
        legacy_user.is_staff = False
        legacy_user.is_superuser = False
        legacy_user.is_active = False
        legacy_user.set_unusable_password()
        legacy_user.save()

    user.email = DEFAULT_ADMIN_EMAIL
    if hasattr(user, "peran"):
        user.peran = Peran.ADMIN
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password(DEFAULT_PASSWORD)
    user.save()
    print(f"Django admin user siap: username/NIK={DEFAULT_ADMIN_NIK} password={DEFAULT_PASSWORD}")


def seed_citizen():
    setup_django("citizen")

    from django.contrib.auth.hashers import make_password
    from django.utils import timezone
    from registrasi.models import KartuKeluarga, PendaftaranAkun, Penduduk, WilayahRT, WilayahRW

    print("\n=== CITIZEN SERVICE: WILAYAH, KK, PENDUDUK ===")
    ensure_django_admin_user()

    rw_objects = {}
    for kode_rw in sorted({account["rw"] for account in SEED_ACCOUNTS}):
        rw_objects[kode_rw], _ = WilayahRW.objects.get_or_create(kode_rw=kode_rw)

    rt_objects = {}
    for account in SEED_ACCOUNTS:
        key = (account["rw"], account["rt"])
        if key not in rt_objects:
            rt_objects[key], _ = WilayahRT.objects.get_or_create(
                rw=rw_objects[account["rw"]],
                kode_rt=account["rt"],
            )

    for account in SEED_ACCOUNTS:
        rt = rt_objects[(account["rw"], account["rt"])]
        kk, _ = KartuKeluarga.objects.update_or_create(
            nomor_kk=account["nomor_kk"],
            defaults={
                "rt": rt,
                "alamat": account["alamat"],
            },
        )
        penduduk, _ = Penduduk.objects.update_or_create(
            nik=account["nik"],
            defaults={
                "nomor_kk": account["nomor_kk"],
                "kk": kk,
                "nama_lengkap": account["nama"],
                "tempat_lahir": "Bandung",
                "tanggal_lahir": date(1990, 1, 1),
                "jenis_kelamin": Penduduk.JenisKelamin.LAKI_LAKI,
                "agama": Penduduk.Agama.ISLAM,
                "email": account["email"],
                "no_hp": account["no_hp"],
                "rt": rt,
                "status_kependudukan": Penduduk.StatusKependudukan.AKTIF,
            },
        )
        PendaftaranAkun.objects.update_or_create(
            nik=account["nik"],
            defaults={
                "nomor_kk": account["nomor_kk"],
                "nama_lengkap": account["nama"],
                "tempat_lahir": "Bandung",
                "tanggal_lahir": date(1990, 1, 1),
                "jenis_kelamin": Penduduk.JenisKelamin.LAKI_LAKI,
                "agama": Penduduk.Agama.ISLAM,
                "rt": rt,
                "alamat": account["alamat"],
                "email": account["email"],
                "no_hp": account["no_hp"],
                "password_hash": make_password(DEFAULT_PASSWORD),
                "status_verifikasi": PendaftaranAkun.StatusVerifikasi.DISETUJUI,
                "verified_by_user_id": None,
                "verified_by_role": Peran.ADMIN,
                "verified_at": timezone.now(),
            },
        )
        print(f"{account['nik']} {account['nama']} -> penduduk #{penduduk.id}")


def seed_auth():
    setup_django("auth")

    from accounts.models import AuthAccount

    print("\n=== AUTH SERVICE: AKUN LOGIN ===")

    account_ids = {}
    for account in SEED_ACCOUNTS:
        auth_account, _ = AuthAccount.objects.get_or_create(
            nik=account["nik"],
            defaults={
                "email": account["email"],
                "peran": account["peran"],
            },
        )
        auth_account.email = account["email"]
        auth_account.peran = account["peran"]
        auth_account.rt_snapshot = account["rt"]
        auth_account.rw_snapshot = account["rw"]
        auth_account.is_active = True
        auth_account.is_staff = account.get("is_staff", False)
        auth_account.is_superuser = account.get("is_superuser", False)
        auth_account.set_password(DEFAULT_PASSWORD)
        auth_account.save()

        account_ids[account["nik"]] = auth_account.id
        print(f"{account['nik']} {account['email']} -> {role_label(account['peran'])} #{auth_account.id}")

    print(JSON_MARKER + json.dumps({"account_ids": account_ids}, sort_keys=True))


def seed_reporting():
    setup_django("reporting")

    from dashboard.models import DashboardSummary, ProfileReadModel

    account_ids = json.loads(os.getenv("SEED_ACCOUNT_IDS", "{}"))
    if not account_ids:
        account_ids = {account["nik"]: index for index, account in enumerate(SEED_ACCOUNTS, start=1)}

    print("\n=== REPORTING SERVICE: PROFILE READ MODEL ===")
    ensure_django_admin_user()

    for account in SEED_ACCOUNTS:
        user_id = account_ids[account["nik"]]
        ProfileReadModel.objects.filter(nik=account["nik"]).exclude(user_id=user_id).delete()
        ProfileReadModel.objects.filter(user_id=user_id).exclude(nik=account["nik"]).delete()
        ProfileReadModel.objects.update_or_create(
            user_id=user_id,
            defaults={
                "account_id": user_id,
                "nik": account["nik"],
                "nomor_kk": account["nomor_kk"],
                "nama_lengkap": account["nama"],
                "jenis_kelamin": 1,
                "tempat_lahir": "Bandung",
                "tanggal_lahir": date(1990, 1, 1),
                "alamat": account["alamat"],
                "email": account["email"],
                "nomor_telepon": account["no_hp"],
                "nip": account.get("nip"),
                "peran": account["peran"],
                "rt": account["rt"],
                "rw": account["rw"],
            },
        )
        print(f"{account['nik']} {account['nama']} -> profile user_id #{user_id}")

    warga_qs = ProfileReadModel.objects.filter(peran=Peran.WARGA)
    summary_specs = [
        ("desa", "all", Peran.ADMIN),
        ("desa", "all", Peran.KEPALA_DESA),
    ]
    summary_specs.extend(("rw", rw, Peran.RW) for rw in sorted(warga_qs.values_list("rw", flat=True).distinct()))
    summary_specs.extend(("rt", rt, Peran.RT) for rt in sorted(warga_qs.values_list("rt", flat=True).distinct()))

    for scope_type, scope_id, peran in summary_specs:
        if scope_type == "desa":
            total_warga = warga_qs.count()
        else:
            total_warga = warga_qs.filter(**{scope_type: scope_id}).count()

        summary, _ = DashboardSummary.objects.get_or_create(
            scope_type=scope_type,
            scope_id=str(scope_id),
            peran=peran,
            defaults={"isi_cards_json": {}, "progress_json": {}},
        )
        cards = dict(summary.isi_cards_json or {})
        cards["total_warga"] = total_warga
        summary.isi_cards_json = cards
        summary.save(update_fields=["isi_cards_json", "updated_at"])


def seed_surat():
    setup_django("document")

    from django.conf import settings
    from django.core.files import File
    from surat.models import JenisSurat

    print("\n=== DOCUMENT SERVICE: JENIS SURAT & TEMPLATE ===")
    ensure_django_admin_user()

    template_dirs = [
        REPO_ROOT / "template_surat",
        Path(getattr(settings, "TEMPLATE_SURAT_DIR", "")),
        Path("/template_surat"),
    ]

    for kode, nama in DATA_JENIS_SURAT:
        obj, _ = JenisSurat.objects.update_or_create(
            kode=kode,
            defaults={
                "nama": nama,
                "aktif": True,
            },
        )

        filename = TEMPLATE_MAPPING.get(kode)
        template_path = next((path / filename for path in template_dirs if filename and (path / filename).exists()), None)

        if not template_path:
            print(f"{kode} file template tidak ditemukan")
            continue

        if obj.template_file:
            obj.template_file.delete(save=False)

        with open(template_path, "rb") as file:
            obj.template_file.save(filename, File(file), save=True)

        print(f"{kode} template ditambahkan / replace")


def run_local_child(service, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [sys.executable, str(__file__), "--service", service],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    payload = {}
    for line in result.stdout.splitlines():
        if line.startswith(JSON_MARKER):
            payload = json.loads(line.removeprefix(JSON_MARKER))
    return payload


def docker_compose_command(*args):
    command = ["docker", "compose", "-f", "docker-compose.microservices.yml"]
    if (REPO_ROOT / ".env.microservices").exists():
        command.extend(["--env-file", ".env.microservices"])
    command.extend(args)
    return command


def run_docker_child(service, extra_env=None):
    compose_service = {
        "citizen": "user-api",
        "registration": "user-api",
        "auth": "user-api",
        "user": "user-api",
        "reporting": "reporting-api",
        "dashboard": "reporting-api",
        "document": "document-api",
    }[service]

    subprocess.run(
        docker_compose_command("cp", str(__file__), f"{compose_service}:/tmp/seed_dev.py"),
        cwd=REPO_ROOT,
        check=True,
    )

    env_args = ["-e", "SEED_SERVICE_ROOT=/app"]
    for key, value in (extra_env or {}).items():
        env_args.extend(["-e", f"{key}={value}"])

    result = subprocess.run(
        docker_compose_command(
            "exec",
            "-T",
            *env_args,
            compose_service,
            "python",
            "/tmp/seed_dev.py",
            "--service",
            service,
        ),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    payload = {}
    for line in result.stdout.splitlines():
        if line.startswith(JSON_MARKER):
            payload = json.loads(line.removeprefix(JSON_MARKER))
    return payload


def run_child(service, target, extra_env=None):
    if target == "docker":
        return run_docker_child(service, extra_env)
    return run_local_child(service, extra_env)


def seed_all(target):
    print("Seed microservice Dekstra")
    print(f"Password default semua akun: {DEFAULT_PASSWORD}")

    run_child("citizen", target)
    auth_payload = run_child("auth", target)
    run_child("reporting", target, {"SEED_ACCOUNT_IDS": json.dumps(auth_payload.get("account_ids", {}))})
    run_child("document", target)

    print("\nSEED MICROSERVICE SELESAI")


def main():
    parser = argparse.ArgumentParser(description="Seed data development untuk sistem microservice Dekstra.")
    parser.add_argument(
        "--service",
        choices=["all", "user", "citizen", "registration", "auth", "reporting", "dashboard", "document"],
        default="all",
        help="Service yang ingin di-seed. Default: all.",
    )
    parser.add_argument(
        "--target",
        choices=["local", "docker"],
        default="local",
        help="Target database. local memakai sqlite service lokal, docker memakai container docker compose.",
    )
    args = parser.parse_args()

    if args.service == "all":
        seed_all(args.target)
    elif args.target == "docker":
        run_child(args.service, args.target)
    elif args.service in {"citizen", "registration"}:
        seed_citizen()
    elif args.service == "auth":
        seed_auth()
    elif args.service == "user":
        seed_citizen()
        seed_auth()
    elif args.service in {"reporting", "dashboard"}:
        seed_reporting()
    elif args.service == "document":
        seed_surat()


if __name__ == "__main__":
    main()
