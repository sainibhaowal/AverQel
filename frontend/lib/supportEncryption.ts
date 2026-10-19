export const SUPPORT_ENCRYPTION_ALGORITHM = "RSA-OAEP-3072+AES-256-GCM" as const;

export type SupportPublicKey = { key_id: string; public_key: string };

export type SupportKeyBackup = SupportPublicKey & {
  private_key_ciphertext: string;
  salt: string;
  iv: string;
};

export type SupportKeyRegistration = SupportKeyBackup;

export type SupportCipherEnvelope = {
  v: 1;
  alg: typeof SUPPORT_ENCRYPTION_ALGORITHM;
  iv: string;
  ciphertext: string;
  recipients: Array<{ key_id: string; wrapped_key: string }>;
};

export type SupportAttachmentEnvelope = {
  v: 1;
  alg: typeof SUPPORT_ENCRYPTION_ALGORITHM;
  file_iv: string;
  details_iv: string;
  details_ciphertext: string;
  recipients: Array<{ key_id: string; wrapped_key: string }>;
};

const PBKDF2_ITERATIONS = 600_000;
const RSA_BITS = 3072;

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return window.btoa(binary);
}

// Web Crypto's current TypeScript definitions require an ArrayBuffer-backed
// BufferSource. Copying also prevents passing a view whose backing buffer may
// be a SharedArrayBuffer or contain unrelated bytes outside the view.
function asArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(copy).set(bytes);
  return copy;
}

function base64ToBytes(value: string): Uint8Array {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function keyFingerprint(publicKey: Uint8Array): Promise<string> {
  return bytesToHex(new Uint8Array(await crypto.subtle.digest("SHA-256", asArrayBuffer(publicKey))));
}

async function deriveBackupKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey(
    "raw",
    asArrayBuffer(new TextEncoder().encode(passphrase)),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: asArrayBuffer(salt), iterations: PBKDF2_ITERATIONS, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function createSupportKeyBackup(
  passphrase: string,
): Promise<{ backup: SupportKeyRegistration; privateKey: CryptoKey }> {
  if (passphrase.length < 14) throw new Error("Use a support-encryption passphrase of at least 14 characters.");
  if (typeof crypto === "undefined" || !crypto.subtle) {
    throw new Error("This browser does not support secure support encryption.");
  }

  const pair = (await crypto.subtle.generateKey(
    {
      name: "RSA-OAEP",
      modulusLength: RSA_BITS,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["encrypt", "decrypt"],
  )) as CryptoKeyPair;
  const publicBytes = new Uint8Array(await crypto.subtle.exportKey("spki", pair.publicKey));
  const privateBytes = new Uint8Array(await crypto.subtle.exportKey("pkcs8", pair.privateKey));
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const wrapKey = await deriveBackupKey(passphrase, salt);
  const encryptedPrivateKey = new Uint8Array(
    await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: asArrayBuffer(iv) },
      wrapKey,
      asArrayBuffer(privateBytes),
    ),
  );
  const privateKey = await crypto.subtle.importKey(
    "pkcs8",
    asArrayBuffer(privateBytes),
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["decrypt"],
  );
  privateBytes.fill(0);

  return {
    backup: {
      key_id: await keyFingerprint(publicBytes),
      public_key: bytesToBase64(publicBytes),
      private_key_ciphertext: bytesToBase64(encryptedPrivateKey),
      salt: bytesToBase64(salt),
      iv: bytesToBase64(iv),
    },
    privateKey,
  };
}

export async function unlockSupportPrivateKey(
  backup: SupportKeyBackup,
  passphrase: string,
): Promise<CryptoKey> {
  const wrapKey = await deriveBackupKey(passphrase, base64ToBytes(backup.salt));
  const privateBytes = new Uint8Array(
    await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: asArrayBuffer(base64ToBytes(backup.iv)) },
      wrapKey,
      asArrayBuffer(base64ToBytes(backup.private_key_ciphertext)),
    ),
  );
  try {
    return await crypto.subtle.importKey(
      "pkcs8",
      privateBytes,
      { name: "RSA-OAEP", hash: "SHA-256" },
      false,
      ["decrypt"],
    );
  } finally {
    privateBytes.fill(0);
  }
}

async function importPublicKey(key: SupportPublicKey): Promise<CryptoKey> {
  const publicBytes = base64ToBytes(key.public_key);
  if ((await keyFingerprint(publicBytes)) !== key.key_id) {
    throw new Error("Support encryption public key fingerprint is invalid.");
  }
  return crypto.subtle.importKey(
    "spki",
      asArrayBuffer(publicBytes),
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  );
}

async function createDataKey(recipients: SupportPublicKey[]): Promise<{
  key: CryptoKey;
  wrapped: SupportCipherEnvelope["recipients"];
}> {
  if (!recipients.length) throw new Error("At least one recipient key is required.");
  const unique = new Map(recipients.map((recipient) => [recipient.key_id, recipient]));
  const key = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true,
    ["encrypt", "decrypt"],
  );
  const rawKey = new Uint8Array(await crypto.subtle.exportKey("raw", key));
  const wrapped: SupportCipherEnvelope["recipients"] = [];
  for (const recipient of unique.values()) {
    const publicKey = await importPublicKey(recipient);
    const ciphertext = await crypto.subtle.encrypt(
      { name: "RSA-OAEP" },
      publicKey,
      asArrayBuffer(rawKey),
    );
    wrapped.push({ key_id: recipient.key_id, wrapped_key: bytesToBase64(new Uint8Array(ciphertext)) });
  }
  rawKey.fill(0);
  return { key, wrapped };
}

