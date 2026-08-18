# Portable ATC Radar Trainer

An experimental, local-first Air Traffic Control training platform. Phase 1 is an engineering and training-workflow prototype for one trainee on one Windows laptop. It is not a certified simulator and must not be used for operational traffic control.

This repository contains the FP-001 runnable application foundation and the FP-001A local model-zoo foundation. The model zoo catalogs and verifies externally stored candidate assets; it does not run or select models. Training, simulation, speech inference, persistence, and replay capabilities belong to later feature packets and are not implemented here.

## Phase 1 architecture

The authoritative Phase 1 architecture is browser-based and backend-authoritative. Normal operation is local and offline. React/TypeScript/Vite provide the browser application; Python/FastAPI/Pydantic/Uvicorn provide the backend.

Unity and BlueSky are explicitly deferred and are not Phase 1 dependencies. Phase 1 also requires no cloud service, container runtime, or distributed deployment.

The governing documents are:

- [Phase 1 Architecture Baseline v1.0](docs/architecture/baseline/ATC_Portable_Trainer_Phase1_Architecture_Baseline_v1.0.md)
- [Phase 1 Feature Packets](docs/feature-packets/ATC_Portable_Trainer_Phase1_Feature_Packets.md)

## Prerequisites

- Windows 11
- Python 3.12
- Node.js 22 or 24 LTS with pnpm 11
- PowerShell 7 or Windows PowerShell 5.1

Internet access is needed only to install dependencies. After installation, the FP-001 application starts and operates without network services.

## Repository boundaries

```text
apps/
  api/                  FastAPI entry point and transport models
  web/                  React browser presentation
packages/
  domain/               Provider-independent domain rules and ports
  application/          Use-case orchestration
  infrastructure/       Concrete local adapters
tests/                  Backend and architecture tests/fixtures
scripts/                Development and architecture-check commands
docs/                   Authoritative architecture and feature packets
model-zoo/              Model metadata, schema, and offline operating guide
```

Dependencies point inward. In particular:

- `packages/domain` must not import `apps`, `packages/application`, or `packages/infrastructure`.
- Infrastructure implements ports owned by inner layers.
- API/browser transport models must not become domain models by convenience.
- The browser must not own authoritative simulation, clearance, scoring, or replay rules.

FP-001 creates package markers only; domain models, services, adapters, persistence, and events are intentionally deferred.

## Install

From the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

Set-Location apps\web
pnpm install --frozen-lockfile
Set-Location ..\..
```

Dependencies and tool versions are pinned in `pyproject.toml`, `apps/web/package.json`, and `apps/web/pnpm-lock.yaml`.

## Run

Start both applications from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

The execution-policy override applies only to this PowerShell process. It does not change the execution policy for the current user or machine.

The API binds to `127.0.0.1:8000` and the browser application to `127.0.0.1:5173`. Open <http://127.0.0.1:5173> if the browser does not open automatically.

Alternatively, use two PowerShell terminals:

```powershell
# Terminal 1, repository root
.\.venv\Scripts\Activate.ps1
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2
Set-Location apps\web
pnpm run dev
```

The frontend reads `VITE_API_URL` when supplied and otherwise uses `http://127.0.0.1:8000`.

## Verify

Run backend tests, lint, types, and the production boundary check from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest
python -m ruff check apps packages scripts tests
python -m mypy
python scripts\check_architecture.py
python scripts\check_model_assets.py
python scripts\verify_model_zoo.py --manifest model-zoo\manifest.json --asset-root <asset-root>
```

Run frontend tests, lint, types, and production build:

```powershell
Set-Location apps\web
pnpm test
pnpm run lint
pnpm run typecheck
pnpm run build
```

With the API running, verify health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Compress
```

Expected response:

```json
{"status":"ok"}
```

The architecture test suite proves both sides of the rule: valid domain imports pass, while `tests/fixtures/invalid_domain_dependency.py` is deliberately rejected. To observe the expected rejection directly:

```powershell
python scripts\check_architecture.py tests\fixtures\invalid_domain_dependency.py
if ($LASTEXITCODE -ne 1) { throw "Invalid dependency fixture was not rejected" }
```

## FP-001 scope boundary

This foundation does not implement session lifecycle, SQLite/persistence, events, scenarios, aircraft or runway logic, simulation, WebSockets, ASR, LLM integration, TTS, radio, competency/scoring, replay, instructor functions, Unity, BlueSky, cloud services, or distributed deployment.

## FP-001A local model zoo

The model-zoo mechanism stores catalog metadata in Git while keeping model files in an external local `<asset-root>`. See [the model-zoo operating guide](model-zoo/README.md) for the manifest contract, offline verification, storage, backup, and restoration procedures. The production manifest is intentionally empty until separately governed acquisition and later benchmark work add candidate records.

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
