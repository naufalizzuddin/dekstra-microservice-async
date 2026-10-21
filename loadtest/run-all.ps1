param(
    [Parameter(Mandatory = $true)]
    [string]$Target,

    [string]$SshTarget,
    [string]$ResultsRoot = "",
    [string]$PrometheusUrl = "http://127.0.0.1:9090",
    [string]$HostHeader = "",
    [string]$TokenFile = "",
    [string]$RemoteProjectPath = "/opt/dekstra-microservice",
    [int]$RequestTimeoutSeconds = 30,
    [switch]$GeneratePeriodicSummary,
    [int]$CooldownSeconds = 60,
    [ValidateRange(1, 100)]
    [int]$Repetitions = 1
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($ResultsRoot)) {
    $ResultsRoot = Join-Path `
        (Join-Path $PSScriptRoot "results") `
        ("campaign-{0}" -f (Get-Date -Format "yyyyMMddTHHmmss"))
}
if ([string]::IsNullOrWhiteSpace($TokenFile)) {
    $TokenFile = Join-Path $PSScriptRoot "generated\accounts.json"
}

$scenarioGroups = @(
    [pscustomobject]@{
        Name = "LT"
        Scenarios = @("LT-01", "LT-02", "LT-03", "LT-04", "LT-05")
    },
    [pscustomobject]@{
        Name = "ST"
        Scenarios = @("ST-01", "ST-02", "ST-03")
    },
    [pscustomobject]@{
        Name = "SP"
        Scenarios = @("SP-01", "SP-02", "SP-03")
    }
)
$failed = @()
$scenarioCount = 0
foreach ($group in $scenarioGroups) {
    $scenarioCount += $group.Scenarios.Count
}
$totalExecutions = $scenarioCount * $Repetitions
$executionNumber = 0

foreach ($group in $scenarioGroups) {
    for ($repetition = 1; $repetition -le $Repetitions; $repetition++) {
        $repetitionLabel = "{0}-repetition-{1:D2}" -f `
            $group.Name, $repetition
        $repetitionResultsRoot = Join-Path $ResultsRoot $repetitionLabel
        New-Item `
            -ItemType Directory `
            -Force `
            -Path $repetitionResultsRoot | Out-Null

        Write-Host (
            "Starting {0} repetition {1} of {2}. Results: {3}" -f `
                $group.Name,
                $repetition,
                $Repetitions,
                $repetitionResultsRoot
        )

        foreach ($scenario in $group.Scenarios) {
            $executionNumber++
            $executionLabel = "{0} repetition {1:D2}" -f `
                $scenario, $repetition

            if ($SshTarget) {
                Write-Host (
                    "Resetting load-test fixtures before $executionLabel..."
                )
                ssh $SshTarget "cd '$RemoteProjectPath' && bash deploy/ubuntu/reset-load-test-data.sh"
                if ($LASTEXITCODE -ne 0) {
                    throw "Fixture reset failed before $executionLabel."
                }
                $tokenParent = Split-Path -Parent $TokenFile
                if ($tokenParent) {
                    New-Item `
                        -ItemType Directory `
                        -Force `
                        -Path $tokenParent | Out-Null
                }
                scp "${SshTarget}:$RemoteProjectPath/loadtest/generated/accounts.json" $TokenFile
                if ($LASTEXITCODE -ne 0) {
                    throw (
                        "Token manifest copy failed after fixture reset " +
                        "for $executionLabel."
                    )
                }
            }

            try {
                $runArgs = @{
                    Scenario = $scenario
                    Target = $Target
                    ResultsRoot = $repetitionResultsRoot
                    PrometheusUrl = $PrometheusUrl
                    HostHeader = $HostHeader
                    TokenFile = $TokenFile
                    RequestTimeoutSeconds = $RequestTimeoutSeconds
                }
                if ($GeneratePeriodicSummary) {
                    $runArgs.GeneratePeriodicSummary = $true
                }
                & (Join-Path $PSScriptRoot "run-scenario.ps1") @runArgs
            }
            catch {
                $failed += $executionLabel
                Write-Warning (
                    "$executionLabel recorded failures: " +
                    $_.Exception.Message
                )
            }

            if ($executionNumber -lt $totalExecutions) {
                Write-Host "Cooling down for $CooldownSeconds seconds..."
                Start-Sleep -Seconds $CooldownSeconds
            }
        }
    }
}

& (Join-Path $PSScriptRoot "summarize-all.ps1") `
    -ResultsRoot $ResultsRoot

if ($failed.Count -gt 0) {
    throw (
        "Completed all profiles. Profiles with failures: " +
        "$($failed -join ', ')."
    )
}
