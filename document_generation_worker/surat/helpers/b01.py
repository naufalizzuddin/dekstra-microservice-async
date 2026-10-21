from copy import copy
from datetime import datetime
import io
import os
import tempfile

import qrcode
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import range_boundaries


SHEET_NAME = "Sheet1"


# =========================================================
# DEFAULT VALUE
# =========================================================
DEFAULT_WILAYAH = {
    "nama_provinsi": "JAWA TENGAH",
    "nama_kabupaten_kota": "SRAGEN",
    "nama_kecamatan": "GANTIWARNO",
    "nama_kelurahan_desa": "MIROTO",
    "nama_dusun_dukuh_kampung": "",
    "nama_ketua_rt": "",
    "nama_ketua_rw": "",
    "nama_kepala_desa": "",
    "nip_kepala_desa": "",
    "tempat_ttd": "SRAGEN",
    "tanggal_ttd": "",
}


# =========================================================
# BACKEND STATIC CODE
# =========================================================
BACKEND_STATIC = {
    "kode_provinsi": "33",
    "kode_kabupaten_kota": "3314",
    "kode_kecamatan": "12",
    "kode_kelurahan_desa": "01",
}


# =========================================================
# STYLE
# =========================================================
STATIC_FILL = PatternFill(fill_type="solid", fgColor="D9D9D9")
SELECTED_FILL = PatternFill(fill_type="solid", fgColor="FFF2CC")
NORMAL_FONT = Font(bold=False)
SELECTED_FONT = Font(bold=True)

CENTER = Alignment(horizontal="center", vertical="bottom")
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center", wrap_text=True)


# =========================================================
# MAPPING
# =========================================================
JENIS_KELAMIN_MAP = {
    "laki-laki": 1,
    "perempuan": 2,
}

JENIS_GELAR_MAP = {
    "akademis": 1,
    "kebangsawanan": 2,
    "keagamaan": 3,
}

AKTA_MAP = {
    "tidak-ada": 1,
    "ada": 2,
    "tidak": 1,
    "ya": 2,
    True: 2,
    False: 1,
}

GOLONGAN_DARAH_MAP = {
    "a": 1,
    "b": 2,
    "ab": 3,
    "o": 4,
    "a+": 5,
    "a-": 6,   # legacy support
    "b+": 7,
    "b-": 8,
    "ab+": 9,
    "ab-": 10,
    "o+": 11,
    "o-": 12,
    "tidak-tahu": 13,
}

AGAMA_MAP = {
    "islam": 1,
    "kristen": 2,
    "katolik": 3,
    "hindu": 4,
    "buddha": 5,
    "konghucu": 6,
    "kepercayaan": 7,  # legacy support
}

STATUS_PERKAWINAN_MAP = {
    "belum-kawin": 1,
    "kawin": 2,
    "cerai-hidup": 3,
    "cerai-mati": 4,
}

STATUS_HUBUNGAN_KELUARGA_MAP = {
    "kepala-keluarga": 1,
    "suami": 2,
    "istri": 3,
    "anak": 4,
    "menantu": 5,
    "cucu": 6,
    "orang-tua": 7,
    "mertua": 8,
    "famili": 9,
    "famili-lain": 9,  # legacy support
    "pembantu": 10,
    "lainnya": 11,
}

KELAINAN_FISIK_MENTAL_MAP = {
    "tidak-ada": 1,
    "ada": 2,
}

PENYANDANG_CACAT_MAP = {
    "tidak-ada": 1,
    "cacat-fisik": 2,
    "cacat-netra": 3,
    "cacat-netra-buta": 3,       # legacy support
    "cacat-rungu-wicara": 4,
    "cacat-mental": 5,
    "cacat-mental-jiwa": 5,      # legacy support
    "cacat-fisik-mental": 6,
    "cacat-fisik-dan-mental": 6, # legacy support
    "cacat-lainnya": 6,          # fallback karena template hanya punya 6 pilihan
}

