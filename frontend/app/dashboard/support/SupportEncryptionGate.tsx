"use client";

import { FormEvent, useEffect, useState } from "react";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import {
  createSupportKeyBackup,
  SupportKeyBackup,
  SupportPublicKey,
  unlockSupportPrivateKey,
} from "@/lib/supportEncryption";

type Scope = "user" | "admin";
type GateState = "loading" | "setup" | "unlock" | "ready" | "error";

export type SupportEncryptionContext = {
  privateKey: CryptoKey;
  keyId: string;
  ownPublicKey: SupportPublicKey;
  adminPublicKey: SupportPublicKey;
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `Support encryption setup failed (${response.status}).`);
  }
  return (await response.json()) as T;
}

export function useSupportEncryption(scope: Scope) {
  const [state, setState] = useState<GateState>("loading");
  const [backup, setBackup] = useState<SupportKeyBackup | null>(null);
  const [adminPublicKey, setAdminPublicKey] = useState<SupportPublicKey | null>(null);
  const [context, setContext] = useState<SupportEncryptionContext | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  async function initialize() {
    setState("loading");
    setError(null);
    setBackup(null);
    try {
      let adminKey: SupportPublicKey | null = null;
      if (scope === "user") {
        adminKey = await readJson<SupportPublicKey>(
          await fetchWithAuth("/support/encryption/admin-public-key"),
        );
        setAdminPublicKey(adminKey);
      }

      const keyUrl =
        scope === "admin"
          ? "/support/encryption/admin-private-key"
          : "/support/encryption/me";
      const response = await fetchWithAuth(keyUrl);
      if (response.status === 404 && scope === "admin") {
        setState("setup");
        return;
      }
      if (response.status === 404 && scope === "user") {
        setState("setup");
        return;
      }
      const keyBackup = await readJson<SupportKeyBackup>(response);
      if (scope === "admin") {
        adminKey = { key_id: keyBackup.key_id, public_key: keyBackup.public_key };
        setAdminPublicKey(adminKey);
      }
      setBackup(keyBackup);
      setState("unlock");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not initialize support encryption. No unencrypted message was sent.",
      );
      setState("error");
    }
  }

  useEffect(() => {
    queueMicrotask(() => void initialize());
    // This hook is scoped to one support screen and initializes once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope]);

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (working) return;
    if (state === "setup" && passphrase !== confirmation) {
      setError("The passphrases do not match.");
      return;
    }
    setWorking(true);
    setError(null);
    try {
      let activeBackup = backup;
      let privateKey: CryptoKey;
      if (state === "setup") {
        const generated = await createSupportKeyBackup(passphrase);
        const endpoint =
          scope === "admin"
            ? "/support/encryption/admin-private-key"
            : "/support/encryption/me";
        const saved = await readJson<SupportPublicKey>(
          await fetchWithAuth(endpoint, {
            method: "PUT",
            body: JSON.stringify(generated.backup),
          }),
        );
        activeBackup = generated.backup;
        privateKey = generated.privateKey;
        if (scope === "admin") setAdminPublicKey(saved);
      } else {
        if (!activeBackup) throw new Error("The encrypted key backup could not be loaded.");
        privateKey = await unlockSupportPrivateKey(activeBackup, passphrase);
      }

      const adminKey =
        scope === "admin"
          ? { key_id: activeBackup!.key_id, public_key: activeBackup!.public_key }
          : adminPublicKey;
      if (!activeBackup || !adminKey) throw new Error("Required support encryption keys are missing.");
      setContext({
        privateKey,
        keyId: activeBackup.key_id,
        ownPublicKey: { key_id: activeBackup.key_id, public_key: activeBackup.public_key },
        adminPublicKey: adminKey,
      });
      setPassphrase("");
      setConfirmation("");
      setState("ready");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The passphrase was incorrect or the encrypted key backup is damaged.",
      );
    } finally {
      setWorking(false);
    }
  }

  const panel = state === "ready" ? null : (
    <section className="mx-auto my-10 w-full max-w-xl rounded-2xl border border-emerald-500/20 bg-[#111916] p-6 text-white shadow-xl">
      {state === "loading" ? (
        <div className="flex items-center gap-3 text-sm text-slate-300" role="status">
          <Loader2 className="animate-spin text-emerald-400" size={20} />
          Checking your encrypted support keys…
        </div>
      ) : state === "error" ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <ShieldCheck className="text-rose-400" size={22} />
            <h2 className="text-lg font-semibold">Support encryption is unavailable</h2>
          </div>
          <p className="text-sm text-slate-300">{error}</p>
          <button
            className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950"
            onClick={() => void initialize()}
            type="button"
          >
            Try again
          </button>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={(event) => void unlock(event)}>
          <div className="flex items-center gap-3">
            <KeyRound className="text-emerald-400" size={22} />
            <h2 className="text-lg font-semibold">
              {state === "setup" ? "Set up encrypted support" : "Unlock encrypted support"}
            </h2>
          </div>
          <p className="text-sm leading-6 text-slate-300">
            {state === "setup"
              ? "Create a long passphrase for your support key. The server stores only a copy encrypted with this passphrase. Save the passphrase: AverQel cannot recover it."
              : "Enter your support-encryption passphrase. It unlocks your private key in this browser only; the server never receives the passphrase."}
          </p>
          <label className="block space-y-1 text-sm">
            <span>{state === "setup" ? "New passphrase (14+ characters)" : "Passphrase"}</span>
            <input
              autoComplete="off"
              className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white"
              onChange={(event) => setPassphrase(event.target.value)}
              required
              type="password"
              value={passphrase}
            />
          </label>
          {state === "setup" && (
            <label className="block space-y-1 text-sm">
              <span>Confirm passphrase</span>
              <input
                autoComplete="off"
                className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white"
                onChange={(event) => setConfirmation(event.target.value)}
                required
                type="password"
                value={confirmation}
              />
            </label>
          )}
          {error && <p className="text-sm text-rose-300" role="alert">{error}</p>}
          <button
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-400 px-4 py-3 font-semibold text-slate-950 disabled:opacity-60"
            disabled={working || !passphrase}
            type="submit"
          >
            {working && <Loader2 className="animate-spin" size={16} />}
            {state === "setup" ? "Create encrypted key" : "Unlock support messages"}
          </button>
          <p className="text-xs leading-5 text-slate-400">
            Message text is encrypted before upload. Account IDs, status, category, and timestamps remain available to the service for routing and support operations.
          </p>
        </form>
      )}
    </section>
  );

  return { ready: state === "ready", context, panel };
}
