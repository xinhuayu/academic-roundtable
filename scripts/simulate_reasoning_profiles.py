#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Fast, Research, and Verification profiles on one approved PDF."
    )
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--rounds", type=int, default=2, choices=range(2, 6))
    parser.add_argument(
        "--session-id",
        help="Reuse an existing source-grounded session and skip create/upload/digestion.",
    )
    return parser.parse_args()


def request_json(base_url: str, method: str, path: str, payload=None, timeout: int = 60):
    body = None
    headers = {"User-Agent": "roundtable-profile-simulation/1.0"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=body, method=method, headers=headers)
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return {
                "status": response.status,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "body": json.loads(raw.decode("utf-8")) if raw else None,
            }
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc


def upload_pdf(base_url: str, session_id: str, pdf_path: Path):
    boundary = f"----profile-simulation-{time.time_ns()}"
    file_bytes = pdf_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{pdf_path.name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = Request(
        f"{base_url}/api/sessions/{session_id}/documents",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "roundtable-profile-simulation/1.0",
        },
    )
    started = time.perf_counter()
    with urlopen(request, timeout=180) as response:
        raw = response.read()
        return {
            "status": response.status,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "body": json.loads(raw.decode("utf-8")),
        }


def wait_for_job(base_url: str, job_id: str, timeout_seconds: int = 1800):
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_seconds:
        job = request_json(base_url, "GET", f"/api/jobs/{job_id}", timeout=30)["body"]
        if job["status"] in {"complete", "failed", "cancelled", "interrupted"}:
            return job, round(time.perf_counter() - started, 3)
        time.sleep(1)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_seconds} seconds")


def wait_for_topic_digest(base_url: str, session_id: str, timeout_seconds: int = 900):
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_seconds:
        view = request_json(base_url, "GET", f"/api/sessions/{session_id}", timeout=30)["body"]
        if (view.get("topic_digest") or {}).get("status") == "developed":
            return view, round(time.perf_counter() - started, 3)
        failed = [
            job for job in view.get("jobs", [])
            if job.get("kind") == "topic_digest" and job.get("status") == "failed"
        ]
        if failed:
            raise RuntimeError(f"Topic digest failed: {failed[-1].get('error')}")
        time.sleep(1)
    raise TimeoutError("Topic digest did not finish")


def stream_segment(base_url: str, session_id: str, rounds: int, starting_speaker: str):
    request = Request(
        f"{base_url}/api/sessions/{session_id}/segments",
        data=json.dumps({
            "rounds": rounds,
            "starting_speaker": starting_speaker,
            "continue_without_sam": True,
        }).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "roundtable-profile-simulation/1.0",
        },
    )
    started = time.perf_counter()
    first_event = None
    first_delta = None
    first_delta_by_speaker: dict[str, float] = {}
    starts: list[dict] = []
    messages: list[dict] = []
    provider_errors: list[dict] = []
    received_bytes = 0
    with urlopen(request, timeout=1800) as response:
        while True:
            line = response.readline()
            if not line:
                break
            received_bytes += len(line)
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded.startswith("data:"):
                continue
            event = json.loads(decoded[5:].strip())
            elapsed = time.perf_counter() - started
            if first_event is None:
                first_event = elapsed
            if event.get("type") == "message_start":
                starts.append({
                    "speaker": event.get("speaker"),
                    "profile": event.get("profile"),
                    "model": event.get("model"),
                    "reasoning_effort": event.get("reasoning_effort"),
                    "source_verification": bool(event.get("source_verification")),
                })
            elif event.get("type") == "delta":
                speaker = str(event.get("speaker"))
                if first_delta is None:
                    first_delta = elapsed
                first_delta_by_speaker.setdefault(speaker, elapsed)
            elif event.get("type") == "message_complete":
                message = event.get("message") or {}
                content = str(message.get("content") or "")
                messages.append({
                    "speaker": message.get("speaker"),
                    "characters": len(content),
                    "words": len(content.split()),
                    "status": message.get("status"),
                    "preview": content[:220].replace("\n", " "),
                })
            elif event.get("type") == "provider_error":
                provider_errors.append({
                    "speaker": event.get("speaker"),
                    "message": event.get("message"),
                    "partial": bool(event.get("partial")),
                })
    return {
        "total_seconds": round(time.perf_counter() - started, 3),
        "first_event_seconds": None if first_event is None else round(first_event, 3),
        "first_delta_seconds": None if first_delta is None else round(first_delta, 3),
        "first_delta_by_speaker": {
            key: round(value, 3) for key, value in first_delta_by_speaker.items()
        },
        "sse_bytes": received_bytes,
        "routing": starts,
        "messages": messages,
        "provider_errors": provider_errors,
    }


