import { render, screen } from "@testing-library/react";

import DeepSpaceMarkdownRenderer from "../app/dashboard/deepspace/_components/DeepSpaceMarkdownRenderer";

describe("DeepSpace markdown streaming", () => {
  it("renders completed Markdown structure immediately as live content changes", () => {
    const view = render(
      <DeepSpaceMarkdownRenderer content="Recent AI developments." streaming={true} />,
    );

    view.rerender(
      <DeepSpaceMarkdownRenderer
        content={"Recent AI developments.\n\n### Major research\n\n- **Robotics:** New capability."}
        streaming={true}
      />,
    );

    expect(screen.getByRole("heading", { name: "Major research" })).toBeInTheDocument();
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByText("Robotics:")).toBeInTheDocument();
  });

  it("repairs a heading boundary as soon as its trailing whitespace arrives", () => {
    const view = render(
      <DeepSpaceMarkdownRenderer content="Summary.###" streaming={true} />,
    );

    view.rerender(<DeepSpaceMarkdownRenderer content="Summary.### Live heading" streaming={true} />);

    expect(screen.getByText("Summary.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Live heading" })).toBeInTheDocument();
  });
});
