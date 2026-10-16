import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import DeepSpaceWormhole from "../app/components/ui/DeepSpaceWormhole";

const SOURCE = "/AverQel Logo/deepspace-wormhole-aperture.svg";

vi.mock("next/image", () => ({
  default: (props: {
    src: string;
    alt?: string;
    width?: number;
    height?: number;
    className?: string;
    unoptimized?: boolean;
  }) => {
    const imageProps = { ...props };
    delete imageProps.unoptimized;
    return (
      <span
        data-testid="wormhole-layer"
        data-src={imageProps.src}
        className={imageProps.className}
        data-width={imageProps.width}
        data-height={imageProps.height}
      />
    );
  },
}));

it("uses only the supplied wormhole artwork for the response animation", () => {
  const assetPath = resolve(process.cwd(), "public/AverQel Logo/deepspace-wormhole-aperture.svg");
  expect(existsSync(assetPath)).toBe(true);
  expect(readFileSync(assetPath, "utf8")).toContain('viewBox="0 0 120 120"');

  const { container } = render(<DeepSpaceWormhole size={24} />);
  const layers = [...container.querySelectorAll('[data-testid="wormhole-layer"]')];

  expect(layers).toHaveLength(1);
  expect(layers.every((layer) => layer.getAttribute("data-src") === SOURCE)).toBe(true);
  expect(layers[0]).toHaveClass("deepspace-wormhole__asset");
  expect(container.firstElementChild).toHaveStyle({ width: "24px", height: "24px" });
});

it("keeps one rotating asset and removes the old dot indicator", () => {
  const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");
  const thread = readFileSync(
    resolve(process.cwd(), "app/dashboard/deepspace/_components/DeepSpaceThread.tsx"),
    "utf8",
  );

  expect(css).toContain(".deepspace-wormhole__asset");
  expect(css).toContain("animation: deepspace-wormhole-rotate 2.8s linear infinite");
  expect(css).not.toContain(".deepspace-wormhole__core");
  expect(css).not.toContain(".deepspace-wormhole__orbit");
  expect(css).not.toContain(".deepspace-response-dot");
  expect(css).not.toContain("deepspace-welcome-dot-orbit");
  expect(thread).toContain("ResponseLoadingIndicator");
  expect(thread).not.toContain("ResponseLoadingDots");
  expect(thread).not.toContain("deepspace-response-dot");
});