export async function encryptSupportPayload(
  value: unknown,
  recipients: SupportPublicKey[],
): Promise<string> {
  const { key, wrapped } = await createDataKey(recipients);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: asArrayBuffer(iv) },
    key,
    asArrayBuffer(new TextEncoder().encode(JSON.stringify(value))),
  );
  return JSON.stringify({
    v: 1,
    alg: SUPPORT_ENCRYPTION_ALGORITHM,
    iv: bytesToBase64(iv),
    ciphertext: bytesToBase64(new Uint8Array(ciphertext)),
    recipients: wrapped,
  } satisfies SupportCipherEnvelope);
}

export async function decryptSupportPayload<T>(
  envelopeValue: string,
  privateKey: CryptoKey,
  keyId: string,
): Promise<T> {
  const envelope = JSON.parse(envelopeValue) as SupportCipherEnvelope;
  if (
    envelope.v !== 1 ||
    envelope.alg !== SUPPORT_ENCRYPTION_ALGORITHM ||
    !Array.isArray(envelope.recipients)
  ) {
    throw new Error("Unsupported or malformed encrypted support content.");
  }
  const wrappedKey = envelope.recipients.find((recipient) => recipient.key_id === keyId);
  if (!wrappedKey) throw new Error("This message is not encrypted for this support key.");
  const rawKey = new Uint8Array(
    await crypto.subtle.decrypt(
      { name: "RSA-OAEP" },
      privateKey,
      asArrayBuffer(base64ToBytes(wrappedKey.wrapped_key)),
    ),
  );
  const dataKey = await crypto.subtle.importKey(
    "raw",
    asArrayBuffer(rawKey),
    "AES-GCM",
    false,
    ["decrypt"],
  );
  rawKey.fill(0);
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: asArrayBuffer(base64ToBytes(envelope.iv)) },
    dataKey,
    asArrayBuffer(base64ToBytes(envelope.ciphertext)),
  );
  return JSON.parse(new TextDecoder().decode(plaintext)) as T;
}

export async function encryptSupportAttachment(
  file: File,
  recipients: SupportPublicKey[],
): Promise<{ encryptedFile: Blob; encryptedMetadata: string }> {
  const { key, wrapped } = await createDataKey(recipients);
  const fileIv = crypto.getRandomValues(new Uint8Array(12));
  const detailsIv = crypto.getRandomValues(new Uint8Array(12));
  const [encryptedFile, encryptedDetails] = await Promise.all([
    crypto.subtle.encrypt(
      { name: "AES-GCM", iv: asArrayBuffer(fileIv) },
      key,
      await file.arrayBuffer(),
    ),
    crypto.subtle.encrypt(
      { name: "AES-GCM", iv: asArrayBuffer(detailsIv) },
      key,
      asArrayBuffer(
        new TextEncoder().encode(JSON.stringify({ filename: file.name, content_type: file.type })),
      ),
    ),
  ]);
  const metadata: SupportAttachmentEnvelope = {
    v: 1,
    alg: SUPPORT_ENCRYPTION_ALGORITHM,
    file_iv: bytesToBase64(fileIv),
    details_iv: bytesToBase64(detailsIv),
    details_ciphertext: bytesToBase64(new Uint8Array(encryptedDetails)),
    recipients: wrapped,
  };
  return {
    encryptedFile: new Blob([encryptedFile], { type: "application/octet-stream" }),
    encryptedMetadata: JSON.stringify(metadata),
  };
}

export async function decryptSupportAttachment(
  encryptedFile: ArrayBuffer,
  encryptedMetadata: string,
  privateKey: CryptoKey,
  keyId: string,
): Promise<{ blob: Blob; filename: string; contentType: string }> {
  const metadata = JSON.parse(encryptedMetadata) as SupportAttachmentEnvelope;
  if (metadata.v !== 1 || metadata.alg !== SUPPORT_ENCRYPTION_ALGORITHM) {
    throw new Error("Unsupported encrypted attachment format.");
  }
  const recipient = metadata.recipients.find((item) => item.key_id === keyId);
  if (!recipient) throw new Error("This attachment is not encrypted for this support key.");
  const rawKey = new Uint8Array(
    await crypto.subtle.decrypt(
      { name: "RSA-OAEP" },
      privateKey,
      asArrayBuffer(base64ToBytes(recipient.wrapped_key)),
    ),
  );
  const dataKey = await crypto.subtle.importKey(
    "raw",
    asArrayBuffer(rawKey),
    "AES-GCM",
    false,
    ["decrypt"],
  );
  rawKey.fill(0);
  const [fileBytes, detailsBytes] = await Promise.all([
    crypto.subtle.decrypt(
      { name: "AES-GCM", iv: asArrayBuffer(base64ToBytes(metadata.file_iv)) },
      dataKey,
      encryptedFile,
    ),
    crypto.subtle.decrypt(
      { name: "AES-GCM", iv: asArrayBuffer(base64ToBytes(metadata.details_iv)) },
      dataKey,
      asArrayBuffer(base64ToBytes(metadata.details_ciphertext)),
    ),
  ]);
  const details = JSON.parse(new TextDecoder().decode(detailsBytes)) as {
    filename: string;
    content_type: string;
  };
  return {
    blob: new Blob([fileBytes], { type: details.content_type }),
    filename: details.filename,
    contentType: details.content_type,
  };
}
