# FP-001D network preflight recovery — 30 September 2026

Two saved preflights were BLOCKED before bootstrap. Zero model inference attempts.
The second showed disconnected Wi-Fi, a remaining Wi-Fi default route, and three
hidden WAN bookkeeping miniports reporting Up without routes. The original guard
was too broad for those unrouted miniports; the default route was independently
blocking and is still rejected.

The corrected PowerShell guard and retained-evidence validator agree: only WAN
Miniport (Network Monitor), WAN Miniport (IP), and WAN Miniport (IPv6) may report
Up without blocking when they have **no routes**. Every other Up adapter, every
routed Up miniport and every IPv4/IPv6 default route still blocks. No network
settings were changed by the agent. Manual disconnection remains mandatory.

Definition version **1.0.1** has 151 hash-verified artifacts.
Canonical SHA-256: `454ff84551f00a575e13190645b75074e528e0909c18daf1478f3b5f4239da61`.
Source revision: `1b9749b34d45bfb1e410e41273db3a074d9f7454`.
The existing bundle directory name `1.0.0` is retained; definition identity is 1.0.1.
Original source/procedure/definition bytes are archived under
`evidence/revisions/1.0.0`. Both blocked attempts and their integrity records are
retained under `D:\ATC-Runtime-Restore\fp001d-reference-001`.

New downloads for this repair: **0 bytes**. The original cumulative runtime/licence
download total remains **307,335,801 bytes**. Wheels, installers, model and input
are unchanged. No weights were freshly hashed or modified. No runtime was installed.

Validation: **82 focused tests; 818 backend tests passed**, including seven cases
exercising the actual PowerShell policy and the evidence validator. Lint, types
and PowerShell syntax passed. The existing Starlette/AnyIO warning remains.
Frontend code was unchanged; prior six frontend tests/build remain the last results.

`-CheckNetworkOnly` is a read-only mode: it reads adapters/routes and reports
READY/BLOCKED without creating an acceptance run or restoring/loading anything.
It was exercised on the connected host and blocked, without creating a run.
Only after it reports READY should the operator invoke the acceptance command.

Follow [OFFLINE-OPERATOR.md](OFFLINE-OPERATOR.md). In the usual administrator
account, open `ncpa.cpl` and **Disable** Wi-Fi (disconnecting an SSID is insufficient
when a default route remains). Disable/unplug other network transports, then
switch into FP001DReference. Do not disable/uninstall Windows WAN miniports.

Acceptance remains BLOCKED / not executed; PR #37 remains draft and unmerged.
CPython 3.12.10 remains a compatibility reference, not the current-security release;
later approval must reassess security. Existing host-native baseline is permitted
but clean-OS/bare-machine native restoration is not proved.

Runtime Preserved != Benchmarked != Approved for runtime.
