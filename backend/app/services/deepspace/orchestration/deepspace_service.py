from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.integrations.models.connector import ConnectorStatus
from app.query.repositories.chat import ChatRepository
from app.query.schemas.structured_response import StructuredAnswerResponse
from app.services.deepspace.execution.agent_executor import AgentExecutor
from app.services.deepspace.missions.mission_registry import MissionRegistry
from app.services.deepspace.deepspace_runtime.runtime_contracts import (
    normalize_conversation_compaction_state,
    resolve_compacted_session_messages,
)
from app.services.deepspace.deepspace_runtime.sse_event_mapper import DeepSpaceSseEventMapper
from app.integrations.services.connector_orchestrator import ConnectorOrchestrator
from app.providers.services.registry import ProviderRegistry
from app.providers.services.selection_service import ProviderSelectionService
from app.providers.services.types import (
    RerankRequest,
    WebSearchRequest,
    WebSearchResponse,
)
from app.query.services.answer_service import AnswerService
from app.query.services.retrieval_service import RetrievalService

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017
CONVERSATION_KIND = "deepspace"
DEFAULT_CONVERSATION_TITLE = "Untitled Note"
MAX_WEB_SEARCH_CONTEXT_CHARS = 6000
logger = logging.getLogger(__name__)
_WEB_SEARCH_INTENT_RE = re.compile(
    r"\b(latest|current|today|now|news|recent|update|pricing|price|stock|weather|release|patch|"
    r"compare|versus|vs\.?|verify|verification|official|live|internet|web)\b",
    re.IGNORECASE,
)
class DeepSpaceService:
    def __init__(self, *, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.chat = ChatRepository(db)
        self.provider_selection = ProviderSelectionService(db, settings)
        self.answer = AnswerService(settings.query_no_result_answer_text, settings)
        self.retrieval = RetrievalService(db, settings)

    @staticmethod
    def _client_storage_connected(auth: AuthContext) -> bool:
        from app.services.deepspace.integrations.client_proxy import client_proxy_registry

        return client_proxy_registry.is_storage_connected(
            str(auth.tenant_id), str(auth.user_id)
        )

    async def _store_client_owned_message(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from app.services.deepspace.integrations.client_proxy import client_proxy_registry

        return await client_proxy_registry.db_proxy_call(
            str(auth.tenant_id),
            str(auth.user_id),
            "db.chats.add_message",
            {
                "conversation_id": str(conversation_id),
                "role": role,
                "content": content,
                "metadata_json": metadata_json or {},
            },
            channel="storage",
        )

    async def _persist_assistant_message(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        message_id: str,
        content: str,
        metadata_json: dict[str, Any],
    ) -> None:
        """Persist replies in the same store used for the conversation.

        When the client-owned storage channel is connected, history is read
        from that encrypted IndexedDB store.  Writing assistant messages to
        PostgreSQL in that mode makes replies disappear after a reload, so the
        write must follow the same ownership decision as user messages.
        """
        if self._client_storage_connected(auth):
            await self._store_client_owned_message(
                auth=auth,
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                metadata_json={**metadata_json, "message_id": message_id},
            )
            return
        self.chat.add_message(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            kind=CONVERSATION_KIND,
            role="assistant",
            content=content,
            metadata_json=metadata_json,
        )

    async def stream_chat(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        conversation_id: uuid.UUID | None,
        note_content: str | None = None,
        thinking_enabled: bool = True,
        web_search_enabled: bool = True,
        background_tasks: Any | None = None,
        agentic_mode: bool = True,
    ) -> AsyncIterator[str]:
        # Delegate to the agentic loop
        async for sse_chunk in self.stream_chat_agentic(
            auth=auth,
            query_text=query_text,
            conversation_id=conversation_id,
            note_content=note_content,
            thinking_enabled=thinking_enabled,
            web_search_enabled=web_search_enabled,
            background_tasks=background_tasks,
            agentic_mode=agentic_mode,
        ):
            yield sse_chunk

    async def stream_chat_agentic(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        conversation_id: uuid.UUID | None,
        note_content: str | None = None,
        thinking_enabled: bool = True,
        web_search_enabled: bool = True,
        background_tasks: Any | None = None,
        agentic_mode: bool = True,
    ) -> AsyncIterator[str]:
        """Agentic chat: runs the full agent loop with tool calling and step visibility."""
        conversation = self._resolve_or_create_conversation(
            auth=auth,
            query_text=query_text,
            conversation_id=conversation_id,
        )
        self._auto_title_conversation(
            tenant_id=auth.tenant_id,
            conversation_id=conversation.id,
            current_title=str(conversation.title or ""),
            query_text=query_text,
        )
        resolved_conversation_id = conversation.id

        execution_mode = MissionRegistry(self.settings, db=self.db).get_execution_mode(
            tenant_id=str(auth.tenant_id),
            user_id=str(auth.user_id),
            conversation_id=str(resolved_conversation_id),
        )

        # Save user message
        if self._client_storage_connected(auth):
            await self._store_client_owned_message(
                auth=auth,
                conversation_id=resolved_conversation_id,
                role="user",
                content=query_text,
            )
        else:
            self.chat.add_message(
                tenant_id=auth.tenant_id,
                conversation_id=resolved_conversation_id,
                kind=CONVERSATION_KIND,
                role="user",
                content=query_text,
            )
        self.db.commit()

        previous_messages = self._build_previous_messages(
            tenant_id=auth.tenant_id,
            conversation_id=resolved_conversation_id,
        )
        # The agent loop is the single controller for chat. The model chooses
        # whether to answer, inspect, search, edit, test, delegate, or ask for
        # approval through its available tools. Routing by keywords or word
        # count caused false orchestration decisions and is intentionally gone.
        stream_kwargs = {
            "auth": auth,
            "conversation_id": resolved_conversation_id,
            "query_text": query_text,
            "previous_messages": previous_messages,
            "note_content": note_content,
            "thinking_enabled": thinking_enabled,
            "web_search_enabled": web_search_enabled,
            "background_tasks": background_tasks,
            "execution_mode": execution_mode,
            "agentic_mode": agentic_mode,
            "append_user_message": False,
        }
        async for chunk in self._stream_agent_turn(**stream_kwargs):
            yield chunk
        return

    async def resume_chat(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        step_id: str,
        tool_id: str,
        approved: bool = True,
        background_tasks: Any | None = None,
    ) -> AsyncIterator[str]:
        """Resumes a paused agent execution after user provides permission."""
        conversation = self.chat.get_conversation(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
        if not conversation:
            raise ApiError(
                code="CONVERSATION_NOT_FOUND",
                message="Conversation not found",
                status_code=404,
            )

        # Find the last assistant message to extract agent_steps history
        messages = self.chat.get_messages(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            kind=CONVERSATION_KIND,
            limit=2,
        )
        last_assistant = next((m for m in messages if m.role == "assistant"), None)
        agent_steps_history = []
        if last_assistant and last_assistant.metadata_json:
            agent_steps_history = last_assistant.metadata_json.get("agent_steps", [])

        previous_messages = self._build_previous_messages(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
        )

        current_agent_steps: list[dict[str, Any]] = list(agent_steps_history)

        is_orchestrated = False
        mission_id = None
        if last_assistant and last_assistant.metadata_json:
            is_orchestrated = bool(
                last_assistant.metadata_json.get("orchestrated", False)
            )
            mission_id = last_assistant.metadata_json.get("mission_id")

        if is_orchestrated and mission_id:
            from app.services.deepspace.orchestration.master_orchestrator import MasterOrchestrator

            registry = MissionRegistry(self.settings, db=self.db)
            registry.resolve_approval(mission_id, step_id, approved)

            if not approved:
                denied_text = "Approval denied. Mission stopped."
                yield DeepSpaceSseEventMapper.encode("delta", {"text": denied_text})
                yield DeepSpaceSseEventMapper.encode("done", {"completed": True})
                if last_assistant is not None:
                    self.chat.create_message_version(
                        tenant_id=auth.tenant_id,
                        message_id=last_assistant.id,
                        content=denied_text,
                        metadata_json={
                            **dict(last_assistant.metadata_json or {}),
                            "mission_summary": "Denied.",
                        },
                        source_type="resume_denied",
                        activate=True,
                    )
                self.db.commit()
                return

            yield DeepSpaceSseEventMapper.encode(
                "start",
                {
                    "message_id": str(last_assistant.id),
                    "conversation_id": str(conversation_id),
                    "started_at": datetime.now(tz=UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "operation": "resume",
                },
            )

            orchestrator = MasterOrchestrator(
                db=self.db,
                auth=auth,
                settings=self.settings,
                background_tasks=background_tasks,
            )

            full_answer_parts: list[str] = []
            thinking_parts: list[str] = []
            agent_steps = list(current_agent_steps)
            for step in agent_steps:
                if (
                    str(step.get("step_id") or "") == step_id
                    and str(step.get("tool_id") or "") == tool_id
                ):
                    step["status"] = "completed"

            awaiting_permission = False
            mission_completed = False
            mission_summary = (
                last_assistant.metadata_json.get("mission_summary")
                if last_assistant.metadata_json
                else None
            )

            try:
                async for event in orchestrator.stream_mission(
                    objective="",
                    conversation_id=conversation_id,
                    execution_mode=registry.get_execution_mode(
                        tenant_id=str(auth.tenant_id),
                        user_id=str(auth.user_id),
                        conversation_id=str(conversation_id),
                    ),
                    mission_id=mission_id,
                ):
                    event_name = str(event.event)
                    payload = dict(event.data or {})
                    lane_type = str(payload.get("lane_type") or "")
                    is_main_lane = lane_type == "main_chat"

                    if event_name == "mission_done":
                        mission_completed = True
                        yield DeepSpaceSseEventMapper.encode(
                            "metrics", {"phase": "complete"}
                        )
                    elif event_name == "mission_summary":
                        mission_summary = str(
                            payload.get("summary") or mission_summary or ""
                        )
                    elif event_name == "approval_request":
                        if is_main_lane:
                            awaiting_permission = True
                            agent_steps.append(
                                {
                                    "step_id": payload.get("step_id"),
                                    "tool_id": payload.get("tool_id"),
                                    "tool_name": payload.get("tool_name"),
                                    "tool_input": payload.get("tool_input"),
                                    "permission_level": payload.get("permission_level"),
                                    "status": "awaiting_approval",
                                    "message": payload.get("message"),
                                }
                            )
                    elif event_name == "lane_delta" and is_main_lane:
                        text = str(payload.get("text") or "")
                        if text:
                            full_answer_parts.append(text)
                        step_data = {"text": text, **payload}
                        agent_steps.append(step_data)
                        payload = step_data
                    elif event_name == "lane_observation" and is_main_lane:
                        observed_at = str(
                            payload.get("observed_at")
                            or datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
                        )
                        agent_steps.append(
                            {
                                "type": "observing",
                                "status": "completed",
                                "step_id": payload.get("step_id"),
                                "tool_id": payload.get("tool_id"),
                                "tool_name": payload.get("tool_name"),
                                "tool_input": payload.get("tool_input"),
                                "summary": payload.get("summary"),
                                "toolOutput": payload.get("summary")
                                or payload.get("message"),
                                "success": bool(payload.get("success", True)),
                                "startedAt": observed_at,
                                "completedAt": observed_at,
                            }
                        )
                    elif event_name == "lane_step_summary" and is_main_lane:
                        agent_steps.append(payload)
                    elif event_name == "lane_result" and is_main_lane:
                        output = str(
                            payload.get("output") or payload.get("summary") or ""
                        )
                        if output and not full_answer_parts:
                            full_answer_parts.append(output)

                    for out_event in DeepSpaceSseEventMapper.map_orchestrator_event(
                        event_name=event_name,
                        payload=payload,
                        is_main_lane=is_main_lane,
                        mission_summary=mission_summary,
                    ):
                        yield DeepSpaceSseEventMapper.encode_stream_event(out_event)
            finally:
                if not mission_completed and mission_id:
                    registry.request_cancellation(mission_id)

            metadata = self._build_assistant_metadata(
                provider_type=last_assistant.metadata_json.get("provider_type"),
                model_name=last_assistant.metadata_json.get("model_name"),
                context_limit=last_assistant.metadata_json.get("context_limit"),
                context_limit_source=last_assistant.metadata_json.get(
                    "context_limit_source"
                ),
                agent_steps=agent_steps,
                thinking_parts=thinking_parts,
                thinking_enabled=True,
                latency_timeline=last_assistant.metadata_json.get("latency_timeline")
                or [],
                started_at=last_assistant.metadata_json.get("started_at")
                or datetime.now(tz=UTC).isoformat(),
            )
            metadata["orchestrated"] = True
            metadata["mission_id"] = mission_id
            if mission_summary:
                metadata["mission_summary"] = mission_summary

            if awaiting_permission:
                self.chat.create_message_version(
                    tenant_id=auth.tenant_id,
                    message_id=last_assistant.id,
                    content="".join(full_answer_parts).strip(),
                    metadata_json=metadata,
                    source_type="resume_paused",
                    activate=True,
                )
                self.db.commit()
                return

            final_text = "".join(full_answer_parts).strip()
            if final_text:
                self.chat.create_message_version(
                    tenant_id=auth.tenant_id,
                    message_id=last_assistant.id,
                    content=final_text,
                    metadata_json=metadata,
                    source_type="resume_success",
                    activate=True,
                )
                self.db.commit()
            return

        pending_request = next(
            (
                step
                for step in reversed(current_agent_steps)
                if str(step.get("step_id") or "") == step_id
                and str(step.get("tool_id") or "") == tool_id
                and isinstance(step.get("tool_name"), str)
                and isinstance(step.get("tool_input"), dict)
            ),
            None,
        )
        if pending_request is None:
            raise ApiError(
                code="PENDING_TOOL_NOT_FOUND",
                message="Pending DeepSpace tool request was not found.",
                status_code=404,
            )
        if not approved:
            denied_text = "Approval denied. Agent execution stopped."
            yield DeepSpaceSseEventMapper.encode("delta", {"text": denied_text})
            yield DeepSpaceSseEventMapper.encode("done", {"completed": True})
            if last_assistant is not None:
                self.chat.create_message_version(
                    tenant_id=auth.tenant_id,
                    message_id=last_assistant.id,
                    content=denied_text,
                    metadata_json={
                        "agent_steps": current_agent_steps,
                    },
                    source_type="resume_denied",
                    activate=True,
                )
            self.db.commit()
            return

        agent = AgentExecutor(
            db=self.db,
            settings=self.settings,
            auth=auth,
            background_tasks=background_tasks,
            execution_mode=MissionRegistry(
                self.settings, db=self.db
            ).get_execution_mode(
                tenant_id=str(auth.tenant_id),
                user_id=str(auth.user_id),
                conversation_id=str(conversation_id),
            ),
        )
        yield DeepSpaceSseEventMapper.encode(
            "tool_start",
            {
                "step_id": step_id,
                "tool_id": tool_id,
                "tool_name": str(pending_request["tool_name"]),
                "tool_input": dict(pending_request["tool_input"]),
                "permission_level": "approved",
                "started_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            },
        )

        async def _resume_tool_sink(payload: dict[str, str]) -> None:
            yield_data = {
                "step_id": step_id,
                "tool_id": tool_id,
                "tool_name": str(pending_request["tool_name"]),
                "tool_input": dict(pending_request["tool_input"]),
                "text": payload.get("text", ""),
                "stream": payload.get("stream"),
                "bash_id": payload.get("bash_id"),
            }
            nonlocal_chunks.append(yield_data)

        nonlocal_chunks: list[dict[str, Any]] = []
        paused_tool_call = {
            "id": tool_id,
            "type": "function",
            "function": {
                "name": str(pending_request["tool_name"]),
                "arguments": json.dumps(pending_request["tool_input"]),
            },
        }
        tool_result = await agent.tool_executor.execute(
            str(pending_request["tool_name"]),
            dict(pending_request["tool_input"]),
            background_tasks=background_tasks,
            event_sink=_resume_tool_sink,
        )
        for item in nonlocal_chunks:
            yield DeepSpaceSseEventMapper.encode("tool_delta", item)
        yield DeepSpaceSseEventMapper.encode(
            "tool_result",
            {
                "step_id": step_id,
                "tool_id": tool_id,
                "tool_name": str(pending_request["tool_name"]),
                "tool_input": dict(pending_request["tool_input"]),
                "success": tool_result.success,
                "output": tool_result.output[:8000],
                "completed_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            },
        )
        resumed_messages = list(previous_messages)
        resumed_messages.append(
            {"role": "assistant", "content": None, "tool_calls": [paused_tool_call]}
        )
        resumed_messages.append(
            {"role": "tool", "tool_call_id": tool_id, "content": tool_result.output}
        )
        async for chunk in self._stream_agent_turn(
            auth=auth,
            conversation_id=conversation_id,
            query_text="",
            previous_messages=resumed_messages,
            note_content=None,
            thinking_enabled=True,
            web_search_enabled=True,
            background_tasks=background_tasks,
            assistant_message_id=(
                last_assistant.id if last_assistant is not None else None
            ),
            operation="resume",
            append_user_message=False,
            execution_mode=MissionRegistry(
                self.settings, db=self.db
            ).get_execution_mode(
                tenant_id=str(auth.tenant_id),
                user_id=str(auth.user_id),
                conversation_id=str(conversation_id),
            ),
            seed_agent_steps=current_agent_steps
            + [
                {
                    "step_id": step_id,
                    "tool_id": tool_id,
                    "tool_name": str(pending_request["tool_name"]),
                    "tool_input": dict(pending_request["tool_input"]),
                    "success": tool_result.success,
                    "output": tool_result.output[:8000],
                }
            ],
        ):
            yield chunk

    async def regenerate_message_stream(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        thinking_enabled: bool = True,
        web_search_enabled: bool = True,
        background_tasks: Any | None = None,
        agentic_mode: bool = True,
    ) -> AsyncIterator[str]:
        user_message, assistant_message = self.chat.get_latest_turn_pair(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
        if user_message is None or assistant_message is None:
            raise ApiError(
                code="TURN_NOT_FOUND",
                message="Latest DeepSpace turn was not found.",
                status_code=404,
            )
        if assistant_message.id != assistant_message_id:
            raise ApiError(
                code="MESSAGE_REGENERATE_NOT_ALLOWED",
                message="Only the latest DeepSpace assistant message can be regenerated.",
                status_code=409,
            )
        previous_messages = self._build_previous_messages_until(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            through_message_id=user_message.id,
        )
        async for chunk in self._stream_agent_turn(
            auth=auth,
            conversation_id=conversation_id,
            query_text=self._message_display_content(user_message),
            previous_messages=previous_messages[:-1],
            note_content=None,
            thinking_enabled=thinking_enabled,
            web_search_enabled=web_search_enabled,
            background_tasks=background_tasks,
            assistant_message_id=assistant_message.id,
            operation="regenerate",
            execution_mode=MissionRegistry(
                self.settings, db=self.db
            ).get_execution_mode(
                tenant_id=str(auth.tenant_id),
                user_id=str(auth.user_id),
                conversation_id=str(conversation_id),
            ),
            agentic_mode=agentic_mode,
        ):
            yield chunk

    async def edit_and_regenerate_message_stream(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        user_message_id: uuid.UUID,
        updated_content: str,
        thinking_enabled: bool = True,
        web_search_enabled: bool = True,
        background_tasks: Any | None = None,
        agentic_mode: bool = True,
    ) -> AsyncIterator[str]:
        user_message, assistant_message = self.chat.get_latest_turn_pair(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            user_id=auth.user_id,
            kind=CONVERSATION_KIND,
        )
        if user_message is None or assistant_message is None:
            raise ApiError(
                code="TURN_NOT_FOUND",
                message="Latest DeepSpace turn was not found.",
                status_code=404,
            )
        if user_message.id != user_message_id:
            raise ApiError(
                code="MESSAGE_EDIT_NOT_ALLOWED",
                message="Only the latest DeepSpace user message can be edited.",
                status_code=409,
            )
        self.chat.create_message_version(
            tenant_id=auth.tenant_id,
            message_id=user_message.id,
            content=updated_content,
            metadata_json=self._message_active_metadata(user_message),
            source_type="user_edit",
            activate=True,
        )
        self.db.commit()
        previous_messages = self._build_previous_messages_until(
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            through_message_id=user_message.id,
        )
        async for chunk in self._stream_agent_turn(
            auth=auth,
            conversation_id=conversation_id,
            query_text=updated_content,
            previous_messages=previous_messages[:-1],
            note_content=None,
            thinking_enabled=thinking_enabled,
            web_search_enabled=web_search_enabled,
            background_tasks=background_tasks,
            assistant_message_id=assistant_message.id,
            operation="edit_regenerate",
            execution_mode=MissionRegistry(
                self.settings, db=self.db
            ).get_execution_mode(
                tenant_id=str(auth.tenant_id),
                user_id=str(auth.user_id),
                conversation_id=str(conversation_id),
            ),
            agentic_mode=agentic_mode,
        ):
            yield chunk

    @staticmethod
    def _is_conversational_query(query_text: str) -> bool:
        """Return True if the query is a short conversational message that does
        not need the full agentic loop (tools, planning, multi-step).

        Criteria (all must hold):
        - Stripped length ≤ 120 characters
        - Does not contain agentic trigger keywords (file paths, code blocks,
          command words, task verbs that imply multi-step work).
        """
        text = query_text.strip()
        if not text or len(text) > 120:
            return False

        lowered = text.lower()

        # Pure greetings / acknowledgements → always conversational
        greetings = {
            "hi", "hello", "hey", "yo", "sup", "howdy",
            "ok", "okay", "sure", "thanks", "thank you",
            "great", "cool", "got it", "understood", "noted",
            "yes", "no", "yep", "nope", "agreed",
        }
        if lowered in greetings:
            return True

        # If it contains agentic trigger words → NOT conversational
        agentic_triggers = (
            "create", "build", "write", "implement", "generate", "make",
            "run", "execute", "edit", "update", "fix", "refactor", "deploy",
            "install", "search", "find in", "grep", "analyse", "analyze",
            "summarize", "summarise", "read file", "open file",
            "```", "#!/", ".py", ".ts", ".js", ".sh",
            "/home/", "/opt/", "sudo ", "docker", "git ",
        )
        for trigger in agentic_triggers:
            if trigger in lowered:
                return False

        return True

    async def _stream_agent_turn(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        query_text: str,
        previous_messages: list[dict[str, Any]],
        note_content: str | None,
        thinking_enabled: bool,
        web_search_enabled: bool,
        background_tasks: Any | None,
        assistant_message_id: uuid.UUID | None = None,
        operation: str = "new_turn",
        append_user_message: bool = True,
        seed_agent_steps: list[dict[str, Any]] | None = None,
        execution_mode: str = "auto_review",
        agentic_mode: bool = True,
    ) -> AsyncIterator[str]:
        turn_started = perf_counter()
        latency_timeline: list[dict[str, Any]] = []
        first_activity_emitted = False
        mapper = DeepSpaceSseEventMapper

        def _timeline_payload(phase: str, detail: str | None = None) -> dict[str, Any]:
            elapsed_ms = int((perf_counter() - turn_started) * 1000)
            latency_timeline.append(
                {
                    "label": phase,
                    "atMs": elapsed_ms,
                    **({"detail": detail} if detail else {}),
                }
            )
            return {"phase": phase, "latencyTimeline": list(latency_timeline)}

        message_id = str(assistant_message_id or generate_uuid7_with_fallback())
        started_at = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
        yield mapper.encode(
            "start",
            {
                "message_id": message_id,
                "conversation_id": str(conversation_id),
                "started_at": started_at,
                "operation": operation,
            },
        )
        yield mapper.encode("metrics", _timeline_payload("turn_started"))

        agent = AgentExecutor(
            db=self.db,
            settings=self.settings,
            auth=auth,
            background_tasks=background_tasks,
            execution_mode=execution_mode,
            restricted_tools=(
                ["web_search", "web_fetch", "crawl_url", "search_ecosystem_docs"]
                if not agentic_mode
                else None
            ),
        )
        _ = agent.llm
        context_limit = agent.reported_context_limit
        model_name = agent.model_name
        provider_type = agent.provider_type
        context_limit_source = agent.context_limit_source
        yield mapper.encode(
            "metrics",
            _timeline_payload(
                "runtime_ready",
                f"{provider_type or 'provider'}:{model_name or 'model'}",
            ),
        )
        effective_thinking_enabled = bool(thinking_enabled)
        effective_web_search_enabled = bool(web_search_enabled)
        if append_user_message and self._should_prefetch_web_context(query_text):
            web_context = self._build_web_search_context(
                auth=auth,
                query_text=query_text,
                enabled=True,
            )
            if web_context and web_context.get("content"):
                note_content = self._merge_note_content(
                    note_content,
                    str(web_context["content"]),
                )

        ecosystem_context = self._build_ecosystem_context(auth, query_text)
        if ecosystem_context:
            note_content = self._merge_note_content(note_content, ecosystem_context)

        manual_context = self._build_manual_document_context(auth, query_text)
        if manual_context:
            note_content = self._merge_note_content(note_content, manual_context)

        yield mapper.encode(
            "meta",
            {
                "conversation_id": str(conversation_id),
                "message_id": message_id,
                "trace_id": str(generate_uuid7_with_fallback()),
                "confidence": 1.0,
                "cached": False,
                "agent_mode": True,
                "execution_mode": execution_mode,
                "model_name": model_name,
                "provider_type": provider_type,
                "context_limit": context_limit,
                "context_limit_source": context_limit_source,
            },
        )
        yield mapper.encode("metrics", _timeline_payload("stream_open"))

        full_answer_parts: list[str] = []
        thinking_parts: list[str] = []
        agent_steps: list[dict[str, Any]] = list(seed_agent_steps or [])
        awaiting_permission = False

        async for step_event in agent.run(
            query_text=query_text,
            previous_messages=previous_messages,
            note_content=note_content,
            thinking_enabled=effective_thinking_enabled,
            web_search_enabled=effective_web_search_enabled,
            append_user_message=append_user_message,
        ):
            if step_event.type == "agent_plan":
                agent_steps.append(step_event.data)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "tool_start":
                agent_steps.append(step_event.data)
                if not first_activity_emitted:
                    first_activity_emitted = True
                    yield mapper.encode(
                        "metrics",
                        _timeline_payload("first_activity", "tool_start"),
                    )
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "tool_result":
                agent_steps.append(step_event.data)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "observing":
                observed_at = str(
                    step_event.data.get("observed_at")
                    or datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
                )
                observation_step = {
                    "type": "observing",
                    "status": "completed",
                    "step_id": step_event.data.get("step_id"),
                    "tool_id": step_event.data.get("tool_id"),
                    "tool_name": step_event.data.get("tool_name"),
                    "tool_input": step_event.data.get("tool_input"),
                    "summary": step_event.data.get("summary"),
                    "toolOutput": step_event.data.get("summary")
                    or step_event.data.get("message"),
                    "success": bool(step_event.data.get("success", True)),
                    "startedAt": observed_at,
                    "completedAt": observed_at,
                }
                agent_steps.append(observation_step)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "tool_delta":
                if not first_activity_emitted:
                    first_activity_emitted = True
                    yield mapper.encode(
                        "metrics",
                        _timeline_payload("first_activity", "tool_delta"),
                    )
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "tool_error":
                agent_steps.append(step_event.data)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "permission_request":
                awaiting_permission = True
                agent_steps.append(step_event.data)
                if not first_activity_emitted:
                    first_activity_emitted = True
                    yield mapper.encode(
                        "metrics",
                        _timeline_payload("first_activity", "approval_request"),
                    )
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "ask_user_question":
                awaiting_permission = True
                agent_steps.append(step_event.data)
                if not first_activity_emitted:
                    first_activity_emitted = True
                    yield mapper.encode(
                        "metrics",
                        _timeline_payload("first_activity", "ask_user_question"),
                    )
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "agent_thinking":
                text = step_event.data.get("text", "")
                if text:
                    thinking_parts.append(str(text))
                    # Keep the provider's actual reasoning trace in the
                    # persisted assistant metadata so it remains visible
                    # after the stream completes or the conversation reloads.
                    agent_steps.append(
                        {
                            **step_event.data,
                            "type": "thinking",
                            "status": step_event.data.get("status", "completed"),
                        }
                    )
                    for out_event in mapper.map_agent_step_event(
                        step_type=step_event.type,
                        payload=step_event.data,
                        agent_steps_count=len(agent_steps),
                    ):
                        yield mapper.encode_stream_event(out_event)
            elif step_event.type == "agent_testing":
                agent_steps.append(step_event.data)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "agent_verifying":
                agent_steps.append(step_event.data)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "agent_self_correct":
                agent_steps.append(step_event.data)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "step_start":
                agent_steps.append(step_event.data)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "step_finish":
                agent_steps.append(step_event.data)
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "answer_delta":
                text = step_event.data.get("text", "")
                if text:
                    full_answer_parts.append(str(text))
                    if not first_activity_emitted:
                        first_activity_emitted = True
                        yield mapper.encode(
                            "metrics",
                            _timeline_payload("first_activity", "answer_delta"),
                        )
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "answer_done":
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "final_answer":
                text = step_event.data.get("content", "")
                if text:
                    full_answer_parts.append(str(text))
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)
            elif step_event.type == "step_summary":
                for out_event in mapper.map_agent_step_event(
                    step_type=step_event.type,
                    payload=step_event.data,
                    agent_steps_count=len(agent_steps),
                ):
                    yield mapper.encode_stream_event(out_event)

        metadata = self._build_assistant_metadata(
            provider_type=provider_type,
            model_name=model_name,
            context_limit=context_limit,
            context_limit_source=context_limit_source,
            agent_steps=agent_steps,
            thinking_parts=thinking_parts,
            thinking_enabled=thinking_enabled,
            latency_timeline=latency_timeline,
            started_at=started_at,
            conversation_compaction=getattr(agent, "last_compaction_state", None),
        )
        if awaiting_permission:
            yield mapper.encode("metrics", _timeline_payload("awaiting_approval"))
            await self._persist_assistant_message(
                auth=auth,
                conversation_id=conversation_id,
                message_id=message_id,
                content="",
                metadata_json=metadata,
            )
            self.db.commit()
            return

        if not full_answer_parts:
            error_text = "The selected language model returned no visible answer."
            yield mapper.encode("error", {"code": "EMPTY_MODEL_RESPONSE", "message": error_text})
            await self._persist_assistant_message(
                auth=auth,
                conversation_id=conversation_id,
                message_id=message_id,
                content=error_text,
                metadata_json={**metadata, "error": "EMPTY_MODEL_RESPONSE"},
            )
            self.db.commit()
            return

        final_text = "".join(full_answer_parts).strip()
        if not final_text:
            return
        yield mapper.encode("metrics", _timeline_payload("complete"))
        await self._persist_assistant_message(
            auth=auth,
            conversation_id=conversation_id,
            message_id=message_id,
            content=final_text,
            metadata_json=metadata,
        )
        self.db.commit()
        yield mapper.encode("done", {"total_steps": len(agent_steps)})

    async def _stream_orchestrated_turn(
        self,
        *,
        auth: AuthContext,
        conversation_id: uuid.UUID,
        query_text: str,
        previous_messages: list[dict[str, Any]],
        note_content: str | None,
        thinking_enabled: bool,
        web_search_enabled: bool,
        background_tasks: Any | None,
        execution_mode: str = "auto_review",
        agentic_mode: bool = True,
    ) -> AsyncIterator[str]:
        """Unified DeepSpace/OpenChat turn routed through the global mission orchestrator."""
        turn_started = perf_counter()
        latency_timeline: list[dict[str, Any]] = []
        mapper = DeepSpaceSseEventMapper

        def _timeline_payload(phase: str, detail: str | None = None) -> dict[str, Any]:
            elapsed_ms = int((perf_counter() - turn_started) * 1000)
            latency_timeline.append(
                {
                    "label": phase,
                    "atMs": elapsed_ms,
                    **({"detail": detail} if detail else {}),
                }
            )
            return {"phase": phase, "latencyTimeline": list(latency_timeline)}

        if not isinstance(self.settings, Settings):
            async for chunk in self._stream_agent_turn(
                auth=auth,
                conversation_id=conversation_id,
                query_text=query_text,
                previous_messages=previous_messages,
                note_content=note_content,
                thinking_enabled=thinking_enabled,
                web_search_enabled=web_search_enabled,
                background_tasks=background_tasks,
                execution_mode=execution_mode,
                agentic_mode=agentic_mode,
            ):
                yield chunk
            return

        from app.services.deepspace.orchestration.master_orchestrator import MasterOrchestrator

        message_id = str(generate_uuid7_with_fallback())
        started_at = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
        yield mapper.encode(
            "start",
            {
                "message_id": message_id,
                "conversation_id": str(conversation_id),
                "started_at": started_at,
                "operation": "mission",
            },
        )
        yield mapper.encode("metrics", _timeline_payload("turn_started"))

        runtime_agent = AgentExecutor(
            db=self.db,
            settings=self.settings,
            auth=auth,
            background_tasks=background_tasks,
            execution_mode=execution_mode,
            restricted_tools=(
                ["web_search", "web_fetch", "crawl_url", "search_ecosystem_docs"]
                if not agentic_mode
                else None
            ),
        )
        _ = runtime_agent.llm
        context_limit = runtime_agent.reported_context_limit
        model_name = runtime_agent.model_name
        provider_type = runtime_agent.provider_type
        context_limit_source = runtime_agent.context_limit_source
        yield mapper.encode(
            "metrics",
            _timeline_payload(
                "runtime_ready",
                f"{provider_type or 'provider'}:{model_name or 'model'}",
            ),
        )

        yield mapper.encode(
            "meta",
            {
                "conversation_id": str(conversation_id),
                "message_id": message_id,
                "trace_id": str(generate_uuid7_with_fallback()),
                "confidence": 1.0,
                "cached": False,
                "agent_mode": True,
                "execution_mode": execution_mode,
                "model_name": model_name,
                "provider_type": provider_type,
                "context_limit": context_limit,
                "context_limit_source": context_limit_source,
                "orchestrated": True,
            },
        )
        yield mapper.encode("metrics", _timeline_payload("stream_open"))

        orchestrator = MasterOrchestrator(
            db=self.db,
            auth=auth,
            settings=self.settings,
            background_tasks=background_tasks,
            agent_executor_cls=AgentExecutor,
        )

        full_answer_parts: list[str] = []
        thinking_parts: list[str] = []
        agent_steps: list[dict[str, Any]] = []
        awaiting_permission = False
        mission_id: str | None = None
        mission_summary: str | None = None
        mission_completed = False

        try:
            async for event in orchestrator.stream_mission(
                objective=query_text,
                note_content=note_content,
                previous_messages=previous_messages,
                conversation_id=conversation_id,
                execution_mode=execution_mode,
            ):
                event_name = str(event.event)
                payload = dict(event.data or {})
                lane_type = str(payload.get("lane_type") or "")
                is_main_lane = lane_type == "main_chat"

                if event_name == "mission_start":
                    mission_id = str(payload.get("mission_id") or mission_id or "")
                    yield mapper.encode("metrics", _timeline_payload("mission_started"))
                    for out_event in mapper.map_orchestrator_event(
                        event_name=event_name,
                        payload={**payload, "execution_mode": execution_mode},
                        is_main_lane=is_main_lane,
                        mission_summary=mission_summary,
                    ):
                        yield mapper.encode_stream_event(out_event)
                    continue

                if event_name == "mission_summary":
                    mission_summary = str(
                        payload.get("summary") or mission_summary or ""
                    )
                    for out_event in mapper.map_orchestrator_event(
                        event_name=event_name,
                        payload=payload,
                        is_main_lane=is_main_lane,
                        mission_summary=mission_summary,
                    ):
                        yield mapper.encode_stream_event(out_event)
                    continue

                if event_name == "mission_planning":
                    yield mapper.encode(
                        "metrics", _timeline_payload("mission_planning")
                    )
                    for out_event in mapper.map_orchestrator_event(
                        event_name=event_name,
                        payload=payload,
                        is_main_lane=is_main_lane,
                        mission_summary=mission_summary,
                    ):
                        yield mapper.encode_stream_event(out_event)
                    continue

                if event_name in {"mission_plan", "mission_graph"}:
                    for out_event in mapper.map_orchestrator_event(
                        event_name=event_name,
                        payload=payload,
                        is_main_lane=is_main_lane,
                        mission_summary=mission_summary,
                    ):
                        yield mapper.encode_stream_event(out_event)
                    continue

                if event_name == "mission_done":
                    mission_completed = True
                    yield mapper.encode("metrics", _timeline_payload("complete"))
                    for out_event in mapper.map_orchestrator_event(
                        event_name=event_name,
                        payload=payload,
                        is_main_lane=is_main_lane,
                        mission_summary=mission_summary,
                    ):
                        yield mapper.encode_stream_event(out_event)
                    continue

                if event_name == "approval_request":
                    if is_main_lane:
                        awaiting_permission = True
                        agent_steps.append(
                            {
                                "step_id": payload.get("step_id"),
                                "tool_id": payload.get("tool_id"),
                                "tool_name": payload.get("tool_name"),
                                "tool_input": payload.get("tool_input"),
                                "permission_level": payload.get("permission_level"),
                                "status": "awaiting_approval",
                                "message": payload.get("message"),
                            }
                        )
                    for out_event in mapper.map_orchestrator_event(
                        event_name=event_name,
                        payload=payload,
                        is_main_lane=is_main_lane,
                        mission_summary=mission_summary,
                    ):
                        yield mapper.encode_stream_event(out_event)
                    continue

                if event_name in {"lane_thinking", "lane_agent_thinking"} and is_main_lane:
                    thinking_text = str(payload.get("text") or "")
                    if thinking_text:
                        thinking_parts.append(thinking_text)
                        agent_steps.append({**payload, "type": "thinking", "status": "completed"})
                elif event_name == "lane_delta" and is_main_lane:
                    text = str(payload.get("text") or "")
                    if text:
                        full_answer_parts.append(text)
                    step_data = {"text": text, **payload}
                    agent_steps.append(step_data)
                    payload = step_data
                elif event_name == "lane_observation" and is_main_lane:
                    observed_at = str(
                        payload.get("observed_at")
                        or datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
                    )
                    agent_steps.append(
                        {
                            "type": "observing",
                            "status": "completed",
                            "step_id": payload.get("step_id"),
                            "tool_id": payload.get("tool_id"),
                            "tool_name": payload.get("tool_name"),
                            "tool_input": payload.get("tool_input"),
                            "summary": payload.get("summary"),
                            "toolOutput": payload.get("summary")
                            or payload.get("message"),
                            "success": bool(payload.get("success", True)),
                            "startedAt": observed_at,
                            "completedAt": observed_at,
                        }
                    )
                elif event_name == "lane_step_summary" and is_main_lane:
                    agent_steps.append(payload)
                elif event_name == "lane_result" and is_main_lane:
                    output = str(payload.get("output") or payload.get("summary") or "")
                    if output and not full_answer_parts:
                        full_answer_parts.append(output)
                for out_event in mapper.map_orchestrator_event(
                    event_name=event_name,
                    payload=payload,
                    is_main_lane=is_main_lane,
                    mission_summary=mission_summary,
                ):
                    yield mapper.encode_stream_event(out_event)
        finally:
            if not mission_completed and mission_id:
                logger.info(
                    "Orchestration stream interrupted for tenant %s user %s conversation %s mission %s. Requesting cancellation.",
                    auth.tenant_id,
                    auth.user_id,
                    conversation_id,
                    mission_id,
                )
                from app.services.deepspace.missions.mission_registry import MissionRegistry

                registry = MissionRegistry(self.settings, db=self.db)
                registry.request_cancellation(mission_id)

        metadata = self._build_assistant_metadata(
            provider_type=provider_type,
            model_name=model_name,
            context_limit=context_limit,
            context_limit_source=context_limit_source,
            agent_steps=agent_steps,
            thinking_parts=thinking_parts,
            thinking_enabled=thinking_enabled,
            latency_timeline=latency_timeline,
            started_at=started_at,
        )
        metadata["orchestrated"] = True
        if mission_id:
            metadata["mission_id"] = mission_id
        if mission_summary:
            metadata["mission_summary"] = mission_summary

        if awaiting_permission:
            await self._persist_assistant_message(
                auth=auth,
                conversation_id=conversation_id,
                message_id=str(generate_uuid7_with_fallback()),
                content="",
                metadata_json=metadata,
            )
            self.db.commit()
            return

        if not full_answer_parts:
            error_text = "The selected language model returned no visible answer."
            yield mapper.encode("error", {"code": "EMPTY_MODEL_RESPONSE", "message": error_text})
            await self._persist_assistant_message(
                auth=auth,
                conversation_id=conversation_id,
                message_id=str(generate_uuid7_with_fallback()),
                content=error_text,
                metadata_json={**metadata, "error": "EMPTY_MODEL_RESPONSE"},
            )
            self.db.commit()
            return

        final_text = "".join(full_answer_parts).strip()
        if not final_text:
            return

        await self._persist_assistant_message(
            auth=auth,
            conversation_id=conversation_id,
            message_id=str(generate_uuid7_with_fallback()),
            content=final_text,
            metadata_json=metadata,
        )
        self.db.commit()
        yield mapper.encode("done", {"total_steps": len(agent_steps)})

    @staticmethod
    def _build_assistant_metadata(
        *,
        provider_type: str | None,
        model_name: str | None,
        context_limit: int | None,
        context_limit_source: str | None,
        agent_steps: list[dict[str, Any]],
        thinking_parts: list[str],
        thinking_enabled: bool,
        latency_timeline: list[dict[str, Any]] | None = None,
        started_at: str | None = None,
        conversation_compaction: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "trace_id": None,
            "confidence": 1.0,
            "citations": [],
            "search_mode": "agentic",
            "provider": {
                "type": provider_type or "chat",
                "model": model_name or "deepspace-agent",
                "context_window": context_limit,
            },
            "context_limit": context_limit,
            "context_limit_source": context_limit_source,
            "reasoning_trace": None,
            "status_history": [],
            "files": [],
            "output": [],
            "agent_steps": agent_steps,
            "latency_timeline": list(latency_timeline) if latency_timeline else [],
            "started_at": started_at,
            "conversation_compaction": (
                dict(conversation_compaction or {}) if conversation_compaction else None
            ),
            "thinking": (
                {
                    "content": "".join(thinking_parts).strip(),
                    "enabled": thinking_enabled,
                }
                if thinking_parts
                else None
            ),
            "follow_up_suggestions": [],
        }

    def _message_display_content(self, message: Any) -> str:
        active_version = getattr(message, "active_version", None)
        if active_version is not None and isinstance(active_version.content, str):
            return active_version.content
        return str(getattr(message, "content", ""))

    def _message_active_metadata(self, message: Any) -> dict[str, Any]:
        active_version = getattr(message, "active_version", None)
        if active_version is not None and isinstance(
            active_version.metadata_json, dict
        ):
            return dict(active_version.metadata_json)
        return dict(getattr(message, "metadata_json", {}) or {})

    @staticmethod
    def _message_content_to_text(content: Any) -> str:
        if isinstance(content, StructuredAnswerResponse):
            return json.dumps(content.model_dump(mode="json"), ensure_ascii=False)
        return str(content)

    def _build_previous_messages_until(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        through_message_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        history = self.chat.get_messages(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            kind=CONVERSATION_KIND,
            limit=100,
        )
        previous_messages: list[dict[str, Any]] = []
        for message in history:
            previous_messages.append(
                {
                    "role": message.role,
                    "content": self._message_content_to_text(
                        self._message_display_content(message)
                    ),
                }
            )
            if message.id == through_message_id:
                break
        return previous_messages[-10:]

    def _build_web_search_context(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        enabled: bool,
    ) -> dict[str, Any] | None:
        if not enabled:
            return None

        selection = self.provider_selection.resolve_web_search(
            tenant_id=auth.tenant_id,
            workspace_id=None,
            actor_user_id=auth.user_id,
        )
        candidate = selection.candidates[0] if selection.candidates else None
        if candidate is None:
            return {
                "content": (
                    "Web search was requested, but no healthy Tavily web-search provider is "
                    "configured for this tenant. Answer without claiming live web access."
                ),
                "metadata": {
                    "enabled": True,
                    "used": False,
                    "reason": "provider_unavailable",
                    "provider": None,
                    "results": [],
                },
            }

        try:
            provider = ProviderRegistry(
                self.settings
            ).get_web_search_provider_from_selection(candidate)
            response = provider.search(
                WebSearchRequest(
                    query=query_text,
                    max_results=5,
                    timeout_seconds=int(self.settings.provider_timeout_seconds),
                    search_depth=str(candidate.metadata.get("search_depth") or "basic"),
                    include_answer=True,
                    include_raw_content=False,
                    provider_name=candidate.provider_type,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "content": (
                    "Web search was requested, but the web-search provider failed. Answer "
                    "without claiming live web access."
                ),
                "metadata": {
                    "enabled": True,
                    "used": False,
                    "reason": "provider_failed",
                    "provider": {
                        "type": candidate.provider_type,
                        "source": candidate.source,
                    },
                    "error": str(exc),
                    "results": [],
                },
            }

        ranked_response = self._maybe_rerank_web_results(
            auth=auth,
            query_text=query_text,
            response=response,
        )
        context = self._format_web_search_context(ranked_response)
        metadata_results = [
            {
                "title": item.title,
                "url": item.url,
                "score": item.score,
            }
            for item in ranked_response.results[:5]
        ]
        return {
            "content": context,
            "metadata": {
                "enabled": True,
                "used": True,
                "provider": {
                    "type": candidate.provider_type,
                    "source": candidate.source,
                    "request_id": ranked_response.request_id,
                },
                "answer": ranked_response.answer,
                "results": metadata_results,
                "usage": ranked_response.usage,
            },
        }

    @staticmethod
    def _should_prefetch_web_context(query_text: str) -> bool:
        return bool(_WEB_SEARCH_INTENT_RE.search(query_text))

    @staticmethod
    def _merge_note_content(*parts: str | None) -> str | None:
        cleaned = [
            part.strip() for part in parts if isinstance(part, str) and part.strip()
        ]
        if not cleaned:
            return None
        return "\n\n".join(dict.fromkeys(cleaned))

    def _build_manual_document_context(
        self, auth: AuthContext, query: str
    ) -> str | None:
        """
        Retrieve the most relevant user-uploaded documents for OpenChat context.

        Manual uploads remain separate from web-crawler ecosystem context, but they
        are still injected into the OpenChat agent loop so the assistant can use them
        without requiring the query page.
        """

        if not getattr(self.retrieval, "documents", None) or not callable(
            getattr(self.retrieval, "retrieve", None)
        ):
            return None

        settings = self.settings
        doc_limit = max(
            1, int(getattr(settings, "deepspace_document_context_doc_limit", 5))
        )
        chunk_limit = max(
            1, int(getattr(settings, "deepspace_document_context_chunk_limit", 4))
        )
        max_chars = max(
            1000, int(getattr(settings, "deepspace_document_context_max_chars", 6000))
        )

        documents = self.retrieval.documents.list_accessible_for_user(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            limit=doc_limit * 2,
        )
        manual_documents = [
            doc for doc in documents if getattr(doc, "connector_id", None) is None
        ]
        if not manual_documents:
            return None

        doc_ids = [doc.id for doc in manual_documents[:doc_limit]]
        chunks = self.retrieval.retrieve(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            query=query or "manual documents",
            top_k=doc_limit * chunk_limit,
            document_ids=doc_ids,
            created_at_from=None,
            created_at_to=None,
            source_types=None,
            min_extraction_coverage=None,
            max_extraction_coverage=None,
            search_mode="hybrid",
        )
        if not chunks:
            return None

        sections = [
            "MANUAL DOCUMENT CONTEXT:",
            "Use these uploaded documents when they are relevant to the user's request.",
        ]
        per_doc_counts: dict[str, int] = {}
        for chunk in chunks:
            doc_key = str(chunk.document_id)
            current_count = per_doc_counts.get(doc_key, 0)
            if current_count >= chunk_limit:
                continue
            per_doc_counts[doc_key] = current_count + 1
            content = " ".join(str(chunk.content or "").split())[:1200]
            sections.append(
                f"[{len(sections)}] Source: {chunk.filename}\nContent: {content}"
            )

        return "\n\n".join(sections)[:max_chars]

    def _maybe_rerank_web_results(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        response: WebSearchResponse,
    ) -> WebSearchResponse:
        if len(response.results) < 2:
            return response
        selection = self.provider_selection.resolve_reranking(
            tenant_id=auth.tenant_id,
            workspace_id=None,
            actor_user_id=auth.user_id,
        )
        candidate = selection.candidates[0] if selection.candidates else None
        if candidate is None:
            return response
        try:
            provider = ProviderRegistry(
                self.settings
            ).get_reranker_provider_from_selection(candidate)
            reranked = provider.rerank(
                RerankRequest(
                    query=query_text,
                    documents=[item.content for item in response.results],
                    model=candidate.model_name,
                    top_n=min(5, len(response.results)),
                    timeout_seconds=int(self.settings.provider_timeout_seconds),
                    provider_name=candidate.provider_type,
                )
            )
        except Exception:  # noqa: BLE001
            return response
        ordered = [
            response.results[item.index]
            for item in reranked.results
            if 0 <= item.index < len(response.results)
        ]
        if not ordered:
            return response
        return WebSearchResponse(
            query=response.query,
            answer=response.answer,
            results=ordered,
            response_time=response.response_time,
            request_id=response.request_id,
            usage=response.usage,
        )

    @staticmethod
    def _format_web_search_context(response: WebSearchResponse) -> str:
        sections = [
            "WEB SEARCH RESULTS:",
            "The user enabled live web search for this turn. Use these external web results when answering. Cite source URLs inline when using them. Do not invent sources.",
        ]
        if response.answer:
            sections.append(f"Tavily answer summary:\n{response.answer.strip()}")
        for index, item in enumerate(response.results[:5], start=1):
            snippet = " ".join(item.content.split())[:900]
            sections.append(
                f"[{index}] {item.title}\nURL: {item.url}\nSnippet: {snippet}"
            )
        return "\n\n".join(sections)[:MAX_WEB_SEARCH_CONTEXT_CHARS]

    def _resolve_or_create_conversation(
        self,
        *,
        auth: AuthContext,
        query_text: str,
        conversation_id: uuid.UUID | None,
    ) -> Any:
        if conversation_id is not None:
            conversation = self.chat.get_conversation(
                tenant_id=auth.tenant_id,
                conversation_id=conversation_id,
                user_id=auth.user_id,
                kind=CONVERSATION_KIND,
            )
            if conversation is None:
                from app.core.errors import ApiError

                raise ApiError(
                    code="CONVERSATION_NOT_FOUND",
                    message="Conversation not found",
                    status_code=404,
                )
            return conversation

        conversation = self.chat.create_conversation(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            title=query_text[:50] + "..." if len(query_text) > 50 else query_text,
            kind=CONVERSATION_KIND,
        )
        self.db.commit()
        return conversation

    def _auto_title_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        current_title: str,
        query_text: str,
    ) -> None:
        normalized_title = current_title.strip()
        if normalized_title and normalized_title != DEFAULT_CONVERSATION_TITLE:
            return

        next_title = query_text[:50].strip()
        if not next_title:
            return
        if len(query_text) > 50:
            next_title = f"{next_title}..."

        updated = self.chat.update_conversation_title(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            title=next_title,
            kind=CONVERSATION_KIND,
        )
        if updated:
            self.db.commit()

    def _build_previous_messages(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        history = list(
            self.chat.get_messages(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                kind=CONVERSATION_KIND,
                limit=100,
            )
        )
        history_payload: list[dict[str, Any]] = []
        latest_compaction = None
        for message in history:
            active_version = getattr(message, "active_version", None)
            content = (
                active_version.content
                if active_version is not None
                else message.content
            )
            metadata = (
                dict(active_version.metadata_json)
                if active_version is not None
                and isinstance(active_version.metadata_json, dict)
                else dict(getattr(message, "metadata_json", {}) or {})
            )
            compacted_state = normalize_conversation_compaction_state(
                metadata.get("conversation_compaction")
            )
            if compacted_state is not None:
                latest_compaction = compacted_state
            if not content:
                continue
            history_payload.append(
                {
                    "id": str(message.id),
                    "message_id": str(message.id),
                    "role": message.role,
                    "content": content,
                }
            )
        items = resolve_compacted_session_messages(
            history_messages=history_payload,
            compaction_state=latest_compaction,
        )
        return items[-10:]

    def _handle_action_intent(
        self,
        auth: AuthContext,
        query: str,
        orchestrator: ConnectorOrchestrator,
        background_tasks: Any | None = None,
    ) -> str | None:
        """
        Parses action intent and triggers the appropriate connector tasks.
        Returns a system message to inform the LLM about the triggered actions.
        """
        q = query.lower()
        actions_taken = []

        # 1. Multiple URL / Web Crawler detection
        urls = re.findall(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            query,
        )
        if urls:
            from app.integrations.repositories.integrations import IntegrationRepository

            repo = IntegrationRepository(self.db)
            connectors = repo.get_connectors(auth.tenant_id)
            crawler = next(
                (c for c in connectors if c.integration.slug == "web-crawler"), None
            )

            if crawler:
                # If multiple URLs, we update to the first one for now, but acknowledge all
                target_url = urls[0]
                crawler.config["url"] = target_url
                self.db.add(crawler)
                self.db.commit()

                if background_tasks:
                    background_tasks.add_task(
                        orchestrator.sync_connector,
                        crawler.id,
                        crawler.tenant_id,
                    )
                else:
                    orchestrator.sync_connector(crawler.id, crawler.tenant_id)

                url_list = ", ".join(urls)
                actions_taken.append(f"Initiated high-speed crawl for: {url_list}")
            else:
                return "ACTION FAILED: No Web Crawler is configured. Tell the user they need to add a Web Crawler source first."

        # 2. Service Sync detection (GitHub, Drive, Notion, Slack, Gmail, Calendar)
        services = [
            "github",
            "google-drive",
            "notion",
            "slack",
            "gmail",
            "google-calendar",
        ]
        for service in services:
            shorthand = service.split("-")[-1]
            if shorthand in q or service.replace("-", " ") in q or service in q:
                from app.integrations.repositories.integrations import IntegrationRepository

                repo = IntegrationRepository(self.db)
                connectors = repo.get_connectors(auth.tenant_id)
                target = next(
                    (c for c in connectors if c.integration.slug == service), None
                )

                if target:
                    if background_tasks:
                        background_tasks.add_task(
                            orchestrator.sync_connector,
                            target.id,
                            target.tenant_id,
                        )
                    else:
                        orchestrator.sync_connector(target.id, target.tenant_id)
                    actions_taken.append(
                        f"Triggered synchronization for {service} ({target.name})"
                    )

        if actions_taken:
            summary = " | ".join(actions_taken)
            return f"AUTONOMOUS ACTIONS EXECUTED: {summary}. Tell the user exactly which actions you have initiated to refresh their knowledge base."

        return None

    def _build_ecosystem_context(self, auth: AuthContext, query: str) -> str | None:
        """
        Retrieves context ONLY from web-crawler documents for the current tenant.
        Ensures complete isolation from manually uploaded documents.
        """
        if not callable(getattr(self.db, "execute", None)):
            return None

        from sqlalchemy import select

        from app.documents.models.document import Document
        from app.integrations.models.connector import Connector
        from app.integrations.models.integration import Integration

        # 1. Find all web-crawler connector IDs for this tenant
        stmt = (
            select(Connector.id)
            .join(Integration, Integration.id == Connector.integration_id)
            .where(
                Connector.tenant_id == auth.tenant_id,
                Integration.slug == "web-crawler",
                Connector.status == ConnectorStatus.ACTIVE,
            )
        )
        crawler_connector_ids = self.db.execute(stmt).scalars().all()

        if not crawler_connector_ids:
            return None

        # 2. Find all document IDs associated with these connectors
        doc_stmt = select(Document.id).where(
            Document.tenant_id == auth.tenant_id,
            Document.connector_id.in_(crawler_connector_ids),
            Document.status == "processed",
            Document.is_deleted == False,
        )
        ecosystem_doc_ids = self.db.execute(doc_stmt).scalars().all()

        if not ecosystem_doc_ids:
            return None

        # 3. Perform targeted retrieval
        chunks = self.retrieval.retrieve(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            query=query,
            top_k=8,
            document_ids=ecosystem_doc_ids,
            created_at_from=None,
            created_at_to=None,
            source_types=None,
            min_extraction_coverage=None,
            max_extraction_coverage=None,
            search_mode="hybrid",
        )

        if not chunks:
            return None

        # 4. Format the context
        sections = [
            "WEB CRAWLER DOCUMENT CONTEXT:",
            "Use these internal crawler results to answer if relevant.",
        ]
        for i, chunk in enumerate(chunks, 1):
            sections.append(
                f"[{i}] Source: {chunk.filename}\nContent: {chunk.content[:1200]}"
            )

        return "\n\n".join(sections)
