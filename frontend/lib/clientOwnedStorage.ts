"use client";

import { getApiBaseUrl } from "@/lib/api";

/**
 * Client-owned data plane.
 *
 * The browser/native client owns the encrypted records. The VPS can ask the
 * connected client to read/write them over the authenticated storage channel,
 * but the server does not receive the encryption key. Native builds should
 * replace the IndexedDB key record with the platform keychain/keystore.
 */

const DB_NAME = "averqel_client_owned_storage";
const DB_VERSION = 1;
const RECORDS = "records";
const META = "meta";

type StoredRecord = {
  id: string;
  namespace: string;
  recordKey: string;
  iv: ArrayBuffer;
  ciphertext: ArrayBuffer;
  updatedAt: string;
};

type RpcRequest = {
  event: "rpc_request";
  id: string;
  method: string;
  params?: Record<string, unknown>;
};

function recordId(namespace: string, key: string): string {
  return `${namespace}:${key}`;
}

function publicConversation(value: Record<string, unknown>): Record<string, unknown> {
  return {
    id: value.id,
    title: value.title,
    kind: value.kind,
    content_html: value.content_html ?? null,
    created_at: value.created_at,
    updated_at: value.updated_at,
  };
}

function publicMessage(value: Record<string, unknown>): Record<string, unknown> {
  return {
    id: value.id,
    role: value.role,
    content: value.content,
    metadata_json: value.metadata_json ?? {},
    created_at: value.created_at,
    active_version_id: value.active_version_id ?? null,
    active_version_index: value.active_version_index ?? 1,
    version_count: value.version_count ?? 1,
    versions: value.versions ?? [],
  };
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !window.indexedDB) {
      reject(new Error("Client-owned storage requires IndexedDB."));
      return;
    }
    const request = window.indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = () => reject(request.error ?? new Error("Unable to open local storage."));
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(RECORDS)) {
        const store = db.createObjectStore(RECORDS, { keyPath: "id" });
        store.createIndex("namespace", "namespace", { unique: false });
        store.createIndex("recordKey", "recordKey", { unique: false });
      }
      if (!db.objectStoreNames.contains(META)) {
        db.createObjectStore(META, { keyPath: "id" });
      }
    };
  });
}

async function encryptionKey(): Promise<CryptoKey> {
  const db = await openDb();
  const existing = await new Promise<CryptoKey | undefined>((resolve, reject) => {
    const request = db.transaction(META, "readonly").objectStore(META).get("encryption-key");
    request.onsuccess = () => resolve(request.result?.value as CryptoKey | undefined);
    request.onerror = () => reject(request.error);
  });
  if (existing) return existing;

  const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, [
    "encrypt",
    "decrypt",
  ]);
  await new Promise<void>((resolve, reject) => {
    const request = db
      .transaction(META, "readwrite")
      .objectStore(META)
      .put({ id: "encryption-key", value: key });
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
  return key;
}

async function encrypt(value: unknown): Promise<{ iv: ArrayBuffer; ciphertext: ArrayBuffer }> {
  const key = await encryptionKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(JSON.stringify(value));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
  return { iv: iv.buffer, ciphertext };
}

async function decrypt(record: StoredRecord): Promise<unknown> {
  const key = await encryptionKey();
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: new Uint8Array(record.iv) },
    key,
    record.ciphertext,
  );
  return JSON.parse(new TextDecoder().decode(plaintext)) as unknown;
}

