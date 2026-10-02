# One final FP-001D Windows reference attempt

On 2 October 2026 the operator approved one final bounded Windows acceptance
effort and answered yes to both pending decisions:

- Raise the C: task allowance from 2 GiB to 4 GiB for this final attempt.
- Temporarily pause only ESET LiveGuard proactive blocking while fully offline,
  restoring its original setting before reconnecting. Other protection stays enabled.

All other original constraints remain: 500 MiB maximum newly downloaded data,
10 GiB D: assets, exact existing model and frozen Windows dependency family,
no fresh large-weight hash, no benchmark or production integration, no merge of
PR #37. Retain all prior failures and diagnostic logs. At most one more acceptance
attempt; stop on failure. Preparation/review target: 60–90 minutes active work.

Use a new standard account FP001DFinal and fresh root
D:\ATC-Runtime-Restore\fp001d-final-003 to avoid existing per-user Python
registration affecting bootstrap. Account metadata belongs in that new root;
the previous account metadata remains unchanged. Account creation is a preparatory
manual administrator step, not permission to execute acceptance before staging
and definition/evidence linkage are verified.

The result, if successful, establishes a Windows reference under the declared
temporary protection configuration, not clean-OS/native restoration, future-OS
compatibility, security approval, or production readiness.
