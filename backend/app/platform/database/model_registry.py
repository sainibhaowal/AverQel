"""Import all feature-owned ORM models for SQLAlchemy/Alembic discovery."""

from app.auth.models.api_key import ApiKey
from app.auth.models.refresh_token import RefreshToken
from app.auth.models.revoked_access_token import RevokedAccessToken
from app.auth.models.role import Role
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.deepspace.models.agent_activity import AgentActivity
from app.deepspace.models.agent_audit import AgentAuditLog
from app.deepspace.models.agent_memory import AgentMemory
from app.deepspace.models.agent_runtime_preference import AgentRuntimePreference
from app.deepspace.models.agent_todo import AgentTodo
from app.deepspace.models.mission_snapshot import DeepSpaceMissionSnapshot
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.collection import (
    CollectionChatMessage,
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
    UserPresence,
)
from app.documents.models.collection_notification import CollectionNotification
from app.documents.models.data_deletion import DataDeletion
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.ingestion.models.ingestion_job import IngestionJob
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.connector_secret import ConnectorSecret
from app.integrations.models.integration import Integration
from app.integrations.models.mcp_connection_policy import MCPConnectionPolicy
from app.integrations.models.mcp_server import (
    MCPEvent,
    MCPOAuthToken,
    MCPOAuthTransaction,
    MCPRegistryEntry,
    MCPServer,
)
from app.providers.models.provider_assignment import ProviderAssignment
from app.providers.models.provider_config import ProviderConfig
from app.providers.models.provider_health_check import ProviderHealthCheck
from app.providers.models.provider_model_cache import ProviderModelCache
from app.providers.models.provider_secret import ProviderSecret
from app.providers.models.provider_usage_record import ProviderUsageRecord
from app.query.models.comment import Comment
from app.query.models.conversation import Conversation
from app.query.models.feedback import Feedback
from app.query.models.message import Message
from app.query.models.message_version import MessageVersion
from app.query.models.pinned_finding import PinnedFinding
from app.query.models.query import Query
from app.query.models.query_citation import QueryCitation
from app.system.models.audit_log import AuditLog
from app.system.models.break_glass_grant import BreakGlassGrant
from app.system.models.idempotency_key import IdempotencyKey
from app.system.models.support_ticket import SupportTicket
from app.system.models.usage_record import UsageRecord

__all__ = [
    "Tenant",
    "User",
    "Role",
    "UserRole",
    "RefreshToken",
    "RevokedAccessToken",
    "ApiKey",
    "Document",
    "DocumentCollection",
    "CollectionPermission",
    "CollectionDocument",
    "CollectionChatMessage",
    "UserPresence",
    "CollectionNotification",
    "IngestionJob",
    "Query",
    "QueryCitation",
    "ProviderConfig",
    "ProviderSecret",
    "ProviderModelCache",
    "ProviderAssignment",
    "ProviderHealthCheck",
    "ProviderUsageRecord",
    "DocumentChunk",
    "ChunkEmbedding",
    "IdempotencyKey",
    "AuditLog",
    "BreakGlassGrant",
    "DataDeletion",
    "DeepSpaceMissionSnapshot",
    "Conversation",
    "Message",
    "MessageVersion",
    "Feedback",
    "PinnedFinding",
    "Comment",
    "UsageRecord",
    "SupportTicket",
    "Integration",
    "Connector",
    "ConnectorStatus",
    "ConnectorSecret",
    "MCPConnectionPolicy",
    "AgentActivity",
    "AgentAuditLog",
    "AgentMemory",
    "AgentTodo",
    "AgentRuntimePreference",
    "MCPServer",
    "MCPRegistryEntry",
    "MCPEvent",
    "MCPOAuthToken",
    "MCPOAuthTransaction",
]
