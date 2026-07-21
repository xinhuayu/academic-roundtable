#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import OrderedDict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode


BASE_URL = "http://127.0.0.1:8765"
TIMEOUT_SECONDS = 180
ROUNDTABLE_DIR = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the live Academic Roundtable API audit.")
    parser.add_argument(
        "--pdf",
        required=True,
        type=Path,
        help="Path to a PDF that the user has approved for transmission to configured providers.",
    )
    return parser.parse_args()


def _truncate(text: str, limit: int = 600) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... (+{len(text)-limit} chars)"


def _pretty(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), indent=None)


def request_json(
    method: str,
    path: str,
    payload=None,
    timeout: int = 30,
    headers=None,
    parse_json: bool = True,
):
    if headers is None:
        headers = {}
    url = f"{BASE_URL}{path}"
    body = None
    if payload is not None:
        if isinstance(payload, (dict, list)):
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            body = encoded
            headers = {"Content-Type": "application/json", **headers}
        elif isinstance(payload, (bytes, bytearray)):
            body = payload
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
    req = Request(url, data=body, method=method)
    req.add_header("User-Agent", "academic-roundtable-audit/1.0")
    for key, value in headers.items():
        req.add_header(key, value)
    started = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 0)
            text = raw.decode("utf-8", errors="replace")
            result = json.loads(text) if (parse_json and text) else (text if text else None)
            return {
                "status": status,
                "seconds": round(time.perf_counter() - started, 3),
                "bytes": len(raw),
                "json": result,
                "raw": raw,
            }
    except HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        if parse_json:
            try:
                result = json.loads(text)
            except Exception:
                result = {"error": text}
        else:
            result = text
        return {
            "status": exc.code,
            "seconds": round(time.perf_counter() - started, 3),
            "bytes": len(raw),
            "json": result,
            "raw": raw,
        }
    except URLError as exc:
        return {
            "status": 0,
            "seconds": round(time.perf_counter() - started, 3),
            "bytes": 0,
            "json": {"error": str(exc)},
            "raw": b"",
        }


def request_streaming_segments(session_id: str, payload: dict) -> dict:
    req = Request(
        f"{BASE_URL}/api/sessions/{session_id}/segments",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream")
    req.add_header("User-Agent", "academic-roundtable-audit/1.0")
    start = time.perf_counter()
    first_chunk = None
    events = 0
    received_bytes = 0
    chars = 0
    host_invited = 0
    provider_errors = []
    deltas = 0
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                received_bytes += len(line)
                decoded = line.decode("utf-8", errors="ignore").strip()
                if not decoded.startswith("data:"):
                    continue
                payload_text = decoded[5:].strip()
                if not payload_text:
                    continue
                if first_chunk is None:
                    first_chunk = time.perf_counter() - start
                events += 1
                try:
                    event = json.loads(payload_text)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type == "delta":
                    deltas += 1
                    chars += len(event.get("text", ""))
                elif event_type == "host_invited":
                    host_invited += 1
                elif event_type == "provider_error":
                    provider_errors.append(
                        {"speaker": event.get("speaker"), "message": event.get("message")}
                    )
    except HTTPError as exc:
        return {
            "status": exc.code,
            "seconds": round(time.perf_counter() - start, 3),
            "bytes": 0,
            "first_chunk_seconds": None,
            "events": 0,
            "deltas": 0,
            "chars": 0,
            "host_invited": 0,
            "provider_errors": [{"speaker": "system", "message": str(exc)}],
        }
    except URLError:
        return {
            "status": 0,
            "seconds": round(time.perf_counter() - start, 3),
            "bytes": 0,
            "first_chunk_seconds": None,
            "events": 0,
            "deltas": 0,
            "chars": 0,
            "host_invited": 0,
            "provider_errors": [{"speaker": "system", "message": "stream_connect_failed"}],
        }
    return {
        "status": 200,
        "seconds": round(time.perf_counter() - start, 3),
        "bytes": received_bytes,
        "first_chunk_seconds": None if first_chunk is None else round(first_chunk, 3),
        "events": events,
        "deltas": deltas,
        "chars": chars,
        "host_invited": host_invited,
        "provider_errors": provider_errors,
    }


def build_multipart(path: Path) -> tuple[bytes, str]:
    boundary = f"----audit{int(time.time() * 1000)}"
    data = []
    with path.open("rb") as handle:
        file_bytes = handle.read()
    data.append(f"--{boundary}\r\n".encode("utf-8"))
    data.append(
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(
            "utf-8"
        )
    )
    data.append(b"Content-Type: application/pdf\r\n\r\n")
    data.append(file_bytes)
    data.append(b"\r\n")
    data.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(data), f"multipart/form-data; boundary={boundary}"


def upload_document(session_id: str, file_path: Path) -> dict:
    body, ctype = build_multipart(file_path)
    req = Request(
        f"{BASE_URL}/api/sessions/{session_id}/documents",
        data=body,
        method="POST",
    )
    req.add_header("Content-Type", ctype)
    req.add_header("User-Agent", "academic-roundtable-audit/1.0")
    started = time.perf_counter()
    try:
        with urlopen(req, timeout=180) as response:
            raw = response.read()
            text = raw.decode("utf-8", errors="replace")
            return {
                "status": getattr(response, "status", 0),
                "seconds": round(time.perf_counter() - started, 3),
                "bytes": len(raw),
                "json": json.loads(text) if text else None,
                "raw": raw,
            }
    except HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"error": text}
        return {
            "status": exc.code,
            "seconds": round(time.perf_counter() - started, 3),
            "bytes": len(raw),
            "json": parsed,
            "raw": raw,
        }
    except URLError as exc:
        return {
            "status": 0,
            "seconds": round(time.perf_counter() - started, 3),
            "bytes": 0,
            "json": {"error": str(exc)},
            "raw": b"",
        }


