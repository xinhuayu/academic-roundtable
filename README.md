<p align="center">
  <img src="frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

# Academic Roundtable

Academic Roundtable is a local-first web application where two configurable LLM participants—**Momo** and **Bobby**—hold an interruptible academic discussion while **Sam** acts as host, learner, participant, and judge.

Its guiding principle is **deep conversations for better learning**. The AIs debate in concise, readable turns; Sam can question, redirect, interrupt, request a recap, or let them continue for another bounded segment.

> Status: audited lean MVP for local learning pilots. It is not yet designed for public hosting or multiple users.

> **Development baseline:** This `academic-roundtable-github-ready` copy is the canonical workspace for all future development, testing, documentation, and GitHub preparation. The earlier working folder is retained only as a historical source snapshot.

## Why this project

Ordinary multi-agent chats tend to become long parallel monologues. Academic Roundtable instead treats focus, human authority, and readable disagreement as system behavior:

- Bobby develops the strongest defensible case through mechanisms, evidence needs, and integrative explanations; Momo persistently audits Bobby's and Sam's claims for necessary assumptions, evidentiary support, scope, causal interpretation, qualifications, alternatives, and boundary conditions. She preserves what is defensible and identifies the decisive test rather than disagreeing by reflex. Both answer Sam directly and pursue depth without turning concise contributions into mini-essays.
- AI-only discussion is limited to two to five rounds at a time. Automatic mode uses two rounds by default, with an occasional three-round variation; Sam may select an exact fixed length.
- Sam can interrupt at any moment without losing already streamed text.
- Live turns use the Topic Digest, latest Conversation Digest, active question, and five recent rounds.
- Uploaded sources can ground the discussion, while each AI contribution includes a concise, separately styled `Background knowledge:` line for internal model knowledge (or an explicit no-additional-knowledge statement).
- Sam can choose Fast discussion, Research mode, or Verification mode. Research and Verification route live turns and background digests to configured flagship models with medium or high reasoning and larger, longer budgets; the Fast profile remains the low-latency default.
- The conversation language is persistent session state. Source processing defaults to English and changes language only when the material is clearly non-English. An explicit request from Sam (for example, “respond in Chinese” or “请用中文回答”) takes precedence over the source language for every later live turn, Document/Topic/Conversation Digest, and closeout summary. Every model request receives a protected output-language instruction.
- The AI LLM mode is an explicit button group on both the landing page and conversation page. The conversation control applies to the next segment and is disabled while the AIs are streaming.
- The conversation header and participant cards show the model and reasoning route selected for the segment. Every completed or interrupted AI contribution retains its actual `profile`, `model`, and `reasoning_effort` and displays them beside the speaker, so a Research/Verification turn cannot be mistaken for a Fast/Lite turn.
- Full transcripts and digest history remain available as inputs to final synthesis and in the complete archive. The closeout Summary Digest contains only Momo's comprehensive synthesized learning record; it does not append the Topic Digest, processed-source digests, current Conversation Digest, or earlier digest history.
- Ending a session performs no automatic synthesis. The closeout page first offers an optional mode selector: Research is the default, while Verification is available when Sam explicitly wants maximum checking. If requested, a highlighted blue notice shows Momo generating the comprehensive Summary Digest and Bobby generating the one-page summary concurrently with the selected routes. Each receives the same frozen package containing bounded extracted source text (never the original binary), processed document digests, the Topic Digest, all periodic/requested Conversation Digests, and the complete substantive conversation history. Cancel remains available after generation begins. Archive/transcript downloads and the next-roundtable action never require summary generation or evaluation.

## Core workflow

```mermaid
flowchart LR
    A["Create topic"] --> B["Momo and Bobby greet"]
    B --> C["Sam sets first direction"]
    C --> D["2–5 round AI segment"]
    D --> E{"Sam's choice"}
    E -->|"question or redirect"| C
    E -->|"interrupt then continue"| D
    E -->|"recap"| F["Visible digest"]
    F --> C
    E -->|"End"| G["Optional final summary and downloads"]
```

## Features

