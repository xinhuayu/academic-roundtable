<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

> Canonical source: This is the active `academic-roundtable-github-ready` workspace.
> The sibling `academic-roundtable/` folder is archived and not for new development.

# Academic Roundtable: Lean Implementation Plan

Last reviewed: 2026-07-20

## Product outcome

Build and validate a focused, responsive roundtable where two LLMs help Sam learn through concise academic explanation, disagreement, and synthesis. The governing principle is **deep conversations for better learning**.

The project uses short, testable increments. It does not add multi-user or cloud infrastructure until the core learning experience has been piloted successfully.

## Delivery rules

- A working vertical slice is preferred to a broad unfinished subsystem.
- Interactive response quality and interruption safety outrank feature count.
- Every increment ends with automated checks and a short human learning-quality review.
- Documentation distinguishes implemented behavior from planned behavior.
- Provider-specific logic stays behind adapters.
- Secrets, transcripts, and uploaded sources remain outside version control.

## Completed MVP increments

### 1. Walking roundtable — complete

- React/FastAPI/SQLite application skeleton
- Two configurable provider adapters
- SSE token streaming and attributed transcript
- Provider health reporting
- Local persistence and production frontend serving

### 2. Host-directed academic segments — complete

- Two-to-five-round scheduler
- Immediate interruption with partial-response retention
- Concise Momo/Bobby debate protocol
- Sam-first answering, direct-name routing, and random undirected routing
- Independent first answers when both AIs are addressed
- Scheduled invitations to Sam and “Let them continue” behavior
- Greeting-only opening and one-time closing response

### 3. Focus and memory — complete

- Provisional Topic Digest and latest Conversation Digest
- The five most recent complete rounds in live context
- Automatic digest scheduling every five or six completed rounds
- Natural-language and interface-triggered recaps
- Append-only digest history for final synthesis and export
- Final summary generated at session close

### 4. Minimal document grounding — complete

- PDF, TXT, and Markdown upload with 30 MB limit
- PDF ingestion now uses PyMuPDF + pdfplumber for table detection and figure-object extraction hints
- Page/section extraction and hierarchical source digestion
- Table extraction prefers structural cues from pdfplumber and PyMuPDF, with pypdf fallback
- SQLite FTS5 passage retrieval with locators
- Digest-only source context during ordinary rounds; no raw passages are repeatedly sent
- Explicit Sam requests to check the original source/PDF/document activate one-segment passage retrieval with source-sized token and timeout limits
- Sources-only evidence policy
- Clearly labeled model background knowledge when permitted
- Public API redaction of internal managed-file paths

### 5. Conversation-first interface and closeout — complete

- Rolling transcript as the dominant view
- Narrow, persistent Sam composer and always-reachable interrupt control
- Active-floor highlight around Sam's composer whenever the AIs are waiting for the host
- Matching highlight on the top-right **Sam has the floor** indicator
- Local-only System digestion notices in the transcript, derived from queued/running topic or conversation digest jobs and removed automatically without persistence
- Participant-name highlighting and distinct background-knowledge styling
- Digests and periodic summaries below the conversation
- Close-session page with highlighted blue final-summary and one-page-summary progress stages, comprehensive Summary Digest download, one-page summary download, summary cancellation, and digest-based fallback wrap-up
- Save/download row before the optional **Evaluate learning** action
- Momo-authored synthesis-only comprehensive Summary Digest using a dedicated critical-synthesis skill, plus a separate one-page learning summary (key concepts, main issues, strategies, research priorities), readable transcript, and ZIP archive downloads; Topic, processed-source, latest Conversation, historical digest, and structured session JSON remain inside the archive
- Guarded one-session retention, optional save/evaluation handoff, and safe one-choice purge before replacement

### Sam voice-input increment — complete

