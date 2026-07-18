import type { ReactNode } from "react";

export default function PolicySection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-white">{title}</h2>
      <div className="space-y-3 text-sm leading-7 text-slate-300">{children}</div>
    </section>
  );
}