- Two independently configured model servers (OpenAI-compatible or native Anthropic-compatible)
- Responses API, Chat Completions, and Anthropic Messages adapter styles
- Streamed, interruptible Momo/Bobby discussion segments
- Direct routing with `@momo`, `@bobby`, or participant names
- Random first respondent for undirected Sam messages
- Independent first answers when both AIs are addressed
- Concise agree/disagree/qualify/extend academic turns
- Scheduled invitations to Sam and **Let them continue** when Sam defers
- Natural-language and button-triggered recaps
- Topic, conversation, periodic, requested, and final digests
- Conversation Digests receive the prior digest plus the recent full transcript and explicitly retain useful labeled background knowledge, source evidence, inference, and speculation as distinct provenance categories
- The five most recent complete rounds in every live model request
- PDF, TXT, and Markdown upload, extraction, digestion, and FTS5 retrieval
- PDF extraction uses PyMuPDF + pdfplumber for table-aware extraction and figure-object detection cues (pypdf fallback remains for compatibility)
- Sources-only mode or labeled internal background knowledge
- Persistent multilingual discussion, digest, summary, greeting, and closeout output, with Sam's explicit language choice taking precedence over automatic source-language detection
- Conversation-first rolling interface with persistent host controls
- Highlighted Sam composer whenever Sam has the floor
- Optional Sam voice input during the human floor, or **Interrupt and speak** during an AI segment; recordings continue until Sam stops them, are transcribed with topic-aware light spelling/punctuation correction, and return to the composer for review and editing before submission
- Optional browser-local **Turn reminder** when an AI segment returns the floor to Sam. It speaks a short localized equivalent of “Sam, what do you think?”, prefers a feminine installed voice after Momo and a masculine installed voice after Bobby when available, and can be disabled persistently in Sam's panel without using an AI API
- Highlighted **Sam** label in the host composer when Sam has the floor
- Provider health and background-job progress
- Temporary local System cards for active Topic Digest and Conversation Digest work; these disappear on completion and are never stored or exported
- Blue closeout progress messages that identify Momo and Bobby as concurrent summary authors and show both job details
- Readable transcript, synthesis-only comprehensive Summary Digest, one-page summary, and complete ZIP archive exports after closure; structured session data and explicit supporting digest files remain inside the archive for machine use
- An **End** action that interrupts generation and opens closeout immediately
- Cancellable final-summary generation; downloads remain available without it
- Single-session local retention with a protected download handoff
- Optional PDF/TXT/Markdown sources can be selected on the landing page; they are uploaded and queued for background digestion immediately after Start, while the greeting screen is already available. The conversation-page evidence library remains available for later additions.

## Architecture

```mermaid
flowchart TB
    UI["React + TypeScript UI"] <-->|"JSON and SSE"| API["FastAPI"]
    API --> Service["RoundtableService"]
    Service --> M["Momo adapter"]
    Service --> B["Bobby adapter"]
    Service --> DB["SQLite + FTS5"]
    Service --> Uploads["Managed local uploads"]
    Service --> Tasks["In-process digest tasks"]
```

The compiled Vite frontend is served by FastAPI for a one-process local deployment. SQLite stores sessions, messages, rounds, documents, jobs, and append-only digest history. Full implementation details are in [docs/SYSTEM-SUMMARY.md](docs/SYSTEM-SUMMARY.md).

## Requirements

- Python 3.11 or newer
- Node.js 20.19+ or 22.12+
- pnpm 9+ recommended
- One or two provider credentials (OpenAI-compatible or Anthropic)
- PyMuPDF and pdfplumber installed for PDF table/figure handling

The two participants may use the same server during development, but separate configurations are supported.

## Quick start on Windows

From the project root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
Copy-Item .env.example .env.local
# Edit .env.local and add provider settings and key environment-variable names.
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Interactive API documentation is available at [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs).

Never place a real credential in `.env.example` or commit `.env.local`.

## Provider configuration

`.env.local` can configure each participant independently:

