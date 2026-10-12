import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import DeepSpaceMark from "../app/components/ui/DeepSpaceMark";

vi.mock("next/image", () => ({
  default: (props: { src: string; alt?: string }) => (
    <span data-testid="deepspace-mark" data-src={props.src} data-alt={props.alt ?? ""} />
  ),
}));

it("uses the logo-only asset with transparent pixels for the DeepSpace mark", () => {
  render(<DeepSpaceMark size={18} />);

  expect(screen.getByTestId("deepspace-mark")).toHaveAttribute(
    "data-src",
    "/brand/deepspace-orbital-vortex-logo-only.webp",
  );

  const webp = readFileSync(
    resolve(process.cwd(), "public/brand/deepspace-orbital-vortex-logo-only.webp"),
  );

  expect(webp.subarray(0, 4).toString("ascii")).toBe("RIFF");
  expect(webp.subarray(8, 12).toString("ascii")).toBe("WEBP");
  expect(webp.subarray(12, 16).toString("ascii")).toBe("VP8X");
  expect(webp[20] & 0x10).toBe(0x10);
});
