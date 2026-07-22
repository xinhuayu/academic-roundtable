from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .adapters import AdapterRegistry
from .config import get_settings
from .database import Database
from .documents import MAX_UPLOAD_BYTES, extract_dependency_health, safe_extension
from .evaluation import RUBRIC, analyze_session, apply_human_ratings, rating_template
from .language import detect_explicit_language_request, localized_closing, localized_greetings
from .schemas import (
    CloseoutSummaryRequest,
    LearningEvaluationSubmission,
    RecapRequest,
    SamMessage,
    SegmentRequest,
    SessionCreate,
    SessionSettingsUpdate,
)
from .service import (
    RoundtableService,
    infer_participant_target,
    is_closing_request,
    is_summary_request,
    is_source_verification_request,
)
from .voice import VoiceTranscriber, VoiceTranscriptionError


settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
database = Database(settings.db_path)
database.initialize()
database.reconcile_abandoned_work()
adapters = AdapterRegistry(settings)
service = RoundtableService(settings, database, adapters)
voice_transcriber = VoiceTranscriber(settings)

app = FastAPI(title="Academic Roundtable", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown() -> None:
    await adapters.close()
    await voice_transcriber.close()


def require_session(session_id: str) -> dict[str, Any]:
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def session_view(session_id: str) -> dict[str, Any]:
    session = require_session(session_id)
    return {
        **session,
        "messages": database.list_messages(session_id),
        "documents": [public_document(item) for item in database.list_documents(session_id)],
        "jobs": database.list_jobs(session_id),
        "summary_history": database.list_summary_digests(session_id),
        "learning_evaluation": database.get_learning_evaluation(session_id),
    }


def public_document(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "stored_path"}


def sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def render_session_markdown(view: dict[str, Any]) -> str:
    one_page_summary = next(
        (digest["digest"].get("content") for digest in reversed(view.get("summary_history", []))
         if digest.get("kind") == "one_page" and isinstance(digest.get("digest"), dict)),
        None,
    )

    lines = [
        f"# {view['topic']}",
        "",
        f"**Learning goal:** {view['learning_goal']}",
        f"**Conversation language:** {view.get('conversation_language', 'English')}",
        f"**Completed rounds:** {view['completed_rounds']}",
        "",
        "## Topic Digest",
        "",
        "```json",
        json.dumps(view["topic_digest"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Conversation Digest",
        "",
        "```json",
        json.dumps(view["conversation_digest"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Summary Digest History",
        "",
    ]
    for index, digest in enumerate(view["summary_history"], start=1):
        lines.extend([
            f"### Digest {index}: {digest['kind']} (through round {digest['through_round']})",
            "",
            "```json",
            json.dumps(digest["digest"], ensure_ascii=False, indent=2),
            "```",
            "",
        ])
    lines.extend(["## Transcript", ""])
    for message in view["messages"]:
        lines.extend([f"### {message['speaker']}", "", message["content"], ""])
    evaluation = view.get("learning_evaluation")
    if evaluation:
        review = (evaluation.get("report") or {}).get("human_review") or {}
        lines.extend(["## Learning-Quality Evaluation", ""])
        lines.append(f"**Weighted human score:** {review.get('weighted_score', 'Not completed')} / 5")
        lines.append("")
        for entry in (review.get("ratings") or {}).values():
            lines.extend([
                f"### {entry.get('label', 'Dimension')}: {entry.get('score') or 'Not scored'}",
                "",
                entry.get("evidence") or entry.get("note") or "No evidence recorded.",
                "",
            ])
    if one_page_summary:
        lines.extend(["## One-page learning summary", "", "```markdown", one_page_summary, "```", ""])
    return "\n".join(lines)


def render_summary_digest(view: dict[str, Any]) -> str:
    """Render only the comprehensive learning synthesis, without raw supporting digests."""
    final_summary = next(
        (
            message["content"]
            for message in reversed(view.get("messages", []))
            if (message.get("metadata") or {}).get("kind") == "final_summary"
        ),
        None,
    )
    lines = [
        f"# Summary Digest: {view['topic']}",
        "",
        f"**Learning goal:** {view['learning_goal']}",
        f"**Conversation language:** {view.get('conversation_language', 'English')}",
        f"**Completed rounds:** {view['completed_rounds']}",
        "",
        "## Comprehensive final synthesis",
        "",
        final_summary or (
            "Final synthesis was cancelled or unavailable. Download the complete archive "
            "to retain the transcript and supporting digest records."
        ),
        "",
    ]
    return "\n".join(lines)


def remove_managed_uploads(paths: list[str]) -> None:
    upload_root = settings.uploads_dir.resolve()
    for raw_path in paths:
        candidate = Path(raw_path)
        try:
            resolved = candidate.resolve()
            if resolved == upload_root or upload_root not in resolved.parents:
                continue
            resolved.unlink(missing_ok=True)
        except OSError:
            continue


async def purge_all_sessions_safely() -> None:
    sessions = database.list_sessions()
    for session_item in sessions:
        await service.interrupt_and_wait(session_item["id"])
        await service.cancel_session_background_tasks(session_item["id"])
        wait_idle = getattr(service, "wait_until_session_idle", None)
        if callable(wait_idle):
            await wait_idle(session_item["id"])
    remove_managed_uploads(database.purge_all_sessions())


@app.get("/api/meta")
async def meta() -> dict[str, Any]:
    return {
        "name": "Academic Roundtable",
        "version": "0.1.0",
        "digest_interval": settings.digest_interval,
        "recent_round_count": settings.recent_round_count,
        "supported_uploads": ["pdf", "txt", "md"],
        "export_formats": ["archive", "markdown", "summary_digest", "one_page_summary", "json"],
        "pdf_dependencies": extract_dependency_health(),
        "conversation_profiles": service.profile_metadata(),
        "voice_input": {
            "configured": voice_transcriber.configured,
            "model": settings.voice_transcription_model,
            "max_audio_bytes": settings.voice_max_audio_bytes,
        },
    }


@app.get("/api/documents/dependencies")
async def document_dependencies() -> dict[str, object]:
    return extract_dependency_health()


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "providers": await service.provider_health()}


@app.get("/api/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    return database.list_sessions()


@app.post("/api/sessions", status_code=201)
async def create_session(payload: SessionCreate) -> dict[str, Any]:
    previous_sessions = database.list_sessions()
    if previous_sessions and not payload.force_reset:
        raise HTTPException(
            status_code=409,
            detail=(
                "A prior local session exists. Start this roundtable with force_reset=true to purge its "
                "transcript, summaries, evaluation, and uploads before creating the new session."
            ),
        )
    if payload.force_reset:
        await purge_all_sessions_safely()
    requested_language = detect_explicit_language_request(
        f"{payload.topic}\n{payload.learning_goal}"
    )
    conversation_language = requested_language or "English"
    session = database.create_session(
        topic=payload.topic,
        learning_goal=payload.learning_goal,
        rounds_per_segment=payload.rounds_per_segment,
        sources_only=payload.sources_only,
        periodic_summary=payload.periodic_summary,
        conversation_profile=payload.conversation_profile,
        conversation_language=conversation_language,
        language_source="sam" if requested_language else "default",
    )
    database.add_message(
        session["id"],
        "Momo",
        "Hello, Sam—I'm Momo. I'm glad to join you and Bobby for this discussion.",
        metadata={"kind": "greeting"},
    )
    database.add_message(
        session["id"],
        "Bobby",
        "Hello, Sam—I'm Bobby. I’m ready when you are; you can set our first scientific direction.",
        metadata={"kind": "greeting"},
    )
    database.update_greeting_messages(
        session["id"], *localized_greetings(conversation_language)
    )
    return session_view(session["id"])


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    return session_view(session_id)


@app.get("/api/sessions/{session_id}/export")
async def export_session(session_id: str, format: str = "markdown"):
    view = session_view(session_id)
    one_page_summary = next(
        (digest["digest"].get("content") for digest in reversed(view.get("summary_history", []))
         if digest.get("kind") == "one_page" and isinstance(digest.get("digest"), dict)),
        None,
    )
    if view["state"] != "CLOSED":
        raise HTTPException(
            status_code=409,
            detail="Conclude the session before downloading its final record",
        )
    if format == "json":
        return JSONResponse(
            view,
            headers={"Content-Disposition": f'attachment; filename="roundtable-{session_id}.json"'},
        )
    if format == "one_page_summary":
        if not one_page_summary:
            raise HTTPException(
                status_code=409,
                detail="One-page summary is not available yet. Complete finalization first.",
            )
        return Response(
            one_page_summary,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="roundtable-{session_id}-one-page-summary.md"'},
        )
    if format == "summary_digest":
        return Response(
            render_summary_digest(view),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="roundtable-{session_id}-summary-digest.md"'
                )
            },
        )
    markdown = render_session_markdown(view)
    if format == "archive":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("session.md", markdown)
            archive.writestr("summary-digest.md", render_summary_digest(view))
            archive.writestr(
                "session.json",
                json.dumps(view, ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "digests/topic-digest.json",
                json.dumps(view.get("topic_digest") or {}, ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "digests/latest-conversation-digest.json",
                json.dumps(view.get("conversation_digest") or {}, ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "digests/digest-history.json",
                json.dumps(view.get("summary_history") or [], ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "digests/processed-source-digests.json",
                json.dumps(
                    [
                        {
                            "filename": document.get("filename"),
                            "status": document.get("status"),
                            "digest": document.get("digest"),
                        }
                        for document in (view.get("documents") or [])
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            upload_root = settings.uploads_dir.resolve()
            for index, document in enumerate(database.list_documents(session_id), start=1):
                source = Path(document["stored_path"])
                try:
                    resolved = source.resolve()
                    if upload_root not in resolved.parents or not resolved.is_file():
                        continue
                    filename = Path(document["filename"]).name
                    archive.write(resolved, f"sources/{index:02d}-{filename}")
                except OSError:
                    continue
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="roundtable-{session_id}.zip"'},
        )
    if format != "markdown":
        raise HTTPException(
            status_code=400,
            detail=(
                "Export format must be markdown, summary_digest, one_page_summary, json, or archive"
            ),
        )
    return Response(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="roundtable-{session_id}.md"'},
    )


def learning_evaluation_bundle(session_id: str) -> dict[str, Any]:
    view = session_view(session_id)
    if view["state"] != "CLOSED":
        raise HTTPException(
            status_code=409,
            detail="Learning evaluation becomes available after final summary processing ends",
        )
    stored = view.get("learning_evaluation")
    report = analyze_session(view)
    ratings = stored["ratings"] if stored else rating_template(view)
    if stored:
        report = apply_human_ratings(report, ratings)
    return {
        "report": report,
        "ratings": ratings,
        "rubric": RUBRIC,
        "saved": bool(stored),
        "updated_at": stored.get("updated_at") if stored else None,
    }


@app.get("/api/sessions/{session_id}/learning-evaluation")
async def get_learning_evaluation(session_id: str) -> dict[str, Any]:
    require_session(session_id)
    return learning_evaluation_bundle(session_id)


@app.put("/api/sessions/{session_id}/learning-evaluation")
async def save_learning_evaluation(
    session_id: str,
    payload: LearningEvaluationSubmission,
) -> dict[str, Any]:
    view = session_view(session_id)
    if view["state"] != "CLOSED":
        raise HTTPException(
            status_code=409,
            detail="Learning evaluation becomes available after final summary processing ends",
        )
    ratings = payload.model_dump()
    ratings["schema_version"] = 1
    ratings["session_id"] = session_id
    report = apply_human_ratings(analyze_session(view), ratings)
    database.save_learning_evaluation(session_id, report, ratings)
    return learning_evaluation_bundle(session_id)


@app.patch("/api/sessions/{session_id}")
async def update_session(session_id: str, payload: SessionSettingsUpdate) -> dict[str, Any]:
    require_session(session_id)
    updates = payload.model_dump(exclude_none=True)
    database.update_session(session_id, **updates)
    return session_view(session_id)


PERIODIC_PATTERN = re.compile(r"\b(periodic|every (?:five|six|5|6) rounds)\b", re.IGNORECASE)


def ensure_closing_message(session_id: str, target: str = "roundtable") -> dict[str, Any]:
    existing = next(
        (
            item for item in database.list_messages(session_id)
            if (item.get("metadata") or {}).get("kind") == "closing"
        ),
        None,
    )
    if existing:
        return existing
    session = require_session(session_id)
    closing_speaker = service.choose_next_speaker(session_id, target)
    return database.add_message(
        session_id,
        closing_speaker,
        localized_closing(str(session.get("conversation_language") or "English")),
        metadata={"kind": "closing"},
    )


@app.post("/api/sessions/{session_id}/messages")
async def add_sam_message(session_id: str, payload: SamMessage) -> dict[str, Any]:
    current_session = require_session(session_id)
    if current_session["state"] in {"CLOSING", "CLOSED"}:
        raise HTTPException(status_code=409, detail="This session has already concluded")
    was_interrupted = await service.interrupt_and_wait(session_id)
    requested_language = detect_explicit_language_request(payload.content)
    language_changed = bool(
        requested_language
        and requested_language != str(current_session.get("conversation_language") or "English")
    )
    if requested_language:
        service.set_conversation_language(session_id, requested_language, "sam")
    inferred_target = infer_participant_target(payload.content, payload.target)
    source_verification_requested = is_source_verification_request(payload.content)
    message = database.add_message(
        session_id,
        "Sam",
        payload.content,
        target=inferred_target,
        metadata={
            "interrupted_active_segment": was_interrupted,
            "explicit_target": payload.target,
            "inferred_target": inferred_target,
            "source_verification_requested": source_verification_requested,
            "input_method": payload.input_method,
        },
    )
    database.update_session(session_id, active_question=payload.content)
    starting_speaker = service.choose_next_speaker(session_id, inferred_target)
    action: dict[str, Any] = {"message": message, "interrupted": was_interrupted}
    if requested_language:
        action["conversation_language"] = requested_language
    closing_requested = is_closing_request(payload.content)
    if language_changed and not closing_requested:
        action["topic_digest_job"] = service.request_topic_digest(
            session_id,
            "conversation_language_changed",
        )
    if closing_requested:
        await service.cancel_session_background_tasks(session_id)
        action["closing_message"] = ensure_closing_message(session_id, inferred_target)
        database.update_session(session_id, state="CLOSED")
        action["suggested_action"] = "show_closeout"
    elif is_summary_request(payload.content):
        periodic = True if PERIODIC_PATTERN.search(payload.content) else None
        action["recap_job"] = service.request_recap(session_id, payload.content, periodic)
        action["suggested_action"] = "wait_for_recap"
    elif payload.continue_rounds:
        action["suggested_action"] = "start_segment"
        action["continue_rounds"] = payload.continue_rounds
        action["starting_speaker"] = starting_speaker
    else:
        action["suggested_action"] = "start_segment"
        action["continue_rounds"] = current_session["rounds_per_segment"]
        action["starting_speaker"] = starting_speaker
    return action


@app.post("/api/sessions/{session_id}/close")
async def close_session(session_id: str) -> dict[str, Any]:
    session = require_session(session_id)
    if session["state"] == "CLOSED":
        return session_view(session_id)
    await service.interrupt_and_wait(session_id)
    await service.cancel_session_background_tasks(session_id)
    ensure_closing_message(session_id)
    database.update_session(session_id, state="CLOSED")
    return session_view(session_id)


@app.post("/api/sessions/{session_id}/final-summary")
async def start_final_summary(
    session_id: str,
    payload: CloseoutSummaryRequest,
) -> dict[str, Any]:
    session = require_session(session_id)
    if session["state"] == "CLOSING":
        return session_view(session_id)
    if session["state"] != "CLOSED":
        raise HTTPException(status_code=409, detail="End the session before generating closeout summaries")
    existing = next(
        (
            item for item in database.list_messages(session_id)
            if (item.get("metadata") or {}).get("kind") == "final_summary"
        ),
        None,
    )
    if existing:
        return session_view(session_id)
    service.request_final_summary(session_id, payload.profile)
    return session_view(session_id)


@app.post("/api/sessions/{session_id}/final-summary/cancel")
async def cancel_final_summary(session_id: str) -> dict[str, Any]:
    session = require_session(session_id)
    if session["state"] == "CLOSED":
        return session_view(session_id)
    if session["state"] != "CLOSING":
        raise HTTPException(status_code=409, detail="No final summary is currently running")
    await service.cancel_final_summary(session_id)
    return session_view(session_id)


@app.delete("/api/sessions/{session_id}", status_code=204)
async def discard_session(session_id: str) -> Response:
    session = require_session(session_id)
    if session["state"] not in {"CLOSING", "CLOSED"}:
        raise HTTPException(status_code=409, detail="End the session before discarding it")
    await service.interrupt_and_wait(session_id)
    await service.cancel_final_summary(session_id)
    await service.cancel_session_background_tasks(session_id)
    wait_idle = getattr(service, "wait_until_session_idle", None)
    if callable(wait_idle):
        await wait_idle(session_id)
    await purge_all_sessions_safely()
    return Response(status_code=204)


@app.delete("/api/sessions", status_code=204)
async def discard_all_sessions() -> Response:
    await purge_all_sessions_safely()
    return Response(status_code=204)


@app.post("/api/sessions/{session_id}/segments")
async def start_segment(session_id: str, payload: SegmentRequest) -> StreamingResponse:
    session = require_session(session_id)
    if session["state"] in {"CLOSING", "CLOSED"}:
        raise HTTPException(status_code=409, detail="This session has concluded")

    async def event_stream():
        async for event in service.stream_segment(
            session_id,
            rounds=payload.rounds,
            starting_speaker=payload.starting_speaker,
            continue_without_sam=payload.continue_without_sam,
        ):
            yield sse(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/sessions/{session_id}/interrupt")
async def interrupt(session_id: str) -> dict[str, Any]:
    require_session(session_id)
    return {"interrupted": await service.interrupt_and_wait(session_id)}


@app.post("/api/sessions/{session_id}/recap", status_code=202)
async def recap(session_id: str, payload: RecapRequest) -> dict[str, Any]:
    session = require_session(session_id)
    if session["state"] in {"CLOSING", "CLOSED"}:
        raise HTTPException(status_code=409, detail="This session has concluded; recap history is now read-only")
    await service.interrupt_and_wait(session_id)
    return service.request_recap(session_id, payload.focus, payload.periodic)


@app.post("/api/sessions/{session_id}/documents", status_code=202)
async def upload_document(session_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    session = require_session(session_id)
    if session["state"] in {"CLOSING", "CLOSED"}:
        raise HTTPException(status_code=409, detail="This session has concluded; its source library is read-only")
    original_name = Path(file.filename or "document").name
    try:
        extension = safe_extension(original_name)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    if extension == ".pdf":
        deps = extract_dependency_health()
        if not (deps["pymupdf"] and deps["pdfplumber"]):
            detected = (
                f"Detected PyMuPDF: {deps.get('pymupdf_version') or 'missing'}, "
                f"pdfplumber: {deps.get('pdfplumber_version') or 'missing'}."
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "PDF ingestion requires PyMuPDF and pdfplumber for robust table/figure extraction. "
                    "Install both packages (`pip install pymupdf pdfplumber`) and retry. "
                    + detected
                ),
            )
    stored_name = f"{uuid.uuid4().hex}{extension}"
    stored_path = settings.uploads_dir / stored_name
    size = 0
    try:
        with stored_path.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds the 30 MB limit")
                handle.write(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    document = database.add_document(
        session_id,
        original_name,
        str(stored_path),
        file.content_type or "application/octet-stream",
    )
    job = service.request_document_digest(document["id"])
    return {"document": public_document(document), "job": job}


@app.post("/api/sessions/{session_id}/voice-transcription")
async def transcribe_sam_voice(session_id: str, request: Request) -> dict[str, Any]:
    session = require_session(session_id)
    if session["state"] in {"CLOSING", "CLOSED"}:
        raise HTTPException(status_code=409, detail="This session has concluded; voice input is unavailable")
    await service.interrupt_and_wait(session_id)
    filename = Path(request.headers.get("x-audio-filename") or "sam-voice.webm").name
    audio = bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio) > settings.voice_max_audio_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Voice recording exceeds the {settings.voice_max_audio_bytes // (1024 * 1024)} MB limit",
            )
    if not audio:
        raise HTTPException(status_code=422, detail="Voice recording is empty")
    try:
        return await voice_transcriber.transcribe(
            bytes(audio),
            filename,
            request.headers.get("content-type") or "application/octet-stream",
            database.get_session(session_id) or session,
        )
    except VoiceTranscriptionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/sessions/{session_id}/jobs")
async def list_jobs(session_id: str) -> list[dict[str, Any]]:
    require_session(session_id)
    return database.list_jobs(session_id)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/documents/{document_id}")
async def get_document(document_id: str) -> dict[str, Any]:
    document = database.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return public_document(document)


frontend_dist = settings.project_root / "frontend" / "dist"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        candidate = frontend_dist / path
        if path and candidate.is_file() and frontend_dist in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": "Academic Roundtable API",
                "message": "Build the frontend or run its development server on port 5173.",
                "docs": "/docs",
            }
        )
