import { Suspense } from "react";
import type { Metadata } from "next";

import ComposioCallbackClient from "./ComposioCallbackClient";

export const metadata: Metadata = { referrer: "no-referrer" };

export default function ComposioCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="mcp-theme-scope mx-auto flex min-h-[50vh] max-w-2xl items-center px-6 py-16">
          <p className="text-sm text-white/65">Preparing Composio verification…</p>
        </main>
      }
    >
      <ComposioCallbackClient />
    </Suspense>
  );
}
