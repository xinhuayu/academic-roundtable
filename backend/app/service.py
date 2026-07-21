from __future__ import annotations

import asyncio
import json
import re
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from .adapters import AdapterRegistry, GenerationRequest, ProviderError
from .config import Settings
from .database import Database
from .documents import extract_passages, format_passage_group, group_passages_for_digest
from .prompts import (
    ACADEMIC_CONVERSATION_SKILL,
    DIGEST_SYSTEM_PROMPT,
    FINAL_SUMMARY_SYSTEM_PROMPT,
    ONE_PAGE_SUMMARY_SYSTEM_PROMPT,
    PERSONAS,
    SOURCE_DIGEST_SYSTEM_PROMPT,
    TOPIC_DIGEST_SYSTEM_PROMPT,
)


ACADEMIC_MOVES = (
    "Develop a mechanism that advances the active question.",
    "Examine one consequential assumption in the preceding argument.",
    "Compare the current explanation with a plausible alternative.",
    "Connect the available evidence to the strength and limits of the inference.",
    "Identify a boundary condition or counterexample and explain why it matters.",
    "Synthesize what has changed in the discussion and deepen one unresolved issue.",
)


def infer_participant_target(content: str, explicit_target: str = "roundtable") -> str:
    if explicit_target in {"Momo", "Bobby", "both"}:
        return explicit_target
    momo = bool(re.search(r"(?:@momo\b|\bmomo\b)", content, re.IGNORECASE))
    bobby = bool(re.search(r"(?:@bobby\b|\bbobby\b)", content, re.IGNORECASE))
    if momo and bobby:
        return "both"
    if momo:
        return "Momo"
    if bobby:
        return "Bobby"
    return "roundtable"


