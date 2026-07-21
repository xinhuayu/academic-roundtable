<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

> Canonical source: This is the active `academic-roundtable-github-ready` workspace.
> The sibling `academic-roundtable/` folder is archived and not for new development.

# Academic Roundtable: Independent Implementation Audit

Audit date: 2026-07-21  
Scope: design, architecture, interface, functions/features, logic flow, security posture, maintainability, tests, and GitHub readiness

## Executive assessment

Academic Roundtable is a coherent lean local MVP. The implemented interaction matches its central principle—**deep conversations for better learning**—more closely than a conventional multi-bot chat: Sam controls direction, AI segments are bounded and interruptible, live contributions are intentionally concise, and durable digests support continuity without sending the full history on every turn.

The architecture is appropriately small for a pilot. React, FastAPI, SQLite/FTS5, local files, SSE, and in-process background tasks form a reasonable single-user vertical slice. The system should not yet be presented as production-ready or multi-user secure.

Audit disposition: **ready for local learning pilots after the recorded fixes; not yet ready for public hosting.**

## Method

The audit inspected the repository structure, API routes, persistence model, orchestration and prompt assembly, provider adapters, document pipeline, frontend session lifecycle, exports, ignore rules, tests, and existing documentation. Deterministic backend tests and a frontend production build are the verification gates; live provider generation is separate because it depends on external services and consumes API capacity.

### Live connection audit (2026-07-21)

I executed `scripts/live_audit_session.py` against the already-running application, with real OpenAI and Google provider calls, using the PDF file:
`Cognitive Trajectories and Subsequent Health Status.pdf`.

The reusable command requires an explicit local path—`python scripts/live_audit_session.py --pdf <approved-pdf-path>`—so the repository contains no developer-specific filesystem location. Because it transmits extracted document content to configured providers, run it only with the document owner's approval.

Observed flow and timing:

- Provider health:
  - Momo: `gpt-5.6-luna` through OpenAI Responses, reachable.
  - Bobby: `gemini-3.1-flash-lite` through Google OpenAI-compatible Chat Completions, reachable.
- `GET /api/meta`: 200, 0.009 s, 280 B.
- `GET /api/documents/dependencies`: 200, 0.022 s.
  - `pymupdf: True`, `pdfplumber: True`, `pypdf: True`
  - versions: `pymupdf 1.28.0`, `pdfplumber 0.11.10`, `pypdf 6.14.2`.
- `POST /api/sessions`: 201, 0.129 s; duplicate create returned the expected 409, and `force_reset` then returned 201.
- PDF upload: 202 in 0.095 s; document digestion completed in 74.3 s.
- source-refined Topic Digest: completed in 6.9 s after document digestion.
- first two-round AI segment: 16.86 s total, first SSE event at 0.069 s, 338 text deltas and 3,733 visible characters; no provider errors.
- targeted Bobby two-round segment: 9.01 s total, first SSE event at 0.102 s, 150 text deltas and 1,619 visible characters; no provider errors.
- six substantive AI messages were 788-1,015 characters each, approximately 105-140 words. No message was truncated or left in an interrupted state.
- requested recap: completed successfully but took 133.5 s. Because recap generation is a background job, conversation controls remain available; this is the principal performance watch item.
- final summary: 14.5 s; one-page summary: 4.3 s; both completed without fallback.
- Markdown export: 49,883 B; one-page summary export: 2,678 B.
- retained structured payload sizes: document digest 20,251 characters, Topic Digest about 5,137 JSON characters, requested recap about 8,167 JSON characters, final digest about 7,413 JSON characters, and one-page digest about 2,729 JSON characters.

Source grounding and extraction evidence:
- `extract_passages` from the supplied PDF (server-side ingestion path) produced 27 passages, 48,474 total chars, and 3,598-char maximum chunk size, with no table extraction failure.
- the document digest and refined Topic Digest completed before Sam's first substantive message; source boundaries were present in the final session state, confirming processed digest grounding was carried into the conversation from the beginning without repeatedly transmitting raw PDF extracts.

