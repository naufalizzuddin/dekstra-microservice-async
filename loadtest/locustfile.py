import base64
import itertools
import json
import os
import random
import threading
import time

from locust import HttpUser, LoadTestShape, between, events, task

from config import ENDPOINT_CODES, ENDPOINT_DEFINITIONS


ACTIVE_ENDPOINTS = tuple(ENDPOINT_CODES)

AUTH_ROLE_ORDER = ["citizen", "rt", "rw", "admin", "kades"]
INFO_ROLE_ORDER = ["citizen", "rt", "rw", "admin", "kades"]
APPROVAL_STAGES = [
    ("rt", "RT"),
    ("rw", "RW"),
    ("admin", "ADMIN"),
    ("kades", "KEPALA-DESA"),
]

ROLE_PREFIX = {
    "citizen": "91",
    "rt": "92",
    "rw": "93",
    "admin": "94",
    "kades": "95",
}

TOTAL_USERS = int(os.getenv("SBLT_USERS", "50"))
BUSINESS_CITIZEN_COUNT = int(os.getenv("SBLT_CITIZENS", "60"))
AUTH_CITIZEN_COUNT = int(os.getenv("SBLT_AUTH_CITIZENS", "500"))
REQUEST_TIMEOUT = float(os.getenv("SBLT_TIMEOUT", "60"))
TOKEN_FILE = os.getenv("SBLT_TOKEN_FILE", "/loadtest/generated/accounts.json")
FIXED_OTP = os.getenv("SBLT_OTP", "246810")
PASSWORD = os.getenv("SBLT_PASSWORD", "LoadTest!2026")
WAIT_MIN = float(os.getenv("SBLT_WAIT_MIN", "1"))
WAIT_MAX = float(os.getenv("SBLT_WAIT_MAX", "3"))
HOST_HEADER = os.getenv("SBLT_HOST_HEADER")
SCENARIO_KIND = os.getenv("SBLT_SCENARIO_KIND", "load")
ENABLE_SHAPE = os.getenv("SBLT_ENABLE_SHAPE") == "1"
def json_env(name, default, b64_name=None):
    raw_value = os.getenv(b64_name or f"{name}_B64")
    if raw_value:
        decoded = base64.b64decode(raw_value).decode("utf-8")
        return json.loads(decoded)
    return json.loads(os.getenv(name, default))


SPIKE_PHASES = json_env("SBLT_SPIKE_PHASES", "[]")
PHASE_ENDPOINT_ALLOCATIONS = json_env(
    "SBLT_PHASE_ENDPOINT_ALLOCATIONS",
    "[]",
)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def endpoint_allocations_from_env(total):
    raw_allocations = (
        os.getenv("SBLT_ENDPOINT_ALLOCATIONS_B64")
        or os.getenv("SBLT_ENDPOINT_ALLOCATIONS")
    )
    if raw_allocations:
        allocations = json_env("SBLT_ENDPOINT_ALLOCATIONS", "{}")
        normalized = {
            endpoint: int(allocations.get(endpoint, 0))
            for endpoint in ACTIVE_ENDPOINTS
        }
        if sum(normalized.values()) != total:
            raise RuntimeError(
                "Endpoint allocation total does not match "
                f"SBLT_USERS={total}: {normalized}"
            )
        return normalized

    allocations = {}
    remaining = total
    endpoints = list(ACTIVE_ENDPOINTS)
    for endpoint in endpoints[:-1]:
        weight = ENDPOINT_DEFINITIONS[endpoint]["weight_percent"]
        allocated = int(total * weight / 100)
        allocations[endpoint] = allocated
        remaining -= allocated
    allocations[endpoints[-1]] = remaining
    return allocations


def endpoint_slots_from_allocations(allocations):
    if PHASE_ENDPOINT_ALLOCATIONS:
        slots = []
        current = {endpoint: 0 for endpoint in ACTIVE_ENDPOINTS}
        for index, phase in enumerate(PHASE_ENDPOINT_ALLOCATIONS):
            target = {
                endpoint: int(
                    phase.get("endpoint_allocations", {}).get(endpoint, 0)
                )
                for endpoint in ACTIVE_ENDPOINTS
            }
            delta_slots = []
            for endpoint in ACTIVE_ENDPOINTS:
                delta = target[endpoint] - current[endpoint]
                if delta > 0:
                    delta_slots.extend([endpoint] * delta)
            random.Random(2026 + index).shuffle(delta_slots)
            slots.extend(delta_slots)
            current = target
        if len(slots) == TOTAL_USERS:
            return slots

    slots = [
        endpoint
        for endpoint in ACTIVE_ENDPOINTS
        for _ in range(int(allocations.get(endpoint, 0)))
    ]
    random.Random(2026).shuffle(slots)
    return slots


