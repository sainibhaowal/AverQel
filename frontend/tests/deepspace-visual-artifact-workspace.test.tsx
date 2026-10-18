import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DeepSpaceVisualArtifactWorkspace, {
  isVisualArtifactDocument,
} from "../app/dashboard/deepspace/_components/DeepSpaceVisualArtifactWorkspace";

describe("DeepSpace saved visual artifacts", () => {
  const block = {
    id: "saved-card-1",
    block_id: "saved-card-1",
    type: "card" as const,
    title: "Saved revenue card",
    content: "Revenue grew this quarter.",
    tone: "success" as const,
    metrics: [{ label: "Revenue", value: "$4m" }],
    actions: [],
    revision: 4,
    schema_version: 1,
  };
  const document = {
    block_id: block.id,
    schema_version: 1,
    revision: block.revision,
    kind: "card",
    data: block,
    source_markdown: null,
    source_mermaid: null,
    assets: [],
    history: [],
    undo: {},
  };

  it("recognizes and rehydrates the persisted visual document", () => {
    expect(isVisualArtifactDocument(JSON.stringify(document))).toBe(true);
    render(
      <DeepSpaceVisualArtifactWorkspace
        value={JSON.stringify(document)}
        onChange={() => {}}
        onBlockChange={() => {}}
      />,
    );
    expect(screen.getByRole("heading", { name: "Saved revenue card" })).toBeInTheDocument();
    expect(screen.getByText("Revenue grew this quarter.")).toBeInTheDocument();
  });

  it("sends artifact edits back as a new revision", async () => {
    const onChange = vi.fn();
    const onBlockChange = vi.fn().mockResolvedValue(undefined);
    render(
      <DeepSpaceVisualArtifactWorkspace
        value={JSON.stringify(document)}
        onChange={onChange}
        onBlockChange={onBlockChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Edit card" }));
    const editor = screen.getByRole("textbox", { name: "Edit card fields as JSON" });
    const edited = { ...block, title: "Updated saved revenue card" };
    fireEvent.change(editor, { target: { value: JSON.stringify(edited, null, 2) } });
    fireEvent.click(screen.getByRole("button", { name: "Save card" }));

    await waitFor(() => expect(onBlockChange).toHaveBeenCalledTimes(1));
    expect(onBlockChange).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Updated saved revenue card", revision: 5 }),
    );
    expect(JSON.parse(onChange.mock.calls[0]?.[0] as string).revision).toBe(5);
  });

  it("shows when an artifact edit cannot synchronize back to chat or note", async () => {
    const onBlockChange = vi.fn().mockRejectedValue(new Error("Chat revision conflict"));
    render(
      <DeepSpaceVisualArtifactWorkspace
        value={JSON.stringify(document)}
        onChange={() => {}}
        onBlockChange={onBlockChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Edit card" }));
    const editor = screen.getByRole("textbox", { name: "Edit card fields as JSON" });
    fireEvent.change(editor, {
      target: { value: JSON.stringify({ ...block, title: "Conflict card" }, null, 2) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save card" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Chat revision conflict");
  });
});
