from datetime import timedelta

from celery import shared_task
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import DashboardChartDaily, DashboardSummary, Notifikasi, ProcessedEvent, ProfileReadModel


ROLE_WARGA = 1
ROLE_RT = 2
ROLE_RW = 3
ROLE_KADES = 4
ROLE_ADMIN = 5


def _mark_processed(event):
    try:
        with transaction.atomic():
            ProcessedEvent.objects.create(event_id=event["event_id"], event_type=event["event_type"])
        return True
    except IntegrityError:
        return False


def _summary(scope_type, scope_id, peran):
    obj, _ = DashboardSummary.objects.get_or_create(
        scope_type=scope_type,
        scope_id=str(scope_id),
        peran=peran,
        defaults={"isi_cards_json": {}, "progress_json": {}},
    )
    return obj


def _inc_progress(summary, key, amount=1):
    progress = dict(summary.progress_json or {})
    progress[key] = max(0, int(progress.get(key, 0)) + amount)
    summary.progress_json = progress
    summary.save(update_fields=["progress_json", "updated_at"])


def _create_notification(penerima_user_id, tipe, judul, pesan, nomor_permohonan=None):
    if not penerima_user_id:
        return False

    if not nomor_permohonan:
        Notifikasi.objects.create(
            penerima_user_id=penerima_user_id,
            tipe=tipe,
            judul=judul,
            pesan=pesan,
        )
        return True

    _, created = Notifikasi.objects.get_or_create(
        penerima_user_id=penerima_user_id,
        tipe=tipe,
        permohonan_nomor=nomor_permohonan,
        defaults={
            "judul": judul,
            "pesan": pesan,
        },
    )
    return created


def _recipient_ids_for_role(role, *, rt=None, rw=None):
    queryset = ProfileReadModel.objects.filter(peran=role)

    if role == ROLE_RT and rt is not None:
        queryset = queryset.filter(rt=rt)
    elif role == ROLE_RW and rw is not None:
        queryset = queryset.filter(rw=rw)

    return list(queryset.values_list("user_id", flat=True))


