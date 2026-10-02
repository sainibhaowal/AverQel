import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import DeepSpaceMarkdownRenderer from "../app/dashboard/deepspace/_components/DeepSpaceMarkdownRenderer";

it("renders ASCII process diagrams in a stable copyable diagram surface", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  const source = `┌──────────┐\n│ INTERFACE│\n└────┬─────┘\n     ↓\n┌──────────┐\n│ TOOL LAYER│\n└──────────┘`;

  const { container } = render(
    <DeepSpaceMarkdownRenderer content={`\`\`\`text\n${source}\n\`\`\``} />,
  );

  const diagram = container.querySelector("section");
  expect(diagram).toBeInTheDocument();
  expect(diagram?.querySelector("pre")).toHaveClass("whitespace-pre");

  fireEvent.click(screen.getByLabelText("Copy ASCII diagram"));
  expect(writeText).toHaveBeenCalledWith(source);
});
