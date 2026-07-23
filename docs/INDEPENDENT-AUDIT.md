<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

> Canonical source: This is the active `academic-roundtable-github-ready` workspace.
> The sibling `academic-roundtable/` folder is archived and not for new development.

# Academic Roundtable: Independent Implementation Audit

Audit date: 2026-07-22  
Scope: design, architecture, interface, functions/features, logic flow, security posture, maintainability, tests, and GitHub readiness

## Executive assessment

Academic Roundtable is a coherent lean local MVP. The implemented interaction matches its central principle—**deep conversations for better learning**—more closely than a conventional multi-bot chat: Sam controls direction, AI segments are bounded and interruptible, live contributions are intentionally concise, and durable digests support continuity without sending the full history on every turn.

The architecture is appropriately small for a pilot. React, FastAPI, SQLite/FTS5, local files, SSE, and in-process background tasks form a reasonable single-user vertical slice. The system should not yet be presented as production-ready or multi-user secure.

Audit disposition: **ready for local learning pilots after the recorded fixes; not yet ready for public hosting.**

## Method

The audit inspected the repository structure, API routes, persistence model, orchestration and prompt assembly, provider adapters, document pipeline, frontend session lifecycle, exports, ignore rules, tests, and existing documentation. Deterministic backend tests and a frontend production build are the repeatable verification gates. The dated live runs below additionally used the configured OpenAI and Google connections and therefore consumed provider capacity.

### Full-system live audit and source-grounded simulation (2026-07-22)

The current build was exercised against the running local server with the configured OpenAI and Google providers and the approved 792,401-byte `Cognitive Trajectories and Subsequent Health Status.pdf`. No key value was printed, logged into the repository, or copied into an artifact.

Provider and extraction status:

- Momo Fast: `gpt-5.6-luna`, OpenAI Responses, reachable.
- Bobby Fast: `gemini-3.5-flash-lite`, Google OpenAI-compatible Chat Completions, reachable.
- PDF stack: PyMuPDF 1.28.0, pdfplumber 0.11.10, and pypdf 6.14.2.
- Upload acknowledgement: 0.231 s.
- Document Digest: 81.704 s and 23,858 characters.
- source-refined Topic Digest: 9.283 s and approximately 5,879 JSON characters.
- The corrected language detector retained **English** for the English paper.

Live conversation measurements:

| Profile | Actual Momo route | Actual Bobby route | First visible text | Two-round segment | Visible turn size | Provider errors |
|---|---|---|---:|---:|---:|---:|
| Fast | `gpt-5.6-luna`, low | `gemini-3.5-flash-lite`, minimal | 2.240 s | 12.062 s | 100-118 words | 0 |
| Research | `gpt-5.6-sol`, medium | `gemini-3.6-flash`, medium | 12.717 s | 62.666 s | 185-231 words | 0 |
| Verification, final route | `gpt-5.6-sol`, high | `gemini-pro-latest`, high | 14.787 s | 51.213 s | 108-122 words | 0 |

Fast remained responsive and concise. Research incurred a five-fold segment-latency increase but added substantive discussion of posterior classification, informative attrition, time-varying confounding, terminal decline, and joint longitudinal-survival alternatives. Two Momo Research turns slightly exceeded the approximate 220-word target (228 and 231 words); this is a prompt-tuning watch item, not a token-limit or truncation defect. Verification retrieved bounded original-source passages only after Sam explicitly requested a PDF check and correctly recorded page-level evidence in the visible turns.

Closeout and export measurements (historical explicit-Verification run):

- Momo's comprehensive Summary Digest and Bobby's one-page summary started within 0.1 seconds of each other and ran concurrently in Verification/high mode.
- Bobby's one-page summary completed in about 26.1 s; Momo's comprehensive digest completed in about 124.8 s; total closeout elapsed time was 125.5 s rather than their sum.
- Both jobs completed normally with no fallback. The one-page output was 5,339 bytes and the comprehensive Summary Digest export was 25,307 bytes.
- Readable transcript export: 83,428 bytes. Complete archive: 544,369 bytes. Every export returned HTTP 200.
- The complete archive retained the source-supporting digest records; the standalone comprehensive Summary Digest remained synthesis-only as designed.

Interface and lifecycle validation at 1280x720:

- The clean landing view had no page scroll, and **Start roundtable** was fully visible at 621-653 px within the 720 px viewport.
- After the requested synthesis completed, closeout displayed all four export controls, then the optional learning evaluation, then the centered new-roundtable action.
- Selecting the new-roundtable action without a UI-recorded download displayed the warning above the action, with separate stay and purge choices.
- The audit-created session was purged through the confirmed UI path; the app was left on a clean landing page.
- No browser-console warning/error and no Unicode replacement character were found.

