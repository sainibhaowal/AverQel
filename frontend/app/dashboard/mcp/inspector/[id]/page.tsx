import MCPInspectorClient from "./MCPInspectorClient";

export const dynamic = "force-static";

export function generateStaticParams() {
  return [{ id: "default" }];
}

export default function MCPInspectorPage() {
  return <MCPInspectorClient />;
}
