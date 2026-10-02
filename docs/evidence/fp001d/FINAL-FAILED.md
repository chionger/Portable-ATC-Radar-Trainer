# Final FP-001D attempt: FAILED, no further retry

Attempt 003, definition 1.0.3: Python bootstrap and venv creation both exited 0.
Package installation exited 1: pip required invocation through python -m pip
to modify itself. The preserved wrapper sets argv[0] to pip and invokes it via
runpy, while the lock requests pip 25.1.1 over bundled 25.0.1. This is a wrapper
defect, not the earlier access-denied error. Focused tests missed this integration
case. The frozen failed artifacts are unchanged; no fix or further execution made.

No model load or inference. All 44 network snapshots reported isolated, covering
14:30:59.217114Z to 14:31:50.9369004Z on 2 October. This is failed-restoration
coverage, not successful offline acceptance or proof of zero native network calls.
ESET setting restoration and reconnection timing still require operator confirmation.

Last recorded storage: D assets 450,961,966 bytes; C accounted with prior reserve
2,254,259,050 bytes, below approved limits. No new downloads; cumulative artifact
download ledger remains 307,335,801 bytes. No weights freshly hashed or modified.

85 focused tests passed before this run; prior full backend suite had 821 passes.
Those results do not establish integration success. Keep PR #37 draft and unmerged.
Final attempt exhausted. Preserve evidence and return to MVP work unless the owner
explicitly changes scope later. Runtime Preserved != Benchmarked != Approved for runtime.