def is_host_invitation(content: str) -> bool:
    """Return true only for a complete final question explicitly addressed to Sam."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content.strip()) if part.strip()]
    if not paragraphs:
        return False
    final_paragraph = paragraphs[-1]
    return bool(
        re.match(r"^Sam,\s+", final_paragraph, re.IGNORECASE)
        and re.search(r"\?[\"'\u2019\u201d)]*$", final_paragraph)
    )


def parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def clip_text(text: str, limit: int, label: str) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    marker = f"\n[... {label} clipped for this request; full content remains in the session ...]\n"
    remaining = max(0, limit - len(marker))
    head = int(remaining * 0.7)
    return text[:head] + marker + text[-(remaining - head):]


def join_with_budget(
    items: list[str],
    total_limit: int,
    item_limit: int,
    label: str,
    separator: str = "\n\n",
) -> str:
    if not items:
        return ""
    fair_share = max(800, total_limit // len(items) - len(separator))
    effective_limit = min(item_limit, fair_share)
    joined = separator.join(clip_text(item, effective_limit, label) for item in items)
    return clip_text(joined, total_limit, label)


class RoundtableService:
    def __init__(self, settings: Settings, database: Database, adapters: AdapterRegistry):
        self.settings = settings
        self.db = database
        self.adapters = adapters
        self.momo_skill = self._load_momo_skill()
        self.momo_one_page_summary_skill = self._load_momo_one_page_summary_skill()
        self.cancel_events: dict[str, asyncio.Event] = {}
        self.stream_tasks: dict[str, asyncio.Task[Any]] = {}
        self.session_locks: dict[str, asyncio.Lock] = {}
        self.background_tasks: set[asyncio.Task[Any]] = set()
        self.session_tasks: dict[str, set[asyncio.Task[Any]]] = {}
        self.final_summary_tasks: dict[str, asyncio.Task[Any]] = {}

    @staticmethod
    def _read_skill_text(path: Path) -> str:
        for encoding in ("utf-8", "cp1252"):
            try:
                return path.read_text(encoding=encoding).strip()
            except UnicodeDecodeError:
                continue
        return ""

    @staticmethod
    def _load_momo_skill() -> str:
        skill_path = Path(__file__).resolve().parent / "skills" / "momo-academic-critical-review.md"
        try:
            return RoundtableService._read_skill_text(skill_path)
        except OSError:
            return ""

    @staticmethod
    def _load_momo_one_page_summary_skill() -> str:
        skill_path = Path(__file__).resolve().parent / "skills" / "momo-one-page-summary.md"
        try:
            return RoundtableService._read_skill_text(skill_path)
        except OSError:
            return ""

    def _speaker_live_token_budget(self, speaker: str) -> int:
        if speaker == "Momo":
            return self.settings.momo_live_max_output_tokens
        if speaker == "Bobby":
            return self.settings.bobby_live_max_output_tokens
        return self.settings.live_max_output_tokens

    def _source_boosts(self, session_id: str) -> tuple[float, float]:
        documents = self.db.list_documents(session_id)
        if not documents:
            return 1.0, 1.0
        if len(documents) >= 2:
            return (
                self.settings.source_multi_doc_token_multiplier,
                self.settings.source_multi_doc_timeout_multiplier,
            )
        return (
            self.settings.source_single_doc_token_multiplier,
            self.settings.source_single_doc_timeout_multiplier,
        )

    def _scaled_tokens(self, base_tokens: int, multiplier: float, minimum: int = 250) -> int:
        return max(minimum, int(base_tokens * multiplier))

    def _scaled_timeout(self, base_seconds: float, multiplier: float) -> float:
        return max(1.0, base_seconds * multiplier)

    def _lock(self, session_id: str) -> asyncio.Lock:
        return self.session_locks.setdefault(session_id, asyncio.Lock())

    def _spawn(self, coroutine: Any, session_id: str) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine)
        self.background_tasks.add(task)
        self.session_tasks.setdefault(session_id, set()).add(task)
        task.add_done_callback(self.background_tasks.discard)

        def clear_session_task(completed: asyncio.Task[Any]) -> None:
            tasks = self.session_tasks.get(session_id)
            if not tasks:
                return
            tasks.discard(completed)
            if not tasks:
                self.session_tasks.pop(session_id, None)

        task.add_done_callback(clear_session_task)
        return task

    async def cancel_session_background_tasks(self, session_id: str) -> int:
        current = asyncio.current_task()
        tasks = [
            task for task in self.session_tasks.get(session_id, set())
            if task is not current and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        active_jobs = [
            job for job in self.db.list_jobs(session_id)
            if job["status"] in {"queued", "running"}
        ]
        for job in active_jobs:
            self.db.update_job(
                job["id"],
                status="cancelled",
                detail="Cancelled when the session ended",
                error=None,
            )
        for document in self.db.list_documents(session_id):
            if document["status"] in {"queued", "processing"}:
                self.db.update_document(
                    document["id"],
                    status="failed",
                    error="Processing was cancelled when the session ended",
                )
        return len(tasks)

    def interrupt(self, session_id: str) -> bool:
        event = self.cancel_events.get(session_id)
        if not event:
            return False
        event.set()
        self.db.update_session(session_id, state="INTERRUPTING")
        return True

    async def interrupt_and_wait(self, session_id: str) -> bool:
        interrupted = self.interrupt(session_id)
        task = self.stream_tasks.get(session_id)
        current = asyncio.current_task()
        if task and task is not current and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return interrupted

    async def wait_until_session_idle(self, session_id: str) -> None:
        async with self._lock(session_id):
            return

    async def provider_health(self) -> list[dict[str, Any]]:
        return await asyncio.gather(
            self.adapters.get("Momo").health_check(),
            self.adapters.get("Bobby").health_check(),
        )

    def build_context(
        self,
        session: dict[str, Any],
        speaker: str,
        move_index: int,
        invite_host: bool = False,
        sam_deferred: bool = False,
    ) -> GenerationRequest:
        recent = self.db.recent_round_messages(session["id"], self.settings.recent_round_count)
        source_token_multiplier, _source_timeout_multiplier = self._source_boosts(session["id"])
        source_context = self._build_source_context(session["id"])
        transcript = join_with_budget(
            [
                f"{message['speaker']} ({message['status']}): {message['content']}"
                for message in recent
            ],
            total_limit=48000,
            item_limit=3200,
            label="recent turn",
        ) or "No completed discussion turns yet."
        query = session.get("active_question") or session["topic"]
        evidence = self.db.search_passages(session["id"], query, limit=5)
        evidence_text = join_with_budget(
            [
                f"[UNTRUSTED SOURCE EVIDENCE: {item['filename']}, page {item['page_number'] or 'n/a'}, evidence_id={item['passage_id']}]\n{item['content']}"
                for item in evidence
            ],
            total_limit=18000,
            item_limit=3400,
            label="source excerpt",
        ) or "No uploaded-source passage was retrieved for this turn. You may use clearly labeled background knowledge."
        source_rule = (
            "Use only uploaded-source evidence; if the sources do not support a claim, state that it is not established."
            if session["sources_only"]
            else "You may add reliable internal knowledge when sources are silent, labeled as Background knowledge."
        )
        latest_message = self.db.list_messages(session["id"])[-1:]
        response_priority = (
            "Sam spoke most recently. Answer Sam's question or comment directly before debating or extending it."
            if latest_message and latest_message[0]["speaker"] == "Sam"
            else "Respond directly to the most recent substantive claim."
        )
        host_instruction = (
            "This is a human checkpoint. End by asking Sam one short, specific question that requires judgment, interpretation, or a choice of direction."
            if invite_host
            else "Do not ask Sam unless human judgment is genuinely needed for this turn."
        )
        if sam_deferred:
            host_instruction = (
                "Sam explicitly chose to continue without answering the previous AI question. "
                "Do not wait for Sam or repeat the question. Continue the intellectual thread; "
                "if the previous turn asked Sam for a judgment, answer it provisionally from your "
                "academic perspective and state the assumption. Do not ask Sam another question in this turn."
            )
        persona = PERSONAS[speaker]
        if speaker == "Momo" and self.momo_skill:
            persona = f"{persona}\n\n{self.momo_skill}"
        system = "\n\n".join(
            [
                persona,
                ACADEMIC_CONVERSATION_SKILL,
                f"Session evidence policy: {source_rule}",
                f"Academic move for this contribution: {ACADEMIC_MOVES[move_index % len(ACADEMIC_MOVES)]}",
                response_priority,
                host_instruction,
            ]
        )
        topic_digest = clip_text(
            json.dumps(session.get("topic_digest") or {}, ensure_ascii=False, indent=2),
            12000,
            "topic digest",
        )
        conversation_digest = clip_text(
            json.dumps(session.get("conversation_digest") or {}, ensure_ascii=False, indent=2),
            12000,
            "conversation digest",
        )
        active_question = clip_text(
            session.get("active_question") or session["topic"],
            6000,
            "active question",
        )
        context = f"""TOPIC DIGEST
{topic_digest}

