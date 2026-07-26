from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.auth.dependencies import AuthContext
from app.core.config import Settings
from app.deepspace.repositories.chat import DeepSpaceChatRepository
from app.deepspace.services.task_loop import DeepSpaceTaskLoopStore, summarize_tasks
from app.providers.services import ChatGenerateRequest, ProviderRegistry
from app.providers.services.base import ProviderRequestError
from app.providers.services.selection_service import ProviderSelectionService
from app.providers.services.types import WebSearchRequest, WebSearchResponse
from app.system.services.rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)

MAX_AGENT_ROUNDS = 12
MAX_WEB_SEARCH_CALLS = 3
MAX_TOOL_RETRIES = 1
MAX_NO_TOOL_REPROMPTS = 2
DEFAULT_AGENT_TIMEOUT_SECONDS = 180
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the public web through the configured self-hosted search provider. "
            "Use this for current, time-sensitive, unfamiliar, or source-backed information."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {"type": "string", "minLength": 2, "maxLength": 512},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                "domains": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 120},
                    "maxItems": 20,
                },
                "time_range": {"type": "string", "enum": ["day", "week", "month", "year"]},
            },
            "required": ["query"],
        },
    },
}
TODO_WRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "todo_write",
        "description": "Create or replace a dynamic task list for this DeepSpace conversation.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tasks": {
                    "type": "array",
                    "maxItems": 40,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string", "maxLength": 1000},
                            "active_form": {"type": "string", "maxLength": 1000},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "blocked", "failed"]},
                            "priority": {"type": "integer", "minimum": 0, "maximum": 1000},
                            "dependencies": {"type": "array", "items": {"type": "string"}, "maxItems": 40},
                        },
                        "required": ["content"],
                    },
                }
            },
            "required": ["tasks"],
        },
    },
}
TODO_READ_TOOL = {
    "type": "function",
    "function": {
        "name": "todo_read",
        "description": "Read the current persisted task list and statuses for this conversation.",
        "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
    },
}
TODO_CHECK_TOOL = {
    "type": "function",
    "function": {
        "name": "todo_check",
        "description": "Verify task completion, dependencies, blockers, and completion evidence.",
        "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
    },
}
TODO_MARK_TOOL = {
    "type": "function",
    "function": {
        "name": "todo_mark",
        "description": "Mark one persisted task completed, blocked, or failed with evidence.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "task_id": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "blocked", "failed"]},
                "evidence": {"type": "string", "maxLength": 1000},
            },
            "required": ["task_id", "status"],
        },
    },
}
OBSERVE_TOOL = {
    "type": "function",
    "function": {
        "name": "observe",
        "description": "Inspect the current note and task state without changing it.",
        "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
    },
}
ANALYZE_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze",
        "description": "Evaluate current task evidence and identify the next safe task; do not claim completion without evidence.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"focus": {"type": "string", "maxLength": 1000}},
        },
    },
}
NOTE_READ_TOOL = {
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read the active DeepSpace note only. This never reads the operating system or files.",
        "parameters": {"type": "object", "additionalProperties": False, "properties": {}},
    },
}
NOTE_WRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "write",
        "description": "Write Markdown to the active DeepSpace note only, replacing or appending note content.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "markdown": {"type": "string", "maxLength": 100000},
                "mode": {"type": "string", "enum": ["replace", "append"]},
            },
            "required": ["markdown"],
        },
    },
}
FINAL_TOOL = {
    "type": "function",
    "function": {
        "name": "final",
        "description": "Produce the final answer only after verifying all required tasks or clearly reporting a blocker.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": {"type": "string", "maxLength": 100000},
                "summary": {"type": "string", "maxLength": 1000},
            },
            "required": ["answer"],
        },
    },
}
PRODUCTIVITY_TOOLS = [
    TODO_WRITE_TOOL,
    TODO_READ_TOOL,
    TODO_CHECK_TOOL,
    TODO_MARK_TOOL,
    OBSERVE_TOOL,
    ANALYZE_TOOL,
    NOTE_READ_TOOL,
    NOTE_WRITE_TOOL,
    FINAL_TOOL,
]
TOOL_CAPABLE_CHAT_PROVIDERS = {
    "openai",
    "groq",
    "groq-openai-compatible",
    "mistral",
    "together",
    "fireworks",
    "perplexity",
    "vllm",
    "custom",
    "opencode-zen",
    "openrouter",
}


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"


