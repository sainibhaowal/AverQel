import type { ReactNode } from "react";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("framer-motion", async () => {
  const React = await import("react");
  const createMotionComponent = (tag: string) =>
    function MotionMock({ children, ...props }: { children?: ReactNode; [key: string]: unknown }) {
      const domProps = { ...props };
      delete domProps.initial;
      delete domProps.whileInView;
      delete domProps.viewport;
      delete domProps.transition;
      return React.createElement(tag, domProps, children);
    };

  return {
    motion: new Proxy({}, { get: (_, tag: string) => createMotionComponent(tag) }),
    AnimatePresence: ({ children }: { children?: ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    useInView: () => true,
    useReducedMotion: () => true,
    useMotionValue: () => ({ get: () => 0, set: () => undefined }),
    useMotionValueEvent: () => undefined,
    useScroll: () => ({ scrollY: { get: () => 0 }, scrollYProgress: 0 }),
    useSpring: (value: unknown) => value,
    useTransform: () => 0,
  };
});

import ProductDomains from "../app/components/marketing/ProductDomains";
import FeaturesGrid from "../app/components/marketing/FeaturesGrid";

describe("ProductDomains", () => {
  it("keeps the product areas in a clear, stable order", () => {
    const { container } = render(<ProductDomains />);
    const ids = Array.from(container.querySelectorAll("section[id]")).map((section) => section.id);

    expect(ids).toEqual([
      "documents-hub",
      "query",
      "collections",
      "deepspace",
      "providers",
      "mcp",
      "workspace-controls",
    ]);
  });

  it("keeps document intake, processing, organization, and sharing inside Documents Hub", () => {
    render(<ProductDomains />);
    const section = document.getElementById("documents-hub");
    expect(section).not.toBeNull();
    const documents = within(section as HTMLElement);

    expect(
      documents.getByRole("heading", { name: /file intake and extraction/i }),
    ).toBeInTheDocument();
    expect(
      documents.getByRole("heading", { name: /processing you can inspect/i }),
    ).toBeInTheDocument();
    expect(
      documents.getByRole("heading", { name: /organization and document automation/i }),
    ).toBeInTheDocument();
    expect(
      documents.getByRole("heading", { name: /document actions and sharing/i }),
    ).toBeInTheDocument();
    expect(documents.getAllByText(/document smart collections/i)).toHaveLength(2);
    expect(
      documents.getByText(/summaries, fact extraction, FAQs, and document comparison/i),
    ).toBeInTheDocument();
    expect(
      documents.getByText(/webhook setup and management require admin permission/i),
    ).toBeInTheDocument();
    expect(documents.queryByText(/approved catalog entries/i)).not.toBeInTheDocument();
    expect(documents.queryByText(/Google Drive/i)).not.toBeInTheDocument();
  });

  it("keeps Query history separate from DeepSpace work and Library files", () => {
    render(<ProductDomains />);
    const querySection = within(document.getElementById("query") as HTMLElement);
    const deepSpaceSection = within(document.getElementById("deepspace") as HTMLElement);

    expect(querySection.getByRole("heading", { name: /scoped retrieval/i })).toBeInTheDocument();
    expect(
      querySection.getByRole("heading", { name: /answers with evidence/i }),
    ).toBeInTheDocument();
    expect(
      querySection.getByText(/Query remains distinct from DeepSpace agent runs/i),
    ).toBeInTheDocument();
    expect(querySection.getByText(/edit or regenerate supported messages/i)).toBeInTheDocument();
    expect(
      deepSpaceSection.getByRole("heading", { name: /DeepSpace Library/i }),
    ).toBeInTheDocument();
    expect(
      deepSpaceSection.getByRole("heading", { name: /DeepSpace Memory/i }),
    ).toBeInTheDocument();
    expect(
      deepSpaceSection.getByRole("heading", { name: /schedules and voice/i }),
    ).toBeInTheDocument();
    expect(
      deepSpaceSection.getByRole("heading", { name: /datasets and derived analysis/i }),
    ).toBeInTheDocument();
    expect(
      deepSpaceSection.getByText(/separate from source documents in Documents Hub/i),
    ).toBeInTheDocument();
    expect(deepSpaceSection.getByText(/separately isolated sandbox/i)).toBeInTheDocument();
  });

  it("separates Collections, AI Providers, MCP, and user-facing workspace controls", () => {
    const { container } = render(<ProductDomains />);
    const collections = within(document.getElementById("collections") as HTMLElement);
    const providers = within(document.getElementById("providers") as HTMLElement);
    const mcp = within(document.getElementById("mcp") as HTMLElement);
    const controls = within(document.getElementById("workspace-controls") as HTMLElement);

    expect(collections.getAllByText(/Experimental beta/i)).toHaveLength(4);
    expect(collections.getByText(/document smart collections/i)).toBeInTheDocument();
    expect(
      collections.getByRole("heading", { name: /member security and alerts/i }),
    ).toBeInTheDocument();
    expect(providers.getByRole("heading", { name: /provider configuration/i })).toBeInTheDocument();
    expect(
      providers.getByText(/Query and DeepSpace use assigned provider roles/i),
    ).toBeInTheDocument();
    expect(mcp.getByRole("heading", { name: /curated marketplace/i })).toBeInTheDocument();
    expect(mcp.getByText(/MCP Inspector/i)).toBeInTheDocument();
    expect(
      mcp.getByText(/arbitrary endpoint registration is not part of this release/i),
    ).toBeInTheDocument();
    expect(controls.getByRole("heading", { name: /support and feedback/i })).toBeInTheDocument();
    expect(controls.getByRole("heading", { name: /notifications/i })).toBeInTheDocument();
    expect(controls.queryByText(/moderation queue/i)).not.toBeInTheDocument();
    expect(container.querySelector('a[href*="/admin"]')).toBeNull();
  });
});

import VoiceDocsPage from "../app/documentation/voice/page";

describe("DocumentsHubMarketing", () => {
  it("names the advanced Documents Hub surface truthfully", () => {
    render(<FeaturesGrid />);

    expect(screen.getByText(/Versions with diff and restore, duplicates/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Quarantine review, quality signals, and bulk retry/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Expiring share links, comments, webhooks/i)).toBeInTheDocument();
  });
});

describe("VoiceDocsPage", () => {
  it("states the deployment gates without promising availability", () => {
    render(<VoiceDocsPage />);

    const headings = screen.getAllByRole("heading", { name: /Voice & Realtime/i });
    expect(headings.length).toBeGreaterThan(0);
    expect(screen.getAllByText(/deployment-gated/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/microphone permission/i).length).toBeGreaterThan(0);
  });
});