High-priority defects found and resolved:

1. **False Portuguese detection for an English PDF.** Common one-letter tokens accumulated Portuguese stop-word points. Latin-language switching now requires repeated distinctive vocabulary evidence, with an English academic regression fixture.
2. **Silent Bobby stream termination.** Streaming HTTP errors were inspected before the response body had been consumed, causing a runtime exception that bypassed the structured error path. Error bodies are now read inside the stream context, unexpected adapter/service exceptions are contained, and the UI always receives a sanitized `provider_error` instead of a hanging participant card.
3. **Google error-envelope mismatch.** Some Google errors are returned as a one-element JSON list. Safe error parsing now normalizes both list- and object-wrapped envelopes.
4. **Unavailable default Verification model.** Google advertised `gemini-2.5-pro` in `/models` but returned 404 for generation because it is unavailable to new users. The default is now the live-validated `gemini-pro-latest`; environment overrides remain supported.

Performance disposition: ordinary Fast discussion is responsive; source digestion, Research, Verification, and closeout are intentionally slower asynchronous/deep paths and all completed inside their configured limits. Visible dialogue remained bounded, no completed reply was truncated, and the large Gemini completion ceilings continued to function as hidden-thinking reserves rather than prose targets.

Environment note: `pip check` on the long-lived local virtual environment reports an orphaned `cryptography` installation whose optional `cffi` dependency is absent. `cryptography` is not a declared application dependency, and live TLS calls to both providers succeeded, so this is not an application failure. Recreating the virtual environment from `requirements.txt` during the pending clean-clone test is preferable to adding an unused package solely to silence local environment drift.

### Live connection audit (2026-07-21)

This section is a dated measurement record, not the current model configuration. The current Bobby defaults are Gemini 3.5 Flash-Lite for Fast, Gemini 3.6 Flash for Research, and `gemini-pro-latest` for Verification; see the 2026-07-22 audit above for the current benchmark.

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
- final summary: 14.5 s; one-page summary: 4.3 s; both completed without fallback. These are historical measurements from the former sequential Momo-only closeout path; the current Momo/Bobby parallel path requires a fresh live-provider benchmark.
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

### Live reasoning-profile switch simulation (2026-07-21)

The table below preserves the exact routes used during that historical run. It should not be read as the current default profile catalog.

I then used `scripts/simulate_reasoning_profiles.py` against the same running server and the same cognitive-trajectories PDF. The reusable script creates or reuses a source-digested session, changes `conversation_profile` through the public session API, sends a source-grounded methodological prompt, streams a fixed two-round segment, and records the actual model, reasoning effort, source-verification flag, first-delta latency, total elapsed time, output size, and provider errors. It intentionally leaves the session open for inspection.

The source pipeline completed before the comparison: the 792,401-byte PDF produced a 20,102-character document digest in about 64.0 seconds and a 5,915-character Topic Digest in about 7.8 seconds. Ordinary Fast and Research turns used the processed source digest rather than raw PDF passages. Verification mode reopened original source passages and correctly cited page 4.

| Profile | Actual Momo route | Actual Bobby route | First visible text | Two-round segment | Per-message output | Errors |
|---|---|---|---:|---:|---:|---:|
| Fast | `gpt-5.6-luna`, low | `gemini-3.1-flash-lite`, low | 1.787 s | 16.710 s | 101-120 words | 0 |
| Research | `gpt-5.6-sol`, medium | `gemini-3.1-pro-preview`, medium | 6.057 s | 48.978 s | 104-119 words | 0 |
| Verification | `gpt-5.6-sol`, high | `gemini-3.1-pro-preview`, high | 15.280 s | 81.126 s | 102-115 words | 0 |

Research was 2.93 times slower than Fast for the complete segment but materially improved the methodological discussion: it raised trajectory-model uncertainty, informative attrition, time-varying confounding, joint cognition-survival models, and the need for a well-defined causal estimand. Verification was 4.85 times slower than Fast and 1.66 times slower than Research, but it checked the paper's five-group BIC selection and highest-posterior assignment against the original PDF, distinguished model fit from proof of biological classes, and challenged an inference that exceeded the reported method.

All three profiles kept visible contributions concise despite their larger internal allowances. SSE traffic was approximately 29 KB per profile, every expected AI message completed, and no model response was truncated, interrupted, or handed invisibly to the other participant. One automatic conversation-digest job overlapped part of the comparison window, so these figures are operational measurements rather than a controlled provider benchmark. They nevertheless demonstrate that profile switching works without a server restart and that the intended quality-latency tradeoff is observable end to end.