ALLOCATIONS = endpoint_allocations_from_env(TOTAL_USERS)
ENDPOINT_SLOTS = endpoint_slots_from_allocations(ALLOCATIONS)
USER_SEQUENCE = itertools.count()
ENDPOINT_SEQUENCES = {
    endpoint: itertools.count()
    for endpoint in ACTIVE_ENDPOINTS
}
USER_LOCK = threading.Lock()
CLAIM_LOCK = threading.Lock()


def load_manifest():
    try:
        with open(TOKEN_FILE, encoding="utf-8-sig") as token_file:
            return json.load(token_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Unable to load load-test tokens from {TOKEN_FILE}: {exc}"
        ) from exc


def token_map_from_manifest(payload):
    tokens = {}
    for account in payload.get("accounts", []):
        token = account.get("access") or account.get("tokens", {}).get("access")
        nik = account.get("nik")
        if nik and token:
            tokens[nik] = token
    if not tokens:
        tokens = payload.get("tokens", payload)
    if not isinstance(tokens, dict) or not tokens:
        raise RuntimeError(f"No tokens were found in {TOKEN_FILE}.")
    return tokens


MANIFEST = load_manifest()
TOKEN_BY_NIK = token_map_from_manifest(MANIFEST)
APPROVAL_CANDIDATES_BY_STAGE = {
    stage_label: [
        candidate
        for candidate in MANIFEST.get("approval_candidates", [])
        if candidate.get("stage") == stage_label
    ]
    for _, stage_label in APPROVAL_STAGES
}
APPROVAL_CANDIDATE_SEQUENCES = {
    stage_label: itertools.count()
    for _, stage_label in APPROVAL_STAGES
}
REGISTRATION_CANDIDATES = MANIFEST.get("registration_candidates", [])
REGISTRATION_CANDIDATE_SEQUENCE = itertools.count()
APPLICATION_CANDIDATES = MANIFEST.get("application_candidates", [])
APPLICATION_CANDIDATES_BY_CITIZEN = {}
for candidate in APPLICATION_CANDIDATES:
    APPLICATION_CANDIDATES_BY_CITIZEN.setdefault(
        candidate.get("citizen_index"),
        [],
    ).append(candidate)
APPLICATION_CANDIDATE_SEQUENCES = {
    citizen_index: itertools.count()
    for citizen_index in APPLICATION_CANDIDATES_BY_CITIZEN
}
APPLICATION_CANDIDATE_SEQUENCE = itertools.count()
WILAYAH_FIXTURE = MANIFEST.get("wilayah", {})


@events.test_start.add_listener
def show_endpoint_allocation(environment, **kwargs):
    allocation = ", ".join(
        f"{endpoint}={count}" for endpoint, count in ALLOCATIONS.items()
    )
    print(
        f"Fixed endpoint allocation "
        f"({SCENARIO_KIND}, {TOTAL_USERS} max users): {allocation}"
    )


if ENABLE_SHAPE:
    class SpikeLoadShape(LoadTestShape):
        def tick(self):
            elapsed = self.get_run_time()
            phase_start = 0
            for phase in SPIKE_PHASES:
                phase_end = phase_start + int(phase["duration_seconds"])
                if elapsed < phase_end:
                    return (
                        int(phase["users"]),
                        float(phase.get("spawn_rate", 10)),
                    )
                phase_start = phase_end
            return None


def nik_for(role, index=1):
    return f"{ROLE_PREFIX[role]}{index:014d}"


def test_registration_nik(index):
    return f"96{index:014d}"


def registration_candidate_for():
    if not REGISTRATION_CANDIDATES:
        return None
    with CLAIM_LOCK:
        index = next(REGISTRATION_CANDIDATE_SEQUENCE)
    if index >= len(REGISTRATION_CANDIDATES):
        return None
    return REGISTRATION_CANDIDATES[index]


