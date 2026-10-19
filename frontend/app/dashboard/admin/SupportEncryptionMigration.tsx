"use client";

import { useState } from "react";
import { Loader2, ShieldCheck } from "lucide-react";
import toast from "react-hot-toast";
import { fetchWithAuth } from "@/lib/api";
import {
  encryptSupportAttachment,
  encryptSupportPayload,
  SupportPublicKey,
} from "@/lib/supportEncryption";
import type { SupportEncryptionContext } from "@/app/dashboard/support/SupportEncryptionGate";

type MigrationMode = "support" | "feedback";
type LegacyRecord = { id: string; user_id: string };
type LegacyPage = { items: LegacyRecord[]; total: number };
type LegacyMessage = {
  id: string;
  body: string;
  author_role: string;
  is_internal: boolean;
  encrypted_payload?: string | null;
};

async function responseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

async function requireOk(response: Response): Promise<void> {
  if (response.ok) return;
  const body = (await response.json().catch(() => null)) as { detail?: string } | null;
  throw new Error(body?.detail ?? `Request failed (${response.status})`);
}

async function getUserPublicKey(userId: string): Promise<SupportPublicKey> {
  return responseJson<SupportPublicKey>(
    await fetchWithAuth(`/support/encryption/users/${userId}/public-key`),
  );
}

async function legacyRecords(mode: MigrationMode): Promise<LegacyRecord[]> {
  const records: LegacyRecord[] = [];
  const endpoint =
    mode === "support"
      ? "/support/admin/encryption/legacy"
      : "/app-feedback/admin/encryption/legacy";
  let offset = 0;
  let total = 0;
  do {
    const page = await responseJson<LegacyPage>(
      await fetchWithAuth(`${endpoint}?limit=200&offset=${offset}`),
    );
    records.push(...page.items);
    total = page.total;
    offset += page.items.length;
    if (!page.items.length) break;
  } while (offset < total);
  return records;
}