PENDIDIKAN_TERAKHIR_MAP = {
    "tidak-belum-sekolah": 1,
    "belum-tamat-sd": 2,
    "belum-tamat-sd-sederajat": 2,
    "tamat-sd": 3,
    "tamat-sd-sederajat": 3,
    "sltp": 4,
    "sltp-sederajat": 4,
    "slta": 5,
    "slta-sederajat": 5,
    "diploma-1-2": 6,
    "d1-d2": 6,
    "diploma-3": 7,
    "d3": 7,
    "diploma-4-s1": 8,
    "d4": 8,
    "s1": 8,
    "s2": 9,
    "s3": 10,
}

PEKERJAAN_KEYS = [
    "belum-tidak-bekerja",
    "mengurus-rumah-tangga",
    "pelajar-mahasiswa",
    "pensiunan",

    "pegawai-negeri-sipil-pns",
    "tentara-nasional-indonesia-tni",
    "kepolisian-ri-polri",

    "perdagangan",
    "petani-pekebun",
    "peternak",
    "nelayan-perikanan",
    "industri",
    "konstruksi",
    "transportasi",
    "karyawan-swasta",
    "karyawan-bumn",
    "karyawan-bumd",
    "karyawan-honorer",

    "buruh-harian-lepas",
    "buruh-tani-perkebunan",
    "buruh-nelayan-perikanan",
    "buruh-peternakan",
    "pembantu-rumah-tangga",

    "tukang-cukur",
    "tukang-listrik",
    "tukang-batu",
    "tukang-kayu",
    "tukang-sol-sepatu",
    "tukang-las-pandan",
    "tukang-jahit",
    "penata-rambut",
    "penata-rias",
    "penata-busana",

    "mekanik",
    "seniman",
    "tabib",
    "paraji",
    "perancang-busana",
    "penterjemah",
    "imam-masjid",
    "pendeta",
    "pastor",
    "wartawan",
    "ustadz-mubaligh",
    "juru-masak",
    "promotor-acara",
    "anggota-dpr-ri",
    "anggota-dpd",
    "anggota-bpk",
    "presiden",
    "wakil-presiden",
    "anggota-mahkamah-konstitusi",
    "anggota-kabinet-kementerian",
    "duta-besar",
    "gubernur",
    "wakil-gubernur",
    "bupati",
    "wakil-bupati",
    "walikota",
    "wakil-walikota",
    "anggota-dprd-provinsi",
    "anggota-dprd-kabupaten-kota",
    "dosen",
    "guru",
    "pilot",
    "pengacara",
    "notaris",
    "arsitek",
    "akuntan",
    "konsultan",
    "dokter",
    "bidan",
    "perawat",
    "apoteker",
    "psikiater-psikolog",
    "penyiar-televisi",
    "penyiar-radio",
    "pelaut",
    "peneliti",
    "sopir",
    "pialang",
    "paranormal",
    "pedagang",
    "perangkat-desa",
    "kepala-desa",
    "biarawati",
    "wiraswasta",

    "lainnya",
]

PEKERJAAN_MAP = {
    key: idx for idx, key in enumerate(PEKERJAAN_KEYS, start=1)
}


# =========================================================
# CELL MAPPING
# =========================================================
HEADER_CELLS = {
    "nama_kepala_keluarga": "J8",
    "alamat": "J10",
    "kode_pos": "J12",
    "rt": "R12",
    "rw": "X12",
    "jumlah_anggota_keluarga": "AJ12",
    "telepon": "J14",
    "provinsi": "CE6",
    "kabupaten_kota": "CE8",
    "kecamatan": "CE10",
    "kelurahan_desa": "CE12",
    "dusun_dukuh_kampung": "CA14",
    "nama_ketua_rt": "J59",
    "nama_ketua_rw": "J62",
}

TTD_CELLS = {
    "tanggal_ttd": "DE59",
    "nama_kepala_desa": "CL67",
    "nip_kepala_desa": "CL68",
    "nama_kepala_keluarga_ttd": "DF68"
}

STATIC_CODE_CELLS = {
    "kode_provinsi": "CA6",
    "kode_kabupaten_kota": "CA8",
    "kode_kecamatan": "CA10",
    "kode_kelurahan_desa": "CA12",
}

