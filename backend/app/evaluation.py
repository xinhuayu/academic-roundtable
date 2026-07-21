from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
EXCLUDED_KINDS = {"greeting", "session_opening", "recap", "final_summary", "closing"}
AI_SPEAKERS = {"Momo", "Bobby"}
STOPWORDS = {
    "about", "after", "again", "also", "because", "been", "before", "being", "between",
    "both", "could", "does", "from", "have", "into", "more", "most", "other", "should",
    "some", "such", "than", "that", "their", "there", "these", "they", "this", "through",
    "under", "very", "what", "when", "where", "which", "while", "with", "would", "your",
}

RUBRIC: dict[str, dict[str, Any]] = {
    "focus": {
        "label": "Focus and relevance",
        "weight": 1.0,
        "question": "Did the discussion remain aligned with Sam's topic and latest direction?",
    },
    "responsive_engagement": {
        "label": "Responsive engagement",
        "weight": 1.0,
        "question": "Did each AI engage the preceding claim rather than deliver a parallel monologue?",
    },
    "intellectual_progress": {
        "label": "Intellectual progress",
        "weight": 1.25,
        "question": "Did successive turns deepen, challenge, connect, or resolve the inquiry?",
    },
    "reasoning_and_uncertainty": {
        "label": "Reasoning and uncertainty",
        "weight": 1.0,
        "question": "Were mechanisms, assumptions, evidence, inference, and uncertainty handled carefully?",
    },
    "readability": {
        "label": "Concision and readability",
        "weight": 1.0,
        "question": "Could Sam follow the exchange at conversational speed without losing important reasoning?",
    },
    "host_agency": {
        "label": "Sam's agency",
        "weight": 1.0,
        "question": "Could Sam redirect, interrupt, continue, and shape the intellectual path effectively?",
    },
    "recap_fidelity": {
        "label": "Recap fidelity",
        "weight": 0.75,
        "question": "Did summaries preserve positions, disagreements, evidence, and unresolved questions?",
    },
    "learning_value": {
        "label": "Learning value",
        "weight": 1.5,
        "question": "Did Sam leave with clearer concepts, better questions, or improved judgment?",
    },
}


def words(text: str) -> list[str]:
    return [item.lower() for item in WORD_RE.findall(text or "")]


def content_terms(text: str) -> set[str]:
    return {item for item in words(text) if len(item) > 3 and item not in STOPWORDS}


def _kind(message: dict[str, Any]) -> str:
    metadata = message.get("metadata") or {}
    return metadata.get("kind", "") if isinstance(metadata, dict) else ""


def substantive_messages(session: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in session.get("messages", [])
        if item.get("content") and _kind(item) not in EXCLUDED_KINDS
    ]


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _digest_text(session: dict[str, Any]) -> str:
    history = session.get("summary_history") or []
    final = next((item.get("digest") for item in reversed(history) if item.get("kind") == "final"), None)
    digest = final or session.get("conversation_digest") or {}
    if isinstance(digest, str):
        return digest
    return json.dumps(digest, ensure_ascii=False)


def _digest_coverage(messages: list[dict[str, Any]], digest_text: str) -> float | None:
    if not digest_text:
        return None
    source_counts: Counter[str] = Counter()
    for message in messages:
        source_counts.update(content_terms(message.get("content", "")))
    salient = {term for term, _ in source_counts.most_common(30)}
    if not salient:
        return None
    return round(len(salient & content_terms(digest_text)) / len(salient), 3)


