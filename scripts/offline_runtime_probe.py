"""Small stdlib entry point for a restored CPython environment, under OS network isolation.

The Python audit hook is defense in depth, not a native-code network sandbox.
It is installed before importing pip, NumPy, Torch or Transformers.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import runpy
import sys
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REFERENCE_ENTRY = "openai-whisper-large-v3-turbo-41f01f3"
REFERENCE_REVISION = "41f01f3fe87f28c78e2fbf8b568835947dd65ed9"


def deny_network(event: str, args: tuple[object, ...]) -> None:
    # gethostname reads the local machine name; pip uses it without network I/O.
    if event.startswith("socket.") and event != "socket.gethostname":
        raise RuntimeError(f"offline probe denied network operation: {event}")


def enable_offline() -> None:
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_CONFIG_FILE": os.devnull,
        }
    )
    sys.addaudithook(deny_network)


def reference_snapshot(model_path: Path, manifest_path: Path) -> None:
    if not model_path.is_dir():
        raise ValueError("model must be an existing local snapshot directory")
    if model_path.name != REFERENCE_REVISION:
        raise ValueError("reference snapshot directory must identify the exact immutable revision")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = [entry for entry in manifest["models"] if entry["entry_id"] == REFERENCE_ENTRY]
    if len(entries) != 1 or entries[0]["identity"]["revision"] != REFERENCE_REVISION:
        raise ValueError("reference model entry/revision missing or mismatched")
    assets = entries[0].get("assets")
    if not assets:
        raise ValueError("reference snapshot requires inline catalogue inventory")
    prefix = f"ASR/OpenAI/whisper-large-v3-turbo/{REFERENCE_REVISION}/"
    for asset in assets:
        if not asset["path"].startswith(prefix):
            raise ValueError("reference asset path does not match immutable snapshot")
        relative = asset["path"][len(prefix) :]
        if "/" in relative or "\\" in relative or ":" in relative or relative in {"", ".", ".."}:
            raise ValueError("unsupported reference snapshot path")
        local = (model_path / relative).resolve(strict=True)
        if not local.is_relative_to(model_path.resolve()) or not local.is_file():
            raise ValueError("reference asset escapes snapshot")
        if local.stat().st_size != asset["size_bytes"]:
            raise ValueError("reference asset size mismatch")
        # Weight integrity relies on the separately reviewed historical integrity record.
        if asset["size_bytes"] <= 4 * 1024 * 1024:
            if hashlib.sha256(local.read_bytes()).hexdigest() != asset["sha256"]:
                raise ValueError("reference metadata digest mismatch")
    config = json.loads((model_path / "config.json").read_text(encoding="utf-8"))
    if config.get("model_type") != "whisper":
        raise ValueError("reference config must identify Whisper")


def infer(
    model_path: Path,
    audio_path: Path,
    max_new_tokens: int,
    manifest_path: Path,
) -> dict[str, Any]:
    reference_snapshot(model_path, manifest_path)
    required = (
        "config.json",
        "model.safetensors",
        "preprocessor_config.json",
        "tokenizer_config.json",
        "tokenizer.json",
        "generation_config.json",
    )
    if any(not (model_path / name).is_file() for name in required):
        raise ValueError("incomplete local Whisper snapshot")
    with wave.open(str(audio_path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 16000):
            raise ValueError("acceptance input must be mono PCM16 WAV at 16000 Hz")
        frames = stream.getnframes()
        if not 1 <= frames <= 160000:
            raise ValueError("acceptance input must be non-empty and at most 10 seconds")
        pcm = stream.readframes(frames)
        if len(pcm) != frames * 2:
            raise ValueError("truncated acceptance input")
    import numpy as np
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    torch.set_num_threads(1)
    torch.manual_seed(0)
    local = str(model_path.resolve(strict=True))
    processor = AutoProcessor.from_pretrained(local, local_files_only=True, trust_remote_code=False)
    model = (
        AutoModelForSpeechSeq2Seq.from_pretrained(
            local,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
            torch_dtype=torch.float32,
        )
        .to("cpu")
        .eval()
    )
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    inputs = processor(samples, sampling_rate=16000, return_tensors="pt")
    with torch.inference_mode():
        tokens = model.generate(
            inputs.input_features,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            language="en",
            task="transcribe",
        )
    if tokens.numel() == 0:
        raise ValueError("inference produced no token sequence")
    transcript = processor.batch_decode(tokens, skip_special_tokens=True)[0]
    return {
        "model": {"entry_id": REFERENCE_ENTRY, "revision": REFERENCE_REVISION},
        "weight_integrity": "size only; historical integrity evidence required separately",
        "model_loaded": True,
        "inference_completed": True,
        "input_sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        "transcript": transcript,
        "generated_token_count": int(tokens.numel()),
        "python": platform.python_version(),
        "packages": {
            item.metadata["Name"]: item.version for item in importlib.metadata.distributions()
        },
        "network_guard": "Python audit hook; OS isolation evidence required separately",
        "benchmarked": False,
        "approved_for_runtime": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    install = modes.add_parser("install")
    install.add_argument("--wheelhouse", type=Path, required=True)
    install.add_argument("--lock", type=Path, required=True)
    modes.add_parser("check")
    probe = modes.add_parser("infer")
    probe.add_argument("--model", type=Path, required=True)
    probe.add_argument("--audio", type=Path, required=True)
    probe.add_argument("--manifest", type=Path, required=True)
    probe.add_argument("--max-new-tokens", type=int, default=32, choices=range(1, 129))
    args = parser.parse_args(argv)
    enable_offline()
    try:
        if args.mode in {"install", "check"}:
            if args.mode == "install":
                wheelhouse = args.wheelhouse.resolve(strict=True)
                if not wheelhouse.is_dir():
                    raise ValueError("wheelhouse must be a local directory")
                # Lock grammar forbids URLs, includes, extra indexes, editable and source builds.
                import re

                lines = args.lock.read_text(encoding="utf-8").splitlines()
                pattern = r"[A-Za-z0-9_.-]+==[0-9][A-Za-z0-9.+_-]* --hash=sha256:[0-9a-f]{64}"
                if not lines or any(not re.fullmatch(pattern, line) for line in lines):
                    raise ValueError("lock must contain only exact package pins with SHA-256")
                sys.argv = [
                    "pip",
                    "--isolated",
                    "install",
                    "--no-index",
                    "--no-cache-dir",
                    "--disable-pip-version-check",
                    "--only-binary=:all:",
                    "--require-hashes",
                    "--find-links",
                    str(wheelhouse),
                    "-r",
                    str(args.lock.resolve(strict=True)),
                ]
            else:
                sys.argv = ["pip", "--isolated", "check"]
            runpy.run_module("pip", run_name="__main__")
            return 0
        result = infer(args.model, args.audio, args.max_new_tokens, args.manifest)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, ImportError, KeyError, TypeError) as error:
        print(json.dumps({"status": "FAILED", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
