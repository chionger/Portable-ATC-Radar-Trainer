param(
    [string]$ApiHost = "127.0.0.1",
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$WebDirectory = Join-Path $RepositoryRoot "apps\web"

$ApiProcess = Start-Process -FilePath "python" `
    -ArgumentList @("-m", "uvicorn", "apps.api.main:app", "--host", $ApiHost, "--port", $ApiPort) `
    -WorkingDirectory $RepositoryRoot -PassThru -WindowStyle Hidden

try {
    Write-Host "API started at http://${ApiHost}:${ApiPort}. Starting the browser application..."
    Push-Location $WebDirectory
    pnpm run dev
}
finally {
    Pop-Location
    if (-not $ApiProcess.HasExited) {
        Stop-Process -Id $ApiProcess.Id
    }
}