ROW_PART1 = list(range(20, 30))
ROW_PART2 = list(range(34, 44))
ROW_PART3 = list(range(48, 58))


# =========================================================
# HELPER
# =========================================================
def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_key(value):
    return normalize_text(value).lower()


def safe_default(value, default_value=""):
    value = normalize_text(value)
    return value if value else default_value


def map_value(value, mapper, default=""):
    return mapper.get(normalize_key(value), default)


def normalize_date(value):
    value = normalize_text(value)
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return value

def format_golongan_darah(value):
    value = normalize_key(value)
    display_map = {
        "a": "A",
        "b": "B",
        "ab": "AB",
        "o": "O",
        "a+": "A+",
        "a-": "A-",
        "b+": "B+",
        "b-": "B-",
        "ab+": "AB+",
        "ab-": "AB-",
        "o+": "O+",
        "o-": "O-",
        "tidak-tahu": "TIDAK TAHU",
    }
    return display_map.get(value, normalize_text(value).upper())

def format_tanggal_ttd(tempat, tanggal):
    tempat = normalize_text(tempat)
    tanggal = normalize_date(tanggal)

    if tempat and tanggal:
        return f"{tempat}, {tanggal}"
    if tanggal:
        return tanggal
    if tempat:
        return tempat
    return ""

def build_nama_dengan_gelar(
    nama_lengkap,
    jenis_gelar="",
    isi_gelar="",
    gelar_akademis="",
    gelar_kebangsawanan="",
    gelar_keagamaan="",
):
    nama_lengkap = normalize_text(nama_lengkap)

    prefixes = []
    suffixes = []

    # Format baru
    jenis_gelar = normalize_key(jenis_gelar)
    isi_gelar = normalize_text(isi_gelar)

    if jenis_gelar and jenis_gelar != "tidak-ada" and isi_gelar:
        if jenis_gelar in ("kebangsawanan", "keagamaan"):
            prefixes.append(isi_gelar)
        elif jenis_gelar == "akademis":
            suffixes.append(isi_gelar)

    # Fallback / kompatibilitas format lama
    old_kebangsawanan = normalize_text(gelar_kebangsawanan)
    old_keagamaan = normalize_text(gelar_keagamaan)
    old_akademis = normalize_text(gelar_akademis)

    if old_kebangsawanan and old_kebangsawanan not in prefixes:
        prefixes.append(old_kebangsawanan)

    if old_keagamaan and old_keagamaan not in prefixes:
        prefixes.append(old_keagamaan)

    if old_akademis and old_akademis not in suffixes:
        suffixes.append(old_akademis)

    hasil = nama_lengkap
    if prefixes:
        hasil = f"{' '.join(prefixes)} {hasil}".strip()
    if suffixes:
        hasil = f"{hasil}, {', '.join(suffixes)}".strip()

    return hasil

def resolve_jenis_gelar(
    jenis_gelar="",
    gelar_akademis="",
    gelar_kebangsawanan="",
    gelar_keagamaan="",
):
    jenis_gelar = normalize_key(jenis_gelar)

    if jenis_gelar in JENIS_GELAR_MAP:
        return jenis_gelar

    if normalize_text(gelar_akademis):
        return "akademis"
    if normalize_text(gelar_kebangsawanan):
        return "kebangsawanan"
    if normalize_text(gelar_keagamaan):
        return "keagamaan"

    return ""

def resolve_merged_cell_ref(ws, cell_ref):
    for merged_range in ws.merged_cells.ranges:
        if cell_ref in merged_range:
            min_col, min_row, max_col, max_row = range_boundaries(str(merged_range))
            return ws.cell(row=min_row, column=min_col).coordinate
    return cell_ref


def set_value(ws, cell_ref, value, align=None):
    if value is None or value == "":
        return
    real_cell_ref = resolve_merged_cell_ref(ws, cell_ref)
    ws[real_cell_ref] = value
    if align:
        ws[real_cell_ref].alignment = copy(align)


def fill_text_block(ws, cell_ref, value, align=LEFT):
    if value is None or value == "":
        return
    real_cell_ref = resolve_merged_cell_ref(ws, cell_ref)
    ws[real_cell_ref] = value
    ws[real_cell_ref].alignment = copy(align)


