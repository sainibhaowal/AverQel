from __future__ import annotations

import asyncio
import base64
import binascii
import importlib
import logging
import mimetypes
import re
import time
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import replace
from threading import Event
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.types import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResult,
    ProviderModelInfo,
)

_AGENT_PROFILES = (
    ("standard", "Manus Standard"),
    ("lite", "Manus Lite"),
    ("max", "Manus Max"),
    ("max-medium", "Manus Max · Medium"),
    ("max-high", "Manus Max · High"),
    ("max-extra", "Manus Max · Extra"),
    ("max-ultra", "Manus Max · Ultra"),
)
_PROFILE_NAMES = {profile for profile, _ in _AGENT_PROFILES}
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MAX_TOTAL_IMAGE_BYTES = 40 * 1024 * 1024
_DEFAULT_TASK_TIMEOUT_SECONDS = 900
_MAX_TASK_TIMEOUT_SECONDS = 1800
_POLL_INTERVAL_SECONDS = 2.0
_CANCEL_EVENT_METADATA_KEY = "_manus_cancel_event"
logger = logging.getLogger(__name__)


class ManusRequestError(ProviderRequestError):
    """Avoid automatic retries that could create duplicate Manus tasks."""

    no_retry = True


class ManusAgentProvider:
    """Manus API v2 adapter exposed through AverQel's chat-provider contract.

    Manus creates asynchronous agent tasks instead of returning a chat
    completion. This adapter waits for a completed task and emits its final
    answer as one chat delta; it does not claim token-by-token streaming.
    """

    provider_name = "manus"
    supports_model_listing = True

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or "https://api.manus.ai").rstrip("/")
        self.api_key = api_key

    def bind(self, base_url: str | None, api_key: str | None = None) -> ManusAgentProvider:
        self.base_url = (base_url or "https://api.manus.ai").rstrip("/")
        self.api_key = api_key
        return self

    @staticmethod
    def _httpx(request: ChatGenerateRequest | None = None) -> Any:
        if request is not None:
            injected = request.metadata.get("httpx_module")
            if injected is not None:
                return injected
        return importlib.import_module("httpx")

    def _endpoint_url(self, route: str) -> str:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderCapabilityError("Manus requires a valid API base URL.")
        base_path = parsed.path.rstrip("/")
        if base_path.endswith("/v2"):
            base_path = base_path[:-3].rstrip("/")
        path = f"{base_path}/v2/{route.lstrip('/')}"
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))

    def _headers(self) -> dict[str, str]:
        if not self.api_key or not self.api_key.strip():
            raise ManusRequestError(
                provider_name=self.provider_name,
                status_code=401,
                message="A Manus API key is required.",
            )
        return {"x-manus-api-key": self.api_key.strip(), "Content-Type": "application/json"}

    def _safe_message(self, value: object) -> str:
        message = value.strip() if isinstance(value, str) else ""
        if self.api_key:
            message = message.replace(self.api_key, "[redacted]")
        message = re.sub(r"(?i)(x-manus-api-key\s*[:=]\s*)\S+", r"\1[redacted]", message)
        return message[:1200]

    def _raise_for_response(self, response: Any) -> dict[str, Any]:
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = None
        if response.status_code >= 400:
            detail: object = None
            if isinstance(payload, dict):
                error = payload.get("error")
                detail = error.get("message") if isinstance(error, dict) else payload.get("message")
            raise ManusRequestError(
                provider_name=self.provider_name,
                status_code=int(response.status_code),
                message=self._safe_message(detail) or "Manus API request failed.",
            )
        if not isinstance(payload, dict):
            raise ManusRequestError(
                provider_name=self.provider_name,
                status_code=502,
                message="Manus API returned an invalid response.",
            )
        if payload.get("ok") is False:
            error = payload.get("error")
            detail = error.get("message") if isinstance(error, dict) else None
            raise ManusRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message=self._safe_message(detail) or "Manus API rejected the request.",
            )
        return payload

    @staticmethod
    def _extract_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)

    def _render_transcript(self, request: ChatGenerateRequest) -> str:
        lines: list[str] = []
        for message in request.messages:
            role = str(message.get("role") or "user").strip().upper()
            if not re.fullmatch(r"[A-Z_]{1,32}", role):
                role = "MESSAGE"
            body = self._extract_text(message.get("content"))
            calls = message.get("tool_calls")
            if isinstance(calls, list) and calls:
                body = f"{body}\nTool call context: {calls!r}".strip()
            if body:
                lines.append(f"{role}:\n{body}")
        transcript = "\n\n".join(lines).strip()
        if not transcript:
            raise ProviderCapabilityError("Manus requires at least one non-empty text message.")
        return transcript

    @staticmethod
    def _decode_image(value: str) -> tuple[bytes, str, str]:
        mime_type = "image/jpeg"
        encoded = value.strip()
        if encoded.startswith("data:"):
            header, separator, encoded = encoded.partition(",")
            if not separator or ";base64" not in header:
                raise ProviderCapabilityError("Manus image attachments must use base64 data URLs.")
            mime_type = header[5:].split(";", maxsplit=1)[0].lower()
        if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            raise ProviderCapabilityError(f"Manus does not support image type {mime_type!r}.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ProviderCapabilityError(
                "Manus received an invalid base64 image attachment."
            ) from exc
        if not data:
            raise ProviderCapabilityError("Manus received an empty image attachment.")
        if len(data) > _MAX_IMAGE_BYTES:
            raise ProviderCapabilityError("Each Manus image attachment must be 20 MiB or smaller.")
        extension = mimetypes.guess_extension(mime_type) or ".jpg"
        if extension == ".jpe":
            extension = ".jpg"
        return data, mime_type, extension

    def _upload_images(self, request: ChatGenerateRequest) -> list[dict[str, str]]:
        images = request.images if isinstance(request.images, list) else []
        if not images:
            return []
        httpx_module = self._httpx(request)
        content_parts: list[dict[str, str]] = []
        total_bytes = 0
        for index, image in enumerate(images, start=1):
            if not isinstance(image, str):
                raise ProviderCapabilityError("Manus image attachments must be base64 strings.")
            image_bytes, mime_type, extension = self._decode_image(image)
            total_bytes += len(image_bytes)
            if total_bytes > _MAX_TOTAL_IMAGE_BYTES:
                raise ProviderCapabilityError("Manus image attachments must total 40 MiB or less.")
            filename = f"averqel-image-{index}{extension}"
            upload_payload = self._raise_for_response(
                httpx_module.post(
                    self._endpoint_url("file.upload"),
                    headers=self._headers(),
                    json={"filename": filename},
                    timeout=30.0,
                )
            )
            file_info = upload_payload.get("file")
            upload_url = upload_payload.get("upload_url")
            file_id = file_info.get("id") if isinstance(file_info, dict) else None
            parsed_upload = urlsplit(upload_url) if isinstance(upload_url, str) else None
            if (
                not isinstance(file_id, str)
                or not file_id
                or parsed_upload is None
                or parsed_upload.scheme != "https"
                or not parsed_upload.netloc
                or parsed_upload.username
                or parsed_upload.password
            ):
                raise ManusRequestError(
                    provider_name=self.provider_name,
                    status_code=502,
                    message="Manus returned an invalid secure attachment upload URL.",
                )
            # The upload URL is presigned. Never forward the Manus API key to
            # this third-party storage host, and do not follow redirects.
            uploaded = httpx_module.put(
                upload_url,
                content=image_bytes,
                headers={"Content-Type": mime_type},
                timeout=60.0,
                follow_redirects=False,
            )
            if uploaded.status_code >= 400:
                raise ManusRequestError(
                    provider_name=self.provider_name,
                    status_code=int(uploaded.status_code),
                    message="Manus could not store an image attachment.",
                )
            detail = self._raise_for_response(
                httpx_module.get(
                    self._endpoint_url("file.detail"),
                    headers=self._headers(),
                    params={"file_id": file_id},
                    timeout=30.0,
                )
            )
            uploaded_file = detail.get("file")
            if not isinstance(uploaded_file, dict) or uploaded_file.get("status") != "uploaded":
                raise ManusRequestError(
                    provider_name=self.provider_name,
                    status_code=502,
                    message="Manus did not confirm that the image attachment finished uploading.",
                )
            content_parts.append({"type": "file", "file_id": file_id, "visibility": "visible"})
        return content_parts

    @staticmethod
    def _agent_profile(model_name: str) -> str:
        normalized = model_name.strip().lower()
        profile = normalized.rsplit("/", maxsplit=1)[-1]
        if profile.startswith("manus-"):
            profile = profile.removeprefix("manus-")
        if profile not in _PROFILE_NAMES:
            raise ProviderCapabilityError(
                "Choose a supported Manus profile: standard, lite, max, or a Max thinking level."
            )
        return profile

    @staticmethod
    def _task_timeout(request: ChatGenerateRequest) -> int:
        value = request.metadata.get("manus_task_timeout_seconds")
        try:
            seconds = int(value) if value is not None else _DEFAULT_TASK_TIMEOUT_SECONDS
        except (TypeError, ValueError):
            seconds = _DEFAULT_TASK_TIMEOUT_SECONDS
        return max(30, min(seconds, _MAX_TASK_TIMEOUT_SECONDS))

    @staticmethod
    def _task_link(task_id: str, task_url: object) -> str:
        if isinstance(task_url, str):
            parsed = urlsplit(task_url)
            host = (parsed.hostname or "").lower()
            if parsed.scheme == "https" and (host == "manus.im" or host.endswith(".manus.im")):
                return task_url
        return f"Manus task ID: {task_id}"

    def _task_detail(
        self, httpx_module: Any, task_id: str, timeout_seconds: float
    ) -> dict[str, Any]:
        response = httpx_module.get(
            self._endpoint_url("task.detail"),
            headers=self._headers(),
            params={"task_id": task_id},
            timeout=timeout_seconds,
        )
        payload = self._raise_for_response(response)
        task = payload.get("task")
        if not isinstance(task, dict):
            raise ManusRequestError(
                provider_name=self.provider_name,
                status_code=502,
                message="Manus returned task details in an invalid format.",
            )
        return task

    def _task_messages(self, httpx_module: Any, task_id: str) -> list[dict[str, Any]]:
        response = httpx_module.get(
            self._endpoint_url("task.listMessages"),
            headers=self._headers(),
            params={"task_id": task_id, "order": "desc", "limit": 200},
            timeout=30.0,
        )
        payload = self._raise_for_response(response)
        messages = payload.get("messages")
        return (
            [item for item in messages if isinstance(item, dict)]
            if isinstance(messages, list)
            else []
        )

    def _stop_task(self, httpx_module: Any, task_id: str) -> None:
        response = httpx_module.post(
            self._endpoint_url("task.stop"),
            headers=self._headers(),
            json={"task_id": task_id},
            timeout=8.0,
        )
        self._raise_for_response(response)

    def _completed_task_response(
        self,
        *,
        request: ChatGenerateRequest,
        task_id: str,
        task_url: object,
        deadline: float,
    ) -> ChatGenerateResponse:
        httpx_module = self._httpx(request)
        timeout_seconds = float(request.metadata.get("timeout_seconds", 8.0))
        while True:
            cancellation_event = request.metadata.get(_CANCEL_EVENT_METADATA_KEY)
            if isinstance(cancellation_event, Event) and cancellation_event.is_set():
                self._stop_task(httpx_module, task_id)
                return ChatGenerateResponse(content="")
            if time.monotonic() >= deadline:
                break
            task = self._task_detail(httpx_module, task_id, timeout_seconds)
            status = str(task.get("status") or "").lower()
            link = self._task_link(task_id, task.get("task_url") or task_url)
            if status == "waiting":
                raise ManusRequestError(
                    provider_name=self.provider_name,
                    status_code=409,
                    message=(
                        "Manus is waiting for user input or an action decision. Open the task in "
                        f"Manus to continue. {link}"
                    ),
                )
            if status == "error":
                messages = self._task_messages(httpx_module, task_id)
                error = next(
                    (
                        item.get("error_message")
                        for item in messages
                        if isinstance(item.get("error_message"), dict)
                    ),
                    None,
                )
                detail = error.get("content") if isinstance(error, dict) else None
                raise ManusRequestError(
                    provider_name=self.provider_name,
                    status_code=502,
                    message=self._safe_message(detail) or f"Manus task failed. {link}",
                )
            if status == "stopped" and task.get("has_running_background_jobs") is False:
                messages = self._task_messages(httpx_module, task_id)
                assistant_messages: list[dict[str, Any]] = []
                for item in messages:
                    assistant_message = item.get("assistant_message")
                    if item.get("type") == "assistant_message" and isinstance(
                        assistant_message, dict
                    ):
                        assistant_messages.append(assistant_message)
                results = [
                    item
                    for item in assistant_messages
                    if item.get("delivery_kind") == "result"
                    and isinstance(item.get("content"), str)
                    and item["content"].strip()
                ]
                candidates = results or [
                    item
                    for item in assistant_messages
                    if isinstance(item.get("content"), str) and item["content"].strip()
                ]
                if not candidates:
                    raise ManusRequestError(
                        provider_name=self.provider_name,
                        status_code=502,
                        message=f"Manus completed the task without a text response. {link}",
                    )
                return ChatGenerateResponse(content=str(candidates[0]["content"]).strip())
            time.sleep(min(_POLL_INTERVAL_SECONDS, max(0.0, deadline - time.monotonic())))
        raise ManusRequestError(
            provider_name=self.provider_name,
            status_code=504,
            message=(
                "Manus task is still running after AverQel's wait limit. Check its status in "
                f"Manus before retrying to avoid starting duplicate work. "
                f"{self._task_link(task_id, task_url)}"
            ),
        )

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        if request.tool_choice == "required":
            raise ProviderCapabilityError(
                "Manus task API cannot return an AverQel function call when one is required."
            )
        transcript = self._render_transcript(request)
        if request.tools:
            transcript = (
                f"{transcript}\n\n"
                "SYSTEM NOTE: This task does not have access to AverQel function tools or linked "
                "services. Use only Manus agent capabilities and do not claim that an AverQel "
                "tool or connected service was called."
            )
        profile = self._agent_profile(request.model)
        httpx_module = self._httpx(request)
        content = [{"type": "text", "text": transcript, "visibility": "visible"}]
        content.extend(self._upload_images(request))
        payload = {
            "message": {"content": content, "connectors": []},
            "agent_profile": profile,
            "interactive_mode": False,
            "share_visibility": "private",
        }
        response = httpx_module.post(
            self._endpoint_url("task.create"),
            headers=self._headers(),
            json=payload,
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
        )
        created = self._raise_for_response(response)
        task_id = created.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ManusRequestError(
                provider_name=self.provider_name,
                status_code=502,
                message="Manus accepted the request but returned no task ID.",
            )
        deadline = time.monotonic() + self._task_timeout(request)
        return self._completed_task_response(
            request=request,
            task_id=task_id,
            task_url=created.get("task_url"),
            deadline=deadline,
        )

    async def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        async for event in self.stream_generate_events(request):
            if event.get("type") == "delta" and isinstance(event.get("text"), str):
                yield event["text"]

    async def stream_generate_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
        cancellation_event = Event()
        stream_request = replace(
            request,
            metadata={
                **request.metadata,
                _CANCEL_EVENT_METADATA_KEY: cancellation_event,
            },
        )
        generation = asyncio.create_task(asyncio.to_thread(self.generate, stream_request))
        try:
            while not generation.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(generation), timeout=_POLL_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    if not generation.done():
                        yield {"type": "agent_status", "status": "running"}
            response = generation.result()
        except asyncio.CancelledError:
            cancellation_event.set()
            try:
                # Keep the worker alive until it observes cancellation and
                # stops the remote task. The thread cannot be force-cancelled.
                await asyncio.shield(generation)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Manus task cancellation could not be confirmed",
                    exc_info=True,
                )
            raise
        if response.content:
            yield {"type": "delta", "text": response.content}

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        response = self.generate(request)
        if response.content:
            yield response.content

    def list_models(self) -> Sequence[ProviderModelInfo]:
        return [
            ProviderModelInfo(
                name=profile,
                kind="chat",
                display_name=display_name,
                capabilities={
                    "provider_protocol": "manus-task-api-v2",
                    "agent_profile": profile,
                    "streaming": "final-result-only",
                    "reports_token_usage": False,
                },
            )
            for profile, display_name in _AGENT_PROFILES
        ]

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        raise ProviderCapabilityError("Manus Agent API does not provide embedding models.")

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def embed_many(self, request: EmbeddingRequest) -> EmbeddingResponse:
        del request
        raise ProviderCapabilityError("Manus Agent API does not provide embeddings.")

    def health_check(self) -> HealthCheckResult:
        started = time.monotonic()
        try:
            response = importlib.import_module("httpx").get(
                self._endpoint_url("task.list"),
                headers=self._headers(),
                params={"limit": 1},
                timeout=8.0,
            )
            self._raise_for_response(response)
        except ProviderRequestError as exc:
            return HealthCheckResult(
                status="unhealthy",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code="manus_api_check_failed",
                error_message_redacted=exc.message,
            )
        except Exception:  # noqa: BLE001
            return HealthCheckResult(
                status="unhealthy",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code="manus_api_check_failed",
                error_message_redacted="Manus API could not be reached.",
            )
        return HealthCheckResult(
            status="healthy",
            latency_ms=int((time.monotonic() - started) * 1000),
            metadata={"check": "task-list", "generation_request_sent": False},
        )
