from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, cast

import redis

from app.core.config import get_settings
from app.deepspace.integrations.codex_proxy import (
    CODEX_ENQUEUE_CANCEL_SCRIPT,
    CODEX_ENQUEUE_REQUEST_SCRIPT,
    CODEX_MAX_PENDING_REQUESTS,
    CODEX_STREAM_TTL_SECONDS,
    codex_online_key,
    codex_request_key,
    codex_response_key,
)
from app.providers.services.base import (
    ChatProvider,
    ProviderCapabilityError,
    ProviderRequestError,
)
from app.providers.services.image_inputs import image_data_url
from app.providers.services.openai_codex_config import (
    codex_reasoning_effort_values,
    codex_supported_reasoning_efforts,
)
from app.providers.services.reasoning_capabilities import normalize_reasoning_effort_value
from app.providers.services.types import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    HealthCheckResult,
    ProviderModelInfo,
)

logger = logging.getLogger(__name__)


def _close_redis_client(client: redis.Redis) -> None:
    client.close()  # type: ignore[no-untyped-call]


class OpenAIPlanUsageLimitError(ProviderRequestError):
    """A plan quota response must never be retried automatically."""

    no_retry = True


def _openai_response_error(
    message: str,
    *,
    code: str | None = None,
    param: str | None = None,
    request_id: str | None = None,
    http_status: int | None = None,
) -> ProviderRequestError:
    normalized_code = (
        code
        if isinstance(code, str)
        and 1 <= len(code) <= 96
        and all(character.isalnum() or character in "_.-" for character in code)
        else None
    )
    normalized_request_id = (
        request_id
        if isinstance(request_id, str)
        and 1 <= len(request_id) <= 128
        and all(character.isalnum() or character in "_.:-" for character in request_id)
        else None
    )
    status = http_status if isinstance(http_status, int) and 100 <= http_status <= 599 else 502
    if normalized_code == "subscription_sharing_usage_limit_exceeded":
        status = 429
        message = (
            "ChatGPT plan usage limit reached. Check ChatGPT settings → Usage before retrying."
        )
    elif normalized_code == "subscription_sharing_usage_unavailable":
        status = 503
    elif normalized_code == "subscription_sharing_user_not_eligible":
        status = 403
    elif normalized_code in {
        "subscription_sharing_invalid_user",
        "chatpass_v2_invalid_authorization_context",
    }:
        status = 401 if normalized_code == "subscription_sharing_invalid_user" else 403

    details: list[str] = []
    if normalized_code:
        details.append(f"code: {normalized_code}")
    if isinstance(param, str) and param:
        details.append(f"parameter: {param[:96]}")
    if normalized_request_id:
        details.append(f"request ID: {normalized_request_id}")
    rendered = message.strip()[:500] or "OpenAI Responses request failed."
    if details:
        rendered = f"{rendered} ({', '.join(details)})"
    if normalized_code == "subscription_sharing_usage_limit_exceeded":
        return OpenAIPlanUsageLimitError("openai", status, rendered)
    return ProviderRequestError("openai", status, rendered)