```dotenv
# Add secrets only in your ignored local copy.
OPENAI_API_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=

MOMO_BASE_URL=https://api.openai.com/v1
MOMO_MODEL=your-momo-model-id
MOMO_API_STYLE=responses
MOMO_API_KEY_ENV=OPENAI_API_KEY
MOMO_REASONING_EFFORT=low
MOMO_LIVE_MAX_OUTPUT_TOKENS=800

BOBBY_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
BOBBY_MODEL=gemini-3.5-flash-lite
BOBBY_API_STYLE=chat_completions
BOBBY_API_KEY_ENV=GEMINI_API_KEY
BOBBY_REASONING_EFFORT=minimal
BOBBY_LIVE_MAX_OUTPUT_TOKENS=1400
BOBBY_CONNECT_TIMEOUT_SECONDS=15
BOBBY_FIRST_TOKEN_TIMEOUT_SECONDS=60
BOBBY_STREAM_IDLE_TIMEOUT_SECONDS=60
BOBBY_TOTAL_TIMEOUT_SECONDS=360

# Gemini completion ceilings include hidden thinking plus visible text.
GEMINI_FAST_MIN_OUTPUT_TOKENS=4096
GEMINI_RESEARCH_MIN_OUTPUT_TOKENS=12288
GEMINI_VERIFICATION_MIN_OUTPUT_TOKENS=32768
GEMINI_MAX_OUTPUT_TOKENS=65536
GEMINI_RESEARCH_TIMEOUT_MULTIPLIER=2.0
GEMINI_VERIFICATION_TIMEOUT_MULTIPLIER=2.25
LIVE_TIMEOUT_RETRY_ATTEMPTS=1
LIVE_TIMEOUT_RETRY_MULTIPLIER=1.5

# Optional alternative for Bobby (disabled until selected)
# BOBBY_BASE_URL=https://api.anthropic.com/v1
# BOBBY_MODEL=claude-3-5-haiku-20241022
# BOBBY_API_STYLE=anthropic_messages
# BOBBY_API_KEY_ENV=ANTHROPIC_API_KEY

# Longer limits apply to medium-reasoning background synthesis.
DIGEST_PROVIDER=momo
FINAL_SUMMARY_MAX_OUTPUT_TOKENS=6000
DIGEST_SECTION_TIMEOUT_SECONDS=300
DIGEST_JOB_TIMEOUT_SECONDS=900
RESEARCH_LIVE_TOKEN_MULTIPLIER=2.75
RESEARCH_LIVE_TIMEOUT_MULTIPLIER=2.5
```

`MOMO_API_KEY_ENV` and `BOBBY_API_KEY_ENV` contain the **names** of environment variables, not the secrets themselves.
Supported API styles are `responses`, `chat_completions`, and `anthropic_messages`.

Reasoning is task-aware. Fast Bobby uses Gemini's `minimal` effort for responsiveness; Research uses medium reasoning, while Verification uses high reasoning and is also activated for an explicit request to check the original source. The UI keeps visible turns concise even when the model allowance grows. Source, topic, conversation, final-summary, and learning-evaluation requests use larger background budgets. Momo uses an 800-token base live allowance. Bobby retains a 1,400-token visible-response basis, but Gemini requests receive minimum completion ceilings of 4,096 / 12,288 / 32,768 for Fast / Research / Verification, capped at 65,536. Those ceilings reserve space for provider-hidden thinking and do not instruct Bobby to produce longer prose. Fast has a 90-second effective first-token deadline and nine-minute total-turn ceiling; Research and Verification use approximately 300- and 338-second first-token deadlines with 30- and 33.75-minute total ceilings. A timeout triggers one automatic retry with a 1.5× retry-only deadline. The transcript immediately shows a temporary System retry notice, clears any incomplete visible attempt, and never saves that notice into history or digests. If the same AI times out again, the System card names the other AI, removes the failed draft, and instructs the other AI to take over from the retained context without claiming to know the missing answer. The floor returns to Sam only if that fallback participant also exhausts its retry. A Chat Completions `finish_reason` of `length` remains an interrupted response rather than silent success.

The provider health endpoint reports each provider's configured Fast/base model. The conversation UI combines that health information with the selected profile catalog and live SSE route metadata, so its active labels show the model that is selected or actually used for the current segment. Each AI message also preserves the actual route in its stored metadata.

### Conversation profiles

The default `.env.example` includes separate model and reasoning settings for the profiles:

- **Fast discussion:** current provider defaults; Bobby uses minimal reasoning, the shortest initial deadline, and one timeout-only retry.
- **Research mode:** GPT-5.6 Sol for Momo and Gemini 3.6 Flash for Bobby by default, medium reasoning, 2.75× live token allowances and 2.5× live deadlines. Bobby additionally receives the 12,288-token Gemini completion floor and 2× Gemini latency margin. Each AI is asked for a focused 140–220-word contribution in two connected paragraphs, including the relevant inferential, methodological, statistical, mathematical, or theoretical detail.
- **Verification mode:** GPT-5.6 Sol for Momo and the provider-maintained `gemini-pro-latest` route for Bobby by default, high reasoning, approximately 2× live allowances and 2.5× live deadlines. Bobby additionally receives the 32,768-token Gemini completion floor and 2.25× Gemini latency margin. Raw PDF/document excerpts are still withheld unless Sam explicitly asks to check the original source.