def _notify_many(user_ids, tipe, judul, pesan, nomor_permohonan=None):
    created = 0
    for user_id in dict.fromkeys(user_ids):
        if _create_notification(user_id, tipe, judul, pesan, nomor_permohonan):
            created += 1
    return created


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def project_event(self, event):
    if not _mark_processed(event):
        return "event already projected"

    event_type = event["event_type"]
    data = event.get("data", {})

    if event_type in {"registrasi.approved", "penduduk.created"}:
        ProfileReadModel.objects.update_or_create(
            user_id=data["user_id"],
            defaults={
                "account_id": data.get("user_id"),
                "penduduk_id": data.get("penduduk_id"),
                "nik": data["nik"],
                "nomor_kk": data.get("nomor_kk"),
                "nama_lengkap": data.get("nama_lengkap", ""),
                "jenis_kelamin": data.get("jenis_kelamin"),
                "tempat_lahir": data.get("tempat_lahir"),
                "tanggal_lahir": data.get("tanggal_lahir"),
                "alamat": data.get("alamat"),
                "email": data.get("email", ""),
                "nomor_telepon": data.get("no_hp") or data.get("nomor_telepon"),
                "nip": data.get("nip"),
                "peran": data.get("peran", 1),
                "rt": data.get("rt"),
                "rw": data.get("rw"),
            },
        )
        for scope_type, scope_id, peran in [("rt", data.get("rt"), 2), ("rw", data.get("rw"), 3), ("desa", "all", 5), ("desa", "all", 4)]:
            summary = _summary(scope_type, scope_id or "unknown", peran)
            cards = dict(summary.isi_cards_json or {})
            cards["total_warga"] = int(cards.get("total_warga", 0)) + 1
            summary.isi_cards_json = cards
            summary.save(update_fields=["isi_cards_json", "updated_at"])

    elif event_type == "surat.created":
        tanggal = timezone.localdate()
        for scope_type, scope_id in [("rt", data.get("rt")), ("rw", data.get("rw")), ("desa", "all")]:
            chart, _ = DashboardChartDaily.objects.get_or_create(
                scope_type=scope_type,
                scope_id=str(scope_id or "unknown"),
                tanggal=tanggal,
            )
            chart.jumlah_pengajuan += 1
            chart.save(update_fields=["jumlah_pengajuan", "updated_at"])
        _inc_progress(_summary("rt", data.get("rt") or "unknown", 2), "menunggu_verifikasi_rt", 1)

    elif event_type == "surat.approved_by_rt":
        # Scope may be enriched by the outbox publisher later.
        for summary in DashboardSummary.objects.filter(peran=2):
            _inc_progress(summary, "menunggu_verifikasi_rt", -1)
            _inc_progress(summary, "disetujui_rt", 1)
        for summary in DashboardSummary.objects.filter(peran=3):
            _inc_progress(summary, "menunggu_verifikasi_rw", 1)

    elif event_type == "surat.approved_by_rw":
        for summary in DashboardSummary.objects.filter(peran=3):
            _inc_progress(summary, "menunggu_verifikasi_rw", -1)
            _inc_progress(summary, "disetujui_rw", 1)
        _inc_progress(_summary("desa", "all", 5), "menunggu_verifikasi_admin", 1)

    elif event_type == "surat.approved_by_admin":
        _inc_progress(_summary("desa", "all", 5), "menunggu_verifikasi_admin", -1)
        _inc_progress(_summary("desa", "all", 5), "disetujui_admin", 1)
        _inc_progress(_summary("desa", "all", 4), "menunggu_verifikasi_kades", 1)

    elif event_type == "surat.approved_by_kades":
        _inc_progress(_summary("desa", "all", 4), "menunggu_verifikasi_kades", -1)
        _inc_progress(_summary("desa", "all", 4), "disetujui_kades", 1)

    return f"projected {event_type}"


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def create_notification_from_event(self, event):
    event_type = event["event_type"]
    data = event.get("data", {})
    nomor = data.get("nomor_permohonan")
    jenis = data.get("jenis_surat_nama") or "surat"
    pemohon = data.get("pemohon_nama") or data.get("pemohon_nik") or "warga"
    created = 0

    if event_type == "surat.created":
        created += _notify_many(
            [data.get("pemohon_user_id")],
            "surat.created.receipt",
            "Pengajuan Surat Diterima",
            f"Pengajuan {jenis} nomor {nomor} sudah diterima dan menunggu verifikasi RT.",
            nomor,
        )
        created += _notify_many(
            _recipient_ids_for_role(ROLE_RT, rt=data.get("rt")),
            "surat.needs_rt_approval",
            "Pengajuan Surat Perlu Verifikasi RT",
            f"Ada pengajuan {jenis} dari {pemohon} yang perlu Anda verifikasi.",
            nomor,
        )

    elif event_type == "surat.approved_by_rt":
        created += _notify_many(
            [data.get("pemohon_user_id")],
            "surat.approved_by_rt",
            "Pengajuan Disetujui RT",
            f"Pengajuan {jenis} nomor {nomor} sudah disetujui RT dan diteruskan ke RW.",
            nomor,
        )
        created += _notify_many(
            _recipient_ids_for_role(ROLE_RW, rw=data.get("rw")),
            "surat.needs_rw_approval",
            "Pengajuan Surat Perlu Verifikasi RW",
            f"Pengajuan {jenis} dari {pemohon} sudah disetujui RT dan perlu verifikasi RW.",
            nomor,
        )

    elif event_type == "surat.approved_by_rw":
        created += _notify_many(
            [data.get("pemohon_user_id")],
            "surat.approved_by_rw",
            "Pengajuan Disetujui RW",
            f"Pengajuan {jenis} nomor {nomor} sudah disetujui RW dan diteruskan ke admin desa.",
            nomor,
        )
        created += _notify_many(
            _recipient_ids_for_role(ROLE_ADMIN),
            "surat.needs_admin_approval",
            "Pengajuan Surat Perlu Verifikasi Admin",
            f"Pengajuan {jenis} dari {pemohon} sudah disetujui RW dan perlu verifikasi admin.",
            nomor,
        )

    elif event_type == "surat.approved_by_admin":
        created += _notify_many(
            [data.get("pemohon_user_id")],
            "surat.approved_by_admin",
            "Pengajuan Divalidasi Admin",
            f"Pengajuan {jenis} nomor {nomor} sudah divalidasi admin dan diteruskan ke kepala desa.",
            nomor,
        )
        created += _notify_many(
            _recipient_ids_for_role(ROLE_KADES),
            "surat.needs_kades_approval",
            "Pengajuan Surat Perlu Persetujuan Kades",
            f"Pengajuan {jenis} dari {pemohon} sudah diverifikasi admin dan perlu persetujuan kepala desa.",
            nomor,
        )

    elif event_type == "document.generated":
        created += _notify_many(
            [data.get("pemohon_user_id")],
            "surat.completed",
            "Surat Selesai",
            f"{jenis} nomor {nomor} sudah jadi dan dapat diunduh.",
            nomor,
        )

    elif event_type == "surat.rejected":
        created += _notify_many(
            [data.get("pemohon_user_id")],
            "surat.rejected",
            "Pengajuan Surat Ditolak",
            f"Pengajuan {jenis} nomor {nomor} ditolak pada tahap {data.get('tahap')}.",
            nomor,
        )

    elif event_type in {"registrasi.approved", "registrasi.rejected"}:
        judul = "Pendaftaran Disetujui" if event_type == "registrasi.approved" else "Pendaftaran Ditolak"
        pesan = data.get("message") or f"{judul}."
        created += _notify_many([data.get("user_id")], event_type, judul, pesan)

    return f"{created} notification(s) created for {event_type}"
