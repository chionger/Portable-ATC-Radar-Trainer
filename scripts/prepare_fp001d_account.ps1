# Run once in an elevated Windows PowerShell window, while still connected.
# Does not alter network settings, existing Python installations or model files.
$ErrorActionPreference = 'Stop'
$Bundle = 'D:\ATC-Runtime-Preservation\whisper-turbo-win64-cpu\1.0.0'
$Restore = 'D:\ATC-Runtime-Restore\fp001d-reference-001'
$Name = 'FP001DReference'
if (Get-LocalUser -Name $Name -ErrorAction SilentlyContinue) { throw 'Account already exists; stop for review.' }
if (Test-Path -LiteralPath $Restore) { throw 'Restore path already exists; stop for review.' }
$Password = Read-Host 'Set a password for the new standard FP001DReference account' -AsSecureString
$Controller = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$User = New-LocalUser -Name $Name -Password $Password -Description 'Bounded FP-001D offline acceptance only'
$UsersGroup = Get-LocalGroup -SID 'S-1-5-32-545'
Add-LocalGroupMember -Group $UsersGroup -Member $Name
New-Item -ItemType Directory -Path $Restore | Out-Null
$Sid = $User.SID.Value
# Exact new roots only. The model inherits its existing read permissions; no model ACL mutation.
& icacls.exe $Bundle /grant "*${Sid}:(OI)(CI)RX"
if ($LASTEXITCODE -ne 0) { throw 'Bundle read permission failed' }
& icacls.exe $Restore /grant "*${Sid}:(OI)(CI)M"
if ($LASTEXITCODE -ne 0) { throw 'Restore permission failed' }
[ordered]@{
    name=$Name; account_sid=$Sid; controller_sid=$Controller
    created_at=[DateTime]::UtcNow.ToString('o'); new_account=$true
    restore_path=$Restore; bundle_path=$Bundle
} | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath "$Bundle\procedure\account.json"
Write-Host 'Account prepared. Follow OPERATOR.md before running acceptance. No acceptance has run.'
