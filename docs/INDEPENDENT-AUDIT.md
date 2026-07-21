<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

# Academic Roundtable: Independent Implementation Audit

Audit date: 2026-07-20  
Scope: design, architecture, interface, functions/features, logic flow, security posture, maintainability, tests, and GitHub readiness

## Executive assessment

Academic Roundtable is a coherent lean local MVP. The implemented interaction matches its central principle—**deep conversations for better learning**—more closely than a conventional multi-bot chat: Sam controls direction, AI segments are bounded and interruptible, live contributions are intentionally concise, and durable digests support continuity without sending the full history on every turn.

The architecture is appropriately small for a pilot. React, FastAPI, SQLite/FTS5, local files, SSE, and in-process background tasks form a reasonable single-user vertical slice. The system should not yet be presented as production-ready or multi-user secure.

Audit disposition: **ready for local learning pilots after the recorded fixes; not yet ready for public hosting.**

## Method

The audit inspected the repository structure, API routes, persistence model, orchestration and prompt assembly, provider adapters, document pipeline, frontend session lifecycle, exports, ignore rules, tests, and existing documentation. Deterministic backend tests and a frontend production build are the verification gates; live provider generation is separate because it depends on external services and consumes API capacity.

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
- Recent-round and digest context assembly
- Upload, extraction, indexing, retrieval, provider health, and job status
- Immediate End, cancellable final summary, Markdown/JSON/ZIP export, and confirmed new-session purge

The earlier documentation overstated several capabilities. Automatic job resumption, safe retries, circuit breakers, production metrics, formal claim graphs, and embedding retrieval are **not implemented** and are now recorded as deferred work.

## Logic-flow audit and fixes

### High-priority findings resolved

1. **Closing state could be overwritten by streaming cleanup.** A close request can interrupt an active segment. The segment's unconditional cleanup previously restored `HUMAN_FLOOR`, racing with `CLOSING` or `CLOSED`. Cleanup now preserves terminal lifecycle states, and final synthesis waits for the session lock so partial text is saved first.
2. **New-session retention was enforced mainly by the interface.** A direct API call could replace an active session. The API now returns `409 Conflict` unless the latest session is `CLOSED`.
3. **Internal upload paths were exposed.** Session, upload, document, and JSON views could reveal managed filesystem paths. Public document serialization now removes `stored_path`; archive creation uses internal records only inside the server.
4. **First-token timeout was configured but not enforced by orchestration.** The service now applies the provider's first-token deadline before continuing the stream and returns control to Sam on failure.

### Medium-priority findings resolved

- Frontend dependency declarations used floating `latest` versions despite a lockfile. Exact versions are now declared.
- Generated TypeScript/Vite files and local work artifacts are now ignored.
- The frontend new-session guard now requires `CLOSED`, preventing a finalization-in-progress bypass.

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

- Backend: **24 tests passed** after audit fixes, the agent-reliability increment, and the session-scoped learning-quality workflow.
- Covered regression cases include first-token timeout recovery, immediate stalled-stream cancellation with partial-text retention, startup reconciliation, session-task cancellation, bounded context assembly, and preservation of `CLOSING` during interrupted stream cleanup.
- Frontend: production type-check/build remains a required final verification gate whenever dependencies or UI code change.
- Live-provider smoke test: intentionally not part of deterministic audit verification.

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
