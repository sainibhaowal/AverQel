import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Documentation | AverQel",
  description:
    "Product guides for AverQel Documents Hub, Query, DeepSpace, Collections, providers, privacy, support, and account settings.",
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
