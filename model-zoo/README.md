# Local model zoo operating guide

The model zoo is an offline asset-preservation and provenance facility. It is not part of the ATC application runtime and does not select, benchmark, discover, load, or run models. FP-001B provides a separate, operator-invoked acquisition command for a model that a human has already selected.

## State boundaries

The following states are deliberately separate:

- **Available:** an asset has been acquired and catalogued.
- **Verified:** the current local file matches the manifest SHA-256 and expected size.
- **Benchmarked:** a later responsible feature packet has evaluated it on reference hardware.
- **Approved for runtime:** a later decision has explicitly selected it for an application role.

`Available != Verified != Benchmarked != Approved for runtime`.

The manifest records catalogue facts and later lifecycle decisions. `VERIFIED` is always computed from current local bytes; it is not inferred from a stored lifecycle flag. FP-027, FP-028, and FP-030 retain ASR, LLM, and TTS benchmark and integration responsibility.

## Repository contents

```text
model-zoo/
  README.md
  manifest.json
  schemas/
    model-manifest.schema.json
```

The production manifest is intentionally empty in FP-001A. Real model entries require a separately governed acquisition; synthetic examples exist only under `tests/fixtures/model-zoo`.

Git contains metadata, expected checksums, provenance/licence references, schema, documentation, and verification tooling. It must never contain model weights or a local `model-zoo/assets`, `cache`, `downloads`, or `staging` tree.

## External storage convention

Choose a local directory outside the Git checkout as `<asset-root>`. Its location is a deployment choice and is passed explicitly to the CLI. The production manifest and application contain no machine-specific absolute model path.

Store files using this convention:

```text
<asset-root>/
  <category>/
    <publisher>/
      <model-name>/
        <immutable-revision>/
          <upstream snapshot files>
          PRESERVATION/
            <locally generated records>
```

Manifest asset paths use forward slashes and are relative to `<asset-root>`, for example `ASR/Publisher/example-id/commit-sha/config.json`. The identity `variant` is catalogue metadata and does not add a mandatory path component. The existing Whisper snapshot is grandfathered and is not migrated by FP-001B. `D:\Portable-ATC-Models` may be used as an example Windows asset root, but it is not a default or hard-coded location.

The asset root also contains disposable provider data outside immutable revisions:

```text
<asset-root>/.cache/    provider download cache
<asset-root>/.staging/  incomplete acquisitions
```

Neither directory, nor any revision's `PRESERVATION` directory, is part of the upstream asset inventory.

## Controlled acquisition

Install the optional, pinned provider dependency:

```powershell
python -m pip install -e ".[dev,acquisition]"
```

Create a JSON metadata file containing the human-reviewed FP-001A fields: `entry_id`, `identity` (`family`, `name`, and `variant`; the tool replaces `revision`), `category`, `intended_role`, `format`, `quantisation`, `publisher`, `licence`, `runtime_compatibility`, and optional `acquisition_notes`. Then run:

```powershell
python scripts\acquire_model.py `
  --provider huggingface `
  --repository openai/whisper-large-v3-turbo `
  --revision <explicit-branch-tag-or-full-sha> `
  --asset-root D:\ATC-Model-Zoo `
  --metadata .\candidate-metadata.json
```

The Hugging Face adapter resolves the requested revision to a full commit SHA and downloads using that SHA. Both values are recorded. The command reports expected and free bytes before transfer. It reserves the larger of 1 GiB or 5 percent of the expected snapshot as a safety margin, refuses clearly insufficient storage, and requires confirmation for an expected uncached download of at least 1 GiB or an unknown size. Use `--yes` only for deliberate unattended acquisition.

Network and timeout failures are retried at most three times with bounded exponential backoff. Provider cache is retained for reuse. An interruption or failure leaves diagnostic state only under `.staging`; it never creates the immutable final revision directory. Rerun the same command to retry. Existing final revisions are always a collision: there is no force, overwrite, repair, or deletion mode.

Acquisition preserves upstream-relative files at the immutable revision root and writes `acquisition.json`, `inventory.json`, `candidate-manifest.json`, and `verification.json` under `PRESERVATION`. The complete one-entry candidate manifest is validated and its staged bytes are verified through the FP-001A implementation before atomic promotion. Review it manually before separately adding an entry to `model-zoo/manifest.json`; acquisition never edits the production catalogue.

## Recording acquisition, provenance, and licence

Before cataloguing an acquired asset, record its exact family, name, upstream revision, variant, format, quantisation where applicable, category, intended role, source publisher/URI, acquisition date/method/notes, licence name or SPDX identifier, licence reference, usage notes, runtime-compatibility notes, byte size, and SHA-256.

An upstream branch name such as `main` is not an exact revision. Prefer an immutable upstream commit, release, or version identifier. Preserve the applicable licence text or reliable offline reference with the external backup when redistribution terms permit it. Metadata does not constitute legal approval; unresolved usage rights must remain visible in licence notes.

## Offline verification

From the repository root:

```powershell
python scripts\verify_model_zoo.py `
  --manifest model-zoo\manifest.json `
  --asset-root <asset-root>
```

Add `--json` for stable machine-readable JSON. The command performs no network operation and never downloads or repairs an asset. It returns exit code `0` only when every listed file is `VERIFIED`, `1` for an integrity/path failure, and `2` for an invalid manifest or unreadable input.

Per-file states include:

- `VERIFIED`: SHA-256 and expected size match.
- `MISSING`: no regular file exists at the safe resolved path.
- `HASH_MISMATCH`: current bytes do not match the expected SHA-256.
- `SIZE_MISMATCH`: SHA-256 matches but recorded size does not.
- `UNSAFE_PATH`: the path or asset root cannot be safely resolved.

## Safe paths

Asset paths must be relative, use forward slashes, contain no drive/UNC prefix, backslash, NUL, `.` or `..` segment, and resolve beneath `<asset-root>`. Symlink or junction resolution may not escape that root. Verification reads regular files only and never writes, moves, or deletes assets.

## Backup and restoration

To back up the zoo:

1. Stop any separate process that could modify assets.
2. Verify the external root against the versioned manifest.
3. Copy the complete external asset tree to offline backup media without flattening paths.
4. Copy the exact manifest, schema, relevant licence/provenance material, and verification output alongside it.
5. Hash or otherwise integrity-protect the backup media inventory.

To restore:

1. Restore into a new external `<asset-root>` outside the Git checkout.
2. Restore the manifest/schema version captured with the backup or check out that repository revision.
3. Run the offline verifier against the restored root.
4. Treat any missing, mismatched, unsafe, or invalid result as unverified; never silently substitute another revision.
5. Do not interpret successful restoration as benchmarking or runtime approval.

The source distribution service is not required for verification, backup, restoration, or later offline use of lawfully preserved assets.
