import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("framer-motion", async () => {
  const React = await import("react");

  const createMotionComponent = (tag: string) =>
    function MotionMock({ children, ...props }: { children?: ReactNode; [key: string]: unknown }) {
      const domProps = { ...props };
      delete domProps.initial;
      delete domProps.whileInView;
      delete domProps.viewport;
      delete domProps.transition;
      delete domProps.animate;
      delete domProps.exit;
      delete domProps.layout;
      return React.createElement(tag, domProps, children);
    };

  return {
    motion: new Proxy(
      {},
      {
        get: (_, tag: string) => createMotionComponent(tag),
      },
    ),
    AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
    useInView: () => true,
    useReducedMotion: () => true,
    useMotionValue: () => ({ get: () => 0, set: () => undefined }),
    useMotionValueEvent: () => undefined,
    useScroll: () => ({ scrollY: { get: () => 0 }, scrollYProgress: 0 }),
    useSpring: (value: unknown) => value,
    useTransform: () => 0,
  };
});

import HeroSection from "../app/components/marketing/HeroSection";

describe("HeroSection", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the current landing hero and runtime monitor", () => {
    render(<HeroSection />);

    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent(/One workspace for knowledge, AI, and action/i);
    expect(screen.getByText(/Your Connected AI Workspace/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Create your workspace/i })).toHaveAttribute(
      "href",
      "/auth/signup",
    );
    expect(screen.getByRole("link", { name: /All desktop builds/i })).toHaveAttribute(
      "href",
      "https://github.com/sainibhaowal/AverQel/releases/latest",
    );
    expect(screen.getByRole("link", { name: /Security Overview/i })).toHaveAttribute(
      "href",
      "/documentation/privacy-security",
    );
    expect(screen.getByRole("link", { name: /Product docs/i })).toHaveAttribute(
      "href",
      "/documentation",
    );
    expect(screen.getByText(/averqel \| productivity runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/DeepSpace for research and deliverables/i)).toBeInTheDocument();
  });

  it("does not offer an unsupported macOS installer", async () => {
    vi.stubGlobal("navigator", {
      userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    });
    render(<HeroSection />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /View Linux and Windows builds/i })).toHaveAttribute(
        "href",
        "https://github.com/sainibhaowal/AverQel/releases/latest",
      );
    });
    expect(screen.queryByRole("link", { name: /Download for macOS/i })).not.toBeInTheDocument();
  });
});
