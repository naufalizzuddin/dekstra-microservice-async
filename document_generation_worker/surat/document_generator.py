import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import qrcode
from django.conf import settings
from django.utils import timezone
from django.utils.formats import date_format
from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage

from .helpers import (
    generate_b01_excel,
    generate_b02_excel,
    generate_b03_excel,
    generate_b04_excel,
    generate_b05_excel,
    generate_b09_excel,
)


EXCEL_GENERATORS = {
    "B01": generate_b01_excel,
    "B02": generate_b02_excel,
    "B03": generate_b03_excel,
    "B04": generate_b04_excel,
    "B05": generate_b05_excel,
    "B09": generate_b09_excel,
}

WILAYAH_DEFAULTS = {
    "nama_desa": "MIROTO",
    "nama_kelurahan_desa": "MIROTO",
    "nama_kecamatan": "GANTIWARNO",
    "nama_kabupaten": "SRAGEN",
    "nama_kabupaten_kota": "SRAGEN",
    "nama_provinsi": "JAWA TENGAH",
    "tempat_ttd": "SRAGEN",
}


class DocumentGenerationError(Exception):
    pass


def fetch_kepala_desa_profile():
    base_url = getattr(settings, "REPORTING_SERVICE_URL", "")
    if not base_url:
        return {}

    url = f"{base_url.rstrip('/')}/internal/pejabat/kepala-desa/"
    try:
        with urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return {}

    return {
        "nama_lengkap": data.get("nama_lengkap"),
        "nip": data.get("nip"),
    }


def resolve_template_path(jenis_surat):
    if jenis_surat.template_file and getattr(jenis_surat.template_file, "path", None):
        path = Path(jenis_surat.template_file.path)
        if path.exists():
            return path

    template_dir = Path(getattr(settings, "TEMPLATE_SURAT_DIR", "/template_surat"))
    matches = sorted(template_dir.glob(f"{jenis_surat.kode} -*"))
    if not matches:
        raise DocumentGenerationError(f"Template untuk kode {jenis_surat.kode} tidak ditemukan.")
    return matches[0]


def build_context(permohonan, dokumen):
    raw = dict(permohonan.data or {})
    now = timezone.localtime()
    signed_at = date_format(now, format="j F Y")
    kades_profile = fetch_kepala_desa_profile()
    kades_name = kades_profile.get("nama_lengkap") or getattr(settings, "KEPALA_DESA_NAMA", "Kepala Desa")
    kades_nip = kades_profile.get("nip") or getattr(settings, "KEPALA_DESA_NIP", "-")

    context = {
        **WILAYAH_DEFAULTS,
        **raw,
        "nomor_surat": permohonan.nomor_permohonan,
        "nomor_permohonan": permohonan.nomor_permohonan,
        "nik": raw.get("nik") or permohonan.pemohon_nik_snapshot,
        "nama_lengkap": raw.get("nama_lengkap") or raw.get("pemohon_nama") or permohonan.pemohon_nama_snapshot,
        "nama_pemohon": raw.get("nama_pemohon") or raw.get("pemohon_nama") or permohonan.pemohon_nama_snapshot,
        "rt": raw.get("rt") or permohonan.pemohon_rt_snapshot,
        "rw": raw.get("rw") or permohonan.pemohon_rw_snapshot,
        "nama_kades": raw.get("nama_kades") or raw.get("nama_kepala_desa") or kades_name,
        "nama_kepala_desa": raw.get("nama_kepala_desa") or raw.get("nama_kades") or kades_name,
        "nip": raw.get("nip") or raw.get("nip_kades") or raw.get("nip_kepala_desa") or kades_nip,
        "nip_kades": raw.get("nip_kades") or raw.get("nip") or raw.get("nip_kepala_desa") or kades_nip,
        "nip_kepala_desa": raw.get("nip_kepala_desa") or raw.get("nip") or raw.get("nip_kades") or kades_nip,
        "signed_at": raw.get("signed_at") or signed_at,
        "tanggal": raw.get("tanggal") or signed_at,
        "tanggal_ttd": raw.get("tanggal_ttd") or now.strftime("%Y-%m-%d"),
        "tanggal_lokasi": raw.get("tanggal_lokasi") or f"{raw.get('tempat_ttd') or WILAYAH_DEFAULTS['tempat_ttd']}, {signed_at}",
        "qr_text": raw.get("qr_text") or str(dokumen.public_token),
        "qr_ttd": raw.get("qr_ttd") or str(dokumen.public_token),
    }
    return context


def complete_docx_context(doc, context):
    completed = dict(context)
    for key in doc.get_undeclared_template_variables():
        completed.setdefault(key, "")
    return completed


def qr_png_buffer(data):
    qr = qrcode.make(data=data)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def libreoffice_binary():
    configured = getattr(settings, "LIBREOFFICE_BIN", "soffice")
    return shutil.which(configured) or shutil.which("soffice") or shutil.which("libreoffice")


def convert_to_pdf(input_path):
    binary = libreoffice_binary()
    if not binary:
        return None

    input_path = Path(input_path)
    with tempfile.TemporaryDirectory() as outdir:
        result = subprocess.run(
            [
                binary,
                "--headless",
                "--nologo",
                "--nolockcheck",
                "--nodefault",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                outdir,
                str(input_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=getattr(settings, "LIBREOFFICE_TIMEOUT_SECONDS", 60),
            check=False,
        )
        if result.returncode != 0:
            raise DocumentGenerationError(
                "Konversi PDF gagal:\n"
                f"STDOUT:\n{result.stdout.decode(errors='ignore')}\n"
                f"STDERR:\n{result.stderr.decode(errors='ignore')}"
            )

        pdf_path = Path(outdir) / f"{input_path.stem}.pdf"
        if not pdf_path.exists():
            raise DocumentGenerationError("PDF tidak terbentuk setelah konversi LibreOffice.")
        return pdf_path.read_bytes()


def render_docx(template_path, context):
    doc = DocxTemplate(str(template_path))
    qr_buffer = qr_png_buffer(context["qr_text"])
    context = complete_docx_context(doc, context)
    context["ttd_img"] = InlineImage(doc, qr_buffer, width=Mm(30))

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "surat.docx"
        doc.render(context)
        doc.save(docx_path)

        pdf_bytes = convert_to_pdf(docx_path)
        if pdf_bytes is not None:
            return pdf_bytes, "pdf"
        return docx_path.read_bytes(), "docx"


def render_xlsx(template_path, context, kode_surat):
    generator = EXCEL_GENERATORS.get(kode_surat)
    if not generator:
        raise DocumentGenerationError(f"Generator Excel untuk {kode_surat} belum tersedia.")

    excel_bytes = generator(str(template_path), context)
    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx_path = Path(tmpdir) / "surat.xlsx"
        xlsx_path.write_bytes(excel_bytes)

        pdf_bytes = convert_to_pdf(xlsx_path)
        if pdf_bytes is not None:
            return pdf_bytes, "pdf"
        return excel_bytes, "xlsx"


def generate_final_document(permohonan, dokumen):
    template_path = resolve_template_path(permohonan.jenis_surat)
    context = build_context(permohonan, dokumen)
    ext = template_path.suffix.lower()

    if ext == ".docx":
        return render_docx(template_path, context)
    if ext == ".xlsx":
        return render_xlsx(template_path, context, permohonan.jenis_surat.kode)
    raise DocumentGenerationError(f"Ekstensi template {ext} belum didukung.")
