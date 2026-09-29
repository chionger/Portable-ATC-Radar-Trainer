# FP-001D â€” Offline runtime preservation

`Runtime Preserved != Benchmarked != Approved for runtime`.

This packet adds operator-invoked preservation contracts, a verifier and a small
offline restoration/inference probe. It does not integrate inference into the ATC
application, change FP-001A/B/C contracts, run benchmarks, or approve a model.
FP-027/028/030 remain out of scope.

The single reference is `openai-whisper-large-v3-turbo-41f01f3`, revision
`41f01f3fe87f28c78e2fbf8b568835947dd65ed9`. Its current local snapshot was found.
Runtime artifacts are now assembled for the frozen Windows x64 / CPython 3.12.10 /
Torch 2.7.1+cpu / Transformers 4.53.3 reference. Real acceptance remains **BLOCKED**
pending the new-account, manually disconnected operator run. See the
[assembly record](../../docs/evidence/fp001d/FP-001D-CODE-EVIDENCE.md),
[real definition](definitions/whisper-turbo-win64-cpu-1.0.0.json), and
[operator procedure](../../docs/evidence/fp001d/OFFLINE-OPERATOR.md).
No passing run or runtime approval is claimed.

CPython 3.12.10 is the last official Python 3.12 Windows binary release and an
accepted compatibility-preservation reference, not the current-security 3.12
release. Later production/runtime approval must reassess interpreter security.
This run permits the existing host-native Windows baseline and cannot prove
clean-OS/bare-machine native dependency restoration.

## Preservation layers and scope

Durable artifacts are the primary preservation layer: a complete offline CPython
installer/distribution, every direct and transitive dependency wheel, any required
native redistributable installer, exact dependency lock, licence material, tooling
source, and a small acceptance input. Preserve bytes, original sources, versions,
sizes and SHA-256 values outside **all** Git checkouts. An installed environment,
`pip freeze`, a dependency list, or a provider cache alone is insufficient.

An optional container image can make startup convenient. It cannot replace the
bootstrap and wheels. Archive an image outside Git, record its artifact digest,
and retain the same durable restoration path even if the container service or
image registry disappears. This packet does not build images.

Record OS version, CPU instruction requirements, architecture, RAM, GPU, driver and
CUDA compatibility as host requirements. Do not preserve operating systems, BIOS,
firmware or hardware. The bounded reference recipe uses CPU/float32, one thread,
English transcription and at most 128 generated tokens. GPU, driver and CUDA
requirements are explicitly recorded as not required for this CPU recipe. Other
platform profiles require separately validated definitions; no performance claim
follows from this recipe.

## Separate contracts

* `runtime-preservation-definition.schema.json` describes a versioned recipe,
  exact `entry_id` and immutable model revision, engine/interpreter/dependency
  identities and sources, durable artifacts, host requirements, configuration,
  bootstrap/environment/start procedures and acceptance input.
* `runtime-preservation-evidence.schema.json` describes one run against that exact
  definition: its canonical SHA-256, timestamp, observed components/platform,
  verified artifact digests, restoration/load/inference outcomes, network isolation
  evidence, input/output digests and retained logs. It cannot grant benchmark or
  runtime approval.

Schemas provide structural validation. The Python verifier additionally enforces
cross-record references, unique paths/identities, durable component artifact
coverage, exact model revision linkage and passing-outcome requirements. Run it
even when a JSON Schema validator succeeds. Regenerate structural schemas with
`python -m scripts.runtime_preservation_schemas`; CI/review can use `--check`.

Definition identity hashes canonical validated JSON (`sort_keys=True`, ASCII,
compact separators). Evidence must change whenever definition content changes.
`PASSED` requires a clean restoration, model load, a completed small inference,
zero external retrievals, OS isolation covering both restoration and inference,
observed versions matching every component, an observed supported OS/architecture
and sufficient actual RAM,
verified durable artifacts, and retained integrity/restoration/inference/network
records. Observed hardware facts are recorded separately from requirements. Native
prerequisites explicitly use the existing-host-baseline restoration scope.

Evidence validation checks a claim's consistency; it is not an attestation service
and cannot prove that manually entered logs describe a real run. Review the logs
and their provenance. Metadata validity, file presence, size checks and fresh
SHA-256 verification are reported separately. The verifier never infers successful
execution from metadata or changes catalogue lifecycle flags.

## Assemble the external bundle (owner gate)

1. Confirm the exact reference entry/revision and its small snapshot metadata.
   Reuse existing preservation/integrity records. Do not rehash existing large
   weights without explicit approval. Do not substitute another model.
2. Choose and record an exact CPython version and complete offline installer,
   exact Transformers/Torch versions and compatible platform wheel tags. Resolve
   the full transitive closure on an assembly machine. Include pip and its needed
   bootstrap resources, NumPy, safetensors, tokenizer dependencies, applicable
   native libraries/redistributables and licences. Source distributions requiring
   an online build are not supported. The frozen reference selection is recorded above; synthetic fixture versions
   are never recommendations.
3. Inventory every preserved file with size, SHA-256 and original source URI;
   reference required files from each component. Record non-Python installers as
   bootstrap artifacts and their exact installation commands in the bootstrap
   procedure. Record the lock and procedure as procedure artifacts and preserve
   this repository's exact source revision/archive as a source artifact.
