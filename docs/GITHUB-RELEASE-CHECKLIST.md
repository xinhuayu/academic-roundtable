<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

> Canonical source: This is the active `academic-roundtable-github-ready` workspace.
> The sibling `academic-roundtable/` folder is archived and not for new development.

# GitHub Release Checklist

## Required before the first push

- [ ] Decide whether the repository is private or public.
- [ ] Choose and add an explicit license if distribution or contribution is intended.
- [ ] Initialize Git in the GitHub-ready copy, not in a folder containing unrelated work.
- [ ] Confirm `.env.local` is ignored and absent from `git status` and `git ls-files`.
- [ ] Scan the full candidate commit and history for secrets.
- [ ] Confirm `data/`, uploads, exports, logs, dependencies, caches, and build artifacts are untracked.
- [ ] Run **51 backend tests**, the frontend test suite, and the frontend production build from the clean copy.
- [ ] Review README limitations and security warnings.
- [ ] Configure private vulnerability reporting before inviting outside users.

## Suggested repository settings

- Protect the default branch and require the CI workflow.
- Require pull requests for changes to the default branch.
- Enable secret scanning and push protection when available.
- Disable unnecessary workflow write permissions.
- Keep Actions permissions read-only by default.

## Latest prepared-archive verification (2026-07-21)

- [x] 51 backend tests passed.
- [x] Frontend Vitest suite passed (3 tests, including ephemeral digest-status messages and landing-page multi-source staging).
- [x] Frontend production build passed.
- [x] Candidate source files passed checks for common OpenAI, Google, and Anthropic key formats, private-key blocks, and developer-specific absolute paths.
- [x] Archive entry inspection found no `.env.local`, runtime database, uploaded source, transcript, log, cache, dependency directory, or compiled build output.
- [x] `.env.example`, README, logo, backend source, frontend source, tests, skills, and documentation are present.
- [x] Current frontend source includes the Sam-floor composer highlight, stage-specific blue closeout progress messages, and save/download-before-evaluation ordering.
- [x] Current frontend source includes the highlighted header floor indicator and non-persistent topic/conversation digestion cards.
- [x] Current source includes the Fast/Research/Verification session profile selector and profile-aware model, reasoning, token, and timeout routing.
- [x] Rebuilt GitHub submission archive has 56 entries and contains no forbidden local/runtime files. Record the final SHA-256 from the packaging run before publication.
- [x] Current frontend source includes explicit AI LLM mode buttons on the landing page and conversation header.

- [x] The reusable live profile-switch simulation is included without a developer-specific PDF path; its 2026-07-21 run confirmed Fast, Research, and Verification routing with no provider errors or truncation.
- [x] Closeout replaces the visible JSON download with a comprehensive Summary Digest; landing-page sources are staged before Start and queued immediately afterward; conversation-page uploads remain available.
- [x] Momo's runtime critique skill checks Bobby's and Sam's assumptions, evidentiary support, scope, causal interpretation, and qualifications without defaulting to reflexive disagreement.
- [x] Lifecycle regression coverage protects strict reset, post-close immutability, summary cancellation across both closeout jobs, latest-summary export selection, and recap-job deduplication.

This verifies the prepared local archive only. A GitHub history scan remains required after repository initialization and before publication.

## Local credential retained in the prepared copy

The prepared development copy may contain a local `.env.local` so it can be tested immediately. That file is intentionally excluded by `.gitignore` and the CI safety job rejects tracked local environment files. Before any push, verify its ignored status again; ignore rules do not remove a secret that was previously committed.
