"use client";

import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type DialogKind = "prompt" | "confirm" | "alert";
type DialogRequest = {
  kind: DialogKind;
  message: string;
  defaultValue?: string;
  resolve: (value: string | boolean | null) => void;
};

const listeners = new Set<(request: DialogRequest) => void>();

function requestDialog(kind: DialogKind, message: string, defaultValue = "") {
  return new Promise<string | boolean | null>((resolve) => {
    listeners.forEach((listener) => listener({ kind, message, defaultValue, resolve }));
  });
}

export async function averqelPrompt(message: string, defaultValue = "") {
  return (await requestDialog("prompt", message, defaultValue)) as string | null;
}

export async function averqelConfirm(message: string) {
  return (await requestDialog("confirm", message)) as boolean;
}

export async function averqelAlert(message: string) {
  await requestDialog("alert", message);
}

export default function AverQelDialogHost() {
  const [request, setRequest] = useState<DialogRequest | null>(null);
  const [value, setValue] = useState("");

  const finish = useCallback((result: string | boolean | null) => {
    if (!request) return;
    request.resolve(result);
    setRequest(null);
  }, [request]);

  useEffect(() => {
    const listener = (next: DialogRequest) => {
      setValue(next.defaultValue ?? "");
      setRequest(next);
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  useEffect(() => {
    if (!request) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish(request.kind === "confirm" ? false : null);
      if (event.key === "Enter" && request.kind !== "alert") finish(request.kind === "prompt" ? value : true);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [finish, request, value]);

  return (
    <AnimatePresence>
      {request ? (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" role="presentation">
          <motion.button
            type="button"
            aria-label="Close dialog"
            className="absolute inset-0 cursor-default bg-slate-950/55 backdrop-blur-md"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => finish(request.kind === "confirm" ? false : null)}
          />
          <motion.section
            role="dialog"
            aria-modal="true"
            aria-labelledby="averqel-dialog-title"
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            className="theme-panel relative w-full max-w-md rounded-2xl border border-primary/20 p-5 shadow-2xl"
          >
            <button type="button" aria-label="Close dialog" onClick={() => finish(request.kind === "confirm" ? false : null)} className="absolute top-4 right-4 rounded-lg p-1.5 text-foreground/50 transition hover:bg-primary/10 hover:text-primary"><X size={17} /></button>
            <div className="mb-5 flex items-center gap-3 pr-8">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary"><AlertTriangle size={17} /></span>
              <div><p id="averqel-dialog-title" className="text-foreground text-sm font-black">AverQel</p><p className="text-foreground/45 mt-0.5 text-[10px] font-bold uppercase tracking-[0.18em]">Workspace action</p></div>
            </div>
            <p className="text-foreground/75 whitespace-pre-line text-sm leading-6">{request.message}</p>
            {request.kind === "prompt" ? <input autoFocus value={value} onChange={(event) => setValue(event.target.value)} className="theme-input mt-4 w-full rounded-xl px-3 py-2.5 text-sm outline-none" /> : null}
            <div className="mt-6 flex justify-end gap-2">
              {request.kind !== "alert" ? <button type="button" onClick={() => finish(request.kind === "confirm" ? false : null)} className="theme-pill px-4 py-2.5 text-xs font-bold">Cancel</button> : null}
              <button type="button" autoFocus={request.kind !== "prompt"} onClick={() => finish(request.kind === "prompt" ? value : true)} className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-xs font-black text-primary-foreground shadow-lg shadow-primary/20 transition hover:brightness-110 active:scale-[0.98]"><Check size={15} />{request.kind === "confirm" ? "Continue" : request.kind === "alert" ? "Close" : "Save"}</button>
            </div>
          </motion.section>
        </div>
      ) : null}
    </AnimatePresence>
  );
}
