from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from .config import ProviderConfig, Settings


class ProviderError(RuntimeError):
    def __init__(self, participant: str, kind: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.participant = participant
        self.kind = kind
        self.retryable = retryable


@dataclass
class GenerationRequest:
    system: str
    messages: list[dict[str, str]]
    max_output_tokens: int
    reasoning_effort: str | None = None
    verbosity: str = "medium"


class LLMAdapter:
    def __init__(self, config: ProviderConfig):
        self.config = config
        timeout = httpx.Timeout(
            connect=config.connect_timeout,
            read=config.stream_idle_timeout,
            write=30.0,
            pool=10.0,
        )
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers=self._auth_headers(config),
        )

    @staticmethod
    def _auth_headers(config: ProviderConfig) -> dict[str, str]:
        api_key = config.api_key
        if not api_key:
            return {}
        if config.api_style == "anthropic_messages":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": os.getenv("ANTHROPIC_API_VERSION", "2023-06-01"),
            }
            beta = os.getenv("ANTHROPIC_BETA_HEADER")
            if beta:
                headers["anthropic-beta"] = beta
            return headers
        return {"Authorization": f"Bearer {api_key}"}

    async def close(self) -> None:
        await self.client.aclose()

    def capabilities(self) -> dict[str, Any]:
        return {
            "participant": self.config.participant,
            "model": self.config.model,
            "api_style": self.config.api_style,
            "configured": self.config.configured,
            "streaming": True,
        }

    async def health_check(self) -> dict[str, Any]:
        result = self.capabilities()
        if not self.config.configured:
            return {**result, "reachable": False, "detail": "Missing endpoint, model, or API key"}
        try:
            response = await self.client.get("/models")
            response.raise_for_status()
            return {**result, "reachable": True, "detail": "Ready"}
        except httpx.HTTPStatusError as exc:
            return {
                **result,
                "reachable": False,
                "detail": f"Provider returned HTTP {exc.response.status_code}",
            }
        except httpx.HTTPError as exc:
            return {
                **result,
                "reachable": False,
                "detail": f"{exc.__class__.__name__}: {str(exc)}",
            }

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        if not self.config.configured:
            raise ProviderError(self.config.participant, "configuration", "Provider is not configured")
        if self.config.api_style == "responses":
            async for delta in self._stream_responses(request):
                yield delta
            return
        if self.config.api_style == "chat_completions":
            async for delta in self._stream_chat_completions(request):
                yield delta
            return
        if self.config.api_style == "anthropic_messages":
            async for delta in self._stream_anthropic_messages(request):
                yield delta
            return
        raise ProviderError(
            self.config.participant,
            "configuration",
            f"Unsupported API style: {self.config.api_style}",
        )

    async def generate(self, request: GenerationRequest) -> str:
        chunks: list[str] = []
        async for chunk in self.stream(request):
            chunks.append(chunk)
        return "".join(chunks).strip()

    async def _stream_responses(self, request: GenerationRequest) -> AsyncIterator[str]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "instructions": request.system,
            "input": request.messages,
            "stream": True,
            "max_output_tokens": request.max_output_tokens,
            "text": {"verbosity": request.verbosity},
        }
        effort = request.reasoning_effort or self.config.reasoning_effort
        if effort:
            body["reasoning"] = {"effort": effort}
        try:
            async with self.client.stream("POST", "/responses", json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type", "")
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta", "")
                        if delta:
                            yield delta
                    elif event_type in {"response.failed", "error"}:
                        error = event.get("error") or event.get("response", {}).get("error") or {}
                        message = error.get("message", "Response generation failed")
                        raise ProviderError(self.config.participant, "provider", message, retryable=True)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.config.participant, "timeout", "Provider timed out", True) from exc
        except httpx.HTTPStatusError as exc:
            detail = self._safe_http_error(exc.response)
            raise ProviderError(
                self.config.participant,
                "http",
                f"Provider returned HTTP {exc.response.status_code}: {detail}",
                exc.response.status_code in {408, 409, 429, 500, 502, 503, 504},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                self.config.participant,
                "connection",
                f"{exc.__class__.__name__}: {str(exc)}",
                True,
            ) from exc

    async def _stream_chat_completions(self, request: GenerationRequest) -> AsyncIterator[str]:
        body = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": request.system}, *request.messages],
            "stream": True,
            "max_tokens": request.max_output_tokens,
        }
        effort = request.reasoning_effort or self.config.reasoning_effort
        if effort:
            # OpenAI-compatible reasoning models, including Gemini 3, map this
            # standard field to their provider-specific thinking controls.
            body["reasoning_effort"] = effort
        try:
            finish_reason: str | None = None
            async with self.client.stream("POST", "/chat/completions", json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                        choice = event.get("choices", [{}])[0]
                        delta = choice.get("delta", {}).get("content", "")
                        if choice.get("finish_reason") is not None:
                            finish_reason = str(choice["finish_reason"]).lower()
                    except (json.JSONDecodeError, IndexError, AttributeError):
                        continue
                    if delta:
                        yield delta
            if finish_reason == "length":
                raise ProviderError(
                    self.config.participant,
                    "output_limit",
                    f"{self.config.participant} reached the generation limit before completing the response",
                    retryable=True,
                )
            if finish_reason not in {None, "stop"}:
                raise ProviderError(
                    self.config.participant,
                    "provider_finish",
                    f"{self.config.participant} stopped with provider finish reason: {finish_reason}",
                    retryable=False,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(self.config.participant, "timeout", "Provider timed out", True) from exc
        except httpx.HTTPStatusError as exc:
            detail = self._safe_http_error(exc.response)
            raise ProviderError(
                self.config.participant,
                "http",
                f"Provider returned HTTP {exc.response.status_code}: {detail}",
                exc.response.status_code in {408, 409, 429, 500, 502, 503, 504},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                self.config.participant,
                "connection",
                f"{exc.__class__.__name__}: {str(exc)}",
                True,
            ) from exc

    async def _stream_anthropic_messages(self, request: GenerationRequest) -> AsyncIterator[str]:
        body = {
            "model": self.config.model,
            "system": request.system,
            "messages": request.messages,
            "max_tokens": request.max_output_tokens,
            "stream": True,
        }
        finish_reason: str | None = None
        try:
            async with self.client.stream("POST", "/messages", json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type", "")
                    if event_type == "content_block_delta":
                        delta = event.get("delta", {}).get("text", "")
                        if delta:
                            yield delta
                        continue
                    if event_type == "message_delta":
                        reason = event.get("delta", {}).get("stop_reason")
                        if reason is not None:
                            finish_reason = str(reason).lower()
                        continue
                    if event_type == "message_stop":
                        message = event.get("message", {})
                        if isinstance(message, dict):
                            reason = message.get("stop_reason")
                            if reason is not None:
                                finish_reason = str(reason).lower()
                        continue
                    if event_type == "error":
                        error = event.get("error", {})
                        message = error.get("message", "Response generation failed")
                        raise ProviderError(
                            self.config.participant,
                            "provider",
                            message,
                            retryable=True,
                        )
            if finish_reason == "max_tokens":
                raise ProviderError(
                    self.config.participant,
                    "output_limit",
                    f"{self.config.participant} reached the generation limit before completing the response",
                    retryable=True,
                )
            if finish_reason not in {None, "", "end_turn", "tool_use"}:
                raise ProviderError(
                    self.config.participant,
                    "provider_finish",
                    f"{self.config.participant} stopped with provider finish reason: {finish_reason}",
                    retryable=False,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(self.config.participant, "timeout", "Provider timed out", True) from exc
        except httpx.HTTPStatusError as exc:
            detail = self._safe_http_error(exc.response)
            raise ProviderError(
                self.config.participant,
                "http",
                f"Provider returned HTTP {exc.response.status_code}: {detail}",
                exc.response.status_code in {408, 409, 429, 500, 502, 503, 504},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                self.config.participant,
                "connection",
                f"{exc.__class__.__name__}: {str(exc)}",
                True,
            ) from exc

    @staticmethod
    def _safe_http_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
            detail = payload.get("error", {}).get("message") or payload.get("message")
            return str(detail)[:300] if detail else "Request failed"
        except (ValueError, AttributeError):
            return "Request failed"


class AdapterRegistry:
    def __init__(self, settings: Settings):
        self.adapters = {
            "Momo": LLMAdapter(settings.momo),
            "Bobby": LLMAdapter(settings.bobby),
        }

    def get(self, participant: str) -> LLMAdapter:
        try:
            return self.adapters[participant]
        except KeyError as exc:
            raise ValueError(f"Unknown participant: {participant}") from exc

    async def close(self) -> None:
        for adapter in self.adapters.values():
            await adapter.close()
