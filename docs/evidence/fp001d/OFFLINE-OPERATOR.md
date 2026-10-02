# Final FP-001D Windows acceptance: attempt 004

Reopened by owner after the pip invocation defect; one corrected attempt. FP001DRecovery is the fresh standard account. Restore root:
D:\ATC-Runtime-Restore\fp001d-recovery-004. Prior attempts remain intact.
No inference has occurred in earlier attempts. The pip diagnostic and repair both
failed reading newly written pip.exe. ESET involvement is suspected, not proven.

The operator approved temporarily pausing ONLY ESET LiveGuard proactive blocking
while fully offline. Do not disable other protection. Record the original setting
and the change time. Restore that setting and verify protection before reconnecting,
whether this attempt passes or fails. Record the restoration and reconnection times.
The script records operator confirmation, not an independent security-setting audit.

1. Keep protections enabled during preparation. Close unnecessary applications.
2. Manually disable/disconnect all networking before changing ESET settings.
3. In ESET Advanced setup > Protections > Cloud-based Protection > ESET LiveGuard,
   change only Proactive protection to allow execution during analysis. If the
   installed UI offers no such setting, stop and report; do not disable all ESET.
   Official reference: https://help.eset.com/essp/18/en-US/idh_config_liveguard.html
4. Sign into FP001DRecovery, still offline. Open ordinary PowerShell.
5. Run the staged run_fp001d_offline.ps1 with -CheckNetworkOnly. Proceed only on READY.
6. Run once with -ConfirmManuallyDisconnected -ConfirmProactiveBlockingPaused.
7. Wait for completion; retain logs. Restore ESET's original setting while offline,
   verify protection is active, then reconnect and report the final output and times.

Frozen candidate: Windows x64, CPython 3.12.10, PyTorch 2.7.1+cpu, Transformers
4.53.3, 31 wheels. CPython 3.12.10 is the last official 3.12 Windows binary
release and a compatibility reference, not the current-security release. Later
production approval must reassess interpreter security. Existing host-native
libraries are permitted; no clean-OS native restoration proof is claimed.

Limits: 500 MiB cumulative downloads; 10 GiB D: assets; approved C: cap 4 GiB.
Runner reserves 2 GiB for previous account/controller assets and permits less than
2 GiB for the new profile (with a conservative 1800 MiB in-process stop threshold).
Weights get size checks and historical provenance only; small files are hashed.
Exactly one synthetic input; no benchmark. No additional runtime family.
Stop on failure, source build, CUDA/GPU dependency, weight change/download, or cap.
PR #37 remains draft and unmerged. Runtime Preserved != Benchmarked != Approved for runtime.