class OpenAICodexProvider(ChatProvider):
    """OpenAI ChatGPT-plan model access through the user's local Electron runtime."""

    provider_name = "openai"
    request_timeout_seconds = 300

    def __init__(
        self,
        *,
        metadata: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        self.metadata = dict(metadata or {})
        codex_settings = self.metadata.get("codex_desktop")
        self.codex_settings: dict[str, Any] = (
            codex_settings if isinstance(codex_settings, dict) else {}
        )
        self.tenant_id = tenant_id
        self.owner_user_id = owner_user_id

    def list_models(self) -> Sequence[ProviderModelInfo]:
        models = self.codex_settings.get("models")
        if not isinstance(models, list):
            return []
        result: list[ProviderModelInfo] = []
        seen: set[str] = set()
        for item in models[:500]:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id or len(model_id) > 255:
                continue
            if model_id in seen:
                continue
            seen.add(model_id)
            display_name = item.get("name")
            capabilities: dict[str, Any] = {"source": "chatgpt_account"}
            supported_efforts = codex_supported_reasoning_efforts(self.codex_settings, model_id)
            if supported_efforts is not None:
                capabilities["supported_reasoning_efforts"] = list(supported_efforts)
                capabilities["supports_reasoning"] = bool(supported_efforts)
                capabilities["reasoning_effort_values"] = (
                    codex_reasoning_effort_values(self.codex_settings, model_id) or {}
                )
            result.append(
                ProviderModelInfo(
                    name=model_id,
                    display_name=(
                        display_name[:255]
                        if isinstance(display_name, str) and display_name.strip()
                        else model_id
                    ),
                    kind="chat",
                    capabilities=capabilities,
                )
            )
        return result

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def health_check(self) -> HealthCheckResult:
        if not self.tenant_id or not self.owner_user_id:
            return HealthCheckResult(
                status="unhealthy",
                error_code="codex_runtime_identity_missing",
                error_message_redacted="The desktop runtime owner could not be identified.",
            )
        started = time.monotonic()
        client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            online = bool(client.exists(codex_online_key(self.tenant_id, self.owner_user_id)))
        except redis.RedisError:
            logger.warning("Codex runtime health check could not reach Redis", exc_info=True)
            return HealthCheckResult(
                status="unhealthy",
                error_code="codex_runtime_status_unavailable",
                error_message_redacted="Desktop runtime status is temporarily unavailable.",
            )
        finally:
            _close_redis_client(client)
        if not online:
            return HealthCheckResult(
                status="degraded",
                error_code="codex_desktop_offline",
                error_message_redacted="Open AverQel Desktop and keep it signed in to use this provider.",
                metadata={"runtime": "electron"},
            )
        return HealthCheckResult(
            status="healthy",
            latency_ms=round((time.monotonic() - started) * 1000),
            metadata={"runtime": "electron", "token_storage": "local"},
        )

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        raise ProviderCapabilityError(
            "ChatGPT-plan access requires streamed Responses API requests."
        )

    async def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        async for event in self.stream_generate_events(request):
            if event.get("type") == "delta" and isinstance(event.get("text"), str):
                yield event["text"]

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        raise ProviderCapabilityError(
            "ChatGPT-plan access is available through DeepSpace streaming only."
        )

    async def stream_generate_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
        tenant_id = str(request.metadata.get("tenant_id") or self.tenant_id or "")
        user_id = str(request.metadata.get("user_id") or self.owner_user_id or "")
        account_id = str(self.codex_settings.get("account_id") or "")
        if not tenant_id or not user_id or not account_id:
            raise ProviderRequestError(
                self.provider_name,
                503,
                "Codex desktop account details are missing. Reconnect the OpenAI Codex provider.",
            )
        payload = self._responses_payload(request)
        settings = get_settings()
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        request_id = str(uuid.uuid4())
        response_key = codex_response_key(request_id)
        request_key = codex_request_key(tenant_id, user_id)
        request_packet = json.dumps(
            {
                "event": "codex_infer",
                "id": request_id,
                "params": {"account_id": account_id, "request": payload},
            },
            separators=(",", ":"),
        )
        try:
            client.delete(response_key)
            queued = cast(
                int,
                client.eval(
                    CODEX_ENQUEUE_REQUEST_SCRIPT,
                    2,
                    codex_online_key(tenant_id, user_id),
                    request_key,
                    request_packet,
                    str(CODEX_STREAM_TTL_SECONDS),
                    str(CODEX_MAX_PENDING_REQUESTS),
                ),
            )
            if queued == 0:
                _close_redis_client(client)
                raise ProviderRequestError(
                    self.provider_name,
                    503,
                    "Open AverQel Desktop and keep it online to use this ChatGPT account.",
                )
            if queued < 0:
                _close_redis_client(client)
                raise ProviderRequestError(
                    self.provider_name,
                    429,
                    "The desktop Codex request queue is full. Wait for an active request to finish.",
                )
        except redis.RedisError as exc:
            _close_redis_client(client)
            raise ProviderRequestError(
                self.provider_name,
                503,
                "The local Codex runtime relay is temporarily unavailable.",
            ) from exc

        last_id = "0-0"
        started = time.monotonic()
        completed = False
        tool_ids: dict[int, str] = {}
        tool_names: dict[int, str] = {}
        accumulated_arguments: dict[int, str] = {}
        try:
            while time.monotonic() - started < self.request_timeout_seconds:
                rows = cast(
                    list[tuple[str, list[tuple[str, dict[str, str]]]]],
                    await asyncio.to_thread(
                        client.xread,
                        {response_key: last_id},
                        count=32,
                        block=1000,
                    ),
                )
                if not rows:
                    online = await asyncio.to_thread(
                        client.exists, codex_online_key(tenant_id, user_id)
                    )
                    if not online:
                        raise ProviderRequestError(
                            self.provider_name,
                            503,
                            "The AverQel Desktop Codex connection closed during the response.",
                        )
                    continue
                for _key, events in rows:
                    for event_id, fields in events:
                        last_id = event_id
                        try:
                            frame = json.loads(fields.get("frame") or "{}")
                        except json.JSONDecodeError as exc:
                            raise ProviderRequestError(
                                self.provider_name,
                                502,
                                "The desktop runtime returned an invalid frame.",
                            ) from exc
                        kind = frame.get("kind")
                        data = frame.get("data")
                        if kind == "error":
                            message = data.get("message") if isinstance(data, dict) else None
                            details = data if isinstance(data, dict) else {}
                            raise _openai_response_error(
                                message if isinstance(message, str) else "Codex request failed.",
                                code=details.get("code"),
                                param=details.get("param"),
                                request_id=details.get("request_id"),
                                http_status=details.get("http_status"),
                            )
                        if kind == "closed":
                            if completed:
                                return
                            raise ProviderRequestError(
                                self.provider_name,
                                502,
                                "The Codex response ended before it completed.",
                            )
                        if kind != "event" or not isinstance(data, dict):
                            continue
                        normalized = self._normalize_event(
                            data,
                            tool_ids=tool_ids,
                            tool_names=tool_names,
                            accumulated_arguments=accumulated_arguments,
                        )
                        if data.get("type") == "response.completed":
                            completed = True
                        for normalized_event in normalized:
                            yield normalized_event
            raise ProviderRequestError(
                self.provider_name, 504, "The ChatGPT model response timed out."
            )
        except asyncio.CancelledError:
            raise
        except redis.RedisError as exc:
            raise ProviderRequestError(
                self.provider_name,
                503,
                "The local Codex runtime relay was interrupted.",
            ) from exc
        finally:
            if not completed:
                try:
                    removed = await asyncio.to_thread(client.lrem, request_key, 1, request_packet)
                    if not removed:
                        await asyncio.to_thread(
                            client.eval,
                            CODEX_ENQUEUE_CANCEL_SCRIPT,
                            2,
                            codex_online_key(tenant_id, user_id),
                            request_key,
                            json.dumps(
                                {"event": "codex_cancel", "id": request_id},
                                separators=(",", ":"),
                            ),
                            str(CODEX_STREAM_TTL_SECONDS),
                        )
                except redis.RedisError:
                    logger.debug("Codex cancellation could not be relayed", exc_info=True)
            try:
                await asyncio.to_thread(client.expire, response_key, 1)
            except redis.RedisError:
                pass
            _close_redis_client(client)

    def _responses_payload(self, request: ChatGenerateRequest) -> dict[str, Any]:
        instructions: list[str] = []
        input_items: list[dict[str, Any]] = []
        for message in request.messages:
            role = str(message.get("role") or "user")
            content = message.get("content", "")
            if role in {"system", "developer"}:
                text = self._text_content(content)
                if text:
                    instructions.append(text)
                continue
            if role == "tool":
                call_id = message.get("tool_call_id")
                if isinstance(call_id, str) and call_id:
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": self._text_content(content),
                        }
                    )
                continue
            if role == "assistant" and isinstance(message.get("tool_calls"), list):
                for call in message["tool_calls"][:128]:
                    function = call.get("function") if isinstance(call, dict) else None
                    if not isinstance(function, dict):
                        continue
                    name = function.get("name")
                    call_id = call.get("id")
                    if not isinstance(name, str) or not isinstance(call_id, str):
                        continue
                    arguments = function.get("arguments", "{}")
                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments, separators=(",", ":"))
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": call_id,
                            "name": name,
                            "arguments": arguments,
                        }
                    )
            parts = self._content_parts(content)
            if parts:
                input_items.append(
                    {"role": "assistant" if role == "assistant" else "user", "content": parts}
                )

        images = request.images if isinstance(request.images, list) else []
        for image in images[:10]:
            if image.startswith("https://"):
                image_url = image
            else:
                try:
                    image_url = image_data_url(image)
                except ValueError as exc:
                    raise ProviderCapabilityError(str(exc)) from exc
            input_items.append(
                {
                    "role": "user",
                    "content": [{"type": "input_image", "image_url": image_url}],
                }
            )

        payload: dict[str, Any] = {"model": request.model, "input": input_items}
        if instructions:
            payload["instructions"] = "\n\n".join(instructions)
        reasoning_mode = str(request.metadata.get("reasoning_mode") or "").lower()
        requested_effort = normalize_reasoning_effort_value(request.reasoning_effort)
        effort_map = {
            "minimal": "minimal",
            "low": "low",
            "medium": "medium",
            "high": "high",
            "very_high": "xhigh",
            "extreme_high": "max",
            "ultra": "ultra",
        }
        if reasoning_mode == "off":
            payload["reasoning"] = {"effort": "none"}
        elif request.reasoning_enabled and request.reasoning_effort:
            if requested_effort is None:
                raise ProviderCapabilityError("This Codex reasoning effort is not supported.")
            supported_efforts = codex_supported_reasoning_efforts(
                self.codex_settings, request.model
            )
            if supported_efforts is not None and requested_effort not in supported_efforts:
                raise ProviderCapabilityError(
                    "The selected Codex model does not support this reasoning effort."
                )
            if supported_efforts is None and requested_effort not in effort_map:
                raise ProviderCapabilityError("This Codex reasoning effort is not supported.")
            native_efforts = codex_reasoning_effort_values(self.codex_settings, request.model)
            payload["reasoning"] = {
                "effort": (native_efforts or {}).get(
                    requested_effort, effort_map.get(requested_effort, requested_effort)
                )
            }

        tool_definitions = self._function_tools(request.tools)
        if tool_definitions:
            payload["tools"] = [
                {
                    "type": "namespace",
                    "name": "averqel",
                    "description": "Tools available to the AverQel agent.",
                    "tools": tool_definitions,
                }
            ]
            if request.tool_choice in {"auto", "required", "none"}:
                payload["tool_choice"] = request.tool_choice
        return payload

    @staticmethod
    def _text_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(item.get("text"))
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text
        return ""

    @staticmethod
    def _content_parts(content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"type": "input_text", "text": content}] if content else []
        if not isinstance(content, list):
            text = OpenAICodexProvider._text_content(content)
            return [{"type": "input_text", "text": text}] if text else []
        result: list[dict[str, Any]] = []
        for item in content[:128]:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "")
            if item_type in {"text", "input_text"} and isinstance(item.get("text"), str):
                result.append({"type": "input_text", "text": item["text"]})
            elif item_type in {"image_url", "input_image"}:
                image = item.get("image_url")
                image_url = image.get("url") if isinstance(image, dict) else image
                if isinstance(image_url, str) and (
                    image_url.startswith("data:image/") or image_url.startswith("https://")
                ):
                    result.append({"type": "input_image", "image_url": image_url})
        return result

    @staticmethod
    def _function_tools(tools: Any) -> list[dict[str, Any]]:
        if not isinstance(tools, list):
            return []
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tool in tools[:128]:
            if not isinstance(tool, dict):
                continue
            function_value = tool.get("function")
            function = function_value if isinstance(function_value, dict) else tool
            name = function.get("name")
            normalized_name = name.strip() if isinstance(name, str) else ""
            if not normalized_name or len(normalized_name) > 64 or normalized_name in seen:
                continue
            seen.add(normalized_name)
            parameters = function.get("parameters")
            if not isinstance(parameters, dict):
                parameters = {"type": "object", "properties": {}}
            result.append(
                {
                    "type": "function",
                    "name": normalized_name,
                    "description": str(function.get("description") or "")[:1000],
                    "parameters": parameters,
                }
            )
        return result

    @staticmethod
    def _normalize_event(
        event: dict[str, Any],
        *,
        tool_ids: dict[int, str],
        tool_names: dict[int, str],
        accumulated_arguments: dict[int, str],
    ) -> list[dict[str, Any]]:
        event_type = event.get("type")
        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            return [{"type": "delta", "text": delta}] if isinstance(delta, str) and delta else []
        if event_type == "response.output_item.added":
            item = event.get("item")
            index = event.get("output_index")
            if (
                not isinstance(item, dict)
                or item.get("type") != "function_call"
                or not isinstance(index, int)
            ):
                return []
            call_id = item.get("call_id") or item.get("id")
            name = item.get("name")
            if isinstance(call_id, str):
                tool_ids[index] = call_id
            if isinstance(name, str):
                tool_names[index] = name
            raw_arguments = item.get("arguments")
            arguments = raw_arguments if isinstance(raw_arguments, str) else ""
            accumulated_arguments[index] = arguments
            return [
                {
                    "type": "tool_calls_delta",
                    "tool_calls": [
                        {
                            "index": index,
                            **({"id": tool_ids[index]} if index in tool_ids else {}),
                            "type": "function",
                            "function": {
                                **({"name": tool_names[index]} if index in tool_names else {}),
                                "arguments": arguments,
                            },
                        }
                    ],
                }
            ]
        if event_type == "response.function_call_arguments.delta":
            index = event.get("output_index")
            delta = event.get("delta")
            if not isinstance(index, int) or not isinstance(delta, str) or not delta:
                return []
            accumulated_arguments[index] = accumulated_arguments.get(index, "") + delta
            call: dict[str, Any] = {"index": index, "function": {"arguments": delta}}
            if index in tool_ids:
                call["id"] = tool_ids[index]
            if index in tool_names:
                call["function"]["name"] = tool_names[index]
            return [{"type": "tool_calls_delta", "tool_calls": [call]}]
        if event_type == "response.function_call_arguments.done":
            index = event.get("output_index")
            final_arguments = event.get("arguments")
            if not isinstance(index, int) or not isinstance(final_arguments, str):
                return []
            prior = accumulated_arguments.get(index, "")
            suffix = final_arguments[len(prior) :] if final_arguments.startswith(prior) else ""
            if not suffix:
                return []
            accumulated_arguments[index] = final_arguments
            call = {"index": index, "function": {"arguments": suffix}}
            if index in tool_ids:
                call["id"] = tool_ids[index]
            if index in tool_names:
                call["function"]["name"] = tool_names[index]
            return [{"type": "tool_calls_delta", "tool_calls": [call]}]
        if event_type == "response.completed":
            usage = event.get("usage")
            response = event.get("response")
            if not isinstance(usage, dict) and isinstance(response, dict):
                usage = response.get("usage")
            if isinstance(usage, dict):
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
                if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                    return [
                        {
                            "type": "usage",
                            "usage": {
                                "prompt_tokens": input_tokens,
                                "completion_tokens": output_tokens,
                                "total_tokens": int(
                                    usage.get("total_tokens") or input_tokens + output_tokens
                                ),
                            },
                        }
                    ]
        if event_type in {"response.failed", "response.incomplete", "error"}:
            error = event.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            details = error if isinstance(error, dict) else {}
            raise _openai_response_error(
                (
                    message
                    if isinstance(message, str)
                    else "ChatGPT returned a failed or incomplete response."
                ),
                code=details.get("code"),
                param=details.get("param"),
                request_id=event.get("request_id"),
            )
        return []