Operational recommendation: keep Fast as the default, use Research for mathematically or statistically demanding exploration, and reserve Verification for disputed claims or explicit requests to inspect the original document.

## Design audit

### Strengths

- The product goal is specific and repeated consistently: meaningful intellectual exchange that improves learning.
- Human authority is encoded in both controls and lifecycle, not merely described in prompts.
- Concision is a design constraint, which protects readability and latency.
- Momo and Bobby receive complementary but non-hierarchical roles.
- Momo's always-carried critique skill explicitly audits Bobby's and Sam's substantive claims for necessary assumptions, evidentiary sufficiency, scope, causal interpretation, and required qualification while preserving the defensible core and naming one decisive test.
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
- Sam's composer receives a restrained active-floor highlight when the AIs are waiting for the host.
- The Sam label in the host composer receives the visible active-floor emphasis, while the redundant conversation-card header row is omitted.
- Explicit AI LLM mode buttons are available on both the landing page and conversation header, making Fast, Research, and Verification choices visible for each next segment.
- Topic/conversation digestion is visible through ephemeral System transcript cards that never enter persistence, model context, summaries, or exports.
- Participant-name highlighting improves conversational scanning.
- Background knowledge is visually separated from the core response.
- Digests sit below the main conversation instead of competing in side frames.
- The closeout view creates a clear download opportunity before single-session deletion.
- Closeout performs no automatic synthesis. It exposes a Research-default / Verification-opt-in selector first, then blue, stage-specific progress notices only after Sam requests final and one-page summaries; save/download actions precede the optional learning evaluation.

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
- Immediate End, cancellable final and one-page summary work, readable transcript/Summary Digest/one-page/ZIP export, and confirmed new-session purge

The earlier documentation overstated several capabilities. Automatic job resumption, safe retries, circuit breakers, production metrics, formal claim graphs, and embedding retrieval are **not implemented** and are now recorded as deferred work.

## Logic-flow audit and fixes

### High-priority findings resolved

1. **Closing state could be overwritten by streaming cleanup.** A close request can interrupt an active segment. The segment's unconditional cleanup previously restored `HUMAN_FLOOR`, racing with `CLOSING` or `CLOSED`. Cleanup now preserves terminal lifecycle states, and final synthesis waits for the session lock so partial text is saved first.
2. **New-session retention was enforced mainly by the interface.** A direct API call could create alongside a retained session. The API now returns `409 Conflict` whenever any prior session exists unless `force_reset=true` is used on creation; this includes closed sessions so the one-session invariant is exact.
3. **Internal upload paths were exposed.** Session, upload, document, and JSON views could reveal managed filesystem paths. Public document serialization now removes `stored_path`; archive creation uses internal records only inside the server.
4. **First-token timeout was configured but not enforced by orchestration.** The service now applies the provider's first-token deadline before continuing the stream and returns control to Sam on failure.
5. **Source digest type handling could crash segment context assembly.** The source-context assembler assumed `documents.digest` was always a string and called `.strip()` directly, but parsed JSON payloads are stored as objects. It now normalizes non-string digests with `json.dumps(...)`, preventing 500 errors during live streams when documents are pre-digested.
6. **Summary cancellation crossed lifecycle boundaries.** The cancel route could close an active conversation with no closeout job, and cancelling while the one-page stage ran could leave that job stuck. Cancellation is now rejected outside `CLOSING`, idempotent after `CLOSED`, and consistently marks both final-summary and one-page-summary jobs cancelled.
7. **Closed sessions still accepted recap and upload mutations.** Both routes now return `409 Conflict` once closeout begins, preserving the downloadable final record.
8. **One-page export selection was stale.** When multiple one-page digests existed, direct and Markdown exports could choose the oldest. Both now select the latest completed one-page digest.
9. **Repeated recap requests could launch concurrent digest calls.** An active Conversation Digest job is now reused and recap controls are disabled while it runs, preventing duplicate provider work.
10. **Closeout synthesis was automatic and over-selected Verification.** Ending a table now closes it without provider work. A top-of-closeout selector offers Research as the balanced default and Verification only by Sam's explicit choice; archive/transcript downloads, evaluation, and a new table remain independent of synthesis.
11. **Ambiguous Latin source text could override English.** Source detection now treats English as the default and switches only on clear non-English evidence. Once Sam names a conversation language, it controls all later source, Topic, Conversation, final, and one-page synthesis prompts regardless of the document language; an actual mid-session switch also queues one deduplicated Topic Digest refresh.

### Medium-priority findings resolved

