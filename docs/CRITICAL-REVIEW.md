<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

> Canonical source: This is the active `academic-roundtable-github-ready` workspace.
> The sibling `academic-roundtable/` folder is archived and not for new development.

# Professional Agent-System Critical Review

Date: 2026-07-20  
Review lens: AI-agent orchestration, learning quality, reliability, latency, data safety, and lean delivery

## Executive judgment

Academic Roundtable has a strong product thesis: **deep conversations for better learning**. Human authority, bounded AI-to-AI segments, concise disagreement, digest-based focus, and explicit source provenance form a coherent learning system rather than a generic multi-agent demo.

The local MVP architecture is appropriate for pilot use. React, FastAPI, SQLite, server-sent events, and provider adapters keep the system understandable and inexpensive to change. The most important weaknesses were lifecycle reliability rather than missing features: an interrupted provider call could remain blocked, background work could race with session deletion, restarts could leave false running states, and accumulated context could degrade latency. These priority-zero issues are now addressed.

The next investment should still emphasize measurement. The manually stopped, review-before-submit Sam voice-input increment is now implemented because it improves host accessibility without changing the text-centered orchestration model. Multi-user hosting, embeddings, OCR, continuous voice interaction, and other broad features should remain postponed until pilot evidence justifies them.

## Priority findings and disposition

| Priority | Finding | Risk | Disposition |
|---|---|---|---|
| P0 | Interrupt previously set a flag but could wait for a stalled provider timeout | Sam could not reliably regain the floor | Fixed with active task cancellation and partial-text preservation |
| P0 | Background tasks were not owned by their session | Purge/new-session operations could race with late writes | Fixed with session task tracking and cancellation before purge/close |
| P0 | Process restarts could leave jobs, documents, rounds, and sessions marked running | Misleading UI and blocked lifecycle | Fixed with deterministic startup reconciliation |
| P0 | Prompt assembly lacked explicit total context ceilings | Long sessions could become slow, costly, or exceed provider limits | Fixed with bounded, visibly clipped context sections |
| P1 | Background jobs are records, not a durable priority queue | Work is not resumable; digestion can contend with live turns | Planned after pilot evidence |
| P1 | Provider failure policy has timeouts but no bounded retry/circuit breaker | Transient failures require manual recovery | Planned, with retries only before visible output |
| P1 | Learning quality has no repeatable evaluation harness | Prompt changes cannot be compared safely | Highest-priority next increment |
| P1 | Upload validation is extension/size oriented | Public deployment would need stronger content controls | Planned before any remote pilot |
| P2 | Lexical retrieval quality is not measured | Evidence selection may miss conceptual matches | Evaluate before adding hybrid retrieval |
| P2 | Host intent matching cannot cover every language or paraphrase | Unrecognized recap/closeout/source-check commands may be treated as ordinary discussion | English and Chinese control forms are covered; extend from multilingual pilot fixtures |
| P3 | No authentication or user isolation | Unsuitable for shared/public hosting | Explicitly postponed |

## Implemented reliability changes

### Immediate, loss-aware interruption

The service now tracks the active streaming task for each session. Interrupting cancels the network-bound stream immediately instead of waiting as long as the provider read deadline. Any already received text is retained as an interrupted contribution, the round is finalized consistently, and control returns to Sam.

### Session-owned background work

Topic, conversation, document, and final-summary tasks are registered against their session. Close, discard, recap, and new-session transitions cancel and await conflicting work before changing or deleting session state. Unfinished job and document records are left in explicit cancelled/failed states rather than silently disappearing.

### Restart recovery

At application startup, abandoned queued/running jobs, processing documents, active rounds, and transient session states are reconciled to stable terminal or human-floor states. A final summary interrupted by restart remains distinguishable from a user-cancelled summary, while the transcript and digest history remain downloadable.

### Explicit context budgets

