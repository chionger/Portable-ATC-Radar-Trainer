# Model Zoo Benchmarking and Evaluation

## Purpose

This directory contains the benchmarking and evaluation evidence framework for preserved Model Zoo candidates.

Benchmarking is separate from model acquisition, asset verification, application runtime integration, and runtime approval.

## Lifecycle

Available -> Verified -> Benchmarked -> Approved for runtime

These states are not interchangeable. A successful benchmark does not automatically approve a model for runtime use.

## Benchmark Definitions

The definitions directory describes what shall be evaluated.

A benchmark definition identifies the benchmark ID and version, category, purpose, evaluation set, metrics, and acceptance criteria.

The same benchmark definition may be applied to multiple candidate models.

## Benchmark Results

The results directory records what happened during a benchmark execution.

Each result identifies the benchmark, exact Model Zoo entry and immutable revision, execution time, hardware, runtime configuration, measurements, outcome, and applicable evidence.

Results for different model revisions are distinct evidence.

## Evidence

Large raw benchmark artifacts shall not be embedded automatically into the Model Zoo manifest.

Benchmark results may reference separately managed logs, raw results, summaries, and other evidence artifacts.

Evidence integrity may be protected with SHA-256 where appropriate.

## Comparison

Models shall be compared only when their benchmark definitions, evaluation sets, metrics, and relevant execution conditions make the comparison meaningful.

ASR, LLM, TTS, vision, embedding, reranking, safety, and multimodal models shall not be reduced to one universal benchmark score.

## Runtime Approval

Benchmarking produces evidence. Runtime approval is a separate explicit decision.

No benchmark result shall automatically set approved_for_runtime to true.

## Verification

From the repository root, replace the example paths and validate benchmark evidence with:

```powershell
python -m scripts.verify_benchmark_evidence --definition "benchmark-definition.json" --result "benchmark-result.json" --manifest model-zoo\manifest.json
```

The verifier validates benchmark structure, exact benchmark and model references, category compatibility, measurements, and acceptance-criteria outcome.

It does not download models, perform inference, modify the Model Zoo manifest, or approve a model for runtime use.
