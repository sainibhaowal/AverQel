/**
 * Web Crypto API client-side E2E Encryption (E2EE) utilities.
 */

// Helper to convert ArrayBuffer to Base64
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

// Helper to convert Base64 to ArrayBuffer
function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

/**
 * Derives a symmetric AES-GCM key from collectionId and connectionCode client-side.
 */
export async function deriveKey(
  collectionId: string,
  connectionCode: string
): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  const passwordBuffer = encoder.encode(connectionCode);
  const salt = encoder.encode(collectionId);

  // Import raw password key
  const keyMaterial = await window.crypto.subtle.importKey(
    "raw",
    passwordBuffer,
    { name: "PBKDF2" },
    false,
    ["deriveKey"]
  );

  // Derive AES-GCM 256 key
  return await window.crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: salt,
      iterations: 100000,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}

/**
 * Encrypts plaintext string using AES-GCM.
 * Returns a JSON envelope containing base64 stringified ciphertext and IV.
 */
export async function encryptMessage(
  text: string,
  key: CryptoKey
): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const iv = window.crypto.getRandomValues(new Uint8Array(12));

  const ciphertextBuffer = await window.crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv },
    key,
    data
  );

  const envelope = {
    ciphertext: arrayBufferToBase64(ciphertextBuffer),
    iv: arrayBufferToBase64(iv.buffer),
  };

  return JSON.stringify(envelope);
}

/**
 * Decrypts a JSON string envelope containing AES-GCM ciphertext and IV.
 */
export async function decryptMessage(
  envelopeStr: string,
  key: CryptoKey
): Promise<string> {
  try {
    const envelope = JSON.parse(envelopeStr) as { ciphertext: string; iv: string };
    if (!envelope.ciphertext || !envelope.iv) {
      return envelopeStr; // fallback to raw string if not an E2EE envelope
    }

    const ciphertext = base64ToArrayBuffer(envelope.ciphertext);
    const iv = new Uint8Array(base64ToArrayBuffer(envelope.iv));

    const decryptedBuffer = await window.crypto.subtle.decrypt(
      { name: "AES-GCM", iv: iv },
      key,
      ciphertext
    );

    const decoder = new TextDecoder();
    return decoder.decode(decryptedBuffer);
  } catch (error) {
    console.error("E2EE decryption failure:", error);
    return "[Decryption Error: Private Key Mismatch or Data Corrupted]";
  }
}

/**
 * Encrypts a binary file using AES-GCM.
 */
export async function encryptFile(
  file: File,
  key: CryptoKey
): Promise<{ encryptedBlob: Blob; iv: string }> {
  const arrayBuffer = await file.arrayBuffer();
  const iv = window.crypto.getRandomValues(new Uint8Array(12));

  const encryptedBuffer = await window.crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv },
    key,
    arrayBuffer
  );

  return {
    encryptedBlob: new Blob([encryptedBuffer], { type: "application/octet-stream" }),
    iv: arrayBufferToBase64(iv.buffer),
  };
}

/**
 * Decrypts binary data to a Blob.
 */
export async function decryptFile(
  encryptedData: ArrayBuffer,
  ivBase64: string,
  mimeType: string,
  key: CryptoKey
): Promise<Blob> {
  const iv = new Uint8Array(base64ToArrayBuffer(ivBase64));

  const decryptedBuffer = await window.crypto.subtle.decrypt(
    { name: "AES-GCM", iv: iv },
    key,
    encryptedData
  );

  return new Blob([decryptedBuffer], { type: mimeType });
}

/**
 * Generates a mathematical Safety Number fingerprint (Signal/WhatsApp style)
 * from the collection identity for client verification.
 * Uses SHA-256 over the key derivation inputs (collectionId + connectionCode)
 * so the fingerprint is deterministic and doesn't require an extractable key.
 */
export async function getSafetyNumber(
  collectionId: string,
  connectionCode: string
): Promise<string> {
  const encoder = new TextEncoder();
  const combined = encoder.encode(`${collectionId}:${connectionCode}`);
  const hashBuffer = await window.crypto.subtle.digest("SHA-256", combined);
  const hashArray = Array.from(new Uint8Array(hashBuffer));

  const segments: string[] = [];
  for (let i = 0; i < hashArray.length; i += 2) {
    if (i + 1 < hashArray.length) {
      const val = (hashArray[i] << 8) + hashArray[i + 1];
      segments.push(val.toString().padStart(5, "0"));
    }
  }
  return segments.slice(0, 8).join("-");
}

/**
 * Encrypts backup JSON payload using password-based PBKDF2 key derivation & AES-GCM.
 */
export async function encryptBackup(
  jsonData: string,
  password: string
): Promise<{ ciphertext: string; salt: string; iv: string }> {
  const encoder = new TextEncoder();
  const passwordBuffer = encoder.encode(password);
  const salt = window.crypto.getRandomValues(new Uint8Array(16));
  const iv = window.crypto.getRandomValues(new Uint8Array(12));

  const keyMaterial = await window.crypto.subtle.importKey(
    "raw",
    passwordBuffer,
    { name: "PBKDF2" },
    false,
    ["deriveKey"]
  );

  const key = await window.crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: salt,
      iterations: 100000,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt"]
  );

  const encrypted = await window.crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv },
    key,
    encoder.encode(jsonData)
  );

  return {
    ciphertext: arrayBufferToBase64(encrypted),
    salt: arrayBufferToBase64(salt.buffer),
    iv: arrayBufferToBase64(iv.buffer),
  };
}

/**
 * Decrypts backup JSON payload using password-based derived key.
 */
export async function decryptBackup(
  ciphertext: string,
  salt: string,
  iv: string,
  password: string
): Promise<string> {
  const passwordBuffer = new TextEncoder().encode(password);
  const saltArray = new Uint8Array(base64ToArrayBuffer(salt));
  const ivArray = new Uint8Array(base64ToArrayBuffer(iv));
  const ciphertextArray = base64ToArrayBuffer(ciphertext);

  const keyMaterial = await window.crypto.subtle.importKey(
    "raw",
    passwordBuffer,
    { name: "PBKDF2" },
    false,
    ["deriveKey"]
  );

  const key = await window.crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: saltArray,
      iterations: 100000,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"]
  );

  const decrypted = await window.crypto.subtle.decrypt(
    { name: "AES-GCM", iv: ivArray },
    key,
    ciphertextArray
  );

  return new TextDecoder().decode(decrypted);
}

