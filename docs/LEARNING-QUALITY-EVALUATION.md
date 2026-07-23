<p align="center">
  <img src="../frontend/public/academic-roundtable-logo.png" alt="Academic Roundtable logo" width="150">
</p>

> Canonical source: This is the active `academic-roundtable-github-ready` workspace.
> The sibling `academic-roundtable/` folder is archived and not for new development.

# Learning-Quality Evaluation Process

## Purpose

The harness tests whether Academic Roundtable is delivering its governing outcome: **deep conversations for better learning**. It is designed for lean prompt and orchestration experiments, not for ranking models in the abstract.

The session now supports three model profiles: **Fast** (the latency baseline), **Research** (Luna `xhigh` for Momo and Gemini 3.6 Flash `medium` for common deeper exploration), and **Verification** (Sol `high` and Gemini `high` for methodological checking with longer deadlines). Treat the profile as an experimental factor: compare profiles on the same fixture, topic, source policy, and rounds, and record latency and visible word count alongside learning ratings. Do not interpret a larger token allowance or higher reasoning setting as evidence of better learning.

The process deliberately separates two kinds of evidence:

1. **Automated diagnostics** detect observable risks such as excessive turn length, high lexical repetition, unbounded AI-only stretches, weak response engagement, and poor digest term coverage.
2. **Sam/reviewer ratings** judge the qualities that require human understanding: intellectual progress, reasoning, host control, summary fidelity, and actual learning value.

Automated values are proxies and quality gates. They must never be reported as proof that learning occurred.

## Included assets

- `backend/app/evaluation.py`: deterministic analysis, rubric validation, reporting, and comparison logic
- `scripts/evaluate_learning.py`: command-line workflow
- `evaluation/fixtures/learning-pilot.json`: ten representative learning scenarios
- `evaluation/results/`: ignored working directory for session reports and ratings

The evaluator makes no provider calls and does not expose API keys. Ordinary users complete it directly on the session closeout page. The command-line tool remains available for developers running controlled baseline/candidate comparisons over downloaded JSON.

## Built-in session workflow

1. End the roundtable.
2. Follow the blue progress notice while the final and one-page summaries are generated, or cancel summary processing if it is not wanted.
3. When the session reaches its closed state, review the save/download row.
4. Select **Evaluate learning** immediately below that row.
5. Score any or all eight dimensions and add brief conversation evidence.
6. Add reflections and select **Save evaluation**.
7. Download or re-download Markdown, structured JSON, or the complete ZIP archive. The saved evaluation is included in every format.

The evaluation belongs only to the current session. Starting a new roundtable permanently clears it with that session's transcript, digests, and managed uploads. There is intentionally no cross-session evaluation-history page in the current release.

## Human rubric

Each dimension is scored from 1 to 5 and requires brief transcript evidence.

| Score | Anchor |
|---:|---|
| 1 | Counterproductive: confused, obstructed, or materially misled learning |
| 2 | Weak: occasional value, but important failures dominate |
| 3 | Adequate: useful and basically sound, with noticeable limitations |
| 4 | Strong: consistently advances understanding with minor limitations |
| 5 | Exceptional: unusually clear, responsive, rigorous, and valuable |

Dimensions and weights:

| Dimension | Weight | What to judge |
|---|---:|---|
| Focus and relevance | 1.00 | Alignment with the topic and Sam's latest direction |
| Responsive engagement | 1.00 | Engagement with the preceding argument rather than parallel monologues |
| Intellectual progress | 1.25 | New mechanisms, challenges, connections, resolutions, or better questions |
| Reasoning and uncertainty | 1.00 | Assumptions, evidence, inference, uncertainty, and provenance |
| Concision and readability | 1.00 | Ability to follow the exchange at conversational speed |
| Sam's agency | 1.00 | Effective redirection, interruption, continuation, and judgment |
| Recap fidelity | 0.75 | Preservation of positions, disagreement, evidence, and open questions |
| Learning value | 1.50 | Clearer concepts, improved judgment, or more productive questions |

## Small experiment workflow

### 1. State one hypothesis

Change one prompt or orchestration behavior and predict an observable result. Example: “Requiring the second speaker to identify one boundary condition will improve responsive engagement and intellectual progress without reducing readability.” Do not bundle prompt, model, token budget, and scheduler changes into one experiment.

