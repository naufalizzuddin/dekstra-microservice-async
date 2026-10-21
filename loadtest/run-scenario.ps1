param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "LT-01",
        "LT-02",
        "LT-03",
        "LT-04",
        "LT-05",
        "ST-01",
        "ST-02",
        "ST-03",
        "SP-01",
        "SP-02",
        "SP-03"
    )]
    [string]$Scenario,

    [Parameter(Mandatory = $true)]
    [string]$Target,

    [string]$ResultsRoot = (Join-Path $PSScriptRoot "results"),
    [string]$PrometheusUrl = "http://127.0.0.1:9090",
    [string]$HostHeader = "",
    [string]$TokenFile = (Join-Path $PSScriptRoot "generated\accounts.json"),
    [int]$RequestTimeoutSeconds = 30,
    [switch]$SkipMetrics,
    [switch]$GeneratePeriodicSummary
)

$ErrorActionPreference = "Stop"

$endpointDefinitions = [ordered]@{
    "E-01" = [ordered]@{
        method = "POST"
        path = "/auth/login/"
        function = "Login pengguna menggunakan OTP"
        actor = "Semua pengguna"
        authentication = "Tidak"
        weight_percent = 10
    }
    "E-02" = [ordered]@{
        method = "POST"
        path = "/auth/register/"
        function = "Pendaftaran akun baru"
        actor = "Warga"
        authentication = "Tidak"
        weight_percent = 8
    }
    "E-03" = [ordered]@{
        method = "GET"
        path = "/pendaftaran-akun/list/"
        function = "Melihat data pendaftaran akun baru"
        actor = "Admin"
        authentication = "Bearer Token"
        weight_percent = 8
    }
    "E-04" = [ordered]@{
        method = "POST"
        path = "/verifikasi/pendaftaran-akun/{id}/"
        function = "Memverifikasi pendaftaran akun"
        actor = "Admin"
        authentication = "Bearer Token"
        weight_percent = 8
    }
    "E-05" = [ordered]@{
        method = "GET"
        path = "/pengajuan-surat/"
        function = "Melihat daftar surat yang telah diajukan"
        actor = "Warga"
        authentication = "Bearer Token"
        weight_percent = 14
    }
    "E-06" = [ordered]@{
        method = "POST"
        path = "/pengajuan-surat/"
        function = "Mengajukan surat baru"
        actor = "Warga"
        authentication = "Bearer Token"
        weight_percent = 14
    }
    "E-07" = [ordered]@{
        method = "POST"
        path = "/upload/berkas-surat/"
        function = "Mengunggah berkas tambahan pengajuan surat"
        actor = "Warga"
        authentication = "Bearer Token"
        weight_percent = 8
    }
    "E-08" = [ordered]@{
        method = "POST"
        path = "/riwayat-persetujuan/"
        function = "Menyetujui atau menolak pengajuan surat"
        actor = "RT, RW, Admin, Kepala Desa"
        authentication = "Bearer Token"
        weight_percent = 14
    }
    "E-09" = [ordered]@{
        method = "GET"
        path = "/notifikasi/"
        function = "Melihat notifikasi yang masuk"
        actor = "Semua pengguna"
        authentication = "Bearer Token"
        weight_percent = 8
    }
    "E-10" = [ordered]@{
        method = "GET"
        path = "/dashboard/"
        function = "Melihat statistik pengajuan surat"
        actor = "RT, RW, Admin, Kepala Desa"
        authentication = "Bearer Token"
        weight_percent = 8
    }
}

function ConvertTo-EndpointAllocationMap([object]$AllocationObject) {
    $map = [ordered]@{}
    foreach ($endpointCode in $endpointDefinitions.Keys) {
        $property = $AllocationObject.PSObject.Properties[$endpointCode]
        if ($null -eq $property) {
            throw "Missing allocation for $endpointCode."
        }
        $map[$endpointCode] = [int]$property.Value
    }
    return $map
}