def analyze_session(session: dict[str, Any]) -> dict[str, Any]:
    messages = substantive_messages(session)
    ai_messages = [item for item in messages if item.get("speaker") in AI_SPEAKERS]
    sam_messages = [item for item in messages if item.get("speaker") == "Sam"]
    lengths = [len(words(item.get("content", ""))) for item in ai_messages]

    engaged = 0
    eligible_engagement = 0
    repeated = 0
    eligible_repetition = 0
    previous: dict[str, Any] | None = None
    for message in messages:
        if message.get("speaker") in AI_SPEAKERS and previous:
            eligible_engagement += 1
            text = message.get("content", "").lower()
            stance = any(marker in text for marker in ("agree", "disagree", "partly", "however", "but "))
            named = str(previous.get("speaker", "")).lower() in text
            overlap = _jaccard(content_terms(text), content_terms(previous.get("content", "")))
            if stance or named or overlap >= 0.08:
                engaged += 1
            if previous.get("speaker") in AI_SPEAKERS:
                eligible_repetition += 1
                if overlap >= 0.65:
                    repeated += 1
        previous = message

    max_ai_streak = 0
    current_streak = 0
    for message in messages:
        if message.get("speaker") in AI_SPEAKERS:
            current_streak += 1
            max_ai_streak = max(max_ai_streak, current_streak)
        elif message.get("speaker") == "Sam":
            current_streak = 0

    ai_text = "\n".join(item.get("content", "") for item in ai_messages)
    label_counts = {
        "background_knowledge": len(re.findall(r"\bbackground knowledge\b", ai_text, re.I)),
        "inference": len(re.findall(r"\binference\b", ai_text, re.I)),
        "speculation": len(re.findall(r"\bspeculation\b", ai_text, re.I)),
        "source_evidence": len(re.findall(r"\b(source|document) evidence\b", ai_text, re.I)),
    }
    invitations = sum(
        1 for item in ai_messages
        if re.search(r"\bSam\b", item.get("content", ""), re.I) and "?" in item.get("content", "")
    )
    concise_target = sum(60 <= length <= 110 for length in lengths)
    readable_limit = sum(length <= 130 for length in lengths)
    digest_coverage = _digest_coverage(messages, _digest_text(session))

    metrics = {
        "substantive_messages": len(messages),
        "ai_turns": len(ai_messages),
        "sam_turns": len(sam_messages),
        "completed_rounds": int(session.get("completed_rounds") or 0),
        "ai_words_mean": round(statistics.mean(lengths), 1) if lengths else 0.0,
        "ai_words_median": round(statistics.median(lengths), 1) if lengths else 0.0,
        "ai_words_max": max(lengths, default=0),
        "target_length_rate": round(concise_target / len(lengths), 3) if lengths else None,
        "under_readable_limit_rate": round(readable_limit / len(lengths), 3) if lengths else None,
        "engagement_proxy_rate": round(engaged / eligible_engagement, 3) if eligible_engagement else None,
        "repetition_proxy_rate": round(repeated / eligible_repetition, 3) if eligible_repetition else None,
        "max_consecutive_ai_turns": max_ai_streak,
        "sam_invitation_count": invitations,
        "digest_salient_term_coverage": digest_coverage,
        "epistemic_label_counts": label_counts,
    }

    gates = {
        "readable_turns": _gate(
            metrics["under_readable_limit_rate"], 0.85, "higher",
            "At least 85% of AI turns are no longer than 130 words.",
        ),
        "extreme_verbosity": _gate(
            metrics["ai_words_max"], 180, "lower_equal",
            "No AI contribution exceeds 180 words.",
        ),
        "low_repetition": _gate(
            metrics["repetition_proxy_rate"], 0.20, "lower_equal",
            "Fewer than 20% of adjacent AI turns have very high lexical overlap.",
        ),
        "bounded_ai_segment": _gate(
            metrics["max_consecutive_ai_turns"], 10, "lower_equal",
            "No more than five two-speaker rounds occur without Sam taking the floor.",
        ),
    }
    warnings = [name for name, gate in gates.items() if gate["status"] == "warn"]
    return {
        "schema_version": 1,
        "session": {
            "id": session.get("id", "unknown"),
            "topic": session.get("topic", ""),
            "learning_goal": session.get("learning_goal", ""),
        },
        "automated_diagnostics": metrics,
        "quality_gates": gates,
        "warnings": warnings,
        "interpretation_note": (
            "Automated diagnostics are proxies for review, not scores of learning quality. "
            "Use the human rubric and cite transcript evidence."
        ),
    }


def _gate(value: float | int | None, threshold: float, direction: str, description: str) -> dict[str, Any]:
    if value is None:
        status = "not_applicable"
    elif direction == "higher":
        status = "pass" if value >= threshold else "warn"
    else:
        status = "pass" if value <= threshold else "warn"
    return {"status": status, "value": value, "threshold": threshold, "description": description}


