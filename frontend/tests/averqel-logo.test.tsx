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
  expect(lockup.querySelector(".averqel-logo__wordmark > div")).toHaveClass(
    "flex",
    "items-center",
    "leading-none",
  );
  expect(lockup.querySelector("img")).toBeInTheDocument();
  expect(lockup.querySelector("img")).toHaveAttribute("width", "92");
  expect(lockup.querySelector("img")).toHaveAttribute("height", "46");
  expect(lockup.querySelector(".averqel-wordmark__svg")).toHaveAttribute("width", "156");
  expect(lockup.querySelector(".averqel-wordmark__svg")).toHaveAttribute("height", "29");
});

it("supports the icon-only logo used in the navigation bars", () => {
  render(<AverQelLogo size="nav" showWordmark={false} />);

  const lockup = document.querySelector<HTMLElement>("[data-brand-lockup]");
  expect(lockup).not.toBeNull();
  if (!lockup) return;

  expect(lockup.querySelector("img")).toHaveAttribute("alt", "AverQel");
  expect(lockup.querySelector(".averqel-logo__wordmark")).not.toBeInTheDocument();
});

it("uses the same tight canvas overlap for the compact footer lockup", () => {
  render(<AverQelLogo size="footer" />);

  const lockup = document.querySelector<HTMLElement>("[data-brand-lockup]");
  expect(lockup).not.toBeNull();
  if (!lockup) return;
  expect(lockup).toHaveClass("averqel-logo", "averqel-logo--footer");
  expect(lockup).toHaveStyle({ columnGap: "0rem" });
  expect(lockup.querySelector(".averqel-logo__wordmark")).toBeInTheDocument();
  expect(lockup.querySelector(".averqel-logo__wordmark > div")).toHaveClass(
    "flex",
    "items-center",
    "leading-none",
  );
});

it("uses the correct optical centering for the footer wordmark canvas", () => {
  expect(globalStyles).toMatch(/\.averqel-wordmark__svg\s*\{[^}]*transform:\s*translateY\(1px\);/);
  expect(globalStyles).toMatch(
    /\.averqel-wordmark--footer\s+\.averqel-wordmark__svg\s*\{[^}]*transform:\s*translateY\(0\.5px\);/,
  );

  const reducedMotionWordmarkRule = globalStyles.match(
    /@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?\.averqel-wordmark__svg\s*\{([^}]*)\}/,
  )?.[1];
  expect(reducedMotionWordmarkRule).toBeDefined();
  expect(reducedMotionWordmarkRule).not.toContain("transform:");
});