- Record during Sam's floor or interrupt an active AI segment and begin speaking
- Continue recording until Sam manually stops, with no duration cutoff; retain only the provider-compatible audio-size safeguard
- Send the in-memory recording to the configurable OpenAI transcription endpoint without saving audio locally
- Guide transcription with the topic, active question, and academic terminology while limiting correction to spelling, punctuation, and obvious grammar
- Return an editable draft to Sam; never auto-submit a transcription
- Expand Sam message validation to 24,000 characters and apply larger recent-turn context, response-token, and timeout multipliers for voice-derived or otherwise long input
- Retain the latest Sam contribution through every AI round in the segment and apply the long-input multiplier consistently to first-token, stream-idle, and total-turn deadlines
- Require an explicit recap command so ordinary academic uses of “summary” do not interrupt conversation routing
- Surface unbounded elapsed recording time, transcription progress, privacy disclosure, and review-ready status inside Sam's persistent composer
- Cover endpoint lifecycle/size guards, provider request construction, configuration, long-input budgets, and frontend states with deterministic tests

## Audit stabilization increment — complete

The independent audit added:

- Server-side rejection of a new session whenever any prior session is retained unless reset is explicitly requested
- Removal of internal upload paths from session, upload, document, JSON, and archive metadata
- Explicit first-token deadline enforcement
- Close/interrupt race protection so streaming cleanup cannot reopen a closing session
- Final-summary serialization behind the session lock
- Exact frontend dependency versions and additional generated-file exclusions
- Regression tests for timeout recovery and lifecycle safety
- Exact server-side one-session enforcement for active and closed retained sessions
- Read-only closing/closed records, with recap and source upload rejected after closeout begins
- Summary cancellation constrained to closeout and propagated across final-summary and one-page-summary jobs
- Active recap-job reuse to avoid duplicate provider work, plus latest-completed one-page export selection
- Accurate UI disclosure that extracted source sections are transmitted to the configured model server for digestion
- Honest documentation of deferred reliability and production features

## Agent reliability review increment — complete

The professional agent-system review implemented the highest-priority controls before adding features:

- Immediate cancellation of a stalled provider stream with partial-response retention
- Session ownership and orderly cancellation of background work before close or purge
- Startup reconciliation for abandoned jobs, documents, rounds, and transient session states
- Explicit per-section and total context ceilings with visible clipping
- Untrusted-evidence labeling for source passages retrieved only during explicit verification
- Regression tests for all four reliability changes

The prioritized rationale and postponed work are recorded in [CRITICAL-REVIEW.md](CRITICAL-REVIEW.md).

## Multi-provider reasoning and latency increment — complete

- Momo and Bobby may use separate provider stacks; the environment template demonstrates OpenAI for Momo and Gemini 3.5 Flash-Lite for Bobby.
- The Chat Completions adapter forwards `reasoning_effort`; Anthropic Messages is also available as an optional Bobby alternative.
- Live turns remain low-reasoning and concise, while source/topic/conversation/final digests and learning evaluation use medium reasoning.
- Per-provider connection, first-token, stream-idle, and total-turn limits are configurable without code changes.
- Background digest sections and complete synthesis jobs have separate, longer configurable deadlines.
- Regression coverage protects reasoning propagation and timeout environment parsing.
- Host-invitation detection requires a complete final question to Sam, preventing ordinary direct address from prematurely ending a segment.
- Roles are deliberately asymmetric: Bobby develops the strongest defensible case; Momo audits both Bobby's and Sam's claims for assumptions, evidentiary support, scope, causal interpretation, and required qualification, then identifies a decisive test while avoiding reflexive disagreement. Momo also serves as the default OpenAI-backed digest provider.
- Participant-specific live budgets allocate 800 base tokens to Momo and a 1,400-token visible-response basis to Bobby. Gemini routes apply bounded 4,096 / 12,288 / 32,768 completion floors for Fast / Research / Verification so hidden thinking and visible prose share sufficient room.
- Chat Completions finish reasons are inspected; length-limited fragments are retained as interrupted and cannot silently hand the floor to the other AI.

## Selective flagship reasoning profiles — complete