The Bobby defaults deliberately separate workloads: Gemini 3.5 Flash-Lite favors interactive latency, Gemini 3.6 Flash provides the normal deep-research balance, and `gemini-pro-latest` is reserved for slower source verification. The provider currently rejects `gemini-2.5-pro` for new users even when it appears in `/models`, so the maintained Pro alias is the safer default. Existing installations with explicit model variables keep those overrides; update or remove the three Bobby model variables to adopt this routing.

Gemini thinking is not free or fully visible: thought tokens count toward billed output. The protected ceilings prevent premature truncation, while `reasoning_effort` remains the actual cost/latency control. Keep Fast on minimal, Research on medium, and use high Verification selectively.

Use Research or Verification for derivations, statistical model comparisons, sensitivity analysis, disputed claims, or source checks. For numerical work, add a calculator/Python/R verification step; model reasoning does not replace deterministic computation.

### Conversation language

The session stores a canonical conversation language and how it was selected. English is the source-processing default; a strongly detected non-English uploaded source may set another language when Sam has not chosen one. Sam can change it at any time with a direct instruction such as “continue in Spanish,” “output in Japanese,” or “请用中文回答”; this explicit choice cannot later be overwritten by another document and governs every later synthesis task even when the source itself is in another language.

A constrained `<output_language>` instruction is placed first in every participant, source-digest, Topic Digest, Conversation Digest, final-summary, and one-page-summary system prompt, and each live-turn user context repeats the current language requirement. Visible prose and summary values must use the selected language, while JSON field names, formulas, proper nouns, and exact quotations remain stable. An actual mid-session language change queues one deduplicated Topic Digest refresh so the visible topic framing follows Sam's choice; later Conversation and closeout digests inherit the same language. Automatic detection is deliberately conservative and may require Sam's explicit instruction for mixed-language, closely related Latin-language, or poor-OCR documents.

Natural language controls include “let's talk in English,” “let's discuss in German,” “change the conversation language to French,” “switch to Japanese for the rest,” and “continue in Spanish.” Ordinary topical mentions such as “the Chinese cohort” are not treated as a language switch.

Check connectivity without displaying credentials:

```powershell
.\.venv\Scripts\python.exe .\scripts\check_providers.py
```

For an opt-in, end-to-end comparison of all three profiles with an approved local paper:

```powershell
.\.venv\Scripts\python.exe .\scripts\simulate_reasoning_profiles.py --pdf "C:\path\to\approved-paper.pdf" --rounds 2
```

This live script consumes provider capacity, reports actual model/reasoning routing plus latency and output size, and leaves the session open for inspection. It is not run by CI. See [docs/INDEPENDENT-AUDIT.md](docs/INDEPENDENT-AUDIT.md) for the recorded cognitive-trajectories simulation.

## Development

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Set-Location frontend
pnpm install --frozen-lockfile
Set-Location ..
```

After backend startup, verify PDF library health:

```powershell
curl http://127.0.0.1:8765/api/documents/dependencies
```

Run the backend:

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8765
```

Run the frontend in a second terminal:

```powershell
Set-Location frontend
pnpm dev
```

The Vite server proxies `/api` to FastAPI.

## Restarting or force-closing the local server

If the page stops responding, the API appears stuck, or a new server cannot bind to port `8765`, restart Uvicorn from the project root. A server restart does **not** purge the local session, transcript, digests, source records, or uploaded files. After the server is back, reload the page; the saved roundtable will be restored and Sam can continue from the last persisted turn. A provider call that was actively streaming when the process stopped is not resumed byte-for-byte, but its saved history remains intact and the session is reconciled to a safe state.

Try a normal `Ctrl+C` in the server terminal first. If the process is unresponsive, force-close only the process listening on port `8765`:

```powershell
$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
$listener.OwningProcess | Sort-Object -Unique | ForEach-Object {
    Stop-Process -Id $_ -Force
}
```

Then start the server again:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

If PowerShell cannot find the listener, use Command Prompt:

```cmd
netstat -ano | findstr :8765
taskkill /PID <PID> /F
```

Replace `<PID>` with the process ID shown by `netstat`. Do not terminate every `python.exe` process, because other applications may be using Python. Restarting is different from **Start a new roundtable**: only the latter intentionally purges the retained session after Sam confirms.

## Verification

Backend tests:

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Frontend production build:

```powershell
Set-Location frontend
pnpm build
```

Optional live-provider smoke test (uses API capacity):

```powershell
.\.venv\Scripts\python.exe .\scripts\smoke_generation.py
.\.venv\Scripts\python.exe .\scripts\smoke_generation.py --participant Bobby
```