def fill_static_code_cell(ws, cell_ref, value):
    if value is None or value == "":
        return
    real_cell_ref = resolve_merged_cell_ref(ws, cell_ref)
    ws[real_cell_ref] = value
    ws[real_cell_ref].alignment = copy(CENTER)
    ws[real_cell_ref].fill = copy(STATIC_FILL)
    ws[real_cell_ref].font = copy(NORMAL_FONT)


def choose_from_map(ws, code, code_map):
    if code in code_map:
        target = code_map[code]
        real_target = resolve_merged_cell_ref(ws, target)
        ws[real_target].fill = copy(SELECTED_FILL)
        ws[real_target].font = copy(SELECTED_FONT)
        ws[real_target].alignment = copy(CENTER)


def normalize_anggota_list(anggota_list, total=10):
    anggota_list = list(anggota_list[:total])
    while len(anggota_list) < total:
        anggota_list.append({})
    return anggota_list


def create_qr_image_file(text):
    if not text:
        return None

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    temp_file.close()

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=1,
    )
    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img.save(temp_file.name)
    return temp_file.name


def add_qr_to_sheet(ws, image_path, anchor_cell="CO62", width=110, height=110):
    if not image_path or not os.path.exists(image_path):
        return

    img = XLImage(image_path)
    img.width = width
    img.height = height
    img.anchor = anchor_cell
    ws.add_image(img)


