param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [Parameter(Mandatory = $true)][string]$RuntimeRoot,
    [Parameter(Mandatory = $true)][string]$Revision,
    [switch]$Preflight
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Revision -notmatch '^[a-f0-9]{40}$') {
    throw 'Deployment requires a full Git commit SHA.'
}
$Workspace = (Resolve-Path -LiteralPath $Workspace).Path
$RuntimeRoot = (Resolve-Path -LiteralPath $RuntimeRoot).Path
$runtimePython = Join-Path $RuntimeRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
    throw 'Authorized runtime Python is missing.'
}
$actualRevision = (& git -C $Workspace rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $Revision) {
    throw "Checkout revision does not match requested deployment: $Revision"
}

$env:DDM501_RUNTIME_ROOT = $RuntimeRoot
$env:GITHUB_SHA = $Revision
Push-Location -LiteralPath $Workspace
try {
    $deployPath = (& $runtimePython pipeline/prepare_runner_env.py --stage-deployment | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $deployPath -PathType Container)) {
        throw 'Failed to stage the exact deployment commit.'
    }
} finally {
    Pop-Location
}

Push-Location -LiteralPath $deployPath
try {
    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration is invalid.' }
    if ($Preflight) {
        Write-Output "Preflight OK: $Revision"
        return
    }

    & docker compose up -d --build --wait --wait-timeout 300
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose deployment failed.' }

    foreach ($url in @(
        'http://localhost:18100/ready',
        'http://localhost:18501/_stcore/health',
        'http://localhost:18600/',
        'http://localhost:13000/api/health',
        'http://localhost:18081/health',
        'http://localhost:15030/',
        'http://localhost:19090/-/ready',
        'http://localhost:18001/metrics',
        'http://localhost:18003/metrics/'
    )) {
        $null = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
    }

    & $runtimePython pipeline/verify_monitoring_centre.py
    if ($LASTEXITCODE -ne 0) { throw 'Monitoring verification failed.' }
    $report = Join-Path $deployPath 'reports\monitoring-verification.json'
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw 'Monitoring verification report is missing.'
    }
    $artifactDirectory = Join-Path $Workspace 'reports'
    New-Item -ItemType Directory -Path $artifactDirectory -Force | Out-Null
    Copy-Item -LiteralPath $report -Destination (Join-Path $artifactDirectory 'deployment-monitoring-verification.json') -Force
    Write-Output "Deployment verified: $Revision"
} finally {
    Pop-Location
}