function ConvertTo-Base64Json([object]$Payload) {
    $json = $Payload | ConvertTo-Json -Compress -Depth 20
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    return [System.Convert]::ToBase64String($bytes)
}

function Assert-AllocationTotal(
    [object]$Allocations,
    [int]$ExpectedTotal,
    [string]$Label
) {
    $actualTotal = 0
    foreach ($value in $Allocations.Values) {
        $actualTotal += [int]$value
    }
    if ($actualTotal -ne $ExpectedTotal) {
        throw (
            "Endpoint allocation for $Label totals $actualTotal users, " +
            "expected $ExpectedTotal."
        )
    }
}

function New-EndpointAllocationRows(
    [object]$Allocations,
    [string]$Phase,
    [string]$PhaseLabel,
    [int]$PhaseUsers,
    [object]$Metadata
) {
    foreach ($endpointCode in $endpointDefinitions.Keys) {
        $definition = $endpointDefinitions[$endpointCode]
        [pscustomobject][ordered]@{
            architecture = $Metadata.architecture
            scenario = $Metadata.scenario
            test_method = $Metadata.test_method
            load_profile = $Metadata.load_profile
            level = $Metadata.level
            phase = $Phase
            phase_label = $PhaseLabel
            users = [int]$Metadata.users
            phase_users = $PhaseUsers
            endpoint_code = $endpointCode
            method = $definition.method
            endpoint = $definition.path
            function = $definition.function
            actor = $definition.actor
            authentication = $definition.authentication
            weight_percent = [int]$definition.weight_percent
            allocated_users = [int]$Allocations[$endpointCode]
        }
    }
}

$profiles = Get-Content (Join-Path $PSScriptRoot "scenarios.json") -Raw |
    ConvertFrom-Json
$profile = $profiles.PSObject.Properties[$Scenario].Value
if ($null -eq $profile) {
    throw "Scenario $Scenario was not found."
}

$testMethod = [string]$profile.test_method
$isSpike = $testMethod -eq "spike"
$endpointAllocations = $null
$phaseWindows = @()
$phaseRuntime = @()

if ($isSpike) {
    $phaseStart = 0
    foreach ($phase in @($profile.phases)) {
        $phaseAllocations = ConvertTo-EndpointAllocationMap `
            $phase.endpoint_allocations
        Assert-AllocationTotal `
            -Allocations $phaseAllocations `
            -ExpectedTotal ([int]$phase.users) `
            -Label "$Scenario/$($phase.name)"
        $phaseEnd = $phaseStart + [int]$phase.duration_seconds
        $phaseWindows += [ordered]@{
            name = [string]$phase.name
            label = [string]$phase.label
            users = [int]$phase.users
            start_seconds = $phaseStart
            end_seconds = $phaseEnd
            duration_seconds = [int]$phase.duration_seconds
            endpoint_allocations = $phaseAllocations
        }
        $phaseRuntime += [ordered]@{
            name = [string]$phase.name
            users = [int]$phase.users
            duration_seconds = [int]$phase.duration_seconds
            spawn_rate = [double]$phase.spawn_rate
        }
        if ([int]$phase.users -eq [int]$profile.users) {
            $endpointAllocations = $phaseAllocations
        }
        $phaseStart = $phaseEnd
    }
    if ($null -eq $endpointAllocations) {
        throw "Spike scenario $Scenario does not define a max-user phase."
    }
}
else {
    $endpointAllocations = ConvertTo-EndpointAllocationMap `
        $profile.endpoint_allocations
    Assert-AllocationTotal `
        -Allocations $endpointAllocations `
        -ExpectedTotal ([int]$profile.users) `
        -Label $Scenario
}

