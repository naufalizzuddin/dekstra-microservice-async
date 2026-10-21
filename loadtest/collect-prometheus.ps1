param(
    [string]$PrometheusUrl = "http://127.0.0.1:9090",

    [Parameter(Mandatory = $true)]
    [long]$StartEpoch,

    [Parameter(Mandatory = $true)]
    [long]$EndEpoch,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$queries = [ordered]@{
    vm_cpu_used_percent = '100 * (1 - avg(rate(node_cpu_seconds_total{job="vm-host",mode="idle"}[1m])))'
    vm_memory_used_mib = '(node_memory_MemTotal_bytes{job="vm-host"} - node_memory_MemAvailable_bytes{job="vm-host"}) / 1024 / 1024'
    vm_memory_used_percent = '100 * (1 - node_memory_MemAvailable_bytes{job="vm-host"} / node_memory_MemTotal_bytes{job="vm-host"})'
    containers_cpu_percent = '100 * sum(rate(container_cpu_usage_seconds_total{image!=""}[1m]))'
    containers_memory_mib = 'sum(container_memory_working_set_bytes{image!=""}) / 1024 / 1024'
}

$series = [ordered]@{}
foreach ($entry in $queries.GetEnumerator()) {
    $parameters = @{
        query = $entry.Value
        start = $StartEpoch
        end = $EndEpoch
        step = "5s"
    }
    $queryString = ($parameters.GetEnumerator() | ForEach-Object {
        "$([uri]::EscapeDataString($_.Key))=$([uri]::EscapeDataString([string]$_.Value))"
    }) -join "&"
    $uri = "$($PrometheusUrl.TrimEnd('/'))/api/v1/query_range?$queryString"
    $response = Invoke-RestMethod -Uri $uri -Method Get
    if ($response.status -ne "success") {
        throw "Prometheus query failed for $($entry.Key)."
    }
    $series[$entry.Key] = $response.data.result
}

$result = [ordered]@{
    prometheus_url = $PrometheusUrl
    start_epoch = $StartEpoch
    end_epoch = $EndEpoch
    step_seconds = 5
    queries = $queries
    series = $series
}

$parent = Split-Path -Parent $OutputPath
if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}
$result | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $OutputPath
Write-Host "Prometheus metrics saved to $OutputPath"
