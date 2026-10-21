param(
    [Parameter(Mandatory = $true)]
    [string]$SshTarget,

    [string]$RemoteProjectPath = "/opt/dekstra-microservice",
    [switch]$NoSudo
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "dekstra-loadtest-sync-{0}" -f ([guid]::NewGuid().ToString("N"))
)
$archivePath = "$stageRoot.zip"
$remoteArchive = "/tmp/dekstra-loadtest-sync.zip"
$remoteStage = "/tmp/dekstra-loadtest-sync"

try {
    New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
    $stageLoadtest = Join-Path $stageRoot "loadtest"
    New-Item -ItemType Directory -Force -Path $stageLoadtest | Out-Null

    Get-ChildItem -LiteralPath $PSScriptRoot -Force |
        Where-Object {
            $_.Name -notin @("generated", "results", "__pycache__") -and
            $_.Extension -notin @(".pyc", ".pyo")
        } |
        ForEach-Object {
            Copy-Item `
                -LiteralPath $_.FullName `
                -Destination $stageLoadtest `
                -Recurse `
                -Force
        }

    Compress-Archive `
        -LiteralPath (Join-Path $stageRoot "loadtest") `
        -DestinationPath $archivePath `
        -Force

    scp $archivePath "${SshTarget}:$remoteArchive"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload loadtest archive."
    }

    $copyCommand = if ($NoSudo) {
        "cp -a '$remoteStage/loadtest/.' '$RemoteProjectPath/loadtest/'"
    }
    else {
        "sudo cp -a '$remoteStage/loadtest/.' '$RemoteProjectPath/loadtest/'"
    }
    $mkdirCommand = if ($NoSudo) {
        "mkdir -p '$RemoteProjectPath/loadtest'"
    }
    else {
        "sudo mkdir -p '$RemoteProjectPath/loadtest'"
    }

    $remoteCommand = @"
set -Eeuo pipefail
rm -rf '$remoteStage'
mkdir -p '$remoteStage'
python3 - <<'PY'
from zipfile import ZipFile
ZipFile('$remoteArchive').extractall('$remoteStage')
PY
$mkdirCommand
$copyCommand
rm -rf '$remoteStage' '$remoteArchive'
"@

    ssh $SshTarget $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update loadtest folder on VM."
    }

    Write-Host "loadtest folder synced to ${SshTarget}:$RemoteProjectPath/loadtest"
}
finally {
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}
