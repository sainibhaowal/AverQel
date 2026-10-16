import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import AverQelWordmark from "../app/components/ui/AverQelWordmark";

it("renders the approved text logo asset with the shared wordmark wrapper", () => {
  render(<AverQelWordmark />);

  const wordmark = screen.getByLabelText("AverQel");
  expect(wordmark).toHaveClass("averqel-wordmark", "averqel-wordmark--nav");
  expect(wordmark).toHaveAttribute("role", "img");
  expect(wordmark.querySelector(".averqel-wordmark__svg")).not.toBeNull();
  expect(wordmark.querySelector("image")).toHaveAttribute("href", "/brand/AverQel_Text.svg");
});

it("supports the compact mobile size", () => {
  render(<AverQelWordmark size="mobile" />);

  expect(screen.getByLabelText("AverQel")).toHaveClass("averqel-wordmark--mobile");
});
