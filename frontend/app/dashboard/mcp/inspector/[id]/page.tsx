"use client";

import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";

export default function MCPInspector({ params }: { params: { id: string } }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const load = () => fetchWithAuth(`/mcp/servers/${params.id}/inspector`)
      .then(async (response) => { if (!response.ok) throw new Error("Inspector unavailable"); return response.json(); })
      .then((value) => { if (active) setData(value); })
      .catch((reason) => { if (active) setError(String(reason)); });
    void load();
    const timer = window.setInterval(load, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [params.id]);
  if (error) return <main className="p-6 text-red-400">{error}</main>;
  if (!data) return <main className="p-6">Loading inspector…</main>;
  return <main className="space-y-6 p-6"><h1 className="text-2xl font-semibold">MCP Inspector: {data.server.name}</h1><pre className="overflow-auto rounded border p-4 text-xs">{JSON.stringify(data, null, 2)}</pre></main>;
}
