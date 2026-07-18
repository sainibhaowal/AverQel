import { fetchWithAuth } from "@/lib/api";

export type ProviderCatalogEntry = {
  provider_type: string;
  display_name: string;
  auth_modes: string[];
  supports_chat: boolean;
  supports_embeddings: boolean;
  supports_reranking?: boolean;
  supports_web_search?: boolean;
  supports_model_listing: boolean;
  supports_model_install: boolean;
  supports_account_linking: boolean;
  is_local: boolean;
};

export type ProviderSecretSummary = {
  secret_type: string;
  masked_value: string;
  expires_at: string | null;
  metadata: Record<string, unknown>;
};

export type ProviderHealth = {
  status: string;
  latency_ms: number | null;
  http_status: number | null;
  error_code: string | null;
  error_message_redacted: string | null;
  metadata_json: Record<string, unknown>;
  checked_at: string | null;
};

export type ProviderConfig = {
  id: string;
  tenant_id: string;
  workspace_id: string | null;
  owner_user_id?: string | null;
  visibility_scope?: string;
  provider_type: string;
  display_name: string;
  api_base_url: string | null;
  auth_mode: string;
  enabled: boolean;
  is_local: boolean;
  supports_chat: boolean;
  supports_embeddings: boolean;
  supports_reranking?: boolean;
  supports_web_search?: boolean;
  supports_model_listing: boolean;
  supports_model_install: boolean;
  default_chat_model: string | null;
  default_embedding_model: string | null;
  default_reranker_model?: string | null;
  timeout_seconds: number;
  priority: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  secrets: ProviderSecretSummary[];
  latest_health: ProviderHealth | null;
};

export type ProviderModel = {
  id: string | null;
  provider_config_id: string | null;
  model_name: string;
  model_kind: string;
  display_name: string | null;
  context_window: number | null;
  capabilities_json: Record<string, unknown>;
  is_available: boolean;
  last_seen_at: string | null;
};

export type ProviderAssignment = {
  id: string;
  tenant_id: string;
  workspace_id: string | null;
  owner_user_id?: string | null;
  visibility_scope?: string;
  feature_scope: string;
  provider_config_id: string;
  model_name: string | null;
  enabled: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
};

export type PreviewProviderModelsInput = {
  workspace_id?: string | null;
  provider_type: string;
  api_base_url?: string | null;
  auth_mode: string;
  supports_chat?: boolean;
  supports_embeddings?: boolean;
  supports_reranking?: boolean;
  supports_web_search?: boolean;
  supports_model_listing?: boolean;
  api_key?: string | null;
};

export type ProviderOAuthStatus = {
  available: boolean;
  connected: boolean;
  provider_type: string;
  message: string;
};

export type ProviderTestResult = ProviderHealth & { provider_id: string | null };

export type CreateProviderInput = {
  workspace_id?: string | null;
  provider_type: string;
  display_name: string;
  api_base_url?: string | null;
  auth_mode: string;
  enabled?: boolean;
  is_local?: boolean;
  supports_chat?: boolean;
  supports_embeddings?: boolean;
  supports_reranking?: boolean;
  supports_web_search?: boolean;
  supports_model_listing?: boolean;
  supports_model_install?: boolean;
  default_chat_model?: string | null;
  default_embedding_model?: string | null;
  default_reranker_model?: string | null;
  timeout_seconds?: number;
  priority?: number;
  metadata_json?: Record<string, unknown>;
  api_key?: string | null;
};

export type UpdateProviderInput = Partial<
  Omit<
    CreateProviderInput,
    | "provider_type"
    | "auth_mode"
    | "is_local"
    | "supports_chat"
    | "supports_embeddings"
    | "supports_reranking"
    | "supports_web_search"
    | "supports_model_listing"
    | "supports_model_install"
  >
>;

export type CreateAssignmentInput = {
  workspace_id?: string | null;
  feature_scope: string;
  provider_config_id: string;
  model_name?: string | null;
  enabled?: boolean;
  priority?: number;
};

export type UpdateAssignmentInput = {
  provider_config_id?: string;
  model_name?: string | null;
  enabled?: boolean;
  priority?: number;
};

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    if (
      data &&
      typeof data === "object" &&
      "error" in data &&
      data.error &&
      typeof data.error === "object" &&
      "message" in data.error &&
      typeof data.error.message === "string"
    ) {
      throw new Error(data.error.message);
    }
    if (text) {
      throw new Error(text);
    }
    throw new Error(`HTTP ${response.status}`);
  }
  return data as T;
}

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = (await fetchWithAuth(endpoint, options)) as Response;
  return parseJson<T>(response);
}

