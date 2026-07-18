import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Documentation | AverQel",
  description: "Product documentation, guides, and help for AverQel",
};

/**
 * Documentation Layout
 *
 * This layout serves as a container for all application documentation.
 * Future structure suggestions:
 *
 * /documentation/
 *   /guides/              - User guides, tutorials, getting started
 *   /integrations/        - Third-party integrations, API docs
 *   /faq/                 - Frequently asked questions
 *   /changelog/           - Release notes and version history
 *   /features/            - Feature documentation and specifications
 *   /troubleshooting/     - Common issues and solutions
 *
 * Each section can have its own page.tsx and sub-sections.
 * Routes will be: /documentation/guides/, /documentation/integrations/, etc.
 */

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