- Added a persisted per-session `conversation_profile`: `fast`, `research`, or `verification`.
- Fast remains the default and preserves the current low-latency provider models and concise live turns.
- Fast Bobby uses Gemini minimal reasoning with a 90-second effective first-token deadline and nine-minute total ceiling. Timeout recovery is attempted once with a 1.5× retry-only deadline.
- Research routes Momo to GPT-5.6 Sol and Bobby to Gemini 3.6 Flash by default, with medium reasoning, 2.75× live token allowances, 2.5× live deadlines, a focused 140–220-word target, and 1.5× background digest deadlines. Gemini adds a 12,288-token completion floor and 2× deadline margin.
- Verification routes Momo to GPT-5.6 Sol and Bobby to Gemini 2.5 Pro with high reasoning, 2× live token allowance, and 2.5× live deadlines; Gemini adds a 32,768-token completion floor and 2.25× deadline margin. Explicit requests to check the original source automatically use this profile for one segment.
- Source excerpts remain excluded from ordinary rounds. Verification mode alone increases reasoning; raw excerpts are still added only when Sam explicitly requests the original source.
- The landing page and session settings expose the profile selector, `/api/meta` publishes the profile catalog, and `.env.example` documents all override variables.
- The landing page and conversation header expose explicit AI LLM mode buttons; the in-session choice applies to the next segment and is disabled during active streaming.
- `/api/meta` publishes the exact Momo/Bobby model and reasoning route for each profile. The conversation header and provider cards show the selected route, live SSE replaces it with the effective route, and each stored AI contribution retains its actual profile/model/reasoning metadata.
- Numerical/statistical claims remain candidates for a future deterministic calculator or Python/R tool; larger LLM budgets do not substitute for computation.

## Persistent multilingual conversation — complete

- Added `conversation_language` and `language_source` to session state with additive migration support.
- A conservative source-language detector can initialize non-English sessions after extraction; Sam's explicit language instruction has permanent precedence over later uploads.
- A constrained output-language tag is appended to every Momo/Bobby live turn and every source, Topic, Conversation, final, and one-page synthesis task.
- Localized greetings and closeout text are available for common languages; the UI header and readable exports disclose the active language.
- JSON keys, formulas, proper nouns, and exact quotations remain stable while visible prose and JSON string values use the selected language.
- English and Chinese recap, closeout, source-verification, and host-question control forms have deterministic coverage. Additional intent-language variants remain a fixture-driven extension.

## Next agile increments

### Increment A — learning-quality pilot

Goal: validate that concise opposition creates better learning.

Harness status: **implemented**. The closeout page now includes session-scoped automated diagnostics and Sam's evidence-backed rubric, and saved evaluations are included in exports. The repository also includes ten fixtures and optional baseline/candidate comparison tools. Running the controlled pilot and tuning behavior remain the next product activities; see [LEARNING-QUALITY-EVALUATION.md](LEARNING-QUALITY-EVALUATION.md).

Deferred deliberately: a cross-session evaluation-history and trend interface. Each current session remains clean and independent; starting a new table removes its evaluation with all other session data. Reconsider history only after the pilot establishes which measures are useful and defines an explicit retention policy.

Build and evaluate:

- A ten-topic fixture set spanning conceptual explanation, theory comparison, evidence interpretation, epidemiologic methods, and source-grounded discussion
- A lightweight rubric for relevance, engagement, novelty, reasoning, provenance, uncertainty, repetition, recap fidelity, and learner value
- Manual timing for acknowledgement, provider dispatch, first token, completion, and interruption
- Prompt tuning based on Sam's qualitative judgments

Exit criteria:

- A 20–30 minute session remains focused and readable.
- AIs respond to one another rather than restating independent answers.
- Recaps preserve the intellectual progression and disagreements.
- Sam can reliably distinguish source evidence from background knowledge.

### Increment B — bounded reliability

Goal: make expected provider and job failures easier to recover from without introducing a distributed stack.

Implemented in this increment:

- One timeout-only retry, including timeouts after partial output; the UI clears the discarded fragment and shows a non-persistent System retry notice
- One cross-participant handoff after an exhausted retry; the fallback prompt forbids inventing the unavailable model's response and preserves the round when the fallback succeeds

