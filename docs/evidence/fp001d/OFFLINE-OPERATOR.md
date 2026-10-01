# FP-001D: one offline acceptance run

Current state: bootstrap attempt 001 FAILED before installation/inference. Help-only diagnostic passed; controlled attempt 002 is prepared, not executed. Do not merge PR #37.

The frozen reference is Windows x64, CPython 3.12.10, Torch 2.7.1+cpu,
Transformers 4.53.3 and exactly 31 wheels. CPython 3.12.10 is accepted as the
last official Python 3.12 Windows binary release and a compatibility-preservation
reference. It is **not** the current-security Python 3.12 release. Later
production/runtime approval must reassess the interpreter security baseline.

This needs your manual actions because the authorized isolation method requires
you to disable/disconnect networking, and the new Windows account needs a password
entered locally. Do not enter that password in chat. Once disconnected, this chat
may be unavailable; the runner is self-contained.

## 1. Use the already-created reference account

Use `FP001DReference`; do not recreate the account or rerun account preparation.
The failed bootstrap did not create the interpreter or venv. Attempt 002 retains
the fresh interpreter/venv destination checks and uses separate temp/cache folders.
Attempt 001 and warning-diagnostic-001 remain unchanged. The help-only diagnostic
loaded the installer interface and exited 0; the operator reports no Windows or
antivirus setting changes. The original access-denied cause is still unknown.
This is one controlled retry, not a claim that the cause has been fixed.

## 2. Disconnect before any restoration

Sign into `FP001DReference`. Close unnecessary applications so at least 8 GiB
physical RAM is available. Before starting the runner, manually unplug Ethernet,
USB tethering and any other network connections, and disable Wi-Fi, Bluetooth
networking, VPN/virtual adapters and every other network-capable adapter.
Airplane mode alone is insufficient. Keep everything disconnected until the
runner explicitly ends. Do not enable networking to resolve an error.

### Read-only network preflight

Two blocked preflights were preserved; neither installed Python nor attempted inference.
The corrected guard tolerates only the three named Windows bookkeeping WAN miniports
when they have no routes. Every other Up adapter, every routed Up miniport, and every
default route still blocks acceptance. Do not disable/uninstall Windows WAN miniports.

Before switching accounts, open `ncpa.cpl` from Win+R in your usual administrator
account, right-click **Wi-Fi**, and select **Disable**. Disable Ethernet/tethering
or other transport adapters too. This is stronger than Disconnect from a Wi-Fi
network. Then switch into FP001DReference without re-enabling networking.

First run this read-only check; it creates no run directory and does not restore
or load anything, so it may be repeated after correcting networking:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\ATC-Runtime-Preservation\whisper-turbo-win64-cpu\1.0.0\procedure\run_fp001d_offline.ps1" -CheckNetworkOnly
```

Proceed to acceptance only if it prints **NETWORK PREFLIGHT READY**. If blocked,
retain the displayed reasons. Do not keep invoking the acceptance command.
The bundle remains at its original directory; revised definition version 1.0.2
and hashes identify the corrected procedure. Versions 1.0.0 and 1.0.1 source/definition and
both blocked network logs remain preserved as historical evidence.

## 3. Run exactly once from the new account

Open ordinary Windows PowerShell in `FP001DReference`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\ATC-Runtime-Preservation\whisper-turbo-win64-cpu\1.0.0\procedure\run_fp001d_offline.ps1" -ConfirmManuallyDisconnected
```

The runner refuses an existing run/interpreter/venv, checks every preserved
artifact, records adapter/route state before bootstrap and throughout execution,
restores CPython to a fresh D: location, creates a fresh venv without system site
packages, installs only the hashed local wheels, and runs `pip check`.
It then loads only the existing exact Whisper snapshot and submits the single
preserved one-second synthetic PCM16/16-kHz WAV once. It retains generated tokens
and any decoded text. Empty decoded text is allowed; no quality judgment is made.

No additional downloads, model copies/modifications, source builds, CUDA/GPU,
alternate runtime families, benchmarks or production integration are allowed.
The runner stops on errors; do not rerun it or repair by adding packages. A
30-minute operator stop bound is not a latency measurement. Do not run either
installer separately or install/repair the host MSVC baseline.

Budget: 500 MiB maximum newly downloaded bodies (assembly ledger counts retries;
no retries were used), 10 GiB total D: bundle/restore/evidence allowance, and
2 GiB total C: temporary/account/bootstrap allowance. TEMP/cache/restore use D:;
the new C: user profile is checked with conservative headroom. If any unexpected
system cache, download or write would exceed these bounds, stop immediately.
Existing model storage is excluded because it is unchanged and not copied.

## 4. Retain results and reconnect

After the runner prints its final status, networking may be restored. Keep all
files under:

```text
D:\ATC-Runtime-Restore\fp001d-reference-001\fp001d-run-002
```

Return to this chat and state that the one run ended. Do not rerun acceptance.
The results will be inspected, their hashes/definition linkage verified, and
the draft PR updated. If any error occurs before the runner can create logs,
retain the exact PowerShell error text. A failure is evidence, not permission
to substitute a runtime or expand scope.

## Evidence limits

The declared existing Windows/MSVC native baseline is permitted. This does
**not** prove clean-OS/bare-machine native dependency restoration. The matching
MSVC installer is preserved but is not executed in this run. OS/CPU/native facts
are retained, with actual available RAM checked before model loading.

The 1,617,824,864-byte weight file receives only a size check. Its historical
catalogue SHA-256 is reused; it is **not freshly rehashed**. Small model files
receive fresh hashes. The original acquisition note contains a revision
placeholder, so exact linkage uses the catalogue and immutable snapshot path;
that historical note is retained unchanged.

Adapter/route snapshots plus your manual physical/OS disconnection establish
the declared boundary; they are not packet capture or independent forensic
attestation. A gap greater than 30 seconds fails evidence collection. Python
socket denial and local-only flags supplement the OS boundary.

**Runtime Preserved != Benchmarked != Approved for runtime**.