def approval_candidate_for(stage_label):
    candidates = APPROVAL_CANDIDATES_BY_STAGE.get(stage_label) or []
    if not candidates:
        return None
    with CLAIM_LOCK:
        index = next(APPROVAL_CANDIDATE_SEQUENCES[stage_label])
    return candidates[index % len(candidates)]


def application_candidate_for(citizen_index=None):
    candidates = APPLICATION_CANDIDATES
    if citizen_index is not None:
        candidates = APPLICATION_CANDIDATES_BY_CITIZEN.get(citizen_index, [])
    if not candidates:
        return None
    if citizen_index is None:
        sequence = APPLICATION_CANDIDATE_SEQUENCE
    else:
        sequence = APPLICATION_CANDIDATE_SEQUENCES[citizen_index]
    index = next(sequence)
    return candidates[index % len(candidates)]


class FixedEndpointUser(HttpUser):
    wait_time = between(WAIT_MIN, WAIT_MAX)

    def on_start(self):
        with USER_LOCK:
            self.sequence = next(USER_SEQUENCE)
            self.endpoint = ENDPOINT_SLOTS[
                self.sequence % len(ENDPOINT_SLOTS)
            ]
            self.endpoint_sequence = next(
                ENDPOINT_SEQUENCES[self.endpoint]
            )

        if HOST_HEADER:
            self.client.headers.update({"Host": HOST_HEADER})

        self.headers = {}
        self.role = None
        self.account_index = None
        self.approval_stage_label = None
        self.approval_index = None

        self._prepare_identity()

    def _prepare_identity(self):
        if self.endpoint == "E-01":
            self.role = AUTH_ROLE_ORDER[
                self.endpoint_sequence % len(AUTH_ROLE_ORDER)
            ]
            if self.role == "citizen":
                account_index = (
                    self.endpoint_sequence // len(AUTH_ROLE_ORDER)
                ) % AUTH_CITIZEN_COUNT + 1
            else:
                account_index = 1
            self.nik = nik_for(self.role, account_index)
            return

        if self.endpoint == "E-02":
            return

        if self.endpoint in {"E-03", "E-04"}:
            self.role = "admin"
            self.nik = nik_for("admin")
            self._load_token()
            return

        if self.endpoint in {"E-09", "E-10"}:
            if self.endpoint == "E-10":
                role_order = ["rt", "rw", "admin", "kades"]
            else:
                role_order = INFO_ROLE_ORDER
            self.role = role_order[self.endpoint_sequence % len(role_order)]
            if self.role == "citizen":
                account_index = (
                    self.endpoint_sequence // len(role_order)
                ) % BUSINESS_CITIZEN_COUNT + 1
                self.account_index = account_index
            else:
                account_index = 1
            self.nik = nik_for(self.role, account_index)
            self._load_token()
            return

        if self.endpoint in {"E-05", "E-06", "E-07"}:
            self.role = "citizen"
            account_index = (
                self.endpoint_sequence % BUSINESS_CITIZEN_COUNT
            ) + 1
            self.account_index = account_index
            self.nik = nik_for("citizen", account_index)
            self._load_token()
            return

        if self.endpoint == "E-08":
            stage_index = self.endpoint_sequence % len(APPROVAL_STAGES)
            self.role, self.approval_stage_label = APPROVAL_STAGES[
                stage_index
            ]
            self.approval_index = (
                self.endpoint_sequence // len(APPROVAL_STAGES)
            ) + 1
            self.nik = nik_for(self.role)
            self._load_token()

    def _load_token(self):
        token = TOKEN_BY_NIK.get(self.nik)
        if not token:
            raise RuntimeError(
                f"Token for load-test account {self.nik} was not exported."
            )
        self.headers = {"Authorization": f"Bearer {token}"}

    def _name(self, endpoint, description):
        return f"{endpoint} {description}"

    def _request(
        self,
        method,
        path,
        endpoint,
        description,
        expected=(200,),
        **kwargs,
    ):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        with self.client.request(
            method,
            path,
            name=self._name(endpoint, description),
            catch_response=True,
            **kwargs,
        ) as response:
            if response.status_code not in expected:
                error = getattr(response, "error", None)
                detail = str(error) if error else response.text[:300]
                response.failure(
                    f"expected {expected}, received {response.status_code}: "
                    f"{detail}"
                )
                return None
            response.success()
            if not response.content:
                return None
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type:
                return response.content
            try:
                return response.json()
            except json.JSONDecodeError:
                response.failure("response is not valid JSON")
                return None

    @task
    def execute_endpoint(self):
        {
            "E-01": self._e01_login,
            "E-02": self._e02_register,
            "E-03": self._e03_registration_list,
            "E-04": self._e04_registration_approval,
            "E-05": self._e05_citizen_applications,
            "E-06": self._e06_submit_application,
            "E-07": self._e07_upload_attachment,
            "E-08": self._e08_approval_post,
            "E-09": self._e09_notifications,
            "E-10": self._e10_dashboard,
        }[self.endpoint]()

    def _e01_login(self):
        self._request(
            "POST",
            "/auth/login/",
            "E-01",
            "POST login",
            json={
                "nik": self.nik,
                "password": PASSWORD,
                "otp": FIXED_OTP,
            },
        )

    def _e02_register(self):
        rt_id = WILAYAH_FIXTURE.get("rt")
        rw_code = WILAYAH_FIXTURE.get("rw", 99)
        if not rt_id:
            return
        unique = (
            int(time.time() * 1_000_000) + self.sequence
        ) % 100_000_000_000_000
        nik = f"97{unique:014d}"
        payload = {
            "nomor_kk": f"98{unique:014d}",
            "nik": nik,
            "nama_lengkap": f"SBLT Registration {unique}",
            "tempat_lahir": "Semarang",
            "tanggal_lahir": "1990-01-01",
            "jenis_kelamin": "1",
            "agama": "1",
            "rt": str(rt_id),
            "rw": str(rw_code),
            "alamat": "Alamat load test",
            "email": f"sblt-{nik}@example.invalid",
            "no_hp": f"08{unique % 10_000_000_000:010d}",
            "password": PASSWORD,
        }
        self._request(
            "POST",
            "/auth/register/",
            "E-02",
            "POST register",
            expected=(201,),
            data=payload,
            files={
                "kk_file": ("kk.png", PNG_BYTES, "image/png"),
                "ktp_file": ("ktp.png", PNG_BYTES, "image/png"),
            },
        )

    def _e03_registration_list(self):
        self._request(
            "GET",
            "/pendaftaran-akun/list/?page_size=100",
            "E-03",
            "GET registration list",
            headers=self.headers,
        )

    def _e04_registration_approval(self):
        registration = registration_candidate_for()
        if not registration:
            return
        self._request(
            "POST",
            f"/verifikasi/pendaftaran-akun/{registration['id']}/",
            "E-04",
            "POST registration approval",
            headers=self.headers,
            json={"aksi": 1},
        )

    def _e05_citizen_applications(self):
        self._request(
            "GET",
            "/pengajuan-surat/",
            "E-05",
            "GET citizen applications",
            headers=self.headers,
        )

    def _e06_submit_application(self):
        self._request(
            "POST",
            "/pengajuan-surat/",
            "E-06",
            "POST application",
            expected=(201,),
            headers=self.headers,
            json={
                "jenis_surat": "A01",
                "data": {
                    "loadtest": True,
                    "nama_usaha": "Usaha Load Test",
                    "alamat_usaha": "Semarang",
                    "tujuan": "Pengujian performa",
                },
            },
        )

    def _e07_upload_attachment(self):
        application = application_candidate_for(self.account_index)
        if not application:
            return
        self._request(
            "POST",
            "/upload/berkas-surat/",
            "E-07",
            "POST application attachment",
            expected=(201,),
            headers=self.headers,
            data={"nomor_permohonan": application["nomor_permohonan"]},
            files={
                "file_berkas": (
                    "berkas.png",
                    PNG_BYTES,
                    "image/png",
                )
            },
        )

    def _e08_approval_post(self):
        application = approval_candidate_for(self.approval_stage_label)
        if not application:
            return
        self._request(
            "POST",
            "/riwayat-persetujuan/",
            "E-08",
            "POST approval",
            expected=(201,),
            headers=self.headers,
            json={
                "nomor_permohonan": application["nomor_permohonan"],
                "aksi": 2,
                "catatan": "Disetujui pada pengujian performa",
            },
        )

    def _e09_notifications(self):
        self._request(
            "GET",
            "/notifikasi/",
            "E-09",
            "GET notifications",
            headers=self.headers,
        )

    def _e10_dashboard(self):
        self._request(
            "GET",
            "/dashboard/",
            "E-10",
            "GET dashboard",
            headers=self.headers,
        )
