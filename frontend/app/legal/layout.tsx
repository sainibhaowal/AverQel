import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Legal & Trust | AverQel",
  description: "Privacy, Security, Terms, and Trust policies for AverQel",
};

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return children;
}