def rating_template(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "session_id": session.get("id", "unknown"),
        "reviewer": "",
        "ratings": {
            name: {
                "score": None,
                "evidence": "",
                "note": details["question"],
            }
            for name, details in RUBRIC.items()
        },
        "most_valuable_moment": "",
        "most_confusing_moment": "",
        "one_change_for_next_run": "",
        "overall_comment": "",
    }


def apply_human_ratings(report: dict[str, Any], ratings: dict[str, Any]) -> dict[str, Any]:
    scored: dict[str, Any] = {}
    weighted_total = 0.0
    total_weight = 0.0
    for name, details in RUBRIC.items():
        entry = (ratings.get("ratings") or {}).get(name, {})
        raw_score = entry.get("score")
        if raw_score is None:
            score = None
        else:
            score = float(raw_score)
            if not math.isfinite(score) or not 1 <= score <= 5:
                raise ValueError(f"Rating '{name}' must be between 1 and 5")
            weighted_total += score * details["weight"]
            total_weight += details["weight"]
        scored[name] = {
            "label": details["label"],
            "weight": details["weight"],
            "score": score,
            "evidence": str(entry.get("evidence", "")).strip(),
            "note": str(entry.get("note", "")).strip(),
        }
    report = json.loads(json.dumps(report))
    report["human_review"] = {
        "reviewer": str(ratings.get("reviewer", "")).strip(),
        "weighted_score": round(weighted_total / total_weight, 2) if total_weight else None,
        "completion_rate": round(len([v for v in scored.values() if v["score"] is not None]) / len(RUBRIC), 3),
        "ratings": scored,
        "most_valuable_moment": ratings.get("most_valuable_moment", ""),
        "most_confusing_moment": ratings.get("most_confusing_moment", ""),
        "one_change_for_next_run": ratings.get("one_change_for_next_run", ""),
        "overall_comment": ratings.get("overall_comment", ""),
    }
    return report


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    desired = {
        "target_length_rate": "higher",
        "under_readable_limit_rate": "higher",
        "engagement_proxy_rate": "higher",
        "repetition_proxy_rate": "lower",
        "digest_salient_term_coverage": "higher",
        "ai_words_mean": "neutral",
    }
    deltas: dict[str, Any] = {}
    before_metrics = baseline.get("automated_diagnostics", {})
    after_metrics = candidate.get("automated_diagnostics", {})
    for name, direction in desired.items():
        before = before_metrics.get(name)
        after = after_metrics.get(name)
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            continue
        delta = round(after - before, 3)
        if direction == "higher":
            assessment = "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"
        elif direction == "lower":
            assessment = "improved" if delta < 0 else "regressed" if delta > 0 else "unchanged"
        else:
            assessment = "descriptive"
        deltas[name] = {"baseline": before, "candidate": after, "delta": delta, "assessment": assessment}

    human_before = (baseline.get("human_review") or {}).get("weighted_score")
    human_after = (candidate.get("human_review") or {}).get("weighted_score")
    completion_before = (baseline.get("human_review") or {}).get("completion_rate", 0)
    completion_after = (candidate.get("human_review") or {}).get("completion_rate", 0)
    human_delta = None
    if isinstance(human_before, (int, float)) and isinstance(human_after, (int, float)):
        human_delta = round(human_after - human_before, 2)

    dimension_deltas: dict[str, Any] = {}
    critical_regression = False
    before_ratings = (baseline.get("human_review") or {}).get("ratings", {})
    after_ratings = (candidate.get("human_review") or {}).get("ratings", {})
    for name in RUBRIC:
        before = (before_ratings.get(name) or {}).get("score")
        after = (after_ratings.get(name) or {}).get("score")
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = round(after - before, 2)
            dimension_deltas[name] = {"baseline": before, "candidate": after, "delta": delta}
            if name in {"focus", "readability", "host_agency", "learning_value"} and delta < 0:
                critical_regression = True

    candidate_warnings = candidate.get("warnings", [])
    review_complete = completion_before == 1.0 and completion_after == 1.0
    candidate_supported = (
        review_complete
        and human_delta is not None
        and human_delta >= 0.15
        and not critical_regression
        and not candidate_warnings
    )
    return {
        "schema_version": 1,
        "baseline_session": baseline.get("session", {}),
        "candidate_session": candidate.get("session", {}),
        "automated_deltas": deltas,
        "human_weighted_score": {
            "baseline": human_before,
            "candidate": human_after,
            "delta": human_delta,
        },
        "human_dimension_deltas": dimension_deltas,
        "human_review_complete": review_complete,
        "critical_dimension_regression": critical_regression,
        "candidate_gate_warnings": candidate_warnings,
        "decision": "candidate_supported" if candidate_supported else "review_required",
        "decision_note": (
            "A candidate is supported only when both rubrics are complete, the weighted human score improves by "
            "at least 0.15, focus/readability/host agency/learning value do not regress, and no deterministic gate warns. "
            "Otherwise review the transcript and evidence; diagnostics never substitute for Sam's learning judgment."
        ),
    }


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Learning-quality comparison",
        "",
        f"**Decision:** `{comparison.get('decision', 'review_required')}`",
        "",
        comparison.get("decision_note", ""),
        "",
        "## Automated diagnostic changes",
        "",
        "| Diagnostic | Baseline | Candidate | Delta | Assessment |",
        "|---|---:|---:|---:|---|",
    ]
    for name, value in comparison.get("automated_deltas", {}).items():
        lines.append(
            f"| {name.replace('_', ' ').title()} | {value['baseline']} | {value['candidate']} "
            f"| {value['delta']} | {value['assessment']} |"
        )
    human = comparison.get("human_weighted_score", {})
    lines.extend([
        "", "## Human learning judgment", "",
        f"- Baseline: {human.get('baseline')}",
        f"- Candidate: {human.get('candidate')}",
        f"- Delta: {human.get('delta')}",
        f"- Both rubrics complete: {comparison.get('human_review_complete')}",
        f"- Critical dimension regression: {comparison.get('critical_dimension_regression')}",
        "", "## Candidate gate warnings", "",
    ])
    warnings = comparison.get("candidate_gate_warnings") or []
    lines.extend([f"- {item}" for item in warnings] or ["- None"])
    return "\n".join(str(line) for line in lines) + "\n"


