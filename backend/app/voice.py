from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from .config import Settings


ALLOWED_AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".ogg", ".wav", ".webm"}
ALLOWED_AUDIO_TYPES = {
    "audio/aac", "audio/flac", "audio/m4a", "audio/mp4", "audio/mpeg",
    "audio/ogg", "audio/wav", "audio/webm", "audio/x-m4a", "audio/x-wav", "video/mp4",
}


class VoiceTranscriptionError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def validate_audio_upload(filename: str, content_type: str) -> str:
    extension = Path(filename).suffix.lower()
    media_type = content_type.split(";", 1)[0].strip().lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise VoiceTranscriptionError("Unsupported voice recording format", 415)
    if media_type and media_type not in ALLOWED_AUDIO_TYPES and media_type != "application/octet-stream":
        raise VoiceTranscriptionError("Unsupported voice recording media type", 415)
    return media_type or "application/octet-stream"


def build_transcription_prompt(session: dict[str, Any]) -> str:
    topic_digest = session.get("topic_digest") or {}
    key_concepts = topic_digest.get("key_concepts") if isinstance(topic_digest, dict) else None
    if isinstance(key_concepts, list):
        concepts = ", ".join(str(item) for item in key_concepts[:20])
    elif key_concepts:
        concepts = str(key_concepts)
    else:
        concepts = ""
    prompt = (
        "Transcribe Sam's academic comment accurately in the language spoken. Preserve meaning, "
        "uncertainty, questions, names, numbers, and technical qualifications. Apply only light "
        "punctuation, obvious grammar, and likely spelling corrections; do not summarize, add claims, "
        "or make the argument more certain.\n"
        f"Roundtable output language after submission: {session.get('conversation_language', 'English')} "
        "(preserve the language Sam actually speaks in this editable transcript; do not translate it).\n"
        f"Roundtable topic: {session.get('topic', '')}\n"
        f"Active question: {session.get('active_question', '')}\n"
        f"Relevant academic terms: {concepts}"
    )
    return prompt[:4000]


class VoiceTranscriber:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=settings.voice_transcription_base_url,
            timeout=httpx.Timeout(
                connect=15.0,
                read=settings.voice_transcription_timeout,
                write=settings.voice_transcription_timeout,
                pool=15.0,
            ),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.voice_transcription_base_url
            and self.settings.voice_transcription_model
            and os.getenv(self.settings.voice_transcription_api_key_env, "")
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def transcribe(
        self,
        audio: bytes,
        filename: str,
        content_type: str,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.configured:
            raise VoiceTranscriptionError("Voice transcription is not configured", 503)
        media_type = validate_audio_upload(filename, content_type)
        headers = {"Authorization": f"Bearer {os.getenv(self.settings.voice_transcription_api_key_env, '')}"}
        try:
            response = await self.client.post(
                "/audio/transcriptions",
                headers=headers,
                data={
                    "model": self.settings.voice_transcription_model,
                    "response_format": "json",
                    "prompt": build_transcription_prompt(session),
                },
                files={"file": (Path(filename).name, audio, media_type)},
            )
            response.raise_for_status()
            payload = response.json()
            text = str(payload.get("text") or "").strip()
            if not text:
                raise VoiceTranscriptionError("The recording did not contain transcribable speech", 422)
            return {"text": text, "model": self.settings.voice_transcription_model, "characters": len(text)}
        except VoiceTranscriptionError:
            raise
        except httpx.TimeoutException as exc:
            raise VoiceTranscriptionError(
                "Voice transcription timed out. The recording was not saved; try again or type the comment.",
                504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = "Voice transcription provider rejected the recording"
            try:
                body = exc.response.json()
                provider_message = body.get("error", {}).get("message")
                if provider_message:
                    detail = str(provider_message)[:300]
            except (json.JSONDecodeError, AttributeError, ValueError):
                pass
            raise VoiceTranscriptionError(detail, 429 if status == 429 else 502) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise VoiceTranscriptionError("Voice transcription could not reach the provider", 502) from exc