CONVERSATION DIGEST
{conversation_digest}

ACTIVE QUESTION
{active_question}

RECENT DISCUSSION — retain and engage these five recent rounds
{transcript}

RELEVANT SOURCE EVIDENCE
{evidence_text}

Continue the roundtable as {speaker}. Address the latest relevant contribution and advance the active question."""
        return GenerationRequest(
            system=system,
            messages=[
                {"role": "user", "content": context},
                *([{"role": "user", "content": f"SOURCE CONTEXT:\n{source_context}"}] if source_context else []),
            ],
            max_output_tokens=self._scaled_tokens(
                self._speaker_live_token_budget(speaker),
                source_token_multiplier * self.settings.live_turn_token_multiplier,
            ),
            reasoning_effort=self.adapters.get(speaker).config.reasoning_effort,
            verbosity="low",
        )

    def _build_source_context(self, session_id: str) -> str:
        documents = self.db.list_documents(session_id)
        if not documents:
            return ""
        digest_fragments: list[str] = []
        for document in documents:
            digest_text = (document.get("digest") or "").strip()
            if digest_text:
                digest_fragments.append(
                    f"{document['filename']} (document digest)"
                    f"\n{clip_text(digest_text, 7000, 'source digest')}"
                )
                continue
            status = document.get("status", "unknown")
            if status == "failed":
                digest_fragments.append(f"{document['filename']} (document digest failed; fallback evidence may be partial)")
            else:
                digest_fragments.append(f"{document['filename']} ({status})")
        return join_with_budget(
            digest_fragments,
            total_limit=12000,
            item_limit=3000,
            label="source context",
        )

    async def stream_segment(
        self,
        session_id: str,
        rounds: int | None = None,
        starting_speaker: str | None = None,
        continue_without_sam: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        async with self._lock(session_id):
            session = self.db.get_session(session_id)
            if not session:
                yield {"type": "error", "message": "Session not found"}
                return
            stream_task = asyncio.current_task()
            if stream_task:
                self.stream_tasks[session_id] = stream_task
            planned_rounds = max(2, min(5, rounds or session["rounds_per_segment"]))
            all_messages = self.db.list_messages(session_id)
            latest_sam_target = next(
                (item.get("target") for item in reversed(all_messages) if item["speaker"] == "Sam"),
                "roundtable",
            )
            directed_speaker = latest_sam_target if latest_sam_target in {"Momo", "Bobby"} else None
            first = starting_speaker or directed_speaker or session.get("next_speaker") or "Momo"
            independent_first_round = latest_sam_target == "both"
            cancel_event = asyncio.Event()
            self.cancel_events[session_id] = cancel_event
            self.db.update_session(session_id, state="AI_SEGMENT_RUNNING")
            yield {"type": "segment_start", "rounds": planned_rounds, "starting_speaker": first}
            stop_for_host = False
            try:
                for segment_round in range(planned_rounds):
                    if cancel_event.is_set():
                        break
                    round_row = self.db.create_round(session_id)
                    source_token_multiplier, source_timeout_multiplier = self._source_boosts(session_id)
                    yield {
                        "type": "round_start",
                        "round_id": round_row["id"],
                        "round_number": round_row["round_number"],
                    }
                    order = [first, "Bobby" if first == "Momo" else "Momo"]
                    session_before_round = self.db.get_session(session_id)
                    host_checkpoint_due = (
                        (session_before_round["completed_rounds"] + 1)
                        % self.settings.host_checkpoint_interval
                        == 0
                    ) and not (continue_without_sam and segment_round == 0)
                    prepared_requests: dict[str, GenerationRequest] = {}
                    if independent_first_round and segment_round == 0:
                        frozen_session = self.db.get_session(session_id)
                        prepared_requests = {
                            speaker: self.build_context(
                                frozen_session,
                                speaker,
                                segment_round * 2 + turn_index,
                                invite_host=host_checkpoint_due and turn_index == 1,
                                sam_deferred=continue_without_sam and segment_round == 0,
                            )
                            for turn_index, speaker in enumerate(order)
                        }
                    round_complete = True
                for turn_index, speaker in enumerate(order):
                    if cancel_event.is_set():
                        round_complete = False
                        break
                    current = self.db.get_session(session_id)
                    request = prepared_requests.get(speaker) or self.build_context(
                        current,
                        speaker,
                        segment_round * 2 + turn_index,
                        invite_host=host_checkpoint_due and turn_index == 1,
                        sam_deferred=continue_without_sam and segment_round == 0,
                    )
                    per_turn_timeout = source_timeout_multiplier * self.settings.live_turn_timeout_multiplier
                    yield {"type": "message_start", "speaker": speaker, "round_id": round_row["id"]}
                    chunks: list[str] = []
                    try:
                        adapter = self.adapters.get(speaker)
                        async with asyncio.timeout(
                            self._scaled_timeout(
                                adapter.config.total_timeout,
                                per_turn_timeout,
                            )
                        ):
                            stream = adapter.stream(request).__aiter__()
                            try:
                                async with asyncio.timeout(
                                    self._scaled_timeout(
                                        adapter.config.first_token_timeout,
                                        per_turn_timeout,
                                    )
                                ):
                                    first_delta = await anext(stream)
                            except TimeoutError as exc:
                                raise ProviderError(
                                    speaker,
                                    "first_token_timeout",
                                    f"{speaker} did not begin responding before the first-token deadline",
                                    retryable=True,
                                ) from exc
                            except StopAsyncIteration as exc:
                                raise ProviderError(
                                    speaker,
                                    "empty_response",
                                    "Provider completed without visible output",
                                    retryable=True,
                                ) from exc
                            if not cancel_event.is_set():
                                chunks.append(first_delta)
                                yield {"type": "delta", "speaker": speaker, "text": first_delta}
                            while True:
                                if cancel_event.is_set():
                                    round_complete = False
                                    break
                                try:
                                    async with asyncio.timeout(
                                        self._scaled_timeout(
                                            adapter.config.stream_idle_timeout,
                                            per_turn_timeout,
                                        )
                                    ):
                                        delta = await anext(stream)
                                except StopAsyncIteration:
                                    break
                                chunks.append(delta)
                                yield {"type": "delta", "speaker": speaker, "text": delta}
                    except (ProviderError, TimeoutError) as exc:
                        message = str(exc) if isinstance(exc, ProviderError) else "Total turn timeout exceeded"
                        partial = "".join(chunks).strip()
                        if partial:
                            self.db.add_message(
                                session_id,
                                speaker,
                                partial,
                                round_id=round_row["id"],
                                status="interrupted",
                            )
                        yield {
                            "type": "provider_error",
                            "speaker": speaker,
                            "message": message,
                            "partial": bool(partial),
                        }
                        round_complete = False
                        stop_for_host = True
                        break
                    except asyncio.CancelledError:
                        partial = "".join(chunks).strip()
                        if partial:
                            self.db.add_message(
                                session_id,
                                speaker,
                                partial,
                                round_id=round_row["id"],
                                status="interrupted",
                            )
                        cancel_event.set()
                        round_complete = False
                        stop_for_host = True
                        break
                    content = "".join(chunks).strip()
                    if cancel_event.is_set():
                        if content:
                            self.db.add_message(
                                session_id,
                                speaker,
                                content,
                                round_id=round_row["id"],
                                status="interrupted",
                            )
                        round_complete = False
                        break
                    message = self.db.add_message(
                        session_id,
                        speaker,
                        content or "[No visible response]",
                        round_id=round_row["id"],
                        metadata={
                            "academic_move": ACADEMIC_MOVES[
                                (segment_round * 2 + turn_index) % len(ACADEMIC_MOVES)
                            ],
                            "independent_answer": bool(prepared_requests),
                        },
                    )
                    yield {"type": "message_complete", "message": message}
                    if is_host_invitation(content[-1000:]):
                        stop_for_host = True
                        if turn_index < len(order) - 1:
                            round_complete = False
                        yield {"type": "host_invited", "speaker": speaker}
                        break
                    if round_complete:
                        self.db.complete_round(round_row["id"])
                        updated = self.db.get_session(session_id)
                        yield {
                            "type": "round_complete",
                            "round_id": round_row["id"],
                            "completed_rounds": updated["completed_rounds"],
                        }
                        await self._maybe_schedule_digests(updated)
                        first = "Bobby" if first == "Momo" else "Momo"
                        if host_checkpoint_due:
                            stop_for_host = True
                            yield {"type": "host_invited", "speaker": order[-1], "scheduled": True}
                    else:
                        self.db.interrupt_round(round_row["id"])
                    if stop_for_host or cancel_event.is_set():
                        break
            finally:
                next_speaker = "Bobby" if first == "Momo" else "Momo"
                latest_session = self.db.get_session(session_id)
                if latest_session and latest_session["state"] not in {"CLOSING", "CLOSED"}:
                    self.db.update_session(
                        session_id,
                        state="HUMAN_FLOOR",
                        next_speaker=next_speaker,
                    )
                self.cancel_events.pop(session_id, None)
                if self.stream_tasks.get(session_id) is stream_task:
                    self.stream_tasks.pop(session_id, None)
            yield {
                "type": "human_floor",
                "interrupted": cancel_event.is_set(),
                "reason": "host_invited" if stop_for_host else "segment_complete",
            }

    async def _maybe_schedule_digests(self, session: dict[str, Any]) -> None:
        completed = session["completed_rounds"]
        if (
            completed >= 3
            and (session.get("topic_digest") or {}).get("status") == "provisional"
            and not self.db.has_active_job(session["id"], "topic_digest")
        ):
            job = self.db.create_job(session["id"], "topic_digest", {"through_round": completed})
            self._spawn(self.run_topic_digest(job["id"], session["id"]), session["id"])
        if (
            completed - session["digested_through_round"] >= self.settings.digest_interval
            and not self.db.has_active_job(session["id"], "conversation_digest")
        ):
            job = self.db.create_job(session["id"], "conversation_digest", {"through_round": completed})
            self._spawn(
                self.run_conversation_digest(
                    job["id"], session["id"], visible=bool(session["periodic_summary"])
                ),
                session["id"],
            )

    def request_recap(self, session_id: str, focus: str | None, periodic: bool | None) -> dict[str, Any]:
        if periodic is not None:
            self.db.update_session(session_id, periodic_summary=periodic)
        job = self.db.create_job(session_id, "conversation_digest", {"focus": focus, "visible": True})
        self._spawn(
            self.run_conversation_digest(job["id"], session_id, visible=True, focus=focus),
            session_id,
        )
        return job

    def request_final_summary(self, session_id: str) -> dict[str, Any]:
        if self.db.has_active_job(session_id, "final_summary"):
            jobs = self.db.list_jobs(session_id)
            return next(job for job in jobs if job["kind"] == "final_summary" and job["status"] in {"queued", "running"})
        job = self.db.create_job(session_id, "final_summary", {})
        self.db.update_session(session_id, state="CLOSING")
        task = self._spawn(self.run_final_summary(job["id"], session_id), session_id)
        self.final_summary_tasks[session_id] = task

        def clear_task(completed: asyncio.Task[Any]) -> None:
            if self.final_summary_tasks.get(session_id) is completed:
                self.final_summary_tasks.pop(session_id, None)

        task.add_done_callback(clear_task)
        return job

    async def cancel_final_summary(self, session_id: str) -> bool:
        active_jobs = [
            job for job in self.db.list_jobs(session_id)
            if job["kind"] == "final_summary" and job["status"] in {"queued", "running"}
        ]
        task = self.final_summary_tasks.get(session_id)
        cancelled = bool(active_jobs or (task and not task.done()))
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for job in active_jobs:
            self.db.update_job(
                job["id"],
                status="cancelled",
                progress=1.0,
                detail="Final summary cancelled by Sam",
                error=None,
            )
        if self.db.get_session(session_id):
            self.db.update_session(session_id, state="CLOSED")
        return cancelled

    def choose_next_speaker(self, session_id: str, target: str) -> str:
        if target in {"Momo", "Bobby"}:
            speaker = target
        else:
            speaker = secrets.choice(["Momo", "Bobby"])
        self.db.update_session(session_id, next_speaker=speaker)
        return speaker

    def request_document_digest(self, document_id: str) -> dict[str, Any]:
        document = self.db.get_document(document_id)
        if not document:
            raise ValueError("Document not found")
        job = self.db.create_job(
            document["session_id"], "document_digest", {"document_id": document_id}
        )
        self._spawn(
            self.run_document_digest(job["id"], document_id),
            document["session_id"],
        )
        return job

    def _digest_adapter(self):
        participant = "Momo" if self.settings.digest_provider == "momo" else "Bobby"
        return self.adapters.get(participant)

    async def run_conversation_digest(
        self,
        job_id: str,
        session_id: str,
        visible: bool = False,
        focus: str | None = None,
    ) -> None:
        self.db.update_job(job_id, status="running", progress=0.1, detail="Collecting discussion")
        try:
            session = self.db.get_session(session_id)
            messages = self.db.list_messages(session_id)
            messages = [
                item for item in messages
                if (item.get("metadata") or {}).get("kind")
                not in {"greeting", "session_opening", "closing", "recap", "final_summary"}
            ]
            transcript = join_with_budget(
                [f"{item['speaker']}: {item['content']}" for item in messages[-80:]],
                total_limit=120000,
                item_limit=6000,
                label="digest transcript turn",
            )
            user_content = f"""Topic: {session['topic']}