### 2. Select fixtures

Use three fixtures for a quick iteration and all ten before accepting a material behavior change. Always include:

- one conceptual or theoretical fixture;
- one evidence/methods fixture;
- the host-redirection or recap-fidelity fixture.

For source-grounded testing, upload the same document in baseline and candidate runs.

### 3. Control the comparison

- Keep provider, model, source files, rounds per segment, and source policy identical.
- Run baseline and candidate close together to reduce provider drift.
- For an important decision, run each selected fixture at least twice because generation is stochastic.
- Save the exact code revision and a short change description alongside the reports.
- Label runs A and B for the reviewer when feasible so the reviewer does not know which is the candidate.

### 4. Evaluate the session

Use the built-in closeout form for ordinary evaluation. The remaining commands are optional development tools for repeatable A/B experiments. Download the structured session JSON and run:

```powershell
python scripts\evaluate_learning.py evaluate C:\path\to\session.json --label fixture-a-baseline
```

The command creates:

- `fixture-a-baseline.evaluation.json`: machine-readable diagnostics;
- `fixture-a-baseline.evaluation.md`: readable report;
- `fixture-a-baseline.ratings.json`: blank human worksheet.

Fill scores and transcript evidence in the ratings JSON, then rerun:

```powershell
python scripts\evaluate_learning.py evaluate C:\path\to\session.json `
  --label fixture-a-baseline `
  --ratings evaluation\results\fixture-a-baseline.ratings.json
```

Repeat for the candidate, then compare:

```powershell
python scripts\evaluate_learning.py compare `
  evaluation\results\fixture-a-baseline.evaluation.json `
  evaluation\results\fixture-a-candidate.evaluation.json `
  --output evaluation\results\fixture-a-comparison.json
```

The comparison command also writes a readable Markdown report.

### 5. Apply the promotion gate

The harness marks a candidate `candidate_supported` only when:

- baseline and candidate human rubrics are complete;
- the weighted human score improves by at least 0.15 points;
- focus, readability, Sam's agency, and learning value do not regress;
- no deterministic quality gate warns.

This is a review threshold, not an automatic deployment decision. Inspect the cited transcript evidence and results across fixtures. If results are mixed, keep the current behavior, narrow the hypothesis, and run another small experiment.

## Interpreting automated diagnostics

- **Target length rate:** share of AI turns within the selected profile target: 60–110 words for Fast and 140–220 words for Research. Profile-aware scoring is required when comparing modes.
- **Readable-limit rate:** share of AI turns below the profile's readability ceiling; do not apply the Fast 130-word ceiling to Research turns.
- **Engagement proxy:** a conservative lexical/stance signal that a reply addresses the preceding turn. It can miss semantically strong engagement and should be checked against the transcript.
- **Repetition proxy:** adjacent AI turns with unusually high content-word overlap.
- **Maximum consecutive AI turns:** checks the five-round human-floor boundary.
- **Digest salient-term coverage:** checks whether common discussion concepts survive into the latest/final digest. It does not establish factual fidelity.
- **Epistemic labels:** counts explicit background-knowledge, inference, speculation, and source-evidence labels; more labels are not automatically better.
- **Language consistency:** for multilingual fixtures, inspect whether both participants, recaps, and final synthesis remain in the persisted conversation language while preserving formulas, proper nouns, and exact source quotations. Treat unintended language switching as a quality failure.

## Review cadence

- **During prompt tuning:** three fixtures, one or two repetitions, one reviewer.
- **Before merging a material behavior change:** all ten fixtures, two repetitions, blinded A/B order where feasible.
- **Before a public pilot:** add a second reviewer to at least 20% of sessions and discuss rating disagreements rather than mechanically averaging them.
- **After release:** sample real consenting sessions and add anonymized failure patterns to the fixture set. Do not retain personal transcripts merely for evaluation convenience.

## Intentionally postponed

An LLM-as-judge step is not part of the first harness. It would add cost and can reward the same stylistic patterns used by the participating models. If manual review becomes the bottleneck, a separately configured blinded judge can be added as a secondary triage signal, calibrated against Sam's ratings and never used as the sole promotion criterion.
