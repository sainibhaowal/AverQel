import { render, screen } from "@testing-library/react";

import DeepSpaceMarkdownRenderer from "../app/dashboard/deepspace/_components/DeepSpaceMarkdownRenderer";

describe("DeepSpace markdown streaming", () => {
  it("renders headings and emphasis before the response finishes", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming
        content={"## Live heading\n\nThis is **already visible** while tokens are arriving."}
      />,
    );

    expect(screen.getByText("Live heading").tagName.toLowerCase()).toBe("h2");
    expect(screen.getByText("already visible").tagName.toLowerCase()).toBe("strong");
  });

  it("renders streamed table rows instead of waiting for completion", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming
        content={"| Name | Score |\n| --- | --- |\n| Alpha | 92 |\n| Beta | 88 |"}
      />,
    );

    expect(screen.getByText("Name").tagName.toLowerCase()).toBe("th");
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("renders compact provider tables as a real table while streaming", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming
        content={
          "| Game | Release | Genre | |------|---------| | **Avowed** | Feb 18, 2025 | RPG (Game Pass) | | **Monster Hunter Wilds** | Feb 28, 2025 | Action |"
        }
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Avowed")).toBeInTheDocument();
    expect(screen.getByText("Monster Hunter Wilds")).toBeInTheDocument();
  });

  it("renders compact science comparison tables after history reload", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming={false}
        content={
          "| Feature | Positron + Electron | Antiproton + Proton | |--------------------|--------------------| | Complexity | Simple — both are fundamental | Complex — both are composite | | Products | Clean: 2 gamma rays | Messy: pions, kaons, gamma rays | | Energy | 1.022 MeV total | ~1.88 GeV total | | Real-world use | PET scans (medical imaging) | Cancer therapy research, physics experiments |"
        }
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Positron + Electron")).toBeInTheDocument();
    expect(screen.getByText("Cancer therapy research, physics experiments")).toBeInTheDocument();
  });

  it("recovers provider tables with a short separator and joined rows", () => {
    render(
      <DeepSpaceMarkdownRenderer
        streaming={false}
        content={
          "| Application | Status | Impact | |-------------|--------|\n| **PET Imaging** | ✅ Widely used | Detects cancer, Alzheimer's, heart disease | | **Antiproton Therapy** | 🔬 Experimental | Potentially 4-5x more effective than protons | | **Targeted Radionuclides** | 🔬 Research | Next-gen cancer treatments | | **FLASH Therapy** | 🏥 Clinical trials | Ultra-precise radiation delivery |"
        }
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("PET Imaging")).toBeInTheDocument();
    expect(screen.getByText("FLASH Therapy")).toBeInTheDocument();
  });

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
    const view = render(<DeepSpaceMarkdownRenderer content="Summary.###" streaming={true} />);

    view.rerender(
      <DeepSpaceMarkdownRenderer content="Summary.### Live heading" streaming={true} />,
    );

    expect(screen.getByText("Summary.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Live heading" })).toBeInTheDocument();
  });
});
