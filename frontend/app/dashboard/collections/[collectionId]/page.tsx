import CollectionDetailClient from "../../admin/collections/[collectionId]/CollectionDetailClient";

export const dynamic = "force-static";

export function generateStaticParams() {
  return [{ collectionId: "default" }];
}

export default function Page() {
  return <CollectionDetailClient />;
}
