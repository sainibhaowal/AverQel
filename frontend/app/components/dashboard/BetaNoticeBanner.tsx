"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, X } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";

const STORAGE_KEY = "averqel_beta_notice";

type BetaBlock = {
  enabled: boolean;
  plan_id: string;
  plan_name: string;
  resurface_hours: number;
};

type NoticeState = {
  dismissedForever?: boolean;
  lastShown?: number;
};

function readNoticeState(): NoticeState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as NoticeState;
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed;
  } catch {
    return {};
  }
}

function writeNoticeState(state: NoticeState): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Storage unavailable (private mode): show every visit instead of crashing.
  }
}

export default function BetaNoticeBanner() {
  const router = useRouter();
  const [beta, setBeta] = useState<BetaBlock | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = (await fetchWithAuth("/plans/current")) as Response;
        if (cancelled || !response.ok) return;
        const data = (await response.json()) as { beta?: BetaBlock };
        if (!data?.beta?.enabled) return;
        const block = data.beta;
        const stored = readNoticeState();
        if (stored.dismissedForever) return;
        const resurfaceMs = Math.max(1, block.resurface_hours) * 3600 * 1000;
        if (stored.lastShown && Date.now() - stored.lastShown < resurfaceMs) return;
        writeNoticeState({ ...stored, lastShown: Date.now() });
        setBeta(block);
        setVisible(true);
      } catch {
        // Plans endpoint unreachable: never block the dashboard for a notice.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!visible || !beta) return null;

  const goToPlan = () => router.push("/dashboard/settings/plan");

  return (
    <div
      role="region"
      aria-label="Beta notice"
      className="border-primary/25 bg-primary/[0.07] mb-3 flex w-full flex-col gap-2 rounded-2xl border p-4 sm:flex-row sm:items-center sm:gap-4"
    >
      <button
        type="button"
        onClick={goToPlan}
        className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 text-left"
        aria-label={`View your ${beta.plan_name} plan and storage`}
      >
        <span className="bg-primary/15 text-primary inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
          <Sparkles size={17} />
        </span>
        <span className="min-w-0">
          <span className="text-foreground block truncate text-sm font-bold">
            You&apos;re on {beta.plan_name} — free until production release
          </span>
          <span className="text-muted-foreground block truncate text-xs">
            Everything in AverQel is open during beta. Tap to see your plan and storage.
          </span>
        </span>
      </button>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={() => {
            writeNoticeState({ dismissedForever: true, lastShown: Date.now() });
            setVisible(false);
          }}
          className="border-border/70 text-muted-foreground hover:text-foreground rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors"
        >
          Don&apos;t show again
        </button>
        <button
          type="button"
          onClick={() => {
            writeNoticeState({ lastShown: Date.now() });
            setVisible(false);
          }}
          aria-label="Dismiss beta notice"
          className="border-border/70 text-muted-foreground hover:text-foreground inline-flex h-8 w-8 items-center justify-center rounded-full border transition-colors"
        >
          <X size={15} />
        </button>
      </div>
    </div>
  );
}