def render_report_markdown(report: dict[str, Any]) -> str:
    session = report.get("session", {})
    metrics = report.get("automated_diagnostics", {})
    lines = [
        "# Learning-quality evaluation",
        "",
        f"**Topic:** {session.get('topic', '')}",
        f"**Learning goal:** {session.get('learning_goal', '')}",
        f"**Session:** `{session.get('id', 'unknown')}`",
        "",
        "## Automated diagnostics",
        "",
        "These values are review aids, not learning-quality scores.",
        "",
        "| Diagnostic | Value |",
        "|---|---:|",
    ]
    for name, value in metrics.items():
        display = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
        lines.append(f"| {name.replace('_', ' ').title()} | {display} |")
    lines.extend(["", "## Quality gates", "", "| Gate | Status | Description |", "|---|---|---|"])
    for name, gate in report.get("quality_gates", {}).items():
        lines.append(f"| {name.replace('_', ' ').title()} | {gate['status']} | {gate['description']} |")

    review = report.get("human_review")
    if review:
        lines.extend([
            "", "## Sam/reviewer rubric", "",
            f"**Weighted score:** {review.get('weighted_score')} / 5  ",
            f"**Completion:** {round(100 * review.get('completion_rate', 0))}%", "",
            "| Dimension | Score | Transcript evidence |", "|---|---:|---|",
        ])
        for entry in review.get("ratings", {}).values():
            evidence = str(entry.get("evidence", "")).replace("|", "\\|")
            lines.append(f"| {entry['label']} | {entry.get('score') or '—'} | {evidence} |")
        lines.extend([
            "", "### Reflection", "",
            f"- Most valuable moment: {review.get('most_valuable_moment', '')}",
            f"- Most confusing moment: {review.get('most_confusing_moment', '')}",
            f"- One change for next run: {review.get('one_change_for_next_run', '')}",
            f"- Overall comment: {review.get('overall_comment', '')}",
        ])
    else:
        lines.extend(["", "## Human review", "", "Not completed. Fill the generated ratings template and rerun the evaluator."])
    return "\n".join(str(line) for line in lines) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