4. Create `requirements.lock` containing one exact pin and one wheel hash per
   line, e.g. `package==1.2.3 --hash=sha256:<64-lowercase-hex>` (replace placeholders).
   No URLs, includes, editable installs, extra indexes or ranges. One definition
   represents one supported platform; include the actual wheel selected for it.
5. Preserve a rights-cleared, non-empty mono PCM16 WAV at 16 kHz, no longer than
   10 seconds. Record its digest; no expected transcription quality is required.
6. Write a real definition only after those facts and artifacts exist. Validate
   metadata and exact model linkage. Missing artifacts, new large downloads,
   unsupported host compatibility or ambiguous restoration steps stop acceptance
   and require an owner decision. The bounded reference assembly was authorized and is now recorded above.

Example layout outside Git:

```text
<runtime-root>/<preservation-id>/<version>/
  bootstrap/           offline interpreter/native installers
  wheels/              complete pinned wheel closure
  requirements.lock
  source/              preserved tool source
  licences/
  input/acceptance.wav
  procedure/           exact host-specific installation instructions
<evidence-root>/<run-id>/
  restoration.txt  inference.json  isolation.txt  model-integrity.json
```

Definitions use relative paths beneath the explicitly supplied runtime root.
Evidence log paths are relative to the separately supplied evidence root.
Keep roots outside the model snapshot as well, so restoration cannot overwrite it.

## Restore and accept without external retrieval

First verify the definition and its artifacts on a trusted controller. The default
command is read-only metadata validation. `--artifact-root` adds existence/size
checks. `--hash-files` explicitly hashes only referenced runtime artifacts and
evidence logs; it never hashes model weights or scans all Model Zoo models.

```powershell
python -m scripts.verify_runtime_preservation --definition <definition.json> `
  --manifest model-zoo/manifest.json --artifact-root <runtime-root> --hash-files
```

Then establish OS-enforced network isolation **before bootstrap installation**,
for example a disposable machine with all network adapters disconnected. Keep
isolation active through installation and inference and record its mechanism,
start/end coverage and independent observations. Do not alter the user's host
network settings automatically. A Python audit hook and offline environment flags
are defense in depth; native code can bypass them. Containers are optional, and
container-only isolation logs do not establish a separate durable restoration.

Install the preserved interpreter and native prerequisites into a fresh external
location using the exact recorded bootstrap commands. The installer must not be
a web installer. Record version, host hardware/compatibility and each exit status.
Create a new external virtual environment, with no system site packages, using
that interpreter's offline `venv`/`ensurepip`. Do not reuse the development `.venv`.
The following illustrates the subsequent fixed commands; replace placeholders
using the definition and run each only after the previous command succeeds:

```powershell
& <restored-python> -m venv <new-external-environment>
& <new-environment-python> <preserved-source>/scripts/offline_runtime_probe.py install `
  --wheelhouse <runtime-root>/wheels --lock <runtime-root>/requirements.lock
& <new-environment-python> <preserved-source>/scripts/offline_runtime_probe.py check
& <new-environment-python> <preserved-source>/scripts/offline_runtime_probe.py infer `
  --model <exact-local-whisper-snapshot> --audio <runtime-root>/input/acceptance.wav `
  --manifest <preserved-source>/model-zoo/manifest.json --definition <definition.json> --max-new-tokens 32
```

Retain complete stdout/stderr and exit statuses outside Git. The installer uses
`--no-index`, `--no-cache-dir`, `--only-binary=:all:` and `--require-hashes`; missing
dependencies fail closed. `pip check` checks the restored dependency closure. The
probe installs a Python socket audit guard before engine imports, requires an
existing local snapshot with the exact reference entry/revision, checks file sizes
and small-file hashes without rehashing weights, uses `local_files_only=True` and `trust_remote_code=False`,
and produces a small JSON result with input/output hashes and observed versions.
It does not calculate WER, accent quality, latency, GPU performance, quantization
quality or ATC suitability. Empty transcription is allowed; a produced token
sequence establishes execution, not accuracy.

Review logs and construct a run record under the evidence contract. Reference the
existing model-integrity record with its provenance, date, expected weight digest
and the limitation that weights were not freshly rehashed. If that evidence is
insufficient for the owner, stop for approval before rehashing. A failed executed
attempt is `FAILED`; an attempt stopped before restoration is `BLOCKED`. When no
complete definition exists, record a preflight blocker separately rather than
inventing version numbers or hashes to make an evidence record validate.

```powershell
python -m scripts.verify_runtime_preservation --definition <definition.json> `
  --manifest model-zoo/manifest.json --evidence <run.json> `
  --artifact-root <runtime-root> --evidence-root <evidence-root> --hash-files
```

Exit codes: `0` = consistent metadata (and any requested file checks), `1` = valid
FAILED/BLOCKED evidence, `2` = invalid metadata/linkage/path/integrity or unreadable
input. Exit `0` alone is never a runtime-preservation claim. Review actual evidence.

## Git and test boundaries

Git contains schemas, definitions when real facts exist, small evidence summaries,
verification/probe source, documentation and synthetic JSON fixtures. Package
caches, weights, runtime installers, wheels and images remain external. The asset
safety checker now also rejects runtime package/binary extensions, runtime artifact
directories and archives under `model-zoo`, including force-added ignored files.

`tests/fixtures/runtime-preservation` is synthetic metadata, not a usable bundle or
proof that Whisper ran. Tests exercise missing/mismatched revisions and hashes,
unsafe paths, false success claims, schema drift, Git safety, blocked retrieval and
fail-closed probe behavior without downloading, reading or hashing model weights.
