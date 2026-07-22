from __future__ import annotations

import asyncio
import os
from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from app import main as main_module
from app.config import get_settings
from app.database import Database
from app.voice import VoiceTranscriber, build_transcription_prompt, validate_audio_upload


class _VoiceNoopService:
    async def interrupt_and_wait(self, *_args: object, **_kwargs: object) -> bool:
        return False


class _FakeVoiceTranscriber:
    configured = True

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def transcribe(self, audio: bytes, filename: str, content_type: str, session: dict):
        self.calls.append({
            "audio": audio,
            "filename": filename,
            "content_type": content_type,
            "topic": session["topic"],
        })
        return {"text": "A corrected academic comment.", "model": "test-transcriber", "characters": 29}


def test_voice_endpoint_returns_editable_text_without_persisting_audio(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "voice-endpoint.sqlite3")
    db.initialize()
    session = db.create_session("Causal trajectories", "Review assumptions", 2, False, False)
    transcriber = _FakeVoiceTranscriber()
    monkeypatch.setattr(main_module, "database", db)
    monkeypatch.setattr(main_module, "service", _VoiceNoopService())
    monkeypatch.setattr(main_module, "voice_transcriber", transcriber)
    client = TestClient(main_module.app)

    response = client.post(
        f"/api/sessions/{session['id']}/voice-transcription",
        content=b"test-audio",
        headers={"Content-Type": "audio/webm", "X-Audio-Filename": "sam.webm"},
    )

    assert response.status_code == 200
    assert response.json()["text"] == "A corrected academic comment."
    assert transcriber.calls[0]["topic"] == "Causal trajectories"
    assert db.list_messages(session["id"]) == []


def test_voice_endpoint_rejects_closed_sessions_and_oversized_audio(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "voice-guards.sqlite3")
    db.initialize()
    closed = db.create_session("Closed", "No mutation", 2, False, False)
    db.update_session(closed["id"], state="CLOSED")
    open_session = db.create_session("Open", "Bound upload", 2, False, False)
    monkeypatch.setattr(main_module, "database", db)
    monkeypatch.setattr(main_module, "service", _VoiceNoopService())
    monkeypatch.setattr(main_module, "voice_transcriber", _FakeVoiceTranscriber())
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, voice_max_audio_bytes=4))
    client = TestClient(main_module.app)

    closed_response = client.post(
        f"/api/sessions/{closed['id']}/voice-transcription",
        content=b"123",
        headers={"Content-Type": "audio/webm", "X-Audio-Filename": "sam.webm"},
    )
    large_response = client.post(
        f"/api/sessions/{open_session['id']}/voice-transcription",
        content=b"12345",
        headers={"Content-Type": "audio/webm", "X-Audio-Filename": "sam.webm"},
    )

    assert closed_response.status_code == 409
    assert large_response.status_code == 413


def test_transcriber_sends_topic_guidance_and_supported_audio(monkeypatch) -> None:
    monkeypatch.setenv("TEST_VOICE_API_KEY", "test-only-key")
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = request.content
        return httpx.Response(200, json={"text": "Trajectory uncertainty matters."})

    settings = replace(
        get_settings(),
        voice_transcription_base_url="https://example.invalid/v1",
        voice_transcription_api_key_env="TEST_VOICE_API_KEY",
        voice_transcription_model="gpt-4o-mini-transcribe",
    )
    client = httpx.AsyncClient(
        base_url=settings.voice_transcription_base_url,
        transport=httpx.MockTransport(handler),
    )
    transcriber = VoiceTranscriber(settings, client=client)
    session = {
        "topic": "Cognitive trajectories",
        "active_question": "Are classes causal types?",
        "topic_digest": {"key_concepts": ["posterior probability", "attrition"]},
    }

    result = asyncio.run(
        transcriber.transcribe(b"audio", "sam.webm", "audio/webm;codecs=opus", session)
    )
    asyncio.run(client.aclose())

    body = captured["body"]
    assert isinstance(body, bytes)
    assert result["text"] == "Trajectory uncertainty matters."
    assert captured["authorization"] == "Bearer test-only-key"
    assert b"gpt-4o-mini-transcribe" in body
    assert b"Cognitive trajectories" in body
    assert b"posterior probability" in body
    assert validate_audio_upload("sam.m4a", "audio/mp4") == "audio/mp4"
    assert "do not summarize" in build_transcription_prompt(session)


def test_voice_configuration_defaults_are_long_form_safe(monkeypatch) -> None:
    for name in (
        "VOICE_TRANSCRIPTION_MODEL",
        "VOICE_TRANSCRIPTION_TIMEOUT_SECONDS",
        "LONG_SAM_INPUT_TOKEN_MULTIPLIER",
        "LONG_SAM_INPUT_TIMEOUT_MULTIPLIER",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = get_settings()
    assert settings.voice_transcription_model == "gpt-4o-mini-transcribe"
    assert settings.voice_transcription_timeout == 480
    assert settings.long_sam_input_token_multiplier == 1.5
    assert settings.long_sam_input_timeout_multiplier == 1.75
