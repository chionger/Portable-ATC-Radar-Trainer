# FP-001D: one offline acceptance run

Current state: runtime bytes assembled; acceptance NOT RUN. Do not merge PR #37.

The frozen reference is Windows x64, CPython 3.12.10, Torch 2.7.1+cpu,
Transformers 4.53.3 and exactly 31 wheels. CPython 3.12.10 is accepted as the
last official Python 3.12 Windows binary release and a compatibility-preservation
reference. It is **not** the current-security Python 3.12 release. Later
production/runtime approval must reassess the interpreter security baseline.

This needs your manual actions because the authorized isolation method requires
you to disable/disconnect networking, and the new Windows account needs a password
entered locally. Do not enter that password in chat. Once disconnected, this chat
may be unavailable; the runner is self-contained.

## 1. Prepare the new account while connected

Open **Windows PowerShell as Administrator** and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\ATC-Runtime-Preservation\whisper-turbo-win64-cpu\1.0.0\procedure\prepare_fp001d_account.ps1"
```

The script prompts securely for a password, creates the standard local account
`FP001DReference`, records its SID/time, grants read access to the exact bundle,
and grants write access to the new restore directory. It does not modify the
existing model, existing Python installation, or networking. If the account or
restore directory already exists, stop; do not reuse or delete it.

## 2. Disconnect before any restoration

Sign into `FP001DReference`. Close unnecessary applications so at least 8 GiB
physical RAM is available. Before starting the runner, manually unplug Ethernet,
USB tethering and any other network connections, and disable Wi-Fi, Bluetooth
networking, VPN/virtual adapters and every other network-capable adapter.
Airplane mode alone is insufficient. Keep everything disconnected until the
runner explicitly ends. Do not enable networking to resolve an error.

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
D:\ATC-Runtime-Restore\fp001d-reference-001\fp001d-run-001
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
