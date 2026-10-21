param(
    [string]$ResultsRoot = (Join-Path $PSScriptRoot "results"),
    [string]$OutputPath = (Join-Path $ResultsRoot "microservice-summary.csv"),
    [string]$EndpointOutputPath = (
        Join-Path $ResultsRoot "microservice-endpoint-summary.csv"
    ),
    [string]$EndpointAllocationOutputPath = (
        Join-Path $ResultsRoot "microservice-endpoint-allocation.csv"
    ),
    [string]$PeriodicOutputPath = (
        Join-Path $ResultsRoot "microservice-periodic-summary.csv"
    ),
    [string]$PhaseOutputPath = (
        Join-Path $ResultsRoot "microservice-phase-summary.csv"
    ),
    [string]$PhaseEndpointOutputPath = (
        Join-Path $ResultsRoot "microservice-phase-endpoint-summary.csv"
    )
)

$ErrorActionPreference = "Stop"
$culture = [System.Globalization.CultureInfo]::InvariantCulture

$currentMethods = @("load", "stress", "spike")

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

if (-not (Test-Path $ResultsRoot)) {
    throw "Results directory was not found: $ResultsRoot"
}

$summaries = Get-ChildItem $ResultsRoot -Recurse -Filter summary.json |
    ForEach-Object {
        Get-Content $_.FullName -Raw | ConvertFrom-Json
    } |
    Where-Object { $currentMethods -contains $_.test_method } |
    Sort-Object test_method, scenario, started_at_utc

if (-not $summaries) {
    Write-Warning "No summary.json files were found in $ResultsRoot."
    return
}

$parent = Split-Path -Parent $OutputPath
if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}
$summaries |
    Export-Csv -NoTypeInformation -Encoding utf8 $OutputPath

Write-Host "Combined microservice results saved to $OutputPath"

$endpointRows = Get-ChildItem $ResultsRoot -Recurse `
    -Filter endpoint-summary.csv |
    ForEach-Object {
        Import-Csv $_.FullName
    } |
    Where-Object { $currentMethods -contains $_.test_method } |
    Sort-Object scenario, endpoint_code, started_at_utc

if ($endpointRows) {
    $endpointParent = Split-Path -Parent $EndpointOutputPath
    if ($endpointParent) {
        New-Item -ItemType Directory -Force `
            -Path $endpointParent | Out-Null
    }
    $endpointRows |
        Export-Csv -NoTypeInformation -Encoding utf8 $EndpointOutputPath
    Write-Host (
        "Combined endpoint results saved to $EndpointOutputPath"
    )
}
else {
    Write-Warning "No endpoint-summary.csv files were found in $ResultsRoot."
}

$endpointAllocationRows = Get-ChildItem $ResultsRoot -Recurse `
    -Filter endpoint-allocation.csv |
    ForEach-Object {
        Import-Csv $_.FullName
    } |
    Where-Object { $currentMethods -contains $_.test_method } |
    Sort-Object scenario, endpoint_code

if ($endpointAllocationRows) {
    $endpointAllocationParent = Split-Path `
        -Parent $EndpointAllocationOutputPath
    if ($endpointAllocationParent) {
        New-Item -ItemType Directory -Force `
            -Path $endpointAllocationParent | Out-Null
    }
    $endpointAllocationRows |
        Export-Csv `
            -NoTypeInformation `
            -Encoding utf8 `
            -Path $EndpointAllocationOutputPath
    Write-Host (
        "Combined endpoint allocation saved to $EndpointAllocationOutputPath"
    )
}
else {
    Write-Warning "No endpoint-allocation.csv files were found in $ResultsRoot."
}

$periodicRows = Get-ChildItem $ResultsRoot -Recurse `
    -Filter periodic-summary.csv |
    ForEach-Object {
        Import-Csv $_.FullName
    } |
    Where-Object { $currentMethods -contains $_.test_method } |
    Sort-Object load_profile, scenario, timestamp_utc

if ($periodicRows) {
    $periodicParent = Split-Path -Parent $PeriodicOutputPath
    if ($periodicParent) {
        New-Item -ItemType Directory -Force `
            -Path $periodicParent | Out-Null
    }
    $periodicRows |
        Export-Csv -NoTypeInformation -Encoding utf8 $PeriodicOutputPath
    Write-Host (
        "Combined periodic results saved to $PeriodicOutputPath"
    )
}
else {
    Write-Warning "No periodic-summary.csv files were found in $ResultsRoot."
}

$phaseRows = Get-ChildItem $ResultsRoot -Recurse `
    -Filter phase-summary.csv |
    ForEach-Object {
        Import-Csv $_.FullName
    } |
    Where-Object { $currentMethods -contains $_.test_method } |
    Sort-Object `
        scenario,
        { Convert-Number $_.phase_start_seconds },
        started_at_utc

if ($phaseRows) {
    $phaseParent = Split-Path -Parent $PhaseOutputPath
    if ($phaseParent) {
        New-Item -ItemType Directory -Force `
            -Path $phaseParent | Out-Null
    }
    $phaseRows |
        Export-Csv -NoTypeInformation -Encoding utf8 $PhaseOutputPath
    Write-Host (
        "Combined phase results saved to $PhaseOutputPath"
    )
}
else {
    Write-Warning "No phase-summary.csv files were found in $ResultsRoot."
}

$phaseEndpointRows = Get-ChildItem $ResultsRoot -Recurse `
    -Filter phase-endpoint-summary.csv |
    ForEach-Object {
        Import-Csv $_.FullName
    } |
    Where-Object { $currentMethods -contains $_.test_method } |
    Sort-Object `
        scenario,
        { Convert-Number $_.phase_start_seconds },
        { Get-EndpointOrder $_.endpoint_code },
        started_at_utc

if ($phaseEndpointRows) {
    $phaseEndpointParent = Split-Path -Parent $PhaseEndpointOutputPath
    if ($phaseEndpointParent) {
        New-Item -ItemType Directory -Force `
            -Path $phaseEndpointParent | Out-Null
    }
    $phaseEndpointRows |
        Export-Csv `
            -NoTypeInformation `
            -Encoding utf8 `
            -Path $PhaseEndpointOutputPath
    Write-Host (
        "Combined phase endpoint results saved to $PhaseEndpointOutputPath"
    )
}
else {
    Write-Warning (
        "No phase-endpoint-summary.csv files were found in $ResultsRoot."
    )
}
