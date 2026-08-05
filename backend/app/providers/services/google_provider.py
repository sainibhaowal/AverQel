from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any
from urllib.parse import quote

from app.providers.services.base import ProviderCapabilityError, ProviderRequestError
from app.providers.services.context_window import (
    extract_context_window,
    resolve_verified_context_window,
)
from app.providers.services.reasoning_capabilities import (
    model_supports_reasoning,
    reasoning_capabilities,
)
from app.providers.services.types import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    HealthCheckResult,
    ProviderModelInfo,
)


class GoogleProvider:
    provider_name = "google"
    _GEMINI_SCHEMA_TYPES = {
        "string": "STRING",
        "number": "NUMBER",
        "integer": "INTEGER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }
    _GEMINI_SCHEMA_KEYS = {
        "type",
        "format",
        "title",
        "description",
        "nullable",
        "enum",
        "maxItems",
        "minItems",
        "properties",
        "required",
        "minProperties",
        "maxProperties",
        "items",
        "anyOf",
        "propertyOrdering",
    }

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key

    def bind(self, base_url: str, api_key: str | None = None) -> GoogleProvider:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        return self

    @staticmethod
    def model_supports_reasoning(model_name: str) -> bool:
        return model_supports_reasoning("google", model_name)

    @staticmethod
    def _httpx() -> Any:
        return importlib.import_module("httpx")

    @staticmethod
    def _extract_candidate_parts(
        candidate: dict[str, Any],
    ) -> tuple[str, str | None, list[dict[str, Any]], list[dict[str, str]]]:
        parts = candidate.get("content", {}).get("parts", [])
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        media: list[dict[str, str]] = []
        for item in parts:
            if not isinstance(item, dict):
                continue
            function_call = item.get("functionCall")
            if isinstance(function_call, dict):
                name = function_call.get("name")
                if isinstance(name, str) and name.strip():
                    arguments = function_call.get("args", {})
                    call: dict[str, Any] = {
                        "id": f"google_call_{len(tool_calls)}",
                        "type": "function",
                        "function": {
                            "name": name.strip(),
                            "arguments": json.dumps(
                                arguments if isinstance(arguments, dict) else {},
                                ensure_ascii=False,
                            ),
                        },
                    }
                    # Gemini thinking models attach an opaque signature to the
                    # function-call part. It must be replayed verbatim on the
                    # next request in a tool loop.
                    thought_signature = item.get("thoughtSignature")
                    if isinstance(thought_signature, str) and thought_signature.strip():
                        call["thought_signature"] = thought_signature.strip()
                    tool_calls.append(call)
                continue
            inline_data = item.get("inlineData") or item.get("inline_data")
            if isinstance(inline_data, dict):
                content_type = inline_data.get("mimeType") or inline_data.get("mime_type")
                data = inline_data.get("data")
                if isinstance(content_type, str) and isinstance(data, str) and data:
                    media.append({"content_type": content_type, "data_base64": data})
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text:
                continue
            if bool(item.get("thought")) or bool(item.get("thoughtSignature")):
                thinking_parts.append(text)
            else:
                text_parts.append(text)
        return (
            "".join(text_parts),
            "".join(thinking_parts).strip() or None,
            tool_calls,
            media,
        )

    @staticmethod
    def _tool_declarations(request: ChatGenerateRequest) -> list[dict[str, Any]]:
        declarations: list[dict[str, Any]] = []
        for tool in request.tools or []:
            function = tool.get("function") if isinstance(tool, dict) else None
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            declaration: dict[str, Any] = {"name": name.strip()}
            description = function.get("description")
            if isinstance(description, str) and description.strip():
                declaration["description"] = description.strip()
            parameters = function.get("parameters")
            if isinstance(parameters, dict):
                declaration["parameters"] = GoogleProvider._gemini_schema(parameters)
            declarations.append(declaration)
        return declarations

    @classmethod
    def _gemini_schema(cls, schema: dict[str, Any]) -> dict[str, Any]:
        """Convert an OpenAI JSON schema into Google's Schema JSON shape.

        DeepSpace tools use provider-neutral JSON Schema. Gemini's REST API
        accepts a narrower Schema representation, uses uppercase enum values
        for types, and rejects OpenAI validation keywords such as
        ``additionalProperties`` and ``minLength``.
        """

        result: dict[str, Any] = {}
        for key, value in schema.items():
            if key not in cls._GEMINI_SCHEMA_KEYS:
                continue
            if key == "type" and isinstance(value, str):
                result[key] = cls._GEMINI_SCHEMA_TYPES.get(value.lower(), value.upper())
            elif key == "properties" and isinstance(value, dict):
                result[key] = {
                    str(name): cls._gemini_schema(item)
                    for name, item in value.items()
                    if isinstance(item, dict)
                }
            elif key == "items" and isinstance(value, dict):
                result[key] = cls._gemini_schema(value)
            elif key == "anyOf" and isinstance(value, list):
                result[key] = [cls._gemini_schema(item) for item in value if isinstance(item, dict)]
            else:
                result[key] = value
        return result

    @staticmethod
    def _tool_config(request: ChatGenerateRequest) -> dict[str, Any] | None:
        if not request.tool_choice:
            return None
        choice = request.tool_choice
        mode = "AUTO"
        allowed: list[str] = []
        if choice == "required":
            mode = "ANY"
        elif choice in {"none", "disabled"}:
            mode = "NONE"
        elif isinstance(choice, dict):
            function = choice.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                allowed = [function["name"]]
            if choice.get("mode") == "required":
                mode = "ANY"
        config: dict[str, Any] = {"mode": mode}
        if allowed:
            config["allowedFunctionNames"] = allowed
        return {"functionCallingConfig": config}

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(item.get("text"))
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            )
        return "" if content is None else str(content)

    @classmethod
    def _build_contents(
        cls, messages: list[dict[str, Any]]
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        system_parts: list[dict[str, str]] = []
        contents: list[dict[str, Any]] = []
        tool_names: dict[str, str] = {}
        for message in messages:
            role = str(message.get("role") or "user")
            if role == "system":
                text = cls._content_text(message.get("content"))
                if text.strip():
                    system_parts.append({"text": text})
                continue
            if role == "tool":
                call_id = str(message.get("tool_call_id") or "").strip()
                name = tool_names.get(call_id, call_id or "tool")
                raw_content = message.get("content", "")
                try:
                    response = (
                        json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                    )
                except json.JSONDecodeError:
                    response = {"output": raw_content}
                if not isinstance(response, dict):
                    response = {"output": response}
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"functionResponse": {"name": name, "response": response}}],
                    }
                )
                continue

            parts: list[dict[str, Any]] = []
            text = cls._content_text(message.get("content"))
            if text.strip():
                parts.append({"text": text})
            if role == "assistant":
                for call in message.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function")
                    if not isinstance(function, dict):
                        continue
                    raw_name = function.get("name")
                    if not isinstance(raw_name, str) or not raw_name.strip():
                        continue
                    name = raw_name
                    call_id = str(call.get("id") or f"google_call_{len(tool_names)}")
                    tool_names[call_id] = name.strip()
                    raw_arguments = function.get("arguments", "{}")
                    try:
                        arguments = (
                            json.loads(raw_arguments)
                            if isinstance(raw_arguments, str)
                            else raw_arguments
                        )
                    except json.JSONDecodeError:
                        arguments = {}
                    function_call_part: dict[str, Any] = {
                        "functionCall": {
                            "name": name.strip(),
                            "args": arguments if isinstance(arguments, dict) else {},
                        }
                    }
                    thought_signature = call.get("thought_signature") or call.get(
                        "thoughtSignature"
                    )
                    if isinstance(thought_signature, str) and thought_signature.strip():
                        function_call_part["thoughtSignature"] = thought_signature.strip()
                    parts.append(function_call_part)
            if parts:
                contents.append(
                    {"role": "model" if role == "assistant" else "user", "parts": parts}
                )
        system = {"parts": system_parts} if system_parts else None
        return system, contents

    @classmethod
    def _build_payload(cls, request: ChatGenerateRequest) -> dict[str, Any]:
        system, contents = cls._build_contents(request.messages)
        payload: dict[str, Any] = {
            "contents": contents or [{"role": "user", "parts": [{"text": ""}]}],
            "generationConfig": cls._build_generation_config(request),
        }
        if system:
            payload["systemInstruction"] = system
        declarations = cls._tool_declarations(request)
        if declarations:
            payload["tools"] = [{"functionDeclarations": declarations}]
            config = cls._tool_config(request)
            if config:
                payload["toolConfig"] = config
        return payload

    @staticmethod
    def _raise_provider_error(response: Any, body: bytes | str | None = None) -> None:
        message: str | None = None
        text: str | None = None
        if isinstance(body, bytes):
            text = body.decode("utf-8", errors="replace")
        elif isinstance(body, str):
            text = body
        if text is not None:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
        else:
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001
                payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                detail = error.get("message")
                if isinstance(detail, str) and detail.strip():
                    message = detail.strip()
        if not message and text and text.strip():
            message = text.strip()
        if not message:
            try:
                response_text = response.text
            except Exception:  # noqa: BLE001
                response_text = None
            if isinstance(response_text, str) and response_text.strip():
                message = response_text.strip()
        raise ProviderRequestError(
            provider_name="google",
            status_code=int(response.status_code),
            message=message,
        )

    @classmethod
    def _build_generation_config(cls, request: ChatGenerateRequest) -> dict[str, Any]:
        generation_config: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
        }
        if (
            cls.model_supports_reasoning(request.model)
            and request.metadata.get("reasoning_mode") != "auto"
            and request.tool_choice != "required"
        ):
            if request.reasoning_enabled:
                generation_config["thinkingConfig"] = {"includeThoughts": True}
            else:
                generation_config["thinkingConfig"] = {
                    "includeThoughts": False,
                    "thinkingBudget": 0,
                }
        return generation_config

    def generate(self, request: ChatGenerateRequest) -> ChatGenerateResponse:
        httpx_module = self._httpx()
        payload = self._build_payload(request)
        api_key = request.api_key or ""
        model = quote(request.model, safe="")
        response = httpx_module.post(
            f"{request.base_url.rstrip('/')}/models/{model}:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=float(request.metadata.get("timeout_seconds", 8.0)),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        payload_obj: dict[str, Any] = response.json()
        candidates = payload_obj.get("candidates", [])
        text = ""
        thinking_text: str | None = None
        tool_calls: list[dict[str, Any]] = []
        if isinstance(candidates, list) and candidates:
            text, thinking_text, tool_calls, _media = self._extract_candidate_parts(candidates[0])
        return ChatGenerateResponse(
            content=text,
            thinking_content=thinking_text,
            tool_calls=tool_calls or None,
        )

    async def stream_generate(self, request: ChatGenerateRequest) -> AsyncIterator[str]:
        async for event in self.stream_generate_events(request):
            if event["type"] == "delta":
                text = event.get("text")
                if isinstance(text, str) and text:
                    yield text

    async def stream_generate_events(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
        httpx_module = self._httpx()
        payload = self._build_payload(request)
        api_key = request.api_key or ""
        model = quote(request.model, safe="")
        async with httpx_module.AsyncClient(
            timeout=float(request.metadata.get("timeout_seconds", 8.0))
        ) as client:
            async with client.stream(
                "POST",
                f"{request.base_url.rstrip('/')}/models/{model}:streamGenerateContent?alt=sse&key={api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    self._raise_provider_error(response, body)
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.split(":", 1)[1].strip()
                    try:
                        payload_obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    candidates = payload_obj.get("candidates", [])
                    if not isinstance(candidates, list) or not candidates:
                        continue
                    text, thinking_text, tool_calls, media = self._extract_candidate_parts(
                        candidates[0]
                    )
                    if thinking_text:
                        yield {"type": "thinking", "text": thinking_text}
                    if text:
                        yield {"type": "delta", "text": text}
                    if tool_calls:
                        yield {"type": "tool_calls_delta", "tool_calls": tool_calls}
                    if media:
                        yield {"type": "media", "media": media}

    def stream_generate_sync(self, request: ChatGenerateRequest) -> Iterator[str]:
        result = self.generate(request)
        if result.content:
            yield result.content

    def list_models(self) -> Sequence[ProviderModelInfo]:
        if not self.base_url:
            raise ProviderCapabilityError("google model listing requires a configured endpoint")
        httpx_module = self._httpx()
        next_page_token: str | None = None
        models: list[ProviderModelInfo] = []
        seen: set[str] = set()
        while True:
            suffix = f"&pageToken={quote(next_page_token, safe='')}" if next_page_token else ""
            response = httpx_module.get(
                f"{self.base_url.rstrip('/')}/models?key={self.api_key or ''}{suffix}",
                headers={"Content-Type": "application/json"},
                timeout=8.0,
            )
            if response.status_code >= 400:
                self._raise_provider_error(response)
            payload_obj: dict[str, Any] = response.json()
            rows = payload_obj.get("models", [])
            for item in rows:
                if not isinstance(item, dict):
                    continue
                if not self._is_supported_chat_model(item):
                    continue
                model_name = self._canonical_model_name(item)
                if model_name in seen:
                    continue
                seen.add(model_name)
                live_context_window = extract_context_window(
                    item,
                    candidate_keys=(
                        "inputTokenLimit",
                        "input_token_limit",
                        "context_window",
                        "context_length",
                    ),
                )
                verified_context_window = resolve_verified_context_window(
                    model_name,
                    provider_type="google",
                )
                context_window = live_context_window or verified_context_window.context_window
                context_window_source = (
                    "live_model"
                    if live_context_window is not None
                    else verified_context_window.source
                )
                models.append(
                    ProviderModelInfo(
                        name=model_name,
                        kind="chat",
                        display_name=(
                            item.get("displayName")
                            if isinstance(item.get("displayName"), str)
                            else None
                        ),
                        context_window=context_window,
                        context_window_source=context_window_source,
                        capabilities={
                            "runtime": "google",
                            **(
                                {"context_window_source": context_window_source}
                                if context_window_source
                                else {}
                            ),
                            **reasoning_capabilities("google", model_name, base_url=self.base_url),
                        },
                    )
                )
            next_page_token = payload_obj.get("nextPageToken")
            if not isinstance(next_page_token, str) or not next_page_token:
                break
        return models

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        raise ProviderCapabilityError("google embeddings are not supported by this adapter")

    def list_reranker_models(self) -> Sequence[ProviderModelInfo]:
        return []

    def capabilities_for_model(self, model_name: str) -> dict[str, object]:
        return reasoning_capabilities("google", model_name)

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(status="healthy", metadata={"provider": self.provider_name})

    @staticmethod
    def _canonical_model_name(item: dict[str, Any]) -> str:
        base_model_id = item.get("baseModelId")
        if isinstance(base_model_id, str) and base_model_id:
            return base_model_id
        name = item.get("name")
        if isinstance(name, str) and name:
            return name.split("/", 1)[-1]
        return ""

    @classmethod
    def _is_supported_chat_model(cls, item: dict[str, Any]) -> bool:
        methods = item.get("supportedGenerationMethods")
        if not isinstance(methods, list) or "generateContent" not in methods:
            return False
        model_name = cls._canonical_model_name(item).lower()
        if not model_name:
            return False
        excluded = ("embedding", "aqa", "imagen", "veo", "tts", "transcribe")
        return not any(token in model_name for token in excluded)
