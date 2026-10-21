param(
    [Parameter(Mandatory = $true)]
    [string]$RunDirectory
)

$ErrorActionPreference = "Stop"
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$runPath = (Resolve-Path $RunDirectory).Path
$statsPath = Join-Path $runPath "locust_stats.csv"
$metadataPath = Join-Path $runPath "metadata.json"
$metricsPath = Join-Path $runPath "prometheus-metrics.json"

if (-not (Test-Path $statsPath)) {
    throw "Missing Locust statistics: $statsPath"
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

function Get-EndpointOrder([string]$EndpointCode) {
    if ($EndpointCode -match "^E-(\d+)$") {
        return [int]$Matches[1]
    }
    return [int]::MaxValue
}

function Get-SeriesAverage([object]$MetricSeries) {
    $values = @()
    foreach ($series in @($MetricSeries)) {
        foreach ($point in @($series.values)) {
            if ($null -ne $point -and $point.Count -ge 2) {
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

function Get-SeriesAverageInWindow(
    [object]$MetricSeries,
    [double]$StartEpoch,
    [double]$EndEpoch
) {
    $values = @()
    foreach ($series in @($MetricSeries)) {
        foreach ($point in @($series.values)) {
            if ($null -eq $point -or $point.Count -lt 2) {
                continue
            }
            $timestamp = Convert-Number $point[0]
            if ($timestamp -ge $StartEpoch -and $timestamp -le $EndEpoch) {
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

function Get-CumulativeSnapshot([object[]]$Rows, [double]$Epoch) {
    $snapshot = $Rows |
        Where-Object { (Convert-Number $_.Timestamp) -le $Epoch } |
        Select-Object -Last 1
    if ($null -eq $snapshot) {
        return [ordered]@{
            request_count = 0.0
            failure_count = 0.0
            latency_total = 0.0
        }
    }
    $requestCount = Convert-Number $snapshot.'Total Request Count'
    $failureCount = Convert-Number $snapshot.'Total Failure Count'
    $averageResponse = Convert-Number $snapshot.'Total Average Response Time'
    return [ordered]@{
        request_count = $requestCount
        failure_count = $failureCount
        latency_total = $requestCount * $averageResponse
    }
}

function Get-WindowRequestMetrics(
    [object[]]$Rows,
    [double]$StartEpoch,
    [double]$EndEpoch,
    [double]$WindowSeconds
) {
    $startSnapshot = Get-CumulativeSnapshot $Rows $StartEpoch
    $endSnapshot = Get-CumulativeSnapshot $Rows $EndEpoch
    $requestCount = [math]::Max(
        0,
        $endSnapshot.request_count - $startSnapshot.request_count
    )
    $failureCount = [math]::Max(
        0,
        $endSnapshot.failure_count - $startSnapshot.failure_count
    )
    $latencyTotal = [math]::Max(
        0,
        $endSnapshot.latency_total - $startSnapshot.latency_total
    )
    $averageResponse = if ($requestCount -gt 0) {
        [math]::Round($latencyTotal / $requestCount, 3)
    }
    else {
        $null
    }
    $errorRate = if ($requestCount -gt 0) {
        [math]::Round(100 * $failureCount / $requestCount, 4)
    }
    else {
        0
    }
    return [ordered]@{
        request_count = [long]$requestCount
        failure_count = [long]$failureCount
        average_response_time_ms = $averageResponse
        throughput_requests_per_second = [math]::Round(
            $requestCount / $WindowSeconds,
            3
        )
        error_rate_percent = $errorRate
    }
}

$metadata = Get-Content $metadataPath -Raw | ConvertFrom-Json
$stats = Import-Csv $statsPath
$aggregate = $stats |
    Where-Object { $_.Name -eq "Aggregated" } |
    Select-Object -Last 1
if ($null -eq $aggregate) {
    throw "Aggregated Locust row was not found in $statsPath."
}

$requestCount = [long](Convert-Number $aggregate.'Request Count')
$failureCount = [long](Convert-Number $aggregate.'Failure Count')
$errorRate = if ($requestCount -gt 0) {
    [math]::Round(100 * $failureCount / $requestCount, 4)
}
else {
    0
}

$metrics = $null
$cpuAverage = $null
$ramPercentAverage = $null
$ramAverage = $null
if (Test-Path $metricsPath) {
    $metrics = Get-Content $metricsPath -Raw | ConvertFrom-Json
    $cpuAverage = Get-SeriesAverage $metrics.series.vm_cpu_used_percent
    $ramPercentAverage = Get-SeriesAverage `
        $metrics.series.vm_memory_used_percent
    $ramAverage = Get-SeriesAverage $metrics.series.vm_memory_used_mib
}

$summary = [ordered]@{
    architecture = $metadata.architecture
    scenario = $metadata.scenario
    test_method = $metadata.test_method
    load_profile = $metadata.load_profile
    level = $metadata.level
    target = $metadata.target
    host_header = $metadata.host_header
    users = [int]$metadata.users
    ramp_seconds = [int]$metadata.ramp_seconds
    spawn_rate = Convert-Number $metadata.spawn_rate
    duration_seconds = [int](
        ([string]$metadata.duration).TrimEnd("s")
    )
    request_timeout_seconds = [int]$metadata.request_timeout_seconds
    request_count = $requestCount
    failure_count = $failureCount
    average_response_time_ms = [math]::Round(
        (Convert-Number $aggregate.'Average Response Time'),
        3
    )
    throughput_requests_per_second = [math]::Round(
        (Convert-Number $aggregate.'Requests/s'),
        3
    )
    error_rate_percent = $errorRate
    average_cpu_percent = $cpuAverage
    average_ram_percent = $ramPercentAverage
    average_ram_mib = $ramAverage
    started_at_utc = $metadata.started_at_utc
    ended_at_utc = $metadata.ended_at_utc
    locust_exit_code = $metadata.locust_exit_code
}

$summaryJson = Join-Path $runPath "summary.json"
$summaryCsv = Join-Path $runPath "summary.csv"
$summary | ConvertTo-Json | Set-Content -Encoding utf8 $summaryJson
[pscustomobject]$summary |
    Export-Csv -NoTypeInformation -Encoding utf8 $summaryCsv

$endpointDetails = @{}
$allocationPath = Join-Path $runPath "endpoint-allocation.csv"
if (Test-Path $allocationPath) {
    foreach ($row in Import-Csv $allocationPath) {
        if (-not $endpointDetails.ContainsKey($row.endpoint_code)) {
            $endpointDetails[$row.endpoint_code] = $row
        }
    }
}

$endpointRows = $stats |
    Where-Object { $_.Name -match "^E-\d{2}\s" } |
    Group-Object { ($_.Name -split "\s+", 2)[0] } |
    ForEach-Object {
        $requestTotal = 0.0
        $failureTotal = 0.0
        $latencyTotal = 0.0
        $throughputTotal = 0.0

        foreach ($row in $_.Group) {
            $rowRequests = Convert-Number $row.'Request Count'
            $rowFailures = Convert-Number $row.'Failure Count'
            $rowAverage = Convert-Number $row.'Average Response Time'
            $rowThroughput = Convert-Number $row.'Requests/s'

            $requestTotal += $rowRequests
            $failureTotal += $rowFailures
            $latencyTotal += ($rowAverage * $rowRequests)
            $throughputTotal += $rowThroughput
        }

        $endpointErrorRate = if ($requestTotal -gt 0) {
            [math]::Round(100 * $failureTotal / $requestTotal, 4)
        }
        else {
            0
        }
        $endpointAverageResponse = if ($requestTotal -gt 0) {
            [math]::Round($latencyTotal / $requestTotal, 3)
        }
        else {
            $null
        }

        [pscustomobject][ordered]@{
            architecture = $metadata.architecture
            scenario = $metadata.scenario
            test_method = $metadata.test_method
            load_profile = $metadata.load_profile
            level = $metadata.level
            users = [int]$metadata.users
            endpoint_code = $_.Name
            method = $endpointDetails[$_.Name].method
            endpoint = $endpointDetails[$_.Name].endpoint
            function = $endpointDetails[$_.Name].function
            actor = $endpointDetails[$_.Name].actor
            authentication = $endpointDetails[$_.Name].authentication
            weight_percent = $endpointDetails[$_.Name].weight_percent
            request_name_count = $_.Group.Count
            request_count = [long]$requestTotal
            failure_count = [long]$failureTotal
            average_response_time_ms = $endpointAverageResponse
            throughput_requests_per_second = [math]::Round(
                $throughputTotal,
                3
            )
            error_rate_percent = $endpointErrorRate
            started_at_utc = $metadata.started_at_utc
            ended_at_utc = $metadata.ended_at_utc
        }
    } |
    Sort-Object endpoint_code

if ($endpointRows) {
    $endpointSummaryCsv = Join-Path $runPath "endpoint-summary.csv"
    $endpointRows |
        Export-Csv -NoTypeInformation -Encoding utf8 $endpointSummaryCsv
    Write-Host "Endpoint metrics saved to:"
    Write-Host "  $endpointSummaryCsv"
}

$phaseWindows = @($metadata.phase_windows | Where-Object { $null -ne $_ })
if ($phaseWindows.Count -gt 0) {
    $historyPath = Join-Path $runPath "locust_stats_history.csv"
    if (-not (Test-Path $historyPath)) {
        throw "Missing Locust history for phase summary: $historyPath"
    }
    $historyRows = Import-Csv $historyPath |
        Sort-Object { Convert-Number $_.Timestamp }
    $aggregateHistory = @(
        $historyRows | Where-Object { $_.Name -eq "Aggregated" }
    )
    $phaseSummaryRows = @()
    $phaseEndpointRows = @()
    foreach ($phase in $phaseWindows) {
        $phaseStartEpoch = (
            [double]$metadata.started_at_epoch +
            [double]$phase.start_seconds
        )
        $phaseEndEpoch = (
            [double]$metadata.started_at_epoch +
            [double]$phase.end_seconds
        )
        $windowSeconds = [double]$phase.duration_seconds
        $phaseMetrics = Get-WindowRequestMetrics `
            $aggregateHistory `
            $phaseStartEpoch `
            $phaseEndEpoch `
            $windowSeconds
        $phaseCpu = $null
        $phaseRamPercent = $null
        $phaseRamMib = $null
        if ($null -ne $metrics) {
            $phaseCpu = Get-SeriesAverageInWindow `
                $metrics.series.vm_cpu_used_percent `
                $phaseStartEpoch `
                $phaseEndEpoch
            $phaseRamPercent = Get-SeriesAverageInWindow `
                $metrics.series.vm_memory_used_percent `
                $phaseStartEpoch `
                $phaseEndEpoch
            $phaseRamMib = Get-SeriesAverageInWindow `
                $metrics.series.vm_memory_used_mib `
                $phaseStartEpoch `
                $phaseEndEpoch
        }
        $phaseSummaryRows += [pscustomobject][ordered]@{
            architecture = $metadata.architecture
            scenario = $metadata.scenario
            test_method = $metadata.test_method
            load_profile = $metadata.load_profile
            level = $metadata.level
            phase = $phase.name
            phase_label = $phase.label
            phase_users = [int]$phase.users
            phase_start_seconds = [int]$phase.start_seconds
            phase_end_seconds = [int]$phase.end_seconds
            phase_duration_seconds = [int]$phase.duration_seconds
            request_count = $phaseMetrics.request_count
            failure_count = $phaseMetrics.failure_count
            average_response_time_ms = $phaseMetrics.average_response_time_ms
            throughput_requests_per_second = (
                $phaseMetrics.throughput_requests_per_second
            )
            error_rate_percent = $phaseMetrics.error_rate_percent
            average_cpu_percent = $phaseCpu
            average_ram_percent = $phaseRamPercent
            average_ram_mib = $phaseRamMib
            started_at_utc = $metadata.started_at_utc
            ended_at_utc = $metadata.ended_at_utc
        }

        foreach ($endpointCode in (
            $endpointDetails.Keys |
                Sort-Object { Get-EndpointOrder $_ }
        )) {
            $endpointHistory = @(
                $historyRows |
                    Where-Object { $_.Name -match "^$endpointCode\s" }
            )
            if (-not $endpointHistory) {
                continue
            }
            $endpointMetrics = Get-WindowRequestMetrics `
                $endpointHistory `
                $phaseStartEpoch `
                $phaseEndEpoch `
                $windowSeconds
            $details = $endpointDetails[$endpointCode]
            $phaseEndpointRows += [pscustomobject][ordered]@{
                architecture = $metadata.architecture
                scenario = $metadata.scenario
                test_method = $metadata.test_method
                load_profile = $metadata.load_profile
                level = $metadata.level
                phase = $phase.name
                phase_label = $phase.label
                phase_users = [int]$phase.users
                phase_start_seconds = [int]$phase.start_seconds
                phase_end_seconds = [int]$phase.end_seconds
                phase_duration_seconds = [int]$phase.duration_seconds
                endpoint_code = $endpointCode
                method = $details.method
                endpoint = $details.endpoint
                function = $details.function
                actor = $details.actor
                authentication = $details.authentication
                weight_percent = $details.weight_percent
                request_count = $endpointMetrics.request_count
                failure_count = $endpointMetrics.failure_count
                average_response_time_ms = (
                    $endpointMetrics.average_response_time_ms
                )
                throughput_requests_per_second = (
                    $endpointMetrics.throughput_requests_per_second
                )
                error_rate_percent = $endpointMetrics.error_rate_percent
                started_at_utc = $metadata.started_at_utc
                ended_at_utc = $metadata.ended_at_utc
            }
        }
    }
    if ($phaseSummaryRows.Count -gt 0) {
        $phaseSummaryCsv = Join-Path $runPath "phase-summary.csv"
        $phaseSummaryRows |
            Export-Csv -NoTypeInformation -Encoding utf8 $phaseSummaryCsv
        Write-Host "Phase metrics saved to:"
        Write-Host "  $phaseSummaryCsv"
    }
    if ($phaseEndpointRows.Count -gt 0) {
        $phaseEndpointCsv = Join-Path $runPath "phase-endpoint-summary.csv"
        $phaseEndpointRows |
            Export-Csv -NoTypeInformation -Encoding utf8 $phaseEndpointCsv
        Write-Host "Phase endpoint metrics saved to:"
        Write-Host "  $phaseEndpointCsv"
    }
}

Write-Host "Research metrics saved to:"
Write-Host "  $summaryJson"
Write-Host "  $summaryCsv"