Current Topic Digest: {json.dumps(session.get('topic_digest') or {}, ensure_ascii=False)}
Requested focus: {focus or 'the full conversation'}

Transcript:
{transcript}"""
            adapter = self._digest_adapter()
            request = GenerationRequest(
                system=DIGEST_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                max_output_tokens=self.settings.conversation_digest_max_output_tokens,
                reasoning_effort="medium",
                verbosity="medium",
            )
            self.db.update_job(job_id, progress=0.35, detail="Synthesizing conversation")
            async with asyncio.timeout(self.settings.digest_job_timeout):
                raw = await adapter.generate(request)
            digest = parse_json_object(raw)
            if not digest:
                digest = {
                    "active_question": session.get("active_question") or session["topic"],
                    "positions": {"momo": "", "bobby": "", "sam": ""},
                    "agreements": [],
                    "disagreements": [],
                    "source_supported_claims": [],
                    "model_knowledge_claims": [],
                    "inferences": [],
                    "speculations": [],
                    "resolved_questions": [],
                    "open_questions": [],
                    "sam_directions": [],
                    "next_directions": [],
                    "visible_recap": raw,
                }
            completed_rounds = session["completed_rounds"]
            self.db.update_session(
                session_id,
                conversation_digest=digest,
                digested_through_round=completed_rounds,
            )
            digest_kind = "requested" if focus else ("periodic" if visible else "automatic")
            self.db.add_summary_digest(session_id, digest_kind, completed_rounds, digest)
            if visible:
                recap = str(digest.get("visible_recap") or raw).strip()
                self.db.add_message(
                    session_id,
                    "System",
                    recap,
                    metadata={"kind": "recap", "through_round": completed_rounds},
                )
            self.db.update_job(job_id, status="complete", progress=1.0, detail="Conversation digest ready")
        except Exception as exc:  # background boundary
            self.db.update_job(job_id, status="failed", error=str(exc)[:500], detail="Digest failed")

    async def run_final_summary(self, job_id: str, session_id: str) -> None:
        # A close request may arrive while an AI segment is still unwinding.
        # Waiting for the session lock ensures interrupted text is persisted before
        # the final summary snapshots messages and digest history.
        async with self._lock(session_id):
            await self._run_final_summary_locked(job_id, session_id)

    async def _run_final_summary_locked(self, job_id: str, session_id: str) -> None:
        self.db.update_job(job_id, status="running", progress=0.1, detail="Collecting summary history")
        try:
            session = self.db.get_session(session_id)
            history = self.db.list_summary_digests(session_id)
            if history:
                digest_text = join_with_budget(
                    [
                        f"Digest {index + 1} ({item['kind']}, through round {item['through_round']}):\n"
                        f"{json.dumps(item['digest'], ensure_ascii=False)}"
                        for index, item in enumerate(history)
                    ],
                    total_limit=140000,
                    item_limit=12000,
                    label="summary digest",
                )
                recent = self.db.recent_round_messages(
                    session_id, self.settings.recent_round_count
                )
                if recent:
                    recent_text = join_with_budget(
                        [f"{item['speaker']}: {item['content']}" for item in recent],
                        total_limit=48000,
                        item_limit=4000,
                        label="recent final-summary turn",
                    )
                    digest_text += "\n\nMost recent substantive turns (may overlap the latest digest):\n" + recent_text
            else:
                messages = [
                    item for item in self.db.list_messages(session_id)
                    if (item.get("metadata") or {}).get("kind")
                    not in {"greeting", "session_opening", "closing", "recap", "final_summary"}
                ]
                digest_text = "No earlier digest exists. Use this substantive transcript:\n\n" + join_with_budget(
                    [f"{item['speaker']}: {item['content']}" for item in messages],
                    total_limit=140000,
                    item_limit=6000,
                    label="final-summary transcript turn",
                )
            request = GenerationRequest(
                system=FINAL_SUMMARY_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Topic: {session['topic']}\nLearning goal: {session['learning_goal']}\n\n{digest_text}",
                }],
                max_output_tokens=self.settings.conversation_digest_max_output_tokens,
                reasoning_effort="medium",
                verbosity="medium",
            )
            self.db.update_job(job_id, progress=0.4, detail="Writing final summary")
            async with asyncio.timeout(self.settings.digest_job_timeout):
                summary = (await self._digest_adapter().generate(request)).strip()
            final_digest = {"status": "final", "visible_recap": summary}
            self.db.add_summary_digest(
                session_id, "final", session["completed_rounds"], final_digest
            )
            self.db.add_message(
                session_id,
                "System",
                summary,
                metadata={"kind": "final_summary", "through_round": session["completed_rounds"]},
            )
            await self._run_one_page_summary_locked(session_id, summary, digest_text, job_id=None)
            self.db.update_session(session_id, state="CLOSED")
            self.db.update_job(job_id, status="complete", progress=1.0, detail="Final summary ready")
        except Exception as exc:
            existing_final = next(
                (
                    item for item in self.db.list_messages(session_id)
                    if (item.get("metadata") or {}).get("kind") == "final_summary"
                ),
                None,
            )
            if not existing_final:
                session = self.db.get_session(session_id)
                history = self.db.list_summary_digests(session_id)
                latest = history[-1]["digest"] if history else (session.get("conversation_digest") or {})
                lines = ["# Final summary", ""]
                field_labels = (
                    ("active_question", "Central question"),
                    ("agreements", "Principal agreements"),
                    ("disagreements", "Principal disagreements"),
                    ("resolved_questions", "Conclusions"),
                    ("open_questions", "Remaining questions"),
                    ("sam_directions", "Sam's directions"),
                )
                for field, label in field_labels:
                    value = latest.get(field)
                    if not value:
                        continue
                    rendered = "\n".join(f"- {item}" for item in value) if isinstance(value, list) else str(value)
                    lines.extend([f"## {label}", "", rendered, ""])
                if len(lines) == 2:
                    lines.extend([
                        "The session concluded before a structured digest was available. The complete transcript is preserved in the session export.",
                    ])
                fallback = "\n".join(lines).strip()
                final_digest = {"status": "final", "visible_recap": fallback, "fallback": True}
                self.db.add_summary_digest(
                    session_id, "final", session["completed_rounds"], final_digest
                )
                self.db.add_message(
                    session_id,
                    "System",
                    fallback,
                    metadata={"kind": "final_summary", "through_round": session["completed_rounds"], "fallback": True},
                )
                await self._run_one_page_summary_locked(
                    session_id,
                    fallback,
                    f"Final summary fallback:\n\n{fallback}",
                    job_id=None,
                )
                self.db.update_session(session_id, state="CLOSED")
            self.db.update_job(
                job_id,
                status="complete",
                progress=1.0,
                error=str(exc)[:500],
                detail="Final summary ready using retained digest fallback",
            )

    async def _run_one_page_summary_locked(
        self,
        session_id: str,
        final_summary: str,
        digest_text: str,
        job_id: str | None = None,
    ) -> None:
        session = self.db.get_session(session_id)
        if not session:
            return
        one_page_job_id = job_id
        if one_page_job_id is None:
            one_page_job = self.db.create_job(session_id, "one_page_summary", {})
            one_page_job_id = one_page_job["id"]
        self.db.update_job(
            one_page_job_id,
            status="running",
            progress=0.1,
            detail="Assembling one-page summary source",
        )
        try:
            source_token_multiplier, source_timeout_multiplier = self._source_boosts(session_id)
            background_and_inferences = digest_text
            summary_prompt = (
                f"Topic: {session['topic']}\nLearning goal: {session['learning_goal']}\n\n"
                f"Final summary:\n{final_summary}\n\n"
                f"Digest context (background knowledge, inferences, and open questions included):\n{background_and_inferences}"
            )
            persona = PERSONAS["Momo"]
            system = "\n\n".join(
                [
                    persona,
                    ONE_PAGE_SUMMARY_SYSTEM_PROMPT,
                    self.momo_one_page_summary_skill,
                ]
            )
            request = GenerationRequest(
                system=system,
                messages=[{"role": "user", "content": summary_prompt}],
                max_output_tokens=self._scaled_tokens(
                    self.settings.conversation_digest_max_output_tokens, source_token_multiplier
                ),
                reasoning_effort="medium",
                verbosity="low",
            )
            self.db.update_job(one_page_job_id, progress=0.45, detail="Writing one-page summary")
            async with asyncio.timeout(
                self._scaled_timeout(self.settings.digest_job_timeout, source_timeout_multiplier)
            ):
                one_page_summary = (await self.adapters.get("Momo").generate(request)).strip()
            one_page_summary = one_page_summary or final_summary
            self.db.add_summary_digest(
                session_id,
                "one_page",
                session["completed_rounds"],
                {"content": one_page_summary},
            )
            self.db.update_job(one_page_job_id, status="complete", progress=1.0, detail="One-page summary ready")
        except Exception as exc:
            fallback = "\n\n".join([
                "## Key concepts",
                "- Core topic-level concepts are preserved in the session transcript and final summary.",
                "## Main issues",
                "- The main unresolved questions remain in the final summary.",
                "## Strategies to solve key problems",
                "- Continue with one focused validation cycle against source evidence and explicit uncertainty points.",
                "## Research priorities",
                "- Prioritize a repeatable comparison run between the final competing explanations.",
            ])
            if one_page_job_id:
                self.db.add_summary_digest(
                    session_id,
                    "one_page",
                    session["completed_rounds"],
                    {"content": fallback},
                )
                self.db.update_job(
                    one_page_job_id,
                    status="complete",
                    progress=1.0,
                    detail="One-page summary created from fallback",
                    error=str(exc)[:500],
                )

    async def run_topic_digest(self, job_id: str, session_id: str) -> None:
        self.db.update_job(job_id, status="running", progress=0.1, detail="Collecting topic context")
        try:
            session = self.db.get_session(session_id)
            messages = self.db.list_messages(session_id)
            messages = [
                item for item in messages
                if (item.get("metadata") or {}).get("kind")
                not in {"greeting", "session_opening", "closing", "recap", "final_summary"}
            ]
            documents = self.db.list_documents(session_id)
            source_summaries = join_with_budget(
                [f"{doc['filename']}: {doc['digest']}" for doc in documents if doc.get("digest")],
                total_limit=100000,
                item_limit=20000,
                label="document digest",
            ) or "No source digests are available."
            transcript = join_with_budget(
                [f"{item['speaker']}: {item['content']}" for item in messages[-30:]],
                total_limit=60000,
                item_limit=5000,
                label="topic-digest transcript turn",
            )
            content = f"""Topic: {session['topic']}
