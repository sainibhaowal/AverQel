/**
 * Local-First IndexedDB utility for securing chat history and counts on the user's PC.
 */

const DB_NAME = "averqel_local_secure_db";
const DB_VERSION = 1;

export interface LocalMessage {
  id: string;
  collection_id: string;
  user_id: string;
  user_email: string;
  message: string;
  status: string;
  is_media: boolean;
  media_mime_type: string | null;
  created_at: string;
}

export function initDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined") {
      reject(new Error("IndexedDB is only available in the browser"));
      return;
    }
    const request = window.indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("chats")) {
        const chatStore = db.createObjectStore("chats", { keyPath: "id" });
        chatStore.createIndex("collection_id", "collection_id", { unique: false });
      }
      if (!db.objectStoreNames.contains("unread_counts")) {
        db.createObjectStore("unread_counts", { keyPath: "collection_id" });
      }
    };
  });
}

export async function saveLocalMessage(msg: {
  id: string;
  collection_id: string;
  user_id: string;
  user_email: string;
  message: string;
  status: string;
  is_media: boolean;
  media_mime_type: string | null;
  created_at: string;
}): Promise<void> {
  const db = await initDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("chats", "readwrite");
    const store = tx.objectStore("chats");
    const request = store.put(msg);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

export async function getLocalMessages(collectionId: string): Promise<LocalMessage[]> {
  const db = await initDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("chats", "readonly");
    const store = tx.objectStore("chats");
    const index = store.index("collection_id");
    const request = index.getAll(collectionId);

    request.onsuccess = () => {
      const msgs = request.result || [];
      // Sort chronologically
      msgs.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
      resolve(msgs);
    };
    request.onerror = () => reject(request.error);
  });
}

export async function getUnreadCount(collectionId: string): Promise<number> {
  const db = await initDb();
  return new Promise((resolve) => {
    const tx = db.transaction("unread_counts", "readonly");
    const store = tx.objectStore("unread_counts");
    const request = store.get(collectionId);
    request.onsuccess = () => {
      const res = request.result as { collection_id: string; count: number } | undefined;
      resolve(res ? res.count : 0);
    };
    request.onerror = () => resolve(0);
  });
}

export async function incrementUnreadCount(collectionId: string): Promise<number> {
  const db = await initDb();
  const current = await getUnreadCount(collectionId);
  const next = current + 1;
  return new Promise((resolve, reject) => {
    const tx = db.transaction("unread_counts", "readwrite");
    const store = tx.objectStore("unread_counts");
    const request = store.put({ collection_id: collectionId, count: next });
    request.onsuccess = () => resolve(next);
    request.onerror = () => reject(request.error);
  });
}

export async function resetUnreadCount(collectionId: string): Promise<void> {
  const db = await initDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("unread_counts", "readwrite");
    const store = tx.objectStore("unread_counts");
    const request = store.put({ collection_id: collectionId, count: 0 });
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

/**
 * Local-first client-side auto-purging of expired E2EE messages from IndexedDB.
 */
export async function purgeExpiredMessages(
  collectionId: string,
  expiryDays: number,
): Promise<number> {
  if (expiryDays <= 0) return 0;
  const db = await initDb();
  const cutoff = Date.now() - expiryDays * 24 * 60 * 60 * 1000;

  return new Promise((resolve, reject) => {
    const tx = db.transaction("chats", "readwrite");
    const store = tx.objectStore("chats");
    const index = store.index("collection_id");
    const request = index.openCursor(IDBKeyRange.only(collectionId));
    let deletedCount = 0;

    request.onsuccess = (event) => {
      const cursor = (event.target as IDBRequest<IDBCursorWithValue | null>).result;
      if (cursor) {
        const msg = cursor.value;
        const msgTime = new Date(msg.created_at).getTime();
        if (msgTime < cutoff) {
          cursor.delete();
          deletedCount++;
        }
        cursor.continue();
      } else {
        resolve(deletedCount);
      }
    };
    request.onerror = () => reject(request.error);
  });
}

/**
 * Completely clears all local messages stored in IndexedDB for a collection.
 */
export async function clearLocalMessages(collectionId: string): Promise<void> {
  const db = await initDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("chats", "readwrite");
    const store = tx.objectStore("chats");
    const index = store.index("collection_id");
    const request = index.openCursor(IDBKeyRange.only(collectionId));

    request.onsuccess = (event) => {
      const cursor = (event.target as IDBRequest<IDBCursorWithValue | null>).result;
      if (cursor) {
        cursor.delete();
        cursor.continue();
      } else {
        resolve();
      }
    };
    request.onerror = () => reject(request.error);
  });
}
