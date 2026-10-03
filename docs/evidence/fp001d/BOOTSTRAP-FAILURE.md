# FP-001D bootstrap failure — 1 October 2026

The disconnected run reached CPython bootstrap and FAILED. The installer log
records `0x80070005` (Access denied), `Failed to load UX DLL`, and `Failed to load UX`.
No restored Python directory, venv, model load or inference exists. All original
logs remain in `D:\ATC-Runtime-Restore\fp001d-reference-001\fp001d-run-001`.
The run location is deliberately not reset while the denial cause is unresolved.

Four network snapshots reported isolation from 14:21:19.836609Z through
14:21:27.5519533Z. This is failed-bootstrap evidence, not successful full
restoration/inference coverage. The installer failure is independent of the
previous network preflight problems.

The wrapper also lost its process exit code, producing a blank error message.
The draft source now creates and owns a System.Diagnostics.Process directly,
captures both streams asynchronously and reads its exit code before disposal.
Synthetic Windows PowerShell 5.1 tests verify 0, 37 and -2147024891, including
stdout/stderr and retained exit values. The frozen bundle remains 1.0.1 so the
failed attempt retains its exact definition/source linkage. No new acceptance
runner is staged until the actual installer denial is understood.

The extracted PythonBA.dll has no Authenticode signature, but unsigned status
alone does not explain the denial. Its ACL grants the test user full control.
No installer-specific Windows CodeIntegrity, AppLocker or Defender event was
found in the inspected time window. ESET and Defender are registered, but neither
is established as the cause. Obtain any exact Windows/ESET block notification
or security-product event for 1 October 2026, 22:21 Singapore time.

No antivirus/security-policy changes, administrator installation, alternate
runtime, installer retry, model operation or additional download was performed.
Before bootstrap the runner measured C: test profile 1,298,377,177 bytes and
D: assets 310,303,233 bytes, within the respective 2 GiB and 10 GiB caps.

See bootstrap-diagnosis.json for retained log sizes/digests and bootstrap-failed.json
for the definition-linked FAILED record. The installer HRESULT comes from its
own retained log; the missing wrapper exit code has not been fabricated.

Keep PR #37 draft and unmerged. Runtime Preserved != Benchmarked != Approved for runtime.

Validation after reporting fix: 821 backend tests passed (including three exact process-exit cases), lint and Git asset safety passed. Definition/runtime/log hashes and FAILED evidence linkage verified successfully.
