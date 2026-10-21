param(
    [Parameter(Mandatory = $true)]
    [string]$RunDirectory,

    [ValidateRange(5, 300)]
    [int]$IntervalSeconds = 5
)

$ErrorActionPreference = "Stop"
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$runPath = (Resolve-Path $RunDirectory).Path
$historyPath = Join-Path $runPath "locust_stats_history.csv"
$metadataPath = Join-Path $runPath "metadata.json"
$metricsPath = Join-Path $runPath "prometheus-metrics.json"
$outputPath = Join-Path $runPath "periodic-summary.csv"

if (-not (Test-Path $historyPath)) {
    throw "Missing Locust history: $historyPath"
}
if (-not (Test-Path $metadataPath)) {
    throw "Missing run metadata: $metadataPath"
}

function Convert-Number([object]$Value) {
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) {
        return $null
    }
    return [double]::Parse([string]$Value, $culture)
}

function Get-MetricAverage(
    [object]$MetricSeries,
    [double]$StartExclusive,
    [double]$EndInclusive
) {
    $values = @()
    foreach ($series in @($MetricSeries)) {
        foreach ($point in @($series.values)) {
            if ($null -eq $point -or $point.Count -lt 2) {
                continue
            }
            $timestamp = Convert-Number $point[0]
            if (
                $timestamp -gt $StartExclusive -and
                $timestamp -le $EndInclusive
            ) {
                $values += Convert-Number $point[1]
            }
        }
    }
    if ($values.Count -eq 0) {
        return $null
    }
    return [math]::Round(
        ($values | Measure-Object -Average).Average,
        3
    )
}

function Get-Phase(
    [double]$StartSeconds,
    [double]$EndSeconds,
    [double]$RampSeconds,
    [object[]]$PhaseWindows
) {
    foreach ($phase in $PhaseWindows) {
        if (
            $EndSeconds -gt [double]$phase.start_seconds -and
            $StartSeconds -lt [double]$phase.end_seconds
        ) {
            return [string]$phase.name
        }
    }
    if ($EndSeconds -le $RampSeconds) {
        return "ramp_up"
    }
    if ($StartSeconds -lt $RampSeconds) {
        return "transition"
    }
    return "steady_state"
}

$metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
$startedAt = [double]$metadata.started_at_epoch
$endedAt = [double]$metadata.ended_at_epoch
$rampSeconds = [double]$metadata.ramp_seconds
$phaseWindows = @($metadata.phase_windows | Where-Object { $null -ne $_ })

$snapshots = Import-Csv $historyPath |
    Where-Object {
        $_.Name -eq "Aggregated" -and
        (Convert-Number $_.Timestamp) -ge $startedAt -and
        (Convert-Number $_.Timestamp) -le $endedAt
    } |
    Sort-Object { Convert-Number $_.Timestamp }

if (-not $snapshots) {
    throw "No Aggregated rows were found in $historyPath."
}

$windowSnapshots = $snapshots |
    Group-Object {
        [math]::Floor(
            ((Convert-Number $_.Timestamp) - $startedAt) /
            $IntervalSeconds
        )
    } |
    ForEach-Object {
        $_.Group | Select-Object -Last 1
    } |
    Sort-Object { Convert-Number $_.Timestamp }

$metrics = $null
if (Test-Path $metricsPath) {
    $metrics = Get-Content $metricsPath -Raw | ConvertFrom-Json
}

$previousTimestamp = $startedAt
$previousRequests = 0.0
$previousFailures = 0.0
$previousLatencyTotal = 0.0
$rows = @()

foreach ($snapshot in $windowSnapshots) {
    $timestamp = Convert-Number $snapshot.Timestamp
    $requestCount = Convert-Number $snapshot.'Total Request Count'
    $failureCount = Convert-Number $snapshot.'Total Failure Count'
    $averageResponse = Convert-Number $snapshot.'Total Average Response Time'
    $latencyTotal = $averageResponse * $requestCount
    $periodDuration = $timestamp - $previousTimestamp

    if ($periodDuration -le 0) {
        $previousTimestamp = $timestamp
        $previousRequests = $requestCount
        $previousFailures = $failureCount
        $previousLatencyTotal = $latencyTotal
        continue
    }

    $periodRequests = $requestCount - $previousRequests
    $periodFailures = $failureCount - $previousFailures
    $periodLatency = $latencyTotal - $previousLatencyTotal

    if ($periodRequests -lt 0 -or $periodFailures -lt 0) {
        throw "Locust cumulative counters decreased at timestamp $timestamp."
    }

    $periodAverageResponse = if ($periodRequests -gt 0) {
        [math]::Round($periodLatency / $periodRequests, 3)
    }
    else {
        $null
    }
    $periodErrorRate = if ($periodRequests -gt 0) {
        [math]::Round(100 * $periodFailures / $periodRequests, 4)
    }
    else {
        0
    }

    $cpuAverage = $null
    $ramPercentAverage = $null
    $ramAverage = $null
    if ($null -ne $metrics) {
        $cpuAverage = Get-MetricAverage `
            $metrics.series.vm_cpu_used_percent `
            $previousTimestamp `
            $timestamp
        $ramPercentAverage = Get-MetricAverage `
            $metrics.series.vm_memory_used_percent `
            $previousTimestamp `
            $timestamp
        $ramAverage = Get-MetricAverage `
            $metrics.series.vm_memory_used_mib `
            $previousTimestamp `
            $timestamp
    }

    $periodStart = $previousTimestamp - $startedAt
    $periodEnd = $timestamp - $startedAt
    $rows += [pscustomobject][ordered]@{
        architecture = $metadata.architecture
        scenario = $metadata.scenario
        test_method = $metadata.test_method
        load_profile = $metadata.load_profile
        level = $metadata.level
        timestamp_utc = [DateTimeOffset]::FromUnixTimeSeconds(
            [long]$timestamp
        ).ToString("o")
        phase = Get-Phase `
            $periodStart `
            $periodEnd `
            $rampSeconds `
            $phaseWindows
        period_start_seconds = [math]::Round($periodStart, 3)
        period_end_seconds = [math]::Round($periodEnd, 3)
        period_duration_seconds = [math]::Round($periodDuration, 3)
        user_count = [int](Convert-Number $snapshot.'User Count')
        request_count = [long]$periodRequests
        failure_count = [long]$periodFailures
        average_response_time_ms = $periodAverageResponse
        throughput_requests_per_second = [math]::Round(
            $periodRequests / $periodDuration,
            3
        )
        error_rate_percent = $periodErrorRate
        average_cpu_percent = $cpuAverage
        average_ram_percent = $ramPercentAverage
        average_ram_mib = $ramAverage
    }

    $previousTimestamp = $timestamp
    $previousRequests = $requestCount
    $previousFailures = $failureCount
    $previousLatencyTotal = $latencyTotal
}

if ($rows.Count -eq 0) {
    throw "No complete periodic windows could be generated."
}

$rows | Export-Csv -NoTypeInformation -Encoding utf8 $outputPath
Write-Host "Periodic research metrics saved to $outputPath"
