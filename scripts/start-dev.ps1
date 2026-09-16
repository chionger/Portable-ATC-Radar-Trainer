param(
    [string]$ApiHost,
    [Nullable[int]]$ApiPort,
    [string]$Config
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$WebDirectory = Join-Path $RepositoryRoot "apps\web"
$LauncherArgs = @("-m", "scripts.run_api")
if ($PSBoundParameters.ContainsKey("ApiHost")) { $LauncherArgs += @("--host", $ApiHost) }
if ($PSBoundParameters.ContainsKey("ApiPort")) { $LauncherArgs += @("--port", "$ApiPort") }
if ($PSBoundParameters.ContainsKey("Config")) {
    $LauncherArgs += @("--config", [IO.Path]::GetFullPath($Config))
}

Push-Location $RepositoryRoot
$ApiProcess = $null
$PreviousApiUrl = $env:VITE_API_URL
try {
    $ApiUrl = & python @LauncherArgs --dev-web
    if ($LASTEXITCODE -ne 0) { throw "API configuration validation failed: $ApiUrl" }
    $env:VITE_API_URL = $ApiUrl
    # Start-Process joins arguments into one command line; quote paths containing spaces.
    $QuotedArgs = $LauncherArgs | ForEach-Object { '"' + $_ + '"' }
    $ApiProcess = Start-Process -FilePath "python" -ArgumentList $QuotedArgs `
        -WorkingDirectory $RepositoryRoot -PassThru -WindowStyle Hidden
    Write-Host "API starting at $ApiUrl. Starting the browser application..."
    Set-Location $WebDirectory
    pnpm run dev
}
finally {
    $env:VITE_API_URL = $PreviousApiUrl
    Pop-Location
    if ($null -ne $ApiProcess -and -not $ApiProcess.HasExited) {
        Stop-Process -Id $ApiProcess.Id
    }
}