def wait_for_job(job_id: str, max_checks: int = 120, interval: float = 1.0) -> dict:
    started = time.perf_counter()
    last = None
    for _ in range(max_checks):
        poll = request_json("GET", f"/api/jobs/{job_id}", timeout=25)
        payload = poll.get("json") or {}
        status = payload.get("status")
        if not isinstance(payload, dict):
            return {"status": "invalid_response", "poll": poll}
        if status in {"complete", "failed", "cancelled"}:
            return {
                "final": payload,
                "elapsed": round(time.perf_counter() - started, 3),
                "bytes": poll["bytes"],
                "status_code": poll["status"],
            }
        last = {"status": status, "poll": poll}
        time.sleep(interval)
    return {"status": "timeout", "poll": last}


def start_backend() -> subprocess.Popen[bytes]:
    python = str(ROUNDTABLE_DIR / ".venv" / "Scripts" / "python.exe")
    cmd = [
        python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        "backend",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]
    log = ROUNDTABLE_DIR / "tmp_server.log"
    err = ROUNDTABLE_DIR / "tmp_server.err"
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROUNDTABLE_DIR),
        stdout=log.open("wb"),
        stderr=err.open("wb"),
    )
    for _ in range(120):
        health = request_json("GET", "/api/health", timeout=2)
        if health["status"] == 200:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Backend failed to reach readiness")
    if proc.poll() is not None:
        error_out = log.read_text(encoding="utf-8", errors="ignore")
        err_out = err.read_text(encoding="utf-8", errors="ignore")
        raise RuntimeError(f"Backend process exited early: {error_out} / {err_out}")
    return proc