The current deterministic backend suite contains 91 passing tests; the frontend suite contains 10 passing tests and the production build is verified. The built-in learning-quality workflow and optional developer comparison tools are documented in [docs/LEARNING-QUALITY-EVALUATION.md](docs/LEARNING-QUALITY-EVALUATION.md). See [docs/CRITICAL-REVIEW.md](docs/CRITICAL-REVIEW.md) for the prioritized agent-system review and [docs/INDEPENDENT-AUDIT.md](docs/INDEPENDENT-AUDIT.md) for the broader audit.

## Conversation memory

Every ordinary live turn receives all four continuity layers—processed document digest, Topic Digest, latest Conversation Digest, and the five most recent completed rounds—along with the active question and participant instructions:

1. The participant persona and concise academic-conversation protocol
2. Sam's latest direction and the active question
3. The Topic Digest
4. Only the most recent Conversation Digest
5. The five most recent complete rounds, including relevant Sam interventions
6. The processed document digest, when an uploaded source is available

The complete transcript and all prior digest versions remain in SQLite. They are used for the final summary and exports but are not repeatedly sent to providers during live discussion.

Raw PDF/document passages are not included in ordinary rounds. If Sam explicitly asks to “check the original source,” “check the original PDF/document,” or otherwise verify a claim against the uploaded material, the next AI segment retrieves up to five relevant indexed passages and sends them as clearly labeled, untrusted original-source excerpts. That verification segment uses the enlarged source-processing token and timeout multipliers. A later Continue action returns to digest-only context unless Sam makes another verification request.

## Session lifecycle and retention

The application intentionally retains one session at a time. Both the interface and direct API creation require explicit reset whenever any prior session record exists, including a closed one:

1. Sam concludes the current session; the active stream is cancelled and the record closes without starting a provider call.
2. The closeout page offers Research (default) and Verification summary modes. Sam may ignore this option and proceed directly to downloads or the next table.
3. If Sam requests synthesis, a blue progress message shows Momo writing the comprehensive Summary Digest and Bobby independently writing the one-page learning summary from the same frozen materials. The shared bounded bundle includes extracted source text with provenance labels, processed source digests, the Topic Digest, all Conversation Digests, and the complete substantive transcript; it excludes uploaded binary files. Both provider calls use the selected mode, run concurrently, and may be cancelled together.
4. Once both jobs settle, the closeout page presents the complete archive, readable transcript, one-page summary, and comprehensive Summary Digest downloads, followed by the optional learning-evaluation control. Either summary has its own digest-based fallback, so one slow or failed provider does not erase the other artifact. The Summary Digest is synthesis-only; download the archive to retain the Topic, source, current Conversation, and historical digest records.
5. Sam may complete and save the built-in learning evaluation; subsequent downloads include it.
6. If the record has not been saved—or the summary was skipped—the app asks whether Sam wants to stay for optional save/evaluation work.
7. Selecting **No, start new roundtable** immediately clears prior database history, evaluation, FTS passages, and managed uploads before showing the new-table form.

Download the ZIP archive before starting a new session if the source files and full record should be kept.

## Runtime data

Default local state lives under `data/`:

```text
data/
├── roundtable.sqlite3
└── uploads/
```

Runtime data, uploads, databases, environment files, logs, dependency directories, and build outputs are ignored by Git.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Application and provider health |
| `GET` | `/api/meta` | Runtime metadata, profile catalog, and PDF dependency summary |
| `GET` | `/api/documents/dependencies` | Confirm PDF extraction dependencies (`pymupdf`, `pdfplumber`) |
| `GET/POST` | `/api/sessions` | List or create the single retained session |
| `GET/PATCH` | `/api/sessions/{id}` | Read or update session settings |
| `POST` | `/api/sessions/{id}/messages` | Add Sam's message and determine the next action |
| `POST` | `/api/sessions/{id}/voice-transcription` | Transcribe a temporary Sam recording into an editable topic-aware draft |
| `POST` | `/api/sessions/{id}/segments` | Stream a bounded AI segment over SSE |
| `POST` | `/api/sessions/{id}/interrupt` | Interrupt active generation |
| `POST` | `/api/sessions/{id}/recap` | Request a conversation digest |
| `POST` | `/api/sessions/{id}/documents` | Upload and schedule source digestion |
| `POST` | `/api/sessions/{id}/close` | End immediately without starting synthesis |
| `POST` | `/api/sessions/{id}/final-summary` | Explicitly start Research or Verification closeout summaries |
| `POST` | `/api/sessions/{id}/final-summary/cancel` | Cancel active closeout summary work |
| `GET` | `/api/sessions/{id}/jobs` | Inspect session background jobs |
| `GET/PUT` | `/api/sessions/{id}/learning-evaluation` | Open or save the session-scoped learning evaluation |
| `GET` | `/api/sessions/{id}/export` | Download transcript Markdown, Summary Digest, one-page summary, structured JSON, or ZIP after closure |