export async function putClientOwnedRecord(
  namespace: string,
  key: string,
  value: unknown,
): Promise<void> {
  const db = await openDb();
  const encrypted = await encrypt(value);
  await new Promise<void>((resolve, reject) => {
    const request = db
      .transaction(RECORDS, "readwrite")
      .objectStore(RECORDS)
      .put({
        id: recordId(namespace, key),
        namespace,
        recordKey: key,
        ...encrypted,
        updatedAt: new Date().toISOString(),
      } satisfies StoredRecord);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

export async function getClientOwnedRecord<T>(namespace: string, key: string): Promise<T | null> {
  const db = await openDb();
  const record = await new Promise<StoredRecord | undefined>((resolve, reject) => {
    const request = db
      .transaction(RECORDS, "readonly")
      .objectStore(RECORDS)
      .get(recordId(namespace, key));
    request.onsuccess = () => resolve(request.result as StoredRecord | undefined);
    request.onerror = () => reject(request.error);
  });
  return record ? ((await decrypt(record)) as T) : null;
}

export async function listClientOwnedRecords<T>(namespace: string): Promise<T[]> {
  const db = await openDb();
  const records = await new Promise<StoredRecord[]>((resolve, reject) => {
    const request = db
      .transaction(RECORDS, "readonly")
      .objectStore(RECORDS)
      .index("namespace")
      .getAll(namespace);
    request.onsuccess = () => resolve((request.result ?? []) as StoredRecord[]);
    request.onerror = () => reject(request.error);
  });
  return Promise.all(records.map(async (record) => (await decrypt(record)) as T));
}

export async function deleteClientOwnedRecord(namespace: string, key: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const request = db
      .transaction(RECORDS, "readwrite")
      .objectStore(RECORDS)
      .delete(recordId(namespace, key));
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

// Reserved for the desktop client-storage transport. The browser build currently uses REST only.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function websocketUrl(): string | null {
  if (typeof window === "undefined" || typeof WebSocket === "undefined") return null;
  try {
    const url = new URL(
      `${getApiBaseUrl().replace(/\/+$/, "")}/deepspace/client-storage/ws`,
      window.location.origin,
    );
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const token = window.localStorage.getItem("averqel_token");
    const tenantId = window.localStorage.getItem("averqel_tenant_id");
    if (!token) return null;
    url.searchParams.set("token", token);
    if (tenantId) url.searchParams.set("tenant_id", tenantId);
    return url.toString();
  } catch {
    return null;
  }
}

// Reserved for the desktop client-storage transport. Keeping this adapter local prevents browser callers
// from bypassing the authenticated API boundary.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
async function handleRpc(request: RpcRequest): Promise<unknown> {
  const params = request.params ?? {};
  const namespace = String(params.namespace ?? "");
  const key = String(params.key ?? "");

  switch (request.method) {
    case "client.storage.put":
      await putClientOwnedRecord(namespace, key, params.value);
      return { stored: true };
    case "client.storage.get":
      return getClientOwnedRecord(namespace, key);
    case "client.storage.list":
      return listClientOwnedRecords(namespace);
    case "client.storage.delete":
      if (!namespace || !key) throw new Error("namespace and key are required");
      await deleteClientOwnedRecord(namespace, key);
      return { deleted: true };
    case "db.chats.list_conversations": {
      const userId = String(params.user_id ?? "");
      const limit = Number(params.limit ?? 50);
      const offset = Number(params.offset ?? 0);
      const items = (await listClientOwnedRecords<Record<string, unknown>>("chat.conversations"))
        .filter((item) => !userId || String(item.user_id ?? "") === userId)
        .sort((left, right) =>
          String(right.updated_at ?? "").localeCompare(String(left.updated_at ?? "")),
        )
        .slice(offset, offset + limit);
      return items.map(publicConversation);
    }
    case "db.chats.create_conversation": {
      const now = new Date().toISOString();
      const conversation = {
        id: crypto.randomUUID(),
        user_id: String(params.user_id ?? ""),
        title: String(params.title ?? "New Conversation"),
        kind: String(params.kind ?? "query"),
        content_html: typeof params.content_html === "string" ? params.content_html : null,
        created_at: now,
        updated_at: now,
      };
      await putClientOwnedRecord("chat.conversations", conversation.id, conversation);
      return publicConversation(conversation);
    }
    case "db.chats.get_chat_history": {
      const conversationId = String(params.conversation_id ?? "");
      const messages = await listClientOwnedRecords<Record<string, unknown>>("chat.messages");
      return messages
        .filter((item) => String(item.conversation_id ?? "") === conversationId)
        .sort((left, right) =>
          String(left.created_at ?? "").localeCompare(String(right.created_at ?? "")),
        )
        .map(publicMessage);
    }
    case "db.chats.get_message": {
      const message = await getClientOwnedRecord<Record<string, unknown>>(
        "chat.messages",
        String(params.message_id ?? key),
      );
      return message ? publicMessage(message) : null;
    }
    case "db.chats.add_message": {
      const now = new Date().toISOString();
      const messageId = String(params.message_id ?? crypto.randomUUID());
      const content = String(params.content ?? "");
      const message = {
        id: messageId,
        conversation_id: String(params.conversation_id ?? ""),
        role: String(params.role ?? "user"),
        content,
        metadata_json: (params.metadata_json as Record<string, unknown> | undefined) ?? {},
        created_at: now,
        active_version_id: messageId,
        active_version_index: 1,
        version_count: 1,
        versions: [
          {
            id: messageId,
            version_index: 1,
            content,
            metadata_json: (params.metadata_json as Record<string, unknown> | undefined) ?? {},
            source_type: "initial",
            created_at: now,
          },
        ],
      };
      await putClientOwnedRecord("chat.messages", messageId, message);
      return publicMessage(message);
    }
    case "db.memories.store_fact": {
      const memory = {
        id: crypto.randomUUID(),
        key: String(params.key ?? ""),
        value: String(params.value ?? ""),
        scope: String(params.scope ?? "user"),
        tags: Array.isArray(params.tags) ? params.tags : [],
        importance_score: Number(params.importance_score ?? 0.5),
        access_count: 0,
        metadata: (params.metadata_json as Record<string, unknown> | undefined) ?? {},
        embedding_provider: null,
        embedding_model: null,
        embedding_version: null,
        pgvector_ready: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      await putClientOwnedRecord("memory.facts", memory.id, memory);
      return memory.id;
    }
    case "db.memories.search_memories": {
      const query = String(params.query ?? "").toLowerCase();
      const limit = Number(params.limit ?? 5);
      const memories = await listClientOwnedRecords<Record<string, unknown>>("memory.facts");
      return memories
        .map((memory) => ({
          ...memory,
          score: `${String(memory.key ?? "")} ${String(memory.value ?? "")}`
            .toLowerCase()
            .includes(query)
            ? 1
            : 0,
        }))
        .filter((memory) => Number(memory.score) > 0)
        .sort((left, right) => Number(right.score) - Number(left.score))
        .slice(0, limit);
    }
    default:
      throw new Error(`Unsupported client storage method: ${request.method}`);
  }
}

export interface ClientOwnedStorageChannel {
  socket: WebSocket;
  close: () => void;
}

export function connectClientOwnedStorageChannel(): ClientOwnedStorageChannel | null {
  return null;
}