Every live request includes the Topic Digest, latest Conversation Digest, active question, the five most recent complete rounds, and any processed document digest, with hard character budgets for each section and the combined history. Ordinary rounds do not resend raw passages. Only Sam's explicit request to check or verify the original source activates one-segment retrieval; those excerpts are labeled as untrusted evidence so document text cannot masquerade as system instruction. Clipping is visible in the prompt and never deletes stored data.

Character ceilings are a pragmatic MVP control. Selective Fast/Research/Verification profiles now provide model-aware budget and timeout multipliers; a later provider-capability layer should estimate tokens per model and reserve output capacity precisely.

Persistent language state now prevents casual provider language drift: a conservative non-English source signal can initialize the session, Sam's explicit request takes precedence, and a protected language tag is attached to every live and synthesis request. Remaining risk is heuristic classification of mixed-language, closely related Latin-language, or poor-OCR sources. The UI exposes the active language so Sam can correct it explicitly; production-quality language identification should be justified by fixture evidence rather than added pre-emptively.

## Architecture critique

- `RoundtableService` is broad, but keeping orchestration centralized is acceptable while product behavior changes quickly. Split it only when tests reveal stable seams, likely into lifecycle, dialogue, digestion, and export services.
- SQLite is a good local source of truth. Schema migrations become mandatory before distribution because additive startup initialization is not a long-term migration strategy.
- In-process tasks are appropriate for a single-user pilot. They are not a durable queue; restart recovery currently marks work honestly rather than resuming it.
- Polling for jobs is simple and adequate at current scale. A second event channel would add complexity without clear learning value.
- Provider adapters correctly isolate protocol differences. They next need a small capability and reliability policy layer, not provider logic scattered through orchestration.

## Recommended implementation plan

### Next: learning-quality evaluation

Create 10–15 representative fixtures covering definitions, theory comparison, causal reasoning, evidence interpretation, epidemiologic methods, and source-grounded debate. Score relevance, engagement with the prior speaker, novelty, reasoning, calibrated uncertainty, provenance, repetition, recap fidelity, learner value, first-token latency, and interruption latency. Use Sam's judgments as the primary signal and make prompt changes only when the fixture results improve.

### Then: bounded provider reliability

- Retry only failures that occur before any user-visible token, with a small attempt limit and jitter.
- Add per-provider cooldown/circuit state and structured error identifiers.
- Reserve concurrency for live dialogue so source digestion cannot delay Sam.
- Record timing by phase: queue, connection, first token, stream, and persistence.
- Add richer model capability metadata and token-aware context allocation. The first profile layer is now implemented; deterministic calculator/Python/R verification remains future work for mathematical claims.

### Then: document and retrieval hardening

- Validate file signatures and extracted-resource limits, and provide explicit retry for failed digestion.
- Measure passage recall with a small question/source fixture set.
- Improve lexical chunking and query expansion first; add embeddings or reranking only if measured failures remain.
- Add OCR only when scanned documents appear frequently in real use.

### Before any shared deployment

Add authentication, authorization, per-user data isolation, durable migrations, edge rate/upload limits, malware scanning, HTTPS, deployment secret management, security headers, audit logging, retention policy, backups, and a durable worker queue.

## Verification recommendations

The deterministic suite now covers immediate stalled-stream cancellation, partial text retention, startup reconciliation, cancellation of session-owned background work, bounded context assembly, timeout recovery, lifecycle races, strict retention, post-close immutability, summary cancellation, latest-summary export selection, recap deduplication, explicit recap-intent discrimination, multi-round latest-Sam retention, long-input deadline persistence, retrieval locators, and routing. Add frontend interaction tests for closeout confirmation and accessibility. Live-provider smoke tests should remain opt-in because they consume capacity and are nondeterministic.

## Lean decision rule

Do not add a feature because it is conventional in agent systems. Add it when pilot evidence identifies a learning, reliability, safety, or usability failure; choose the smallest observable change; test it; and keep it only if the relevant outcome improves.
