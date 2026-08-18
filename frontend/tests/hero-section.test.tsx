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
      delete domProps.animate;
      delete domProps.exit;
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
  it("renders the current landing hero and runtime monitor", () => {
    render(<HeroSection />);

    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent(/Turn your documents into/i);
    expect(heading).toHaveTextContent(/grounded answers and useful work/i);
    expect(screen.getByText(/Your Private AI Workspace/i)).toBeInTheDocument();
    expect(screen.getByText(/Start Using AverQel/i)).toBeInTheDocument();
    expect(screen.getByText(/averqel \| productivity runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/DeepSpace for research and deliverables/i)).toBeInTheDocument();
  });
});
