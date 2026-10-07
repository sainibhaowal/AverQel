import SharedDocumentClient from "./SharedDocumentClient";
import { Suspense } from "react";

export function generateStaticParams() {
  return [{ link_id: "default" }];
}
export default function SharedDocumentPage() {
  return (
    <Suspense fallback={null}>
      <SharedDocumentClient />
    </Suspense>
  );
}
