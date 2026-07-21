<p align="center">
  <img src="frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

> Working copy: This repository copy (`academic-roundtable-github-ready`) is the authoritative folder for all contributions and verification.

# Contributing to Academic Roundtable

Thank you for helping improve **deep conversations for better learning**. Keep changes lean, observable, and centered on the learning experience.

## Development setup

1. Copy `.env.example` to `.env.local` and add local credentials. Never commit this file.
2. Run `scripts\setup.ps1` on Windows.
3. Start the application with `run.ps1` and open `http://127.0.0.1:8765/`.

See [Development Guide](docs/DEVELOPMENT.md) for manual setup and architecture boundaries.

## Change process

1. State the user or learning problem and the smallest proposed change.
2. Add or update deterministic tests for lifecycle and data behavior.
3. For conversational changes, use the learning-quality fixtures and record Sam's transcript-based judgment.
4. Run backend tests and the frontend production build.
5. Update documentation when behavior, limitations, configuration, or data retention changes.
6. Keep unrelated changes out of the pull request.

## Required verification

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest backend\tests -q

Set-Location frontend
pnpm install --frozen-lockfile
pnpm build
```

Live-provider smoke tests are optional and consume API capacity:

```powershell
.\.venv\Scripts\python.exe .\scripts\smoke_generation.py
```

## Pull requests

Describe the outcome, risk, verification evidence, and deferred work. Do not include API keys, local databases, uploaded documents, transcripts, build outputs, or dependency directories. UI changes should include a screenshot when practical.

## Scope guardrails

Authentication, shared hosting, cross-session evaluation history, durable workers, embeddings, OCR, and voice remain deferred until pilot evidence and an explicit data-retention design justify them.