class DeepSpaceChatService:
    """Provider-backed productivity chat owned by DeepSpace.

    This service deliberately has no retrieval, grounding cache, classifier, or
    citation dependency. It uses durable DeepSpace history as conversation
    context and the provider registry only for model selection.
    """

    def __init__(self, *, db: Any, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.chat = DeepSpaceChatRepository(db)
        self.providers = ProviderSelectionService(db, settings)
        self.registry = ProviderRegistry(settings)
        self.task_store = DeepSpaceTaskLoopStore(db)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _messages(self, *, auth: AuthContext, conversation_id: uuid.UUID) -> list[dict[str, Any]]:
        history = self.chat.get_messages(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
        )
        result: list[dict[str, Any]] = []
        for message in history[-20:]:
            content = message.active_version.content if message.active_version else message.content
            if content.strip():
                result.append({"role": message.role, "content": content})
        return result

    @staticmethod
    def _tool_call_accumulator(
        accumulator: dict[int, dict[str, Any]],
        deltas: object,
    ) -> None:
        if not isinstance(deltas, list):
            return
        for position, item in enumerate(deltas):
            if not isinstance(item, dict):
                continue
            raw_index = item.get("index", position)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                index = position
            current = accumulator.setdefault(
                index,
                {"id": f"tool_{index}", "type": "function", "function": {"name": "", "arguments": ""}},
            )
            call_id = item.get("id")
            if isinstance(call_id, str) and call_id.strip():
                current["id"] = call_id.strip()
            function = item.get("function") if isinstance(item.get("function"), dict) else item
            name = function.get("name") if isinstance(function, dict) else None
            if isinstance(name, str) and name.strip():
                current["function"]["name"] = name.strip()
            arguments = function.get("arguments") if isinstance(function, dict) else None
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, ensure_ascii=False)
            if isinstance(arguments, str):
                current["function"]["arguments"] += arguments

    @staticmethod
    def _parse_tool_arguments(call: dict[str, Any]) -> dict[str, Any] | None:
        function = call.get("function")
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            return None
        raw = function.get("arguments")
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _tool_name(call: dict[str, Any]) -> str:
        function = call.get("function")
        return str(function.get("name") or "unknown") if isinstance(function, dict) else "unknown"

    async def _request_disconnected(self, request: Any | None) -> bool:
        if request is None:
            return False
        checker = getattr(request, "is_disconnected", None)
        if not callable(checker):
            return False
        try:
            return bool(await checker())
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _tool_phase(tool_name: str) -> tuple[str, str]:
        if tool_name == "todo_write":
            return "planning", "Creating the task plan."
        if tool_name in {"todo_read", "todo_check", "observe"}:
            return "checking", "Checking the current workspace state."
        if tool_name == "analyze":
            return "analyzing", "Analyzing evidence and choosing the next task."
        if tool_name == "web_search":
            return "searching", "Searching the configured web provider."
        if tool_name == "final":
            return "finalizing", "Verifying the work before the final answer."
        return "working", f"Working with {tool_name}."

    @staticmethod
    def _requires_agent_tools(prompt: str) -> bool:
        words = prompt.split()
        if len(words) >= 12:
            return True
        tool_intent_terms = (
            "search",
            "latest",
            "internet",
            "research",
            "case study",
            "references",
            "citations",
            "diagram",
            "table",
            "write",
            "analyze",
            "compare",
            "plan",
            "checklist",
        )
        lowered = prompt.lower()
        return any(term in lowered for term in tool_intent_terms)

    async def _execute_productivity_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        auth: AuthContext,
        conversation_id: uuid.UUID,
        web_provider: Any | None,
        web_candidate: Any | None,
        request: Any | None,
    ) -> dict[str, Any]:
        if tool_name == "todo_write":
            tasks = arguments.get("tasks")
            if not isinstance(tasks, list):
                raise ValueError("todo_write requires a tasks array.")
            result = self.task_store.replace_tasks(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                tasks=tasks,
            )
            return {"tasks": result, "summary": summarize_tasks(result)}
        if tool_name == "todo_read":
            tasks = self.task_store.read_tasks(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
            return {"tasks": tasks, "summary": summarize_tasks(tasks)}
        if tool_name == "todo_check":
            return self.task_store.check_tasks(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
        if tool_name == "todo_mark":
            task_id = str(arguments.get("task_id") or "").strip()
            status = str(arguments.get("status") or "").strip()
            if not task_id:
                raise ValueError("todo_mark requires task_id.")
            task = self.task_store.mark_task(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                task_id=task_id,
                status=status,
                evidence=str(arguments.get("evidence") or "")[:1000],
            )
            return {"task": task, "summary": "Task status updated."}
        if tool_name == "observe":
            tasks = self.task_store.check_tasks(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
            note = self.task_store.read_note(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
            return {
                "tasks": tasks,
                "note": {"length": note["length"], "conversation_id": note["conversation_id"]},
            }
        if tool_name == "analyze":
            check = self.task_store.check_tasks(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
            next_task = next(
                (item for item in check["tasks"] if item["status"] not in {"completed", "failed", "blocked"}),
                None,
            )
            return {
                "focus": str(arguments.get("focus") or "").strip()[:1000],
                "task_check": check,
                "next_task": next_task,
                "decision": "complete" if check["complete"] else ("work_next_task" if next_task else "report_blocker"),
            }
        if tool_name == "read":
            return self.task_store.read_note(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
        if tool_name == "write":
            return self.task_store.write_note(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
                markdown=str(arguments.get("markdown") or ""),
                mode=str(arguments.get("mode") or "replace"),
            )
        if tool_name == "web_search":
            if web_provider is None or web_candidate is None:
                raise ValueError("No web search provider is configured.")
            _response, payload = await self._run_web_search(
                provider=web_provider,
                candidate=web_candidate,
                arguments=arguments,
                auth=auth,
                request=request,
            )
            return payload
        if tool_name == "final":
            check = self.task_store.check_tasks(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                conversation_id=conversation_id,
            )
            if check["task_count"] and not check["complete"]:
                return {"accepted": False, "reason": "todo_check_required", "task_check": check}
            return {
                "accepted": True,
                "answer": str(arguments.get("answer") or "").strip(),
                "summary": str(arguments.get("summary") or "").strip()[:1000],
                "task_check": check,
            }
        raise ValueError(f"Tool '{tool_name}' is not available in DeepSpace.")

    @staticmethod
    def _domain_allowed_by_config(domain: str, configured: object) -> bool:
        if not isinstance(configured, list) or not configured:
            return True
        host = domain.lower().lstrip(".")
        return any(
            isinstance(item, str)
            and (host == item.strip().lower().lstrip(".") or host.endswith(f".{item.strip().lower().lstrip('.')}"))
            for item in configured
        )

    async def _run_web_search(
        self,
        *,
        provider: Any,
        candidate: Any,
        arguments: dict[str, Any],
        auth: AuthContext,
        request: Any | None,
    ) -> tuple[WebSearchResponse, dict[str, Any]]:
        query = str(arguments.get("query") or "").strip()[:512]
        max_results_raw = arguments.get("max_results", 5)
        try:
            max_results = max(1, min(int(max_results_raw), 10))
        except (TypeError, ValueError):
            max_results = 5
        configured_allowed = candidate.metadata.get("allowed_domains")
        requested_domains = arguments.get("domains")
        if isinstance(requested_domains, list) and requested_domains:
            allowed_domains = [
                str(item).strip().lower()
                for item in requested_domains
                if isinstance(item, str)
                and str(item).strip()
                and self._domain_allowed_by_config(str(item), configured_allowed)
            ][:20]
        else:
            allowed_domains = configured_allowed
        metadata = {
            **dict(candidate.metadata),
            "allowed_domains": allowed_domains,
            "time_range": arguments.get("time_range"),
            "tenant_id": str(auth.tenant_id),
            "user_id": str(auth.user_id),
        }
        if request is not None:
            metadata["rate_limit_request"] = request
        search_request = WebSearchRequest(
            query=query,
            max_results=max_results,
            timeout_seconds=15,
            include_answer=False,
            include_raw_content=False,
            provider_name=candidate.provider_type,
            metadata=metadata,
        )
        response = await asyncio.to_thread(provider.search, search_request)
        citations = [
            {
                "id": index,
                "title": item.title,
                "url": item.url,
                "snippet": item.content[:800],
                "published_date": item.published_date,
                "source": item.source,
            }
            for index, item in enumerate(response.results, start=1)
        ]
        return response, {"query": response.query, "citations": citations, "results": citations}

    @staticmethod
    def _append_citations(answer: str, citations: list[dict[str, Any]]) -> str:
        if not citations:
            return answer
        lines = ["", "### Sources"]
        for item in citations[:8]:
            title = str(item.get("title") or "Source").replace("[", "(").replace("]", ")")
            url = str(item.get("url") or "").strip()
            if url.startswith(("http://", "https://")):
                lines.append(f"[{item.get('id', '?')}] [{title}]({url})")
        return answer.rstrip() + "\n" + "\n".join(lines) if len(lines) > 2 else answer

    async def stream_turn(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID | None,
        prompt: str,
        thinking_enabled: bool = False,
        request: Any | None = None,
    ) -> AsyncIterator[str]:
        prompt = " ".join(prompt.strip().split())
        if not prompt:
            yield sse("error", {"code": "EMPTY_MESSAGE", "message": "Message cannot be empty."})
            return

        if request is not None:
            RateLimitService(self.settings).enforce_deepspace_user_limit(request=request, user_id=str(auth.user_id))

        if conversation_id is None:
            conversation = self.chat.create_conversation(
                tenant_id=auth.tenant_id,
                user_id=auth.user_id,
                title=prompt[:80],
            )
            conversation_id = conversation.id
        elif self.chat.get_conversation(tenant_id=auth.tenant_id, conversation_id=conversation_id, user_id=auth.user_id) is None:
            yield sse("error", {"code": "CONVERSATION_NOT_FOUND", "message": "DeepSpace conversation not found."})
            return

        previous = self._messages(auth=auth, conversation_id=conversation_id)
        self.chat.add_message(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            role="user",
            content=prompt,
        )
        assistant_message = self.chat.add_message(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            role="assistant",
            content="",
            metadata_json={"status": "streaming", "surface": "deepspace"},
        )
        self.db.commit()

        started_at = self._now()
        yield sse("start", {"conversation_id": str(conversation_id), "message_id": str(assistant_message.id), "started_at": started_at})

        selection = self.providers.resolve_chat(
            tenant_id=auth.tenant_id,
            workspace_id=None,
            actor_user_id=auth.user_id,
        )
        candidate = selection.candidates[0] if selection.candidates else None
        if candidate is None:
            yield sse("error", {"code": "LLM_UNAVAILABLE", "message": "No DeepSpace chat model is configured."})
            return

        meta = {
            "conversation_id": str(conversation_id),
            "message_id": str(assistant_message.id),
            "model_name": candidate.model_name,
            "provider_type": candidate.provider_type,
        }
        if candidate.context_window is not None:
            meta["context_window"] = candidate.context_window
            meta["context_limit"] = candidate.context_window
        if candidate.context_window_source:
            meta["context_limit_source"] = candidate.context_window_source
        yield sse("meta", meta)
        provider = self.registry.get_chat_provider_from_selection(candidate)
        web_candidate = None
        web_provider = None
        if candidate.provider_type in TOOL_CAPABLE_CHAT_PROVIDERS:
            try:
                web_selection = self.providers.resolve_web_search(
                    tenant_id=auth.tenant_id,
                    workspace_id=None,
                    actor_user_id=auth.user_id,
                )
                web_candidate = web_selection.candidates[0] if web_selection.candidates else None
                if web_candidate is not None:
                    web_provider = self.registry.get_web_search_provider_from_selection(web_candidate)
            except Exception:  # noqa: BLE001
                logger.warning("DeepSpace web search is unavailable; continuing without the tool", exc_info=True)
                web_candidate = None
                web_provider = None
        productivity_tools = PRODUCTIVITY_TOOLS if candidate.provider_type in TOOL_CAPABLE_CHAT_PROVIDERS else []
        web_tools = [WEB_SEARCH_TOOL] if web_candidate is not None and web_provider is not None else []
        available_tools = [*productivity_tools, *web_tools]
        if available_tools:
            yield sse(
                "agent_status",
                {
                    "phase": "planning",
                    "message": "DeepSpace is ready to plan and execute this request safely.",
                    "active_tools": [str(item["function"]["name"]) for item in available_tools],
                },
            )

        conversation_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are DeepSpace, a productivity assistant for drafting, research, planning, "
                    "analysis, and note work. Answer directly in Markdown. Do not assume access to "
                    "files, shell commands, cURL, terminal, file explorer, MCP, or retrieval results "
                    "unless they are explicitly provided. The read and write tools operate only on "
                    "the active DeepSpace note. They never access the operating system. For a request "
                    "with multiple meaningful steps, call analyze, then todo_write and todo_read before "
                    "doing work. Use observe after work, analyze the evidence, todo_check, and todo_mark "
                    "each task with evidence. Call final only after todo_check confirms completion or a "
                    "clear blocker. Thinking/reasoning text is display-only and never controls execution. "
                    "When web_search results are provided, use only those sources for web claims, cite "
                    "them as [1], [2], and do not invent URLs."
                ),
            },
            *previous,
            {"role": "user", "content": prompt},
        ]
        answer_parts: list[str] = []
        thinking_parts: list[str] = []
        citations: list[dict[str, Any]] = []
        forced_answer: str | None = None
        seen_tool_calls: dict[str, int] = {}
        web_search_calls = 0
        no_tool_reprompts = 0
        loop_deadline = time.monotonic() + max(
            30,
            min(int(getattr(self.settings, "deepspace_agent_timeout_seconds", DEFAULT_AGENT_TIMEOUT_SECONDS)), 300),
        )
        try:
            for round_index in range(MAX_AGENT_ROUNDS):
                if time.monotonic() >= loop_deadline:
                    yield sse("agent_status", {"phase": "blocked", "message": "DeepSpace reached its safe execution timeout.", "active_tools": []})
                    break
                if await self._request_disconnected(request):
                    yield sse("agent_status", {"phase": "blocked", "message": "DeepSpace run cancelled because the client disconnected.", "active_tools": []})
                    break
                tool_calls: dict[int, dict[str, Any]] = {}
                request_payload = ChatGenerateRequest(
                    model=candidate.model_name,
                    messages=conversation_messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens_per_request,
                    base_url=candidate.base_url or "",
                    api_key=candidate.api_key,
                    stream=True,
                    reasoning_enabled=thinking_enabled,
                    tools=available_tools or None,
                    tool_choice=(
                        "required"
                        if available_tools
                        and round_index == 0
                        and self._requires_agent_tools(prompt)
                        else ("auto" if available_tools else None)
                    ),
                    metadata={
                        "surface": "deepspace",
                        "conversation_id": str(conversation_id),
                        "provider_type": candidate.provider_type,
                        "timeout_seconds": min(15, int(getattr(self.settings, "llm_timeout_seconds", 15))),
                    },
                )
                stream_events = getattr(provider, "stream_generate_events", None)
                if callable(stream_events):
                    async for provider_event in stream_events(request_payload):
                        if not isinstance(provider_event, dict):
                            continue
                        event_type = str(provider_event.get("type") or "")
                        if event_type in {"tool_calls_delta", "tool_call", "tool_calls"}:
                            raw_deltas = provider_event.get("tool_calls") or provider_event.get("tool_call")
                            if isinstance(raw_deltas, list):
                                for position, item in enumerate(raw_deltas):
                                    if not isinstance(item, dict):
                                        continue
                                    function = item.get("function") if isinstance(item.get("function"), dict) else item
                                    if not isinstance(function, dict):
                                        continue
                                    fragment = function.get("arguments")
                                    if isinstance(fragment, dict):
                                        fragment = json.dumps(fragment, ensure_ascii=False, separators=(",", ":"))
                                    name = str(function.get("name") or "").strip()
                                    call_id = str(item.get("id") or f"tool_{position}")
                                    if isinstance(fragment, str) and fragment:
                                        yield sse(
                                            "tool_delta",
                                            {
                                                "tool_name": name or "pending_tool",
                                                "tool_id": call_id,
                                                "step_id": f"tool_{round_index}_{call_id}",
                                                "tool_input": {},
                                                "text": fragment,
                                                "stream": "arguments",
                                                "turn_index": round_index,
                                            },
                                        )
                            self._tool_call_accumulator(tool_calls, raw_deltas)
                            continue
                        text = provider_event.get("text")
                        if not isinstance(text, str) or not text:
                            continue
                        if event_type in {"thinking", "reasoning", "reasoning_delta"}:
                            thinking_parts.append(text)
                            yield sse("thinking", {"text": text})
                        elif event_type in {"delta", "text", "content"}:
                            answer_parts.append(text)
                            yield sse("delta", {"text": text})
                else:
                    async for chunk in provider.stream_generate(request_payload):
                        if not chunk:
                            continue
                        answer_parts.append(chunk)
                        yield sse("delta", {"text": chunk})

                normalized_calls = [tool_calls[index] for index in sorted(tool_calls)]
                if not normalized_calls:
                    task_check = self.task_store.check_tasks(
                        tenant_id=auth.tenant_id,
                        user_id=auth.user_id,
                        conversation_id=conversation_id,
                    )
                    if (
                        available_tools
                        and task_check["task_count"]
                        and not task_check["complete"]
                        and no_tool_reprompts < MAX_NO_TOOL_REPROMPTS
                        and round_index + 1 < MAX_AGENT_ROUNDS
                    ):
                        no_tool_reprompts += 1
                        yield sse(
                            "agent_status",
                            {
                                "phase": "retrying",
                                "message": "The task plan is unfinished; requesting the next structured tool step.",
                                "active_tools": [],
                                "attempt": no_tool_reprompts + 1,
                            },
                        )
                        conversation_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Your persisted DeepSpace task list is unfinished. Do not provide a prose answer yet. "
                                    "Call exactly one appropriate structured tool now to continue the next pending task, "
                                    "then inspect its result. Use web_search for current web research."
                                ),
                            }
                        )
                        continue
                    break
                no_tool_reprompts = 0

                conversation_messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": normalized_calls,
                    }
                )
                for call in normalized_calls:
                    call_id = str(call.get("id") or uuid.uuid4())
                    tool_name = self._tool_name(call)
                    arguments = self._parse_tool_arguments(call)
                    step_id = f"{tool_name}_{round_index}_{call_id}"
                    if arguments is None:
                        output = f"The {tool_name} arguments were invalid JSON."
                        yield sse(
                            "tool_error",
                            {
                                "tool_name": tool_name,
                                "tool_id": call_id,
                                "step_id": step_id,
                                "error": output,
                            },
                        )
                        conversation_messages.append(
                            {"role": "tool", "tool_call_id": call_id, "content": output}
                        )
                        continue

                    signature = hashlib.sha256(
                        json.dumps({"name": tool_name, "arguments": arguments}, sort_keys=True, ensure_ascii=False).encode("utf-8")
                    ).hexdigest()
                    seen_tool_calls[signature] = seen_tool_calls.get(signature, 0) + 1
                    if seen_tool_calls[signature] > 2:
                        output = "Duplicate tool call detected and stopped safely."
                        yield sse("tool_error", {"tool_name": tool_name, "tool_id": call_id, "step_id": step_id, "error": output})
                        conversation_messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
                        continue
                    phase, phase_message = self._tool_phase(tool_name)

                    yield sse(
                        "tool_start",
                        {
                            "tool_name": tool_name,
                            "tool_id": call_id,
                            "step_id": step_id,
                            "tool_input": arguments,
                            "permission_level": "auto",
                            "turn_index": round_index,
                            "started_at": self._now(),
                        },
                    )
                    yield sse(
                        "agent_status",
                        {
                            "phase": phase,
                            "message": phase_message,
                            "active_tools": [tool_name],
                        },
                    )
                    success = False
                    output = ""
                    for attempt in range(MAX_TOOL_RETRIES + 1):
                        if time.monotonic() >= loop_deadline or await self._request_disconnected(request):
                            output = "Tool execution cancelled or timed out safely."
                            break
                        try:
                            if tool_name == "web_search":
                                web_search_calls += 1
                                if web_search_calls > MAX_WEB_SEARCH_CALLS:
                                    raise ValueError("Maximum web-search calls reached for this turn.")
                            tool_payload = await asyncio.wait_for(
                                self._execute_productivity_tool(
                                    tool_name=tool_name,
                                    arguments=arguments,
                                    auth=auth,
                                    conversation_id=conversation_id,
                                    web_provider=web_provider,
                                    web_candidate=web_candidate,
                                    request=request,
                                ),
                                timeout=max(5, min(30, loop_deadline - time.monotonic())),
                            )
                            if tool_name == "web_search":
                                citations.extend(tool_payload.get("citations", []))
                            output = json.dumps(tool_payload, ensure_ascii=False, separators=(",", ":"))
                            success = True
                            break
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("DeepSpace tool failed: %s", tool_name, exc_info=True)
                            output = f"{tool_name} failed safely: {exc}"
                            if attempt < MAX_TOOL_RETRIES:
                                yield sse("agent_status", {"phase": "retrying", "message": f"Retrying {tool_name}.", "active_tools": [tool_name], "attempt": attempt + 2})
                            else:
                                yield sse("tool_error", {"tool_name": tool_name, "tool_id": call_id, "step_id": step_id, "error": str(exc)})
                    if success:
                        yield sse(
                            "tool_result",
                            {
                                "tool_name": tool_name,
                                "tool_id": call_id,
                                "step_id": step_id,
                                "tool_input": arguments,
                                "output": output,
                                "success": True,
                                "turn_index": round_index,
                                "completed_at": self._now(),
                            },
                        )
                        yield sse(
                            "observing",
                            {
                                "tool_name": tool_name,
                                "tool_id": call_id,
                                "step_id": step_id,
                                "summary": "Search results received; analyzing sources.",
                                "success": True,
                                "turn_index": round_index,
                            },
                        )
                        if isinstance(tool_payload, dict) and isinstance(tool_payload.get("tasks"), list):
                            yield sse(
                                "agent_status",
                                {
                                    "phase": "checking",
                                    "message": summarize_tasks(tool_payload["tasks"]),
                                    "active_tools": [],
                                    "task_summary": tool_payload,
                                },
                            )
                        if tool_name == "final" and isinstance(tool_payload, dict) and tool_payload.get("accepted"):
                            forced_answer = str(tool_payload.get("answer") or "").strip()
                            yield sse("agent_status", {"phase": "completed", "message": "All required work was verified.", "active_tools": []})
                            conversation_messages.append({"role": "tool", "tool_call_id": call_id, "content": output})
                            break
                    yield sse(
                        "agent_status",
                        {
                            "phase": "analyzing",
                            "message": "Analyzing the tool result and choosing the next safe step.",
                            "active_tools": [],
                        },
                    )
                    conversation_messages.append(
                        {"role": "tool", "tool_call_id": call_id, "content": output}
                    )
                if forced_answer is not None:
                    break
        except ProviderRequestError as exc:
            self.db.rollback()
            logger.warning("DeepSpace provider request failed", exc_info=True)
            yield sse("error", {"code": "LLM_REQUEST_FAILED", "message": str(exc)})
            return
        except Exception:
            self.db.rollback()
            logger.exception("DeepSpace stream failed")
            yield sse("error", {"code": "DEEPSPACE_STREAM_FAILED", "message": "DeepSpace could not complete this response."})
            return

        yield sse("agent_status", {"phase": "finalizing", "message": "Preparing the final answer.", "active_tools": []})
        final_task_check = self.task_store.check_tasks(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            conversation_id=conversation_id,
        )
        raw_answer = (forced_answer or "".join(answer_parts)).strip()
        if final_task_check["task_count"] and not final_task_check["complete"] and forced_answer is None:
            raw_answer = (
                "I could not safely complete every planned task within this run. "
                "The remaining work is persisted in the DeepSpace task list."
            )
            yield sse(
                "agent_status",
                {
                    "phase": "blocked",
                    "message": "Final output held because todo_check found unfinished work.",
                    "active_tools": [],
                    "task_summary": final_task_check,
                },
            )
        answer = self._append_citations(raw_answer, citations)
        if answer != raw_answer and answer.startswith(raw_answer):
            yield sse("delta", {"text": answer[len(raw_answer):]})
        metadata = {
            "status": "ready",
            "surface": "deepspace",
            "provider_type": candidate.provider_type,
            "model_name": candidate.model_name,
            "task_check": final_task_check,
        }
        if thinking_parts:
            metadata["thinking"] = {"content": "".join(thinking_parts)}
        self.chat.complete_assistant_message(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            user_id=auth.user_id,
            content=answer,
            metadata_json=metadata,
        )
        self.db.commit()
        metrics = {
            "modelName": candidate.model_name,
            "providerType": candidate.provider_type,
            "totalTokens": len(answer.split()),
        }
        if candidate.context_window is not None:
            metrics["contextLimit"] = candidate.context_window
        if candidate.context_window_source:
            metrics["contextLimitSource"] = candidate.context_window_source
        yield sse("metrics", metrics)
        yield sse("done", {"conversation_id": str(conversation_id), "message_id": str(assistant_message.id)})
