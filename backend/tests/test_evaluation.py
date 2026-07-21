from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import Database
from app.evaluation import analyze_session, apply_human_ratings, compare_reports, rating_template


def session_fixture() -> dict:
    momo = " ".join(
        ["Momo argues that mechanism and context clarify the causal claim"] * 7
    )
    bobby = " ".join(
        ["I partly disagree with Momo because an alternative explanation remains plausible"] * 7
    )
    return {
        "id": "ses_eval",
        "topic": "Causal explanation",
        "learning_goal": "Compare mechanisms and alternatives",
        "completed_rounds": 1,
        "messages": [
            {"speaker": "Momo", "content": "Hello", "metadata": {"kind": "greeting"}},
            {"speaker": "Sam", "content": "Start with the central mechanism.", "metadata": {}},
            {"speaker": "Momo", "content": momo, "metadata": {}},
            {"speaker": "Bobby", "content": bobby, "metadata": {}},
        ],
        "conversation_digest": {"visible_recap": "Mechanism, context, and an alternative explanation remain central."},
        "summary_history": [],
    }


def test_learning_diagnostics_exclude_greetings_and_measure_engagement() -> None:
    report = analyze_session(session_fixture())
    metrics = report["automated_diagnostics"]
    assert metrics["substantive_messages"] == 3
    assert metrics["ai_turns"] == 2
    assert metrics["sam_turns"] == 1
    assert metrics["engagement_proxy_rate"] == 1.0
    assert metrics["target_length_rate"] == 1.0
    assert report["quality_gates"]["readable_turns"]["status"] == "pass"


def test_repetition_proxy_warns_without_claiming_a_learning_score() -> None:
    session = session_fixture()
    repeated = "The same causal mechanism depends on shared contextual assumptions and measured evidence. " * 6
    session["messages"][2]["content"] = repeated
    session["messages"][3]["content"] = repeated
    report = analyze_session(session)
    assert report["automated_diagnostics"]["repetition_proxy_rate"] == 1.0
    assert "low_repetition" in report["warnings"]
    assert "not scores of learning quality" in report["interpretation_note"]


def test_human_rubric_requires_valid_scores_and_computes_weighted_result() -> None:
    session = session_fixture()
    ratings = rating_template(session)
    ratings["reviewer"] = "Sam"
    for entry in ratings["ratings"].values():
        entry["score"] = 4
        entry["evidence"] = "The transcript contains a concrete example."
    report = apply_human_ratings(analyze_session(session), ratings)
    assert report["human_review"]["weighted_score"] == 4.0
    assert report["human_review"]["completion_rate"] == 1.0

    ratings["ratings"]["learning_value"]["score"] = 6
    with pytest.raises(ValueError, match="between 1 and 5"):
        apply_human_ratings(analyze_session(session), ratings)


def test_comparison_requires_human_improvement_and_clean_gates() -> None:
    baseline = analyze_session(session_fixture())
    candidate = analyze_session(session_fixture())
    base_ratings = rating_template(session_fixture())
    candidate_ratings = rating_template(session_fixture())
    for entry in base_ratings["ratings"].values():
        entry["score"] = 3
    for entry in candidate_ratings["ratings"].values():
        entry["score"] = 4
    baseline = apply_human_ratings(baseline, base_ratings)
    candidate = apply_human_ratings(candidate, candidate_ratings)
    comparison = compare_reports(baseline, candidate)
    assert comparison["human_weighted_score"]["delta"] == 1.0
    assert comparison["decision"] == "candidate_supported"


def test_learning_evaluation_is_session_scoped_and_purged(tmp_path) -> None:
    database = Database(tmp_path / "evaluation.sqlite3")
    database.initialize()
    session = database.create_session("Bias", "Improve causal judgment", 3, False, True)
    report = analyze_session({**session, "messages": [], "summary_history": []})
    ratings = rating_template(session)
    saved = database.save_learning_evaluation(session["id"], report, ratings)
    assert saved["report"]["session"]["id"] == session["id"]
    assert saved["ratings"]["session_id"] == session["id"]

    database.purge_all_sessions()
    assert database.get_learning_evaluation(session["id"]) is None


def test_learning_evaluation_api_is_closeout_only_and_exported(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    database = Database(tmp_path / "evaluation-api.sqlite3")
    database.initialize()
    monkeypatch.setattr(main_module, "database", database)
    monkeypatch.setattr(main_module.service, "db", database)
    session = database.create_session("Selection bias", "Improve study judgment", 3, False, True)
    database.add_message(session["id"], "Sam", "How does selection affect the estimate?")
    database.add_message(session["id"], "Momo", "Selection can induce a noncausal association.")
    client = TestClient(main_module.app)

    assert client.get(f"/api/sessions/{session['id']}/learning-evaluation").status_code == 409
    database.update_session(session["id"], state="CLOSED")
    bundle = client.get(f"/api/sessions/{session['id']}/learning-evaluation").json()
    ratings = bundle["ratings"]
    for entry in ratings["ratings"].values():
        entry["score"] = 4
        entry["evidence"] = "The exchange clarified the causal problem."
    saved = client.put(
        f"/api/sessions/{session['id']}/learning-evaluation", json=ratings
    )
    assert saved.status_code == 200
    assert saved.json()["report"]["human_review"]["weighted_score"] == 4.0

    exported = client.get(f"/api/sessions/{session['id']}/export?format=json").json()
    assert exported["learning_evaluation"]["ratings"]["ratings"]["learning_value"]["score"] == 4
    markdown = client.get(f"/api/sessions/{session['id']}/export?format=markdown").text
    assert "Learning-Quality Evaluation" in markdown
