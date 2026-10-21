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
    const { dom, exposed, invoke } = bootPreload("https://averqel.com/dashboard");
    const titlebar = await waitForTitlebar(dom);
    const buttons = titlebar.querySelectorAll<HTMLButtonElement>("button");

    expect(Array.from(buttons).map((button) => button.getAttribute("aria-label"))).toEqual([
      "Minimize window",
      "Maximize window",
      "Close window",
    ]);
    expect(titlebar.querySelector('[role="img"]')).not.toBeInTheDocument();
    expect(titlebar.querySelectorAll("img")).toHaveLength(0);
    const shellStyle = dom.window.document.getElementById(
      "averqel-electron-shell-style",
    )?.textContent;
    expect(shellStyle).toContain("html, body");
    expect(shellStyle).toContain("overflow: hidden !important");
    expect(shellStyle).toContain("overflow-y: auto !important");
    expect(shellStyle).not.toContain("averqel-electron-wordmark");
    expect(
      dom.window.document.documentElement.style.getPropertyValue("--averqel-desktop-chrome-height"),
    ).toBe("40px");
    expect(invoke).toHaveBeenCalledWith("window:is-maximized");
    expect(exposed.electron).not.toHaveProperty("workspace");
    buttons[0]?.click();
    buttons[1]?.click();
    buttons[2]?.click();
    await vi.waitFor(() => {
      expect(invoke).toHaveBeenCalledWith("window:minimize");
      expect(invoke).toHaveBeenCalledWith("window:toggle-maximize");
      expect(invoke).toHaveBeenCalledWith("window:close");
    });
    const legacyBridge = exposed.electron as {
      window: { hide: () => Promise<unknown> };
    };
    await legacyBridge.window.hide();
    expect(invoke).toHaveBeenLastCalledWith("window:close");
    dom.window.close();
  });

  it("does not add secondary workspace chrome to the AverQel window", async () => {
    const { dom } = bootPreload("https://averqel.com/");
    await waitForTitlebar(dom);

    expect(
      dom.window.document.getElementById("averqel-electron-neosis-return-strip"),
    ).not.toBeInTheDocument();
    dom.window.close();
  });
});
