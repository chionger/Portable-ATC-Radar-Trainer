# Windows PowerShell 5.1 compatible. Run in the NEW standard account after MANUAL disconnection.
param([switch]$ConfirmManuallyDisconnected, [switch]$CheckNetworkOnly, [switch]$ConfirmProactiveBlockingPaused)
$ErrorActionPreference = 'Stop'
$Bundle = 'D:\ATC-Runtime-Preservation\whisper-turbo-win64-cpu\1.0.0'
$Restore = 'D:\ATC-Runtime-Restore\fp001d-recovery-004'
$Model = 'D:\ATC-Model-Zoo\ASR\OpenAI\whisper-large-v3-turbo\41f01f3fe87f28c78e2fbf8b568835947dd65ed9'
$Run = "$Restore\fp001d-run-004"
$Python = "$Restore\python\python.exe"
$EnvPython = "$Restore\environment\Scripts\python.exe"
$Source = "$Bundle\source"
$Watch = $null
$InferenceStarted = $false
$ExecutionStarted = $null
$FinalStatus = 'BLOCKED'
$Failure = $null
function UTC { [DateTime]::UtcNow.ToString('o') }
function SizeOf([string]$Path) {
    if (!(Test-Path -LiteralPath $Path)) { return [long]0 }
    [long](Get-ChildItem -LiteralPath $Path -Recurse -Force -File -ErrorAction Stop | Measure-Object -Property Length -Sum).Sum
}
function Budget {
    $DBytes = (SizeOf $Bundle) + (SizeOf 'D:\ATC-Runtime-Restore')
    $CBytes = (SizeOf $env:USERPROFILE) + 2GB # Reserve 2 GiB for prior account and controller task assets.
    if ($DBytes -ge 10GB -or $CBytes -ge 4GB) { throw "Storage cap reached: D=$DBytes C-profile=$CBytes" }
    @{timestamp=(UTC); d_assets_bytes=$DBytes; c_accounted_with_prior_reserve_bytes=$CBytes} |
        ConvertTo-Json -Compress | Add-Content -Encoding UTF8 "$Run\storage.jsonl"
}
$NetworkPolicy = Join-Path $PSScriptRoot 'fp001d_network.ps1'
$NetworkSnapshot = {
    param($Log, $Violation, $PolicyPath)
    $ErrorActionPreference = 'Stop'
    try {
        . $PolicyPath
        $Snapshot = Get-Fp001dNetworkSnapshot
        $Snapshot | ConvertTo-Json -Depth 6 -Compress | Add-Content -Encoding UTF8 -LiteralPath $Log
        if (!$Snapshot.isolated) { $Snapshot.reasons | Set-Content -LiteralPath $Violation }
    } catch {
        $_.Exception.Message | Set-Content -LiteralPath $Violation
    }
}
if ($CheckNetworkOnly) {
    . $NetworkPolicy
    $Snapshot = Get-Fp001dNetworkSnapshot
    $Snapshot | ConvertTo-Json -Depth 6
    if ($Snapshot.isolated) { Write-Host 'NETWORK PREFLIGHT READY (no restoration/inference executed)'; exit 0 }
    Write-Host 'NETWORK PREFLIGHT BLOCKED (no restoration/inference executed)'
    exit 1
}
function Isolated {
    if (Test-Path -LiteralPath "$Run\network-violation.txt") { throw 'Network isolation failed; inspect network log.' }
    if ($Watch -and $Watch.State -ne 'Running') { throw 'Network monitor stopped unexpectedly' }
}
function Execute([string]$Name, [string]$File, [string]$Arguments) {
    Isolated
    Budget
    "$(UTC) START $Name $File $Arguments" | Add-Content -Encoding UTF8 "$Run\restoration.txt"
    # Own the process handle from creation; Start-Process redirection can lose ExitCode on PS 5.1.
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $File
    $StartInfo.Arguments = $Arguments
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo
    if (!$Process.Start()) { throw "$Name could not start" }
    $Stdout = $Process.StandardOutput.ReadToEndAsync()
    $Stderr = $Process.StandardError.ReadToEndAsync()
    try {
        while (!$Process.WaitForExit(1000)) {
            Isolated
            if (((Get-Date).ToUniversalTime() - $ExecutionStarted).TotalMinutes -gt 30) { throw '30 minute operator bound reached; no retry permitted' }
            # Conservative ceilings leave headroom for installer writes between checks.
            if ((SizeOf $Restore) -gt 8GB -or (SizeOf $env:USERPROFILE) -gt 1800MB) { throw 'Storage reserve nearly exhausted; stop before cap' }
        }
        $Process.WaitForExit()
        $Code = $Process.ExitCode
        if ($null -eq $Code) { throw "$Name exit code unavailable; success cannot be established" }
    } catch {
        if (!$Process.HasExited) { & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F | Out-File "$Run\termination.txt" }
        throw
    } finally {
        if ($Process.HasExited) {
            [IO.File]::WriteAllText("$Run\$Name.stdout.txt", $Stdout.GetAwaiter().GetResult())
            [IO.File]::WriteAllText("$Run\$Name.stderr.txt", $Stderr.GetAwaiter().GetResult())
        }
        $Process.Dispose()
    }
    Get-Content "$Run\$Name.stdout.txt","$Run\$Name.stderr.txt" | Add-Content -Encoding UTF8 "$Run\restoration.txt"
    "$(UTC) END $Name exit=$Code" | Add-Content -Encoding UTF8 "$Run\restoration.txt"
    Isolated
    if ($Code -ne 0) { throw "$Name failed with exit $Code (including reboot-required codes); stop" }
    return 0
}
if (Test-Path -LiteralPath $Run) { throw 'This one-run location already exists. No repeat acceptance authorized.' }
New-Item -ItemType Directory -Path $Run -ErrorAction Stop | Out-Null
try {
    if (!$ConfirmManuallyDisconnected) { throw 'First manually disable/disconnect ALL networking, then supply -ConfirmManuallyDisconnected' }
    $Account = Get-Content -Raw "$Restore\account.json" | ConvertFrom-Json
    if (!$ConfirmProactiveBlockingPaused) { throw 'Confirm only LiveGuard proactive blocking was paused while offline; other protection remains enabled.' }
    @{recorded_at=(UTC); operator_confirmed=$true; intervention='ESET LiveGuard proactive blocking paused offline; other protections retained'; restoration_required='Restore original setting and verify protection before reconnecting'; verdict_scope='Historical file verdicts do not establish runtime approval'} | ConvertTo-Json | Set-Content -Encoding UTF8 "$Run\security-context.json"
    $Sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if ($Sid -ne $Account.account_sid -or $Sid -eq $Account.controller_sid) { throw 'Must run as the newly prepared account' }
    if (Test-Path "$Restore\python") { throw 'Interpreter destination is not fresh' }
    if (Test-Path "$Restore\environment") { throw 'Environment destination is not fresh' }
    if (!(Test-Path "$Model\config.json")) { throw 'Existing model unavailable/read access missing; do not copy or download weights' }
    $Definition = Get-Content -Raw "$Bundle\definition.json" | ConvertFrom-Json
    foreach ($Artifact in $Definition.artifacts) {
        $Path = Join-Path $Bundle $Artifact.path
        if ((Get-Item -LiteralPath $Path).Length -ne $Artifact.size_bytes -or
            (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Artifact.sha256) {
            throw "Preserved artifact verification failed: $($Artifact.path)"
        }
    }
    & $NetworkSnapshot "$Run\network.jsonl" "$Run\network-violation.txt" $NetworkPolicy
    Isolated
    $Watch = Start-Job -ScriptBlock {
        param($Snapshot, $Log, $Violation, $Stop, $PolicyPath)
        $Block = [scriptblock]::Create($Snapshot)
        while (!(Test-Path -LiteralPath $Stop)) {
            & $Block $Log $Violation $PolicyPath
            Start-Sleep -Seconds 1
        }
    } -ArgumentList $NetworkSnapshot.ToString(),"$Run\network.jsonl","$Run\network-violation.txt","$Run\stop-monitor.txt",$NetworkPolicy
    $ExecutionStarted = (Get-Date).ToUniversalTime()
    $FinalStatus = 'FAILED'
    $Native = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
    if (!$Native.Installed -or ([version]$Native.Version.TrimStart('v')).ToString() -ne '14.51.36247.0') { throw 'Declared native baseline mismatch; no native installation authorized' }
    $OS = Get-CimInstance Win32_OperatingSystem
    if ($OS.Version -ne $Definition.platform.os_version -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Host OS/architecture mismatch' }
    New-Item -ItemType Directory "$Restore\temp-004","$Restore\cache-004" | Out-Null
    $env:TEMP = "$Restore\temp-004"; $env:TMP = $env:TEMP
    $env:PYTHONNOUSERSITE = '1'; $env:PYTHONDONTWRITEBYTECODE = '1'; $env:PYTHONPATH = $Source
    $env:HF_HOME = "$Restore\cache-004\huggingface"; $env:HF_HUB_DISABLE_XET = '1'
    $env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'; $env:HF_HUB_DISABLE_TELEMETRY='1'
    $env:PIP_NO_INDEX='1'; $env:PIP_DISABLE_PIP_VERSION_CHECK='1'; $env:PIP_CONFIG_FILE='NUL'
    Set-Location -LiteralPath $Source
    $BootstrapExit = Execute 'bootstrap' "$Bundle\bootstrap\python-3.12.10-amd64.exe" "/quiet InstallAllUsers=0 TargetDir=$Restore\python Include_pip=1 Include_launcher=0 InstallLauncherAllUsers=0 PrependPath=0 AssociateFiles=0 Shortcuts=0 Include_test=0 Include_doc=0 Include_tcltk=0 Include_tools=0 Include_dev=0 Include_debug=0 Include_symbols=0 /log $Run\python-installer.log"
    $VenvExit = Execute 'venv' $Python "-m venv $Restore\environment"
    if (!(Select-String -LiteralPath "$Restore\environment\pyvenv.cfg" -Pattern '^include-system-site-packages = false$' -Quiet)) { throw 'venv has system site packages' }
    $InstallExit = Execute 'install' $EnvPython "-m scripts.offline_runtime_probe install --wheelhouse $Bundle\wheels --lock $Bundle\procedure\requirements.lock"
    $CheckExit = Execute 'dependency-check' $EnvPython '-m scripts.offline_runtime_probe check'
    $OS = Get-CimInstance Win32_OperatingSystem
    if ([long]$OS.FreePhysicalMemory*1024 -lt $Definition.platform.minimum_ram_bytes) { throw 'Less than required available RAM; no model load attempted' }
    $InferenceStarted = $true
    $InferenceExit = Execute 'inference' $EnvPython "-m scripts.offline_runtime_probe infer --model $Model --audio $Bundle\input\acceptance.wav --manifest $Source\model-zoo\manifest.json --definition $Bundle\definition.json --max-new-tokens 32"
    # Last stdout line is the JSON result; warnings remain in retained stderr.
    (Get-Content "$Run\inference.stdout.txt" | Select-Object -Last 1) | Set-Content -Encoding UTF8 "$Run\inference.json"
    $Ended = UTC
    $Observed = @{
        operating_system='Windows'; os_version=$OS.Version; architecture=$env:PROCESSOR_ARCHITECTURE
        cpu=(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)
        total_ram_bytes=([long]$OS.TotalVisibleMemorySize*1024)
        available_ram_bytes_before_load=([long]$OS.FreePhysicalMemory*1024)
        native_versions=@{'msvc-x64'='14.51.36247.0'}
    }
    $Execution = @{
        account_sid=$Sid; controller_sid=$Account.controller_sid; new_account=$true
        python_location=$Python; environment_location="$Restore\environment"; system_site_packages=$false
        bootstrap_exit_code=$BootstrapExit; venv_exit_code=$VenvExit; install_exit_code=$InstallExit
        dependency_check_exit_code=$CheckExit; inference_exit_code=$InferenceExit
        started_at=$ExecutionStarted.ToString('o'); ended_at=$Ended; native_restoration_proven=$false
    }
    @{execution=$Execution; observed_platform=$Observed} | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 "$Run\execution.json"
    'done' | Set-Content "$Run\stop-monitor.txt"
    Wait-Job $Watch -Timeout 10 | Out-Null
    Receive-Job $Watch -ErrorAction Stop | Out-Null
    $Watch = $null
    & $NetworkSnapshot "$Run\network.jsonl" "$Run\network-violation.txt" $NetworkPolicy
    Isolated
    & $EnvPython -m scripts.collect_runtime_evidence --bundle $Bundle --run $Run *> "$Run\collection.txt"
    if ($LASTEXITCODE -ne 0) { throw 'Evidence collection failed' }
    & $EnvPython -m scripts.verify_runtime_preservation --definition "$Bundle\definition.json" --manifest "$Source\model-zoo\manifest.json" --evidence "$Run\run.json" --artifact-root $Bundle --evidence-root $Run --hash-files --acceptance *> "$Run\verification.txt"
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance evidence verification failed' }
    Budget
    $FinalStatus = 'PASSED'
} catch {
    $Failure = $_.Exception.Message
} finally {
    if ($Watch) { Stop-Job $Watch; Receive-Job $Watch -ErrorAction SilentlyContinue | Out-Null; Remove-Job $Watch }
    @{status=$FinalStatus; failure=$Failure; inference_started=$InferenceStarted; ended_at=(UTC)
      limitation='Existing host-native baseline only; no clean-OS/bare-machine restoration proof. Weights not freshly hashed.'
      benchmarked=$false; approved_for_runtime=$false} | ConvertTo-Json | Set-Content -Encoding UTF8 "$Run\operator-result.json"
}
Write-Host "FP-001D $FinalStatus. $Failure"
Write-Host "Retain all files in $Run. Restore ESET proactive blocking and verify protection BEFORE reconnecting. Do not rerun acceptance."
