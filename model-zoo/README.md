# Local model zoo operating guide

The FP-001A model zoo is an offline asset-preservation and provenance facility. It is not part of the ATC application runtime and does not select, benchmark, download, discover, load, or run models.

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
    <model-id>/
      <revision>/
        <variant>/
          <asset files>
```

Manifest asset paths use forward slashes and are relative to `<asset-root>`, for example `asr/example-id/revision/variant/asset.dat`. `D:\Portable-ATC-Models` may be used as an example Windows asset root, but it is not a default or hard-coded location.

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
