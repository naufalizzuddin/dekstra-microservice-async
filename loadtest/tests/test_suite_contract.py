import ast
import csv
import json
import unittest
from pathlib import Path


LOADTEST_DIR = Path(__file__).resolve().parents[1]
ROOT = LOADTEST_DIR.parent
LOCUSTFILE = LOADTEST_DIR / "locustfile.py"
CONFIG = LOADTEST_DIR / "config.py"
SCENARIOS = LOADTEST_DIR / "scenarios.json"
DEPLOY_DIR = ROOT / "deploy" / "ubuntu"


def assignment(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"Assignment {name} was not found.")


class ThesisLoadTestContract(unittest.TestCase):
    def test_profiles_match_report_table(self):
        profiles = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        expected = {
            "LT-01": ("load", 100, 10, "300s"),
            "LT-02": ("load", 200, 20, "300s"),
            "LT-03": ("load", 300, 30, "300s"),
            "LT-04": ("load", 400, 40, "300s"),
            "LT-05": ("load", 500, 50, "300s"),
            "ST-01": ("stress", 1500, 60, "300s"),
            "ST-02": ("stress", 2000, 80, "300s"),
            "ST-03": ("stress", 2500, 100, "300s"),
            "SP-01": ("spike", 1000, 30, "780s"),
            "SP-02": ("spike", 1250, 40, "780s"),
            "SP-03": ("spike", 1500, 50, "780s"),
        }
        self.assertEqual(set(profiles), set(expected))
        for code, values in expected.items():
            test_method, users, ramp, duration = values
            self.assertEqual(profiles[code]["test_method"], test_method)
            self.assertEqual(profiles[code]["users"], users)
            self.assertEqual(profiles[code]["ramp_seconds"], ramp)
            self.assertEqual(profiles[code]["duration"], duration)

        spike_rates = {
            "SP-01": 30,
            "SP-02": 28.75,
            "SP-03": 28,
        }
        for code, spawn_rate in spike_rates.items():
            profile = profiles[code]
            self.assertEqual(profile["spawn_rate"], spawn_rate)
            self.assertEqual(
                profile["phases"][1]["ramp_seconds"],
                profile["ramp_seconds"],
            )
            self.assertEqual(profile["phases"][1]["spawn_rate"], spawn_rate)
            self.assertEqual(profile["phases"][2]["spawn_rate"], spawn_rate)

    def test_weighted_load_uses_report_endpoint_subset(self):
        source = LOCUSTFILE.read_text(encoding="utf-8")
        self.assertIn("ACTIVE_ENDPOINTS", source)
        self.assertIn("endpoint_allocations_from_env", source)
        self.assertIn("Fixed endpoint allocation", source)
        self.assertIn("class FixedEndpointUser", source)
        self.assertNotIn("WORKLOAD_WEIGHTS", source)

    def test_endpoint_allocations_match_report_profiles(self):
        profiles = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        for scenario, profile in profiles.items():
            if profile["test_method"] == "spike":
                for phase in profile["phases"]:
                    self.assertEqual(
                        sum(phase["endpoint_allocations"].values()),
                        phase["users"],
                    )
                continue
            self.assertEqual(
                sum(profile["endpoint_allocations"].values()),
                profile["users"],
            )
        self.assertEqual(profiles["LT-03"]["endpoint_allocations"]["E-05"], 42)
        self.assertEqual(profiles["ST-01"]["endpoint_allocations"]["E-05"], 210)
        self.assertEqual(profiles["ST-02"]["endpoint_allocations"]["E-05"], 280)
        self.assertEqual(profiles["ST-03"]["endpoint_allocations"]["E-05"], 350)
        self.assertEqual(profiles["SP-01"]["phases"][0]["users"], 100)
        self.assertEqual(profiles["SP-01"]["phases"][1]["users"], 1000)
        self.assertEqual(profiles["SP-01"]["phases"][2]["users"], 100)
        for scenario in ("SP-01", "SP-02", "SP-03"):
            phases = profiles[scenario]["phases"]
            self.assertEqual(
                [phase["duration_seconds"] for phase in phases],
                [60, 120, 600],
            )
            self.assertEqual(
                sum(phase["duration_seconds"] for phase in phases),
                int(profiles[scenario]["duration"].removesuffix("s")),
            )
        self.assertEqual(profiles["SP-01"]["phases"][2]["duration_seconds"], 600)
        self.assertEqual(profiles["SP-02"]["phases"][2]["duration_seconds"], 600)
        self.assertEqual(profiles["SP-03"]["phases"][2]["duration_seconds"], 600)
        self.assertEqual(profiles["SP-02"]["phases"][1]["users"], 1250)
        self.assertEqual(profiles["SP-03"]["phases"][1]["users"], 1500)

    def test_all_10_endpoint_codes_are_locked(self):
        definitions = assignment(CONFIG, "ENDPOINT_DEFINITIONS")
        endpoints = {
            code: (details["method"], details["path"])
            for code, details in definitions.items()
        }
        self.assertEqual(endpoints, {
            "E-01": ("POST", "/auth/login/"),
            "E-02": ("POST", "/auth/register/"),
            "E-03": ("GET", "/pendaftaran-akun/list/"),
            "E-04": ("POST", "/verifikasi/pendaftaran-akun/{id}/"),
            "E-05": ("GET", "/pengajuan-surat/"),
            "E-06": ("POST", "/pengajuan-surat/"),
            "E-07": ("POST", "/upload/berkas-surat/"),
            "E-08": ("POST", "/riwayat-persetujuan/"),
            "E-09": ("GET", "/notifikasi/"),
            "E-10": ("GET", "/dashboard/"),
        })

    def test_gateway_exposes_all_tested_route_groups(self):
        gateway = (ROOT / "gateway" / "nginx.production.conf").read_text(
            encoding="utf-8"
        )
        for route in (
            "/auth/login/",
            "/auth/register/",
            "/pendaftaran-akun/",
            "/verifikasi/pendaftaran-akun/",
            "/pengajuan-surat/",
            "/upload/berkas-surat/",
            "/riwayat-persetujuan/",
            "/notifikasi/",
            "/dashboard/",
        ):
            self.assertIn(f"location {route}", gateway)

    def test_runner_uses_manifest_and_microservice_metadata(self):
        source = (LOADTEST_DIR / "run-scenario.ps1").read_text(encoding="utf-8")
        self.assertIn('"SP-03"', source)
        self.assertIn('architecture = "microservice"', source)
        self.assertIn('load_profile = "weighted_endpoint"', source)
        self.assertIn('test_method = $testMethod', source)
        self.assertIn("endpoint-allocation.csv", source)
        self.assertIn("phase_windows", source)
        self.assertIn("SBLT_AUTH_CITIZENS=500", source)
        self.assertIn("[int]$RequestTimeoutSeconds = 30", source)
        self.assertIn("SBLT_TIMEOUT=$RequestTimeoutSeconds", source)
        self.assertIn("SBLT_ENDPOINT_ALLOCATIONS", source)
        self.assertIn("ConvertTo-Base64Json", source)
        self.assertIn("SBLT_ENDPOINT_ALLOCATIONS_B64", source)
        self.assertIn("SBLT_SPIKE_PHASES", source)
        self.assertIn("SBLT_SPIKE_PHASES_B64", source)
        self.assertIn("SBLT_PHASE_ENDPOINT_ALLOCATIONS", source)
        self.assertIn("SBLT_PHASE_ENDPOINT_ALLOCATIONS_B64", source)
        self.assertIn("host.docker.internal:host-gateway", source)
        self.assertIn("HostHeader must be a host name only", source)
        self.assertIn("dekstra-microservice-locust:2.43.4", source)
        self.assertIn('SBLT_TIMEOUT", "60"', LOCUSTFILE.read_text(encoding="utf-8"))
        self.assertIn("def json_env", LOCUSTFILE.read_text(encoding="utf-8"))

    def test_loadtest_mode_exposes_gateway_for_direct_vm_target(self):
        compose = (ROOT / "docker-compose.production.yml").read_text(
            encoding="utf-8"
        )
        start_script = (DEPLOY_DIR / "start-load-test-mode.sh").read_text(
            encoding="utf-8"
        )
        env_example = (ROOT / ".env.production.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("${GATEWAY_BIND_ADDRESS:-127.0.0.1}", compose)
        self.assertIn('GATEWAY_BIND_ADDRESS="${GATEWAY_BIND_ADDRESS:-0.0.0.0}"', start_script)
        self.assertIn("GATEWAY_BIND_ADDRESS=0.0.0.0", env_example)

    def test_manifest_contract_is_available_to_locust(self):
        source = LOCUSTFILE.read_text(encoding="utf-8")
        for token in (
            'TOKEN_FILE = os.getenv("SBLT_TOKEN_FILE"',
            '"approval_candidates"',
            '"registration_candidates"',
            '"application_candidates"',
            '"wilayah"',
            "TOKEN_BY_NIK.get(self.nik)",
        ):
            self.assertIn(token, source)
        self.assertNotIn("StopUser", source)

    def test_mutating_endpoints_cycle_fixture_targets(self):
        source = LOCUSTFILE.read_text(encoding="utf-8")
        self.assertNotIn("mutation_done", source)
        self.assertIn("def registration_candidate_for", source)
        self.assertIn("def approval_candidate_for", source)
        self.assertIn("index >= len(REGISTRATION_CANDIDATES)", source)
        self.assertIn("APPLICATION_CANDIDATES_BY_CITIZEN", source)
        self.assertIn("application_candidate_for(self.account_index)", source)
        self.assertIn("index % len(candidates)", source)
        self.assertIn('"loadtest": True', source)

    def test_fixture_defaults_match_monolith_and_report_contract(self):
        source = (LOADTEST_DIR / "seed_load_test.py").read_text(encoding="utf-8")
        for token in (
            'parser.add_argument("--citizens", type=int, default=60)',
            'parser.add_argument("--auth-citizens", type=int, default=500)',
            'parser.add_argument("--pending-per-stage", type=int, default=5000)',
            'parser.add_argument("--registrations", type=int, default=25000)',
            'parser.add_argument("--completed-documents", type=int, default=2500)',
            '"--otp-ttl-hours"',
            'default=int(os.getenv("LOAD_TEST_OTP_TTL_HOURS", "12"))',
            "timedelta(hours=otp_ttl_hours)",
            "registration_candidates=",
            "approval_candidates=",
            "application_candidates=",
            "final_document_tokens=",
            "wilayah=",
            "OTPEmail.objects.update_or_create",
        ):
            self.assertIn(token, source)

    def test_deploy_scripts_keep_full_manifest_from_fixture_seed(self):
        overwrite_pattern = "export_load_test_tokens > loadtest/generated/accounts.json"
        for script_name in (
            "start-load-test-mode.sh",
            "reset-load-test-data.sh",
        ):
            source = (DEPLOY_DIR / script_name).read_text(encoding="utf-8")
            self.assertNotIn(overwrite_pattern, source)
            self.assertIn("loadtest/seed_load_test.py", source)
            self.assertIn("--confirm-loadtest-target", source)
            self.assertIn("--auth-citizens", source)
            self.assertIn("--completed-documents", source)
            self.assertIn(
                'LOADTEST_REGISTRATIONS="${LOADTEST_REGISTRATIONS:-25000}"',
                source,
            )
            self.assertIn(
                'LOADTEST_COMPLETED_DOCUMENTS="${LOADTEST_COMPLETED_DOCUMENTS:-2500}"',
                source,
            )
            self.assertIn("loadtest/generated/accounts.json", source)

    def test_monitoring_uses_current_cadvisor_registry(self):
        compose = (ROOT / "docker-compose.monitoring.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ghcr.io/google/cadvisor:0.56.2", compose)
        self.assertNotIn("gcr.io/cadvisor/cadvisor", compose)

    def test_reporting_loadtest_mode_uses_local_read_model(self):
        overlay = (ROOT / "docker-compose.loadtest-target.yml").read_text(
            encoding="utf-8"
        )
        settings = (
            ROOT / "reporting_service" / "config" / "settings.py"
        ).read_text(encoding="utf-8")
        views = (
            ROOT / "reporting_service" / "dashboard" / "views.py"
        ).read_text(encoding="utf-8")
        self.assertIn("REPORTING_DASHBOARD_FETCH_DOCUMENT_STATS", overlay)
        self.assertIn('REPORTING_DASHBOARD_FETCH_DOCUMENT_STATS: "0"', overlay)
        self.assertIn('LOAD_TESTING = env_bool("LOAD_TESTING"', settings)
        self.assertIn("DOCUMENT_DASHBOARD_TIMEOUT_SECONDS", settings)
        self.assertIn("REPORTING_DASHBOARD_FETCH_DOCUMENT_STATS", settings)
        self.assertIn("settings.REPORTING_DASHBOARD_FETCH_DOCUMENT_STATS", views)

    def test_loadtest_otp_cleanup_preserves_fixed_login_otp(self):
        serializers = (
            ROOT / "user_service" / "accounts" / "serializers.py"
        ).read_text(encoding="utf-8")
        tasks = (ROOT / "user_service" / "accounts" / "tasks.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def otp_expiry_delta", serializers)
        self.assertIn("timedelta(hours=settings.LOAD_TEST_OTP_TTL_HOURS)", serializers)
        self.assertIn("def cleanup_expired_otp_email", tasks)
        self.assertIn("settings.LOAD_TESTING", tasks)
        self.assertIn("exclude(tujuan=OTPEmail.Tujuan.LOGIN)", tasks)

    def test_application_number_creation_uses_unique_pending_placeholder(self):
        for service in (
            "document_service",
            "approval_service",
            "document_generation_worker",
        ):
            source = (ROOT / service / "surat" / "models.py").read_text(
                encoding="utf-8"
            )
            self.assertIn('f"PENDING/{uuid.uuid4()}"', source)
            self.assertIn("needs_final_number", source)
            self.assertIn('f"{now:%Y}/{now:%m}/{self.jenis_surat.kode}/{self.id}"', source)

    def test_manifest_copy_is_writable_inside_service_containers(self):
        source = (LOADTEST_DIR / "seed_load_test.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def copy_manifest_to_service", source)
        self.assertIn('"--user",', source)
        self.assertIn('"chmod",', source)
        self.assertIn('"666",', source)

    def test_loadtest_target_queues_otp_email_with_in_memory_backend(self):
        overlay = (ROOT / "docker-compose.loadtest-target.yml").read_text(
            encoding="utf-8"
        )
        settings = (
            ROOT / "user_service" / "config" / "settings.py"
        ).read_text(encoding="utf-8")
        serializers = (
            ROOT / "user_service" / "accounts" / "serializers.py"
        ).read_text(encoding="utf-8")
        self.assertIn("user-api:", overlay)
        self.assertIn('LOAD_TESTING: "1"', overlay)
        self.assertEqual(overlay.count('OTP_EMAIL_ENABLED: "1"'), 2)
        self.assertEqual(
            overlay.count(
                "EMAIL_BACKEND: django.core.mail.backends.locmem.EmailBackend"
            ),
            2,
        )
        self.assertIn('LOAD_TEST_OTP_TTL_HOURS: "12"', overlay)
        self.assertIn('LOAD_TESTING = env_bool("LOAD_TESTING"', settings)
        self.assertIn('LOAD_TEST_OTP_TTL_HOURS = int(os.getenv("LOAD_TEST_OTP_TTL_HOURS", "12"))', settings)
        self.assertIn('EMAIL_BACKEND = os.getenv(', settings)
        self.assertIn('"EMAIL_BACKEND",', settings)
        self.assertIn("send_otp_email.apply_async", serializers)

    def test_loadtest_mode_uses_fast_password_hashers(self):
        source = (ROOT / "user_service" / "config" / "settings.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('LOAD_TESTING = env_bool("LOAD_TESTING"', source)
        self.assertIn("django.contrib.auth.hashers.MD5PasswordHasher", source)

    def test_endpoint_summary_outputs_are_generated(self):
        run_summary = (LOADTEST_DIR / "summarize-run.ps1").read_text(
            encoding="utf-8"
        )
        all_summary = (LOADTEST_DIR / "summarize-all.ps1").read_text(
            encoding="utf-8"
        )
        for field in (
            "architecture",
            "scenario",
            "test_method",
            "load_profile",
            "level",
            "users",
            "ramp_seconds",
            "spawn_rate",
            "duration_seconds",
            "request_count",
            "failure_count",
            "average_response_time_ms",
            "throughput_requests_per_second",
            "error_rate_percent",
            "average_cpu_percent",
            "average_ram_percent",
            "average_ram_mib",
            "method",
            "endpoint",
            "function",
            "actor",
            "authentication",
            "weight_percent",
        ):
            self.assertIn(field, run_summary)
        self.assertIn("endpoint-summary.csv", run_summary)
        self.assertIn("phase-summary.csv", run_summary)
        self.assertIn("phase-endpoint-summary.csv", run_summary)
        self.assertIn("microservice-endpoint-summary.csv", all_summary)
        self.assertIn("microservice-endpoint-allocation.csv", all_summary)
        self.assertIn("microservice-phase-summary.csv", all_summary)
        self.assertIn("microservice-phase-endpoint-summary.csv", all_summary)

    def test_periodic_summary_is_standard_diagnostic_output(self):
        scenario_runner = (LOADTEST_DIR / "run-scenario.ps1").read_text(
            encoding="utf-8"
        )
        all_runner = (LOADTEST_DIR / "run-all.ps1").read_text(encoding="utf-8")
        periodic = (LOADTEST_DIR / "summarize-periodic.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[switch]$GeneratePeriodicSummary", scenario_runner)
        self.assertIn("[switch]$GeneratePeriodicSummary", all_runner)
        self.assertIn("if ((-not $SkipMetrics) -or $GeneratePeriodicSummary)", scenario_runner)
        self.assertIn("[int]$IntervalSeconds = 5", periodic)
        self.assertIn("average_ram_percent", periodic)
        self.assertIn("phaseWindows", periodic)
        run_summary = (LOADTEST_DIR / "summarize-run.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("Get-WindowRequestMetrics", run_summary)
        self.assertIn("$endSnapshot.request_count", run_summary)
        self.assertIn("$startSnapshot.request_count", run_summary)
        self.assertIn("$endSnapshot.latency_total", run_summary)
        self.assertIn("$startSnapshot.latency_total", run_summary)
        self.assertIn("phaseStartEpoch", run_summary)
        self.assertIn("phaseEndEpoch", run_summary)

    def test_all_runner_repetition_contract(self):
        all_runner = (LOADTEST_DIR / "run-all.ps1").read_text(
            encoding="utf-8"
        )
        all_summary = (LOADTEST_DIR / "summarize-all.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[ValidateRange(1, 100)]", all_runner)
        self.assertIn("[int]$Repetitions = 1", all_runner)
        self.assertIn('$failed += $executionLabel', all_runner)
        self.assertIn(
            'Join-Path $ResultsRoot $repetitionLabel',
            all_runner,
        )
        self.assertIn(
            'Get-ChildItem $ResultsRoot -Recurse -Filter summary.json',
            all_summary,
        )

    def test_endpoint_allocation_template_matches_profiles_when_present(self):
        template = LOADTEST_DIR / "endpoint-allocation-template.csv"
        if not template.exists():
            return
        profiles = json.loads(SCENARIOS.read_text(encoding="utf-8"))
        endpoints = assignment(CONFIG, "ENDPOINT_DEFINITIONS")
        with template.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len(profiles) * len(endpoints))


if __name__ == "__main__":
    unittest.main()
