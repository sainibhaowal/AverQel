"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useAuth } from "@/app/context/AuthContext";
import { fetchWithAuth } from "@/lib/api";
import {
  createSupportKeyBackup,
  unlockSupportPrivateKey,
} from "@/lib/supportEncryption";
import type { SupportKeyBackup, SupportPublicKey } from "@/lib/supportEncryption";
import {
  getSupportEncryptionSessionKey,
  getUnlockedSupportEncryptionSession,
  isSupportEncryptionLockEvent,
  rememberUnlockedSupportEncryptionSession,
  clearSupportEncryptionSession,
  SUPPORT_ENCRYPTION_IDLE_TIMEOUT_MS,
  SUPPORT_ENCRYPTION_LOCK_EVENT,
} from "@/lib/supportEncryptionSession";
import type { SupportEncryptionContext } from "@/lib/supportEncryptionSession";

type Scope = "user" | "admin";
type GateState = "loading" | "setup" | "unlock" | "ready" | "error";

export type { SupportEncryptionContext } from "@/lib/supportEncryptionSession";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `Support encryption setup failed (${response.status}).`);
  }
  return (await response.json()) as T;
}

export function useSupportEncryption(scope: Scope) {
  const { user, loading: authLoading } = useAuth();
  const sessionKey = getSupportEncryptionSessionKey(
    scope,
    user?.id ?? null,
    user?.tenant_id ?? null,
  );
  const sessionKeyRef = useRef(sessionKey);
  const previousSessionKeyRef = useRef<string | null>(null);
  useLayoutEffect(() => {
    const previousSessionKey = previousSessionKeyRef.current;
    if (previousSessionKey && previousSessionKey !== sessionKey) {
      clearSupportEncryptionSession(previousSessionKey);
    }
    previousSessionKeyRef.current = sessionKey;
    sessionKeyRef.current = sessionKey;
  }, [sessionKey]);

  const [gateState, setGateState] = useState<{ sessionKey: string | null; value: GateState }>({
    sessionKey: null,
    value: "loading",
  });
  const [backup, setBackup] = useState<SupportKeyBackup | null>(null);
  const [adminPublicKey, setAdminPublicKey] = useState<SupportPublicKey | null>(null);
  const [contextState, setContextState] = useState<{
    sessionKey: string;
    context: SupportEncryptionContext;
  } | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const initializationVersionRef = useRef(0);

  const state = gateState.sessionKey === sessionKey ? gateState.value : "loading";
  const context = contextState?.sessionKey === sessionKey ? contextState.context : null;
  const setState = useCallback(
    (value: GateState) => setGateState({ sessionKey, value }),
    [sessionKey],
  );
  const setContext = useCallback(
    (value: SupportEncryptionContext | null) => {
      setContextState(value && sessionKey ? { sessionKey, context: value } : null);
    },
    [sessionKey],
  );

  const initialize = useCallback(async () => {
    const version = ++initializationVersionRef.current;
    const isCurrent = () =>
      initializationVersionRef.current === version && sessionKeyRef.current === sessionKey;

    if (authLoading) return;
    setState("loading");
    setError(null);
    setBackup(null);
    setAdminPublicKey(null);
    setPassphrase("");
    setConfirmation("");
    setWorking(false);

    if (!sessionKey) {
      setError("Sign in to unlock encrypted support.");
      setState("error");
      return;
    }

    const cachedContext = getUnlockedSupportEncryptionSession(sessionKey);
    if (!isCurrent()) return;
    if (cachedContext) {
      setContext(cachedContext);
      setAdminPublicKey(cachedContext.adminPublicKey);
      setState("ready");
      return;
    }

    try {
      let adminKey: SupportPublicKey | null = null;
      if (scope === "user") {
        adminKey = await readJson<SupportPublicKey>(
          await fetchWithAuth("/support/encryption/admin-public-key"),
        );
        if (!isCurrent()) return;
        setAdminPublicKey(adminKey);
      }

      const keyUrl =
        scope === "admin"
          ? "/support/encryption/admin-private-key"
          : "/support/encryption/me";
      const response = await fetchWithAuth(keyUrl);
      if (!isCurrent()) return;
      if (response.status === 404 && scope === "admin") {
        setState("setup");
        return;
      }
      if (response.status === 404 && scope === "user") {
        setState("setup");
        return;
      }
      const keyBackup = await readJson<SupportKeyBackup>(response);
      if (!isCurrent()) return;
      if (scope === "admin") {
        adminKey = { key_id: keyBackup.key_id, public_key: keyBackup.public_key };
        setAdminPublicKey(adminKey);
      }
      setBackup(keyBackup);
      setState("unlock");
    } catch (cause) {
      if (!isCurrent()) return;
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not initialize support encryption. No unencrypted message was sent.",
      );
      setState("error");
    }
  }, [authLoading, scope, sessionKey, setContext, setState]);

  useEffect(() => {
    if (!sessionKey) return;

    const handleSessionLock = (event: Event) => {
      if (!isSupportEncryptionLockEvent(event) || event.detail.sessionKey !== sessionKey) return;
      setContext(null);
      setBackup(null);
      setAdminPublicKey(null);
      setPassphrase("");
      setConfirmation("");
      setWorking(false);

      if (event.detail.reason === "idle") {
        setState("loading");
        setError(null);
        void initialize();
      } else {
        setError("Your sign-in session ended. Sign in again to unlock encrypted support.");
        setState("error");
      }
    };

    window.addEventListener(SUPPORT_ENCRYPTION_LOCK_EVENT, handleSessionLock);
    return () => window.removeEventListener(SUPPORT_ENCRYPTION_LOCK_EVENT, handleSessionLock);
  }, [initialize, sessionKey, setContext, setState]);

  useEffect(() => {
    if (authLoading) return;
    queueMicrotask(() => void initialize());
    return () => {
      initializationVersionRef.current += 1;
    };
  }, [authLoading, initialize]);

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (working) return;
    const operationSessionKey = sessionKey;
    if (!operationSessionKey) return;
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
        if (sessionKeyRef.current !== operationSessionKey) return;
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
        if (sessionKeyRef.current !== operationSessionKey) return;
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
      const unlockedContext: SupportEncryptionContext = {
        privateKey,
        keyId: activeBackup.key_id,
        ownPublicKey: { key_id: activeBackup.key_id, public_key: activeBackup.public_key },
        adminPublicKey: adminKey,
      };
      if (sessionKeyRef.current !== operationSessionKey) return;
      rememberUnlockedSupportEncryptionSession(operationSessionKey, unlockedContext);
      setContext(unlockedContext);
      setPassphrase("");
      setConfirmation("");
      setState("ready");
    } catch (cause) {
      if (sessionKeyRef.current !== operationSessionKey) return;
      setError(
        cause instanceof Error
          ? cause.message
          : "The passphrase was incorrect or the encrypted key backup is damaged.",
      );
    } finally {
      if (sessionKeyRef.current === operationSessionKey) setWorking(false);
    }
  }

  const panel =
    state === "ready" ? null : (
      <section className="theme-panel-strong text-foreground mx-auto my-10 w-full max-w-xl rounded-2xl p-6 shadow-xl">
        {state === "loading" ? (
          <div className="text-muted-foreground flex items-center gap-3 text-sm" role="status">
            <Loader2 className="text-primary animate-spin" size={20} />
            Checking your encrypted support keys…
          </div>
        ) : state === "error" ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <ShieldCheck className="text-rose-700 dark:text-rose-300" size={22} />
              <h2 className="text-lg font-semibold text-rose-800 dark:text-rose-200">
                Support encryption is unavailable
              </h2>
            </div>
            <p className="text-muted-foreground text-sm">{error}</p>
            <button
              className="bg-primary text-primary-foreground hover:bg-primary/90 focus-visible:outline-primary rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2"
              onClick={() => void initialize()}
              type="button"
            >
              Try again
            </button>
          </div>
        ) : (
          <form className="space-y-4" onSubmit={(event) => void unlock(event)}>
            <div className="flex items-center gap-3">
              <KeyRound className="text-primary" size={22} />
              <h2 className="text-lg font-semibold">
                {state === "setup" ? "Set up encrypted support" : "Unlock encrypted support"}
              </h2>
            </div>
            <p className="text-muted-foreground text-sm leading-6">
              {state === "setup"
                ? "Create a long passphrase for your support key. The server stores only a copy encrypted with this passphrase. Save the passphrase: AverQel cannot recover it."
                : "Enter your support-encryption passphrase. It unlocks your private key in this browser only; the server never receives the passphrase."}
            </p>
            <label className="block space-y-1 text-sm">
              <span>{state === "setup" ? "New passphrase (14+ characters)" : "Passphrase"}</span>
              <input
                autoComplete="off"
                className="border-glass-border bg-surface-1 text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-primary/25 w-full rounded-lg border px-3 py-2 focus:ring-2 focus:outline-none"
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
                  className="border-glass-border bg-surface-1 text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-primary/25 w-full rounded-lg border px-3 py-2 focus:ring-2 focus:outline-none"
                  onChange={(event) => setConfirmation(event.target.value)}
                  required
                  type="password"
                  value={confirmation}
                />
              </label>
            )}
            {error && (
              <p className="text-sm text-rose-700 dark:text-rose-300" role="alert">
                {error}
              </p>
            )}
            <button
              className="bg-primary text-primary-foreground hover:bg-primary/90 focus-visible:outline-primary flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60"
              disabled={working || !passphrase}
              type="submit"
            >
              {working && <Loader2 className="animate-spin" size={16} />}
              {state === "setup" ? "Create encrypted key" : "Unlock support messages"}
            </button>
            <p className="text-muted-foreground text-xs leading-5">
              Message text is encrypted before upload. Account IDs, status, category, and timestamps
              remain available to the service for routing and support operations.
            </p>
            <p className="text-muted-foreground text-xs leading-5">
              Once unlocked, your key stays available across Support and Feedback while you use
              AverQel. It locks after {SUPPORT_ENCRYPTION_IDLE_TIMEOUT_MS / (60 * 60 * 1000)} hours
              without activity, when you sign out, or when your
              login session expires.
            </p>
          </form>
        )}
      </section>
    );

  return { ready: state === "ready" && context !== null, context, panel };
}