async function migrateSupportRecord(
  record: LegacyRecord,
  context: SupportEncryptionContext,
  userKey: SupportPublicKey,
): Promise<void> {
  const detail = await responseJson<{
    id: string;
    subject: string;
    description: string;
    encrypted_payload?: string | null;
    messages: LegacyMessage[];
    attachments: Array<{
      id: string;
      filename: string;
      content_type: string;
      download_url: string;
      is_encrypted: boolean;
    }>;
  }>(await fetchWithAuth(`/support/admin/tickets/${record.id}`));
  const recipients = [context.ownPublicKey, userKey];
  const pendingMessages = detail.messages.filter(
    (message) => !message.encrypted_payload && message.author_role !== "system",
  );
  if (!detail.encrypted_payload || pendingMessages.length) {
    const body: {
      encrypted_payload?: string;
      messages: Array<{ id: string; encrypted_payload: string }>;
    } = {
      messages: await Promise.all(
        pendingMessages.map(async (message) => ({
          id: message.id,
          encrypted_payload: await encryptSupportPayload(
            { body: message.body },
            message.is_internal ? [context.ownPublicKey] : recipients,
          ),
        })),
      ),
    };
    if (!detail.encrypted_payload) {
      body.encrypted_payload = await encryptSupportPayload(
        { subject: detail.subject, description: detail.description },
        recipients,
      );
    }
    await responseJson(
      await fetchWithAuth(`/support/admin/tickets/${record.id}/encryption`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    );
  }

  for (const attachment of detail.attachments) {
    if (attachment.is_encrypted) continue;
    const downloadResponse = await fetchWithAuth(attachment.download_url);
    await requireOk(downloadResponse);
    const download = await downloadResponse.blob();
    const sourceFile = new File([download], attachment.filename, {
      type: attachment.content_type,
    });
    const encrypted = await encryptSupportAttachment(sourceFile, recipients);
    const form = new FormData();
    form.append("file", encrypted.encryptedFile, "encrypted.bin");
    form.append("encrypted_metadata", encrypted.encryptedMetadata);
    await requireOk(
      await fetchWithAuth(
        `/support/admin/tickets/${record.id}/attachments/${attachment.id}/encryption`,
        { method: "POST", body: form },
      ),
    );
  }
}

async function migrateFeedbackRecord(
  record: LegacyRecord,
  context: SupportEncryptionContext,
): Promise<void> {
  const detail = await responseJson<{
    id: string;
    subject: string;
    content: string;
    encrypted_payload?: string | null;
    recipient_public_key?: SupportPublicKey | null;
    messages: LegacyMessage[];
  }>(await fetchWithAuth(`/app-feedback/admin/submissions/${record.id}`));
  if (!detail.recipient_public_key) throw new Error("The user has not set up an encryption key yet.");
  const recipients = [context.ownPublicKey, detail.recipient_public_key];
  const pendingMessages = detail.messages.filter(
    (message) => !message.encrypted_payload && message.author_role !== "system",
  );
  if (!detail.encrypted_payload || pendingMessages.length) {
    const body: {
      encrypted_payload?: string;
      messages: Array<{ id: string; encrypted_payload: string }>;
    } = {
      messages: await Promise.all(
        pendingMessages.map(async (message) => ({
          id: message.id,
          encrypted_payload: await encryptSupportPayload(
            { body: message.body },
            message.is_internal ? [context.ownPublicKey] : recipients,
          ),
        })),
      ),
    };
    if (!detail.encrypted_payload) {
      body.encrypted_payload = await encryptSupportPayload(
        { subject: detail.subject, content: detail.content },
        recipients,
      );
    }
    await responseJson(
      await fetchWithAuth(`/app-feedback/admin/submissions/${record.id}/encryption`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    );
  }
}

export default function SupportEncryptionMigration({
  mode,
  context,
}: {
  mode: MigrationMode;
  context: SupportEncryptionContext;
}) {
  const [working, setWorking] = useState(false);
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);

  async function startMigration() {
    if (working) return;
    setWorking(true);
    setProgress(null);
    let migrated = 0;
    const failures: string[] = [];
    try {
      const records = await legacyRecords(mode);
      setProgress({ current: 0, total: records.length });
      for (const [index, record] of records.entries()) {
        try {
          const userKey = await getUserPublicKey(record.user_id);
          if (mode === "support") {
            await migrateSupportRecord(record, context, userKey);
          } else {
            await migrateFeedbackRecord(record, context);
          }
          migrated += 1;
        } catch (error) {
          failures.push(error instanceof Error ? error.message : "Could not encrypt this record.");
        } finally {
          setProgress({ current: index + 1, total: records.length });
        }
      }
      if (failures.length) {
        const uniqueFailures = [...new Set(failures)];
        toast.error(
          `${migrated} encrypted. ${failures.length} need attention: ${uniqueFailures.slice(0, 2).join("; ")}`,
          { duration: 8000 },
        );
      } else {
        toast.success(
          records.length
            ? `Encrypted ${migrated} existing ${mode} records.`
            : `No unencrypted ${mode} records remain.`,
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not start encryption migration.");
    } finally {
      setWorking(false);
    }
  }

  const label = mode === "support" ? "support tickets" : "feedback records";

  return (
    <section className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <ShieldCheck size={19} className="mt-0.5 shrink-0 text-emerald-400" />
          <div>
            <h2 className="font-semibold">Encrypt existing {label}</h2>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-400">
              Legacy text is encrypted in this browser and the database fields are replaced after
              successful validation. Users who have not set up an encryption key are skipped and
              can be migrated after they open Support or Feedback once.
              {mode === "support" &&
                " Encrypted attachments cannot be scanned by the server; only download files you trust."}
            </p>
          </div>
        </div>
        <button
          className="flex items-center gap-2 rounded-lg bg-emerald-400 px-4 py-2 text-xs font-semibold text-slate-950 disabled:opacity-60"
          disabled={working}
          onClick={() => void startMigration()}
          type="button"
        >
          {working && <Loader2 className="animate-spin" size={15} />}
          {working && progress
            ? `Encrypting ${progress.current}/${progress.total}`
            : `Encrypt legacy ${mode}`}
        </button>
      </div>
    </section>
  );
}