def main() -> int:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pdf_path = args.pdf.expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    health = request_json(args.base_url, "GET", "/api/health", timeout=30)["body"]
    if health.get("status") != "ok" or not all(
        provider.get("reachable") for provider in health.get("providers", [])
    ):
        raise RuntimeError(f"Providers are not ready: {health}")

    if args.session_id:
        session_id = args.session_id
        source_view = request_json(
            args.base_url, "GET", f"/api/sessions/{session_id}", timeout=60
        )["body"]
        if not source_view.get("documents") or source_view["documents"][0].get("status") != "ready":
            raise RuntimeError("Reused session does not have a ready source document")
        upload = {"elapsed_seconds": 0.0}
        document_seconds = 0.0
        topic_seconds = 0.0
    else:
        create = request_json(
            args.base_url,
            "POST",
            "/api/sessions",
            payload={
                "topic": "Cognitive trajectories and subsequent health status",
                "learning_goal": (
                    "Evaluate the statistical identification, trajectory modeling, attrition, "
                    "and causal interpretation of the uploaded longitudinal study."
                ),
                "rounds_per_segment": args.rounds,
                "sources_only": False,
                "periodic_summary": False,
                "conversation_profile": "fast",
                "force_reset": True,
            },
            timeout=60,
        )
        session_id = create["body"]["id"]
        upload = upload_pdf(args.base_url, session_id, pdf_path)
        document_job, document_seconds = wait_for_job(
            args.base_url, upload["body"]["job"]["id"], timeout_seconds=1800
        )
        if document_job["status"] != "complete":
            raise RuntimeError(f"Document digestion did not complete: {document_job}")
        source_view, topic_seconds = wait_for_topic_digest(args.base_url, session_id)

    prompts = {
        "fast": (
            "Momo, establish the paper's principal estimands and distinguish observed "
            "cognitive trajectory groups from causal latent types. Keep the exchange concise."
        ),
        "research": (
            "Momo, now examine the paper's trajectory-model uncertainty, informative attrition, "
            "time-varying confounding, and whether the reported health associations support causal interpretation."
        ),
        "verification": (
            "Momo, check the original PDF and verify the strongest numerical or methodological claim "
            "behind the trajectory-health association. Identify any mismatch between the original document "
            "and our digest, then have Bobby challenge the verification."
        ),
    }
    profiles: dict[str, dict] = {}
    for profile, prompt in prompts.items():
        patch = request_json(
            args.base_url,
            "PATCH",
            f"/api/sessions/{session_id}",
            payload={"conversation_profile": profile},
            timeout=30,
        )
        message = request_json(
            args.base_url,
            "POST",
            f"/api/sessions/{session_id}/messages",
            payload={"content": prompt, "target": "Momo", "continue_rounds": args.rounds},
            timeout=30,
        )
        profiles[profile] = {
            "profile_patch_seconds": patch["elapsed_seconds"],
            "sam_message_seconds": message["elapsed_seconds"],
            "segment": stream_segment(args.base_url, session_id, args.rounds, "Momo"),
        }

    final_view = request_json(
        args.base_url, "GET", f"/api/sessions/{session_id}", timeout=60
    )["body"]
    report = {
        "session_id": session_id,
        "session_state": final_view.get("state"),
        "paper": {
            "filename": pdf_path.name,
            "bytes": pdf_path.stat().st_size,
            "upload_seconds": upload["elapsed_seconds"],
            "document_digest_seconds": document_seconds,
            "document_digest_characters": len(str(final_view["documents"][0].get("digest") or "")),
            "topic_digest_wait_seconds": topic_seconds,
            "topic_digest_characters": len(
                json.dumps(source_view.get("topic_digest") or {}, ensure_ascii=False)
            ),
        },
        "providers": health.get("providers"),
        "profiles": profiles,
        "completed_rounds": final_view.get("completed_rounds"),
        "final_profile": final_view.get("conversation_profile"),
        "note": "Session remains open for UI inspection; no final summary was requested.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
