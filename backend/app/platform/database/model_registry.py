"""Import all feature-owned ORM models for SQLAlchemy/Alembic discovery."""

from app.auth.models.api_key import ApiKey
from app.auth.models.auth_session import AuthSession
from app.auth.models.oauth_identity import OAuthIdentity
from app.auth.models.refresh_token import RefreshToken
from app.auth.models.revoked_access_token import RevokedAccessToken
from app.auth.models.role import Role
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.deepspace.models.agent_activity import AgentActivity
from app.deepspace.models.agent_memory import AgentMemory
from app.deepspace.models.agent_memory_preferences import AgentMemoryPreferences
from app.deepspace.models.agent_runtime import (
    DeepSpaceAgentRun,
    DeepSpaceAgentStep,
    DeepSpaceRunEvent,
)
from app.deepspace.models.agent_todo import AgentTodo
from app.deepspace.models.artifact_job import DeepSpaceArtifactJob
from app.deepspace.models.context_epoch import DeepSpaceContextEpoch
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.conversation_context_summary import (
    DeepSpaceConversationContextSummary,
)
from app.deepspace.models.conversation_retrieval_chunk import (  # noqa: F401
    DeepSpaceConversationRetrievalChunk,
)
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.deepspace.models.message import Message
from app.deepspace.models.message_version import MessageVersion
from app.deepspace.models.mission_snapshot import DeepSpaceMissionSnapshot
from app.deepspace.models.queue_control import DeepSpaceQueueControl
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.models.request_metric import DeepSpaceRequestMetric
from app.deepspace.models.research import DeepSpaceResearchRun, DeepSpaceResearchSource
from app.deepspace.models.schedule import DeepSpaceSchedule
from app.deepspace.models.schedule_run import DeepSpaceScheduleRun
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.models.workspace_file_version import DeepSpaceWorkspaceFileVersion
from app.deepspace.models.workspace_folder import DeepSpaceWorkspaceFolder
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.collection import (
    CollectionChatDelivery,
    CollectionChatEpoch,
    CollectionChatMedia,
    CollectionChatMessage,
    CollectionDocument,
    CollectionPermission,
    DocumentCollection,
    UserPresence,
)
from app.documents.models.collection_notification import CollectionNotification
from app.documents.models.collection_security import (
    CollectionChatBlock,
    CollectionChatReport,
    CollectionDevice,
    CollectionModerationAction,
    CollectionPushDelivery,
    CollectionPushSubscription,
)
from app.documents.models.data_deletion import DataDeletion
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.documents.models.organization import (
    DocumentAIAction,
    DocumentAutomationSchedule,
    DocumentAutomationScheduleRule,
    DocumentAutomationScheduleRun,
    DocumentClassificationApplication,
    DocumentClassificationRule,
    DocumentClassificationRun,
    DocumentFolder,
    DocumentFolderAssignment,
    DocumentSavedView,
    DocumentShare,
    DocumentShareLink,
    DocumentSmartCollection,
    DocumentSmartCollectionEvaluation,
    DocumentTag,
    DocumentTagAssignment,
    DocumentWebhookDelivery,
    DocumentWebhookSubscription,
)
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
from app.query.models.feedback import Feedback
from app.query.models.pinned_finding import PinnedFinding
from app.query.models.query import Query
from app.query.models.query_citation import QueryCitation
from app.system.models.app_feedback import AppFeedback, FeedbackCampaign
from app.system.models.app_feedback_message import AppFeedbackMessage
from app.system.models.audit_log import AuditLog
from app.system.models.break_glass_grant import BreakGlassGrant
from app.system.models.idempotency_key import IdempotencyKey
from app.system.models.notification_delivery import NotificationDelivery  # noqa: F401
from app.system.models.storage_cleanup import StorageCleanupJob
from app.system.models.storage_lifecycle import (
    StorageArchiveManifest,
    StorageLifecycleItem,
    StorageQuotaReservation,
    StorageReconciliationRun,
    StorageRetentionDecision,
    StorageRetentionRun,
)
from app.system.models.support_ticket import SupportTicket
from app.system.models.support_ticket_attachment import SupportTicketAttachment
from app.system.models.support_ticket_message import SupportTicketMessage
from app.system.models.tenant_storage_allocation import TenantStorageAllocation
from app.system.models.usage_record import UsageRecord
from app.system.models.user_notification import UserNotification
from app.system.models.user_notification_preference import UserNotificationPreference  # noqa: F401

