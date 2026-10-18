import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import DeepSpaceMark from "../app/components/ui/DeepSpaceMark";

vi.mock("next/image", () => ({
  default: (props: {
    src: string;
    alt?: string;
    width?: number;
    height?: number;
    style?: { display?: string; objectFit?: string; transform?: string };
  }) => (
    <span
      data-testid="deepspace-mark"
      data-src={props.src}
      data-alt={props.alt ?? ""}
      data-width={props.width}
      data-height={props.height}
      data-display={props.style?.display}
      data-object-fit={props.style?.objectFit}
      data-transform={props.style?.transform}
    />
  ),
}));

it("uses the supplied transparent DeepSpace logo for the compact mark", () => {
  expect(
    existsSync(
      resolve(process.cwd(), "public/DeepSpace Logo/DeepSpace_Logo_Only_NoBlack_Exact.svg"),
    ),
  ).toBe(true);

  render(<DeepSpaceMark size={18} />);

  expect(screen.getByTestId("deepspace-mark")).toHaveAttribute(
    "data-src",
    "/DeepSpace Logo/DeepSpace_Logo_Only_NoBlack_Exact.svg",
  );
});

it("keeps the non-square logo aligned in a fixed navigation-sized box", () => {
  render(<DeepSpaceMark size={18} />);

  expect(screen.getByTestId("deepspace-mark")).toHaveAttribute("data-width", "18");
  expect(screen.getByTestId("deepspace-mark")).toHaveAttribute("data-height", "18");
  expect(screen.getByTestId("deepspace-mark")).toHaveAttribute("data-display", "block");
  expect(screen.getByTestId("deepspace-mark")).toHaveAttribute("data-object-fit", "contain");
});

it("keeps the emblem decorative when the navigation supplies the DeepSpace label", () => {
  render(<DeepSpaceMark size={18} />);

  expect(screen.getByTestId("deepspace-mark")).toHaveAttribute("data-alt", "");
});

it("can enlarge the artwork without changing its navigation slot", () => {
  render(<DeepSpaceMark size={18} visualScale={1.3} />);

  const mark = screen.getByTestId("deepspace-mark");
  expect(mark).toHaveAttribute("data-width", "18");
  expect(mark).toHaveAttribute("data-height", "18");
  expect(mark).toHaveAttribute("data-transform", "scale(1.3)");
});

it("supports a navbar-specific DeepSpace logo source", () => {
  render(
    <DeepSpaceMark size={18} source="/DeepSpace Logo/DeepSpace_Logo_Only_NoBlack_Exact.svg" />,
  );

  expect(screen.getByTestId("deepspace-mark")).toHaveAttribute(
    "data-src",
    "/DeepSpace Logo/DeepSpace_Logo_Only_NoBlack_Exact.svg",
  );
});