# =========================================================
# TRANSFORM RAW JSON
# =========================================================
def transform_raw_to_data(raw):
    anggota_raw = raw.get("anggota_keluarga", [])

    nama_provinsi = safe_default(raw.get("nama_provinsi"), DEFAULT_WILAYAH["nama_provinsi"])
    nama_kabupaten_kota = safe_default(raw.get("nama_kabupaten_kota"), DEFAULT_WILAYAH["nama_kabupaten_kota"])
    nama_kecamatan = safe_default(raw.get("nama_kecamatan"), DEFAULT_WILAYAH["nama_kecamatan"])
    nama_kelurahan_desa = safe_default(raw.get("nama_kelurahan_desa"), DEFAULT_WILAYAH["nama_kelurahan_desa"])
    nama_dusun_dukuh_kampung = safe_default(
        raw.get("nama_dusun_dukuh_kampung"),
        DEFAULT_WILAYAH["nama_dusun_dukuh_kampung"]
    )

    nama_ketua_rt = safe_default(raw.get("nama_ketua_rt"), DEFAULT_WILAYAH["nama_ketua_rt"])
    nama_ketua_rw = safe_default(raw.get("nama_ketua_rw"), DEFAULT_WILAYAH["nama_ketua_rw"])
    nama_kepala_desa = safe_default(raw.get("nama_kepala_desa"), DEFAULT_WILAYAH["nama_kepala_desa"])
    nip_kepala_desa = safe_default(raw.get("nip_kepala_desa"), DEFAULT_WILAYAH["nip_kepala_desa"])
    tempat_ttd = safe_default(raw.get("tempat_ttd"), DEFAULT_WILAYAH["tempat_ttd"])
    tanggal_ttd = safe_default(raw.get("tanggal_ttd"), DEFAULT_WILAYAH["tanggal_ttd"])

    anggota_transformed = []
    for anggota in anggota_raw:
        jenis_gelar = anggota.get("jenis_gelar", "")
        isi_gelar = anggota.get("isi_gelar", "")

        # kompatibilitas format lama
        gelar_akademis = anggota.get("gelar_akademis", "")
        gelar_kebangsawanan = anggota.get("gelar_kebangsawanan", "")
        gelar_keagamaan = anggota.get("gelar_keagamaan", "")

        resolved_jenis_gelar = resolve_jenis_gelar(
            jenis_gelar=jenis_gelar,
            gelar_akademis=gelar_akademis,
            gelar_kebangsawanan=gelar_kebangsawanan,
            gelar_keagamaan=gelar_keagamaan,
        )

        nama_tampil = build_nama_dengan_gelar(
            nama_lengkap=anggota.get("nama_lengkap", ""),
            jenis_gelar=jenis_gelar,
            isi_gelar=isi_gelar,
            gelar_akademis=gelar_akademis,
            gelar_kebangsawanan=gelar_kebangsawanan,
            gelar_keagamaan=gelar_keagamaan,
        )

        transformed = {
            "nama_lengkap": nama_tampil,
            "jenis_gelar": resolved_jenis_gelar,

            # tetap disimpan untuk kompatibilitas
            "gelar_akademis": isi_gelar if normalize_key(jenis_gelar) == "akademis" else gelar_akademis,
            "gelar_kebangsawanan": isi_gelar if normalize_key(jenis_gelar) == "kebangsawanan" else gelar_kebangsawanan,
            "gelar_keagamaan": isi_gelar if normalize_key(jenis_gelar) == "keagamaan" else gelar_keagamaan,

            "nomor_ktp_nopen": anggota.get("no_ktp", ""),
            "alamat_sebelumnya": anggota.get("alamat_sebelumnya", ""),
            "nomor_paspor": anggota.get("nomor_paspor", ""),
            "tanggal_berakhir_paspor": normalize_date(anggota.get("tanggal_berakhir_paspor", "")),
            "jenis_kelamin": map_value(anggota.get("jenis_kelamin"), JENIS_KELAMIN_MAP, ""),
            "tempat_lahir": anggota.get("tempat_lahir", ""),
            "tanggal_lahir": normalize_date(anggota.get("tanggal_lahir", "")),
            "umur": anggota.get("umur", ""),
            "akta_lahir": map_value(anggota.get("akta_lahir"), AKTA_MAP, ""),
            "nomor_akta_kelahiran": anggota.get("nomor_akta_kelahiran", ""),
            "golongan_darah": format_golongan_darah(anggota.get("golongan_darah", "")),
            "agama": map_value(anggota.get("agama"), AGAMA_MAP, ""),
            "kepercayaan_terhadap_tuhan_yme": "",
            "status_perkawinan": map_value(anggota.get("status_perkawinan"), STATUS_PERKAWINAN_MAP, ""),
            "akta_perkawinan_buku_nikah": map_value(anggota.get("akta_perkawinan", "tidak-ada"), AKTA_MAP, 1),
            "nomor_akta_perkawinan": anggota.get("nomor_akta_perkawinan", ""),
            "tanggal_perkawinan": normalize_date(anggota.get("tanggal_perkawinan", "")),
            "akta_cerai_surat_cerai": map_value(anggota.get("akta_perceraian", "tidak-ada"), AKTA_MAP, 1),
            "nomor_akta_perceraian": anggota.get("nomor_akta_perceraian", ""),
            "tanggal_perceraian": normalize_date(anggota.get("tanggal_perceraian", "")),
            "status_hubungan_dalam_keluarga": map_value(
                anggota.get("status_hubungan_keluarga"),
                STATUS_HUBUNGAN_KELUARGA_MAP,
                ""
            ),
            "kelainan_fisik_mental": map_value(
                anggota.get("kelainan_fisik_mental"),
                KELAINAN_FISIK_MENTAL_MAP,
                ""
            ),
            "penyandang_cacat": map_value(
                anggota.get("penyandang_cacat", "tidak-ada"),
                PENYANDANG_CACAT_MAP,
                1
            ),
            "pendidikan_terakhir": map_value(
                anggota.get("pendidikan_terakhir"),
                PENDIDIKAN_TERAKHIR_MAP,
                ""
            ),
            "pekerjaan": map_value(anggota.get("pekerjaan"), PEKERJAAN_MAP, ""),
            "pekerjaan_lainnya": anggota.get("pekerjaan_lainnya", ""),
            "nik_ibu": anggota.get("nik_ibu", ""),
            "nama_lengkap_ibu": anggota.get("nama_ibu", ""),
            "nik_ayah": anggota.get("nik_ayah", ""),
            "nama_lengkap_ayah": anggota.get("nama_ayah", ""),
        }
        anggota_transformed.append(transformed)

    qr_text = safe_default(raw.get("qr_ttd"), "")
    if not qr_text and nama_kepala_desa:
        qr_text = f"Ditandatangani secara elektronik oleh Kepala Desa {nama_kepala_desa}"
        if nip_kepala_desa:
            qr_text += f", NIP {nip_kepala_desa}"

    return {
        "kepala_keluarga": {
            "nama_kepala_keluarga": raw.get("nama_kepala_keluarga", ""),
            "alamat": raw.get("alamat", ""),
            "kode_pos": raw.get("kode_pos", ""),
            "rt": raw.get("rt", ""),
            "rw": raw.get("rw", ""),
            "jumlah_anggota_keluarga": len(anggota_raw),
            "telepon": raw.get("nomor_telepon", ""),
            "provinsi": nama_provinsi,
            "kabupaten_kota": nama_kabupaten_kota,
            "kecamatan": nama_kecamatan,
            "kelurahan_desa": nama_kelurahan_desa,
            "dusun_dukuh_kampung": nama_dusun_dukuh_kampung,
            "nama_ketua_rt": nama_ketua_rt,
            "nama_ketua_rw": nama_ketua_rw,
        },
        "anggota_keluarga": anggota_transformed,
        "ttd": {
            "tanggal_ttd_display": format_tanggal_ttd(tempat_ttd, tanggal_ttd),
            "nama_lengkap_kepala_desa": nama_kepala_desa,
            "nip_kepala_desa": f"NIP. {nip_kepala_desa}",
            "nama_kepala_keluarga": raw.get("nama_kepala_keluarga", ""),
            "qr_text": qr_text,
        }
    }