## Project structure

```text
academic-roundtable/
├── backend/
│   ├── app/                 # API, orchestration, adapters, prompts, DB, documents
│   └── tests/               # deterministic backend tests
├── docs/
│   ├── SYSTEM-SUMMARY.md
│   ├── IMPLEMENTATION-PLAN.md
│   ├── INDEPENDENT-AUDIT.md
│   ├── CRITICAL-REVIEW.md
│   ├── LEARNING-QUALITY-EVALUATION.md
│   ├── DEVELOPMENT.md
│   └── GITHUB-RELEASE-CHECKLIST.md
├── evaluation/
│   └── fixtures/            # repeatable learning-quality pilot scenarios
├── frontend/
│   ├── public/              # logo
│   └── src/                 # React UI and API client
├── scripts/                 # setup, provider check, live smoke test
├── .github/workflows/       # backend, frontend, and secret-tracking CI checks
├── CONTRIBUTING.md
├── SECURITY.md
├── .env.example
├── requirements.txt
└── run.ps1
```

## Security and privacy

The local MVP keeps credentials server-side, omits internal upload paths from public API objects, validates managed-file paths before deletion/archive, and treats uploaded text as untrusted evidence. It does not print API keys during its provider check.

This is not sufficient for public hosting. Before remote deployment, add authentication and authorization, per-user isolation, request and rate limits, malware scanning, stricter file validation, HTTPS, secure secret management, security headers, monitoring, and a retention policy.

Before publishing the repository, run a secret scan over both the working tree and Git history.

## Current limitations

- Single local user and one retained session
- No automatic restart/resume for interrupted background jobs
- One timeout-only retry and cross-participant handoff are implemented; there is no general provider circuit breaker or durable retry queue
- FTS5 lexical retrieval only
- No OCR for scanned image-only PDFs
- English-pattern detection for recap and closing intents
- No formal claim graph, scoring dashboard, continuous/realtime voice conversation, or autonomous web research
- No license selected yet; choose one before public distribution or outside contributions

## Sam voice input

Voice input uses the configured OpenAI transcription endpoint with `gpt-4o-mini-transcribe` by default. The browser has no recording-time cutoff: Sam can speak for three minutes, five minutes, or longer and stops the recording manually. The in-memory recording is uploaded only after Sam stops. The transcription prompt includes the roundtable topic, active question, and key academic terms so obvious terminology and spelling errors can be corrected without summarizing or strengthening Sam's claims. The returned text is never submitted automatically: Sam reviews and edits it in the normal composer, then selects **Answer**. A provider-compatible audio-size safeguard remains necessary for a single upload; if reached, the captured portion is stopped and transcribed rather than discarded.

The recording is sent to OpenAI for transcription and is not written to the roundtable database, upload directory, transcript, exports, or archive. Only the edited text Sam submits becomes session history. Voice-derived or otherwise long Sam comments may contain up to 24,000 characters and receive 1.5× response-token room, 1.75× first-token/stream-idle/total-turn time, and a larger recent-turn context slot throughout the complete AI segment; visible AI turns remain governed by the concise conversation prompt. Natural-language recaps require an explicit conversational command, so topical phrases such as “statistical summary” do not divert the turn into recap generation.

The prioritized next increments are in [docs/IMPLEMENTATION-PLAN.md](docs/IMPLEMENTATION-PLAN.md). Repository preparation steps are in [docs/GITHUB-RELEASE-CHECKLIST.md](docs/GITHUB-RELEASE-CHECKLIST.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [development and testing guide](docs/DEVELOPMENT.md). Security reports should follow [SECURITY.md](SECURITY.md).

Before proposing a change:

1. Keep the conversation-first interface and human-control guarantees intact.
2. Add deterministic coverage for scheduler, lifecycle, persistence, or API behavior changes.
3. Run backend tests and the frontend production build.
4. Do not commit credentials, transcripts, uploaded sources, runtime databases, or generated build artifacts.
5. Update the system summary when behavior or architecture changes.

## License

No license has been selected yet. Add an explicit license before distributing the project publicly or accepting external contributions.
