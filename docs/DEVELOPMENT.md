<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

> Canonical source: This is the active `academic-roundtable-github-ready` workspace.
> The sibling `academic-roundtable/` folder is archived and not for new development.

# Development and Testing Guide

## Development principle

Preserve the product's central outcome: **deep conversations for better learning**. Prefer small vertical changes with measurable behavior over broad infrastructure or feature expansion.

This `academic-roundtable-github-ready` folder is the canonical development baseline. All future code changes, tests, documentation updates, and repository preparation should be performed and verified here.

## Repository roles

- `backend/app`: FastAPI routes, SQLite persistence, orchestration, provider adapters, prompts, document processing, and learning evaluation
- `backend/tests`: deterministic unit and API lifecycle tests
- `frontend/src`: React conversation, closeout, and evaluation interface
- `evaluation/fixtures`: controlled learning-quality scenarios
- `scripts`: setup, provider checks, smoke generation, and offline evaluation
- `docs`: system, audit, planning, evaluation, and release guidance

## Local setup

Requirements: Python 3.11+, Node.js 20.19+ or 22.12+, and preferably pnpm.

```powershell
Copy-Item .env.example .env.local
.\.venv\Scripts\python.exe -m pip install pymupdf pdfplumber  # required for robust PDF table/figure extraction
.\scripts\setup.ps1
.\run.ps1
```

Real API keys remain in `.env.local`, which is ignored by Git. The application stores runtime state in `data/`, also ignored.

### PDF extraction validation

The app uses PyMuPDF (`pymupdf`) + `pdfplumber` for richer table and figure-oriented extraction. You can quickly verify runtime readiness from the shell:

```powershell
.\.venv\Scripts\python.exe -c "from backend.app.documents import extract_dependency_health; print(extract_dependency_health())"
```

If either package is missing, PDF uploads are blocked and the backend returns an actionable message instructing you to install both packages before retrying.

## Test layers

### Deterministic backend

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

For a fast regression check focused on closeout exports and the new one-page summary path, run:

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest backend\tests\test_export_regression.py -q
```

These tests must not call live LLM providers.

### Frontend type and production build

```powershell
Set-Location frontend
pnpm install --frozen-lockfile
pnpm build
```

### Conversational learning quality

Use the built-in closeout evaluation for individual sessions. For controlled prompt comparisons, follow [LEARNING-QUALITY-EVALUATION.md](LEARNING-QUALITY-EVALUATION.md) and use the optional offline comparison script.

### Live-provider smoke test

Run only when external connectivity, credentials, and API capacity are intentionally available:

```powershell
.\.venv\Scripts\python.exe .\scripts\check_providers.py
.\.venv\Scripts\python.exe .\scripts\smoke_generation.py
```

## Data lifecycle

The app retains one session. Starting a new table deletes the prior transcript, digest history, evaluation, FTS passages, and managed uploads. Download, summary review, and learning evaluation are optional and never gate the next table.

## Deferred architecture

Do not introduce cross-session history, multi-user identity, a durable queue, embeddings, OCR, or public deployment infrastructure without evidence and an updated retention/security design.