Learning goal: {session['learning_goal']}

Recent discussion:
{transcript}

Source summaries:
{source_summaries}"""
            request = GenerationRequest(
                system=TOPIC_DIGEST_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                max_output_tokens=self.settings.topic_digest_max_output_tokens,
                reasoning_effort="medium",
                verbosity="medium",
            )
            self.db.update_job(job_id, progress=0.4, detail="Synthesizing topic")
            async with asyncio.timeout(self.settings.digest_job_timeout):
                raw = await self._digest_adapter().generate(request)
            digest = parse_json_object(raw)
            if not digest:
                raise ValueError("Topic digest was not valid JSON")
            digest["status"] = "developed"
            self.db.update_session(session_id, topic_digest=digest)
            self.db.update_job(job_id, status="complete", progress=1.0, detail="Topic digest ready")
        except Exception as exc:
            self.db.update_job(job_id, status="failed", error=str(exc)[:500], detail="Topic digest failed")

    async def run_document_digest(self, job_id: str, document_id: str) -> None:
        document = self.db.get_document(document_id)
        if not document:
            return
        self.db.update_document(document_id, status="processing", error=None)
        self.db.update_job(job_id, status="running", progress=0.05, detail="Extracting document")
        try:
            path = Path(document["stored_path"])
            passages = await asyncio.to_thread(extract_passages, path)
            if not passages:
                raise ValueError("No extractable text was found")
            self.db.replace_passages(document_id, document["filename"], passages)
            groups = group_passages_for_digest(passages)
            section_digests: list[str] = []
            adapter = self._digest_adapter()
            for index, group in enumerate(groups):
                self.db.update_job(
                    job_id,
                    progress=0.1 + 0.65 * (index / max(1, len(groups))),
                    detail=f"Digesting section {index + 1} of {len(groups)}",
                )
                request = GenerationRequest(
                    system=SOURCE_DIGEST_SYSTEM_PROMPT,
                    messages=[
                        {
                            "role": "user",
                            "content": format_passage_group(group, document["filename"]),
                        }
                    ],
                    max_output_tokens=self.settings.source_digest_max_output_tokens,
                    reasoning_effort="medium",
                    verbosity="high",
                )
                async with asyncio.timeout(self.settings.digest_section_timeout):
                    section_digests.append(await adapter.generate(request))
            self.db.update_job(job_id, progress=0.8, detail="Creating document synthesis")
            synthesis_input = join_with_budget(
                section_digests,
                total_limit=120000,
                item_limit=20000,
                label="source section digest",
                separator="\n\n---\n\n",
            )
            synthesis_request = GenerationRequest(
                system=SOURCE_DIGEST_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": "Create a unified document-level synthesis from these faithful section digests:\n\n"
                        + synthesis_input,
                    }
                ],
                max_output_tokens=self.settings.source_digest_max_output_tokens,
                reasoning_effort="medium",
                verbosity="high",
            )
            async with asyncio.timeout(self.settings.digest_job_timeout):
                digest = await adapter.generate(synthesis_request)
            self.db.update_document(document_id, status="ready", digest=digest)
            self.db.update_job(job_id, status="complete", progress=1.0, detail="Document ready")
            topic_job = self.db.create_job(
                document["session_id"], "topic_digest", {"source_document": document_id}
            )
            self._spawn(
                self.run_topic_digest(topic_job["id"], document["session_id"]),
                document["session_id"],
            )
        except Exception as exc:
            self.db.update_document(document_id, status="failed", error=str(exc)[:500])
            self.db.update_job(job_id, status="failed", error=str(exc)[:500], detail="Document digestion failed")
