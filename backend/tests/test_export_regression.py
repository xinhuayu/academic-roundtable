from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from app import main as main_module
from app.database import Database


class _NoopService:
    async def interrupt_and_wait(self, *_args: object, **_kwargs: object) -> bool:
        return False

    async def cancel_session_background_tasks(self, *_args: object) -> int:
        return 0

    async def cancel_final_summary(self, *_args: object) -> bool:
        return False


def make_test_client(db: Database, monkeypatch) -> TestClient:
    monkeypatch.setattr(main_module, "database", db)
    monkeypatch.setattr(main_module, "service", _NoopService())  # type: ignore[assignment]
    return TestClient(main_module.app)


def test_one_page_summary_export_is_available_only_after_close(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "export-regression.sqlite3")
    db.initialize()
    session = db.create_session("One-page validation", "Test export gating", 2, False, False)
    db.add_summary_digest(session["id"], "one_page", 2, {"content": "Concise synthesis: topic, evidence, and next steps."})

    client = make_test_client(db, monkeypatch)
    not_closed = client.get(f"/api/sessions/{session['id']}/export?format=one_page_summary")
    assert not_closed.status_code == 409

    db.update_session(session["id"], state="CLOSED")
    response = client.get(f"/api/sessions/{session['id']}/export?format=one_page_summary")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith(
        f'attachment; filename="roundtable-{session["id"]}-one-page-summary.md"'
    )
    assert "Concise synthesis" in response.text


def test_markdown_export_includes_one_page_summary_block_and_missing_summary_blocks(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "export-regression-missing.sqlite3")
    db.initialize()
    session = db.create_session("Markdown export", "Keep transcript visible", 2, False, False)
    db.add_message(session["id"], "Momo", "Hello from summary test.")
    db.update_session(session["id"], state="CLOSED")

    client = make_test_client(db, monkeypatch)
    missing = client.get(f"/api/sessions/{session['id']}/export?format=one_page_summary")
    assert missing.status_code == 409

    db.add_summary_digest(session["id"], "one_page", 2, {"content": "Actionable learning: clarify assumptions and test robustness."})
    db.add_summary_digest(session["id"], "one_page", 3, {"content": "Latest learning summary: verify the decisive assumption."})
    markdown = client.get(f"/api/sessions/{session['id']}/export?format=markdown").text
    assert "## One-page learning summary" in markdown
    assert "Latest learning summary" in markdown
    latest = client.get(f"/api/sessions/{session['id']}/export?format=one_page_summary")
    assert "Latest learning summary" in latest.text
    assert "Actionable learning" not in latest.text


def test_summary_digest_export_contains_only_the_comprehensive_synthesis(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "summary-digest-export.sqlite3")
    db.initialize()
    session = db.create_session("Trajectory evidence", "Retain the learning progression", 2, False, False)
    db.add_summary_digest(
        session["id"],
        "periodic",
        2,
        {"active_question": "Are the reported groups causal types?", "agreements": ["No"]},
    )
    db.add_summary_digest(
        session["id"],
        "final",
        2,
        {"status": "final", "visible_recap": "A durable methodological synthesis."},
    )
    db.add_message(
        session["id"],
        "System",
        "## Executive synthesis\nThe groups are descriptive model assignments, not established biological classes.",
        metadata={"kind": "final_summary"},
    )
    db.update_session(session["id"], state="CLOSED")

    client = make_test_client(db, monkeypatch)
    response = client.get(f"/api/sessions/{session['id']}/export?format=summary_digest")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith(
        f'attachment; filename="roundtable-{session["id"]}-summary-digest.md"'
    )
    assert "# Summary Digest: Trajectory evidence" in response.text
    assert "## Comprehensive final synthesis" in response.text
    assert "descriptive model assignments" in response.text
    assert "## Topic Digest" not in response.text
    assert "## Processed Source Digests" not in response.text
    assert "## Latest Conversation Digest" not in response.text
    assert "## Complete Digest History" not in response.text
    assert "Are the reported groups causal types?" not in response.text


