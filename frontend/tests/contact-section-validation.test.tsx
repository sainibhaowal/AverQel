import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      return React.createElement(tag, domProps, children);
    };

  return {
    motion: new Proxy({}, { get: (_, tag: string) => createMotionComponent(tag) }),
    useReducedMotion: () => true,
  };
});

import ContactSection from "../app/components/marketing/ContactSection";

describe("ContactSection validation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("requires a valid email before requesting a verification code", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ available: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ContactSection />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /email me a code/i })).toBeEnabled(),
    );

    fireEvent.click(screen.getByRole("button", { name: /email me a code/i }));

    expect(
      await screen.findByText("Enter a valid email address, such as you@example.com."),
    ).toBeVisible();
    expect(screen.getByLabelText("Email for my reply")).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("unlocks message fields only after the email code is confirmed", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ available: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ challenge_id: "challenge_id_for_contact_test_123456" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          verified: true,
          verification_token: "verified-token-for-contact-test",
        }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);

    render(<ContactSection />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /email me a code/i })).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("Email for my reply"), {
      target: { value: "visitor@example.net" },
    });
    fireEvent.click(screen.getByRole("button", { name: /email me a code/i }));
    expect(
      await screen.findByText("A code was sent. Check your inbox and spam folder."),
    ).toBeVisible();
    expect(screen.getByLabelText("Verification code")).toBeVisible();
    expect(screen.queryByLabelText("Your name")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Verification code"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    expect(
      await screen.findByText("Email verified. You can now write and send your message."),
    ).toBeVisible();
    expect(screen.getByText("Verified")).toBeVisible();
    expect(screen.getByLabelText("Your name")).toBeVisible();
    expect(screen.getByLabelText("Subject")).toBeVisible();
    expect(screen.getByLabelText("Your message")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Ada" } });
    fireEvent.change(screen.getByLabelText("Subject"), { target: { value: "Question" } });
    fireEvent.change(screen.getByLabelText("Your message"), {
      target: { value: "I have a question." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(
      await screen.findByText(
        "Your message was accepted by the email service. Thank you for reaching out.",
      ),
    ).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(4);
    const submission = fetchMock.mock.calls[3][1] as RequestInit;
    expect(JSON.parse(String(submission.body))).toMatchObject({
      email: "visitor@example.net",
      verification_token: "verified-token-for-contact-test",
      name: "Ada",
      subject: "Question",
      message: "I have a question.",
    });
  });
});
