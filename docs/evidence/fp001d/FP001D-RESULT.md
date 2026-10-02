# FP-001D: restoration and separate inference verified

The exact openai-whisper-large-v3-turbo-41f01f3 reference, revision
41f01f3fe87f28c78e2fbf8b568835947dd65ed9, loaded locally and generated [[2411]].
Decoded output was " .". This was the one preserved synthetic PCM16 16-kHz input;
no quality, WER, latency or other benchmark was performed and none is inferred.

Definition 1.0.4 canonical SHA-256:
f9111b785e4ad4d9b379be2a30fc80e63e3dd72df0ce5353c75ef6af8cb68881.
Source revision: 9f2faed0117aa18f7a0864c5061a9d14ec5073ae.
CPython 3.12.10 and all 31 packages matched the lock, including torch 2.7.1+cpu
and transformers 4.53.3. All 151 bundle artifacts and retained inference-log
digests verified. Input/output hashes and full inventory are in
SEPARATE-INFERENCE-VERIFIED.json and the preserved definition.

Restoration attempt fp001d-run-004 completed bootstrap, venv, package installation
and pip check offline, then stopped at its RAM guard. Inference-session-001 later
completed with 9,306,894,336 bytes available before model load. Its 73 adapter/route
snapshots all showed isolation, 3 October 2026 00:22:01 to 00:23:59 Singapore time.
No external retrieval was observed; local-only loading and Python audit guard
were active. This is not native packet-capture evidence.

IMPORTANT: restoration and inference occurred in separate offline sessions with
reconnection/restart between them. Original uninterrupted acceptance remains
NOT SATISFIED. Do not mark prior FAILED evidence as PASSED or silently weaken the
acceptance contract. Owner review may accept the separately evidenced result or
define future work; no further inference is authorized by this report.

Download ledger: 307,335,801 bytes; no new downloads for this review.
D assets at review: 2,061,545,288 bytes (before small report copies), below 10 GiB.
C pre-inference accounting: 3,027,448,018 bytes, including a conservative 2 GiB
prior-account/controller reserve, below the approved 4 GiB cap. This is not a
fresh full C: measurement. Large/binary runtime assets remain outside Git.

Limitations: large weights were size-checked using historical digest/provenance,
not freshly hashed; 12 small model files were hashed. Existing native Windows
baseline was used; clean-OS restoration and future-OS portability are not proven.
CPython 3.12.10 is a compatibility-preservation reference, not the current-security
Python 3.12 release; future approval must reassess that baseline. The retained
attention-mask warning does not invalidate generated-token execution evidence,
but no reliability or accuracy claim is made. ESET enabled was instructed for
inference; protection state was not independently audited.

Prior code validation: backend run 821 passed with one Git ownership setup failure;
the Git safety suite then passed all 7 checks with checkout-scoped configuration.
Pip invocation regression and lint passed. This review additionally validates
actual tokens, configuration, package closure, source/definition linkage, network
observations and digests. No inference rerun, code change, or benchmark occurred.

Keep PR #37 draft and unmerged. No production integration, FP-027/028/030 work,
or runtime approval. Runtime Preserved != Benchmarked != Approved for runtime.
