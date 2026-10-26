import { expect, test } from "@playwright/test";

test("light palette keeps readable contrast and maps legacy cool utilities to AverQel green", async ({
  page,
}) => {
  await page.goto("/auth/login");
  await page.evaluate(() => {
    localStorage.setItem("averqel-theme", "light");
    window.dispatchEvent(new Event("averqel-theme-change"));
  });
  await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);

  const palette = await page.evaluate(() => {
    const root = document.documentElement;
    const styles = getComputedStyle(root);
    const probes = document.createElement("div");
    probes.innerHTML = `
      <span id="cool-text" class="text-sky-300">Accent</span>
      <span id="muted-text" class="text-slate-400">Muted</span>
      <button id="solid-action" class="bg-blue-600 text-white">
        <span id="solid-action-label" class="text-white">Action</span>
      </button>
      <div id="surface-card" class="bg-white"></div>
      <div id="cool-border" class="border border-cyan-300/20"></div>
    `;
    document.body.append(probes);

    const getColor = (id: string, property: "color" | "backgroundColor" | "borderTopColor") =>
      getComputedStyle(document.getElementById(id)!)[property];
    const normalize = (value: string) => {
      const probe = document.createElement("span");
      probe.style.color = value;
      document.body.append(probe);
      const color = getComputedStyle(probe).color;
      probe.remove();
      return color;
    };

    return {
      background: styles.getPropertyValue("--background").trim(),
      surface: styles.getPropertyValue("--surface-0").trim(),
      foreground: styles.getPropertyValue("--foreground").trim(),
      body: styles.getPropertyValue("--text-body").trim(),
      muted: styles.getPropertyValue("--text-muted").trim(),
      backgroundColor: normalize("var(--background)"),
      primary: normalize("hsl(var(--primary))"),
      coolInk: normalize("var(--light-cool-ink)"),
      coolBorder: getComputedStyle(document.getElementById("cool-border")!).borderTopColor,
      surfaceCard: getColor("surface-card", "backgroundColor"),
      coolText: getColor("cool-text", "color"),
      mutedText: getColor("muted-text", "color"),
      solidAction: getColor("solid-action", "backgroundColor"),
      solidActionText: getColor("solid-action-label", "color"),
    };
  });

  const contrast = (foreground: string, background: string) => {
    const luminance = (value: string) => {
      const channels = value
        .match(/[\d.]+/g)
        ?.slice(0, 3)
        .map(Number);
      if (!channels || channels.length !== 3) throw new Error(`Unexpected color: ${value}`);
      const [r, g, b] = channels.map((channel) => {
        const sRGB = channel / 255;
        return sRGB <= 0.04045 ? sRGB / 12.92 : ((sRGB + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
    return (values[0] + 0.05) / (values[1] + 0.05);
  };

  const colorProbe = await page.evaluate(() => {
    const toRGB = (value: string) => {
      const element = document.createElement("span");
      element.style.color = value;
      document.body.append(element);
      const color = getComputedStyle(element).color;
      element.remove();
      return color;
    };
    return {
      foreground: toRGB("var(--foreground)"),
      body: toRGB("var(--text-body)"),
      muted: toRGB("var(--text-muted)"),
      surface: toRGB("var(--surface-0)"),
      background: toRGB("var(--background)"),
      white: "rgb(255, 255, 255)",
    };
  });

  expect(contrast(colorProbe.foreground, colorProbe.background)).toBeGreaterThanOrEqual(7);
  expect(contrast(colorProbe.body, colorProbe.surface)).toBeGreaterThanOrEqual(7);
  expect(contrast(colorProbe.muted, colorProbe.surface)).toBeGreaterThanOrEqual(4.5);
  expect(contrast(colorProbe.white, palette.primary)).toBeGreaterThanOrEqual(4.5);
  expect(palette.background).not.toBe("#ffffff");
  expect(palette.coolText).toBe(palette.coolInk);
  expect(palette.solidAction).toBe(palette.primary);
  expect(palette.solidActionText).toBe(colorProbe.white);
  expect(palette.surfaceCard).toBe(colorProbe.surface);
  expect(palette.coolBorder).toBe("rgba(31, 92, 59, 0.34)");
});

test("light palette overrides do not alter the existing dark palette", async ({ page }) => {
  await page.goto("/auth/login");
  await page.evaluate(() => document.documentElement.classList.add("dark"));
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);

  const darkPalette = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const probe = document.createElement("span");
    probe.className = "text-cyan-300";
    document.body.append(probe);
    const cyanText = getComputedStyle(probe).color;
    probe.remove();
    return {
      background: root.getPropertyValue("--background").trim(),
      accent: root.getPropertyValue("--accent").trim(),
      accentCyan: root.getPropertyValue("--accent-cyan").trim(),
      info: root.getPropertyValue("--info").trim(),
      borderSubtle: root.getPropertyValue("--border-subtle").trim(),
      cyanText,
    };
  });

  expect(darkPalette.background).toBe("#0b0f0c");
  expect(darkPalette.accent).toBe("45, 93%, 47%");
  expect(darkPalette.accentCyan).toBe("#7fd5bd");
  expect(darkPalette.info).toBe("188, 84%, 38%");
  expect(darkPalette.borderSubtle).toContain("15, 118, 110");
  expect(darkPalette.cyanText).not.toBe("rgb(21, 88, 61)");
});
