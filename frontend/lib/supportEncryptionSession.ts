import type { SupportPublicKey } from "@/lib/supportEncryption";

export type SupportEncryptionContext = {
  privateKey: CryptoKey;
  keyId: string;
  ownPublicKey: SupportPublicKey;
  adminPublicKey: SupportPublicKey;
};

export type SupportEncryptionScope = "user" | "admin";

export const SUPPORT_ENCRYPTION_LOCK_EVENT = "averqel_support_encryption_locked";
export const SUPPORT_ENCRYPTION_IDLE_TIMEOUT_MS = 4 * 60 * 60 * 1000;

type LockReason = "idle" | "auth";

type LockEventDetail = {
  sessionKey: string;
  reason: LockReason;
};

type UnlockedSession = {
  context: SupportEncryptionContext;
  expiresAt: number;
  timer: number;
};

const unlockedSessions = new Map<string, UnlockedSession>();
let lifecycleListenersInstalled = false;

export function getSupportEncryptionSessionKey(
  scope: SupportEncryptionScope,
  userId: string | null,
  tenantId: string | null,
): string | null {
  if (!userId || (scope === "user" && !tenantId)) return null;

  // The administrator key is platform-wide; user keys are tenant-scoped.
  return JSON.stringify([scope, userId, scope === "admin" ? "platform" : tenantId]);
}

function dispatchLockEvent(sessionKey: string, reason: LockReason) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<LockEventDetail>(SUPPORT_ENCRYPTION_LOCK_EVENT, {
      detail: { sessionKey, reason },
    }),
  );
}

function lockSession(sessionKey: string, reason: LockReason) {
  const session = unlockedSessions.get(sessionKey);
  if (!session) return;
  window.clearTimeout(session.timer);
  unlockedSessions.delete(sessionKey);
  dispatchLockEvent(sessionKey, reason);
}

function scheduleExpiry(sessionKey: string, session: UnlockedSession) {
  window.clearTimeout(session.timer);
  session.timer = window.setTimeout(
    () => {
      const activeSession = unlockedSessions.get(sessionKey);
      if (activeSession !== session) return;

      if (activeSession.expiresAt <= Date.now()) {
        lockSession(sessionKey, "idle");
        return;
      }

      scheduleExpiry(sessionKey, activeSession);
    },
    Math.max(1, session.expiresAt - Date.now()),
  );
}

function expireOrExtendSessions() {
  const now = Date.now();
  for (const [sessionKey, session] of unlockedSessions) {
    if (session.expiresAt <= now) {
      lockSession(sessionKey, "idle");
      continue;
    }

    session.expiresAt = now + SUPPORT_ENCRYPTION_IDLE_TIMEOUT_MS;
    scheduleExpiry(sessionKey, session);
  }
}

function expireSessionsWithoutExtending() {
  const now = Date.now();
  for (const [sessionKey, session] of unlockedSessions) {
    if (session.expiresAt <= now) lockSession(sessionKey, "idle");
  }
}

function handleAuthStorage(event: StorageEvent) {
  if (event.key === "averqel_token" && event.newValue === null) {
    clearSupportEncryptionSessions();
  }
}

function installLifecycleListeners() {
  if (lifecycleListenersInstalled || typeof window === "undefined") return;
  lifecycleListenersInstalled = true;

  document.addEventListener("pointerdown", expireOrExtendSessions, { passive: true });
  document.addEventListener("keydown", expireOrExtendSessions);
  document.addEventListener("touchstart", expireOrExtendSessions, { passive: true });
  document.addEventListener("wheel", expireOrExtendSessions, { passive: true });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") expireSessionsWithoutExtending();
  });
  window.addEventListener("storage", handleAuthStorage);
}

export function getUnlockedSupportEncryptionSession(
  sessionKey: string,
): SupportEncryptionContext | null {
  const session = unlockedSessions.get(sessionKey);
  if (!session) return null;
  if (session.expiresAt <= Date.now()) {
    lockSession(sessionKey, "idle");
    return null;
  }

  session.expiresAt = Date.now() + SUPPORT_ENCRYPTION_IDLE_TIMEOUT_MS;
  scheduleExpiry(sessionKey, session);
  return session.context;
}

export function rememberUnlockedSupportEncryptionSession(
  sessionKey: string,
  context: SupportEncryptionContext,
) {
  if (typeof window === "undefined") return;
  installLifecycleListeners();

  const existing = unlockedSessions.get(sessionKey);
  if (existing) window.clearTimeout(existing.timer);

  const session: UnlockedSession = {
    context,
    expiresAt: Date.now() + SUPPORT_ENCRYPTION_IDLE_TIMEOUT_MS,
    timer: 0,
  };
  unlockedSessions.set(sessionKey, session);
  scheduleExpiry(sessionKey, session);
}

export function clearSupportEncryptionSessions() {
  if (typeof window === "undefined") return;
  for (const sessionKey of [...unlockedSessions.keys()]) lockSession(sessionKey, "auth");
}

export function clearSupportEncryptionSession(sessionKey: string) {
  if (typeof window === "undefined") return;
  lockSession(sessionKey, "auth");
}

export function isSupportEncryptionLockEvent(event: Event): event is CustomEvent<LockEventDetail> {
  return event instanceof CustomEvent && typeof event.detail?.sessionKey === "string";
}