# =========================================================
# FILL DATA
# =========================================================
def fill_anggota_part1(ws, row, anggota):
    fill_text_block(ws, f"B{row}", anggota.get("nama_lengkap", ""))

    choose_from_map(ws, map_value(anggota.get("jenis_gelar"), JENIS_GELAR_MAP, ""), {
        1: f"BJ{row}",  # akademis
        2: f"BK{row}",  # kebangsawanan
        3: f"BL{row}",  # keagamaan
    })

    fill_text_block(ws, f"BM{row}", anggota.get("nomor_ktp_nopen", ""))
    fill_text_block(ws, f"CC{row}", anggota.get("alamat_sebelumnya", ""))
    fill_text_block(ws, f"DA{row}", anggota.get("nomor_paspor", ""))
    fill_text_block(ws, f"DJ{row}", anggota.get("tanggal_berakhir_paspor", ""))


def fill_anggota_part2(ws, row, anggota):
    choose_from_map(ws, anggota.get("jenis_kelamin"), {
        1: f"B{row}",
        2: f"D{row}",
    })

    fill_text_block(ws, f"F{row}", anggota.get("tempat_lahir", ""))
    fill_text_block(ws, f"AH{row}", anggota.get("tanggal_lahir", ""))
    set_value(ws, f"AP{row}", anggota.get("umur", ""), CENTER)

    choose_from_map(ws, anggota.get("akta_lahir"), {
        1: f"AS{row}",
        2: f"AU{row}",
    })
    fill_text_block(ws, f"AW{row}", anggota.get("nomor_akta_kelahiran", ""))

    # Template asli: golongan darah adalah teks di kolom BE:BH
    fill_text_block(ws, f"BE{row}", anggota.get("golongan_darah", ""), CENTER)

    # Template asli: agama adalah pilihan 1-7 di BI:BO
    choose_from_map(ws, anggota.get("agama"), {
        1: f"BI{row}",
        2: f"BJ{row}",
        3: f"BK{row}",
        4: f"BL{row}",
        5: f"BM{row}",
        6: f"BN{row}",
        7: f"BO{row}",
    })

    fill_text_block(ws, f"BP{row}", anggota.get("kepercayaan_terhadap_tuhan_yme", ""))

    choose_from_map(ws, anggota.get("status_perkawinan"), {
        1: f"BY{row}",
        2: f"BZ{row}",
        3: f"CA{row}",
        4: f"CB{row}",
    })

    choose_from_map(ws, anggota.get("akta_perkawinan_buku_nikah"), {
        1: f"CC{row}",
        2: f"CE{row}",
    })
    fill_text_block(ws, f"CG{row}", anggota.get("nomor_akta_perkawinan", ""))
    fill_text_block(ws, f"CP{row}", anggota.get("tanggal_perkawinan", ""))

    choose_from_map(ws, anggota.get("akta_cerai_surat_cerai"), {
        1: f"CX{row}",
        2: f"CZ{row}",
    })
    fill_text_block(ws, f"DB{row}", anggota.get("nomor_akta_perceraian", ""))
    fill_text_block(ws, f"DJ{row}", anggota.get("tanggal_perceraian", ""))