Remaining candidate work:

- Explicit UI recovery choices after partial streamed failure
- Per-provider concurrency limits and simple health cooldown
- Startup reconciliation that marks abandoned running jobs as interrupted
- Manual retry for failed document/digest jobs
- Structured latency and token metadata without recording secret prompt content

Exit criteria:

- A failed provider does not corrupt session state or disable the other provider.
- Retries never duplicate visible partial content.
- Restarted applications present abandoned jobs honestly and allow safe manual recovery.

### Increment C — grounding quality

Goal: improve source usefulness only if the pilot shows lexical retrieval is insufficient.

Candidate work:

- Retrieval evaluation fixtures and precision review
- Better query generation or lexical reranking
- OCR for image-only PDFs
- Optional embeddings and hybrid retrieval after evidence justifies the complexity
- Stronger passage-level citation display in the transcript

### Increment D — GitHub/public preview readiness

Goal: make the repository safe and understandable for outside collaborators.

Completed repository preparation: contributor and security guidance, development/test documentation, release checklist, and GitHub Actions checks for the backend, frontend, and accidental tracking of local environment files. License selection, clean-copy verification, history scanning, screenshots, and accessibility review remain publication gates.

Required before publication:

- Choose and add a license
- Run a secret scan and inspect repository history
- Add CI for backend tests and frontend build
- Add contribution and security policies if accepting outside reports
- Capture current interface screenshots
- Test setup from a clean clone on supported Python and Node versions

### Increment E — remote or multi-user deployment, only if requested

Potential scope:

- Authentication and authorization
- Per-user/project data isolation and configurable retention
- Request size/rate controls, malware scanning, and audit logging
- PostgreSQL/object storage and a durable worker queue
- Deployment secrets management, HTTPS, backups, and monitoring

## Current technical policies

| Work type | Output budget | Execution |
|---|---:|---|
| Live Momo contribution | 800 base completion tokens; Fast targets 60–110 words; Research uses 2.75× token room and targets 140–220 words | critical response plus sufficient OpenAI reasoning room |
| Live Bobby contribution | 1,400 visible-response basis; Gemini completion floors: 4,096 Fast, 12,288 Research, 32,768 Verification; 65,536 hard cap | concise case development plus provider-hidden thinking reserve |
| Conversation digest/recap | at least 2,000; default 4,000 | background or requested foreground |
| Topic digest | at least 3,000; default 6,000 | background |
| Source section/synthesis | at least 4,000; default 8,000 | background |

Live context keeps the participant protocol, Sam's direction, Topic Digest, latest Conversation Digest, five recent rounds, and processed document digest. Targeted raw evidence is added only for a one-segment original-source verification request from Sam. Complete digest history is reserved for final synthesis and export.

Conversation-digest jobs receive the prior Conversation Digest plus the recent full transcript. Provenance-labeled background knowledge/information, source evidence, inference, and speculation are explicitly retained as input material and mapped to separate digest fields.

Timeout defaults are provider-configurable: 10 seconds to connect, 45 seconds to first token, 45 seconds of stream-read idle time, and 180 seconds total per live turn. Digest operations have longer explicit task deadlines.

## Verification strategy

Automated checks should cover:

- Segment bounds and completed-round accounting
- Interrupt and closing-state precedence
- First-token and total-turn failure handling
- Direct mention and both-participant routing
- Five-round history and greeting exclusion
- Digest scheduling and append-only history
- Source locator retention and public path redaction
- Safe one-session purge and export eligibility
- Frontend type checking and production build

Model-behavior evaluation remains partly human because “better learning” cannot be reduced to a deterministic unit test.

## Definition of done for the first public pilot

- Clean-clone setup and documented verification succeed.
- Both real provider configurations pass health, streaming, cancellation, and failure checks.
- No critical lifecycle, credential, path-disclosure, or export defect remains.
- A long-session learning pilot meets the agreed readability and coherence criteria.
- Current limitations are accurate and visible.
- A license and automated CI are present.
