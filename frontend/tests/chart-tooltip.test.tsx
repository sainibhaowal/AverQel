import { fireEvent, render, screen } from "@testing-library/react";

import ChartBlock from "../app/dashboard/query/_components/ChartBlock";

describe("chart tooltip", () => {
  it("uses readable rounded-rectangle controls for the chat chart toolbar", () => {
    render(
      <ChartBlock
        block={{
          id: "styled-chart",
          type: "chart",
          chart_type: "line",
          series: [{ label: "Revenue", value: 12 }],
        }}
        onSaveArtifact={vi.fn()}
      />,
    );

    for (const name of ["Download chart data", "Save chart artifact", "Edit data"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toHaveClass("visual-block-action", "rounded-lg");
      expect(button).not.toHaveClass("rounded-full", "theme-chip");
    }

    fireEvent.click(screen.getByRole("button", { name: "Edit data" }));
    expect(screen.getByRole("button", { name: "Done" })).toHaveClass("visual-block-action--active");
  });

  it("uses the shared theme-aware rounded tooltip surface", async () => {
    const svgPrototype = SVGSVGElement.prototype;
    const originalCreateSvgPoint = Object.getOwnPropertyDescriptor(svgPrototype, "createSVGPoint");
    const originalGetScreenCtm = Object.getOwnPropertyDescriptor(svgPrototype, "getScreenCTM");
    const originalGetBoundingClientRect = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    );
    const svgPoint = {
      x: 0,
      y: 0,
      matrixTransform: () => ({ x: 120, y: 120 }),
    };
    const rect = (left: number, top: number, width: number, height: number) =>
      ({
        x: left,
        y: top,
        left,
        top,
        right: left + width,
        bottom: top + height,
        width,
        height,
        toJSON: () => ({}),
      }) as DOMRect;

    Object.defineProperty(svgPrototype, "createSVGPoint", {
      configurable: true,
      value: () => svgPoint,
    });
    Object.defineProperty(svgPrototype, "getScreenCTM", {
      configurable: true,
      value: () => ({}),
    });
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value: function (this: HTMLElement) {
        if (this.hasAttribute("data-chart-tooltip-boundary")) return rect(100, 100, 300, 200);
        if (this.getAttribute("role") === "tooltip") return rect(0, 0, 160, 80);
        return originalGetBoundingClientRect?.value?.call(this) ?? rect(0, 0, 0, 0);
      },
    });

    try {
      const { container } = render(
        <ChartBlock
          block={{
            id: "chart-1",
            type: "chart",
            chart_type: "line",
            series: [
              { label: "First", value: 3 },
              { label: "Second", value: 5 },
            ],
          }}
        />,
      );

      const chartSvg = container.querySelector('svg[role="img"]');
      const points = container.querySelectorAll("g.cursor-pointer");
      const firstPoint = points[0];
      expect(firstPoint).not.toBeNull();
      fireEvent.mouseEnter(firstPoint!);

      const tooltip = await screen.findByRole("tooltip");
      expect(tooltip).toHaveClass("averqel-tooltip-surface", "rounded-xl");
      expect(tooltip.style.left).toBe("8px");
      expect(tooltip.style.top).toBe("32px");
      expect(tooltip).toHaveTextContent("First");
      expect(tooltip).toHaveTextContent("Value:");

      fireEvent.mouseLeave(firstPoint!);
      fireEvent.mouseEnter(points[1]!);
      expect(screen.getByRole("tooltip")).toBe(tooltip);
      expect(tooltip).toHaveTextContent("Second");
      expect(container.querySelector('svg[role="img"]')).toBe(chartSvg);
    } finally {
      if (originalCreateSvgPoint)
        Object.defineProperty(svgPrototype, "createSVGPoint", originalCreateSvgPoint);
      else Reflect.deleteProperty(svgPrototype, "createSVGPoint");

      if (originalGetScreenCtm)
        Object.defineProperty(svgPrototype, "getScreenCTM", originalGetScreenCtm);
      else Reflect.deleteProperty(svgPrototype, "getScreenCTM");

      if (originalGetBoundingClientRect)
        Object.defineProperty(
          HTMLElement.prototype,
          "getBoundingClientRect",
          originalGetBoundingClientRect,
        );
      else Reflect.deleteProperty(HTMLElement.prototype, "getBoundingClientRect");
    }
  });

  it("updates the visual data when a user edits a point", () => {
    render(
      <ChartBlock
        block={{
          id: "editable-chart",
          type: "chart",
          chart_type: "bar",
          series: [
            { label: "First", value: 3 },
            { label: "Second", value: 5 },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit data" }));
    const valueInput = screen.getByRole("spinbutton", { name: "Chart point 1 value" });
    fireEvent.change(valueInput, { target: { value: "42" } });

    expect(valueInput).toHaveValue(42);
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
  });

  it("centers single-series bars in category slots and anchors them at zero", () => {
    const { container } = render(
      <ChartBlock
        block={{
          id: "aligned-bars",
          type: "chart",
          chart_type: "bar",
          series: [
            { label: "Negative", value: -5 },
            { label: "Peak", value: 10 },
            { label: "Mid", value: 5 },
          ],
        }}
      />,
    );

    const svg = container.querySelector('svg[role="img"]');
    const bars = Array.from(svg?.querySelectorAll("rect") ?? []);
    expect(bars).toHaveLength(3);
    expect(svg?.querySelectorAll("circle")).toHaveLength(0);

    const centers = bars.map(
      (bar) => Number(bar.getAttribute("x")) + Number(bar.getAttribute("width")) / 2,
    );
    expect(centers[0]).toBeCloseTo(154.17, 1);
    expect(centers[1]).toBeCloseTo(352.5, 1);
    expect(centers[2]).toBeCloseTo(550.83, 1);

    const zeroBaseline = 30 + 220 - (5 / 15) * 220;
    expect(Number(bars[0].getAttribute("y"))).toBeCloseTo(zeroBaseline, 1);
    expect(Number(bars[0].getAttribute("height"))).toBeCloseTo(250 - zeroBaseline, 1);
    expect(Number(bars[1].getAttribute("y"))).toBeCloseTo(30, 1);
    expect(Number(bars[1].getAttribute("height"))).toBeCloseTo(zeroBaseline - 30, 1);
    expect(Number(bars[2].getAttribute("y"))).toBeCloseTo(103.33, 1);
    expect(Number(bars[2].getAttribute("height"))).toBeCloseTo(73.33, 1);
  });

  it("keeps grouped bars centered inside each category", () => {
    const { container } = render(
      <ChartBlock
        block={{
          id: "grouped-aligned-bars",
          type: "chart",
          chart_type: "bar",
          series: [],
          series_groups: [
            {
              name: "Actual",
              points: [
                { label: "Q1", value: -4 },
                { label: "Q2", value: 7 },
              ],
            },
            {
              name: "Plan",
              points: [
                { label: "Q1", value: 5 },
                { label: "Q2", value: 6 },
              ],
            },
          ],
        }}
      />,
    );

    const svg = container.querySelector('svg[role="img"]');
    const bars = Array.from(svg?.querySelectorAll("rect") ?? []);
    expect(bars).toHaveLength(4);
    const centers = bars.map(
      (bar) => Number(bar.getAttribute("x")) + Number(bar.getAttribute("width")) / 2,
    );
    expect((centers[0] + centers[2]) / 2).toBeCloseTo(199, 1);
    expect((centers[1] + centers[3]) / 2).toBeCloseTo(481, 1);
    expect(centers[0]).toBeLessThan(centers[2]);
    expect(centers[1]).toBeLessThan(centers[3]);

    const categoryLabels = Array.from(svg?.querySelectorAll("text") ?? []).filter((label) =>
      ["Q1", "Q2"].includes(label.textContent ?? ""),
    );
    expect(Number(categoryLabels[0].getAttribute("x"))).toBeCloseTo(199, 1);
    expect(Number(categoryLabels[1].getAttribute("x"))).toBeCloseTo(481, 1);

    const zeroBaseline = 34 + 232 - (4 / 11) * 232;
    expect(Number(bars[0].getAttribute("y"))).toBeCloseTo(zeroBaseline, 1);
    expect(Number(bars[0].getAttribute("height"))).toBeCloseTo(266 - zeroBaseline, 1);
  });

  it("renders and persists named multi-series edits with a secondary axis and annotation", () => {
    const onChange = vi.fn();
    render(
      <ChartBlock
        block={{
          id: "multi-series",
          type: "chart",
          chart_type: "bar",
          series: [],
          series_groups: [
            { name: "Revenue", points: [{ label: "Q1", value: 42 }] },
            {
              name: "Latency",
              axis: "right",
              points: [{ label: "Q1", value: 120 }],
            },
          ],
          secondary_y_label: "milliseconds",
          annotations: [{ label: "Launch", x: "Q1" }],
        }}
        onChange={onChange}
      />,
    );

    expect(screen.getByRole("button", { name: "Revenue" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Latency · right axis" })).toBeInTheDocument();
    expect(screen.getByText("Secondary axis: milliseconds")).toBeInTheDocument();
    expect(screen.getByText("Launch")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit data" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Series 1 name" }), {
      target: { value: "Bookings" },
    });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Series 2 point 1 value" }), {
      target: { value: "140" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        revision: 1,
        series_groups: expect.arrayContaining([
          expect.objectContaining({ name: "Bookings" }),
          expect.objectContaining({
            name: "Latency",
            points: [expect.objectContaining({ value: 140 })],
          }),
        ]),
      }),
    );
  });
});