__all__ = [
    "Tenant",
    "User",
    "Role",
    "UserRole",
    "OAuthIdentity",
    "AuthSession",
    "RefreshToken",
    "RevokedAccessToken",
    "ApiKey",
    "Document",
    "DocumentCollection",
    "CollectionPermission",
    "CollectionDocument",
    "CollectionChatMessage",
    "CollectionChatEpoch",
    "CollectionChatMedia",
    "CollectionChatDelivery",
    "UserPresence",
    "CollectionNotification",
    "CollectionDevice",
    "CollectionChatBlock",
    "CollectionChatReport",
    "CollectionModerationAction",
    "CollectionPushSubscription",
    "CollectionPushDelivery",
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
    "DocumentTag",
    "DocumentTagAssignment",
    "DocumentFolder",
    "DocumentFolderAssignment",
    "DocumentSavedView",
    "DocumentSmartCollection",
    "DocumentSmartCollectionEvaluation",
    "DocumentShare",
    "DocumentShareLink",
    "DocumentAIAction",
    "DocumentClassificationRule",
    "DocumentClassificationRun",
    "DocumentClassificationApplication",
    "DocumentAutomationScheduleRule",
    "DocumentAutomationScheduleRun",
    "DocumentAutomationSchedule",
    "DocumentWebhookSubscription",
    "DocumentWebhookDelivery",
    "ChunkEmbedding",
    "IdempotencyKey",
    "AuditLog",
    "BreakGlassGrant",
    "DataDeletion",
    "StorageCleanupJob",
    "StorageLifecycleItem",
    "StorageQuotaReservation",
    "StorageArchiveManifest",
    "StorageReconciliationRun",
    "StorageRetentionRun",
    "StorageRetentionDecision",
    "TenantStorageAllocation",
    "Conversation",
    "Message",
    "MessageVersion",
    "DeepSpaceResearchRun",
    "DeepSpaceResearchSource",
    "DeepSpaceSchedule",
    "DeepSpaceScheduleRun",
    "DeepSpaceMediaArtifact",
    "DeepSpaceWorkspaceFile",
    "DeepSpaceWorkspaceFolder",
    "DeepSpaceWorkspaceFileVersion",
    "Feedback",
    "PinnedFinding",
    "Comment",
    "UsageRecord",
    "SupportTicket",
    "SupportTicketMessage",
    "SupportTicketAttachment",
    "AppFeedbackMessage",
    "UserNotification",
    "UserNotificationPreference",
    "NotificationDelivery",
    "Integration",
    "Connector",
    "ConnectorStatus",
    "ConnectorSecret",
    "MCPConnectionPolicy",
    "AgentMemory",
    "AgentMemoryPreferences",
    "DeepSpaceContextEpoch",
    "DeepSpaceConversationContextSummary",
    "AppFeedback",
    "FeedbackCampaign",
    "DeepSpaceAgentRun",
    "DeepSpaceArtifactJob",
    "DeepSpaceQueuedTurn",
    "DeepSpaceQueueControl",
    "DeepSpaceRequestMetric",
    "DeepSpaceAgentStep",
    "DeepSpaceRunEvent",
    "DeepSpaceLibraryUpload",
    "AgentTodo",
    "AgentActivity",
    "DeepSpaceMissionSnapshot",
    "MCPServer",
    "MCPRegistryEntry",
    "MCPEvent",
    "MCPOAuthToken",
    "MCPOAuthTransaction",
]
