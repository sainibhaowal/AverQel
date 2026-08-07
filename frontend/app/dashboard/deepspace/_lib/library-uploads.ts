"use client";

const DB_NAME = "averqel-deepspace-library";
const DB_VERSION = 1;
const STORE_NAME = "upload-files";

export type PersistedUploadFile = {
  uploadId: string;
  conversationId: string;
  file: File;
};

function openUploadDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("Browser storage is unavailable."));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME))
        db.createObjectStore(STORE_NAME, { keyPath: "uploadId" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error("Unable to open browser upload storage."));
  });
}

export async function savePersistedUpload(value: PersistedUploadFile): Promise<void> {
  const db = await openUploadDb();
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(value);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Unable to save upload."));
  });
  db.close();
}

export async function getPersistedUpload(uploadId: string): Promise<PersistedUploadFile | null> {
  const db = await openUploadDb();
  const value = await new Promise<PersistedUploadFile | null>((resolve, reject) => {
    const request = db.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(uploadId);
    request.onsuccess = () => resolve((request.result as PersistedUploadFile | undefined) ?? null);
    request.onerror = () => reject(request.error ?? new Error("Unable to read upload."));
  });
  db.close();
  return value;
}

export async function deletePersistedUpload(uploadId: string): Promise<void> {
  try {
    const db = await openUploadDb();
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(uploadId);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () =>
        reject(transaction.error ?? new Error("Unable to delete upload."));
    });
    db.close();
  } catch {
    // A missing/blocked browser store must not prevent normal Library use.
  }
}
