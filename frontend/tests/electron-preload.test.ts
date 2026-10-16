import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import { JSDOM } from "jsdom";
import { describe, expect, it, vi } from "vitest";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const preloadSource = readFileSync(
  resolve(repositoryRoot, "applications/desktop/electron/preload.cjs"),
  "utf-8",
);

function bootPreload(url: string) {
  const dom = new JSDOM(
    "<!doctype html><html><head></head><body><div id='app'></div></body></html>",
    {
      url,
    },
  );
  const exposed: Record<string, unknown> = {};
  const invoke = vi.fn(async (channel: string) => {
    if (channel === "window:is-maximized") return false;
    return { ok: true };
  });
  runInNewContext(preloadSource, {
    clearTimeout,
    document: dom.window.document,
    history: dom.window.history,
    location: dom.window.location,
    MutationObserver: dom.window.MutationObserver,
    process: { platform: "linux" },
    queueMicrotask,
    require: (name: string) => {
      if (name !== "electron") throw new Error(`Unexpected preload import: ${name}`);
      return {
        contextBridge: {
          exposeInMainWorld: (key: string, value: unknown) => {
            exposed[key] = value;
          },
        },
        ipcRenderer: { invoke },
      };
    },
    setTimeout,
    URL,
    URLSearchParams,
    window: dom.window,
  });
  dom.window.dispatchEvent(new dom.window.Event("DOMContentLoaded"));

  return { dom, exposed, invoke };
}

async function waitForTitlebar(dom: JSDOM): Promise<HTMLElement> {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const titlebar = dom.window.document.querySelector<HTMLElement>("#averqel-electron-titlebar");
    if (titlebar) return titlebar;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  }
  throw new Error("Electron window controls were not mounted.");
}

describe("frameless Electron shell", () => {
  it("shows only minimize, maximize, and close controls in the top strip", async () => {
    const { dom, invoke } = bootPreload("https://averqel.com/dashboard");
    const titlebar = await waitForTitlebar(dom);
    const buttons = titlebar.querySelectorAll<HTMLButtonElement>("button");

    expect(Array.from(buttons).map((button) => button.getAttribute("aria-label"))).toEqual([
      "Minimize window",
      "Maximize window",
      "Close window",
    ]);
    const brand = titlebar.querySelector<HTMLElement>('[role="img"]');
    expect(brand).toHaveAttribute("aria-label", "AverQel");
    expect(brand).toHaveStyle({ gap: "6px" });
    const icon = titlebar.querySelector<HTMLImageElement>('img[alt="AverQel icon"]');
    expect(icon).toHaveAttribute("src", "https://averqel.com/brand/AverQel_Icon.svg");
    expect(icon).toHaveAttribute("width", "38");
    const wordmark = titlebar.querySelector<HTMLImageElement>('img[alt="AverQel"]');
    expect(wordmark).toHaveAttribute("src", "https://averqel.com/brand/AverQel_Text.svg");
    expect(wordmark).toHaveAttribute("width", "124");
    expect(
      dom.window.document.getElementById("averqel-electron-shell-style")?.textContent,
    ).toContain("transform: translateY(1px)");
    expect(
      dom.window.document.documentElement.style.getPropertyValue("--averqel-desktop-chrome-height"),
    ).toBe("40px");
    expect(invoke).toHaveBeenCalledWith("window:is-maximized");
    buttons[0]?.click();
    buttons[1]?.click();
    buttons[2]?.click();
    await vi.waitFor(() => {
      expect(invoke).toHaveBeenCalledWith("window:minimize");
      expect(invoke).toHaveBeenCalledWith("window:toggle-maximize");
      expect(invoke).toHaveBeenCalledWith("window:close");
    });
    dom.window.close();
  });

  it("puts the AverQel return control in the NeoSIS page, outside the window controls", async () => {
    const { dom, invoke } = bootPreload("http://127.0.0.1:43127/?token=test-token");
    const titlebar = await waitForTitlebar(dom);
    const button = dom.window.document.querySelector<HTMLButtonElement>(
      "#averqel-electron-neosis-return-strip button",
    );

    expect(button?.getAttribute("aria-label")).toBe("Return to AverQel dashboard");
    expect(titlebar.querySelectorAll("button")).toHaveLength(3);
    expect(titlebar.querySelector('img[alt="AverQel icon"]')).toHaveAttribute(
      "src",
      "http://127.0.0.1:43127/brand/AverQel_Icon.svg",
    );
    expect(titlebar.querySelector('img[alt="AverQel"]')).toHaveAttribute(
      "src",
      "http://127.0.0.1:43127/brand/AverQel_Text.svg",
    );
    const wordmark = titlebar.querySelector<HTMLImageElement>('img[alt="AverQel"]');
    wordmark?.dispatchEvent(new dom.window.Event("error"));
    expect(wordmark).toHaveAttribute("src", "https://averqel.com/brand/AverQel_Text.svg");
    button?.click();
    await vi.waitFor(() => expect(invoke).toHaveBeenCalledWith("workspace:open-averqel"));
    dom.window.close();
  });

  it("exposes the packaged NeoSIS availability check through the preload bridge", async () => {
    const { dom, exposed, invoke } = bootPreload("https://averqel.com/");
    const electron = exposed.electron as {
      workspace: { neosisAvailable: () => Promise<boolean> };
    };

    await electron.workspace.neosisAvailable();

    expect(invoke).toHaveBeenCalledWith("workspace:neosis-available");
    dom.window.close();
  });
});
