import { fireEvent, render, screen } from "@testing-library/react";

import ChartBlock from "../app/dashboard/query/_components/ChartBlock";

describe("chart tooltip", () => {
  it("uses the shared theme-aware rounded tooltip surface", async () => {
    const svgPrototype = SVGSVGElement.prototype;
    const originalCreateSvgPoint = Object.getOwnPropertyDescriptor(svgPrototype, "createSVGPoint");
    const originalGetScreenCtm = Object.getOwnPropertyDescriptor(svgPrototype, "getScreenCTM");
    const svgPoint = {
      x: 0,
      y: 0,
      matrixTransform: () => ({ x: 120, y: 120 }),
    };

    Object.defineProperty(svgPrototype, "createSVGPoint", {
      configurable: true,
      value: () => svgPoint,
    });
    Object.defineProperty(svgPrototype, "getScreenCTM", {
      configurable: true,
      value: () => ({}),
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

      const firstPoint = container.querySelector("g.cursor-pointer");
      expect(firstPoint).not.toBeNull();
      fireEvent.mouseEnter(firstPoint!);

      const tooltip = await screen.findByRole("tooltip");
      expect(tooltip).toHaveClass("averqel-tooltip-surface", "rounded-xl");
      expect(tooltip).toHaveTextContent("First");
      expect(tooltip).toHaveTextContent("Value:");
    } finally {
      if (originalCreateSvgPoint)
        Object.defineProperty(svgPrototype, "createSVGPoint", originalCreateSvgPoint);
      else Reflect.deleteProperty(svgPrototype, "createSVGPoint");

      if (originalGetScreenCtm)
        Object.defineProperty(svgPrototype, "getScreenCTM", originalGetScreenCtm);
      else Reflect.deleteProperty(svgPrototype, "getScreenCTM");
    }
  });
});