The audit also confirmed dependency metadata and diagnostics were hardened:
- `/api/documents/dependencies` now resolves `pymupdf_version` correctly as `1.28.0`.
- provider errors are now captured with underlying transport details (for example `ConnectError: All connection attempts failed`), improving root-cause analysis for connection failures.
- the live-audit runner now reuses an already-running server, records total background-job elapsed time, counts SSE bytes, and reports stored output sizes.

Performance disposition: live discussion latency and output sizes are appropriate for the current concise-turn design. Source digestion is acceptably asynchronous for a 27-passage academic PDF. Requested recap latency is within the configured 900-second background-job ceiling but should be monitored in further trials; it is not currently evidence of timeout, truncation, or retry failure.

## Design audit

### Strengths

- The product goal is specific and repeated consistently: meaningful intellectual exchange that improves learning.
- Human authority is encoded in both controls and lifecycle, not merely described in prompts.
- Concision is a design constraint, which protects readability and latency.
- Momo and Bobby receive complementary but non-hierarchical roles.
- Digests and raw recent turns balance long-session focus with fidelity.
- Source evidence and internal model knowledge can coexist under an explicit provenance policy.

### Watch items

- Prompt compliance alone cannot guarantee concise, adversarial, non-repetitive discussion; the pilot needs a human-scored evaluation set.
- “Deep” and “better learning” need observable criteria. The proposed rubric in the implementation plan should be the next product increment.
- The sources-only policy is prompt-enforced, not a formal verifier of every generated claim.

## Architecture audit

### Strengths

- Provider adapters isolate server API differences.
- Session locking prevents overlapping segments and now serializes finalization with active streaming.
- SQLite is adequate for one local user and enables transactional state plus FTS5 retrieval.
- Background digests protect the interactive path from large synthesis calls.
- Public document objects are separated from internal storage metadata.

### Constraints

- Background tasks are in-process. Job records persist, but queued/running work is not resumed after restart.
- There is no durable queue, concurrency governor, retry policy, or circuit breaker.
- SQLite plus single-session deletion is intentional but unsuitable for concurrent users.
- Lexical FTS retrieval has no semantic fallback or measured retrieval quality.

These are acceptable MVP boundaries when stated honestly.

## Interface audit

### Strengths

- The transcript is visually dominant and uses internal scrolling, preventing token streaming from moving Sam's controls off-screen.
- Sam's composer remains separate and reachable for interruption.
- Participant-name highlighting improves conversational scanning.
- Background knowledge is visually separated from the core response.
- Digests sit below the main conversation instead of competing in side frames.
- The closeout view creates a clear download opportunity before single-session deletion.

### Follow-up validation

- Test keyboard navigation, focus behavior, contrast, and screen-reader labels.
- Test narrow laptop and mobile widths with long formulas, URLs, and unbroken strings.
- Add current screenshots to the repository before a public release.
- Make provider/job failures easy to recover from without requiring a page refresh.

## Functions and feature audit

The following core functions are present and connected end-to-end:

- Session creation, greeting-only opening, and Sam-led start
- Automatic response to Sam followed by bounded AI-to-AI rounds
- Direct-name and `@mention` routing, both-AI independent answers, and random default selection
- Immediate interrupt, partial-text retention, and continued discussion
- AI invitations to Sam plus host-deferred continuation
- Automatic and requested summaries
- Topic and source digestion with enlarged budgets
- Digest-only grounding during ordinary rounds, with raw passage retrieval reserved for Sam's explicit original-source verification requests
- Recent-round and digest context assembly
- Upload, extraction, indexing, retrieval, provider health, and job status
- Immediate End, cancellable final summary, Markdown/JSON/ZIP export, and confirmed new-session purge

The earlier documentation overstated several capabilities. Automatic job resumption, safe retries, circuit breakers, production metrics, formal claim graphs, and embedding retrieval are **not implemented** and are now recorded as deferred work.

## Logic-flow audit and fixes

### High-priority findings resolved

