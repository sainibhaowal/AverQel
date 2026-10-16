import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { expect, it } from "vitest";

import AverQelLogo from "../app/components/ui/AverQelLogo";

const globalStyles = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");

it("keeps the nav icon and wordmark as a close, vertically aligned lockup", () => {
  render(<AverQelLogo size="nav" />);

  const lockup = document.querySelector<HTMLElement>("[data-brand-lockup]");
  expect(lockup).not.toBeNull();
  if (!lockup) return;
  expect(lockup).toHaveClass("averqel-logo", "averqel-logo--nav");
  expect(lockup).toHaveStyle({ columnGap: "0rem" });
  expect(lockup.querySelector(".averqel-logo__wordmark")).toBeInTheDocument();
  expect(lockup.querySelector('img[src="/brand/AverQel_Icon.svg"]')).toBeInTheDocument();
  expect(lockup.querySelector('img[src="/brand/AverQel_Icon.svg"]')).toHaveAttribute("width", "92");
  expect(lockup.querySelector('img[src="/brand/AverQel_Icon.svg"]')).toHaveAttribute(
    "height",
    "46",
  );
  expect(lockup.querySelector(".averqel-wordmark__svg")).toHaveAttribute("width", "156");
  expect(lockup.querySelector(".averqel-wordmark__svg")).toHaveAttribute("height", "29");
});

it("uses the same tight canvas overlap for the compact footer lockup", () => {
  render(<AverQelLogo size="footer" />);

  const lockup = document.querySelector<HTMLElement>("[data-brand-lockup]");
  expect(lockup).not.toBeNull();
  if (!lockup) return;
  expect(lockup).toHaveClass("averqel-logo", "averqel-logo--footer");
  expect(lockup).toHaveStyle({ columnGap: "0rem" });
  expect(lockup.querySelector(".averqel-logo__wordmark")).toBeInTheDocument();
});

it("keeps the wordmark optically centered without size-specific downward offsets", () => {
  expect(globalStyles).toContain("transform: translateY(1px);");
  expect(globalStyles).not.toMatch(
    /\.averqel-wordmark--nav\s+\.averqel-wordmark__svg\s*\{[^}]*transform:/s,
  );
  expect(globalStyles).not.toMatch(
    /\.landing-trace-frame\s+\.averqel-wordmark--nav\s+\.averqel-wordmark__svg\s*\{[^}]*transform:/s,
  );
  expect(globalStyles).not.toMatch(
    /\.averqel-wordmark--footer\s+\.averqel-wordmark__svg\s*\{[^}]*transform:/s,
  );
});
