import { webcrypto } from "node:crypto";
import { afterAll, describe, expect, it, vi } from "vitest";
import {
  createSupportKeyBackup,
  decryptSupportAttachment,
  decryptSupportPayload,
  encryptSupportAttachment,
  encryptSupportPayload,
  unlockSupportPrivateKey,
} from "@/lib/supportEncryption";

const originalCrypto = globalThis.crypto;
vi.stubGlobal("crypto", webcrypto);

function blobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

function blobArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

afterAll(() => {
  vi.stubGlobal("crypto", originalCrypto);
});

describe("support end-to-end encryption", () => {
  it("encrypts and decrypts a message and an attachment only with the matching key", async () => {
    const { backup, privateKey } = await createSupportKeyBackup(
      "correct horse battery staple!",
    );
    const admin = await createSupportKeyBackup("admin's separate recovery passphrase");
    const publicKey = { key_id: backup.key_id, public_key: backup.public_key };
    const adminPublicKey = {
      key_id: admin.backup.key_id,
      public_key: admin.backup.public_key,
    };
    const recipients = [publicKey, adminPublicKey];
    const message = { subject: "Private subject", body: "Private support details" };
    const encrypted = await encryptSupportPayload(message, recipients);

    expect(encrypted).not.toContain(message.subject);
    expect(encrypted).not.toContain(message.body);
    await expect(decryptSupportPayload(encrypted, privateKey, backup.key_id)).resolves.toEqual(
      message,
    );
    await expect(
      decryptSupportPayload(encrypted, admin.privateKey, admin.backup.key_id),
    ).resolves.toEqual(message);
    await expect(decryptSupportPayload(encrypted, privateKey, "c".repeat(64))).rejects.toThrow(
      "not encrypted for this support key",
    );

    const file = new File(["private attachment bytes"], "diagnostic.txt", {
      type: "text/plain",
    });
    Object.defineProperty(file, "arrayBuffer", {
      value: async () => new TextEncoder().encode("private attachment bytes").buffer,
    });
    const encryptedFile = await encryptSupportAttachment(file, recipients);
    expect(await blobText(encryptedFile.encryptedFile)).not.toContain("private attachment bytes");
    const decryptedFile = await decryptSupportAttachment(
      await blobArrayBuffer(encryptedFile.encryptedFile),
      encryptedFile.encryptedMetadata,
      admin.privateKey,
      admin.backup.key_id,
    );
    expect(decryptedFile.filename).toBe("diagnostic.txt");
    expect(decryptedFile.contentType).toBe("text/plain");
    await expect(blobText(decryptedFile.blob)).resolves.toBe("private attachment bytes");
  });

  it("protects the private key backup with the passphrase", async () => {
    const { backup, privateKey } = await createSupportKeyBackup(
      "a longer support-only passphrase",
    );
    await expect(
      unlockSupportPrivateKey(backup, "a different passphrase entirely"),
    ).rejects.toThrow();
    await expect(unlockSupportPrivateKey(backup, "a longer support-only passphrase"))
      .resolves.toBeDefined();
    expect(privateKey.type).toBe("private");
    expect(privateKey.extractable).toBe(false);
  });
});
