import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mode", ["default", "override", "invalid"])
def test_dev_launcher_preflight_arguments_and_cleanup(mode: str) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required for the Windows development launcher")
    harness = r'''
$ErrorActionPreference = 'Stop'
$global:Started = $false
$global:Stopped = $false
$global:WebStarted = $false
$originalLocation = (Get-Location).Path
$env:VITE_API_URL = 'original-value'
function python {
    $global:PythonArgs = @($args)
    if ($env:FP002_TEST_MODE -eq 'invalid') {
        $global:LASTEXITCODE = 2
        return 'Invalid configuration: api.port'
    }
    $global:LASTEXITCODE = 0
    return 'http://127.0.0.1:8123'
}
function Start-Process {
    param($FilePath, $ArgumentList, $WorkingDirectory, [switch]$PassThru, $WindowStyle)
    $global:Started = $true
    $global:LaunchArgs = $ArgumentList
    if ($WindowStyle -ne 'Hidden') { throw 'Expected a hidden server process' }
    return [PSCustomObject]@{ HasExited = $false; Id = 4242 }
}
function Stop-Process {
    param($Id)
    if ($Id -ne 4242) { throw 'Unexpected process cleanup' }
    $global:Stopped = $true
}
function pnpm {
    $global:WebStarted = $true
    if ($env:VITE_API_URL -ne 'http://127.0.0.1:8123') { throw 'Wrong frontend API URL' }
}
$caught = $false
try {
    if ($env:FP002_TEST_MODE -eq 'override') {
        & $env:FP002_TEST_SCRIPT -ApiPort 8123 -Config './config with spaces.yaml'
    } else {
        & $env:FP002_TEST_SCRIPT
    }
} catch {
    if ($env:FP002_TEST_MODE -ne 'invalid') { throw }
    if ($_ -notmatch 'configuration validation failed') { throw }
    $caught = $true
}
if ($env:VITE_API_URL -ne 'original-value') { throw 'Environment was not restored' }
if ((Get-Location).Path -ne $originalLocation) { throw 'Working directory was not restored' }
if ($env:FP002_TEST_MODE -eq 'invalid') {
    if (-not $caught -or $global:Started -or $global:WebStarted) {
        throw 'Invalid startup proceeded'
    }
} else {
    if (-not $global:Started -or -not $global:Stopped -or -not $global:WebStarted) {
        throw 'Startup or cleanup incomplete'
    }
    if ($global:PythonArgs[-1] -ne '--dev-web') { throw 'Missing configuration preflight' }
    if ($env:FP002_TEST_MODE -eq 'override') {
        if ($global:PythonArgs -notcontains '8123') { throw 'Missing explicit override' }
        $expected = '"' + [IO.Path]::GetFullPath('./config with spaces.yaml') + '"'
        if ($global:LaunchArgs -notcontains $expected) { throw 'Config path was not quoted' }
    } elseif ($global:PythonArgs -contains '--port') {
        throw 'Defaults masked environment settings'
    }
}
Write-Output 'launcher-check-passed'
'''
    completed = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", harness],
        cwd=ROOT,
        env={
            **os.environ,
            "FP002_TEST_SCRIPT": str(ROOT / "scripts/start-dev.ps1"),
            "FP002_TEST_MODE": mode,
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "launcher-check-passed" in completed.stdout