$trimmedHostHeader = $HostHeader.Trim()
if ($trimmedHostHeader -match "^[a-zA-Z][a-zA-Z0-9+.-]*://" -or
    $trimmedHostHeader -match "/") {
    throw "HostHeader must be a host name only, not a URL: $HostHeader"
}
if (-not (Test-Path -LiteralPath $TokenFile)) {
    throw @"
Load testing requires a token manifest.
Create it first:
  ssh user@VM_IP "cd /opt/dekstra-microservice && bash deploy/ubuntu/start-load-test-mode.sh"
  scp user@VM_IP:/opt/dekstra-microservice/loadtest/generated/accounts.json .\loadtest\generated\accounts.json
Expected token file: $TokenFile
"@
}
$resolvedTokenFile = (Resolve-Path -LiteralPath $TokenFile).Path

if (-not $SkipMetrics) {
    $prometheusHealthUrl = (
        "$($PrometheusUrl.TrimEnd('/'))/api/v1/status/buildinfo"
    )
    try {
        $prometheusStatus = Invoke-RestMethod `
            -Uri $prometheusHealthUrl `
            -Method Get `
            -TimeoutSec 5
        if ($prometheusStatus.status -ne "success") {
            throw "Prometheus returned status '$($prometheusStatus.status)'."
        }
    }
    catch {
        throw @"
Prometheus is not reachable at $PrometheusUrl.
Start the SSH tunnel in a separate terminal:
  ssh -N -L 9090:127.0.0.1:9090 user@VM_IP
Then verify:
  curl.exe http://127.0.0.1:9090/-/ready
Original error: $($_.Exception.Message)
Use -SkipMetrics only when CPU and RAM metrics are intentionally omitted.
"@
    }
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is not available."
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$outputDir = Join-Path $ResultsRoot "$Scenario-$testMethod-$timestamp"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$outputDir = (Resolve-Path $outputDir).Path

$image = "dekstra-microservice-locust:2.43.4"
docker build --tag $image $PSScriptRoot
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build the Locust image."
}

$started = [DateTimeOffset]::UtcNow
$metadataPath = Join-Path $outputDir "metadata.json"
$metadata = [ordered]@{
    architecture = "microservice"
    scenario = $Scenario
    test_method = $testMethod
    load_profile = "weighted_endpoint"
    allocation_method = "fixed_weighted_endpoint"
    endpoint_count = $endpointDefinitions.Count
    endpoint_allocations = $endpointAllocations
    phase_windows = @($phaseWindows)
    level = $profile.level
    target = $Target.TrimEnd("/")
    host_header = $trimmedHostHeader
    users = [int]$profile.users
    ramp_seconds = [int]$profile.ramp_seconds
    spawn_rate = [double]$profile.spawn_rate
    duration = $profile.duration
    request_timeout_seconds = $RequestTimeoutSeconds
    started_at_utc = $started.ToString("o")
    started_at_epoch = $started.ToUnixTimeSeconds()
    status = "running"
}
$metadata | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $metadataPath

$allocationRows = @()
if ($isSpike) {
    foreach ($phase in $phaseWindows) {
        $allocationRows += New-EndpointAllocationRows `
            -Allocations $phase.endpoint_allocations `
            -Phase $phase.name `
            -PhaseLabel $phase.label `
            -PhaseUsers ([int]$phase.users) `
            -Metadata $metadata
    }
}
else {
    $allocationRows += New-EndpointAllocationRows `
        -Allocations $endpointAllocations `
        -Phase "overall" `
        -PhaseLabel "Overall" `
        -PhaseUsers ([int]$profile.users) `
        -Metadata $metadata
}
$allocationRows |
    Export-Csv `
        -NoTypeInformation `
        -Encoding utf8 `
        -Path (Join-Path $outputDir "endpoint-allocation.csv")

Write-Host "Running $Scenario ($testMethod, weighted endpoint) against $Target"
Write-Host "Results: $outputDir"

$endpointAllocationsBase64 = ConvertTo-Base64Json $endpointAllocations
$dockerArguments = @(
    "run", "--rm",
    "--add-host", "host.docker.internal:host-gateway",
    "--env", "SBLT_USERS=$($profile.users)",
    "--env", "SBLT_CITIZENS=60",
    "--env", "SBLT_AUTH_CITIZENS=500",
    "--env", "SBLT_TIMEOUT=$RequestTimeoutSeconds",
    "--env", "SBLT_OTP=246810",
    "--env", "SBLT_HOST_HEADER=$trimmedHostHeader",
    "--env", "SBLT_SCENARIO_KIND=$testMethod",
    "--env", "SBLT_ENDPOINT_ALLOCATIONS_B64=$endpointAllocationsBase64",
    "--mount", "type=bind,source=$outputDir,target=/results"
)
if ($isSpike) {
    $spikePhasesBase64 = ConvertTo-Base64Json $phaseRuntime
    $phaseEndpointAllocationsBase64 = ConvertTo-Base64Json $phaseWindows
    $dockerArguments += @(
        "--env", "SBLT_ENABLE_SHAPE=1",
        "--env", "SBLT_SPIKE_PHASES_B64=$spikePhasesBase64",
        "--env", "SBLT_PHASE_ENDPOINT_ALLOCATIONS_B64=$phaseEndpointAllocationsBase64"
    )
}
$tokenRoot = Split-Path -Parent $resolvedTokenFile
$tokenFileName = Split-Path -Leaf $resolvedTokenFile
$dockerArguments += @(
    "--env", "SBLT_TOKEN_FILE=/loadtest/generated/$tokenFileName",
    "--mount",
    "type=bind,source=$tokenRoot,target=/loadtest/generated,readonly"
)
$dockerArguments += @(
    $image,
    "-f", "/loadtest/locustfile.py",
    "--headless",
    "--host", $metadata.target,
    "--run-time", $profile.duration,
    "--stop-timeout", "$RequestTimeoutSeconds",
    "--csv", "/results/locust",
    "--csv-full-history",
    "--html", "/results/report.html",
    "--logfile", "/results/locust.log",
    "--exit-code-on-error", "1"
)
if (-not $isSpike) {
    $dockerArguments += @(
        "--users", $profile.users,
        "--spawn-rate", $profile.spawn_rate
    )
}
docker @dockerArguments
$locustExitCode = $LASTEXITCODE

$ended = [DateTimeOffset]::UtcNow
$metadata["ended_at_utc"] = $ended.ToString("o")
$metadata["ended_at_epoch"] = $ended.ToUnixTimeSeconds()
$metadata["elapsed_seconds"] = [math]::Round(($ended - $started).TotalSeconds, 3)
$metadata["locust_exit_code"] = $locustExitCode
$metadata["status"] = if ($locustExitCode -eq 0) { "completed" } else { "failed" }
$metadata | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $metadataPath

if (-not $SkipMetrics) {
    try {
        Start-Sleep -Seconds 6
        & (Join-Path $PSScriptRoot "collect-prometheus.ps1") `
            -PrometheusUrl $PrometheusUrl `
            -StartEpoch $metadata["started_at_epoch"] `
            -EndEpoch $metadata["ended_at_epoch"] `
            -OutputPath (Join-Path $outputDir "prometheus-metrics.json")
    }
    catch {
        Write-Warning "Prometheus metrics were not collected: $($_.Exception.Message)"
    }
}

if ((-not $SkipMetrics) -or $GeneratePeriodicSummary) {
    try {
        & (Join-Path $PSScriptRoot "summarize-periodic.ps1") `
            -RunDirectory $outputDir `
            -IntervalSeconds 5
    }
    catch {
        Write-Warning "Periodic summary was not generated: $($_.Exception.Message)"
    }
}

try {
    & (Join-Path $PSScriptRoot "summarize-run.ps1") `
        -RunDirectory $outputDir
}
catch {
    Write-Warning "Run summary was not generated: $($_.Exception.Message)"
}

if ($locustExitCode -ne 0) {
    throw "$Scenario completed with request failures. See $outputDir."
}

Write-Host "$Scenario completed successfully."