1. **Closing state could be overwritten by streaming cleanup.** A close request can interrupt an active segment. The segment's unconditional cleanup previously restored `HUMAN_FLOOR`, racing with `CLOSING` or `CLOSED`. Cleanup now preserves terminal lifecycle states, and final synthesis waits for the session lock so partial text is saved first.
2. **New-session retention was enforced mainly by the interface.** A direct API call could replace an active session. The API now returns `409 Conflict` when any prior session remains non-closed unless `force_reset=true` is used on creation.
3. **Internal upload paths were exposed.** Session, upload, document, and JSON views could reveal managed filesystem paths. Public document serialization now removes `stored_path`; archive creation uses internal records only inside the server.
4. **First-token timeout was configured but not enforced by orchestration.** The service now applies the provider's first-token deadline before continuing the stream and returns control to Sam on failure.
5. **Source digest type handling could crash segment context assembly.** The source-context assembler assumed `documents.digest` was always a string and called `.strip()` directly, but parsed JSON payloads are stored as objects. It now normalizes non-string digests with `json.dumps(...)`, preventing 500 errors during live streams when documents are pre-digested.

### Medium-priority findings resolved

- Frontend dependency declarations used floating `latest` versions despite a lockfile. Exact versions are now declared.
- Generated TypeScript/Vite files and local work artifacts are now ignored.
- The frontend new-session guard now requires either all sessions to be closed or an explicit reset acknowledgement, preventing a finalization-in-progress bypass.

### Remaining logic risks

- Natural-language recap and closing detection uses English regular expressions and may miss paraphrases or other languages.
- Provider cancellation stops visible consumption but cannot guarantee remote computation is cancelled for every compatible server.
- Empty or malformed model output falls back in some digest paths but recovery behavior is not uniform across all provider failures.
- Document digestion can be retried only by a future feature; completed section checkpoints are not resumable.

## Security and privacy audit

Appropriate local safeguards are present: secrets are environment-only, sensitive paths and runtime data are ignored, upload paths are managed, deletion/archive paths are root-validated, and source text is framed as evidence rather than instructions.

Before internet exposure, add authentication, authorization, CSRF/deployment-origin review, rate and upload limits at the edge, malware scanning, stricter MIME/content validation, HTTPS, secret management, database/file isolation, security headers, audit logging, retention policy, and backup/recovery procedures.

Before pushing to GitHub, scan the working tree and repository history for secrets. The audit did not print or validate any plaintext API key.

## Verification evidence

- Backend: **46 tests passed** with `PYTHONPATH=backend .venv\Scripts\python.exe -m pytest backend\tests`. Coverage includes digest-only ordinary source context, explicit original-source verification routing, and source-sized verification budgets in addition to the earlier reliability cases.
- Covered regression cases include first-token timeout recovery, immediate stalled-stream cancellation with partial-text retention, startup reconciliation, session-task cancellation, bounded context assembly, and preservation of `CLOSING` during interrupted stream cleanup.
- Frontend: `npm test` and production build remain required verification gates whenever dependencies or UI code change.
- Independent API lifecycle smoke script (mocked providers) confirms session creation, Sam message routing, segment streaming, document digest jobs, recap triggering, closeout, learning-evaluation availability, and export paths in a clean temporary DB.
- Live-provider smoke test remains intentionally separate because it depends on external model availability and API keys.

## GitHub readiness checklist

- [x] GitHub-oriented README with setup, architecture, API, data, limitations, and contribution guidance
- [x] System summary and implementation plan aligned with current code
- [x] Dedicated audit record
- [x] Secret and runtime artifacts excluded by `.gitignore`
- [x] Exact frontend dependency declarations and committed lockfile
- [ ] Choose and add an open-source or private-use license
- [x] Add CI for backend tests, frontend build, and local-environment tracking protection
- [ ] Run a secret scan over the complete Git history
- [ ] Test setup from a clean clone
- [ ] Add screenshots and accessibility results
- [x] Add `SECURITY.md` before accepting public vulnerability reports

## Recommendation

Do not expand the feature surface yet. Run the learning-quality pilot first, tune turn length and opposition behavior from Sam's judgments, then implement only the reliability or retrieval improvements supported by observed failures. That preserves the project's lean architecture and keeps the conversation—not infrastructure—the primary product.

The subsequent prioritized AI-agent assessment and implemented reliability changes are documented in [CRITICAL-REVIEW.md](CRITICAL-REVIEW.md).
