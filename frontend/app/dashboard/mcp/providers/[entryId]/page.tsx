export const dynamic = "force-static";

export function generateStaticParams() {
  return [{ entryId: "default" }];
}

import MCPProviderPageClient from "./MCPProviderPageClient";

export default function MCPProviderPage() {
  return <MCPProviderPageClient />;
}