export async function listProviders(workspaceId?: string | null): Promise<ProviderConfig[]> {
  const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  const data = await request<{ items: ProviderConfig[] }>(`/providers${query}`);
  return data.items;
}

export function createProvider(payload: CreateProviderInput): Promise<ProviderConfig> {
  return request<ProviderConfig>("/providers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProvider(id: string): Promise<ProviderConfig> {
  return request<ProviderConfig>(`/providers/${id}`);
}

export function updateProvider(id: string, payload: UpdateProviderInput): Promise<ProviderConfig> {
  return request<ProviderConfig>(`/providers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteProvider(id: string): Promise<{ provider_id: string; status: string }> {
  return request<{ provider_id: string; status: string }>(`/providers/${id}`, { method: "DELETE" });
}

export function testProvider(id: string): Promise<ProviderTestResult> {
  return request<ProviderTestResult>(`/providers/${id}/test`, { method: "POST" });
}

export function getProviderHealth(id: string): Promise<ProviderHealth> {
  return request<ProviderHealth>(`/providers/${id}/health`);
}

export async function refreshProviderModels(id: string): Promise<ProviderModel[]> {
  const data = await request<{ items: ProviderModel[] }>(`/providers/${id}/models/refresh`, {
    method: "POST",
  });
  return data.items;
}

export async function listProviderModels(id: string): Promise<ProviderModel[]> {
  const data = await request<{ items: ProviderModel[] }>(`/providers/${id}/models`);
  return data.items;
}

export async function previewProviderModels(
  payload: PreviewProviderModelsInput,
): Promise<ProviderModel[]> {
  const data = await request<{ items: ProviderModel[] }>("/providers/models/preview", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data.items;
}

export function pullProviderModel(
  id: string,
  modelName: string,
): Promise<{ status: string; message: string }> {
  return request<{ status: string; message: string }>(`/providers/${id}/models/pull`, {
    method: "POST",
    body: JSON.stringify({ model_name: modelName }),
  });
}

export async function listAssignments(workspaceId?: string | null): Promise<ProviderAssignment[]> {
  const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  const data = await request<{ items: ProviderAssignment[] }>(`/providers/assignments${query}`);
  return data.items;
}

export function createAssignment(payload: CreateAssignmentInput): Promise<ProviderAssignment> {
  return request<ProviderAssignment>("/providers/assignments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAssignment(
  id: string,
  payload: UpdateAssignmentInput,
): Promise<ProviderAssignment> {
  return request<ProviderAssignment>(`/providers/assignments/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAssignment(id: string): Promise<void> {
  return request<void>(`/providers/assignments/${id}`, {
    method: "DELETE",
  });
}

export async function listSupportedProviderTypes(): Promise<ProviderCatalogEntry[]> {
  const data = await request<{ items: ProviderCatalogEntry[] }>(
    "/providers/catalog/supported-types",
  );
  return data.items;
}

export function startOpenAIOAuth(): Promise<{
  available: boolean;
  authorization_url: string | null;
  message: string;
}> {
  return request<{ available: boolean; authorization_url: string | null; message: string }>(
    "/providers/oauth/openai/start",
    {
      method: "POST",
      body: JSON.stringify({ provider_type: "openai" }),
    },
  );
}

export function getOpenAIOAuthStatus(): Promise<ProviderOAuthStatus> {
  return request<ProviderOAuthStatus>("/providers/oauth/openai/status");
}

export function disconnectProvider(
  id: string,
): Promise<{ provider_id: string; revoked_secret_count: number }> {
  return request<{ provider_id: string; revoked_secret_count: number }>(
    `/providers/${id}/disconnect`,
    { method: "POST" },
  );
}

export function refreshProviderToken(
  id: string,
): Promise<{ provider_id: string; revoked_secret_count: number }> {
  return request<{ provider_id: string; revoked_secret_count: number }>(
    `/providers/${id}/refresh-token`,
    { method: "POST" },
  );
}

export function rotateProviderSecret(
  id: string,
  secretValue: string,
  secretType = "api_key",
): Promise<{ provider_id: string; revoked_secret_count: number }> {
  return request<{ provider_id: string; revoked_secret_count: number }>(
    `/providers/${id}/rotate-secret`,
    {
      method: "POST",
      body: JSON.stringify({ secret_type: secretType, secret_value: secretValue }),
    },
  );
}
