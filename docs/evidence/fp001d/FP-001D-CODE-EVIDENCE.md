> Latest outcome: [1 October bootstrap failure](BOOTSTRAP-FAILURE.md). Installer access denied; no inference. Do not rerun until diagnosed.

> Current update: [network recovery and definition 1.0.1](NETWORK-RECOVERY.md). The assembly record below is historical; acceptance remains pending.

# FP-001D — CODE + EVIDENCE, operator handoff

**Runtime assembly complete; offline acceptance BLOCKED / NOT RUN. PR #37 remains draft and must not be merged.**

The blocking step is the explicitly required manual network disconnection and
new Windows account session. No account has yet been created. The prepared
account script prompts locally for a password; no password belongs in chat.
Follow [OFFLINE-OPERATOR.md](OFFLINE-OPERATOR.md). After the single run ends,
return to the chat for evidence inspection and the final acceptance PR update.

## Actual assembly

- Windows x64, CPython 3.12.10, Torch 2.7.1+cpu, Transformers 4.53.3.
- Exactly 31 preserved wheels: 261,367,389 bytes; expanded wheel payloads:
  1,382,478,818 bytes (metadata sum, not an installed environment).
- Python installer: 26,964,224 bytes;
  SHA-256 `67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb`.
  Valid Python Software Foundation Authenticode signature.
- MSVC 14.51.36247.0 installer: 18,731,856 bytes;
  SHA-256 `843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c`.
  Valid Microsoft signature; preserved, not executed.
- Total newly downloaded HTTP response bodies: **307,335,801 bytes**
  (293.098 MiB), including four licence sources.
  No retries, source distributions, model downloads, or additional runtime families.
  All 31 wheel hashes and MSVC hash match their recorded upstream digests.
  Python has a fresh SHA-256 and valid signature; no upstream Python SHA-256 was
  available in the original proposal, so one is not falsely claimed as compared.
- 150 definition artifacts: **309,060,245 bytes**. Complete sizes, SHA-256s and
  source URIs: the external artifact-inventory.csv,
  [definition](../../../model-zoo/runtime-preservation/definitions/whisper-turbo-win64-cpu-1.0.0.json), the external download ledger.
- Actual full directory footprints at the final measurement are in
  the external storage record. No D: restored environment or C: acceptance-user
  profile exists yet. Caps remain 10 GiB D: and 2 GiB C:; no disk preallocation.

Durable root: `D:\ATC-Runtime-Preservation\whisper-turbo-win64-cpu\1.0.0`.
All installers, wheels and WAV bytes are outside every Git checkout. The
definition, summaries, schemas and source changes are the only Git additions.
Source commit: `402619d9296715605e8efb3aa282c82d7ab0f6f5`.
Canonical definition SHA-256: `e05bc39471d80cc8d20fa800672a7b4578408a7e52f6722fdefd783384b0693f`.

Downloaded artifacts retain original HTTPS URIs. Licence texts extracted from
wheels retain the corresponding wheel URI. Locally generated input, lock and
assembly helper files use a procedure/source-context URI rather than pretending
they were downloaded; their exact bytes and generation source are preserved in
the bundle. The source commit identifies the runner; per-file hashes also bind
the externally preserved assembly helpers. Historical local model records use
the catalogue context and are copied unchanged.

## Restoration / inference / isolation results

**Not executed.** No generated tokens or inference text exists; no restoration
or isolation success is claimed. [assembly-blocked.json](assembly-blocked.json)
validates against the frozen definition and is deliberately BLOCKED. Its zero
acceptance retrieval count denotes no acceptance execution, not proven offline
coverage. Assembly itself was online and is recorded separately.

The staged runner requires a new account, fresh CPython and venv, no system site
packages, successful bootstrap/install/pip-check exits, one generated sequence,
and manually disabled/disconnected networking throughout restoration/inference.
Adapter/route snapshots and timestamps, full subprocess logs, input/output
digests, component versions and host facts are retained. No second inference or
retry is scheduled. The runner has passed syntax inspection and synthetic tests;
its actual end-to-end restoration behavior remains unproved until the operator run.

## Code and checks

The bounded change adds definition-bound inference; real observed host/RAM and
native-baseline fields; normalized package names; explicit exit/account/time
evidence; retained-log verification; and the self-contained offline wrapper.
`--acceptance` requires both artifact/evidence roots, fresh runtime/log hashes,
passing execution and reproducible evidence linkage. Metadata validity alone
still cannot establish preservation.

- **75 focused tests passed; 811 backend tests passed; 6 frontend tests passed.**
- Python lint/types, schema drift, architecture, Git asset safety, frontend
  lint/types/build and PowerShell parsing passed.
- The first broader run had 810 passes and one Git ownership environment failure.
  A process-only trust setting for this exact checkout resolved it; the final
  full suite passed. The existing Starlette/AnyIO deprecation warning remains.
- Retained logs: external `evidence/tests/`; [test-results.json](test-results.json).
- No WER, quality, latency, accents, ATC phraseology, GPU or other benchmark.

## Limitations and owner gate

CPython 3.12.10 is the last official Python 3.12 Windows binary release, accepted
as a compatibility-preservation reference. It is **not the current-security
Python 3.12 release**. Later production/runtime approval must reassess the
interpreter security baseline.

The permitted existing host-native Windows/MSVC baseline does **not** prove
clean-OS/bare-machine native dependency restoration. The native installer is
preserved but not exercised. Account separation alone is not a network boundary.
Network snapshots/manual disconnection are not independent packet capture.

The exact Whisper reference is `openai-whisper-large-v3-turbo-41f01f3`, revision
`41f01f3fe87f28c78e2fbf8b568835947dd65ed9`. All 13 sizes and 12 small-file hashes
were freshly checked. The 1,617,824,864-byte weight file was **not freshly hashed**;
historical SHA-256 `542566a422ae4f3fd23f1ba11add198fca01bbf82e66e6a2857b3f608b1eb9d1`
and provenance are reused. The original acquisition note contains a revision
placeholder; exact linkage relies on the immutable catalogue/snapshot path.

No production integration, FP-027/028/030, runtime approval, auto-merge or merge.

**Runtime Preserved != Benchmarked != Approved for runtime**.
