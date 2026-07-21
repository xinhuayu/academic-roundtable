from __future__ import annotations

from fastapi.testclient import TestClient

from app import main as main_module
from app.database import Database


class _NoopService:
    async def interrupt_and_wait(self, *_args: object, **_kwargs: object) -> bool:
        return False

    async def cancel_session_background_tasks(self, *_args: object) -> int:
        return 0


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
    markdown = client.get(f"/api/sessions/{session['id']}/export?format=markdown").text
    assert "## One-page learning summary" in markdown
    assert "Actionable learning" in markdown


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
