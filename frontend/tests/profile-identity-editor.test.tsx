import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProfileIdentityEditor from "../app/components/profile/ProfileIdentityEditor";

describe("ProfileIdentityEditor", () => {
  it("saves a trimmed display name and one of the preset avatars", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ProfileIdentityEditor displayName="" onSave={onSave} />);

    expect(screen.getAllByRole("button", { name: /avatar$/i })).toHaveLength(12);
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "  Ravi  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Orbit avatar" }));
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    const saved = onSave.mock.calls[0][0] as { display_name: string; avatar: string };
    expect(saved.display_name).toBe("Ravi");
    expect(saved.avatar).toMatch(/^data:image\/svg\+xml;charset=utf-8,/);
  });

  it("rejects non-image uploads before saving", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ProfileIdentityEditor onSave={onSave} />);
    const input = screen.getByLabelText("Upload photo") as HTMLInputElement;
    const invalidFile = new File(["not an image"], "notes.txt", { type: "text/plain" });

    fireEvent.change(input, { target: { files: [invalidFile] } });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Choose a JPEG, PNG, WebP, or AVIF photo.",
    );
    expect(onSave).not.toHaveBeenCalled();
  });

  it("keeps labels unique when profile editors appear together", () => {
    render(
      <>
        <ProfileIdentityEditor onSave={vi.fn()} />
        <ProfileIdentityEditor onSave={vi.fn()} />
      </>,
    );
    const fields = screen.getAllByLabelText("Display name");
    expect(fields).toHaveLength(2);
    expect(fields[0].id).not.toBe(fields[1].id);
  });

  it("does not resend an unchanged legacy avatar when only the name changes", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <ProfileIdentityEditor
        displayName="Existing name"
        avatar="http://legacy-avatar.example.test/profile.png"
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "New name" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    expect(onSave).toHaveBeenCalledWith({ display_name: "New name" });
  });
});
