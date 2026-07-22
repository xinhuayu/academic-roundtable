from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.adapters import GenerationRequest, LLMAdapter, ProviderError
from app.config import ProviderConfig, Settings, get_settings, provider_from_env
from app.database import Database
from app.prompts import ACADEMIC_CONVERSATION_SKILL, PERSONAS
from app.service import (
    RoundtableService,
    infer_participant_target,
    is_host_invitation,
    is_source_verification_request,
    parse_json_object,
)
from app.schemas import SessionCreate


def make_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    return db


def test_session_defaults_and_round_completion(tmp_path: Path) -> None:
    assert SessionCreate(topic="Causal inference").rounds_per_segment == 2
    db = make_db(tmp_path)
    session = db.create_session("Causal inference", "Understand assumptions", 3, False, False)
    assert session["topic_digest"]["status"] == "provisional"
    round_row = db.create_round(session["id"])
    db.add_message(session["id"], "Momo", "First contribution", round_id=round_row["id"])
    db.add_message(session["id"], "Bobby", "Second contribution", round_id=round_row["id"])
    db.complete_round(round_row["id"])
    assert db.get_session(session["id"])["completed_rounds"] == 1


def test_recent_rounds_keep_sam_interventions(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Measurement", "Explore validity", 3, False, False)
    for index in range(7):
        round_row = db.create_round(session["id"])
        db.add_message(session["id"], "Momo", f"Momo {index}", round_id=round_row["id"])
        db.add_message(session["id"], "Bobby", f"Bobby {index}", round_id=round_row["id"])
        if index == 4:
            db.add_message(session["id"], "Sam", "Keep this direction")
        db.complete_round(round_row["id"])
    recent = db.recent_round_messages(session["id"], 5)
    contents = [message["content"] for message in recent]
    assert "Momo 0" not in contents
    assert "Momo 2" in contents
    assert "Keep this direction" in contents


def test_json_parser_handles_fenced_json() -> None:
    parsed = parse_json_object('```json\n{"active_question":"Why?"}\n```')
    assert parsed == {"active_question": "Why?"}


def test_chat_completions_forwards_task_reasoning_effort(monkeypatch) -> None:
    monkeypatch.setenv("FAKE_GEMINI_KEY", "test-only-key")
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        event = 'data: {"choices":[{"delta":{"content":"Ready"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=event, headers={"content-type": "text/event-stream"})

    provider = ProviderConfig(
        participant="Bobby",
        base_url="https://example.invalid/v1",
        model="gemini-3.1-flash-lite",
        api_style="chat_completions",
        api_key_env="FAKE_GEMINI_KEY",
        reasoning_effort="low",
    )
    adapter = LLMAdapter(provider)

    async def scenario() -> str:
        await adapter.client.aclose()
        adapter.client = httpx.AsyncClient(
            base_url=provider.base_url,
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer test-only-key"},
        )
        try:
            request = GenerationRequest(
                system="Test",
                messages=[{"role": "user", "content": "Synthesize"}],
                max_output_tokens=4000,
                reasoning_effort="medium",
                model="gemini-3.1-pro-preview",
            )
            return await adapter.generate(request)
        finally:
            await adapter.close()

    assert asyncio.run(scenario()) == "Ready"
    assert captured["reasoning_effort"] == "medium"
    assert captured["max_tokens"] == 4000
    assert captured["model"] == "gemini-3.1-pro-preview"


def test_chat_completion_length_finish_is_not_silent_success(monkeypatch) -> None:
    monkeypatch.setenv("FAKE_GEMINI_KEY", "test-only-key")

    async def handler(request: httpx.Request) -> httpx.Response:
        events = (
            'data: {"choices":[{"delta":{"content":"An unfinished claim"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
            'data: [DONE]\n\n'
        )
        return httpx.Response(200, text=events, headers={"content-type": "text/event-stream"})

    provider = ProviderConfig(
        participant="Bobby",
        base_url="https://example.invalid/v1",
        model="gemini-3.1-flash-lite",
        api_style="chat_completions",
        api_key_env="FAKE_GEMINI_KEY",
        reasoning_effort="low",
    )
    adapter = LLMAdapter(provider)

    async def scenario() -> list[str]:
        await adapter.client.aclose()
        adapter.client = httpx.AsyncClient(
            base_url=provider.base_url,
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer test-only-key"},
        )
        chunks: list[str] = []
        try:
            request = GenerationRequest(
                system="Test",
                messages=[{"role": "user", "content": "Respond"}],
                max_output_tokens=350,
                reasoning_effort="low",
            )
            with pytest.raises(ProviderError, match="generation limit"):
                async for chunk in adapter.stream(request):
                    chunks.append(chunk)
            return chunks
        finally:
            await adapter.close()

    assert asyncio.run(scenario()) == ["An unfinished claim"]


def test_anthropic_messages_style_streams_delta_and_handles_max_tokens_limit(monkeypatch) -> None:
    monkeypatch.setenv("FAKE_ANTHROPIC_KEY", "test-only-key")
    headers: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        headers["x-api-key"] = request.headers.get("x-api-key", "")
        headers["anthropic-version"] = request.headers.get("anthropic-version", "")
        events = (
            'data: {"type":"message_start","message":{"id":"msg","type":"message","role":"assistant","content":[]}}\n\n'
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Critical"}}\n\n'
            'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":" point"}}\n\n'
            'data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"}}\n\n'
            'data: [DONE]\n\n'
        )
        return httpx.Response(200, text=events, headers={"content-type": "text/event-stream"})

    provider = ProviderConfig(
        participant="Bobby",
        base_url="https://example.invalid/v1",
        model="claude-3-5-haiku-20241022",
        api_style="anthropic_messages",
        api_key_env="FAKE_ANTHROPIC_KEY",
        reasoning_effort="low",
    )
    adapter = LLMAdapter(provider)

    async def scenario() -> list[str]:
        await adapter.client.aclose()
        adapter.client = httpx.AsyncClient(
            base_url=provider.base_url,
            transport=httpx.MockTransport(handler),
            headers={"x-api-key": "test-only-key", "anthropic-version": "2023-06-01"},
        )
        chunks: list[str] = []
        try:
            request = GenerationRequest(
                system="Test",
                messages=[{"role": "user", "content": "Challenge this claim"}],
                max_output_tokens=350,
                reasoning_effort="low",
            )
            with pytest.raises(ProviderError, match="generation limit"):
                async for chunk in adapter.stream(request):
                    chunks.append(chunk)
            return chunks
        finally:
            await adapter.close()

    chunks = asyncio.run(scenario())
    assert chunks == ["Critical", " point"]
    assert headers["x-api-key"] == "test-only-key"
    assert headers["anthropic-version"] == "2023-06-01"


def test_provider_timeout_profile_is_configurable(monkeypatch) -> None:
    monkeypatch.setenv("BOBBY_FIRST_TOKEN_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("BOBBY_STREAM_IDLE_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("BOBBY_TOTAL_TIMEOUT_SECONDS", "240")
    provider = provider_from_env("bobby", "fallback")
    assert provider.first_token_timeout == 60
    assert provider.stream_idle_timeout == 60
    assert provider.total_timeout == 240


def test_momo_digest_and_participant_budget_defaults(monkeypatch) -> None:
    for name in (
        "DIGEST_PROVIDER",
        "LIVE_MAX_OUTPUT_TOKENS",
        "MOMO_LIVE_MAX_OUTPUT_TOKENS",
        "BOBBY_LIVE_MAX_OUTPUT_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = get_settings()
    assert settings.digest_provider == "momo"
    assert settings.live_max_output_tokens == 800
    assert settings.momo_live_max_output_tokens == 800
    assert settings.bobby_live_max_output_tokens == 1400


def test_research_profile_selects_flagship_models_and_expanded_budget(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session(
        "Statistical mediation", "Understand identification", 2, False, False, "research"
    )
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fast-model",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="momo", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    service = RoundtableService(settings, db, FakeRegistry())
    momo_request = service.build_context(db.get_session(session["id"]), "Momo", 0)
    bobby_request = service.build_context(db.get_session(session["id"]), "Bobby", 1)
    assert momo_request.model == "gpt-5.6-sol"
    assert bobby_request.model == "gemini-3.1-pro-preview"
    assert momo_request.reasoning_effort == "medium"
    assert bobby_request.reasoning_effort == "medium"
    assert momo_request.max_output_tokens == 1600
    assert bobby_request.max_output_tokens == 2800
    assert momo_request.stream_idle_timeout == 90


def test_academic_roles_require_depth_and_distinct_critical_angles() -> None:
    assert "Answer Sam's actual question" in ACADEMIC_CONVERSATION_SKILL
    assert "one level deeper" in ACADEMIC_CONVERSATION_SKILL
    assert "Stress-test Bobby's and Sam's substantive claims" in PERSONAS["Momo"]
    momo_skill = RoundtableService._load_momo_skill()
    assert "especially when responding to Bobby or Sam" in momo_skill
    assert "what must be true for that claim to hold" in momo_skill
    assert "established, plausible, underdetermined, or contradicted" in momo_skill
    assert "Preserve the defensible core rather than disagreeing reflexively" in momo_skill
    assert "case developer" in PERSONAS["Bobby"]


def test_interrupt_event_is_immediate(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    service = object.__new__(RoundtableService)
    service.cancel_events = {"session": asyncio.Event()}
    service.db = db
    service.db.create_session("A topic", "A goal", 3, False, False)
    # Unknown session still flips its active in-memory generation event safely.
    assert service.interrupt("session") is True
    assert service.cancel_events["session"].is_set()


def test_fts_retrieval_preserves_source_locator(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Positivity", "Understand identification", 3, False, False)
    document = db.add_document(session["id"], "paper.pdf", "paper.pdf", "application/pdf")
    db.replace_passages(
        document["id"],
        document["filename"],
        [{"page_number": 7, "content": "Positivity requires treatment variation within covariate strata."}],
    )
    results = db.search_passages(session["id"], "positivity treatment", limit=3)
    assert results[0]["filename"] == "paper.pdf"
    assert results[0]["page_number"] == 7


class FakeAdapter:
    def __init__(self, participant: str):
        self.requests: list[GenerationRequest] = []
        self.config = ProviderConfig(
            participant=participant,
            base_url="https://example.invalid/v1",
            model="fake",
            api_style="responses",
            api_key_env="FAKE_KEY",
            reasoning_effort="low",
            total_timeout=2,
        )

    async def stream(self, request: GenerationRequest):
        self.requests.append(request)
        yield f"{self.config.participant} advances the argument."

    async def generate(self, request: GenerationRequest):
        return "# Final summary\n\nThe discussion developed a clear comparison and retained one open question."


class FakeRegistry:
    def __init__(self):
        self.items = {"Momo": FakeAdapter("Momo"), "Bobby": FakeAdapter("Bobby")}

    def get(self, participant: str):
        return self.items[participant]


def test_two_round_segment_completes_without_human_checkpoint(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Theory comparison", "Explore mechanisms", 2, False, False)
    provider = ProviderConfig(
        participant="Momo",
        base_url="https://example.invalid/v1",
        model="fake",
        api_style="responses",
        api_key_env="FAKE_KEY",
        reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path,
        uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3",
        host="127.0.0.1",
        port=8765,
        digest_provider="bobby",
        digest_interval=6,
        recent_round_count=5,
        host_checkpoint_interval=3,
        live_max_output_tokens=500,
        conversation_digest_max_output_tokens=2000,
        topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000,
        momo=provider,
        bobby=provider,
    )
    service = RoundtableService(settings, db, FakeRegistry())

    async def collect():
        return [event async for event in service.stream_segment(session["id"], rounds=2)]

    events = asyncio.run(collect())
    assert sum(event["type"] == "round_complete" for event in events) == 2
    assert db.get_session(session["id"])["completed_rounds"] == 2
    assert [message["speaker"] for message in db.list_messages(session["id"])] == [
        "Momo",
        "Bobby",
        "Bobby",
        "Momo",
    ]


def test_direct_address_to_sam_does_not_interrupt_round(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Direct address", "Keep the debate moving", 2, False, False)
    db.add_message(session["id"], "Sam", "Begin with the main distinction.")
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    registry = FakeRegistry()

    async def direct_address(request: GenerationRequest):
        yield "Sam, this distinction matters because the estimands differ."

    registry.items["Momo"].stream = direct_address
    service = RoundtableService(settings, db, registry)

    async def collect():
        return [event async for event in service.stream_segment(
            session["id"], rounds=2, starting_speaker="Momo"
        )]

    events = asyncio.run(collect())
    assert not any(event["type"] == "host_invited" for event in events)
    assert sum(event["type"] == "round_complete" for event in events) == 2
    assert len([item for item in db.list_messages(session["id"]) if item["speaker"] != "Sam"]) == 4


def test_name_and_at_mention_routing() -> None:
    assert infer_participant_target("@momo, explain this", "roundtable") == "Momo"
    assert infer_participant_target("Bobby should challenge this", "roundtable") == "Bobby"
    assert infer_participant_target("Momo and Bobby, compare views", "roundtable") == "both"
    assert infer_participant_target("Continue the discussion", "roundtable") == "roundtable"
    assert infer_participant_target("Momo is mentioned", "Bobby") == "Bobby"


def test_direct_address_to_sam_does_not_end_ai_segment() -> None:
    assert not is_host_invitation("Sam, this distinction matters because the estimands differ.")
    assert not is_host_invitation("Sam, would you prefer the causal interpretation")
    assert not is_host_invitation("Sam, what is your view?\n\nThe analysis continues with a limitation.")


def test_complete_final_question_invites_sam() -> None:
    contribution = (
        "The two interpretations imply different identifying assumptions.\n\n"
        "Sam, which assumption should we examine next?"
    )
    assert is_host_invitation(contribution)


def test_greetings_are_excluded_from_initial_live_context(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Measurement", "Learn validity", 3, False, False)
    db.add_message(session["id"], "Momo", "Hello from Momo", metadata={"kind": "greeting"})
    db.add_message(session["id"], "Bobby", "Hello from Bobby", metadata={"kind": "greeting"})
    db.add_message(session["id"], "Sam", "Let's start with construct validity.")
    recent = db.recent_round_messages(session["id"], 5)
    assert [item["speaker"] for item in recent] == ["Sam"]


def test_source_digest_dict_is_accepted_in_stream_context(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Digest robustness", "Use parsed digests", 2, False, False)
    doc = db.add_document(session["id"], "notes.txt", str(tmp_path / "notes.txt"), "text/plain")
    db.update_document(doc["id"], digest='{"status": "ok", "topic": "test"}')
    provider = ProviderConfig(
        participant="Momo",
        base_url="https://example.invalid/v1",
        model="fake",
        api_style="responses",
        api_key_env="FAKE_KEY",
        reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path,
        uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3",
        host="127.0.0.1",
        port=8765,
        digest_provider="momo",
        digest_interval=6,
        recent_round_count=5,
        host_checkpoint_interval=3,
        live_max_output_tokens=500,
        conversation_digest_max_output_tokens=2000,
        topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000,
        momo=provider,
        bobby=provider,
    )
    service = RoundtableService(settings, db, FakeRegistry())

    request = service.build_context(db.get_session(session["id"]), "Momo", 0)
    assert "document digest" in request.messages[1]["content"]


def test_summary_digest_history_is_append_only(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Bias", "Compare explanations", 3, False, False)
    db.add_summary_digest(session["id"], "automatic", 6, {"active_question": "First"})
    db.add_summary_digest(session["id"], "requested", 8, {"active_question": "Second"})
    history = db.list_summary_digests(session["id"])
    assert [item["kind"] for item in history] == ["automatic", "requested"]
    assert history[0]["digest"]["active_question"] == "First"


def test_new_session_purge_removes_all_prior_history(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    first = db.create_session("First", "Learn", 3, False, False)
    second = db.create_session("Second", "Compare", 3, False, False)
    db.add_message(first["id"], "Sam", "A retained message")
    db.add_summary_digest(first["id"], "periodic", 5, {"active_question": "Earlier"})
    document = db.add_document(first["id"], "source.txt", str(tmp_path / "source.txt"), "text/plain")
    db.replace_passages(document["id"], "source.txt", [{"content": "A searchable passage."}])

    paths = db.purge_all_sessions()

    assert paths == [str(tmp_path / "source.txt")]
    assert db.list_sessions() == []
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM summary_digests").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0] == 0


def test_continue_without_sam_answers_provisionally_and_skips_immediate_checkpoint(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Interpretation", "Compare judgments", 2, False, False)
    db.add_message(session["id"], "Sam", "Start with interpretation.")
    for _ in range(2):
        round_row = db.create_round(session["id"])
        db.add_message(session["id"], "Momo", "A claim", round_id=round_row["id"])
        db.add_message(session["id"], "Bobby", "Sam, which interpretation do you prefer?", round_id=round_row["id"])
        db.complete_round(round_row["id"])
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    registry = FakeRegistry()
    service = RoundtableService(settings, db, registry)

    async def collect():
        return [event async for event in service.stream_segment(
            session["id"], rounds=2, continue_without_sam=True
        )]

    events = asyncio.run(collect())
    requests = registry.items["Momo"].requests + registry.items["Bobby"].requests
    assert any("Sam explicitly chose to continue" in request.system for request in requests)
    assert sum(event["type"] == "round_complete" for event in events) == 2


def test_first_token_timeout_returns_control_to_sam(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Latency", "Handle a stalled provider", 2, False, False)
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    registry = FakeRegistry()
    registry.items["Momo"].config = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
        first_token_timeout=0.01, total_timeout=1,
    )

    async def stalled_stream(request: GenerationRequest):
        await asyncio.sleep(0.05)
        yield "Too late"

    registry.items["Momo"].stream = stalled_stream
    service = RoundtableService(settings, db, registry)

    async def collect():
        return [event async for event in service.stream_segment(
            session["id"], rounds=2, starting_speaker="Momo"
        )]

    events = asyncio.run(collect())
    timeout_event = next(event for event in events if event["type"] == "provider_error")
    assert "first-token deadline" in timeout_event["message"]
    assert db.get_session(session["id"])["state"] == "HUMAN_FLOOR"


def test_output_limit_preserves_partial_and_prevents_next_speaker(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Truncation", "Do not continue from fragments", 2, False, False)
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=500,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    registry = FakeRegistry()

    async def truncated_stream(request: GenerationRequest):
        yield "An unfinished Bobby claim"
        raise ProviderError("Bobby", "output_limit", "Bobby reached the generation limit", True)

    registry.items["Bobby"].stream = truncated_stream
    service = RoundtableService(settings, db, registry)

    async def collect():
        return [event async for event in service.stream_segment(
            session["id"], rounds=2, starting_speaker="Bobby"
        )]

    events = asyncio.run(collect())
    messages = db.list_messages(session["id"])
    assert [(item["speaker"], item["status"]) for item in messages] == [
        ("Bobby", "interrupted")
    ]
    assert any(event["type"] == "provider_error" for event in events)
    assert not any(event["type"] == "message_start" and event.get("speaker") == "Momo" for event in events)
    assert db.get_session(session["id"])["state"] == "HUMAN_FLOOR"


def test_closing_state_survives_interrupting_stream_cleanup(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Closure", "Preserve lifecycle state", 2, False, False)
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    registry = FakeRegistry()
    service = RoundtableService(settings, db, registry)

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocked_stream(request: GenerationRequest):
            started.set()
            await release.wait()
            yield "A partial thought"

        registry.items["Momo"].stream = blocked_stream

        async def collect():
            return [event async for event in service.stream_segment(
                session["id"], rounds=2, starting_speaker="Momo"
            )]

        task = asyncio.create_task(collect())
        await started.wait()
        service.interrupt(session["id"])
        db.update_session(session["id"], state="CLOSING")
        release.set()
        await task

    asyncio.run(scenario())
    assert db.get_session(session["id"])["state"] == "CLOSING"


def test_final_summary_can_be_cancelled_without_losing_session_record(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Closure", "Keep the transcript without a summary", 2, False, False)
    db.add_message(session["id"], "Sam", "Let us stop here.")
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    registry = FakeRegistry()
    service = RoundtableService(settings, db, registry)

    async def scenario():
        started = asyncio.Event()

        async def blocked_generate(request: GenerationRequest):
            started.set()
            await asyncio.Event().wait()
            return "unreachable"

        # Momo always owns the comprehensive final Summary Digest, independent
        # of the provider selected for routine periodic digests.
        registry.items["Momo"].generate = blocked_generate
        job = service.request_final_summary(session["id"])
        one_page_job = db.create_job(session["id"], "one_page_summary", {})
        db.update_job(one_page_job["id"], status="running", detail="Writing one-page summary")
        await started.wait()
        assert db.get_session(session["id"])["state"] == "CLOSING"
        assert await service.cancel_final_summary(session["id"]) is True
        return job, one_page_job

    job, one_page_job = asyncio.run(scenario())
    assert db.get_job(job["id"])["status"] == "cancelled"
    assert db.get_job(one_page_job["id"])["status"] == "cancelled"
    assert db.get_session(session["id"])["state"] == "CLOSED"
    assert [message["content"] for message in db.list_messages(session["id"])] == [
        "Let us stop here."
    ]


def test_restart_reconciliation_clears_stranded_runtime_state(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Recovery", "Show honest restart state", 2, False, False)
    db.update_session(session["id"], state="CLOSING")
    round_row = db.create_round(session["id"])
    document = db.add_document(
        session["id"], "source.txt", str(tmp_path / "source.txt"), "text/plain"
    )
    db.update_document(document["id"], status="processing")
    job = db.create_job(session["id"], "document_digest", {})
    db.update_job(job["id"], status="running", detail="Working")

    counts = db.reconcile_abandoned_work()

    assert counts == {"jobs": 1, "documents": 1, "rounds": 1, "sessions": 1}
    assert db.get_session(session["id"])["state"] == "CLOSED"
    assert db.get_job(job["id"])["status"] == "interrupted"
    assert db.get_document(document["id"])["status"] == "failed"
    with db.connect() as connection:
        status = connection.execute(
            "SELECT status FROM rounds WHERE id = ?", (round_row["id"],)
        ).fetchone()[0]
    assert status == "interrupted"


def test_session_background_tasks_are_cancelled_before_purge(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Cancellation", "Avoid orphaned writes", 2, False, False)
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    service = RoundtableService(settings, db, FakeRegistry())

    async def scenario():
        started = asyncio.Event()

        async def blocked_work():
            started.set()
            await asyncio.Event().wait()

        job = db.create_job(session["id"], "topic_digest", {})
        db.update_job(job["id"], status="running")
        service._spawn(blocked_work(), session["id"])
        await started.wait()
        cancelled = await service.cancel_session_background_tasks(session["id"])
        return job, cancelled

    job, cancelled = asyncio.run(scenario())
    assert cancelled == 1
    assert db.get_job(job["id"])["status"] == "cancelled"
    assert session["id"] not in service.session_tasks


def test_live_context_is_bounded_and_marks_clipped_content(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Context limits", "Remain responsive", 2, False, False)
    db.add_message(session["id"], "Sam", "S" * 12000)
    db.update_session(
        session["id"],
        topic_digest={"status": "developed", "notes": "T" * 25000},
        conversation_digest={"active_question": "Limits", "notes": "C" * 25000},
    )
    document = db.add_document(
        session["id"], "source.txt", str(tmp_path / "source.txt"), "text/plain"
    )
    db.update_document(
        document["id"],
        status="ready",
        digest="Processed source digest: context limits are discussed in the uploaded study.",
    )
    db.replace_passages(
        document["id"], "source.txt", [{"content": "Context limits evidence " * 1000}],
    )
    for index in range(6):
        round_row = db.create_round(session["id"])
        db.add_message(
            session["id"], "Momo", f"Momo recent round {index}", round_id=round_row["id"]
        )
        db.add_message(
            session["id"], "Bobby", f"Bobby recent round {index}", round_id=round_row["id"]
        )
        db.complete_round(round_row["id"])
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    service = RoundtableService(settings, db, FakeRegistry())

    request = service.build_context(db.get_session(session["id"]), "Momo", 0)
    bobby_request = service.build_context(db.get_session(session["id"]), "Bobby", 1)
    verification_request = service.build_context(
        db.get_session(session["id"]), "Momo", 0, source_verification=True
    )
    bobby_verification_request = service.build_context(
        db.get_session(session["id"]), "Bobby", 1, source_verification=True
    )
    context = request.messages[0]["content"]
    verification_context = verification_request.messages[0]["content"]

    assert "clipped for this request; full content remains in the session" in context
    assert "UNTRUSTED ORIGINAL SOURCE EXCERPT" not in context
    assert "Context limits evidence" not in context
    assert "Processed source digest" in request.messages[1]["content"]
    assert '"active_question": "Limits"' in context
    assert "Momo recent round 0" not in context
    assert "Momo recent round 1" in context
    assert "Bobby recent round 5" in context
    assert "UNTRUSTED ORIGINAL SOURCE EXCERPT" in verification_context
    assert "Context limits evidence" in verification_context
    assert len(context) < 60000
    assert request.max_output_tokens == 1200
    assert bobby_request.max_output_tokens == 2100
    assert verification_request.max_output_tokens == 2400
    assert bobby_verification_request.max_output_tokens == 4200
    assert verification_request.reasoning_effort == "high"
    assert verification_request.model == "gpt-5.6-sol"


@pytest.mark.parametrize(
    "content",
    [
        "Please check the original source for that estimate.",
        "Can Bobby double-check the original PDF?",
        "Go back to the uploaded document and verify the table value.",
        "The original article should be reviewed before we conclude.",
    ],
)
def test_source_verification_request_detection(content: str) -> None:
    assert is_source_verification_request(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "What source supports that claim?",
        "Please explain the source digest.",
        "Let's continue discussing the document.",
    ],
)
def test_ordinary_source_discussion_does_not_reopen_extracts(content: str) -> None:
    assert is_source_verification_request(content) is False


def test_interrupt_cancels_stalled_stream_and_preserves_partial_text(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Interruption", "Stop immediately", 2, False, False)
    provider = ProviderConfig(
        participant="Momo", base_url="https://example.invalid/v1", model="fake",
        api_style="responses", api_key_env="FAKE_KEY", reasoning_effort="low",
    )
    settings = Settings(
        project_root=tmp_path, data_dir=tmp_path, uploads_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.sqlite3", host="127.0.0.1", port=8765,
        digest_provider="bobby", digest_interval=6, recent_round_count=5,
        host_checkpoint_interval=3, live_max_output_tokens=350,
        conversation_digest_max_output_tokens=2000, topic_digest_max_output_tokens=3000,
        source_digest_max_output_tokens=4000, momo=provider, bobby=provider,
    )
    registry = FakeRegistry()
    service = RoundtableService(settings, db, registry)

    async def scenario():
        stalled = asyncio.Event()

        async def stalled_stream(request: GenerationRequest):
            yield "A useful partial claim"
            stalled.set()
            await asyncio.Event().wait()
            yield "unreachable"

        registry.items["Momo"].stream = stalled_stream

        async def collect():
            return [event async for event in service.stream_segment(
                session["id"], rounds=2, starting_speaker="Momo"
            )]

        task = asyncio.create_task(collect())
        await stalled.wait()
        assert await service.interrupt_and_wait(session["id"]) is True
        return await task

    events = asyncio.run(scenario())
    assert any(event["type"] == "human_floor" and event["interrupted"] for event in events)
    messages = db.list_messages(session["id"])
    assert messages[-1]["content"] == "A useful partial claim"
    assert messages[-1]["status"] == "interrupted"
    assert db.get_session(session["id"])["state"] == "HUMAN_FLOOR"


def test_recap_request_reuses_an_active_digest_job(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    session = db.create_session("Recap", "Avoid duplicate model work", 2, False, False)
    active = db.create_job(session["id"], "conversation_digest", {"visible": False})
    service = object.__new__(RoundtableService)
    service.db = db

    returned = service.request_recap(session["id"], focus="methods", periodic=True)

    assert returned["id"] == active["id"]
    assert len([job for job in db.list_jobs(session["id"]) if job["kind"] == "conversation_digest"]) == 1
    assert db.get_session(session["id"])["periodic_summary"] is True
