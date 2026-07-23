import { ShieldAlert } from "lucide-react";

export default function MCPCommunityWarning() {
  return (
    <aside className="flex gap-3 rounded-xl border border-amber-400/25 bg-amber-400/10 p-4 text-sm text-amber-100" role="note">
      <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" aria-hidden="true" />
      <p>
        This is a reviewed community connector. AverQel does not operate or guarantee the vendor&apos;s tools.
        Review its documentation, permissions, and privacy policy before connecting.
      </p>
    </aside>
  );
}