def fill_anggota_part3(ws, row, anggota):
    set_value(ws, f"B{row}", anggota.get("status_hubungan_dalam_keluarga", ""), CENTER)

    choose_from_map(ws, anggota.get("kelainan_fisik_mental"), {
        1: f"F{row}",
        2: f"H{row}",
    })

    choose_from_map(ws, anggota.get("penyandang_cacat"), {
        1: f"J{row}",
        2: f"L{row}",
        3: f"N{row}",
        4: f"P{row}",
        5: f"R{row}",
        6: f"T{row}",
    })

    choose_from_map(ws, anggota.get("pendidikan_terakhir"), {
        1: f"V{row}",
        2: f"X{row}",
        3: f"Z{row}",
        4: f"AB{row}",
        5: f"AD{row}",
        6: f"AF{row}",
        7: f"AH{row}",
        8: f"AJ{row}",
        9: f"AL{row}",
        10: f"AN{row}",
    })

    set_value(ws, f"AP{row}", anggota.get("pekerjaan", ""), CENTER)

    fill_text_block(ws, f"AT{row}", anggota.get("nik_ibu", ""))
    fill_text_block(ws, f"BJ{row}", anggota.get("nama_lengkap_ibu", ""))
    fill_text_block(ws, f"CE{row}", anggota.get("nik_ayah", ""))
    fill_text_block(ws, f"CU{row}", anggota.get("nama_lengkap_ayah", ""))


def fill_header(ws, header):
    for key, cell_ref in HEADER_CELLS.items():
        fill_text_block(ws, cell_ref, header.get(key, ""))


def fill_backend_static_codes(ws):
    for key, cell_ref in STATIC_CODE_CELLS.items():
        value = BACKEND_STATIC.get(key, "")
        fill_static_code_cell(ws, cell_ref, value)


def fill_ttd(ws, data_ttd):
    fill_text_block(ws, TTD_CELLS["tanggal_ttd"], data_ttd.get("tanggal_ttd_display", ""), RIGHT)
    fill_text_block(ws, TTD_CELLS["nama_kepala_desa"], data_ttd.get("nama_lengkap_kepala_desa", ""), CENTER)
    fill_text_block(ws, TTD_CELLS["nip_kepala_desa"], data_ttd.get("nip_kepala_desa", ""), CENTER)
    fill_text_block(ws, TTD_CELLS["nama_kepala_keluarga_ttd"], data_ttd.get("nama_kepala_keluarga", ""), CENTER)

    qr_path = create_qr_image_file(data_ttd.get("qr_text", ""))
    if qr_path:
        add_qr_to_sheet(ws, qr_path, anchor_cell="CO62", width=110, height=110)

    return qr_path


def generate_b01_excel(template_path, raw_data):
    data = transform_raw_to_data(raw_data)

    wb = load_workbook(template_path)
    ws = wb[SHEET_NAME]

    fill_header(ws, data["kepala_keluarga"])
    fill_backend_static_codes(ws)

    anggota_list = normalize_anggota_list(data.get("anggota_keluarga", []), total=10)

    for i in range(10):
        anggota = anggota_list[i]
        fill_anggota_part1(ws, ROW_PART1[i], anggota)
        fill_anggota_part2(ws, ROW_PART2[i], anggota)
        fill_anggota_part3(ws, ROW_PART3[i], anggota)

    qr_path = fill_ttd(ws, data["ttd"])

    output = io.BytesIO()
    try:
        wb.save(output)
        output.seek(0)
        return output.getvalue()
    finally:
        if qr_path and os.path.exists(qr_path):
            os.remove(qr_path)