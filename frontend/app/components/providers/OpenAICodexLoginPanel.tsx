"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, KeyRound, LoaderCircle, LogOut, RefreshCw } from "lucide-react";

type Props = {
  initialAccountId: string | null;
  onChange: (accountId: string | null, models: ElectronCodexModel[]) => void;
};

export default function OpenAICodexLoginPanel({ initialAccountId, onChange }: Props) {
  const [available, setAvailable] = useState(false);
  const [chatgptSignInAvailable, setChatgptSignInAvailable] = useState(false);
  const [accounts, setAccounts] = useState<ElectronCodexAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState(initialAccountId || "");
  const [models, setModels] = useState<ElectronCodexModel[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cliMessage, setCliMessage] = useState("");

  const publish = useCallback(
    (accountId: string | null, accountModels: ElectronCodexModel[]) => {
      setSelectedAccountId(accountId || "");
      setModels(accountModels);
      onChange(accountId, accountModels);
    },
    [onChange],
  );

  const loadModels = useCallback(
    async (accountId: string) => {
      const electron = window.electron;
      if (!electron?.codex) throw new Error("Codex login is available in AverQel Desktop only.");
      const accountModels = await electron.codex.models(accountId);
      publish(accountId, accountModels);
      setError("");
    },
    [publish],
  );

  useEffect(() => {
    let cancelled = false;
    const initialize = async () => {
      const electron = window.electron;
      if (!electron?.isElectron || !electron.codex) {
        setAvailable(false);
        setError("Codex login is available in the AverQel Windows, Linux, and macOS desktop app.");
        return;
      }
      try {
        const status = await electron.codex.status();
        if (cancelled) return;
        setAvailable(status.available);
        setChatgptSignInAvailable(status.chatgptSignInAvailable ?? status.available);
        setAccounts(status.accounts);
        setCliMessage(status.cliMessage || "");
        if (!status.available) {
          setError(status.message || "Secure operating-system credential storage is unavailable.");
          return;
        }
        const matching = status.accounts.find((account) => account.id === initialAccountId);
        const account =
          matching ||
          status.accounts.find((candidate) => candidate.source === "codex_cli") ||
          (status.accounts.length === 1 ? status.accounts[0] : null);
        if (account) {
          setSelectedAccountId(account.id);
          await loadModels(account.id);
        } else {
          publish(null, []);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Codex account status could not be loaded.",
          );
        }
      }
    };
    void initialize();
    return () => {
      cancelled = true;
    };
  }, [initialAccountId, loadModels, publish]);

  const handleSelect = async (accountId: string) => {
    setSelectedAccountId(accountId);
    setError("");
    setNotice("");
    if (!accountId) {
      publish(null, []);
      return;
    }
    setBusy(true);
    try {
      await loadModels(accountId);
    } catch (loadError) {
      publish(accountId, []);
      setError(
        loadError instanceof Error
          ? loadError.message
          : "The account model list could not be loaded.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleConnect = async (
    requestedSource?: "chatgpt" | "codex_cli",
    startNewChatGPTAccount = false,
  ) => {
    const electron = window.electron;
    if (!electron?.codex) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const selected = accounts.find((account) => account.id === selectedAccountId);
      const source = requestedSource || selected?.source || "chatgpt";
      const accountId = startNewChatGPTAccount ? null : selectedAccountId || null;
      const result = await electron.codex.connect(accountId, source);
      const status = await electron.codex.status();
      setAccounts(status.accounts);
      setChatgptSignInAvailable(status.chatgptSignInAvailable ?? status.available);
      setCliMessage(status.cliMessage || "");
      publish(result.account.id, result.models);
      if (result.modelError) setError(result.modelError);
    } catch (connectError) {
      setError(connectError instanceof Error ? connectError.message : "ChatGPT sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    const electron = window.electron;
    if (!electron?.codex || !selectedAccountId) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await electron.codex.disconnect(selectedAccountId);
      const status = await electron.codex.status();
      setAccounts(status.accounts);
      setChatgptSignInAvailable(status.chatgptSignInAvailable ?? status.available);
      setCliMessage(status.cliMessage || "");
      publish(null, []);
      setNotice(
        result.revoked
          ? "Removed from this desktop. OpenAI confirmed the revocation request."
          : "Removed from this desktop, but OpenAI could not confirm revocation. Check ChatGPT Settings → Usage to remove AverQel’s access.",
      );
    } catch (disconnectError) {
      setError(
        disconnectError instanceof Error
          ? disconnectError.message
          : "ChatGPT account could not be removed.",
      );
    } finally {
      setBusy(false);
    }
  };

  const selectedAccount = accounts.find((account) => account.id === selectedAccountId) || null;

  if (!available && !error) {
    return (
      <div className="text-muted-foreground rounded-xl border border-white/10 bg-black/20 p-4 text-xs">
        Checking secure desktop sign-in…
      </div>
    );
  }

  return (
    <section className="space-y-4 rounded-2xl border border-teal-400/20 bg-teal-950/20 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-lg border border-teal-300/20 bg-teal-400/10 p-2 text-teal-200">
          <KeyRound size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-foreground text-sm font-semibold">
            ChatGPT account for Codex models
          </h3>
          <p className="text-muted-foreground mt-1 text-xs leading-5">
            AverQel can use your existing Codex CLI ChatGPT sign-in. If it is not available, sign in
            with ChatGPT in your system browser. Credentials stay in the local sign-in store.
            DeepSpace prompts still pass through the AverQel server.
          </p>
        </div>
      </div>

      {!available ? (
        <p
          role="alert"
          className="rounded-lg border border-amber-400/20 bg-amber-950/20 p-3 text-xs text-amber-200"
        >
          {error || "Secure operating-system credential storage is unavailable."}
        </p>
      ) : (
        <>
          {accounts.length > 0 && (
            <label className="block space-y-1.5">
              <span className="text-muted-foreground text-[10px] font-semibold tracking-[0.16em] uppercase">
                Connected ChatGPT account
              </span>
              <select
                value={selectedAccountId}
                onChange={(event) => void handleSelect(event.target.value)}
                disabled={busy}
                className="text-foreground h-10 w-full rounded-lg border border-white/10 bg-slate-950/80 px-3 text-xs outline-none focus:border-teal-300/40"
              >
                <option value="">Choose a saved account</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.source === "codex_cli"
                      ? `Use signed-in Codex CLI account${account.planType ? ` (${account.planType.toUpperCase()})` : ""}`
                      : account.name || account.email || "ChatGPT account"}
                  </option>
                ))}
              </select>
            </label>
          )}

          {selectedAccountId && models.length > 0 ? (
            <div className="flex items-center gap-2 text-xs text-teal-100">
              <Check size={14} />
              {models.length} model options listed; access is confirmed when a model is used
            </div>
          ) : null}

          {cliMessage ? (
            <p className="text-muted-foreground rounded-lg border border-white/10 bg-black/10 p-3 text-xs">
              {cliMessage}
            </p>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {selectedAccountId ? (
              <button
                type="button"
                onClick={() => void handleSelect(selectedAccountId)}
                disabled={busy}
                className="text-muted-foreground inline-flex h-9 items-center gap-2 rounded-lg border border-white/10 px-3 text-xs transition hover:border-teal-300/25 hover:text-teal-100 disabled:opacity-50"
              >
                {busy ? (
                  <LoaderCircle size={14} className="animate-spin" />
                ) : (
                  <RefreshCw size={14} />
                )}
                {models.length > 0 ? "Refresh models" : "Retry model list"}
              </button>
            ) : null}
            {selectedAccount ? (
              <button
                type="button"
                onClick={() => void handleConnect(selectedAccount.source || "chatgpt")}
                disabled={busy}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-teal-300/25 bg-teal-400/10 px-3 text-xs font-semibold text-teal-100 transition hover:bg-teal-400/15 disabled:opacity-50"
              >
                {busy ? (
                  <LoaderCircle size={14} className="animate-spin" />
                ) : (
                  <RefreshCw size={14} />
                )}
                {selectedAccount.source === "codex_cli" ? "Use Codex CLI login" : "Sign in again"}
              </button>
            ) : null}
            {selectedAccount?.source !== "codex_cli" && selectedAccountId ? (
              <button
                type="button"
                onClick={() => void handleDisconnect()}
                disabled={busy}
                className="text-muted-foreground inline-flex h-9 items-center gap-2 rounded-lg border border-white/10 px-3 text-xs transition hover:border-red-300/25 hover:text-red-200 disabled:opacity-50"
              >
                <LogOut size={14} />
                Remove from this desktop
              </button>
            ) : null}
            {chatgptSignInAvailable ? (
              <button
                type="button"
                onClick={() => void handleConnect("chatgpt", true)}
                disabled={busy}
                className="text-muted-foreground inline-flex h-9 items-center gap-2 rounded-lg border border-white/10 px-3 text-xs transition hover:border-teal-300/25 hover:text-teal-100 disabled:opacity-50"
              >
                {busy ? (
                  <LoaderCircle size={14} className="animate-spin" />
                ) : (
                  <KeyRound size={14} />
                )}
                {selectedAccount?.source === "codex_cli"
                  ? "Sign in with ChatGPT instead"
                  : "Continue with ChatGPT"}
              </button>
            ) : null}
          </div>
          {error ? (
            <p
              role="alert"
              className="rounded-lg border border-red-400/20 bg-red-950/20 p-3 text-xs text-red-200"
            >
              {error}
            </p>
          ) : null}
          {notice ? (
            <p
              role="status"
              className="rounded-lg border border-teal-300/20 bg-teal-950/20 p-3 text-xs text-teal-100"
            >
              {notice}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
