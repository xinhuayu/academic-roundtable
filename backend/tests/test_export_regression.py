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