def stop_backend(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def print_result(name: str, result: dict) -> None:
    print(f"\n[{name}]")
    if "status" in result:
        print(f"status={result['status']} seconds={result['seconds']} bytes={result['bytes']}")
    if "json" in result:
        print(_truncate(_pretty(result["json"])))
    if "error" in result:
        print(_truncate(_pretty(result["error"])))


def main() -> int:
    pdf_path = parse_args().pdf.expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    proc: subprocess.Popen[bytes] | None = None
    metrics = OrderedDict()
    try:
        existing = request_json("GET", "/api/health", timeout=3)
        if existing["status"] == 200:
            metrics["backend_started"] = "reused_running_server"
        else:
            proc = start_backend()
            metrics["backend_started"] = "started_by_audit"

        meta = request_json("GET", "/api/meta", timeout=30)
        metrics["meta"] = {"status": meta["status"], "seconds": meta["seconds"], "bytes": meta["bytes"]}
        if meta["status"] != 200:
            print_result("meta", meta)
            return 1

        deps = request_json("GET", "/api/documents/dependencies", timeout=30)
        metrics["dependency_check"] = {
            "status": deps["status"],
            "seconds": deps["seconds"],
            "body": deps["json"],
        }

        create = request_json(
            "POST",
            "/api/sessions",
            payload={
                "topic": "Cognitive trajectories and subsequent health status",
                "learning_goal": "Evaluate mechanisms linking cognitive change and health across longitudinal evidence.",
                "rounds_per_segment": 2,
                "sources_only": True,
                "periodic_summary": True,
                "force_reset": True,
            },
            timeout=40,
        )
        metrics["create_session"] = {"status": create["status"], "seconds": create["seconds"], "bytes": create["bytes"]}
        if create["status"] != 201:
            print_result("create_session", create)
            return 1
        session = create["json"]
        session_id = session["id"]

        conflict = request_json(
            "POST",
            "/api/sessions",
            payload={
                "topic": "Cognitive trajectories test duplicate",
                "learning_goal": "Should reject duplicate without reset.",
                "rounds_per_segment": 2,
                "sources_only": True,
                "periodic_summary": True,
            },
            timeout=20,
        )
        metrics["create_session_conflict"] = {
            "status": conflict["status"],
            "seconds": conflict["seconds"],
            "bytes": conflict["bytes"],
            "expected": 409,
        }
        reset = request_json(
            "POST",
            "/api/sessions",
            payload={
                "topic": "Cognitive trajectories and subsequent health status",
                "learning_goal": "Evaluate mechanisms linking cognitive change and health across longitudinal evidence.",
                "rounds_per_segment": 2,
                "sources_only": True,
                "periodic_summary": True,
                "force_reset": True,
            },
            timeout=40,
        )
        metrics["create_session_after_reset"] = {
            "status": reset["status"],
            "seconds": reset["seconds"],
            "bytes": reset["bytes"],
        }
        if reset["status"] != 201:
            print_result("create_session_after_reset", reset)
            return 1
        session = reset["json"]
        session_id = session["id"]

        upload = upload_document(session_id, pdf_path)
        metrics["upload_pdf"] = {
            "status": upload["status"],
            "seconds": upload["seconds"],
            "bytes": upload["bytes"],
        }
        if upload["status"] not in {200, 202}:
            print_result("upload_pdf", upload)
            return 1
        upload_job = upload["json"]["job"]["id"]
        doc_job = wait_for_job(upload_job, max_checks=180, interval=1)
        metrics["document_digest"] = {
            "status": doc_job["final"]["status"],
            "seconds": doc_job["elapsed"],
            "bytes": doc_job["bytes"],
        }

        start_msg = request_json(
            "POST",
            f"/api/sessions/{session_id}/messages",
            payload={
                "content": "Let's start with definitions around cognitive trajectories and subsequent health status.",
                "target": "roundtable",
            },
            timeout=30,
        )
        metrics["start_message"] = {
            "status": start_msg["status"],
            "seconds": start_msg["seconds"],
            "bytes": start_msg["bytes"],
        }
        if start_msg["status"] != 200:
            print_result("start_message", start_msg)
            return 1

        segment = request_streaming_segments(session_id, payload={"rounds": 2})
        metrics["segment_1"] = segment
        if segment["status"] != 200:
            print("segment_1 failed", segment["provider_errors"])
            return 1

        direct = request_json(
            "POST",
            f"/api/sessions/{session_id}/messages",
            payload={
                "content": "Bobby, challenge the assumptions behind the directional interpretation.",
                "target": "Bobby",
            },
            timeout=30,
        )
        metrics["targeted_bobby_message"] = {
            "status": direct["status"],
            "seconds": direct["seconds"],
            "bytes": direct["bytes"],
        }
        if direct["status"] == 200:
            segment_b = request_streaming_segments(session_id, payload={"rounds": 2})
            metrics["segment_2"] = segment_b

        recap = request_json(
            "POST",
            f"/api/sessions/{session_id}/recap",
            payload={"focus": "summarize the current evidence-grounded mechanism dispute"},
            timeout=30,
        )
        metrics["start_recap"] = {
            "status": recap["status"],
            "seconds": recap["seconds"],
            "bytes": recap["bytes"],
        }
        if recap["status"] in {200, 202}:
            recap_job = recap["json"]["id"]
            recap_result = wait_for_job(recap_job, max_checks=180, interval=1)
            metrics["recap_job"] = {
                "status": recap_result["final"]["status"],
                "seconds": recap_result["elapsed"],
                "bytes": recap_result["bytes"],
            }

        close = request_json("POST", f"/api/sessions/{session_id}/close", timeout=30)
        metrics["close"] = {"status": close["status"], "seconds": close["seconds"], "bytes": close["bytes"]}

        for _ in range(240):
            jobs = request_json("GET", f"/api/sessions/{session_id}/jobs", timeout=15)
            if jobs["status"] != 200:
                time.sleep(0.5)
                continue
            finals = {
                item.get("kind"): item.get("status")
                for item in jobs["json"]
                if isinstance(item, dict) and item.get("kind") in {"final_summary", "one_page_summary"}
            }
            if finals.get("final_summary") in {"complete", "failed", "cancelled"} and finals.get(
                "one_page_summary"
            ) in {"complete", "failed", "cancelled"}:
                break
            time.sleep(1)
        metrics["post_close_jobs"] = jobs["json"] if jobs["status"] == 200 else None

        session_export = request_json(
            "GET",
            f"/api/sessions/{session_id}/export?format=markdown",
            timeout=60,
            parse_json=False,
        )
        metrics["export_markdown"] = {
            "status": session_export["status"],
            "seconds": session_export["seconds"],
            "bytes": session_export["bytes"],
            "head": _truncate(session_export["raw"].decode("utf-8", errors="replace")[:400]),
        }

        one_page = request_json(
            "GET",
            f"/api/sessions/{session_id}/export?format=one_page_summary",
            timeout=60,
            parse_json=False,
        )
        metrics["export_one_page"] = {
            "status": one_page["status"],
            "seconds": one_page["seconds"],
            "bytes": one_page["bytes"],
        }

        final_view = request_json("GET", f"/api/sessions/{session_id}", timeout=30)
        if final_view["status"] == 200:
            messages = final_view["json"].get("messages", [])
            substantive_ai = [
                item for item in messages
                if item.get("speaker") in {"Momo", "Bobby"}
                and (item.get("metadata") or {}).get("kind") not in {"greeting", "closing"}
            ]
            summary_history = final_view["json"].get("summary_history", [])
            metrics["final_session_state"] = {
                "state": final_view["json"].get("state"),
                "summary_kinds": sorted(
                    {
                        item.get("kind")
                        for item in final_view["json"].get("summary_history", [])
                        if isinstance(item, dict)
                    }
                ),
                "messages": len(messages),
                "jobs": len(final_view["json"].get("jobs", [])),
            }
            metrics["output_sizes"] = {
                "substantive_ai_messages": len(substantive_ai),
                "ai_message_chars": [len(str(item.get("content") or "")) for item in substantive_ai],
                "document_digest_chars": [
                    len(str(item.get("digest") or ""))
                    for item in final_view["json"].get("documents", [])
                ],
                "topic_digest_json_chars": len(
                    json.dumps(final_view["json"].get("topic_digest") or {}, ensure_ascii=False)
                ),
                "summary_digest_json_chars": [
                    {
                        "kind": item.get("kind"),
                        "chars": len(json.dumps(item.get("digest") or {}, ensure_ascii=False)),
                    }
                    for item in summary_history
                ],
            }
            metrics["source_evidence_present"] = bool(
                final_view["json"].get("topic_digest", {}).get("source_boundaries")
            )

        print("\n=== AUDIT SUMMARY ===")
        for key, value in metrics.items():
            print(f"{key}: {value}")
        return 0
    finally:
        if proc is not None:
            stop_backend(proc)


if __name__ == "__main__":
    raise SystemExit(main())