- Frontend dependency declarations used floating `latest` versions despite a lockfile. Exact versions are now declared.
- Generated TypeScript/Vite files and local work artifacts are now ignored.
- The frontend new-session guard now requires either all sessions to be closed or an explicit reset acknowledgement, preventing a finalization-in-progress bypass.

### Remaining logic risks

- Natural-language recap, closeout, and original-source verification include English and Chinese control forms. Language switching recognizes direct forms such as “let's talk in English,” “let's discuss in German,” “change the conversation language to French,” and “switch to Japanese for the rest,” while ordinary topical mentions remain ordinary discussion. Other languages and uncommon paraphrases may still be treated as ordinary discussion; Sam can use the visible controls or an explicit supported form.
- Provider cancellation stops visible consumption but cannot guarantee remote computation is cancelled for every compatible server.
- Empty or malformed model output falls back in some digest paths but recovery behavior is not uniform across all provider failures.
- Document digestion can be retried only by a future feature; completed section checkpoints are not resumable.

## Security and privacy audit

Appropriate local safeguards are present: secrets are environment-only, sensitive paths and runtime data are ignored, upload paths are managed, deletion/archive paths are root-validated, and source text is framed as evidence rather than instructions.

Before internet exposure, add authentication, authorization, CSRF/deployment-origin review, rate and upload limits at the edge, malware scanning, stricter MIME/content validation, HTTPS, secret management, database/file isolation, security headers, audit logging, retention policy, and backup/recovery procedures.

Before pushing to GitHub, scan the working tree and repository history for secrets. The audit did not print or validate any plaintext API key.

## Verification evidence

- Backend: **98 tests passed** with `.venv\Scripts\python.exe -m pytest backend\tests -q`. Coverage includes ephemeral voice transcription, audio format/size/lifecycle guards, topic-guided provider requests, multi-round persistence of expanded long-Sam allowances, English-default conservative document-language detection, natural language-switch forms, Sam-authoritative output language across differently languaged sources, both-participant live language tags, resilient Chat Completions metadata/error handling, exact profile/model/reasoning metadata in SSE and stored turns, preservation of background knowledge/inference in Conversation Digest materials, synthesis-only Summary Digest export, close-without-summary behavior, Research-default and Verification-opt-in concurrent Momo/Bobby closeout generation, identical delivery of bounded extracted text, processed source digests, Topic Digest, complete Conversation Digest history, and substantive transcript to both authors, explicit supporting digest files in the complete archive, digest-only ordinary source context, explicit original-source verification routing, bounded Gemini hidden-thinking reserves and timeout margins, one timeout-only retry with ephemeral notice and partial reset, cross-participant timeout handoff, exact one-session retention, post-close immutability, joint summary-job cancellation, latest one-page selection, and recap deduplication.
- Covered regression cases also include voice-expanded first-token/stream-idle/total-turn deadlines, first-token timeout recovery, immediate stalled-stream cancellation with partial-text retention, startup reconciliation, session-task cancellation, bounded context assembly, and preservation of `CLOSING` during interrupted stream cleanup.
- Frontend: **13 Vitest tests passed**, followed by a successful TypeScript/Vite production build. Coverage includes actual model/mode/reasoning disclosure per AI turn, translated and separate background-knowledge provenance formatting, the ephemeral timeout-retry System card, Research/Verification Momo/Bobby closeout status, landing-page ordering and accent styling, localized Sam-turn reminder copy, last-speaker voice selection, and the accessible persistent reminder toggle in addition to the existing voice-input, upload, and digest-status behavior. The earlier local browser audit confirmed that Voice input, its privacy notice, the four composer controls, textarea, and Answer button fit within Sam's fixed panel without scrolling or console errors.
- Independent API lifecycle smoke script (mocked providers) confirms session creation, Sam message routing, segment streaming, document digest jobs, recap triggering, closeout, learning-evaluation availability, and export paths in a clean temporary DB.
- Live-provider simulation remains intentionally separate from CI because it depends on external model availability, consumes API capacity, and transmits approved source extracts.
- A current local-browser regression created and ended a temporary session against the rebuilt server. It observed `CLOSED` immediately with no final-summary job, Research selected by default with the expected medium-reasoning model labels, explicit Verification label switching, and archive/transcript/evaluation/new-table controls without synthesis. The test session was then purged and the app left on the clean landing page.

The 2026-07-22 current-code audit reported Momo (`gpt-5.6-luna`, OpenAI Responses) and Bobby (`gemini-3.5-flash-lite`, Google-compatible Chat Completions) configured and reachable. Fast, Research, Verification, explicit original-source retrieval, concurrent closeout, every export, the unsaved-session warning, and final purge were exercised with an audit-created session. The app was left with no retained session.

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
