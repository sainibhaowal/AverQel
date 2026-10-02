import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
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

import CapabilityDirectory from "../app/components/marketing/CapabilityDirectory";

describe("CapabilityDirectory", () => {
  it("exposes each current capability with an honest status and documentation route", () => {
    render(<CapabilityDirectory />);

    expect(
      screen.getByRole("heading", { name: /one workspace, clear ways to work/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /DeepSpace workspace/i })).toHaveAttribute(
      "href",
      "/documentation/memory-workspace",
    );
    expect(screen.getByRole("link", { name: /Library \+ document intelligence/i })).toHaveAttribute(
      "href",
      "/documentation/library",
    );
    expect(screen.getByRole("link", { name: /Sandboxed analysis/i })).toHaveAttribute(
      "href",
      "/documentation/sandbox",
    );
    expect(screen.getByRole("link", { name: /Artifacts \+ exports/i })).toHaveAttribute(
      "href",
      "/documentation/artifacts",
    );
    expect(screen.getByRole("link", { name: /Schedules \+ long-running work/i })).toHaveAttribute(
      "href",
      "/documentation/automation",
    );
    expect(screen.getByRole("link", { name: /Voice \+ realtime/i })).toHaveAttribute(
      "href",
      "/documentation/voice",
    );
    expect(screen.getByText(/Enable sandbox profile/i)).toBeInTheDocument();
    expect(screen.getByText(/Worker \+ Beat required/i)).toBeInTheDocument();
    expect(screen.getByText(/Deployment gated/i)).toBeInTheDocument();
  });
});

import VoiceDocsPage from "../app/documentation/voice/page";

describe("VoiceDocsPage", () => {
  it("states the deployment gates without promising availability", () => {
    render(<VoiceDocsPage />);

    const headings = screen.getAllByRole("heading", { name: /Voice & Realtime/i });
    expect(headings.length).toBeGreaterThan(0);
    expect(screen.getAllByText(/deployment-gated/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/microphone permission/i).length).toBeGreaterThan(0);
  });
});
