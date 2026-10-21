import csv
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree


LOADTEST_DIR = Path(__file__).resolve().parents[1]


class PowerShellSummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not cls.powershell:
            raise unittest.SkipTest("PowerShell tidak tersedia.")

    def run_file(self, script_path, *arguments):
        command = [
            self.powershell,
            "-NoProfile",
            "-NonInteractive",
        ]
        if Path(self.powershell).name.lower() == "powershell.exe":
            command[1:1] = ["-ExecutionPolicy", "Bypass"]
        command.extend([
            "-File",
            str(script_path),
            *map(str, arguments),
        ])
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            self.fail(
                "PowerShell command failed with exit code "
                f"{completed.returncode}.\nSTDOUT:\n{completed.stdout}"
                f"\nSTDERR:\n{completed.stderr}"
            )
        return completed

    def run_script(self, script, *arguments):
        return self.run_file(LOADTEST_DIR / script, *arguments)

    def run_fake_all_runner(self, temporary, *arguments):
        runner_dir = Path(temporary)
        shutil.copy2(LOADTEST_DIR / "run-all.ps1", runner_dir)
        (runner_dir / "run-scenario.ps1").write_text(
            """param(
    [string]$Scenario,
    [string]$Target,
    [string]$ResultsRoot,
    [string]$PrometheusUrl,
    [string]$HostHeader,
    [string]$TokenFile,
    [int]$RequestTimeoutSeconds,
    [switch]$GeneratePeriodicSummary
)
New-Item -ItemType Directory -Force -Path $ResultsRoot | Out-Null
[pscustomobject]@{
    scenario = $Scenario
    results_root = $ResultsRoot
} | ConvertTo-Json -Compress | Add-Content `
    -Path (Join-Path $PSScriptRoot "calls.jsonl")
""",
            encoding="utf-8",
        )
        (runner_dir / "summarize-all.ps1").write_text(
            """param([string]$ResultsRoot)
Set-Content `
    -Path (Join-Path $PSScriptRoot "summarized-root.txt") `
    -Value $ResultsRoot
""",
            encoding="utf-8",
        )
        results_root = runner_dir / "results"
        self.run_file(
            runner_dir / "run-all.ps1",
            "-Target",
            "http://loadtest.invalid",
            "-ResultsRoot",
            results_root,
            "-CooldownSeconds",
            0,
            *arguments,
        )
        calls = [
            json.loads(line)
            for line in (runner_dir / "calls.jsonl").read_text(
                encoding="utf-8-sig"
            ).splitlines()
        ]
        return results_root, calls

    @staticmethod
    def expected_all_runner_calls(repetitions):
        groups = (
            ("LT", ("LT-01", "LT-02", "LT-03", "LT-04", "LT-05")),
            ("ST", ("ST-01", "ST-02", "ST-03")),
            ("SP", ("SP-01", "SP-02", "SP-03")),
        )
        return [
            (scenario, f"{group}-repetition-{repetition:02d}")
            for group, scenarios in groups
            for repetition in range(1, repetitions + 1)
            for scenario in scenarios
        ]

    def test_run_all_defaults_to_one_grouped_repetition(self):
        with tempfile.TemporaryDirectory() as temporary:
            results_root, calls = self.run_fake_all_runner(temporary)
            actual = [
                (call["scenario"], Path(call["results_root"]).name)
                for call in calls
            ]
            expected = self.expected_all_runner_calls(1)
            self.assertEqual(actual, expected)
            self.assertEqual(
                sorted(path.name for path in results_root.iterdir()),
                ["LT-repetition-01", "SP-repetition-01", "ST-repetition-01"],
            )

    def test_run_all_groups_three_repetitions_and_result_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            results_root, calls = self.run_fake_all_runner(
                temporary,
                "-Repetitions",
                3,
            )
            actual = [
                (call["scenario"], Path(call["results_root"]).name)
                for call in calls
            ]
            expected = self.expected_all_runner_calls(3)
            self.assertEqual(actual, expected)
            self.assertEqual(len(calls), 33)
            self.assertTrue((results_root / "LT-repetition-03").is_dir())
            self.assertTrue((results_root / "ST-repetition-03").is_dir())
            self.assertTrue((results_root / "SP-repetition-03").is_dir())

    def test_summarize_all_reads_repetition_folders_recursively(self):
        with tempfile.TemporaryDirectory() as temporary:
            results_root = Path(temporary)
            for repetition, request_count in ((1, 100), (2, 200)):
                run_dir = (
                    results_root
                    / f"LT-repetition-{repetition:02d}"
                    / "LT-01-load-test"
                )
                run_dir.mkdir(parents=True)
                (run_dir / "summary.json").write_text(
                    json.dumps(
                        {
                            "architecture": "microservice",
                            "scenario": "LT-01",
                            "test_method": "load",
                            "started_at_utc": f"2026-01-0{repetition}T00:00:00Z",
                            "request_count": request_count,
                        }
                    ),
                    encoding="utf-8",
                )

            self.run_script(
                "summarize-all.ps1",
                "-ResultsRoot",
                results_root,
            )

            with (results_root / "microservice-summary.csv").open(
                encoding="utf-8-sig",
                newline="",
            ) as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                [int(row["request_count"]) for row in rows],
                [100, 200],
            )

    def test_run_and_periodic_summaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            started = 1_700_000_000
            metadata = {
                "architecture": "microservice",
                "scenario": "LT-01",
                "test_method": "load",
                "load_profile": "weighted_endpoint",
                "level": "Load 100 VU",
                "target": "http://localhost:8080",
                "host_header": "",
                "users": 100,
                "ramp_seconds": 7,
                "spawn_rate": 10,
                "duration": "300s",
                "request_timeout_seconds": 30,
                "started_at_utc": "2023-11-14T22:13:20Z",
                "started_at_epoch": started,
                "ended_at_utc": "2023-11-14T22:13:35Z",
                "ended_at_epoch": started + 15,
                "locust_exit_code": 0,
            }
            (run_dir / "metadata.json").write_text(
                json.dumps(metadata),
                encoding="utf-8",
            )

            with (run_dir / "locust_stats.csv").open(
                "w",
                newline="",
                encoding="utf-8",
            ) as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=[
                        "Name",
                        "Request Count",
                        "Failure Count",
                        "Average Response Time",
                        "Requests/s",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Name": "E-01 POST OTP request",
                        "Request Count": 10,
                        "Failure Count": 1,
                        "Average Response Time": 100,
                        "Requests/s": 0.8,
                    }
                )
                writer.writerow(
                    {
                        "Name": "E-02 POST login",
                        "Request Count": 20,
                        "Failure Count": 2,
                        "Average Response Time": 130,
                        "Requests/s": 1.2,
                    }
                )
                writer.writerow(
                    {
                        "Name": "Aggregated",
                        "Request Count": 30,
                        "Failure Count": 3,
                        "Average Response Time": 120,
                        "Requests/s": 2,
                    }
                )

            with (run_dir / "locust_stats_history.csv").open(
                "w",
                newline="",
                encoding="utf-8",
            ) as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=[
                        "Timestamp",
                        "Name",
                        "Total Request Count",
                        "Total Failure Count",
                        "Total Average Response Time",
                        "User Count",
                    ],
                )
                writer.writeheader()
                for offset, requests, failures, average, users in (
                    (5, 10, 0, 100, 30),
                    (10, 20, 1, 110, 50),
                    (15, 30, 3, 120, 50),
                ):
                    writer.writerow(
                        {
                            "Timestamp": started + offset,
                            "Name": "Aggregated",
                            "Total Request Count": requests,
                            "Total Failure Count": failures,
                            "Total Average Response Time": average,
                            "User Count": users,
                        }
                    )

            self.run_script(
                "summarize-periodic.ps1",
                "-RunDirectory",
                run_dir,
                "-IntervalSeconds",
                5,
            )
            self.run_script(
                "summarize-run.ps1",
                "-RunDirectory",
                run_dir,
            )

            with (run_dir / "periodic-summary.csv").open(
                encoding="utf-8-sig",
                newline="",
            ) as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 3)
            self.assertEqual(
                [row["phase"] for row in rows],
                ["ramp_up", "transition", "steady_state"],
            )
            self.assertEqual(
                [float(row["period_duration_seconds"]) for row in rows],
                [5.0, 5.0, 5.0],
            )

            summary = json.loads(
                (run_dir / "summary.json").read_text(encoding="utf-8-sig")
            )
            self.assertEqual(summary["architecture"], "microservice")
            self.assertEqual(summary["scenario"], "LT-01")
            self.assertEqual(summary["test_method"], "load")
            self.assertEqual(summary["load_profile"], "weighted_endpoint")
            self.assertEqual(summary["request_count"], 30)
            self.assertEqual(summary["failure_count"], 3)
            self.assertEqual(summary["error_rate_percent"], 10)
            self.assertIn("average_ram_percent", summary)

            with (run_dir / "endpoint-summary.csv").open(
                encoding="utf-8-sig",
                newline="",
            ) as source:
                endpoint_rows = list(csv.DictReader(source))
            self.assertEqual(len(endpoint_rows), 2)
            self.assertEqual(endpoint_rows[0]["scenario"], "LT-01")
            self.assertEqual(endpoint_rows[0]["endpoint_code"], "E-01")
            self.assertEqual(int(endpoint_rows[0]["request_count"]), 10)
            self.assertEqual(int(endpoint_rows[0]["failure_count"]), 1)
            self.assertEqual(endpoint_rows[1]["endpoint_code"], "E-02")
            self.assertEqual(int(endpoint_rows[1]["request_count"]), 20)
            self.assertEqual(int(endpoint_rows[1]["failure_count"]), 2)

    def test_export_results_excel_builds_openxml_workbook(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "campaign-20260627T133536" / "LT-01-load"
            run_dir.mkdir(parents=True)
            metadata = {
                "architecture": "microservice",
                "scenario": "LT-01",
                "test_method": "load",
                "load_profile": "weighted_endpoint",
                "level": "Load 100 VU",
                "target": "http://localhost:8080",
                "users": 100,
                "ramp_seconds": 10,
                "duration": "300s",
                "started_at_utc": "2026-06-27T06:35:36Z",
            }
            summary = {
                **metadata,
                "request_count": 1000,
                "failure_count": 2,
                "average_response_time_ms": 125.5,
                "throughput_requests_per_second": 20.2,
                "error_rate_percent": 0.2,
            }
            (run_dir / "metadata.json").write_text(
                json.dumps(metadata),
                encoding="utf-8",
            )
            (run_dir / "summary.json").write_text(
                json.dumps(summary),
                encoding="utf-8",
            )
            for file_name, fieldnames, rows in (
                (
                    "endpoint-summary.csv",
                    [
                        "architecture",
                        "scenario",
                        "endpoint_code",
                        "request_count",
                        "failure_count",
                    ],
                    [
                        {
                            "architecture": "microservice",
                            "scenario": "LT-01",
                            "endpoint_code": "E-01",
                            "request_count": 250,
                            "failure_count": 0,
                        }
                    ],
                ),
                (
                    "locust_stats.csv",
                    [
                        "Name",
                        "Request Count",
                        "Failure Count",
                        "Average Response Time",
                    ],
                    [
                        {
                            "Name": "Aggregated",
                            "Request Count": 1000,
                            "Failure Count": 2,
                            "Average Response Time": 125.5,
                        }
                    ],
                ),
            ):
                with (run_dir / file_name).open(
                    "w",
                    newline="",
                    encoding="utf-8",
                ) as output:
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

            output_path = root / "hasil-uji.xlsx"
            self.run_script(
                "export-results-excel.ps1",
                "-ResultsRoot",
                root,
                "-OutputPath",
                output_path,
            )

            with zipfile.ZipFile(output_path) as workbook:
                names = set(workbook.namelist())
                self.assertIn("xl/workbook.xml", names)
                self.assertIn("xl/worksheets/sheet1.xml", names)
                self.assertIn("xl/styles.xml", names)

                workbook_xml = workbook.read("xl/workbook.xml")
                tree = ElementTree.fromstring(workbook_xml)
                namespace = {
                    "main": (
                        "http://schemas.openxmlformats.org/"
                        "spreadsheetml/2006/main"
                    )
                }
                sheet_names = [
                    sheet.attrib["name"]
                    for sheet in tree.findall("main:sheets/main:sheet", namespace)
                ]
                self.assertIn("run_summary", sheet_names)
                self.assertIn("endpoint_summary", sheet_names)
                self.assertIn("locust_stats", sheet_names)
                joined_sheets = "\n".join(
                    workbook.read(name).decode("utf-8")
                    for name in names
                    if name.startswith("xl/worksheets/")
                )
                self.assertIn("microservice", joined_sheets)
                self.assertIn("LT-01", joined_sheets)
                self.assertIn("E-01", joined_sheets)


if __name__ == "__main__":
    unittest.main()
