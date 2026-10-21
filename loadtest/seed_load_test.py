import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_MANIFEST = Path("/tmp/loadtest_accounts.json")
ASYNC_WORKERS = [
    "otp-email-worker",
    "document-generation-worker",
    "reporting-projection-worker",
    "notification-worker",
]


def load_seed_config():
    spec = importlib.util.spec_from_file_location(
        "loadtest_seed_config",
        SCRIPT_DIR / "config.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEED_CONFIG = load_seed_config()
KK_NUMBER = SEED_CONFIG.KK_NUMBER
PASSWORD = SEED_CONFIG.PASSWORD
RT_CODE = SEED_CONFIG.RT_CODE
RW_CODE = SEED_CONFIG.RW_CODE
approval_number = SEED_CONFIG.approval_number
completed_number = SEED_CONFIG.completed_number
registration_email = SEED_CONFIG.registration_email
registration_nik = SEED_CONFIG.registration_nik
test_email = SEED_CONFIG.test_email
test_nik = SEED_CONFIG.test_nik


def require_confirmation():
    if os.getenv("LOADTEST_SEED_CONFIRMED") != "1":
        raise RuntimeError(
            "Seeder hanya boleh dijalankan pada target load test khusus. "
            "Gunakan --confirm-loadtest-target."
        )


def setup_django():
    service_root = Path(os.environ.get("LOADTEST_SERVICE_ROOT", "/app"))
    os.chdir(service_root)
    sys.path.insert(0, str(service_root))
    sys.path.insert(0, "/shared")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()


def write_manifest(path, manifest):
    target = Path(path)
    payload = json.dumps(manifest, indent=2)
    try:
        target.write_text(payload, encoding="utf-8")
    except PermissionError:
        target.unlink(missing_ok=True)
        target.write_text(payload, encoding="utf-8")


def read_manifest(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_accounts(path):
    return read_manifest(path)["accounts"]


def update_manifest(path, **sections):
    manifest = read_manifest(path)
    manifest.update(sections)
    write_manifest(path, manifest)


def loadtest_email_query(model):
    from django.db.models import Q

    return model.objects.filter(
        Q(email__startswith="loadtest-")
        | Q(email__startswith="sblt-")
    )


def purge_auth():
    require_confirmation()
    setup_django()

    from django.db.models import Q
    from accounts.models import AuthAccount, OutboxEvent

    count, _ = loadtest_email_query(AuthAccount).delete()
    OutboxEvent.objects.filter(
        Q(payload__data__email__startswith="loadtest-")
        | Q(payload__data__email__startswith="sblt-")
    ).delete()
    print(f"Auth rows dihapus: {count}")


def seed_auth(citizens, auth_citizens, manifest_path, otp_ttl_hours):
    require_confirmation()
    setup_django()

    from django.conf import settings
    from django.contrib.auth.hashers import make_password
    from django.utils import timezone
    from accounts.models import AuthAccount, OTPEmail
    from accounts.serializers import token_response_for

    loadtest_email_query(AuthAccount).delete()
    password_hash = make_password(PASSWORD)
    definitions = [
        ("citizen", 1, auth_citizens),
        ("rt", 2, 1),
        ("rw", 3, 1),
        ("admin", 5, 1),
        ("kades", 4, 1),
    ]
    objects = []
    account_meta = []
    for role_name, role_value, count in definitions:
        for index in range(1, count + 1):
            objects.append(
                AuthAccount(
                    nik=test_nik(role_name, index),
                    email=test_email(role_name, index),
                    peran=role_value,
                    password=password_hash,
                    rt_snapshot=RT_CODE,
                    rw_snapshot=RW_CODE,
                    is_active=True,
                    is_staff=role_name == "admin",
                    is_superuser=role_name == "admin",
                )
            )
    AuthAccount.objects.bulk_create(objects)

    stored = {
        account.nik: account
        for account in AuthAccount.objects.filter(
            email__startswith="loadtest-"
        )
    }
    for role_name, role_value, count in definitions:
        for index in range(1, count + 1):
            account = stored[test_nik(role_name, index)]
            token = token_response_for(account)
            account_meta.append(
                {
                    "id": account.id,
                    "role": role_name,
                    "role_value": role_value,
                    "index": index,
                    "nik": account.nik,
                    "email": account.email,
                    "access": token["access"],
                    "refresh": token["refresh"],
                }
            )

    otp_hash = make_password(getattr(settings, "LOAD_TEST_OTP", "246810"))
    expires_at = timezone.now() + timedelta(hours=otp_ttl_hours)
    for account in stored.values():
        OTPEmail.objects.update_or_create(
            account=account,
            tujuan=OTPEmail.Tujuan.LOGIN,
            defaults={
                "kode_hash": otp_hash,
                "kedaluwarsa_at": expires_at,
                "dipakai_at": None,
            },
        )

    write_manifest(manifest_path, {"accounts": account_meta})
    print(f"Akun load test dibuat: {len(account_meta)}")


def _purge_citizen_models():
    from django.db.models import Q
    from registrasi.models import (
        KartuKeluarga,
        OutboxEvent,
        PendaftaranAkun,
        Penduduk,
    )

    registrations = PendaftaranAkun.objects.filter(
        Q(email__startswith="loadtest-")
        | Q(email__startswith="sblt-")
    )
    residents = Penduduk.objects.filter(
        Q(email__startswith="loadtest-")
        | Q(email__startswith="sblt-")
    )
    family_ids = list(residents.values_list("kk_id", flat=True))
    registrations.delete()
    residents.delete()
    OutboxEvent.objects.filter(
        Q(payload__data__email__startswith="loadtest-")
        | Q(payload__data__email__startswith="sblt-")
    ).delete()
    KartuKeluarga.objects.filter(
        Q(pk__in=family_ids) | Q(nomor_kk=KK_NUMBER)
    ).delete()


def seed_citizen(manifest_path, registrations):
    require_confirmation()
    setup_django()

    from django.contrib.auth.hashers import make_password
    from registrasi.models import (
        KartuKeluarga,
        PendaftaranAkun,
        Penduduk,
        WilayahRT,
        WilayahRW,
    )

    _purge_citizen_models()
    accounts = read_accounts(manifest_path)
    rw, _ = WilayahRW.objects.get_or_create(kode_rw=RW_CODE)
    rt, _ = WilayahRT.objects.get_or_create(
        rw=rw,
        kode_rt=RT_CODE,
    )
    family, _ = KartuKeluarga.objects.update_or_create(
        nomor_kk=KK_NUMBER,
        defaults={"rt": rt, "alamat": "Wilayah Load Test"},
    )

    residents = [
        Penduduk(
            nik=account["nik"],
            nomor_kk=KK_NUMBER,
            kk=family,
            nama_lengkap=(
                f"Load Test {account['role'].title()} "
                f"{account['index']}"
            ),
            tempat_lahir="Semarang",
            tanggal_lahir=date(1990, 1, 1),
            jenis_kelamin=1,
            agama=1,
            email=account["email"],
            no_hp=f"08{account['id'] % 10_000_000_000:010d}",
            rt=rt,
        )
        for account in accounts
    ]
    Penduduk.objects.bulk_create(residents)

    password_hash = make_password(PASSWORD)
    pending = [
        PendaftaranAkun(
            nomor_kk=f"98{index:014d}",
            nik=registration_nik(index),
            nama_lengkap=f"Load Test Registration {index}",
            tempat_lahir="Semarang",
            tanggal_lahir=date(1990, 1, 1),
            jenis_kelamin=1,
            agama=1,
            rt=rt,
            alamat="Alamat Load Test",
            email=registration_email(index),
            no_hp=f"08{index:010d}",
            password_hash=password_hash,
            status_verifikasi=PendaftaranAkun.StatusVerifikasi.DITINJAU,
        )
        for index in range(1, registrations + 1)
    ]
    PendaftaranAkun.objects.bulk_create(pending)
    update_manifest(
        manifest_path,
        registration_candidates=[
            {"id": row.id, "nik": row.nik}
            for row in (
                PendaftaranAkun.objects.filter(
                    email__startswith="loadtest-registration-",
                    status_verifikasi=PendaftaranAkun.StatusVerifikasi.DITINJAU,
                ).order_by("id")
            )
        ],
        wilayah={
            "rw": RW_CODE,
            "rt": rt.id,
        },
    )
    print(
        f"Citizen fixture: {len(residents)} penduduk, "
        f"{registrations} pendaftaran."
    )


def purge_user_registration_data():
    require_confirmation()
    setup_django()
    _purge_citizen_models()
    print("Citizen fixture dihapus.")


def _purge_reporting_models():
    from django.db.models import Q
    from dashboard.models import Notifikasi, ProfileReadModel

    profiles = ProfileReadModel.objects.filter(
        Q(email__startswith="loadtest-")
        | Q(email__startswith="sblt-")
    )
    user_ids = list(profiles.values_list("user_id", flat=True))
    Notifikasi.objects.filter(penerima_user_id__in=user_ids).delete()
    profiles.delete()


def seed_reporting(manifest_path, registrations):
    require_confirmation()
    setup_django()

    from dashboard.models import (
        DashboardSummary,
        Notifikasi,
        ProfileReadModel,
    )

    _purge_reporting_models()
    accounts = read_accounts(manifest_path)
    profiles = [
        ProfileReadModel(
            user_id=account["id"],
            account_id=account["id"],
            nik=account["nik"],
            nomor_kk=KK_NUMBER,
            nama_lengkap=(
                f"Load Test {account['role'].title()} "
                f"{account['index']}"
            ),
            jenis_kelamin=1,
            tempat_lahir="Semarang",
            tanggal_lahir=date(1990, 1, 1),
            alamat="Wilayah Load Test",
            email=account["email"],
            nomor_telepon=f"08{account['id'] % 10_000_000_000:010d}",
            nip="LOADTEST-2026" if account["role"] == "kades" else None,
            peran=account["role_value"],
            rt=RT_CODE,
            rw=RW_CODE,
        )
        for account in accounts
    ]
    ProfileReadModel.objects.bulk_create(profiles)

    citizens = [
        account for account in accounts if account["role"] == "citizen"
    ]
    Notifikasi.objects.bulk_create(
        [
            Notifikasi(
                penerima_user_id=account["id"],
                tipe="surat.selesai",
                judul="Dokumen final tersedia",
                pesan="Dokumen load test siap diunduh.",
                permohonan_nomor=completed_number(account["index"]),
            )
            for account in citizens
        ]
    )
    for scope_type, scope_id, role in [
        ("rt", str(RT_CODE), 2),
        ("rw", str(RW_CODE), 3),
        ("desa", "all", 5),
        ("desa", "all", 4),
    ]:
        DashboardSummary.objects.update_or_create(
            scope_type=scope_type,
            scope_id=scope_id,
            peran=role,
            defaults={
                "isi_cards_json": {
                    "total_warga": len(citizens),
                    "pendaftaran_perlu_verifikasi": registrations,
                },
                "progress_json": {},
            },
        )
    print(
        f"Reporting fixture: {len(profiles)} profil, "
        f"{len(citizens)} notifikasi."
    )


def purge_reporting():
    require_confirmation()
    setup_django()
    _purge_reporting_models()
    print("Reporting fixture dihapus.")


def ensure_letter_template(letter_type):
    if letter_type.template_file:
        return

    from django.core.files import File

    candidates = [
        Path("/template_surat/A01 - Surat Keterangan Usaha.docx"),
        REPO_ROOT / "template_surat" / "A01 - Surat Keterangan Usaha.docx",
    ]
    template = next((item for item in candidates if item.exists()), None)
    if not template:
        raise RuntimeError("Template A01 tidak ditemukan.")
    with template.open("rb") as source:
        letter_type.template_file.save(
            template.name,
            File(source),
            save=True,
        )


def _purge_document_models():
    from django.db.models import Q
    from surat.models import OutboxEvent, PermohonanSurat

    PermohonanSurat.objects.filter(
        Q(nomor_permohonan__startswith="LT/")
        | Q(data__loadtest=True)
    ).delete()
    OutboxEvent.objects.filter(
        Q(payload__data__nomor_permohonan__startswith="LT/")
        | Q(payload__data__pemohon_nik__startswith="91")
    ).delete()


def seed_document(manifest_path, pending_per_stage, completed_documents):
    require_confirmation()
    setup_django()

    from django.conf import settings
    from django.utils import timezone
    from surat.models import (
        DokumenSurat,
        JenisSurat,
        PermohonanSurat,
        RiwayatPersetujuan,
    )

    _purge_document_models()
    accounts = read_accounts(manifest_path)
    citizens = [
        account for account in accounts if account["role"] == "citizen"
    ]
    actors = {
        account["role"]: account
        for account in accounts
        if account["role"] != "citizen"
    }

    letter_type, _ = JenisSurat.objects.update_or_create(
        kode="A01",
        defaults={
            "nama": "Surat Keterangan Usaha",
            "aktif": True,
        },
    )
    ensure_letter_template(letter_type)

    media_file = Path(settings.MEDIA_ROOT) / "loadtest" / "final.pdf"
    media_file.parent.mkdir(parents=True, exist_ok=True)
    media_file.write_bytes(
        b"%PDF-1.4\n% Dekstra load-test document\n%%EOF\n"
    )
    now = timezone.now()

    completed = [
        PermohonanSurat(
            nomor_permohonan=completed_number(index),
            jenis_surat=letter_type,
            pemohon_user_id=account["id"],
            pemohon_nik_snapshot=account["nik"],
            pemohon_nama_snapshot=(
                f"Load Test Citizen {account['index']}"
            ),
            pemohon_rt_snapshot=RT_CODE,
            pemohon_rw_snapshot=RW_CODE,
            data={
                "loadtest": True,
                "tujuan": "Download load-test document",
            },
            status=PermohonanSurat.Status.SELESAI,
            current_tahap=PermohonanSurat.Tahap.SELESAI,
            diajukan_at=now,
            selesai_at=now,
        )
        for index in range(1, completed_documents + 1)
        for account in [citizens[(index - 1) % len(citizens)]]
    ]
    PermohonanSurat.objects.bulk_create(completed)
    completed_rows = PermohonanSurat.objects.filter(
        nomor_permohonan__startswith="LT/DONE/"
    )
    DokumenSurat.objects.bulk_create(
        [
            DokumenSurat(
                permohonan=application,
                file_final="loadtest/final.pdf",
                status_generate=DokumenSurat.StatusGenerate.SELESAI,
            )
            for application in completed_rows
        ]
    )

    stages = [
        ("RT", PermohonanSurat.Tahap.RT, "rt"),
        ("RW", PermohonanSurat.Tahap.RW, "rw"),
        ("ADMIN", PermohonanSurat.Tahap.ADMIN, "admin"),
        (
            "KEPALA-DESA",
            PermohonanSurat.Tahap.KEPALA_DESA,
            "kades",
        ),
    ]
    for label, stage, actor_role in stages:
        applications = [
            PermohonanSurat(
                nomor_permohonan=approval_number(label, index),
                jenis_surat=letter_type,
                pemohon_user_id=citizens[(index - 1) % len(citizens)]["id"],
                pemohon_nik_snapshot=citizens[
                    (index - 1) % len(citizens)
                ]["nik"],
                pemohon_nama_snapshot=(
                    f"Load Test Citizen "
                    f"{citizens[(index - 1) % len(citizens)]['index']}"
                ),
                pemohon_rt_snapshot=RT_CODE,
                pemohon_rw_snapshot=RW_CODE,
                data={
                    "loadtest": True,
                    "load_profile": "weighted_endpoint",
                    "approval_stage": label,
                },
                status=PermohonanSurat.Status.DIAJUKAN,
                current_tahap=stage,
                diajukan_at=now,
            )
            for index in range(1, pending_per_stage + 1)
        ]
        PermohonanSurat.objects.bulk_create(applications)
        stored = PermohonanSurat.objects.filter(
            nomor_permohonan__startswith=f"LT/{label}/"
        )
        actor = actors[actor_role]
        RiwayatPersetujuan.objects.bulk_create(
            [
                RiwayatPersetujuan(
                    permohonan=application,
                    tahap=stage,
                    aksi=RiwayatPersetujuan.Aksi.AJUKAN,
                    oleh_user_id=actor["id"],
                    oleh_role_snapshot=actor["role_value"],
                    waktu=now,
                )
                for application in stored
            ]
        )
        print(f"Antrean {label}: {pending_per_stage}")

    citizen_index_by_id = {
        account["id"]: account["index"]
        for account in citizens
    }
    stage_labels = {
        int(PermohonanSurat.Tahap.RT): "RT",
        int(PermohonanSurat.Tahap.RW): "RW",
        int(PermohonanSurat.Tahap.ADMIN): "ADMIN",
        int(PermohonanSurat.Tahap.KEPALA_DESA): "KEPALA-DESA",
    }
    pending_applications = (
        PermohonanSurat.objects.filter(
            nomor_permohonan__startswith="LT/",
            status=PermohonanSurat.Status.DIAJUKAN,
        )
        .exclude(nomor_permohonan__startswith="LT/DONE/")
        .order_by("id")
    )
    update_manifest(
        manifest_path,
        approval_candidates=[
            {
                "id": application.id,
                "nomor_permohonan": application.nomor_permohonan,
                "stage": stage_labels.get(int(application.current_tahap)),
            }
            for application in pending_applications
            if int(application.current_tahap) in stage_labels
        ],
        application_candidates=[
            {
                "id": application.id,
                "nomor_permohonan": application.nomor_permohonan,
                "pemohon_user_id": application.pemohon_user_id,
                "citizen_index": citizen_index_by_id.get(
                    application.pemohon_user_id
                ),
            }
            for application in pending_applications
        ],
        final_document_tokens=[
            str(row.public_token)
            for row in (
                DokumenSurat.objects.filter(
                    permohonan__nomor_permohonan__startswith="LT/DONE/",
                    file_final__gt="",
                ).order_by("id")
            )
        ],
    )
    print(f"Dokumen final: {completed_documents}")


def purge_document():
    require_confirmation()
    setup_django()
    _purge_document_models()
    print("Document fixture dihapus.")


def compose_base(args):
    command = ["docker", "compose", "--env-file", args.env_file]
    for compose_file in args.compose_file:
        command.extend(["-f", compose_file])
    return command


def compose_run(args, *command):
    return subprocess.run(
        [*compose_base(args), *command],
        cwd=REPO_ROOT,
        check=True,
    )


def copy_seed_code(args, service):
    compose_run(args, "cp", "loadtest/config.py", f"{service}:/tmp/config.py")
    compose_run(
        args,
        "cp",
        "loadtest/seed_load_test.py",
        f"{service}:/tmp/seed_load_test.py",
    )


def copy_manifest_to_service(args, manifest_host, service):
    compose_run(args, "cp", str(manifest_host), f"{service}:{DEFAULT_MANIFEST}")
    compose_run(
        args,
        "exec",
        "-T",
        "--user",
        "0",
        service,
        "chmod",
        "666",
        str(DEFAULT_MANIFEST),
    )


def exec_service(args, service, service_mode, extra_args=None):
    copy_seed_code(args, service)
    compose_run(
        args,
        "exec",
        "-T",
        "--user",
        "0",
        "-e",
        "LOADTEST_SERVICE_ROOT=/app",
        "-e",
        "LOADTEST_SEED_CONFIRMED=1",
        service,
        "python",
        "/tmp/seed_load_test.py",
        "--service",
        service_mode,
        *(extra_args or []),
    )


def prepare_docker(args):
    generated_dir = REPO_ROOT / "loadtest" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    manifest_host = generated_dir / "accounts.json"

    compose_run(args, "stop", *ASYNC_WORKERS)
    try:
        compose_run(
            args,
            "exec",
            "-T",
            "redis",
            "sh",
            "-c",
            'redis-cli --no-auth-warning -a "$REDIS_PASSWORD" -n 0 '
            'FLUSHDB && redis-cli --no-auth-warning -a "$REDIS_PASSWORD" '
            "-n 1 FLUSHDB",
        )

        exec_service(
            args,
            "document-api",
            "document",
            ["--purge-only"],
        )
        exec_service(
            args,
            "reporting-api",
            "reporting",
            ["--purge-only"],
        )
        exec_service(
            args,
            "user-api",
            "citizen",
            ["--purge-only"],
        )
        exec_service(
            args,
            "user-api",
            "auth",
            [
                "--citizens",
                str(args.citizens),
                "--auth-citizens",
                str(args.auth_citizens),
                "--manifest",
                str(DEFAULT_MANIFEST),
                "--otp-ttl-hours",
                str(args.otp_ttl_hours),
            ],
        )
        compose_run(
            args,
            "cp",
            f"user-api:{DEFAULT_MANIFEST}",
            str(manifest_host),
        )

        for service in (
            "user-api",
            "reporting-api",
            "document-api",
        ):
            copy_manifest_to_service(args, manifest_host, service)

        exec_service(
            args,
            "user-api",
            "citizen",
            [
                "--manifest",
                str(DEFAULT_MANIFEST),
                "--registrations",
                str(args.registrations),
            ],
        )
        compose_run(
            args,
            "cp",
            f"user-api:{DEFAULT_MANIFEST}",
            str(manifest_host),
        )
        for service in (
            "reporting-api",
            "document-api",
        ):
            copy_manifest_to_service(args, manifest_host, service)

        exec_service(
            args,
            "reporting-api",
            "reporting",
            [
                "--manifest",
                str(DEFAULT_MANIFEST),
                "--registrations",
                str(args.registrations),
            ],
        )
        exec_service(
            args,
            "document-api",
            "document",
            [
                "--manifest",
                str(DEFAULT_MANIFEST),
                "--pending-per-stage",
                str(args.pending_per_stage),
                "--completed-documents",
                str(args.completed_documents),
            ],
        )
        compose_run(
            args,
            "cp",
            f"document-api:{DEFAULT_MANIFEST}",
            str(manifest_host),
        )
    finally:
        compose_run(args, "start", *ASYNC_WORKERS)

    print(
        "Fixture siap: "
        f"{args.citizens} warga bisnis, "
        f"{args.auth_citizens} warga autentikasi, "
        "1 RT, 1 RW, 1 Admin, "
        f"1 Kepala Desa, {args.pending_per_stage} permohonan/tahap, "
        f"{args.registrations} pendaftaran, "
        f"{args.completed_documents} dokumen final."
    )


def purge_docker(args):
    compose_run(args, "stop", *ASYNC_WORKERS)
    try:
        for service, mode in (
            ("document-api", "document"),
            ("reporting-api", "reporting"),
            ("user-api", "citizen"),
            ("user-api", "auth"),
        ):
            exec_service(
                args,
                service,
                mode,
                ["--purge-only"],
            )
    finally:
        compose_run(args, "start", *ASYNC_WORKERS)
    print("Seluruh fixture load test telah dihapus.")


def main():
    parser = argparse.ArgumentParser(
        description="Fixture deterministik load testing Dekstra microservice."
    )
    parser.add_argument(
        "--service",
        choices=["docker", "auth", "citizen", "reporting", "document"],
        default="docker",
    )
    parser.add_argument("--citizens", type=int, default=60)
    parser.add_argument("--auth-citizens", type=int, default=500)
    parser.add_argument("--pending-per-stage", type=int, default=5000)
    parser.add_argument("--registrations", type=int, default=25000)
    parser.add_argument("--completed-documents", type=int, default=2500)
    parser.add_argument(
        "--otp-ttl-hours",
        type=int,
        default=int(os.getenv("LOAD_TEST_OTP_TTL_HOURS", "12")),
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--purge-only", action="store_true")
    parser.add_argument("--confirm-loadtest-target", action="store_true")
    parser.add_argument("--env-file", default=".env.production")
    parser.add_argument(
        "--compose-file",
        action="append",
        default=[],
    )
    args = parser.parse_args()

    if not args.compose_file:
        args.compose_file = [
            "docker-compose.production.yml",
            "docker-compose.loadtest-target.yml",
        ]
    if min(
        args.citizens,
        args.auth_citizens,
        args.pending_per_stage,
        args.registrations,
        args.completed_documents,
        args.otp_ttl_hours,
    ) < 1:
        parser.error("Semua jumlah fixture harus lebih besar dari nol.")
    if args.auth_citizens < args.citizens:
        parser.error("--auth-citizens harus >= --citizens.")
    if args.service == "docker" and not args.confirm_loadtest_target:
        parser.error("--confirm-loadtest-target wajib diberikan.")
    if args.confirm_loadtest_target:
        os.environ["LOADTEST_SEED_CONFIRMED"] = "1"

    if args.service == "docker":
        purge_docker(args) if args.purge_only else prepare_docker(args)
    elif args.service == "auth":
        purge_auth() if args.purge_only else seed_auth(
            args.citizens,
            args.auth_citizens,
            args.manifest,
            args.otp_ttl_hours,
        )
    elif args.service == "citizen":
        purge_user_registration_data() if args.purge_only else seed_citizen(
            args.manifest,
            args.registrations,
        )
    elif args.service == "reporting":
        purge_reporting() if args.purge_only else seed_reporting(
            args.manifest,
            args.registrations,
        )
    elif args.service == "document":
        purge_document() if args.purge_only else seed_document(
            args.manifest,
            args.pending_per_stage,
            args.completed_documents,
        )


if __name__ == "__main__":
    main()
