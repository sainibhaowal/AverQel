import { fireEvent, render, screen } from "@testing-library/react";

import ProfileAvatar from "../app/components/profile/ProfileAvatar";

describe("ProfileAvatar", () => {
  it("shows the profile photo without a colored tile, shadow, or green ring", () => {
    const { container } = render(
      <ProfileAvatar
        avatar="data:image/png;base64,dGVzdA=="
        displayName="AverQel User"
        className="h-10 w-10 rounded-xl"
      />,
    );

    const avatarImage = container.querySelector("img");
    const avatarShell = container.querySelector("span");

    expect(avatarImage).toHaveAttribute("src", "data:image/png;base64,dGVzdA==");
    expect(avatarShell).toHaveClass("overflow-hidden", "text-foreground");
    expect(avatarShell).not.toHaveClass("bg-gradient-to-br", "shadow-sm", "ring-1");
  });

  it("keeps the initials fallback visible without adding a background", () => {
    render(<ProfileAvatar displayName="AverQel User" />);

    expect(screen.getByText("AU")).toHaveClass("text-[0.72em]");
    expect(screen.getByText("AU").parentElement).not.toHaveClass("bg-gradient-to-br");
  });

  it("falls back to initials if the profile photo fails to load", () => {
    const { container } = render(
      <ProfileAvatar avatar="https://example.test/avatar.png" displayName="AverQel User" />,
    );

    fireEvent.error(container.querySelector("img")!);

    expect(screen.getByText("AU")).toBeInTheDocument();
    expect(screen.getByText("AU").parentElement).not.toHaveClass("bg-gradient-to-br", "ring-1");
  });
});