def test_complete_archive_keeps_supporting_digest_records(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "archive-digest-records.sqlite3")
    db.initialize()
    session = db.create_session("Archive evidence", "Keep supporting records", 2, False, False)
    db.update_session(
        session["id"],
        topic_digest={"scope": "Topic evidence"},
        conversation_digest={"active_question": "Current question"},
    )
    db.add_summary_digest(
        session["id"],
        "periodic",
        2,
        {"active_question": "Earlier question"},
    )
    document = db.add_document(
        session["id"],
        "paper.pdf",
        str(tmp_path / "missing-paper.pdf"),
        "application/pdf",
    )
    db.update_document(
        document["id"],
        status="ready",
        digest=json.dumps({"finding": "Processed source evidence"}),
    )
    db.add_message(
        session["id"],
        "System",
        "## Executive synthesis\nA clean final synthesis.",
        metadata={"kind": "final_summary"},
    )
    db.update_session(session["id"], state="CLOSED")

    client = make_test_client(db, monkeypatch)
    response = client.get(f"/api/sessions/{session['id']}/export?format=archive")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert {
            "digests/topic-digest.json",
            "digests/latest-conversation-digest.json",
            "digests/digest-history.json",
            "digests/processed-source-digests.json",
        }.issubset(archive.namelist())
        assert json.loads(archive.read("digests/topic-digest.json"))["scope"] == "Topic evidence"
        assert json.loads(archive.read("digests/latest-conversation-digest.json"))["active_question"] == "Current question"
        assert json.loads(archive.read("digests/digest-history.json"))[0]["digest"]["active_question"] == "Earlier question"
        assert json.loads(archive.read("digests/processed-source-digests.json"))[0]["digest"]["finding"] == "Processed source evidence"
        summary_digest = archive.read("summary-digest.md").decode("utf-8")
        assert "A clean final synthesis" in summary_digest
        assert "Topic evidence" not in summary_digest
        assert "Earlier question" not in summary_digest
        assert "Processed source evidence" not in summary_digest


def test_create_session_force_reset_clears_existing_active_sessions(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "export-create-session-regression.sqlite3")
    db.initialize()
    first = db.create_session("Observational bias", "Test guarded reset", 2, False, False)
    db.update_session(first["id"], state="AI_SEGMENT_RUNNING")
    client = make_test_client(db, monkeypatch)

    without_reset = client.post(
        "/api/sessions",
        json={
            "topic": "New topic should be blocked",
            "learning_goal": "Check reset path",
            "rounds_per_segment": 2,
            "sources_only": False,
            "periodic_summary": False,
            "force_reset": False,
        },
    )
    assert without_reset.status_code == 409

    with_reset = client.post(
        "/api/sessions",
        json={
            "topic": "Retained after reset",
            "learning_goal": "Verify purge works",
            "rounds_per_segment": 2,
            "sources_only": False,
            "periodic_summary": False,
            "force_reset": True,
        },
    )
    assert with_reset.status_code == 201
    created = with_reset.json()
    sessions = db.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == created["id"]


def test_create_session_requires_force_reset_if_any_old_session_is_non_closed(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "export-create-session-regression-2.sqlite3")
    db.initialize()
    stale = db.create_session("Active residue", "Need purge check", 2, False, False)
    db.update_session(stale["id"], state="AI_SEGMENT_RUNNING")
    closed = db.create_session("Closed anchor", "Finished one", 2, False, False)
    db.update_session(closed["id"], state="CLOSED")
    client = make_test_client(db, monkeypatch)

    without_reset = client.post(
        "/api/sessions",
        json={
            "topic": "Replacement after mixed states",
            "learning_goal": "Verify non-closure check scans all rows",
            "rounds_per_segment": 2,
            "sources_only": False,
            "periodic_summary": False,
            "force_reset": False,
        },
    )
    assert without_reset.status_code == 409


def test_create_session_requires_force_reset_for_closed_prior_session(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "export-create-session-closed-regression.sqlite3")
    db.initialize()
    prior = db.create_session("Closed record", "Must be purged before replacement", 2, False, False)
    db.update_session(prior["id"], state="CLOSED")
    client = make_test_client(db, monkeypatch)

    blocked = client.post(
        "/api/sessions",
        json={
            "topic": "Replacement",
            "learning_goal": "Verify strict one-session retention",
            "rounds_per_segment": 2,
            "sources_only": False,
            "periodic_summary": False,
            "force_reset": False,
        },
    )
    assert blocked.status_code == 409

    replacement = client.post(
        "/api/sessions",
        json={
            "topic": "Replacement",
            "learning_goal": "Verify strict one-session retention",
            "rounds_per_segment": 2,
            "sources_only": False,
            "periodic_summary": False,
            "force_reset": True,
        },
    )
    assert replacement.status_code == 201
    assert len(db.list_sessions()) == 1
    assert db.list_sessions()[0]["id"] == replacement.json()["id"]


def test_closed_session_rejects_recap_and_upload_and_active_cancel_is_guarded(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "closed-session-boundaries.sqlite3")
    db.initialize()
    session = db.create_session("Lifecycle", "Keep the final record immutable", 2, False, False)
    client = make_test_client(db, monkeypatch)

    active_cancel = client.post(f"/api/sessions/{session['id']}/final-summary/cancel")
    assert active_cancel.status_code == 409
    assert db.get_session(session["id"])["state"] == "HUMAN_FLOOR"

    db.update_session(session["id"], state="CLOSED")
    recap = client.post(f"/api/sessions/{session['id']}/recap", json={})
    upload = client.post(
        f"/api/sessions/{session['id']}/documents",
        files={"file": ("late-source.txt", b"late evidence", "text/plain")},
    )
    closed_cancel = client.post(f"/api/sessions/{session['id']}/final-summary/cancel")

    assert recap.status_code == 409
    assert upload.status_code == 409
    assert closed_cancel.status_code == 200
    assert closed_cancel.json()["state"] == "CLOSED"
